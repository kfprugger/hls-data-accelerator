using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Tests.Helper
{
    public static class MockDataGenerator
    {
        public static ExportResponseMessage GenerateSuccessExportResponse()
        {
            return new ExportResponseMessage()
            {
                TransactionTime = DateTime.UtcNow,
                RequiresAccessToken = false,
                Error = null,
                Issues = null,
                Output = new List<Output>() { new Output { Count= 1 , Type = "Resource", Url = "https://test.com"} }
            };
        }

        public static ExportResponseMessage GenerateExportResponseWithErrors()
        {
            return new ExportResponseMessage()
            {
                TransactionTime = DateTime.UtcNow,
                RequiresAccessToken = false,
                Error = new List<Output>() { new Output { Count = 1, Type = "Resource", Url = "https://errortest.com" } },
                Issues = null,
                Output = new List<Output>() { new Output { Count = 1, Type = "Resource", Url = "https://test.com" } }
            };
        }

        public static string GenerateExportResponseWithIssues()
        {
            string responseMessageWithIssues = JsonConvert.SerializeObject(
                new {
                   TransactionTime = DateTime.UtcNow,
                   RequiresAccessToken = false,
                   Issues = new List<dynamic> { new {Code = "NotSupported", Diagnostics = "Not Supported", Severity = "warning" } }
                }
                );

            return responseMessageWithIssues;
        }

    }
}

