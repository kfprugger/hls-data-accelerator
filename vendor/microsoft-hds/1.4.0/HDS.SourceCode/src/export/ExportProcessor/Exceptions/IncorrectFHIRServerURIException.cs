using System;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions
{
    public class IncorrectFHIRServerURIException : Exception
    {
        public IncorrectFHIRServerURIException()
        {
        }
        public IncorrectFHIRServerURIException(string message) : base(message)
        {
        }
    }
}
