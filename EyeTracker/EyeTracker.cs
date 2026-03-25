using UnityEngine;
using UnityEngine.XR.OpenXR;
using VIVE.OpenXR;
using VIVE.OpenXR.EyeTracker;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Collections;

public class EyeTracker : MonoBehaviour
{
    // One struct per eye — mirrors both left and right independently.
    [System.Serializable]
    public struct EyeData
    {
        // Raw pose from OpenXR — in HMD-local space.
        // World-space pose = HMD transform applied to these values.
        public Vector3 localPos;       // gazePose.position (HMD-local)
        public Quaternion localRot;    // gazePose.orientation (HMD-local)

        // World-space position of the gaze origin (localPos transformed by HMD)
        public Vector3 worldPos;

        // Pre-computed forward vectors for convenience / validation.
        public Vector3 localDir;       // localRot * Vector3.forward  (HMD-local)
        public Vector3 worldDir;       // HMD world rotation * localDir

        public bool isValid;
        public float openness;
        public float pupilDiameter;
    }

    [System.Serializable]
    public struct EyeDataFrame
    {
        // Timestamp in seconds from start of recording (zero-based).
        public float timestamp;

        // HMD world transform — apply to left/right localPos/localRot to get world-space gaze.
        public Vector3 hmdPosition;
        public Quaternion hmdRotation;

        // Per-eye raw data.
        public EyeData left;
        public EyeData right;

        // ROI — determined by world-space raycast from left eye (primary).
        public string focusedROI;

        // Spectator camera world transform.
        public Vector3 camPosition;
        public Quaternion camRotation;
    }

    private List<EyeDataFrame> recordedEyeData = new List<EyeDataFrame>();
    private float recordingStartTime;
    public bool IsRecording { get; private set; } = false;

    ViveEyeTracker eyeTrackerFeature;


    void Awake()
    {
        eyeTrackerFeature = OpenXRSettings.Instance.GetFeature<ViveEyeTracker>();
    }

    void Start()
    {
        Debug.Log("[EyeTracker] Initializing Eye Tracker...");
        if (eyeTrackerFeature == null || !eyeTrackerFeature.enabled)
        {
            Debug.LogWarning("[EyeTracker] ViveEyeTracker feature is missing or disabled in OpenXR Settings.");
        }
    }

    public void StartRecording()
    {
        recordedEyeData.Clear();
        recordingStartTime = Time.time;
        IsRecording = true;
        Debug.Log("[EyeTracker] Eye Data Recording Started");
    }

    public void StopRecording()
    {
        if (!IsRecording) return;
        IsRecording = false;

        Debug.Log($"[EyeTracker] Eye Data Recording Stopped. Captured {recordedEyeData.Count} frames.");
        if (recordedEyeData.Count > 0)
            SaveDataToCSV();
    }

    // Format float with G9 precision for round-trip float32 accuracy.
    private static string F(float v) => v.ToString("G9", System.Globalization.CultureInfo.InvariantCulture);
    private static string F(Vector3 v) => $"{F(v.x)},{F(v.y)},{F(v.z)}";
    private static string F(Quaternion q) => $"{F(q.x)},{F(q.y)},{F(q.z)},{F(q.w)}";

    private void SaveDataToCSV()
    {
        string filename = $"EyeData_{System.DateTime.Now:yyyyMMdd_HHmmss}.csv";
        string filePath = Path.Combine(Application.persistentDataPath, filename);

        var sb = new StringBuilder();

        // Write Camera Metadata
        var specCam = Camera.main;

        sb.AppendLine("# [Camera]");
        if (specCam != null)
        {
            sb.AppendLine($"# FOV: {F(specCam.fieldOfView)}");
            sb.AppendLine($"# AspectRatio: {F(specCam.aspect)}");
        }

        sb.AppendLine("# [ROIs]");
        sb.AppendLine("# ID,PosX,PosY,PosZ,RotX,RotY,RotZ,RotW,ScaleX,ScaleY,ScaleZ");
        var rois = FindObjectsByType<RegionOfInterest>(FindObjectsSortMode.None);
        if (rois != null)
        {
            foreach (var roi in rois)
            {
                string id = !string.IsNullOrEmpty(roi.regionName) ? roi.regionName : roi.name;
                Transform t = roi.transform;
                sb.AppendLine($"# {id},{F(t.position)},{F(t.rotation)},{F(t.lossyScale)}");
            }
        }

        // Column layout:
        // Timestamp
        // HMD world transform (position + quaternion)
        // Left eye: local pos, local rot (quat), local dir (fwd vec), world dir (fwd vec), isValid, openness, pupilDiameter
        // Right eye: same layout
        // FocusedROI
        // Spectator cam: position + quaternion
        sb.AppendLine(
            "Timestamp," +
            "HmdPosX,HmdPosY,HmdPosZ,HmdRotX,HmdRotY,HmdRotZ,HmdRotW," +
            "L_LocalPosX,L_LocalPosY,L_LocalPosZ," +
            "L_WorldPosX,L_WorldPosY,L_WorldPosZ," +
            "L_LocalRotX,L_LocalRotY,L_LocalRotZ,L_LocalRotW," +
            "L_LocalDirX,L_LocalDirY,L_LocalDirZ," +
            "L_WorldDirX,L_WorldDirY,L_WorldDirZ," +
            "L_IsValid,L_Openness,L_PupilDiameter," +
            "R_LocalPosX,R_LocalPosY,R_LocalPosZ," +
            "R_WorldPosX,R_WorldPosY,R_WorldPosZ," +
            "R_LocalRotX,R_LocalRotY,R_LocalRotZ,R_LocalRotW," +
            "R_LocalDirX,R_LocalDirY,R_LocalDirZ," +
            "R_WorldDirX,R_WorldDirY,R_WorldDirZ," +
            "R_IsValid,R_Openness,R_PupilDiameter," +
            "FocusedROI," +
            "CamPosX,CamPosY,CamPosZ,CamRotX,CamRotY,CamRotZ,CamRotW"
        );

        foreach (var frame in recordedEyeData)
        {
            sb.Append(F(frame.timestamp)).Append(',');
            sb.Append(F(frame.hmdPosition)).Append(',').Append(F(frame.hmdRotation)).Append(',');
            // Left
            sb.Append(F(frame.left.localPos)).Append(',');
            sb.Append(F(frame.left.worldPos)).Append(',');
            sb.Append(F(frame.left.localRot)).Append(',');
            sb.Append(F(frame.left.localDir)).Append(',');
            sb.Append(F(frame.left.worldDir)).Append(',');
            sb.Append(frame.left.isValid ? "1" : "0").Append(',');
            sb.Append(F(frame.left.openness)).Append(',');
            sb.Append(F(frame.left.pupilDiameter)).Append(',');
            // Right
            sb.Append(F(frame.right.localPos)).Append(',');
            sb.Append(F(frame.right.worldPos)).Append(',');
            sb.Append(F(frame.right.localRot)).Append(',');
            sb.Append(F(frame.right.localDir)).Append(',');
            sb.Append(F(frame.right.worldDir)).Append(',');
            sb.Append(frame.right.isValid ? "1" : "0").Append(',');
            sb.Append(F(frame.right.openness)).Append(',');
            sb.Append(F(frame.right.pupilDiameter)).Append(',');
            // ROI and spectator cam
            sb.Append(frame.focusedROI).Append(',');
            sb.Append(F(frame.camPosition)).Append(',');
            sb.AppendLine(F(frame.camRotation));
        }

        try
        {
            // Writing asynchronously avoiding blocking the main thread
            string outputData = sb.ToString();
            System.Threading.Tasks.Task.Run(() =>
            {
                File.WriteAllText(filePath, outputData);
                Debug.Log($"[EyeTracker] Eye data saved asynchronously to: {filePath}");
            });
        }
        catch (System.Exception e)
        {
            Debug.LogError($"[EyeTracker] Failed to save eye data: {e.Message}");
        }
    }

