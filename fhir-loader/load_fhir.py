"""
FHIR Loader - Uploads Synthea data to Azure FHIR Service and creates device linkages

This script:
1. Downloads Synthea-generated FHIR bundles from Azure Blob Storage
2. Uploads Atlanta provider organizations  
3. Identifies patients with qualifying conditions for home monitoring
4. Creates FHIR Device resources for Masimo pulse oximeters
5. Creates DeviceAssociation resources linking devices to patients
6. Ensures Children's Healthcare of Atlanta patients are pediatric
"""

import os
import sys
import json
import hashlib
import tempfile
import time
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from typing import List, Dict, Any, Optional

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("=== FHIR LOADER STARTING ===", flush=True)

import requests
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

# Configuration
FHIR_SERVICE_URL = os.getenv('FHIR_SERVICE_URL', '').rstrip('/')
STORAGE_ACCOUNT = os.getenv('STORAGE_ACCOUNT', '')
CONTAINER_NAME = os.getenv('CONTAINER_NAME', 'synthea-output')
DEVICE_COUNT = int(os.getenv('DEVICE_COUNT', '100'))
CANONICAL_MANIFEST_BLOB = os.getenv('CANONICAL_MANIFEST_BLOB', '_control/canonical-fixture-manifest.json')
RESEED_DATA = os.getenv('RESEED_DATA', '').strip().lower() in {'1', 'true', 'yes', 'on'}

print(f"FHIR Service URL: {FHIR_SERVICE_URL}", flush=True)
print(f"Storage Account: {STORAGE_ACCOUNT}", flush=True)
print(f"Container Name: {CONTAINER_NAME}", flush=True)
print(f"Device Count: {DEVICE_COUNT}", flush=True)
print(f"Reseed Data: {RESEED_DATA}", flush=True)

# Children's Healthcare of Atlanta organization IDs
CHOA_ORG_IDS = [
    'childrens-healthcare-atlanta',
    'choa-egleston', 
    'choa-scottish-rite',
    'choa-hughes-spalding'
]

# Load device registry
with open('/app/device_registry.json', 'r') as f:
    DEVICE_REGISTRY = json.load(f)

# Load Atlanta providers
with open('/app/atlanta_providers.json', 'r') as f:
    ATLANTA_PROVIDERS = json.load(f)


