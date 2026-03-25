# Gaze Analysis App
Vive Focus 3 headset eyetracking in Unity projects.

Two files:
`eyetracker.apk` (Unity project with the Unity package setup in it)
`GazeAnalyzer.exe` (Pre-built exe of Python app)

Desktop app requires ADB installed for importing. Looks for ADB at `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`

Unity package is in `EyeTracker` folder.
VIVE OpenXR Plugin Version: `2.5.1`
OpenXR Version: `1.12.1` (required by VIVE, must manually change to this older version)

VIVE Spectator Camera does not allow recording passthrough so it is unused currently.

To run:
```python
python run.py
``

To build:
`python build.py` or VSCode `Run Task > Build GazeAnalyzer executable`