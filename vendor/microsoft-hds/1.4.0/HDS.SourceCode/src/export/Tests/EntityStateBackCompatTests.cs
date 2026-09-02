using System;
using System.Collections.Generic;
using STJ = System.Text.Json;
using Microsoft.IntegratedDataPlatform.ExportProcessor;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Xunit;

namespace Tests
{
    /// <summary>
    /// Verifies durable-entity state back-compat across the .NET 6 in-process -> .NET 8 isolated migration.
    ///
    /// IMPORTANT: these tests serialize/deserialize with System.Text.Json (STJ) because that is the serializer
    /// the .NET 8 isolated DurableTask runtime actually uses for entity state. (Newtonsoft attributes on the
    /// state classes are ignored at runtime.) Tests assert against the REAL persisted shapes:
    ///   - modern/isolated: PascalCase top-level (e.g. { "EntityKeyDict": ... }, { "End": ..., "Status": 0 })
    ///   - legacy/in-process: camelCase wrapped under the state field name
    ///       (e.g. { "entityKeyManagerState": { "entityKeyDict": ... } }, { "entityState": { "till": ... } })
    /// On an in-place (deployUpdatesOnly) upgrade the new runtime must read the legacy shape so persisted
    /// progress is preserved; on fresh deployments the modern shape must round-trip unchanged.
    /// </summary>
    public class EntityStateBackCompatTests
    {
        // ---------- EntityKeyManagerState ----------

        [Fact]
        public void EntityKeyManagerState_MigratesLegacyWrappedState()
        {
            string legacyJson = "{\"entityKeyManagerState\":{\"entityKeyDict\":{\"Patient\":\"key-1\",\"Encounter\":\"key-2\"}}}";

            var state = STJ.JsonSerializer.Deserialize<EntityKeyManagerState>(legacyJson);

            Assert.Equal("key-1", state.EntityKeyDict["Patient"]);
            Assert.Equal("key-2", state.EntityKeyDict["Encounter"]);
        }

        [Fact]
        public void EntityKeyManagerState_KeepsNativeIsolatedState()
        {
            // Real persisted isolated shape is PascalCase.
            string isolatedJson = "{\"EntityKeyDict\":{\"Patient\":\"key-1\"}}";

            var state = STJ.JsonSerializer.Deserialize<EntityKeyManagerState>(isolatedJson);

            Assert.Equal("key-1", state.EntityKeyDict["Patient"]);

            string roundTripped = STJ.JsonSerializer.Serialize(state);
            Assert.Contains("EntityKeyDict", roundTripped);
            // Fresh deployments must NOT emit a legacy wrapper.
            Assert.DoesNotContain("entityKeyManagerState", roundTripped);
        }

        [Fact]
        public void EntityKeyManagerState_GuardsNullDictionary()
        {
            var state = STJ.JsonSerializer.Deserialize<EntityKeyManagerState>("{}");
            Assert.NotNull(state.EntityKeyDict);
            Assert.Empty(state.EntityKeyDict);
        }

        // ---------- ResourceManagerState ----------

        [Fact]
        public void ResourceManagerState_MigratesLegacyWrappedWatermarks()
        {
            string legacyJson = "{\"resourceManagerState\":{\"resourceDict\":{\"Patient\":{\"start\":\"2023-01-31T16:00:00Z\",\"resourceType\":\"Patient\"}}}}";

            var state = STJ.JsonSerializer.Deserialize<ResourceManagerState>(legacyJson);

            Assert.True(state.ResourceDict.ContainsKey("Patient"));
            Assert.Equal("Patient", state.ResourceDict["Patient"].ResourceType);
            Assert.Equal(
                DateTime.Parse("2023-01-31T16:00:00Z").ToUniversalTime(),
                state.ResourceDict["Patient"].Start.Value.ToUniversalTime());
        }

