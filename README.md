# Gaze Analysis App
Companion analysis app for the Vive Focus Vision 3 headset eyetracking in Unity projects.

Accompanying Unity code can be found at [ARTSLab-CITH/Unity-XR-Modules](https://github.com/ARTSLab-CITH/Unity-XR-Modules/tree/main/EyeTracker)

## Release Information
`eyetracker.apk` (Basic passthrough with eyetracking APK for the Vive Focus Vision 3 headset)
`GazeAnalyzer.exe` (Pre-built exe of Python app)

## Requirements
Desktop app requires ADB installed for importing. Looks for ADB at `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`

Unity package is in `EyeTracker` folder.
VIVE OpenXR Plugin Version: `2.5.1`
OpenXR Version: `1.12.1` (required by VIVE, must manually change to this older version)

VIVE Spectator Camera does not allow recording passthrough so it is unused currently.

## Running:
Execute the released exe or `python run.py`.

## Building:
`python build.py` or VSCode `Run Task > Build GazeAnalyzer executable`