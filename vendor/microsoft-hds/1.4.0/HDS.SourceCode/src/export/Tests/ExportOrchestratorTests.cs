using Azure.Storage.Blobs;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Entities;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.IntegratedDataPlatform.ExportProcessor;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Helper;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Services;
using Moq;
using Tests.Helper;
using Xunit;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces;

namespace Tests
{
    public class ExportOrchestratorTests
    {
        public ExportOrchestrator ExportOrchestrator;
        public DateTime CurrentDateTime;
        public ExportOrchestratorTests()
        {
            var handlerMock = new Mock<HttpMessageHandler>(MockBehavior.Strict);
            var client = new HttpClient(handlerMock.Object);
            var fhirServerSettings = new Mock<IFHIRServerSettings>();
            var fhirServiceMock = new Mock<FHIRServerService>(client, fhirServerSettings.Object);
            CurrentDateTime = DateTime.Parse(TestConstants.Since);

            var exportProcessorSettings = Options.Create(new ExportProcessorSettings()
            {
                Resources = "Patient,Encounter",
                DataStart = CurrentDateTime,
                RetryCount = 3
            });

            var logger = new LoggerFactory().CreateLogger<ExportOrchestrator>();
            var blobServiceClientMock = new Mock<BlobServiceClient>();
            ExportOrchestrator = new ExportOrchestrator(exportProcessorSettings, logger, fhirServiceMock.Object, blobServiceClientMock.Object);
        }

