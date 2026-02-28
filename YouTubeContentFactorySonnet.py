# -*- coding: utf-8 -*-
"""
YouTube Content Factory (Claude 3.5 Sonnet - Safe Switch v2)
------------------------------------------------------------
預設使用 Amazon Bedrock 的 Anthropic Claude 3.5 Sonnet（boto3 / Converse API）進行段落翻譯與語意處理。
修法 A：移除 additionalModelRequestFields，僅保留標準 inferenceConfig；修正 topP 大小寫。
新增：ENABLE_GEMINI_FALLBACK（預設 False），關閉 Gemini 備援嘗試。
強化：_process_with_sonnet() 的 JSON 解析防護，遇到前置敘述或非純 JSON 會自動抽出陣列再解析；
解析失敗時以保守結構回退，避免整批中止。

安全性：不硬編 API Key；若需 Gemini，請以環境變數 GEMINI_API_KEY 提供金鑰。
"""

import os
import json
import re
import whisper
import ffmpeg
import yt_dlp
import google.generativeai as genai
import shutil
from botocore.config import Config
import boto3

# --- 全域設定 ---
def load_api_key(key_file="GEMINI_API_KEY.txt"):
    """
    從檔案讀取 Gemini API Key（與 YouTubeContentFactory.py 保持一致）
    
    Args:
        key_file: API Key 檔案路徑，預設為 GEMINI_API_KEY.txt
        
    Returns:
        API Key 字串，或 None 如果檔案不存在
    """
    try:
        if os.path.exists(key_file):
            with open(key_file, 'r', encoding='utf-8') as f:
                api_key = f.read().strip()
                if api_key and not api_key.startswith("您的"):
                    return api_key
        # 備帶：檢查環境變數
        env_key = os.getenv("GEMINI_API_KEY", "")
        if env_key:
            return env_key
        print(f"⚠️ 警告: 找不到有效的 API Key 檔案 ({key_file}) 或環境變數 GEMINI_API_KEY")
        return None
    except Exception as e:
        print(f"❌ 讀取 API Key 檔案時出錯: {e}")
        return None

def load_model_config(config_file="model_config.json"):
    """
    從外部 JSON 檔案讀取模型配置（與 YouTubeContentFactory.py 保持一致）
    
    Args:
        config_file: 模型配置檔案路徑，預設為 model_config.json
        
    Returns:
        模型配置字典，或 {} 如果檔案不存在
    """
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                return config_data.get('model_configs', {})
        print(f"⚠️  警告: 找不到模型配置檔案 ({config_file})")
        return {}
    except json.JSONDecodeError as e:
        print(f"❌ 解析模型配置檔案時出錯: {e}")
        return {}
    except Exception as e:
        print(f"❌ 讀取模型配置檔案時出錯: {e}")
        return {}

OUTPUT_DIR = "./app_assets"
TEMP_DIR = "./temp_downloads"

# 開關：是否啟用 Gemini 備援（預設 False）
ENABLE_GEMINI_FALLBACK = os.getenv("ENABLE_GEMINI_FALLBACK", "false").lower() == "false"

# 建立必要的資料夾
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# 設定 Gemini（優先從檔案讀取，次選環境變數，避免金鑰外洩）
GEMINI_API_KEY = load_api_key()
MODEL_CONFIG = load_model_config()
if GEMINI_API_KEY and ENABLE_GEMINI_FALLBACK:
    genai.configure(api_key=GEMINI_API_KEY)


