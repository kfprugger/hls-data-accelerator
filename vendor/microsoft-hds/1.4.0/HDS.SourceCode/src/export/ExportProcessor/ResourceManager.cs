using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask.Entities;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor
{
    /// <summary>
    /// Manages FHIR resource types and their export start times.
    /// Extends TaskEntity&lt;ResourceManagerState&gt; for the .NET 8 isolated worker durable entity model.
    /// Tracks per-resource export progress so subsequent exports start from where the last one ended.
    /// </summary>
    public class ResourceManager : TaskEntity<ResourceManagerState>, IResourceManager
    {
        private readonly IResourceManagerSettings _resourceManagerSettings;

        public ResourceManager(IResourceManagerSettings settings)
        {
            _resourceManagerSettings = settings;
        }

        /// <summary>
        /// Updates the resource state dictionary with the latest export end time for each resource type.
        /// Called by the orchestrator after a successful export to track progress.
        /// </summary>
        public void UpdateResources(UpdateResourcesInput input)
        {
            State ??= new ResourceManagerState();
            // Migrate legacy .NET 6 in-process wrapped state and guard against null dictionaries
            State.Normalize();

            List<string> resources = input.ResourceString.Split(",").ToList();
            foreach(string resource in resources)
            {
                ResourceState newResourceState = new ResourceState()
                {
                    Start = input.End,
                    ResourceType = resource
                };
                State.ResourceDict[resource] = newResourceState;
            }
        }

        /// <summary>
        /// Returns the list of export entities for the given resource types, grouped by start time.
        /// Creates new resource state entries with the configured DataStart if a resource hasn't been exported before.
        /// </summary>
        public List<ExportEntity> GetExportEntities(string resourceString)
        {
            State ??= new ResourceManagerState();
            // Migrate legacy .NET 6 in-process wrapped state and guard against null dictionaries
            State.Normalize();

            List<string> resources = resourceString.Split(",").ToList();
            List<ResourceState> resourceStates = new List<ResourceState>();
            foreach (string resource in resources)
            {
                ResourceState resourceState;
                if (State.ResourceDict.TryGetValue(resource, out ResourceState currentResourceState))
                {
                    resourceState = currentResourceState;
                }
                else
                {
                    ResourceState newResourceState = new ResourceState() { Start = _resourceManagerSettings.DataStart, ResourceType = resource };
                    State.ResourceDict[resource] = newResourceState;
                    resourceState = newResourceState;
                }
                resourceStates.Add(resourceState);
            }

            var exportEntities = resourceStates
                .GroupBy(rs => rs.Start)
                .Select(g => new ExportEntity()
                {
                    Start = g.Key,
                    ResourceType = string.Join(",", g.Select(rs => rs.ResourceType))
                })
                .ToList();

            return exportEntities;
        }

        /// <summary>
        /// Entity trigger dispatch function for the isolated worker model.
        /// Routes incoming entity operations to the ResourceManager instance methods.
        /// </summary>
        [Function(nameof(ResourceManager))]
        public static Task RunEntityDispatcher([EntityTrigger] TaskEntityDispatcher dispatcher)
        {
            return dispatcher.DispatchAsync<ResourceManager>();
        }
    }
    [JsonConverter(typeof(ResourceManagerStateJsonConverter))]
    public class ResourceManagerState
    {
        [JsonPropertyName("ResourceDict")]
        public Dictionary<string, ResourceState> ResourceDict { get; set; }

        /// <summary>
        /// Ensures the dictionary is non-null. Legacy .NET 6 in-process wrapped state is migrated up-front by
        /// <see cref="ResourceManagerStateJsonConverter"/> during deserialization, so this is a cheap, idempotent
        /// guard for both freshly-constructed and deserialized instances.
        /// </summary>
        public void Normalize()
        {
            ResourceDict ??= new Dictionary<string, ResourceState>();
        }
    }

    /// <summary>
    /// Reads both the modern isolated shape ({ "ResourceDict": { ... } }) and the legacy .NET 6 in-process
    /// shape ({ "resourceManagerState": { "resourceDict": { ... } } }), and always writes the modern shape.
    /// This preserves the per-resource export watermarks across an in-place upgrade so exports resume from the
    /// last end time instead of re-exporting from DataStart. Inner ResourceState values are read
    /// case-insensitively so the legacy camelCase ("start"/"resourceType") payload binds too.
    /// </summary>
    public class ResourceManagerStateJsonConverter : JsonConverter<ResourceManagerState>
    {
        // Case-insensitive so the legacy camelCase ResourceState ("start"/"resourceType") binds as well as the
        // modern PascalCase. Reused across calls (JsonSerializerOptions is immutable/thread-safe after first use).
        // Equivalent to the runtime options under the current bare ConfigureFunctionsWorkerDefaults() setup.
        private static readonly JsonSerializerOptions CaseInsensitive = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };

        public override ResourceManagerState Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            var state = new ResourceManagerState();
            using JsonDocument doc = JsonDocument.ParseValue(ref reader);
            JsonElement root = doc.RootElement;

            if (EntityStateJson.TryGetProperty(root, "ResourceDict", out JsonElement dictEl))
            {
                state.ResourceDict = ReadResourceDictionary(dictEl);
            }
            else if (EntityStateJson.TryGetProperty(root, "resourceManagerState", out JsonElement legacyEl)
                     && EntityStateJson.TryGetProperty(legacyEl, "resourceDict", out JsonElement legacyDictEl))
            {
                state.ResourceDict = ReadResourceDictionary(legacyDictEl);
            }

            state.Normalize();
            return state;
        }

        public override void Write(Utf8JsonWriter writer, ResourceManagerState value, JsonSerializerOptions options)
        {
            writer.WriteStartObject();
            writer.WritePropertyName("ResourceDict");
            JsonSerializer.Serialize(writer, value.ResourceDict ?? new Dictionary<string, ResourceState>(), options);
            writer.WriteEndObject();
        }

        private static Dictionary<string, ResourceState> ReadResourceDictionary(JsonElement element)
        {
            var result = new Dictionary<string, ResourceState>();
            if (element.ValueKind == JsonValueKind.Object)
            {
                foreach (JsonProperty prop in element.EnumerateObject())
                {
                    // Skip null entries: downstream GetExportEntities groups by rs.Start and reads
                    // rs.ResourceType, so a null ResourceState would throw NullReferenceException and
                    // break the whole export. Dropping it lets the entity re-seed from DataStart.
                    if (prop.Value.ValueKind == JsonValueKind.Null)
                    {
                        continue;
                    }

                    ResourceState resourceState = prop.Value.Deserialize<ResourceState>(CaseInsensitive);
                    if (resourceState is null)
                    {
                        continue;
                    }

                    result[prop.Name] = resourceState;
                }
            }

            return result;
        }
    }

    public class ResourceState
    {
        public DateTime? Start { get; set; }

        public string ResourceType { get; set; }
    }

    public interface IResourceManagerSettings
    {
        public DateTime? DataStart { get; set; }

    }
}
