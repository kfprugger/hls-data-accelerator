using Azure.Core;
using Azure.Identity;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.Logging;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Helper;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces;
using System;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Services.Authentication
{
    /// <summary>
    /// Will be used when the FHIR Server is protected by Microsoft Auth provider like Azure Health Data Services (AHDS)
    /// Token will be stored in Memory cache
    /// </summary>
    public class MSFTAuthenticationService : ITokenAuthenticationService
    {
        private readonly IMemoryCache _memoryCache;
        private readonly ILogger _logger;

        public MSFTAuthenticationService(ILogger<MSFTAuthenticationService> logger, IMemoryCache memoryCache)
        {
            _memoryCache = memoryCache ?? throw new ArgumentNullException(nameof(memoryCache));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        }

        /// <summary>
        /// Retrieve the token from cache
        /// if not present, Request from Azure AD
        /// </summary>
        /// <param name="resourceId"></param>
        /// <returns></returns>
        public async Task<string> RetrieveToken(string resourceId)
        {

            var tokenKey = getTokenKey(resourceId);

            if (!_memoryCache.TryGetValue(tokenKey, out string token))
            {
                var tokenCredential = new ManagedIdentityCredential();
                var accessToken = await tokenCredential.GetTokenAsync(
                    new TokenRequestContext(scopes: new string[] { resourceId + Constants.AzureADDefaultScope }) { }
                );

                _memoryCache.Set(tokenKey, accessToken.Token, accessToken.ExpiresOn.Subtract(TimeSpan.FromMinutes(1)));
                token = accessToken.Token;
            }
            else
            {
                _logger.LogInformation($"Using cached token for resource - {resourceId}");
            }

            return token;
        }

        /// <summary>
        /// Delete the token from cache
        /// </summary>
        /// <param name="resourceId">The key for the token</param>
        /// <returns></returns>
        public void DeleteTokenFromCache(string resourceId)
        {

            var tokenKey = getTokenKey(resourceId);

            if (_memoryCache.TryGetValue(tokenKey, out string token))
            {
                _memoryCache.Remove(tokenKey);
                _logger.LogInformation($"Removing cached authentication token - {resourceId}");
            }
        }


        /// <summary>
        /// Generates the token key for a given resoruceID
        /// </summary>
        /// <param name="resourceId"></param>
        /// <returns></returns>
        public string getTokenKey(string resourceId)
        {
            return $"MSFTAuthToken-{resourceId}";
        }
    }
}
