import { memo, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import { ClinicalSection, NotesSection, ReportSection, type NoteAnchor } from '@/components/patient/Clinical';
import { GenomicsSection } from '@/components/patient/Genomics';
import { PathologyPanel, RadiologyFootnotes, RadiologyPanel } from '@/components/patient/Imaging';
import { MultimodalHero } from '@/components/patient/MultimodalHero';
import { MeasurementsPanel, PrimaryCareGlance } from '@/components/patient/PrimaryCare';
import { buildModel, LifeTimeline, noteMarks, type Mark, type Model, type Orientation } from '@/components/patient/Timeline';
import { TimelineDetail } from '@/components/patient/TimelineDetail';
import { Scrubber, type ScrubItem } from '@/components/Scrubber';
import { AlertStopwatchCard } from '@/components/AlertStopwatchCard';
import { usePatient } from '@/hooks/useCohort';
import { useNotes, type NotesState } from '@/hooks/useNotes';
import { num, parseJson, SILO_NAMES, str, type PatientBundle, type Silo } from '@/lib/api';
import { ageAt, fmtBytes, fmtDate, fmtMonth, fmtMs, fmtNum, fmtSpan, parseDate, plain, shortStage } from '@/lib/format';
import { LOCAL_DATA } from '@/lib/localMode';
import { itemsFor, tabDef, TAB_IDS, TABS, tabFor, type TabGroup, type TabId } from '@/lib/record';
import { OPEN_EVENT, type OpenRequest } from '@/lib/timelineLink';

export function personLine(b: PatientBundle): string {
  const p = b.patient;
  const sex = str(p.sex)?.toLowerCase() === 'female' ? 'woman' : 'man';
  const parts = [`${num(p.age_at_diagnosis)}-year-old ${sex} at diagnosis`, str(p.race), str(p.country)];
  const smoking = str(p.smoking_status);
  if (smoking) {
    const packs = num(p.pack_years);
    const s = /Non-Smoker/i.test(smoking) ? 'Never smoked' : smoking.startsWith('Current Reformed') ? 'Former smoker' : /Current Smoker/i.test(smoking) ? 'Current smoker' : smoking;
    parts.push(packs ? `${s}, ${packs} pack-years` : s);
  }
  return parts.filter(Boolean).join(' · ');
}

export function diseaseLine(b: PatientBundle): string {
  const p = b.patient;
  const tnm = [str(p.t_stage), str(p.n_stage), str(p.m_stage)].filter(Boolean).join(' ');
  const stage = str(p.stage) ? `stage ${shortStage(str(p.stage))}` : null;
  const gleason = num(p.gleason_score) ? `Gleason ${num(p.gleason_score)}` : null;
  const site = plain(str(p.tissue_of_origin)).replace(/^(.+), (\w+)$/, '$1 of $2');
  const where = [str(p.laterality), site].filter(Boolean).join(' ').toLowerCase();
  const head = [stage, gleason, tnm && `(${tnm})`].filter(Boolean).join(' ');
  return `${str(p.cancer_type)}${head ? `, ${head}` : ''}${where ? `, ${where}` : ''}`;
}

export function conditionSubtitle(b: PatientBundle): string {
  const p = b.patient;
  const stage = str(p.stage);
  const stg = stage ? `Stage ${shortStage(stage)}` : null;
  const cancer = str(p.cancer_type);
  const prettyCancer = cancer === 'Clear cell renal cell carcinoma'
    ? 'Clear Cell Renal Carcinoma'
    : (cancer ? cancer.charAt(0).toUpperCase() + cancer.slice(1) : '');
  if (stg && prettyCancer) return `${stg} ${prettyCancer}`;
  return stg || prettyCancer || 'Clinical Case';
}

export function outcomeText(b: PatientBundle): { label: string; value: string; alert: boolean } {
  const p = b.patient;
  const days = num(p.days_to_last_contact) ?? 0;
  if (str(p.vital_status) === 'Dead') return { label: 'Died', value: `${fmtSpan(num(p.days_to_death))} after diagnosis`, alert: true };
  return { label: 'Last contact', value: `Alive, ${fmtSpan(days)} after diagnosis`, alert: false };
}
function Modality({ silo, label, children, synthetic }: { silo: string; label: string; children: ReactNode; synthetic?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="t-label flex items-center gap-1.5">
        <span className={`swatch sw-${synthetic ? 'synthetic' : silo}`} />
        {label}
      </div>
      <div className="num mt-0.5 text-[13px]">{children}</div>
    </div>
  );
}

/** Short context that stays on screen with the name: cancer, stage, age and sex, outcome. */
function barLine(b: PatientBundle): string {
  const p = b.patient;
  const stage = str(p.stage) ? `stage ${shortStage(str(p.stage))}` : null;
  const sex = str(p.sex)?.toLowerCase() === 'female' ? 'F' : 'M';
  const out = outcomeText(b);
  const status = out.alert ? `Died ${out.value}` : out.value;
  return [str(p.cancer_type), stage, `${num(p.age_at_diagnosis)} ${sex}`, status].filter(Boolean).join(' · ');
}

/** Who the patient is, the key facts, and what each silo holds; the top of the Summary section. */
function Overview({ b, onProvenance, loadMs }: { b: PatientBundle; onProvenance: () => void; loadMs: number | null }) {
  const p = b.patient;
  const prof = b.profile ?? {};
  const out = outcomeText(b);
  const prov = b.provenance;
  const silos = new Set(prov.queries.flatMap((q) => q.silos));
  const slide = b.slide ?? {};
  const radBytes = b.radiologySeries.reduce((s, r) => s + (num(r.raw_bytes) ?? 0), 0);
  const allSlides = b.slides?.length ? b.slides : [slide];
  const gp = allSlides.reduce((s, x) => s + (num(x.width) ?? 0) * (num(x.height) ?? 0), 0) / 1e9;
  const slideBytes = allSlides.reduce((s, x) => s + (num(x.raw_bytes) ?? 0), 0);
  const slideCount = allSlides.length;
  return (
    <div className="mb-7">
      <div className="grid items-start gap-x-14 gap-y-5 xl:grid-cols-[minmax(0,1fr)_minmax(440px,auto)]">
        <div className="min-w-0">
          <div className="text-[19px] leading-snug">{diseaseLine(b)}</div>
          <div className="t-muted mt-1.5 text-[13.5px]">{personLine(b)}</div>
        </div>
        <dl className="facts grid-cols-2 pt-1">
          <div className="fact">
            <dt>Diagnosed</dt>
            <dd>
              {fmtMonth(str(p.diagnosis_date))}
              <div className="t-faint text-[12px]">year real, day synthetic</div>
            </dd>
          </div>
          <div className="fact">
            <dt>{out.label}</dt>
            <dd style={{ color: out.alert ? 'var(--c-alert)' : undefined }}>{out.value}</dd>
          </div>
          <div className="fact">
            <dt>Molecular subtype</dt>
            <dd className="mono">{str(prof.subtype)?.replace(/_/g, ' ') ?? '–'}</dd>
          </div>
          <div className="fact">
            <dt>Tumour mutations</dt>
            <dd>
              {fmtNum(num(prof.mutation_count), 0)}
              <span className="t-faint"> · {fmtNum(num(prof.tmb), 1)} per Mb</span>
            </dd>
          </div>
        </dl>
      </div>
      <div className="hair mt-5 grid grid-cols-2 gap-x-8 gap-y-3 border-t pt-4 md:grid-cols-3 xl:grid-cols-6">
        <Modality silo="clinical" label="Clinical Registry & Demographics">
          {b.diagnoses.length} diagnoses · {b.treatments.filter((t) => t.given).length} treatments · {b.followUps.length} follow-ups
        </Modality>
        <Modality silo="clinical" label="Primary care" synthetic>
          {b.encounters.length} visits · {fmtNum(b.observations.filter((o) => o.synthetic).length, 0)} results
        </Modality>
        <Modality silo="genomics" label="Somatic Mutations & Molecular Drivers">
          {fmtNum(num(prof.mutation_count), 0)} mutations · {b.segments.length} CN segments
        </Modality>
        <Modality silo="pathology" label={slideCount > 1 ? 'H&E slides' : 'Diagnostic slide'}>
          {slideCount > 1 ? `${slideCount} slides · ` : ''}
          {fmtNum(gp, 1)} gigapixels · {fmtBytes(slideBytes)} SVS
        </Modality>
        <Modality silo="radiology" label="Radiology">
          {b.radiologyStudies.length} {b.radiologyStudies.length === 1 ? 'study' : 'studies'} · {fmtBytes(radBytes)} DICOM
        </Modality>
        <button onClick={onProvenance} className="text-left" title="See every query that built this page">
          <div className="t-label flex items-center gap-1.5">
            <span className="swatch" style={{ background: 'var(--accent)' }} />
            Read in place
          </div>
          <div className="num mt-0.5 text-[13px] underline decoration-[var(--line-strong)] underline-offset-[3px] hover:decoration-[var(--accent)]">
            {prov.queries.length} queries · {silos.size} silos · {fmtMs(loadMs ?? prov.totalMs)} · 0 bytes copied
          </div>
        </button>
      </div>
    </div>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  clinical: 'Clinical',
  genomics: 'Genomics',
  pathology: 'Pathology',
  radiology: 'Radiology',
};

function Summary({ b }: { b: PatientBundle }) {
  const s = b.summary;
  if (!s) return <p className="t-faint text-[13px]">No summary has been written for this patient.</p>;
  const points = parseJson<{ source: string; text: string }[]>(s.points_json, []);
  return (
    <div className="hair grid gap-x-14 gap-y-6 border-t pt-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <div>
        <h2 className="t-display text-[25px] leading-tight">{str(s.headline)}</h2>
        <p className="lede mt-3">{str(s.summary)}</p>
        <p className="t-faint mt-4 max-w-[74ch] text-[11.5px]">{str(s.generated_by)}</p>
      </div>
      <div>
        <div className="t-label mb-1">What matters</div>
        <ul className="points">
          {points.map((pt) => (
            <li key={pt.text}>
              <span className={`swatch sw-${pt.source}`} title={SOURCE_LABEL[pt.source]} />
              <span>{pt.text}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ProvenanceDrawer({ b, onClose }: { b: PatientBundle; onClose: () => void }) {
  const prov = b.provenance;
  const bySilo = (['clinical', 'genomics', 'imaging'] as Silo[]).map((silo) => ({
    silo,
    queries: prov.queries.filter((q) => q.silos.length === 1 && q.silos[0] === silo),
  }));
  const cross = prov.queries.filter((q) => q.silos.length > 1);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const access = Object.values(b.access);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" aria-label="How this page was read">
        <div className="hair flex items-center justify-between border-b px-6 py-4">
          <div>
            <div className="t-label">Read in place</div>
            <div className="t-display text-[22px]">How this page was assembled</div>
          </div>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
        <div className="space-y-6 px-6 py-5 text-[13px]">
          <p className="t-muted">
          {LOCAL_DATA ? (
            <>
              The app queried <span className="mono">{prov.database}</span> on this computer: DuckDB views over the
              parquet tables in work/, standing in for the patient360 shortcuts and its SQL analytics endpoint. Images
              are read from the work/ folder.
            </>
          ) : (
            <>
              The app queried <span className="mono">{prov.database}</span>, a Lakehouse made only of OneLake shortcuts, through its
              SQL analytics endpoint. Every row below was read where it lives. Images stream from the imaging silo through
              read-only links scoped to this patient.
            </>
          )}
          </p>
          <div>
            <div className="t-label mb-1">One statement across all three silos</div>
            <pre className="code">{prov.showcaseSql}</pre>
          </div>
          {cross.length > 0 && (
            <div>
              <div className="t-label mb-1">Cross-silo queries</div>
              {cross.map((q) => (
                <div key={q.id} className="prov-row">
                  <span className="mono">{q.tables.join(', ')}</span>
                  <span className="num t-faint">{q.rows} rows</span>
                  <span className="num">{fmtMs(q.ms)}</span>
                </div>
              ))}
            </div>
          )}
          {bySilo.map(({ silo, queries }) => (
            <div key={silo}>
              <div className="t-label mb-1 flex items-center gap-1.5">
                <span className={`swatch sw-${silo}`} />
                {SILO_NAMES[silo]}
              </div>
              {queries.map((q) => (
                <div key={q.id} className="prov-row">
                  <span className="mono">{q.tables.join(', ')}</span>
                  <span className="num t-faint">{fmtNum(q.rows, 0)} rows</span>
                  <span className="num">{fmtMs(q.ms)}</span>
                </div>
              ))}
            </div>
          ))}
          <div>
            <div className="t-label mb-1">
              {LOCAL_DATA ? 'File access (local mode: read from work/ on this computer)' : 'Signed file access (read-only, expires in 55 minutes)'}
            </div>
            {access.map((a) => (
              <div key={a.scope} className="prov-row">
                <span className="mono">{a.scope}</span>
                <span className="t-faint">{a.error ? 'unavailable' : 'read'}</span>
                <span className="num">{a.expiresOn ? new Date(a.expiresOn).toLocaleTimeString() : ''}</span>
              </div>
            ))}
          </div>
          <div className="t-faint text-[12px]">
            Endpoint <span className="mono">{prov.endpoint}</span>. Served {new Date(prov.servedAt).toLocaleString()}.
          </div>
        </div>
      </aside>
    </>
  );
}


/* ================================================================== the record: timeline left, tabs right */

const WIDTH_KEY = 'p360.timelineWidth';
const HEIGHT_KEY = 'p360.timelineHeight';
const LAYOUT_KEY = 'p360.timelineLayout';
const COLLAPSED_KEY = 'p360.timelineCollapsed';
/** Size of the collapsed timeline strip (height on top, width on the left). */
const STRIP = { top: 112, left: 72 };
const KEEP_ALIVE: TabId[] = ['pathology', 'radiology', 'report'];

/** Tab groups, separated by a thin rule. */
const GROUPS: { id: TabGroup }[] = [{ id: 'overview' }, { id: 'primary' }, { id: 'cancer' }, { id: 'board' }];

/** Visits with numeric primary-care results: the items of the Measurements tab. */
function measuredVisits(b: PatientBundle): Set<string> {
  const out = new Set<string>();
  for (const o of b.observations) if (o.synthetic && o.encounter_id && num(o.value) !== null) out.add(`v:${str(o.encounter_id)}`);
  return out;
}

/** Name and context across the top of the record; the timeline's controls sit at its right. */
function RecordHead({ b, controlsRef }: { b: PatientBundle; controlsRef: (el: HTMLDivElement | null) => void }) {
  const p = b.patient;
  return (
    <div className="rec-head flex-wrap items-baseline gap-x-4 gap-y-1 overflow-hidden max-w-full">
      <div className="flex flex-col sm:flex-row sm:items-baseline gap-x-3 gap-y-0.5 min-w-0">
        <div className="flex items-baseline gap-2 min-w-0">
          <h1 className="t-display text-[20px] sm:text-[26px] leading-tight truncate">{str(p.display_name)}</h1>
          <span className="mono t-faint text-[12px] shrink-0" title="De-identified TCGA patient identifier">{str(p.patient_id)}</span>
          <span className="syn-tag hidden md:inline" title="TCGA publishes no names. The display name is generated.">synthetic name</span>
        </div>
        <div className="patient-subtitle text-[14px] text-[var(--ink-2)] font-medium truncate">
          {conditionSubtitle(b)}
        </div>
      </div>
      <span className="t-muted min-w-0 truncate text-[12.5px] hidden xl:inline">{barLine(b)}</span>
      <div ref={controlsRef} className="rec-head-controls" aria-label="Timeline controls" />
    </div>
  );
}

function TabBar({ tab, counts, onTab }: { tab: TabId; counts: Partial<Record<TabId, number>>; onTab: (t: TabId) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [clip, setClip] = useState({ left: false, right: false });
  // Bring the open tab into view only when it is cut off, and only by scrolling the tab bar itself.
  useEffect(() => {
    const bar = ref.current;
    const el = bar?.querySelector<HTMLElement>('[aria-selected="true"]');
    if (!bar || !el) return;
    const left = el.offsetLeft - bar.offsetLeft;
    if (left < bar.scrollLeft + 24) bar.scrollTo({ left: Math.max(0, left - 48), behavior: 'smooth' });
    else if (left + el.offsetWidth > bar.scrollLeft + bar.clientWidth - 24) bar.scrollTo({ left: left + el.offsetWidth - bar.clientWidth + 48, behavior: 'smooth' });
  }, [tab]);
  // When the tabs do not fit, the clipped edge fades and the mouse wheel scrolls them sideways.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setClip({ left: el.scrollLeft > 2, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 2 });
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    el.addEventListener('scroll', measure, { passive: true });
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      ro.disconnect();
      el.removeEventListener('scroll', measure);
      el.removeEventListener('wheel', onWheel);
    };
  }, []);
  return (
    <div ref={ref} className={`rec-tabs${clip.left ? ' clip-l' : ''}${clip.right ? ' clip-r' : ''}`} role="tablist" aria-label="Record">
      {GROUPS.map((g, gi) => (
        <div key={g.id} className={`rec-tab-group${gi > 0 ? ' sep' : ''}`} role="presentation">
          <div className="rec-tab-row">
            {TABS.filter((t) => t.group === g.id).map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                className="rec-tab"
                onClick={() => onTab(t.id)}
                title={[t.hint, t.group === 'primary' ? 'synthetic primary care (Synthea)' : null].filter(Boolean).join(', ') || undefined}
              >
                {t.label}
                {counts[t.id] !== undefined && counts[t.id]! > 1 && <span className="n num">{counts[t.id]}</span>}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

const IndexRow = memo(function IndexRow({ m, on, onSelect, birth }: { m: Mark; on: boolean; onSelect: (id: string) => void; birth: Date }) {
  return (
    <tr className={on ? 'on' : ''} onClick={() => onSelect(m.id)}>
      <td className="num whitespace-nowrap">{fmtDate(m.start.toISOString())}</td>
      <td className="num text-right">{ageAt(m.start, birth) ?? ''}</td>
      <td>{m.title}</td>
      <td className="t-faint">{m.lines.slice(1, 3).filter(Boolean).join(' · ')}</td>
    </tr>
  );
});

/** Every item in the tab, in time order; the selected one is marked. */
function ItemIndex({ items, selected, onSelect, plural, birth }: { items: Mark[]; selected: string | null; onSelect: (id: string) => void; plural: string; birth: Date }) {
  if (items.length < 2) return null;
  return (
    <div className="hair mt-8 border-t pt-4">
      <div className="t-label mb-2">
        All {items.length} {plural}, oldest first
      </div>
      <table className="tbl idx">
        <thead>
          <tr>
            <th className="w-[108px]">Date</th>
            <th className="w-[44px] text-right">Age</th>
            <th>What</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {items.map((m) => (
            <IndexRow key={m.id} m={m} on={m.id === selected} onSelect={onSelect} birth={birth} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Positions 0..1 by date, with items on the same (or nearly the same) date pushed apart so each one gets its own
 * stop on the slider. All on one day spreads them evenly.
 */
function scrubPositions(times: number[]): number[] {
  const n = times.length;
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const raw = times.map((t, i) => (t1 > t0 ? (t - t0) / (t1 - t0) : n > 1 ? i / (n - 1) : 0.5));
  const gap = Math.min(0.03, 1 / Math.max(1, n - 1));
  const p: number[] = [];
  for (let i = 0; i < n; i++) p.push(i ? Math.max(raw[i], p[i - 1] + gap) : raw[i]);
  const last = p[n - 1] || 1;
  return p.map((v) => 0.02 + 0.96 * (last > 1 ? v / last : v));
}

/** A slider over the tab's items, spaced by date. */
function ItemScrubber({ items, selected, onSelect, noun, plural }: { items: Mark[]; selected: string | null; onSelect: (id: string) => void; noun: string; plural: string }) {
  if (items.length < 2) return null;
  const at = scrubPositions(items.map((m) => m.start.getTime()));
  const oneDay = new Set(items.map((m) => fmtDate(m.start.toISOString()))).size === 1;
  const scrub: ScrubItem[] = items.map((m, i) => ({
    id: m.id,
    at: at[i],
    label: `${fmtDate(m.start.toISOString())} · ${m.title.length > 52 ? `${m.title.slice(0, 50)}…` : m.title}`,
  }));
  return (
    <Scrubber
      items={scrub}
      selected={selected}
      onSelect={onSelect}
      name={`Choose a ${noun}`}
      gutter={96}
      leading={
        <>
          <div className="text-[12px] leading-tight" style={{ color: 'var(--ink)' }}>
            {items.length} {plural}
          </div>
          <div>{oneDay ? 'same day, drag through' : 'drag through time'}</div>
        </>
      }
    />
  );
}

export function PatientView({ id }: { id: string }) {
  const { bundle, error, loadMs } = usePatient(id);
  const [params] = useSearchParams();
  const b = useMemo(() => {
    if (!bundle) return null;
    let mod = bundle;
    if (params.get('mockEmptyRad') === '1') mod = { ...mod, radiologySeries: [] };
    if (params.get('mockEmptyDrivers') === '1') mod = { ...mod, drivers: [] };
    return mod;
  }, [bundle, params]);

  if (error) {
    return (
      <div className="p-8 text-[13px]">
        <div style={{ color: 'var(--c-alert)' }}>Could not read this patient: {error}</div>
      </div>
    );
  }
  if (!b) {
    return (
      <div>
        <div className="loading-bar" />
        <div className="t-faint px-7 py-6 text-[13px]">Reading {id} from three Lakehouses</div>
      </div>
    );
  }
  return <Record key={id} id={id} b={b} loadMs={loadMs} />;
}

function Record({ id, b, loadMs }: { id: string; b: PatientBundle; loadMs: number | null }) {
  const notes = useNotes(id);
  const base = useMemo(() => buildModel(b), [b]);
  const model: Model = useMemo(
    () => ({ ...base, marks: [...base.marks, ...noteMarks(notes.notes, base.marks, base.dx)] }),
    [base, notes.notes]
  );
  const byId = useMemo(() => new Map(model.marks.map((m) => [m.id, m])), [model]);
  const measured = useMemo(() => measuredVisits(b), [b]);
  const [provOpen, setProvOpen] = useState(false);
  const [compose, setCompose] = useState(0);
  const [controlsHost, setControlsHost] = useState<HTMLDivElement | null>(null);

  // The tab and the selected event live in the URL (?tab=visits&e=v:<encounter>), so links and Back work.
  const [params, setParams] = useSearchParams();
  const tabParam = params.get('tab');
  const tab: TabId = tabParam && TAB_IDS.has(tabParam) ? (tabParam as TabId) : 'summary';
  const tabItems = useMemo(
    () => Object.fromEntries(TABS.map((t) => [t.id, itemsFor(t.id, model.marks, measured)])) as Record<TabId, Mark[]>,
    [model, measured]
  );
  const itemsOf = useCallback((t: TabId) => tabItems[t], [tabItems]);
  const items = tabItems[tab];
  const lastByTab = useRef<Partial<Record<TabId, string>>>({});
  const selFor = (t: TabId, list: Mark[], explicit: string | null): string | null => {
    if (explicit && list.some((m) => m.id === explicit)) return explicit;
    const last = lastByTab.current[t];
    if (last && list.some((m) => m.id === last)) return last;
    return list.length ? list[list.length - 1].id : null;
  };
  const selected = selFor(tab, items, params.get('e'));
  const selMark = selected ? byId.get(selected) ?? null : null;
  useEffect(() => {
    if (selected) lastByTab.current[tab] = selected;
  }, [tab, selected]);

  // The last event viewed outside the notes tab: what a new note is about.
  const [anchorId, setAnchorId] = useState<string | null>(null);
  useEffect(() => {
    if (tab !== 'notes' && tab !== 'summary' && selected) setAnchorId(selected);
  }, [tab, selected]);

  const setParamsRef = useRef(setParams);
  setParamsRef.current = setParams;
  const go = useCallback(
    (t: TabId, e: string | null, push: boolean) =>
      setParamsRef.current(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (t === 'summary') next.delete('tab');
          else next.set('tab', t);
          if (e) next.set('e', e);
          else next.delete('e');
          return next;
        },
        { replace: !push }
      ),
    []
  );
  const tabRef = useRef(tab);
  tabRef.current = tab;
  const select = useCallback(
    (markId: string, push = true) => {
      const m = byId.get(markId);
      // A note just written has no mark until the notes reload; open it in the notes tab directly.
      if (!m && markId.startsWith('n:')) return go('notes', markId, push);
      if (!m) return;
      go(tabFor(m, tabRef.current, measured), markId, push);
    },
    [byId, go, measured]
  );
  const step = useCallback((markId: string) => select(markId, false), [select]);
  const openTab = useCallback((t: TabId) => go(t, lastByTab.current[t] ?? null, true), [go]);

  // Links from charts and tables elsewhere in the record (openInTimeline).
  useEffect(() => {
    const onOpen = (e: Event) => {
      const req = (e as CustomEvent<OpenRequest>).detail;
      let target = req.id ? byId.get(req.id) : undefined;
      if (!target && req.kind && req.title) {
        const at = parseDate(req.at ?? null)?.getTime() ?? model.dx.getTime();
        const cands = model.marks.filter((m) => m.kind === req.kind && m.title.toLowerCase() === req.title!.toLowerCase());
        const dist = (m: Mark) => (at >= m.start.getTime() && at <= (m.end ?? m.start).getTime() ? 0 : Math.abs(m.start.getTime() - at));
        target = cands.sort((a, z) => dist(a) - dist(z))[0];
      }
      if (!target && req.fallback) target = byId.get(req.fallback);
      if (target) select(target.id);
    };
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_EVENT, onOpen);
  }, [byId, model, select]);

  const navigate = useCallback(
    (section: string, seriesKey?: string) => {
      if (section === 'imaging' && seriesKey) {
        const series = b.radiologySeries.find((s) => s.series_key === seriesKey);
        if (series) return select(`r:${str(series.study_uid)}`);
      }
      if (section === 'imaging') return select('slide');
      if (section === 'genomics') return select('genome');
      if (section === 'report') return select('report');
      if (section === 'clinical') return openTab('treatment');
    },
    [b, select, openTab]
  );

  // Arrow keys step through the open tab, unless focus is in a field, a slider or a viewer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.altKey || e.metaKey || e.ctrlKey || e.shiftKey) return;
      if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;
      const t = e.target as HTMLElement | null;
      if (t?.closest('input, select, textarea, [role="slider"], .well, canvas')) return;
      const i = items.findIndex((m) => m.id === selected);
      if (i < 0) return;
      const next = items[i + (e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : -1)];
      if (!next) return;
      e.preventDefault();
      step(next.id);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [items, selected, step]);

  // The timeline sits across the top (tabs below) or down the left (tabs beside it); the divider resizes it.
  const [orientation, setOrientation] = useState<Orientation>(() => (localStorage.getItem(LAYOUT_KEY) === 'left' ? 'left' : 'top'));
  const top = orientation === 'top';
  useEffect(() => {
    localStorage.setItem(LAYOUT_KEY, orientation);
    const t = window.setTimeout(() => window.dispatchEvent(new Event('resize')), 340);
    return () => window.clearTimeout(t);
  }, [orientation]);
  const [width, setWidth] = useState(() => Number(localStorage.getItem(WIDTH_KEY)) || 460);
  const [height, setHeight] = useState(() => Number(localStorage.getItem(HEIGHT_KEY)) || 500);
  useEffect(() => localStorage.setItem(WIDTH_KEY, String(Math.round(width))), [width]);
  useEffect(() => localStorage.setItem(HEIGHT_KEY, String(Math.round(height))), [height]);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === '1');
  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0');
    // Viewers fit themselves to the space once the timeline has finished folding.
    const t = window.setTimeout(() => window.dispatchEvent(new Event('resize')), 320);
    return () => window.clearTimeout(t);
  }, [collapsed]);
  const [resizing, setResizing] = useState(false);
  const dragging = useRef<{ at: number; size: number } | null>(null);
  const clampW = (v: number) => Math.max(320, Math.min(Math.min(900, window.innerWidth - 540), v));
  const clampH = (v: number) => Math.max(260, Math.min(window.innerHeight - 260, v));
  const resize = (delta: number) => (top ? setHeight((v) => clampH(v + delta)) : setWidth((v) => clampW(v + delta)));

  const splitHandlers = {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
      if (collapsed) return;
      dragging.current = { at: top ? e.clientY : e.clientX, size: top ? height : width };
      setResizing(true);
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => {
      const d = dragging.current;
      if (!d) return;
      if (top) setHeight(clampH(d.size + e.clientY - d.at));
      else setWidth(clampW(d.size + e.clientX - d.at));
    },
    onPointerUp: (e: React.PointerEvent<HTMLDivElement>) => {
      dragging.current = null;
      setResizing(false);
      if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
      window.dispatchEvent(new Event('resize'));
    },
    onDoubleClick: () => (collapsed ? setCollapsed(false) : top ? setHeight(460) : setWidth(460)),
    onKeyDown: (e: React.KeyboardEvent<HTMLDivElement>) => {
      const back = top ? 'ArrowUp' : 'ArrowLeft';
      const fwd = top ? 'ArrowDown' : 'ArrowRight';
      if (e.key === back) resize(-24);
      else if (e.key === fwd) resize(24);
      else return;
      e.preventDefault();
      e.stopPropagation();
    },
  };

  // Viewers that are slow to start stay mounted once opened; tell them when they are shown again.
  const [visited, setVisited] = useState<Set<TabId>>(() => new Set([tab]));
  useEffect(() => {
    setVisited((v) => (v.has(tab) ? v : new Set([...v, tab])));
    const t = window.setTimeout(() => window.dispatchEvent(new Event('resize')), 30);
    return () => window.clearTimeout(t);
  }, [tab]);

  // The page scrolls as a whole. A new selection made while reading further down the details brings the top of the
  // details (under the pinned tab bar) back into view; the timeline is left where it is.
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    const page = document.getElementById('patient-scroll');
    if (!el || !page) return;
    const tabsH = el.previousElementSibling instanceof HTMLElement ? el.previousElementSibling.offsetHeight : 0;
    const top = el.getBoundingClientRect().top - page.getBoundingClientRect().top + page.scrollTop - tabsH;
    if (page.scrollTop > top + 1) page.scrollTo({ top, behavior: 'smooth' });
  }, [tab, selected]);

  const counts = useMemo(() => {
    const out: Partial<Record<TabId, number>> = {};
    for (const t of TABS) if (t.kinds.length) out[t.id] = itemsOf(t.id).length;
    return out;
  }, [itemsOf]);
  const lens = useMemo(() => new Set(tabDef(tab).kinds), [tab]);
  const tabIndex = TABS.findIndex((t) => t.id === tab);
  const prevIndex = useRef(tabIndex);
  const dir = tabIndex >= prevIndex.current ? 1 : -1;
  useEffect(() => {
    prevIndex.current = tabIndex;
  }, [tabIndex]);

  const anchorFor = useCallback(
    (eventId: string | undefined): NoteAnchor | null => {
      const m = eventId ? byId.get(eventId) : undefined;
      return m ? { id: m.id, label: `${m.title}, ${fmtDate(m.start.toISOString())}` } : null;
    },
    [byId]
  );

  const openEvent = useCallback((eid: string) => select(eid), [select]);
  const addNote = useCallback(() => {
    setCompose((n) => n + 1);
    openTab('notes');
  }, [openTab]);
  const openProvenance = useCallback(() => setProvOpen(true), []);
  const defaultAnchor = useMemo(() => anchorFor(anchorId ?? undefined), [anchorFor, anchorId]);

  const pane = (t: TabId) => {
    const list = t === tab ? items : itemsOf(t);
    const sid = t === tab ? selected : selFor(t, list, null);
    const mark = sid ? byId.get(sid) ?? null : null;
    return (
      <TabPane
        key={t}
        tab={t}
        b={b}
        model={model}
        items={list}
        mark={mark}
        onSelect={step}
        onNavigate={navigate}
        notes={notes}
        anchorFor={anchorFor}
        defaultAnchor={defaultAnchor}
        onOpenEvent={openEvent}
        onAddNote={addNote}
        compose={compose}
        onProvenance={openProvenance}
        loadMs={loadMs}
      />
    );
  };

  return (
    <article className="record">
      <RecordHead b={b} controlsRef={setControlsHost} />
      <div className={`rec-body ${top ? 'is-top' : 'is-left'}${resizing ? ' resizing' : ''}${collapsed ? ' tl-folded' : ''}`}>
        <section
          className="chap chap-tl"
          style={top ? { height: collapsed ? STRIP.top : height } : { width: collapsed ? STRIP.left : width }}
          aria-label="Lifetime timeline"
        >
          <ChapterRule
            pill={top || !collapsed ? 'Timeline' : undefined}
            action={
              <button className="chap-act" onClick={() => setCollapsed((c) => !c)} aria-expanded={!collapsed}>
                {!(collapsed && !top) && <span>{collapsed ? 'Show' : 'Hide'}</span>}
                <ChevronDown size={15} strokeWidth={2} className={`chap-chev${collapsed ? '' : ' open'}`} aria-hidden />
              </button>
            }
          />
          <div className="chap-grid">
            <div className="rec-timeline">
              <LifeTimeline
                model={model}
                selected={selMark ? selMark.id : null}
                onSelect={(mid, stepping) => select(mid, !stepping)}
                lens={lens}
                orientation={orientation}
                onOrientation={setOrientation}
                collapsed={collapsed}
                onCollapsed={setCollapsed}
                controlsHost={controlsHost}
                showCollapse={false}
              />
            </div>
          </div>
        </section>
        {!top && (
          <div
            className="rec-split"
            title="Drag to resize the timeline; double-click to reset"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize the timeline"
            aria-valuenow={Math.round(width)}
            tabIndex={0}
            {...splitHandlers}
          />
        )}
        <section className="chap rec-main" aria-label="Details">
          <ChapterRule
            pill="Details"
            className={top ? 'split' : undefined}
            {...(top
              ? {
                  title: collapsed ? undefined : 'Drag to resize the timeline; double-click to reset',
                  role: 'separator',
                  'aria-orientation': 'horizontal' as const,
                  'aria-label': 'Resize the timeline',
                  'aria-valuenow': Math.round(height),
                  tabIndex: 0,
                  ...splitHandlers,
                }
              : {})}
          />
          <TabBar tab={tab} counts={counts} onTab={openTab} />
          <div ref={scrollRef} className="rec-scroll">
            {TABS.filter((t) => t.id === tab || (KEEP_ALIVE.includes(t.id) && visited.has(t.id))).map((t) => (
              <div key={t.id} hidden={t.id !== tab} className="tab-in" style={{ ['--tab-dir' as string]: dir }}>
                {pane(t.id)}
              </div>
            ))}
          </div>
        </section>
      </div>
      {provOpen && <ProvenanceDrawer b={b} onClose={() => setProvOpen(false)} />}
    </article>
  );
}

/** A section rule: a 2 px orange line with a pill at its start and an optional action at its end. */
function ChapterRule({
  pill,
  action,
  className,
  ...rest
}: { pill?: string; action?: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement> & Record<string, unknown>) {
  return (
    <div className={`chap-rule${className ? ` ${className}` : ''}`} {...rest}>
      {pill && (
        <span className="chap-pill-wrap">
          <span className="chap-pill">{pill}</span>
        </span>
      )}
      {action && <span className="chap-act-wrap">{action}</span>}
    </div>
  );
}

/** A tab's content. Memoised: switching events re-renders only the open tab, not the viewers kept behind it. */
const TabPane = memo(function TabPane({
  tab,
  b,
  model,
  items,
  mark,
  onSelect,
  onNavigate,
  notes,
  anchorFor,
  defaultAnchor,
  onOpenEvent,
  onAddNote,
  compose,
  onProvenance,
  loadMs,
}: {
  tab: TabId;
  b: PatientBundle;
  model: Model;
  items: Mark[];
  mark: Mark | null;
  onSelect: (id: string) => void;
  onNavigate: (section: string, seriesKey?: string) => void;
  notes: NotesState;
  anchorFor: (eventId: string | undefined) => NoteAnchor | null;
  defaultAnchor: NoteAnchor | null;
  onOpenEvent: (eventId: string) => void;
  onAddNote: () => void;
  /** Increases when "Add note" is pressed elsewhere, to bring the note form into view. */
  compose: number;
  onProvenance: () => void;
  loadMs: number | null;
}) {
  const def = tabDef(tab);
  if (tab === 'summary') {
    return (
      <div className="rec-pane">
        <Overview b={b} loadMs={loadMs} onProvenance={onProvenance} />
        {str(b.patient?.patient_id) === 'TCGA-G6-A8L6' && (
          <div className="my-6">
            <AlertStopwatchCard patientId={str(b.patient.patient_id) as string} />
          </div>
        )}
        <Summary b={b} />
        <div className="hair mt-8 border-t pt-6">
          <PrimaryCareGlance b={b} />
        </div>
      </div>
    );
  }
  if (tab === 'multimodal') {
    return (
      <div className="rec-pane">
        <MultimodalHero b={b} />
      </div>
    );
  }
  if (!mark) {
    if (tab === 'notes') {
      return (
        <div className="rec-pane">
          <NotesSection
            state={notes}
            selected={null}
            onSelect={(nid) => onSelect(`n:${nid}`)}
            anchorFor={anchorFor}
            onOpenEvent={onOpenEvent}
            defaultAnchor={defaultAnchor}
            compose={compose}
          />
        </div>
      );
    }
    return <div className="rec-pane t-faint text-[13px]">Nothing of this kind is recorded for this patient.</div>;
  }

  const about = mark.kind === 'note' ? [] : notes.notes.filter((n) => n.eventId === mark.id);
  const actions =
    mark.kind === 'note' ? null : (
      <>
        {about.length > 0 && (
          <button className="btn" onClick={() => onOpenEvent(`n:${about[0].id}`)} title="Tumour board notes about this event">
            {about.length} {about.length === 1 ? 'note' : 'notes'}
          </button>
        )}
        <button className="btn" onClick={onAddNote} title="Write a tumour board note about this event">
          Add note
        </button>
      </>
    );
  const detail = (children?: ReactNode, hideBody = false) => (
    <TimelineDetail
      b={b}
      mark={mark}
      marks={model.marks}
      items={items}
      noun={def.noun}
      birth={model.birth}
      dx={model.dx}
      onSelect={onSelect}
      onNavigate={onNavigate}
      actions={actions}
      hideBody={hideBody}
      scrubber={<ItemScrubber items={items} selected={mark.id} onSelect={onSelect} noun={def.noun} plural={def.plural} />}
    >
      {children}
    </TimelineDetail>
  );
  const index = <ItemIndex items={items} selected={mark.id} onSelect={onSelect} plural={def.plural} birth={model.birth} />;

  switch (tab) {
    case 'measurements':
      return (
        <div className="rec-pane">
          {detail(null, true)}
          <MeasurementsPanel b={b} pinned={mark.start.getTime()} />
          {index}
        </div>
      );
    case 'cancer':
      return (
        <div className="rec-pane">
          {detail()}
          <div className="hair mt-8 border-t pt-6">
            <ClinicalSection b={b} />
          </div>
          {index}
        </div>
      );
    case 'pathology': {
      const slides = b.slides?.length ? b.slides : b.slide ? [b.slide] : [];
      const slide = mark.rows[0];
      const markFor = (sid: string) => items.find((m) => str(m.rows[0]?.slide_id) === sid)?.id;
      return (
        <div className="rec-pane">
          {detail(
            <div className="mb-6">
              <PathologyPanel slide={slide} slides={slides} onSlide={(sid) => markFor(sid) && onSelect(markFor(sid)!)} access={b.access.slide} stepper={false} />
            </div>
          )}
        </div>
      );
    }
    case 'radiology': {
      const series = b.radiologySeries.find((s) => s.study_uid === mark.rows[0]?.study_uid) ?? null;
      return (
        <div className="rec-pane">
          {detail(
            series ? (
              <div className="mb-6">
                <RadiologyPanel
                  b={b}
                  stepper={false}
                  seriesKey={str(series.series_key)}
                  onSeries={(k) => {
                    const s = b.radiologySeries.find((x) => x.series_key === k);
                    if (s) onSelect(`r:${str(s.study_uid)}`);
                  }}
                />
                <RadiologyFootnotes b={b} />
              </div>
            ) : (
              <p className="t-faint mb-4 text-[13px]">This study is listed in NCI Imaging Data Commons, but its images are not in the viewer.</p>
            )
          )}
          {index}
        </div>
      );
    }
    case 'report':
      return (
        <div className="rec-pane">
          {detail(null, true)}
          <ReportSection b={b} />
        </div>
      );
    case 'genomics':
      return (
        <div className="rec-pane">
          {detail(null, true)}
          <GenomicsSection b={b} />
        </div>
      );
    case 'notes': {
      const note = notes.notes.find((n) => `n:${n.id}` === mark.id);
      const anchor = anchorFor(note?.eventId);
      return (
        <div className="rec-pane">
          {detail(
            note && (
              <div className="rise mb-8 max-w-[860px]" key={note.id}>
                <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{note.body}</p>
                <div className="t-faint mt-2 text-[12.5px]">
                  Written {new Date(note.createdAt).toLocaleString()} · about{' '}
                  {anchor ? (
                    <button className="link" onClick={() => onOpenEvent(anchor.id)}>
                      {anchor.label}
                    </button>
                  ) : (
                    'the case as a whole'
                  )}
                </div>
              </div>
            ),
            true
          )}
          <NotesSection
            state={notes}
            selected={note?.id ?? null}
            onSelect={(nid) => onSelect(`n:${nid}`)}
            anchorFor={anchorFor}
            onOpenEvent={onOpenEvent}
            defaultAnchor={defaultAnchor}
            compose={compose}
          />
        </div>
      );
    }
    default:
      return (
        <div className="rec-pane">
          {detail()}
          {index}
        </div>
      );
  }
});
