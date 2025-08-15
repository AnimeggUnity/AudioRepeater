![image](https://github.com/AnimeggUnity/AudioRepeater/blob/f9fd7f8cb2f245a2e6c955c96b6ae876e8b11609/2025-08-15_235733.jpg)

# 音訊重複器 (Audio Repeater)

一個簡單易用的 Windows 程式，可以重複播放音訊檔案達到指定的時長。

## 功能特色

- **支援多種音訊格式**：可讀取 WAV, MP3, M4A, FLAC, OGG, AAC, WMA。
- **智慧格式處理**：若輸入與輸出格式相同（例如 MP3 到 MP3），採用無損合併，速度最快且不損失品質。
- **多種輸出選項**：支援輸出為 MP3, WAV, M4A, FLAC, OGG 格式。
- **無 FFmpeg 備援**：即使未安裝 FFmpeg，仍可處理 WAV 格式檔案的重複。
- **自動計算**：根據來源檔案時長與目標時間，自動計算需要重複的次數。
- **直觀的圖形化使用者介面**：所有操作一目了然。

## 安裝與使用

### 從原始碼執行

1.  **安裝 Python 依賴套件**：
    開啟終端機或命令提示字元，導航到專案目錄，然後執行以下命令安裝所需的套件：
    ```bash
    pip install -r requirements.txt
    ```
    如果您沒有 `requirements.txt` 檔案，可以手動安裝：
    ```bash
    pip install FreeSimpleGUI mutagen
    ```
2.  **運行程式**：
    安裝完成後，在終端機中執行：
    ```bash
    python audio_repeater.py
    ```

## 使用說明

1. **選擇音訊檔案**：點擊「瀏覽」按鈕選擇要重複的音訊檔案。
2. **設定目標時間**：在「目標時間」欄位輸入想要的總時長（分鐘）。
3. **選擇輸出格式**：程式會自動選擇與來源檔相同的格式以進行無損處理。您也可以手動更改為其他支援的格式（MP3, WAV, M4A, FLAC, OGG）。
4. **計算重複次數**：點擊「計算重複次數」預覽將執行的操作與最終時長。
5. **設定輸出檔名**：指定輸出檔案的名稱和位置。
6. **生成檔案**：點擊「生成檔案」開始處理。

## 系統需求

- Windows 10 或更新版本
- Python 3.7+ （如果從原始碼執行）
- **FFmpeg（強烈建議）**：用於處理 MP3, M4A, FLAC 等格式的轉換與合併。

### FFmpeg 安裝（建議）

為了使用本程式的完整功能（例如處理 MP3, M4A 等格式），建議安裝 FFmpeg。若您只處理 WAV 檔案，則非必需。

**方法一：簡單方式**
1. 下載 FFmpeg：https://ffmpeg.org/download.html 
2. 將 `ffmpeg.exe` 直接放到程式目錄。程式會自動偵測。

**方法二：系統安裝**
1. 下載 FFmpeg 完整版本。
2. 解壓縮到任意目錄。
3. 將其 `bin` 目錄加入系統 PATH 環境變數。

## 技術規格

- 使用 **FreeSimpleGUI** 建立使用者界面
- 使用 **mutagen** 讀取音訊檔案資訊
- 使用 **FFmpeg** 進行高效音訊合併（支援無損複製），並提供純 Python 的 WAV 處理備援方案
- 支援透過 **PyInstaller** 打包為可執行檔
