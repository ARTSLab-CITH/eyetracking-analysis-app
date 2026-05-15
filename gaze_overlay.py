import cv2
import pandas as pd
import numpy as np
import argparse
import sys
import math
import os
from pathlib import Path

# Add src to path so we can import gaze_analyzer
sys.path.insert(0, os.path.join(str(Path(__file__).resolve().parent), "src"))

class GazeProjector:
    def __init__(self, fov_v_deg, aspect_ratio, width, height):
        self.fov_v_deg = fov_v_deg
        self.aspect_ratio = aspect_ratio
        self.width = width
        self.height = height
        self.tan_half_fov_v = math.tan(math.radians(fov_v_deg / 2.0))
        self.tan_half_fov_h = self.tan_half_fov_v * aspect_ratio

    def project(self, l_pos, l_dir, r_pos, r_dir):
        # Unity is LHS: +Z Forward, +Y Up. 
        # Convert to numpy arrays
        o1 = np.array(l_pos, dtype=float)
        d1 = np.array(l_dir, dtype=float)
        o2 = np.array(r_pos, dtype=float)
        d2 = np.array(r_dir, dtype=float)
        
        # Calculate stereoscopic vergence (closest intersection of two rays)
        w0 = o1 - o2
        a = np.dot(d1, d1)
        b = np.dot(d1, d2)
        c = np.dot(d2, d2)
        d = np.dot(d1, w0)
        e = np.dot(d2, w0)
        denom = a * c - b * b
        
        if denom < 1e-6:
            # Rays are practically parallel; vergence is effectively at infinity.
            # Using left eye ray at depth 10.0m as fallback
            focus_point = o1 + d1 * 10.0
            distance = 10.0
            s_c, t_c = 10.0, 10.0
            fallback = True
        else:
            fallback = False
            s_c = (b * e - c * d) / denom
            t_c = (a * e - b * d) / denom
            
            # If the intersection is behind the local position (diverging)
            if s_c < 0 or t_c < 0:
                s_c = max(s_c, 0.1)
                t_c = max(t_c, 0.1)
                fallback = True
                
            p1 = o1 + s_c * d1
            p2 = o2 + t_c * d2
            focus_point = (p1 + p2) / 2.0
            distance = (s_c + t_c) / 2.0

        if focus_point[2] <= 0: # looking behind the camera
            return np.nan, np.nan, None

        # Project the 3D focus point onto the near plane
        x_hit = focus_point[0] / focus_point[2]
        y_hit = focus_point[1] / focus_point[2]
        
        # NDC (-1 to 1)
        ndc_x = x_hit / self.tan_half_fov_h
        ndc_y = y_hit / self.tan_half_fov_v
        
        # Pixel coordinates
        px = self.width / 2 * (1.0 + ndc_x)
        py = self.height / 2 * (1.0 - ndc_y) # Unity +Y is up, so +ndc_y is top of screen
        
        debug_info = {
            'l_pos': o1,
            'r_pos': o2,
            'l_dir': d1,
            'r_dir': d2,
            's_c': s_c,
            't_c': t_c,
            'fallback': fallback,
            'focus_point': focus_point,
            'distance': distance,
            'x_hit': x_hit,
            'y_hit': y_hit,
            'ndc_x': ndc_x,
            'ndc_y': ndc_y,
            'fov_v': self.fov_v_deg,
            'aspect_ratio': self.aspect_ratio,
            'tan_h': self.tan_half_fov_h,
            'tan_v': self.tan_half_fov_v
        }
        
        return px, py, debug_info

def parse_metadata(filepath):
    fov = 98.4044418
    aspect_ratio = 2.0
    with open(filepath, 'r') as f:
        for line in f:
            if not line.startswith('#'):
                break
            if 'FOV:' in line:
                try:
                    fov = float(line.split('FOV:')[1].strip())
                except ValueError:
                    pass
            elif 'AspectRatio:' in line:
                try:
                    aspect_ratio = float(line.split('AspectRatio:')[1].strip())
                except ValueError:
                    pass
    return fov, aspect_ratio

