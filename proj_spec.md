# 🔬 AI 語言學習系統 - 程式碼規格書

本文件詳細說明四個核心模組的架構、API 介面與實現細節。

---

## 📑 目錄

1. [YouTubeContentFactory.py](#1-youtubecontentfactorypy---gemini-版本)
2. [YouTubeContentFactorySonnet.py](#2-youtubecontentfactorysonnetpy---bedrock-版本)
3. [desktop_player.py](#3-desktop_playerpy---播放器應用)
4. [model_config.json](#4-model_configjson---配置檔案)

---

## 1. YouTubeContentFactory.py - Gemini 版本

### 類別結構

```
YouTubeContentFactory
├── __init__(model_name, model_size)
├── 模型管理
│   ├── switch_model(model_name)
│   ├── _list_available_models()
│   └── _get_available_models()
├── 配額追蹤
│   ├── _check_and_reset_day()
│   ├── _load_daily_requests()
│   ├── _save_daily_requests()
│   ├── _record_request(token_count)
│   ├── _check_daily_limit()
│   └── _suggest_model_switch()
├── 速率控制
│   ├── _throttle_request()
│   └── _retry_with_backoff(func, max_retries)
├── 影片處理
│   ├── process_url(youtube_url)
│   ├── _download_youtube_video(url)
│   ├── _get_video_id(url)
│   ├── _extract_audio(video_path, audio_output_path)
│   └── _extract_audio_mp3(video_path, audio_output_path)
├── 語音轉錄
│   └── [Whisper 集成 - 內蝕處理]
├── AI 翻譯
│   ├── _process_segments_in_batches(raw_segments)
│   ├── _process_with_gemini(raw_segments)
│   └── _retranslate_existing_json(json_path, existing_data)
└── 檔案輸出
    └── _save_json_and_files(...)
```

### 關鍵方法詳解

#### `__init__(model_name='Gemini 2.5 Flash', model_size='base')`
**用途**: 初始化工廠，載入 Whisper 模型與 Gemini 設置

**參數**:
- `model_name` (str): 從 `model_config.json` 中定義的模型名稱
- `model_size` (str): Whisper 模型大小 (`'tiny'`, `'base'`, `'small'`, `'medium'`, `'large'`)

**初始化步驟**:
1. 載入 Whisper 模型（GPU/CPU 自動偵測）
2. 驗證 `model_name` 是否存在於 `MODEL_CONFIG`
3. 初始化 Gemini 客戶端
4. 設置 RPM/TPM/RPD 追蹤變數
5. 載入當日請求計數（從 `api_usage_tracking.json`）

**狀態變數初始化**:
```python
self.whisper_model          # OpenAI Whisper 模型
self.model_name             # 當前 AI 模型名稱
self.config                 # 模型配置字典（RPM, TPM, RPD, batch_size 等）
self.gemini_model           # Google GenerativeAI 模型實例
self.last_request_time      # 上次 API 請求時間戳
self.request_times          # 過去 60 秒內的請求時間列表（RPM 追蹤）
self.tpm_usage              # 當前分鐘的權杖使用量
self.tpm_window_start       # TPM 計時窗口開始時間
self.requests_today         # 今日已用請求數（RPD 追蹤）
self.daily_request_file     # 日配額追蹤檔案路徑
self.today                  # 當前日期（YYYY-MM-DD 格式）
```

#### `process_url(youtube_url)`
**用途**: 核心工作流程 - 從 URL 到完成翻譯輸出的完整端到端處理

**工作流程**:
```
1. 檢查 RPD 限制 → 2. 快速取得影片 ID
↓ (失敗) 3. 檢查 JSON 是否存在
                ↓ (存在且完整)
                返回，跳過處理
                
                ↓ (存在但缺翻譯)
                調用 _retranslate_existing_json()
                
                ↓ (不存在)
4. 下載影片 → 5. 提取音訊 (WAV)
↓
6. Whisper 轉錄 → 7. Gemini 翻譯 (批次)
↓
8. 提取 MP3 & 產生 JSON
↓
9. 複製輸出到 app_assets/
```

**例外處理**:
- 403 Forbidden: 返回，提示用戶嘗試 VPN/Cookie
- JSON 解析錯誤: 保存原始 Whisper 結果，標記為 `[無中文翻譯]`
- API 配額溢出: 提示並建議切換模型

#### `_process_segments_in_batches(raw_segments)`
**用途**: 將長影片片段分批發送給 Gemini，避免請求過長

**批次策略**:
```
raw_segments (e.g., 200 個) 
    ↓
分割成 batch_size (e.g., 40) 的多個批次
    ↓
迴圈處理每個批次:
  1. 調用 _process_with_gemini(batch)
  2. 若失敗則返回 None，整個流程失敗
  3. 若成功則累積結果
    ↓
所有批次成功 → 返回完整結果列表
```

**邊界情況**:
- 若 `len(raw_segments) <= batch_size` → 直接單批處理，不分割
- 若任一批次失敗 → 整體失敗（不跳過失敗批次）

#### `_process_with_gemini(raw_segments)`
**用途**: 單個批次的 Gemini API 呼叫，包含重試與錯誤恢復

**核心邏輯**:
```python
prompt = "將 {len(segments)} 個片段翻譯為繁體中文..."

def api_call():
    return self.gemini_model.generate_content(prompt)

response = self._retry_with_backoff(api_call)
# 最多重試 self.config['max_retries'] 次，指數退避
# 偵測是否為「可重試」錯誤 (quota, rate_limit, resource_exhausted)

if response.text is JSON valid:
    parsed = json.loads(response.text)
    
    # 驗證片段數量
    if len(parsed) != len(raw_segments):
        return None  # Gemini 意外合併了片段，拒絕
    
    # 保留原始 word-level timestamps
    for i, item in enumerate(parsed):
        item["words"] = raw_segments[i].get("words", [])
    
    # 記錄請求（用於 RPD 追蹤）
    self._record_request(token_count=len(prompt))
    
    return parsed
else:
    # JSON 解析失敗，記錄詳情並返回 None
    return None
```

**重試機制（指數退避）**:
```
嘗試 1: 立即執行
↓ (失敗)
等待 retry_delay_base 秒 (e.g., 5s)
↓ (超時)
嘗試 2: 重新執行
↓ (失敗)
等待 retry_delay_base * 2 秒 (e.g., 10s)
↓ (超時)
嘗試 3: 最後一次
↓ (失敗)
返回 None，標記為失敗
```

#### `_retry_with_backoff(func, max_retries=None)`
**用途**: 通用重試包裝器，支援指數退避

**參數**:
- `func`: 傳入無參數函數，返回結果或拋出異常
- `max_retries`: None 表示使用 `self.config['max_retries']`

**判斷「可重試」錯誤的關鍵字**:
```python
retryable_keywords = ['quota', 'limit', 'rate', 'too_many', 'resource_exhausted']

if any(keyword in error_msg.lower() for keyword in retryable_keywords):
    # 可重試 → 等待後重新嘗試
else:
    # 不可重試 → 立即拋出異常
```

**退避公式**:
```
delay_n = retry_delay_base * (2 ^ n)

例: retry_delay_base = 5
    嘗試 1 失敗 → 等 5 秒
    嘗試 2 失敗 → 等 10 秒
    嘗試 3 失敗 → 等 20 秒
```

#### `_throttle_request()`
**用途**: 多層次速率限制控制，確保遵守 RPM 與最小請求間隔

**三層控制**:

**層 1: RPM 限制**
```python
# 移除超過 60 秒的舊請求記錄
self.request_times = [t for t in self.request_times if now - t < 60]

if len(self.request_times) >= self.config['rpm_limit']:
    # 已達到本分鐘上限 → 睡眠至最老請求超過 60 秒
    oldest = self.request_times[0]
    wait_time = 60 - (now - oldest)
    if wait_time > 0:
        sleep(wait_time)
```

**層 2: 最小請求間隔**
```python
if self.last_request_time > 0:
    elapsed = now - self.last_request_time
    min_interval = self.config['delay_between_requests']
    if elapsed < min_interval:
        sleep(min_interval - elapsed)
```

**層 3: 紀錄請求時間**
```python
self.last_request_time = now
self.request_times.append(now)
```

### API 配額追蹤系統

#### RPD (Requests Per Day) 追蹤
**檔案**: `api_usage_tracking.json`
```json
{
  "date": "2026-02-20",
  "count": 42,
  "model": "Gemini 2.5 Flash",
  "timestamp": 1740044400.123
}
```

**重置邏輯**:
- 每次檢查時，對比檔案中的 `date` 與當前日期
- 若不符，表示跨日，重置 `count = 0`

**查詢方法**:
```python
remaining = factory.config['rpd_limit'] - factory.requests_today
print(f"今日剩餘配額: {remaining} 個請求")
```

#### 警告階梯
```python
if remaining <= 0:
    # 🔴 紅色警告：已超限
    print("❌ 已達到今日請求限制！")
elif remaining <= 10:
    # 🟠 橙色警告：即將用盡
    print("⚠️ 警告: 今日配額即將用盡! 剩餘 {remaining} 個請求")
elif remaining <= 50:
    # 🟡 黃色提示：定期通知（每 10 個請求）
    percentage = (remaining / rpd_limit) * 100
    print(f"ℹ️ 今日已用 {requests_today}/{rpd_limit} ({100-percentage:.1f}%)")
```

### 資料流與轉換

#### 輸入：原始 Whisper 片段
```python
raw_segments = [
    {
        "id": 0,
        "start": 0.0,
        "end": 5.5,
        "text": "Welcome to the course.",
        "words": [
            {"word": "Welcome", "start": 0.0, "end": 0.8},
            ...
        ]
    },
    ...
]
```

#### 處理：發送給 Gemini 的格式（簡化，不含 words）
```json
[
  {
    "id": 0,
    "start": 0.0,
    "end": 5.5,
    "text": "Welcome to the course."
  }
]
```

#### 輸出：Gemini 回應（應該帶有翻譯）
```json
[
  {
    "id": 0,
    "start_time": 0.0,
    "end_time": 5.5,
    "text_en": "Welcome to the course.",
    "text_zh": "歡迎來到這個課程。",
    "keywords": ["welcome", "course"]
  }
]
```

#### 加工：加回 words 陣列
```python
for i, item in enumerate(parsed_data):
    item["words"] = raw_segments[i].get("words", [])
```

#### 最終輸出：保存到 JSON
```json
{
  "lesson_id": "dQw4w9WgXcQ",
  "title": "Rick Astley - Never Gonna Give You Up",
  "source_url": "https://youtube.com/...",
  "video_filename": "dQw4w9WgXcQ.mp4",
  "audio_filename": "dQw4w9WgXcQ.mp3",
  "audio_only_size_mb": 12.5,
  "duration": 213.456,
  "segments": [
    {
      "id": 0,
      "start_time": 0.0,
      "end_time": 5.5,
      "text_en": "Welcome to the course.",
      "text_zh": "歡迎來到這個課程。",
      "keywords": ["welcome", "course"],
      "words": [...]
    }
  ]
}
```

### 全域函數

#### `load_api_key(key_file="GEMINI_API_KEY.txt")`
**優先級順序**:
1. 檢查檔案 `GEMINI_API_KEY.txt`
2. 檢查環保變數 `GEMINI_API_KEY`
3. 均未找到 → 返回 None，打印警告

#### `load_model_config(config_file="model_config.json")`
**返回**: 字典 `{model_name: {config_dict}, ...}`

**配置項**:
- `name`: 模型顯示名稱
- `api_name`: Gemini API 中的正式名稱（e.g., `"gemini-2.5-flash"`)
- `rpm_limit`: 每分鐘請求數限制
- `tpm_limit`: 每分鐘輸入權杖數限制
- `rpd_limit`: 每天請求數限制 ⚠️
- `delay_between_requests`: 最小請求間隔(秒)
- `batch_size`: 批次處理的片段數
- `max_retries`: 最大重試次數
- `retry_delay_base`: 初始退避延遲(秒)
- `timeout`: 註：已移除（Gemini API 不支持）
- `daily_reset_hour`: UTC 重置時間（當前未使用）

---

## 2. YouTubeContentFactorySonnet.py - Bedrock 版本

### 架構概述

本模組使用 **Amazon Bedrock** 而非 Google Gemini，核心邏輯相同，差異如下：

### BedrocksonnetClient 類別

```python
class BedrocksonnetClient:
    def __init__(self, region_priority=("ap-southeast-1", "us-east-1"))
    
    方法:
    ├── _init_client()           # 初始化 Bedrock 客戶端（多地域容錯）
    ├── _model_id()              # 返回當前模型 ID
    ├── converse_sonnet_lite_text(system_text, user_text, ...)
    │   # 文本對話 API
    │   參數:
    │   ├── system_text: 系統提示
    │   ├── user_text: 用戶問題
    │   ├── max_tokens: 最大輸出權杖數 (預設 800)
    │   ├── temperature: 創意度 (預設 0.2 - 保守)
    │   └── top_p: 核採樣參數 (預設 0.9)
    │   返回: {"text": "...", "usage": {...}, "region": "ap-southeast-1"}
    │
    └── converse_sonnet_lite_vision(system_text, user_text, image_bytes, ...)
        # 視圖對話 API（本專案未使用）
```

### BedrocksonnetClient 與 YouTubeContentFactorySonnet 的整合

**初始化流程**:
```python
try:
    self.sonnet = BedrocksonnetClient(...)
    # 成功 → prefer_model = "sonnet_lite"
except Exception:
    # 失敗 → 降級至 Gemini
    self.prefer_model = "gemini"
    print("⚠️ Bedrock 初始化失敗，將降級至 Gemini")
```

**選擇邏輯** (_process_segments_single_batch):
```python
if prefer_model == "sonnet_lite":
    try:
        return self._process_with_sonnet(raw_segments)
    except Exception as e:
        if ENABLE_GEMINI_FALLBACK and gemini_model is not None:
            return self._process_with_gemini(raw_segments)
        else:
            raise
elif prefer_model == "gemini":
    return self._process_with_gemini(raw_segments)
```

### _process_with_sonnet() 詳解

**提示工程**:
```python
system_text = "You are a precise bilingual translator for English to Traditional Chinese (Taiwan). Keep structure exactly."

user_text = f"""
Translate to Traditional Chinese (Taiwan) and keep the exact structure.
Input ({len(segments)} segments):
{json.dumps(segments, ensure_ascii=False)}

Output ({len(segments)} items):
[{{"id": ..., "start_time": ..., "end_time": ..., "text_en": "...", "text_zh": "中文", "keywords": ["..."]}}]

Rules:
- Output EXACTLY {len(segments)} items
- keywords: 1-5 English words (min 1, max 5), do NOT translate
- Keep all ids, timestamps, text_en unchanged
"""
```

**回應解析**:
```python
raw_text = response.text  # 可能含前置敘述或markdown fence

# 步驟 1: 移除 markdown
clean = raw_text.replace("```json", "").replace("```", "").strip()

# 步驟 2: 抽出第一個 JSON 陣列
match = re.search(r'(\[.*\])', clean, re.DOTALL)
if match:
    clean = match.group(1).strip()

# 步驟 3: 解析 JSON
try:
    parsed_data = json.loads(clean)
except json.JSONDecodeError:
    # 解析失敗時的保守回退
    parsed_data = [
        {
            "id": s["id"],
            "start_time": s["start"],
            "end_time": s["end"],
            "text_en": s["text"],
            "text_zh": s["text"],  # 無翻譯時直接用英文
            "keywords": [],
            "words": raw_segments[s["id"]].get("words", [])
        }
        for s in simplified_input
    ]

# 步驟 4: 加回 words
for i, item in enumerate(parsed_data):
    item["words"] = raw_segments[i].get("words", [])
```

### AWS 認證與地域支援

**支援的地域** (按優先級):
1. `ap-southeast-1` (新加坡 - 低延遲)
2. `us-east-1` (美國東部 - 備用)

**容錯邏輯**:
```python
for region in region_priority:
    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        return client  # 成功
    except Exception:
        continue  # 嘗試下一個地域
        
if all failed:
    raise RuntimeError("Bedrock client init failed")
```

### 環保變數支援

```python
# API Key 載入優先級
1. 檔案: GEMINI_API_KEY.txt (用於 Gemini 備援)
2. 環保變數: GEMINI_API_KEY (用於 Gemini 備援)
3. AWS CLI config (~/.aws/credentials) (用於 Bedrock)
```

---

## 3. desktop_player.py - 播放器應用

### 類別架構

```
LanguagePlayer (QMainWindow)
├── UI 元件初始化
│   ├── _init_ui()
│   │   ├── 左側面板 (課程列表)
│   │   │   ├── QListWidget lessons_list
│   │   │   └── 刷新按鈕
│   │   ├── 中央面板 (字幕與控制)
│   │   │   ├── 英文字幕 (QLabel)
│   │   │   ├── 中文字幕 (QLabel)
│   │   │   ├── 片段進度 (QLabel)
│   │   │   ├── 進度條 (QSlider)
│   │   │   ├── 播放/暫停按鈕
│   │   │   ├── 速度調整 (QComboBox)
│   │   │   ├── 音量滑桿 (QSlider)
│   │   │   └── 背景噪聲控制
│   │   └── 右側面板 (統計)
│   │       └── 詳細資訊顯示
│   │
│   └── _init_media_players()
│       ├── self.player (QMediaPlayer - 主音訊)
│       ├── self.audio_output (QAudioOutput)
│       └── self.noise_player (QMediaPlayer - 背景噪聲)
│
├── 課程管理
│   ├── _scan_lessons()         # 掃描 app_assets/
│   ├── _refresh_lesson_list()
│   └── _load_lesson(json_path)
│
├── 播放控制
│   ├── _play_lesson()
│   ├── _pause_resume()
│   ├── _seek_to_time(ms)
│   ├── _update_playback_speed(speed)
│   └── on_position_changed(position)
│
├── 片段同步
│   ├── _find_current_segment()
│   ├── _update_segment_display()
│   └── _highlight_keywords()
│
├── 背景噪聲
│   ├── _scan_noises()
│   ├── _play_noise_loop()
│   ├── _set_noise_volume(volume)
│   └── _update_noise_mix()
│
└── 進度保存
    ├── _load_playback_position()
    ├── _save_playback_position()
    └── _resume_from_last_position()
```

### 核心資料結構

#### 課程資料 (self.segments)
```python
segments = [
    {
        "id": 0,
        "start_time": 0.0,      # 秒
        "end_time": 5.5,        # 秒
        "text_en": "Hello world",
        "text_zh": "你好世界",
        "keywords": ["hello", "world"],
        "words": [              # word-level timestamps
            {"word": "Hello", "start": 0.0, "end": 0.8},
            {"word": "world", "start": 1.0, "end": 1.8}
        ]
    },
    ...
]
```

#### 播放狀態
```python
self.is_playing               # bool - 播放中
self.current_position_ms      # int - 當前播放位置(毫秒)
self.current_segment_id       # int - 當前片段 ID
self.playback_speed           # float - 播放速度倍率
self.main_volume             # float - 主音訊音量 (0.0-1.0)
self.noise_volume            # float - 背景噪聲音量 (0.0-1.0)
self.audio_only_mode         # bool - 純音訊模式
```

### 關鍵方法詳解

#### `_init_ui()`
**用途**: 建立完整的使用者介面

**佈局結構**:
```
┌─────────────────────────────────────────────┐
│              LanguagePlayer                 │
├──────────────┬────────────────────┬─────────┤
│              │                    │         │
│  課程列表    │   字幕 + 控制      │  統計   │
│              │                    │         │
│  ┌─────┐    │  ┌──────────────┐  │ ┌─────┐│
│  │ 課  │    │  │  英文        │  │ │進度 ││
│  │ 程  │    │  │  中文        │  │ │ 及 ││
│  │ 清  │    │  │  進度        │  │ │ 統 ││
│  │ 單  │    │  └──────────────┘  │ │ 計 ││
│  │     │    │  ┌──────────────┐  │ │     ││
│  │ 刷新│    │  │  進度條      │  │ │     ││
│  │ 按  │    │  └──────────────┘  │ └─────┘│
│  │ 鈕  │    │  ┌──────────────┐  │
│  │     │    │  │ ⏯ ⏸  🔊   🎚  │  │
│  │     │    │  │ 速度  噪聲等  │  │
│  │     │    │  └──────────────┘  │
│  └─────┘    │                    │
│             │                    │
└──────────────┴────────────────────┴─────────┘
```

#### `_load_lesson(json_path)`
**用途**: 從 JSON 檔案載入課程資料

**步驟**:
1. 打開 JSON 檔案，驗證結構
2. 提取 segments 陣列
3. 計算總時長
4. 檢查音訊檔案存在情況
5. 載入播放位置（如果有保存）
6. 準備播放器

```python
def _load_lesson(self, json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        self.current_json_data = json.load(f)
    
    self.segments = self.current_json_data.get('segments', [])
    self.video_duration = self.current_json_data.get('duration', 0)
    
    mp3_path = os.path.join(ASSETS_DIR, f"{self.current_json_data['lesson_id']}.mp3")
    if os.path.exists(mp3_path):
        self.player.setSource(QUrl.fromLocalFile(mp3_path))
    
    self._resume_from_last_position()
```

#### `on_position_changed(position_ms)`
**用途**: 根據播放位置實時更新字幕

**邏輯**:
```python
def on_position_changed(self, position_ms):
    current_segment = self._find_current_segment(position_ms)
    
    if current_segment:
        # 更新字幕顯示
        self.label_en.setText(current_segment['text_en'])
        self.label_zh.setText(current_segment['text_zh'])
        
        # 更新進度資訊
        self.label_progress.setText(
            f"{self._ms_to_timestamp(position_ms)} / {self._duration_to_timestamp()}"
        )
        
        # 更新進度條（不觸發 sliderMoved 事件）
        self.slider.blockSignals(True)
        self.slider.setValue(int(position_ms))
        self.slider.blockSignals(False)
        
        # 保存進度
        self._save_playback_position(position_ms)
```

#### `_find_current_segment(position_ms)`
**用途**: 根據播放位置找出當前片段

**演算法** (二分搜尋):
```python
def _find_current_segment(self, position_ms):
    position_s = position_ms / 1000.0
    
    # 簡單線性搜尋（因片段通常 < 1000 個）
    for seg in self.segments:
        if seg['start_time'] <= position_s < seg['end_time']:
            return seg
    
    return None  # 未找到（e.g., 在片段間隙)
```

**優化版本**（使用二分搜尋）:
```python
import bisect

def _find_current_segment_optimized(self, position_ms):
    position_s = position_ms / 1000.0
    
    # 用 bisect 快速定位
    segment_starts = [seg['start_time'] for seg in self.segments]
    idx = bisect.bisect_right(segment_starts, position_s) - 1
    
    if 0 <= idx < len(self.segments):
        seg = self.segments[idx]
        if position_s < seg['end_time']:
            return seg
    
    return None
```

#### 背景噪聲混音邏輯

**架構**:
```
主音訊 (mp3) → volume: 1.0-main_volume
背景噪聲 (wav) → volume: 0.0-noise_volume
                    ↓
                混音輸出
```

**可用噪聲列表** (掃描 `noises/` 目錄):
```python
def _scan_noises(self):
    if not os.path.exists(NOISE_DIR):
        os.makedirs(NOISE_DIR)
        return []
    return [f for f in os.listdir(NOISE_DIR) if f.lower().endswith('.wav')]
```

**播放邏輯**:
```python
def _play_noise_loop(self, noise_file):
    if not noise_file or noise_file == "None":
        self.noise_player.stop()
        return
    
    noise_path = os.path.join(NOISE_DIR, noise_file)
    self.noise_player.setSource(QUrl.fromLocalFile(noise_path))
    
    # 無限迴圈
    @self.noise_player.mediaStatusChanged.connect
    def on_noise_status_changed(status):
        if status == QMediaPlayer.EndOfMedia:
            self.noise_player.play()  # 重新播放
    
    self._set_noise_volume(self.noise_target_volume)
    self.noise_player.play()
```

### 進度管理

#### 檔案格式: `playback_progress.json`
```json
{
  "lesson_id": "video_id",
  "position_ms": 12500,
  "last_played": "2026-02-20T15:30:45Z"
}
```

#### 載入邏輯
```python
def _resume_from_last_position(self):
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                data = json.load(f)
            
            if data['lesson_id'] == self.current_json_data['lesson_id']:
                self.player.setPosition(data['position_ms'])
        except:
            pass
```

### 速度調整

**支援的倍率**:
```python
playback_speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
```

**實現**:
```python
def _update_playback_speed(self, speed):
    self.playback_speed = speed
    self.player.setPlaybackRate(speed)
```

### 鍵盤快捷鍵 (可擴展)

| 按鍵 | 動作 |
|------|------|
| Space | 播放/暫停 |
| Left Arrow | -5 秒 |
| Right Arrow | +5 秒 |
| [ | 減速 |
| ] | 加速 |

---

## 4. model_config.json - 配置檔案

### 結構

```json
{
  "model_configs": {
    "模型名稱": {
      "name": "...",
      "api_name": "...",
      "rpm_limit": 60,
      "tpm_limit": 50000,
      "rpd_limit": 3000,
      "delay_between_requests": 1.0,
      "batch_size": 18,
      "max_retries": 3,
      "retry_delay_base": 5,
      "timeout": 60,
      "daily_reset_hour": 0
    },
    ...
  },
  "default_model": "Gemini 2.5 Flash"
}
```

### 已配置的模型

| 模型名稱 | RPM | TPM | RPD | 適用場景 |
|----------|-----|-----|-----|----------|
| Gemini 2.5 Flash | 360 | 1M | 10,000 | ⭐ 推薦 - 快速批量 |
| Gemini 2.5 Pro | 180 | 300K | 5,000 | 高質量翻譯 |
| Gemini 3 Flash Preview | 300 | 800K | 8,000 | 最新功能測試 |
| Gemini 3 Pro Preview | 120 | 400K | 4,000 | 最新高級功能 |
| Gemini 2.0 Flash | 120 | 300K | 2,000 | 穩定版本 |
| Gemini 2.0 Flash Lite | 60 | 100K | 1,000 | 低成本 |
| Gemma 3 27B | 60 | 50K | 3,000 | 開源替代 |
| Gemma 3 12B | 100 | 80K | 5,000 | 輕量級 |
| Gemma 3 4B | 150 | 120K | 8,000 | 極輕量級 |

### 參數說明

#### RPM (Requests Per Minute)
```
每分鐘最多發送 rpm_limit 個 API 請求
超過時自動 sleep，等待最老請求超過 60 秒後再發新請求
```

#### TPM (Tokens Per Minute)
```
每分鐘最多送入 tpm_limit 個輸入權杖（tokens）
當前實現中未強制此限制（Gemini 自動處理）
```

#### RPD (Requests Per Day) ⚠️
```
每天 UTC 00:00 重置
是遠程 API 的最嚴格限制
超過時整個應用停止，需等待隔天
```

#### delay_between_requests
```
相鄰兩個 API 請求間的最小延遲（秒）
例如: delay = 0.5 表示最多每 0.5 秒發一個請求
```

#### batch_size
```
_process_segments_in_batches() 中
每個批次處理的片段數
越大越快（但回應可能變長而被截斷）
越小越安全（但總請求數增加）
```

#### max_retries & retry_delay_base
```
max_retries: 總重試次數（包括首次）
例如 max_retries=3 表示最多嘗試 3 次

retry_delay_base: 初始退避延遲
例如 retry_delay_base=5 表示:
    1st retry: sleep 5s
    2nd retry: sleep 10s
    3rd retry: sleep 20s (exponential)
```

---

## 📊 效能指標

### 典型運行時間（200 片段影片）

| 階段 | 耗時 | 備註 |
|------|------|------|
| YouTube 下載 | 2-5 min | 取決於影片時長 & 網速 |
| Whisper 轉錄 | 5-15 min | 純本地，取決於 CPU/GPU |
| Gemini 翻譯 (12 批次) | 3-8 min | 包含 API 延遲 & 重試 |
| MP3 提取 | 1-3 min | FFmpeg 壓縮 |
| 總計 | **11-31 min** | 端到端 |

### 資源消耗

| 資源 | 消耗量 |
|------|--------|
| CPU (Whisper) | 50-80% single core |
| RAM | 2-4 GB (base), 6-8 GB (large) |
| Disk (臨時) | 500MB - 2GB |
| API 費用 (Gemini) | $0.01 - $0.10 per video |
| API 配額 (per day) | 1-30 影片(取決於模型) |

---

## 🔧 擴展點

### 1. 增加新的 AI 模型
編輯 `model_config.json`，添加新模型配置

### 2. 支援新的影片平台
修改 `_download_youtube_video()`，支援其他 yt-dlp 支援的平台

### 3. 自訂翻譯提示
編輯 `_process_with_gemini()` 中的 `prompt` 變數

### 4. 增加播放器功能
繼承 `LanguagePlayer` 或修改其方法

---

**最後更新**: 2026-02-20
