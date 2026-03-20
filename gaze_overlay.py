import cv2
import pandas as pd
import numpy as np
import argparse
import sys
import os
import subprocess
import shutil
import datetime

# Device paths on VIVE Focus Vision (Android filesystem)
DEVICE_VIDEO_DIR = "/sdcard/Movies/Screenrecorder/"
DEVICE_CSV_DIR = "/sdcard/Android/data/com.artslab.eyetracking/files/"
VIDEO_PREFIX = "Screenrecord"
CSV_PREFIX = "EyeData"

ADB_SDK_PATH = os.path.join(
    os.path.expanduser("~"), "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"
)


def _find_adb(adb_path_override=None):
    """Locate the adb executable. Checks: explicit override, PATH, then Android SDK default."""
    if adb_path_override:
        if os.path.isfile(adb_path_override):
            return adb_path_override
        print(f"[Import] Specified adb path not found: {adb_path_override}")
        sys.exit(1)

    # Check PATH
    found = shutil.which("adb")
    if found:
        return found

    # Check default Android SDK location
    if os.path.isfile(ADB_SDK_PATH):
        return ADB_SDK_PATH

    print("[Import] adb not found. Install the Android SDK platform-tools or pass --adb-path.")
    print(f"[Import] Expected location: {ADB_SDK_PATH}")
    sys.exit(1)


