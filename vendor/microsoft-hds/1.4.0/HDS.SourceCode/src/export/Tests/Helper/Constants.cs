using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Tests.Helper
{
    public static class TestConstants
    {
        public const string ContentLocation = "https://test.com";
        public const string Since = "2023-01-31t16:00:00+08:00";
        public const string TestResource = "TestResource";
        public const string TestCorrelationId = "TestCorrelationId";
        public const string TestRunId = "TestRunId";
        public static readonly Guid MockGuid = new Guid("F9168C5E-CEB2-4faa-B6BF-329BF39FA1E4");
        public static readonly string PatientGuidKey = "1d1963a4-9193-47f2-9e35-014bf184968c";
        public static readonly string EncounterGuidKey = "e7ca173d-1d32-4e9e-9ab5-4f01e79db828";
        public static readonly string ObservationGuidKey = "d4863f17-4634-45c3-88e6-0f40c7c41f74";
    }
}
