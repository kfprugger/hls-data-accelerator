using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces
{
    /// <summary>
    /// Interface for the entity Key manager
    /// </summary>
    public interface IEntityKeyManager
    {
        //public Task<EntityState> GetEntityState();

        /// <summary>
        /// Generates an entity Key given the resource type.
        /// If there is an existing entity Key for the given resource type return that entity Key
        /// Otherwise return a new entity Key
        /// Entity interfaces can only take one argument - https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-dotnet-entities#restrictions-on-entity-interfaces
        /// </summary>
        /// <returns>
        /// A string which is the entity Key for the given resource type
        /// </returns>
        public Task<string> GenerateEntityKey(string resourceType);
    }
}