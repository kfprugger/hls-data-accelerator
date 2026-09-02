using Microsoft.IntegratedDataPlatform.ExportProcessor.Exceptions;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using Newtonsoft.Json;
using Polly;
using Polly.Extensions.Http;
using Polly.Retry;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Runtime.CompilerServices;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Helper
{
    public static class Utility
    {
        private static readonly HttpStatusCode[] httpStatusCodesWorthRetrying = {
            HttpStatusCode.Forbidden, // 403
            HttpStatusCode.Unauthorized, // 404
            HttpStatusCode.TooManyRequests //429
        };

        public static AsyncRetryPolicy<HttpResponseMessage> GetRetryPolicy<T>(IServiceProvider services, HttpRequestMessage requestMessage, int retryCount)
        {
            Random jitterer = new Random();
            var retryPolicy = Policy
                .HandleResult<HttpResponseMessage>(r => httpStatusCodesWorthRetrying.Contains(r.StatusCode))
                .OrTransientHttpError() //Network Failures, 5XX and 408
                .WaitAndRetryAsync(retryCount, retryAttempt => TimeSpan.FromSeconds(Math.Pow(2, retryAttempt))  // exponential back-off: 2, 4, 8 etc
                    + TimeSpan.FromMilliseconds(jitterer.Next(0, 1000)),
                    onRetry: (outcome, timespan, retryAttempt, context) =>
                    {
                        if (outcome != null)
                        {
                            if (outcome.Result != null)
                            {
                                services.GetService<ILogger<T>>()?
                                .LogError($"{requestMessage.RequestUri} HTTP Request Failed with {outcome.Result.StatusCode} Delaying for {timespan.TotalMilliseconds}ms, then making retry attempt #{retryAttempt}.");
                            }
                            else
                            {
                                if (outcome.Exception != null)
                                {
                                    services.GetService<ILogger<T>>()?
                                    .LogError($"{requestMessage.RequestUri} HTTP Request Failed with {outcome.Exception.Message} Delaying for {timespan.TotalMilliseconds}ms, then making retry attempt #{retryAttempt}.");
                                } else
                                {
                                    services.GetService<ILogger<T>>()?
                                    .LogError($"{requestMessage.RequestUri} HTTP Request Failed. Delaying for {timespan.TotalMilliseconds}ms, then making retry attempt #{retryAttempt}.");
                                }
                            }
                        } else
                        {
                            services.GetService<ILogger<T>>()?
                            .LogError($"{requestMessage.RequestUri} HTTP Request Failed with null outcome. Delaying for {timespan.TotalMilliseconds}ms, then making retry attempt #{retryAttempt}.");
                        }
                    }
                    );

            return retryPolicy;
        }

        public static T DeserializeJsonFromStream<T>(Stream stream)
        {
            using (var streamReader = new StreamReader(stream))
            {
                using (var jsonTextReader = new JsonTextReader(streamReader))
                {
                    var jsonSerializer = new JsonSerializer();
                    return jsonSerializer.Deserialize<T>(jsonTextReader);
                }
            }
        }

        public static string ParseStringFromDate(DateTime? date)
        {
            var result = date?.ToString("yyyy-MM-ddTHH:mm:sszzz");
            return result.Replace("+", "%2B");
        }

        public static string GetPathToFolderGivenUrl(string url)
        {
            var splitPath = url.Split('/');
            if (splitPath.Length < Constants.MinimumBlobUrlLengthWhenSplit) throw new ArgumentException($"When split by separator, the path to the blob storage is of length: {splitPath.Length}. The url must be of at least length {Constants.MinimumBlobUrlLengthWhenSplit} when split by /. The url is {url}");
            return string.Join('/', splitPath.Skip(Constants.BlobUrlLengthPriorToFolderPath).Take(splitPath.Length - Constants.BlobUrlLengthPriorToFolderPath - 1));
        }

        public static bool VerifyFHIRServerUri(string uri)
        {
            if (!Uri.TryCreate(uri, UriKind.Absolute, out var serverUri))
                return false;

            if (serverUri.Scheme != Uri.UriSchemeHttp && serverUri.Scheme != Uri.UriSchemeHttps)
                return false;
            return true;
        }
    }
}
