# 音訊重複器 (Audio Repeater)

一個簡單易用的 Windows 程式，可以重複播放音訊檔案達到指定的時長。

## 功能特色

- 支援多種音訊格式：WAV, MP3, M4A, FLAC, OGG, AAC, WMA
- 自動計算音訊檔案時長
- 設定目標時間（分鐘），自動計算需要重複次數
- 支援輸出為 MP3 或 WAV 格式
- 直觀的圖形化使用者介面

## 安裝與使用

### 方法一：使用可執行檔（推薦）
1. 下載 `AudioRepeater.exe`
2. 雙擊執行即可

### 方法二：從原始碼執行
1. 執行 `setup_clean_env.ps1` 建立虛擬環境
2. 運行 `python audio_repeater.py`

### 方法三：建立可執行檔
1. 執行 `setup_clean_env.ps1` 建立虛擬環境
2. 啟動虛擬環境：`venv_clean\Scripts\Activate.ps1`
3. 運行 `python build_exe.py`
4. 可執行檔會在 `dist` 資料夾中

## 使用說明

1. **選擇音訊檔案**：點擊「瀏覽」按鈕選擇要重複的音訊檔案
2. **設定目標時間**：在「目標時間」欄位輸入想要的總時長（分鐘）
3. **計算重複次數**：點擊「計算重複次數」查看需要重複幾次
4. **選擇輸出格式**：選擇 MP3 或 WAV 格式
5. **設定輸出檔名**：指定輸出檔案的名稱和位置
6. **生成檔案**：點擊「生成檔案」開始處理

## 系統需求

- Windows 10 或更新版本
- Python 3.7+ （如果從原始碼執行）
- FFmpeg （用於音訊合併功能）

### FFmpeg 安裝（必需）

**方法一：簡單方式**
1. 下載 FFmpeg：https://ffmpeg.org/download.html 
2. 將 `ffmpeg.exe` 直接放到程式目錄 (`C:\Work\Wav_project\`)

**方法二：系統安裝**
1. 下載 FFmpeg 完整版本
2. 解壓縮到任意目錄（如 C:\ffmpeg）
3. 將 ffmpeg\bin 目錄加入系統 PATH 環境變數

## 技術規格

- 使用 FreeSimpleGUI 建立使用者界面
- 使用 mutagen 讀取音訊檔案資訊
- 使用 FFmpeg 進行音訊合併
- 支援透過 PyInstaller 打包為可執行檔
