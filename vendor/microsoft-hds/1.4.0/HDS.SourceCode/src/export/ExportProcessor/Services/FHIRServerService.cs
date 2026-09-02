using Microsoft.IntegratedDataPlatform.ExportProcessor.Helper;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using System;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Services
{

    /// <summary>
    /// Defines the interface for a FHIR Server Service
    /// </summary>
    public class FHIRServerService
    {
        private readonly HttpClient _httpClient;
        private readonly IFHIRServerSettings _fhirServerSettings;

        public FHIRServerService(HttpClient httpClient, IFHIRServerSettings settings)
        {
            _httpClient = httpClient;
            _fhirServerSettings = settings;
        }

        /// <summary>
        /// GetEntityState the metadata of the configured fhir server
        /// </summary>
        /// <param name="url">The url to call</param>
        /// <returns>The http response from the call</returns>
        public virtual async Task<CapabilityStatement> GetMetadata()
        {
            var request = new HttpRequestMessage()
            {
                RequestUri = new Uri("metadata", UriKind.Relative),
                Method = HttpMethod.Get,
            };
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue(HTTPHeadersExtensions.AcceptAppJson));
            var response = await _httpClient.SendAsync(request);
            response.EnsureSuccessStatusCode();
            using (var stream = await response.Content.ReadAsStreamAsync())
            {
                return Utility.DeserializeJsonFromStream<CapabilityStatement>(stream);
            }

        }

        /// <summary>
        /// Will trigger an export on the FHIR Server
        /// </summary>
        /// <param name="resourceType">A string delimited list of resources</param>
        /// <param name="since">The start time of the export</param>
        /// <param name="till">The end time of the export</param>
        /// <returns>The http response from the call</returns>
        public virtual Task<HttpResponseMessage> TriggerExport(string resourceType, string since)
        {
            var relativeUrl = $"$export?&_type={resourceType}&_since={since}";
            return InvokeExport(relativeUrl);
        }

        /// <summary>
        /// Will call the provided uri
        /// </summary>
        /// <param name="url">The url to call</param>
        /// <returns>The http response from the call</returns>
        public virtual Task<HttpResponseMessage> PollContentLocation(Uri pollingUri) {
            var request = new HttpRequestMessage()
            {
                RequestUri = pollingUri,
                Method = HttpMethod.Get,
            };
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue(HTTPHeadersExtensions.AcceptAppJson));
            return _httpClient.SendAsync(request);
        }

        /// <summary>
        /// Execute a trigger operation on the fhir server
        /// </summary>
        /// <param name="relativeUrl">The relative URL to call to trigger an export</param>
        /// <returns></returns>
        public Task<HttpResponseMessage> InvokeExport(string relativeUrl)
        {
            var request = new HttpRequestMessage()
            {
                RequestUri = new Uri(relativeUrl, UriKind.Relative),
                Method = HttpMethod.Get,
            };
            request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue(HTTPHeadersExtensions.AcceptAppFhirjson));
            request.Headers.Add(HTTPHeadersExtensions.Prefer, HTTPHeadersExtensions.PreferResponse);
            return _httpClient.SendAsync(request);
        }
    }

    public interface IFHIRServerSettings
    {
        public string FHIRServerUri { get; set; }

    }
}
