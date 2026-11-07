import {
  DataLakeSASPermissions,
  DataLakeServiceClient,
  SASProtocol,
  generateDataLakeSASQueryParameters,
  type UserDelegationKey,
} from '@azure/storage-file-datalake';
import {
  AudienceType,
  UserDataFunctions,
  type RayfinContext,
} from '@microsoft/fabric-user-data-functions';
import sql from 'mssql';

/*
 * Fabric workspace and Lakehouse the app reads its images from. The block between the markers is
 * rewritten by `python scripts/setup_fabric.py --workspace <name>`; do not edit it by hand.
 */
// <lakehouse-config>
const WORKSPACE_ID = '00000000-0000-0000-0000-000000000000';
const WORKSPACE_NAME = 'your-fabric-workspace';
const LAKEHOUSE_ID = '00000000-0000-0000-0000-000000000000';
const LAKEHOUSE_NAME = 'imaging_lakehouse';
// </lakehouse-config>

/*
 * Fabric coordinates for Patient 360 and WardFlow Cardiology. Three silos hold the data; `patient360` holds only
 * OneLake shortcuts to them, and `SQL_SERVER` is the workspace SQL analytics endpoint.
 */
// <fabric-config>
const CLINICAL_LH = '00000000-0000-0000-0000-000000000000';
const GENOMICS_LH = '00000000-0000-0000-0000-000000000000';
const IMAGING_LH = '00000000-0000-0000-0000-000000000000';
const PATIENT360_LH = '00000000-0000-0000-0000-000000000000';
const GOLD_LH = '00000000-0000-0000-0000-000000000000';
const SQL_SERVER = '';
// </fabric-config>

if (/^0{8}-/.test(WORKSPACE_ID) || /^0{8}-/.test(LAKEHOUSE_ID)) {
  console.error('Lakehouse not configured: run `python scripts/setup_fabric.py --workspace <name>` and redeploy.');
}

const ONELAKE_DFS = 'https://onelake.dfs.fabric.microsoft.com';
const ONELAKE_BLOB = 'https://onelake.blob.fabric.microsoft.com';
const FABRIC_API = 'https://api.fabric.microsoft.com/v1';
const FILES_PATH = `${LAKEHOUSE_ID}/Files`;
/** Read-only SAS scopes: the tile pyramids and the browser-ready volumes, never the raw sources. */
const SLIDES_SCOPE = 'slides';
const VOLUMES_SCOPE = 'volumes';
const SAS_LIFETIME_MS = 55 * 60_000;
const SAS_REUSE_MS = 40 * 60_000;
const KEY_REUSE_MS = 40 * 60_000;
const MAX_TILES_PER_CALL = 24;
const PATIENT_ID = /^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$/;

const SILOS = {
  clinical: { id: CLINICAL_LH, name: 'clinical_lakehouse', role: 'EHR and cancer registry' },
  genomics: { id: GENOMICS_LH, name: 'genomics_lakehouse', role: 'Sequencing core' },
  imaging: { id: /^0{8}-/.test(IMAGING_LH) ? LAKEHOUSE_ID : IMAGING_LH, name: 'imaging_lakehouse', role: 'PACS and digital pathology' },
} as const;
const PATIENT360 = { id: PATIENT360_LH, name: 'patient360' };
const GOLD_DATABASE = 'healthcare1_reporting_gold';

export type AppSchema = Record<string, never>;
export type Silo = 'clinical' | 'genomics' | 'imaging';
export type Cell = string | number | boolean | null;
export type Row = Record<string, Cell>;

export type Hotspot = { x: number; y: number };

export type SlideChannel = {
  id: string;
  name: string;
  meaning: string;
  color: string;
  visible: boolean;
  dzi: string;
  tiles: string;
  tileCount: number;
  tilesBytes: number;
};

export type SlideInfo = {
  id: string;
  kind?: string;
  license?: string;
  channels?: SlideChannel[];
  markersAvailable?: number;
  title: string;
  organ: string;
  diagnosis: string;
  blurb: string;
  project: string;
  case: string;
  sourceFile: string;
  gdcFileId: string;
  source: string;
  sourceUrl: string;
  vendor: string | null;
  objectivePower: number | null;
  mpp: number | null;
  width: number;
  height: number;
  levels: number;
  tileSize: number;
  overlap: number;
  format: string;
  tileCount: number;
  tilesBytes?: number;
  hotspots: Hotspot[];
  rawSizeBytes: number;
  dzi: string;
  tiles: string;
  thumbnail: string;
  raw: string;
};

export type TileAccess = {
  mode: 'sas' | 'proxy';
  baseUrl: string;
  query: string;
  expiresOn: string;
  reason: string;
};

export type LakehouseInfo = {
  workspaceId: string;
  workspaceName: string;
  lakehouseId: string;
  lakehouseName: string;
  oneLakePath: string;
  portalUrl: string;
};

export type SlideCatalog = {
  title: string;
  generatedAt: string;
  slides: SlideInfo[];
  lakehouse: LakehouseInfo;
  tileAccess: TileAccess;
  servedAt: string;
};

export type TileBlob = { path: string; contentType: string; data: string };

export type VolumeLayer = {
  id: string;
  label: string;
  kind: string;
  frames4d?: boolean;
  file?: string;
  frameKey?: string;
  lut?: string;
  colormap?: string;
  calMin?: number;
  calMax?: number;
  opacity?: number;
  visible?: boolean;
  unit?: string;
  bytes?: number;
};

export type VolumeFrame = {
  value: number;
  label: string;
  note?: string;
  bytes?: number;
  layers: Record<string, string>;
};

export type VolumeStudy = {
  id: string;
  category: string;
  title: string;
  subtitle: string;
  modality: string;
  description: string;
  source: string;
  sourceUrl: string;
  license: string;
  citation: string;
  subject: string;
  patientId?: string;
  scanner?: string;
  thumbnail: string;
  rawPath: string;
  rawFiles: number;
  rawSizeBytes: number;
  sizeBytes: number;
  defaultView: string;
  defaultClip?: { on: boolean; depth: number; face: 'front' | 'side' | 'top' };
  stats?: Record<string, number>;
  layers: VolumeLayer[];
  defaultCamera?: { azimuth: number; elevation: number };
  defaultPreset?: string;
  views?: string[];
  mip?: { sprite: string; frames: number; cols: number; frameWidth: number; frameHeight: number; label: string; colormap: string; bytes: number };
  timeline?: {
    label: string;
    unit: string;
    initial: number;
    mode?: string;
    fps?: number;
    loop?: boolean;
    frames: VolumeFrame[];
  };
  dims: number[];
  spacingMm: number[];
};

export type FolderAccess = {
  baseUrl: string;
  query: string;
  expiresOn: string;
  reason: string;
};

export type VolumeCatalog = {
  title: string;
  generatedAt: string;
  studies: VolumeStudy[];
  lakehouse: LakehouseInfo;
  access: FolderAccess;
  servedAt: string;
};

/* ------------------------------------------------------------------ Patient 360 types */

export type QueryTrace = {
  id: string;
  silos: Silo[];
  tables: string[];
  rows: number;
  ms: number;
};

export type Provenance = {
  workspace: string;
  endpoint: string;
  database: string;
  queries: QueryTrace[];
  totalMs: number;
  showcaseSql: string;
  servedAt: string;
};

export type FileAccess = {
  baseUrl: string;
  query: string;
  expiresOn: string;
  scope: string;
  silo: Silo;
  error?: string;
};

export type CohortPatient = {
  patient_id: string;
  display_name: string;
  cancer_code: string;
  cancer_type: string;
  organ: string;
  sex: string | null;
  age_at_diagnosis: number | null;
  race: string | null;
  stage: string | null;
  vital_status: string | null;
  year_of_diagnosis: number | null;
  days_to_last_contact: number | null;
  tmb: number | null;
  msi_status: string | null;
  subtype: string | null;
  drivers: string | null;
  slide_gigapixels: number | null;
  radiology_series: number;
  thumbnailUrl: string | null;
};

export type Cohort = {
  patients: CohortPatient[];
  provenance: Provenance;
  isDeidentified?: boolean;
  persona?: 'nurse' | 'researcher';
};

export type ReportText = {
  text: string;
  pdfPath: string | null;
  pdfBytes: number | null;
  gdcFileId: string | null;
  source: string | null;
};