class FHIRClient:
    """Client for interacting with Azure FHIR Service"""
    
    def __init__(self, fhir_url: str):
        self.fhir_url = fhir_url
        self.credential = None
        self.access_token = None
        self.token_expiry = None
        self.token_lock = threading.Lock()
        # Use the FHIR URL itself as the resource scope
        self.resource_scope = f"{fhir_url}/.default"
        
    def _get_token(self) -> str:
        """Get access token using Managed Identity"""
        with self.token_lock:
            if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
                return self.access_token
                
            try:
                # Use AZURE_CLIENT_ID for user-assigned managed identity, fall back to Default
                client_id = os.environ.get('AZURE_CLIENT_ID')
                try:
                    self.credential = ManagedIdentityCredential(client_id=client_id)
                    token = self.credential.get_token(self.resource_scope)
                except Exception:
                    self.credential = DefaultAzureCredential(managed_identity_client_id=client_id)
                    token = self.credential.get_token(self.resource_scope)
                    
                self.access_token = token.token
                # Token typically expires in 1 hour, refresh 5 minutes early
                self.token_expiry = datetime.fromtimestamp(token.expires_on - 300)
                return self.access_token
            except Exception as e:
                print(f"Error getting token: {e}", flush=True)
                raise
    
    def _headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self._get_token()}',
            'Content-Type': 'application/fhir+json',
            'Accept': 'application/fhir+json'
        }
    
    def post_bundle(self, bundle: Dict) -> Dict:
        """Post a transaction bundle to FHIR"""
        response = requests.post(
            self.fhir_url,
            headers=self._headers(),
            json=bundle,
            timeout=300
        )
        if response.status_code not in [200, 201]:
            print(f"Bundle POST failed: {response.status_code} - {response.text[:500]}", flush=True)
        response.raise_for_status()
        return response.json()
    
    def post_resource(self, resource: Dict) -> Dict:
        """Post a single resource to FHIR"""
        resource_type = resource['resourceType']
        response = requests.post(
            f"{self.fhir_url}/{resource_type}",
            headers=self._headers(),
            json=resource,
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    
    def put_resource(self, resource: Dict, resource_id: str) -> Dict:
        """Put (update/create) a resource with specific ID"""
        resource_type = resource['resourceType']
        response = requests.put(
            f"{self.fhir_url}/{resource_type}/{resource_id}",
            headers=self._headers(),
            json=resource,
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    
    def search(self, resource_type: str, params: Dict = None) -> List[Dict]:
        """Search for resources"""
        response = requests.get(
            f"{self.fhir_url}/{resource_type}",
            headers=self._headers(),
            params=params or {},
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        return result.get('entry', [])
    
    def get_count(self, resource_type: str) -> int:
        """Get count of resources"""
        response = requests.get(
            f"{self.fhir_url}/{resource_type}",
            headers=self._headers(),
            params={'_summary': 'count'},
            timeout=60
        )
        response.raise_for_status()
        return response.json().get('total', 0)

    def bulk_delete_all(self) -> None:
        """Delete all resources before an authoritative replacement load."""
        headers = self._headers()
        headers['Prefer'] = 'respond-async'
        response = requests.delete(f"{self.fhir_url}/$bulk-delete", headers=headers, timeout=120)
        if response.status_code not in (200, 202, 204):
            raise RuntimeError(f"FHIR bulk delete failed: {response.status_code} {response.text[:500]}")
        poll_url = response.headers.get('Content-Location') or response.headers.get('Location')
        if response.status_code == 202 and poll_url:
            for _ in range(180):
                poll = requests.get(poll_url, headers=self._headers(), timeout=60)
                if poll.status_code in (200, 204):
                    return
                if poll.status_code not in (202, 201):
                    raise RuntimeError(f"FHIR bulk delete polling failed: {poll.status_code} {poll.text[:500]}")
                time.sleep(5)
            raise TimeoutError("FHIR bulk delete did not complete within 15 minutes")

    def assert_counts(self, expected: Dict[str, int]) -> None:
        mismatches = []
        for resource_type, expected_count in sorted(expected.items()):
            if resource_type == 'Organization':
                continue  # Provider bootstrap intentionally adds organizations.
            actual = self.get_count(resource_type)
            if actual != expected_count:
                mismatches.append(f"{resource_type}: expected {expected_count}, got {actual}")
        for resource_type, expected_count in [('Device', DEVICE_COUNT), ('Basic', DEVICE_COUNT)]:
            actual = self.get_count(resource_type)
            if actual != expected_count:
                mismatches.append(f"{resource_type}: expected {expected_count}, got {actual}")
        if mismatches:
            raise RuntimeError("Canonical FHIR count validation failed: " + "; ".join(mismatches))


def calculate_age(birth_date_str: str, as_of: Optional[date] = None) -> int:
    """Calculate age at a deterministic fixture date when supplied."""
    try:
        birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
        reference_date = as_of or date.today()
        return reference_date.year - birth_date.year - ((reference_date.month, reference_date.day) < (birth_date.month, birth_date.day))
    except (TypeError, ValueError):
        return 0


def is_pediatric(patient: Dict, as_of: Optional[date] = None) -> bool:
    """Check if patient is under 21 at the fixture reference date."""
    birth_date = patient.get('birthDate', '')
    return bool(birth_date) and calculate_age(birth_date, as_of) < 21


def has_qualifying_condition(bundle: Dict) -> bool:
    """Check if patient bundle has a qualifying condition for home monitoring
    
    Supports both ICD-10 codes (used by some EHRs) and SNOMED CT codes (used by Synthea)
    """
    # Get qualifying codes from registry - support both formats
    qualifying_icd10 = []
    qualifying_snomed = []
    
    qc = DEVICE_REGISTRY.get('qualifyingConditions', {})
    
    # Support old format (codes) and new format (icd10/snomed)
    if 'codes' in qc:
        qualifying_icd10 = [c['code'] for c in qc['codes']]
    if 'icd10' in qc:
        qualifying_icd10 = [c['code'] for c in qc['icd10']]
    if 'snomed' in qc:
        qualifying_snomed = [c['code'] for c in qc['snomed']]
    
    for entry in bundle.get('entry', []):
        resource = entry.get('resource', {})
        if resource.get('resourceType') == 'Condition':
            code = resource.get('code', {})
            for coding in code.get('coding', []):
                code_value = coding.get('code', '')
                system = coding.get('system', '')
                
                # Check SNOMED codes (exact match)
                if 'snomed' in system.lower() and code_value in qualifying_snomed:
                    return True
                
                # Check ICD-10 codes (prefix match for hierarchical codes)
                if 'icd' in system.lower():
                    for qc in qualifying_icd10:
                        if code_value.startswith(qc):
                            return True
                
                # Also check if no system specified - try prefix match against ICD-10
                if not system:
                    for qc in qualifying_icd10:
                        if code_value.startswith(qc):
                            return True
    return False


def get_patient_from_bundle(bundle: Dict) -> Optional[Dict]:
    """Extract Patient resource from bundle"""
    for entry in bundle.get('entry', []):
        resource = entry.get('resource', {})
        if resource.get('resourceType') == 'Patient':
            return resource
    return None


def get_patient_managing_org(bundle: Dict) -> Optional[str]:
    """Get the managing organization from patient encounters"""
    for entry in bundle.get('entry', []):
        resource = entry.get('resource', {})
        if resource.get('resourceType') == 'Encounter':
            service_provider = resource.get('serviceProvider', {})
            ref = service_provider.get('reference', '')
            if ref:
                return ref.split('/')[-1] if '/' in ref else ref
    return None


def is_choa_patient(bundle: Dict) -> bool:
    """Check if patient is associated with Children's Healthcare of Atlanta"""
    org_id = get_patient_managing_org(bundle)
    if org_id:
        for choa_id in CHOA_ORG_IDS:
            if choa_id in org_id.lower():
                return True
    return False


def create_device_resource(device_info: Dict) -> Dict:
    """Create a FHIR Device resource for a Masimo pulse oximeter"""
    return {
        "resourceType": "Device",
        "id": device_info['id'],
        "identifier": [
            {
                "system": "http://masimo.com/devices",
                "value": device_info['id']
            },
            {
                "system": "http://masimo.com/serial-numbers",
                "value": device_info['serialNumber']
            }
        ],
        "status": "active",
        "manufacturer": device_info['manufacturer'],
        "deviceName": [
            {
                "name": f"Masimo {device_info['model']} Pulse Oximeter",
                "type": "user-friendly-name"
            }
        ],
        "modelNumber": device_info['model'],
        "serialNumber": device_info['serialNumber'],
        "type": {
            "coding": [
                {
                    "system": "http://snomed.info/sct",
                    "code": "706767009",
                    "display": "Pulse oximeter"
                }
            ],
            "text": "Pulse Oximeter"
        },
        "note": [
            {
                "text": "Measures: SpO2 (oxygen saturation), heart rate, perfusion index"
            }
        ],
        "safety": [
            {
                "coding": [
                    {
                        "system": "urn:oid:2.16.840.1.113883.3.26.1.1",
                        "code": "C113844",
                        "display": "Labeling does not contain latex warning"
                    }
                ]
            }
        ]
    }


def create_device_association(device_id: str, patient_reference: str, patient_name: str, start_date: Optional[str] = None) -> Dict:
    """Create a DeviceAssociation linking a device to a patient (FHIR R5 style, R4 compatible)"""
    # Note: In FHIR R4, this would typically be modeled differently
    # Using a custom extension or the Device.patient field
    # For R4 compatibility, we'll use a Basic resource with extensions
    return {
        "resourceType": "Basic",
        "id": f"device-assoc-{device_id}",
        "meta": {
            "profile": ["http://example.org/StructureDefinition/device-association"]
        },
        "code": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/basic-resource-type",
                    "code": "device-assoc",
                    "display": "Device Association"
                }
            ]
        },
        "subject": {
            "reference": patient_reference,
            "display": patient_name
        },
        "extension": [
            {
                "url": "http://example.org/StructureDefinition/associated-device",
                "valueReference": {
                    "reference": f"Device/{device_id}",
                    "display": f"Masimo Radius-7 ({device_id})"
                }
            },
            {
                "url": "http://example.org/StructureDefinition/association-status",
                "valueCode": "active"
            },
            {
                "url": "http://example.org/StructureDefinition/association-period",
                "valuePeriod": {
                    "start": start_date or datetime.now().strftime('%Y-%m-%d')
                }
            }
        ]
    }


