using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace fhirservice
{
    public class MSFTFHIRServerService
    {

        private string fhirurl;
        public MSFTFHIRServerService(string fhirurl)
        {
            this.fhirurl = fhirurl;
        }

        public void SendCreateRequest(string url, string filePath)
        {

            using (HttpClient client = new HttpClient())
            {
                // Read the content of the JSON file into a string
                string payload = File.ReadAllText(filePath); ;

                HttpContent content = new StringContent(payload, System.Text.Encoding.UTF8, "application/json");
                Console.WriteLine($"Generating BearerToken FHIR Server - {this.fhirurl}");
                MSFTAuthenticationService authService = new MSFTAuthenticationService();
                string bearerToken = authService.RetrieveToken(this.fhirurl).Result;
                client.DefaultRequestHeaders.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", bearerToken);
                try
                {
                    Console.WriteLine($"Creating a resource in FHIR Server - {url}");
                    // Make the POST request
                    HttpResponseMessage response = client.PostAsync(url, content).Result;

                    // Check if the request was successful
                    if (response.IsSuccessStatusCode)
                    {
                        // Read the response content
                        string responseBody = response.Content.ReadAsStringAsync().Result;
                        Console.WriteLine("Response: " + responseBody);
                    }
                    else
                    {
                        // Handle the failure
                        Console.WriteLine("HTTP request failed with status code: " + response.StatusCode);
                    }
                }
                catch (Exception ex)
                {
                    // Handle any exceptions
                    Console.WriteLine("Error occurred: " + ex.Message);
                }
            }

        }

        public void CreatePatient()
        {

            using (HttpClient client = new HttpClient())
            {
                string url = $"{this.fhirurl}/Patient";
                string filePath = @".\patient.json";

                SendCreateRequest(url, filePath);
            }

        }

        public void CreateAllergyIntolerance()
        {
            using (HttpClient client = new HttpClient())
            {
                string url = $"{this.fhirurl}/AllergyIntolerance";
                string filePath = @".\AllergyIntolerance.json";

                SendCreateRequest(url, filePath);
            }

        }

        public void CreateObservation()
        {
            using (HttpClient client = new HttpClient())
            {
                string url = $"{this.fhirurl}/Observation";
                string filePath = @".\Observation.json";

                SendCreateRequest(url, filePath);
            }

        }

        public void CreateProcedure()
        {
            using (HttpClient client = new HttpClient())
            {
                string url = $"{this.fhirurl}/Procedure";
                string filePath = @".\Procedure.json";

                SendCreateRequest(url, filePath);
            }

        }
    }
}
