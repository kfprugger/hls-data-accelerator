using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Helper
{
    public static class HTTPHeadersExtensions
    {
        public const string ContentLocation = "Content-Location";
        public const string BearerToken = "Bearer";
        public const string Prefer = "Prefer";
        public const string AcceptAppJson = "application/json";
        public const string AcceptAppFhirjson = "application/fhir+json";
        public const string PreferResponse = "respond-async";
    }

    public static class FHIRServerNames
    {
        public const string AzureAPIForFHIR = "Azure API for FHIR";
        public const string AzureHealthcareAPIs = "Azure Healthcare APIs";
    }

    public static class Constants {

        public const int PollAfterInSeconds = 60;
        public const int BlobUrlLengthPriorToFolderPath = 4;
        public const int MinimumBlobUrlLengthWhenSplit = 6;
        public const string OutputType = "export";
        public const string SuccessfulExport = "Export completed successfully.";
        public const string SuccessfulExportWithNoOutput = "Export completed successfully. There was nothing to export.";
        public const string OutputFolderPath = "processing_status/fhir_2_omop/to_process";
        public const string AzureADDefaultScope = "/.default";
        public const string ExportJobInstanceId = "EXPORTJOB";
        public const string EntityKeyManagerId = "EntityKeyManager";
        public const string ResourceManagerId = "ResourceManager";
    }
}