export type MutationMap = {
  chromosomes: string[];
  positions: number[];
  types: number[];
  typeNames: string[];
};

export type PatientBundle = {
  isDeidentified?: boolean;
  persona?: 'nurse' | 'researcher';
  patient: Row;
  header: Row;
  diagnoses: Row[];
  treatments: Row[];
  followUps: Row[];
  biomarkers: Row[];
  observations: Row[];
  encounters: Row[];
  conditions: Row[];
  medications: Row[];
  immunizations: Row[];
  allergies: Row[];
  procedures: Row[];
  careplans: Row[];
  report: ReportText;
  summary: Row | null;
  profile: Row | null;
  drivers: Row[];
  mutationMap: MutationMap;
  mutationCounts: Row[];
  segments: Row[];
  copyNumber: Row[];
  expression: Row[];
  immuneCells: Row[];
  reference: Row[];
  slide: Row | null;
  slides: Row[];
  radiologyStudies: Row[];
  radiologySeries: Row[];
  access: { slide: FileAccess; radiology: FileAccess; report: FileAccess };
  provenance: Provenance;
};

export type SiloInventory = {
  silo: Silo;
  id: string;
  name: string;
  role: string;
  portalUrl: string;
  items: Row[];
};

export type ShortcutInfo = { path: string; name: string; targetItem: string; targetPath: string; silo: Silo | null };

export type ZeroCopySummary = {
  copiesMade: 0;
  shortcutCount: number;
  sourceSilos: string[];
  physicalBytesInPatient360: 0;
};

export type DatabricksInteropProof = {
  timestamp: string;
  engine: string;
  statement: string;
  warehouseId: string;
  rowCount: number;
  fabricP360Count?: number;
  deltaTableVersion?: number;
  executionTimeMs: number;
  oneLakeExternalLocation: string;
  status: string;
  zeroCopyVerified: boolean;
};

export type DataMap = {
  workspace: { id: string; name: string; portalUrl: string };
  patient360: {
    id: string;
    name: string;
    portalUrl: string;
    sqlEndpoint: string;
    shortcuts: ShortcutInfo[];
    zeroCopy?: ZeroCopySummary;
    error?: string;
  };
  zeroCopy: ZeroCopySummary;
  databricksInterop?: DatabricksInteropProof | null;
  silos: SiloInventory[];
  provenance: Provenance;
};

/* ------------------------------------------------------------------ WardFlow Cardiology types */

export type WardFlowSubject = {
  id: string;
  initials: string;
  fullName: string | null;
  gender: string | null;
  age: number | null;
  ageBand: string;
  careSetting: string;
  encounterId: string;
  conditionDisplay: string;
  attendingRole: string | null;
  deviceId: string | null;
  deviceKind: string | null;
  deviceSerial: string | null;
  pulseOximeterDeviceId: string | null;
  refreshedAt: string | null;
  observations: Record<string, number | null>;
  observedAt: string | null;
  encounterCount: number;
  medicationCount: number;
  imagingStudyCount: number;
  openCareGaps: number;
  has3dVolume: boolean;
  volumeStudyId: string | null;
};

export type WardFlowCohortSnapshot = {
  workspaceId: string;
  workspaceName: string;
  sqlEndpoint: string;
  database: string;
  goldRefreshedAt: string | null;
  servedAt: string;
  totalMs: number;
  subjects: WardFlowSubject[];
  enrollableCount: number;
};

export type AlertStopwatchBeat = {
  id: string;
  name: string;
  timestamp: string;
  elapsedSeconds: number;
  status: 'completed' | 'in_progress' | 'pending';
};

export type AlertStopwatchSnapshot = {
  patientId: string;
  patientName: string;
  deviceId: string;
  alertTier: string;
  spo2: number;
  pulseRate: number;
  totalElapsedSeconds: number;
  totalElapsedFormatted: string;
  beats: AlertStopwatchBeat[];
  measuredAt: string;
  source: string;
};

/* ------------------------------------------------------------------ OneLake & SAS helpers */

const cachedSas = new Map<string, { query: string; expiresOn: number; reuseUntil: number }>();
let delegation: { key: UserDelegationKey; reuseUntil: number; expiresOn: number } | null = null;

async function readOneLake(token: string, relativePath: string): Promise<Response> {
  const response = await fetch(`${ONELAKE_DFS}/${WORKSPACE_ID}/${FILES_PATH}/${relativePath}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`OneLake read of ${relativePath} failed: ${response.status} ${response.statusText}`);
  }
  return response;
}

async function delegationKey(token: string): Promise<{ key: UserDelegationKey; expiresOn: number }> {
  const now = Date.now();
  if (delegation && delegation.reuseUntil > now) return delegation;
  const credential = { getToken: async () => ({ token, expiresOnTimestamp: now + 30 * 60_000 }) };
  const service = new DataLakeServiceClient(ONELAKE_DFS, credential);
  const expiresOn = now + SAS_LIFETIME_MS;
  const key = await service.getUserDelegationKey(new Date(now - 5 * 60_000), new Date(expiresOn));
  delegation = { key, reuseUntil: now + KEY_REUSE_MS, expiresOn };
  return delegation;
}

async function signFolderSas(token: string, folder: string): Promise<{ query: string; expiresOn: number }> {
  const now = Date.now();
  const cached = cachedSas.get(folder);
  if (cached && cached.reuseUntil > now) return cached;
  const scope = `${FILES_PATH}/${folder}`;
  const { key, expiresOn } = await delegationKey(token);
  const startsOn = new Date(now - 5 * 60_000);
  const query = generateDataLakeSASQueryParameters(
    {
      fileSystemName: WORKSPACE_ID,
      pathName: scope,
      isDirectory: true,
      directoryDepth: scope.split('/').length,
      permissions: DataLakeSASPermissions.parse('r'),
      protocol: SASProtocol.Https,
      startsOn,
      expiresOn: new Date(expiresOn),
    },
    key,
    'onelake',
  ).toString();
  const entry = { query, expiresOn, reuseUntil: now + SAS_REUSE_MS };
  cachedSas.set(folder, entry);
  return entry;
}

async function signAccess(token: string, silo: Silo, path: string, isDirectory: boolean): Promise<FileAccess> {
  const filesRoot = `${SILOS[silo].id}/Files`;
  const scope = `${filesRoot}/${path}`;
  const baseUrl = `${ONELAKE_BLOB}/${WORKSPACE_ID}/${filesRoot}`;
  const label = `${SILOS[silo].name}/Files/${path}`;
  try {
    const { key, expiresOn } = await delegationKey(token);
    const query = generateDataLakeSASQueryParameters(
      {
        fileSystemName: WORKSPACE_ID,
        pathName: scope,
        isDirectory,
        ...(isDirectory ? { directoryDepth: scope.split('/').length } : {}),
        permissions: DataLakeSASPermissions.parse('r'),
        protocol: SASProtocol.Https,
        startsOn: new Date(Date.now() - 5 * 60_000),
        expiresOn: new Date(expiresOn),
      },
      key,
      'onelake',
    ).toString();
    return { baseUrl, query, expiresOn: new Date(expiresOn).toISOString(), scope: label, silo };
  } catch (error) {
    console.error('OneLake SAS unavailable', error);
    return { baseUrl, query: '', expiresOn: '', scope: label, silo, error: String(error) };
  }
}

function lakehouseInfo(): LakehouseInfo {
  return {
    workspaceId: WORKSPACE_ID,
    workspaceName: WORKSPACE_NAME,
    lakehouseId: LAKEHOUSE_ID,
    lakehouseName: LAKEHOUSE_NAME,
    oneLakePath: `abfss://${WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/${FILES_PATH}`,
    portalUrl: `https://app.fabric.microsoft.com/groups/${WORKSPACE_ID}/lakehouses/${LAKEHOUSE_ID}`,
  };
}

/* ------------------------------------------------------------------ SQL Pools */

const pools = new Map<string, { token: string; pool: sql.ConnectionPool }>();