        [Fact]
        public void ResourceManagerState_KeepsNativeIsolatedState()
        {
            // Real persisted isolated shape is PascalCase ("ResourceDict"/"Start"/"ResourceType").
            string isolatedJson = "{\"ResourceDict\":{\"Patient\":{\"Start\":\"2023-01-31T16:00:00Z\",\"ResourceType\":\"Patient\"}}}";

            var state = STJ.JsonSerializer.Deserialize<ResourceManagerState>(isolatedJson);

            Assert.True(state.ResourceDict.ContainsKey("Patient"));
            Assert.Equal("Patient", state.ResourceDict["Patient"].ResourceType);
            Assert.Equal(
                DateTime.Parse("2023-01-31T16:00:00Z").ToUniversalTime(),
                state.ResourceDict["Patient"].Start.Value.ToUniversalTime());

            string roundTripped = STJ.JsonSerializer.Serialize(state);
            Assert.Contains("ResourceDict", roundTripped);
            Assert.DoesNotContain("resourceManagerState", roundTripped);
        }

        [Fact]
        public void ResourceManagerState_SkipsNullDictionaryEntries()
        {
            // A null ResourceState value must be dropped on read; otherwise GetExportEntities groups by
            // rs.Start and throws NullReferenceException, breaking the whole export.
            string jsonWithNull = "{\"ResourceDict\":{\"Patient\":{\"Start\":\"2023-01-31T16:00:00Z\",\"ResourceType\":\"Patient\"},\"Encounter\":null}}";

            var state = STJ.JsonSerializer.Deserialize<ResourceManagerState>(jsonWithNull);

            Assert.True(state.ResourceDict.ContainsKey("Patient"));
            Assert.False(state.ResourceDict.ContainsKey("Encounter"));
            Assert.DoesNotContain(null, state.ResourceDict.Values);
        }

        // ---------- Export EntityState ----------

        [Fact]
        public void ExportEntityState_MigratesLegacyTillToEnd()
        {
            // Legacy state used "since"/"till"; "till" (last successful transaction time) maps to "End".
            // status 0 == ExportStatus.Succeeded.
            string legacyJson = "{\"entityState\":{\"since\":\"2023-01-31T16:00:00Z\",\"till\":\"2023-02-01T16:00:00Z\",\"status\":0,\"resourceType\":\"Patient\",\"contentLocation\":\"https://fhir/export/123\",\"successOutput\":[]}}";

            var state = STJ.JsonSerializer.Deserialize<EntityState>(legacyJson);

            Assert.Equal(
                DateTime.Parse("2023-02-01T16:00:00Z").ToUniversalTime(),
                state.End.Value.ToUniversalTime());
            Assert.Equal(ExportStatus.Succeeded, state.Status);
            Assert.Equal("Patient", state.ResourceType);
            Assert.Equal(new Uri("https://fhir/export/123"), state.ContentLocation);
        }

        [Fact]
        public void ExportEntityState_KeepsNativeIsolatedState()
        {
            // Real persisted isolated shape is PascalCase. status 1 == ExportStatus.InProgress.
            string isolatedJson = "{\"End\":\"2023-02-01T16:00:00Z\",\"Status\":1,\"ResourceType\":\"Patient\",\"ContentLocation\":null,\"SuccessOutput\":null}";

            var state = STJ.JsonSerializer.Deserialize<EntityState>(isolatedJson);

            Assert.Equal(ExportStatus.InProgress, state.Status);
            Assert.Equal("Patient", state.ResourceType);

            string roundTripped = STJ.JsonSerializer.Serialize(state);
            Assert.Contains("End", roundTripped);
            Assert.Contains("Status", roundTripped);
            Assert.DoesNotContain("entityState", roundTripped);
        }

        [Fact]
        public void ExportEntityState_MigratesLegacySuccessOutput()
        {
            // Legacy successOutput entries were camelCase ("type"/"url"/"count").
            string legacyJson = "{\"entityState\":{\"till\":\"2023-02-01T16:00:00Z\",\"status\":0,\"resourceType\":\"Patient\",\"successOutput\":[{\"type\":\"Patient\",\"url\":\"https://blob/patient.ndjson\",\"count\":5}]}}";

            var state = STJ.JsonSerializer.Deserialize<EntityState>(legacyJson);

            Assert.NotNull(state.SuccessOutput);
            Assert.Single(state.SuccessOutput);
            Assert.Equal("Patient", state.SuccessOutput[0].Type);
            Assert.Equal("https://blob/patient.ndjson", state.SuccessOutput[0].Url);
            Assert.Equal(5, state.SuccessOutput[0].Count);
        }
    }
}
