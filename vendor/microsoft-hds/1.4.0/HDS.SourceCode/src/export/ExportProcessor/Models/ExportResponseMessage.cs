using Newtonsoft.Json;
using System;
using System.Collections.Generic;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Models
{
    public  class ExportResponseMessage
    {
        [JsonProperty("transactionTime")]
        public DateTime TransactionTime { get; set; }

        [JsonProperty("request")]
        public string Request { get; set; }

        [JsonProperty("requiresAccessToken")]
        public bool RequiresAccessToken { get; set; }

        [JsonProperty("output")]
        public List<Output> Output { get; set; }

        [JsonProperty("error")]
        public List<Output> Error { get; set; }

        [JsonProperty("Issues")]
        public List<Issue> Issues { get; set; }

        public override string ToString()
        {
            return JsonConvert.SerializeObject(this);
        }
    }

    public class OperationOutcome
    {
        [JsonProperty("resourceType")]
        public string ResourceType { get; set; }

        [JsonProperty("id")]
        public string Id { get; set; }

        [JsonProperty("Issues")]
        public List<Issue> Issues { get; set; }
        public override string ToString()
        {
            return JsonConvert.SerializeObject(this);
        }
    }

    public class Output
    {

        [JsonProperty("type")]
        public string Type { get; set; }

        [JsonProperty("url")]
        public string Url { get; set; }

        [JsonProperty("count")]
        public int Count { get; set; }
        public override string ToString()
        {
            return JsonConvert.SerializeObject(this);
        }
    }

    public class Issue
    {

        [JsonProperty("severity")]
        public IssueSeverity Severity { get; set; }

        [JsonProperty("code")]
        public string Code { get; set; }

        [JsonProperty("diagnostics")]
        public string Diagnostics { get; set; }

        public override string ToString()
        {
            return JsonConvert.SerializeObject(this);
        }
    }

    public class ExportOrchestrationStatus
    {
        [JsonProperty("isError")]
        public ExportStatus? ExportStatus { get; set; }

        [JsonProperty("output")]
        public List<Output> Output { get; set; }

        [JsonProperty("end")]
        public DateTime? End { get; set; }
    }
}
