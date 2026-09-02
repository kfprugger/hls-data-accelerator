using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor
{
    /// <summary>
    /// Shared helpers for the durable-entity state <see cref="System.Text.Json.Serialization.JsonConverter{T}"/>s.
    ///
    /// Background: the .NET 8 isolated worker serializes durable entity state with System.Text.Json, which
    /// emits/reads PascalCase top-level properties (e.g. { "EntityKeyDict": ... }). The legacy .NET 6
    /// in-process model serialized the entity *class* with Newtonsoft.Json, producing a camelCase payload
    /// wrapped under the state field name (e.g. { "entityKeyManagerState": { "entityKeyDict": ... } }).
    /// On an in-place (deployUpdatesOnly) upgrade the new runtime must read that legacy payload so persisted
    /// progress (entity-key mappings and per-resource export watermarks) is preserved instead of reset.
    /// These helpers do case-insensitive lookups so both shapes bind, regardless of serializer casing.
    /// </summary>
    internal static class EntityStateJson
    {
        /// <summary>Case-insensitive property lookup on a JSON object element.</summary>
        public static bool TryGetProperty(JsonElement obj, string name, out JsonElement value)
        {
            if (obj.ValueKind == JsonValueKind.Object)
            {
                // Fast path: exact match.
                if (obj.TryGetProperty(name, out value))
                {
                    return true;
                }

                foreach (JsonProperty prop in obj.EnumerateObject())
                {
                    if (string.Equals(prop.Name, name, StringComparison.OrdinalIgnoreCase))
                    {
                        value = prop.Value;
                        return true;
                    }
                }
            }

            value = default;
            return false;
        }

        /// <summary>Reads a string-keyed/string-valued dictionary from a JSON object element.</summary>
        public static Dictionary<string, string> ReadStringDictionary(JsonElement element)
        {
            var result = new Dictionary<string, string>();
            if (element.ValueKind == JsonValueKind.Object)
            {
                foreach (JsonProperty prop in element.EnumerateObject())
                {
                    result[prop.Name] = prop.Value.ValueKind == JsonValueKind.Null ? null : prop.Value.GetString();
                }
            }

            return result;
        }
    }
}
