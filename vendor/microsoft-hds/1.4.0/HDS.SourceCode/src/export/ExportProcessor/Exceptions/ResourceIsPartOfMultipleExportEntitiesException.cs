using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions
{
    public class ResourceIsPartOfMultipleExportEntitiesException : Exception
    {
        public ResourceIsPartOfMultipleExportEntitiesException() { }
        public ResourceIsPartOfMultipleExportEntitiesException(string message) : base(message)
        {
        }
    }
}
