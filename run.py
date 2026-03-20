import sys
from pathlib import Path

# Add src to the Python path
src_path = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(src_path))

from gaze_analyzer.main import MainWindow
from gaze_analyzer.database import init_db
from PySide6.QtWidgets import QApplication

if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
