namespace ExtensionSupport
{
    public class Utils
    {

        /// <summary>
        /// Transform $ref value from the fhir.schema.json to
        /// Newtonsoft JSON token format
        /// <example>
        /// #/definitions/ValueSet
        /// will become
        /// $.definitions.ValueSet
        /// </example
        /// </summary>
        public static string? TransformReftoNJSON(string reference)
        {
            if (string.IsNullOrEmpty(reference))
                return null;

            return reference.Replace('#', '$').Replace('/', '.');
        }

        public static String GetRefTypeName(string reference)
        {
            return reference.Substring(reference.LastIndexOf("/") + 1);
        }

    }
}