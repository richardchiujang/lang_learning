import os
import json
import whisper
import ffmpeg
import yt_dlp
import google.generativeai as genai
import shutil
import time
from datetime import timedelta
from typing import Dict, Optional

# --- 全域設定 ---
# ⚠️⚠️⚠️ 從外部檔案讀取 Google Gemini API Key ⚠️⚠️⚠️
def load_api_key(key_file="GEMINI_API_KEY.txt"):
    """
    從檔案讀取 Gemini API Key
    
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
        print(f"⚠️ 警告: 找不到有效的 API Key 檔案 ({key_file})")
        print(f"   請在 {key_file} 中填入您的 Gemini API Key")
        return None
    except Exception as e:
        print(f"❌ 讀取 API Key 檔案時出錯: {e}")
        return None

GEMINI_API_KEY = load_api_key()

OUTPUT_DIR = "./app_assets"
TEMP_DIR = "./temp_downloads"

# 建立必要的資料夾
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# 設定 Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- 📋 模型配置管理系統 ---
# 根據不同模型調整速率限制、批次大小和重試策略
# 📌 三維度限制說明：
#    RPM: Requests Per Minute (每分鐘請求數)
#    TPM: Tokens Per Minute (每分鐘輸入權杖數)
#    RPD: Requests Per Day (每天請求數) ⚠️ 最關鍵的限制

def load_model_config(config_file="model_config.json"):
    """
    從外部 JSON 檔案讀取模型配置
    
    Args:
        config_file: 模型配置檔案路徑，預設為 model_config.json
        
    Returns:
        模型配置字典，或 None 如果檔案不存在
    """
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                return config_data.get('model_configs', {})
        print(f"⚠️  警告: 找不到模型配置檔案 ({config_file})")
        print(f"   請確保 {config_file} 存在於應用程式目錄中")
        return {}
    except json.JSONDecodeError as e:
        print(f"❌ 解析模型配置檔案時出錯: {e}")
        return {}
    except Exception as e:
        print(f"❌ 讀取模型配置檔案時出錯: {e}")
        return {}

MODEL_CONFIG = load_model_config()

class YouTubeContentFactory:
    def __init__(self, model_name: str = 'Gemma 3 27B', model_size: str = "base"):
        """
        初始化 YouTubeContentFactory
        
        Args:
            model_name: AI 模型名稱，支持: 'Gemini 2.0 Flash Lite', 'Gemini 2.0 Flash', 
                       'Gemini 1.5 Pro', 'Gemini 1.5 Flash', 'Gemma 3 27B'
            model_size: Whisper 模型大小
        """
        print(f"📡 正在載入 Whisper 模型 ({model_size})...")
        self.whisper_model = None

        def _load_whisper_model(self):
            if self.whisper_model is None:
                import whisper
                self.whisper_model = whisper.load_model(self.model_size)
            return self.whisper_model
        # 選擇並設定 AI 模型
        if model_name not in MODEL_CONFIG:
            print(f"⚠️  模型 '{model_name}' 未找到，使用預設值: 'Gemini 2.0 Flash Lite'")
            model_name = 'Gemma 3 27B'
        
        self.model_name = model_name
        self.config = MODEL_CONFIG[model_name]
        
        # 初始化模型和速率限制
        self.gemini_model = genai.GenerativeModel(self.config['api_name'])
        
        # === RPM 追蹤 ===
        self.last_request_time = 0
        self.request_times = []  # 追蹤最近60秒的請求
        
        # === TPM 追蹤 ===
        self.tpm_usage = 0  # 當前分鐘的權杖使用量
        self.tpm_window_start = time.time()
        
        # === RPD 追蹤 (最關鍵的限制) ===
        import json
        from datetime import datetime, timedelta
        
        self.daily_request_file = "./api_usage_tracking.json"
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.requests_today = self._load_daily_requests()
        
        print(f"🧠 設定 AI 模型為: {self.model_name}")
        print(f"   ⚙️  配置參數:")
        print(f"      • RPM 限制: {self.config['rpm_limit']} 請求/分鐘")
        print(f"      • TPM 限制: {self.config['tpm_limit']} 權杖/分鐘")
        print(f"      • RPD 限制: {self.config['rpd_limit']} 請求/天 ⚠️")
        print(f"      • 今日已用: {self.requests_today}/{self.config['rpd_limit']}")
        print(f"      • 請求間延遲: {self.config['delay_between_requests']} 秒")
        print(f"      • 批次大小: {self.config['batch_size']} 個片段/次")
        print(f"      • 最大重試次數: {self.config['max_retries']}")
        print(f"      • API 超時時間: {self.config['timeout']} 秒")

    def switch_model(self, model_name: str) -> bool:
        """
        切換 AI 模型並自動更新配置
        
        Args:
            model_name: 新模型名稱
            
        Returns:
            是否成功切換
        """
        if model_name not in MODEL_CONFIG:
            print(f"❌ 模型 '{model_name}' 不存在，切換失敗")
            self._list_available_models()
            return False
        
        self.model_name = model_name
        self.config = MODEL_CONFIG[model_name]
        self.gemini_model = genai.GenerativeModel(self.config['api_name'])
        self.last_request_time = 0
        self.request_times = []
        self.requests_today = self._load_daily_requests()  # 重新載入當前模型的每日計數
        
        print(f"✅ 已切換到模型: {self.model_name}")
        print(f"   ⚙️ 新配置:")
        print(f"      • RPM: {self.config['rpm_limit']} | TPM: {self.config['tpm_limit']} | RPD: {self.config['rpd_limit']}")
        print(f"      • 今日已用: {self.requests_today}/{self.config['rpd_limit']}")
        return True
    
    def _get_available_models(self) -> list:
        """取得帳號中可用的模型列表"""
        available = []
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available.append(m.name)
        except Exception as e:
            print(f"無法列出模型: {e}")
        return available

    # === 📅 每日限制 (RPD) 追蹤方法 ===
    def _check_and_reset_day(self):
        """檢查是否跨天，如果是則重置計數"""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.today:
            print(f"📅 日期已更新: {self.today} → {today}")
            self.today = today
            self.requests_today = 0
            self._save_daily_requests()
    
    def _load_daily_requests(self) -> int:
        """從檔案載入今天的請求計數"""
        from datetime import datetime
        try:
            if os.path.exists(self.daily_request_file):
                with open(self.daily_request_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 如果日期已變，重置為 0
                    if data.get('date') != self.today:
                        return 0
                    return data.get('count', 0)
        except Exception as e:
            print(f"⚠️ 無法讀取每日請求記錄: {e}")
        return 0
    
    def _save_daily_requests(self):
        """將今天的請求計數保存到檔案"""
        try:
            with open(self.daily_request_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'date': self.today,
                    'count': self.requests_today,
                    'model': self.model_name,
                    'timestamp': time.time()
                }, f, indent=2)
        except Exception as e:
            print(f"⚠️ 無法保存每日請求記錄: {e}")
    
    def _record_request(self, token_count: int = 0):
        """
        記錄一個 API 請求
        
        Args:
            token_count: 本次請求使用的權杖數（用於 TPM 追蹤）
        """
        self._check_and_reset_day()
        self.requests_today += 1
        self._save_daily_requests()
        
        # TPM 追蹤
        current_time = time.time()
        if current_time - self.tpm_window_start > 60:
            self.tpm_usage = 0
            self.tpm_window_start = current_time
        self.tpm_usage += token_count
    
    def _check_daily_limit(self) -> bool:
        """
        檢查是否超過每日限制 (RPD)
        
        Returns:
            如果還有配額返回 True，超過限制返回 False
        """
        self._check_and_reset_day()
        
        remaining = self.config['rpd_limit'] - self.requests_today
        
        if remaining <= 0:
            print(f"\n⚠️ ===== 每日限制警告 =====")
            print(f"❌ 已達到今日請求限制!")
            print(f"   模型: {self.model_name}")
            print(f"   限制: {self.config['rpd_limit']} 請求/天")
            print(f"   已用: {self.requests_today}/{self.config['rpd_limit']}")
            print(f"   下次重置: 明天 00:00 UTC")
            print(f"========================\n")
            return False
        
        # 警告：接近限制
        if remaining <= 10:
            print(f"⚠️ 警告: 今日配額即將用盡! 剩餘 {remaining} 個請求")
        elif remaining <= 50:
            percentage = (remaining / self.config['rpd_limit']) * 100
            if remaining % 10 == 0:  # 每 10 個請求提醒一次
                print(f"ℹ️ 今日已用 {self.requests_today}/{self.config['rpd_limit']} " + 
                      f"({100-percentage:.1f}%)")
        
        return True
    
    def _suggest_model_switch(self):
        """根據 RPD 使用情況建議切換模型"""
        print(f"\n💡 模型建議:")
        models_by_rpd = sorted(MODEL_CONFIG.items(), 
                               key=lambda x: x[1]['rpd_limit'], 
                               reverse=True)
        for i, (name, cfg) in enumerate(models_by_rpd[:3], 1):
            print(f"   {i}. {name}: {cfg['rpd_limit']} 請求/天")
        print()

    # --- 🆕 新增方法：只取得 ID 不下載影片 ---
    def _throttle_request(self):
        """速率限制控制：根據模型配置調整請求之間的延遲"""
        current_time = time.time()
        
        # 移除超過1分鐘的舊請求記錄
        self.request_times = [t for t in self.request_times if current_time - t < 60]
        
        # 檢查是否超過每分鐘請求限制
        if len(self.request_times) >= self.config['rpm_limit']:
            # 計算需要等待的時間
            oldest_request = self.request_times[0]
            wait_time = 60 - (current_time - oldest_request)
            if wait_time > 0:
                print(f"⏳ 達到速率限制，等待 {wait_time:.1f} 秒...")
                time.sleep(wait_time)
                current_time = time.time()
                self.request_times = [t for t in self.request_times if current_time - t < 60]
        
        # 加入配置的最小請求間延遲
        if self.last_request_time > 0:
            elapsed = current_time - self.last_request_time
            if elapsed < self.config['delay_between_requests']:
                sleep_time = self.config['delay_between_requests'] - elapsed
                time.sleep(sleep_time)
                current_time = time.time()
        
        self.last_request_time = current_time
        self.request_times.append(current_time)
    
    def _retry_with_backoff(self, func, max_retries: Optional[int] = None):
        """
        帶指數退避的重試機制
        
        Args:
            func: 要執行的函數
            max_retries: 最大重試次數（若為 None 使用模型配置）
            
        Returns:
            函數執行結果，或 None 如果所有重試都失敗
        """
        if max_retries is None:
            max_retries = self.config['max_retries']
        
        retry_delay = self.config['retry_delay_base']
        
        for attempt in range(max_retries + 1):
            try:
                self._throttle_request()
                return func()
            except Exception as e:
                error_msg = str(e).lower()
                
                # 檢查是否是速率限制或配額錯誤
                is_retryable = any(keyword in error_msg for keyword in 
                                 ['quota', 'limit', 'rate', 'too_many', 'resource_exhausted'])
                
                if attempt < max_retries and is_retryable:
                    print(f"   🔄 第 {attempt + 1} 次重試失敗，等待 {retry_delay} 秒後重試...")
                    print(f"      錯誤: {str(e)[:100]}")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指數退避
                else:
                    raise
        
        return None
    
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
        
        # === 檢查每日限制 (RPD) ===
        if not self._check_daily_limit():
            print(f"⏹️ 已達到今日 API 限制，無法繼續處理。")
            self._suggest_model_switch()
            return
        
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
        result = self.whisper_model.transcribe(audio_path, fp16=False, word_timestamps=True)
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
        batch_size = self.config['batch_size']  # 使用模型配置的批次大小
        
        # 如果片段數量少於批次大小，直接處理
        if total_segments <= batch_size:
            return self._process_with_gemini(raw_segments)
        
        # 分批處理
        print(f"   總共 {total_segments} 個片段，將分 {(total_segments + batch_size - 1) // batch_size} 批次處理")
        all_processed = []
        
        for i in range(0, total_segments, batch_size):
            batch_num = i // batch_size + 1
            batch = raw_segments[i:i + batch_size]
            print(f"   📦 處理第 {batch_num} 批 ({len(batch)} 個片段)...")
            
            processed_batch = self._process_with_gemini(batch)
            
            if not processed_batch:
                print(f"   ❌ 第 {batch_num} 批處理失敗")
                return None
            
            all_processed.extend(processed_batch)
        
        print(f"   ✅ 所有批次處理完成，共 {len(all_processed)} 個片段")
        return all_processed

    def _process_with_gemini(self, raw_segments):
        """
        透過 Gemini API 處理片段
        包含速率限制、重試機制和錯誤處理
        """
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
        - keywords: Select the important words in a sentence; these words represent the semantic key and can determine the meaning of the sentence (min 1,max 5), in English
        - don't translate keywords.
        - Keep all IDs, timestamps, text_en unchanged
        """

        def api_call():
            return self.gemini_model.generate_content(prompt)
        
        response = None
        try:
            # 使用重試機制進行 API 呼叫
            response = self._retry_with_backoff(api_call)
            
            if response is None:
                print(f"   ❌ 所有重試都失敗")
                return None
            
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
            
            print(f"   ✅ Gemini 成功處理 {len(parsed_data)} 個片段")
            
            # === 記錄請求 (用於追蹤 RPD) ===
            self._record_request(token_count=len(prompt))
            
            return parsed_data
            
        except json.JSONDecodeError as e:
            print(f"   ❌ Gemini 回應格式錯誤 (無法解析 JSON)")
            print(f"      錯誤詳情: {e}")
            if response and hasattr(response, 'text'):
                print(f"      回應長度: {len(response.text)} 字元")
            print(f"      跳過此批次，繼續處理下一批")
            return None
                
        except Exception as e:
            print(f"   ❌ Gemini API 呼叫最終失敗（超過最大重試次數）")
            print(f"      錯誤類型: {type(e).__name__}")
            print(f"      錯誤訊息: {str(e)}")
            
            # 檢查常見錯誤並提供建議
            error_msg = str(e).lower()
            if 'quota' in error_msg or 'resource_exhausted' in error_msg:
                print(f"      💡 原因: API 配額用完或達到速率限制")
                print(f"      建議: ")
                print(f"         1. 檢查 https://aistudio.google.com/app/apikey")
                print(f"         2. 嘗試增加 delay_between_requests 或減少 batch_size")
                print(f"         3. 切換到更寬鬆限制的模型，例如:")
                print(f"            factory.switch_model('Gemini 2.0 Flash Lite')")
            elif 'api_key' in error_msg or 'authentication' in error_msg:
                print(f"      💡 原因: API Key 無效或過期")
            elif 'permission' in error_msg:
                print(f"      💡 原因: API Key 權限不足")
            elif 'timeout' in error_msg or 'connection' in error_msg:
                print(f"      💡 原因: 網路連線問題或請求超時")
            
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
        """列出您帳號可用的模型和本程式支援的模型配置"""
        print("\n📋 ==== 模型配置信息 ====\n")
        print("程式支援的模型配置:")
        print(f"{'模型':<22} {'RPM':>6} {'TPM':>8} {'RPD':>8} {'批次':>6}")
        print("-" * 55)
        
        for model_key in MODEL_CONFIG.keys():
            cfg = MODEL_CONFIG[model_key]
            print(f"{model_key:<22} {cfg['rpm_limit']:>6} {cfg['tpm_limit']:>8} {cfg['rpd_limit']:>8} {cfg['batch_size']:>6}")
        
        print("\n📌 說明:")
        print("  • RPM: 每分鐘請求數限制")
        print("  • TPM: 每分鐘輸入權杖數限制")
        print("  • RPD: 每天請求數限制 ⚠️（最關鍵的限制！）")
        print("  • 批次: 每批處理的片段數")
        
        print("\n💡 建議:")
        print("  • 極速批處理 → 使用 Gemini 2.5 Flash（RPD: 10000）")
        print("  • 大量批處理 → 使用 Gemma 3 4B（RPD: 8000）或 Gemini 3 Flash Preview（RPD: 8000）")
        print("  • 平衡性能 → 使用 Gemini 2.5 Pro（RPD: 5000）")
        print("  • 最保守 → 使用 Gemini 2.0 Flash Lite（RPD: 1000）")
        
        print("\n🔍 正在查詢您帳號可用的模型...")
        try:
            available = self._get_available_models()
            if available:
                print("您的帳號可用模型:")
                for model in available:
                    print(f"  • {model}")
            else:
                print("無法列出模型，請檢查 API Key")
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
    if GEMINI_API_KEY is None:
        print("❌ 錯誤：請先在 GEMINI_API_KEY.txt 檔案中填入您的 Google Gemini API Key")
    else:
        # ⚙️ 模型選擇（可根据需要修改）
        SELECTED_MODEL = 'Gemma 3 27B'  # 默認模型，支持快速切换
        
        factory = YouTubeContentFactory(model_name=SELECTED_MODEL, model_size="base")
        
        # 🔄 模型切換示例（取消註釋以使用其他模型）
        # factory.switch_model('Gemini 2.0 Flash')       # 中等限制
        # factory.switch_model('Gemini 3 Flash Preview') # 高速率限制與新功能
        # factory.switch_model('Gemini 2.5 Pro')         # 專業版
        # factory.switch_model('Gemma 3 4B')             # 輕量級替代方案
        
        # 列出可用模型配置
        print("\n" + "="*60)
        factory._list_available_models()
        print("="*60 + "\n")
        
        # 💾 從 JSON 檔案讀取視頻 URL 列表
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