import pandas as pd
import numpy as np
import json
from scipy.spatial.transform import Slerp, Rotation

def _calc_behavioral_metrics(df):
    if len(df) == 0:
        return df
    
    # Blinks: L_Openness / R_Openness drop
    if 'L_Openness' in df.columns and 'R_Openness' in df.columns:
        df['IsBlinking'] = (df['L_Openness'] < 0.2) | (df['R_Openness'] < 0.2)
    
    # Pupillometry
    if 'L_PupilDia' in df.columns and 'R_PupilDia' in df.columns:
        df['MeanPupil'] = (df['L_PupilDia'] + df['R_PupilDia']) / 2.0
        baseline = df['MeanPupil'].head(100).mean() if len(df) > 100 else df['MeanPupil'].mean()
        df['PupilDeviation'] = df['MeanPupil'] - baseline
        
    # I-VT Classifier for Saccades
    if 'Cyclopean_X' in df.columns and 'RelativeTime' in df.columns:
        vecs = df[['Cyclopean_X', 'Cyclopean_Y', 'Cyclopean_Z']].values
        v1 = vecs[:-1]
        v2 = vecs[1:]
        
        n1 = np.linalg.norm(v1, axis=1)
        n2 = np.linalg.norm(v2, axis=1)
        n1[n1 == 0] = 1
        n2[n2 == 0] = 1
        
        dot_prods = np.sum(v1 * v2, axis=1) / (n1 * n2)
        dot_prods = np.clip(dot_prods, -1.0, 1.0)
        angles = np.arccos(dot_prods) * (180.0 / np.pi)
        
        dt = np.diff(df['RelativeTime'].values)
        dt[dt == 0] = 0.001 
        
        ang_vel = angles / dt
        ang_vel = np.insert(ang_vel, 0, 0)
        df['IsSaccade'] = ang_vel > 30.0
        df['AngularVelocity'] = ang_vel

    return df

def load_session_data(csv_path):
    print(f"Loading CSV data from {csv_path}...")
    try:
        metadata = {"camera": {}, "rois": {}}
        # Parse headers
        current_section = None
        with open(csv_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.startswith('#'):
                    break
                
                clean_line = line[1:].strip()
                if clean_line == '[Camera]':
                    current_section = 'camera'
                    continue
                elif clean_line == '[ROIs]':
                    current_section = 'rois'
                    continue
                    
                if current_section == 'camera':
                    if ':' in clean_line:
                        parts = clean_line.split(':', 1)
                        metadata['camera'][parts[0].strip()] = float(parts[1].strip())
                elif current_section == 'rois':
                    if clean_line.startswith('ID,'):
                        continue # header
                    parts = clean_line.split(',')
                    if len(parts) >= 11:
                        roi_id = parts[0].strip()
                        metadata['rois'][roi_id] = {
                            'pos': [float(parts[1]), float(parts[2]), float(parts[3])],
                            'rot': [float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])],
                            'scale': [float(parts[8]), float(parts[9]), float(parts[10])]
                        }
                
        df = pd.read_csv(csv_path, comment='#')
        if 'Timestamp' in df.columns:
            # Unity passes timestamp in ms via (Time.time) * 1000f
            df['RelativeTime'] = (df['Timestamp'] - df['Timestamp'].iloc[0]) / 1000.0
        else:
            df['RelativeTime'] = 0.0
            
        # Cyclopean Vector Calculation
        if all(c in df.columns for c in ['L_WorldDirX', 'L_WorldDirY', 'L_WorldDirZ', 'R_WorldDirX', 'R_WorldDirY', 'R_WorldDirZ']):
            valid_l = df['L_IsValid'] == 1 if 'L_IsValid' in df.columns else pd.Series(True, index=df.index)
            valid_r = df['R_IsValid'] == 1 if 'R_IsValid' in df.columns else pd.Series(True, index=df.index)
            
            lx = df['L_WorldDirX'].where(valid_l, 0)
            ly = df['L_WorldDirY'].where(valid_l, 0)
            lz = df['L_WorldDirZ'].where(valid_l, 0)
            
            rx = df['R_WorldDirX'].where(valid_r, 0)
            ry = df['R_WorldDirY'].where(valid_r, 0)
            rz = df['R_WorldDirZ'].where(valid_r, 0)
            
            cx = (lx + rx) / 2.0
            cy = (ly + ry) / 2.0
            cz = (lz + rz) / 2.0
            
            mask = valid_l | valid_r
            df['Cyclopean_X'] = cx.where(mask, np.nan)
            df['Cyclopean_Y'] = cy.where(mask, np.nan)
            df['Cyclopean_Z'] = cz.where(mask, np.nan)
            
        df = _calc_behavioral_metrics(df)
            
        return df, metadata
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return pd.DataFrame(), {}
        
