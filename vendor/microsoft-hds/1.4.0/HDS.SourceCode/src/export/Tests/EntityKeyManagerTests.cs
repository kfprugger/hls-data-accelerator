using Azure.Storage.Blobs;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.IntegratedDataPlatform.ExportProcessor;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Helper;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Services;
using Moq;
using Tests.Helper;
using Xunit;

namespace Tests
{
    public class EntityKeyManagerTests
    {
        public EntityKeyManager EntityKeyManager;
        public EntityKeyManagerTests()
        {
            EntityKeyManager = new EntityKeyManager();
        }

        [Fact]
        public async Task GenerateEntityId_VerifySameResourceTypeGeneratesSameKey()
        {
            string resourceType = "Account,ActivityDefinition,AdverseEvent,AllergyIntolerance";
            string entityKey1 = await EntityKeyManager.GenerateEntityKey(resourceType);
            string entityKey2 = await EntityKeyManager.GenerateEntityKey(resourceType);
            Assert.Equal(entityKey1, entityKey2);
        }

        [Fact]
        public async Task GenerateEntityId_VerifyDifferentResourceTypeGeneratesDifferentKey()
        {
            string resourceType = "Account,ActivityDefinition,AdverseEvent,AllergyIntolerance";
            string resourceType2 = "Patient,Encounter,Observation,Practitioner,Organization,MedicationRequest,Procedure,DocumentReference,PractitionerRole,Condition";
            string entityKey1 = await EntityKeyManager.GenerateEntityKey(resourceType);
            string entityKey2 = await EntityKeyManager.GenerateEntityKey(resourceType2);
            Assert.NotEqual(entityKey1, entityKey2);
        }
    }
}