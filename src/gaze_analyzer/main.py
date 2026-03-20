import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTabWidget, QFileDialog, QMessageBox, QDialog, QListWidget, QSystemTrayIcon,
    QFrame, QSizePolicy, QStyle, QListWidgetItem, QAbstractItemView
)
from PySide6.QtCore import Qt
from gaze_analyzer.database import init_db, SessionLocal, Session
from gaze_analyzer.import_service import ImportWorker
from gaze_analyzer.video_player_widget import VideoPlayerWidget
from gaze_analyzer.view_3d_widget import View3DWidget
from gaze_analyzer.data_processor import load_session_data

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gaze Analyzer")
        self.resize(1024, 768)
        
        # UI Setup
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Main split: left panel for controls, right panel for visualization
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)
        
        # --- Left Panel (Controls) ---
        left_panel = QFrame()
        left_panel.setFrameShape(QFrame.StyledPanel)
        left_panel.setMaximumWidth(280)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(15)
        
        lbl_control = QLabel("<b>Data Management</b>")
        lbl_control.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(lbl_control)
        
        self.btn_auto_import = QPushButton("Import from Device (ADB)")
        self.btn_auto_import.setMinimumHeight(35)
        self.btn_auto_import.clicked.connect(self.start_adb_import)
        left_layout.addWidget(self.btn_auto_import)
        
        self.btn_manual_import = QPushButton("Manual File Selection")
        self.btn_manual_import.setMinimumHeight(35)
        self.btn_manual_import.clicked.connect(self.manual_import)
        left_layout.addWidget(self.btn_manual_import)
        
        left_layout.addSpacing(20)
        
        lbl_session = QLabel("<b>Session Management</b>")
        lbl_session.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(lbl_session)
        
        self.btn_load_session = QPushButton("Database Explorer")
        self.btn_load_session.setMinimumHeight(35)
        self.btn_load_session.clicked.connect(self.show_load_session_dialog)
        left_layout.addWidget(self.btn_load_session)
        
        left_layout.addStretch()
        
        content_layout.addWidget(left_panel)
        
        # --- Right Panel (Visualizations) ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(right_panel, 1) # stretch parameter
        
        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs)
        
        tab_2d_container = QWidget()
        l_2d = QVBoxLayout(tab_2d_container)
        l_2d.setContentsMargins(0, 0, 0, 0)
        self.video_player = VideoPlayerWidget()
        l_2d.addWidget(self.video_player)
        self.tabs.addTab(tab_2d_container, "2D Video Overlay")
        
        tab_3d_container = QWidget()
        l_3d = QVBoxLayout(tab_3d_container)
        l_3d.setContentsMargins(0, 0, 0, 0)
        self.view_3d = View3DWidget()
        l_3d.addWidget(self.view_3d)
        self.tabs.addTab(tab_3d_container, "3D Spatial View")

        # Connect 2d player to 3d view for live video projection
        self.video_player.frame_processed.connect(self.view_3d.update_video_plane)

        # --- Status Bar ---
        self.statusBar().showMessage("Ready. Initialize a session by importing from a VIVE headset or selecting files manually.")
        
        self.imports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Imports")
        os.makedirs(self.imports_dir, exist_ok=True)
        
        self.import_worker = None

    def start_adb_import(self):
        self.statusBar().showMessage("Starting import...")
        self.btn_auto_import.setEnabled(False)
        self.import_worker = ImportWorker(self.imports_dir)
        self.import_worker.progress.connect(self.statusBar().showMessage)
        self.import_worker.error.connect(self.handle_import_error)
        self.import_worker.finished_import.connect(self.handle_import_success)
        self.import_worker.start()

    def handle_import_error(self, err_msg):
        self.statusBar().showMessage("Import failed.")
        QMessageBox.critical(self, "Import Error", err_msg)
        self.btn_auto_import.setEnabled(True)

    def handle_import_success(self, mp4_path, csv_path):
        self.statusBar().showMessage(f"Successfully imported: {os.path.basename(mp4_path)}")
        self.btn_auto_import.setEnabled(True)
        self.register_session(mp4_path, csv_path)

    def manual_import(self):
        mp4_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", "", "Video Files (*.mp4)")
        if not mp4_path:
            return
            
        csv_path, _ = QFileDialog.getOpenFileName(self, "Select Eye Tracking CSV", os.path.dirname(mp4_path), "CSV Files (*.csv)")
        if not csv_path:
            return
            
        self.statusBar().showMessage(f"Manually loaded: {os.path.basename(mp4_path)}")
        self.register_session(mp4_path, csv_path)

    def register_session(self, video_path, csv_path):
        db = SessionLocal()
        session_name = os.path.basename(video_path).replace(".mp4", "")
        
        # Check if already exists to avoid duplicates
        existing = db.query(Session).filter_by(name=session_name).first()
        if not existing:
            new_session = Session(
                name=session_name,
                video_path=video_path,
                csv_path=csv_path
            )
            db.add(new_session)
            db.commit()
            db.refresh(new_session)
        db.close()
        
        QMessageBox.information(self, "Session Loaded", f"Session '{session_name}' is ready for visualization.")
        
        self.load_active_session(video_path, csv_path)

    def load_active_session(self, video_path, csv_path):
        # Load session data into UI components
        df, metadata = load_session_data(csv_path)
        self.video_player.load_session(video_path, df, metadata)
        self.view_3d.load_session(df)

    def show_load_session_dialog(self):
        db = SessionLocal()
        sessions = db.query(Session).order_by(Session.imported_at.desc()).all()
        
        if not sessions:
            QMessageBox.information(self, "No Sessions", "No previous sessions found in the database.")
            db.close()
            return
            
        dlg = QDialog(self)
        dlg.setWindowTitle("Database Explorer")
        dlg.resize(500, 350)
        
        layout = QVBoxLayout(dlg)
        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        
        def populate_list():
            list_widget.clear()
            current_sessions = db.query(Session).order_by(Session.imported_at.desc()).all()
            for sess in current_sessions:
                item_text = f"{sess.name} (Imported: {sess.imported_at.strftime('%Y-%m-%d %H:%M')})"
                item = QListWidgetItem(item_text)
                item.setData(100, sess.video_path)
                item.setData(101, sess.csv_path)
                item.setData(102, sess.id)
                list_widget.addItem(item)
                
        populate_list()
        layout.addWidget(list_widget)
        
        btn_layout = QHBoxLayout()
        
        btn_delete = QPushButton("Delete Session")
        btn_delete.setStyleSheet("QPushButton { color: red; }")
        
        def delete_selected():
            item = list_widget.currentItem()
            if not item:
                return
            sess_id = item.data(102)
            reply = QMessageBox.question(dlg, "Confirm Delete", "Are you sure you want to delete this session? The underlying files will not be deleted.", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                session_to_delete = db.query(Session).filter(Session.id == sess_id).first()
                if session_to_delete:
                    db.delete(session_to_delete)
                    db.commit()
                    populate_list()
        
        btn_delete.clicked.connect(delete_selected)
        btn_layout.addWidget(btn_delete)
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dlg.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_load = QPushButton("Load")
        btn_load.clicked.connect(dlg.accept)
        btn_load.setDefault(True)
        btn_layout.addWidget(btn_load)
        
        layout.addLayout(btn_layout)
        
        if dlg.exec() == QDialog.Accepted and list_widget.currentItem():
            item = list_widget.currentItem()
            video_path = item.data(100)
            csv_path = item.data(101)
            
            if os.path.exists(video_path) and os.path.exists(csv_path):
                self.statusBar().showMessage(f"Loaded from database: {os.path.basename(video_path)}")
                self.load_active_session(video_path, csv_path)
            else:
                QMessageBox.warning(self, "Files Missing", "The original files for this session have been moved or deleted.")
                
        db.close()
