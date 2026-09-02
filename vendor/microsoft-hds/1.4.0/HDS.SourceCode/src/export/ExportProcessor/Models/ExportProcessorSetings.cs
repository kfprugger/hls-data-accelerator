using Microsoft.IntegratedDataPlatform.ExportProcessor.Services;
using Microsoft.IntegratedDataPlatform.ExportProcessor;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Models
{
    public class ExportProcessorSettings : IMSFTFHIRServerSettings, IFHIRServerSettings, IResourceManagerSettings
    {
        public string FHIRServerUri { get; set; }
        public string ExportContainerName { get; set; }
        public DateTime? DataStart { get; set; }
        public int RetryCount { get; set; }
        public string Resources { get; set; }
        public string JobOutputStorageAccountName { get; set; }
        public string JobOutputContainerName { get; set; }
    }
}
