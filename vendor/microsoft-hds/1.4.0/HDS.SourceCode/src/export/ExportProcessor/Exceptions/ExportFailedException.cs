using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions
{
    public class ExportFailedException : Exception
    {
        public ExportFailedException() { }
        public ExportFailedException(string message) : base(message)
        {
        }
    }
}
