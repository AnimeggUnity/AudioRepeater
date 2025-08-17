#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""音訊重複器 - 音訊檔案重複播放和媒體管理工具"""

import math
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import FreeSimpleGUI as sg
import psutil
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

# Constants - 程式常數設定
MONITORING_INTERVAL = 2  # 媒體監控間隔時間（秒）
MAX_DISPLAY_ITEMS = 5    # 最大顯示項目數量
DEFAULT_MP3_BITRATE = '192k'  # 預設MP3位元率
THREAD_JOIN_TIMEOUT = 1  # 執行緒結束等待時間（秒）
LABEL_WIDTH = 15         # 標籤寬度
BUTTON_WIDTH = 15        # 按鈕寬度
INPUT_WIDTH = 30         # 輸入框寬度
COMBO_WIDTH = 25         # 下拉選單寬度

# GUI Layout constants - 圖形界面佈局常數
WINDOW_TITLE = '音訊轉檔重複器'  # 視窗標題
SUPPORTED_FORMATS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.aac', '.wma']  # 支援的音訊格式
AUDIO_FILE_TYPES = (  # 檔案選擇對話框的檔案類型
    ('音訊檔案', '*.wav *.mp3 *.m4a *.flac *.ogg *.aac *.wma'),
)

# FFmpeg constants - FFmpeg相關常數
FFMPEG_EXE = 'ffmpeg.exe'        # FFmpeg執行檔名稱
FFMPEG_TIMEOUT = 60              # FFmpeg執行逾時時間（秒）
PCM_S16LE_CODEC = 'pcm_s16le'    # PCM音訊編碼器
LIBMP3LAME_CODEC = 'libmp3lame'  # MP3音訊編碼器

# Size conversion constants - 檔案大小轉換常數
BYTES_TO_MB = 1024 * 1024        # 位元組轉MB
BYTES_TO_GB = 1024 ** 3          # 位元組轉GB


