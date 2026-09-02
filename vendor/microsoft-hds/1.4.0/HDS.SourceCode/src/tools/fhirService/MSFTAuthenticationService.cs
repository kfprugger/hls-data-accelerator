using Azure.Core;
using Azure.Identity;

namespace fhirservice
{
    public class MSFTAuthenticationService
    {


        public MSFTAuthenticationService()
        {

        }

        /// <summary>
        /// Retrieve the token from cache
        /// if not present, Request from Azure AD
        /// </summary>
        /// <param name="resourceId"></param>
        /// <returns></returns>
        public async Task<string> RetrieveToken(string resourceId)
        {
            var tokenCredential = new DefaultAzureCredential(); // CodeQL [SM05137] This code is used for local testing and not deployed in production.
            var accessToken = await tokenCredential.GetTokenAsync(
                new TokenRequestContext(scopes: new string[] { resourceId + "/.default" }) { }
            );
            return accessToken.Token;
        }
    }

}
