using Newtonsoft.Json.Linq;

namespace ExtensionSupport
{
    /// <summary>
    /// Represent avro record object in AVRO schema, but written as a reference.
    /// So we should have only type 
    /// </summary>
    public class AvroReferenceObject : AvroBaseObject
    {
        public override JToken GetAvroSchema()
        {
            return this.type;
        }
    }

}