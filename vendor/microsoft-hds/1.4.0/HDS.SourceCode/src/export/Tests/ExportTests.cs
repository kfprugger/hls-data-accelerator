using Microsoft.Extensions.Logging;
using Microsoft.IntegratedDataPlatform.ExportProcessor;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Helper;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Services;
using Moq;
using System.Net;
using Xunit;
using Tests.Helper;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions;
using Newtonsoft.Json;

namespace Tests
{
    public class ExportTests
    {
        public Mock<FHIRServerService> FhirServiceMock;
        public TestableExport ExportEntity;
        public ExportEntity ExportEntityState;

        public ExportTests()
        {

            var handlerMock = new Mock<HttpMessageHandler>(MockBehavior.Strict);
            var client = new HttpClient(handlerMock.Object);
            var fhirServerSettings = new Mock<IFHIRServerSettings>();
            FhirServiceMock = new Mock<FHIRServerService>(client, fhirServerSettings.Object);

            var logger = new LoggerFactory().CreateLogger<Export>();
            ExportEntity = new TestableExport(FhirServiceMock.Object, logger);
            ExportEntity.TestState = new EntityState();
            ExportEntityState = new ExportEntity()
            {
                Start = DateTime.Parse(TestConstants.Since),
                ResourceType = TestConstants.TestResource,
            };
        }