class RemovableMediaManager:
    """可移動媒體管理器"""
    
    def __init__(self, callback=None):
        """
        初始化媒體管理器
        
        Args:
            callback: 媒體狀態改變時的回調函數
        """
        self.callback = callback
        self.known_drives: Set[str] = set()
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.batch_mode = False
        self.source_file: Optional[str] = None
        self.processing_drives: Set[str] = set()
        self.completed_drives: Set[str] = set()
        self.auto_process_queue: List[str] = []
        self.update_known_drives()

    def update_known_drives(self) -> None:
        """更新已知的磁碟機列表"""
        current_drives = set()
        for partition in psutil.disk_partitions():
            if self._is_removable_partition(partition):
                current_drives.add(partition.device)
        self.known_drives = current_drives

    def _is_removable_partition(self, partition) -> bool:
        """檢查分區是否為可移動媒體"""
        return ('removable' in partition.opts or 
                self.is_removable_drive(partition.device))

    def is_removable_drive(self, device: str) -> bool:
        """
        檢查是否為可移動磁碟機
        
        Args:
            device: 設備名稱
            
        Returns:
            是否為可移動媒體
        """
        try:
            for partition in psutil.disk_partitions():
                if partition.device == device:
                    return 'removable' in partition.opts
        except (psutil.Error, OSError):
            pass
        return False

    def get_removable_drives(self) -> List[Dict[str, Union[str, int]]]:
        """
        獲取所有可移動磁碟機
        
        Returns:
            可移動磁碟機資訊列表
        """
        drives = []
        for partition in psutil.disk_partitions():
            if self._is_removable_partition(partition):
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    drives.append({
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total': usage.total,
                        'free': usage.free,
                        'used': usage.used
                    })
                except (psutil.Error, OSError):
                    continue
        return drives

    def start_monitoring(self) -> None:
        """開始監視媒體變化"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop, 
                daemon=True
            )
            self.monitor_thread.start()

    def stop_monitoring(self) -> None:
        """停止監視媒體變化"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=THREAD_JOIN_TIMEOUT)

    def _monitor_loop(self) -> None:
        """監視媒體變化的主循環"""
        while self.monitoring:
            try:
                current_drives = self._get_current_removable_drives()
                new_drives, removed_drives = self._detect_drive_changes(
                    current_drives
                )
                
                if new_drives or removed_drives:
                    self.known_drives = current_drives
                    self._handle_drive_changes(new_drives)
                    self._notify_drive_changes(new_drives, removed_drives)

            except Exception:
                pass  # 忽略錯誤，繼續監視

            time.sleep(MONITORING_INTERVAL)

    def _get_current_removable_drives(self) -> Set[str]:
        """獲取當前可移動磁碟機集合"""
        current_drives = set()
        for partition in psutil.disk_partitions():
            if self._is_removable_partition(partition):
                current_drives.add(partition.device)
        return current_drives

    def _detect_drive_changes(self, current_drives: Set[str]) -> Tuple[Set[str], Set[str]]:
        """偵測磁碟機變化"""
        new_drives = current_drives - self.known_drives
        removed_drives = self.known_drives - current_drives
        return new_drives, removed_drives

    def _handle_drive_changes(self, new_drives: Set[str]) -> None:
        """處理新插入的磁碟機"""
        if not (self.batch_mode and new_drives and self.source_file):
            return
            
        for drive in new_drives:
            if self._should_process_drive(drive):
                self.auto_process_queue.append(drive)
                thread = threading.Thread(
                    target=self._auto_process_drive,
                    args=(drive,),
                    daemon=True
                )
                thread.start()

    def _should_process_drive(self, drive: str) -> bool:
        """檢查是否應該處理該磁碟機"""
        return (drive not in self.processing_drives and 
                drive not in self.completed_drives)

    def _notify_drive_changes(self, new_drives: Set[str], removed_drives: Set[str]) -> None:
        """通知磁碟機變化"""
        if self.callback:
            self.callback(new_drives, removed_drives)

    def clear_drive(self, drive_path: str, callback=None) -> Tuple[bool, str]:
        """
        清空磁碟機（刪除所有檔案和資料夾）
        
        Args:
            drive_path: 磁碟機路徑
            callback: 進度回調函數
            
        Returns:
            (成功狀態, 訊息)
        """
        if not self._validate_drive_path(drive_path):
            return False, "磁碟機不存在"

        try:
            items = self._scan_drive_items(drive_path, callback)
            if not items:
                if callback:
                    callback('info', f"磁碟機 {drive_path} 已經是空的")
                return True, "磁碟機已經是空的"

            return self._delete_items(drive_path, items, callback)

        except Exception as e:
            return False, f"清理失敗：{str(e)}"

    def _validate_drive_path(self, drive_path: str) -> bool:
        """驗證磁碟機路徑"""
        return os.path.exists(drive_path)

    def _scan_drive_items(self, drive_path: str, callback) -> List[str]:
        """掃描磁碟機項目"""
        try:
            items = os.listdir(drive_path)
        except Exception as e:
            raise Exception(f"無法讀取磁碟機內容：{str(e)}")

        if callback and items:
            self._report_scan_results(items, drive_path, callback)

        return items

    def _report_scan_results(self, items: List[str], drive_path: str, callback) -> None:
        """報告掃描結果"""
        files, folders = self._categorize_items(items, drive_path)
        total_items = len(files) + len(folders)
        
        callback('info', 
                f"掃描完成：找到 {len(files)} 個檔案，"
                f"{len(folders)} 個資料夾（共 {total_items} 項）")

        if files:
            file_display = self._format_item_list(files, "檔案")
            callback('info', file_display)
            
        if folders:
            folder_display = self._format_item_list(folders, "資料夾")
            callback('info', folder_display)

        callback('info', "開始清理...")

    def _categorize_items(self, items: List[str], drive_path: str) -> Tuple[List[str], List[str]]:
        """將項目分類為檔案和資料夾"""
        files = []
        folders = []
        
        for item in items:
            item_path = os.path.join(drive_path, item)
            if os.path.isfile(item_path):
                files.append(item)
            elif os.path.isdir(item_path):
                folders.append(item)
                
        return files, folders

    def _format_item_list(self, items: List[str], item_type: str) -> str:
        """格式化項目列表顯示"""
        if len(items) <= MAX_DISPLAY_ITEMS:
            return f"{item_type}：{', '.join(items)}"
        
        visible_items = ', '.join(items[:MAX_DISPLAY_ITEMS])
        remaining_count = len(items) - MAX_DISPLAY_ITEMS
        return f"{item_type}：{visible_items} ...（還有{remaining_count}個）"

    def _delete_items(self, drive_path: str, items: List[str], callback) -> Tuple[bool, str]:
        """刪除項目"""
        deleted_count = 0
        failed_items = []

        for item in items:
            success = self._delete_single_item(drive_path, item, callback)
            if success:
                deleted_count += 1
            else:
                failed_items.append(item)

        return self._finalize_deletion(
            drive_path, deleted_count, len(items), failed_items, callback
        )

    def _delete_single_item(self, drive_path: str, item: str, callback) -> bool:
        """刪除單個項目"""
        item_path = os.path.join(drive_path, item)
        try:
            if os.path.isfile(item_path):
                os.remove(item_path)
                if callback:
                    callback('progress', f"已刪除檔案：{item}")
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
                if callback:
                    callback('progress', f"已刪除資料夾：{item}")
            return True
        except Exception as e:
            if callback:
                callback('warning', f"無法刪除 {item}：{str(e)}")
            return False

    def _finalize_deletion(self, drive_path: str, deleted_count: int, 
                          total_items: int, failed_items: List[str], 
                          callback) -> Tuple[bool, str]:
        """完成刪除操作並返回結果"""
        remaining_items = self._check_remaining_items(drive_path, callback)
        
        success_msg = f"清理完成：成功刪除 {deleted_count}/{total_items} 個項目"
        if failed_items:
            success_msg += f"，失敗 {len(failed_items)} 個"

        if callback:
            callback('complete', success_msg)

        return True, success_msg

    def _check_remaining_items(self, drive_path: str, callback) -> List[str]:
        """檢查剩餘項目"""
        try:
            remaining_items = os.listdir(drive_path)
            if remaining_items and callback:
                remaining_display = ', '.join(remaining_items[:3])
                if len(remaining_items) > 3:
                    remaining_display += "..."
                callback('warning', 
                        f"仍有 {len(remaining_items)} 個項目未被刪除：{remaining_display}")
            return remaining_items
        except Exception:
            return []

    def copy_file_to_drive(self, source_file: str, drive_path: str, 
                          filename: Optional[str] = None) -> Tuple[bool, str]:
        """
        複製檔案到磁碟機
        
        Args:
            source_file: 源檔案路徑
            drive_path: 目標磁碟機路徑
            filename: 目標檔案名（可選）
            
        Returns:
            (成功狀態, 訊息)
        """
        try:
            if not os.path.exists(source_file):
                return False, "源檔案不存在"

            if not os.path.exists(drive_path):
                return False, "目標磁碟機不存在"

            if filename is None:
                filename = os.path.basename(source_file)

            target_path = os.path.join(drive_path, filename)
            shutil.copy2(source_file, target_path)

            return self._verify_copy(source_file, target_path)

        except Exception as e:
            return False, f"複製失敗：{str(e)}"

    def _verify_copy(self, source_file: str, target_path: str) -> Tuple[bool, str]:
        """驗證檔案複製"""
        if not os.path.exists(target_path):
            return False, "檔案複製失敗"

        source_size = os.path.getsize(source_file)
        target_size = os.path.getsize(target_path)
        
        if source_size == target_size:
            return True, f"檔案成功複製到 {target_path}"
        else:
            return False, "檔案複製不完整"

    def verify_file(self, source_file: str, target_file: str) -> Tuple[bool, str]:
        """
        驗證檔案複製是否成功
        
        Args:
            source_file: 源檔案路徑
            target_file: 目標檔案路徑
            
        Returns:
            (成功狀態, 訊息)
        """
        try:
            if not os.path.exists(target_file):
                return False, "目標檔案不存在"

            source_size = os.path.getsize(source_file)
            target_size = os.path.getsize(target_file)

            if source_size != target_size:
                return False, (f"檔案大小不符：原檔 {source_size} bytes，"
                             f"目標檔 {target_size} bytes")

            return True, "檔案驗證成功"

        except Exception as e:
            return False, f"驗證失敗：{str(e)}"

    def set_batch_mode(self, enabled: bool, source_file: Optional[str] = None) -> None:
        """
        設定批次處理模式
        
        Args:
            enabled: 是否啟用批次模式
            source_file: 源檔案路徑
        """
        self.batch_mode = enabled
        self.source_file = source_file
        if not enabled:
            self.processing_drives.clear()
            self.completed_drives.clear()
            self.auto_process_queue.clear()

    def _auto_process_drive(self, drive_device: str) -> None:
        """
        自動處理單個磁碟機的完整流程
        
        Args:
            drive_device: 磁碟機設備名
        """
        try:
            self.processing_drives.add(drive_device)
            drive_path = self._get_drive_path(drive_device)
            
            if not drive_path:
                self._notify_callback('error', 
                                    f"{drive_device} 無法取得磁碟機路徑")
                return

            self._process_drive_workflow(drive_device, drive_path)

        except Exception as e:
            self._notify_callback('error', 
                                f"{drive_device} 處理錯誤：{str(e)}")
        finally:
            self.processing_drives.discard(drive_device)

    def _get_drive_path(self, drive_device: str) -> Optional[str]:
        """獲取磁碟機路徑"""
        for partition in psutil.disk_partitions():
            if partition.device == drive_device:
                return partition.mountpoint
        return None

    def _process_drive_workflow(self, drive_device: str, drive_path: str) -> None:
        """執行磁碟機處理工作流程"""
        self._notify_callback('start', f"開始處理 {drive_device}")
        
        # 步驟1：清空媒體
        if not self._clear_media_step(drive_device, drive_path):
            return
            
        # 步驟2：複製檔案
        filename = self._copy_file_step(drive_device, drive_path)
        if not filename:
            return
            
        # 步驟3：驗證檔案
        if not self._verify_file_step(drive_device, drive_path, filename):
            return
            
        # 步驟4：完成通知
        self._complete_processing(drive_device)

    def _clear_media_step(self, drive_device: str, drive_path: str) -> bool:
        """執行清空媒體步驟"""
        self._notify_callback('progress', 
                            f"{drive_device} 正在掃描磁碟內容...")

        def clear_callback(msg_type, message):
            self._notify_callback('info', f"{drive_device} {message}")

        success, message = self.clear_drive(drive_path, callback=clear_callback)
        if not success:
            self._notify_callback('error', 
                                f"{drive_device} 清空失敗：{message}")
            return False

        self._notify_callback('progress', 
                            f"{drive_device} 清空完成，準備複製檔案")
        return True

    def _copy_file_step(self, drive_device: str, drive_path: str) -> Optional[str]:
        """執行複製檔案步驟"""
        filename = os.path.basename(self.source_file)
        source_size_mb = os.path.getsize(self.source_file) / BYTES_TO_MB
        
        self._notify_callback('progress', 
                            f"{drive_device} 正在複製檔案：{filename} "
                            f"({source_size_mb:.1f} MB)")

        success, message = self.copy_file_to_drive(self.source_file, 
                                                  drive_path, filename)
        if not success:
            self._notify_callback('error', 
                                f"{drive_device} 複製失敗：{message}")
            return None

        self._notify_callback('progress', 
                            f"{drive_device} 複製完成：{filename}")
        return filename

    def _verify_file_step(self, drive_device: str, drive_path: str, 
                         filename: str) -> bool:
        """執行檔案驗證步驟"""
        target_path = os.path.join(drive_path, filename)
        self._notify_callback('progress', 
                            f"{drive_device} 正在驗證檔案完整性...")

        success, message = self.verify_file(self.source_file, target_path)
        if not success:
            self._notify_callback('error', 
                                f"{drive_device} 驗證失敗：{message}")
            return False

        target_size_mb = os.path.getsize(target_path) / BYTES_TO_MB
        self._notify_callback('progress', 
                            f"{drive_device} 驗證成功：檔案大小 "
                            f"{target_size_mb:.1f} MB，完整性確認")
        return True

    def _complete_processing(self, drive_device: str) -> None:
        """完成處理流程"""
        self.completed_drives.add(drive_device)
        completion_message = (f"{drive_device} 處理完成，"
                            f"請手動執行安全移除（系統托盤→安全移除硬體→{drive_device}）")
        self._notify_callback('complete', completion_message)

    def _notify_callback(self, event_type: str, message: str) -> None:
        """通知回調函數處理狀態"""
        if self.callback:
            self.callback(set(), set(), event_type, message)

    def get_processing_status(self) -> Dict[str, Union[int, List[str]]]:
        """
        獲取處理狀態
        
        Returns:
            處理狀態字典
        """
        return {
            'processing': len(self.processing_drives),
            'completed': len(self.completed_drives),
            'processing_drives': list(self.processing_drives),
            'completed_drives': list(self.completed_drives)
        }


