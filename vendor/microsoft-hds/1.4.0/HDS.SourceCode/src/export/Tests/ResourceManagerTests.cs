using Microsoft.IntegratedDataPlatform.ExportProcessor;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Moq;
using Tests.Helper;
using Xunit;

namespace Tests
{
    public class ResourceManagerTests
    {
        public ResourceManager ResourceManager;
        public DateTime TestDateTime;
        public ResourceManagerTests()
        {
            TestDateTime = DateTime.Parse(TestConstants.Since);

            var settings = new Mock<IResourceManagerSettings>();
            settings.SetupGet(z => z.DataStart).Returns(TestDateTime);
            ResourceManager = new ResourceManager(settings.Object);
        }

        [Fact]
        public void ResourceManagerFlow()
        {
            string resourceType = "R1,R2,R3,R4";
            List<ExportEntity> exportEntities = ResourceManager.GetExportEntities(resourceType);
            ValidateExportEntitiesAndUpdate(exportEntities, new List<string> { resourceType }, new List<DateTime?> { TestDateTime });

            resourceType = "R1,R2,R3,R4,R5";
            exportEntities = ResourceManager.GetExportEntities(resourceType);
            ValidateExportEntitiesAndUpdate(exportEntities, new List<string> { "R1,R2,R3,R4", "R5" }, new List<DateTime?> { TestDateTime.AddHours(1), TestDateTime });

            resourceType = "R1,R2,R3,R5";
            exportEntities = ResourceManager.GetExportEntities(resourceType);
            ValidateExportEntitiesAndUpdate(exportEntities, new List<string> { "R1,R2,R3", "R5" }, new List<DateTime?> { TestDateTime.AddHours(2), TestDateTime.AddHours(1) });

            resourceType = "R1,R2,R3,R4,R5";
            exportEntities = ResourceManager.GetExportEntities(resourceType);
            ValidateExportEntitiesAndUpdate(exportEntities, new List<string> { "R1,R2,R3", "R4,R5" }, new List<DateTime?> { TestDateTime.AddHours(3), TestDateTime.AddHours(2) });

            resourceType = "R4,R5";
            exportEntities = ResourceManager.GetExportEntities(resourceType);
            ValidateExportEntitiesAndUpdate(exportEntities, new List<string> { "R4,R5" }, new List<DateTime?> { TestDateTime.AddHours(3) });

            resourceType = "R1,R2,R3,R4,R5";
            exportEntities = ResourceManager.GetExportEntities(resourceType);
            ValidateExportEntitiesAndUpdate(exportEntities, new List<string> { "R1,R2,R3,R4,R5" }, new List<DateTime?> { TestDateTime.AddHours(4) });
        }

        private void ValidateExportEntitiesAndUpdate(List<ExportEntity> exportEntities, List<string> resourceType, List<DateTime?> since)
        {
            List<DateTime?> sinceList = exportEntities.Select(x => x.Start).ToList();
            List<string> resourceTypeList = exportEntities.Select(e => e.ResourceType).ToList();

            Assert.Equal(resourceType, resourceTypeList);
            Assert.Equal(since, sinceList);

            foreach (ExportEntity exportEntity in exportEntities)
            {
                ResourceManager.UpdateResources(new UpdateResourcesInput { ResourceString = exportEntity.ResourceType, End = exportEntity.Start.Value.AddHours(1) });
            }
        }
    }
}