def _run_adb(adb, *args):
    """Run an adb command and return stdout. Exits on failure."""
    cmd = [adb] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[Import] adb command failed: {' '.join(cmd)}")
        print(f"[Import] stderr: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout


def _find_most_recent(adb, directory, prefix, extension):
    """List files on device sorted by modification time and return the most recent match."""
    output = _run_adb(adb, "shell", f"ls -t {directory}")
    for line in output.strip().splitlines():
        name = line.strip()
        if name.startswith(prefix) and name.endswith(extension):
            return name
    return None


def _get_device_mtime(adb, path):
    """Return the modification time of a file on the device as a datetime (device local time)."""
    output = _run_adb(adb, "shell", f"stat -c \"%Y\" {path}")
    epoch = int(output.strip())
    return datetime.datetime.fromtimestamp(epoch)


def _print_file_info(label, name, mtime):
    """Print file timestamp and warn if older than 15 minutes."""
    age = datetime.datetime.now() - mtime
    age_mins = age.total_seconds() / 60
    timestamp_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[Import] {label}: {name}")
    print(f"[Import]   Modified: {timestamp_str} ({age_mins:.1f} min ago)")
    if age_mins > 15:
        print(f"[Import]   WARNING: This file is {age_mins:.0f} minutes old — is this the correct recording?")


def import_from_device(imports_dir, adb_path_override=None):
    """
    Pull the most recent screen recording (MP4) and eye-tracking CSV from a
    connected VIVE Focus Vision headset into the local Imports directory.

    Returns:
        tuple: (mp4_local_path, csv_local_path)
    """
    adb = _find_adb(adb_path_override)
    print(f"[Import] Using adb: {adb}")

    # Verify device is connected
    devices_output = _run_adb(adb, "devices")
    connected = [l for l in devices_output.strip().splitlines()[1:] if "device" in l]
    if not connected:
        print("[Import] No device connected. Ensure USB debugging is enabled and the headset is plugged in.")
        sys.exit(1)
    print(f"[Import] Device found: {connected[0].split()[0]}")

    os.makedirs(imports_dir, exist_ok=True)

    # --- Find most recent MP4 ---
    video_name = _find_most_recent(adb, DEVICE_VIDEO_DIR, VIDEO_PREFIX, ".mp4")
    if not video_name:
        print(f"[Import] No files matching '{VIDEO_PREFIX}*.mp4' found in {DEVICE_VIDEO_DIR}")
        sys.exit(1)
    video_mtime = _get_device_mtime(adb, DEVICE_VIDEO_DIR + video_name)
    _print_file_info("Video", video_name, video_mtime)

    # --- Find most recent CSV ---
    csv_name = _find_most_recent(adb, DEVICE_CSV_DIR, CSV_PREFIX, ".csv")
    if not csv_name:
        print(f"[Import] No files matching '{CSV_PREFIX}*.csv' found in {DEVICE_CSV_DIR}")
        sys.exit(1)
    csv_mtime = _get_device_mtime(adb, DEVICE_CSV_DIR + csv_name)
    _print_file_info("CSV  ", csv_name, csv_mtime)

    # --- Pull files ---
    mp4_local = os.path.join(imports_dir, video_name)
    csv_local = os.path.join(imports_dir, csv_name)

    print(f"[Import] Pulling {video_name}...")
    _run_adb(adb, "pull", DEVICE_VIDEO_DIR + video_name, mp4_local)

    print(f"[Import] Pulling {csv_name}...")
    _run_adb(adb, "pull", DEVICE_CSV_DIR + csv_name, csv_local)

    print(f"[Import] Files saved to {imports_dir}")
    return mp4_local, csv_local


def load_data(csv_path):
    print(f"Loading CSV data from {csv_path}...")
    try:
        df = pd.read_csv(csv_path)
        return df
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None

def q_mult_v(q, v):
    """
    Unity-equivalent Quaternion * Vector3 multiplication.
    q: [x, y, z, w]
    v: [x, y, z]
    """
    x, y, z, w = q[0], q[1], q[2], q[3]
    vx, vy, vz = v[0], v[1], v[2]
    num = x * 2.0
    num2 = y * 2.0
    num3 = z * 2.0
    num4 = x * num
    num5 = y * num2
    num6 = z * num3
    num7 = x * num2
    num8 = x * num3
    num9 = y * num3
    num10 = w * num
    num11 = w * num2
    num12 = w * num3

    rx = (1.0 - (num5 + num6)) * vx + (num7 - num12) * vy + (num8 + num11) * vz
    ry = (num7 + num12) * vx + (1.0 - (num4 + num6)) * vy + (num9 - num10) * vz
    rz = (num8 - num11) * vx + (num9 + num10) * vy + (1.0 - (num4 + num5)) * vz
    return np.array([rx, ry, rz])

def q_inv(q):
    """Unity-equivalent Quaternion.Inverse"""
    return np.array([-q[0], -q[1], -q[2], q[3]])

def unity_to_cv_projection(gaze_origin, gaze_dir_world, cam_pos, cam_rot_quat, fov, width, height):
    """
    Project a world-space gaze ray onto the 2D image plane of the spectator camera.

    Args:
        gaze_origin: np.array [x, y, z] — world-space origin of the gaze ray
        gaze_dir_world: np.array [x, y, z] — pre-computed world-space unit direction
        cam_pos: np.array [x, y, z] — spectator camera world position
        cam_rot_quat: np.array [x, y, z, w] — spectator camera world rotation
        fov: vertical field of view in degrees
        width, height: image dimensions in pixels

    Returns:
        tuple (x, y) in pixel coordinates, or None if behind camera
    """
    # Target point at arbitrary depth along gaze ray
    target_pos = gaze_origin + gaze_dir_world * 10.0

    # Transform target into camera-local space: P_local = R_cam_inv * (P_world - P_cam)
    local_pos = q_mult_v(q_inv(cam_rot_quat), target_pos - cam_pos)

    # local_pos uses Unity camera-space convention: +X right, +Y up, +Z forward
    if local_pos[2] <= 0:
        return None

    fov_rad = np.deg2rad(fov)
    half_h = local_pos[2] * np.tan(fov_rad / 2.0)
    half_w = half_h * (width / height)

    # Unity viewport: (0,0) = bottom-left; OpenCV: (0,0) = top-left
    viewport_x = (local_pos[0] / (half_w * 2.0)) + 0.5
    viewport_y = (local_pos[1] / (half_h * 2.0)) + 0.5
    pixel_x = int(viewport_x * width)
    pixel_y = int((1.0 - viewport_y) * height)

    return (pixel_x, pixel_y)

def process_video(video_path, csv_path, output_path, fov=60):
    df = load_data(csv_path)
    if df is None:
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error opening video: {video_path}")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"Video: {width}x{height} @ {fps}fps, {total_frames} frames")

    fourcc = cv2.VideoWriter.fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # Support both 0-based timestamps and old absolute timestamps
    if 'Timestamp' in df.columns:
        df['RelativeTime'] = df['Timestamp'] - df['Timestamp'].iloc[0]
        timestamps = df['RelativeTime'].to_numpy()
    else:
        timestamps = np.zeros(len(df))

    current_frame = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        video_time = current_frame / fps

        # Find CSV row closest to current video time
        idx = int(np.abs(timestamps - video_time).argmin())
        row = df.iloc[idx]

        time_delta = abs(row['RelativeTime'] - video_time)
        if time_delta <= 0.5:
            left_valid = int(row['L_IsValid']) == 1
            right_valid = int(row['R_IsValid']) == 1

            # Use left eye primary, right eye as fallback
            if left_valid or right_valid:
                eye_prefix = 'L_' if left_valid else 'R_'

                hmd_pos = np.array([row['HmdPosX'], row['HmdPosY'], row['HmdPosZ']])
                hmd_rot = np.array([row['HmdRotX'], row['HmdRotY'], row['HmdRotZ'], row['HmdRotW']])

                # Backward compatibility: Check if WorldPos is exported
                world_pos_key = f'{eye_prefix}WorldPosX'
                if world_pos_key in row:
                    gaze_origin = np.array([
                        row[f'{eye_prefix}WorldPosX'],
                        row[f'{eye_prefix}WorldPosY'],
                        row[f'{eye_prefix}WorldPosZ'],
                    ])
                else:
                    gaze_local_pos = np.array([
                        row[f'{eye_prefix}LocalPosX'],
                        row[f'{eye_prefix}LocalPosY'],
                        row[f'{eye_prefix}LocalPosZ'],
                    ])
                    # World-space gaze origin = HMD_pos + HMD_rot * local_gaze_pos
                    gaze_origin = hmd_pos + q_mult_v(hmd_rot, gaze_local_pos)

                gaze_dir_world = np.array([
                    row[f'{eye_prefix}WorldDirX'],
                    row[f'{eye_prefix}WorldDirY'],
                    row[f'{eye_prefix}WorldDirZ'],
                ])

                cam_pos = np.array([row['CamPosX'], row['CamPosY'], row['CamPosZ']])
                cam_rot = np.array([row['CamRotX'], row['CamRotY'], row['CamRotZ'], row['CamRotW']])

                screen_point = unity_to_cv_projection(
                    gaze_origin, gaze_dir_world, cam_pos, cam_rot, fov, width, height
                )

                if screen_point:
                    cv2.circle(frame, screen_point, 15, (0, 0, 255), 2)   # red ring
                    cv2.circle(frame, screen_point, 3,  (0, 255, 0), -1)  # green center

                    roi_text = str(row['FocusedROI'])
                    if roi_text and roi_text != 'nan':
                        cv2.putText(frame, roi_text,
                                    (screen_point[0] + 20, screen_point[1]),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        out.write(frame)
        current_frame += 1
        if current_frame % 60 == 0:
            sys.stdout.write(f"\rProcessing: {current_frame}/{total_frames} ({current_frame/total_frames*100:.1f}%)")
            sys.stdout.flush()

    cap.release()
    out.release()
    print("\nProcessing complete. Saved to", output_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Overlay Gaze Data on Video')
    parser.add_argument('video', nargs='?', help='Path to input video file')
    parser.add_argument('csv', nargs='?', help='Path to EyeData CSV file')
    parser.add_argument('--output', help='Path to output video file', default='output_gaze.mp4')
    parser.add_argument('--fov', type=float, help='Camera Field of View', default=60.0)
    parser.add_argument('--import-device', action='store_true',
                        help='Import the most recent MP4 and CSV from a connected VIVE Focus Vision')
    parser.add_argument('--adb-path', help='Path to adb executable (auto-detected if omitted)')

    args = parser.parse_args()

    if args.import_device:
        imports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Imports')
        video_path, csv_path = import_from_device(imports_dir, adb_path_override=args.adb_path)
        process_video(video_path, csv_path, args.output, args.fov)
    else:
        if not args.video or not args.csv:
            parser.error('video and csv arguments are required unless --import-device is used')
        process_video(args.video, args.csv, args.output, args.fov)
