using System;
using System.Collections.Generic;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Models
{
    /// <summary>
    /// Input for the EntitiesToTriggerExport sub-orchestrator.
    /// Replaces ValueTuple which does not serialize reliably across the isolated worker gRPC boundary.
    /// </summary>
    public class EntitiesToTriggerExportInput
    {
        public List<string> Entities { get; set; }
        public string RunId { get; set; }
        public string CorrelationId { get; set; }
    }

    /// <summary>
    /// Output for the EntitiesToTriggerExport sub-orchestrator.
    /// </summary>
    public class EntitiesToTriggerExportOutput
    {
        public List<ExportEntity> EntitiesToTakeAction { get; set; }
        public List<ExportOrchestrationStatus> SuccessEntityStates { get; set; }
    }

    /// <summary>
    /// Input for the TakeActionOnEntity sub-orchestrator and Export.TakeAction entity method.
    /// </summary>
    public class TakeActionOnEntityInput
    {
        public ExportEntity Entity { get; set; }
        public string RunId { get; set; }
        public string CorrelationId { get; set; }
    }

    /// <summary>
    /// Input for the GenerateEntityKey sub-orchestrator.
    /// </summary>
    public class GenerateEntityKeyInput
    {
        public string Entity { get; set; }
        public string RunId { get; set; }
        public string CorrelationId { get; set; }
    }

    /// <summary>
    /// Input for the ResourceManager.UpdateResources entity method.
    /// </summary>
    public class UpdateResourcesInput
    {
        public string ResourceString { get; set; }
        public DateTime? End { get; set; }
    }
}