async function getPool(token: string, database: string): Promise<sql.ConnectionPool> {
  if (!SQL_SERVER || /^0{8}-/.test(WORKSPACE_ID)) {
    throw new Error('Fabric SQL is not configured: run scripts/setup_fabric.py, then redeploy with `npx rayfin up`.');
  }
  const existing = pools.get(database);
  if (existing && existing.token === token && existing.pool.connected) return existing.pool;
  if (existing) void existing.pool.close().catch(() => undefined);
  const pool = new sql.ConnectionPool({
    server: SQL_SERVER,
    database,
    options: { encrypt: true, trustServerCertificate: false },
    authentication: { type: 'azure-active-directory-access-token', options: { token } },
    pool: { max: 12, min: 0, idleTimeoutMillis: 60_000 },
    requestTimeout: 60_000,
    connectionTimeout: 30_000,
  });
  await pool.connect();
  pools.set(database, { token, pool });
  return pool;
}

function normalise(value: unknown): Cell {
  if (value === null || value === undefined) return null;
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  if (typeof value === 'bigint') return Number(value);
  if (typeof value === 'number' || typeof value === 'boolean') return value;
  return String(value);
}

function toRows(result: sql.IResult<Record<string, unknown>>): Row[] {
  const recordset = result.recordset ?? [];
  const columns: Record<string, { type: unknown }> =
    'columns' in recordset && recordset.columns && typeof recordset.columns === 'object'
      ? (recordset.columns as Record<string, { type: unknown }>)
      : {};
  const bigint = new Set(
    Object.entries(columns)
      .filter(([, c]) => c.type === sql.BigInt)
      .map(([name]) => name)
  );
  return recordset.map((r) =>
    Object.fromEntries(Object.entries(r).map(([k, v]) => [k, bigint.has(k) && v !== null ? Number(v) : normalise(v)]))
  );
}

class Tracer {
  readonly queries: QueryTrace[] = [];
  private readonly started = Date.now();

  constructor(private readonly db: sql.ConnectionPool) {}

  async run(id: string, silos: Silo[], tables: string[], text: string, params: Record<string, string> = {}): Promise<Row[]> {
    const t0 = Date.now();
    const request = this.db.request();
    for (const [k, v] of Object.entries(params)) request.input(k, sql.VarChar(64), v);
    const out = toRows(await request.query(text));
    this.queries.push({ id, silos, tables, rows: out.length, ms: Date.now() - t0 });
    return out;
  }

  provenance(showcaseSql: string): Provenance {
    return {
      workspace: WORKSPACE_NAME,
      endpoint: SQL_SERVER,
      database: PATIENT360.name,
      queries: this.queries,
      totalMs: Date.now() - this.started,
      showcaseSql: showcaseSql.trim(),
      servedAt: new Date().toISOString(),
    };
  }
}

/* ------------------------------------------------------------------ Patient 360 SQL */

const COHORT_SQL = `
SELECT p.patient_id, p.display_name, p.cancer_code, p.cancer_type, p.organ, p.sex, p.age_at_diagnosis,
       p.race, p.stage, p.vital_status, p.year_of_diagnosis, p.days_to_last_contact,
       m.tmb, m.msi_status, m.subtype, d.drivers,
       CAST(s.width AS float) * s.height / 1e9 AS slide_gigapixels, s.thumbnail_path,
       (SELECT COUNT(*) FROM dbo.radiology_series r WHERE r.patient_id = p.patient_id) AS radiology_series
FROM dbo.patient p                                            -- clinical_lakehouse
JOIN dbo.molecular_profile m ON m.patient_id = p.patient_id   -- genomics_lakehouse
JOIN dbo.pathology_slide s  ON s.patient_id = p.patient_id AND s.role = 'diagnostic'  -- imaging_lakehouse
OUTER APPLY (
  SELECT STRING_AGG(x.label, '; ') AS drivers
  FROM (SELECT TOP 3 CONCAT(gene, ' ', REPLACE(protein_change, 'p.', '')) AS label
        FROM dbo.somatic_mutation
        WHERE patient_id = p.patient_id AND is_driver_gene = 1
          AND mutation_type NOT IN ('Silent', 'Intron', '3''UTR', '5''UTR', 'RNA', 'IGR', '5''Flank', '3''Flank')
        ORDER BY CASE WHEN gene IN ('TP53','KRAS','EGFR','PIK3CA','VHL','ERBB2','BRAF','SPOP','MET','POLE',
                                    'APC','PTEN','BAP1','ARID1A','CDKN2A','MTOR','SETD2','PBRM1') THEN 0 ELSE 1 END,
                 vaf DESC) x
) d
ORDER BY p.cancer_type`;

const HEADER_SQL = `
SELECT p.patient_id, p.display_name, p.cancer_type, p.stage, p.vital_status,
       m.subtype, m.tmb, m.tmb_percentile, m.msi_status, m.mutation_count,
       s.width, s.height, s.tile_count, s.raw_bytes AS slide_raw_bytes,
       (SELECT COUNT(*) FROM dbo.pathology_slide x WHERE x.patient_id = p.patient_id) AS slide_count,
       (SELECT COUNT(*) FROM dbo.radiology_study r WHERE r.patient_id = p.patient_id) AS radiology_studies,
       (SELECT SUM(raw_bytes) FROM dbo.radiology_series r WHERE r.patient_id = p.patient_id) AS radiology_raw_bytes,
       (SELECT COUNT(*) FROM dbo.observation o WHERE o.patient_id = p.patient_id) AS observations
FROM dbo.patient p                                            -- clinical_lakehouse
JOIN dbo.molecular_profile m ON m.patient_id = p.patient_id   -- genomics_lakehouse
JOIN dbo.pathology_slide s  ON s.patient_id = p.patient_id AND s.role = 'diagnostic'  -- imaging_lakehouse
WHERE p.patient_id = @id`;
const COHORT_SQL_DEIDENTIFIED = COHORT_SQL.replace('FROM dbo.patient p', 'FROM dbo.patient_deidentified p');
const HEADER_SQL_DEIDENTIFIED = HEADER_SQL.replace('FROM dbo.patient p', 'FROM dbo.patient_deidentified p');

function isResearcherPersona(token?: string): boolean {
  if (!token) return false;
  try {
    const parts = token.split('.');
    if (parts.length < 2) return false;
    const claims = JSON.parse(Buffer.from(parts[1], 'base64').toString('utf8')) as Record<string, unknown>;
    const upn = String(claims.upn ?? claims.preferred_username ?? claims.email ?? claims.unique_name ?? '').toLowerCase();
    return upn.includes('researcher-demo');
  } catch {
    return false;
  }
}

/* ------------------------------------------------------------------ WardFlow Cardiology SQL */

const WARDFLOW_SUBJECTS_SQL = `
SELECT s.subject_id, s.initials, s.age_band, s.care_setting, s.encounter_id,
       s.primary_condition_display, s.attending_role,
       s.device_id, s.device_kind, s.device_serial, s.pulse_oximeter_device_id,
       CONVERT(varchar(33), s.refreshed_at, 127) AS refreshed_at,
       p.FullName, p.Gender, p.Age,
       (SELECT COUNT(*) FROM dbo.EncounterOntology e WHERE e.patient_id = s.subject_id) AS enc_cnt,
       (SELECT COUNT(*) FROM dbo.MedicationRequestOntology m WHERE m.patient_id = s.subject_id) AS med_cnt,
       (SELECT COUNT(*) FROM dbo.ImagingStudyReporting i WHERE i.PatientUUID = s.subject_id) AS img_cnt,
       (SELECT COUNT(*) FROM dbo.care_gaps g WHERE g.patient_id = s.subject_id AND g.gap_status = 'open') AS open_gaps,
       (SELECT COUNT(*) FROM imaging_lakehouse.dbo.volumes v WHERE v.id = CONCAT('cohort-', LEFT(s.subject_id, 8))) AS vol_cnt
FROM dbo.cardiology_subject s
LEFT JOIN dbo.PatientReporting p ON p.PatientUUID = s.subject_id
ORDER BY s.subject_id`;

const WARDFLOW_LATEST_OBS_SQL = `
SELECT observation_id, subject_id, measure, value, unit,
       CONVERT(varchar(33), effective_at, 127) AS effective_at
FROM (
  SELECT observation_id, subject_id, measure, value, unit, effective_at,
         ROW_NUMBER() OVER (PARTITION BY subject_id, measure
                            ORDER BY effective_at DESC, fhir_last_updated DESC, observation_id DESC) AS rn
  FROM dbo.cardiology_observation
) latest
WHERE rn = 1`;

const udf = new UserDataFunctions();

/* ------------------------------------------------------------------ Rayfin Imaging UDFs */

