"""Temporary debug script to analyze CSV data and projection math."""
import pandas as pd
import numpy as np
from scipy.spatial.transform import Rotation as R

csv_path = r"Imports\EyeData_20260311_093246.csv"
df = pd.read_csv(csv_path)

print(f"Rows: {len(df)}")
print(f"IsValid counts:")
print(df["IsValid"].value_counts())
print(f"\nTimestamp range: {df['Timestamp'].min():.2f} - {df['Timestamp'].max():.2f} (duration: {df['Timestamp'].max()-df['Timestamp'].min():.2f}s)")

print(f"\nGaze Position ranges:")
for c in ["GazePosX", "GazePosY", "GazePosZ"]:
    print(f"  {c}: [{df[c].min():.6f}, {df[c].max():.6f}]")

print(f"\nCam Position ranges:")
for c in ["CamPosX", "CamPosY", "CamPosZ"]:
    print(f"  {c}: [{df[c].min():.6f}, {df[c].max():.6f}]")

# Simulate projection for several valid rows
valid = df[df["IsValid"] == 1]
print(f"\nValid rows: {len(valid)} / {len(df)}")

fov = 60.0
width, height = 1920, 1080  # typical guess

behind_count = 0
oob_count = 0
ok_count = 0

for i in range(min(50, len(valid))):
    row = valid.iloc[i]
    gaze_pos = np.array([row["GazePosX"], row["GazePosY"], row["GazePosZ"]])
    gaze_rot = np.array([row["GazeRotX"], row["GazeRotY"], row["GazeRotZ"], row["GazeRotW"]])
    cam_pos = np.array([row["CamPosX"], row["CamPosY"], row["CamPosZ"]])
    cam_rot = np.array([row["CamRotX"], row["CamRotY"], row["CamRotZ"], row["CamRotW"]])

    r_gaze = R.from_quat(gaze_rot)
    gaze_dir = r_gaze.apply([0, 0, 1])
    target_pos = gaze_pos + gaze_dir * 10.0

    r_cam = R.from_quat(cam_rot)
    rel_pos = target_pos - cam_pos
    local_pos = r_cam.inv().apply(rel_pos)

    if local_pos[2] <= 0:
        behind_count += 1
        if i < 5:
            print(f"\n  Row {i}: BEHIND CAMERA (local Z = {local_pos[2]:.4f})")
            print(f"    gaze_pos={gaze_pos}, gaze_dir={gaze_dir}")
            print(f"    cam_pos={cam_pos}, cam_fwd={r_cam.apply([0,0,1])}")
            print(f"    target={target_pos}")
            print(f"    local={local_pos}")
        continue

    fov_rad = np.deg2rad(fov)
    half_h = local_pos[2] * np.tan(fov_rad / 2)
    aspect = width / height
    half_w = half_h * aspect
    vx = (local_pos[0] / (half_w * 2)) + 0.5
    vy = (local_pos[1] / (half_h * 2)) + 0.5
    px = int(vx * width)
    py = int((1 - vy) * height)

    in_bounds = 0 <= px < width and 0 <= py < height
    if in_bounds:
        ok_count += 1
    else:
        oob_count += 1

    if i < 5:
        print(f"\n  Row {i}: pixel=({px}, {py}), in_bounds={in_bounds}")
        print(f"    gaze_pos={gaze_pos}")
        print(f"    gaze_dir={gaze_dir}")
        print(f"    cam_pos={cam_pos}")
        print(f"    cam_fwd={r_cam.apply([0,0,1])}")
        print(f"    target={target_pos}")
        print(f"    local_cam_space={local_pos}")
        print(f"    viewport=({vx:.4f}, {vy:.4f})")

print(f"\n--- Summary (first {min(50, len(valid))} valid rows) ---")
print(f"  Behind camera: {behind_count}")
print(f"  Out of bounds: {oob_count}")
print(f"  In bounds:     {ok_count}")

# Key question: are gaze positions in HEAD-LOCAL space or WORLD space?
# If gaze_pos barely moves but cam_pos moves a lot, gaze is likely head-local.
print(f"\n--- Coordinate space check ---")
gaze_stddev = valid[["GazePosX","GazePosY","GazePosZ"]].std()
cam_stddev = valid[["CamPosX","CamPosY","CamPosZ"]].std()
print(f"  Gaze position stddev: X={gaze_stddev['GazePosX']:.6f}, Y={gaze_stddev['GazePosY']:.6f}, Z={gaze_stddev['GazePosZ']:.6f}")
print(f"  Cam  position stddev: X={cam_stddev['CamPosX']:.6f}, Y={cam_stddev['CamPosY']:.6f}, Z={cam_stddev['CamPosZ']:.6f}")
print(f"\n  Gaze pos mean: X={valid['GazePosX'].mean():.6f}, Y={valid['GazePosY'].mean():.6f}, Z={valid['GazePosZ'].mean():.6f}")
print(f"  Cam  pos mean: X={valid['CamPosX'].mean():.6f}, Y={valid['CamPosY'].mean():.6f}, Z={valid['CamPosZ'].mean():.6f}")
print(f"\n  Distance gaze_origin to cam: {np.linalg.norm(gaze_pos - cam_pos):.4f} (last sampled row)")
