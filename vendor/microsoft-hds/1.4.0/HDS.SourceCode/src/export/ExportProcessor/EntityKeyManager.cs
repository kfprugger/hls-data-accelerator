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
    /// Manages entity key mappings for FHIR resource types.
    /// Extends TaskEntity&lt;EntityKeyManagerState&gt; for the .NET 8 isolated worker durable entity model.
    /// State is automatically serialized/deserialized by the Durable Task framework.
    /// </summary>
    public class EntityKeyManager : TaskEntity<EntityKeyManagerState>, IEntityKeyManager
    {
        /// <summary>Returns current entity state, migrating any legacy .NET 6 in-process wrapped state, or a new empty state if not yet initialized.</summary>
        public EntityKeyManagerState GetEntityState()
        {
            State ??= new EntityKeyManagerState();
            State.Normalize();
            return State;
        }

        /// <summary>
        /// Generates or retrieves a deterministic entity key for a given resource type.
        /// Uses a dictionary to ensure the same resource type always maps to the same entity key.
        /// </summary>
        /// <param name="resourceType">Comma-separated FHIR resource types (e.g., "Patient,Encounter")</param>
        /// <returns>A GUID-based entity key for the resource type</returns>
        public Task<string> GenerateEntityKey(string resourceType)
        {
            State ??= new EntityKeyManagerState();
            // Migrate legacy .NET 6 in-process wrapped state and guard against null dictionaries
            State.Normalize();

            string entityKey;
            if (State.EntityKeyDict.TryGetValue(resourceType, out string existingEntityKey))
            {
                entityKey = existingEntityKey;
            }
            else
            {
                string newEntityKey = System.Guid.NewGuid().ToString();
                State.EntityKeyDict[resourceType] = newEntityKey;
                entityKey = newEntityKey;
            }
            return Task.FromResult(entityKey);
        }

        /// <summary>
        /// Entity trigger dispatch function for the isolated worker model.
        /// Routes incoming entity operations to the EntityKeyManager instance methods.
        /// </summary>
        [Function(nameof(EntityKeyManager))]
        public static Task RunEntityDispatcher([EntityTrigger] TaskEntityDispatcher dispatcher)
        {
            return dispatcher.DispatchAsync<EntityKeyManager>();
        }
    }
    [JsonConverter(typeof(EntityKeyManagerStateJsonConverter))]
    public class EntityKeyManagerState
    {
        [JsonPropertyName("EntityKeyDict")]
        public Dictionary<string, string> EntityKeyDict { get; set; }

        /// <summary>
        /// Ensures the dictionary is non-null. Legacy .NET 6 in-process wrapped state is migrated up-front by
        /// <see cref="EntityKeyManagerStateJsonConverter"/> during deserialization, so this is a cheap, idempotent
        /// guard for both freshly-constructed and deserialized instances.
        /// </summary>
        public void Normalize()
        {
            EntityKeyDict ??= new Dictionary<string, string>();
        }
    }

    /// <summary>
    /// Reads both the modern isolated shape ({ "EntityKeyDict": { ... } }) and the legacy .NET 6 in-process
    /// shape ({ "entityKeyManagerState": { "entityKeyDict": { ... } } }), and always writes the modern shape.
    /// This preserves existing resourceType -&gt; entity-key mappings across an in-place upgrade with zero change
    /// to how state is persisted going forward.
    /// </summary>
    public class EntityKeyManagerStateJsonConverter : JsonConverter<EntityKeyManagerState>
    {
        public override EntityKeyManagerState Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            var state = new EntityKeyManagerState();
            using JsonDocument doc = JsonDocument.ParseValue(ref reader);
            JsonElement root = doc.RootElement;

            if (EntityStateJson.TryGetProperty(root, "EntityKeyDict", out JsonElement dictEl))
            {
                state.EntityKeyDict = EntityStateJson.ReadStringDictionary(dictEl);
            }
            else if (EntityStateJson.TryGetProperty(root, "entityKeyManagerState", out JsonElement legacyEl)
                     && EntityStateJson.TryGetProperty(legacyEl, "entityKeyDict", out JsonElement legacyDictEl))
            {
                state.EntityKeyDict = EntityStateJson.ReadStringDictionary(legacyDictEl);
            }

            state.Normalize();
            return state;
        }

        public override void Write(Utf8JsonWriter writer, EntityKeyManagerState value, JsonSerializerOptions options)
        {
            writer.WriteStartObject();
            writer.WritePropertyName("EntityKeyDict");
            JsonSerializer.Serialize(writer, value.EntityKeyDict ?? new Dictionary<string, string>(), options);
            writer.WriteEndObject();
        }
    }
}