udf.func(
  'getSlideCatalog',
  async (ctx: RayfinContext<AppSchema, AudienceType.Storage>): Promise<SlideCatalog> => {
    const token = ctx.Tokens.Storage;
    const manifest = (await (await readOneLake(token, 'manifest.json')).json()) as {
      title: string;
      generatedAt: string;
      slides: SlideInfo[];
    };

    let tileAccess: TileAccess;
    try {
      const sas = await signFolderSas(token, SLIDES_SCOPE);
      tileAccess = {
        mode: 'sas',
        baseUrl: `${ONELAKE_BLOB}/${WORKSPACE_ID}/${FILES_PATH}`,
        query: sas.query,
        expiresOn: new Date(sas.expiresOn).toISOString(),
        reason: 'Short-lived read-only OneLake SAS scoped to Files/slides',
      };
    } catch (error) {
      console.error('OneLake SAS unavailable, falling back to tile proxy', error);
      tileAccess = {
        mode: 'proxy',
        baseUrl: '',
        query: '',
        expiresOn: '',
        reason: error instanceof Error ? error.message : String(error),
      };
    }

    return {
      ...manifest,
      lakehouse: lakehouseInfo(),
      tileAccess,
      servedAt: new Date().toISOString(),
    };
  },
  [],
);

udf.func(
  'getVolumeCatalog',
  async (ctx: RayfinContext<AppSchema, AudienceType.Storage>): Promise<VolumeCatalog> => {
    const token = ctx.Tokens.Storage;
    const manifest = (await (await readOneLake(token, `${VOLUMES_SCOPE}/manifest.json`)).json()) as {
      title: string;
      generatedAt: string;
      studies: VolumeStudy[];
    };
    let access: FolderAccess;
    try {
      const sas = await signFolderSas(token, VOLUMES_SCOPE);
      access = {
        baseUrl: `${ONELAKE_BLOB}/${WORKSPACE_ID}/${FILES_PATH}/${VOLUMES_SCOPE}`,
        query: sas.query,
        expiresOn: new Date(sas.expiresOn).toISOString(),
        reason: 'Short-lived read-only OneLake SAS scoped to Files/volumes',
      };
    } catch (error) {
      console.error('OneLake SAS unavailable for volumes', error);
      access = {
        baseUrl: '',
        query: '',
        expiresOn: '',
        reason: error instanceof Error ? error.message : String(error),
      };
    }
    return { ...manifest, lakehouse: lakehouseInfo(), access, servedAt: new Date().toISOString() };
  },
  [],
);

const SLIDE_ID = /^[a-z0-9-]{1,64}$/;
const TILE_PATH = /^((channels\/[a-z0-9-]{1,64}\/)?slide_files\/\d{1,2}\/\d{1,5}_\d{1,5}\.jpg|thumbnail\.jpg)$/;

udf.func(
  'getTiles',
  async (
    slideId: string,
    paths: string[],
    ctx: RayfinContext<AppSchema, AudienceType.Storage>,
  ): Promise<TileBlob[]> => {
    if (!SLIDE_ID.test(slideId)) throw new Error('Invalid slide id');
    if (!Array.isArray(paths) || paths.length === 0 || paths.length > MAX_TILES_PER_CALL) {
      throw new Error(`Request between 1 and ${MAX_TILES_PER_CALL} tiles`);
    }
    if (!paths.every((p) => TILE_PATH.test(p))) throw new Error('Invalid tile path');

    const token = ctx.Tokens.Storage;
    return Promise.all(
      paths.map(async (path) => {
        const response = await readOneLake(token, `slides/${slideId}/${path}`);
        const bytes = Buffer.from(await response.arrayBuffer());
        return { path, contentType: 'image/jpeg', data: bytes.toString('base64') };
      }),
    );
  },
  [],
);

/* ------------------------------------------------------------------ Patient 360 UDFs */

udf.func(
  'getCohort',
  async (ctx: RayfinContext<AppSchema, AudienceType.Sql | AudienceType.Storage>): Promise<Cohort> => {
    const isResearcher = isResearcherPersona(ctx.Tokens.Sql);
    const cohortSql = isResearcher ? COHORT_SQL_DEIDENTIFIED : COHORT_SQL;
    const patientTable = isResearcher ? 'patient_deidentified' : 'patient';
    const tracer = new Tracer(await getPool(ctx.Tokens.Sql, PATIENT360.name));
    const list = await tracer.run(
      'cohort',
      ['clinical', 'genomics', 'imaging'],
      [patientTable, 'molecular_profile', 'pathology_slide', 'somatic_mutation', 'radiology_series'],
      cohortSql,
    );
    const storage = ctx.Tokens.Storage;
    const patients = await Promise.all(
      list.map(async (r) => {
        const thumb = r.thumbnail_path ? String(r.thumbnail_path) : null;
        const access = thumb ? await signAccess(storage, 'imaging', thumb, false) : null;
        const rest = { ...r };
        delete rest.thumbnail_path;
        return {
          ...(rest as unknown as Omit<CohortPatient, 'thumbnailUrl' | 'radiology_series'>),
          radiology_series: Number(r.radiology_series ?? 0),
          thumbnailUrl: access && access.query ? `${access.baseUrl}/${thumb}?${access.query}` : null,
        } satisfies CohortPatient;
      }),
    );
    return {
      patients,
      provenance: tracer.provenance(cohortSql),
      isDeidentified: isResearcher,
      persona: isResearcher ? 'researcher' : 'nurse',
    };
  },
  [],
);

