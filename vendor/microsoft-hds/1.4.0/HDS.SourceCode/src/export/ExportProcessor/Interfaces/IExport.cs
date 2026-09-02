using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces
{
    /// <summary>
    /// Interface for the export durable entity used to maintain the state of each export run
    /// </summary>
    public interface IExport
    {
        //public Task<EntityState> GetEntityState();

        /// <summary>
        /// Takes action based on the export status of the durable entity.
        /// Succeeded, Failed, Null - Trigger new run
        /// Inprogress - call content location
        /// Entity interfaces can only take one argument - https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-dotnet-entities#restrictions-on-entity-interfaces
        /// </summary>
        /// <returns>
        /// An ExportOrchestrationStatus Object which if an export succeeded will contain the paths to the output folders
        /// </returns>
        public Task<ExportOrchestrationStatus> TakeAction(TakeActionOnEntityInput input);
    }
}