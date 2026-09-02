using Newtonsoft.Json.Linq;

namespace ExtensionSupport
{
    public class SchemaBuilder
    {
        #region DefinedTypes for work with unlimited references 

        /// <summary>
        /// Helper class for our collection of previously
        /// defined types
        /// </summary>
        public class DefinedType
        {
            public string? Name { get; set; }
            public string? FullName { get; set; }

            private List<string> childrenTypes = new List<string>();
            public List<string> ChildrenTypes { get { return this.childrenTypes; } }
        }

        protected bool IsTypeRegistered(string fullName)
        {
            return DefinedTypes.ContainsKey(fullName);
        }

        /// <summary>
        /// Finds type name which will be unique in collection of types
        /// </summary>
        /// <param name="nameSpaceName"></param>
        /// <param name="name"></param>
        /// <returns>unique type name</returns>
        protected string GenerateUniqueType(string nameSpaceName, string name)
        {
            string uniqueName = name;
            int index = 1;
            while (IsTypeRegistered(nameSpaceName + "." + uniqueName))
            {
                uniqueName = name + index.ToString();
                index++;
            }
            return uniqueName;
        }

        protected Dictionary<string, DefinedType> DefinedTypes = new Dictionary<string, DefinedType>();

        #endregion



        private JObject wholeSchema;
        private string schemaToBuild;
        private int maxLevel;
        private bool processUnderscoreProperties = false;
        private int maxExtensionLevels = 2;
        private List<string> unsupportedProperties = new List<string> { "modifierExtension" };

        private string _namespace = "org.hl7.fhir.extgenerated";

        /// <summary>
        /// Default namespace which tool will use to create types
        /// </summary>
        public string Namespace { get { return this._namespace; } set { this._namespace = value; } }

        /// <summary>
        /// Maximum levels of extensions support (default 2)
        /// </summary>
        public int MaxExtensionLevels { get { return this.maxExtensionLevels; } set { this.maxExtensionLevels = value; } }


        /// <summary>
        /// Default list of prohibited properties
        /// default values:
        /// - 'modifierExtension'
        /// </summary>
        public List<string> UnsupportedProperties { get { return this.unsupportedProperties; } }

        /// <summary>
        /// Process properties started with _
        /// (basically extensions for simple types)
        /// </summary>
        public bool ProcessUnderscoreProperties { get { return this.processUnderscoreProperties; } set { this.processUnderscoreProperties = value; } }

        /// <summary>
        /// Create instance of schema builder
        /// </summary>
        /// <param name="maxLevels">maximum nested levels support </param>
        /// <param name="wholeSchema">Full FHIR or different schema</param>
        /// <param name="schemaToBuild">object for which we built schema</param>
        public SchemaBuilder(int maxLevels, JObject wholeSchema, string schemaToBuild)
        {
            this.maxLevel = maxLevels;
            this.wholeSchema = wholeSchema;
            this.schemaToBuild = schemaToBuild;
        }

        public AvroBaseObject BuildSchema()
        {
            var schemaToBuildJson = wholeSchema["definitions"][schemaToBuild];

            return ParseObjectSchema(schemaToBuildJson, schemaToBuild, 0);
        }

        protected AvroBaseObject ParseObjectSchema(JToken resource, string name, int currentLevel)
        {
            // we have reached maximum nesting depth, lets return max avro object
            // to transform it to the string field or string array 
            if (currentLevel >= maxLevel)
            {
                return new MaxLevelAvroObject();
            }

            if (resource.Type == JTokenType.Object)
            {
                var properties = resource.SelectToken("properties");
                var type = resource.SelectToken("type");
                if (properties != null)
                {
                    // we have "properties" attribute, so we have complex type
                    return CreateAvroComplexType(resource, properties, name, currentLevel);
                }
                else if (type != null)
                {
                    // we have "type" attribute, so we have simple type
                    var strType = type.Value<string>();
                    return CreateAvroSimpleType(strType, name);
                }

            }
            else if (resource.Type == JTokenType.Property)
            {
                // we have property type here, it can be array, enum, const or reference
                JProperty prop = (JProperty)resource;
                if (prop.Value != null && prop.Value.SelectToken("type") != null)
                {
                    string type = (string)prop.Value["type"];
                    if (type == "array")
                    {
                        string reference = (string)prop.Value["items"]["$ref"];
                        if (reference != null)
                        {
                            AvroBaseObject typeProp = GetReferenceTypeProperty(reference, prop.Name, currentLevel + 1);
                            return new AvroArrayObject(name, typeProp);
                        }
                        else
                        {
                            //other specific cases like 
                            // "items":{ "enum": [...]
                            return new AvroArrayObject(name, new AvroBaseObject(name, "string"));
                        }
                    }
                    else
                    {
                        JObject obj = (JObject)prop.Value;
                        return CreateAvroSimpleType(type, name);
                    }
                }
                else
                // enums & const will be represented as strings
                if (prop.Value != null && (prop.Value.SelectToken("enum") != null ||
                prop.Value.SelectToken("const") != null))
                {
                    return new AvroBaseObject(name, "string");
                }

                else if (prop.Value != null && prop.Value["$ref"] != null)
                {
                    string reference = (string)prop.Value["$ref"];
                    return GetReferenceTypeProperty(reference, prop.Name, currentLevel + 1);
                }
            }
            // basically we shouldn't never get there
            throw new Exception("Unknown type of resource with name {name}");
        }