def upload_providers(client: FHIRClient) -> None:
    """Upload every configured provider organization or fail."""
    for item in ATLANTA_PROVIDERS.get('entry', []):
        resource = item.get('resource', {})
        if resource.get('resourceType') == 'Organization':
            client.put_resource(resource, resource['id'])


def upload_devices(client: FHIRClient) -> None:
    """Upload every configured Masimo device or fail."""
    devices = DEVICE_REGISTRY['devices'][:DEVICE_COUNT]
    if len(devices) != DEVICE_COUNT:
        raise RuntimeError(f"Device registry has {len(devices)} devices; expected {DEVICE_COUNT}")
    for device_info in devices:
        client.put_resource(create_device_resource(device_info), device_info['id'])
    print(f"Uploaded {len(devices)} devices", flush=True)


def get_blob_service_client():
    """Get blob service client with user-assigned managed identity"""
    client_id = os.environ.get('AZURE_CLIENT_ID')
    try:
        credential = ManagedIdentityCredential(client_id=client_id)
        return BlobServiceClient(
            account_url=f"https://{STORAGE_ACCOUNT}.blob.core.windows.net",
            credential=credential
        )
    except Exception:
        credential = DefaultAzureCredential(managed_identity_client_id=client_id)
        return BlobServiceClient(
            account_url=f"https://{STORAGE_ACCOUNT}.blob.core.windows.net",
            credential=credential
        )

def load_canonical_manifest() -> Optional[Dict[str, Any]]:
    """Load the optional authoritative fixture manifest from blob storage."""
    blob_service = get_blob_service_client()
    blob_client = blob_service.get_blob_client(CONTAINER_NAME, CANONICAL_MANIFEST_BLOB)
    try:
        manifest = json.loads(blob_client.download_blob().readall())
    except Exception as exc:
        if 'BlobNotFound' in str(exc) or '404' in str(exc):
            return None
        raise
    if manifest.get('syntheticOnly') is not True:
        raise RuntimeError('Canonical fixture manifest must declare syntheticOnly=true')
    if int(manifest.get('patientCount', 0)) != DEVICE_COUNT:
        raise RuntimeError(f"Canonical fixture patientCount must equal DEVICE_COUNT ({DEVICE_COUNT})")
    return manifest


def is_synthea_bundle_blob_name(blob_name: str) -> bool:
    """Return true only for patient transaction bundle blobs."""
    return (
        blob_name.endswith('.json')
        and not blob_name.startswith(('_control/', 'hospitalInformation', 'practitionerInformation'))
        and blob_name != 'device-associations.json'
    )


