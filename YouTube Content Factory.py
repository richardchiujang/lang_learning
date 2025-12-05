import os
import json
import whisper
import ffmpeg
import yt_dlp
import google.generativeai as genai
import shutil
from datetime import timedelta

# --- 全域設定 ---
# ⚠️⚠️⚠️ 請在此填入您的 Google Gemini API Key ⚠️⚠️⚠️
GEMINI_API_KEY = "您的_GOOGLE_GEMINI_API_KEY" 

OUTPUT_DIR = "./app_assets"
TEMP_DIR = "./temp_downloads"

# 建立必要的資料夾
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# 設定 Gemini
if "您的_GOOGLE" not in GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

class YouTubeContentFactory:
    def __init__(self, model_size="base", batch_size=15):
        print(f"📡 正在載入 Whisper 模型 ({model_size})...")
        self.model = whisper.load_model(model_size)
        
        # 改用 Gemini 2.0 Flash Lite
        self.model_name = 'gemini-2.5-flash'
        print(f"🧠 設定 AI 模型為: {self.model_name}")
        self.gemini_model = genai.GenerativeModel(self.model_name)
        
        # 批次處理大小（避免單次請求過長）
        self.batch_size = batch_size
        print(f"   批次處理大小: {batch_size} 個片段/次")
        print(f"   💡 策略: Gemini 翻譯 + Whisper words 陣列（用於英文逐字高亮）")

    # --- 🆕 新增方法：只取得 ID 不下載影片 ---
    def _get_video_id(self, url):
        """快速取得影片 ID 以便檢查檔案是否存在"""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True, # 關鍵：設定為 True 表示只抓資訊不下載檔案
            'nocheckcertificate': True,  # 跳過 SSL 憑證驗證
            'no_check_certificate': True,  # 備用選項
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
        
        # --- 1. 優先檢查：檔案是否已存在？ ---
        # 先快速取得 ID (不下載影片)
        video_id = self._get_video_id(youtube_url)
        
        if not video_id:
            print("❌ 無法取得影片 ID，跳過此連結。")
            return

        # 檢查目標 JSON 是否已經在資料夾中
        expected_json_path = os.path.join(OUTPUT_DIR, f"{video_id}.json")
        
        if os.path.exists(expected_json_path):
            # 檢查是否需要重新翻譯（檔案存在但無中文翻譯）
            try:
                with open(expected_json_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                
                # 檢查 segments 中是否有 "[無中文翻譯]"
                segments = existing_data.get("segments", [])
                needs_translation = any(
                    seg.get("text_zh") == "[無中文翻譯]" for seg in segments
                )
                
                if needs_translation:
                    print(f"🔄 檔案已存在但缺少中文翻譯，開始重新翻譯...")
                    # 提取原始 segments 進行 Gemini 翻譯
                    self._retranslate_existing_json(expected_json_path, existing_data)
                    return
                else:
                    print(f"⏭️  檔案已存在且已完成翻譯 ({video_id}.json)，跳過處理。")
                    return
            except Exception as e:
                print(f"⚠️ 讀取現有檔案時發生錯誤: {e}")
                print(f"   將跳過此檔案，繼續下一個。")
                return
        # -------------------------------------

        print(f"📥 檔案不存在，開始下載影片...")

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

        # 4. Gemini 語意處理（支援批次處理）
        print("🧠 正在呼叫 Gemini 進行語意合併與翻譯...")
        processed_segments = self._process_segments_in_batches(raw_segments)

        if not processed_segments:
            print("⚠️ Gemini 處理失敗，儲存 Whisper 原始結果以便稍後重新翻譯。")
            # 將 Whisper 原始格式轉換為播放器可讀取的格式
            processed_segments = [
                {
                    "id": seg.get("id", i),
                    "start_time": seg["start"],
                    "end_time": seg["end"],
                    "text_en": seg["text"].strip(),
                    "text_zh": "[無中文翻譯]",  # 無翻譯時顯示提示
                    "keywords": [],
                    "words": seg.get("words", [])  # 保留 word-level timestamps 以便未來重新處理
                }
                for i, seg in enumerate(raw_segments)
            ]
            self._list_available_models()
            
            # 直接儲存 JSON 並結束處理
            self._save_json_and_files(video_id, video_title, youtube_url, video_path, 
                                     video_info, processed_segments)
            return

        # 5. Gemini 成功，繼續正常處理
        self._save_json_and_files(video_id, video_title, youtube_url, video_path, 
                                 video_info, processed_segments)

    def _save_json_and_files(self, video_id, video_title, youtube_url, video_path, 
                            video_info, processed_segments):
        """儲存 JSON 和相關檔案的共用方法"""
        print("🎵 正在提取 MP3 音訊檔...")
        mp3_filename = f"{video_id}.mp3"
        mp3_path = os.path.join(OUTPUT_DIR, mp3_filename)
        self._extract_audio_mp3(video_path, mp3_path)
        
        # 計算檔案大小（可選）
        audio_size_mb = 0
        if os.path.exists(mp3_path):
            audio_size_mb = round(os.path.getsize(mp3_path) / (1024 * 1024), 2)

        # 打包 JSON
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

        # 存檔 JSON
        json_path = os.path.join(OUTPUT_DIR, f"{video_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(app_data, f, ensure_ascii=False, indent=2)
            
        # 複製影片檔到輸出資料夾
        final_video_path = os.path.join(OUTPUT_DIR, os.path.basename(video_path))
        if os.path.exists(video_path):
             shutil.copy2(video_path, final_video_path)
             print(f"   (原始影片已保留在: {video_path})")
        
        print(f"✅ 處理完成！\n   📄 JSON 檔: {json_path}\n   🎥 影片檔: {final_video_path}\n   🎵 音訊檔: {mp3_path} ({audio_size_mb} MB)")

    def _process_segments_in_batches(self, raw_segments):
        """將片段分批處理，避免單次請求過長導致回應被截斷"""
        total_segments = len(raw_segments)
        
        # 如果片段數量少於批次大小，直接處理
        if total_segments <= self.batch_size:
            return self._process_with_gemini(raw_segments)
        
        # 分批處理
        print(f"   總共 {total_segments} 個片段，將分 {(total_segments + self.batch_size - 1) // self.batch_size} 批次處理")
        all_processed = []
        
        for i in range(0, total_segments, self.batch_size):
            batch_num = i // self.batch_size + 1
            batch = raw_segments[i:i + self.batch_size]
            print(f"   📦 處理第 {batch_num} 批 ({len(batch)} 個片段)...")
            
            processed_batch = self._process_with_gemini(batch)
            
            if not processed_batch:
                print(f"   ❌ 第 {batch_num} 批處理失敗")
                return None
            
            all_processed.extend(processed_batch)
        
        print(f"   ✅ 所有批次處理完成，共 {len(all_processed)} 個片段")
        return all_processed

    def _process_with_gemini(self, raw_segments):
        # 不包含 words 陣列發送給 Gemini，避免回應過長被截斷
        simplified_input = [
            {
                "id": i, 
                "start": seg["start"], 
                "end": seg["end"], 
                "text": seg["text"].strip()
            } 
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
        - keywords: choose difficult, important, meaning and name words (min 1,max 5), in English
        - don't translate keywords.
        - Keep all IDs, timestamps, text_en unchanged
        """

        response = None
        try:
            response = self.gemini_model.generate_content(prompt)
            response_text = response.text
            
            # 檢查回應是否被截斷
            if len(response_text) > 100000:
                print(f"   ⚠️ Gemini 回應過長 ({len(response_text)} 字元)，可能被截斷")
            
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            
            # 嘗試解析 JSON
            parsed_data = json.loads(clean_text)
            
            # 驗證輸出片段數量
            if len(parsed_data) != len(simplified_input):
                print(f"   ⚠️ 警告: Gemini 合併了片段！輸入 {len(simplified_input)} 個，輸出 {len(parsed_data)} 個")
                print(f"   片段數量不符，放棄此批次")
                return None
            
            # ✨ 關鍵步驟：將原始 Whisper 的 words 陣列加回去
            for i, item in enumerate(parsed_data):
                item["words"] = raw_segments[i].get("words", [])
            
            print(f"✅ Gemini 成功處理 {len(parsed_data)} 個片段")
            return parsed_data
            
        except json.JSONDecodeError as e:
            print(f"\n❌ Gemini 回應格式錯誤 (無法解析 JSON)")
            print(f"   錯誤詳情: {e}")
            if response and hasattr(response, 'text'):
                print(f"   回應長度: {len(response.text)} 字元")
            print(f"   跳過此批次，繼續處理下一批")
            return None
                
        except Exception as e:
            print(f"\n❌ Gemini API 呼叫失敗")
            print(f"   錯誤類型: {type(e).__name__}")
            print(f"   錯誤訊息: {str(e)}")
            
            # 檢查常見錯誤
            error_msg = str(e).lower()
            if 'quota' in error_msg or 'limit' in error_msg:
                print(f"   💡 可能原因: API 配額用完或達到速率限制")
                print(f"   建議: 檢查 https://aistudio.google.com/app/apikey")
            elif 'api_key' in error_msg or 'authentication' in error_msg:
                print(f"   💡 可能原因: API Key 無效或過期")
            elif 'permission' in error_msg:
                print(f"   💡 可能原因: API Key 權限不足")
            elif 'timeout' in error_msg or 'connection' in error_msg:
                print(f"   💡 可能原因: 網路連線問題")
            
            return None

    def _retranslate_existing_json(self, json_path, existing_data):
        """重新翻譯已存在但缺少中文翻譯的 JSON 檔案"""
        print("🧠 正在呼叫 Gemini 重新翻譯現有片段...")
        
        segments = existing_data.get("segments", [])
        
        # 準備輸入給 Gemini（模擬 raw_segments 格式，保留 words）
        raw_segments_format = [
            {
                "start": seg.get("start_time", seg.get("start", 0)),
                "end": seg.get("end_time", seg.get("end", 0)),
                "text": seg.get("text_en", seg.get("text", "")),
                "words": seg.get("words", [])  # 保留原始 words 陣列
            }
            for seg in segments
        ]
        
        # 使用批次處理方法進行翻譯
        processed_segments = self._process_segments_in_batches(raw_segments_format)
        
        if processed_segments:
            # 更新 JSON 資料
            existing_data["segments"] = processed_segments
            
            # 存檔
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 重新翻譯完成！已更新檔案: {json_path}")
        else:
            print(f"❌ Gemini 翻譯失敗，保持原檔案不變。")

    def _list_available_models(self):
        print("\n🔍 正在查詢您帳號可用的模型列表...")
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    print(f" - {m.name}")
        except Exception as e:
            print(f"無法列出模型: {e}")

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
        """提取 MP3 格式音訊（用於手機版純音訊模式）"""
        try:
            (
                ffmpeg
                .input(video_path)
                .output(audio_output_path, 
                       acodec='libmp3lame', 
                       audio_bitrate='128k',
                       ac=2)  # 立體聲
                .run(quiet=True, overwrite_output=True)
            )
            print(f"   ✅ MP3 音訊檔已生成")
        except ffmpeg.Error as e:
            print(f"   ⚠️ MP3 提取失敗: {e}")

# --- 執行區 ---
if __name__ == "__main__":
    if "您的_GOOGLE" in GEMINI_API_KEY:
        print("❌ 錯誤：請先在程式碼第 11 行填入您的 Google Gemini API Key")
    else:
        factory = YouTubeContentFactory(model_size="base")
        
        # 您可以在這裡放入大量的網址，已下載過的會自動跳過
        video_urls = [
            "https://www.youtube.com/watch?v=X0W6CX-uHhk",
            "https://www.youtube.com/watch?v=UF8uR6Z6KLc",
            "https://www.youtube.com/watch?v=zG3gbdb00lY&list=PPSV",
            "https://www.youtube.com/watch?v=D6SHe459EPM",
            "https://www.youtube.com/watch?v=gaMPn1doLac",
            "https://www.youtube.com/watch?v=jNI0fiX4q4A",
            "https://www.youtube.com/watch?v=NsyI9LIXbFM",
            "https://www.youtube.com/watch?v=xjycSL8JJUI",
        ]
        
        for url in video_urls:
            factory.process_url(url)