        protected AvroBaseObject CreateAvroComplexType(JToken resource, JToken properties, string name, int currentLevel)
        {
            var typeName = name;
            // now we need to check if we have type name already registered
            // we need return registered type as reference
            // and we have different logic for extension 
            if (IsTypeRegistered(Namespace + "." + typeName))
            {
                if (name == "Extension")
                {
                    // if we are here, it means we have extension of extension
                    // (because Extension type has been already registered)
                    // as we want to support up to two levels of extensions
                    // we need to generate new type name it we havn't reach maximum level yet 
                    if (currentLevel <= maxExtensionLevels - 1)
                    {
                        // generate another level of extensions
                        typeName = GenerateUniqueType(Namespace, typeName);
                    }
                    else
                    {
                        // return any new extensions level as string
                        return new MaxLevelAvroObject();
                    }
                }
                else
                {
                    return new AvroReferenceObject() { Name = typeName, Type = Namespace + "." + typeName };
                }

            }

            DefinedType defined_type = new DefinedType
            {
                Name = typeName,
                FullName = Namespace + "." + typeName
            };
            // defined the type, so we will not get into issues with circular references
            DefinedTypes.Add(defined_type.FullName, defined_type);

            // creating new avro type here
            var avroType = new AvroRecordObject
            {
                Name = typeName,
                Namespace = Namespace
            };

            var descr = resource.SelectToken("description");
            if (descr != null)
            {
                avroType.Doc = descr.Value<string>();
            }
            // populate properties
            foreach (JProperty property in properties)
            {
                var property_name = property.Name;
                if (property_name != null)
                {
                    if (property_name.StartsWith("_"))
                    {
                        // we don't support properties starting with "_" at the moment
                        continue;
                    }

                    //check if property_name in list of forbidden names
                    if (UnsupportedProperties.Contains(property_name))
                    {
                        continue;
                    }

                    avroType.Fields.Add(property_name, ParseObjectSchema(property, property_name, currentLevel));
                }
            }

            foreach (KeyValuePair<string, AvroBaseObject> kvPair in avroType.Fields)
            {
                if (kvPair.Value is AvroReferenceProperty)
                {
                    // lets add children types to the parent type dependency cache
                    var record = (kvPair.Value as AvroReferenceProperty).RefType;
                    if (record is AvroRecordObject)
                    {
                        defined_type.ChildrenTypes.Add((record as AvroRecordObject).Name);
                    }
                    else if (record is AvroReferenceObject)
                    {
                        // lets add reference type as well, 
                        // even we are not concerned about them for circular references
                        defined_type.ChildrenTypes.Add("[R]" + (record as AvroReferenceObject).Name);
                    }
                }
            }

            return avroType;
        }


        protected AvroBaseObject GetReferenceTypeProperty(string referenceType, string propName, int level)
        {
            // look for reference type in the whole schema
            JToken refObject = wholeSchema.SelectToken(Utils.TransformReftoNJSON(referenceType));

            if (refObject == null)
            {
                // we don't have reference type in the whole schema
                // so we need to throw exception here

                throw new Exception("Reference type " + referenceType + " not found in the schema");
            }

            if (refObject.SelectToken("$.type") != null)
            {
                var type = refObject.SelectToken("$.type").Value<string>();
                return CreateAvroSimpleType(type, propName);
            }
            else if (refObject.SelectToken("$.properties") != null)
            {
                return new AvroReferenceProperty(propName,
                    ParseObjectSchema(refObject, Utils.GetRefTypeName(referenceType), level));
            }
            // default ?
            return ParseObjectSchema(refObject, referenceType, level + 1);
        }

        /// <summary>
        /// Just create simple and mostly simple types in AVRO
        /// </summary>
        /// <param name="type">type name</param>
        /// <param name="name">property name</param>
        /// <returns></returns>
        protected AvroBaseObject CreateAvroSimpleType(string type, string name)
        {
            string correctType = type;
            // in AVRO we don't have "number" type, normally its "int"
            if (type == "number")
            {
                type = "int";
            }

            // when we have extensions, they basically redefine all the type in 
            // their value* attributes.
            // For our needs we can just ignore their definitions and use the actual
            // type from the property name 
            if (name.StartsWith("value"))
            {
                //extension...support
                //get Type from the name
                correctType = name.Substring("value".Length).ToLower();
            }

            // date support
            if (correctType == "date")
            {
                return new AvroExtendedSimpleObject(name,
                        new JObject{
                    {"type", "int"},
                    {"logicalType","date"}
                            }
                    );
            }
            // datetime
            else if (correctType == "datetime")
            {
                return new AvroExtendedSimpleObject(name,
                        new JObject{
                    {"type", "long"},
                    {"logicalType","timestamp-micros"}
                            }
                    );
            }
            //decimal
            else if (correctType == "decimal")
            {
                return new AvroExtendedSimpleObject(name,
                        new JObject{
                    {"type", "bytes"},
                    {"logicalType","decimal"},
                    {"precision", 18},
                    {"scale",5},
                            }
                    );
            }
            // instant
            else if (correctType == "instant")
            {
                return new AvroExtendedSimpleObject(name,
                        new JObject{
                    {"type", "long"},
                    {"logicalType","timestamp-millis"}
                            }
                    );
            }
            // or just return exact type name from the FHIR schema
            return new AvroBaseObject(name, type);
        }
    }
}