def stream_synthea_bundles(manifest: Optional[Dict[str, Any]] = None, batch_size: int = 50, max_retries: int = 12, retry_delay: int = 10):
    """Stream verified bundle blobs; any malformed or missing blob is fatal."""
    print("Streaming Synthea bundles from blob storage...", flush=True)
    json_blobs = None
    container_client = None
    for attempt in range(max_retries):
        try:
            container_client = get_blob_service_client().get_container_client(CONTAINER_NAME)
            blobs = list(container_client.list_blobs())
            json_blobs = [blob for blob in blobs if is_synthea_bundle_blob_name(blob.name)]
            break
        except Exception as exc:
            error_text = str(exc).lower()
            if attempt < max_retries - 1 and any(token in error_text for token in ('authorization', 'permission', '403')):
                time.sleep(retry_delay)
                continue
            raise
    if json_blobs is None or container_client is None:
        raise RuntimeError("Failed to list Synthea blobs")
    expected_files = manifest.get('files', {}) if manifest else None
    actual_names = {blob.name for blob in json_blobs}
    if expected_files is not None and actual_names != set(expected_files):
        raise RuntimeError(f"Canonical blob set mismatch: missing={sorted(set(expected_files) - actual_names)}, extra={sorted(actual_names - set(expected_files))}")

    batch = []
    downloaded_count = 0
    for blob in sorted(json_blobs, key=lambda item: item.name):
        content = container_client.get_blob_client(blob.name).download_blob().readall()
        if expected_files is not None:
            actual_hash = hashlib.sha256(content).hexdigest()
            if actual_hash != expected_files[blob.name]:
                raise RuntimeError(f"Canonical fixture checksum mismatch for {blob.name}")
        bundle = json.loads(content)
        if bundle.get('resourceType') != 'Bundle' or bundle.get('type') != 'transaction':
            raise RuntimeError(f"Blob {blob.name} is not a transaction Bundle")
        batch.append(bundle)
        downloaded_count += 1
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
    expected_count = int(manifest.get('patientCount', downloaded_count)) if manifest else downloaded_count
    if downloaded_count != expected_count:
        raise RuntimeError(f"Expected {expected_count} patient bundles, streamed {downloaded_count}")
    print(f"Streamed {downloaded_count} verified FHIR bundles", flush=True)


def is_conditional_reference(ref: str) -> bool:
    """Check if a reference is a conditional reference (contains ?)"""
    return isinstance(ref, str) and '?' in ref


def transform_urn_uuid_reference(ref: str, full_url_ref_map: Dict[str, str] = None) -> str:
    """Transform urn:uuid references to typed direct FHIR references.

    HDS downstream transforms require ResourceType/id references. A bare UUID is
    syntactically accepted by some FHIR stores but flattens to null in HDS Silver,
    which breaks OMOP/CMA joins. Unknown transaction URNs are preserved instead of
    being degraded to a bare id.
    """
    if not isinstance(ref, str):
        return ref
    if full_url_ref_map and ref in full_url_ref_map:
        return full_url_ref_map[ref]
    if ref.startswith('urn:uuid:'):
        return ref
    return ref


