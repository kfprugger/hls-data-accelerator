using Microsoft.Extensions.Logging;
using Microsoft.IntegratedDataPlatform.ExportProcessor;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Services;

namespace Tests.Helper
{
    /// <summary>
    /// Test wrapper for Export that exposes the protected State property.
    /// TaskEntity&lt;TState&gt;.State is protected, so tests need this subclass to set/get state.
    /// </summary>
    public class TestableExport : Export
    {
        public TestableExport(FHIRServerService fhirServer, ILogger<Export> logger) : base(fhirServer, logger) { }

        public EntityState TestState
        {
            get => State!;
            set => State = value;
        }
    }
}
