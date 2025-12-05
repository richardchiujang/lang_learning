import numpy as np
from scipy.io import wavfile
import os

# 設定輸出目錄
NOISE_DIR = "./noises"
os.makedirs(NOISE_DIR, exist_ok=True)

def generate_noise(color, duration_sec=60, sample_rate=44100):
    """
    生成不同顏色的噪音 (合成音效)
    White: 電視雜訊 (刺耳)
    Pink:  下雨聲/風聲 (柔和)
    Brown: 瀑布聲/遠方車流/機艙聲 (低沉，最適合閱讀)
    """
    print(f"正在生成 {color} noise ({duration_sec}秒)...")
    samples = int(duration_sec * sample_rate)
    
    if color == 'white':
        noise = np.random.normal(0, 1, samples)
    
    elif color == 'pink':
        # 粉紅噪音演算法 (1/f)
        uneven = sample_rate // 2
        X_white = np.fft.rfft(np.random.normal(0, 1, samples))
        S = np.sqrt(np.arange(X_white.size) + 1.)  # +1 to avoid divide by zero
        X_pink = X_white / S
        noise = np.fft.irfft(X_pink)
        
    elif color == 'brown':
        # 棕色噪音演算法 (1/f^2) - 聽起來像瀑布或機艙
        uneven = sample_rate // 2
        X_white = np.fft.rfft(np.random.normal(0, 1, samples))
        S = np.arange(X_white.size) + 1.  # +1 to avoid divide by zero
        X_brown = X_white / S
        noise = np.fft.irfft(X_brown)
    
    else:
        return

    # 正規化音量到 -20dB 左右，避免爆音
    noise = noise / np.max(np.abs(noise))
    data = (noise * 32767).astype(np.int16)
    
    # 存檔
    output_path = os.path.join(NOISE_DIR, f"synthetic_{color}.wav")
    wavfile.write(output_path, sample_rate, data)
    print(f"✅ 已生成: {output_path}")

def convert_mp3_to_wav(mp3_path):
    """使用 pydub 轉換 MP3 為 WAV (需要 ffmpeg)"""
    try:
        from pydub import AudioSegment
        
        filename = os.path.basename(mp3_path)
        base_name = os.path.splitext(filename)[0]
        wav_path = os.path.join(NOISE_DIR, f"{base_name}.wav")
        
        if os.path.exists(wav_path):
            print(f"⏭️ 跳過: {base_name}.wav 已存在")
            return wav_path
        
        print(f"🔄 轉換中: {filename} → {base_name}.wav...")
        audio = AudioSegment.from_mp3(mp3_path)
        audio.export(wav_path, format="wav")
        print(f"✅ 已轉換: {wav_path}")
        return wav_path
    except ImportError:
        print(f"⚠️ 跳過: 需要安裝 pydub (pip install pydub)")
        return None
    except Exception as e:
        print(f"❌ 轉換失敗 {filename}: {e}")
        return None

def check_downloaded_files():
    """檢查使用者是否已經放入了 MP3 或 WAV，並轉換 MP3 為 WAV"""
    # 修改：同時偵測 .mp3 和 .wav (不分大小寫)
    files = [f for f in os.listdir(NOISE_DIR) if f.lower().endswith(('.mp3', '.wav'))]
    
    # 轉換 MP3 為 WAV
    mp3_files = [f for f in files if f.lower().endswith('.mp3')]
    if mp3_files:
        print(f"\n🎵 偵測到 {len(mp3_files)} 個 MP3 檔案，正在轉換為 WAV...")
        for mp3_file in mp3_files:
            mp3_path = os.path.join(NOISE_DIR, mp3_file)
            convert_mp3_to_wav(mp3_path)
    
    if not files:
        print(f"\n⚠️ 提示: {NOISE_DIR} 資料夾是空的！")
        print("請去 https://mixkit.co/free-sound-effects/ 下載一些 mp3 或 wav 放進來。")
        print("推薦命名: airport.wav, cafe.mp3, traffic.wav")
    else:
        print(f"\n✅ 偵測到以下背景噪音檔 ({len(files)} 個):")
        for f in files:
            print(f"  - {f}")

if __name__ == "__main__":
    # 1. 自動生成合成噪音 (當作備用)
    generate_noise('brown', duration_sec=60) # 聽起來像機艙/瀑布
    generate_noise('pink', duration_sec=60)  # 聽起來像下雨
    
    # 2. 檢查下載檔案
    check_downloaded_files()