class AudioRepeater:
    """音訊重複器"""
    
    def __init__(self):
        """初始化音訊重複器"""
        self.supported_formats = SUPPORTED_FORMATS

    def get_audio_duration(self, file_path: str) -> Optional[float]:
        """
        獲取音訊檔案的時長（秒）
        
        Args:
            file_path: 音訊檔案路徑
            
        Returns:
            檔案時長（秒），失敗時返回 None
        """
        try:
            audio_file = File(file_path)
            if audio_file is not None and hasattr(audio_file, 'info'):
                return audio_file.info.length
            return None
        except Exception:
            return None

    def calculate_repeat_count(self, audio_duration: float, 
                             target_minutes: float) -> int:
        """
        計算需要重複的次數
        
        Args:
            audio_duration: 音訊檔案時長（秒）
            target_minutes: 目標時間（分鐘）
            
        Returns:
            需要重複的次數
        """
        target_seconds = target_minutes * 60
        return math.ceil(target_seconds / audio_duration)

    def create_repeated_audio(self, file_path: str, repeat_count: int,
                            output_path: str, output_format: str) -> Tuple[bool, str, Optional[str]]:
        """
        創建重複音訊檔案
        
        Args:
            file_path: 輸入檔案路徑
            repeat_count: 重複次數
            output_path: 輸出檔案路徑
            output_format: 輸出格式
            
        Returns:
            (成功狀態, 訊息, 實際輸出路徑)
        """
        try:
            ffmpeg_path = self._find_ffmpeg()
            
            if not ffmpeg_path:
                return self._handle_no_ffmpeg(file_path, repeat_count, 
                                            output_path, output_format)

            return self._create_with_ffmpeg(ffmpeg_path, file_path, 
                                          repeat_count, output_path, 
                                          output_format)

        except Exception as e:
            return False, f"錯誤：{str(e)}", None

    def _find_ffmpeg(self) -> Optional[str]:
        """尋找 FFmpeg 執行檔"""
        local_ffmpeg = os.path.join(os.getcwd(), FFMPEG_EXE)
        
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg
        elif os.path.exists(FFMPEG_EXE):
            return FFMPEG_EXE
        elif shutil.which('ffmpeg'):
            return 'ffmpeg'
        
        return None

    def _handle_no_ffmpeg(self, file_path: str, repeat_count: int,
                         output_path: str, output_format: str) -> Tuple[bool, str, Optional[str]]:
        """處理沒有 FFmpeg 的情況"""
        input_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        output_ext = output_format.lower()

        if input_ext == 'wav' and output_ext == 'wav':
            return self._create_repeated_wav_python(file_path, repeat_count, 
                                                  output_path)
        else:
            error_msg = ("錯誤：找不到 ffmpeg.exe。僅支援 WAV 格式，"
                        "其他格式需要 ffmpeg 正確處理檔頭")
            return False, error_msg, None

    def _create_with_ffmpeg(self, ffmpeg_path: str, file_path: str,
                           repeat_count: int, output_path: str,
                           output_format: str) -> Tuple[bool, str, Optional[str]]:
        """使用 FFmpeg 創建重複音訊"""
        import subprocess
        
        temp_dir = os.path.dirname(output_path)
        list_file = os.path.join(temp_dir, 'filelist.txt')

        try:
            self._create_filelist(list_file, file_path, repeat_count)
            cmd = self._build_ffmpeg_command(ffmpeg_path, list_file, 
                                           file_path, output_path, 
                                           output_format)
            
            result = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=FFMPEG_TIMEOUT, encoding='utf-8',
                                  errors='ignore')

            if result.returncode == 0:
                return True, f"成功創建檔案：{output_path}", output_path
            else:
                return False, f"ffmpeg 錯誤：{result.stderr}", None

        finally:
            self._cleanup_temp_file(list_file)

    def _create_filelist(self, list_file: str, file_path: str, 
                        repeat_count: int) -> None:
        """創建 FFmpeg 檔案列表"""
        with open(list_file, 'w', encoding='utf-8') as f:
            for _ in range(repeat_count):
                f.write(f"file '{os.path.abspath(file_path)}'\n")

    def _build_ffmpeg_command(self, ffmpeg_path: str, list_file: str,
                             file_path: str, output_path: str,
                             output_format: str) -> List[str]:
        """建立 FFmpeg 命令"""
        input_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        output_ext = output_format.lower()

        base_cmd = [ffmpeg_path, '-y', '-f', 'concat', '-safe', '0',
                   '-i', list_file]

        format_mapping = {
            'm4a': 'mp4',
            'mp4': 'mp4',
            'mp3': 'mp3',
            'wav': 'wav',
            'flac': 'flac',
            'ogg': 'ogg'
        }

        input_format = format_mapping.get(input_ext, input_ext)
        target_format = format_mapping.get(output_ext, output_ext)

        if (input_format == target_format or 
            (input_ext == 'm4a' and output_ext == 'm4a')):
            return base_cmd + ['-c', 'copy', output_path]
        elif output_format.lower() == 'mp3':
            return base_cmd + ['-c:a', LIBMP3LAME_CODEC, '-b:a', 
                              DEFAULT_MP3_BITRATE, output_path]
        elif output_format.lower() == 'wav':
            return base_cmd + ['-c:a', PCM_S16LE_CODEC, output_path]
        else:
            return base_cmd + ['-c', 'copy', output_path]

    def _cleanup_temp_file(self, list_file: str) -> None:
        """清理臨時檔案"""
        if os.path.exists(list_file):
            try:
                os.remove(list_file)
            except OSError:
                pass

    def _create_repeated_wav_python(self, file_path: str, repeat_count: int,
                                   output_path: str) -> Tuple[bool, str, Optional[str]]:
        """
        使用純 Python 重複 WAV 檔案（正確處理檔頭）
        
        Args:
            file_path: 輸入檔案路徑
            repeat_count: 重複次數
            output_path: 輸出檔案路徑
            
        Returns:
            (成功狀態, 訊息, 輸出路徑)
        """
        try:
            import wave

            with wave.open(file_path, 'rb') as input_wav:
                params = input_wav.getparams()
                frames = input_wav.readframes(params.nframes)

            with wave.open(output_path, 'wb') as output_wav:
                output_wav.setparams(params)
                for _ in range(repeat_count):
                    output_wav.writeframes(frames)

            success_msg = f"成功創建檔案：{output_path}（純 Python WAV 處理）"
            return True, success_msg, output_path

        except Exception as e:
            return False, f"WAV 處理錯誤：{str(e)}", None