    void Update()
    {
        if (eyeTrackerFeature == null || !eyeTrackerFeature.enabled) return;

        if (IsRecording)
        {
            EyeDataFrame frame = new EyeDataFrame();
            frame.timestamp = (Time.time - recordingStartTime) * 1000f;
            frame.focusedROI = "";

            // HMD world transform — Camera.main is the head-tracked XR camera.
            var hmdTransform = Camera.main.transform;
            frame.hmdPosition = hmdTransform.position;
            frame.hmdRotation = hmdTransform.rotation;

            // Fallback Spectator camera world transform to HMD.
            frame.camPosition = hmdTransform.position;
            frame.camRotation = hmdTransform.rotation;

            if (eyeTrackerFeature.GetEyeGazeData(out XrSingleEyeGazeDataHTC[] gazes))
            {
                frame.left = BuildEyeData(gazes[(int)XrEyePositionHTC.XR_EYE_POSITION_LEFT_HTC], hmdTransform);
                frame.right = BuildEyeData(gazes[(int)XrEyePositionHTC.XR_EYE_POSITION_RIGHT_HTC], hmdTransform);

                // World-space ROI raycast from left eye (use right if left invalid).
                var primary = frame.left.isValid ? frame.left : (frame.right.isValid ? frame.right : default);
                if (primary.isValid)
                {
                    Vector3 worldGazeOrigin = hmdTransform.TransformPoint(primary.localPos);
                    Ray ray = new Ray(worldGazeOrigin, primary.worldDir);
                    if (Physics.Raycast(ray, out RaycastHit hit, Mathf.Infinity, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Collide))
                    {
                        var roi = hit.collider.GetComponent<RegionOfInterest>();
                        if (roi != null)
                            frame.focusedROI = !string.IsNullOrEmpty(roi.regionName) ? roi.regionName : roi.name;
                    }
                }
            }

            if (eyeTrackerFeature.GetEyeGeometricData(out XrSingleEyeGeometricDataHTC[] geometrics))
            {
                frame.left.openness = geometrics[(int)XrEyePositionHTC.XR_EYE_POSITION_LEFT_HTC].eyeOpenness;
                frame.right.openness = geometrics[(int)XrEyePositionHTC.XR_EYE_POSITION_RIGHT_HTC].eyeOpenness;
            }

            if (eyeTrackerFeature.GetEyePupilData(out XrSingleEyePupilDataHTC[] pupils))
            {
                frame.left.pupilDiameter = pupils[(int)XrEyePositionHTC.XR_EYE_POSITION_LEFT_HTC].pupilDiameter;
                frame.right.pupilDiameter = pupils[(int)XrEyePositionHTC.XR_EYE_POSITION_RIGHT_HTC].pupilDiameter;
            }

            recordedEyeData.Add(frame);
        }
    }

    private static EyeData BuildEyeData(XrSingleEyeGazeDataHTC gaze, Transform hmdTransform)
    {
        var eye = new EyeData();
        eye.isValid = gaze.isValid;
        if (!gaze.isValid) return eye;

        eye.localPos = gaze.gazePose.position.ToUnityVector();
        eye.worldPos = hmdTransform.TransformPoint(eye.localPos);
        eye.localRot = gaze.gazePose.orientation.ToUnityQuaternion();
        eye.localDir = eye.localRot * Vector3.forward;
        eye.worldDir = hmdTransform.TransformDirection(eye.localDir);
        return eye;
    }
}