# Extension support .NET tool

This tool is used to generate the extension schema in AVRO format and process the AVRO schema files to add the extension support to the AVRO schema files.
 - add attribute `extension` to top level record (right after `id`)
 - add attribute `extension` to top `struct` types and `arrays`:`struct` types (right after `id`)
 - tool support configurations to ommit adding full extension schema to other complex types


## Generic Build commands
### To build the tool
```bash
dotnet build
```
### To run the tool
```bash
dotnet run
```
### To publish the tool
```bash
dotnet publish -c Release
```

## Tool specific commands
### To generate the extension schema for the folder
```bash
.{path_to_extension_build}/extensionSupport --inputfolder {path to simple avro schemas folder} --outputfolder {path to the folder where put enriched avro schemas}
```

As an example in my environment I run the following command:

```bash
./bin/Debug/net6.0/extensionSupport --inputfolder /home/DataPlatform/src/tools/fhir2spark/src/resources/r4/schemas/simple --outputfolder /home/DataPlatform/src/tools/extensionSupport/enriched_schema
```

An example to generate schema for a single file would be:
  
  ```bash
  ./bin/Debug/net6.0/extensionSupport --inputfile /home/DataPlatform/src/tools/fhir2spark/src/resources/r4/schemas/simple/patient.avsc --outputfile /home/DataPlatform/src/tools/extensionSupport/patient.avsc
  ```

## Tool command line help:
```
bin/Debug/net6.0/extensionSupport
extensionSupport 1.0.0
Copyright (C) 2023 extensionSupport

  -i, --inputfile       Required. Input file to be processed. (Note: you required to
                        use input file or input folder option)

  -o, --outputfile      Output file to be generated.

  -f, --inputfolder     Required. Input folder to be processed. (Note: you required to
                        use input file or input folder option)

  -g, --outputfolder    Output folder to be generated.

  --help                Display this help screen.

  --version             Display version information.
```

Note: Tool supports either input file or input folder option. If both are provided, tool will throw en error with description to console.

## Tool specific configurations

Tool configuration is located in appsettings.json file. You can change the configuration to change the behavior of the tool.
Below is default configuration:

```json 
{
  "AppSettings": {
    "_help": "App settings contains some of the settings used for generating the schemas",
    "ExtensionLevels": 2,
    "NestedObjectLevels": 5,
    "FhirSchemaFile": "fhir.schema.json",
    "ExtensionAvroSchemaFile": "extension.schema.json",
    "AlwaysRegenerateFhirSchema": false
  },
  "SchemaEnricher": {
    "UseStringForComplexObjects": true,
    "UseFullExtensionProperties": false,
    "FullExtensionPropertyTypes": [
      {
        "resource": "Patient",
        "propertyTypes": [
          "Address"
        ]
      }
    ]
  }
}
```

Lets go through each of the configuration settings:

|Section | Configuration | Description | Default value |
| ------------- |------------- | ----------- | ------------- |
| AppSettings| ExtensionLevels | This configuration is used to define the number of levels for the extension. Be default, if the value is 2, then the tool will support only 2 levels of extension in its definition. All other extension properties will be strings | 2 |
| AppSettings| NestedObjectLevels | This configuration is used to define the number of levels to go down for the nested objects. Default value is 5, then the tool build complex types up to 5 levels in depth. Right now we are using this tool to build extension, so extension themselves took 2 first levels, so we are using only 3 levels. In that case for extension property `valueCodeableReference` we can go as deep as `extension[0].extension[0].valueCodeableReference.reference.identifier.assigner`, where `assigner` will be `string` as last level of supported hierarchy  | 5 |
| AppSettings| FhirSchemaFile | This configuration is used to define the path to used fhir.schema.json file to build extension schema. By default we use provided with program in bin folder | fhir.schema.json |
| AppSettings| ExtensionAvroSchemaFile | This configuration is used to define the name of the extension schema file. If this file is present - we will read generated extension from it, rather than generate. Else tool will generate and preserve this file for the future usage. | extension.schema.json |
| AppSettings| AlwaysRegenerateFhirSchema | This configuration is used to define if the tool should always regenerate the extension schema file. If the value is false, then the tool will only regenerate the extension schema file if it does not exist. | false |
| SchemaEnricher| UseStringForComplexObjects | This configuration is used to define if the tool should use string instead full extension definition for complex objects in file. If the value is true, then the tool will use string for complex objects. we anyway will use full extension schema for top level `extension` resource attribute | true |
| SchemaEnricher| UseFullExtensionProperties | This configuration is used to define if the tool should use full extension schema for just subset of types. If the value is true, then the tool will use 'FullExtensionPropertyTypes' list to define which types for which resources will require full extension schema support.| false |
| SchemaEnricher| FullExtensionPropertyTypes | This configuration is used to define which types for which resources will require full extension schema support. the list contain with object like `{"resource": "Patient","propertyTypes": ["Address"]}` where `resource` property specifies resourceType which has complex `extension` types, and `propertyTypes` defines a collection of type names for which we should extend them with full `extension` attribute schema, not just `string` | [] |

