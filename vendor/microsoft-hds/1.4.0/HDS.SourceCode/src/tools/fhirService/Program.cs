// See https://aka.ms/new-console-template for more information
using fhirservice;
class Program
{
    static void Main(string[] args)
    {

        string fhirServiceUrl = "https://hdssharedfs-fhirserver.fhir.azurehealthcareapis.com";
        if (args.Length > 0)
        {
            fhirServiceUrl = args[0];
        }
        MSFTFHIRServerService mSFTFHIRServerService = new MSFTFHIRServerService(fhirServiceUrl);
        mSFTFHIRServerService.CreatePatient();
        mSFTFHIRServerService.CreateAllergyIntolerance();
        mSFTFHIRServerService.CreateProcedure();
        mSFTFHIRServerService.CreateObservation();

        Console.WriteLine("Hello, World!");
    }
}