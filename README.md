# 🎓 AI 語言學習系統

一個基於 AI 的全自動 YouTube 影片轉錄、翻譯與互動式語言學習平台。支援多個先進 AI 模型（Google Gemini、Amazon Bedrock Claude）與桌面播放器。

## 📋 專案概述

### 核心功能

本專案由四個主要模組組成，共同實現從影片下載、語音轉錄、AI 翻譯，到互動式學習的完整工作流程：

---

## 🔧 專案模組說明

### 1️⃣ **YouTubeContentFactory.py** - 核心內容處理引擎
**用途**: 自動化 YouTube 影片內容處理與 AI 翻譯

**主要功能**：
- 🎥 **自動下載**: 從 YouTube URL 下載高品質影片（最高 720p）
- 🎤 **語音轉錄**: 使用 OpenAI Whisper 進行多語言語音辨識（word-level timestamps）
- 🧠 **AI 翻譯**: 呼叫 Google Gemini API 進行英文→繁體中文翻譯與語意合併
- 🎵 **多音訊格式**: 同時輸出 WAV（轉錄用）與 MP3（播放用）
- ⚡ **批次處理**: 支援大量影片的自動化處理
- 📊 **配額管理**: 智慧 RPM/TPM/RPD 限制追蹤與自動退避

**支援模型**（來源：model_config.json）：
- Gemini 2.5 Flash（RPD: 10,000 - 推薦用於大批量）
- Gemini 2.5 Pro（RPD: 5,000 - 專業版）
- Gemini 3 Flash/Pro Preview（RPD: 8,000/4,000 - 最新功能）
- Gemma 3 系列（4B, 12B, 27B - 輕量級替代方案）

**輸出格式**：
```json
{
  "lesson_id": "video_id",
  "title": "影片標題",
  "source_url": "https://youtube.com/...",
  "duration": 1234.56,
  "segments": [
    {
      "id": 0,
      "start_time": 0.0,
      "end_time": 5.5,
      "text_en": "English transcription",
      "text_zh": "繁體中文翻譯",
      "keywords": ["key", "words"],
      "words": [{"word": "text", "start": 0.0, "end": 1.2}, ...]
    }
  ]
}
```

---

### 2️⃣ **YouTubeContentFactorySonnet.py** - 替代方案（AWS Bedrock）
**用途**: 使用 Amazon Bedrock 上的 Claude 3.5 Sonnet 進行內容處理

**主要差異**：
- 🏢 **雲端服務**: 透過 AWS Bedrock 而非 Google Gemini
- 🔄 **智慧降級**: 預設優先使用 Bedrock，失敗時自動降級至 Gemini
- 🔐 **環保變數支援**: 支援從環保變數讀取 API 金鑰
- 📝 **相同輸出**: 生成相同格式的 JSON 檔案

**適用場景**：
- 已有 AWS Bedrock 帳戶的用戶
- 需要 Claude 3.5 Sonnet 的專業翻譯質量
- 想要多模型備援策略

**配置**（需要）：
- AWS 認證（IAL 或 Access Keys）
- Bedrock 地域設置（預設: ap-southeast-1, us-east-1）

---

### 3️⃣ **desktop_player.py** - 互動式學習播放器
**用途**: 桌面應用程式，用於播放與互動式學習轉錄內容

**核心特性**：
- 📂 **課程管理**: 自動掃描 `app_assets/` 目錄中的所有 JSON 課程
- 🎵 **同步播放**: 跟蹤音訊位置，自動顯示當前片段
- 🔤 **雙語字幕**: 實時顯示英文與中文翻譯（可個別切換）
- 🔊 **背景噪聲**: 支援混合環境噪聲（檔案在 `noises/`），模擬真實環境
- ⏱️ **進度控制**: 拖曳進度條、播放速度調整（0.5x - 2.0x）
- 🎯 **片段導航**: 點選列表快速跳轉到任意片段
- 📊 **統計資訊**: 顯示影片時長、已播放比例等
- 💾 **進度保存**: 自動記錄播放位置（下次開啟時恢復）