def extract_conditional_refs_from_resource(obj: Any, refs: set) -> None:
    """Recursively extract all conditional references from a resource."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == 'reference' and isinstance(value, str) and is_conditional_reference(value):
                refs.add(value)
            else:
                extract_conditional_refs_from_resource(value, refs)
    elif isinstance(obj, list):
        for item in obj:
            extract_conditional_refs_from_resource(item, refs)


def create_practitioner_from_npi(npi: str) -> Dict:
    """Create a minimal Practitioner resource from an NPI number."""
    import hashlib
    # Generate a deterministic UUID from the NPI
    uuid = hashlib.md5(f"practitioner-npi-{npi}".encode()).hexdigest()
    uuid_formatted = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:32]}"
    
    return {
        "resourceType": "Practitioner",
        "id": uuid_formatted,
        "identifier": [
            {
                "system": "http://hl7.org/fhir/sid/us-npi",
                "value": npi
            }
        ],
        "active": True,
        "name": [
            {
                "use": "official",
                "family": f"Provider-{npi[-4:]}",
                "given": ["Healthcare"]
            }
        ]
    }


def fetch_existing_locations(client: 'FHIRClient') -> Dict[str, str]:
    """Fetch all existing Location resources from FHIR and build a reference cache.
    
    Returns a dict mapping conditional reference strings to direct references:
    {"Location?identifier=system|value": "Location/resource-id"}
    """
    print("Checking FHIR server for existing Location resources...", flush=True)
    
    location_cache: Dict[str, str] = {}
    try:
        entries = client.search('Location', {'_count': '1000'})
        
        for entry in entries:
            resource = entry.get('resource', {})
            resource_id = resource.get('id', '')
            if not resource_id:
                continue
            
            for identifier in resource.get('identifier', []):
                system = identifier.get('system', '')
                value = identifier.get('value', '')
                if system and value:
                    conditional_ref = f"Location?identifier={system}|{value}"
                    location_cache[conditional_ref] = f"Location/{resource_id}"
        
        if location_cache:
            print(f"  Found {len(location_cache)} existing Locations in FHIR — will reuse", flush=True)
        else:
            print(f"  No existing Locations found — will create from Synthea references", flush=True)
    except Exception as e:
        print(f"  Warning: Could not query existing Locations: {e}", flush=True)
        print(f"  Will create Location stubs as needed", flush=True)
    
    return location_cache


def create_location_from_ref(location_ref: str) -> Optional[Dict]:
    """Create an enriched Location resource from a conditional reference.
    
    Each Location stub is assigned a real Atlanta-area hospital address and
    GPS coordinates (round-robin) so the Silver Lakehouse Location table
    has usable data for map visualizations.
    """
    import hashlib
    import urllib.parse
    
    # Real Atlanta hospital locations with addresses + GPS coordinates
    ATLANTA_HOSPITALS = [
        {"name": "Emory University Hospital", "line": "1364 Clifton Road NE", "city": "Atlanta", "state": "GA", "postalCode": "30322", "lat": 33.7916, "lng": -84.3222, "org": "Organization/emory-university-hospital"},
        {"name": "Piedmont Atlanta Hospital", "line": "1968 Peachtree Road NW", "city": "Atlanta", "state": "GA", "postalCode": "30309", "lat": 33.8121, "lng": -84.3860, "org": "Organization/piedmont-atlanta-hospital"},
        {"name": "Grady Memorial Hospital", "line": "80 Jesse Hill Jr Drive SE", "city": "Atlanta", "state": "GA", "postalCode": "30303", "lat": 33.7545, "lng": -84.3830, "org": "Organization/grady-memorial-hospital"},
        {"name": "Northside Hospital Atlanta", "line": "1000 Johnson Ferry Road NE", "city": "Atlanta", "state": "GA", "postalCode": "30342", "lat": 33.8789, "lng": -84.3589, "org": "Organization/northside-hospital"},
        {"name": "WellStar Kennestone Hospital", "line": "677 Church Street NE", "city": "Marietta", "state": "GA", "postalCode": "30060", "lat": 33.9527, "lng": -84.5197, "org": "Organization/wellstar-kennestone-hospital"},
        {"name": "Children's Healthcare at Egleston", "line": "1405 Clifton Road NE", "city": "Atlanta", "state": "GA", "postalCode": "30322", "lat": 33.7881, "lng": -84.3217, "org": "Organization/choa-egleston"},
        {"name": "Children's Healthcare at Scottish Rite", "line": "1001 Johnson Ferry Road NE", "city": "Atlanta", "state": "GA", "postalCode": "30342", "lat": 33.8790, "lng": -84.3575, "org": "Organization/choa-scottish-rite"},
        {"name": "Emory Saint Joseph's Hospital", "line": "5665 Peachtree Dunwoody Road NE", "city": "Atlanta", "state": "GA", "postalCode": "30342", "lat": 33.8932, "lng": -84.3362, "org": "Organization/emory-saint-josephs"},
        {"name": "Emory Midtown Hospital", "line": "550 Peachtree Street NE", "city": "Atlanta", "state": "GA", "postalCode": "30308", "lat": 33.7654, "lng": -84.3860, "org": "Organization/emory-midtown"},
        {"name": "Atlanta VA Medical Center", "line": "1670 Clairmont Road", "city": "Decatur", "state": "GA", "postalCode": "30033", "lat": 33.7851, "lng": -84.3076, "org": "Organization/atlanta-va-medical-center"},
        {"name": "Hughes Spalding Hospital", "line": "35 Jesse Hill Jr Drive SE", "city": "Atlanta", "state": "GA", "postalCode": "30303", "lat": 33.7543, "lng": -84.3807, "org": "Organization/choa-hughes-spalding"},
    ]
    
    # Parse the conditional reference to extract identifier
    # Format: Location?identifier=system|value
    if '?' not in location_ref:
        return None
    
    parts = location_ref.split('?', 1)
    if len(parts) != 2:
        return None
    
    params = urllib.parse.parse_qs(parts[1])
    identifier_value = params.get('identifier', [''])[0]
    
    if not identifier_value or '|' not in identifier_value:
        return None
    
    system, value = identifier_value.split('|', 1)
    
    # Generate deterministic UUID
    uuid = hashlib.md5(f"location-{system}-{value}".encode()).hexdigest()
    uuid_formatted = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:32]}"
    
    # Deterministic hospital assignment based on identifier hash
    hospital_index = int(uuid[:8], 16) % len(ATLANTA_HOSPITALS)
    hospital = ATLANTA_HOSPITALS[hospital_index]
    
    return {
        "resourceType": "Location",
        "id": uuid_formatted,
        "identifier": [
            {
                "system": system,
                "value": value
            }
        ],
        "status": "active",
        "name": hospital["name"],
        "address": {
            "line": [hospital["line"]],
            "city": hospital["city"],
            "state": hospital["state"],
            "postalCode": hospital["postalCode"],
            "country": "US"
        },
        "position": {
            "longitude": hospital["lng"],
            "latitude": hospital["lat"]
        },
        "managingOrganization": {
            "reference": hospital["org"]
        }
    }


def create_organization_from_ref(org_ref: str) -> Optional[Dict]:
    """Create a minimal Organization resource from a conditional reference."""
    import hashlib
    import urllib.parse
    
    # Parse the conditional reference to extract identifier
    # Format: Organization?identifier=system|value
    if '?' not in org_ref:
        return None
    
    parts = org_ref.split('?', 1)
    if len(parts) != 2:
        return None
    
    params = urllib.parse.parse_qs(parts[1])
    identifier_value = params.get('identifier', [''])[0]
    
    if not identifier_value or '|' not in identifier_value:
        return None
    
    system, value = identifier_value.split('|', 1)
    
    # Generate deterministic UUID
    uuid = hashlib.md5(f"organization-{system}-{value}".encode()).hexdigest()
    uuid_formatted = f"{uuid[:8]}-{uuid[8:12]}-{uuid[12:16]}-{uuid[16:20]}-{uuid[20:32]}"
    
    return {
        "resourceType": "Organization",
        "id": uuid_formatted,
        "identifier": [
            {
                "system": system,
                "value": value
            }
        ],
        "active": True,
        "name": f"Organization {value[-8:] if len(value) > 8 else value}"
    }


def inject_referenced_resources(bundle: Dict, existing_locations: Dict[str, str] = None) -> Dict:
    """Scan bundle for conditional references and create missing resources.
    
    This handles the case where Synthea bundles reference Practitioners, Locations,
    and Organizations via conditional references, but don't include those resources 
    in the bundle. We create minimal stub resources so the references can resolve.
    
    If existing_locations is provided, Location stubs are skipped for references
    that already have a corresponding resource in the FHIR server.
    """
    # Collect all conditional references in the bundle
    conditional_refs = set()
    for entry in bundle.get('entry', []):
        resource = entry.get('resource', {})
        extract_conditional_refs_from_resource(resource, conditional_refs)
    
    # Group by resource type
    practitioner_npis = set()
    location_refs = set()
    organization_refs = set()
    
    for ref in conditional_refs:
        if ref.startswith('Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|'):
            # Extract NPI
            npi = ref.split('|')[-1]
            practitioner_npis.add(npi)
        elif ref.startswith('Location?'):
            location_refs.add(ref)
        elif ref.startswith('Organization?'):
            organization_refs.add(ref)
    
    # Create new entries for missing resources
    new_entries = []
    
    # Create Organization resources (first, as others may reference them)
    for org_ref in organization_refs:
        org = create_organization_from_ref(org_ref)
        if org:
            new_entries.append({
                'fullUrl': f"urn:uuid:{org['id']}",
                'resource': org
            })
    
    # Create Practitioner resources
    for npi in practitioner_npis:
        practitioner = create_practitioner_from_npi(npi)
        new_entries.append({
            'fullUrl': f"urn:uuid:{practitioner['id']}",
            'resource': practitioner
        })
    
    # Create Location resources (skip any that already exist in FHIR)
    skipped_locations = 0
    for loc_ref in location_refs:
        if existing_locations and loc_ref in existing_locations:
            skipped_locations += 1
            continue
        location = create_location_from_ref(loc_ref)
        if location:
            new_entries.append({
                'fullUrl': f"urn:uuid:{location['id']}",
                'resource': location
            })
    if skipped_locations:
        pass  # Logged at batch level to avoid per-bundle noise
    
    # Add new entries at the beginning of the bundle (they need to be processed first)
    if new_entries:
        bundle['entry'] = new_entries + bundle.get('entry', [])
    
    return bundle


def build_conditional_reference_map(bundle: Dict) -> Dict[str, str]:
    """Build a mapping from conditional references to direct UUID references.
    
    Scans all entries in the bundle to find resources with identifiers.
    Creates mappings like:
      'Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|9999801290' -> 'Practitioner/abc-123-uuid'
    """
    ref_map = {}
    
    for entry in bundle.get('entry', []):
        resource = entry.get('resource', {})
        resource_type = resource.get('resourceType', '')
        full_url = entry.get('fullUrl', '')
        
        # Get the UUID for this resource
        if full_url.startswith('urn:uuid:'):
            resource_uuid = full_url.replace('urn:uuid:', '')
        elif '/' in full_url:
            resource_uuid = full_url.split('/')[-1]
        else:
            resource_uuid = resource.get('id', '')
        
        if not resource_uuid:
            continue
        
        # For each identifier on this resource, create a conditional reference mapping
        for identifier in resource.get('identifier', []):
            system = identifier.get('system', '')
            value = identifier.get('value', '')
            if system and value:
                # Create the conditional reference format
                conditional_ref = f"{resource_type}?identifier={system}|{value}"
                # Map to direct reference
                direct_ref = f"{resource_type}/{resource_uuid}"
                ref_map[conditional_ref] = direct_ref
    
    return ref_map

def build_full_url_reference_map(bundle: Dict) -> Dict[str, str]:
    """Map transaction fullUrl values to typed FHIR direct references."""
    ref_map = {}
    for entry in bundle.get('entry', []):
        resource = entry.get('resource', {})
        resource_type = resource.get('resourceType', '')
        full_url = entry.get('fullUrl', '')
        resource_id = resource.get('id', '')

        if not resource_type or not resource_id or not full_url:
            continue
        ref_map[full_url] = f"{resource_type}/{resource_id}"
    return ref_map



def transform_conditional_to_direct(obj: Any, ref_map: Dict[str, str]) -> Any:
    """Recursively transform conditional references to direct references using the map."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == 'reference' and isinstance(value, str) and is_conditional_reference(value):
                # Look up in ref_map
                if value in ref_map:
                    result[key] = ref_map[value]
                else:
                    # Keep the conditional reference if we can't resolve it
                    result[key] = value
            else:
                result[key] = transform_conditional_to_direct(value, ref_map)
        return result
    elif isinstance(obj, list):
        return [transform_conditional_to_direct(item, ref_map) for item in obj]
    else:
        return obj


