import { useEffect, useMemo, useRef, useState } from 'react';

import { drugClass } from '@/lib/clinical';
import { ReportPdf, warmPdfJs } from '@/components/patient/ReportPdf';
import { Scrubber } from '@/components/Scrubber';
import type { NotesState } from '@/hooks/useNotes';
import { fileUrl, num, str, type PatientBundle, type Row } from '@/lib/api';
import { fmtBytes, fmtDay, fmtNum, fmtSpan, plain } from '@/lib/format';
import { LOCAL_DATA } from '@/lib/localMode';

function Kv({ rows }: { rows: [string, string | null | undefined][] }) {
  const shown = rows.filter(([, v]) => v);
  return (
    <dl className="kv">
      {shown.map(([k, v]) => (
        <div key={k} className="contents">
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ------------------------------------------------------------------ clinical */

function treatmentLabel(t: Row): string {
  const agent = str(t.agent);
  if (agent) return agent.replace(/ Hydrochloride| Malate| Mesylate/g, '');
  return plain(str(t.treatment_type));
}

export function ClinicalSection({ b }: { b: PatientBundle }) {
  const p = b.patient;
  const priors = b.diagnoses.filter((d) => /prior|synchronous/i.test(str(d.classification) ?? ''));
  const spread = b.diagnoses.filter((d) => /metast|recurr/i.test(str(d.classification) ?? '') && num(d.day) !== null);
  const given = b.treatments.filter((t) => t.given);
  const dated = given.filter((t) => num(t.start_day) !== null).sort((a, z) => (num(a.start_day) ?? 0) - (num(z.start_day) ?? 0));
  const undated = given.filter((t) => num(t.start_day) === null && (str(t.agent) || !/Pharmaceutical/i.test(str(t.treatment_type) ?? '')));
  const labs = b.biomarkers.filter((t) => !str(t.gene));
  const perf = b.followUps.find((f) => num(f.ecog) !== null || num(f.karnofsky) !== null);
  const pft = b.observations.filter((o) => o.source === 'TCGA');
  const tnm = [str(p.t_stage), str(p.n_stage), str(p.m_stage)].filter(Boolean).join(' ');

  return (
    <div>
      <div className="sec-head">
        <h2 className="sec-title">Cancer registry</h2>
        <span className="sec-note">Diagnosis, staging, treatment and outcomes as abstracted by the treating site for TCGA.</span>
        <span className="src ml-auto"><span className="swatch sw-clinical" />clinical_lakehouse</span>
      </div>
      <div className="grid gap-x-12 gap-y-8 xl:grid-cols-3">
        <div>
          <div className="t-label mb-2">Diagnosis and staging</div>
          <Kv
            rows={[
              ['Histology', plain(str(p.primary_diagnosis))],
              ['Site', [str(p.laterality), plain(str(p.tissue_of_origin)).replace(/^(.+), (\w+)$/, '$1 of $2').toLowerCase()].filter(Boolean).join(' ')],
              ['ICD-10 · morphology', [str(p.icd10), str(p.morphology)].filter(Boolean).join(' · ')],
              ['Stage', [str(p.stage), str(p.stage_system)].filter(Boolean).join(', ')],
              ['TNM', tnm],
              ['Grade', str(p.grade)],
              ['Gleason score', num(p.gleason_score) ? String(num(p.gleason_score)) : null],
              ['Resection margin', str(p.residual_disease)],
              ['Child-Pugh class', str(p.child_pugh)],
              ['Fibrosis (Ishak)', str(p.fibrosis)],
              ['Diagnosed by', str(p.method_of_diagnosis)],
            ]}
          />
          {priors.length > 0 && (
            <div className="mt-4">
              <div className="t-label mb-1">Other primary cancers</div>
              {priors.map((d, i) => (
                <div key={i} className="text-[13px]">
                  {plain(str(d.site)) || 'Site not recorded'}
                  <span className="t-faint"> · {str(d.classification)?.toLowerCase()}{str(d.primary_diagnosis) ? `, ${plain(str(d.primary_diagnosis))}` : ''}</span>
                </div>
              ))}
            </div>
          )}
          {spread.length > 0 && (
            <div className="mt-4">
              <div className="t-label mb-1">Recurrence and spread</div>
              {spread.map((d, i) => (
                <div key={i} className="flex gap-2 text-[13px]">
                  <span className="num t-faint w-[70px] shrink-0">{fmtDay(num(d.day))}</span>
                  <span style={{ color: 'var(--c-alert)' }}>{/metast/i.test(str(d.classification) ?? '') ? 'Metastasis' : 'Recurrence'}</span>
                  <span>{plain(str(d.site))}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="t-label mb-2">Treatment</div>
          <table className="tbl">
            <tbody>
              {dated.map((t, i) => {
                const cls = /surgery|radiation|brachy|ablation/i.test(str(t.treatment_type) ?? '') ? null : drugClass(str(t.agent), str(t.treatment_type));
                const dur = num(t.end_day) !== null && num(t.start_day) !== null ? fmtSpan((num(t.end_day) ?? 0) - (num(t.start_day) ?? 0)) : '';
                const dose = num(t.dose) && str(t.dose_units) === 'cGy' ? `${fmtNum(num(t.dose), 0)} cGy${num(t.fractions) ? ` / ${num(t.fractions)} fx` : ''}` : '';
                return (
                  <tr key={i}>
                    <td className="num t-faint w-[78px] whitespace-nowrap">{fmtDay(num(t.start_day))}{t.start_estimated ? '*' : ''}</td>
                    <td>
                      <div className="font-medium">{treatmentLabel(t)}</div>
                      <div className="t-faint text-[11.5px]">
                        {[cls && cls !== 'chemo' ? cls : str(t.agent) ? 'chemotherapy' : null, dur && `for ${dur}`, dose, str(t.intent)?.toLowerCase()]
                          .filter(Boolean)
                          .join(' · ')}
                      </div>
                    </td>
                    <td className="text-right text-[12px]">{str(t.outcome)?.replace('Treatment Ongoing', 'Ongoing') ?? ''}</td>
                  </tr>
                );
              })}
              {undated.map((t, i) => (
                <tr key={`u${i}`}>
                  <td className="t-faint text-[11.5px]">no date</td>
                  <td>
                    <div className="font-medium">{treatmentLabel(t)}</div>
                    <div className="t-faint text-[11.5px]">{[str(t.intent), str(t.disease_status)].filter(Boolean).join(' · ').toLowerCase()}</div>
                  </td>
                  <td className="text-right text-[12px]">{str(t.outcome) ?? ''}</td>
                </tr>
              ))}
              {given.length === 0 && (
                <tr>
                  <td className="t-faint">No treatment recorded.</td>
                </tr>
              )}
            </tbody>
          </table>
          {dated.some((t) => t.start_estimated) && <div className="t-faint mt-1.5 text-[11.5px]">* surgery at diagnosis, day not recorded</div>}
        </div>

        <div>
          <div className="t-label mb-2">Risk factors and measurements</div>
          <Kv
            rows={[
              ['Smoking', [str(p.smoking_status)?.replace('Current Reformed Smoker for < or = 15 yrs', 'Former smoker').replace('Lifelong Non-Smoker', 'Never smoked').replace('Current Smoker', 'Current smoker'), num(p.pack_years) ? `${num(p.pack_years)} pack-years` : null, num(p.smoking_quit_year) ? `quit ${num(p.smoking_quit_year)}` : null].filter(Boolean).join(', ')],
              ['Occupation', str(p.occupation)],
              ['Body mass index', num(p.bmi) ? `${fmtNum(num(p.bmi), 1)}${num(p.weight_kg) ? ` (${num(p.weight_kg)} kg, ${num(p.height_cm)} cm)` : ''}` : null],
              ['Menopause', str(p.menopause_status)],
              ['Risk factors', str(p.risk_factors)],
              ['Comorbidities', str(p.comorbidities)],
              ['Family history', str(p.family_history)],
              ['Performance', perf ? [num(perf.ecog) !== null ? `ECOG ${num(perf.ecog)}` : null, num(perf.karnofsky) ? `Karnofsky ${num(perf.karnofsky)}` : null].filter(Boolean).join(', ') : null],
            ]}
          />
          {(labs.length > 0 || pft.length > 0) && (
            <div className="mt-4">
              <div className="t-label mb-1">Tests at diagnosis</div>
              <table className="tbl">
                <tbody>
                  {labs.map((t, i) => {
                    const v = num(t.value);
                    const lo = num(t.ref_low);
                    const hi = num(t.ref_high);
                    const flag = str(t.result) === 'Elevated' || (v !== null && hi !== null && v > hi) ? 'high' : str(t.result) === 'Low' || (v !== null && lo !== null && v < lo) ? 'low' : null;
                    return (
                      <tr key={i}>
                        <td>{str(t.test)}</td>
                        <td className="num text-right font-medium" style={{ color: flag ? 'var(--c-alert)' : undefined }}>
                          {v !== null ? fmtNum(v, 1) : str(t.result)}
                        </td>
                        <td className="t-faint text-[11.5px]">
                          {str(t.units) ?? ''}
                          {flag ? ` · ${flag}` : ''}
                          {lo !== null && hi !== null ? ` · ref ${lo}–${hi}` : ''}
                        </td>
                      </tr>
                    );
                  })}
                  {pft.map((o, i) => (
                    <tr key={`f${i}`}>
                      <td>{str(o.name)}</td>
                      <td className="num text-right font-medium">{fmtNum(num(o.value), 0)}</td>
                      <td className="t-faint text-[11.5px]">{str(o.units)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ report */

const REPORT_TERMS = [
  /\b(carcinoma|adenocarcinoma|sarcoma|melanoma|lymphoma)\b/gi,
  /\bgrade\s*[IVX0-9/]+\b/gi,
  /\b(well|moderately|poorly)[ -]differentiated\b/gi,
  /\b\d+(\.\d+)?\s*(x\s*\d+(\.\d+)?\s*)*cm\b/gi,
  /\b(margins?[^.]{0,40}(free|negative|positive|involved|uninvolved|clear))\b/gi,
  /\b\d+\s*\/\s*\d+\s*(lymph nodes?)?\b/gi,
  /\b(lymphovascular|perineural|vascular)\s+invasion[^.]{0,20}/gi,
  /\bp?T[0-4][a-c]?\s*N[0-3X][a-c]?(\s*M[01X])?\b/g,
  /\bGleason[^.]{0,30}/gi,
  /\b(Fuhrman|FIGO|Nottingham)[^.]{0,30}/gi,
];

function highlight(text: string): string {
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return REPORT_TERMS.reduce((s, re) => s.replace(re, (m) => `<mark>${m}</mark>`), esc);
}

export function ReportSection({ b }: { b: PatientBundle }) {
  const r = b.report;
  const [showPdf, setShowPdf] = useState(true);
  const [pages, setPages] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const pdfUrl = r.pdfPath && !b.access.report.error ? fileUrl(b.access.report, r.pdfPath) : null;
  useEffect(() => {
    setPages(null);
    setPage(1);
  }, [pdfUrl]);
  useEffect(() => {
    warmPdfJs().catch(() => undefined);
  }, []);
  const html = useMemo(() => highlight(r.text || ''), [r.text]);
  return (
    <div>
      <div className="sec-head">
        <h2 className="sec-title">Pathology report</h2>
        <span className="sec-note">The surgical pathology report as scanned, and its machine-readable text with key findings marked.</span>
        <span className="src ml-auto"><span className="swatch sw-clinical" />clinical_lakehouse/Files/reports</span>
      </div>
      <div className="grid gap-8 xl:grid-cols-2">
        <div className="min-w-0">
          <div className="t-label mb-1.5 flex items-center gap-3">
            Text (OCR)
            <span className="t-faint normal-case">{fmtNum(r.text.length, 0)} characters</span>
          </div>
          {r.text.length > 200 ? (
            <div className="report" dangerouslySetInnerHTML={{ __html: html }} />
          ) : (
            <div className="report t-faint">{r.text || 'No machine-readable text was produced for this report.'} The scanned original is on the right.</div>
          )}
          <div className="t-faint mt-1.5 text-[11.5px]">{r.source}</div>
        </div>
        <div className="min-w-0">
          <div className="t-label mb-1.5 flex items-center gap-3">
            Scanned original
            {r.pdfBytes && (
              <span className="t-faint normal-case">
                PDF, {fmtBytes(r.pdfBytes)}
                {pages ? ` · ${pages} ${pages === 1 ? 'page' : 'pages'}` : ''}
              </span>
            )}
            {pdfUrl && (
              <>
                <button className="link t-muted normal-case" onClick={() => setShowPdf((v) => !v)}>
                  {showPdf ? 'Hide' : 'Show'}
                </button>
                <a className="link t-muted normal-case" href={pdfUrl} target="_blank" rel="noreferrer">
                  Open in a new tab
                </a>
              </>
            )}
          </div>
          {pdfUrl && showPdf && pages && pages > 1 && (
            <Scrubber
              name="Report pages"
              gutter={92}
              leading={
                <>
                  <div className="text-[12px]" style={{ color: 'var(--ink)' }}>
                    1 report
                  </div>
                  <div>{pages} pages</div>
                </>
              }
              items={Array.from({ length: pages }, (_, i) => ({
                id: String(i + 1),
                at: 0.08 + (0.84 * i) / (pages - 1),
                label: `Page ${i + 1} of ${pages}`,
                tick: `p. ${i + 1}`,
              }))}
              selected={String(page)}
              onSelect={(id) => setPage(Number(id))}
            />
          )}
          {pdfUrl && showPdf ? (
            <ReportPdf key={pdfUrl} url={pdfUrl} onPages={setPages} page={page} onPage={setPage} />
          ) : (
            <div className="report t-faint">{pdfUrl ? 'Hidden.' : 'The scanned report is not available.'}</div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ tumour board notes (app-owned data) */

/** Seeded case-review notes carry this author name and are labelled in the list. */
const ILLUSTRATIVE = /\(illustrative\)$/;

export type NoteAnchor = { id: string; label: string };

/**
 * The tumour board notes. Each note is about an event on the timeline (or the case as a whole); new notes are about
 * the event chosen in "About", which defaults to the last event viewed in another tab.
 */
export function NotesSection({
  state,
  selected,
  onSelect,
  anchorFor,
  onOpenEvent,
  defaultAnchor,
  compose = 0,
}: {
  state: NotesState;
  selected: string | null;
  onSelect: (noteId: string) => void;
  /** Label for the event a note is about; null for the case as a whole or an unknown event. */
  anchorFor: (eventId: string | undefined) => NoteAnchor | null;
  onOpenEvent: (eventId: string) => void;
  defaultAnchor: NoteAnchor | null;
  /** Increases when "Add note" is pressed on an event: the form scrolls into view and takes focus. */
  compose?: number;
}) {
  const { notes, error, me, add, remove, addIllustrative } = state;
  const draftRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!compose) return;
    const t = window.setTimeout(() => {
      draftRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      draftRef.current?.focus({ preventScroll: true });
    }, 260);
    return () => window.clearTimeout(t);
  }, [compose]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [about, setAbout] = useState<string>(defaultAnchor?.id ?? '');
  useEffect(() => setAbout(defaultAnchor?.id ?? ''), [defaultAnchor?.id]);

  const submit = async () => {
    setBusy(true);
    const created = await add(draft, about || undefined);
    setBusy(false);
    if (created) {
      setDraft('');
      onSelect(created.id);
    }
  };

  return (
    <div>
      <div className="sec-head">
        <h2 className="sec-title">All notes</h2>
        <span className="sec-note">
          {LOCAL_DATA
            ? 'The only data this app writes. In local mode, notes are kept in work/local/notes.json, never in the patient silos.'
            : "The only data this app writes: notes are kept in the app's own Rayfin database, never in the patient silos."}
        </span>
      </div>
      <div className="max-w-[860px] space-y-1">
        {notes.map((n) => {
          const anchor = anchorFor(n.eventId);
          return (
            <div
              key={n.id}
              className={`note-row${n.id === selected ? ' on' : ''}`}
              onClick={() => onSelect(n.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && onSelect(n.id)}
            >
              <div className="t-faint flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
                <span className="text-[var(--ink)]">{n.authorName}</span>
                {ILLUSTRATIVE.test(n.authorName) && (
                  <span className="syn-tag" title="Written for the demo from facts in this patient's record; TCGA has no tumour board notes.">
                    illustrative, written for the demo
                  </span>
                )}
                <span>written {new Date(n.createdAt).toLocaleString()}</span>
                <span>
                  about{' '}
                  {anchor ? (
                    <button
                      className="link"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenEvent(anchor.id);
                      }}
                    >
                      {anchor.label}
                    </button>
                  ) : (
                    'the case'
                  )}
                </span>
                {n.createdBy === me && (
                  <button
                    className="link ml-auto"
                    onClick={(e) => {
                      e.stopPropagation();
                      void remove(n.id);
                    }}
                  >
                    Delete
                  </button>
                )}
              </div>
              <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-[13.5px]">{n.body}</p>
            </div>
          );
        })}
        {notes.length === 0 && !error && (
          <div className="t-faint text-[13px]">
            No notes yet.
            {addIllustrative && (
              <>
                {' '}
                <button className="link" onClick={() => void addIllustrative().then((n) => n && onSelect(n.id))}>
                  Add the illustrative case-review note
                </button>{' '}
                written for this demo from facts in the record.
              </>
            )}
          </div>
        )}
        <div className="hair mt-4 border-t pt-4">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px]">
            <label htmlFor="note-about" className="t-faint">
              About
            </label>
            <select id="note-about" className="field !h-[30px] !w-auto max-w-[520px] py-0" value={about} onChange={(e) => setAbout(e.target.value)}>
              <option value="">The case as a whole</option>
              {defaultAnchor && <option value={defaultAnchor.id}>{defaultAnchor.label}</option>}
            </select>
          </div>
          <div className="flex items-start gap-3">
            <textarea
              ref={draftRef}
              className="field !h-[64px] py-2"
              placeholder="Add a note for the tumour board"
              value={draft}
              maxLength={1000}
              onChange={(e) => setDraft(e.target.value)}
            />
            <button className="btn btn-ink" disabled={busy || !draft.trim()} onClick={() => void submit()}>
              Add note
            </button>
          </div>
        </div>
        {error && <div className="text-[12px]" style={{ color: 'var(--c-alert)' }}>{error}</div>}
      </div>
    </div>
  );
}
