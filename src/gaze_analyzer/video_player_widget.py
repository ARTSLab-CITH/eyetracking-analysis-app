import cv2
import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QCheckBox,
    QSizePolicy, QToolTip, QProgressDialog, QApplication
)
from gaze_analyzer.data_processor import unity_to_cv_projection, q_mult_v, get_interpolated_frame, project_point_to_2d

class VideoPlayerWidget(QWidget):
    frame_processed = Signal(np.ndarray, np.ndarray, np.ndarray) # frame, cam_pos, cam_rot

    def __init__(self):
        super().__init__()
        self.video_path = None
        self.csv_data = None
        self.cap = None
        self.total_frames = 0
        self.fps = 30
        self.current_frame = 0
        self.is_playing = False

        self.setup_ui()

        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Video Display
        self.video_label = QLabel("No Video Loaded")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setMouseTracking(True)
        self.video_label.mouseMoveEvent = self.on_video_mouse_move
        self.video_label.mousePressEvent = self.on_video_mouse_press
        layout.addWidget(self.video_label, stretch=1)

        # Controls
        controls_layout = QHBoxLayout()
        
        self.btn_play = QPushButton("Play")
        self.btn_play.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.btn_play)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.valueChanged.connect(self.seek_video)
        controls_layout.addWidget(self.slider)

        self.lbl_time = QLabel("00:00 / 00:00")
        controls_layout.addWidget(self.lbl_time)

        layout.addLayout(controls_layout)

        # Overlays
        overlay_layout = QHBoxLayout()
        self.chk_rings = QCheckBox("Gaze Rings")
        self.chk_rings.setChecked(True)
        self.chk_rings.toggled.connect(self.update_frame_display)
        
        self.chk_roi = QCheckBox("ROI Text")
        self.chk_roi.setChecked(True)
        self.chk_roi.toggled.connect(self.update_frame_display)

        self.chk_roi_wireframe = QCheckBox("ROI Wireframes")
        self.chk_roi_wireframe.setChecked(True)
        self.chk_roi_wireframe.toggled.connect(self.update_frame_display)

        self.chk_heatmap = QCheckBox("Heatmap (Spatial)")
        self.chk_heatmap.toggled.connect(self.update_frame_display)

        from PySide6.QtWidgets import QComboBox
        self.cmb_heatmap_length = QComboBox()
        self.cmb_heatmap_length.addItems(["All", "1s", "3s", "5s", "10s"])
        self.cmb_heatmap_length.currentTextChanged.connect(self.update_frame_display)

        overlay_layout.addWidget(self.chk_rings)
        overlay_layout.addWidget(self.chk_roi)
        overlay_layout.addWidget(self.chk_roi_wireframe)
        overlay_layout.addWidget(self.chk_heatmap)
        overlay_layout.addWidget(QLabel("Length:"))
        overlay_layout.addWidget(self.cmb_heatmap_length)
        overlay_layout.addStretch()

        layout.addLayout(overlay_layout)

    def load_session(self, video_path, csv_data, metadata=None):
        self.video_path = video_path
        self.csv_data = csv_data
        self.metadata = metadata or {}
        
        if self.cap:
            self.cap.release()
            
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            self.video_label.setText("Error loading video.")
            return

        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.slider.setRange(0, max(0, self.total_frames - 1))
        
        self.precomputed_frames = []
        if self.csv_data is not None and not self.csv_data.empty:
            sync_progress = QProgressDialog("Detecting visual sync (Curtain Drop)...", "Cancel", 0, self.total_frames, self)
            sync_progress.setWindowModality(Qt.WindowModal)
            sync_progress.setMinimumDuration(0)
            sync_progress.show()

            first_valid_frame = 0
            for i in range(self.total_frames):
                if sync_progress.wasCanceled():
                    break
                ret, frame = self.cap.read()
                if not ret:
                    break
                
                if frame.mean() > 15.0:
                    first_valid_frame = i
                    break
                
                if i % 30 == 0:
                    sync_progress.setValue(i)
                    QApplication.instance().processEvents()
                    
            sync_progress.setValue(self.total_frames)
            
            # Reset video to frame 0
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            progress = QProgressDialog("Pre-computing sync data...", "Cancel", 0, self.total_frames, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.show()
            
            for i in range(self.total_frames):
                if progress.wasCanceled():
                    break
                target_time = (i - first_valid_frame) / self.fps
                row_dict = get_interpolated_frame(self.csv_data, target_time)
                
                if target_time < 0:
                    row_dict['L_IsValid'] = 0
                    row_dict['R_IsValid'] = 0
                    row_dict['IsValid'] = 0
                    
                self.precomputed_frames.append(row_dict)
                
                if i % 30 == 0:
                    progress.setValue(i)
                    QApplication.instance().processEvents()
                    
            progress.setValue(self.total_frames)

        # Precalculate screen points for faster jumping
        vid_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vid_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fov = self.metadata.get('camera', {}).get('FOV', 60.0) if hasattr(self, 'metadata') else 60.0
        
        for row in self.precomputed_frames:
            left_valid = int(row.get('L_IsValid', 0)) == 1
            right_valid = int(row.get('R_IsValid', 0)) == 1
            row['screen_point'] = None
            if left_valid or right_valid:
                eye_prefix = 'L_' if left_valid else 'R_'
                try:
                    h_pos = np.array([row['HmdPosX'], row['HmdPosY'], row['HmdPosZ']])
                    h_rot = np.array([row['HmdRotX'], row['HmdRotY'], row['HmdRotZ'], row['HmdRotW']])
                    
                    if f'{eye_prefix}WorldPosX' in row:
                        g_org = np.array([row[f'{eye_prefix}WorldPosX'], row[f'{eye_prefix}WorldPosY'], row[f'{eye_prefix}WorldPosZ']])
                    else:
                        g_loc = np.array([row[f'{eye_prefix}LocalPosX'], row[f'{eye_prefix}LocalPosY'], row[f'{eye_prefix}LocalPosZ']])
                        g_org = h_pos + q_mult_v(h_rot, g_loc)
                        
                    g_dir = np.array([row[f'{eye_prefix}WorldDirX'], row[f'{eye_prefix}WorldDirY'], row[f'{eye_prefix}WorldDirZ']])
                    c_pos = np.array([row['CamPosX'], row['CamPosY'], row['CamPosZ']])
                    c_rot = np.array([row['CamRotX'], row['CamRotY'], row['CamRotZ'], row['CamRotW']])
                    
                    row['screen_point'] = unity_to_cv_projection(g_org, g_dir, c_pos, c_rot, fov, vid_w, vid_h)
                except Exception:
                    pass
        
        self.current_frame = 0
        self.seek_video(0)

        # Start paused
        self.is_playing = False
        self.btn_play.setText("Play")
        self.timer.stop()

    def toggle_play(self):
        if not self.cap or not self.cap.isOpened(): return
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.btn_play.setText("Pause")
            self.timer.start(int(1000 / self.fps))
        else:
            self.btn_play.setText("Play")
            self.timer.stop()

    def seek_video(self, frame_idx):
        if not self.cap: return
        self.current_frame = frame_idx
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        self.update_frame_display()

    def next_frame(self):
        if not self.cap: return
        if self.current_frame >= self.total_frames - 1:
            self.toggle_play()
            return
            
        self.current_frame += 1
        self.slider.blockSignals(True)
        self.slider.setValue(self.current_frame)
        self.slider.blockSignals(False)
        self.update_frame_display()

    def update_frame_display(self):
        if not self.cap: return
        
        # Keep track of current pos
        current_pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
        if current_pos != self.current_frame:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            
        ret, frame = self.cap.read()
        if not ret: return

        # Format time
        cur_sec = self.current_frame / self.fps
        tot_sec = self.total_frames / self.fps
        self.lbl_time.setText(f"{int(cur_sec//60):02d}:{int(cur_sec%60):02d} / {int(tot_sec//60):02d}:{int(tot_sec%60):02d}")

        # Process overlays
        out_frame = frame.copy()
        video_time = self.current_frame / self.fps
        
        row = None
        if hasattr(self, 'precomputed_frames') and 0 <= self.current_frame < len(self.precomputed_frames):
            row = self.precomputed_frames[self.current_frame]
            
        if row is not None:
            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
            # Find valid eye
            left_valid = int(row.get('L_IsValid', 0)) == 1
            right_valid = int(row.get('R_IsValid', 0)) == 1
            
            screen_point = None
            
            if left_valid or right_valid:
                eye_prefix = 'L_' if left_valid else 'R_'
                
                screen_point = getattr(row, 'screen_point', None)
                if screen_point is None and 'screen_point' in row:
                    screen_point = row['screen_point']
                
                try:
                    if screen_point is None:
                        hmd_pos = np.array([row['HmdPosX'], row['HmdPosY'], row['HmdPosZ']])
                        hmd_rot = np.array([row['HmdRotX'], row['HmdRotY'], row['HmdRotZ'], row['HmdRotW']])
                        
                        world_pos_key = f'{eye_prefix}WorldPosX'
                        if world_pos_key in row:
                            gaze_origin = np.array([row[f'{eye_prefix}WorldPosX'], row[f'{eye_prefix}WorldPosY'], row[f'{eye_prefix}WorldPosZ']])
                        else:
                            gaze_local_pos = np.array([row[f'{eye_prefix}LocalPosX'], row[f'{eye_prefix}LocalPosY'], row[f'{eye_prefix}LocalPosZ']])
                            gaze_origin = hmd_pos + q_mult_v(hmd_rot, gaze_local_pos)
                            
                        gaze_dir_world = np.array([row[f'{eye_prefix}WorldDirX'], row[f'{eye_prefix}WorldDirY'], row[f'{eye_prefix}WorldDirZ']])
                        cam_pos = np.array([row['CamPosX'], row['CamPosY'], row['CamPosZ']])
                        cam_rot = np.array([row['CamRotX'], row['CamRotY'], row['CamRotZ'], row['CamRotW']])
                        
                        fov = self.metadata.get('camera', {}).get('FOV', 60.0)
                        screen_point = unity_to_cv_projection(gaze_origin, gaze_dir_world, cam_pos, cam_rot, fov, w, h)
                except Exception as e:
                    pass # Ignore missing columns gracefully

                if screen_point:
                    if self.chk_rings.isChecked():
                        cv2.circle(out_frame, screen_point, 15, (0, 0, 255), 2)
                        cv2.circle(out_frame, screen_point, 3, (0, 255, 0), -1)
                        
                    if self.chk_roi.isChecked():
                        roi_text = str(row.get('FocusedROI', 'nan'))
                        if roi_text and roi_text != 'nan':
                            cv2.putText(out_frame, roi_text, (screen_point[0] + 20, screen_point[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                if self.chk_roi_wireframe.isChecked() and hasattr(self, 'metadata') and 'rois' in self.metadata:
                    try:
                        for roi_id, r_data in self.metadata['rois'].items():
                            c_pos = np.array([row['CamPosX'], row['CamPosY'], row['CamPosZ']])
                            c_rot = np.array([row['CamRotX'], row['CamRotY'], row['CamRotZ'], row['CamRotW']])
                            
                            r_pos = np.array(r_data['pos'])
                            r_rot = np.array(r_data['rot'])
                            r_scl = np.array(r_data['scale'])
                            
                            vertices = [
                                np.array([x, y, z]) * r_scl * 0.5
                                for x in [-1, 1] for y in [-1, 1] for z in [-1, 1]
                            ]
                            
                            proj_pts = []
                            fov = self.metadata.get('camera', {}).get('FOV', 60.0)
                            for v in vertices:
                                v_world = r_pos + q_mult_v(r_rot, v)
                                pt = project_point_to_2d(v_world, c_pos, c_rot, fov, w, h)
                                proj_pts.append(pt)
                            
                            if all(p is not None for p in proj_pts):
                                edges = [
                                    (0,1), (0,2), (0,4), (1,3), (1,5), (2,3),
                                    (2,6), (3,7), (4,5), (4,6), (5,7), (6,7)
                                ]
                                for e in edges:
                                    cv2.line(out_frame, proj_pts[e[0]], proj_pts[e[1]], (255, 255, 0), 1)
                                
                                # Tag wireframe
                                cv2.putText(out_frame, roi_id, (proj_pts[0][0], proj_pts[0][1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
                    except Exception as e:
                        pass

            if self.chk_heatmap.isChecked() and self.csv_data is not None:
                # Process heatmap over time window using Spatial points
                hm_mode = self.cmb_heatmap_length.currentText()
                if hm_mode == "All":
                    window_df = self.csv_data
                else:
                    secs = int(hm_mode.replace("s", ""))
                    window_df = self.csv_data[(self.csv_data['RelativeTime'] >= video_time - secs) & (self.csv_data['RelativeTime'] <= video_time + secs)]
                
                # Fetch current camera state for projecting historical 3D points
                if not window_df.empty:
                    try:
                        cam_pos = np.array([row['CamPosX'], row['CamPosY'], row['CamPosZ']])
                        cam_rot = np.array([row['CamRotX'], row['CamRotY'], row['CamRotZ'], row['CamRotW']])
                        
                        heatmap_overlay = np.zeros_like(out_frame, dtype=np.float32)
                        
                        for _, hrow in window_df.iterrows():
                            left_valid = int(hrow.get('L_IsValid', 0)) == 1
                            if left_valid:
                                if 'L_WorldPosX' in hrow:
                                    g_org = np.array([hrow['L_WorldPosX'], hrow['L_WorldPosY'], hrow['L_WorldPosZ']])
                                else:
                                    h_pos = np.array([hrow['HmdPosX'], hrow['HmdPosY'], hrow['HmdPosZ']])
                                    h_rot = np.array([hrow['HmdRotX'], hrow['HmdRotY'], hrow['HmdRotZ'], hrow['HmdRotW']])
                                    g_loc = np.array([hrow['L_LocalPosX'], hrow['L_LocalPosY'], hrow['L_LocalPosZ']])
                                    g_org = h_pos + q_mult_v(h_rot, g_loc)
                                
                                g_dir = np.array([hrow['L_WorldDirX'], hrow['L_WorldDirY'], hrow['L_WorldDirZ']])
                                fov = self.metadata.get('camera', {}).get('FOV', 60.0)
                                h_pt = unity_to_cv_projection(g_org, g_dir, cam_pos, cam_rot, fov, w, h)
                                
                                if h_pt and 0 <= h_pt[0] < w and 0 <= h_pt[1] < h:
                                    cv2.circle(heatmap_overlay, h_pt, 40, (0, 0, 10), -1)
                        
                        # Apply colormap
                        heatmap_norm = np.clip(heatmap_overlay, 0, 255).astype(np.uint8)
                        # We use cv2.applyColorMap to turn the intensity into a jet heatmap
                        # A better way is separating it, creating a scalar heat map, blurring, applying jet.
                        gray_heat = heatmap_norm[:,:,2]
                        if np.max(gray_heat) > 0:
                            gray_heat = cv2.GaussianBlur(gray_heat, (51, 51), 0)
                            gray_heat = cv2.normalize(gray_heat, None, 0, 255, cv2.NORM_MINMAX)
                            color_hm = cv2.applyColorMap(gray_heat, cv2.COLORMAP_JET)
                            
                            # Add to frame
                            mask = gray_heat > 10
                            out_frame[mask] = cv2.addWeighted(out_frame[mask], 0.4, color_hm[mask], 0.6, 0)
                    except Exception as e:
                        pass
        
        try:
            if row is not None and 'CamPosX' in row:
                cam_pos_sig = np.array([row['CamPosX'], row['CamPosY'], row['CamPosZ']])
                cam_rot_sig = np.array([row['CamRotX'], row['CamRotY'], row['CamRotZ'], row['CamRotW']])
                self.frame_processed.emit(out_frame, cam_pos_sig, cam_rot_sig)
        except:
            pass

        # Convert to QPixmap
        h, w, ch = out_frame.shape
        bytes_per_line = ch * w
        qimg = QImage(out_frame.data, w, h, bytes_per_line, QImage.Format_BGR888)
        pixmap = QPixmap.fromImage(qimg)
        
        # Scale to label size keeping aspect ratio
        pixmap = pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.FastTransformation)
        self.video_label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_frame_display()

    def on_video_mouse_move(self, event):
        # ROI Hover logic (Simplified: if we hovered an area, we'd check ROI dwell time)
        # For now, just show a temporary tooltip
        if self.csv_data is not None and not self.is_playing:
            # Note: Map screen coordinates to video coordinates to find underlying ROI
            # and calculate the dwell time stat
            QToolTip.showText(event.globalPos(), f"Hover Stats: Ready", self.video_label)

    def on_video_mouse_press(self, event):
        if not self.cap or not hasattr(self, 'precomputed_frames'):
            return
            
        if event.button() != Qt.LeftButton:
            return

        lbl_w = self.video_label.width()
        lbl_h = self.video_label.height()
        vid_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vid_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        if vid_w == 0 or vid_h == 0: return

        scale_w = lbl_w / vid_w
        scale_h = lbl_h / vid_h
        scale = min(scale_w, scale_h)
        
        disp_w = vid_w * scale
        disp_h = vid_h * scale
        
        offset_x = (lbl_w - disp_w) / 2
        offset_y = (lbl_h - disp_h) / 2
        
        click_x = event.pos().x()
        click_y = event.pos().y()
        
        import math
        min_dist = float('inf')
        best_frame = -1
        
        for i, row in enumerate(self.precomputed_frames):
            pt = row.get('screen_point')
            if pt:
                # Calculate where this projected video point sits on the UI
                proj_ui_x = pt[0] * scale + offset_x
                proj_ui_y = pt[1] * scale + offset_y
                
                dist = math.hypot(click_x - proj_ui_x, click_y - proj_ui_y)
                if dist < min_dist:
                    min_dist = dist
                    best_frame = i
                
        if best_frame != -1:
            self.seek_video(best_frame)