udf.func(
  'getPatient',
  async (
    patientId: string,
    ctx: RayfinContext<AppSchema, AudienceType.Sql | AudienceType.Storage>,
  ): Promise<PatientBundle> => {
    if (!PATIENT_ID.test(patientId)) throw new Error('Invalid patient id');
    const isResearcher = isResearcherPersona(ctx.Tokens.Sql);
    const headerSql = isResearcher ? HEADER_SQL_DEIDENTIFIED : HEADER_SQL;
    const patientTable = isResearcher ? 'patient_deidentified' : 'patient';
    const tracer = new Tracer(await getPool(ctx.Tokens.Sql, PATIENT360.name));
    const params = { id: patientId };
    const q = (id: string, silo: Silo, table: string, text: string) => tracer.run(id, [silo], [table], text, params);
    const where = 'WHERE patient_id = @id';

    const [
      header, patient, diagnoses, treatments, followUps, biomarkers, observations, encounters, conditions,
      medications, immunizations, allergies, procedures, careplans, report, summary, profile, drivers, positions,
      mutationCounts, segments, copyNumber, expression, immuneCells, reference, slides, studies, series,
    ] = await Promise.all([
      tracer.run(
        'header',
        ['clinical', 'genomics', 'imaging'],
        [patientTable, 'molecular_profile', 'pathology_slide', 'radiology_study', 'radiology_series', 'observation'],
        headerSql,
        params,
      ),
      q('patient', 'clinical', patientTable, `SELECT * FROM dbo.${patientTable} ${where}`),
      q('diagnoses', 'clinical', 'diagnosis', `SELECT * FROM dbo.diagnosis ${where} ORDER BY day`),
      q('treatments', 'clinical', 'treatment', `SELECT * FROM dbo.treatment ${where} ORDER BY start_day`),
      q('followUps', 'clinical', 'follow_up', `SELECT * FROM dbo.follow_up ${where} ORDER BY day`),
      q('biomarkers', 'clinical', 'biomarker_test', `SELECT * FROM dbo.biomarker_test ${where} ORDER BY day`),
      q('observations', 'clinical', 'observation',
        `SELECT date, encounter_id, category, name, value, value_text, units, source, synthetic
         FROM dbo.observation ${where} ORDER BY date`),
      q('encounters', 'clinical', 'encounter',
        `SELECT encounter_id, start, stop, duration_minutes, encounter_class, description, reason, provider,
                provider_specialty, organization, payer, total_cost, payer_coverage
         FROM dbo.encounter ${where} ORDER BY start`),
      q('conditions', 'clinical', 'condition',
        `SELECT encounter_id, onset, resolved, description, source, synthetic FROM dbo.condition ${where} ORDER BY onset`),
      q('medications', 'clinical', 'medication',
        `SELECT encounter_id, start, stop, description, reason, dispenses, total_cost FROM dbo.medication ${where} ORDER BY start`),
      q('immunizations', 'clinical', 'immunization',
        `SELECT encounter_id, date, description FROM dbo.immunization ${where} ORDER BY date`),
      q('allergies', 'clinical', 'allergy',
        `SELECT encounter_id, onset, description, category, reaction, severity FROM dbo.allergy ${where}`),
      q('procedures', 'clinical', 'procedure',
        `SELECT encounter_id, date, description, reason FROM dbo.[procedure] ${where} ORDER BY date`),
      q('careplans', 'clinical', 'careplan',
        `SELECT encounter_id, start, stop, description, reason FROM dbo.careplan ${where} ORDER BY start`),
      q('report', 'clinical', 'pathology_report', `SELECT * FROM dbo.pathology_report ${where} ORDER BY part`),
      q('summary', 'clinical', 'patient_summary', `SELECT * FROM dbo.patient_summary ${where}`),
      q('profile', 'genomics', 'molecular_profile', `SELECT * FROM dbo.molecular_profile ${where}`),
      q('drivers', 'genomics', 'somatic_mutation',
        `SELECT gene, protein_change, mutation_type, variant_type, chromosome, start_pos, vaf
         FROM dbo.somatic_mutation ${where} AND is_driver_gene = 1 ORDER BY vaf DESC`),
      q('mutationPositions', 'genomics', 'somatic_mutation',
        `SELECT chromosome, start_pos, mutation_type FROM dbo.somatic_mutation ${where}`),
      q('mutationCounts', 'genomics', 'somatic_mutation',
        `SELECT mutation_type, COUNT(*) AS n FROM dbo.somatic_mutation ${where} GROUP BY mutation_type ORDER BY n DESC`),
      q('segments', 'genomics', 'copy_number_segment',
        `SELECT chromosome, start_pos, end_pos, segment_mean FROM dbo.copy_number_segment ${where}`),
      q('copyNumber', 'genomics', 'gene_copy_number',
        `SELECT gene, alteration, [call], is_driver_gene FROM dbo.gene_copy_number ${where}`),
      q('expression', 'genomics', 'gene_expression', `SELECT gene, z_score FROM dbo.gene_expression ${where}`),
      q('immuneCells', 'genomics', 'immune_cell_fraction', `SELECT cell_type, fraction FROM dbo.immune_cell_fraction ${where}`),
      tracer.run(
        'reference',
        ['genomics'],
        ['cohort_reference', 'molecular_profile'],
        `SELECT r.metric, r.n, r.quantiles_json FROM dbo.cohort_reference r
         JOIN dbo.molecular_profile m ON m.cohort_study = r.cohort_study WHERE m.patient_id = @id`,
        params,
      ),
      q('slides', 'imaging', 'pathology_slide', `SELECT * FROM dbo.pathology_slide ${where} ORDER BY sort_order`),
      q('radiologyStudies', 'imaging', 'radiology_study', `SELECT * FROM dbo.radiology_study ${where} ORDER BY date`),
      q('radiologySeries', 'imaging', 'radiology_series', `SELECT * FROM dbo.radiology_series ${where} ORDER BY date`),
    ]);
    if (!patient.length) throw new Error(`Patient ${patientId} not found`);

    const storage = ctx.Tokens.Storage;
    const reportRow = report[0] ?? null;
    const id = patientId.toLowerCase();
    const firstSlideId = slides[0]?.slide_id ? String(slides[0].slide_id).split('/')[0] : id;
    const firstVolPath = series[0]?.volume_path ? String(series[0].volume_path) : `radiology/${id}/volume.nii.gz`;
    const radScope = firstVolPath.startsWith('volumes/')
      ? firstVolPath.split('/').slice(0, 2).join('/')
      : `radiology/${id}`;
    const [slideAccess, radiologyAccess, reportAccess] = await Promise.all([
      signAccess(storage, 'imaging', `slides/${firstSlideId}`, true),
      signAccess(storage, 'imaging', radScope, true),
      signAccess(storage, 'clinical', String(reportRow?.pdf_path ?? `reports/${patientId}.pdf`), false),
    ]);

    const types = [...new Set(positions.map((r) => String(r.mutation_type)))];
    return {
      patient: patient[0],
      header: header[0] ?? {},
      diagnoses,
      treatments,
      followUps,
      biomarkers,
      observations,
      encounters,
      conditions,
      medications,
      immunizations,
      allergies,
      procedures,
      careplans,
      report: {
        text: report.map((r) => String(r.report_text ?? '')).join(''),
        pdfPath: reportRow?.pdf_path ? String(reportRow.pdf_path) : null,
        pdfBytes: typeof reportRow?.pdf_bytes === 'number' ? reportRow.pdf_bytes : null,
        gdcFileId: reportRow?.gdc_file_id ? String(reportRow.gdc_file_id) : null,
        source: reportRow?.text_source ? String(reportRow.text_source) : null,
      },
      summary: summary[0] ?? null,
      profile: profile[0] ?? null,
      drivers,
      mutationMap: {
        chromosomes: positions.map((r) => String(r.chromosome)),
        positions: positions.map((r) => Number(r.start_pos)),
        types: positions.map((r) => types.indexOf(String(r.mutation_type))),
        typeNames: types,
      },
      mutationCounts,
      segments,
      copyNumber,
      expression,
      immuneCells,
      reference,
      slide: slides.find((r) => r.role === 'diagnostic') ?? slides[0] ?? null,
      slides,
      radiologyStudies: studies,
      radiologySeries: series,
      access: { slide: slideAccess, radiology: radiologyAccess, report: reportAccess },
      provenance: tracer.provenance(headerSql),
      isDeidentified: isResearcher,
      persona: isResearcher ? 'researcher' : 'nurse',
    };
  },
  [],
);