**UI 模式**：
- **純音訊模式**（預設）: 只顯示音訊與字幕（輕量級）
- **視頻模式**（可選）: 同時顯示視頻影像（如果 MP4 可用）

**依賴庫**：
- PySide6 - 現代 PyQt6 綁定
- Whisper（可選）- 本地語音轉錄備援

---

### 4️⃣ **desktop_player.spec** - 可執行檔配置
**用途**: PyInstaller 配置，用於將 `desktop_player.py` 編譯成獨立的 Windows/Mac/Linux 可執行檔

**功能**：
- 🔨 **一鍵打包**: 將 Python 應用轉換為 `.exe`（Windows）或 `.app`（Mac）
- 🎯 **依賴管理**: 自動包含 PySide6 與其他必要庫
- 🔒 **不需 Python**: 最終用戶無需安裝 Python 運行

**使用方式**：
```bash
pyinstaller desktop_player.spec
```

生成的可執行檔位於 `dist/desktop_player/` 目錄

---

## 🚀 快速開始

### 環境設置

```bash
# 1. 安裝依賴
pip install -r requirements.txt

# 2. 設定 API Key（選擇一個）
# 選項 A: Gemini（推薦）
echo "your-gemini-api-key" > GEMINI_API_KEY.txt

# 選項 B: 環保變數
export GEMINI_API_KEY="your-api-key"    # Linux/Mac
set GEMINI_API_KEY=your-api-key         # Windows CMD
```

### 工作流程

#### 方案 A: 使用 Gemini（Google）
```bash
python YouTubeContentFactory.py
```
需要 `video_urls.json` 檔案：
```json
[
  "https://www.youtube.com/watch?v=VIDEO_ID_1",
  {
    "url": "https://www.youtube.com/watch?v=VIDEO_ID_2",
    "description": "影片描述"
  }
]
```

#### 方案 B: 使用 Bedrock（AWS）
```bash
python YouTubeContentFactorySonnet.py
```
需要 AWS 認證設置

#### 啟動播放器
```bash
python desktop_player.py
```

---

## 📁 檔案結構

```
lang_learning/
├── YouTubeContentFactory.py          # Gemini 版本
├── YouTubeContentFactorySonnet.py    # Bedrock 版本
├── desktop_player.py                  # 播放器應用
├── desktop_player.spec                # PyInstaller 配置
├── model_config.json                  # AI 模型配置（9 個預設模型）
├── GEMINI_API_KEY.txt                # Gemini API Key（需自行填入）
├── video_urls.json                    # 影片列表配置
├── requirements.txt                   # Python 依賴清單
│
├── app_assets/                        # 處理結果輸出目錄
│   ├── {video_id}.json               # 轉錄與翻譯結果
│   ├── {video_id}.mp3                # 提取的音訊（MP3 格式）
│   └── {video_id}.mp4                # 原始影片
│
├── temp_downloads/                    # 臨時檔案目錄
│   └── {video_id}.wav                # 臨時音訊（WAV 格式）
│
└── noises/                            # 背景噪聲檔案
    ├── office.wav                    # 辦公室噪聲
    ├── coffee.wav                    # 咖啡館噪聲
    └── ...
```

---

## ⚙️ 配置文件說明

### `model_config.json`
定義所有可用的 AI 模型及其 API 限制參數：
- **RPM**: 每分鐘請求數限制
- **TPM**: 每分鐘輸入權杖數限制  
- **RPD**: 每天請求數限制（⚠️ 最關鍵）
- **batch_size**: 每次批次處理的片段數
- **delays/timeouts**: 速率控制參數

### `video_urls.json`
支援兩種格式：
```json
[
  "https://...",                      // 簡單 URL
  {
    "url": "https://...",
    "description": "課程名稱"
  }
]
```

---

## 📊 輸出統計

典型運行結果（以 200 片段影片為例）：

