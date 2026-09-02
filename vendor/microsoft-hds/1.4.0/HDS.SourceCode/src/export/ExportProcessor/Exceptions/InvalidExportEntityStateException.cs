using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions
{
    public class InvalidExportEntityStateException : Exception
    {
        public InvalidExportEntityStateException() { }
        public InvalidExportEntityStateException(string message) : base(message)
        {
        }
    }
}
