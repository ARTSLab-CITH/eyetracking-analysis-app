# Project Guidelines

## Code Style
- Use absolute imports from `src` (e.g., `from gaze_analyzer.database import init_db`).
- The entry point script (`run.py`) manually inserts the `src` folder into the Python path at runtime (`sys.path.insert(0, ...)`). Keep this in mind when dealing with imports.

## Architecture
- **Dual Flow:** The project serves as both a fast OpenCV CLI script (`gaze_overlay.py`) for rendering visual overlays and a full `PySide6` Desktop GUI (`src/gaze_analyzer/main.py`) for managing recording sessions.
- **Database Layer:** `SQLAlchemy` is used (`src/gaze_analyzer/database.py`) to map VIVE sessions and Regions of Interest (ROIs).
- **Device Integration:** Relies on grabbing screen recordings and CSV metrics straight from an Android-based VIVE headset using ADB commands.
- **Spatial Processing:** Transforms and 3D-to-2D projection math are handled largely by `numpy` and `scipy.spatial.transform.Rotation`.

## Build and Run
- **Install Dependencies:** `pip install -r requirements.txt`
- **Run the GUI Application:** `python run.py`
- **Run the CLI Script:** `python gaze_overlay.py <video> <csv> [--output <output.mp4>] [--fov <fov_degrees>]`
- **Clean Environment (Wipe DB & Data):** `python clean_env.py`
- *Note: No formal testing framework is currently in place.*

## Conventions & Pitfalls
- **Pathing Discrepancy for "Imports":** Be careful with the `Imports` folder. `clean_env.py` targets a `root_dir / "Imports"` folder, but the UI in `src/gaze_analyzer/main.py` explicitly constructs its path inside `src/gaze_analyzer/Imports`.
- **3D Coordinate Math Confusion:** Unity (where the data comes from) is Left-Handed Y-up, whereas SciPy usually relies on distinct coordinate frame assumptions. See `_debug_projection.py` for sandbox scripts analyzing quaternion math for projecting a 3D gaze vector onto a 2D viewport.
- **Hardcoded Windows ADB Path:** `gaze_overlay.py` has a hardcoded Windows path to find `adb.exe`. Watch out for cross-platform execution issues.