| 階段 | 耗時 | 說明 |
|------|------|------|
| 下載 | 2-5 min | 取決於影片長度與網路 |
| 轉錄 (Whisper) | 5-15 min | 純本地，依 CPU 性能 |
| 翻譯 (Gemini) | 3-8 min | 包含 API 延遲與批次處理 |
| 總計 | **10-30 min** | 端到端處理時間 |

**輸出檔案大小**：
- JSON: 500KB - 2MB
- MP3: 5-50MB
- MP4: 100-1000MB

---

## 🔑 API 金鑰管理

### 安全建議
1. ✅ **使用檔案**: 填入 `GEMINI_API_KEY.txt`（Git 忽略此檔案）
2. ✅ **環保變數**: `export GEMINI_API_KEY="..."`
3. ❌ **硬編碼**: 不要在程式碼中直接寫入金鑰

### Gemini API 額度檢查
訪問: https://aistudio.google.com/app/apikey

### AWS Bedrock 設置
```bash
aws configure
# 設定 AWS Access Key ID、Secret Access Key 與地域
```

---

## 🐛 常見問題與排查

### HTTP 403 Forbidden（YouTube 下載失敗）
原因可能為：地理限制、年齡限制、帳號驗證

**解決方案**（按優先級）：
1. 升級 yt-dlp: `pip install -U yt-dlp`
2. 使用 User-Agent 偽裝: 見 YouTubeContentFactory.py 中的 `_download_youtube_video()` 方法
3. 啟用 Cookie: 從 Chrome 匯出 cookies.txt，參考 yt-dlp 文件
4. 使用 VPN 切換地區

### Gemini API 配額用盡
**症狀**: `ResourceExhausted` 或 `RESOURCE_EXHAUSTED` 錯誤

**解決方案**：
1. 檢查日限額: `factory._check_daily_limit()`
2. 切換模型至 RPD 更高的: `factory.switch_model('Gemini 2.5 Flash')`
3. 增加 `delay_between_requests` 或減少 `batch_size`
4. 等待至隔天 UTC 00:00 重置

### Whisper 轉錄效果差
**症狀**: 轉錄內容有大量錯誤或遺漏

**改善方案**：
1. 嘗試更大的 Whisper 模型: `whisper.load_model("medium")` 或 `"large"`
2. 確保輸入音訊清晰（檢查 `temp_downloads/*.wav`）
3. 如需更精準的商用級轉錄，考慮使用 Assembly AI 或 Rev.AI

---

## 📈 效能優化建議

| 動作 | 效果 | 難度 |
|------|------|------|
| 使用更大 Whisper 模型 | +20% 精準度 | ⭐ |
| 降低視頻解析度（MP4） | -30% 空間 | ⭐ |
| 增加批次大小 | -15% API 時間 | ⭐ |
| 使用 Bedrock + 本地緩存 | -40% API 成本 | ⭐⭐ |
| 並行處理多影片 | -50% 總時間 | ⭐⭐⭐ |

---

## 📝 開發環境

**已測試環境**：
- Python 3.10+
- Windows 10/11, macOS 12+, Ubuntu 20.04+
- Conda 虛擬環境 (`conda_envs/lang_learn`)

**核心依賴版本**（見 `requirements.txt`）：
- openai-whisper ≥ 20240101
- google-generativeai ≥ 0.7.0
- yt-dlp ≥ 2024.01.01
- PySide6 ≥ 6.6.0
- boto3 ≥ 1.34.0（Bedrock 需求）

---

## 🤝 貢獻與反饋

遇到問題？有改進建議？
- 檢查 [常見問題](#-常見問題與排查) 部分
- 查看 `COMPLETION_REPORT.md` 與 `CHANGELOG.md` 了解更新歷史
- 查看 `proj_spec.md` 了解詳細的程式碼規格

---

## 📄 授權

詳見 [LICENSE](LICENSE) 檔案

---

**最後更新**: 2026-02-20
