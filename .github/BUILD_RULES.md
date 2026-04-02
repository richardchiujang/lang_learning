# BUILD_RULES.md

## Build/Test/執行規則（給人、CI、AI看的唯一真相）

### 作業系統/終端機
- **僅支援 Windows，預設 terminal 必須為 cmd（嚴禁 powershell）**

### Python 環境
- 必須使用 conda 環境：`D:\conda_envs\lang_learn`
- 啟動：
  ```cmd
  conda activate D:\conda_envs\lang_learn
  ```
- 直接執行：
  ```cmd
  D:\conda_envs\lang_learn\python.exe your_script.py
  ```

### 安裝依賴
```cmd
REM 請在 cmd 或 Anaconda Prompt 執行，不要用 powershell
```

### 測試
```cmd
REM 請在 cmd 或 Anaconda Prompt 執行，不要用 powershell
```

### Build 桌面 app
```cmd
D:/anaconda3/Scripts/conda.exe run -p D:\conda_envs\lang_learn pyinstaller --clean desktop_player.spec
xcopy /E /I /Y app_assets dist\app_assets & xcopy /E /I /Y noises dist\noises & echo "打包完成"
```

### 常見陷阱
- PySide6、Whisper 需額外系統依賴，詳見 README
- 路徑請用相對路徑，避免跨平台問題
- API 配額超過會中斷，請監控

### 這份文件內容不可優化、不可重構、不可自動調整
