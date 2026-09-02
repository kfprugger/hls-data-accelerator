using Newtonsoft.Json;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Models
{
    public class CapabilityStatement
    {
        [JsonProperty("resourceType")]
        public string ResourceType { get; set; }

        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("version")]
        public string Version { get; set; }

        [JsonProperty("software")]
        public Software Software { get; set; }
    }

    public class Software
    {

        [JsonProperty("name")]
        public string Name { get; set; }

        [JsonProperty("version")]
        public string Version { get; set; }
    }
}