def transform_references_in_resource(obj: Any, full_url_ref_map: Dict[str, str] = None) -> Any:
    """Recursively transform transaction URN references to typed direct references."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == 'reference' and isinstance(value, str):
                result[key] = transform_urn_uuid_reference(value, full_url_ref_map)
            else:
                result[key] = transform_references_in_resource(value, full_url_ref_map)
        return result
    elif isinstance(obj, list):
        return [transform_references_in_resource(item, full_url_ref_map) for item in obj]
    else:
        return obj


def has_any_conditional_reference(resource: Dict) -> bool:
    """Recursively check if a resource or any of its children has conditional references"""
    if isinstance(resource, dict):
        for key, value in resource.items():
            if key == 'reference' and is_conditional_reference(value):
                return True
            if has_any_conditional_reference(value):
                return True
    elif isinstance(resource, list):
        for item in resource:
            if has_any_conditional_reference(item):
                return True
    return False


def reorder_bundle_entries(bundle: Dict) -> Dict:
    """Reorder bundle entries so that referenced resources come first.
    Order: Organization -> Practitioner -> Location -> Patient -> everything else
    This ensures conditional references can resolve properly."""
    
    entries = bundle.get('entry', [])
    
    # Define processing order - referenced resources first
    type_order = {
        'Organization': 0,
        'Practitioner': 1,
        'PractitionerRole': 2,
        'Location': 3,
        'Patient': 4,
    }
    
    def get_order(entry):
        resource_type = entry.get('resource', {}).get('resourceType', '')
        return type_order.get(resource_type, 99)
    
    # Sort entries by type order
    sorted_entries = sorted(entries, key=get_order)
    bundle['entry'] = sorted_entries
    return bundle


def split_bundle_entries(bundle: Dict, max_entries: int = 400) -> List[Dict]:
    """Split a bundle into smaller bundles if it exceeds max entries.
    Uses 400 to stay safely under FHIR's 500 limit."""
    entries = bundle.get('entry', [])
    
    if len(entries) <= max_entries:
        return [bundle]
    
    # Separate entries by type - foundational resources must come first
    # Order: Organization, Practitioner, PractitionerRole, Location, Patient, then others
    type_order = {'Organization': 0, 'Practitioner': 1, 'PractitionerRole': 2, 'Location': 3, 'Patient': 4}
    
    def get_order(e):
        rt = e.get('resource', {}).get('resourceType', '')
        return type_order.get(rt, 99)
    
    # Sort all entries by type order
    sorted_entries = sorted(entries, key=get_order)
    
    # Find where foundational resources end (everything with order < 99)
    foundational = [e for e in sorted_entries if get_order(e) < 99]
    other_entries = [e for e in sorted_entries if get_order(e) >= 99]
    
    bundles = []
    # First bundle gets foundational resources + first batch of other entries
    # Subsequent bundles only get other entries (foundational resources already uploaded)
    for i in range(0, max(1, len(other_entries)), max_entries - len(foundational)):
        chunk = other_entries[i:i + max_entries - len(foundational)]
        new_bundle = {
            'resourceType': 'Bundle',
            'type': bundle.get('type', 'transaction'),
            'entry': foundational + chunk if i == 0 else chunk
        }
        bundles.append(new_bundle)
    
    return bundles


