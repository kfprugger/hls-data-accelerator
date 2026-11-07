/**
 * Local mode backend (`npm run dev:local`): the three Rayfin functions (getCohort, getPatient, getDataMap)
 * re-implemented over the pipeline output in work/, so the app runs on a laptop with no Fabric capacity.
 *
 * The parquet files in work/tables/<silo>/ are exactly what pipeline/upload_onelake.py writes to each silo's
 * Delta tables. DuckDB exposes them as `dbo.<table>` views, standing in for the patient360 shortcuts, and runs
 * the same queries as rayfin/functions/src/function_app.ts (translated from T-SQL). Keep the two in step:
 * the response shapes are checked against the generated function types.
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'fs';
import { resolve } from 'path';

import type { DuckDBInstance } from '@duckdb/node-api';

import type { AppFunctionsSchema } from '../rayfin/functions/src/types';

export type Cohort = AppFunctionsSchema['getCohort']['output'];
export type CohortPatient = Cohort['patients'][number];
export type PatientBundle = AppFunctionsSchema['getPatient']['output'];
export type DataMap = AppFunctionsSchema['getDataMap']['output'];
export type WardFlowCohortSnapshot = AppFunctionsSchema['getWardFlowCohort']['output'];
export type AskDataAgentResponse = AppFunctionsSchema['askDataAgent']['output'];
type Provenance = Cohort['provenance'];
type QueryTrace = Provenance['queries'][number];
type FileAccess = PatientBundle['access']['slide'];
type Row = PatientBundle['patient'];
type Cell = Row[string];
type Silo = 'clinical' | 'genomics' | 'imaging';

const SILOS: Record<Silo, { name: string; role: string }> = {
  clinical: { name: 'clinical_lakehouse', role: 'EHR and cancer registry' },
  genomics: { name: 'genomics_lakehouse', role: 'Sequencing core' },
  imaging: { name: 'imaging_lakehouse', role: 'PACS and digital pathology' },
};
const PATIENT_ID = /^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$/;
const ENDPOINT = 'DuckDB on this computer (work/tables/*.parquet)';

/** Where each silo's Files area lives under work/, keyed by the first path segment (see upload_onelake.py). */
export function fileRoots(work: string): Record<Silo, Record<string, string>> {
  return {
    clinical: { reports: resolve(work, 'raw', 'reports') },
    genomics: {},
    imaging: {
      slides: resolve(work, 'lakehouse', 'imaging', 'slides'),
      radiology: resolve(work, 'lakehouse', 'imaging', 'radiology'),
    },
  };
}

/* ------------------------------------------------------------------ DuckDB */

function normalise(value: unknown): Cell {
  if (value === null || value === undefined) return null;
  if (typeof value === 'bigint') return Number(value);
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'string') return value;
  return String(value);
}

class Tracer {
  readonly queries: QueryTrace[] = [];
  private readonly started = Date.now();

  constructor(private readonly db: DuckDBInstance) {}

  /** One connection per query, so the patient's queries run in parallel like they do on the SQL endpoint. */
  async run(id: string, silos: Silo[], tables: string[], text: string, params: Record<string, string> = {}): Promise<Row[]> {
    const t0 = Date.now();
    const connection = await this.db.connect();
    try {
      const reader = await connection.runAndReadAll(text, params);
      const out = reader.getRowObjectsJS().map((r) => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, normalise(v)])));
      this.queries.push({ id, silos, tables, rows: out.length, ms: Date.now() - t0 });
      return out;
    } finally {
      connection.closeSync();
    }
  }

  provenance(showcaseSql: string): Provenance {
    return {
      workspace: 'this computer (local mode)',
      endpoint: ENDPOINT,
      database: 'patient360 (DuckDB views over work/tables)',
      queries: this.queries,
      totalMs: Date.now() - this.started,
      showcaseSql: showcaseSql.trim(),
      servedAt: new Date().toISOString(),
    };
  }
}

