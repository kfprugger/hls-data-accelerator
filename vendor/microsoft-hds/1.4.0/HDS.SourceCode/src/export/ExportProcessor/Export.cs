using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask.Entities;
using Microsoft.Extensions.Logging;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Helper;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Services;
using Newtonsoft.Json;
using Stj = System.Text.Json;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor
{

    /// <summary>
    /// Durable entity representing a single FHIR export operation.
    /// Extends TaskEntity&lt;EntityState&gt; for the .NET 8 isolated worker durable entity model.
    /// Tracks export status lifecycle: null → InProgress → Updating → Succeeded/Failed.
    /// </summary>
    public class Export : TaskEntity<EntityState>, IExport
    {

        private readonly FHIRServerService _fHIRServerService;
        private readonly ILogger<Export> _logger;
        private LoggingMetadata _loggingObject = new LoggingMetadata();

        public EntityState GetEntityState()
        {
            State ??= new EntityState();
            State.Normalize();
            return State;
        }

        public Export(FHIRServerService fhirServer, ILogger<Export> logger)
        {
            _fHIRServerService = fhirServer;
            _logger = logger;
        }

        public void CompleteExport()
        {
            State ??= new EntityState();
            State.Normalize();
            _logger.LogInformationEx("Export Succeeded.", _loggingObject);
            State.Status = ExportStatus.Succeeded;
        }

        /// <summary>
        /// Main entry point for the export entity. Determines action based on current state:
        /// - Succeeded/Failed/null: Trigger a new export
        /// - InProgress: Poll the FHIR server for export completion
        /// - Updating: Wait for ResourceManager update
        /// </summary>
        public async Task<ExportOrchestrationStatus> TakeAction(TakeActionOnEntityInput input)
        {
            State ??= new EntityState(); // State may be null on first entity invocation
            State.Normalize(); // Migrate legacy .NET 6 in-process wrapped state on in-place upgrade
            string resourceType = input.Entity.ResourceType;
            _loggingObject = new LoggingMetadata()
            {
                RunId = input.RunId,
                CorrelationId = input.CorrelationId,
                Entity = resourceType
            };

            State.ResourceType = resourceType;
            _logger.LogInformationEx($"Taking action on {resourceType} entity.", _loggingObject);
            var result = new ExportOrchestrationStatus();
            try
            {
                switch (State.Status)
                {
                    case ExportStatus.Updating:
                        _logger.LogInformationEx($"{resourceType} entity is in {State.Status}. Awaiting ResourceManager Update.", _loggingObject);
                        break;
                    case ExportStatus.InProgress:
                        _logger.LogInformationEx($"{resourceType} entity is in {State.Status}. Polling for progress.", _loggingObject);
                        await PollInProgress();
                        break;
                    case ExportStatus.Succeeded:
                    case ExportStatus.Failed:
                    default:
                        _logger.LogInformationEx($"{resourceType} entity is in {State.Status}. Triggering new export.", _loggingObject);
                        await TriggerExport(input.Entity.Start);
                        break;
                }
            }
            catch (Exception ex)
            {
                _logger.LogErrorEx(_loggingObject, ex);
                State.Status = ExportStatus.Failed;
                // Have to catch and throw a generic exception.
                // Otherwise the parent orchestration function fails to get the exception with details.                
                throw new Exception(ex.Message, ex);
            }

            result.ExportStatus = State.Status;
            result.Output = State.SuccessOutput;
            result.End = State.End;
            return result;
        }

        /// <summary>
        /// Triggers a new export on the fhir server for the given resource
        /// </summary>
        /// <param name="start">The time to start the export from</param>
        /// <returns></returns>
        private async Task TriggerExport(DateTime? start)
        {
            try
            {
                State.End = null;
                State.SuccessOutput = null;

                var startString = Utility.ParseStringFromDate(start);

                var responseMessage = await _fHIRServerService.TriggerExport(State.ResourceType, startString);
                if (responseMessage.IsSuccessStatusCode
                    && responseMessage.Content.Headers.TryGetValues(HTTPHeadersExtensions.ContentLocation, out var contentLocations))
                {
                    var contentLocation = contentLocations.FirstOrDefault();

                    State.ContentLocation = new Uri(contentLocation);
                    State.Status = ExportStatus.InProgress;
                    _logger.LogInformationEx("Successfully triggered export", _loggingObject);
                }
                else
                {
                    State.Status = ExportStatus.Failed;
                    if (!responseMessage.IsSuccessStatusCode)
                    {
                        using (var stream = await responseMessage.Content.ReadAsStreamAsync())
                        {
                            var ex = new HttpRequestException($"Failed to trigger export. Status : {responseMessage.StatusCode} message: {new StreamReader(stream).ReadToEnd()}");
                            _logger.LogErrorEx(_loggingObject, ex);
                            throw ex;
                        }
                    }
                    else
                    {
                        var ex = new ContentLocationMissingException("Failed to trigger export. Export resonse is missing Content-Location");
                        _logger.LogErrorEx(_loggingObject, ex);
                        throw ex;
                    }
                }
            }
            catch (Exception ex)
            {
                State.Status = ExportStatus.Failed;
                _logger.LogErrorEx(_loggingObject, ex);
                throw;
            }
        }

        /// <summary>
        /// Calls the FHIR Server for export job status
        /// </summary>
        /// <returns></returns>
        private async Task PollInProgress()
        {

            try
            {
                var responseMessage = await _fHIRServerService.PollContentLocation(State.ContentLocation);

                using (var stream = await responseMessage.Content.ReadAsStreamAsync())
                {

                    if (responseMessage.StatusCode == HttpStatusCode.Accepted)
                    {
                        _logger.LogInformationEx($"Polled export status. Status is : {State.Status}", _loggingObject);
                        return;
                    }

                    if (responseMessage.IsSuccessStatusCode)
                    {
                        var exportResponse = Utility.DeserializeJsonFromStream<ExportResponseMessage>(stream);

                        if ((exportResponse?.Error?.Any() ?? false)
                            || (exportResponse?.Issues?.Where(issue => issue.Severity != IssueSeverity.Information)?.Any() ?? false))
                        {
                            State.Status = ExportStatus.Failed;
                            var ex = new ExportPartialSuccessException($"Export failed with errors and/or Issues. Errors: {JsonConvert.SerializeObject(exportResponse.Error)} Issues: {JsonConvert.SerializeObject(exportResponse.Issues)}");
                            _logger.LogErrorEx(_loggingObject, ex);
                            throw ex;
                        }
                        else
                        {
                            State.Status = ExportStatus.Updating;
                            State.End = exportResponse.TransactionTime;
                            _logger.LogInformationEx("Export Completed. Currently in Updating State pending Resource Manager Updates", _loggingObject);
                            State.SuccessOutput = exportResponse.Output;
                        }
                    }
                    else
                    {
                        State.Status = ExportStatus.Failed;
                        var ex = new HttpRequestException($"Export Failed. Status : {responseMessage.StatusCode} message: {new StreamReader(stream).ReadToEnd()}");
                        _logger.LogErrorEx(_loggingObject, ex);
                        throw ex;
                    }
                }
            }
            catch (Exception ex)
            {
                State.Status = ExportStatus.Failed;
                _logger.LogErrorEx(_loggingObject, ex);
                throw;
            }

        }

        /// <summary>
        /// Entity trigger dispatch function for the isolated worker model.
        /// Routes incoming entity operations to the Export instance methods.
        /// </summary>
        [Function(nameof(Export))]
        public static Task RunEntityDispatcher([EntityTrigger] TaskEntityDispatcher dispatcher)
        {
            return dispatcher.DispatchAsync<Export>();
        }
    }

    [Stj.Serialization.JsonConverter(typeof(EntityStateJsonConverter))]
    public class EntityState
    {
        public DateTime? End { get; set; }

        public ExportStatus? Status { get; set; }

        public string ResourceType { get; set; }

        public Uri ContentLocation { get; set; }

        public List<Output> SuccessOutput { get; set; }

        /// <summary>
        /// Legacy .NET 6 in-process wrapped state is migrated up-front by <see cref="EntityStateJsonConverter"/>
        /// during deserialization. Retained as an idempotent no-op hook so call sites stay serializer-agnostic.
        /// </summary>
        public void Normalize()
        {
        }
    }

    /// <summary>
    /// Reads both the modern isolated shape (top-level "End"/"Status"/... ) and the legacy .NET 6 in-process
    /// shape ({ "entityState": { "since", "till", ... } }), and always writes the modern shape. The legacy
    /// "till" (last successful transaction time) maps to the new "End"; legacy "since" is dropped because the
    /// next export start time now comes from the ResourceManager entity. Reads are case-insensitive so the
    /// legacy camelCase payload binds too.
    /// </summary>
    public class EntityStateJsonConverter : Stj.Serialization.JsonConverter<EntityState>
    {
        // Case-insensitive so the legacy camelCase payload ("till"/"status"/"resourceType"/...) binds as well as
        // the modern PascalCase. Reused across calls (JsonSerializerOptions is immutable/thread-safe after first
        // use). Equivalent to the runtime options under the current bare ConfigureFunctionsWorkerDefaults() setup.
        private static readonly Stj.JsonSerializerOptions CaseInsensitive = new Stj.JsonSerializerOptions { PropertyNameCaseInsensitive = true };

        public override EntityState Read(ref Stj.Utf8JsonReader reader, Type typeToConvert, Stj.JsonSerializerOptions options)
        {
            var state = new EntityState();
            using Stj.JsonDocument doc = Stj.JsonDocument.ParseValue(ref reader);
            Stj.JsonElement root = doc.RootElement;

            // Legacy in-process payload wraps the state under "entityState".
            Stj.JsonElement src = root;
            if (EntityStateJson.TryGetProperty(root, "entityState", out Stj.JsonElement wrapper)
                && wrapper.ValueKind == Stj.JsonValueKind.Object)
            {
                src = wrapper;
            }

            // Modern "End"; fall back to legacy "till".
            if (TryGetValue(src, "end", out Stj.JsonElement endEl))
            {
                state.End = Stj.JsonSerializer.Deserialize<DateTime?>(endEl, CaseInsensitive);
            }
            else if (TryGetValue(src, "till", out Stj.JsonElement tillEl))
            {
                state.End = Stj.JsonSerializer.Deserialize<DateTime?>(tillEl, CaseInsensitive);
            }

            if (TryGetValue(src, "status", out Stj.JsonElement statusEl))
            {
                state.Status = Stj.JsonSerializer.Deserialize<ExportStatus?>(statusEl, CaseInsensitive);
            }

            if (TryGetValue(src, "resourceType", out Stj.JsonElement rtEl))
            {
                state.ResourceType = rtEl.GetString();
            }

            if (TryGetValue(src, "contentLocation", out Stj.JsonElement clEl))
            {
                state.ContentLocation = Stj.JsonSerializer.Deserialize<Uri>(clEl, CaseInsensitive);
            }

            if (TryGetValue(src, "successOutput", out Stj.JsonElement soEl))
            {
                state.SuccessOutput = Stj.JsonSerializer.Deserialize<List<Output>>(soEl, CaseInsensitive);
            }

            state.Normalize();
            return state;
        }

        public override void Write(Stj.Utf8JsonWriter writer, EntityState value, Stj.JsonSerializerOptions options)
        {
            writer.WriteStartObject();
            writer.WritePropertyName("End");
            Stj.JsonSerializer.Serialize(writer, value.End, options);
            writer.WritePropertyName("Status");
            Stj.JsonSerializer.Serialize(writer, value.Status, options);
            writer.WritePropertyName("ResourceType");
            Stj.JsonSerializer.Serialize(writer, value.ResourceType, options);
            writer.WritePropertyName("ContentLocation");
            Stj.JsonSerializer.Serialize(writer, value.ContentLocation, options);
            writer.WritePropertyName("SuccessOutput");
            Stj.JsonSerializer.Serialize(writer, value.SuccessOutput, options);
            writer.WriteEndObject();
        }

        private static bool TryGetValue(Stj.JsonElement obj, string name, out Stj.JsonElement value)
        {
            return EntityStateJson.TryGetProperty(obj, name, out value) && value.ValueKind != Stj.JsonValueKind.Null;
        }
    }

}