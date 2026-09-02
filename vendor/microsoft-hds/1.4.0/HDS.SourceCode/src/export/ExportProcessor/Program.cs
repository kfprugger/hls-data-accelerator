// Program.cs — Entry point for the .NET 8 isolated worker function app.
// Replaces Startup.cs (FunctionsStartup) from the in-process model.
// Configures the Functions worker runtime, DI services, and Azure clients.

using Azure.Identity;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Azure;
using Microsoft.IntegratedDataPlatform.ExportProcessor;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Helper;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Services;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Services.Authentication;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions;
using System;

var host = new HostBuilder()
    .ConfigureFunctionsWorkerDefaults() // Registers the isolated worker middleware pipeline
    .ConfigureServices((context, services) =>
    {
        var configuration = context.Configuration;

        var settings = new Lazy<ExportProcessorSettings>(() =>
        {
            var exportProcessorSettings = new ExportProcessorSettings();
            configuration.Bind(exportProcessorSettings);
            return exportProcessorSettings;
        });

        services.AddMemoryCache();

        services.AddAzureClients(b =>
        {
            b.AddBlobServiceClient(new Uri($"https://{settings.Value.JobOutputStorageAccountName}.blob.core.windows.net"));
            b.UseCredential(new ManagedIdentityCredential());
        });

        services.TryAddSingleton<IMSFTFHIRServerSettings>(_ => settings.Value);
        services.TryAddSingleton<IFHIRServerSettings>(_ => settings.Value);
        services.TryAddSingleton<IResourceManagerSettings>(_ => settings.Value);
        services.Configure<ExportProcessorSettings>(configuration);

        if (Utility.VerifyFHIRServerUri(settings.Value.FHIRServerUri))
        {
            services.TryAddSingleton<MSFTAuthenticationService>();
            services.AddHttpClient<FHIRServerService, MSFTFHIRServerService>(client =>
                    client.BaseAddress = new Uri(settings.Value.FHIRServerUri))
                .AddPolicyHandler((serviceProvider, request) =>
                    Utility.GetRetryPolicy<MSFTFHIRServerService>(serviceProvider, request, settings.Value.RetryCount))
                .AddHttpMessageHandler(s =>
                    new BearerTokenAuthenticationHandler(s.GetService<MSFTAuthenticationService>(), settings.Value.FHIRServerUri));
        }
        else
        {
            throw new IncorrectFHIRServerURIException("The specified FHIR Server URI is invalid.");
        }
    })
    .Build();

host.Run();
