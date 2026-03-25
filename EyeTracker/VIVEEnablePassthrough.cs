using UnityEngine;
using VIVE.OpenXR.Passthrough;
using VIVE.OpenXR.Samples;
namespace VIVE.OpenXR.CompositionLayer.Samples.Passthrough
{
    public class VIVEEnablePassthrough : MonoBehaviour
    {
        OpenXR.Passthrough.XrPassthroughHTC passthrough;

        void Start()
        {
            var result = PassthroughAPI.CreatePlanarPassthrough(out passthrough, LayerType.Underlay);
        }

        void OnDestroy()
        {
            PassthroughAPI.DestroyPassthrough(passthrough);
        }
    }

}