### FhirSchemaFile

This configuration is used to define the path to used fhir.schema.json file to build extension schema. This file represents the full fhir schema with all types and properties. 
By default we are using FHIR R4B (v4.3.0) schema which you can find at [https://hl7.org/fhir/r4b/downloads.html](https://hl7.org/fhir/r4b/downloads.html) at JSON:: JSON Schema section.

## Generating specific configurations

### All string 'extension' attributes, except top level 'extension' property:

The `appsettings.json` will look like:

```json
{
  "AppSettings": {
    "_help": "App settings contains some of the settings used for generating the schemas",
    "ExtensionLevels": 2,
    "NestedObjectLevels": 5,
    "FhirSchemaFile": "fhir.schema.json",
    "ExtensionAvroSchemaFile": "extension.schema.json",
    "AlwaysRegenerateFhirSchema": false
  },
  "SchemaEnricher": {
    "UseStringForComplexObjects": true,
    "UseFullExtensionProperties": false,
    "FullExtensionPropertyTypes": [
      {
        "resource": "Patient",
        "propertyTypes": [
          "Address"
        ]
      }
    ]
  }
}
```

Note: `UseStringForComplexObjects` should be `true` and `UseFullExtensionProperties` should be `false`

then run a command:
  
  ```bash 
  ./bin/Debug/net6.0/extensionSupport --inputfolder /home/DataPlatform/src/tools/fhir2spark/src/resources/r4/schemas/simple 
  
  --outputfolder /home/DataPlatform/src/tools/extensionSupport/schema/string_extension_schema
  ```

  to generate simplified (string properties for extensions) schema for all files in the folder `string_extension_schema`

### All full 'extension' attributes

The `appsettings.json` will look like:

```json
{
  "AppSettings": {
    "_help": "App settings contains some of the settings used for generating the schemas",
    "ExtensionLevels": 2,
    "NestedObjectLevels": 5,
    "FhirSchemaFile": "fhir.schema.json",
    "ExtensionAvroSchemaFile": "extension.schema.json",
    "AlwaysRegenerateFhirSchema": false
  },
  "SchemaEnricher": {
    "UseStringForComplexObjects": false,
    "UseFullExtensionProperties": false,
    "FullExtensionPropertyTypes": [
      {
        "resource": "Patient",
        "propertyTypes": [
          "Address"
        ]
      }
    ]
  }
}
```

Note: `UseStringForComplexObjects` should be `false` and `UseFullExtensionProperties` should be `false` (it can be `true` - doesn't matter because we anyway generate full extension schema for all types)

then run a command:
  
  ```bash 
  ./bin/Debug/net6.0/extensionSupport --inputfolder /home/DataPlatform/src/tools/fhir2spark/src/resources/r4/schemas/simple 
  
  --outputfolder /home/DataPlatform/src/tools/extensionSupport/schema/full_extension_schema
  ```

  to generate full extension support  schema for all files in the folder `full_extension_schema`

### Selective full 'extension' attributes just for several types in several schemas (except top level 'extension' property, which always will be full extension schema)

The `appsettings.json` will look like:

```json
{
  "AppSettings": {
    "_help": "App settings contains some of the settings used for generating the schemas",
    "ExtensionLevels": 2,
    "NestedObjectLevels": 5,
    "FhirSchemaFile": "fhir.schema.json",
    "ExtensionAvroSchemaFile": "extension.schema.json",
    "AlwaysRegenerateFhirSchema": false
  },
  "SchemaEnricher": {
    "UseStringForComplexObjects": true,
    "UseFullExtensionProperties": true,
    "FullExtensionPropertyTypes": [
      {
        "resource": "Patient",
        "propertyTypes": [
          "Address"
        ]
      }
    ]
  }
}
```

Note: `UseStringForComplexObjects` should be `true` and `UseFullExtensionProperties` should be `true`. `FullExtensionPropertyTypes` should contain a list of objects, which will define which types for which resources will require full extension schema support.

In the example above we will process `Address` type for `Patient` resource and generate full extension schema for it.


then run a command:
  
  ```bash 
  ./bin/Debug/net6.0/extensionSupport --inputfolder /home/DataPlatform/src/tools/fhir2spark/src/resources/r4/schemas/simple 
  
  --outputfolder /home/DataPlatform/src/tools/extensionSupport/schema/partial_extension_schema
  ```

  to partial schema (string properties for extensions except defined in settings) schema for all files in the folder `partial_extension_schema`