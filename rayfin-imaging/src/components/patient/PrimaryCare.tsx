import * as d3 from 'd3';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { num, str, type PatientBundle, type Row } from '@/lib/api';
import { describe, flag, interpretScore, medicine, term, VISIT_CLASS } from '@/lib/clinical';
import { ageAt, fmtDate, fmtMoney, fmtMonth, fmtNum, parseDate } from '@/lib/format';
import { openInTimeline } from '@/lib/timelineLink';

const DAY = 86_400_000;
const YEAR = 365.25 * DAY;

type Window = 'decade' | 'adult' | 'all';
type Point = { t: number; v: number; eid: string | null };
type Series = { name: string; re: RegExp; ref?: [number, number] };
type Measure = { id: string; label: string; unit: string; digits: number; series: Series[]; refLabel?: string };

/** The measurements a GP would look at first. Reference ranges are typical adult ranges, for orientation only. */
const MEASURES: Measure[] = [
  {
    id: 'bp',
    label: 'Blood pressure',
    unit: 'mmHg',
    digits: 0,
    refLabel: '< 130/80',
    series: [
      { name: 'Systolic', re: /^Systolic Blood Pressure/, ref: [90, 129] },
      { name: 'Diastolic', re: /^Diastolic Blood Pressure/, ref: [60, 79] },
    ],
  },
  { id: 'bmi', label: 'Body mass index', unit: 'kg/m²', digits: 1, series: [{ name: 'BMI', re: /^Body mass index \(BMI\) \[Ratio\]/, ref: [18.5, 24.9] }] },
  { id: 'weight', label: 'Weight', unit: 'kg', digits: 1, series: [{ name: 'Weight', re: /^Body Weight/ }] },
  { id: 'hr', label: 'Heart rate', unit: '/min', digits: 0, series: [{ name: 'Heart rate', re: /^Heart rate/, ref: [60, 100] }] },
  { id: 'a1c', label: 'HbA1c', unit: '%', digits: 1, series: [{ name: 'HbA1c', re: /^Hemoglobin A1c/, ref: [4, 5.6] }] },
  { id: 'glucose', label: 'Glucose', unit: 'mg/dL', digits: 0, series: [{ name: 'Glucose', re: /^Glucose \[Mass\/volume\] in (Blood|Serum)/, ref: [70, 99] }] },
  { id: 'ldl', label: 'LDL cholesterol', unit: 'mg/dL', digits: 0, refLabel: '< 130', series: [{ name: 'LDL', re: /^Cholesterol in LDL/, ref: [0, 129] }] },
  { id: 'hdl', label: 'HDL cholesterol', unit: 'mg/dL', digits: 0, refLabel: '≥ 40', series: [{ name: 'HDL', re: /^Cholesterol in HDL/, ref: [40, 1000] }] },
  { id: 'creat', label: 'Creatinine', unit: 'mg/dL', digits: 2, series: [{ name: 'Creatinine', re: /^Creatinine/, ref: [0.6, 1.3] }] },
  { id: 'hb', label: 'Haemoglobin', unit: 'g/dL', digits: 1, series: [{ name: 'Haemoglobin', re: /^Hemoglobin \[Mass\/volume\] in Blood/, ref: [12, 17.5] }] },
];

