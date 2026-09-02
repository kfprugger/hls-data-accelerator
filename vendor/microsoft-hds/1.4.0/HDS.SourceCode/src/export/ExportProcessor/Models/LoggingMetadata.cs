using Newtonsoft.Json;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Models
{
    public class LoggingMetadata
    {

        [JsonProperty("correlationId")]
        public string CorrelationId { get; set; }

        [JsonProperty("entity")]
        public string Entity { get; set; }

        [JsonProperty("runId")]
        public string RunId { get; set; }
    }
}
