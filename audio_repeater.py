#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import FreeSimpleGUI as sg
import os
import math
from pathlib import Path
from mutagen import File
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis

class AudioRepeater:
    def __init__(self):
        self.supported_formats = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.aac', '.wma']
        
    def get_audio_duration(self, file_path):
        """獲取音訊檔案的時長（秒）"""
        try:
            audio_file = File(file_path)
            if audio_file is not None and hasattr(audio_file, 'info'):
                return audio_file.info.length
            return None
        except Exception as e:
            return None
            
    def calculate_repeat_count(self, audio_duration, target_minutes):
        """計算需要重複的次數"""
        target_seconds = target_minutes * 60
        return math.ceil(target_seconds / audio_duration)
        
    def create_repeated_audio(self, file_path, repeat_count, output_path, output_format):
        """創建重複音訊檔案"""
        try:
            import subprocess
            import shutil
            
            # 檢查 ffmpeg 是否可用（先檢查同目錄，再檢查 PATH）
            ffmpeg_path = None
            local_ffmpeg = os.path.join(os.getcwd(), 'ffmpeg.exe')
            
            if os.path.exists(local_ffmpeg):
                ffmpeg_path = local_ffmpeg
            elif os.path.exists('ffmpeg.exe'):
                ffmpeg_path = 'ffmpeg.exe'
            elif shutil.which('ffmpeg'):
                ffmpeg_path = 'ffmpeg'
            else:
                # 沒有 ffmpeg，檢查是否可以用純 Python 方式處理
                input_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                output_ext = output_format.lower()
                
                if input_ext == 'wav' and output_ext == 'wav':
                    # 只有 WAV 格式可以用純 Python 可靠處理
                    return self._create_repeated_wav_python(file_path, repeat_count, output_path)
                else:
                    return False, "錯誤：找不到 ffmpeg.exe。僅支援 WAV 格式，其他格式需要 ffmpeg 正確處理檔頭", None
            
            # 創建臨時檔案列表
            temp_dir = os.path.dirname(output_path)
            list_file = os.path.join(temp_dir, 'filelist.txt')
            
            with open(list_file, 'w', encoding='utf-8') as f:
                for i in range(repeat_count):
                    f.write(f"file '{os.path.abspath(file_path)}'\n")
            
            # 使用 ffmpeg 合併檔案
            # 檢查輸入和輸出格式是否相同
            input_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
            output_ext = output_format.lower()
            
            # 由於界面已經確保格式一致，直接使用 output_path
            corrected_output_path = output_path
            
            # 格式對應關係
            format_mapping = {
                'm4a': 'mp4',  # m4a 實際上是 mp4 容器
                'mp4': 'mp4',
                'mp3': 'mp3',
                'wav': 'wav',
                'flac': 'flac',
                'ogg': 'ogg'
            }
            
            input_format = format_mapping.get(input_ext, input_ext)
            target_format = format_mapping.get(output_ext, output_ext)
            
            if input_format == target_format or (input_ext == 'm4a' and output_ext == 'm4a'):
                # 同格式或都是 m4a，直接複製（最快，無損）
                cmd = [
                    ffmpeg_path, '-y', '-f', 'concat', '-safe', '0',
                    '-i', list_file, '-c', 'copy', corrected_output_path
                ]
            elif output_format.lower() == 'mp3':
                # 轉換為 MP3
                cmd = [
                    ffmpeg_path, '-y', '-f', 'concat', '-safe', '0',
                    '-i', list_file, '-c:a', 'libmp3lame', '-b:a', '192k', corrected_output_path
                ]
            elif output_format.lower() == 'wav':
                # 轉換為 WAV
                cmd = [
                    ffmpeg_path, '-y', '-f', 'concat', '-safe', '0',
                    '-i', list_file, '-c:a', 'pcm_s16le', corrected_output_path
                ]
            else:
                # 其他格式嘗試直接複製
                cmd = [
                    ffmpeg_path, '-y', '-f', 'concat', '-safe', '0',
                    '-i', list_file, '-c', 'copy', corrected_output_path
                ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # 清理臨時檔案
            if os.path.exists(list_file):
                os.remove(list_file)
                
            if result.returncode == 0:
                return True, f"成功創建檔案：{corrected_output_path}", corrected_output_path
            else:
                return False, f"ffmpeg 錯誤：{result.stderr}", None
                
        except Exception as e:
            return False, f"錯誤：{str(e)}", None
    
    def _create_repeated_wav_python(self, file_path, repeat_count, output_path):
        """使用純 Python 重複 WAV 檔案（正確處理檔頭）"""
        try:
            import wave
            
            # 開啟原始 WAV 檔案
            with wave.open(file_path, 'rb') as input_wav:
                # 獲取音訊參數
                params = input_wav.getparams()
                frames = input_wav.readframes(params.nframes)
                
            # 創建輸出 WAV 檔案
            with wave.open(output_path, 'wb') as output_wav:
                output_wav.setparams(params)
                
                # 重複寫入音訊資料
                for i in range(repeat_count):
                    output_wav.writeframes(frames)
                    
            return True, f"成功創建檔案：{output_path}（純 Python WAV 處理）", output_path
            
        except Exception as e:
            return False, f"WAV 處理錯誤：{str(e)}", None

def create_gui():
    sg.theme('LightBlue3')
    
    layout = [
        [sg.Text('音訊重複器', font=('Arial', 16, 'bold'), justification='center')],
        [sg.HSeparator()],
        [sg.Text('FFmpeg 狀態:', size=(15, 1)), 
         sg.Text('檢查中...', key='-FFMPEG_STATUS-', size=(40, 1))],
        
        [sg.Text('選擇音訊檔案:', size=(15, 1)), 
         sg.Input(key='-FILE-', size=(40, 1), enable_events=True), 
         sg.FileBrowse(file_types=(('音訊檔案', '*.wav *.mp3 *.m4a *.flac *.ogg *.aac *.wma'),))],
        
        [sg.Text('檔案時長:', size=(15, 1)), 
         sg.Text('未選擇檔案', key='-DURATION-', size=(30, 1), text_color='gray')],
        
        [sg.Text('目標時間(分鐘):', size=(15, 1)), 
         sg.Input(key='-TARGET_TIME-', size=(10, 1)), 
         sg.Text('分鐘')],
        
        [sg.Button('計算重複次數', size=(15, 1))],
        
        [sg.Text('需要重複次數:', size=(15, 1)), 
         sg.Text('--', key='-REPEAT_COUNT-', size=(10, 1))],
        
        [sg.Text('輸出格式:', size=(15, 1)), 
         sg.Combo(['mp3', 'wav', 'm4a', 'flac', 'ogg'], default_value='', key='-OUTPUT_FORMAT-', size=(10, 1), enable_events=True)],
        
        [sg.Text('檔案名稱:', size=(15, 1)), 
         sg.Input(key='-OUTPUT_NAME-', size=(25, 1)), 
         sg.Text('', key='-FILE_EXT-', size=(5, 1))],
        
        [sg.Text('輸出位置:', size=(15, 1)), 
         sg.Input(key='-OUTPUT_DIR-', size=(30, 1)), 
         sg.FolderBrowse('選擇資料夾')],
        
        [sg.HSeparator()],
        
        [sg.Button('生成檔案', size=(15, 1)), 
         sg.Button('退出', size=(15, 1))],
        
        [sg.HSeparator()],
        
        [sg.Multiline(size=(70, 8), key='-OUTPUT-', disabled=True, autoscroll=True)]
    ]
    
    return sg.Window('音訊重複器', layout, finalize=True)

def main():
    import shutil
    
    repeater = AudioRepeater()
    window = create_gui()
    
    # 檢查 ffmpeg（先檢查同目錄，再檢查 PATH）
    if os.path.exists('ffmpeg.exe'):
        window['-FFMPEG_STATUS-'].update('本地 ffmpeg.exe - 支援所有格式', text_color='green')
    elif shutil.which('ffmpeg'):
        window['-FFMPEG_STATUS-'].update('系統 PATH 中的 ffmpeg - 支援所有格式', text_color='orange')
    else:
        window['-FFMPEG_STATUS-'].update('未找到 ffmpeg - 僅支援 WAV 格式', text_color='red')
    
    # 初始化檔案副檔名顯示（空值）
    
    # 初始化輸出目錄為當前目錄
    window['-OUTPUT_DIR-'].update(os.getcwd())
    
    while True:
        event, values = window.read()
        
        if event == sg.WIN_CLOSED or event == '退出':
            break
            
        elif event == '-OUTPUT_FORMAT-':
            # 當輸出格式改變時，更新副檔名顯示
            selected_format = values['-OUTPUT_FORMAT-']
            window['-FILE_EXT-'].update(f'.{selected_format}')
            
        elif event == '-FILE-':
            file_path = values['-FILE-']
            if file_path and os.path.exists(file_path):
                window['-DURATION-'].update('讀取中...', text_color='orange')
                window.refresh()
                
                duration = repeater.get_audio_duration(file_path)
                if duration:
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    window['-DURATION-'].update(f'{minutes}分{seconds}秒 ({duration:.2f}秒)', text_color='green')
                    
                    # 獲取檔案格式並自動設為輸出格式
                    input_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                    input_format = input_ext.upper()
                    
                    # 檢查 ffmpeg 可用性
                    has_ffmpeg = (os.path.exists('ffmpeg.exe') or shutil.which('ffmpeg'))
                    
                    # 設定輸出格式為原始格式（如果支援的話）
                    if input_ext in ['mp3', 'wav', 'm4a', 'flac', 'ogg']:
                        window['-OUTPUT_FORMAT-'].update(input_ext)
                        window['-FILE_EXT-'].update(f'.{input_ext}')
                        window['-OUTPUT-'].print(f'已載入檔案: {os.path.basename(file_path)}')
                        window['-OUTPUT-'].print(f'檔案格式: {input_format}, 時長: {minutes}分{seconds}秒')
                        
                        if input_ext == 'wav':
                            window['-OUTPUT-'].print(f'輸出格式已設為: {input_format} (純 Python，完全支援)')
                        elif has_ffmpeg:
                            window['-OUTPUT-'].print(f'輸出格式已設為: {input_format} (ffmpeg 無損複製)')
                        else:
                            window['-OUTPUT-'].print(f'輸出格式已設為: {input_format}')
                            window['-OUTPUT-'].print(f'警告: 無 ffmpeg，{input_format} 格式無法正確處理！')
                            window['-OUTPUT-'].print(f'建議: 改選 WAV 格式或安裝 ffmpeg')
                    else:
                        window['-OUTPUT-'].print(f'已載入檔案: {os.path.basename(file_path)}')
                        window['-OUTPUT-'].print(f'檔案格式: {input_format}, 時長: {minutes}分{seconds}秒')
                        window['-OUTPUT-'].print(f'注意: 不支援 {input_format} 直接輸出，請選擇其他格式')
                else:
                    window['-DURATION-'].update('無法讀取', text_color='red')
                    window['-OUTPUT-'].print('錯誤: 無法讀取音訊檔案')
            elif file_path:
                window['-DURATION-'].update('檔案不存在', text_color='red')
            else:
                window['-DURATION-'].update('未選擇檔案', text_color='gray')
                    
        elif event == '計算重複次數':
            file_path = values['-FILE-']
            target_time = values['-TARGET_TIME-']
            
            if not file_path:
                window['-OUTPUT-'].print('錯誤: 請選擇音訊檔案')
                continue
                
            if not target_time:
                window['-OUTPUT-'].print('錯誤: 請輸入目標時間')
                continue
                
            try:
                target_minutes = float(target_time)
                duration = repeater.get_audio_duration(file_path)
                
                if duration:
                    repeat_count = repeater.calculate_repeat_count(duration, target_minutes)
                    actual_duration = (duration * repeat_count) / 60
                    
                    window['-REPEAT_COUNT-'].update(str(repeat_count))
                    input_format = os.path.splitext(file_path)[1].lower().lstrip('.')
                    output_format = values['-OUTPUT_FORMAT-'].lower()
                    
                    # 判斷是否為無損複製
                    is_lossless = (input_format == output_format)
                    
                    window['-OUTPUT-'].print(f'計算結果:')
                    window['-OUTPUT-'].print(f'  原檔案格式: {input_format.upper()}')
                    window['-OUTPUT-'].print(f'  輸出格式: {output_format.upper()}')
                    window['-OUTPUT-'].print(f'  處理方式: {"無損複製 (最快)" if is_lossless else "格式轉換 (較慢)"}')
                    window['-OUTPUT-'].print(f'  原檔案時長: {duration:.2f}秒')
                    window['-OUTPUT-'].print(f'  目標時間: {target_minutes}分鐘')
                    window['-OUTPUT-'].print(f'  需要重複: {repeat_count}次')
                    window['-OUTPUT-'].print(f'  實際總時長: {actual_duration:.2f}分鐘')
                    if not is_lossless:
                        window['-OUTPUT-'].print(f'  提示: 選擇 {input_format.upper()} 格式可獲得最佳速度')
                    window['-OUTPUT-'].print('-' * 40)
                else:
                    window['-OUTPUT-'].print('錯誤: 無法讀取音訊檔案時長')
                    
            except ValueError:
                window['-OUTPUT-'].print('錯誤: 請輸入有效的數字')
                
        elif event == '生成檔案':
            file_path = values['-FILE-']
            target_time = values['-TARGET_TIME-']
            output_name = values['-OUTPUT_NAME-']
            output_dir = values['-OUTPUT_DIR-']
            output_format = values['-OUTPUT_FORMAT-']
            
            if not all([file_path, target_time, output_name, output_dir]):
                window['-OUTPUT-'].print('錯誤: 請填寫所有必要欄位')
                continue
                
            # 組合完整的輸出檔案路徑
            output_file = os.path.join(output_dir, f"{output_name}.{output_format}")
                
            try:
                target_minutes = float(target_time)
                duration = repeater.get_audio_duration(file_path)
                
                if duration:
                    repeat_count = repeater.calculate_repeat_count(duration, target_minutes)
                    
                    window['-OUTPUT-'].print(f'開始生成檔案...')
                    window['-OUTPUT-'].print(f'重複次數: {repeat_count}')
                    window.refresh()
                    
                    success, message, actual_output_path = repeater.create_repeated_audio(
                        file_path, repeat_count, output_file, output_format
                    )
                    
                    if success and actual_output_path:
                        window['-OUTPUT-'].print(message)
                        actual_size = os.path.getsize(actual_output_path) / (1024 * 1024)
                        window['-OUTPUT-'].print(f'檔案大小: {actual_size:.2f} MB')
                    else:
                        window['-OUTPUT-'].print(message)
                        
                else:
                    window['-OUTPUT-'].print('錯誤: 無法讀取音訊檔案')
                    
            except ValueError:
                window['-OUTPUT-'].print('錯誤: 請輸入有效的數字')
            except Exception as e:
                window['-OUTPUT-'].print(f'錯誤: {str(e)}')
    
    window.close()

if __name__ == '__main__':
    main()