#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import FreeSimpleGUI as sg
import os
import math
import threading
import time
import shutil
import psutil
from pathlib import Path
from mutagen import File
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis

class RemovableMediaManager:
    def __init__(self, callback=None):
        self.callback = callback  # 當媒體狀態改變時的回調函數
        self.known_drives = set()
        self.monitoring = False
        self.monitor_thread = None
        self.batch_mode = False  # 批次處理模式
        self.source_file = None  # 要複製的檔案
        self.processing_drives = set()  # 正在處理的磁碟機
        self.completed_drives = set()  # 已完成處理的磁碟機
        self.auto_process_queue = []  # 自動處理佇列
        self.update_known_drives()
        
    def update_known_drives(self):
        """更新已知的磁碟機列表"""
        current_drives = set()
        for partition in psutil.disk_partitions():
            if 'removable' in partition.opts or self.is_removable_drive(partition.device):
                current_drives.add(partition.device)
        self.known_drives = current_drives
        
    def is_removable_drive(self, device):
        """檢查是否為可移動磁碟機"""
        try:
            # 在Windows上，可移動磁碟機通常不包含系統分區
            # 檢查磁碟機類型
            for partition in psutil.disk_partitions():
                if partition.device == device:
                    return 'removable' in partition.opts
        except:
            pass
        return False
        
    def get_removable_drives(self):
        """獲取所有可移動磁碟機"""
        drives = []
        for partition in psutil.disk_partitions():
            if 'removable' in partition.opts or self.is_removable_drive(partition.device):
                try:
                    # 檢查磁碟機是否可訪問
                    usage = psutil.disk_usage(partition.mountpoint)
                    drives.append({
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total': usage.total,
                        'free': usage.free,
                        'used': usage.used
                    })
                except:
                    # 磁碟機無法訪問（可能沒有媒體）
                    continue
        return drives
        
    def start_monitoring(self):
        """開始監視媒體變化"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            
    def stop_monitoring(self):
        """停止監視媒體變化"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
            
    def _monitor_loop(self):
        """監視媒體變化的主循環"""
        while self.monitoring:
            try:
                current_drives = set()
                for partition in psutil.disk_partitions():
                    if 'removable' in partition.opts or self.is_removable_drive(partition.device):
                        current_drives.add(partition.device)
                
                # 檢查新插入的媒體
                new_drives = current_drives - self.known_drives
                removed_drives = self.known_drives - current_drives
                
                if new_drives or removed_drives:
                    self.known_drives = current_drives
                    
                    # 如果是批次模式且有新媒體插入，自動開始處理
                    if self.batch_mode and new_drives and self.source_file:
                        for drive in new_drives:
                            if drive not in self.processing_drives and drive not in self.completed_drives:
                                self.auto_process_queue.append(drive)
                                threading.Thread(target=self._auto_process_drive, args=(drive,), daemon=True).start()
                    
                    if self.callback:
                        self.callback(new_drives, removed_drives)
                        
            except Exception as e:
                pass  # 忽略錯誤，繼續監視
                
            time.sleep(2)  # 每2秒檢查一次
            
    def clear_drive(self, drive_path, callback=None):
        """清空磁碟機（刪除所有檔案和資料夾）"""
        try:
            if not os.path.exists(drive_path):
                return False, "磁碟機不存在"
                
            # 先掃描所有項目
            items = []
            try:
                items = os.listdir(drive_path)
            except Exception as e:
                return False, f"無法讀取磁碟機內容：{str(e)}"
                
            if not items:
                if callback:
                    callback('info', f"磁碟機 {drive_path} 已經是空的")
                return True, "磁碟機已經是空的"
                
            # 顯示發現的項目
            files = []
            folders = []
            for item in items:
                item_path = os.path.join(drive_path, item)
                if os.path.isfile(item_path):
                    files.append(item)
                elif os.path.isdir(item_path):
                    folders.append(item)
                    
            total_items = len(files) + len(folders)
            if callback:
                callback('info', f"掃描完成：找到 {len(files)} 個檔案，{len(folders)} 個資料夾（共 {total_items} 項）")
                
                if files:
                    callback('info', f"檔案：{', '.join(files[:5])}" + (f" ...（還有{len(files)-5}個）" if len(files) > 5 else ""))
                if folders:
                    callback('info', f"資料夾：{', '.join(folders[:5])}" + (f" ...（還有{len(folders)-5}個）" if len(folders) > 5 else ""))
                    
                callback('info', "開始清理...")
                
            # 執行刪除
            deleted_count = 0
            failed_items = []
            
            for item in items:
                item_path = os.path.join(drive_path, item)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        deleted_count += 1
                        if callback:
                            callback('progress', f"已刪除檔案：{item}")
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        deleted_count += 1
                        if callback:
                            callback('progress', f"已刪除資料夾：{item}")
                except Exception as e:
                    failed_items.append(f"{item} ({str(e)})")
                    if callback:
                        callback('warning', f"無法刪除 {item}：{str(e)}")
                    continue
                    
            # 最終確認
            remaining_items = []
            try:
                remaining_items = os.listdir(drive_path)
            except:
                pass
                
            if remaining_items:
                if callback:
                    callback('warning', f"仍有 {len(remaining_items)} 個項目未被刪除：{', '.join(remaining_items[:3])}" + ("..." if len(remaining_items) > 3 else ""))
                    
            success_msg = f"清理完成：成功刪除 {deleted_count}/{total_items} 個項目"
            if failed_items:
                success_msg += f"，失敗 {len(failed_items)} 個"
                
            if callback:
                callback('complete', success_msg)
                
            return True, success_msg
            
        except Exception as e:
            return False, f"清理失敗：{str(e)}"
            
    def copy_file_to_drive(self, source_file, drive_path, filename=None):
        """複製檔案到磁碟機"""
        try:
            if not os.path.exists(source_file):
                return False, "源檔案不存在"
                
            if not os.path.exists(drive_path):
                return False, "目標磁碟機不存在"
                
            if filename is None:
                filename = os.path.basename(source_file)
                
            target_path = os.path.join(drive_path, filename)
            
            # 複製檔案
            shutil.copy2(source_file, target_path)
            
            # 驗證檔案是否成功複製
            if os.path.exists(target_path):
                source_size = os.path.getsize(source_file)
                target_size = os.path.getsize(target_path)
                if source_size == target_size:
                    return True, f"檔案成功複製到 {target_path}"
                else:
                    return False, "檔案複製不完整"
            else:
                return False, "檔案複製失敗"
                
        except Exception as e:
            return False, f"複製失敗：{str(e)}"
            
            
            
    def verify_file(self, source_file, target_file):
        """驗證檔案複製是否成功"""
        try:
            if not os.path.exists(target_file):
                return False, "目標檔案不存在"
                
            source_size = os.path.getsize(source_file)
            target_size = os.path.getsize(target_file)
            
            if source_size != target_size:
                return False, f"檔案大小不符：原檔 {source_size} bytes，目標檔 {target_size} bytes"
                
            # 可以添加更詳細的驗證，如檔案雜湊值比較
            return True, "檔案驗證成功"
            
        except Exception as e:
            return False, f"驗證失敗：{str(e)}"
            
    def set_batch_mode(self, enabled, source_file=None):
        """設定批次處理模式"""
        self.batch_mode = enabled
        self.source_file = source_file
        if not enabled:
            self.processing_drives.clear()
            self.completed_drives.clear()
            self.auto_process_queue.clear()
            
    def _auto_process_drive(self, drive_device):
        """自動處理單個磁碟機的完整流程"""
        try:
            self.processing_drives.add(drive_device)
            
            # 獲取磁碟機路徑
            drive_path = None
            for partition in psutil.disk_partitions():
                if partition.device == drive_device:
                    drive_path = partition.mountpoint
                    break
                    
            if not drive_path:
                self._notify_callback('error', f"{drive_device} 無法取得磁碟機路徑")
                return
                
            self._notify_callback('start', f"開始處理 {drive_device}")
            
            # 步驟1：清空媒體
            self._notify_callback('progress', f"{drive_device} 正在掃描磁碟內容...")
            
            def clear_callback(msg_type, message):
                self._notify_callback('info', f"{drive_device} {message}")
                
            success, message = self.clear_drive(drive_path, callback=clear_callback)
            if not success:
                self._notify_callback('error', f"{drive_device} 清空失敗：{message}")
                return
                
            self._notify_callback('progress', f"{drive_device} 清空完成，準備複製檔案")
            
            # 步驟2：複製檔案
            filename = os.path.basename(self.source_file)
            source_size = os.path.getsize(self.source_file) / (1024 * 1024)  # MB
            self._notify_callback('progress', f"{drive_device} 正在複製檔案：{filename} ({source_size:.1f} MB)")
            
            success, message = self.copy_file_to_drive(self.source_file, drive_path, filename)
            if not success:
                self._notify_callback('error', f"{drive_device} 複製失敗：{message}")
                return
                
            self._notify_callback('progress', f"{drive_device} 複製完成：{filename}")
            
            # 步驟3：驗證檔案
            target_path = os.path.join(drive_path, filename)
            self._notify_callback('progress', f"{drive_device} 正在驗證檔案完整性...")
            
            success, message = self.verify_file(self.source_file, target_path)
            if not success:
                self._notify_callback('error', f"{drive_device} 驗證失敗：{message}")
                return
                
            # 顯示驗證詳情
            target_size = os.path.getsize(target_path) / (1024 * 1024)  # MB
            self._notify_callback('progress', f"{drive_device} 驗證成功：檔案大小 {target_size:.1f} MB，完整性確認")
            
            # 步驟4：完成通知
            self.completed_drives.add(drive_device)
            self._notify_callback('complete', f"{drive_device} 處理完成，請手動執行安全移除（系統托盤→安全移除硬體→{drive_device}）")
            
        except Exception as e:
            self._notify_callback('error', f"{drive_device} 處理錯誤：{str(e)}")
        finally:
            self.processing_drives.discard(drive_device)
            
    def _notify_callback(self, event_type, message):
        """通知回調函數處理狀態"""
        if self.callback:
            self.callback(set(), set(), event_type, message)
            
    def get_processing_status(self):
        """獲取處理狀態"""
        return {
            'processing': len(self.processing_drives),
            'completed': len(self.completed_drives),
            'processing_drives': list(self.processing_drives),
            'completed_drives': list(self.completed_drives)
        }

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
        
        # 媒體管理區域
        [sg.Text('可移動媒體管理', font=('Arial', 12, 'bold'))],
        
        # 批次處理模式
        [sg.Checkbox('批次處理模式', key='-BATCH_MODE-', default=False, enable_events=True, font=('Arial', 10, 'bold')),
         sg.Text('（插入媒體時自動執行完整流程）', text_color='gray')],
        
        [sg.Text('處理檔案:', size=(15, 1)), 
         sg.Input(key='-BATCH_FILE-', size=(30, 1), enable_events=True), 
         sg.FileBrowse('選擇檔案', key='-BATCH_BROWSE-', file_types=(('音訊檔案', '*.wav *.mp3 *.m4a *.flac *.ogg *.aac *.wma'),))],
        
        [sg.Text('批次狀態:', size=(15, 1)), 
         sg.Text('未啟用', key='-BATCH_STATUS-', size=(40, 1), text_color='gray')],
        
        [sg.HSeparator()],
        
        # 手動媒體操作（可折疊）
        [sg.Button('▶ 手動媒體操作', key='-TOGGLE_MANUAL-', font=('Arial', 10, 'bold'), 
                  button_color=('black', 'lightgray'), border_width=0, size=(20, 1))],
        
        [sg.pin(sg.Column([
            [sg.Text('複製檔案:', size=(15, 1)), 
             sg.Input(key='-MANUAL_FILE-', size=(30, 1)), 
             sg.FileBrowse('選擇檔案', key='-MANUAL_BROWSE-', file_types=(('音訊檔案', '*.wav *.mp3 *.m4a *.flac *.ogg *.aac *.wma'),))],
            
            [sg.Text('可用媒體:', size=(15, 1)), 
             sg.Combo([], default_value='', key='-MEDIA_LIST-', size=(25, 1), enable_events=True),
             sg.Button('重新整理', size=(10, 1))],
            
            [sg.Text('媒體狀態:', size=(15, 1)), 
             sg.Text('沒有媒體', key='-MEDIA_STATUS-', size=(40, 1), text_color='gray')],
            
            [sg.Checkbox('自動複製到媒體', key='-AUTO_COPY-', default=False),
             sg.Checkbox('複製前清空媒體', key='-CLEAR_BEFORE_COPY-', default=False)],
            
            [sg.Button('清空選中媒體', size=(15, 1)), 
             sg.Button('複製到媒體', size=(15, 1))]
        ], key='-MANUAL_SECTION-', visible=False))],
        
        [sg.HSeparator()],
        
        [sg.Multiline(size=(70, 8), key='-OUTPUT-', disabled=True, autoscroll=True)]
    ]
    
    return sg.Window('音訊重複器', layout, finalize=True)

