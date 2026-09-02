
namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Models
{
    public enum ExportStatus {
        Succeeded,
        InProgress,
        Failed,
        Updating
    }
    public enum IssueSeverity
    {
        Fatal,
        Error,
        Warning,
        Information
    }
}