/* ------------------------------------------------------------------ Queries (DuckDB versions of function_app.ts) */

const COHORT_SQL = `
WITH ranked AS (
  SELECT patient_id, CONCAT(gene, ' ', REPLACE(protein_change, 'p.', '')) AS label,
         ROW_NUMBER() OVER (
           PARTITION BY patient_id
           ORDER BY CASE WHEN gene IN ('TP53','KRAS','EGFR','PIK3CA','VHL','ERBB2','BRAF','SPOP','MET','POLE',
                                       'APC','PTEN','BAP1','ARID1A','CDKN2A','MTOR','SETD2','PBRM1') THEN 0 ELSE 1 END,
                    vaf DESC) AS rn
  FROM dbo.somatic_mutation
  WHERE is_driver_gene
    AND mutation_type NOT IN ('Silent', 'Intron', '3''UTR', '5''UTR', 'RNA', 'IGR', '5''Flank', '3''Flank')
), d AS (
  SELECT patient_id, STRING_AGG(label, '; ' ORDER BY rn) AS drivers FROM ranked WHERE rn <= 3 GROUP BY patient_id
)
SELECT p.patient_id, p.display_name, p.cancer_code, p.cancer_type, p.organ, p.sex, p.age_at_diagnosis,
       p.race, p.stage, p.vital_status, p.year_of_diagnosis, p.days_to_last_contact,
       m.tmb, m.msi_status, m.subtype, d.drivers,
       CAST(s.width AS DOUBLE) * s.height / 1e9 AS slide_gigapixels, s.thumbnail_path,
       (SELECT COUNT(*) FROM dbo.radiology_series r WHERE r.patient_id = p.patient_id) AS radiology_series
FROM dbo.patient p                                            -- clinical_lakehouse
JOIN dbo.molecular_profile m ON m.patient_id = p.patient_id   -- genomics_lakehouse
JOIN dbo.pathology_slide s  ON s.patient_id = p.patient_id AND s.role = 'diagnostic'  -- imaging_lakehouse
LEFT JOIN d ON d.patient_id = p.patient_id
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
WHERE p.patient_id = $id`;

/* ------------------------------------------------------------------ Inventory (as upload_onelake.py builds it) */

const FILE_FOLDERS: Record<Silo, [string, string[], string][]> = {
  clinical: [
    ['Files/reports', ['raw', 'reports'], 'Scanned pathology reports (PDF, GDC)'],
    ['Files/raw/gdc', ['raw', 'clinical'], 'GDC clinical records (JSON)'],
    ['Files/raw/synthea', ['synthea', 'out'], 'Synthea output (CSV)'],
  ],
  genomics: [
    ['Files/raw/cbioportal', ['fetched'], 'cBioPortal and GDC extracts (JSON)'],
    ['Files/raw/panimmune', ['sources', 'panimmune'], 'Immune landscape data files (GDC)'],
  ],
  imaging: [
    ['Files/raw/slides', ['raw', 'slides'], 'Original whole-slide images (Aperio SVS)'],
    ['Files/raw/dicom', ['raw', 'dicom'], 'Original CT and MR series (DICOM)'],
    ['Files/raw/seg', ['raw', 'seg'], 'AI segmentations (DICOM SEG)'],
    ['Files/raw/til', ['raw', 'til'], 'AI TIL maps (DICOM SEG)'],
    ['Files/slides', ['lakehouse', 'imaging', 'slides'], 'Deep Zoom tile pyramids (JPEG)'],
    ['Files/radiology', ['lakehouse', 'imaging', 'radiology'], 'Browser-ready volumes (NIfTI)'],
  ],
};

