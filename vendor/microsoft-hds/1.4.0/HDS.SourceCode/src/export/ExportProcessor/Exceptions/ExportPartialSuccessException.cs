using System;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions
{
    public class ExportPartialSuccessException : Exception
    {
        public ExportPartialSuccessException() { }
        public ExportPartialSuccessException(string message) : base(message)
        {
        }
    }
}
