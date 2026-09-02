using Newtonsoft.Json.Linq;

namespace ExtensionSupport
{
    /// <summary>
    /// Represent record object in AVRO schema
    /// Contains most basic AVRO schema record properties for fields or types:
    /// - name, type, default, doc, namespace
    /// </summary>
    public class AvroRecordObject : AvroBaseObject
    {
        protected Dictionary<string, AvroBaseObject> fields = new();

        public Dictionary<string, AvroBaseObject> Fields
        {
            get { return this.fields; }
        }

        protected string? doc;
        protected string? _namespace;

        public string? Doc { get { return this.doc; } set { this.doc = value; } }
        public string? Namespace { get { return this._namespace; } set { this._namespace = value; } }

        public AvroRecordObject()
        {
            // set internal type to record
            this.type = "record";
        }

        public override JToken GetAvroSchema()
        {
            JObject result = new(
                new JProperty("type", "record"),
                new JProperty("name", this.name)
            );

            if (!string.IsNullOrEmpty(this.doc))
            {
                result.Add("doc", this.doc);
            }

            if (!string.IsNullOrEmpty(this._namespace))
            {
                result.Add("namespace", this._namespace);
            }

            JArray fieldsArr = new();
            foreach (var field in this.fields)
            {
                fieldsArr.Add(field.Value.GetAvroSchema());
            }
            result.Add("fields", fieldsArr);

            result.Add("default", JToken.FromObject(new Object()));

            return result;
        }
    }
}