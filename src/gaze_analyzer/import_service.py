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

class ImportWorker(QThread):
    progress = Signal(str)
    finished_import = Signal(str, str)
    error = Signal(str)

    def __init__(self, imports_dir):
        super().__init__()
        self.imports_dir = imports_dir

    def _run_adb(self, adb, *args):
        cmd = [adb] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"adb command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
        return result.stdout

    def _find_most_recent(self, adb, directory, prefix, extension):
        output = self._run_adb(adb, "shell", f"ls -t {directory}")
        for line in output.strip().splitlines():
            name = line.strip()
            if name.startswith(prefix) and name.endswith(extension):
                return name
        return None

    def run(self):
        try:
            adb = _find_adb()
            if not adb:
                self.error.emit("adb not found. Please install the Android SDK platform-tools.")
                return

            self.progress.emit(f"Using adb: {adb}")
            devices_output = self._run_adb(adb, "devices")
            connected = [l for l in devices_output.strip().splitlines()[1:] if "device" in l]
            if not connected:
                self.error.emit("No device connected. Ensure USB debugging is enabled.")
                return

            os.makedirs(self.imports_dir, exist_ok=True)

            self.progress.emit("Finding files...")
            video_name = self._find_most_recent(adb, DEVICE_VIDEO_DIR, VIDEO_PREFIX, ".mp4")
            if not video_name:
                self.error.emit(f"No MP4 files found in {DEVICE_VIDEO_DIR}")
                return

            csv_name = self._find_most_recent(adb, DEVICE_CSV_DIR, CSV_PREFIX, ".csv")
            if not csv_name:
                self.error.emit(f"No CSV files found in {DEVICE_CSV_DIR}")
                return

            mp4_local = os.path.join(self.imports_dir, video_name)
            csv_local = os.path.join(self.imports_dir, csv_name)

            self.progress.emit(f"Pulling {video_name}...")
            self._run_adb(adb, "pull", DEVICE_VIDEO_DIR + video_name, mp4_local)

            self.progress.emit(f"Pulling {csv_name}...")
            self._run_adb(adb, "pull", DEVICE_CSV_DIR + csv_name, csv_local)

            self.progress.emit("Import complete!")
            self.finished_import.emit(mp4_local, csv_local)

        except Exception as e:
            self.error.emit(str(e))