def get_interpolated_frame(df, target_time):
    if df.empty or 'RelativeTime' not in df.columns:
        return None
        
    if target_time <= df['RelativeTime'].iloc[0]:
        return df.iloc[0].to_dict()
    if target_time >= df['RelativeTime'].iloc[-1]:
        return df.iloc[-1].to_dict()
        
    idx_next = df['RelativeTime'].searchsorted(target_time)
    idx_prev = idx_next - 1
    
    row_prev = df.iloc[idx_prev]
    row_next = df.iloc[idx_next]
    
    t0 = row_prev['RelativeTime']
    t1 = row_next['RelativeTime']
    
    if t1 == t0:
        return row_prev.to_dict()
        
    alpha = (target_time - t0) / (t1 - t0)
    res = {}
    for col in df.columns:
        val_prev = row_prev[col]
        val_next = row_next[col]
        if isinstance(val_prev, (int, float, np.number)) and isinstance(val_next, (int, float, np.number)) and not pd.isna(val_prev) and not pd.isna(val_next):
            res[col] = val_prev + alpha * (val_next - val_prev)
        else:
            res[col] = val_prev
            
    def nlerp_quat(col_prefix):
        if all(f"{col_prefix}{c}" in res for c in ['X', 'Y', 'Z', 'W']):
            q0 = row_prev[[f"{col_prefix}X", f"{col_prefix}Y", f"{col_prefix}Z", f"{col_prefix}W"]].values.astype(float)
            q1 = row_next[[f"{col_prefix}X", f"{col_prefix}Y", f"{col_prefix}Z", f"{col_prefix}W"]].values.astype(float)
            dot = np.dot(q0, q1)
            if dot < 0.0:
                q1 = -q1
                dot = -dot
            q_interp = q0 + alpha * (q1 - q0)
            norm = np.linalg.norm(q_interp)
            if norm > 0:
                q_interp /= norm
            res[f"{col_prefix}X"] = q_interp[0]
            res[f"{col_prefix}Y"] = q_interp[1]
            res[f"{col_prefix}Z"] = q_interp[2]
            res[f"{col_prefix}W"] = q_interp[3]
            
    def norm_vec(col_prefix):
        if all(f"{col_prefix}{c}" in res for c in ['X', 'Y', 'Z']):
            v = np.array([res[f"{col_prefix}X"], res[f"{col_prefix}Y"], res[f"{col_prefix}Z"]])
            norm = np.linalg.norm(v)
            if norm > 0:
                v /= norm
            res[f"{col_prefix}X"] = v[0]
            res[f"{col_prefix}Y"] = v[1]
            res[f"{col_prefix}Z"] = v[2]

    # Interpolate quaternions correctly with NLERP
    nlerp_quat('CamRot')
    nlerp_quat('HmdRot')
    nlerp_quat('L_LocalRot')
    nlerp_quat('R_LocalRot')
    
    # Normalize directional vectors
    norm_vec('L_LocalDir')
    norm_vec('L_WorldDir')
    norm_vec('R_LocalDir')
    norm_vec('R_WorldDir')
    norm_vec('Cyclopean_')
            
    res['RelativeTime'] = target_time
    return res

def calculate_roi_metrics(df):
    if df.empty or 'FocusedROI' not in df.columns or 'RelativeTime' not in df.columns:
        return {}
        
    metrics = {}
    rois = df['FocusedROI'].dropna().unique()
    
    for roi in rois:
        if roi == "" or pd.isna(roi): continue
        roi_mask = df['FocusedROI'] == roi
        df_roi = df[roi_mask]
        
        if df_roi.empty:
            continue
            
        ttff = df_roi['RelativeTime'].iloc[0]
        
        t_diff = df['RelativeTime'].diff().fillna(0)
        total_dwell = t_diff[roi_mask].sum()
        
        changed = df['FocusedROI'] != df['FocusedROI'].shift()
        blocks = df[changed & roi_mask]
        revisits = max(0, len(blocks) - 1)
        
        metrics[roi] = {
            'TotalDwellTime': float(total_dwell),
            'TimeToFirstFixation': float(ttff),
            'Revisits': int(revisits)
        }
    return metrics

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

def project_point_to_2d(world_pos, cam_pos, cam_rot_quat, fov, width, height):
    """Project a single 3D world coordinate to 2D pixel coordinates."""
    local_pos = q_mult_v(q_inv(cam_rot_quat), world_pos - cam_pos)

    # local_pos uses Unity camera-space convention: +X right, +Y up, +Z forward
    if local_pos[2] <= 0:
        return None

    fov_rad = np.deg2rad(fov)
    half_h = local_pos[2] * np.tan(fov_rad / 2.0)
    half_w = half_h * (width / height)

    viewport_x = (local_pos[0] / (half_w * 2.0)) + 0.5
    viewport_y = (local_pos[1] / (half_h * 2.0)) + 0.5
    pixel_x = int(viewport_x * width)
    pixel_y = int((1.0 - viewport_y) * height)

    return (pixel_x, pixel_y)

def unity_to_cv_projection(gaze_origin, gaze_dir_world, cam_pos, cam_rot_quat, fov, width, height):
    """
    Project a world-space gaze ray onto the 2D image plane of the spectator camera.
    """
    target_pos = gaze_origin + gaze_dir_world * 10.0
    return project_point_to_2d(target_pos, cam_pos, cam_rot_quat, fov, width, height)
