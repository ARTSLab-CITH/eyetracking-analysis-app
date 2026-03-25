using UnityEngine;
using UnityEngine.UI;
using System.IO;
using System.Collections;
using System.Collections.Generic;

public class SystemRecorderWatcher : MonoBehaviour
{
    private EyeTracker eyeTracker;
    private GameObject blockerCanvasObj;
    private Text statusText;
    private Canvas blockerCanvas;

    private string[] searchPaths = new string[] {
        "/sdcard/Movies/Screenrecorder",
        "/sdcard/Movies",
        "/sdcard/DCIM/Screen records",
        "/storage/emulated/0/Movies",
        "/sdcard/Video" // Focus 3 might use an unusual path
    };

    private Dictionary<string, int> directoryFileCounts = new Dictionary<string, int>();
    private HashSet<string> existingFiles = new HashSet<string>();
    private string currentRecordingFile = null;
    private long lastFileSize = -1;
    private float timeSinceLastSizeChange = 0f;
    private bool isWaitingForStart = true;
    private bool hasInitializedBaseline = false;

    void Start()
    {
        Debug.Log("[SystemRecorderWatcher] Starting initialization...");
        eyeTracker = FindFirstObjectByType<EyeTracker>();
        if (eyeTracker == null)
            Debug.LogWarning("[SystemRecorderWatcher] No EyeTracker found in scene yet. Will retry in Update.");

#if UNITY_ANDROID && !UNITY_EDITOR
        if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.ExternalStorageRead))
        {
            Debug.Log("[SystemRecorderWatcher] Requesting READ_EXTERNAL_STORAGE permission.");
            UnityEngine.Android.Permission.RequestUserPermission(UnityEngine.Android.Permission.ExternalStorageRead);
        }
