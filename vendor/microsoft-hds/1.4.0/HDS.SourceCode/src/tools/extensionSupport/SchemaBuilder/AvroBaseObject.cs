using Newtonsoft.Json.Linq;

namespace ExtensionSupport
{
    /// <summary>
    /// Represent basic object from AVRO schema
    /// Contains most basic AVRO schema properties for fields or types:
    /// - name, type, default
    /// </summary>
    public class AvroBaseObject
    {
        protected string? name = null;
        protected string? type = null;
        protected JObject? defJsonObject = null;
        protected bool isNullable = true;

        /// <summary>
        /// Name of the object
        /// </summary>
        public string? Name { get { return this.name; } set { this.name = value; } }
        /// <summary>
        /// Type of the object
        /// </summary>
        public string? Type { get { return this.type; } set { this.type = value; } }
        /// <summary>
        /// Default JSON object of the object
        /// </summary>
        public virtual JObject? DefJsonObject { get { return this.defJsonObject; } set { this.defJsonObject = value; } }

        /// <summary>
        /// Is the object nullable
        /// </summary>
        public bool IsNullable { get { return this.isNullable; } set { this.isNullable = value; } }

        protected AvroBaseObject() { }

        public AvroBaseObject(string name, string type)
        {
            this.name = name;
            this.type = type;
        }

        public AvroBaseObject(string name, string type, JObject defJsonObject) : this(name, type)
        {
            this.defJsonObject = defJsonObject;
        }

        /// <summary>
        /// Returns the Avro schema of the object
        /// </summary>
        /// <returns>json in form of JToken</returns>
        public virtual JToken GetAvroSchema()
        {
            JObject result = new(new JProperty("name", name));
            
            if (isNullable)
            {
                result.Add("type", new JArray { "null", type });
                result.Add("default", null);
            }
            else
            {
                result.Add("type", type);
            }

            return result;
        }
    }
}