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
    const tracer = new Tracer(await getPool(ctx.Tokens.Sql, PATIENT360.name));
    const list = await tracer.run(
      'cohort',
      ['clinical', 'genomics', 'imaging'],
      ['patient', 'molecular_profile', 'pathology_slide', 'somatic_mutation', 'radiology_series'],
      COHORT_SQL,
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
    return { patients, provenance: tracer.provenance(COHORT_SQL) };
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
        ['patient', 'molecular_profile', 'pathology_slide', 'radiology_study', 'radiology_series', 'observation'],
        HEADER_SQL,
        params,
      ),
      q('patient', 'clinical', 'patient', `SELECT * FROM dbo.patient ${where}`),
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
      provenance: tracer.provenance(HEADER_SQL),
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
