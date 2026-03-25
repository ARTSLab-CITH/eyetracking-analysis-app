using UnityEngine;

public class RegionOfInterest : MonoBehaviour
{
    [Tooltip("Name of the region to be recorded. If empty, uses the GameObject name.")]
    public string regionName;

    void Awake()
    {
        // Ensure the visual representation is invisible at runtime if a renderer exists
        var renderer = GetComponent<Renderer>();
        if (renderer != null)
        {
            renderer.enabled = false;
        }

        // Validate collider presence
        if (GetComponent<Collider>() == null)
        {
            Debug.LogWarning($"RegionOfInterest '{name}' is missing a Collider! Gaze detection will not work.", this);
        }
    }
}