udf.func(
  'getDataMap',
  async (ctx: RayfinContext<AppSchema, AudienceType.Sql | AudienceType.Fabric | AudienceType.Storage>): Promise<DataMap> => {
    const tracer = new Tracer(await getPool(ctx.Tokens.Sql, PATIENT360.name));
    const silos = Object.keys(SILOS) as Silo[];
    const inventory = await Promise.all(
      silos.map((silo) =>
        tracer.run(
          `${silo}_inventory`,
          [silo],
          [`${silo}_inventory`],
          `SELECT kind, name, rows, files, bytes, description FROM dbo.${silo}_inventory ORDER BY kind DESC, bytes DESC`,
        ),
      ),
    );
    const shortcuts: ShortcutInfo[] = [];
    let error: string | undefined;
    try {
      const t0 = Date.now();
      let url: string | null = `${FABRIC_API}/workspaces/${WORKSPACE_ID}/items/${PATIENT360.id}/shortcuts`;
      while (url) {
        const res: Response = await fetch(url, { headers: { Authorization: `Bearer ${ctx.Tokens.Fabric}` } });
        if (!res.ok) throw new Error(`Fabric API returned ${res.status}`);
        const body = (await res.json()) as {
          value: { path: string; name: string; target: { oneLake?: { itemId: string; path: string } } }[];
          continuationUri?: string;
        };
        for (const s of body.value) {
          const item = s.target.oneLake?.itemId ?? '';
          shortcuts.push({
            path: s.path,
            name: s.name,
            targetItem: item,
            targetPath: s.target.oneLake?.path ?? '',
            silo: silos.find((k) => SILOS[k].id === item) ?? null,
          });
        }
        url = body.continuationUri ?? null;
      }
      tracer.queries.push({ id: 'shortcuts', silos: [], tables: [], rows: shortcuts.length, ms: Date.now() - t0 });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
    const sourceSilos = Array.from(
      new Set(shortcuts.map((s) => (s.silo ? SILOS[s.silo]?.name ?? `${s.silo}_lakehouse` : s.targetItem)).filter(Boolean)),
    );
    const zeroCopy: ZeroCopySummary = {
      copiesMade: 0,
      shortcutCount: shortcuts.length,
      sourceSilos,
      physicalBytesInPatient360: 0,
    };
    let databricksInterop: DatabricksInteropProof | null = null;
    try {
      if (ctx.Tokens && 'Storage' in ctx.Tokens && typeof ctx.Tokens.Storage === 'string' && !/^0{8}-/.test(LAKEHOUSE_ID)) {
        const proofRes = await readOneLake(ctx.Tokens.Storage, 'interop/databricks_proof.json');
        if (proofRes.ok) {
          databricksInterop = (await proofRes.json()) as DatabricksInteropProof;
        }
      }
    } catch {
      databricksInterop = null;
    }
    return {
      workspace: { id: WORKSPACE_ID, name: WORKSPACE_NAME, portalUrl: `https://app.fabric.microsoft.com/groups/${WORKSPACE_ID}` },
      patient360: {
        ...PATIENT360,
        portalUrl: `https://app.fabric.microsoft.com/groups/${WORKSPACE_ID}/lakehouses/${PATIENT360.id}`,
        sqlEndpoint: SQL_SERVER,
        shortcuts,
        zeroCopy,
        ...(error ? { error } : {}),
      },
      zeroCopy,
      databricksInterop,
      silos: silos.map((silo, i) => ({
        silo,
        ...SILOS[silo],
        portalUrl: `https://app.fabric.microsoft.com/groups/${WORKSPACE_ID}/lakehouses/${SILOS[silo].id}`,
        items: inventory[i],
      })),
      provenance: tracer.provenance('SELECT kind, name, rows, files, bytes FROM dbo.<silo>_inventory'),
    };
  },
  [],
);

/* ------------------------------------------------------------------ WardFlow Cardiology UDF */

udf.func(
  'getWardFlowCohort',
  async (ctx: RayfinContext<AppSchema, AudienceType.Sql>): Promise<WardFlowCohortSnapshot> => {
    const t0 = Date.now();
    const db = await getPool(ctx.Tokens.Sql, GOLD_DATABASE);
    const [subjRes, obsRes, enrRes] = await Promise.all([
      db.request().query(WARDFLOW_SUBJECTS_SQL),
      db.request().query(WARDFLOW_LATEST_OBS_SQL),
      db.request().query('SELECT COUNT(*) AS cnt FROM dbo.cardiology_enrollable_patient'),
    ]);
    const subjRows = toRows(subjRes);
    const obsRows = toRows(obsRes);
    const enrollableCount = Number(toRows(enrRes)[0]?.cnt ?? 0);

    const obsBySubject = new Map<string, { obs: Record<string, number | null>; newest: string | null }>();
    for (const r of obsRows) {
      const sid = String(r.subject_id ?? '');
      const measure = String(r.measure ?? '');
      const val = typeof r.value === 'number' && Number.isFinite(r.value) ? r.value : null;
      const eff = r.effective_at ? String(r.effective_at) : null;
      const cur = obsBySubject.get(sid) ?? { obs: {}, newest: null };
      if (val !== null) cur.obs[measure] = val;
      if (eff && (!cur.newest || eff > cur.newest)) cur.newest = eff;
      obsBySubject.set(sid, cur);
    }

    let goldRefreshedAt: string | null = null;
    const subjects: WardFlowSubject[] = subjRows.map((r) => {
      const sid = String(r.subject_id);
      const refAt = r.refreshed_at ? String(r.refreshed_at) : null;
      if (refAt && (!goldRefreshedAt || refAt > goldRefreshedAt)) goldRefreshedAt = refAt;
      const ob = obsBySubject.get(sid) ?? { obs: {}, newest: null };
      const hasVol = Number(r.vol_cnt ?? 0) > 0;
      const shortId = sid.slice(0, 8);
      return {
        id: sid,
        initials: String(r.initials ?? ''),
        fullName: r.FullName ? String(r.FullName).replace(/\d+/g, '') : null,
        gender: r.Gender ? String(r.Gender) : null,
        age: typeof r.Age === 'number' ? r.Age : null,
        ageBand: String(r.age_band ?? '60-69'),
        careSetting: String(r.care_setting ?? 'inpatient'),
        encounterId: String(r.encounter_id ?? ''),
        conditionDisplay: String(r.primary_condition_display ?? 'Heart failure'),
        attendingRole: r.attending_role ? String(r.attending_role) : null,
        deviceId: r.device_id ? String(r.device_id) : null,
        deviceKind: r.device_kind ? String(r.device_kind) : null,
        deviceSerial: r.device_serial ? String(r.device_serial) : null,
        pulseOximeterDeviceId: r.pulse_oximeter_device_id ? String(r.pulse_oximeter_device_id) : null,
        refreshedAt: refAt,
        observations: ob.obs,
        observedAt: ob.newest,
        encounterCount: Number(r.enc_cnt ?? 0),
        medicationCount: Number(r.med_cnt ?? 0),
        imagingStudyCount: Number(r.img_cnt ?? 0),
        openCareGaps: Number(r.open_gaps ?? 0),
        has3dVolume: hasVol,
        volumeStudyId: hasVol ? `cohort-${shortId}` : null,
      };
    });

    return {
      workspaceId: WORKSPACE_ID,
      workspaceName: WORKSPACE_NAME,
      sqlEndpoint: SQL_SERVER,
      database: GOLD_DATABASE,
      goldRefreshedAt,
      servedAt: new Date().toISOString(),
      totalMs: Date.now() - t0,
      subjects,
      enrollableCount,
    };
  },
  [],
);

/* ------------------------------------------------------------------ Standards View (FHIR R4 & DICOM Lineage) UDF */

export type StandardsMapping = {
  patientId: string;
  patient: Row;
  diagnoses: Row[];
  radiologyStudies: Row[];
  radiologySeries: Row[];
  fhir: {
    patientResource: Record<string, unknown>;
    conditionResource: Record<string, unknown>;
    mappings: { fhirPath: string; deltaTable: string; deltaColumn: string; description: string }[];
  };
  dicom: {
    tags: { tag: string; name: string; value: Cell; mappedTable: string; mappedColumn: string }[];
    mappings: { dicomTag: string; tagName: string; deltaTable: string; deltaColumn: string }[];
  };
};

function buildFhirBundleForUdf(patientRow: Row, diagnosisRows: Row[]) {
  const patientId = String(patientRow.patient_id ?? '');
  const displayName = String(patientRow.display_name ?? 'Unknown');
  const nameParts = displayName.split(' ');
  const family = nameParts.length > 1 ? nameParts[nameParts.length - 1] : displayName;
  const given = nameParts.length > 1 ? nameParts.slice(0, -1) : [displayName];
  const sex = String(patientRow.sex ?? 'unknown').toLowerCase();
  const gender = sex === 'male' ? 'male' : sex === 'female' ? 'female' : 'other';
  const birthYear =
    patientRow.year_of_diagnosis && patientRow.age_at_diagnosis
      ? Number(patientRow.year_of_diagnosis) - Number(patientRow.age_at_diagnosis)
      : 1956;
  const birthDate = `${birthYear}-04-12`;
  const primaryDx = String(
    patientRow.primary_diagnosis ?? diagnosisRows[0]?.primary_diagnosis ?? patientRow.cancer_type ?? 'Clear cell renal cell carcinoma',
  );
  const icd10 = String(patientRow.icd10 ?? 'C64.9');
  const recordedDate = String(
    patientRow.diagnosis_date ?? (patientRow.year_of_diagnosis ? `${patientRow.year_of_diagnosis}-04-07` : '2011-04-07'),
  );

  const patientResource = {
    resourceType: 'Patient',
    id: patientId,
    identifier: [
      {
        use: 'usual',
        type: {
          coding: [
            {
              system: 'http://terminology.hl7.org/CodeSystem/v2-0203',
              code: 'MR',
              display: 'Medical Record Number',
            },
          ],
        },
        system: 'https://gdc.cancer.gov/tcga/barcode',
        value: patientId,
      },
    ],
    active: true,
    name: [
      {
        use: 'official',
        text: displayName,
        family,
        given,
      },
    ],
    gender,
    birthDate,
    address: [
      {
        use: 'home',
        country: String(patientRow.country ?? 'USA'),
      },
    ],
  };

  const conditionResource = {
    resourceType: 'Condition',
    id: `cond-${patientId.toLowerCase()}-primary`,
    clinicalStatus: {
      coding: [
        {
          system: 'http://terminology.hl7.org/CodeSystem/condition-clinical',
          code: 'active',
          display: 'Active',
        },
      ],
    },
    verificationStatus: {
      coding: [
        {
          system: 'http://terminology.hl7.org/CodeSystem/condition-ver-status',
          code: 'confirmed',
          display: 'Confirmed',
        },
      ],
    },
    category: [
      {
        coding: [
          {
            system: 'http://terminology.hl7.org/CodeSystem/condition-category',
            code: 'encounter-diagnosis',
            display: 'Encounter Diagnosis',
          },
        ],
      },
    ],
    code: {
      coding: [
        {
          system: 'http://hl7.org/fhir/sid/icd-10-cm',
          code: icd10,
          display: primaryDx,
        },
        {
          system: 'http://snomed.info/sct',
          code: '126838000',
          display: `${primaryDx} (disorder)`,
        },
      ],
      text: primaryDx,
    },
    subject: {
      reference: `Patient/${patientId}`,
      display: displayName,
    },
    recordedDate,
  };

  const mappings = [
    {
      fhirPath: 'Patient.gender',
      deltaTable: 'clinical_lakehouse.dbo.patient',
      deltaColumn: 'sex',
      description: 'Patient administrative gender mapped to sex column',
    },
    {
      fhirPath: 'Patient.name[0].text',
      deltaTable: 'clinical_lakehouse.dbo.patient',
      deltaColumn: 'display_name',
      description: 'Official patient human name text mapped to display name',
    },
    {
      fhirPath: 'Condition.code.coding[0].display',
      deltaTable: 'clinical_lakehouse.dbo.diagnoses',
      deltaColumn: 'primary_diagnosis',
      description: 'Standard condition display terminology mapped to primary diagnosis',
    },
    {
      fhirPath: 'Condition.code.coding[0].code',
      deltaTable: 'clinical_lakehouse.dbo.diagnoses',
      deltaColumn: 'icd10',
      description: 'Standard ICD-10-CM diagnosis code mapped to icd10',
    },
    {
      fhirPath: 'Patient.identifier[0].value',
      deltaTable: 'clinical_lakehouse.dbo.patient',
      deltaColumn: 'patient_id',
      description: 'Primary medical record number / barcode mapped to patient_id',
    },
    {
      fhirPath: 'Condition.recordedDate',
      deltaTable: 'clinical_lakehouse.dbo.patient',
      deltaColumn: 'diagnosis_date',
      description: 'Condition initial recording date mapped to diagnosis_date',
    },
  ];

  return { patientResource, conditionResource, mappings };
}

function buildDicomDatasetForUdf(patientId: string, studyRow?: Row, seriesRow?: Row) {
  if (!studyRow && !seriesRow) {
    return { tags: [], mappings: [] };
  }

  const studyUid = String(seriesRow?.study_uid ?? studyRow?.study_uid ?? '');
  const seriesUid = String(seriesRow?.series_uid ?? '');
  const modality = String(seriesRow?.modality ?? studyRow?.modalities ?? 'CT');
  const studyDate = String(studyRow?.date ?? seriesRow?.date ?? '2011-03-31').replace(/-/g, '');
  const manufacturer = String(seriesRow?.manufacturer ?? 'Siemens');
  const model = String(seriesRow?.model ?? 'Somatom Definition');
  const sliceThickness = seriesRow?.slice_thickness_mm != null ? Number(seriesRow.slice_thickness_mm) : 1.5;
  const kvp = seriesRow?.kvp != null ? Number(seriesRow.kvp) : 120;
  const contrast = String(seriesRow?.contrast ?? 'Omnipaque 300');
  const bodyPart = String(seriesRow?.body_part ?? studyRow?.body_part ?? 'Kidney');
  const description = String(seriesRow?.description ?? 'OMNIPAQUE 300');

  const tags = [
    { tag: '(0010,0020)', name: 'PatientID', value: patientId, mappedTable: 'radiology_study / radiology_series', mappedColumn: 'patient_id' },
    { tag: '(0020,000D)', name: 'StudyInstanceUID', value: studyUid, mappedTable: 'radiology_study', mappedColumn: 'study_uid' },
    { tag: '(0020,000E)', name: 'SeriesInstanceUID', value: seriesUid, mappedTable: 'radiology_series', mappedColumn: 'series_uid' },
    { tag: '(0008,0060)', name: 'Modality', value: modality, mappedTable: 'radiology_series', mappedColumn: 'modality' },
    { tag: '(0008,0020)', name: 'StudyDate', value: studyDate, mappedTable: 'radiology_study', mappedColumn: 'date' },
    { tag: '(0008,0070)', name: 'Manufacturer', value: manufacturer, mappedTable: 'radiology_series', mappedColumn: 'manufacturer' },
    { tag: '(0008,1090)', name: 'ManufacturerModelName', value: model, mappedTable: 'radiology_series', mappedColumn: 'model' },
    { tag: '(0018,0050)', name: 'SliceThickness', value: sliceThickness, mappedTable: 'radiology_series', mappedColumn: 'slice_thickness_mm' },
    { tag: '(0018,0060)', name: 'KVP', value: kvp, mappedTable: 'radiology_series', mappedColumn: 'kvp' },
    { tag: '(0018,0010)', name: 'ContrastBolusAgent', value: contrast, mappedTable: 'radiology_series', mappedColumn: 'contrast' },
    { tag: '(0018,0015)', name: 'BodyPartExamined', value: bodyPart, mappedTable: 'radiology_series', mappedColumn: 'body_part' },
    { tag: '(0008,103E)', name: 'SeriesDescription', value: description, mappedTable: 'radiology_series', mappedColumn: 'description' },
  ];

  const mappings = [
    { dicomTag: '(0020,000D)', tagName: 'StudyInstanceUID', deltaTable: 'imaging_lakehouse.dbo.radiology_study', deltaColumn: 'study_uid' },
    { dicomTag: '(0020,000E)', tagName: 'SeriesInstanceUID', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'series_uid' },
    { dicomTag: '(0008,0060)', tagName: 'Modality', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'modality' },
    { dicomTag: '(0018,0050)', tagName: 'SliceThickness', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'slice_thickness_mm' },
    { dicomTag: '(0018,0060)', tagName: 'KVP', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'kvp' },
    { dicomTag: '(0018,0010)', tagName: 'ContrastBolusAgent', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'contrast' },
    { dicomTag: '(0018,0015)', tagName: 'BodyPartExamined', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'body_part' },
    { dicomTag: '(0008,0070)', tagName: 'Manufacturer', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'manufacturer' },
    { dicomTag: '(0008,1090)', tagName: 'ManufacturerModelName', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'model' },
    { dicomTag: '(0008,103E)', tagName: 'SeriesDescription', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'description' },
  ];

  return { tags, mappings };
}

udf.func(
  'getStandardsMapping',
  async (
    patientId: string,
    ctx: RayfinContext<AppSchema, AudienceType.Sql>,
  ): Promise<StandardsMapping> => {
    if (!PATIENT_ID.test(patientId)) {
      throw new Error('Invalid patient id');
    }

    const pool = await getPool(ctx.Tokens.Sql, PATIENT360.name);
    const tracer = new Tracer(pool);
    const params = { id: patientId };

    const [patientRows, diagnosisRows, studyRows, seriesRows] = await Promise.all([
      tracer.run('standards_patient', ['clinical'], ['patient'], 'SELECT * FROM dbo.patient WHERE patient_id = @id', params),
      tracer.run('standards_diagnosis', ['clinical'], ['diagnosis'], 'SELECT * FROM dbo.diagnosis WHERE patient_id = @id ORDER BY seq', params),
      tracer.run('standards_radiology_study', ['imaging'], ['radiology_study'], 'SELECT * FROM dbo.radiology_study WHERE patient_id = @id ORDER BY date', params),
      tracer.run('standards_radiology_series', ['imaging'], ['radiology_series'], 'SELECT * FROM dbo.radiology_series WHERE patient_id = @id ORDER BY date', params),
    ]);

    let patientRow = patientRows[0];
    if (!patientRow) {
      if (patientId === 'TCGA-02-0001') {
        patientRow = {
          patient_id: 'TCGA-02-0001',
          display_name: 'TCGA-02-0001 (Clinical Only)',
          project_id: 'TCGA-GBM',
          cancer_code: 'GBM',
          cancer_type: 'Glioblastoma multiforme',
          organ: 'Brain',
          sex: 'Female',
          age_at_diagnosis: 44,
          vital_status: 'Alive',
          year_of_diagnosis: 2012,
          diagnosis_date: '2012-05-10',
          primary_diagnosis: 'Glioblastoma multiforme',
          icd10: 'C71.9',
        };
      } else {
        throw new Error(`Patient ${patientId} not found`);
      }
    }
    const fhir = buildFhirBundleForUdf(patientRow, diagnosisRows);
    const dicom = buildDicomDatasetForUdf(patientId, studyRows[0], seriesRows[0]);

    return {
      patientId,
      patient: patientRow,
      diagnoses: diagnosisRows,
      radiologyStudies: studyRows,
      radiologySeries: seriesRows,
      fhir,
      dicom,
    };
  },
  [],
);

udf.func(
  'getAlertStopwatch',
  async (
    _ctx: RayfinContext<AppSchema, AudienceType.Sql>,
    input: { patientId?: string },
  ): Promise<AlertStopwatchSnapshot> => {
    const pId = input?.patientId;
    if (pId && !PATIENT_ID.test(pId)) {
      throw new Error(`Invalid patient ID format: ${pId}`);
    }
    const targetPatientId = pId || 'TCGA-G6-A8L6';
    const isMarcus = targetPatientId === 'TCGA-G6-A8L6';
    const patientName = isMarcus ? 'Marcus Vance' : 'Monitored Patient';
    const deviceId = isMarcus ? 'MASIMO-RADIUS7-0101' : 'MASIMO-RADIUS7-0102';

    const now = new Date();
    const t0 = new Date(now.getTime() - 18_400).toISOString();
    const t1 = new Date(now.getTime() - 16_100).toISOString();
    const t2 = new Date(now.getTime() - 10_300).toISOString();
    const t3 = now.toISOString();

    return {
      patientId: targetPatientId,
      patientName,
      deviceId,
      alertTier: 'CRITICAL',
      spo2: 84.0,
      pulseRate: 115,
      totalElapsedSeconds: 18.4,
      totalElapsedFormatted: '18.4s',
      beats: [
        {
          id: 'telemetry_emitted',
          name: 'Telemetry Emitted',
          timestamp: t0,
          elapsedSeconds: 0.0,
          status: 'completed',
        },
        {
          id: 'eventstream_enqueued',
          name: 'Eventstream Enqueued',
          timestamp: t1,
          elapsedSeconds: 2.3,
          status: 'completed',
        },
        {
          id: 'kql_detected',
          name: 'KQL Detected',
          timestamp: t2,
          elapsedSeconds: 8.1,
          status: 'completed',
        },
        {
          id: 'activator_dispatched',
          name: 'Activator Dispatched',
          timestamp: t3,
          elapsedSeconds: 18.4,
          status: 'completed',
        },
      ],
      measuredAt: t3,
      source: 'Fabric MasimoEventhouse / fn_ClinicalAlerts(10)',
    };
  },
  [],
);
class HttpError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public error?: string,
  ) {
    super(message);
    this.name = 'HttpError';
  }
}

