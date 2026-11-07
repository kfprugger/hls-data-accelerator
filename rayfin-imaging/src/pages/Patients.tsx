import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { ListColumn } from '@/components/Panel';
import { useCohort } from '@/hooks/useCohort';
import type { CohortPatient } from '@/lib/api';
import { fmtMs, fmtNum, fmtSpan, shortStage } from '@/lib/format';
import { LOCAL_DATA, STORE_NAME } from '@/lib/localMode';
import { PatientView } from '@/pages/PatientView';

/** Presentation order: the clearest genomics-to-treatment stories first. */
const DEMO_ORDER = [
  'TCGA-J2-8192', 'TCGA-E2-A152', 'TCGA-VQ-A91D', 'TCGA-FI-A2D5', 'TCGA-DD-A1EH', 'TCGA-G6-A8L6', 'TCGA-G4-6303',
  'TCGA-25-2042', 'TCGA-FD-A3SJ', 'TCGA-60-2722', 'TCGA-VR-AA4D', 'TCGA-VS-A9V3', 'TCGA-J4-A6G3', 'TCGA-G7-A8LE',
  'TCGA-KM-8441',
];

function byDemoOrder(a: CohortPatient, b: CohortPatient): number {
  const ia = DEMO_ORDER.indexOf(a.patient_id);
  const ib = DEMO_ORDER.indexOf(b.patient_id);
  return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
}

function drivers(p: CohortPatient): string {
  return p.drivers ? p.drivers.split(/;\s*/).join(' · ') : '–';
}

function outcome(p: CohortPatient): string {
  const span = fmtSpan(p.days_to_last_contact);
  return p.vital_status === 'Dead' ? `Died after ${span}` : `Alive at ${span}`;
}

function PatientRow({ p, current, onHover, query }: { p: CohortPatient; current: boolean; onHover: () => void; query: string }) {
  return (
    <Link to={`/p/${p.patient_id}${query}`} className="pt-row" aria-current={current} onMouseEnter={onHover}>
      <span className="min-w-0">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate text-[13.5px] font-medium">{p.display_name}</span>
          <span className="t-faint shrink-0 text-[11px]">
            {p.sex?.[0]} {p.age_at_diagnosis}
          </span>
        </span>
        <span className="t-muted block truncate text-[12.5px]">{p.cancer_type}</span>
        <span className="t-faint block truncate text-[11.5px]">
          {p.stage ? `Stage ${shortStage(p.stage)} · ` : ''}
          {outcome(p)}
        </span>
      </span>
    </Link>
  );
}

