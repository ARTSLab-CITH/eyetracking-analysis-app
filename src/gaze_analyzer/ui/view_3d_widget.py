import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout
import vispy.scene
from vispy.scene import visuals
from vispy.visuals.transforms import MatrixTransform

class View3DWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Setup VisPy canvas
        self.canvas = vispy.scene.SceneCanvas(keys='interactive', show=True)
        self.layout.addWidget(self.canvas.native)
        
        self.view = self.canvas.central_widget.add_view()
        self.view.camera = 'turntable'  # Arcball/turntable camera for 3D
        self.view.camera.fov = 60
        self.view.camera.distance = 5

        # Add coordinate axes
        visuals.XYZAxis(parent=self.view.scene)

        # Plot nodes
        self.cam_path_line = visuals.Line(color='white', width=2, method='gl', parent=self.view.scene)
        self.gaze_scatter = visuals.Markers(parent=self.view.scene)
        
        # Video plane
        self.video_img = visuals.Image(parent=self.view.scene)
        self.video_img.transform = MatrixTransform()

    def update_video_plane(self, frame, cam_pos, cam_rot):
        try:
            # We want to display the frame as an RGB image
            # frame is coming from OpenCV, so it's BGR
            import cv2
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.video_img.set_data(rgb_frame)
            
            # Reset transform
            transform = MatrixTransform()
            
            # Center the image around origin properly based on its shape
            h, w, _ = rgb_frame.shape
            
            # The image needs to be scaled down so it's not huge in 3d space (e.g. w=1920 to w=2 meters)
            scale_factor = 2.0 / w
            transform.scale((scale_factor, scale_factor, scale_factor))
            
            # Translate image center to the center
            transform.translate((-1.0, -h/w, 0))
            
            # Apply Unity rotation using quaternion math? Or just simple position translation.
            # In VisPy, transform matrix can be set directly or incrementally
            # To apply cam_rot, a simpler way is just projecting to cam_pos, we can skip full rot for now and just face it forward.
            
            # Move to camera position
            # Add an offset to push it slightly forward of the camera path so it doesn't clip
            transform.translate((cam_pos[0], cam_pos[1], cam_pos[2]))
            
            self.video_img.transform = transform
            self.canvas.update()
        except:
            pass

    def load_session(self, csv_data):
        if csv_data is None or csv_data.empty:
            return

        try:
            # Extract camera path
            if 'CamPosX' in csv_data.columns:
                cam_pos = np.vstack((csv_data['CamPosX'], csv_data['CamPosY'], csv_data['CamPosZ'])).T
                self.cam_path_line.set_data(pos=cam_pos)
                self.view.camera.center = np.mean(cam_pos, axis=0)

            # Extract basic gaze points (approx 2m out)
            if 'L_WorldPosX' in csv_data.columns or 'L_LocalPosX' in csv_data.columns:
                gaze_pts = []
                # Simple approximation: just take cam pos and add gaze dir
                for i, row in csv_data.iterrows():
                    left_valid = int(row.get('L_IsValid', 0)) == 1
                    if left_valid:
                        if 'L_WorldPosX' in row:
                            origin = np.array([row['L_WorldPosX'], row['L_WorldPosY'], row['L_WorldPosZ']])
                        else:
                            # fallback to cam pos for visualization simplicity
                            origin = np.array([row['CamPosX'], row['CamPosY'], row['CamPosZ']])
                            
                        dir = np.array([row['L_WorldDirX'], row['L_WorldDirY'], row['L_WorldDirZ']])
                        gaze_pts.append(origin + dir * 2.0) # Project 2 meters out

                if gaze_pts:
                    gaze_data = np.array(gaze_pts)
                    colors = np.ones((len(gaze_data), 4))
                    colors[:, 0] = 1 # Red
                    colors[:, 1:3] = 0
                    self.gaze_scatter.set_data(pos=gaze_data, face_color=colors, size=5)
        except Exception as e:
            print(f"Error loading 3D data: {e}")
