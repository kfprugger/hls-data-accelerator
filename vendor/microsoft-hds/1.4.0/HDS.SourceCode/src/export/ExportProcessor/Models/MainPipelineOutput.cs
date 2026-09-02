using Newtonsoft.Json;
using System;
using System.Collections.Generic;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Models
{
    public class MainPipelineOutput
    {
        [JsonProperty("fileName")]
        public string FileName { get; set; }

        [JsonProperty("timestamp")]
        public string Timestamp { get; set; }

        [JsonProperty("resourcesToTransform")]
        public List<ResourceToTransform> ResourcesToTransform { get; set; }

    }

    public class ResourceToTransform
    {

        [JsonProperty("resourceType")]
        public string ResourceType { get; set; }


        [JsonProperty("path")]
        public string PathToFolder { get; set; }

    }
}