class AudioRepeaterGUI:
    """音訊重複器 GUI 管理器"""
    
    def __init__(self):
        """初始化 GUI 管理器"""
        self.repeater = AudioRepeater()
        self.window = self._create_window()
        self.media_manager = None
        self.current_drives = []

    def _create_window(self) -> sg.Window:
        """創建主視窗"""
        sg.theme('LightBlue3')
        layout = self._create_layout()
        return sg.Window(WINDOW_TITLE, layout, finalize=True)

    def _create_layout(self) -> List[List[sg.Element]]:
        """創建 GUI 佈局"""
        layout = []
        
        # 標題和狀態
        layout.extend(self._create_header_section())
        
        # 音訊檔案選擇和設定
        layout.extend(self._create_audio_section())
        
        # 媒體管理區域
        layout.extend(self._create_media_section())
        
        # 輸出區域
        layout.extend(self._create_output_section())
        
        return layout

    def _create_header_section(self) -> List[List[sg.Element]]:
        """創建標題區域"""
        return [
            [sg.Text(WINDOW_TITLE, font=('Arial', 16, 'bold'), 
                    justification='center')],
            [sg.HSeparator()],
            [sg.Text('FFmpeg 狀態:', size=(LABEL_WIDTH, 1)),
             sg.Text('檢查中...', key='-FFMPEG_STATUS-', size=(40, 1))],
        ]

    def _create_audio_section(self) -> List[List[sg.Element]]:
        """創建音訊設定區域"""
        return [
            [sg.Text('選擇音訊檔案:', size=(LABEL_WIDTH, 1)),
             sg.Input(key='-FILE-', size=(40, 1), enable_events=True),
             sg.FileBrowse(file_types=AUDIO_FILE_TYPES)],
            
            [sg.Text('檔案時長:', size=(LABEL_WIDTH, 1)),
             sg.Text('未選擇檔案', key='-DURATION-', size=(INPUT_WIDTH, 1), 
                    text_color='gray')],
            
            [sg.Text('目標時間(分鐘):', size=(LABEL_WIDTH, 1)),
             sg.Input(key='-TARGET_TIME-', size=(10, 1)),
             sg.Text('分鐘')],
            
            [sg.Button('計算重複次數', size=(BUTTON_WIDTH, 1))],
            
            [sg.Text('需要重複次數:', size=(LABEL_WIDTH, 1)),
             sg.Text('--', key='-REPEAT_COUNT-', size=(10, 1))],
            
            [sg.Text('輸出格式:', size=(LABEL_WIDTH, 1)),
             sg.Combo(['mp3', 'wav', 'm4a', 'flac', 'ogg'], 
                     default_value='mp3', key='-OUTPUT_FORMAT-', 
                     size=(10, 1), enable_events=True)],
            
            [sg.Text('檔案名稱:', size=(LABEL_WIDTH, 1)),
             sg.Input(key='-OUTPUT_NAME-', size=(COMBO_WIDTH, 1)),
             sg.Text('', key='-FILE_EXT-', size=(5, 1))],
            
            [sg.Text('輸出位置:', size=(LABEL_WIDTH, 1)),
             sg.Input(key='-OUTPUT_DIR-', size=(INPUT_WIDTH, 1)),
             sg.FolderBrowse('選擇資料夾')],
            
            [sg.HSeparator()],
            
            [sg.Button('生成檔案', size=(BUTTON_WIDTH, 1)),
             sg.Button('聯絡資訊', size=(BUTTON_WIDTH, 1)),
             sg.Button('退出', size=(BUTTON_WIDTH, 1))],
            
            [sg.HSeparator()],
        ]

    def _create_media_section(self) -> List[List[sg.Element]]:
        """創建媒體管理區域"""
        return [
            [sg.Text('可移動媒體管理', font=('Arial', 12, 'bold'))],
            
            # 批次處理模式
            [sg.Checkbox('批次處理模式', key='-BATCH_MODE-', 
                        default=False, enable_events=True, 
                        font=('Arial', 10, 'bold')),
             sg.Text('（插入媒體時自動執行完整流程）', text_color='gray')],
            
            [sg.Text('處理檔案:', size=(LABEL_WIDTH, 1)),
             sg.Input(key='-BATCH_FILE-', size=(INPUT_WIDTH, 1), 
                     enable_events=True),
             sg.FileBrowse('選擇檔案', key='-BATCH_BROWSE-', 
                          file_types=AUDIO_FILE_TYPES)],
            
            [sg.Text('批次狀態:', size=(LABEL_WIDTH, 1)),
             sg.Text('未啟用', key='-BATCH_STATUS-', size=(40, 1), 
                    text_color='gray')],
            
            [sg.HSeparator()],
            
            # 手動媒體操作（可折疊）
            [sg.Button('▶ 手動媒體操作', key='-TOGGLE_MANUAL-', 
                      font=('Arial', 10, 'bold'),
                      button_color=('black', 'lightgray'), 
                      border_width=0, size=(20, 1))],
            
            [sg.pin(sg.Column(self._create_manual_section(), 
                             key='-MANUAL_SECTION-', visible=False))],
            
            [sg.HSeparator()],
        ]

    def _create_manual_section(self) -> List[List[sg.Element]]:
        """創建手動操作區域"""
        return [
            [sg.Text('複製檔案:', size=(LABEL_WIDTH, 1)),
             sg.Input(key='-MANUAL_FILE-', size=(INPUT_WIDTH, 1)),
             sg.FileBrowse('選擇檔案', key='-MANUAL_BROWSE-', 
                          file_types=AUDIO_FILE_TYPES)],
            
            [sg.Text('可用媒體:', size=(LABEL_WIDTH, 1)),
             sg.Combo([], default_value='', key='-MEDIA_LIST-', 
                     size=(COMBO_WIDTH, 1), enable_events=True),
             sg.Button('重新整理', size=(10, 1))],
            
            [sg.Text('媒體狀態:', size=(LABEL_WIDTH, 1)),
             sg.Text('沒有媒體', key='-MEDIA_STATUS-', size=(40, 1), 
                    text_color='gray')],
            
            [sg.Checkbox('自動複製到媒體', key='-AUTO_COPY-', default=False),
             sg.Checkbox('複製前清空媒體', key='-CLEAR_BEFORE_COPY-', 
                        default=False)],
            
            [sg.Button('清空選中媒體', size=(BUTTON_WIDTH, 1)),
             sg.Button('複製到媒體', size=(BUTTON_WIDTH, 1))]
        ]

    def _create_output_section(self) -> List[List[sg.Element]]:
        """創建輸出區域"""
        return [
            [sg.Multiline(size=(70, 8), key='-OUTPUT-', 
                         disabled=True, autoscroll=True)]
        ]

    def run(self) -> None:
        """運行主程式"""
        self._initialize_app()
        self._run_event_loop()
        self._cleanup()

    def _initialize_app(self) -> None:
        """初始化應用程式"""
        self._initialize_media_manager()
        self._check_ffmpeg_status()
        self._initialize_output_directory()
        self._update_media_list()

    def _initialize_media_manager(self) -> None:
        """初始化媒體管理器"""
        self.media_manager = RemovableMediaManager(
            callback=self._media_change_callback
        )
        self.media_manager.start_monitoring()

    def _media_change_callback(self, new_drives: Set[str], 
                              removed_drives: Set[str], 
                              event_type: Optional[str] = None, 
                              message: Optional[str] = None) -> None:
        """媒體變化回調函數"""
        try:
            if event_type:
                self.window.write_event_value('-BATCH_UPDATE-', 
                                            f'{event_type}:{message}')
            else:
                self._handle_drive_changes(new_drives, removed_drives)
        except Exception:
            pass

    def _handle_drive_changes(self, new_drives: Set[str], 
                             removed_drives: Set[str]) -> None:
        """處理磁碟機變化"""
        for drive in new_drives:
            self.window.write_event_value('-MEDIA_CHANGED-', f'插入: {drive}')
        for drive in removed_drives:
            self.window.write_event_value('-MEDIA_CHANGED-', f'移除: {drive}')

    def _check_ffmpeg_status(self) -> None:
        """檢查 FFmpeg 狀態"""
        if os.path.exists(FFMPEG_EXE):
            self.window['-FFMPEG_STATUS-'].update(
                '本地 ffmpeg.exe - 支援所有格式', text_color='green')
        elif shutil.which('ffmpeg'):
            self.window['-FFMPEG_STATUS-'].update(
                '系統 PATH 中的 ffmpeg - 支援所有格式', text_color='orange')
        else:
            self.window['-FFMPEG_STATUS-'].update(
                '未找到 ffmpeg - 僅支援 WAV 格式', text_color='red')

    def _initialize_output_directory(self) -> None:
        """初始化輸出目錄"""
        self.window['-OUTPUT_DIR-'].update(os.getcwd())

    def _update_media_list(self, preserve_selection: bool = False) -> List[Dict]:
        """更新媒體列表"""
        current_selection = (self.window['-MEDIA_LIST-'].get() 
                           if preserve_selection else None)

        drives = self.media_manager.get_removable_drives()
        drive_options = []
        
        for drive in drives:
            size_gb = drive['total'] / BYTES_TO_GB
            free_gb = drive['free'] / BYTES_TO_GB
            option = (f"{drive['device']} "
                     f"({free_gb:.1f}GB free / {size_gb:.1f}GB total)")
            drive_options.append(option)

        self.window['-MEDIA_LIST-'].update(values=drive_options)

        if preserve_selection and current_selection:
            self._restore_media_selection(current_selection, drive_options)

        self._update_media_status(drives)
        self.current_drives = drives
        return drives

    def _restore_media_selection(self, current_selection: str, 
                                drive_options: List[str]) -> None:
        """恢復媒體選擇"""
        current_device = current_selection.split(' ')[0]
        for option in drive_options:
            if option.startswith(current_device):
                self.window['-MEDIA_LIST-'].update(value=option)
                break

    def _update_media_status(self, drives: List[Dict]) -> None:
        """更新媒體狀態顯示"""
        if drives:
            status_text = f'找到 {len(drives)} 個可移動媒體'
            self.window['-MEDIA_STATUS-'].update(status_text, text_color='green')
        else:
            self.window['-MEDIA_STATUS-'].update('沒有可用的媒體', 
                                               text_color='gray')

    def _get_selected_media_path(self) -> Optional[str]:
        """獲取選中媒體的實際路徑"""
        selected = self.window['-MEDIA_LIST-'].get()
        if not selected:
            return None

        device = selected.split(' ')[0]
        for drive in self.current_drives:
            if drive['device'] == device:
                return drive['mountpoint']
        return None

    def _copy_to_media(self, file_path: str) -> bool:
        """複製檔案到媒體"""
        media_path = self._get_selected_media_path()
        if not media_path:
            self.window['-OUTPUT-'].print('錯誤: 請選擇一個媒體裝置')
            return False

        if not os.path.exists(file_path):
            self.window['-OUTPUT-'].print('錯誤: 檔案不存在')
            return False

        if self.window['-CLEAR_BEFORE_COPY-'].get():
            self.window['-OUTPUT-'].print(f'正在清空媒體 {media_path}...')
            success, message = self.media_manager.clear_drive(media_path)
            self.window['-OUTPUT-'].print(message)
            if not success:
                return False

        filename = os.path.basename(file_path)
        self.window['-OUTPUT-'].print(f'正在複製檔案到媒體 {media_path}...')
        success, message = self.media_manager.copy_file_to_drive(
            file_path, media_path, filename)
        self.window['-OUTPUT-'].print(message)

        return success

    def _run_event_loop(self) -> None:
        """運行事件循環"""
        while True:
            event, values = self.window.read()

            if event in (sg.WIN_CLOSED, '退出'):
                break

            try:
                self._handle_event(event, values)
            except Exception as e:
                self.window['-OUTPUT-'].print(f'錯誤: {str(e)}')

    def _handle_event(self, event: str, values: Dict) -> None:
        """處理事件"""
        event_handlers = {
            '-MEDIA_CHANGED-': self._handle_media_changed,
            '-BATCH_UPDATE-': self._handle_batch_update,
            '-BATCH_FILE-': self._handle_batch_file,
            '-BATCH_MODE-': self._handle_batch_mode,
            '-TOGGLE_MANUAL-': self._handle_toggle_manual,
            '重新整理': self._handle_refresh_media,
            '-MEDIA_LIST-': self._handle_media_selection,
            '清空選中媒體': self._handle_clear_media,
            '複製到媒體': self._handle_copy_to_media,
            '-OUTPUT_FORMAT-': self._handle_output_format,
            '-FILE-': self._handle_file_selection,
            '計算重複次數': self._handle_calculate_repeat,
            '生成檔案': self._handle_generate_file,
            '聯絡資訊': self._handle_contact_info,
        }

        handler = event_handlers.get(event)
        if handler:
            handler(values)

    def _handle_media_changed(self, values: Dict) -> None:
        """處理媒體變化事件"""
        message = values['-MEDIA_CHANGED-']
        self.window['-OUTPUT-'].print(f'媒體變化: {message}')
        self._update_media_list(preserve_selection=True)

    def _handle_batch_update(self, values: Dict) -> None:
        """處理批次更新事件"""
        update_info = values['-BATCH_UPDATE-']
        event_type, message = update_info.split(':', 1)

        emoji_map = {
            'start': '🔄',
            'progress': '⏳',
            'info': '📋',
            'warning': '⚠️',
            'complete': '✅',
            'error': '❌'
        }

        emoji = emoji_map.get(event_type, '')
        self.window['-OUTPUT-'].print(f'{emoji} {message}')

        self._update_batch_status()

    def _update_batch_status(self) -> None:
        """更新批次狀態"""
        status = self.media_manager.get_processing_status()
        
        if status['processing'] > 0:
            status_text = f'處理中: {status["processing"]} 個媒體'
            self.window['-BATCH_STATUS-'].update(status_text, text_color='orange')
        elif status['completed'] > 0:
            status_text = f'已完成: {status["completed"]} 個媒體'
            self.window['-BATCH_STATUS-'].update(status_text, text_color='green')
        else:
            if self.window['-BATCH_MODE-'].get():
                self.window['-BATCH_STATUS-'].update('等待媒體插入...', 
                                                   text_color='blue')
            else:
                self.window['-BATCH_STATUS-'].update('未啟用', text_color='gray')

    def _handle_batch_file(self, values: Dict) -> None:
        """處理批次檔案選擇"""
        batch_file = values['-BATCH_FILE-']
        if batch_file and os.path.exists(batch_file):
            filename = os.path.basename(batch_file)
            self.window['-OUTPUT-'].print(f'📁 已選擇批次處理檔案: {filename}')
            
            if values['-BATCH_MODE-']:
                self.media_manager.set_batch_mode(True, batch_file)
                self.window['-BATCH_STATUS-'].update('等待媒體插入...', 
                                                   text_color='blue')

    def _handle_batch_mode(self, values: Dict) -> None:
        """處理批次模式切換"""
        batch_mode = values['-BATCH_MODE-']

        if batch_mode:
            batch_file = values['-BATCH_FILE-']
            if batch_file and os.path.exists(batch_file):
                self.media_manager.set_batch_mode(True, batch_file)
                self.window['-BATCH_STATUS-'].update('等待媒體插入...', 
                                                   text_color='blue')
                self.window['-OUTPUT-'].print('🚀 批次處理模式已啟用')
                filename = os.path.basename(batch_file)
                self.window['-OUTPUT-'].print(f'📁 處理檔案: {filename}')
                self.window['-OUTPUT-'].print('💡 插入媒體將自動執行：清空→複製→驗證→完成通知')
            else:
                self.window['-BATCH_MODE-'].update(False)
                self.window['-OUTPUT-'].print('❌ 請先選擇要處理的檔案')
        else:
            self.media_manager.set_batch_mode(False)
            self.window['-BATCH_STATUS-'].update('未啟用', text_color='gray')
            self.window['-OUTPUT-'].print('⏹️ 批次處理模式已關閉')

    def _handle_toggle_manual(self, values: Dict) -> None:
        """處理手動區域切換"""
        current_visible = self.window['-MANUAL_SECTION-'].visible
        self.window['-MANUAL_SECTION-'].update(visible=not current_visible)

        if current_visible:
            self.window['-TOGGLE_MANUAL-'].update('▶ 手動媒體操作')
        else:
            self.window['-TOGGLE_MANUAL-'].update('▼ 手動媒體操作')
            self._update_media_list(preserve_selection=True)

    def _handle_refresh_media(self, values: Dict) -> None:
        """處理重新整理媒體"""
        self._update_media_list(preserve_selection=True)
        self.window['-OUTPUT-'].print('媒體列表已更新')

    def _handle_media_selection(self, values: Dict) -> None:
        """處理媒體選擇變化"""
        selected = values['-MEDIA_LIST-']
        if selected:
            device = selected.split(' ')[0]
            self.window['-MEDIA_STATUS-'].update(f'已選擇: {device}', 
                                               text_color='blue')
        else:
            self.window['-MEDIA_STATUS-'].update('沒有選擇媒體', 
                                               text_color='gray')

    def _handle_clear_media(self, values: Dict) -> None:
        """處理清空媒體"""
        media_path = self._get_selected_media_path()
        if media_path:
            self.window['-OUTPUT-'].print(f'正在清空媒體 {media_path}...')
            success, message = self.media_manager.clear_drive(media_path)
            self.window['-OUTPUT-'].print(message)
        else:
            self.window['-OUTPUT-'].print('錯誤: 請先選擇一個媒體裝置')

    def _handle_copy_to_media(self, values: Dict) -> None:
        """處理複製到媒體"""
        manual_file = values['-MANUAL_FILE-']

        if manual_file and os.path.exists(manual_file):
            self._copy_to_media(manual_file)
        else:
            self._copy_generated_file(values)

    def _copy_generated_file(self, values: Dict) -> None:
        """複製生成的檔案"""
        output_dir = values['-OUTPUT_DIR-']
        output_name = values['-OUTPUT_NAME-']
        output_format = values['-OUTPUT_FORMAT-']

        if output_name and output_format:
            output_file = os.path.join(output_dir, f"{output_name}.{output_format}")
            if os.path.exists(output_file):
                self._copy_to_media(output_file)
            else:
                self.window['-OUTPUT-'].print('錯誤: 請選擇要複製的檔案或先生成檔案')
        else:
            self.window['-OUTPUT-'].print('錯誤: 請選擇要複製的檔案')

    def _handle_output_format(self, values: Dict) -> None:
        """處理輸出格式變化"""
        selected_format = values['-OUTPUT_FORMAT-']
        self.window['-FILE_EXT-'].update(f'.{selected_format}')

    def _handle_file_selection(self, values: Dict) -> None:
        """處理檔案選擇"""
        file_path = values['-FILE-']
        
        if not file_path:
            self.window['-DURATION-'].update('未選擇檔案', text_color='gray')
            return

        if not os.path.exists(file_path):
            self.window['-DURATION-'].update('檔案不存在', text_color='red')
            return

        self._process_audio_file(file_path)

    def _process_audio_file(self, file_path: str) -> None:
        """處理音訊檔案"""
        self.window['-DURATION-'].update('讀取中...', text_color='orange')
        self.window.refresh()

        duration = self.repeater.get_audio_duration(file_path)
        if duration:
            self._display_audio_info(file_path, duration)
        else:
            self.window['-DURATION-'].update('無法讀取', text_color='red')
            self.window['-OUTPUT-'].print('錯誤: 無法讀取音訊檔案')

    def _display_audio_info(self, file_path: str, duration: float) -> None:
        """顯示音訊檔案資訊"""
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        duration_text = f'{minutes}分{seconds}秒 ({duration:.2f}秒)'
        self.window['-DURATION-'].update(duration_text, text_color='green')

        input_ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        input_format = input_ext.upper()

        has_ffmpeg = (os.path.exists(FFMPEG_EXE) or shutil.which('ffmpeg'))

        if input_ext in ['mp3', 'wav', 'm4a', 'flac', 'ogg']:
            self._set_output_format(input_ext, file_path, input_format, 
                                  minutes, seconds, has_ffmpeg)
        else:
            self._display_unsupported_format(file_path, input_format, 
                                           minutes, seconds)

    def _set_output_format(self, input_ext: str, file_path: str, 
                          input_format: str, minutes: int, seconds: int, 
                          has_ffmpeg: bool) -> None:
        """設定輸出格式"""
        # 固定使用mp3格式
        self.window['-OUTPUT_FORMAT-'].update('mp3')
        self.window['-FILE_EXT-'].update('.mp3')
        
        filename = os.path.basename(file_path)
        self.window['-OUTPUT-'].print(f'已載入檔案: {filename}')
        time_info = f'檔案格式: {input_format}, 時長: {minutes}分{seconds}秒'
        self.window['-OUTPUT-'].print(time_info)

        # 固定顯示mp3格式訊息
        if has_ffmpeg:
            self.window['-OUTPUT-'].print('輸出格式已設為: mp3 (使用 FFmpeg 轉換)')
        else:
            self.window['-OUTPUT-'].print('輸出格式已設為: mp3 (需要 FFmpeg 支援)')
            self.window['-OUTPUT-'].print(
                f'警告: 無 ffmpeg，{input_format} 格式無法正確處理！')
            self.window['-OUTPUT-'].print('建議: 改選 WAV 格式或安裝 ffmpeg')

    def _display_unsupported_format(self, file_path: str, input_format: str, 
                                   minutes: int, seconds: int) -> None:
        """顯示不支援的格式資訊"""
        filename = os.path.basename(file_path)
        self.window['-OUTPUT-'].print(f'已載入檔案: {filename}')
        time_info = f'檔案格式: {input_format}, 時長: {minutes}分{seconds}秒'
        self.window['-OUTPUT-'].print(time_info)
        self.window['-OUTPUT-'].print(
            f'注意: 不支援 {input_format} 直接輸出，請選擇其他格式')

    def _handle_calculate_repeat(self, values: Dict) -> None:
        """處理計算重複次數"""
        file_path = values['-FILE-']
        target_time = values['-TARGET_TIME-']

        if not file_path:
            self.window['-OUTPUT-'].print('錯誤: 請選擇音訊檔案')
            return

        if not target_time:
            self.window['-OUTPUT-'].print('錯誤: 請輸入目標時間')
            return

        try:
            target_minutes = float(target_time)
            duration = self.repeater.get_audio_duration(file_path)

            if duration:
                self._display_calculation_results(file_path, target_minutes, 
                                                duration, values)
            else:
                self.window['-OUTPUT-'].print('錯誤: 無法讀取音訊檔案時長')

        except ValueError:
            self.window['-OUTPUT-'].print('錯誤: 請輸入有效的數字')

    def _display_calculation_results(self, file_path: str, target_minutes: float,
                                   duration: float, values: Dict) -> None:
        """顯示計算結果"""
        repeat_count = self.repeater.calculate_repeat_count(duration, target_minutes)
        actual_duration = (duration * repeat_count) / 60

        self.window['-REPEAT_COUNT-'].update(str(repeat_count))
        
        input_format = os.path.splitext(file_path)[1].lower().lstrip('.')
        output_format = values['-OUTPUT_FORMAT-'].lower()
        is_lossless = (input_format == output_format)

        self.window['-OUTPUT-'].print('計算結果:')
        self.window['-OUTPUT-'].print(f'  原檔案格式: {input_format.upper()}')
        self.window['-OUTPUT-'].print(f'  輸出格式: {output_format.upper()}')
        
        processing_type = "無損複製 (最快)" if is_lossless else "格式轉換 (較慢)"
        self.window['-OUTPUT-'].print(f'  處理方式: {processing_type}')
        
        self.window['-OUTPUT-'].print(f'  原檔案時長: {duration:.2f}秒')
        self.window['-OUTPUT-'].print(f'  目標時間: {target_minutes}分鐘')
        self.window['-OUTPUT-'].print(f'  需要重複: {repeat_count}次')
        self.window['-OUTPUT-'].print(f'  實際總時長: {actual_duration:.2f}分鐘')
        
        if not is_lossless:
            self.window['-OUTPUT-'].print(
                f'  提示: 選擇 {input_format.upper()} 格式可獲得最佳速度')
        
        self.window['-OUTPUT-'].print('-' * 40)

    def _handle_generate_file(self, values: Dict) -> None:
        """處理生成檔案"""
        required_fields = ['-FILE-', '-TARGET_TIME-', '-OUTPUT_NAME-', '-OUTPUT_DIR-']
        if not all(values[field] for field in required_fields):
            self.window['-OUTPUT-'].print('錯誤: 請填寫所有必要欄位')
            return

        try:
            self._generate_audio_file(values)
        except ValueError:
            self.window['-OUTPUT-'].print('錯誤: 請輸入有效的數字')
        except Exception as e:
            self.window['-OUTPUT-'].print(f'錯誤: {str(e)}')

    def _generate_audio_file(self, values: Dict) -> None:
        """生成音訊檔案"""
        file_path = values['-FILE-']
        target_minutes = float(values['-TARGET_TIME-'])
        output_name = values['-OUTPUT_NAME-']
        output_dir = values['-OUTPUT_DIR-']
        output_format = values['-OUTPUT_FORMAT-']

        output_file = os.path.join(output_dir, f"{output_name}.{output_format}")

        duration = self.repeater.get_audio_duration(file_path)
        if not duration:
            self.window['-OUTPUT-'].print('錯誤: 無法讀取音訊檔案')
            return

        repeat_count = self.repeater.calculate_repeat_count(duration, target_minutes)

        self.window['-OUTPUT-'].print('開始生成檔案...')
        self.window['-OUTPUT-'].print(f'重複次數: {repeat_count}')
        self.window.refresh()

        success, message, actual_output_path = self.repeater.create_repeated_audio(
            file_path, repeat_count, output_file, output_format)

        if success and actual_output_path:
            self._handle_successful_generation(actual_output_path, values)
        else:
            self.window['-OUTPUT-'].print(message)

    def _handle_successful_generation(self, actual_output_path: str, 
                                    values: Dict) -> None:
        """處理成功生成檔案"""
        actual_size = os.path.getsize(actual_output_path) / BYTES_TO_MB
        self.window['-OUTPUT-'].print(f'檔案大小: {actual_size:.2f} MB')

        if values['-AUTO_COPY-']:
            self.window['-OUTPUT-'].print('正在自動複製到媒體...')
            self.window.refresh()
            copy_success = self._copy_to_media(actual_output_path)
            if copy_success:
                self.window['-OUTPUT-'].print('自動複製完成！')
            else:
                self.window['-OUTPUT-'].print('自動複製失敗，可手動複製')

    def _handle_contact_info(self, values: Dict) -> None:
        """處理聯絡資訊按鈕點擊"""
        import FreeSimpleGUI as sg
        
        contact_text = """如有程式修改或使用上的問題，
請聯絡：at7263@ntpc.gov.tw
感謝您的使用！"""
        
        sg.popup(contact_text, title='聯絡資訊', 
                button_color=('white', '#1f77b4'),
                font=('Microsoft JhengHei', 12))

    def _cleanup(self) -> None:
        """清理資源"""
        if self.media_manager:
            self.media_manager.stop_monitoring()
        self.window.close()


def main():
    """主程式入口點"""
    app = AudioRepeaterGUI()
    app.run()


if __name__ == '__main__':
    main()
