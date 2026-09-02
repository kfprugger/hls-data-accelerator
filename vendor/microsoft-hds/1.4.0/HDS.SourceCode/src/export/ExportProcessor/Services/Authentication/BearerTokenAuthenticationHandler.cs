using System;
using System.Net.Http.Headers;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Helper;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Services.Authentication
{
    public class BearerTokenAuthenticationHandler : DelegatingHandler
    {
        private readonly ITokenAuthenticationService _authService = null;
        private readonly string _resourceId = null;

        public BearerTokenAuthenticationHandler(ITokenAuthenticationService authService, string resourceId)
        {
            _authService = authService;
            _resourceId = resourceId;
        }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request is null)
            {
                throw new ArgumentNullException(nameof(request));
            }

            var token = await _authService.RetrieveToken(_resourceId).ConfigureAwait(false);
            request.Headers.Authorization = new AuthenticationHeaderValue(HTTPHeadersExtensions.BearerToken, token);
            var result = await base.SendAsync(request, cancellationToken).ConfigureAwait(false);

            // If status code is related to authentication, delete token from cache 
            if (result.StatusCode == System.Net.HttpStatusCode.Unauthorized || result.StatusCode == System.Net.HttpStatusCode.Forbidden)
            {
                _authService.DeleteTokenFromCache(_resourceId);
            }

            return result;
        }
    }

}
