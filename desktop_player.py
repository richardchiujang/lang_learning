import sys
import os
import json
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QSlider, QComboBox, 
                             QFrame, QSizePolicy, QListWidget)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import QUrl, Qt, QTime

# --- 設定 ---
ASSETS_DIR = "./app_assets"
NOISE_DIR = "./noises"

class LanguagePlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 語言學習播放器 v6.0 (純音訊模式)")
        self.resize(1200, 850)

        # 資料變數
        self.current_json_data = None
        self.segments = []
        self.noises = self._scan_noises()
        
        # 狀態變數
        self.noise_target_volume = 0.3 # 記住使用者設定的噪聲最大音量 (0.0 ~ 1.0)
        self.video_duration = 0
        self.audio_only_mode = False  # 純音訊模式開關

        # 初始化 UI
        self._init_ui()
        self._init_media_players()
        
        # 啟動時掃描課程列表
        self._refresh_lesson_list()

    def _scan_noises(self):
        """掃描 noises 資料夾中的 WAV 檔案 (QMediaPlayer 對 WAV 的支援最佳)"""
        if not os.path.exists(NOISE_DIR):
            os.makedirs(NOISE_DIR)
            return []
        return [f for f in os.listdir(NOISE_DIR) if f.lower().endswith('.wav')]

    def _init_ui(self):
        """建立介面元件"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)

        # --- 1. 左側：課程播放清單 ---
        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(250)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
                font-size: 14px;
                border: 1px solid #3a3a3a;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3a3a3a;
            }
            QListWidget::item:selected {
                background-color: #4a90e2;
                color: white;
            }
        """)
        self.list_widget.itemClicked.connect(self.on_lesson_selected)
        main_layout.addWidget(self.list_widget)

        # --- 2. 右側：播放器區域 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(right_panel, stretch=1)

        # A. 影片區域
        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout.addWidget(self.video_widget, stretch=5)

        # B. 字幕區域
        subtitle_container = QFrame()
        subtitle_container.setStyleSheet("background-color: #1a1a1a; border-radius: 8px; margin: 10px; padding: 10px;")
        sub_layout = QVBoxLayout(subtitle_container)
        
        self.lbl_en = QLabel("Ready")
        self.lbl_en.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_en.setStyleSheet("font-size: 24px; font-family: Arial; color: #888;") 
        self.lbl_en.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_en.setWordWrap(True)
        
        self.lbl_zh = QLabel("請選擇課程")
        self.lbl_zh.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_zh.setStyleSheet("font-size: 20px; font-family: 'Microsoft JhengHei', sans-serif; color: #666;")
        self.lbl_zh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_zh.setWordWrap(True)

        sub_layout.addWidget(self.lbl_en)
        sub_layout.addWidget(self.lbl_zh)
        right_layout.addWidget(subtitle_container, stretch=2)

        # --- 新增：影片進度條區塊 ---
        progress_container = QWidget()
        progress_layout = QHBoxLayout(progress_container)
        progress_layout.setContentsMargins(10, 0, 10, 0)
        
        self.lbl_current_time = QLabel("00:00")
        self.lbl_total_time = QLabel("00:00")
        
        self.slider_video = QSlider(Qt.Orientation.Horizontal)
        self.slider_video.setRange(0, 0)
        self.slider_video.sliderMoved.connect(self.set_video_position) # 拖動時跳轉
        self.slider_video.sliderPressed.connect(self.video_slider_pressed) # 按下暫停更新
        self.slider_video.sliderReleased.connect(self.video_slider_released) # 放開恢復

        progress_layout.addWidget(self.lbl_current_time)
        progress_layout.addWidget(self.slider_video)
        progress_layout.addWidget(self.lbl_total_time)
        
        right_layout.addWidget(progress_container)

        # C. 控制面板
        control_panel = QFrame()
        control_layout = QHBoxLayout(control_panel)

        self.btn_play = QPushButton("▶ 播放")
        self.btn_play.setMinimumHeight(40)
        self.btn_play.clicked.connect(self.toggle_video)
        control_layout.addWidget(self.btn_play)

        # 音訊模式切換按鈕
        self.btn_audio_mode = QPushButton("🎵 純音訊")
        self.btn_audio_mode.setMinimumHeight(40)
        self.btn_audio_mode.setCheckable(True)
        self.btn_audio_mode.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 2px solid #555;
                border-radius: 5px;
                padding: 5px 10px;
                color: #e0e0e0;
            }
            QPushButton:checked {
                background-color: #4a90e2;
                border-color: #4a90e2;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        self.btn_audio_mode.toggled.connect(self.toggle_audio_mode)
        control_layout.addWidget(self.btn_audio_mode)

        control_layout.addWidget(QLabel("|"))  # 分隔線

        control_layout.addWidget(QLabel("速度:"))
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.5x","0.75x", "1.0x", "1.25x", "1.5x", "2.0x", "2.5x"])
        self.combo_speed.setCurrentText("1.0x")
        self.combo_speed.currentTextChanged.connect(self.change_speed)
        control_layout.addWidget(self.combo_speed)

        # 噪音選擇
        control_layout.addWidget(QLabel("| 噪音源:"))
        self.combo_noise = QComboBox()
        self.combo_noise.addItem("無噪音 (Off)")
        self.combo_noise.addItems(self.noises)
        self.combo_noise.currentTextChanged.connect(self.change_noise_source)
        control_layout.addWidget(self.combo_noise)

        # --- 新增：噪音密度 (Ratio) ---
        control_layout.addWidget(QLabel("密度:"))
        self.combo_noise_ratio = QComboBox()
        # 建立選項與數值的對應
        self.noise_ratios = {
            "100% (持續)": 1.0,
            "80%": 0.8,
            "70%": 0.7,
            "60%": 0.6,
            "50%": 0.5,
            "40%": 0.4,
            "30%": 0.3
        }
        self.combo_noise_ratio.addItems(list(self.noise_ratios.keys()))
        self.combo_noise_ratio.setCurrentText("100% (持續)")
        self.combo_noise_ratio.setFixedWidth(100)
        control_layout.addWidget(self.combo_noise_ratio)

        # 噪音音量
        control_layout.addWidget(QLabel("音量:"))
        self.slider_noise_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_noise_vol.setRange(0, 1000)
        self.slider_noise_vol.setValue(300)
        self.slider_noise_vol.setFixedWidth(80)
        self.slider_noise_vol.valueChanged.connect(self.change_noise_volume)
        control_layout.addWidget(self.slider_noise_vol)

        # 字幕控制
        control_layout.addWidget(QLabel("| 字幕:"))
        
        self.btn_subtitle_en = QPushButton("EN ✓")
        self.btn_subtitle_en.setCheckable(True)
        self.btn_subtitle_en.setChecked(True)
        self.btn_subtitle_en.setMaximumWidth(60)
        self.btn_subtitle_en.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 3px;
                color: #e0e0e0;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #4a90e2;
                border-color: #4a90e2;
                color: white;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        self.btn_subtitle_en.toggled.connect(self.toggle_subtitle_en)
        control_layout.addWidget(self.btn_subtitle_en)
        
        self.btn_subtitle_zh = QPushButton("中 ✓")
        self.btn_subtitle_zh.setCheckable(True)
        self.btn_subtitle_zh.setChecked(True)
        self.btn_subtitle_zh.setMaximumWidth(60)
        self.btn_subtitle_zh.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 3px;
                color: #e0e0e0;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #4a90e2;
                border-color: #4a90e2;
                color: white;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """)
        self.btn_subtitle_zh.toggled.connect(self.toggle_subtitle_zh)
        control_layout.addWidget(self.btn_subtitle_zh)

        right_layout.addWidget(control_panel)
        
        # 內部變數控制 slider 更新
        self.slider_being_dragged = False
        self.show_subtitle_en = True
        self.show_subtitle_zh = True

    def _init_media_players(self):
        self.player_video = QMediaPlayer()
        self.audio_video = QAudioOutput()
        self.player_video.setAudioOutput(self.audio_video)
        self.player_video.setVideoOutput(self.video_widget)
        
        # 綁定訊號
        self.player_video.positionChanged.connect(self.on_position_changed)
        self.player_video.durationChanged.connect(self.on_duration_changed)

        self.player_noise = QMediaPlayer()
        self.audio_noise = QAudioOutput()
        self.player_noise.setAudioOutput(self.audio_noise)
        self.player_noise.setLoops(-1)
        self.audio_noise.setVolume(0.3) 

    def _refresh_lesson_list(self):
        self.list_widget.clear()
        if not os.path.exists(ASSETS_DIR):
            self.lbl_en.setText(f"錯誤：找不到 {ASSETS_DIR}")
            return

        files = [f for f in os.listdir(ASSETS_DIR) if f.endswith(".json")]
        files.sort()

        if not files:
            self.lbl_en.setText("沒有課程資料")
            return

        # 載入每個 JSON 取得 title，並建立映射
        self.json_file_mapping = {}  # {display_title: json_filename}
        
        for f in files:
            json_path = os.path.join(ASSETS_DIR, f)
            try:
                with open(json_path, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    title = data.get('title', f.replace('.json', ''))  # 如果沒有 title 就用檔名
                    self.json_file_mapping[title] = f
                    self.list_widget.addItem(title)
            except Exception as e:
                print(f"無法讀取 {f}: {e}")
                # 讀取失敗時仍顯示檔名
                self.list_widget.addItem(f)
                self.json_file_mapping[f] = f
        
        self.list_widget.setCurrentRow(0)
        if files:
            first_title = self.list_widget.item(0).text()
            first_file = self.json_file_mapping.get(first_title, files[0])
            self.load_lesson(os.path.join(ASSETS_DIR, first_file))

    def on_lesson_selected(self, item):
        display_title = item.text()
        filename = self.json_file_mapping.get(display_title, display_title)
        json_path = os.path.join(ASSETS_DIR, filename)
        
        self.player_video.stop()
        self.player_noise.stop()
        self.btn_play.setText("▶ 播放")
        self.slider_video.setValue(0)
        self.lbl_current_time.setText("00:00")
        
        self.load_lesson(json_path)

    def load_lesson(self, json_path):
        print(f"Loading: {json_path}")
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.current_json_data = data
            self.segments = data.get("segments", [])
            
            video_filename = data.get("video_filename")
            video_path = os.path.join(ASSETS_DIR, video_filename)
            
            if os.path.exists(video_path):
                self.player_video.setSource(QUrl.fromLocalFile(os.path.abspath(video_path)))
                self.lbl_en.setText(f"<div style='color: white;'>{data.get('title', 'Ready')}</div>")
                self.lbl_zh.setText("<div style='color: #AAA;'>請按播放開始</div>")
            else:
                self.lbl_en.setText(f"<span style='color: red;'>影片遺失: {video_filename}</span>")
        except Exception as e:
            print(f"Load Error: {e}")
            self.lbl_en.setText("檔案讀取錯誤")

    def toggle_audio_mode(self, checked):
        """切換純音訊模式"""
        self.audio_only_mode = checked
        
        if checked:
            # 進入純音訊模式
            self.video_widget.hide()
            self.btn_audio_mode.setText("🎥 顯示影片")
            
            # 放大字幕區域
            self.lbl_en.setStyleSheet("font-size: 32px; font-family: Arial; color: #FFD700; font-weight: bold;")
            self.lbl_zh.setStyleSheet("font-size: 28px; font-family: 'Microsoft JhengHei', sans-serif; color: #e0e0e0;")
            
            print("🎵 已切換到純音訊模式 (節省電量)")
        else:
            # 返回影片模式
            self.video_widget.show()
            self.btn_audio_mode.setText("🎵 純音訊")
            
            # 恢復原始字幕大小
            self.lbl_en.setStyleSheet("font-size: 24px; font-family: Arial; color: #888;")
            self.lbl_zh.setStyleSheet("font-size: 20px; font-family: 'Microsoft JhengHei', sans-serif; color: #666;")
            
            print("🎥 已切換到影片模式")

    def toggle_video(self):
        if self.player_video.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player_video.pause()
            self.player_noise.pause() 
            self.btn_play.setText("▶ 播放")
        else:
            self.player_video.play()
            # 只有當選了噪音時才播放噪音，音量由邏輯控制
            if self.combo_noise.currentIndex() > 0:
                self.player_noise.play()
            self.btn_play.setText("❚❚ 暫停")

    def change_speed(self, text):
        speed = float(text.replace("x", ""))
        self.player_video.setPlaybackRate(speed)

    def change_noise_source(self, text):
        self.player_noise.stop()
        if text == "無噪音 (Off)":
            return
        
        noise_path = os.path.join(NOISE_DIR, text)
        if os.path.exists(noise_path):
            self.player_noise.setSource(QUrl.fromLocalFile(os.path.abspath(noise_path)))
            if self.player_video.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player_noise.play()

    def change_noise_volume(self, value):
        # 更新目標音量 (slider 範圍 0-1000 對應 0.0-1.0)
        self.noise_target_volume = value / 1000.0
        # 如果目前是 100% 模式，直接更新音量，否則等待下一次循環更新
        ratio_text = self.combo_noise_ratio.currentText()
        if ratio_text == "100% (持續)":
             self.audio_noise.setVolume(self.noise_target_volume)

    def toggle_subtitle_en(self, checked):
        """切換英文字幕"""
        self.show_subtitle_en = checked
        self.btn_subtitle_en.setText("EN ✓" if checked else "EN ✗")
        # 立即更新字幕顯示
        if self.player_video.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.on_position_changed(self.player_video.position())
        elif self.segments:
            # 如果沒在播放，也要更新一下字幕顯示
            self.on_position_changed(0)

    def toggle_subtitle_zh(self, checked):
        """切換中文字幕"""
        self.show_subtitle_zh = checked
        self.btn_subtitle_zh.setText("中 ✓" if checked else "中 ✗")
        # 立即更新字幕顯示
        if self.player_video.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.on_position_changed(self.player_video.position())
        elif self.segments:
            # 如果沒在播放，也要更新一下字幕顯示
            self.on_position_changed(0)

    # --- 影片進度條相關 ---
    def on_duration_changed(self, duration):
        self.video_duration = duration
        self.slider_video.setRange(0, duration)
        self.lbl_total_time.setText(self.format_time(duration))

    def set_video_position(self, position):
        self.player_video.setPosition(position)

    def video_slider_pressed(self):
        self.slider_being_dragged = True

    def video_slider_released(self):
        self.slider_being_dragged = False

    def format_time(self, ms):
        seconds = (ms // 1000) % 60
        minutes = (ms // 60000)
        return f"{minutes:02}:{seconds:02}"

    # --- 核心邏輯：位置更新 (包含字幕與噪音控制) ---
    def on_position_changed(self, position_ms):
        # 1. 更新 Slider 與 時間顯示
        if not self.slider_being_dragged:
            self.slider_video.setValue(position_ms)
        self.lbl_current_time.setText(self.format_time(position_ms))

        # 2. 更新字幕 (雙語高亮)
        self.update_subtitle(position_ms)

        # 3. 更新間歇性噪音 (Intermittent Noise Logic)
        self.update_noise_intermittence(position_ms)

    def update_noise_intermittence(self, position_ms):
        """根據設定的比例，週期性開關噪音音量"""
        # 如果沒有選擇噪音，直接跳過
        if self.combo_noise.currentIndex() == 0:
            return

        ratio_text = self.combo_noise_ratio.currentText()
        ratio = self.noise_ratios.get(ratio_text, 1.0)

        # 如果是 100%，保持最大音量
        if ratio >= 1.0:
            if self.audio_noise.volume() != self.noise_target_volume:
                self.audio_noise.setVolume(self.noise_target_volume)
            return

        # 週期設定：2000ms (2秒)
        # 邏輯：先靜音(Off)，再開啟(On)。
        # 例如 50% -> 1000ms 靜音, 1000ms 噪音
        # 例如 30% -> 1400ms 靜音, 600ms 噪音
        cycle_duration = 2000 
        on_duration = cycle_duration * ratio
        off_duration = cycle_duration - on_duration
        
        cycle_pos = position_ms % cycle_duration

        if cycle_pos < off_duration:
            # 在 "靜音" 區間
            self.audio_noise.setVolume(0)
        else:
            # 在 "噪音" 區間 -> 恢復使用者設定的音量
            self.audio_noise.setVolume(self.noise_target_volume)

    def update_subtitle(self, position_ms):
        """雙語字幕高亮邏輯 (相容兩種 JSON 格式 + keywords 紅字顯示 + 精確 word-level 時間戳)"""
        current_sec = position_ms / 1000.0
        
        found_segment = False
        for seg in self.segments:
            # 相容兩種格式：Gemini 處理後 (start_time/end_time) 和 Whisper 原始 (start/end)
            start_time = seg.get('start_time', seg.get('start', 0))
            end_time = seg.get('end_time', seg.get('end', 0))
            
            if start_time <= current_sec <= end_time:
                found_segment = True
                
                # 相容兩種格式
                text_en = seg.get('text_en', seg.get('text', ''))
                text_zh = seg.get('text_zh', '[無中文翻譯]')
                keywords = seg.get('keywords', [])
                words_data = seg.get('words', [])  # 取得 word-level timestamps

                # A. 英文 (優先使用 word-level timestamps，回退到進度估算)
                if words_data:
                    # 使用精確的 word-level timestamps
                    en_html_parts = []
                    for word_info in words_data:
                        word = word_info.get('word', '').strip()
                        word_start = word_info.get('start', 0)
                        word_end = word_info.get('end', 0)
                        
                        # 移除標點符號來比對 keywords
                        clean_word = word.strip('.,!?;:\'"').lower()
                        is_keyword = any(kw.lower() == clean_word for kw in keywords)
                        
                        # 檢查當前時間是否在此單字的時間範圍內
                        is_current = word_start <= current_sec <= word_end
                        
                        if is_current:
                            # 當前播放的單字 (金色高亮) - 優先顯示
                            en_html_parts.append(f"<span style='color: #FFD700; font-weight: bold; font-size: 1.2em;'>{word}</span>")
                        elif is_keyword:
                            # keywords 顯示為粗體紅字 (未播放到時)
                            en_html_parts.append(f"<span style='color: #FF4444; font-weight: bold; font-size: 1.1em;'>{word}</span>")
                        else:
                            # 其他單字
                            en_html_parts.append(f"<span style='color: #DDDDDD;'>{word}</span>")
                    final_html_en = " ".join(en_html_parts)
                else:
                    # 回退到舊的進度估算方式 (當沒有 word-level timestamps 時)
                    seg_duration = end_time - start_time
                    time_elapsed = current_sec - start_time
                    progress = 0.0
                    if seg_duration > 0:
                        progress = time_elapsed / seg_duration
                    
                    words = text_en.split(' ')
                    word_count = len(words)
                    en_html_parts = []
                    if word_count > 0:
                        current_word_idx = int(progress * word_count)
                        current_word_idx = max(0, min(current_word_idx, word_count - 1))
                        for i, word in enumerate(words):
                            clean_word = word.strip('.,!?;:\'"').lower()
                            is_keyword = any(kw.lower() == clean_word for kw in keywords)
                            
                            if is_keyword:
                                en_html_parts.append(f"<span style='color: #FF4444; font-weight: bold; font-size: 1.2em;'>{word}</span>")
                            elif current_word_idx - 2 <= i <= current_word_idx + 2:
                                en_html_parts.append(f"<span style='color: #FFD700; font-weight: bold; font-size: 1.1em;'>{word}</span>")
                            else:
                                en_html_parts.append(f"<span style='color: #DDDDDD;'>{word}</span>")
                    final_html_en = " ".join(en_html_parts)

                # B. 中文 (使用進度估算)
                seg_duration = end_time - start_time
                time_elapsed = current_sec - start_time
                progress = 0.0
                if seg_duration > 0:
                    progress = time_elapsed / seg_duration
                
                chars = list(text_zh) 
                char_count = len(chars)
                zh_html_parts = []
                if char_count > 0:
                    current_char_idx = int(progress * char_count)
                    current_char_idx = max(0, min(current_char_idx, char_count - 1))
                    for i, char in enumerate(chars):
                        if current_char_idx - 2 <= i <= current_char_idx + 2:
                            zh_html_parts.append(f"<span style='color: #FFD700; font-weight: bold; font-size: 1.1em;'>{char}</span>")
                        else:
                            zh_html_parts.append(f"<span style='color: #DDDDDD;'>{char}</span>")
                final_html_zh = "".join(zh_html_parts)

                if self.show_subtitle_en:
                    self.lbl_en.setText(f"<div style='text-align: center;'>{final_html_en}</div>")
                else:
                    self.lbl_en.setText("")
                
                if self.show_subtitle_zh:
                    self.lbl_zh.setText(f"<div style='text-align: center;'>{final_html_zh}</div>")
                else:
                    self.lbl_zh.setText("")
                break
        
        if not found_segment:
            pass
    
    def update_subtitle_visibility(self):
        """根據設定更新字幕可見性"""
        if not self.show_subtitle_en:
            self.lbl_en.setText("")
        if not self.show_subtitle_zh:
            self.lbl_zh.setText("")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LanguagePlayer()
    window.show()
    sys.exit(app.exec())