        [Theory]
        [MemberData(nameof(TestTriggerExportData))]
        public async Task TakeAction_TriggerExport_VerifyStatusChange_SuccessStatusCode(ExportStatus? status, DateTime? end = null)
        {

            var responseMessage = new HttpResponseMessage() { StatusCode = HttpStatusCode.Accepted };
            responseMessage.Content.Headers.Add(HTTPHeadersExtensions.ContentLocation, TestConstants.ContentLocation);
            FhirServiceMock.Setup(p => p.TriggerExport(It.IsAny<string>(), It.IsAny<string>())).ReturnsAsync(responseMessage);
            ExportEntity.TestState.Status = status;
            ExportEntity.TestState.End = end;

            var result = await ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId });
            Assert.Equal(ExportStatus.InProgress, ExportEntity.TestState.Status);
            Assert.Equal(new Uri(TestConstants.ContentLocation), ExportEntity.TestState.ContentLocation);
            Assert.Equal(ExportStatus.InProgress, result.ExportStatus);
            Assert.Null(result.Output);
        }

        [Theory]
        [MemberData(nameof(TestTriggerExportData))]
        public async Task TakeAction_TriggerExport_VerifyStatusChange_FailedStatusCode(ExportStatus? status, DateTime? end = null)
        {

            var responseMessage = new HttpResponseMessage() { StatusCode = HttpStatusCode.Unauthorized };
            FhirServiceMock.Setup(p => p.TriggerExport(It.IsAny<string>(), It.IsAny<string>())).ReturnsAsync(responseMessage);
            ExportEntity.TestState.Status = status;
            ExportEntity.TestState.End = end;

            await Assert.ThrowsAsync<Exception>(() => ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId }));
            Assert.Equal(ExportStatus.Failed, ExportEntity.TestState.Status);
        }

        [Theory]
        [MemberData(nameof(TestTriggerExportData))]
        public async Task TakeAction_TriggerExport_VerifyStatusChange_FHIRServiceThrowingError(ExportStatus? status, DateTime? end = null)
        {

            FhirServiceMock.Setup(p => p.TriggerExport(It.IsAny<string>(), It.IsAny<string>())).ThrowsAsync(new ArgumentNullException("FHIR Server Uri Is Null"));
            ExportEntity.TestState.Status = status;
            ExportEntity.TestState.End = end;

            await Assert.ThrowsAsync<Exception>(() => ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId }));
            Assert.Equal(ExportStatus.Failed, ExportEntity.TestState.Status);
        }


        [Theory]
        [MemberData(nameof(TestTriggerExportData))]
        public async Task TakeAction_TriggerExport_VerifyStatusChange_ContentLocationNotExisting(ExportStatus? status, DateTime? end = null)
        {

            var responseMessage = new HttpResponseMessage() { StatusCode = HttpStatusCode.Accepted };
            FhirServiceMock.Setup(p => p.TriggerExport(It.IsAny<string>(), It.IsAny<string>())).ReturnsAsync(responseMessage);
            ExportEntity.TestState.Status = status;
            ExportEntity.TestState.End = end;

            await Assert.ThrowsAsync<Exception>(() => ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId }));
            Assert.Equal(ExportStatus.Failed, ExportEntity.TestState.Status);
        }

        [Fact]
        public async Task TakeAction_PollInProgress_VerifyNoStatusChange_ExportJobReturningAcceptedStatusCode()
        {

            var responseMessage = new HttpResponseMessage() { StatusCode = HttpStatusCode.Accepted };
            FhirServiceMock.Setup(p => p.PollContentLocation(It.IsAny<Uri>())).ReturnsAsync(responseMessage);
            ExportEntity.TestState.Status = ExportStatus.InProgress;

            var result = await ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId });
            Assert.Equal(ExportStatus.InProgress, ExportEntity.TestState.Status);
            Assert.Equal(ExportStatus.InProgress, result.ExportStatus);
            Assert.Null(result.Output);
        }

        [Fact]
        public async Task TakeAction_PollInProgress_VerifyStatusChange_ExportJobReturningSuccessStatusCode()
        {

            var responseMessage = new HttpResponseMessage() { StatusCode = HttpStatusCode.OK };
            responseMessage.Content = new StringContent(JsonConvert.SerializeObject(MockDataGenerator.GenerateSuccessExportResponse()), System.Text.Encoding.UTF8, "application/json");
            FhirServiceMock.Setup(p => p.PollContentLocation(It.IsAny<Uri>())).ReturnsAsync(responseMessage);
            ExportEntity.TestState.Status = ExportStatus.InProgress;

            var result = await ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId });
            Assert.Equal(ExportStatus.Updating, ExportEntity.TestState.Status);
            Assert.Single(result.Output);
            Assert.Equal(ExportStatus.Updating, result.ExportStatus);
            Assert.Single(result.Output);
        }

        [Fact]
        public async Task TakeAction_PollInProgress_VerifyStatusChange_ExportJobReturningSuccessStatusCode_WithErrors()
        {

            var responseMessage = new HttpResponseMessage() { StatusCode = HttpStatusCode.OK };
            responseMessage.Content = new StringContent(JsonConvert.SerializeObject(MockDataGenerator.GenerateExportResponseWithErrors()), System.Text.Encoding.UTF8, "application/json");
            FhirServiceMock.Setup(p => p.PollContentLocation(It.IsAny<Uri>())).ReturnsAsync(responseMessage);
            ExportEntity.TestState.Status = ExportStatus.InProgress;

            await Assert.ThrowsAsync<Exception>(() => ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId }));
            Assert.Equal(ExportStatus.Failed, ExportEntity.TestState.Status);
        }

        [Fact]
        public async Task TakeAction_PollInProgress_VerifyStatusChange_ExportJobReturningSuccessStatusCode_WithIssues()
        {

            var responseMessage = new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.OK,
                Content = new StringContent(MockDataGenerator.GenerateExportResponseWithIssues())
            };
            FhirServiceMock.Setup(p => p.PollContentLocation(It.IsAny<Uri>())).ReturnsAsync(responseMessage);
            ExportEntity.TestState.Status = ExportStatus.InProgress;

            await Assert.ThrowsAsync<Exception>(() => ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId }));
            Assert.Equal(ExportStatus.Failed, ExportEntity.TestState.Status);
        }

        [Fact]
        public async Task TakeAction_PollInProgress_VerifyStatusChange_ExportJobReturningNonSuccessStatusCode()
        {

            var responseMessage = new HttpResponseMessage() { StatusCode = HttpStatusCode.NotFound };
            FhirServiceMock.Setup(p => p.PollContentLocation(It.IsAny<Uri>())).ReturnsAsync(responseMessage);
            ExportEntity.TestState.Status = ExportStatus.InProgress;

            await Assert.ThrowsAsync<Exception>(() => ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId })) ;
            Assert.Equal(ExportStatus.Failed, ExportEntity.TestState.Status);
        }

        [Fact]
        public async Task TakeAction_PollInProgress_VerifyStatusChange_ExportJobReturningThrowsExcpetion()
        {

            FhirServiceMock.Setup(p => p.PollContentLocation(It.IsAny<Uri>()))
                .ThrowsAsync(new ArgumentNullException("FHIR Server Uri Is Null"));
            ExportEntity.TestState.Status = ExportStatus.InProgress;

            await Assert.ThrowsAsync<Exception>(() => ExportEntity.TakeAction(new TakeActionOnEntityInput { Entity = ExportEntityState, RunId = TestConstants.TestRunId, CorrelationId = TestConstants.TestCorrelationId }));
            Assert.Equal(ExportStatus.Failed, ExportEntity.TestState.Status);
        }

        public static IEnumerable<object?[]> TestTriggerExportData()
        {
            yield return new object?[] { null };
            yield return new object?[] { ExportStatus.Succeeded, DateTime.UtcNow };
            yield return new object?[] { ExportStatus.Failed};
        }
    }
}
