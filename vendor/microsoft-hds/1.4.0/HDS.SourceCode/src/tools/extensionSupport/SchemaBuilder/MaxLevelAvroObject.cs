using Newtonsoft.Json.Linq;

namespace ExtensionSupport
{
    /// <summary>
    /// Defines special avro object when we reach max level of nesting
    /// This special object will be used to generate the 'string' type for property or in array
    /// </summary>
    public class MaxLevelAvroObject : AvroBaseObject
    {
        public override JObject GetAvroSchema()
        {
            return new JObject { "Should not see" };
        }
    }
}