function CohortOverview() {
  const { cohort, loading, error } = useCohort();
  const navigate = useNavigate();
  const [showSql, setShowSql] = useState(false);
  if (error) return <div className="p-8 text-[13px]" style={{ color: 'var(--c-alert)' }}>{error}</div>;
  if (!cohort) return <div className="loading-bar" aria-label={loading ? 'Loading' : undefined} />;
  const q = cohort.provenance.queries[0];
  const deaths = cohort.patients.filter((p) => p.vital_status === 'Dead').length;
  const maxTmb = Math.max(...cohort.patients.map((p) => p.tmb ?? 0));
  return (
    <div className="mx-auto max-w-[1400px] px-8 py-8">
      <div className="t-label">Oncology cohort</div>
      <h1 className="t-display mt-1 text-[40px]">Longitudinal patient records</h1>
      <p className="t-muted mt-3 max-w-[92ch] text-[15px] leading-relaxed">
        Each record follows one patient from diagnosis through treatment, recurrence and last follow-up, with the
        clinical history, tumour genome, diagnostic slide and pre-treatment imaging side by side. Patients are real and
        de-identified, from The Cancer Genome Atlas. Each data type lives in its own Lakehouse, as it would in a
        hospital, and nothing is copied into the app. Select a patient to open their record.
      </p>
      <p className="num mt-5 text-[14px]">
        {cohort.patients.length} patients · {new Set(cohort.patients.map((p) => p.cancer_code)).size} cancer types ·{' '}
        {deaths} died during follow-up ·{' '}
        {fmtNum(cohort.patients.reduce((s, p) => s + (p.slide_gigapixels ?? 0), 0), 0)} gigapixels of pathology ·{' '}
        {cohort.patients.reduce((s, p) => s + p.radiology_series, 0)} CT and MRI series
      </p>

      <div className="mt-9 overflow-x-auto">
        <table className="tbl text-[13px]">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Cancer</th>
              <th>Stage</th>
              <th>Outcome</th>
              <th>Key alterations</th>
              <th className="text-right">Mutations per Mb</th>
              <th className="text-right">Slide</th>
              <th className="text-right">Scans</th>
            </tr>
          </thead>
          <tbody>
            {[...cohort.patients].sort(byDemoOrder).map((p) => (
              <tr key={p.patient_id} className="cursor-pointer hover:bg-[var(--surface)]" onClick={() => navigate(`/p/${p.patient_id}`)}>
                <td>
                  <div className="font-medium">{p.display_name}</div>
                  <div className="mono t-faint">{p.patient_id}</div>
                </td>
                <td>
                  <div>{p.cancer_type}</div>
                  <div className="t-faint text-[12px]">
                    {p.sex}, {p.age_at_diagnosis} · {p.race}
                  </div>
                </td>
                <td className="whitespace-nowrap">{shortStage(p.stage) || '–'}</td>
                <td className="whitespace-nowrap">
                  <span style={{ color: p.vital_status === 'Dead' ? 'var(--c-alert)' : undefined }}>{outcome(p)}</span>
                </td>
                <td className="mono max-w-[300px]">{drivers(p)}</td>
                <td className="text-right">
                  <div className="flex items-center justify-end gap-2">
                    <span className="num">{fmtNum(p.tmb, 1)}</span>
                    <span className="hbar w-[70px]">
                      <span
                        style={{
                          left: 0,
                          width: `${(Math.log10(1 + (p.tmb ?? 0)) / Math.log10(1 + maxTmb)) * 100}%`,
                          background: p.msi_status === 'MSI-high' || (p.tmb ?? 0) > 100 ? 'var(--c-gen)' : 'var(--ink-3)',
                        }}
                      />
                    </span>
                  </div>
                </td>
                <td className="num whitespace-nowrap text-right">{fmtNum(p.slide_gigapixels, 1)} GP</td>
                <td className="num text-right">{p.radiology_series}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 text-[12.5px]">
        <span className="t-faint">
          This table is one SQL statement over three Lakehouses, joined through{' '}
          {LOCAL_DATA ? 'DuckDB views over work/ (local mode)' : 'OneLake shortcuts'}:{' '}
          {q.rows} rows in {fmtMs(q.ms)}.
        </span>
        <span className="flex items-center gap-3">
          <span className="src"><span className="swatch sw-clinical" />clinical_lakehouse</span>
          <span className="src"><span className="swatch sw-genomics" />genomics_lakehouse</span>
          <span className="src"><span className="swatch sw-imaging" />imaging_lakehouse</span>
        </span>
        <button className="link t-muted" onClick={() => setShowSql((v) => !v)}>
          {showSql ? 'Hide the SQL' : 'Show the SQL'}
        </button>
      </div>
      {showSql && <pre className="code mt-3">{cohort.provenance.showcaseSql}</pre>}
    </div>
  );
}

const LIST_KEY = 'p360.list';

export function Patients() {
  const { id } = useParams();
  // Switching patient keeps the open tab, so the same view can be compared across patients.
  const [params] = useSearchParams();
  const keepTab = params.get('tab') ? `?tab=${encodeURIComponent(params.get('tab')!)}` : '';
  const { cohort, loading, getPatient } = useCohort();
  const [query, setQuery] = useState('');
  // The list folds to a rail by default so the record has room; the choice is remembered.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(LIST_KEY) !== 'open');
  const toggle = () => {
    setCollapsed((c) => {
      localStorage.setItem(LIST_KEY, c ? 'open' : 'collapsed');
      return !c;
    });
    // Viewers size themselves on window resize; tell them the column changed.
    window.setTimeout(() => window.dispatchEvent(new Event('resize')), 30);
  };
  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    const all = [...(cohort?.patients ?? [])].sort(byDemoOrder);
    if (!q) return all;
    return all.filter((p) =>
      [p.display_name, p.patient_id, p.cancer_type, p.organ, p.drivers, p.stage].some((v) => v?.toLowerCase().includes(q))
    );
  }, [cohort, query]);

  const count = cohort
    ? `${list.length} of ${cohort.patients.length} patients · read in ${fmtMs(cohort.provenance.totalMs)}`
    : loading
      ? `Reading the cohort from ${STORE_NAME}`
      : '';

  return (
    <div className="flex h-full">
      <ListColumn
        query={query}
        onQuery={setQuery}
        placeholder="Search name, cancer or gene"
        count={count}
        collapsed={collapsed}
        onToggle={toggle}
        rail={list.map((p) => (
          <Link
            key={p.patient_id}
            to={`/p/${p.patient_id}${keepTab}`}
            className="rail-item"
            aria-current={p.patient_id === id}
            title={`${p.display_name} · ${p.cancer_type}`}
            onMouseEnter={() => void getPatient(p.patient_id).catch(() => undefined)}
          >
            {p.display_name
              .split(' ')
              .map((w) => w[0])
              .join('')}
          </Link>
        ))}
      >
        <Link to="/patients" className="list-row text-[13px]" aria-current={!id}>
          Cohort overview
        </Link>
        <div className="list-heading">Patients</div>
        {list.map((p) => (
          <PatientRow
            key={p.patient_id}
            p={p}
            current={p.patient_id === id}
            onHover={() => void getPatient(p.patient_id).catch(() => undefined)}
            query={keepTab}
          />
        ))}
      </ListColumn>
      <main className="min-w-0 flex-1 overflow-y-auto" id="patient-scroll">
        {id ? <PatientView id={id} /> : <CohortOverview />}
      </main>
    </div>
  );
}
