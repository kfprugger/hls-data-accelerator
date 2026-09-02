using Newtonsoft.Json.Linq;

namespace ExtensionSupport
{
    /// <summary>
    /// The AvroExtendedSimpleObject class for 
    /// dealing with types which requires additional properties, like decimal
    /// </summary>
    public class AvroExtendedSimpleObject : AvroBaseObject
    {
        protected JToken improvedType;
        public JToken ImprovedType
        {
            get { return this.ImprovedType; }
            set { this.ImprovedType = value; }
        }

        public AvroExtendedSimpleObject(string name, JToken improvedType) : base(name, "improved")
        {
            this.improvedType = improvedType;
        }

        public override JToken GetAvroSchema()
        {
            JToken result = base.GetAvroSchema();
            // just replace type with more improved version of it
            result["type"] = new JArray { "null", this.improvedType };
            return result;
        }
    }
}