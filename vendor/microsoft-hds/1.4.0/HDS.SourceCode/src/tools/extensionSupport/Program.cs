using CommandLine;
using CommandLine.Text;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Microsoft.Extensions.Configuration;

namespace ExtensionSupport
{
    class Program
    {

        private static CommandLineOptions _options = null;

        static bool ProcessArguments(string[] args)
        {
            Parser.Default.ParseArguments<CommandLineOptions>(args)
                .WithParsed(o =>
                {
                    _options = o;
                });

            if (_options == null)
            {
                return false;
            }
            return true;

        }

        static void Main(string[] args)
        {
            // read the arguments
            if (ProcessArguments(args))
            {
                // read the configuration
                IConfiguration configuration = new ConfigurationBuilder().
                    AddJsonFile("appsettings.json").Build();

                // get the extension levels
                var extLevels = configuration.GetValue<int>("AppSettings:ExtensionLevels");
                // get the nested complex objects levels
                var nestedLevels = configuration.GetValue<int>("AppSettings:NestedObjectLevels");
                // get the relative path to the schema file
                var fhirSchemaFile = configuration.GetValue<string>("AppSettings:FhirSchemaFile");
                // extension avro schema file name 
                var extensionSchemaFileName = configuration.GetValue<string>("AppSettings:ExtensionAvroSchemaFile");
                // always regenerate the extension schema
                var alwaysRegenerateExtension = configuration.GetValue<bool>("AppSettings:AlwaysRegenerateFhirSchema");


                // Read schema Enricher settings

                // use string for complex objects 'extension' property
                // (i.e. use string for `extension` property on complex objects, like encounter.subject)
                var useStringForComplexObjects = configuration.GetValue<bool>("SchemaEnricher:UseStringForComplexObjects");

                // use list to determine which properties should use full extension instead of string
                // if this property used with useStringForComplexObjects=true -> it doesn't matter
                var useFullExtensionPropertiesList = configuration.GetValue<bool>("SchemaEnricher:UseFullExtensionProperties");

                // list of resource names and top-level property names 
                // which should use full extension instead of string
                var fullExtensionPropertiesSection = configuration.GetSection("SchemaEnricher:FullExtensionPropertyTypes");
                List<FullExtensionProperty> fullExtensionPropertyTypes = fullExtensionPropertiesSection.Get<List<FullExtensionProperty>>();


                // build the full path to the schema file
                var executableFolder = Path.GetDirectoryName(System.Reflection.Assembly.GetEntryAssembly().Location);
                var extensionSchemaFilePath = Path.Combine(executableFolder, extensionSchemaFileName);

                string? fullExtensionSchemaText = null;

                if (File.Exists(extensionSchemaFilePath) && !alwaysRegenerateExtension)
                {
                    Console.WriteLine($"Will use extension schema file already exists: {extensionSchemaFilePath}");
                    // read the schema from the file
                    fullExtensionSchemaText = File.ReadAllText(extensionSchemaFilePath);
                }
                else
                {
                    Console.WriteLine($"Will generate extension schema file: {extensionSchemaFilePath}");
                    var wholeFHIRSchema = File.ReadAllText(Path.Combine(executableFolder, fhirSchemaFile));
                    var wholeFHIRSchemaJson = JObject.Parse(wholeFHIRSchema);

                    SchemaBuilder builder = new SchemaBuilder(nestedLevels, wholeFHIRSchemaJson, "Extension")
                    {
                        MaxExtensionLevels = extLevels,
                        ProcessUnderscoreProperties = false
                    };
                    // build the schema
                    fullExtensionSchemaText = builder.BuildSchema().GetAvroSchema().ToString();
                    // write the schema to the file
                    File.WriteAllText(extensionSchemaFilePath, fullExtensionSchemaText);
                    Console.WriteLine($"Extension schema has been built and file written: {extensionSchemaFilePath}");
                }

                if (_options.InputFile != null)
                {
                    Console.WriteLine($"Input file specified: {_options.InputFile}");
                    Console.WriteLine($"Output file specified: {_options.OutputFile}");

                    ConvertFile(_options.InputFile, _options.OutputFile, fullExtensionSchemaText, useStringForComplexObjects,
                     useFullExtensionPropertiesList, fullExtensionPropertyTypes);
                }
                else if (_options.InputFolder != null)
                {
                    Console.WriteLine($"Input folder specified: {_options.InputFolder}");
                    Console.WriteLine($"Output folder specified: {_options.OutputFolder}");

                    if (string.IsNullOrEmpty(_options.InputFolder) || !Directory.Exists(_options.InputFolder))
                    {
                        Console.WriteLine($"Input folder does not exist: {_options.InputFolder}");
                        return;
                    }

                    if (string.IsNullOrEmpty(_options.OutputFolder) || !Directory.Exists(_options.OutputFolder))
                    {
                        Console.WriteLine($"Output folder does not exist: {_options.OutputFolder}");
                        return;
                    }

                    foreach (var file in Directory.GetFiles(_options.InputFolder, "*.avsc"))
                    {
                        var outputFile = Path.Combine(_options.OutputFolder, Path.GetFileName(file));
                        ConvertFile(file, outputFile, fullExtensionSchemaText, useStringForComplexObjects,
                            useFullExtensionPropertiesList, fullExtensionPropertyTypes);
                    }
                }
                else
                {
                    Console.WriteLine("No input file or folder specified");
                    return;
                }
            }
        }

        protected static void ConvertFile(string inputFile, string outputFile, string fullExtensionSchemaText, bool useStringForComplexObjects,
            bool useFullExtensionPropertiesList = false, List<FullExtensionProperty> fullExtensionPropertyTypes = null)
        {
            if (!File.Exists(inputFile))
            {
                Console.WriteLine($"Input file does not exist: {inputFile}");
                return;
            }
            // check if output file is specified
            if (string.IsNullOrEmpty(outputFile))
            {
                Console.WriteLine($"Output file is not specified");
                return;
            }
            // read the input file
            var inputText = File.ReadAllText(inputFile);
            // create the converter
            var converter = new SchemaEnricher(fullExtensionSchemaText, inputText)
            {
                UseStringForComplexObject = useStringForComplexObjects,
                UseFullExtensionPropertyTypes = useFullExtensionPropertiesList,
                FullExtensionPropertyTypes = fullExtensionPropertyTypes
            };
            // convert the input file
            var outputJson = converter.Enrich();
            // write the output file
            File.WriteAllText(outputFile, outputJson);
            Console.WriteLine($"Output file converted: {outputFile} from: {inputFile}");
        }
    }
}