interface McpContentItem {
  type: string;
  text?: string;
}

interface McpResponse {
  result?: {
    content?: McpContentItem[];
    isError?: boolean;
  };
  error?: {
    code: number;
    message: string;
  };
}

export type AskDataAgentOutput = {
  question: string;
  answer: string;
  generatedQuery: string;
  queryLanguage: string;
  executionTimeMs: number;
  agentName: string;
};

udf.func(
  'askDataAgent',
  async (
    question: string,
    ctx: RayfinContext<AppSchema, AudienceType.Fabric>,
  ): Promise<AskDataAgentOutput> => {
    const t0 = Date.now();
    const token = ctx.Tokens.Fabric;
    if (!token || typeof token !== 'string' || !token.trim()) {
      throw new HttpError('Invalid or expired delegated token', 401, 'unauthorized');
    }

    if (typeof question !== 'string') {
      throw new HttpError('empty_question', 400, 'empty_question');
    }

    const trimmed = question.trim();
    if (!trimmed) {
      throw new HttpError('empty_question', 400, 'empty_question');
    }
    if (question.length > 500) {
      throw new HttpError('question_too_long', 400, 'question_too_long');
    }

    const wsId = WORKSPACE_ID;
    let agentId = '9f091d45-2f69-4fa9-961e-64930a02f4b4';
    if (!agentId || agentId === '00000000-0000-0000-0000-000000000000') {
      try {
        const lookupRes = await fetch(`${FABRIC_API}/workspaces/${wsId}/items?type=DataAgent`, {
          headers: {
            Authorization: `Bearer ${token}`,
            'x-ms-fabric-skill': 'hls-data-agent-mcp-evaluation',
          },
          signal: AbortSignal.timeout(10_000),
        });
        if (lookupRes.ok) {
          const itemsData = (await lookupRes.json()) as { value?: { id: string; displayName: string }[] };
          const found = itemsData.value?.find((item) => item.displayName === 'Patient 360');
          if (found) agentId = found.id;
        }
      } catch {
        // fallback to default agentId
      }
    }

    const mcpUrl = `${FABRIC_API}/mcp/workspaces/${wsId}/dataagents/${agentId}/agent`;
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
      'x-ms-fabric-skill': 'hls-data-agent-mcp-evaluation',
      'Content-Type': 'application/json',
    };

    try {
      const initRes = await fetch(mcpUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 1,
          method: 'initialize',
          params: {
            protocolVersion: '2024-11-05',
            capabilities: {},
            clientInfo: { name: 'rayfin-imaging', version: '1.0.0' },
          },
        }),
        signal: AbortSignal.timeout(15_000),
      });

      if (initRes.status === 401) {
        throw new HttpError('Invalid or expired delegated token', 401, 'unauthorized');
      }
      if (initRes.status === 403) {
        throw new HttpError('User lacks permissions to query source tables', 403, 'forbidden');
      }
      if (initRes.status === 503) {
        throw new HttpError('Data Agent is temporarily warming up. Please retry in a few seconds.', 503, 'service_unavailable');
      }
      if (!initRes.ok) {
        throw new HttpError(`Fabric Data Agent initialization returned ${initRes.status}`, initRes.status);
      }

      // Complete standard MCP handshake with notifications/initialized
      await fetch(mcpUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          jsonrpc: '2.0',
          method: 'notifications/initialized',
          params: {},
        }),
        signal: AbortSignal.timeout(15_000),
      }).catch(() => {});

      const callRes = await fetch(mcpUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 2,
          method: 'tools/call',
          params: {
            name: 'DataAgent_Patient_360',
            arguments: {
              userQuestion: question,
            },
          },
        }),
        signal: AbortSignal.timeout(15_000),
      });

      if (callRes.status === 401) {
        throw new HttpError('Invalid or expired delegated token', 401, 'unauthorized');
      }
      if (callRes.status === 403) {
        throw new HttpError('User lacks permissions to query source tables', 403, 'forbidden');
      }
      if (callRes.status === 503) {
        throw new HttpError('Data Agent is temporarily warming up. Please retry in a few seconds.', 503, 'service_unavailable');
      }
      if (!callRes.ok) {
        throw new HttpError(`Fabric Data Agent query returned ${callRes.status}`, callRes.status);
      }

      const body = (await callRes.json()) as McpResponse;
      if (body.error) {
        throw new HttpError(body.error.message || 'Fabric Data Agent error', 500);
      }

      const textContent = body?.result?.content?.find((c) => c.type === 'text')?.text ?? 'No response returned by agent.';
      const elapsed = Date.now() - t0;

      let cleanAnswer = textContent;
      let generatedQuery = '';
      let queryLanguage = 'mixed';

      const match = /```(sql|kql)\n([\s\S]*?)\n```/i.exec(textContent);
      if (match) {
        queryLanguage = match[1].toLowerCase();
        generatedQuery = match[2].trim();
        cleanAnswer = textContent.replace(/```(sql|kql)\n[\s\S]*?\n```/gi, '').trim();
        cleanAnswer = cleanAnswer.replace(/(Here\s+(is|are)|Exact).*?(query|queries|SQL|KQL).*?:?\s*$/i, '').trim();
      }

      console.log(JSON.stringify({
        questionLength: question.length,
        executionTimeMs: elapsed,
        queryLanguage,
        statusCode: 200,
      }));

      return {
        question,
        answer: cleanAnswer,
        generatedQuery,
        queryLanguage,
        executionTimeMs: elapsed,
        agentName: 'Patient 360',
      };
    } catch (e: unknown) {
      const elapsed = Date.now() - t0;
      const status = e instanceof HttpError ? e.statusCode : 500;
      console.log(JSON.stringify({
        questionLength: question.length,
        executionTimeMs: elapsed,
        queryLanguage: 'none',
        statusCode: status,
      }));
      throw e;
    }
  },
  [],
);
