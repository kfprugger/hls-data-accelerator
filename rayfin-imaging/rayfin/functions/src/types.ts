/**
 * Function schema types for RayfinClient.
 *
 * AUTO-GENERATED — do not edit manually.
 * Re-generated automatically when function source files change.
 *
 * If this file is not updating automatically, run:
 *   rayfin dev functions apply
 *
 * The schema is a closed object type: only the function names listed
 * below are accepted by RayfinClient.functions.<name>.invoke(...).
 * Adding, renaming, or changing the signature of a udf.func() call
 * regenerates this file and surfaces type errors at every consumer.
 *
 * IMPORTANT: This file must NOT import any Node.js packages — it is
 * resolved by the frontend app's TypeScript compiler.
 */

export type AppFunctionsSchema = {
  getSlideCatalog: {
    input: Record<string, never>;
    output: { title: string; generatedAt: string; slides: { id: string; kind?: undefined | string; license?: undefined | string; channels?: undefined | { id: string; name: string; meaning: string; color: string; visible: boolean; dzi: string; tiles: string; tileCount: number; tilesBytes: number }[]; markersAvailable?: undefined | number; title: string; organ: string; diagnosis: string; blurb: string; project: string; case: string; sourceFile: string; gdcFileId: string; source: string; sourceUrl: string; vendor: null | string; objectivePower: null | number; mpp: null | number; width: number; height: number; levels: number; tileSize: number; overlap: number; format: string; tileCount: number; tilesBytes?: undefined | number; hotspots: { x: number; y: number }[]; rawSizeBytes: number; dzi: string; tiles: string; thumbnail: string; raw: string }[]; lakehouse: { workspaceId: string; workspaceName: string; lakehouseId: string; lakehouseName: string; oneLakePath: string; portalUrl: string }; tileAccess: { mode: 'sas' | 'proxy'; baseUrl: string; query: string; expiresOn: string; reason: string }; servedAt: string };
  };
  getVolumeCatalog: {
    input: Record<string, never>;
    output: { title: string; generatedAt: string; studies: { id: string; category: string; title: string; subtitle: string; modality: string; description: string; source: string; sourceUrl: string; license: string; citation: string; subject: string; patientId?: undefined | string; scanner?: undefined | string; thumbnail: string; rawPath: string; rawFiles: number; rawSizeBytes: number; sizeBytes: number; defaultView: string; defaultClip?: undefined | { on: boolean; depth: number; face: 'front' | 'side' | 'top' }; stats?: undefined | { [k: string]: number }; layers: { id: string; label: string; kind: string; frames4d?: undefined | false | true; file?: undefined | string; frameKey?: undefined | string; lut?: undefined | string; colormap?: undefined | string; calMin?: undefined | number; calMax?: undefined | number; opacity?: undefined | number; visible?: undefined | false | true; unit?: undefined | string; bytes?: undefined | number }[]; defaultCamera?: undefined | { azimuth: number; elevation: number }; defaultPreset?: undefined | string; views?: undefined | string[]; mip?: undefined | { sprite: string; frames: number; cols: number; frameWidth: number; frameHeight: number; label: string; colormap: string; bytes: number }; timeline?: undefined | { label: string; unit: string; initial: number; mode?: undefined | string; fps?: undefined | number; loop?: undefined | false | true; frames: { value: number; label: string; note?: undefined | string; frameIndex?: undefined | number; brainVolumeMl?: undefined | number; layers: { [k: string]: string }; bytes?: undefined | number }[] }; dims: number[]; spacingMm: number[] }[]; lakehouse: { workspaceId: string; workspaceName: string; lakehouseId: string; lakehouseName: string; oneLakePath: string; portalUrl: string }; access: { baseUrl: string; query: string; expiresOn: string; reason: string }; servedAt: string };
  };
  getTiles: {
    input: { slideId: string; paths: string[] };
    output: { path: string; contentType: string; data: string }[];
  };
  getCohort: {
    input: Record<string, never>;
    output: { patients: { patient_id: string; display_name: string; cancer_code: string; cancer_type: string; organ: string; sex: null | string; age_at_diagnosis: null | number; race: null | string; stage: null | string; vital_status: null | string; year_of_diagnosis: null | number; days_to_last_contact: null | number; tmb: null | number; msi_status: null | string; subtype: null | string; drivers: null | string; slide_gigapixels: null | number; radiology_series: number; thumbnailUrl: null | string }[]; provenance: { workspace: string; endpoint: string; database: string; queries: { id: string; silos: ('clinical' | 'genomics' | 'imaging')[]; tables: string[]; rows: number; ms: number }[]; totalMs: number; showcaseSql: string; servedAt: string } };
  };
  getPatient: {
    input: { patientId: string };
    output: { patient: { [k: string]: null | string | number | false | true }; header: { [k: string]: null | string | number | false | true }; diagnoses: { [k: string]: null | string | number | false | true }[]; treatments: { [k: string]: null | string | number | false | true }[]; followUps: { [k: string]: null | string | number | false | true }[]; biomarkers: { [k: string]: null | string | number | false | true }[]; observations: { [k: string]: null | string | number | false | true }[]; encounters: { [k: string]: null | string | number | false | true }[]; conditions: { [k: string]: null | string | number | false | true }[]; medications: { [k: string]: null | string | number | false | true }[]; immunizations: { [k: string]: null | string | number | false | true }[]; allergies: { [k: string]: null | string | number | false | true }[]; procedures: { [k: string]: null | string | number | false | true }[]; careplans: { [k: string]: null | string | number | false | true }[]; report: { text: string; pdfPath: null | string; pdfBytes: null | number; gdcFileId: null | string; source: null | string }; summary: null | { [k: string]: null | string | number | false | true }; profile: null | { [k: string]: null | string | number | false | true }; drivers: { [k: string]: null | string | number | false | true }[]; mutationMap: { chromosomes: string[]; positions: number[]; types: number[]; typeNames: string[] }; mutationCounts: { [k: string]: null | string | number | false | true }[]; segments: { [k: string]: null | string | number | false | true }[]; copyNumber: { [k: string]: null | string | number | false | true }[]; expression: { [k: string]: null | string | number | false | true }[]; immuneCells: { [k: string]: null | string | number | false | true }[]; reference: { [k: string]: null | string | number | false | true }[]; slide: null | { [k: string]: null | string | number | false | true }; slides: { [k: string]: null | string | number | false | true }[]; radiologyStudies: { [k: string]: null | string | number | false | true }[]; radiologySeries: { [k: string]: null | string | number | false | true }[]; access: { slide: { baseUrl: string; query: string; expiresOn: string; scope: string; silo: 'clinical' | 'genomics' | 'imaging'; error?: undefined | string }; radiology: { baseUrl: string; query: string; expiresOn: string; scope: string; silo: 'clinical' | 'genomics' | 'imaging'; error?: undefined | string }; report: { baseUrl: string; query: string; expiresOn: string; scope: string; silo: 'clinical' | 'genomics' | 'imaging'; error?: undefined | string } }; provenance: { workspace: string; endpoint: string; database: string; queries: { id: string; silos: ('clinical' | 'genomics' | 'imaging')[]; tables: string[]; rows: number; ms: number }[]; totalMs: number; showcaseSql: string; servedAt: string } };
  };
  getDataMap: {
    input: Record<string, never>;
    output: { workspace: { id: string; name: string; portalUrl: string }; patient360: { id: string; name: string; portalUrl: string; sqlEndpoint: string; shortcuts: { path: string; name: string; targetItem: string; targetPath: string; silo: null | 'clinical' | 'genomics' | 'imaging' }[]; zeroCopy?: { copiesMade: 0; shortcutCount: number; sourceSilos: string[]; physicalBytesInPatient360: 0 }; error?: undefined | string }; zeroCopy: { copiesMade: 0; shortcutCount: number; sourceSilos: string[]; physicalBytesInPatient360: 0 }; databricksInterop?: null | { timestamp: string; engine: string; statement: string; warehouseId: string; rowCount: number; fabricP360Count?: number; deltaTableVersion?: number; executionTimeMs: number; oneLakeExternalLocation: string; status: string; zeroCopyVerified: boolean }; silos: { silo: 'clinical' | 'genomics' | 'imaging'; id: string; name: string; role: string; portalUrl: string; items: { [k: string]: null | string | number | false | true }[] }[]; provenance: { workspace: string; endpoint: string; database: string; queries: { id: string; silos: ('clinical' | 'genomics' | 'imaging')[]; tables: string[]; rows: number; ms: number }[]; totalMs: number; showcaseSql: string; servedAt: string } };
  };
  getWardFlowCohort: {
    input: Record<string, never>;
    output: { workspaceId: string; workspaceName: string; sqlEndpoint: string; database: string; goldRefreshedAt: null | string; servedAt: string; totalMs: number; subjects: { id: string; initials: string; fullName: null | string; gender: null | string; age: null | number; ageBand: string; careSetting: string; encounterId: string; conditionDisplay: string; attendingRole: null | string; deviceId: null | string; deviceKind: null | string; deviceSerial: null | string; pulseOximeterDeviceId: null | string; refreshedAt: null | string; observations: { [k: string]: null | number }; observedAt: null | string; encounterCount: number; medicationCount: number; imagingStudyCount: number; openCareGaps: number; has3dVolume: boolean; volumeStudyId: null | string }[]; enrollableCount: number };
  };
  getStandardsMapping: {
    input: { patientId: string };
    output: {
      patientId: string;
      patient: { [k: string]: null | string | number | false | true };
      diagnoses: { [k: string]: null | string | number | false | true }[];
      radiologyStudies: { [k: string]: null | string | number | false | true }[];
      radiologySeries: { [k: string]: null | string | number | false | true }[];
      fhir: {
        patientResource: { [k: string]: unknown };
        conditionResource: { [k: string]: unknown };
        mappings: { fhirPath: string; deltaTable: string; deltaColumn: string; description: string }[];
      };
      dicom: {
        tags: { tag: string; name: string; value: null | string | number; mappedTable: string; mappedColumn: string }[];
        mappings: { dicomTag: string; tagName: string; deltaTable: string; deltaColumn: string }[];
      };
    };
  };
};
