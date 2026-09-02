using Newtonsoft.Json.Linq;

namespace ExtensionSupport
{
    public class SchemaEnricher
    {
        private string extensionSchema;
        private string fileSchema;

        private bool useStringForComplexObject = false;

        private bool useFullExtensionPropertyTypes = false;

        private List<FullExtensionProperty> fullExtensionPropertyTypes = null;

        /// <summary>
        /// Use string for complex object (i.e. use string for `extension` property on complex objects, like encounter.subject)
        /// </summary>
        public bool UseStringForComplexObject
        {
            get { return this.useStringForComplexObject; }
            set { this.useStringForComplexObject = value; }
        }

        /// <summary>
        /// Use full extension only on specified properties below
        /// </summary>
        public bool UseFullExtensionPropertyTypes
        {
            get { return this.useFullExtensionPropertyTypes; }
            set { this.useFullExtensionPropertyTypes = value; }
        }

        /// <summary>
        /// List of all properties for all resources which support full extension instead if string
        /// </summary>
        public List<FullExtensionProperty> FullExtensionPropertyTypes
        {
            get { return this.fullExtensionPropertyTypes; }
            set { this.fullExtensionPropertyTypes = value; }
        }


        /// <summary>
        /// Constructor
        /// </summary>
        /// <param name="extensionSchema">extension schema</param>
        /// <param name="fileSchema">file schema</param>
        public SchemaEnricher(string extensionSchema, string fileSchema)
        {
            this.extensionSchema = extensionSchema;
            this.fileSchema = fileSchema;
        }

        /// <summary>
        /// Enrich the file schema to extension schema
        /// </summary>
        /// <returns></returns>
        public string Enrich()
        {
            JObject fileJsonSchema = JObject.Parse(fileSchema);
            // search for the top level id field
            var idf = fileJsonSchema.SelectToken("$.fields[?(@name=='id')]");
            // search resourceType
            var resourceType = (string)fileJsonSchema["name"];
            // find all the records in the file to extend with "extension" property
            var records = fileJsonSchema.SelectTokens("$.fields..[?(@type=='record')]");

            // read extension schema attributes
            var extensionSchemaJson = JObject.Parse(extensionSchema);
            var extensionName = extensionSchemaJson.SelectToken("$.name").Value<string>();
            var extensionNamespace = extensionSchemaJson.SelectToken("$.namespace").Value<string>();
            var extensionType = extensionNamespace + "." + extensionName;

            // prepare the extension properties type for the file
            var extRefPropertyFull = new JObject {
                {"name","extension"},
                {"type",
                    new JObject{
                        {"type","array"},
                        {"items",extensionType},
                        {"default",new JArray{}}
                    }},
                {"default",new JArray{}}
                };

            // prepare the extension properties type for the file
            var extRefPropertyString = new JObject {
                {"name","extension"},
                {"type",
                    new JArray{
                        "null",
                        "string"
                    }},
                {"default", null}
            };

            // add extension property to all types in the file
            foreach (var element in records)
            {
                if (UseFullExtensionPropertyTypes)
                {
                    if (!string.IsNullOrEmpty(resourceType) && FullExtensionPropertyTypes != null)
                    {
                        /// find the full extension property item for the resource
                        var fullExtensionProperty = FullExtensionPropertyTypes.FirstOrDefault(x => x.Resource == resourceType);
                        if (fullExtensionProperty != null)
                        {
                            // if the property is in the list of full extension properties types
                            if (fullExtensionProperty.PropertyTypes.Contains(element["name"].Value<string>()))
                            {
                                // append full 'extension' property as first element in the fields array
                                element.SelectToken("fields").First.AddBeforeSelf(extRefPropertyFull.DeepClone());
                                continue;
                            }
                        }
                    }
                }
                // if we cannot find a property type in the PropertTypes list, lets use default method for extensions
                if (UseStringForComplexObject)
                {
                    // append string 'extension' property as first element in the fields array
                    element.SelectToken("fields").First.AddBeforeSelf(extRefPropertyString.DeepClone());
                }
                else
                {
                    // append full 'extension' property  as first element in the fields array
                    element.SelectToken("fields").First.AddBeforeSelf(extRefPropertyFull.DeepClone());
                }
            }

            // it would be full extension top level property defintion
            var extProperty = new JObject {
                {"name","extension"},
                {"type",
                    new JObject{
                        {"type","array"},
                        {"items",extensionSchemaJson},
                        {"default",new JArray{}}
                    }},
                {"default",new JArray{}}
            };

            if (UseStringForComplexObject)
            {
                idf.AddAfterSelf(extRefPropertyString);
            }
            else {
                idf.AddAfterSelf(extProperty);
            }

            // return the enriched schema
            return fileJsonSchema.ToString();
        }


    }
}