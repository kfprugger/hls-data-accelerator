using Newtonsoft.Json.Linq;

namespace ExtensionSupport
{
    /// <summary>
    /// Represent basic array object in AVRO schema
    /// Contains most basic AVRO schema properties for fields or types:
    /// - name, type
    /// </summary>
    public class AvroArrayObject : AvroBaseObject
    {
        protected AvroBaseObject refToken;
        public AvroBaseObject RefToken
        {
            get { return this.refToken; }
            set { this.refToken = value; }
        }

        public AvroArrayObject(string name, AvroBaseObject refToken) : base(name, "array")
        {
            // set internal type to array and Preserve internal type
            this.refToken = refToken;
        }

        public override JToken GetAvroSchema()
        {
            JToken token = this.RefToken.GetAvroSchema();

            if (this.RefToken.GetType() == typeof(AvroBaseObject))
            {
                token = this.RefToken.Type;
            }
            else if (this.RefToken is AvroReferenceProperty)
            {
                var refProp = this.RefToken as AvroReferenceProperty;
                if (refProp.RefType is AvroReferenceObject)
                {
                    token = refProp.RefType.Type;
                }
                else if (refProp.RefType is MaxLevelAvroObject)
                {
                    token = "string";
                }
                else if (refProp.RefType is AvroRecordObject)
                {
                    token = refProp.RefType.GetAvroSchema();
                }
            }

            return new JObject {
            {"name",this.name},
            {"type",
                new JObject{
                    {"type","array"},
                    {"items",token},
                    {"default",new JArray{}}
                }},
            {"default",new JArray{}}
        };
        }
    }
}