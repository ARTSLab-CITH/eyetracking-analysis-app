import os
import shutil
import subprocess
import datetime
from PySide6.QtCore import QThread, Signal

DEVICE_VIDEO_DIR = "/sdcard/Movies/Screenrecorder/"
DEVICE_CSV_DIR = "/sdcard/Android/data/com.artslab.eyetracking/files/"
VIDEO_PREFIX = "Screenrecord"
CSV_PREFIX = "EyeData"

ADB_SDK_PATH = os.path.join(
    os.path.expanduser("~"), "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"
)

def _find_adb():
    found = shutil.which("adb")
    if found:
        return found
    if os.path.isfile(ADB_SDK_PATH):
        return ADB_SDK_PATH
    return None

def pull_latest_data(imports_dir, print_fn=print):
    adb = _find_adb()
    if not adb:
        raise Exception("adb not found. Please install the Android SDK platform-tools.")

    def _run_adb(*args):
        cmd = [adb] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"adb command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
        return result.stdout

    def _find_most_recent(directory, prefix, extension):
        output = _run_adb("shell", f"ls -t {directory}")
        for line in output.strip().splitlines():
            name = line.strip()
            if name.startswith(prefix) and name.endswith(extension):
                return name
        return None

    print_fn(f"Using adb: {adb}")
    devices_output = _run_adb("devices")
    connected = [l for l in devices_output.strip().splitlines()[1:] if "device" in l]
    if not connected:
        raise Exception("No device connected. Ensure USB debugging is enabled.")

    os.makedirs(imports_dir, exist_ok=True)

    print_fn("Finding files...")
    video_name = _find_most_recent(DEVICE_VIDEO_DIR, VIDEO_PREFIX, ".mp4")
    if not video_name:
        raise Exception(f"No MP4 files found in {DEVICE_VIDEO_DIR}")

    csv_name = _find_most_recent(DEVICE_CSV_DIR, CSV_PREFIX, ".csv")
    if not csv_name:
        raise Exception(f"No CSV files found in {DEVICE_CSV_DIR}")

    mp4_local = os.path.join(imports_dir, video_name)
    csv_local = os.path.join(imports_dir, csv_name)

    print_fn(f"Pulling {video_name}...")
    _run_adb("pull", DEVICE_VIDEO_DIR + video_name, mp4_local)

    print_fn(f"Pulling {csv_name}...")
    _run_adb("pull", DEVICE_CSV_DIR + csv_name, csv_local)

    print_fn("Import complete!")
    return mp4_local, csv_local

class ImportWorker(QThread):
    progress = Signal(str)
    finished_import = Signal(str, str)
    error = Signal(str)

    def __init__(self, imports_dir):
        super().__init__()
        self.imports_dir = imports_dir

    def run(self):
        try:
            mp4_local, csv_local = pull_latest_data(self.imports_dir, print_fn=self.progress.emit)
            self.finished_import.emit(mp4_local, csv_local)
        except Exception as e:
            self.error.emit(str(e))