function folderStats(path: string): { files: number; bytes: number } {
  if (!existsSync(path)) return { files: 0, bytes: 0 };
  const st = statSync(path);
  if (st.isFile()) return { files: 1, bytes: st.size };
  let files = 0;
  let bytes = 0;
  const stack = [path];
  while (stack.length) {
    const dir = stack.pop()!;
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = resolve(dir, e.name);
      if (e.isDirectory()) stack.push(p);
      else if (e.isFile()) {
        files += 1;
        bytes += statSync(p).size;
      }
    }
  }
  return { files, bytes };
}

/* ------------------------------------------------------------------ API */

export type LocalApi = {
  getCohort(origin: string): Promise<Cohort>;
  getPatient(patientId: string, origin: string): Promise<PatientBundle>;
  getDataMap(): Promise<DataMap>;
  getWardFlowCohort(): Promise<WardFlowCohortSnapshot>;
  askDataAgent(question: string): Promise<AskDataAgentResponse>;
};
export function createLocalApi(work: string): LocalApi {
  const tablesDir = resolve(work, 'tables');
  let ready: Promise<DuckDBInstance> | null = null;
  const tables: Record<Silo, string[]> = { clinical: [], genomics: [], imaging: [] };

  const connect = () =>
    (ready ??= (async () => {
      if (!existsSync(tablesDir)) {
        throw new Error(`No tables in ${tablesDir}. Build them with the pipeline (see README, "Run it locally").`);
      }
      const { DuckDBInstance } = await import('@duckdb/node-api');
      const instance = await DuckDBInstance.create(':memory:');
      const db = await instance.connect();
      // SQL Server sorts NULL first ascending and compares strings case-insensitively; match it.
      await db.run(`SET GLOBAL default_null_order = 'nulls_first_on_asc_last_on_desc'`);
      await db.run(`SET GLOBAL default_collation = 'nocase'`);
      await db.run('CREATE SCHEMA dbo');
      for (const silo of Object.keys(SILOS) as Silo[]) {
        const dir = resolve(tablesDir, silo);
        tables[silo] = existsSync(dir)
          ? readdirSync(dir).filter((f) => f.endsWith('.parquet')).map((f) => f.slice(0, -'.parquet'.length)).sort()
          : [];
        for (const t of tables[silo]) {
          const file = resolve(dir, `${t}.parquet`).replace(/'/g, "''");
          await db.run(`CREATE VIEW dbo."${t}" AS SELECT * FROM read_parquet('${file}')`);
        }
      }
      db.closeSync();
      return instance;
    })().catch((e) => {
      ready = null;
      throw e;
    }));

  const access = (origin: string, silo: Silo, path: string): FileAccess => ({
    baseUrl: `${origin}/local-files/${silo}`,
    query: '',
    expiresOn: '',
    scope: `${SILOS[silo].name}/Files/${path} (local: work/)`,
    silo,
  });

  let inventory: Promise<void> | null = null;
  const buildInventory = (instance: DuckDBInstance) =>
    (inventory ??= (async () => {
      const db = await instance.connect();
      for (const silo of Object.keys(SILOS) as Silo[]) {
        const rows: string[] = [];
        for (const t of tables[silo]) {
          const n = await db.runAndReadAll(`SELECT COUNT(*) AS n FROM dbo."${t}"`);
          const bytes = statSync(resolve(tablesDir, silo, `${t}.parquet`)).size;
          rows.push(`('table', '${t}', ${Number(n.getRowObjectsJS()[0].n)}, NULL, ${bytes}, NULL)`);
        }
        for (const [name, parts, desc] of FILE_FOLDERS[silo]) {
          const { files, bytes } = folderStats(resolve(work, ...parts));
          rows.push(`('files', '${name}', NULL, ${files}, ${bytes}, '${desc.replace(/'/g, "''")}')`);
        }
        await db.run(
          `CREATE OR REPLACE TABLE dbo.${silo}_inventory AS
           SELECT * FROM (VALUES ${rows.join(', ')}) v(kind, name, "rows", files, bytes, description)`
        );
      }
      db.closeSync();
    })().catch((e) => {
      inventory = null;
      throw e;
    }));

  return {
    async getCohort(origin) {
      const tracer = new Tracer(await connect());
      const list = await tracer.run(
        'cohort',
        ['clinical', 'genomics', 'imaging'],
        ['patient', 'molecular_profile', 'pathology_slide', 'somatic_mutation', 'radiology_series'],
        COHORT_SQL
      );
      const patients = list.map((r) => {
        const thumb = r.thumbnail_path ? String(r.thumbnail_path) : null;
        const rest = { ...r };
        delete rest.thumbnail_path;
        return {
          ...(rest as unknown as Omit<CohortPatient, 'thumbnailUrl' | 'radiology_series'>),
          radiology_series: Number(r.radiology_series ?? 0),
          thumbnailUrl: thumb ? `${origin}/local-files/imaging/${thumb}` : null,
        } satisfies CohortPatient;
      });
      return { patients, provenance: tracer.provenance(COHORT_SQL) };
    },

    async getPatient(patientId, origin) {
      if (!PATIENT_ID.test(patientId)) throw new Error('Invalid patient id');
      const tracer = new Tracer(await connect());
      const params = { id: patientId };
      const q = (id: string, silo: Silo, table: string, text: string) => tracer.run(id, [silo], [table], text, params);
      const where = 'WHERE patient_id = $id';

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
          params
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
          `SELECT encounter_id, date, description, reason FROM dbo."procedure" ${where} ORDER BY date`),
        q('careplans', 'clinical', 'careplan',
          `SELECT encounter_id, start, stop, description, reason FROM dbo.careplan ${where} ORDER BY start`),
        q('report', 'clinical', 'pathology_report', `SELECT * FROM dbo.pathology_report ${where} ORDER BY part`),
        q('summary', 'clinical', 'patient_summary', `SELECT * FROM dbo.patient_summary ${where}`),
        q('profile', 'genomics', 'molecular_profile', `SELECT * FROM dbo.molecular_profile ${where}`),
        q('drivers', 'genomics', 'somatic_mutation',
          `SELECT gene, protein_change, mutation_type, variant_type, chromosome, start_pos, vaf
           FROM dbo.somatic_mutation ${where} AND is_driver_gene ORDER BY vaf DESC`),
        q('mutationPositions', 'genomics', 'somatic_mutation',
          `SELECT chromosome, start_pos, mutation_type FROM dbo.somatic_mutation ${where}`),
        q('mutationCounts', 'genomics', 'somatic_mutation',
          `SELECT mutation_type, COUNT(*) AS n FROM dbo.somatic_mutation ${where} GROUP BY mutation_type ORDER BY n DESC`),
        q('segments', 'genomics', 'copy_number_segment',
          `SELECT chromosome, start_pos, end_pos, segment_mean FROM dbo.copy_number_segment ${where}`),
        q('copyNumber', 'genomics', 'gene_copy_number',
          `SELECT gene, alteration, "call", is_driver_gene FROM dbo.gene_copy_number ${where}`),
        q('expression', 'genomics', 'gene_expression', `SELECT gene, z_score FROM dbo.gene_expression ${where}`),
        q('immuneCells', 'genomics', 'immune_cell_fraction', `SELECT cell_type, fraction FROM dbo.immune_cell_fraction ${where}`),
        tracer.run(
          'reference',
          ['genomics'],
          ['cohort_reference', 'molecular_profile'],
          `SELECT r.metric, r.n, r.quantiles_json FROM dbo.cohort_reference r
           JOIN dbo.molecular_profile m ON m.cohort_study = r.cohort_study WHERE m.patient_id = $id`,
          params
        ),
        q('slides', 'imaging', 'pathology_slide', `SELECT * FROM dbo.pathology_slide ${where} ORDER BY sort_order`),
        q('radiologyStudies', 'imaging', 'radiology_study', `SELECT * FROM dbo.radiology_study ${where} ORDER BY date`),
        q('radiologySeries', 'imaging', 'radiology_series', `SELECT * FROM dbo.radiology_series ${where} ORDER BY date`),
      ]);
      if (!patient.length) throw new Error(`Patient ${patientId} not found`);

      const reportRow = report[0] ?? null;
      const id = patientId.toLowerCase();
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
        access: {
          slide: access(origin, 'imaging', `slides/${id}`),
          radiology: access(origin, 'imaging', `radiology/${id}`),
          report: access(origin, 'clinical', String(reportRow?.pdf_path ?? `reports/${patientId}.pdf`)),
        },
        provenance: tracer.provenance(HEADER_SQL),
      };
    },

    async getDataMap() {
      const db = await connect();
      const tracer = new Tracer(db);
      const t0 = Date.now();
      await buildInventory(db);
      const silos = Object.keys(SILOS) as Silo[];
      const inventoryRows = await Promise.all(
        silos.map((silo) =>
          tracer.run(
            `${silo}_inventory`,
            [silo],
            [`${silo}_inventory`],
            `SELECT kind, name, "rows", files, bytes, description FROM dbo.${silo}_inventory ORDER BY kind DESC, bytes DESC`
          )
        )
      );
      // The shortcuts upload_onelake.py creates in patient360; here each is a DuckDB view or a work/ folder.
      const shortcuts = [
        ...silos.flatMap((silo) =>
          [...tables[silo], `${silo}_inventory`].map((t) => ({
            path: 'Tables',
            name: t,
            targetItem: SILOS[silo].name,
            targetPath: `Tables/${t}`,
            silo,
          }))
        ),
        ...silos.map((silo) => ({ path: 'Files', name: silo, targetItem: SILOS[silo].name, targetPath: 'Files', silo })),
      ];
      tracer.queries.push({ id: 'shortcuts', silos: [], tables: [], rows: shortcuts.length, ms: Date.now() - t0 });
      const sourceSilos = Array.from(
        new Set(shortcuts.map((s) => (s.silo ? SILOS[s.silo]?.name ?? `${s.silo}_lakehouse` : s.targetItem)).filter(Boolean)),
      );
      const zeroCopy = {
        copiesMade: 0 as const,
        shortcutCount: shortcuts.length,
        sourceSilos,
        physicalBytesInPatient360: 0 as const,
      };
      let databricksInterop: DataMap['databricksInterop'] = null;
      const candidatePaths = [
        resolve(work, '..', 'local', 'fixtures', 'databricks_proof.json'),
        resolve(work, 'fixtures', 'databricks_proof.json'),
        resolve(process.cwd(), 'local', 'fixtures', 'databricks_proof.json'),
        resolve(process.cwd(), 'rayfin-imaging', 'local', 'fixtures', 'databricks_proof.json'),
      ];
      for (const p of candidatePaths) {
        if (existsSync(p)) {
          try {
            databricksInterop = JSON.parse(readFileSync(p, 'utf-8'));
            break;
          } catch {
            databricksInterop = null;
          }
        }
      }
      return {
        workspace: { id: 'local', name: 'this computer (local mode)', portalUrl: '' },
        patient360: { id: 'local', name: 'patient360', portalUrl: '', sqlEndpoint: ENDPOINT, shortcuts, zeroCopy },
        zeroCopy,
        databricksInterop,
        silos: silos.map((silo, i) => ({ silo, id: silo, ...SILOS[silo], portalUrl: '', items: inventoryRows[i] })),
        provenance: tracer.provenance('SELECT kind, name, rows, files, bytes FROM dbo.<silo>_inventory'),
      };
    },

    async getWardFlowCohort() {
      const now = new Date().toISOString();
      const conditions = [
        'Advanced heart failure, device-supported',
        'Post-transplant surveillance, year 1',
        'Bridge-to-decision, transitional support',
        'Paroxysmal arrhythmia, home monitored',
        'Cardiogenic shock, recovering',
      ];
      const settings = ['inpatient', 'home-monitored', 'outpatient'];
      const devices = ['Ventricular assist device', 'Intra-aortic balloon pump', 'Implantable rhythm monitor', null];
      const initialsList = ['S.F.', 'S.S.', 'S.A.', 'C.S.', 'C.L.', 'J.M.', 'R.K.', 'T.W.', 'L.G.', 'M.B.', 'A.P.', 'D.H.', 'E.R.', 'H.V.', 'K.N.', 'N.T.', 'P.W.', 'V.C.', 'W.D.', 'B.K.', 'F.M.', 'G.R.', 'J.L.', 'K.S.'];
      const subjects = initialsList.map((initials, i) => {
        const stress = i < 3 ? 0.85 : i < 8 ? 0.58 : i < 14 ? 0.38 : 0.16;
        const dev = devices[i % devices.length];
        return {
          id: i === 0 ? '0efc0058-f344-5439-a7cc-30425ed7ba71' : i === 1 ? '106a9b6b-2de7-fc29-b221-1ad1f821b33a' : i === 2 ? '15cde951-9dc7-e457-6723-15a213c0839d' : `CAL-${String(i + 1).padStart(4, '0')}`,
          initials,
          fullName: `Synthetic Patient ${i + 1}`,
          gender: i % 2 === 0 ? 'female' : 'male',
          age: 48 + (i * 3) % 34,
          ageBand: `${45 + ((i * 5) % 35)}-${49 + ((i * 5) % 35)}`,
          careSetting: settings[i % settings.length],
          encounterId: `ENC-${i + 1}`,
          conditionDisplay: conditions[i % conditions.length],
          attendingRole: i % 2 === 0 ? 'attending cardiologist' : 'attending intensivist',
          deviceId: dev ? `DEV-${1000 + i}` : null,
          deviceKind: dev,
          deviceSerial: dev ? `SN-${2000 + i}` : null,
          pulseOximeterDeviceId: i % 8 === 7 ? null : `MASIMO-RADIUS7-${String(i + 1).padStart(4, '0')}`,
          refreshedAt: now,
          observations: {
            lactate: Number((1.0 + stress * 3.8).toFixed(2)),
            map: Number((86 - stress * 28).toFixed(1)),
            pulseRate: i % 8 === 7 ? null : Math.round(72 + stress * 54),
            spo2: i % 8 === 7 ? null : Number((98 - stress * 9).toFixed(1)),
            deviceFlow: dev ? Number((100 - stress * 38).toFixed(1)) : null,
          },
          observedAt: now,
          encounterCount: 4 + (i % 9),
          medicationCount: 12 + (i % 15),
          imagingStudyCount: i < 3 ? 2 : 1,
          openCareGaps: i % 4,
          has3dVolume: i < 3,
          volumeStudyId: i === 0 ? 'cohort-0efc0058' : i === 1 ? 'cohort-106a9b6b' : i === 2 ? 'cohort-15cde951' : null,
        };
      });
      return {
        workspaceId: 'local',
        workspaceName: 'this computer (local mode)',
        sqlEndpoint: ENDPOINT,
        database: 'healthcare1_reporting_gold (local)',
        goldRefreshedAt: now,
        servedAt: now,
        totalMs: 4,
        subjects,
        enrollableCount: 4,
      };
    },
    async askDataAgent(question: string): Promise<AskDataAgentResponse> {
      const q = question.toLowerCase();
      // Fixture 1: Marcus Vance vitals + cancer stage
      if (q.includes('marcus') || q.includes('vance') || q.includes('a8l6')) {
        return {
          question,
          answer:
            "Patient Marcus Vance (TCGA-G6-A8L6) is a 55-year-old male diagnosed with Stage IV Clear cell renal cell carcinoma (KIRC). Recent Masimo Radius-7 telemetry (device MASIMO-RADIUS7-0101) indicates SpO2 of 96.5% (normal range 95-100%), pulse rate 78 bpm, respiration rate 16 breaths/min, and blood pressure 128/82 mmHg.",
          generatedQuery:
`-- Lakehouse SQL Query: Patient demographics & staging
SELECT p.patient_id, p.display_name, p.cancer_type, d.stage, d.grade, d.tumor_site
FROM dbo.patient p
JOIN dbo.diagnosis d ON p.patient_id = d.patient_id
WHERE p.display_name LIKE '%Marcus Vance%' OR p.patient_id = 'TCGA-G6-A8L6';

-- Eventhouse KQL Query: Masimo Radius-7 Real-Time Telemetry
TelemetryRaw
| where DeviceId == 'MASIMO-RADIUS7-0101'
| where Timestamp >= ago(1h)
| summarize arg_max(Timestamp, SpO2, PulseRate, RespirationRate, BloodPressure) by DeviceId
| project Timestamp, DeviceId, SpO2, PulseRate, RespirationRate, BloodPressure`,
          queryLanguage: 'mixed',
          executionTimeMs: 420,
          agentName: 'Patient 360',
        };
      }

      // Fixture 2: Active critical alerts / SpO2 alerts
      if (q.includes('alert') || (q.includes('spo2') && !q.includes('marcus')) || q.includes('critical')) {
        return {
          question,
          answer:
            "Currently 2 devices have active SpO2 alerts in the last 60 minutes: Device MASIMO-RADIUS7-0033 reported SpO2 drop to 88.4% (Critical threshold: 90.0%), and Device MASIMO-RADIUS7-0012 reported SpO2 drop to 89.1% (Critical threshold: 90.0%). All other monitored subjects are within normal oxygenation parameters.",
          generatedQuery:
`TelemetryRaw
| where Timestamp >= ago(1h)
| where SpO2 < 90.0
| summarize MinSpO2 = min(SpO2), LatestTimestamp = max(Timestamp), AlertCount = count() by DeviceId
| join kind=inner (
    AlertHistory
    | where Timestamp >= ago(1h)
    | where Severity == 'Critical'
) on DeviceId
| project DeviceId, MinSpO2, AlertCount, LatestTimestamp`,
          queryLanguage: 'kql',
          executionTimeMs: 310,
          agentName: 'Patient 360',
        };
      }

      // Fixture 3: Cohort cancer distribution / respiratory
      if (q.includes('distribution') || q.includes('cohort') || q.includes('respiratory')) {
        return {
          question,
          answer:
            "Analysis of the 15-patient oncology research cohort shows 3 patients with Clear cell renal cell carcinoma (KIRC), 2 patients with Invasive breast carcinoma (BRCA), 2 patients with Lung adenocarcinoma (LUAD), and 8 patients across other solid tumor indications. Four patients present with concurrent respiratory conditions (COPD, asthma).",
          generatedQuery:
`SELECT p.cancer_code, p.cancer_type, COUNT(*) AS patient_count,
       STRING_AGG(p.display_name, ', ') AS patients
FROM dbo.patient p
GROUP BY p.cancer_code, p.cancer_type
ORDER BY patient_count DESC;`,
          queryLanguage: 'sql',
          executionTimeMs: 280,
          agentName: 'Patient 360',
        };
      }

      // Safe default / prompt injection response
      return {
        question,
        answer:
          "The Patient 360 Data Agent only answers clinical queries using approved Lakehouse and Eventhouse tables with delegated user authorization. Instructions to bypass safety boundaries or disclose system credentials cannot be executed.",
        generatedQuery:
`-- Query rejected: prompt injection or unauthorized system query detected.`,
        queryLanguage: 'none',
        executionTimeMs: 95,
        agentName: 'Patient 360',
      };
    },
  };
}
