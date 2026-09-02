using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Interfaces
{
    /// <summary>
    /// Interface for the Resource Manager
    /// </summary>
    public interface IResourceManager
    {
        /// <summary>
        /// Given a resource string that is a comma delimited list of resources
        /// Update all the resource with the new time for next export
        /// Entity interfaces can only take one argument - https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-dotnet-entities#restrictions-on-entity-interfaces
        /// <param name="input">The input which is a tuple containing (resourceString: resource string to update, end: the end time of the export)</param>
        /// </summary>
        public void UpdateResources(UpdateResourcesInput input);

        /// <summary>
        /// Given a resource string that is a comma delimited list of resources
        /// First. Add the Resource to the Resource Manager if it doesn't exist
        /// Next. Group the Resources based on the since (startTime) of the resource
        /// Entity interfaces can only take one argument - https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-dotnet-entities#restrictions-on-entity-interfaces
        /// </summary>
        /// <param name="resourceString">The resourceString to create export entities from</param>
        /// <returns>
        /// List of Export Entities to perform export in the form of (startTime, ResourceTypeString)
        /// </returns>
        public List<ExportEntity> GetExportEntities(string resourceString);
    }
}