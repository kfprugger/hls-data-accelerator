import * as d3 from 'd3';
import { useMemo, type ReactNode } from 'react';

import type { Mark } from '@/components/patient/Timeline';
import { num, parseJson, str, type PatientBundle, type Row } from '@/lib/api';
import { CLASS_STYLE, describe, drugClass, flag, interpretScore, medicine, product, term, VISIT_CLASS, type Panel } from '@/lib/clinical';
import { ageAt, fmtBytes, fmtDate, fmtDay, fmtDuration, fmtMoney, fmtMonth, fmtNum, fmtSpan, ordinal, parseDate, plain } from '@/lib/format';

type Point = { t: number; v: number };
type Select = (id: string) => void;
type Navigate = (section: string, seriesKey?: string) => void;

interface Ctx {
  b: PatientBundle;
  marks: Mark[];
  birth: Date;
  dx: Date;
  history: Map<string, Point[]>;
  onSelect: Select;
  onNavigate: Navigate;
}

const DAY = 86_400_000;

function val(v: number | null): string {
  if (v === null) return '';
  return fmtNum(v, Math.abs(v) < 10 ? 2 : 1);
}

function unit(u: string | null): string {
  return (u ?? '').replace(/^\{score\}$|^\{nominal\}$/, '').replace('mm[Hg]', 'mmHg').replace(/m2$/, 'm²');
}

function ResultTable({ children }: { children: ReactNode }) {
  return (
    <table className="tbl table-fixed">
      <colgroup>
        <col style={{ width: '44%' }} />
        <col style={{ width: '28%' }} />
        <col />
      </colgroup>
      <tbody>{children}</tbody>
    </table>
  );
}

function Block({ title, note, children }: { title: string; note?: ReactNode; children: ReactNode }) {
  return (
    <div className="mb-6 break-inside-avoid">
      <div className="t-label mb-1.5 flex items-baseline gap-2">
        <span>{title}</span>
        {note && <span className="t-faint">{note}</span>}
      </div>
      {children}
    </div>
  );
}

