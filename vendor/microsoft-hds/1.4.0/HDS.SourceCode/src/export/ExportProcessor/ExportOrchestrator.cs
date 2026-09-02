using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Entities;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Helper;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Services;
using Newtonsoft.Json;
using Azure.Storage.Blobs;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor
{
    /// <summary>
    /// Orchestrates FHIR bulk data export operations using Durable Functions.
    /// Contains the HTTP trigger entry point, main orchestrator, and sub-orchestrators
    /// for entity-level export management.
    /// 
    /// Migrated to .NET 8 isolated worker model:
    /// - Uses TaskOrchestrationContext (replaces IDurableOrchestrationContext)
    /// - Uses DurableTaskClient (replaces IDurableClient)
    /// - Entity operations go through context.Entities.CallEntityAsync (replaces entity proxies)
    /// - Retry via TaskOptions.FromRetryPolicy (replaces RetryOptions)
    /// </summary>
    public class ExportOrchestrator
    {

        private readonly IOptions<ExportProcessorSettings> _settings;
        private readonly ILogger<ExportOrchestrator> _logger;
        private readonly FHIRServerService _fhirServerService;
        private readonly BlobServiceClient _blobServiceClient;

        public ExportOrchestrator(IOptions<ExportProcessorSettings> settings, ILogger<ExportOrchestrator> logger, FHIRServerService fhirService, BlobServiceClient blobServiceClient)
        {
            _settings = settings;
            _logger = logger;
            _fhirServerService = fhirService;
            _blobServiceClient = blobServiceClient;
        }

        /// <summary>
        /// HTTP Trigger to trigger an orchestration export
        /// Creates a Singleton background job orchestration
        /// </summary>
        /// <param name="req"></param>
        /// <param name="orchestrationClient"></param>
        /// <returns></returns>
        [Function(nameof(Run_Export))]
        public async Task<HttpResponseData> Run_Export(
            [HttpTrigger(AuthorizationLevel.Function, "get", Route = "Run_Export/{run_id}")] HttpRequestData req, string run_id, [DurableClient] DurableTaskClient client)
        {
            var instanceId = Constants.ExportJobInstanceId;
            var runId = run_id;
            // Check if an instance with the specified ID already exists or an existing one stopped running(completed/failed/terminated).            
            var existingInstance = await client.GetInstanceAsync($"{instanceId}");
            if (existingInstance == null
            || existingInstance.RuntimeStatus == OrchestrationRuntimeStatus.Completed
            || existingInstance.RuntimeStatus == OrchestrationRuntimeStatus.Failed
            || existingInstance.RuntimeStatus == OrchestrationRuntimeStatus.Terminated)
            {
                // An instance with the specified ID doesn't exist or an existing one stopped running, create one.
                await client.ScheduleNewOrchestrationInstanceAsync(nameof(Orchestrate_Export), runId, new StartOrchestrationOptions { InstanceId = instanceId });

                return client.CreateCheckStatusResponse(req, instanceId);
            }
            else
            {
                // An instance with the specified ID exists or an existing one still running, don't create one.
                var response = req.CreateResponse(HttpStatusCode.Conflict);
                await response.WriteStringAsync($"An instance with ID '{instanceId}' already exists.");
                return response;
            }
        }

        /// <summary>
        /// Orchestrates the export of all configured entities
        /// </summary>
        /// <param name="context"></param>
        /// <returns></returns>
        [Function(nameof(Orchestrate_Export))]
        public async Task<string> Orchestrate_Export(
            [OrchestrationTrigger] TaskOrchestrationContext context)
        {
            var correlationId = context.NewGuid().ToString();
            var runId = context.GetInput<string>();
            var loggingObject = new LoggingMetadata()
            {
                CorrelationId = correlationId,
                RunId = runId
            };
            var replaySafeLogger = context.CreateReplaySafeLogger<ExportOrchestrator>();

            replaySafeLogger.LogInformationEx("Started Export Orchestration", loggingObject);
            var taskOptions = TaskOptions.FromRetryPolicy(new RetryPolicy(
                maxNumberOfAttempts: _settings.Value.RetryCount,
                firstRetryInterval: TimeSpan.FromSeconds(5)
                ));

            // 1. Figure out if batch or parallel
            bool isBatchMode = await context.CallActivityAsync<bool>(nameof(IsBatchMode), correlationId, taskOptions);
            var entities = isBatchMode ? new List<string>() { _settings.Value.Resources } : _settings.Value.Resources.Split(",").ToList();
            replaySafeLogger.LogInformationEx(isBatchMode ? "Export is running in batch mode" : "Export is running in parallel mode", loggingObject);

            //2. Get Entities to Export based on State
            var entitiesToTriggerInput = new EntitiesToTriggerExportInput { Entities = entities, RunId = runId, CorrelationId = correlationId };
            var entitiesToTriggerOutput = await context.CallSubOrchestratorAsync<EntitiesToTriggerExportOutput>(nameof(EntitiesToTriggerExport), entitiesToTriggerInput, taskOptions);
            var entitiesToTakeAction = entitiesToTriggerOutput.EntitiesToTakeAction;
            var successEntityStates = entitiesToTriggerOutput.SuccessEntityStates;
            replaySafeLogger.LogInformationEx($"Taking action on {entitiesToTakeAction.Count} entities", loggingObject);

            //3. Orchestrate Export
            var exportEntityTasks = new List<Task<ExportOrchestrationStatus>>();
            foreach (ExportEntity entity in entitiesToTakeAction)
            {
                var exportEntityTask = context.CallSubOrchestratorAsync<ExportOrchestrationStatus>(nameof(TakeActionOnEntity), new TakeActionOnEntityInput { Entity = entity, RunId = runId, CorrelationId = correlationId }, taskOptions);
                exportEntityTasks.Add(exportEntityTask);
            }
            successEntityStates.AddRange(await Task.WhenAll(exportEntityTasks));
            replaySafeLogger.LogInformationEx($"Successfuly completed taking action on {entitiesToTakeAction.Count} entities ", loggingObject);

            if (successEntityStates?.Count > 0 && successEntityStates.Any(successEntity => successEntity.ExportStatus == ExportStatus.Succeeded && successEntity.Output?.Count > 0))
            {
                replaySafeLogger.LogInformationEx($"Export successfully completed.", loggingObject);
                return $"{Constants.SuccessfulExport}";
            }
            else
            {
                replaySafeLogger.LogInformationEx($"No resources were exported by any of the entities.", loggingObject);
                return $"{Constants.SuccessfulExportWithNoOutput}";
            }

        }

        /// <summary>
        /// Uses the metadata of the FHIR Server to determine if the server can handle export in batch
        /// </summary>
        /// <param name="correlationId"></param>
        /// <returns>
        /// true: server can handle exporting multiple entities in batch in a performant way
        /// </returns>
        [Function(nameof(IsBatchMode))]
        public async Task<bool> IsBatchMode([ActivityTrigger] string correlationId)
        {
            try
            {
                var capabilityStatement = await _fhirServerService.GetMetadata();
                if (FHIRServerNames.AzureHealthcareAPIs.Equals(capabilityStatement?.Software?.Name, StringComparison.OrdinalIgnoreCase)) return true;
                return false;
            }
            catch (Exception ex)
            {
                // Have to catch and throw a generic exception.
                // Otherwise the parent orchestration function fails to get the exception with details.
                throw new Exception(ex.Message, ex);
            }
        }

        /// <summary>
        /// Generates an entity key for an entity. 
        /// Uses external orchestrations - https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-eternal-orchestrations?tabs=csharp
        /// </summary>
        /// <param name="context"></param>
        /// <returns>
        /// An Entity key for a given entity resource type
        /// </returns>
        [Function(nameof(GenerateEntityKey))]
        public async Task<string> GenerateEntityKey([OrchestrationTrigger] TaskOrchestrationContext context)
        {
            var input = context.GetInput<GenerateEntityKeyInput>();
            var loggingObject = new LoggingMetadata()
            {
                RunId = input.RunId,
                CorrelationId = input.CorrelationId,
                Entity = input.Entity
            };

            var entityId = new EntityInstanceId(nameof(EntityKeyManager), Constants.EntityKeyManagerId);
            var result = await context.Entities.CallEntityAsync<string>(entityId, nameof(IEntityKeyManager.GenerateEntityKey), input.Entity);

            var replaySafeLogger = context.CreateReplaySafeLogger<ExportOrchestrator>();
            replaySafeLogger.LogInformationEx($"Generating Entity Key for {input.Entity} entity. Retrieved Key: {result}", loggingObject);
            return result;
        }

        /// <summary>
        /// Orchestrates an export of each entity. 
        /// Uses external orchestrations - https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-eternal-orchestrations?tabs=csharp
        /// </summary>
        /// <param name="context"></param>
        /// <returns></returns>
        /// <exception cref="ExportFailedException"></exception>
        [Function(nameof(TakeActionOnEntity))]
        public async Task<ExportOrchestrationStatus> TakeActionOnEntity(
    [OrchestrationTrigger] TaskOrchestrationContext context)
        {
            try
            {
                var input = context.GetInput<TakeActionOnEntityInput>();
                var loggingObject = new LoggingMetadata()
                {
                    RunId = input.RunId,
                    CorrelationId = input.CorrelationId,
                    Entity = input.Entity.ResourceType
                };
                var taskOptions = TaskOptions.FromRetryPolicy(new RetryPolicy(
                    maxNumberOfAttempts: _settings.Value.RetryCount,
                    firstRetryInterval: TimeSpan.FromSeconds(5)
                ));

                var replaySafeLogger = context.CreateReplaySafeLogger<ExportOrchestrator>();
                replaySafeLogger.LogInformationEx($"Taking action on {input.Entity.ResourceType} entity starting from time: {input.Entity.Start}.", loggingObject);

                var entityKey = await context.CallSubOrchestratorAsync<string>(nameof(GenerateEntityKey), new GenerateEntityKeyInput { Entity = input.Entity.ResourceType, RunId = input.RunId, CorrelationId = input.CorrelationId }, taskOptions);
                var entityId = new EntityInstanceId(nameof(Export), entityKey);
                var result = await context.Entities.CallEntityAsync<ExportOrchestrationStatus>(entityId, nameof(IExport.TakeAction), new TakeActionOnEntityInput { Entity = input.Entity, RunId = input.RunId, CorrelationId = input.CorrelationId });

                if (result.ExportStatus == ExportStatus.Updating)
                {
                    replaySafeLogger.LogInformationEx($"{input.Entity.ResourceType} entity is in {result.ExportStatus} state. Updating ResourceManager.", loggingObject);
                    var resourceEntityId = new EntityInstanceId(nameof(ResourceManager), Constants.ResourceManagerId);
                    await context.Entities.CallEntityAsync(resourceEntityId, "UpdateResources", new UpdateResourcesInput { ResourceString = input.Entity.ResourceType, End = result.End });
                    await context.Entities.CallEntityAsync(entityId, "CompleteExport");
                    result.ExportStatus = ExportStatus.Succeeded;
                }

                if (result.ExportStatus == ExportStatus.InProgress)
                {
                    replaySafeLogger.LogInformationEx($"{input.Entity.ResourceType} entity is in {result.ExportStatus} state. Will poll after {Constants.PollAfterInSeconds} seconds.", loggingObject);
                    // sleep before polling again
                    DateTime nextPoll = context.CurrentUtcDateTime.AddSeconds(Constants.PollAfterInSeconds);
                    await context.CreateTimer(nextPoll, CancellationToken.None);
                    context.ContinueAsNew(input);
                }

                // This should never be true. Export Entity should throw an error for any failed state.
                // Worst case this will throw an error so that orchestrator can retry.
                if (result.ExportStatus == ExportStatus.Failed)
                {
                    var ex = new ExportFailedException($"Export Failed for entity: {input.Entity.ResourceType}");
                    replaySafeLogger.LogErrorEx(loggingObject, ex);
                    throw ex;
                }

                replaySafeLogger.LogInformationEx($"{input.Entity.ResourceType} entity completed successfully.", loggingObject);
                return result;
            }
            catch (Exception ex)
            {
                // Have to catch and throw a generic exception.
                // Otherwise the parent orchestration function fails to get the exception with details.
                throw new Exception(ex.Message, ex);
            }
        }

        /// <summary>
        /// Loops through list of entities, retrieves the entity state
        /// If no export entities are in error state, return the list of all entities
        /// Otherwise, return a list of entities in error and null state
        /// </summary>
        /// <param name="context"></param>
        /// <returns>
        /// A list of entities to be exported
        /// A list of ExportOrchestrationStatus of entities in success state in case any entities are in error state
        /// </returns>

        [Function(nameof(EntitiesToTriggerExport))]
        public async Task<EntitiesToTriggerExportOutput> EntitiesToTriggerExport(
    [OrchestrationTrigger] TaskOrchestrationContext context)
        {
            try
            {
                var input = context.GetInput<EntitiesToTriggerExportInput>();
                var loggingObject = new LoggingMetadata()
                {
                    RunId = input.RunId,
                    CorrelationId = input.CorrelationId,
                };
                var taskOptions = TaskOptions.FromRetryPolicy(new RetryPolicy(
                    maxNumberOfAttempts: _settings.Value.RetryCount,
                    firstRetryInterval: TimeSpan.FromSeconds(5)
                ));

                var replaySafeLogger = context.CreateReplaySafeLogger<ExportOrchestrator>();
                replaySafeLogger.LogInformationEx("Calculating entities on which to trigger export", loggingObject);

                var unsuccessfulEntities = new List<ExportEntity>();
                var successEntities = new List<ExportEntity>();
                var successOutputs = new List<ExportOrchestrationStatus>();

                var resourceEntityId = new EntityInstanceId(nameof(ResourceManager), Constants.ResourceManagerId);

                List<ExportEntity> exportEntities = new List<ExportEntity>();
                List<Task<List<ExportEntity>>> getExportEntitiesTasks = new List<Task<List<ExportEntity>>>();
                foreach (var entity in input.Entities)
                {
                    getExportEntitiesTasks.Add(context.Entities.CallEntityAsync<List<ExportEntity>>(resourceEntityId, "GetExportEntities", entity));
                }
                var getExportEntitiesTasksResult = await Task.WhenAll(getExportEntitiesTasks);
                exportEntities.AddRange(getExportEntitiesTasksResult.SelectMany(list => list));

                foreach (ExportEntity exportEntity in exportEntities)
                {
                    var resourceType = exportEntity.ResourceType;
                    var entityKey = await context.CallSubOrchestratorAsync<string>(nameof(GenerateEntityKey), new GenerateEntityKeyInput { Entity = resourceType, RunId = input.RunId, CorrelationId = input.CorrelationId }, taskOptions);
                    var entityId = new EntityInstanceId(nameof(Export), entityKey);
                    var stateResponse = await context.Entities.CallEntityAsync<EntityState>(entityId, "GetEntityState");

                    replaySafeLogger.LogInformationEx($"{resourceType} Entity is in {stateResponse.Status} state", loggingObject);
                    if (stateResponse.Status == null)
                    {
                        continue;
                    }
                    else if (stateResponse.Status == ExportStatus.Failed || stateResponse.Status == ExportStatus.InProgress || stateResponse.Status == ExportStatus.Updating)
                    {
                        unsuccessfulEntities.Add(exportEntity);
                    }
                    else if (stateResponse.Status == ExportStatus.Succeeded)
                    {
                        successEntities.Add(exportEntity);
                        successOutputs.Add(new ExportOrchestrationStatus()
                        {
                            End = stateResponse.End,
                            Output = stateResponse.SuccessOutput
                        });
                    }
                    else
                    {
                        throw new InvalidExportEntityStateException($"Filtering entities to trigger export on. Entity Key: {entityId.Key} is in {stateResponse.Status} state.");
                    }
                }
                if (unsuccessfulEntities.Any())
                {
                    replaySafeLogger.LogInformationEx($"{unsuccessfulEntities} entities are in error/inprogress/updating state. Triggering export on only entities in error, inprogress, updating or null state.", loggingObject);
                    return new EntitiesToTriggerExportOutput
                    {
                        EntitiesToTakeAction = exportEntities.Where(resource => successEntities.All(successEntity => successEntity.ResourceType != resource.ResourceType)).ToList(),
                        SuccessEntityStates = successOutputs
                    };
                }
                else
                {
                    replaySafeLogger.LogInformationEx($"0 entities are in error/inprogress state. Triggering export on all entities.", loggingObject);
                    return new EntitiesToTriggerExportOutput
                    {
                        EntitiesToTakeAction = exportEntities,
                        SuccessEntityStates = new List<ExportOrchestrationStatus>()
                    };
                }
            }
            catch (Exception ex)
            {
                // Have to catch and throw a generic exception.
                // Otherwise the parent orchestration function fails to get the exception with details.
                throw new Exception(ex.Message, ex);
            }
        }
    }
}
