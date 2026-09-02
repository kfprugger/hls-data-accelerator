using Microsoft.Extensions.Logging;
using Microsoft.IntegratedDataPlatform.ExportProcessor.Models;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;

namespace Microsoft.IntegratedDataPlatform.ExportProcessor.Helper
{
    public static class LoggerExtensions
    {
        /// <summary>
        /// This function was build ot avoid using Begin Scope
        /// </summary>
        /// <param name="loggingObject">the object to use for setting scope</param>
        /// <param name="methodName"></param>
        /// <param name="filePath"></param>
        /// <param name="lineNumber"></param>
        /// <param name="exception"></param>
        /// <returns></returns>
        private static IReadOnlyCollection<KeyValuePair<string, object>> CreateScope(string methodName, LoggingMetadata loggingObject, string filePath,
            int lineNumber, Exception exception = null)
        {
            BindingFlags bindingAttr = BindingFlags.DeclaredOnly | BindingFlags.Public | BindingFlags.Instance;
            var result = loggingObject.GetType().GetProperties(bindingAttr)
                .ToDictionary(
                propInfo => propInfo.Name,
                propInfo => propInfo.GetValue(loggingObject, null));

            result.TryAdd("MethodName", methodName);
            result.TryAdd("FilePath", filePath);
            result.TryAdd("LineNumber", lineNumber);
            if (exception != null)
            {
                result.TryAdd("ExceptionString", exception.ToString());
            }

            return result;
        }

        /// <summary>
        /// Formats and writes a Information log message.
        /// </summary>
        /// <param name="logger">The <see cref="ILogger"/> to write to.</param>
        /// <param name="message">Format string of the log message in message template format. Example: <code>"User {User} logged in from {Address}"</code></param>
        /// <param name="correlationId">The correlationId to use</param>
        /// <param name="resourceType">The resourceType for the export</param>
        /// <param name="args">An object array that contains zero or more objects to format.</param>
        /// <example>logger.LogDebug(0, exception, "Error while processing request from {Address}", address)</example>
        public static void LogInformationEx(this ILogger logger, string message, LoggingMetadata loggingObject, [CallerMemberName] string memberName = "", [CallerFilePath] string filePath = "", [CallerLineNumber] int lineNumber = 0, params object[] args)
        {
            using var _ = logger.BeginScope(CreateScope(memberName, loggingObject, filePath, lineNumber));
            logger.LogInformation(message, args);
        }

        /// <summary>
        /// Formats and writes a Error log message.
        /// </summary>
        /// <param name="logger">The <see cref="ILogger"/> to write to.</param>
        /// <param name="message">Format string of the log message in message template format. Example: <code>"User {User} logged in from {Address}"</code></param>
        /// <param name="correlationId">The correlationId to use</param>
        /// <param name="resourceType">The resourceType for the export</param>
        /// <param name="exception">The exception that was thrown</param>
        /// <param name="args">An object array that contains zero or more objects to format.</param>
        /// <example>logger.LogDebug(0, exception, "Error while processing request from {Address}", address)</example>
        public static void LogErrorEx(this ILogger logger, LoggingMetadata loggingObject, Exception exception, [CallerMemberName] string memberName = "", [CallerFilePath] string filePath = "", [CallerLineNumber] int lineNumber = 0, params object[] args)
        {
            using var _ = logger.BeginScope(CreateScope(memberName, loggingObject, filePath, lineNumber, exception));
            logger.LogError(exception.Message, args);
        }
    }
}