def main():
    import shutil
    
    repeater = AudioRepeater()
    window = create_gui()
    
    # 媒體變化回調函數
    def media_change_callback(new_drives, removed_drives, event_type=None, message=None):
        try:
            if event_type:
                # 批次處理狀態更新
                window.write_event_value('-BATCH_UPDATE-', f'{event_type}:{message}')
            else:
                # 一般媒體變化
                if new_drives:
                    for drive in new_drives:
                        window.write_event_value('-MEDIA_CHANGED-', f'插入: {drive}')
                if removed_drives:
                    for drive in removed_drives:
                        window.write_event_value('-MEDIA_CHANGED-', f'移除: {drive}')
        except:
            pass
    
    # 初始化媒體管理器
    media_manager = RemovableMediaManager(callback=media_change_callback)
    media_manager.start_monitoring()
    
    # 更新媒體列表的函數
    def update_media_list(preserve_selection=False):
        current_selection = window['-MEDIA_LIST-'].get() if preserve_selection else None
        
        drives = media_manager.get_removable_drives()
        drive_options = []
        for drive in drives:
            size_gb = drive['total'] / (1024**3)
            free_gb = drive['free'] / (1024**3)
            drive_options.append(f"{drive['device']} ({free_gb:.1f}GB free / {size_gb:.1f}GB total)")
        
        window['-MEDIA_LIST-'].update(values=drive_options)
        
        # 嘗試恢復之前的選擇
        if preserve_selection and current_selection:
            # 檢查之前選擇的媒體是否還存在
            current_device = current_selection.split(' ')[0]
            for option in drive_options:
                if option.startswith(current_device):
                    window['-MEDIA_LIST-'].update(value=option)
                    break
        
        if drives:
            window['-MEDIA_STATUS-'].update(f'找到 {len(drives)} 個可移動媒體', text_color='green')
        else:
            window['-MEDIA_STATUS-'].update('沒有可用的媒體', text_color='gray')
        
        return drives
    
    # 獲取選中媒體的實際路徑
    def get_selected_media_path():
        selected = window['-MEDIA_LIST-'].get()
        if selected:
            device = selected.split(' ')[0]  # 提取設備名稱（如 D:）
            drives = media_manager.get_removable_drives()
            for drive in drives:
                if drive['device'] == device:
                    return drive['mountpoint']
        return None
    
    # 複製檔案到媒體的函數
    def copy_to_media(file_path):
        media_path = get_selected_media_path()
        if not media_path:
            window['-OUTPUT-'].print('錯誤: 請選擇一個媒體裝置')
            return False
            
        if not os.path.exists(file_path):
            window['-OUTPUT-'].print('錯誤: 檔案不存在')
            return False
        
        # 檢查是否需要清空媒體
        if window['-CLEAR_BEFORE_COPY-'].get():
            window['-OUTPUT-'].print(f'正在清空媒體 {media_path}...')
            success, message = media_manager.clear_drive(media_path)
            window['-OUTPUT-'].print(message)
            if not success:
                return False
        
        # 複製檔案
        filename = os.path.basename(file_path)
        window['-OUTPUT-'].print(f'正在複製檔案到媒體 {media_path}...')
        success, message = media_manager.copy_file_to_drive(file_path, media_path, filename)
        window['-OUTPUT-'].print(message)
        
        return success
    
    # 檢查 ffmpeg（先檢查同目錄，再檢查 PATH）
    if os.path.exists('ffmpeg.exe'):
        window['-FFMPEG_STATUS-'].update('本地 ffmpeg.exe - 支援所有格式', text_color='green')
    elif shutil.which('ffmpeg'):
        window['-FFMPEG_STATUS-'].update('系統 PATH 中的 ffmpeg - 支援所有格式', text_color='orange')
    else:
        window['-FFMPEG_STATUS-'].update('未找到 ffmpeg - 僅支援 WAV 格式', text_color='red')
    
    # 初始化輸出目錄為當前目錄
    window['-OUTPUT_DIR-'].update(os.getcwd())
    
    # 初始化媒體列表
    current_drives = update_media_list()
    
    while True:
        event, values = window.read()
        
        if event == sg.WIN_CLOSED or event == '退出':
            media_manager.stop_monitoring()
            break
            
        elif event == '-MEDIA_CHANGED-':
            # 媒體變化事件
            message = values['-MEDIA_CHANGED-']
            window['-OUTPUT-'].print(f'媒體變化: {message}')
            current_drives = update_media_list(preserve_selection=True)
            
        elif event == '-BATCH_UPDATE-':
            # 批次處理狀態更新
            update_info = values['-BATCH_UPDATE-']
            event_type, message = update_info.split(':', 1)
            
            if event_type == 'start':
                window['-OUTPUT-'].print(f'🔄 {message}')
            elif event_type == 'progress':
                window['-OUTPUT-'].print(f'⏳ {message}')
            elif event_type == 'info':
                window['-OUTPUT-'].print(f'📋 {message}')
            elif event_type == 'warning':
                window['-OUTPUT-'].print(f'⚠️ {message}')
            elif event_type == 'complete':
                window['-OUTPUT-'].print(f'✅ {message}')
            elif event_type == 'error':
                window['-OUTPUT-'].print(f'❌ {message}')
                
            # 更新批次狀態
            status = media_manager.get_processing_status()
            if status['processing'] > 0:
                window['-BATCH_STATUS-'].update(f'處理中: {status["processing"]} 個媒體', text_color='orange')
            elif status['completed'] > 0:
                window['-BATCH_STATUS-'].update(f'已完成: {status["completed"]} 個媒體', text_color='green')
            else:
                if window['-BATCH_MODE-'].get():
                    window['-BATCH_STATUS-'].update('等待媒體插入...', text_color='blue')
                else:
                    window['-BATCH_STATUS-'].update('未啟用', text_color='gray')
                    
        elif event == '-BATCH_FILE-':
            # 批次檔案選擇變化
            batch_file = values['-BATCH_FILE-']
            if batch_file and os.path.exists(batch_file):
                window['-OUTPUT-'].print(f'📁 已選擇批次處理檔案: {os.path.basename(batch_file)}')
                # 如果批次模式已啟用，更新設定
                if values['-BATCH_MODE-']:
                    media_manager.set_batch_mode(True, batch_file)
                    window['-BATCH_STATUS-'].update('等待媒體插入...', text_color='blue')
                
        elif event == '-BATCH_MODE-':
            # 批次模式切換
            batch_mode = values['-BATCH_MODE-']
            
            if batch_mode:
                batch_file = values['-BATCH_FILE-']
                if batch_file and os.path.exists(batch_file):
                    media_manager.set_batch_mode(True, batch_file)
                    window['-BATCH_STATUS-'].update('等待媒體插入...', text_color='blue')
                    window['-OUTPUT-'].print('🚀 批次處理模式已啟用')
                    window['-OUTPUT-'].print(f'📁 處理檔案: {os.path.basename(batch_file)}')
                    window['-OUTPUT-'].print('💡 插入媒體將自動執行：清空→複製→驗證→完成通知')
                else:
                    window['-BATCH_MODE-'].update(False)
                    window['-OUTPUT-'].print('❌ 請先選擇要處理的檔案')
            else:
                media_manager.set_batch_mode(False)
                window['-BATCH_STATUS-'].update('未啟用', text_color='gray')
                window['-OUTPUT-'].print('⏹️ 批次處理模式已關閉')
            
        elif event == '-TOGGLE_MANUAL-':
            # 切換手動媒體操作區域的顯示/隱藏
            current_visible = window['-MANUAL_SECTION-'].visible
            window['-MANUAL_SECTION-'].update(visible=not current_visible)
            
            # 更新按鈕文字和樣式
            if current_visible:
                # 隱藏 -> 顯示收合箭頭
                window['-TOGGLE_MANUAL-'].update('▶ 手動媒體操作')
            else:
                # 顯示 -> 顯示展開箭頭，並初始化媒體列表
                window['-TOGGLE_MANUAL-'].update('▼ 手動媒體操作')
                # 展開時更新媒體列表
                current_drives = update_media_list(preserve_selection=True)
                
        elif event == '重新整理':
            # 手動重新整理媒體列表
            current_drives = update_media_list(preserve_selection=True)
            window['-OUTPUT-'].print('媒體列表已更新')
            
        elif event == '-MEDIA_LIST-':
            # 媒體選擇變化
            selected = values['-MEDIA_LIST-']
            if selected:
                device = selected.split(' ')[0]
                window['-MEDIA_STATUS-'].update(f'已選擇: {device}', text_color='blue')
            else:
                window['-MEDIA_STATUS-'].update('沒有選擇媒體', text_color='gray')
                
        elif event == '清空選中媒體':
            # 清空選中的媒體
            media_path = get_selected_media_path()
            if media_path:
                window['-OUTPUT-'].print(f'正在清空媒體 {media_path}...')
                success, message = media_manager.clear_drive(media_path)
                window['-OUTPUT-'].print(message)
            else:
                window['-OUTPUT-'].print('錯誤: 請先選擇一個媒體裝置')
                
        elif event == '複製到媒體':
            # 手動複製檔案到媒體
            manual_file = values['-MANUAL_FILE-']
            
            if manual_file and os.path.exists(manual_file):
                copy_to_media(manual_file)
            else:
                # 如果沒有選擇手動檔案，則使用生成的檔案
                output_dir = values['-OUTPUT_DIR-']
                output_name = values['-OUTPUT_NAME-']
                output_format = values['-OUTPUT_FORMAT-']
                
                if output_name and output_format:
                    output_file = os.path.join(output_dir, f"{output_name}.{output_format}")
                    if os.path.exists(output_file):
                        copy_to_media(output_file)
                    else:
                        window['-OUTPUT-'].print('錯誤: 請選擇要複製的檔案或先生成檔案')
                else:
                    window['-OUTPUT-'].print('錯誤: 請選擇要複製的檔案')
                    
            
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
                        
                        # 檢查是否需要自動複製到媒體
                        if values['-AUTO_COPY-']:
                            window['-OUTPUT-'].print('正在自動複製到媒體...')
                            window.refresh()
                            copy_success = copy_to_media(actual_output_path)
                            if copy_success:
                                window['-OUTPUT-'].print('自動複製完成！')
                            else:
                                window['-OUTPUT-'].print('自動複製失敗，可手動複製')
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
