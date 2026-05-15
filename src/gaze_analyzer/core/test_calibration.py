import pandas as pd
import numpy as np
import math
import sys
from pathlib import Path

# Add src to path so we can import gaze_analyzer
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from gaze_analyzer.core.Quaternion import Quaternion




def classify_quadrant(px, py, width, height):
    if np.isnan(px) or np.isnan(py):
        return None
    cx, cy = width / 2, height / 2
    if px < cx and py < cy:
        return 'Top-Left'
    elif px >= cx and py < cy:
        return 'Top-Right'
    elif px < cx and py >= cy:
        return 'Bottom-Left'
    else:
        return 'Bottom-Right'

def test_calibration(csv_path):
    print(f"Testing calibration for {csv_path}")
    fov, aspect_ratio = parse_metadata(csv_path)
    
    # We will use 1920x960 for aspect ratio of 2.0
    width = 1920
    height = int(width / aspect_ratio) if aspect_ratio else 960
    
    projector = GazeProjector(fov, aspect_ratio, width, height)
    
    df = pd.read_csv(csv_path, comment='#')
    
    # 1. Compute 2D projected coordinates
    projections = []
    for _, row in df.iterrows():
        cam_rot = [row['CamRotX'], row['CamRotY'], row['CamRotZ'], row['CamRotW']]
        gaze_dir = [row['L_LocalDirX'], row['L_LocalDirY'], row['L_LocalDirZ']] 
        px, py = projector.project(cam_rot, gaze_dir)
        projections.append((px, py))
        
    projections = np.array(projections)
    df['px'] = projections[:, 0]
    df['py'] = projections[:, 1]
    
    # 2. Geometric analysis to detect settled eye gaze
    diff_px = np.diff(df['px'].fillna(0))
    diff_py = np.diff(df['py'].fillna(0))
    magnitude = np.sqrt(diff_px**2 + diff_py**2)
    
    df['gaze_diff'] = np.concatenate([[0], magnitude])
    
    # Settle threshold
    settle_threshold = 5.0 # pixels
    df['settled'] = df['gaze_diff'] < settle_threshold
    df.loc[df['px'].isna() | df['py'].isna(), 'settled'] = False
    
    # 3. Detect phases of head movement
    # CamRot magnitude diff
    cam_rot_cols = ['CamRotX', 'CamRotY', 'CamRotZ', 'CamRotW']
    cam_rot_diff = df[cam_rot_cols].diff().fillna(0)
    cam_rot_mag = np.linalg.norm(cam_rot_diff, axis=1)
    
    # Identify periods where head is moving vs stable
    # Threshold empirically lowered from 0.05 to 0.005 so head motions trigger it
    df['head_moving'] = cam_rot_mag > 0.005
    is_stable = ~df['head_moving']
    
    # A new phase starts when head transitions from moving to stable
    phase_starts = is_stable & ~is_stable.shift(1, fill_value=False)
    df['phase'] = phase_starts.cumsum()
    
    # Filter for only the stable frames of each phase to conduct quadrant tests
    stable_df = df[is_stable]
    
    print(f"Total phases detected: {stable_df['phase'].nunique()}")
    
    expected_sequence = ['Top-Left', 'Top-Right', 'Bottom-Right', 'Bottom-Left']
    
    passed_sequences = 0
    for phase, group in stable_df.groupby('phase', dropna=True):
        # Find frames where the eye gaze also settled during this stable-head phase
        settled_group = group[group['settled']].copy()
        
        # Determine quadrant for each settled point
        settled_group['quadrant'] = settled_group.apply(lambda r: classify_quadrant(r['px'], r['py'], width, height), axis=1)
        
        # Get sequence of unique quadrants visited during this phase
        visited = []
        for q in settled_group['quadrant'].dropna():
            if not visited or visited[-1] != q:
                visited.append(q)
                
        # Filter down to just the 4 target quadrants
        visited = [q for q in visited if q in expected_sequence]
        
        if len(visited) == 0:
            continue
            
        # 4. Verify sequence
        # Check if the sequence rigorously matches expected sequentially, allowing any cyclic shift
        def matches_strict_order(visited, expected):
            n = len(expected)
            for i in range(n):
                shifted_expected = expected[i:] + expected[:i]
                expected_idx = 0
                for v in visited:
                    if expected_idx < n and v == shifted_expected[expected_idx]:
                        expected_idx += 1
                if expected_idx == n:
                    return True
            return False
            
        if matches_strict_order(visited, expected_sequence):
            print(f"Phase {phase}: SUCCESS: Correct sequence found. {visited}")
            passed_sequences += 1
        else:
            print(f"Phase {phase}: WARNING: Did not find correct sequence. Found: {visited}")

    if passed_sequences >= 3:
        print(f"Overall Calibration Test: PASSED ({passed_sequences} expected sequences found)")
    else:
        print(f"Overall Calibration Test: FAILED (Found {passed_sequences} expected sequences, needed >= 3)")
if __name__ == "__main__":
    import sys
    csv_path = Path(__file__).parent.parent / "Imports" / "EyeData_20260410_111812.csv"
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
        
    test_calibration(csv_path)