def process_synthea_bundles(client: FHIRClient, existing_locations: Dict[str, str] = None, manifest: Optional[Dict[str, Any]] = None) -> List[Dict]:
    """Transform and upload every bundle; any skipped or failed patient is fatal."""
    max_workers = 10
    patients: List[Dict] = []
    state_lock = threading.Lock()
    as_of = date.fromisoformat(manifest['asOfDate']) if manifest else None

    def process_bundle_worker(bundle: Dict[str, Any]) -> Dict[str, Any]:
        patient = get_patient_from_bundle(bundle)
        if not patient:
            raise RuntimeError("Canonical bundle has no Patient resource")
        if is_choa_patient(bundle) and not is_pediatric(patient, as_of):
            raise RuntimeError(f"CHOA patient {patient.get('id')} is not pediatric at fixture asOfDate")
        bundle = inject_referenced_resources(bundle, existing_locations)
        bundle = reorder_bundle_entries(bundle)
        ref_map = build_conditional_reference_map(bundle)
        if existing_locations:
            ref_map.update(existing_locations)
        full_url_ref_map = build_full_url_reference_map(bundle)
        ref_map.update(full_url_ref_map)
        bundle['type'] = 'transaction'
        for item in bundle.get('entry', []):
            resource = item.get('resource', {})
            resource_type = resource.get('resourceType', '')
            full_url = item.get('fullUrl', '')
            if full_url.startswith('urn:uuid:'):
                resource_id = full_url.removeprefix('urn:uuid:')
            elif '/' in full_url:
                resource_id = full_url.split('/')[-1]
            else:
                resource_id = resource.get('id', '')
            if not resource_type or not resource_id:
                raise RuntimeError(f"Resource missing type/id in patient bundle {patient.get('id')}")
            resource['id'] = resource_id
            transformed = transform_references_in_resource(resource, full_url_ref_map)
            transformed = transform_conditional_to_direct(transformed, ref_map)
            item['resource'] = transformed
            item['request'] = {'method': 'PUT', 'url': f"{resource_type}/{resource_id}"}
        for sub_bundle in split_bundle_entries(bundle, max_entries=400):
            client.post_bundle(sub_bundle)
        names = patient.get('name', [])
        name = names[0] if names else {}
        patient_name = name.get('text') or f"{' '.join(name.get('given', []))} {name.get('family', '')}".strip()
        return {
            'id': patient['id'],
            'name': patient_name,
            'birthDate': patient.get('birthDate', ''),
            'isPediatric': is_pediatric(patient, as_of),
            'hasQualifyingCondition': has_qualifying_condition(bundle),
        }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for batch in stream_synthea_bundles(manifest=manifest, batch_size=50):
            futures = [executor.submit(process_bundle_worker, bundle) for bundle in batch]
            for future in as_completed(futures):
                result = future.result()
                with state_lock:
                    patients.append(result)
    expected = int(manifest.get('patientCount', len(patients))) if manifest else len(patients)
    if len(patients) != expected:
        raise RuntimeError(f"Uploaded {len(patients)} patients; expected {expected}")
    print(f"Uploaded {len(patients)} patient bundles", flush=True)
    return sorted(patients, key=lambda patient: patient['id'])


