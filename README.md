# Gaze Analysis App
Companion analysis app for the Vive Focus Vision 3 headset eyetracking in Unity projects.

Accompanying Unity code can be found at [ARTSLab-CITH/Unity-XR-Modules](https://github.com/ARTSLab-CITH/Unity-XR-Modules/tree/main/EyeTracker)

## Major Issues with Projection of Gaze Position
- Spectator camera does not allow recording of passthrough (VIVE Internal).
- VIVE screen recording is different than app view and only from a single eye, not centered on eyes.
- FieldOfView is different in recording and app
- Projection depth (which 2D point is dependent on) has to be approximated using stereoscopic vergence
- VIVE Eye Tracking API & Unity `WorldToScreenPoint` are not behaving reliably in tests
- 

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