        [Fact]
        public async Task Run_ExportOrchestration_VerifySuccessfulExportWithNoOutput()
        {
            var exportEntities = new List<ExportEntity>() {
                new ExportEntity() {Start = CurrentDateTime, ResourceType = "Patient,Encounter"}
            };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            mockContext.Setup(x => x.NewGuid()).Returns(TestConstants.MockGuid);
            mockContext.Setup(x => x.CallActivityAsync<bool>("IsBatchMode", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync(true);
            mockContext.Setup(x => x.CallSubOrchestratorAsync<EntitiesToTriggerExportOutput>("EntitiesToTriggerExport", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync(new EntitiesToTriggerExportOutput { EntitiesToTakeAction = exportEntities, SuccessEntityStates = new List<ExportOrchestrationStatus>() });
            mockContext.Setup(x => x.CallSubOrchestratorAsync<ExportOrchestrationStatus>("TakeActionOnEntity", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync(new ExportOrchestrationStatus());

            var result = await ExportOrchestrator.Orchestrate_Export(mockContext.Object);
            Assert.Equal(Constants.SuccessfulExportWithNoOutput, result);

        }

        [Fact]
        public async Task Run_ExportOrchestration_VerifySuccessfulExportWithOutput()
        {
            var exportEntities = new List<ExportEntity>(){
                new ExportEntity() { Start = CurrentDateTime, ResourceType = "Patient"},
                new ExportEntity() { Start = CurrentDateTime, ResourceType = "Encounter" }
            };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            mockContext.Setup(x => x.NewGuid()).Returns(TestConstants.MockGuid);
            mockContext.Setup(x => x.CallActivityAsync<bool>("IsBatchMode", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync(false);
            mockContext.Setup(x => x.CallSubOrchestratorAsync<EntitiesToTriggerExportOutput>("EntitiesToTriggerExport", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync(new EntitiesToTriggerExportOutput { EntitiesToTakeAction = exportEntities, SuccessEntityStates = new List<ExportOrchestrationStatus>() });
            mockContext.Setup(x => x.CallSubOrchestratorAsync<ExportOrchestrationStatus>("TakeActionOnEntity", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync(new ExportOrchestrationStatus() { ExportStatus = ExportStatus.Succeeded, Output = new List<Output>() { new Output() { Count = 10 } } });

            var result = await ExportOrchestrator.Orchestrate_Export(mockContext.Object);
        }

        [Fact]
        public async Task Run_ExportOrchestration_VerifyExportWithExceptions()
        {
            var exportEntities = new List<ExportEntity>() {
                new ExportEntity() {Start = CurrentDateTime, ResourceType = "Patient,Encounter"}
            };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            mockContext.Setup(x => x.NewGuid()).Returns(TestConstants.MockGuid);
            mockContext.Setup(x => x.CallActivityAsync<bool>("IsBatchMode", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync(true);
            mockContext.Setup(x => x.CallSubOrchestratorAsync<EntitiesToTriggerExportOutput>("EntitiesToTriggerExport", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync(new EntitiesToTriggerExportOutput { EntitiesToTakeAction = exportEntities, SuccessEntityStates = new List<ExportOrchestrationStatus>() });
           
            mockContext.Setup(x => x.CallSubOrchestratorAsync<ExportOrchestrationStatus>("TakeActionOnEntity", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync((TaskName functionName, object? inputObj, TaskOptions? options) =>
            {
                var entityName = (TakeActionOnEntityInput)inputObj!;
                if (entityName.Entity.ResourceType.Contains("Encounter"))
                {
                    throw new ExportFailedException("Export Failed.");
                }

                return new ExportOrchestrationStatus() { ExportStatus = ExportStatus.Succeeded, Output = new List<Output>() { new Output() { Count = 10 } } };

            });
            await Assert.ThrowsAsync<ExportFailedException>(() => ExportOrchestrator.Orchestrate_Export(mockContext.Object));
        }


        [Fact]
        public async Task Run_ExportOrchestration_EntitiesToTriggerExport_VerifyAllSuccessStates()
        {
            var resourcesToExport = new List<string>() { "Patient", "Encounter" };
            var exportEntities = new List<ExportEntity>() { 
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Patient" },
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Encounter" } 
            };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            mockContext.Setup(x => x.GetInput<EntitiesToTriggerExportInput>()).Returns(new EntitiesToTriggerExportInput { Entities = resourcesToExport, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.MockGuid.ToString() });
            mockEntities.Setup(x => x.CallEntityAsync<EntityState>(It.IsAny<EntityInstanceId>(), "GetEntityState", null, null)).ReturnsAsync(new EntityState()
            {

            });

            var result1 = await ExportOrchestrator.EntitiesToTriggerExport(mockContext.Object);
            var observedResourcesToExport = result1.EntitiesToTakeAction;
            var observedOrchestrationState = result1.SuccessEntityStates;
            Assert.Equal(exportEntities.Count, observedResourcesToExport.Count);
            Assert.Empty(observedOrchestrationState);
        }

        [Fact]
        public async Task Run_ExportOrchestration_EntitiesToTriggerExport_VerifyAllNullStates()
        {
            var resourcesToExport = new List<string>() { "Patient", "Encounter" };
            var exportEntities = new List<ExportEntity>() {
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Patient" },
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Encounter" }
            };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            mockContext.Setup(x => x.GetInput<EntitiesToTriggerExportInput>()).Returns(new EntitiesToTriggerExportInput { Entities = resourcesToExport, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.MockGuid.ToString() });
            mockEntities.Setup(x => x.CallEntityAsync<EntityState>(It.IsAny<EntityInstanceId>(), "GetEntityState", null, null)).ReturnsAsync(new EntityState()
            { });

            var result1 = await ExportOrchestrator.EntitiesToTriggerExport(mockContext.Object);
            var observedResourcesToExport = result1.EntitiesToTakeAction;
            var observedOrchestrationState = result1.SuccessEntityStates;
            Assert.Equal(exportEntities.Count, observedResourcesToExport.Count);
            Assert.Empty(observedOrchestrationState);
        }


        [Fact]
        public async Task Run_ExportOrchestration_EntitiesToTriggerExport_VerifyAllErrorStates()
        {
            var resourcesToExport = new List<string>() { "Patient", "Encounter" };
            var exportEntities = new List<ExportEntity>() {
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Patient" },
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Encounter" }
            };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            mockContext.Setup(x => x.GetInput<EntitiesToTriggerExportInput>()).Returns(new EntitiesToTriggerExportInput { Entities = resourcesToExport, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.MockGuid.ToString() });
            mockEntities.Setup(x => x.CallEntityAsync<EntityState>(It.IsAny<EntityInstanceId>(), "GetEntityState", null, null)).ReturnsAsync(new EntityState()
            {
                Status = ExportStatus.Failed
            });

            var result1 = await ExportOrchestrator.EntitiesToTriggerExport(mockContext.Object);
            var observedResourcesToExport = result1.EntitiesToTakeAction;
            var observedOrchestrationState = result1.SuccessEntityStates;
            Assert.Equal(exportEntities.Count, observedResourcesToExport.Count);
            Assert.Empty(observedOrchestrationState);
        }

        [Fact]
        public async Task Run_ExportOrchestration_EntitiesToTriggerExport_VerifyPartialErrorStates()
        {
            var resourcesToExport = new List<string>() { "Patient", "Encounter" };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            var expectedExportEntities = new List<ExportEntity>() {
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Patient" },
            };
            mockContext.Setup(x => x.GetInput<EntitiesToTriggerExportInput>()).Returns(new EntitiesToTriggerExportInput { Entities = resourcesToExport, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.MockGuid.ToString() });
            mockEntities.Setup(x => x.CallEntityAsync<EntityState>(It.IsAny<EntityInstanceId>(), "GetEntityState", null, null)).ReturnsAsync((EntityInstanceId entityId, string name, object? input, CallEntityOptions? opts) =>
            {
                if (entityId.Key.Equals(TestConstants.PatientGuidKey))
                {
                    return new EntityState()
                    {
                        Status = ExportStatus.Failed
                    };
                }

                return new EntityState()
                {
                    Status = ExportStatus.Succeeded
                };
            });

            var result1 = await ExportOrchestrator.EntitiesToTriggerExport(mockContext.Object);
            var observedResourcesToExport = result1.EntitiesToTakeAction;
            var observedOrchestrationState = result1.SuccessEntityStates;
            Assert.Equal(expectedExportEntities.Count, observedResourcesToExport.Count);
            Assert.Single(observedOrchestrationState);
        }

        [Fact]
        public async Task Run_ExportOrchestration_EntitiesToTriggerExport_VerifyPartialErrorAndNullStates()
        {
            var resourcesToExport = new List<string>() { "Patient", "Encounter", "Observation" };
            var expectedExportEntities = new List<ExportEntity>() {
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Patient" },
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Observation" }
            };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            mockContext.Setup(x => x.GetInput<EntitiesToTriggerExportInput>()).Returns(new EntitiesToTriggerExportInput { Entities = resourcesToExport, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.MockGuid.ToString() });
            mockEntities.Setup(x => x.CallEntityAsync<EntityState>(It.IsAny<EntityInstanceId>(), "GetEntityState", null, null)).ReturnsAsync((EntityInstanceId entityId, string name, object? input, CallEntityOptions? opts) =>
            {
                if (entityId.Key.Equals(TestConstants.PatientGuidKey))
                {
                    return new EntityState()
                    {
                        Status = ExportStatus.Failed
                    };
                }

                if (entityId.Key.Equals(TestConstants.ObservationGuidKey))
                {
                    return new EntityState();
                }


                return new EntityState()
                {
                    Status = ExportStatus.Succeeded
                };

            });

            var result1 = await ExportOrchestrator.EntitiesToTriggerExport(mockContext.Object);
            var observedResourcesToExport = result1.EntitiesToTakeAction;
            var observedOrchestrationState = result1.SuccessEntityStates;
            Assert.Equal(expectedExportEntities.Count, observedResourcesToExport.Count);
            Assert.Single(observedOrchestrationState);
        }

        [Fact]
        public async Task Run_ExportOrchestration_EntitiesToTriggerExport_VerifyPartialInprogressStates()
        {
            var resourcesToExport = new List<string>() { "Patient", "Encounter", "Observation" };
            var expectedExportEntities = new List<ExportEntity>() {
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Encounter" },
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Observation" }
            };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            mockContext.Setup(x => x.GetInput<EntitiesToTriggerExportInput>()).Returns(new EntitiesToTriggerExportInput { Entities = resourcesToExport, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.MockGuid.ToString() });
            mockEntities.Setup(x => x.CallEntityAsync<EntityState>(It.IsAny<EntityInstanceId>(), "GetEntityState", null, null)).ReturnsAsync((EntityInstanceId entityId, string name, object? input, CallEntityOptions? opts) =>
            {
                if (!entityId.Key.Equals(TestConstants.PatientGuidKey))
                {
                    return new EntityState()
                    {
                        Status = ExportStatus.InProgress
                    };
                }

                return new EntityState()
                {
                    Status = ExportStatus.Succeeded
                };
            });


            var result1 = await ExportOrchestrator.EntitiesToTriggerExport(mockContext.Object);
            var observedResourcesToExport = result1.EntitiesToTakeAction;
            var observedOrchestrationState = result1.SuccessEntityStates;
            Assert.Equal(expectedExportEntities.Count, observedResourcesToExport.Count);
            Assert.Single(observedOrchestrationState);
        }

        [Fact]
        public async Task Run_ExportOrchestration_EntitiesToTriggerExport_VerifyWhenWeHaveEntitiesInAllStates()
        {
            var resourcesToExport = new List<string>() { "Patient", "Encounter", "Observation", "Procedure" };
            var expectedExportEntities = new List<ExportEntity>() {
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Patient" },
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Encounter" },
                new ExportEntity(){Start = CurrentDateTime, ResourceType = "Observation" }
            };
            var (mockContext, mockEntities) = createMockContext(CurrentDateTime);
            mockContext.Setup(x => x.GetInput<EntitiesToTriggerExportInput>()).Returns(new EntitiesToTriggerExportInput { Entities = resourcesToExport, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.MockGuid.ToString() });
            mockEntities.Setup(x => x.CallEntityAsync<EntityState>(It.IsAny<EntityInstanceId>(), "GetEntityState", null, null)).ReturnsAsync((EntityInstanceId entityId, string name, object? input, CallEntityOptions? opts) =>
            {
                if (entityId.Key.Equals(TestConstants.PatientGuidKey))
                {
                    return new EntityState()
                    {
                        Status = ExportStatus.Failed
                    };
                }

                if (entityId.Key.Equals(TestConstants.EncounterGuidKey))
                {
                    return new EntityState();
                }

                if (entityId.Key.Equals(TestConstants.ObservationGuidKey))
                {
                    return new EntityState()
                    {
                        Status = ExportStatus.InProgress
                    };
                }

                return new EntityState()
                {
                    Status = ExportStatus.Succeeded
                };
            });

            var result1 = await ExportOrchestrator.EntitiesToTriggerExport(mockContext.Object);
            var observedResourcesToExport = result1.EntitiesToTakeAction;
            var observedOrchestrationState = result1.SuccessEntityStates;
            Assert.Equal(expectedExportEntities.Count, observedResourcesToExport.Count);
            Assert.Single(observedOrchestrationState);
        }

        public static (Mock<TaskOrchestrationContext>, Mock<TaskOrchestrationEntityFeature>) createMockContext(DateTime currentDateTime)
        {
            var mockContext = new Mock<TaskOrchestrationContext>() { DefaultValue = DefaultValue.Mock };
            var mockEntities = new Mock<TaskOrchestrationEntityFeature>();
            mockContext.Setup(x => x.Entities).Returns(mockEntities.Object);

            mockContext.Setup(x => x.CallSubOrchestratorAsync<string>("GenerateEntityKey", It.IsAny<object?>(), It.IsAny<TaskOptions>())).ReturnsAsync(
                (TaskName function, object? inputObj, TaskOptions? options) =>
            {
                var input = (GenerateEntityKeyInput)inputObj!;
                if (input.Entity == "Patient")
                {
                    return TestConstants.PatientGuidKey;
                }
                if (input.Entity == "Encounter")
                {
                    return TestConstants.EncounterGuidKey;
                }
                if (input.Entity == "Observation")
                {
                    return TestConstants.ObservationGuidKey;
                }
                return TestConstants.MockGuid.ToString();
            });
            mockEntities
                .Setup(x => x.CallEntityAsync<List<ExportEntity>>(It.IsAny<EntityInstanceId>(), "GetExportEntities", It.IsAny<object?>(), null))
                .ReturnsAsync((EntityInstanceId entityId, string operationName, object? resourceObj, CallEntityOptions? opts) =>
                {
                    var resourceString = (string)resourceObj!;
                    return new List<ExportEntity>(){
                        new ExportEntity() { Start = currentDateTime, ResourceType = resourceString }
                    };
                });
            return (mockContext, mockEntities);
        }
    }
}