# --- Amazon Bedrock：Anthropic Claude 3.5 Sonnet 客戶端 ---
class BedrocksonnetClient:
    def __init__(self, region_priority=("ap-southeast-1", "us-east-1")):
        self.region_priority = region_priority
        self.model_id_primary = "amazon.nova-lite-v1:0"    ### "anthropic.claude-3-5-sonnet-20240620-v1:0"
        self.client = None
        self.current_region = None
        self._init_client()

    def _init_client(self):
        last_error = None
        for region in self.region_priority:
            try:
                self.client = boto3.client(
                    "bedrock-runtime",
                    region_name=region,
                    config=Config(connect_timeout=3600, read_timeout=3600, retries={"max_attempts": 1})
                )
                self.current_region = region
                return
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(f"Bedrock client init failed: {last_error}")

    def _model_id(self):
        return self.model_id_primary

    def converse_sonnet_lite_text(self, system_text, user_text,
                                max_tokens=800, temperature=0.2, top_p=0.9):
        """修法 A：僅保留 inferenceConfig（移除 additionalModelRequestFields）"""
        resp = self.client.converse(
            modelId=self._model_id(),
            system=[{"text": system_text}],
            messages=[{"role": "user", "content": [{"text": user_text}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature, "topP": top_p}
        )
        out = resp.get("output", {})
        msg = (out.get("message") or {})
        content = msg.get("content") or []
        text = ""
        if isinstance(content, list):
            for blk in content:
                if "text" in blk:
                    text = blk["text"]
                    break
        usage = resp.get("usage", {})
        return {"text": text, "usage": usage, "region": self.current_region}

    def converse_sonnet_lite_vision(self, system_text, user_text, image_bytes, image_format="jpeg",
                                  max_tokens=800, temperature=0.2, top_p=0.9):
        """修法 A：僅保留 inferenceConfig（注意 topP 大小寫），移除 additionalModelRequestFields"""
        resp = self.client.converse(
            modelId=self._model_id(),
            system=[{"text": system_text}],
            messages=[{
                "role": "user",
                "content": [
                    {"text": user_text},
                    {"image": {"format": image_format, "source": {"bytes": image_bytes}}}
                ]
            }],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature, "topP": top_p}
        )
        out = resp.get("output", {})
        msg = (out.get("message") or {})
        content = msg.get("content") or []
        text = ""
        if isinstance(content, list):
            for blk in content:
                if "text" in blk:
                    text = blk["text"]
                    break
        usage = resp.get("usage", {})
        return {"text": text, "usage": usage, "region": self.current_region}


class YouTubeContentFactory:
    def __init__(self, model_size="base", batch_size=5, prefer_model="sonnet_lite"):
        print(f"📡 正在載入 Whisper 模型 ({model_size})...")
        self.model = whisper.load_model(model_size)

        # === 模型路由設定 ===
        self.prefer_model = prefer_model  # "sonnet_lite"（預設 Bedrock）或 "gemini"

        # 保留 Gemini（備援），使用 model_config.json 中最新的模型
        self.model_name = 'Gemma 3 27B'  # 與 YouTubeContentFactory.py 同步為最新模型
        print(f"🧠 備援 Gemini 模型: {self.model_name}")
        if GEMINI_API_KEY and ENABLE_GEMINI_FALLBACK:
            self.gemini_model = genai.GenerativeModel(self.model_name)
            print("✅ Gemini 備援已啟用")
        else:
            self.gemini_model = None
            print("ℹ️ Gemini 備援已禁用")

        # 預設：Bedrock（Amazon Nova Lite）
        print("🧠 預設模型：Amazon Bedrock - Nova Lite (優化版)")
        try:
            self.sonnet = BedrocksonnetClient(region_priority=("ap-southeast-1", "us-east-1"))
            print(f"✅ Bedrock 初始化完成，Region: {self.sonnet.current_region}")
        except Exception as e:
            print(f"⚠️ Bedrock 初始化失敗。將降級至 Gemini。錯誤：{e}")
            if not (GEMINI_API_KEY and ENABLE_GEMINI_FALLBACK):
                print("❌ 無可用備援模型。")
            self.prefer_model = "gemini"

        self.batch_size = batch_size
        print(f"   批次處理大小: {batch_size} 個片段/次")
        print(f"   💡 策略: 優先使用 Amazon Bedrock；遇到錯誤時降級至 Gemini（预设禁用）")

    # --- 只取得 ID 不下載影片 ---
    def _get_video_id(self, url):
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'nocheckcertificate': True,
            'no_check_certificate': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('id')
        except Exception as e:
            print(f"⚠️ 無法取得影片 ID: {e}")
            return None

    def process_url(self, youtube_url):
        print(f"\n🚀 準備處理: {youtube_url}")
        # 1. 檢查：檔案是否已存在？
        video_id = self._get_video_id(youtube_url)
        if not video_id:
            print("❌ 無法取得影片 ID，跳過此連結。")
            return
        expected_json_path = os.path.join(OUTPUT_DIR, f"{video_id}.json")
        if os.path.exists(expected_json_path):
            try:
                with open(expected_json_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                segments = existing_data.get("segments", [])
                needs_translation = any(seg.get("text_zh") == "[無中文翻譯]" for seg in segments)
                if needs_translation:
                    print("🔄 檔案已存在但缺少中文翻譯，開始重新翻譯...")
                    self._retranslate_existing_json(expected_json_path, existing_data)
                    return
                else:
                    print(f"⏭️ 檔案已存在且已完成翻譯（{video_id}.json），跳過處理。")
                    return
            except Exception as e:
                print(f"⚠️ 讀取現有檔案時發生錯誤: {e}")
                print(" 將跳過此檔案，繼續下一個。")
                return

        print("📥 檔案不存在，開始下載影片...")
        # 2. 下載影片
        video_info = self._download_youtube_video(youtube_url)
        if not video_info:
            print("❌ 影片下載失敗，中止處理。")
            return
        video_path = video_info['path']
        video_title = video_info['title']

        # 3. 轉錄 (Whisper)
        audio_path = os.path.join(TEMP_DIR, f"{video_id}.wav")
        self._extract_audio(video_path, audio_path)
        if not os.path.exists(audio_path):
            print("❌ 音訊提取失敗，請檢查電腦是否已安裝 FFmpeg。")
            return
        print("🤖 正在進行 Whisper 語音辨識 (將音訊轉為文字)...")
        result = self.model.transcribe(audio_path, fp16=False, word_timestamps=True)
        raw_segments = result["segments"]

        # 4. 段落翻譯與合併（預設 Claude 3.5 Sonnet；備援由開關控制）
        print("🧠 正在進行段落合併與翻譯（預設 Claude 3.5 Sonnet）...")
        processed_segments = self._process_segments_in_batches(raw_segments)
        if not processed_segments:
            print("⚠️ 模型處理失敗，儲存 Whisper 原始結果以便稍後重新翻譯。")
            processed_segments = [
                {
                    "id": seg.get("id", i),
                    "start_time": seg["start"],
                    "end_time": seg["end"],
                    "text_en": seg["text"].strip(),
                    "text_zh": "[無中文翻譯]",
                    "keywords": [],
                    "words": seg.get("words", [])
                }
                for i, seg in enumerate(raw_segments)
            ]

        # 5. 存檔
        self._save_json_and_files(video_id, video_title, youtube_url, video_path, video_info, processed_segments)
        return

    def _save_json_and_files(self, video_id, video_title, youtube_url, video_path, video_info, processed_segments):
        print("🎵 正在提取 MP3 音訊檔...")
        mp3_filename = f"{video_id}.mp3"
        mp3_path = os.path.join(OUTPUT_DIR, mp3_filename)
        self._extract_audio_mp3(video_path, mp3_path)
        audio_size_mb = 0
        if os.path.exists(mp3_path):
            audio_size_mb = round(os.path.getsize(mp3_path) / (1024 * 1024), 2)
        app_data = {
            "lesson_id": video_id,
            "title": video_title,
            "source_url": youtube_url,
            "video_filename": os.path.basename(video_path),
            "audio_filename": mp3_filename,
            "audio_only_size_mb": audio_size_mb,
            "duration": video_info['duration'],
            "segments": processed_segments
        }
        json_path = os.path.join(OUTPUT_DIR, f"{video_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(app_data, f, ensure_ascii=False, indent=2)
        final_video_path = os.path.join(OUTPUT_DIR, os.path.basename(video_path))
        if os.path.exists(video_path):
            shutil.copy2(video_path, final_video_path)
        print(f" (原始影片已保留在: {video_path})")
        print(f"✅ 處理完成！\n 📄 JSON 檔: {json_path}\n 🎥 影片檔: {final_video_path}\n 🎵 音訊檔: {mp3_path} ({audio_size_mb} MB)")

    def _process_segments_in_batches(self, raw_segments):
        total_segments = len(raw_segments)
        if total_segments <= self.batch_size:
            return self._process_segments_single_batch(raw_segments)
        print(f" 總共 {total_segments} 個片段，將分 {(total_segments + self.batch_size - 1) // self.batch_size} 批次處理")
        all_processed = []
        for i in range(0, total_segments, self.batch_size):
            batch_num = i // self.batch_size + 1
            batch = raw_segments[i:i + self.batch_size]
            print(f" 📦 處理第 {batch_num} 批（{len(batch)} 個片段）...")
            processed_batch = self._process_segments_single_batch(batch)
            if not processed_batch:
                print(f" ❌ 第 {batch_num} 批處理失敗")
                return None
            all_processed.extend(processed_batch)
        print(f" ✅ 所有批次處理完成，共 {len(all_processed)} 個片段")
        return all_processed

    def _process_segments_single_batch(self, raw_segments):
        # 優先 Bedrock（Claude 3.5 Sonnet）；備援由開關控制
        try:
            return self._process_with_sonnet(raw_segments)
        except Exception as e:
            print(f"⚠️ Bedrock 批次失敗：{e}")
            if ENABLE_GEMINI_FALLBACK and self.gemini_model is not None:
                try:
                    return self._process_with_gemini(raw_segments)
                except Exception as e2:
                    print(f"❌ Gemini 備援也失敗：{e2}")
                    return None
            else:
                print("ℹ️ 備援關閉，直接回傳失敗。")
                return None

    def _process_with_sonnet(self, raw_segments):
        # 準備簡化輸入（不帶 words）
        simplified_input = [
            {"id": i, "start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
            for i, seg in enumerate(raw_segments)
        ]
        system_text = "You are a precise bilingual translator for English to Traditional Chinese (Taiwan). Keep structure exactly."
        user_text = (
            "Translate to Traditional Chinese (Taiwan) and keep the exact structure.\n"
            f"Input ({len(simplified_input)} segments):\n{json.dumps(simplified_input, ensure_ascii=False)}\n\n"
            "Output the SAME number of items with fields:\n"
            "[{\"id\": <same>, \"start_time\": <same start>, \"end_time\": <same end>, "
            "\"text_en\": \"<same text>\", \"text_zh\": \"中文翻譯\", \"keywords\": [\"重要英文關鍵字\"]}]\n"
            "Rules:\n- Output EXACTLY the same count.\n- keywords: 1~5 English words representing semantic keys; do NOT translate keywords.\n- Keep all ids, timestamps, and text_en unchanged."
        )

        out = self.sonnet.converse_sonnet_lite_text(system_text=system_text, user_text=user_text)
        raw_text = (out.get("text") or "").strip()

        # 防護：若回覆空或非 JSON，先輸出原始文字並回退保守結果
        if not raw_text:
            print("⚠️ Claude 回覆為空字串，改用保守結構回退。")
            return [
                {
                    "id": s["id"],
                    "start_time": s["start"],
                    "end_time": s["end"],
                    "text_en": s["text"],
                    "text_zh": s["text"],
                    "keywords": [],
                    "words": raw_segments[s["id"]].get("words", [])
                } for s in simplified_input
            ]

        # 去除 markdown fence
        clean = raw_text.replace("```json", "").replace("```", "").strip()

        # 自動抽出第一個 JSON 陣列（處理前置敘述）
        m = re.search(r'(\[.*\])', clean, re.DOTALL)
        if m:
            clean = m.group(1).strip()

        # 解析 JSON；失敗則保守回退
        try:
            parsed_data = json.loads(clean)
        except Exception as e:
            print(f"⚠️ JSON 解析失敗：{e}")
            print("── 原始模型回覆（截斷 500 字） ──")
            print(clean[:500])
            parsed_data = [
                {
                    "id": s["id"],
                    "start_time": s["start"],
                    "end_time": s["end"],
                    "text_en": s["text"],
                    "text_zh": s["text"],
                    "keywords": [],
                    "words": raw_segments[s["id"]].get("words", [])
                } for s in simplified_input
            ]

        # 合併 words（保留 whisper 的逐字時間戳）
        for i, item in enumerate(parsed_data):
            item["words"] = raw_segments[i].get("words", [])

        print(f"✅ Claude 3.5 Sonnet 成功處理 {len(parsed_data)} 個片段，Region={out.get('region')}, Tokens={out.get('usage')}")
        return parsed_data

    def _process_with_gemini(self, raw_segments):
        if not (ENABLE_GEMINI_FALLBACK and self.gemini_model):
            raise RuntimeError("Gemini fallback is disabled or not initialized.")
        simplified_input = [
            {"id": i, "start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
            for i, seg in enumerate(raw_segments)
        ]
        prompt = f"""
Translate to Traditional Chinese (Taiwan). Keep exact structure.
Input ({len(simplified_input)} segments):
{json.dumps(simplified_input, ensure_ascii=False)}
Output ({len(simplified_input)} segments with translations):
[
  {{
    "id": <same>,
    "start_time": <same start>,
    "end_time": <same end>,
    "text_en": "<same text>",
    "text_zh": "中文翻譯",
    "keywords": ["important_word"]
  }}
]
Rules:
- Output EXACTLY {len(simplified_input)} items
- keywords: Select the important words in a sentence; these words represent the semantic key (min 1, max 5), in English
- don't translate keywords.
- Keep all IDs, timestamps, text_en unchanged
"""
        response = self.gemini_model.generate_content(prompt)
        clean_text = (response.text or "").replace("```json", "").replace("```", "").strip()
        parsed_data = json.loads(clean_text)
        for i, item in enumerate(parsed_data):
            item["words"] = raw_segments[i].get("words", [])
        print(f"✅ Gemini 成功處理 {len(parsed_data)} 個片段")
        return parsed_data

    def _retranslate_existing_json(self, json_path, existing_data):
        print("🧠 正在重新翻譯現有片段（預設 Claude 3.5 Sonnet；備援由開關控制）...")
        segments = existing_data.get("segments", [])
        raw_segments_format = [
            {
                "start": seg.get("start_time", seg.get("start", 0)),
                "end": seg.get("end_time", seg.get("end", 0)),
                "text": seg.get("text_en", seg.get("text", "")),
                "words": seg.get("words", [])
            }
            for seg in segments
        ]
        processed_segments = self._process_segments_in_batches(raw_segments_format)
        if processed_segments:
            existing_data["segments"] = processed_segments
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            print(f"✅ 重新翻譯完成！已更新檔案: {json_path}")
        else:
            print("❌ 翻譯失敗，保持原檔案不變。")

    def _download_youtube_video(self, url):
        ydl_opts = {
            'format': 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(TEMP_DIR, '%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return {
                    'id': info['id'],
                    'title': info['title'],
                    'duration': info['duration'],
                    'path': ydl.prepare_filename(info)
                }
        except Exception as e:
            print(f"下載模組錯誤: {e}")
            return None

    def _extract_audio(self, video_path, audio_output_path):
        try:
            (
                ffmpeg
                .input(video_path)
                .output(audio_output_path, acodec='pcm_s16le', ac=1, ar='16k')
                .run(quiet=True, overwrite_output=True)
            )
        except ffmpeg.Error:
            pass

    def _extract_audio_mp3(self, video_path, audio_output_path):
        try:
            (
                ffmpeg
                .input(video_path)
                .output(audio_output_path, acodec='libmp3lame', audio_bitrate='128k', ac=2)
                .run(quiet=True, overwrite_output=True)
            )
            print(" ✅ MP3 音訊檔已生成")
        except ffmpeg.Error as e:
            print(f" ⚠️ MP3 提取失敗: {e}")


# --- 執行區 ---
if __name__ == "__main__":
    factory = YouTubeContentFactory(model_size="base", prefer_model="sonnet_lite")
    
    # 💾 從 JSON 檔案讀取視頻 URL 列表（與 YouTubeContentFactory.py 保持一致）
    video_config_file = "video_urls.json"
    video_urls = []
    
    try:
        if os.path.exists(video_config_file):
            with open(video_config_file, 'r', encoding='utf-8') as f:
                video_data = json.load(f)
                video_urls = video_data
            print(f"✅ 已從 {video_config_file} 讀取 {len(video_urls)} 個視頻")
        else:
            print(f"❌ 找不到視頻配置檔案: {video_config_file}")
            print(f"   請建立 {video_config_file} 並填入視頻 URL")
            video_urls = []
    except json.JSONDecodeError as e:
        print(f"❌ 解析 JSON 檔案出錯: {e}")
        video_urls = []
    except Exception as e:
        print(f"❌ 讀取視頻配置檔案時出錯: {e}")
        video_urls = []
    
    # 處理視頻列表
    if video_urls:
        print(f"\n🎬 準備處理 {len(video_urls)} 個視頻:\n")
        
        for i, video_item in enumerate(video_urls, 1):
            # 支援兩種格式：
            # 1. 直接字符串 URL
            # 2. 包含 url 和 description 的字典
            
            if isinstance(video_item, str):
                url = video_item
                description = "無描述"
            elif isinstance(video_item, dict):
                url = video_item.get('url')
                description = video_item.get('description', '無描述')
            else:
                print(f"⚠️ 跳過無效的視頻項: {video_item}")
                continue
            
            if not url:
                print(f"⚠️ 跳過空的 URL")
                continue
            
            print(f"\n[{i}/{len(video_urls)}] 📺 {description}")
            print(f"    URL: {url}")
            print("-" * 70)
            
            factory.process_url(url)
    else:
        print("⚠️ 沒有視頻要處理。請檢查 video_urls.json 檔案。")