const WINDOWS: [Window, string][] = [
  ['decade', 'Last 10 years'],
  ['adult', 'Adult life'],
  ['all', 'Whole record'],
];

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.floor(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** Year ticks at least `minPx` apart. */
function yearTicks(from: number, to: number, px: number, minPx = 42): Date[] {
  const years = (to - from) / YEAR;
  const step = [1, 2, 5, 10, 20].find((s) => px / (years / s) >= minPx) ?? 20;
  return d3.utcYear.every(step)?.range(new Date(from), new Date(to)) ?? [];
}

function nearest(points: Point[], t: number, within: number): Point | null {
  let best: Point | null = null;
  for (const p of points) if (Math.abs(p.t - t) <= within && (!best || Math.abs(p.t - t) < Math.abs(best.t - t))) best = p;
  return best;
}

function TrendChart({
  m,
  series,
  from,
  to,
  adultFrom,
  hover: hoverT,
  pinned,
  onHover,
}: {
  m: Measure;
  series: Point[][];
  from: number;
  to: number;
  adultFrom: number;
  hover: number | null;
  /** The selected visit's date, shown when nothing is hovered. */
  pinned: number | null;
  onHover: (t: number | null) => void;
}) {
  const hover = hoverT ?? (pinned !== null && pinned >= from && pinned <= to ? pinned : null);
  const [ref, w] = useWidth<HTMLDivElement>();
  const H = 112;
  const M = { l: 34, r: 8, t: 6, b: 18 };
  const all = series.flat();
  const primary = series[0];
  const within = (to - from) / 30;
  const hovered = hover !== null ? series.map((s) => nearest(s, hover, within)) : null;
  const shown = hovered && hovered[0] ? hovered : series.map((s) => s[s.length - 1] ?? null);
  const shownT = shown[0]?.t ?? null;
  const flags = shown.map((p, i) => (p && p.t >= adultFrom ? flag(p.v, m.series[i].ref) : null));
  const anyFlag = flags.find(Boolean);
  const values = all.map((p) => p.v);

  let y: d3.ScaleLinear<number, number> | null = null;
  if (all.length) {
    let lo = d3.min(values)!;
    let hi = d3.max(values)!;
    const span = Math.max(hi - lo, Math.abs(hi) * 0.15, 0.1);
    // Show the reference band when it is near the data, so a result just outside the range reads as such.
    for (const s of m.series) {
      if (!s.ref) continue;
      for (const bound of s.ref) {
        if (bound > 0 && bound >= lo - 2 * span && bound <= hi + 2 * span) {
          lo = Math.min(lo, bound);
          hi = Math.max(hi, bound);
        }
      }
    }
    const pad = (hi - lo || span) * 0.12;
    // Measurements here are never negative.
    y = d3.scaleLinear().domain([Math.max(0, lo - pad), hi + pad]).nice(4).range([H - M.b, M.t]);
  }
  const yFmt = y ? y.tickFormat(3) : () => '';
  const x = d3.scaleUtc().domain([new Date(from), new Date(to)]).range([M.l, Math.max(M.l + 10, w - M.r)]);
  const xt = w ? yearTicks(from, to, w - M.l - M.r) : [];

  const pick = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - r.left;
    if (px < M.l || px > w - M.r) return onHover(null);
    onHover(x.invert(px).getTime());
  };

  return (
    <div className="trend min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <div className="trend-name">{m.label}</div>
        <div className="t-faint num text-[11px]">
          {primary.length ? `${primary.length} result${primary.length === 1 ? '' : 's'}` : ''}
          {m.series[0].ref || m.refLabel ? ` · ref ${m.refLabel ?? `${m.series[0].ref![0]}–${m.series[0].ref![1]}`}` : ''}
        </div>
      </div>
      <div className="num mt-0.5 flex items-baseline gap-1.5">
        <span className="text-[19px] leading-none" style={{ color: anyFlag ? 'var(--c-alert)' : undefined }}>
          {shown[0] ? shown.map((p) => (p ? fmtNum(p.v, m.digits) : '–')).join('/') : '–'}
        </span>
        <span className="t-faint text-[11.5px]">{m.unit}</span>
        {anyFlag && <span className="text-[11.5px]" style={{ color: 'var(--c-alert)' }}>{anyFlag}</span>}
      </div>
      <div className="t-faint num h-[16px] text-[11px]">
        {shownT !== null
          ? `${hovered && hovered[0] ? (hoverT === null ? 'at this visit,' : 'on') : 'latest'} ${fmtDate(new Date(shownT).toISOString())}`
          : 'Not measured in this period'}
      </div>
      <div ref={ref} className="relative">
        {w > 0 && (
          <svg
            width={w}
            height={H}
            className="block"
            style={{ cursor: all.length ? 'crosshair' : 'default' }}
            onPointerMove={pick}
            onPointerLeave={() => onHover(null)}
            onClick={() => {
              const p = shown[0];
              if (p?.eid) openInTimeline({ id: `v:${p.eid}` });
            }}
          >
            <rect x={M.l} y={M.t} width={Math.max(0, w - M.l - M.r)} height={H - M.t - M.b} fill="none" stroke="var(--line)" />
            {!all.length && (
              <text x={(M.l + w - M.r) / 2} y={(M.t + H - M.b) / 2 + 4} textAnchor="middle" className="trend-axis">
                No results in this period
              </text>
            )}
            {y &&
              m.series.map(
                (s, i) =>
                  s.ref && (
                    <rect
                      key={`ref${i}`}
                      x={M.l}
                      width={Math.max(0, w - M.l - M.r)}
                      y={Math.max(M.t, y(s.ref[1]))}
                      height={Math.max(0, Math.min(H - M.b, y(s.ref[0])) - Math.max(M.t, y(s.ref[1])))}
                      fill="var(--surface)"
                      opacity={m.series.length > 1 ? 0.7 : 1}
                    />
                  )
              )}
            {y &&
              y.ticks(3).map((v) => (
                <g key={v}>
                  <line x1={M.l} x2={w - M.r} y1={y!(v)} y2={y!(v)} stroke="var(--line)" strokeDasharray="1 3" />
                  <text x={M.l - 5} y={y!(v) + 3} textAnchor="end" className="trend-axis">
                    {yFmt(v)}
                  </text>
                </g>
              ))}
            {xt.map((d) => (
              <g key={d.getTime()}>
                <line x1={x(d)} x2={x(d)} y1={H - M.b} y2={H - M.b + 3} stroke="var(--line-strong)" />
                <text x={x(d)} y={H - 4} textAnchor="middle" className="trend-axis">
                  {d.getUTCFullYear()}
                </text>
              </g>
            ))}
            {y &&
              series.map((pts, i) => (
                <g key={i}>
                  {pts.length > 1 && (
                    <polyline
                      fill="none"
                      stroke="var(--c-syn)"
                      strokeWidth={1.1}
                      strokeDasharray="3 2"
                      points={pts.map((p) => `${x(new Date(p.t))},${y!(p.v)}`).join(' ')}
                    />
                  )}
                  {pts.map((p, k) => {
                    const f = p.t >= adultFrom ? flag(p.v, m.series[i].ref) : null;
                    const c = f ? 'var(--c-alert)' : 'var(--ink-2)';
                    return (
                      <circle
                        key={k}
                        cx={x(new Date(p.t))}
                        cy={y!(p.v)}
                        r={2.3}
                        fill={i === 0 ? c : 'var(--bg)'}
                        stroke={c}
                        strokeWidth={i === 0 ? 0 : 1.2}
                      />
                    );
                  })}
                </g>
              ))}
            {y && pinned !== null && pinned >= from && pinned <= to && (
              <line x1={x(new Date(pinned))} x2={x(new Date(pinned))} y1={M.t} y2={H - M.b} stroke="var(--accent)" strokeWidth={1.5} />
            )}
            {y && hoverT !== null && hoverT >= from && hoverT <= to && (
              <line x1={x(new Date(hoverT))} x2={x(new Date(hoverT))} y1={M.t} y2={H - M.b} stroke="var(--accent)" opacity={0.5} />
            )}
            {y &&
              hovered?.map(
                (p, i) => p && <circle key={`h${i}`} cx={x(new Date(p.t))} cy={y!(p.v)} r={4.5} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
              )}
          </svg>
        )}
      </div>
    </div>
  );
}

