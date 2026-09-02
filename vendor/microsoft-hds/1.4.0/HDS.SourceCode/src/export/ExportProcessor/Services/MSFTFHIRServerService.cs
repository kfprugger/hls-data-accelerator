using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Services
{
    public class MSFTFHIRServerService : FHIRServerService
    {
        private readonly IMSFTFHIRServerSettings _fhirServerSettings;

        public MSFTFHIRServerService(HttpClient httpClient, IMSFTFHIRServerSettings fhirServerSettings, ILogger<MSFTFHIRServerService> logger) : base(httpClient, fhirServerSettings)
        {
            _fhirServerSettings = fhirServerSettings ;
        }

        public override Task<HttpResponseMessage> TriggerExport(string resourceType, string since)
        {
            var relativeUrl = $"$export?_container={_fhirServerSettings.ExportContainerName}&_type={resourceType}&_since={since}";
            return InvokeExport(relativeUrl);
        }
    }

    public interface IMSFTFHIRServerSettings : IFHIRServerSettings
    {
        public string ExportContainerName { get; set; }

    }
}