function Kv({ rows, tight }: { rows: [string, ReactNode][]; tight?: boolean }) {
  const shown = rows.filter(([, v]) => v !== null && v !== undefined && v !== '');
  return (
    <dl className={tight ? 'kv kv-tight detail-kv' : 'kv detail-kv'}>
      {shown.map(([k, v]) => (
        <div key={k} className="contents">
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function LinkButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button className="link text-left" onClick={onClick}>
      {children}
    </button>
  );
}

/** Marks that carry a given source row. */
function markFor(marks: Mark[], kind: Mark['kind'], row: Row): Mark | undefined {
  const all = marks.filter((m) => m.kind === kind && m.rows.includes(row));
  const onset = parseDate(str(row.onset) ?? str(row.start));
  return all.find((m) => onset && m.start.getTime() === onset.getTime()) ?? all[0];
}

function visitLabel(e: Row): string {
  const cls = VISIT_CLASS[str(e.encounter_class) ?? '']?.label ?? 'Visit';
  return `${cls}, ${fmtDate(str(e.start))}`;
}

function VisitLink({ ctx, encounterId }: { ctx: Ctx; encounterId: Row[string] }) {
  const e = ctx.b.encounters.find((x) => x.encounter_id === encounterId);
  if (!e) return null;
  return <LinkButton onClick={() => ctx.onSelect(`v:${str(e.encounter_id)}`)}>{visitLabel(e)}</LinkButton>;
}

/* ------------------------------------------------------------------ trend chart */

function Trend({ points, refRange, marker, from, to, unit }: {
  points: Point[];
  refRange?: [number, number];
  marker?: number;
  from: number;
  to: number;
  unit: string;
}) {
  const W = 420;
  const H = 96;
  if (points.length < 2) return <div className="t-faint text-[12px]">Too few results to draw a trend.</div>;
  const vs = points.map((p) => p.v);
  const lo = Math.min(...vs, refRange ? Math.max(refRange[0], Math.min(...vs) * 0.9) : Infinity);
  const hi = Math.max(...vs, refRange ? Math.min(refRange[1], Math.max(...vs) * 1.1) : -Infinity);
  const x = d3.scaleLinear().domain([from, to]).range([34, W - 6]);
  const y = d3.scaleLinear().domain([lo, hi]).nice().range([H - 18, 6]);
  const years = d3.utcYear.every(Math.max(1, Math.round((to - from) / (365.25 * DAY) / 5)))?.range(new Date(from), new Date(to)) ?? [];
  return (
    <svg width={W} height={H} className="chart block">
      {refRange && (
        <rect x={34} width={W - 40} y={y(Math.min(refRange[1], y.domain()[1]))} height={Math.max(1, y(Math.max(refRange[0], y.domain()[0])) - y(Math.min(refRange[1], y.domain()[1])))} fill="var(--surface)" />
      )}
      {y.ticks(3).map((t) => (
        <text key={t} x={30} y={y(t) + 3} textAnchor="end" style={{ fontSize: 10 }}>
          {t}
        </text>
      ))}
      {years.map((d) => (
        <text key={d.getTime()} x={x(d.getTime())} y={H - 4} textAnchor="middle" style={{ fontSize: 10 }}>
          {d.getUTCFullYear()}
        </text>
      ))}
      {marker !== undefined && <line x1={x(marker)} x2={x(marker)} y1={4} y2={H - 16} stroke="var(--ink)" strokeDasharray="2 3" />}
      <polyline fill="none" stroke="var(--ink-2)" strokeWidth={1.3} points={points.map((p) => `${x(p.t)},${y(p.v)}`).join(' ')} />
      {points.map((p, i) => (
        <circle key={i} cx={x(p.t)} cy={y(p.v)} r={1.8} fill="var(--ink-2)" />
      ))}
      <text x={W - 6} y={12} textAnchor="end" style={{ fontSize: 10 }}>
        {unit}
      </text>
    </svg>
  );
}

/* ------------------------------------------------------------------ visit */

function VisitDetail({ ctx, e }: { ctx: Ctx; e: Row }) {
  const { b, history } = ctx;
  const eid = e.encounter_id;
  const d = parseDate(str(e.start))!;
  const obs = b.observations.filter((o) => o.encounter_id === eid);
  const sex = str(b.patient.sex);
  // Reference ranges are adult values; children are shown without flags.
  const adult = (ageAt(d, ctx.birth) ?? 99) >= 18;

  const groups = new Map<Panel, { name: string; raw: string; order: number; ref?: [number, number]; o: Row }[]>();
  for (const o of obs) {
    const def = describe(String(o.name), str(o.category));
    const list = groups.get(def.panel) ?? [];
    list.push({ name: def.name, raw: String(o.name), order: def.order, ref: def.ref, o });
    groups.set(def.panel, list);
  }
  groups.forEach((list) => list.sort((a, z) => a.order - z.order || a.name.localeCompare(z.name)));

  const prev = (raw: string): Point | null => {
    const series = history.get(raw);
    if (!series) return null;
    let best: Point | null = null;
    for (const p of series) if (p.t < d.getTime()) best = p;
    return best;
  };

  const resultRows = (list: { name: string; raw: string; ref?: [number, number]; o: Row }[]) => {
    const rows = [...list];
    const sys = rows.find((r) => r.name === 'Systolic BP');
    const dia = rows.find((r) => r.name === 'Diastolic BP');
    const out: ReactNode[] = [];
    if (sys && dia) {
      const sv = num(sys.o.value);
      const dv = num(dia.o.value);
      const high = adult && ((sv ?? 0) > 129 || (dv ?? 0) > 79);
      const ps = prev(sys.raw);
      const pd = prev(dia.raw);
      out.push(
        <tr key="bp">
          <td>Blood pressure</td>
          <td className="num whitespace-nowrap font-medium" style={{ color: high ? 'var(--c-alert)' : undefined }}>
            {fmtNum(sv, 0)}/{fmtNum(dv, 0)} <span className="t-faint font-normal">mmHg{high ? ' · high' : ''}</span>
          </td>
          <td className="t-faint num text-[11.5px]">{ps && pd ? `was ${fmtNum(ps.v, 0)}/${fmtNum(pd.v, 0)}, ${fmtMonth(new Date(ps.t).toISOString())}` : ''}</td>
        </tr>
      );
    }
    for (const [i, r] of rows.entries()) {
      if (r === sys || r === dia) continue;
      const v = num(r.o.value);
      const f = adult ? flag(v, r.ref) : null;
      const p = v !== null ? prev(r.raw) : null;
      out.push(
        <tr key={`${r.raw}:${i}`}>
          <td>{r.name}</td>
          <td className="num whitespace-nowrap font-medium" style={{ color: f ? 'var(--c-alert)' : undefined }}>
            {v !== null ? val(v) : str(r.o.value_text)}{' '}
            <span className="t-faint font-normal">
              {unit(str(r.o.units))}
              {f ? ` · ${f}` : ''}
            </span>
          </td>
          <td className="t-faint num text-[11.5px]">
            {p ? `was ${val(p.v)}, ${fmtMonth(new Date(p.t).toISOString())}` : r.ref && adult ? `ref ${r.ref[0]}–${r.ref[1]}` : ''}
          </td>
        </tr>
      );
    }
    return out;
  };

  const panelsInOrder: Panel[] = ['Vital signs', 'Blood count', 'Metabolic panel', 'Liver', 'Lipids', 'Diabetes', 'Blood gas', 'Urinalysis', 'Other tests', 'Examination'];
  const screening = groups.get('Screening') ?? [];
  const social = groups.get('Social needs') ?? [];
  const conditions = b.conditions.filter((c) => c.encounter_id === eid);
  const resolved = b.conditions.filter((c) => c.synthetic && str(c.resolved) === str(e.start) && c.encounter_id !== eid);
  const meds = b.medications.filter((m) => m.encounter_id === eid);
  const procedures = b.procedures.filter((p) => p.encounter_id === eid);
  const vaccines = b.immunizations.filter((i) => i.encounter_id === eid);
  const careplans = b.careplans.filter((c) => c.encounter_id === eid);
  const allergies = b.allergies.filter((a) => a.encounter_id === eid);
  const nothing = obs.length + conditions.length + meds.length + procedures.length + vaccines.length + careplans.length === 0;

  return (
    <div>
      <div className="mb-5 grid gap-x-10 gap-y-2 text-[13px] md:grid-cols-2 xl:grid-cols-[1fr_1.5fr_1fr_1fr]">
        <Kv tight rows={[['Reason', term(str(e.reason)) || 'Routine'], ['Type', VISIT_CLASS[str(e.encounter_class) ?? '']?.label ?? str(e.encounter_class)]]} />
        <Kv tight rows={[['Clinician', [str(e.provider), str(e.provider_specialty)?.toLowerCase()].filter(Boolean).join(', ')], ['Facility', str(e.organization)]]} />
        <Kv tight rows={[['Duration', fmtDuration(num(e.duration_minutes))], ['Payer', str(e.payer) === 'NO_INSURANCE' ? 'No insurance' : str(e.payer)]]} />
        <Kv tight rows={[['Claim', fmtMoney(num(e.total_cost))], ['Payer paid', fmtMoney(num(e.payer_coverage))]]} />
      </div>
      {nothing ? (
        <div className="t-faint text-[13px]">Nothing else was recorded at this visit.</div>
      ) : (
        <div className="columns-1 gap-x-12 lg:columns-2 2xl:columns-3">
          {panelsInOrder.map((panel) => {
            const list = groups.get(panel);
            if (!list?.length) return null;
            return (
              <Block key={panel} title={panel} note={!adult ? 'paediatric, no adult flags' : panel !== 'Vital signs' ? 'typical adult ranges' : undefined}>
                <ResultTable>{resultRows(list)}</ResultTable>
              </Block>
            );
          })}
          {screening.length > 0 && (
            <Block title="Screening">
              <table className="tbl">
                <tbody>
                  {screening.map((r, i) => {
                    const v = num(r.o.value);
                    const reading = interpretScore(r.name, v, sex);
                    return (
                      <tr key={`${r.raw}:${i}`}>
                        <td>{r.name}</td>
                        <td className="num font-medium">{v !== null ? fmtNum(v, 0) : str(r.o.value_text)}</td>
                        <td className="text-[12px]" style={{ color: reading === 'positive screen' ? 'var(--c-alert)' : 'var(--ink-3)' }}>
                          {reading ?? ''}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Block>
          )}
          {social.length > 0 && (
            <Block title="Social needs" note="PRAPARE screening">
              <dl className="kv text-[12.5px]" style={{ gridTemplateColumns: '170px 1fr' }}>
                {social.map((r, i) => (
                  <div key={`${r.raw}:${i}`} className="contents">
                    <dt>{r.name}</dt>
                    <dd>
                      {r.name === 'Household income'
                        ? fmtMoney(num(r.o.value) ?? num(r.o.value_text)) || str(r.o.value_text)
                        : (str(r.o.value_text) ?? val(num(r.o.value)))}
                    </dd>
                  </div>
                ))}
              </dl>
            </Block>
          )}
          {conditions.length > 0 && (
            <Block title="Diagnosed at this visit">
              {conditions.map((c, i) => {
                const m = markFor(ctx.marks, 'condition', c);
                return (
                  <div key={i} className="py-0.5 text-[13px]">
                    {m ? <LinkButton onClick={() => ctx.onSelect(m.id)}>{term(str(c.description))}</LinkButton> : term(str(c.description))}
                    <span className="t-faint">{str(c.resolved) ? ` · resolved ${fmtDate(str(c.resolved))}` : ' · ongoing'}</span>
                  </div>
                );
              })}
            </Block>
          )}
          {resolved.length > 0 && (
            <Block title="Resolved">
              {resolved.map((c, i) => (
                <div key={i} className="py-0.5 text-[13px]">
                  {term(str(c.description))}
                </div>
              ))}
            </Block>
          )}
          {meds.length > 0 && (
            <Block title="Prescribed">
              {meds.map((m, i) => {
                const mk = markFor(ctx.marks, 'medication', m);
                const name = medicine(str(m.description));
                return (
                  <div key={i} className="py-0.5 text-[13px]">
                    {mk ? <LinkButton onClick={() => ctx.onSelect(mk.id)}>{name}</LinkButton> : name}
                    <span className="t-faint">
                      {str(m.reason) ? ` · for ${term(str(m.reason)).toLowerCase()}` : ''}
                      {num(m.dispenses) ? ` · ${num(m.dispenses)} dispensed` : ''}
                    </span>
                  </div>
                );
              })}
            </Block>
          )}
          {procedures.length > 0 && (
            <Block title="Procedures">
              {procedures.map((p, i) => (
                <div key={i} className="py-0.5 text-[13px]">
                  {term(str(p.description))}
                  {str(p.reason) && <span className="t-faint"> · for {term(str(p.reason)).toLowerCase()}</span>}
                </div>
              ))}
            </Block>
          )}
          {vaccines.length > 0 && (
            <Block title="Immunisations">
              {vaccines.map((v, i) => (
                <div key={i} className="py-0.5 text-[13px]">
                  {term(str(v.description))}
                </div>
              ))}
            </Block>
          )}
          {careplans.length > 0 && (
            <Block title="Care plans started">
              {careplans.map((c, i) => (
                <div key={i} className="py-0.5 text-[13px]">
                  {term(str(c.description))}
                  {str(c.reason) && <span className="t-faint"> · for {term(str(c.reason)).toLowerCase()}</span>}
                </div>
              ))}
            </Block>
          )}
          {allergies.length > 0 && (
            <Block title="Allergies recorded">
              {allergies.map((a, i) => (
                <div key={i} className="py-0.5 text-[13px]">
                  {term(str(a.description))}
                  {str(a.reaction) && <span className="t-faint"> · {term(str(a.reaction)).toLowerCase()}</span>}
                </div>
              ))}
            </Block>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ condition, medicine, vaccine */

const RELATED: [RegExp, string][] = [
  [/hypertension/i, 'Systolic BP'],
  [/diabetes|prediabetes|hyperglyc|metabolic syndrome/i, 'HbA1c'],
  [/obesity|body mass index/i, 'Body mass index'],
  [/hyperlipidemia|hypertriglyceridemia|heart disease|myocardial|coronary/i, 'LDL cholesterol'],
  [/anemia/i, 'Haemoglobin'],
  [/kidney/i, 'eGFR'],
];

function seriesFor(ctx: Ctx, measure: string) {
  const pts: Point[] = [];
  let ref: [number, number] | undefined;
  let units = '';
  for (const o of ctx.b.observations) {
    if (!o.synthetic) continue;
    const def = describe(String(o.name), str(o.category));
    if (def.name !== measure) continue;
    const v = num(o.value);
    const t = parseDate(str(o.date))?.getTime();
    if (v === null || t === undefined) continue;
    pts.push({ t, v });
    ref = def.ref;
    units = unit(str(o.units));
  }
  return { pts: pts.sort((a, z) => a.t - z.t), ref, unit: units };
}

function ConditionDetail({ ctx, m }: { ctx: Ctx; m: Mark }) {
  const name = m.title;
  const rows = [...m.rows].sort((a, z) => String(a.onset).localeCompare(String(z.onset)));
  const onset = parseDate(str(rows[0]?.onset));
  const meds = ctx.b.medications
    .filter((x) => term(str(x.reason)).toLowerCase() === name.toLowerCase())
    .sort((a, z) => String(a.start).localeCompare(String(z.start)));
  const firstOf = new Map<string, Row>();
  for (const x of meds) if (!firstOf.has(medicine(str(x.description)))) firstOf.set(medicine(str(x.description)), x);
  const medNames = [...firstOf.entries()];
  const plans = ctx.b.careplans.filter((x) => term(str(x.reason)).toLowerCase() === name.toLowerCase());
  const related = RELATED.find(([re]) => re.test(name));
  const series = related ? seriesFor(ctx, related[1]) : null;
  // Childhood readings sit on a different scale; adult-onset conditions trend from age 18.
  if (series && onset && ctx.birth && (ageAt(onset, ctx.birth) ?? 0) >= 18) {
    const adult = new Date(ctx.birth.getTime());
    adult.setFullYear(adult.getFullYear() + 18);
    series.pts = series.pts.filter((p) => p.t >= adult.getTime());
  }
  return (
    <div className="grid gap-x-12 gap-y-6 xl:grid-cols-2">
      <div>
        <Kv
          rows={[
            ['First recorded', onset ? `${fmtDate(onset.toISOString())} · age ${ageAt(onset, ctx.birth)}` : ''],
            ['Status', m.end && m.shape === 'bar' ? (m.lines[1] ?? '') : rows.every((r) => str(r.resolved)) ? 'Resolved' : 'Ongoing at cancer diagnosis'],
            ['Episodes', rows.length > 1 ? `${rows.length}` : ''],
            ['Duration', m.end ? fmtSpan((m.end.getTime() - m.start.getTime()) / DAY) : ''],
          ]}
        />
        <Block title="Recorded at">
          {rows.slice(0, 12).map((r, i) => (
            <div key={i} className="flex gap-3 py-0.5 text-[13px]">
              <span className="num t-faint w-[90px] shrink-0">{fmtDate(str(r.onset))}</span>
              <VisitLink ctx={ctx} encounterId={r.encounter_id} />
              {str(r.resolved) && <span className="t-faint">resolved {fmtDate(str(r.resolved))}</span>}
            </div>
          ))}
          {rows.length > 12 && <div className="t-faint text-[12px]">{rows.length - 12} more episodes</div>}
        </Block>
        {medNames.length > 0 && (
          <Block title="Treated with">
            {medNames.map(([n, row]) => {
              const mk = markFor(ctx.marks, 'medication', row);
              return (
                <div key={n} className="py-0.5 text-[13px]">
                  {mk ? <LinkButton onClick={() => ctx.onSelect(mk.id)}>{n}</LinkButton> : n}
                  <span className="t-faint"> · from {fmtMonth(str(row.start))}</span>
                </div>
              );
            })}
          </Block>
        )}
        {plans.length > 0 && (
          <Block title="Care plans">
            {plans.map((c, i) => (
              <div key={i} className="py-0.5 text-[13px]">
                {term(str(c.description))} <span className="t-faint">· {fmtMonth(str(c.start))}</span>
              </div>
            ))}
          </Block>
        )}
      </div>
      {series && series.pts.length > 1 && related && (
        <Block title={`${related[1]} across the record`} note="dashed line: onset; band: typical range">
          <Trend
            points={series.pts}
            refRange={series.ref}
            marker={onset?.getTime()}
            from={series.pts[0].t}
            to={ctx.dx.getTime()}
            unit={series.unit}
          />
        </Block>
      )}
    </div>
  );
}

function MedicationDetail({ ctx, m }: { ctx: Ctx; m: Mark }) {
  const name = m.title;
  const all = ctx.b.medications
    .filter((x) => medicine(str(x.description)) === name)
    .sort((a, z) => String(a.start).localeCompare(String(z.start)));
  const reasons = [...new Set(all.map((x) => term(str(x.reason))).filter(Boolean))];
  const first = parseDate(str(all[0]?.start));
  const total = d3.sum(all, (x) => num(x.total_cost) ?? 0);
  return (
    <div className="grid gap-x-12 gap-y-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
      <div>
        <Kv
          rows={[
            ['Medication', product(str(all[0]?.description))],
            ['For', reasons.join('; ') || 'Not recorded'],
            ['First prescribed', first ? `${fmtDate(first.toISOString())} · age ${ageAt(first, ctx.birth)}` : ''],
            ['This course', m.end ? `${fmtDate(m.start.toISOString())} to ${fmtDate(m.end.toISOString())} (${fmtSpan((m.end.getTime() - m.start.getTime()) / DAY)})` : fmtDate(m.start.toISOString())],
            ['Prescriptions', `${all.length}`],
            ['Total cost', total ? fmtMoney(total) : ''],
          ]}
        />
      </div>
      <Block title="Prescription history">
        <table className="tbl">
          <thead>
            <tr>
              <th>Start</th>
              <th>Stop</th>
              <th>Prescribed at</th>
              <th className="text-right">Dispensed</th>
            </tr>
          </thead>
          <tbody>
            {all.slice(-14).map((x, i) => (
              <tr key={i}>
                <td className="num whitespace-nowrap">{fmtDate(str(x.start))}</td>
                <td className="num whitespace-nowrap">{str(x.stop) ? fmtDate(str(x.stop)) : 'ongoing'}</td>
                <td>
                  <VisitLink ctx={ctx} encounterId={x.encounter_id} />
                </td>
                <td className="num text-right">{num(x.dispenses) ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {all.length > 14 && <div className="t-faint mt-1 text-[12px]">Showing the latest 14 of {all.length}.</div>}
      </Block>
    </div>
  );
}

function VaccineDetail({ ctx, m }: { ctx: Ctx; m: Mark }) {
  const d = m.start;
  return (
    <div className="grid gap-x-12 xl:grid-cols-2">
      <Kv
        rows={[
          ['Given', `${fmtDate(d.toISOString())} · age ${ageAt(d, ctx.birth)}`],
          ['At', <VisitLink key="v" ctx={ctx} encounterId={m.rows[0]?.encounter_id ?? null} />],
        ]}
      />
      <Block title="Immunisations">
        {m.rows.map((r, i) => (
          <div key={i} className="py-0.5 text-[13px]">
            {term(str(r.description))}
          </div>
        ))}
      </Block>
    </div>
  );
}

/* ------------------------------------------------------------------ cancer course */

function NavButtons({ items }: { items: [string, () => void][] }) {
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {items.map(([label, fn]) => (
        <button key={label} className="btn" onClick={fn}>
          {label}
        </button>
      ))}
    </div>
  );
}

function DiagnosisDetail({ ctx }: { ctx: Ctx }) {
  const { b, onNavigate, dx } = ctx;
  const p = b.patient;
  const tnm = [str(p.t_stage), str(p.n_stage), str(p.m_stage)].filter(Boolean).join(' ');
  const yearBefore = b.encounters.filter((e) => {
    const t = parseDate(str(e.start))?.getTime() ?? 0;
    return t >= dx.getTime() - 365 * DAY && t <= dx.getTime();
  });
  const lastVisit = b.encounters[b.encounters.length - 1];
  const primary = b.radiologySeries.find((s) => s.role === 'primary');
  return (
    <div className="grid gap-x-12 gap-y-6 xl:grid-cols-2">
      <div>
        <Kv
          rows={[
            ['Cancer', str(p.cancer_type)],
            ['Histology', plain(str(p.primary_diagnosis))],
            ['Site', [str(p.laterality), plain(str(p.tissue_of_origin))].filter(Boolean).join(' ').toLowerCase()],
            ['Stage', [str(p.stage), str(p.stage_system)].filter(Boolean).join(', ')],
            ['TNM', tnm],
            ['Grade', str(p.grade)],
            ['Gleason', num(p.gleason_score) ? String(num(p.gleason_score)) : ''],
            ['ICD-10', [str(p.icd10), str(p.morphology)].filter(Boolean).join(' · ')],
            ['Diagnosed by', str(p.method_of_diagnosis)],
            ['Age', `${num(p.age_at_diagnosis)}`],
          ]}
        />
      </div>
      <div>
        <Block title="Leading up to it" note="synthetic primary care">
          <div className="text-[13px]">
            {yearBefore.length} visits in the year before diagnosis
            {lastVisit ? (
              <>
                ; last visit <VisitLink ctx={ctx} encounterId={lastVisit.encounter_id} />
              </>
            ) : null}
            .
          </div>
        </Block>
        <NavButtons
          items={[
            ['Open the diagnostic slide', () => onNavigate('imaging')],
            ...(primary ? [['Open the staging scan', () => onNavigate('imaging', String(primary.series_key))] as [string, () => void]] : []),
            ['Tumour genome', () => onNavigate('genomics')],
            ['Pathology report', () => onNavigate('report')],
          ]}
        />
      </div>
    </div>
  );
}

function SpreadDetail({ ctx, m }: { ctx: Ctx; m: Mark }) {
  const r = m.rows[0];
  const day = Math.round((m.start.getTime() - ctx.dx.getTime()) / DAY);
  const next = ctx.b.treatments
    .map((t, idx) => ({ t, idx }))
    .filter(({ t }) => t.given && num(t.start_day) !== null && (num(t.start_day) ?? 0) >= day - 7 && (num(t.start_day) ?? 0) <= day + 240);
  return (
    <div className="grid gap-x-12 gap-y-6 xl:grid-cols-2">
      <Kv
        rows={[
          ['Event', m.title],
          ['When', `${fmtDate(m.start.toISOString())} · ${fmtDay(day)} · ${fmtSpan(day)} after diagnosis`],
          ['Type', str(r.classification) ?? str(r.progression_type)],
          ['Site', plain(str(r.site) ?? str(r.progression_site))],
          ['Histology', plain(str(r.primary_diagnosis))],
          ['Evidence', str(r.evidence)],
        ]}
      />
      <Block title="Treatment that followed">
        {next.length ? (
          next.map(({ t, idx }) => (
            <div key={idx} className="flex gap-3 py-0.5 text-[13px]">
              <span className="num t-faint w-[70px] shrink-0">{fmtDay(num(t.start_day))}</span>
              <LinkButton onClick={() => ctx.onSelect(`t:${idx}`)}>{str(t.agent) ?? plain(str(t.treatment_type))}</LinkButton>
            </div>
          ))
        ) : (
          <div className="t-faint text-[13px]">No dated treatment recorded in the following eight months.</div>
        )}
      </Block>
    </div>
  );
}

function StatusDetail({ m }: { m: Mark }) {
  const f = m.rows[0];
  return (
    <Kv
      rows={[
        ['Assessment', str(f.timepoint)],
        ['Disease status', str(f.disease_response)?.replace('TF-', '').replace('WT-', '')],
        ['Progression', str(f.progression) ? `${str(f.progression)}${str(f.progression_type) ? `, ${str(f.progression_type)?.toLowerCase()}` : ''}` : ''],
        ['ECOG', num(f.ecog) !== null ? String(num(f.ecog)) : ''],
        ['Karnofsky', num(f.karnofsky) !== null ? String(num(f.karnofsky)) : ''],
        ['Imaging', [str(f.imaging_type), str(f.imaging_findings)].filter(Boolean).join(': ')],
      ]}
    />
  );
}

function OutcomeDetail({ ctx, m }: { ctx: Ctx; m: Mark }) {
  const p = ctx.b.patient;
  const died = m.shape === 'cross';
  const day = Math.round((m.start.getTime() - ctx.dx.getTime()) / DAY);
  return (
    <Kv
      rows={[
        ['Status', died ? 'Died' : 'Alive at last contact'],
        ['Date', `${fmtDate(m.start.toISOString())} · ${fmtDay(day)} · age ${ageAt(m.start, ctx.birth)}`],
        ['After diagnosis', fmtSpan(day)],
        ['Cause of death', str(p.cause_of_death)],
        ['Overall survival', num(p.os_months) ? `${fmtNum(num(p.os_months), 1)} months` : ''],
        ['Progression-free', num(p.pfs_months) ? `${fmtNum(num(p.pfs_months), 1)} months` : ''],
      ]}
    />
  );
}

function TreatmentDetail({ ctx, m }: { ctx: Ctx; m: Mark }) {
  const t = m.rows[0];
  const cls = m.kind === 'drug' ? drugClass(str(t.agent), str(t.treatment_type)) : null;
  const partners = ctx.b.treatments
    .map((x, idx) => ({ x, idx }))
    .filter(({ x }) => x !== t && x.given && str(x.agent) && num(x.start_day) !== null && num(x.start_day) === num(t.start_day));
  const start = num(t.start_day);
  const end = num(t.end_day);
  return (
    <div className="grid gap-x-12 gap-y-6 xl:grid-cols-2">
      <Kv
        rows={[
          ['Treatment', str(t.agent) ?? plain(str(t.treatment_type))],
          ['Class', cls ? CLASS_STYLE[cls].label : plain(str(t.treatment_type))],
          ['Started', start !== null ? `${fmtDate(str(t.start_date))} · ${fmtDay(start)}` : 'not recorded'],
          ['Ended', end !== null ? `${fmtDate(str(t.end_date))} · ${fmtDay(end)}` : str(t.outcome) === 'Treatment Ongoing' ? 'ongoing at last contact' : 'not recorded'],
          ['Duration', start !== null && end !== null ? fmtSpan(end - start) : ''],
          ['Cycles', num(t.cycles) ? String(num(t.cycles)) : ''],
          ['Dose', num(t.dose) ? `${fmtNum(num(t.dose), 0)} ${str(t.dose_units) ?? ''}` : ''],
          ['Fractions', num(t.fractions) ? String(num(t.fractions)) : ''],
          ['Route', str(t.route)],
          ['Site', str(t.anatomic_site)],
          ['Intent', str(t.intent)],
          ['Disease status', str(t.disease_status)],
          ['Response', str(t.outcome)],
          ['Clinical trial', str(t.clinical_trial)],
        ]}
      />
      <div>
        {partners.length > 0 && (
          <Block title="Given with">
            {partners.map(({ x, idx }) => (
              <div key={idx} className="py-0.5 text-[13px]">
                <LinkButton onClick={() => ctx.onSelect(`t:${idx}`)}>{str(x.agent)}</LinkButton>
              </div>
            ))}
          </Block>
        )}
        <NavButtons items={[['Full treatment history', () => ctx.onNavigate('clinical')]]} />
      </div>
    </div>
  );
}

function ScanDetail({ ctx, m }: { ctx: Ctx; m: Mark }) {
  const s = m.rows[0];
  const series = m.rows[1];
  const day = Math.round((m.start.getTime() - ctx.dx.getTime()) / DAY);
  const measures = parseJson<Record<string, { volumeMl: number }>>(series?.ai_measures ?? null, {});
  return (
    <div className="grid gap-x-12 gap-y-6 xl:grid-cols-2">
      <Kv
        rows={[
          ['Study', `${str(s.modalities)} ${str(s.body_part)?.toLowerCase() ?? ''}`],
          ['When', `${fmtDate(str(s.date))} · ${fmtDay(day)}`],
          ['Series and images', `${num(s.series_count)} series, ${fmtNum(num(s.images), 0)} images`],
          ['Series in the viewer', series ? str(series.description) : 'none'],
          ['Scanner', series ? [str(series.manufacturer), str(series.model)].filter(Boolean).join(' ') : ''],
          ['Slice thickness', series && num(series.slice_thickness_mm) ? `${num(series.slice_thickness_mm)} mm` : ''],
          ['Contrast', series ? str(series.contrast) : ''],
          ['Original DICOM', series ? `${fmtBytes(num(series.raw_bytes))}, ${num(series.raw_files)} files` : ''],
        ]}
      />
      <div>
        {Object.keys(measures).length > 0 && (
          <Block title="AI segmentation" note={str(series?.ai_algorithm) ?? ''}>
            {Object.entries(measures).map(([k, v]) => (
              <div key={k} className="flex gap-3 py-0.5 text-[13px]">
                <span className="w-[90px]">{k}</span>
                <span className="num">{fmtNum(v.volumeMl, 1)} mL</span>
              </div>
            ))}
          </Block>
        )}
        {series ? (
          <NavButtons items={[['Open in the viewer', () => ctx.onNavigate('imaging', String(series.series_key))]]} />
        ) : (
          <div className="t-faint text-[13px]">Listed in NCI Imaging Data Commons; its images are not loaded in this demo.</div>
        )}
      </div>
    </div>
  );
}

function SlideDetail({ ctx }: { ctx: Ctx }) {
  const s = ctx.b.slide!;
  const gp = ((num(s.width) ?? 0) * (num(s.height) ?? 0)) / 1e9;
  return (
    <div className="grid gap-x-12 gap-y-6 xl:grid-cols-2">
      <Kv
        rows={[
          ['Slide', str(s.barcode)],
          ['Stain', `${str(s.stain)}, ${str(s.specimen)}`],
          ['Size', `${fmtNum(num(s.width), 0)} × ${fmtNum(num(s.height), 0)} px (${fmtNum(gp, 1)} gigapixels)`],
          ['Scanned at', `${num(s.objective_power)}× · ${fmtNum(num(s.mpp), 3)} µm per pixel`],
          ['Original', `${fmtBytes(num(s.raw_bytes))} Aperio SVS`],
          ['AI lymphocytes', num(s.til_positive_fraction) !== null ? `${fmtNum((num(s.til_positive_fraction) ?? 0) * 100, 1)}% of tissue tiles` : ''],
        ]}
      />
      <NavButtons items={[['Open the slide', () => ctx.onNavigate('imaging')]]} />
    </div>
  );
}

function GenomeDetail({ ctx }: { ctx: Ctx }) {
  const g = ctx.b.profile ?? {};
  const drivers = ctx.b.drivers.filter((d) => !/Silent|Intron|UTR|Flank|RNA|IGR/.test(String(d.mutation_type))).slice(0, 8);
  return (
    <div className="grid gap-x-12 gap-y-6 xl:grid-cols-2">
      <Kv
        rows={[
          ['Subtype', str(g.subtype)?.replace(/_/g, ' ')],
          ['Mutation burden', `${fmtNum(num(g.tmb), 1)} per Mb${num(g.tmb_percentile) !== null ? `, ${ordinal(Math.round(num(g.tmb_percentile) ?? 0))} percentile` : ''}`],
          ['Mutations', fmtNum(num(g.mutation_count), 0)],
          ['Microsatellites', str(g.msi_status)],
          ['Genome altered', num(g.fraction_genome_altered) !== null ? `${fmtNum((num(g.fraction_genome_altered) ?? 0) * 100, 0)}%` : ''],
          ['Leukocyte fraction', num(g.leukocyte_fraction) !== null ? `${fmtNum((num(g.leukocyte_fraction) ?? 0) * 100, 0)}% of cells` : ''],
        ]}
      />
      <div>
        <Block title="Driver gene mutations">
          {drivers.map((d, i) => (
            <div key={i} className="mono py-0.5">
              {str(d.gene)} {str(d.protein_change)}
            </div>
          ))}
        </Block>
        <NavButtons items={[['Open the tumour genome', () => ctx.onNavigate('genomics')]]} />
      </div>
    </div>
  );
}

function TestsDetail({ m }: { m: Mark }) {
  const method = (r: Row) => str(r.method) ?? str(r.timepoint) ?? '';
  const hasMethod = m.rows.some((r) => method(r));
  const hasRef = m.rows.some((r) => num(r.ref_low) !== null);
  return (
    <table className="tbl max-w-[760px]">
      <thead>
        <tr>
          <th>Test</th>
          <th>Result</th>
          {hasMethod && <th>Method</th>}
          {hasRef && <th>Reference</th>}
        </tr>
      </thead>
      <tbody>
        {m.rows.map((r, i) => {
          const v = num(r.value);
          return (
            <tr key={i}>
              <td className="font-medium">{str(r.test) ?? str(r.name)}</td>
              <td className="num">
                {v !== null ? `${fmtNum(v, 2)} ${str(r.units) ?? ''}` : str(r.result)}
                {str(r.intensity) ? ` (${str(r.intensity)})` : ''}
                {str(r.exon) ? `, exon ${str(r.exon)} ${str(r.variant_type)?.toLowerCase() ?? ''}` : ''}
              </td>
              {hasMethod && <td className="t-muted">{method(r)}</td>}
              {hasRef && <td className="t-faint num">{num(r.ref_low) !== null ? `${num(r.ref_low)}–${num(r.ref_high)}` : ''}</td>}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/* ------------------------------------------------------------------ panel */

const SOURCE: Partial<Record<Mark['kind'], string>> = {
  visit: 'encounter, observation, condition, medication, procedure, immunization, careplan',
  condition: 'condition, medication, careplan, observation',
  medication: 'medication, encounter',
  vaccine: 'immunization',
  diagnosis: 'patient, diagnosis',
  spread: 'diagnosis, follow_up, treatment',
  status: 'follow_up',
  outcome: 'patient',
  surgery: 'treatment',
  radiation: 'treatment',
  drug: 'treatment',
  scan: 'radiology_study, radiology_series',
  slide: 'pathology_slide',
  genome: 'molecular_profile, somatic_mutation',
  tests: 'biomarker_test, observation',
  report: 'pathology_report',
};

const SILO: Partial<Record<Mark['kind'], string>> = {
  scan: 'imaging_lakehouse',
  slide: 'imaging_lakehouse',
  genome: 'genomics_lakehouse',
};

export function TimelineDetail({
  b,
  mark,
  marks,
  items,
  noun,
  birth,
  dx,
  onSelect,
  onNavigate,
  scrubber,
  actions,
  children,
  hideBody,
}: {
  b: PatientBundle;
  mark: Mark;
  marks: Mark[];
  /** The open tab's items in time order; Earlier and Later step through them. */
  items: Mark[];
  noun: string;
  birth: Date;
  dx: Date;
  onSelect: (id: string) => void;
  onNavigate: Navigate;
  /** Drag control over the tab's items. */
  scrubber?: ReactNode;
  /** Extra buttons in the header (notes on this event, add a note). */
  actions?: ReactNode;
  /** Drawn between the header and the detail body (e.g. a viewer). */
  children?: ReactNode;
  /** Leave out the standard detail body when the tab draws its own. */
  hideBody?: boolean;
}) {
  const history = useMemo(() => {
    const map = new Map<string, Point[]>();
    for (const o of b.observations) {
      const v = num(o.value);
      const t = parseDate(str(o.date))?.getTime();
      if (v === null || t === undefined) continue;
      const list = map.get(String(o.name)) ?? [];
      list.push({ t, v });
      map.set(String(o.name), list);
    }
    map.forEach((l) => l.sort((a, z) => a.t - z.t));
    return map;
  }, [b]);
  const ctx: Ctx = { b, marks, birth, dx, history, onSelect, onNavigate };

  const idx = items.findIndex((m) => m.id === mark.id);
  const day = Math.round((mark.start.getTime() - dx.getTime()) / DAY);
  const age = ageAt(mark.start, birth);

  let body: ReactNode = null;
  switch (mark.kind) {
    case 'visit':
      body = <VisitDetail ctx={ctx} e={mark.rows[0]} />;
      break;
    case 'condition':
      body = <ConditionDetail ctx={ctx} m={mark} />;
      break;
    case 'medication':
      body = <MedicationDetail ctx={ctx} m={mark} />;
      break;
    case 'vaccine':
      body = <VaccineDetail ctx={ctx} m={mark} />;
      break;
    case 'diagnosis':
      body = <DiagnosisDetail ctx={ctx} />;
      break;
    case 'spread':
      body = <SpreadDetail ctx={ctx} m={mark} />;
      break;
    case 'status':
      body = <StatusDetail m={mark} />;
      break;
    case 'outcome':
      body = <OutcomeDetail ctx={ctx} m={mark} />;
      break;
    case 'surgery':
    case 'radiation':
    case 'drug':
      body = <TreatmentDetail ctx={ctx} m={mark} />;
      break;
    case 'scan':
      body = <ScanDetail ctx={ctx} m={mark} />;
      break;
    case 'slide':
      body = <SlideDetail ctx={ctx} />;
      break;
    case 'genome':
      body = <GenomeDetail ctx={ctx} />;
      break;
    case 'tests':
      body = <TestsDetail m={mark} />;
      break;
    default:
      body = null;
  }

  const title =
    mark.kind === 'visit'
      ? `${VISIT_CLASS[str(mark.rows[0].encounter_class) ?? '']?.label ?? 'Visit'}: ${term(str(mark.rows[0].description))}`
      : mark.title;
  const silo = SILO[mark.kind] ?? 'clinical_lakehouse';

  return (
    <section aria-label="Selected event">
      <div className="mb-3 flex flex-wrap items-start gap-x-6 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="t-label flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="num">
              {fmtDate(mark.start.toISOString())}
              {age !== null && age >= 0 ? ` · age ${age}` : ''}
              {` · ${day < 0 ? `${fmtSpan(-day)} before diagnosis` : day === 0 ? 'at diagnosis' : `${fmtSpan(day)} after diagnosis`}`}
            </span>
            {mark.kind === 'note' ? (
              <span className="src">app database</span>
            ) : mark.synthetic ? (
              <span className="syn-tag">synthetic, Synthea</span>
            ) : (
              <span className="src">real, TCGA</span>
            )}
            {SOURCE[mark.kind] && (
              <span className="src">
                <span className={`swatch sw-${silo === 'clinical_lakehouse' ? 'clinical' : silo === 'genomics_lakehouse' ? 'genomics' : 'imaging'}`} />
                {silo}: {SOURCE[mark.kind]}
              </span>
            )}
          </div>
          <h3 className="t-display mt-1 text-[24px] leading-tight">{title}</h3>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {actions}
          {items.length > 1 && (
            <>
              <span className="t-faint num text-[12px]">
                {noun} {idx + 1} of {items.length}
              </span>
              <button className="btn" disabled={idx <= 0} onClick={() => onSelect(items[idx - 1].id)} aria-label="Earlier">
                ‹ Earlier
              </button>
              <button className="btn" disabled={idx >= items.length - 1} onClick={() => onSelect(items[idx + 1].id)} aria-label="Later">
                Later ›
              </button>
            </>
          )}
        </div>
      </div>
      {scrubber && <div className="hair mb-5 border-b pb-1">{scrubber}</div>}
      {children}
      {!hideBody && body && (
        <div key={mark.id} className="rise">
          {body}
        </div>
      )}
    </section>
  );
}