/** Visits per year, stacked by type. */
function VisitsChart({ encounters, from, to }: { encounters: Row[]; from: number; to: number }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const H = 96;
  const M = { l: 26, r: 4, t: 4, b: 18 };
  const years = d3.range(new Date(from).getUTCFullYear(), new Date(to).getUTCFullYear() + 1);
  const counts = years.map((yr) => {
    const c = [0, 0, 0];
    for (const e of encounters) {
      const d = parseDate(str(e.start));
      if (!d || d.getUTCFullYear() !== yr || d.getTime() < from || d.getTime() > to) continue;
      c[VISIT_CLASS[str(e.encounter_class) ?? '']?.row ?? 1] += 1;
    }
    return { yr, c };
  });
  const max = Math.max(1, ...counts.map((r) => r.c[0] + r.c[1] + r.c[2]));
  const x = d3.scaleBand<number>().domain(years).range([M.l, Math.max(M.l + 10, w - M.r)]).padding(0.25);
  const y = d3.scaleLinear().domain([0, max]).nice(3).range([H - M.b, M.t]);
  const step = Math.ceil(years.length / Math.max(1, Math.floor((w - M.l) / 38)));
  const fills = ['var(--ink-3)', 'var(--ink-2)', 'var(--c-alert)'];
  return (
    <div ref={ref}>
      {w > 0 && (
        <svg width={w} height={H} className="block">
          {y.ticks(3).map((v) => (
            <g key={v}>
              <line x1={M.l} x2={w - M.r} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeDasharray="1 3" />
              <text x={M.l - 5} y={y(v) + 3} textAnchor="end" className="trend-axis">
                {v}
              </text>
            </g>
          ))}
          {counts.map(({ yr, c }) => {
            let top = H - M.b;
            return (
              <g key={yr}>
                {c.map((n, i) => {
                  if (!n) return null;
                  const h = H - M.b - y(n);
                  top -= h;
                  return <rect key={i} x={x(yr)} y={top} width={x.bandwidth()} height={h} fill={fills[i]} opacity={i === 0 ? 0.55 : 1} />;
                })}
                {(yr - years[0]) % step === 0 && (
                  <text x={(x(yr) ?? 0) + x.bandwidth() / 2} y={H - 4} textAnchor="middle" className="trend-axis">
                    {yr}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
      <div className="t-faint mt-1 flex flex-wrap gap-x-4 text-[11px]">
        {['Routine', 'Problem visit', 'Emergency or inpatient'].map((l, i) => (
          <span key={l} className="flex items-center gap-1.5">
            <span className="swatch" style={{ background: fills[i], opacity: i === 0 ? 0.55 : 1 }} />
            {l}
          </span>
        ))}
      </div>
    </div>
  );
}

function Block({ title, note, children, className }: { title: string; note?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`min-w-0 ${className ?? ''}`}>
      <div className="mb-2 flex items-baseline gap-3">
        <h3 className="text-[14px] font-medium">{title}</h3>
        {note && <span className="t-faint text-[11.5px]">{note}</span>}
      </div>
      {children}
    </div>
  );
}

function Link({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button className="link text-left" onClick={onClick}>
      {children}
    </button>
  );
}

/** Trend charts of the measurements a GP looks at first, with the selected visit pinned on every chart. */
export function MeasurementsPanel({ b, pinned }: { b: PatientBundle; pinned: number | null }) {
  const dxDate = parseDate(str(b.patient.diagnosis_date))!;
  const dx = dxDate.getTime();
  const age = num(b.patient.age_at_diagnosis) ?? 0;
  const firstVisit = parseDate(str(b.encounters[0]?.start));
  const birth = new Date(Math.min(dx - age * YEAR - 180 * DAY, firstVisit?.getTime() ?? Infinity));
  const adultFrom = birth.getTime() + 18 * YEAR;
  const [range, setRange] = useState<Window>('decade');
  const [hover, setHover] = useState<number | null>(null);

  const firstObs = parseDate(str(b.observations.find((o) => o.synthetic)?.date))?.getTime() ?? birth.getTime();
  const from = range === 'decade' ? dx - 10 * YEAR : range === 'adult' ? Math.max(adultFrom, firstObs) : Math.min(firstObs, firstVisit?.getTime() ?? firstObs);
  useEffect(() => {
    if (pinned !== null && pinned < from) setRange(pinned >= adultFrom ? 'adult' : 'all');
  }, [pinned]); // eslint-disable-line react-hooks/exhaustive-deps

  const byName = useMemo(() => {
    const map = new Map<string, Point[]>();
    for (const o of b.observations) {
      if (!o.synthetic) continue;
      const v = num(o.value);
      const t = parseDate(str(o.date))?.getTime();
      if (v === null || t === undefined || t > dx) continue;
      const k = String(o.name);
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push({ t, v, eid: str(o.encounter_id) });
    }
    map.forEach((l) => l.sort((a, z) => a.t - z.t));
    return map;
  }, [b, dx]);
  const seriesFor = (s: Series) => {
    const key = [...byName.keys()].find((k) => s.re.test(k));
    return (key ? byName.get(key)! : []).filter((p) => p.t >= from);
  };

  const inWindow = b.encounters.filter((e) => {
    const t = parseDate(str(e.start))?.getTime() ?? 0;
    return t >= from && t <= dx;
  });
  const acute = inWindow.filter((e) => VISIT_CLASS[str(e.encounter_class) ?? '']?.row === 2).length;
  const cost = d3.sum(inWindow, (e) => num(e.total_cost) ?? 0);
  const lastVisit = [...b.encounters].reverse().find((e) => (parseDate(str(e.start))?.getTime() ?? Infinity) <= dx);
  const years = Math.round((dx - from) / YEAR);

  return (
    <div>
      <div className="sec-head">
        <h2 className="sec-title">Measurements before diagnosis</h2>
        <span className="syn-tag">synthetic, Synthea</span>
        <div className="seg ml-auto" role="group" aria-label="Period">
          {WINDOWS.map(([id, label]) => (
            <button key={id} aria-pressed={range === id} onClick={() => setRange(id)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <Block
        title="Measurements"
        note={`${fmtDate(new Date(from).toISOString())} to diagnosis, ${years} years · shaded band is the usual adult range · the selected visit is marked; hover to compare dates, click a point to open that visit`}
      >
        <div className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
          {MEASURES.map((m) => (
            <TrendChart
              key={m.id}
              m={m}
              series={m.series.map(seriesFor)}
              from={from}
              to={dx}
              adultFrom={adultFrom}
              hover={hover}
              pinned={pinned}
              onHover={setHover}
            />
          ))}
        </div>
      </Block>

      <div className="hair mt-8 grid gap-x-12 gap-y-8 border-t pt-6 xl:grid-cols-2">
        <Block title="Care contacts" note={`${fmtDate(new Date(from).toISOString())} to diagnosis`}>
          <VisitsChart encounters={b.encounters} from={from} to={dx} />
          <dl className="kv kv-tight mt-3 text-[12.5px]">
            <dt>Visits</dt>
            <dd className="num">
              {inWindow.length}
              {acute ? ` · ${acute} emergency or inpatient` : ''}
            </dd>
            <dt>Claims</dt>
            <dd className="num">{fmtMoney(cost)}</dd>
            <dt>Last visit</dt>
            <dd>
              {lastVisit ? (
                <Link onClick={() => openInTimeline({ id: `v:${str(lastVisit.encounter_id)}` })}>
                  {fmtDate(str(lastVisit.start))}, {term(str(lastVisit.description)).toLowerCase()}
                </Link>
              ) : (
                '–'
              )}
            </dd>
            <dt>Payer</dt>
            <dd>{str(lastVisit?.payer) === 'NO_INSURANCE' ? 'No insurance' : str(lastVisit?.payer) ?? '–'}</dd>
          </dl>
        </Block>

      </div>
    </div>
  );
}

/** Primary care at diagnosis: conditions, medications, allergies, lifestyle and immunisations (synthetic). */
export function PrimaryCareGlance({ b }: { b: PatientBundle }) {
  const dxDate = parseDate(str(b.patient.diagnosis_date))!;
  const dx = dxDate.getTime();
  const age = num(b.patient.age_at_diagnosis) ?? 0;
  const firstVisit = parseDate(str(b.encounters[0]?.start));
  const birth = new Date(Math.min(dx - age * YEAR - 180 * DAY, firstVisit?.getTime() ?? Infinity));
  const sex = str(b.patient.sex);
  const [showPast, setShowPast] = useState(false);

  const ageAtDx = (iso: string | null) => ageAt(parseDate(iso), birth);



  // Problem list: one row per condition; active at diagnosis first.
  const problems = useMemo(() => {
    const groups = d3.group(
      b.conditions.filter((c) => c.synthetic && parseDate(str(c.onset))),
      (c) => term(str(c.description))
    );
    return [...groups].map(([name, rows]) => {
      const onsets = rows.map((r) => parseDate(str(r.onset))!.getTime());
      const active = rows.some((r) => {
        const end = parseDate(str(r.resolved))?.getTime();
        return parseDate(str(r.onset))!.getTime() <= dx && (end === undefined || end > dx);
      });
      const resolved = d3.max(rows, (r) => parseDate(str(r.resolved))?.getTime() ?? 0) || null;
      const first = rows[onsets.indexOf(Math.min(...onsets))];
      return { name, rows, first: str(first.onset), firstEid: str(first.encounter_id), active, resolved, episodes: rows.length };
    });
  }, [b, dx]);
  const active = problems.filter((p) => p.active).sort((a, z) => String(a.first).localeCompare(String(z.first)));
  const past = problems.filter((p) => !p.active).sort((a, z) => (z.resolved ?? 0) - (a.resolved ?? 0));

  // Medicines being taken at diagnosis (not single doses given during a procedure).
  const meds = useMemo(() => {
    const current = b.medications.filter((m) => {
      if (/Injection|Injectable|Inhalation Solution/i.test(String(m.description))) return false;
      const s0 = parseDate(str(m.start))?.getTime();
      const e = parseDate(str(m.stop))?.getTime();
      return s0 !== undefined && s0 <= dx && (e === undefined || e >= dx - 30 * DAY);
    });
    const names = [...new Set(current.map((m) => medicine(str(m.description))))];
    return names.map((name) => {
      const all = b.medications.filter((m) => medicine(str(m.description)) === name);
      const latest = current.filter((m) => medicine(str(m.description)) === name).sort((a, z) => String(z.start).localeCompare(String(a.start)))[0];
      return {
        name,
        reason: term(str(latest.reason)),
        first: str(all[0].start),
        last: str(latest.start),
        scripts: all.length,
        eid: str(latest.encounter_id),
      };
    });
  }, [b, dx]);
  const otherMeds = new Set(b.medications.map((m) => medicine(str(m.description)))).size - meds.length;

  const shots = useMemo(() => {
    const g = d3.group(b.immunizations, (i) => term(str(i.description)));
    return [...g]
      .map(([name, rows]) => ({ name, doses: rows.length, last: d3.max(rows, (r) => str(r.date) ?? '') ?? null }))
      .sort((a, z) => String(z.last).localeCompare(String(a.last)));
  }, [b]);

  // Latest screening and social-history answers before diagnosis.
  const latest = useMemo(() => {
    const out = new Map<string, { value: string; date: string | null; reading: string | null }>();
    const rows = b.observations.filter((o) => o.synthetic && (parseDate(str(o.date))?.getTime() ?? Infinity) <= dx);
    for (const o of rows) {
      const def = describe(String(o.name), str(o.category));
      if (def.panel !== 'Screening' && def.panel !== 'Social needs') continue;
      const v = num(o.value);
      const value =
        def.name === 'Household income'
          ? fmtMoney(v ?? num(o.value_text)) || (str(o.value_text) ?? '')
          : str(o.value_text) ?? (v !== null ? fmtNum(v, 0) : '');
      out.set(def.name, { value, date: str(o.date), reading: interpretScore(def.name, v, sex) });
    }
    return out;
  }, [b, dx, sex]);
  const lifestyle: [string, string][] = [
    ['Tobacco', 'Tobacco'],
    ['Alcohol (AUDIT-C)', 'AUDIT-C alcohol score'],
    ['Drug use (DAST-10)', 'DAST-10 drug use score'],
    ['Depression (PHQ-2)', 'PHQ-2 depression screen'],
    ['Depression (PHQ-9)', 'PHQ-9 depression score'],
    ['Anxiety (GAD-7)', 'GAD-7 anxiety score'],
    ['Partner violence (HARK)', 'HARK partner-violence screen'],
    ['Employment', 'Employment'],
    ['Education', 'Education'],
    ['Housing', 'Housing'],
    ['Household income', 'Household income'],
    ['Insurance', 'Insurance'],
    ['Stress', 'Stress'],
  ];

  const realConditions = b.conditions.filter((c) => !c.synthetic);


  return (
    <div>
      <div className="sec-head">
        <h2 className="sec-title">Primary care at diagnosis</h2>
        <span className="syn-tag">synthetic, Synthea</span>
      </div>
      <p className="t-muted -mt-1 mb-5 max-w-[110ch] text-[12.5px]">
        TCGA holds no routine care records. This record is generated (Synthea) to match the patient's sex and age, ends on
        the day of cancer diagnosis ({fmtDate(str(b.patient.diagnosis_date))}), and is calibrated to the real height and
        weight. Use it to show what a full record looks like, not for research on these patients.
      </p>
      {realConditions.length > 0 && (
        <div className="mb-5 text-[13px]">
          <span className="t-label mr-2">Recorded by the treating site (real)</span>
          {realConditions.map((c) => str(c.description)).join(' · ')}
        </div>
      )}

      <div className="hair mt-8 grid gap-x-12 gap-y-8 border-t pt-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <Block title="Problem list (conditions)" note={`${active.length} active at diagnosis · ${past.length} resolved`}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Condition</th>
                <th>First recorded</th>
                <th>Age</th>
                <th>Status at diagnosis</th>
                <th className="text-right">Episodes</th>
              </tr>
            </thead>
            <tbody>
              {[...active, ...(showPast ? past : [])].map((p) => (
                <tr key={p.name}>
                  <td>
                    <Link onClick={() => openInTimeline({ kind: 'condition', title: p.name, at: p.first, fallback: p.firstEid ? `v:${p.firstEid}` : undefined })}>
                      {p.name}
                    </Link>
                  </td>
                  <td className="num whitespace-nowrap">{fmtDate(p.first)}</td>
                  <td className="num">{ageAtDx(p.first)}</td>
                  <td style={{ color: p.active ? 'var(--ink)' : 'var(--ink-3)' }}>
                    {p.active ? 'Active' : p.resolved ? `Resolved ${fmtMonth(new Date(p.resolved).toISOString())}` : 'Resolved'}
                  </td>
                  <td className="num text-right">{p.episodes}</td>
                </tr>
              ))}
              {!active.length && !showPast && (
                <tr>
                  <td colSpan={5} className="t-faint">
                    No active problems at diagnosis.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {past.length > 0 && (
            <button className="link t-muted mt-2 text-[12px]" onClick={() => setShowPast((v) => !v)}>
              {showPast ? 'Hide resolved problems' : `Show ${past.length} resolved problems`}
            </button>
          )}
        </Block>

        <Block title="Medications at diagnosis" note={otherMeds > 0 ? `${otherMeds} other medications earlier in the record` : undefined}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Medication</th>
                <th>For</th>
                <th>First prescribed</th>
                <th className="text-right">Scripts</th>
              </tr>
            </thead>
            <tbody>
              {meds.map((m) => (
                <tr key={m.name}>
                  <td>
                    <Link onClick={() => openInTimeline({ kind: 'medication', title: m.name, at: m.last, fallback: m.eid ? `v:${m.eid}` : undefined })}>
                      {m.name}
                    </Link>
                  </td>
                  <td className="t-muted">{m.reason || '–'}</td>
                  <td className="num whitespace-nowrap">{fmtMonth(m.first)}</td>
                  <td className="num text-right">{m.scripts}</td>
                </tr>
              ))}
              {!meds.length && (
                <tr>
                  <td colSpan={4} className="t-faint">
                    No regular medications at diagnosis.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <div className="mt-6">
            <Block title="Allergies and intolerances">
              {b.allergies.length ? (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Allergen</th>
                      <th>Type</th>
                      <th>Reaction</th>
                      <th>Severity</th>
                      <th>Since</th>
                    </tr>
                  </thead>
                  <tbody>
                    {b.allergies.map((a, i) => (
                      <tr key={i}>
                        <td>{term(str(a.description))}</td>
                        <td className="t-muted">{str(a.category) ?? '–'}</td>
                        <td>{term(str(a.reaction)) || '–'}</td>
                        <td>{str(a.severity)?.toLowerCase() ?? '–'}</td>
                        <td className="num">{fmtMonth(str(a.onset))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="text-[13px]">No known allergies recorded.</div>
              )}
            </Block>
          </div>
        </Block>
      </div>

      <div className="hair mt-8 grid gap-x-12 gap-y-8 border-t pt-6 xl:grid-cols-2">
        <Block title="Lifestyle and screening" note="latest answer before diagnosis">
          <table className="tbl">
            <tbody>
              {lifestyle.map(([label, key]) => {
                const v = latest.get(key);
                if (!v) return null;
                return (
                  <tr key={key}>
                    <td className="t-muted whitespace-nowrap">{label}</td>
                    <td>
                      {v.value}
                      {v.reading && (
                        <span style={{ color: v.reading === 'positive screen' ? 'var(--c-alert)' : 'var(--ink-3)' }}> · {v.reading}</span>
                      )}
                    </td>
                    <td className="t-faint num whitespace-nowrap text-right">{fmtMonth(v.date)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Block>

        <Block title="Immunisations" note={`${b.immunizations.length} doses in the record`}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Immunisation</th>
                <th className="text-right">Doses</th>
                <th className="text-right">Last given</th>
              </tr>
            </thead>
            <tbody>
              {shots.slice(0, 12).map((s) => (
                <tr key={s.name}>
                  <td>
                    <Link onClick={() => openInTimeline({ id: `i:${s.last}` })}>{s.name}</Link>
                  </td>
                  <td className="num text-right">{s.doses}</td>
                  <td className="num whitespace-nowrap text-right">{fmtMonth(s.last)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Block>
      </div>
    </div>
  );
}