def build_device_patient_assignments(devices: List[Dict], patients: List[Dict], device_count: int) -> List[tuple]:
    """Assign every selected telemetry device, cycling patients when necessary.

    Reused environments can legitimately have fewer patients than devices. Leaving
    the remaining devices unassigned breaks alert, location, and dashboard joins.
    Multiple monitoring devices per patient are valid for this synthetic demo.
    """
    if not patients or device_count <= 0:
        return []
    selected_devices = devices[:device_count]
    return [(device, patients[index % len(patients)]) for index, device in enumerate(selected_devices)]


def create_device_associations(client: FHIRClient, patients: List[Dict], manifest: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    """Create all associations from the explicit manifest when available."""
    patients_by_id = {patient['id']: patient for patient in patients}
    devices_by_id = {device['id']: device for device in DEVICE_REGISTRY['devices'][:DEVICE_COUNT]}
    if manifest:
        requested = manifest.get('deviceAssignments', [])
        if len(requested) != DEVICE_COUNT:
            raise RuntimeError(f"Canonical manifest must define {DEVICE_COUNT} device assignments")
        assignments = []
        for item in requested:
            device = devices_by_id.get(item.get('deviceId'))
            patient = patients_by_id.get(item.get('patientId'))
            if not device or not patient:
                raise RuntimeError(f"Invalid canonical device assignment: {item}")
            expected_name = item.get('patientName')
            if expected_name and expected_name != patient['name']:
                raise RuntimeError(f"Canonical patient name mismatch for {patient['id']}")
            assignments.append((device, patient))
    else:
        assignments = build_device_patient_assignments(list(devices_by_id.values()), patients, DEVICE_COUNT)
    if len(assignments) != DEVICE_COUNT:
        raise RuntimeError(f"Expected {DEVICE_COUNT} device assignments, got {len(assignments)}")

    association_mapping: List[Dict[str, str]] = []
    for device_info, patient in assignments:
        association = create_device_association(device_info['id'], f"Patient/{patient['id']}", patient['name'], manifest.get('asOfDate') if manifest else None)
        client.put_resource(association, association['id'])
        association_mapping.append({"patientId": patient['id'], "deviceId": device_info['id'], "patientName": patient['name']})
    blob_client = get_blob_service_client().get_blob_client(CONTAINER_NAME, "device-associations.json")
    blob_client.upload_blob(json.dumps(association_mapping, indent=2), overwrite=True)
    print(f"Created and persisted {len(association_mapping)} device associations", flush=True)
    return association_mapping


def print_summary(client: FHIRClient) -> None:
    """Print summary of FHIR data"""
    print("\n=== FHIR DATA SUMMARY ===", flush=True)
    
    resource_types = ['Patient', 'Organization', 'Practitioner', 'Location',
                      'Encounter', 'Condition', 'Observation', 'Device', 'Basic']
    
    for rt in resource_types:
        try:
            count = client.get_count(rt)
            print(f"  {rt}: {count}", flush=True)
        except Exception as e:
            print(f"  {rt}: Error - {e}", flush=True)


def main():
    if not FHIR_SERVICE_URL:
        raise RuntimeError("FHIR_SERVICE_URL is required")
    client = FHIRClient(FHIR_SERVICE_URL)
    for attempt in range(12):
        try:
            client.get_count('Patient')
            break
        except Exception:
            if attempt == 11:
                raise
            time.sleep(10)

    manifest = load_canonical_manifest()
    if manifest:
        print(f"Authoritative canonical fixture {manifest.get('fixtureVersion')} detected", flush=True)
    if manifest or RESEED_DATA:
        if RESEED_DATA and not manifest:
            print("Authoritative data reseed requested", flush=True)
        client.bulk_delete_all()
    existing_locations = fetch_existing_locations(client)
    upload_providers(client)
    upload_devices(client)
    patients = process_synthea_bundles(client, existing_locations, manifest)
    create_device_associations(client, patients, manifest)

    if manifest:
        expected = manifest.get('expectedUniqueResourceCounts', {})
        last_error = None
        for _ in range(30):
            try:
                client.assert_counts(expected)
                last_error = None
                break
            except RuntimeError as exc:
                last_error = exc
                time.sleep(10)
        if last_error:
            raise last_error
        print("Canonical FHIR resource counts validated", flush=True)
    print_summary(client)
    print("\n=== FHIR LOADER COMPLETE ===", flush=True)


if __name__ == '__main__':
    main()
