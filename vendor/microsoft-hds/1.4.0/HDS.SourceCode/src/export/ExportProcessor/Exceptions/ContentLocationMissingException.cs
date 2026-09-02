using System;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions
{
    public class ContentLocationMissingException : Exception
    {
        public ContentLocationMissingException()
        {
        }
        public ContentLocationMissingException(string message) : base(message)
        {
        }
    }
}
