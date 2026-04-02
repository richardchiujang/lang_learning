# AI_WORKSPACE.md

## 系統世界觀與 AI 定位

本專案是一個 AI 驅動的 YouTube 語音內容自動轉錄、翻譯與互動學習平台。

### 系統目標
- 自動下載 YouTube 影片
- Whisper 進行語音辨識
- Gemini/Claude 進行語意翻譯與合併
- 產出標準 JSON lesson，供桌面播放器互動學習

### 核心模組
- YouTubeContentFactory.py：下載、轉錄、翻譯主引擎
- YouTubeContentFactorySonnet.py：AWS Claude 3.5 Sonnet 版本
- desktop_player.py：桌面互動播放器
- model_config.json：AI 模型與配額設定

### AI 的角色
- 任務型 agent，負責自動化 pipeline
- 不主導 UI/UX 設計
- 不自由更改輸出格式
- 不主動重構架構

### 這份文件只提供 Context，不提供操作指令或約束