#endif

        CreateBlockerUI();
        StartCoroutine(PollForRecording());
    }

    void Update()
    {
        if (eyeTracker == null)
            eyeTracker = FindFirstObjectByType<EyeTracker>();

        if (blockerCanvas != null && blockerCanvas.worldCamera == null)
        {
            if (Camera.main != null)
            {
                blockerCanvas.worldCamera = Camera.main;
            }
        }
    }

    void CreateBlockerUI()
    {
        blockerCanvasObj = new GameObject("BlockerCanvas");
        DontDestroyOnLoad(blockerCanvasObj);
        blockerCanvas = blockerCanvasObj.AddComponent<Canvas>();

        blockerCanvas.renderMode = RenderMode.ScreenSpaceCamera;
        blockerCanvas.worldCamera = Camera.main;
        blockerCanvas.planeDistance = 0.5f;
        blockerCanvas.sortingOrder = 9999;

        blockerCanvasObj.AddComponent<CanvasScaler>();
        blockerCanvasObj.AddComponent<GraphicRaycaster>();

        GameObject bgObj = new GameObject("Background");
        bgObj.transform.SetParent(blockerCanvasObj.transform, false);
        Image bgImg = bgObj.AddComponent<Image>();
        bgImg.color = Color.black;
        RectTransform bgRect = bgObj.GetComponent<RectTransform>();
        bgRect.anchorMin = Vector2.zero;
        bgRect.anchorMax = Vector2.one;
        bgRect.offsetMin = new Vector2(-5000, -5000);
        bgRect.offsetMax = new Vector2(5000, 5000);

        GameObject textObj = new GameObject("Text");
        textObj.transform.SetParent(blockerCanvasObj.transform, false);
        statusText = textObj.AddComponent<Text>();
        statusText.text = "Waiting for System Screen Recording...\n(Start recording to begin passthrough test)";
        statusText.font = Resources.GetBuiltinResource<Font>("Arial.ttf");
        if (statusText.font == null) statusText.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        statusText.fontSize = 48;
        statusText.alignment = TextAnchor.MiddleCenter;
        statusText.color = Color.white;
        RectTransform textRect = textObj.GetComponent<RectTransform>();
        textRect.anchorMin = Vector2.zero;
        textRect.anchorMax = Vector2.one;
        textRect.sizeDelta = Vector2.zero;
    }

    IEnumerator PollForRecording()
    {
        WaitForSeconds waitQuick = new WaitForSeconds(0.5f);
        WaitForSeconds waitSlow = new WaitForSeconds(1.0f);

        Debug.Log("[SystemRecorderWatcher] Entering PollForRecording coroutine loop.");
        while (true)
        {
            if (!hasInitializedBaseline)
            {
#if UNITY_ANDROID && !UNITY_EDITOR
                if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(UnityEngine.Android.Permission.ExternalStorageRead))
                {
                    yield return waitQuick;
                    continue;
                }
#endif
                // After permissions are granted (or immediately in editor), snapshot the preexisting file counts
                foreach (var path in searchPaths)
                {
                    if (Directory.Exists(path))
                    {
                        try
                        {
                            var files = Directory.GetFiles(path, "*.mp4");
                            directoryFileCounts[path] = files.Length;
                            foreach (var f in files) existingFiles.Add(f);
                        }
                        catch (System.Exception e) { Debug.LogWarning($"[SystemRecorderWatcher] Init read error on {path}: {e.Message}"); }
                    }
                }
                hasInitializedBaseline = true;
                Debug.Log($"[SystemRecorderWatcher] Baseline initialized. Tracking {existingFiles.Count} existing mp4 files.");
                yield return waitQuick;
                continue;
            }

            if (isWaitingForStart)
            {
                bool newFileDetected = false;

                foreach (var path in searchPaths)
                {
                    if (!Directory.Exists(path)) continue;

                    try
                    {
                        var files = Directory.GetFiles(path, "*.mp4");
                        if (!directoryFileCounts.ContainsKey(path)) directoryFileCounts[path] = 0;

                        int previousCount = directoryFileCounts[path];
                        directoryFileCounts[path] = files.Length;

                        if (files.Length > previousCount)
                        {
                            // File count strictly increased! Let's find the new one.
                            foreach (var file in files)
                            {
                                if (!existingFiles.Contains(file))
                                {
                                    Debug.Log($"[SystemRecorderWatcher] NEW ACTIVE RECORDING DETECTED via count increase! File: {file}");
                                    currentRecordingFile = file;
                                    isWaitingForStart = false;
                                    existingFiles.Add(file);
                                    newFileDetected = true;
                                    break;
                                }
                            }
                        }
                        else if (files.Length < previousCount)
                        {
                            Debug.Log($"[SystemRecorderWatcher] File deleted in {path}. New count: {files.Length}");
                        }

                        // Always sync the known file set just in case
                        foreach (var file in files) existingFiles.Add(file);
                    }
                    catch (System.Exception e) { Debug.LogWarning($"[SystemRecorderWatcher] Error polling {path}: {e.Message}"); }

                    if (newFileDetected) break;
                }

                if (newFileDetected)
                {
                    Debug.Log($"[SystemRecorderWatcher] Waiting 2 seconds for {currentRecordingFile} hardware stream...");
                    statusText.text = "Recording detected, synchronizing...";
                    yield return new WaitForSeconds(2.0f);

                    Debug.Log("[SystemRecorderWatcher] ** CURTAIN DROP ** - Disabling blocker canvas and starting EyeTracker!");
                    blockerCanvasObj.SetActive(false);
                    if (eyeTracker != null)
                        eyeTracker.StartRecording();

                    try
                    {
                        lastFileSize = new FileInfo(currentRecordingFile).Length;
                    }
                    catch { lastFileSize = -1; }

                    timeSinceLastSizeChange = 0f;
                }

                yield return waitQuick;
            }
            else
            {
                try
                {
                    if (File.Exists(currentRecordingFile))
                    {
                        long currentSize = new FileInfo(currentRecordingFile).Length;
                        if (currentSize == lastFileSize)
                        {
                            timeSinceLastSizeChange += 1.0f;
                            if (timeSinceLastSizeChange >= 2.0f)
                            {
                                Debug.Log($"[SystemRecorderWatcher] Screen recording stopped updating for 2s! Triggering stop: {currentRecordingFile}");
                                if (eyeTracker != null) eyeTracker.StopRecording();

                                blockerCanvasObj.SetActive(true);
                                statusText.text = "Waiting for System Screen Recording...\n(Start recording to begin passthrough test)";
                                isWaitingForStart = true;
                                currentRecordingFile = null;
                            }
                        }
                        else
                        {
                            lastFileSize = currentSize;
                            timeSinceLastSizeChange = 0f;
                        }
                    }
                    else
                    {
                        Debug.LogError($"[SystemRecorderWatcher] TRACKED RECORDING FILE LOST! {currentRecordingFile}");
                        if (eyeTracker != null) eyeTracker.StopRecording();
                        blockerCanvasObj.SetActive(true);
                        statusText.text = "File lost. Waiting for System Screen Recording...";
                        isWaitingForStart = true;
                        currentRecordingFile = null;
                    }
                }
                catch (System.Exception e) { Debug.LogWarning($"[SystemRecorderWatcher] Error monitoring file: {e.Message}"); }

                yield return waitSlow;
            }
        }
    }
}
