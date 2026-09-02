using Newtonsoft.Json.Linq;

namespace ExtensionSupport
{
    /// <summary>
    /// Represent reference property object 
    /// So this represent property 
    /// </summary>
    public class AvroReferenceProperty : AvroBaseObject
    {
        private AvroBaseObject refType;
        public AvroBaseObject RefType
        {
            get { return this.refType; }
            set { this.refType = value; }
        }

        public AvroReferenceProperty(string name, AvroBaseObject refType) : base(name, "complex")
        {
            this.refType = refType;
        }

        public override JToken GetAvroSchema()
        {

            if (refType is MaxLevelAvroObject)
            {
                return new AvroBaseObject(name, "string").GetAvroSchema();
            }

            return new JObject {
            {"name",this.name},
            {"type", refType.GetAvroSchema()},
            {"default",new JObject{}}
        };
        }
    }
}
