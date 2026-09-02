using System;
using Newtonsoft.Json;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Models
{
    public class ExportEntity
    {
        [JsonProperty("start")]
        public DateTime? Start { get; set; }

        [JsonProperty("resourceType")]
        public string ResourceType { get; set; }
    }
}
