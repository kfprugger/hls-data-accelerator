using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces
{
    /// <summary>
    /// Interface to be implemented by all auth services
    /// </summary>
    public interface ITokenAuthenticationService
    {
        public Task<string> RetrieveToken(string resourceId);

        public void DeleteTokenFromCache(string resourceId);

    }
}