def main():
    parser = argparse.ArgumentParser(description="Overlay gaze onto video.")
    parser.add_argument("video", nargs="?", help="Path to input video (optional)")
    parser.add_argument("csv", nargs="?", help="Path to input CSV (optional)")
    parser.add_argument("--output", default="output_gaze.mp4", help="Path to output video")
    parser.add_argument("--fov", type=float, help="FOV override")
    args = parser.parse_args()

    video_path = args.video
    csv_path = args.csv

    if not video_path or not csv_path:
        print("Video or CSV not provided. Attempting to pull latest from connected device...")
        from gaze_analyzer.core.import_service import pull_latest_data
        imports_dir = os.path.join(Path(__file__).resolve().parent, "src", "gaze_analyzer", "Imports")
        try:
            video_path, csv_path = pull_latest_data(imports_dir)
        except Exception as e:
            print(f"Failed to pull from device: {e}")
            sys.exit(1)

    fov, aspect_ratio_csv = parse_metadata(csv_path)
    if args.fov is not None:
        fov = args.fov

    df = pd.read_csv(csv_path, comment='#')
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error opening video file {video_path}")
        sys.exit(1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or np.isnan(fps):
        fps = 30.0

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(args.output, fourcc, fps, (width, height))

    aspect_ratio_video = width / float(height) if height else aspect_ratio_csv
    projector = GazeProjector(fov, aspect_ratio_video, width, height)

    frame_index = 0
    sync_frame_idx = -1
    sync_threshold = 20.0 # Average brightness threshold to detect black screen removal

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if sync_frame_idx == -1:
            if np.mean(frame) > sync_threshold:
                sync_frame_idx = frame_index
                print(f"Sync frame found at index {sync_frame_idx} (approx {sync_frame_idx / fps:.2f}s)")

        if sync_frame_idx != -1 and frame_index >= sync_frame_idx:
            # Eye tracking time 0 starts exactly when the screen brightens
            video_time_ms = (frame_index - sync_frame_idx) * 1000.0 / fps

            # Find closest row based on timestamp
            closest_idx = (df['Timestamp'] - video_time_ms).abs().idxmin()
            
            # Avoid freezing the last gaze point forever if the video is much longer than the data
            if abs(df.loc[closest_idx, 'Timestamp'] - video_time_ms) < 500: # within 500ms
                row = df.loc[closest_idx]

                cam_rot = [row['CamRotX'], row['CamRotY'], row['CamRotZ'], row['CamRotW']]
                l_pos = [row['L_LocalPosX'], row['L_LocalPosY'], row['L_LocalPosZ']]
                l_dir = [row['L_LocalDirX'], row['L_LocalDirY'], row['L_LocalDirZ']] 
                r_pos = [row['R_LocalPosX'], row['R_LocalPosY'], row['R_LocalPosZ']]
                r_dir = [row['R_LocalDirX'], row['R_LocalDirY'], row['R_LocalDirZ']]

                px, py, debug_info = projector.project(l_pos, l_dir, r_pos, r_dir)

                # Unity Screen Position (average of L and R)
                # Unity's WorldToScreenPoint typically returns (0,0) at bottom-left and (width, height) at top-right.
                # Assuming Unity used 1920x960 (Aspect 2.0). We will normalize and rescale.
                unity_w = 1920.0
                unity_h = 960.0
                
                # Check if the ScreenPos columns exist
                has_screen_pos = 'L_ScreenPosX' in row and 'L_ScreenPosY' in row and 'R_ScreenPosX' in row and 'R_ScreenPosY' in row
                unity_px, unity_py = np.nan, np.nan
                if has_screen_pos:
                    avg_screen_x = (row['L_ScreenPosX'] + row['R_ScreenPosX']) / 2.0
                    avg_screen_y = (row['L_ScreenPosY'] + row['R_ScreenPosY']) / 2.0
                    
                    # Normalize (0 to 1)
                    norm_x = avg_screen_x / unity_w
                    norm_y = avg_screen_y / unity_h
                    
                    # Rescale to video resolution and invert Y (Unity bottom-left, OpenCV top-left)
                    unity_px = norm_x * width
                    unity_py = (1.0 - norm_y) * height

                if not np.isnan(px) and not np.isnan(py):
                    # filled red dot (BGR in OpenCV) for our calculated projection
                    cv2.circle(frame, (int(px), int(py)), 10, (0, 0, 255), -1)
                    
                if not np.isnan(unity_px) and not np.isnan(unity_py):
                    # filled green dot (BGR) for Unity's exported screen position
                    cv2.circle(frame, (int(unity_px), int(unity_py)), 8, (0, 255, 0), -1)

                if debug_info:
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    scale = 0.6
                    color = (0, 255, 0)
                    thickness = 2
                    
                    y_pos = 30
                    fallback_str = " (FALLBACK)" if debug_info['fallback'] else ""
                    texts = [
                        f"Time (ms): {video_time_ms:.1f}",
                        f"L_Pos: ({debug_info['l_pos'][0]:.4f}, {debug_info['l_pos'][1]:.4f}, {debug_info['l_pos'][2]:.4f}) | R_Pos: ({debug_info['r_pos'][0]:.4f}, {debug_info['r_pos'][1]:.4f}, {debug_info['r_pos'][2]:.4f})",
                        f"L_Dir: ({debug_info['l_dir'][0]:.4f}, {debug_info['l_dir'][1]:.4f}, {debug_info['l_dir'][2]:.4f}) | R_Dir: ({debug_info['r_dir'][0]:.4f}, {debug_info['r_dir'][1]:.4f}, {debug_info['r_dir'][2]:.4f})",
                        f"Rays intersecting at depth s: {debug_info['s_c']:.3f}m, t: {debug_info['t_c']:.3f}m{fallback_str}",
                        f"Focus Point: ({debug_info['focus_point'][0]:.4f}, {debug_info['focus_point'][1]:.4f}, {debug_info['focus_point'][2]:.4f})",
                        f"Distance: {debug_info['distance']: .3f}m",
                        f"Near Plane Hit (x_hit, y_hit): ({debug_info['x_hit']:.4f}, {debug_info['y_hit']:.4f})",
                        f"NDC (ndc_x, ndc_y): ({debug_info['ndc_x']:.4f}, {debug_info['ndc_y']:.4f})",
                        f"Pixels (px, py): ({px:.1f}, {py:.1f})",
                        f"Unity Pixels (px, py): ({unity_px:.1f}, {unity_py:.1f})" if not np.isnan(unity_px) else "Unity Pixels: N/A",
                        f"FOV_V: {debug_info['fov_v']:.2f}, AR: {debug_info['aspect_ratio']:.3f}",
                        f"Tan Half FOV (H: {debug_info['tan_h']:.3f}, V: {debug_info['tan_v']:.3f})"
                    ]
                    
                    for text in texts:
                        cv2.putText(frame, text, (10, y_pos), font, scale, color, thickness)
                        y_pos += 30

        out.write(frame)
        frame_index += 1

    cap.release()
    out.release()
    print("Done. Output saved to", args.output)

if __name__ == "__main__":
    main()
