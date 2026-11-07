import * as d3 from 'd3';
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Minus, PanelLeft, PanelTop, Plus } from 'lucide-react';
import { memo, startTransition, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import type { Note } from '@/hooks/useNotes';
import { num, str, type PatientBundle, type Row } from '@/lib/api';
import { bodySystem, CLASS_STYLE, drugClass, medicine, SYSTEMS, term, VISIT_CLASS } from '@/lib/clinical';
import { fmtDate, fmtDay, parseDate, plain } from '@/lib/format';

export type LaneId = 'visits' | 'problems' | 'cancer' | 'diagnostics' | 'notes';
export type MarkKind =
  | 'visit'
  | 'condition'
  | 'medication'
  | 'vaccine'
  | 'diagnosis'
  | 'spread'
  | 'status'
  | 'outcome'
  | 'surgery'
  | 'radiation'
  | 'drug'
  | 'scan'
  | 'slide'
  | 'genome'
  | 'tests'
  | 'report'
  | 'note';
type Shape = 'tick' | 'dot' | 'ring' | 'diamond' | 'tri' | 'cross' | 'square' | 'bar';

export interface Mark {
  id: string;
  kind: MarkKind;
  lane: LaneId;
  row: number;
  start: Date;
  end?: Date;
  shape: Shape;
  colour: string;
  outline?: boolean;
  faded?: boolean;
  big?: boolean;
  /** A condition: drawn as a translucent band the width of its row. */
  band?: boolean;
  /** A medicine inside its condition's band: a thin solid bar. */
  inset?: boolean;
  /** Written on the chart at the start of the mark. */
  label?: string;
  title: string;
  lines: string[];
  synthetic?: boolean;
  /** The source rows behind the mark, for the detail panel. */
  rows: Row[];
}

export interface Lane {
  id: LaneId;
  label: string;
  note?: string;
  /** Natural size of each row across the time axis, in pixels. */
  sizes: number[];
  /** Short names for rows that carry no label of their own. */
  rowNames?: (string | null)[];
  synthetic?: boolean;
}

type Tip = { x: number; y: number; mark: Mark };

const DAY = 86_400_000;
const YEAR = 365.25 * DAY;
const MAX_CONDITIONS = 6;
const MAX_OTHER_MEDS = 3;
const VISIT_COLOUR = ['var(--ink-2)', 'var(--ink)', 'var(--c-alert)'];

function addDays(d: Date, n: number): Date {
  return new Date(d.getTime() + n * DAY);
}

/** Groups occurrences of the same item into continuous spans (gaps up to `gapDays` are bridged). */
function spans(rows: { start: Date; end: Date; row: Row }[], gapDays: number) {
  const sorted = [...rows].sort((a, z) => a.start.getTime() - z.start.getTime());
  const out: { start: Date; end: Date; rows: Row[] }[] = [];
  for (const r of sorted) {
    const last = out[out.length - 1];
    if (last && r.start.getTime() - last.end.getTime() <= gapDays * DAY) {
      if (r.end > last.end) last.end = r.end;
      last.rows.push(r.row);
    } else {
      out.push({ start: r.start, end: r.end, rows: [r.row] });
    }
  }
  return out;
}

export function buildModel(b: PatientBundle) {
  const p = b.patient;
  const dx = parseDate(str(p.diagnosis_date))!;
  const last = parseDate(str(p.last_contact_date)) ?? addDays(dx, num(p.days_to_last_contact) ?? 0);
  const firstVisit = d3.min(b.encounters, (e) => parseDate(str(e.start)) ?? undefined);
  const computedBirth = addDays(dx, -(num(p.age_at_diagnosis) ?? 60) * 365.25 - 180);
  const birth = firstVisit && firstVisit < computedBirth ? firstVisit : computedBirth;
  const dayLine = (d: Date) => `${fmtDate(d.toISOString())} · ${fmtDay(Math.round((d.getTime() - dx.getTime()) / DAY))}`;
  const marks: Mark[] = [];

  // ---- Lifetime: synthetic primary care -------------------------------------------------------
  for (const e of b.encounters) {
    const d = parseDate(str(e.start));
    if (!d) continue;
    const cls = VISIT_CLASS[str(e.encounter_class) ?? ''] ?? { label: 'Visit', row: 1 };
    const stop = parseDate(str(e.stop));
    const long = stop && stop.getTime() - d.getTime() >= 2 * DAY;
    marks.push({
      id: `v:${str(e.encounter_id)}`,
      kind: 'visit',
      lane: 'visits',
      row: cls.row,
      start: d,
      end: long ? stop! : undefined,
      shape: long ? 'bar' : 'tick',
      colour: VISIT_COLOUR[cls.row] ?? 'var(--ink-2)',
      synthetic: true,
      title: `${cls.label}: ${term(str(e.description))}`,
      lines: [dayLine(d), term(str(e.reason)), str(e.organization) ?? ''].filter(Boolean),
      rows: [e],
    });
  }

  for (const [date, rows] of d3.group(b.immunizations, (i) => str(i.date) ?? '')) {
    const d = parseDate(date);
    if (!d) continue;
    marks.push({
      id: `i:${date}`,
      kind: 'vaccine',
      lane: 'visits',
      row: 3,
      start: d,
      shape: 'dot',
      colour: 'var(--c-vax)',
      synthetic: true,
      title: rows.length === 1 ? term(str(rows[0].description)) : `${rows.length} immunisations`,
      lines: [dayLine(d), ...rows.slice(0, 4).map((r) => term(str(r.description)))],
      rows,
    });
  }

  // Problems: one row per long-term condition, coloured by body system, with the medicines that treat it drawn
  // inside the same row. Short illnesses share an "episodes" row and short courses of medicine a "courses" row.
  const condGroups = d3.group(
    b.conditions.filter((c) => c.synthetic && parseDate(str(c.onset))),
    (c) => term(str(c.description))
  );
  const chronic: { name: string; start: Date; end: Date; ongoing: boolean; rows: Row[] }[] = [];
  const episodes: { name: string; start: Date; end: Date | null; rows: Row[] }[] = [];
  for (const [name, rows] of condGroups) {
    const occ = rows.map((r) => ({ start: parseDate(str(r.onset))!, end: parseDate(str(r.resolved)), row: r }));
    const isChronic = occ.some((o) => !o.end || o.end.getTime() - o.start.getTime() >= 180 * DAY);
    if (isChronic) {
      const ongoing = occ.some((o) => !o.end);
      const start = d3.min(occ, (o) => o.start)!;
      const end = ongoing ? dx : d3.max(occ, (o) => o.end!)!;
      chronic.push({ name, start, end, ongoing, rows });
    } else {
      occ.forEach((o) => episodes.push({ name, start: o.start, end: o.end, rows }));
    }
  }
  const byLength = [...chronic].sort((a, z) => z.end.getTime() - z.start.getTime() - (a.end.getTime() - a.start.getTime()));
  const keptConditions = byLength.slice(0, MAX_CONDITIONS).sort((a, z) => a.start.getTime() - z.start.getTime());
  // Long-term conditions beyond the rows available are shown as episodes at their onset.
  for (const c of byLength.slice(MAX_CONDITIONS)) episodes.push({ name: c.name, start: c.start, end: c.ongoing ? null : c.end, rows: c.rows });
  const conditionRow = new Map(keptConditions.map((c, i) => [c.name, 2 + i]));
  episodes.forEach((o, i) =>
    marks.push({
      id: `ca:${o.name}:${i}`,
      kind: 'condition',
      lane: 'problems',
      row: 0,
      start: o.start,
      shape: 'dot',
      colour: SYSTEMS[bodySystem(o.name)].colour,
      synthetic: true,
      title: o.name,
      lines: [dayLine(o.start), o.end ? `resolved ${fmtDate(o.end.toISOString())}` : '', SYSTEMS[bodySystem(o.name)].label].filter(Boolean),
      rows: o.rows,
    })
  );

  const medGroups = d3.group(
    b.medications.filter((m) => parseDate(str(m.start))),
    (m) => medicine(str(m.description))
  );
  const rowMeds = new Map<number, string[]>();
  const otherMeds: { name: string; reason: string; spans: { start: Date; end: Date; rows: Row[] }[]; total: number }[] = [];
  const insetMeds: { name: string; reason: string; row: number; spans: { start: Date; end: Date; rows: Row[] }[] }[] = [];
  for (const [name, rows] of medGroups) {
    const reason = d3.greatest(d3.rollups(rows, (v) => v.length, (r) => term(str(r.reason))), ([, n]) => n)?.[0] ?? '';
    const colour = SYSTEMS[bodySystem(reason)].colour;
    const occ = rows.map((r) => {
      const start = parseDate(str(r.start))!;
      const stop = parseDate(str(r.stop));
      return { start, end: stop ?? dx, row: r };
    });
    const merged = spans(occ, 60);
    const longest = d3.max(merged, (x) => x.end.getTime() - x.start.getTime()) ?? 0;
    if (longest >= 90 * DAY && conditionRow.has(reason)) {
      insetMeds.push({ name, reason, row: conditionRow.get(reason)!, spans: merged });
      rowMeds.set(conditionRow.get(reason)!, [...(rowMeds.get(conditionRow.get(reason)!) ?? []), name]);
    } else if (longest >= 90 * DAY) {
      otherMeds.push({ name, reason, spans: merged, total: d3.sum(merged, (x) => x.end.getTime() - x.start.getTime()) });
    } else {
      occ.forEach((o, i) =>
        marks.push({
          id: `ma:${name}:${i}`,
          kind: 'medication',
          lane: 'problems',
          row: 1,
          start: o.start,
          shape: 'tick',
          colour,
          synthetic: true,
          title: name,
          lines: [dayLine(o.start), reason ? `for ${reason.toLowerCase()}` : ''].filter(Boolean),
          rows: rows,
        })
      );
    }
  }
  keptConditions.forEach((c) => {
    const row = conditionRow.get(c.name)!;
    const sys = SYSTEMS[bodySystem(c.name)];
    const meds = rowMeds.get(row) ?? [];
    marks.push({
      id: `c:${c.name}`,
      kind: 'condition',
      lane: 'problems',
      row,
      start: c.start,
      end: c.end,
      shape: 'bar',
      band: true,
      colour: sys.colour,
      synthetic: true,
      label: meds.length ? `${c.name} · ${meds.join(', ')}` : c.name,
      title: c.name,
      lines: [
        `Onset ${fmtDate(c.start.toISOString())}`,
        c.ongoing ? 'Ongoing at cancer diagnosis' : `Resolved ${fmtDate(c.end.toISOString())}`,
        sys.label,
        meds.length ? `Treated with ${meds.join(', ')}` : '',
      ].filter(Boolean),
      rows: c.rows,
    });
  });
  const pushMedSpans = (m: { name: string; reason: string; spans: { start: Date; end: Date; rows: Row[] }[] }, row: number, inset: boolean) =>
    m.spans.forEach((x, k) =>
      marks.push({
        id: `m:${m.name}:${k}`,
        kind: 'medication',
        lane: 'problems',
        row,
        start: x.start,
        end: x.end,
        shape: 'bar',
        inset,
        colour: SYSTEMS[bodySystem(m.reason)].colour,
        synthetic: true,
        label: !inset && k === 0 ? m.name : undefined,
        title: m.name,
        lines: [`${fmtDate(x.start.toISOString())} to ${fmtDate(x.end.toISOString())}`, m.reason ? `for ${m.reason.toLowerCase()}` : ''].filter(Boolean),
        rows: x.rows,
      })
    );
  insetMeds.forEach((m) => pushMedSpans(m, m.row, true));
  const keptOther = otherMeds.sort((a, z) => z.total - a.total).slice(0, MAX_OTHER_MEDS).sort((a, z) => a.spans[0].start.getTime() - z.spans[0].start.getTime());
  const otherBase = 2 + keptConditions.length;
  keptOther.forEach((m, i) => pushMedSpans(m, otherBase + i, false));
  // Any long-term medicine beyond the rows available is drawn as courses.
  otherMeds
    .filter((m) => !keptOther.includes(m))
    .forEach((m) =>
      m.spans.forEach((x, k) =>
        marks.push({
          id: `m:${m.name}:${k}`,
          kind: 'medication',
          lane: 'problems',
          row: 1,
          start: x.start,
          shape: 'tick',
          colour: SYSTEMS[bodySystem(m.reason)].colour,
          synthetic: true,
          title: m.name,
          lines: [`${fmtDate(x.start.toISOString())} to ${fmtDate(x.end.toISOString())}`, m.reason ? `for ${m.reason.toLowerCase()}` : ''].filter(Boolean),
          rows: x.rows,
        })
      )
    );

  // ---- Cancer course: real (TCGA) -------------------------------------------------------------
  marks.push({
    id: 'dx',
    kind: 'diagnosis',
    lane: 'cancer',
    row: 0,
    start: dx,
    shape: 'diamond',
    colour: 'var(--ink)',
    big: true,
    label: 'Diagnosis',
    title: `Diagnosis: ${str(p.cancer_type)}`,
    lines: [fmtDate(str(p.diagnosis_date)), [str(p.stage), plain(str(p.primary_diagnosis))].filter(Boolean).join(' · ')],
    rows: [p],
  });
  const seen = new Set<number>();
  b.diagnoses.forEach((d, i) => {
    const cls = str(d.classification);
    const day = num(d.day);
    if (!cls || day === null || !/metast|recurr/i.test(cls)) return;
    const date = addDays(dx, day);
    seen.add(day);
    marks.push({
      id: `s:${i}`,
      kind: 'spread',
      lane: 'cancer',
      row: 0,
      start: date,
      shape: 'tri',
      colour: 'var(--c-alert)',
      title: `${/metast/i.test(cls) ? 'Metastasis' : 'Recurrence'}${str(d.site) ? `: ${plain(str(d.site))}` : ''}`,
      lines: [dayLine(date), plain(str(d.primary_diagnosis))].filter(Boolean),
      rows: [d],
    });
  });
  b.followUps.forEach((f, i) => {
    const pday = num(f.days_to_progression);
    if (str(f.progression) === 'Yes' && pday !== null && !seen.has(pday)) {
      seen.add(pday);
      const date = addDays(dx, pday);
      marks.push({
        id: `p:${i}`,
        kind: 'spread',
        lane: 'cancer',
        row: 0,
        start: date,
        shape: 'tri',
        colour: 'var(--c-alert)',
        title: `${str(f.progression_type) ?? ''} progression${str(f.progression_site) ? `: ${plain(str(f.progression_site))}` : ''}`.trim(),
        lines: [dayLine(date), str(f.evidence) ?? ''].filter(Boolean),
        rows: [f],
      });
    }
    const resp = str(f.disease_response);
    const fd = num(f.day);
    if (resp && fd !== null) {
      const free = resp.startsWith('TF');
      const date = addDays(dx, fd);
      marks.push({
        id: `f:${i}`,
        kind: 'status',
        lane: 'cancer',
        row: 0,
        start: date,
        shape: free ? 'ring' : 'dot',
        colour: free ? 'var(--c-good)' : 'var(--ink-3)',
        title: free ? 'Tumour free' : 'With tumour',
        lines: [dayLine(date), str(f.timepoint) ?? 'Follow-up'],
        rows: [f],
      });
    }
  });
  const died = str(p.vital_status) === 'Dead' && parseDate(str(p.death_date));
  marks.push({
    id: 'end',
    kind: 'outcome',
    lane: 'cancer',
    row: 0,
    start: died ? parseDate(str(p.death_date))! : last,
    shape: died ? 'cross' : 'square',
    colour: died ? 'var(--c-alert)' : 'var(--ink)',
    big: !!died,
    label: died ? 'Died' : 'Last contact',
    title: died ? 'Died' : 'Last contact, alive',
    lines: [dayLine(died ? parseDate(str(p.death_date))! : last), str(p.cause_of_death) ?? ''].filter(Boolean),
    rows: [p],
  });

  const agents: string[] = [];
  b.treatments.forEach((t, idx) => {
    if (!t.given) return;
    const type = str(t.treatment_type) ?? '';
    const start = parseDate(str(t.start_date));
    if (!start) return;
    const agent = str(t.agent);
    if (/surgery|radiation|brachy|ablation|transplant|embolization/i.test(type)) {
      const end = parseDate(str(t.end_date));
      const radiation = /radiation|brachy/i.test(type);
      const dose =
        num(t.dose) && str(t.dose_units)
          ? `${num(t.dose)} ${str(t.dose_units)}${num(t.fractions) ? ` in ${num(t.fractions)} fractions` : ''}`
          : '';
      marks.push({
        id: `t:${idx}`,
        kind: radiation ? 'radiation' : 'surgery',
        lane: 'cancer',
        row: 1,
        start,
        end: radiation && end ? end : undefined,
        shape: radiation ? 'bar' : 'square',
        colour: radiation ? 'var(--c-path)' : 'var(--ink)',
        outline: radiation,
        label: radiation ? undefined : plain(type).replace(/, Open/, ''),
        title: plain(type),
        lines: [dayLine(start), dose, str(t.anatomic_site) ?? '', str(t.outcome) ?? ''].filter(Boolean),
        rows: [t],
      });
      return;
    }
    if (!agent) return;
    const name = agent.replace(/ Hydrochloride| Malate| Mesylate/g, '');
    let row = agents.indexOf(name);
    if (row < 0) {
      agents.push(name);
      row = agents.length - 1;
    }
    const cls = drugClass(agent, type);
    const ongoing = str(t.outcome) === 'Treatment Ongoing';
    let end = parseDate(str(t.end_date));
    // Continuous oral or hormonal therapy marked ongoing runs to last contact; cytotoxic courses without an
    // end date are drawn as 12 weeks, faded, and say so.
    const openEnded = !end;
    if (!end) end = ongoing && cls !== 'chemo' ? last : addDays(start, 84);
    if (end.getTime() - start.getTime() < 5 * DAY) end = addDays(start, 5);
    marks.push({
      id: `t:${idx}`,
      kind: 'drug',
      lane: 'cancer',
      row: 2 + row,
      start,
      end,
      shape: 'bar',
      colour: CLASS_STYLE[cls].fill,
      outline: cls === 'hormone',
      faded: openEnded && !(ongoing && cls !== 'chemo'),
      label: name,
      title: `${name} · ${CLASS_STYLE[cls].label}`,
      lines: [
        `${fmtDate(start.toISOString())} to ${
          str(t.end_date) ? fmtDate(str(t.end_date)) : ongoing && cls !== 'chemo' ? 'ongoing at last contact' : 'end date not recorded'
        }`,
        str(t.outcome) ? `Response: ${str(t.outcome)}` : '',
      ].filter(Boolean),
      rows: [t],
    });
  });

  for (const s of b.radiologyStudies) {
    const d = parseDate(str(s.date));
    if (!d) continue;
    const series = b.radiologySeries.find((r) => r.study_uid === s.study_uid);
    marks.push({
      id: `r:${str(s.study_uid)}`,
      kind: 'scan',
      lane: 'diagnostics',
      row: 0,
      start: d,
      shape: 'square',
      colour: 'var(--c-rad)',
      big: !!series,
      outline: !series,
      title: `${str(s.modalities)} ${str(s.body_part)?.toLowerCase() ?? ''}`.trim(),
      lines: [dayLine(d), `${num(s.series_count)} series, ${num(s.images)} images`, series ? 'In the viewer' : 'Metadata only'],
      rows: series ? [s, series] : [s],
    });
  }
  const slides = b.slides?.length ? b.slides : b.slide ? [b.slide] : [];
  for (const sl of slides) {
    const diagnostic = sl.role !== 'frozen';
    const d = num(sl.day) !== null ? addDays(dx, num(sl.day)!) : parseDate(str(sl.date)) ?? dx;
    marks.push({
      // The diagnostic slide keeps the id `slide`; links elsewhere open it by that id.
      id: diagnostic && sl === (b.slide ?? slides[0]) ? 'slide' : `sl:${str(sl.slide_id)}`,
      kind: 'slide',
      lane: 'diagnostics',
      row: 1,
      start: d,
      shape: 'square',
      colour: 'var(--c-path)',
      big: diagnostic,
      outline: !diagnostic,
      label: diagnostic ? 'H&E slide' : undefined,
      title: diagnostic
        ? 'Diagnostic H&E slide'
        : `Frozen section ${str(sl.section) ?? ''}, ${/normal/i.test(str(sl.sample_type) ?? '') ? 'normal tissue' : 'tumour'}`.replace(' ,', ','),
      lines: [dayLine(d), str(sl.barcode) ?? '', str(sl.specimen) ?? ''].filter(Boolean),
      rows: [sl],
    });
  }
  if (b.report.text || b.report.pdfPath) {
    marks.push({
      id: 'report',
      kind: 'report',
      lane: 'diagnostics',
      row: 2,
      start: dx,
      shape: 'square',
      colour: 'var(--ink-2)',
      outline: true,
      title: 'Surgical pathology report',
      lines: [fmtDate(str(p.diagnosis_date)), b.report.pdfPath ? 'Scanned PDF and OCR text' : 'OCR text'],
      rows: [p],
    });
  }
  if (b.profile) {
    marks.push({
      id: 'genome',
      kind: 'genome',
      lane: 'diagnostics',
      row: 4,
      start: dx,
      shape: 'dot',
      colour: 'var(--c-gen)',
      big: true,
      label: 'Tumour sequenced',
      title: 'Tumour genome',
      lines: ['Whole-exome sequencing, copy number and RNA', 'Same tumour sample as the slide'],
      rows: [b.profile],
    });
  }
  const tests = [...b.biomarkers, ...b.observations.filter((o) => o.source === 'TCGA')];
  for (const [day, rows] of d3.group(tests, (t) => num(t.day) ?? 0)) {
    const d = addDays(dx, day);
    marks.push({
      id: `b:${day}`,
      kind: 'tests',
      lane: 'diagnostics',
      row: 3,
      start: d,
      shape: 'square',
      colour: 'var(--ink-2)',
      outline: true,
      title: `${rows.length} ${rows.length === 1 ? 'test' : 'tests'}${day === 0 ? ' at diagnosis' : ''}`,
      lines: [dayLine(d), ...rows.slice(0, 4).map((r) => str(r.test) ?? str(r.name) ?? '')],
      rows,
    });
  }

  const lanes: Lane[] = [
    { id: 'visits', label: 'Visits', note: 'synthetic', sizes: [9, 9, 9, 10], rowNames: ['wellness', 'office', 'emergency, inpatient', 'immunisations'], synthetic: true },
    {
      id: 'problems',
      label: 'Conditions and medications',
      note: 'synthetic',
      sizes: [11, 9, ...keptConditions.map(() => 17), ...keptOther.map(() => 14)],
      rowNames: ['acute conditions', 'short courses', ...keptConditions.map(() => null), ...keptOther.map(() => null)],
      synthetic: true,
    },
    {
      id: 'cancer',
      label: 'Cancer course and treatment',
      note: 'real, TCGA',
      sizes: [20, 14, ...(agents.length ? agents : ['']).map(() => 15)],
      rowNames: ['cancer course', 'surgery, radiotherapy', ...(agents.length ? agents.map(() => null) : ['systemic therapy'])],
    },
    { id: 'diagnostics', label: 'Pathology, radiology and tests', note: 'real, TCGA', sizes: [12, 12, 11, 11, 11], rowNames: ['radiology', 'pathology', 'report', 'tests', 'genomics'] },
    { id: 'notes', label: 'Tumour board', sizes: [20], rowNames: [null] },
  ];
  return { marks, lanes, dx, last, birth };
}

/** Year or month ticks for one segment of the axis, spaced at least `minPx` apart. */
function segmentTicks(from: Date, to: Date, px: number, minPx = 54): { date: Date; label: string }[] {
  const span = to.getTime() - from.getTime();
  if (span <= 0 || px <= 0) return [];
  const years = span / YEAR;
  if (years > 4 || px / (span / (30.44 * DAY)) < minPx / 6) {
    const step = [1, 2, 5, 10, 20, 50].find((s) => px / (years / s) >= minPx) ?? 50;
    return (d3.utcYear.every(step)?.range(from, to) ?? []).map((d) => ({ date: d, label: d3.utcFormat('%Y')(d) }));
  }
  const months = span / (30.44 * DAY);
  const step = [1, 2, 3, 6, 12].find((s) => px / (months / s) >= minPx + 16) ?? 12;
  return (d3.utcMonth.every(step)?.range(from, to) ?? []).map((d) => ({ date: d, label: d3.utcFormat('%b %Y')(d) }));
}

function ageTicks(birth: Date, from: Date, to: Date, px: number, minPx = 40): number[] {
  const years = (to.getTime() - from.getTime()) / YEAR;
  if (years <= 0) return [];
  const step = [1, 2, 5, 10, 20].find((s) => px / (years / s) >= minPx) ?? 20;
  const a0 = Math.ceil((from.getTime() - birth.getTime()) / YEAR / step) * step;
  const out: number[] = [];
  for (let a = Math.max(0, a0); birth.getTime() + a * YEAR <= to.getTime(); a += step) out.push(a);
  return out;
}

export interface Model {
  marks: Mark[];
  lanes: Lane[];
  dx: Date;
  last: Date;
  birth: Date;
}
/** One mark per tumour board note, at the event the note is about (or at diagnosis when it is about the case). */
export function noteMarks(notes: Note[], marks: Mark[], dx: Date): Mark[] {
  const byId = new Map(marks.map((m) => [m.id, m]));
  return notes.map((n) => {
    const about = n.eventId ? byId.get(n.eventId) : undefined;
    const body = n.body.length > 110 ? `${n.body.slice(0, 108)}…` : n.body;
    return {
      id: `n:${n.id}`,
      kind: 'note',
      lane: 'notes',
      row: 0,
      start: about?.start ?? dx,
      shape: 'dot',
      colour: 'var(--accent)',
      title: `Note by ${n.authorName}`,
      lines: [about ? `About: ${about.title}` : 'About the case', body],
      rows: [],
    } satisfies Mark;
  });
}

/* ================================================================== lifetime timeline, vertical or horizontal */

export type Orientation = 'left' | 'top';

const ANIM_MS = 320;
/** Lane names in the collapsed strip. */
const STRIP_NAME: Record<LaneId, string> = {
  visits: 'Visits',
  problems: 'Conditions, meds',
  cancer: 'Cancer',
  diagnostics: 'Pathology/radiology',
  notes: 'Tumour board',
};
const LANE_PAD = 4;
const LANE_GAP = 8;
const MINI = 22;
const MIN_LANE = 22;
const SIZES_KEY = 'p360.laneSizes';

type TFn = ((d: Date) => number) & { invert: (p: number) => Date };

function ease(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

function readSizes(): Partial<Record<LaneId, number>> {
  try {
    return JSON.parse(localStorage.getItem(SIZES_KEY) ?? '{}') as Partial<Record<LaneId, number>>;
  } catch {
    return {};
  }
}

/**
 * The patient's whole life as one timeline, across the top of the record or down its left. Time runs from birth
 * to last contact or death; life before diagnosis is compressed and the cancer course expanded. Five lanes: visits;
 * conditions and medications (by body system, each medication in the row of the condition it treats); cancer course
 * and treatment; pathology, radiology and tests; tumour board notes. Each lane's share of the space can be changed
 * (drag the divider beside its name, or double-click the name). Collapsed, it becomes a strip with one thin row
 * per lane that still shows and selects events. Zoom is a window `{f0, f1}` of fractions over the base scale.
 * Positions are computed on a time axis and a cross axis, then mapped to x and y for the orientation.
 */
export function LifeTimeline({
  model,
  selected,
  onSelect,
  lens,
  orientation,
  onOrientation,
  collapsed,
  onCollapsed,
  controlsHost,
  showCollapse = true,
}: {
  model: Model;
  selected: string | null;
  /** `stepping` is true while the date picker is dragged (the record replaces history instead of adding to it). */
  onSelect: (id: string, stepping?: boolean) => void;
  /** Kinds belonging to the open tab; other marks are faded. Empty for no emphasis. */
  lens: Set<MarkKind>;
  orientation: Orientation;
  onOrientation: (o: Orientation) => void;
  collapsed: boolean;
  onCollapsed: (c: boolean) => void;
  /** Where to draw the controls (zoom, layout, key, collapse): the record's header. */
  controlsHost?: HTMLElement | null;
  /** Draw the collapse button with the controls (the record puts it on the section rule instead). */
  showCollapse?: boolean;
}) {
  const vertical = orientation === 'left';
  const clipId = useId().replace(/:/g, '');
  const wrapRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ w: 900, h: 400 });
  const [zoom, setZoom] = useState<{ f0: number; f1: number } | null>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const [hover, setHover] = useState<{ t: number; c: number } | null>(null);
  const [brush, setBrush] = useState<{ a: number; b: number } | null>(null);
  const [keyOpen, setKeyOpen] = useState(false);
  const [mults, setMults] = useState<Partial<Record<LaneId, number>>>(readSizes);
  const dragRef = useRef<{ a: number; moved: boolean } | null>(null);
  const { marks, lanes, dx, last, birth } = model;
  const byId = useMemo(() => new Map(marks.map((m) => [m.id, m])), [marks]);
  useEffect(() => localStorage.setItem(SIZES_KEY, JSON.stringify(mults)), [mults]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: Math.max(40, e.contentRect.width), h: Math.max(40, e.contentRect.height) }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const { w, h } = size;

  // Gutters. Expanded: controls in the top-left corner; lane names on the left (top) or headings above (left); age
  // and year along the axis. Collapsed: controls at the start, one thin row per lane.
  const G = collapsed
    ? vertical
      ? { t0: 8, t1: h - 8, c0: 6, c1: w - 6 }
      : { t0: 118, t1: w - 12, c0: 23, c1: h - 3 }
    : vertical
      ? { t0: 104, t1: h - 10, c0: 86, c1: w - (zoom ? MINI + 6 : 8) }
      : { t0: 150, t1: w - 14, c0: 50, c1: h - (zoom ? MINI + 8 : 10) };
  const tLen = Math.max(10, G.t1 - G.t0);
  const cAvail = Math.max(10, G.c1 - G.c0);

  const { split, end } = useMemo(() => {
    const cancer = marks.filter((m) => !m.synthetic && m.kind !== 'note');
    const first = d3.min(cancer, (m) => m.start) ?? dx;
    const lastEvent = d3.max(marks, (m) => m.end ?? m.start) ?? last;
    return {
      split: addDays(new Date(Math.min(first.getTime(), dx.getTime())), -45),
      end: addDays(new Date(Math.max(last.getTime(), lastEvent.getTime())), 30),
    };
  }, [marks, dx, last]);

  const base = useMemo(
    () => d3.scaleUtc().domain([birth, split, end]).range([G.t0, G.t0 + tLen * 0.6, G.t1]),
    [birth, split, end, G.t0, G.t1, tLen]
  );

  const f0 = zoom?.f0 ?? 0;
  const f1 = zoom?.f1 ?? 1;
  const target: TFn = useMemo(() => {
    const k = 1 / (f1 - f0);
    const fn = ((d: Date) => G.t0 + ((base(d) - G.t0) / tLen - f0) * k * tLen) as TFn;
    fn.invert = (p: number) => base.invert(G.t0 + (f0 + ((p - G.t0) / tLen) * (f1 - f0)) * tLen);
    return fn;
  }, [base, f0, f1, G.t0, tLen]);

  // Zoom changes made with buttons glide from the old scale to the new one.
  const shownRef = useRef<TFn>(target);
  const [anim, setAnim] = useState<{ from: TFn; t0: number } | null>(null);
  const [, setFrame] = useState(0);
  const glide = useCallback(() => setAnim({ from: shownRef.current, t0: performance.now() }), []);
  useEffect(() => {
    if (!anim) return;
    let raf = 0;
    const tick = () => {
      if (performance.now() - anim.t0 >= ANIM_MS) return setAnim(null);
      setFrame((n) => n + 1);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    // Background tabs get no animation frames; finish the glide anyway.
    const done = window.setTimeout(() => setAnim(null), ANIM_MS + 60);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(done);
    };
  }, [anim]);
  const prog = anim ? ease(Math.min(1, (performance.now() - anim.t0) / ANIM_MS)) : 1;
  const T: TFn = useMemo(() => {
    if (!anim || prog >= 1) return target;
    const from = anim.from;
    const fn = ((d: Date) => from(d) + (target(d) - from(d)) * prog) as TFn;
    fn.invert = target.invert;
    return fn;
  }, [anim, prog, target]);
  shownRef.current = T;
  useEffect(() => glide(), [orientation]); // eslint-disable-line react-hooks/exhaustive-deps

  const domain: [Date, Date] = useMemo(() => [target.invert(G.t0), target.invert(G.t1)], [target, G.t0, G.t1]);
  const zoomFactor = 1 / (f1 - f0);
  const maxZoom = 160;

  const zoomTo = useCallback(
    (z: number, anchor = 0.5, animate = false) => {
      const k = Math.max(1, Math.min(maxZoom, z));
      if (animate) glide();
      if (k <= 1.001) return setZoom(null);
      const at = f0 + anchor * (f1 - f0);
      const span = 1 / k;
      const a = Math.max(0, Math.min(1 - span, at - anchor * span));
      setZoom({ f0: a, f1: a + span });
    },
    [f0, f1, glide]
  );
  const panTo = useCallback(
    (start: number) => {
      if (!zoom) return;
      const span = zoom.f1 - zoom.f0;
      const a = Math.max(0, Math.min(1 - span, start));
      setZoom({ f0: a, f1: a + span });
    },
    [zoom]
  );

  // Cross axis: each lane gets a share of the space from its rows' natural sizes times the user's size for it.
  const layout = useMemo(() => {
    const gaps = LANE_GAP * (lanes.length - 1);
    const out: Record<string, { c0: number; c1: number; rows: { c: number; size: number }[] }> = {};
    if (collapsed) {
      const each = (cAvail - 2 * (lanes.length - 1)) / lanes.length;
      lanes.forEach((l, i) => {
        const c0 = G.c0 + i * (each + 2);
        out[l.id] = { c0, c1: c0 + each, rows: l.sizes.map(() => ({ c: c0 + each / 2, size: each })) };
      });
      return out;
    }
    const natural = lanes.map((l) => (d3.sum(l.sizes) + LANE_PAD * 2) * (mults[l.id] ?? 1));
    const k = Math.max(0, cAvail - gaps) / d3.sum(natural);
    let c = G.c0;
    lanes.forEach((l, i) => {
      const len = Math.max(0, natural[i] * k);
      const inner = Math.max(0, len - LANE_PAD * 2);
      const total = d3.sum(l.sizes);
      let rc = c + LANE_PAD;
      const rows = l.sizes.map((sz) => {
        const r = { c: rc + ((sz / total) * inner) / 2, size: (sz / total) * inner };
        rc += (sz / total) * inner;
        return r;
      });
      out[l.id] = { c0: c, c1: c + len, rows };
      c += len + LANE_GAP;
    });
    return out;
  }, [lanes, cAvail, G.c0, mults, collapsed]);
  const rowOf = (m: Mark) => layout[m.lane].rows[Math.min(m.row, layout[m.lane].rows.length - 1)];

  // Resize a lane by dragging the divider after it (in the lane-name gutter); the next lane gives or takes the space.
  const laneDrag = useRef<{ i: number; at: number; a: number; b: number; ma: number; mb: number } | null>(null);
  const startLaneDrag = (i: number, e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    const A = layout[lanes[i].id];
    const B = layout[lanes[i + 1].id];
    laneDrag.current = {
      i,
      at: vertical ? e.clientX : e.clientY,
      a: A.c1 - A.c0,
      b: B.c1 - B.c0,
      ma: mults[lanes[i].id] ?? 1,
      mb: mults[lanes[i + 1].id] ?? 1,
    };
    const move = (ev: PointerEvent) => {
      const d = laneDrag.current;
      if (!d) return;
      const delta = (vertical ? ev.clientX : ev.clientY) - d.at;
      const a = Math.max(MIN_LANE, Math.min(d.a + d.b - MIN_LANE, d.a + delta));
      const b = d.a + d.b - a;
      setMults((m) => ({ ...m, [lanes[d.i].id]: (d.ma * a) / d.a, [lanes[d.i + 1].id]: (d.mb * b) / d.b }));
    };
    const up = () => {
      laneDrag.current = null;
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  /** Double-click a lane's name: give it most of the room; again to share it out evenly. */
  const focusLane = (id: LaneId) => {
    const base0 = lanes.map((l) => d3.sum(l.sizes) + LANE_PAD * 2);
    const i = lanes.findIndex((l) => l.id === id);
    const L = layout[id];
    if ((L.c1 - L.c0) / cAvail > 0.5) return setMults({});
    const rest = d3.sum(base0) - base0[i];
    setMults({ [id]: (0.58 * rest) / (0.42 * base0[i]) });
  };

  // Map a (time, cross) position to the screen.
  const X = (t: number, c: number) => (vertical ? c : t);
  const Y = (t: number, c: number) => (vertical ? t : c);
  const along = (t1: number, t2: number, c0: number, thick: number) =>
    vertical
      ? { x: c0, y: t1, width: Math.max(0, thick), height: Math.max(0, t2 - t1) }
      : { x: t1, y: c0, width: Math.max(0, t2 - t1), height: Math.max(0, thick) };

  const visible = useMemo(() => marks.filter((m) => (m.end ?? m.start) >= domain[0] && m.start <= domain[1]), [marks, domain]);
  const lensOn = lens.size > 0;
  const lensLanes = useMemo(() => new Set(marks.filter((m) => lens.has(m.kind)).map((m) => m.lane)), [marks, lens]);
  const dim = (m: Mark) => lensOn && !lens.has(m.kind);

  // Ticks per visible segment, with a break at `split`.
  const segments: [Date, Date, number][] = [];
  if (domain[0] < split && domain[1] > split) {
    segments.push([domain[0], split, target(split) - G.t0], [split, domain[1], G.t1 - target(split)]);
  } else {
    segments.push([domain[0], domain[1], tLen]);
  }
  const minGap = vertical ? 24 : collapsed ? 80 : 54;
  const ticks = segments.flatMap(([a, z, px]) => segmentTicks(a, z, px, minGap));
  const ages = collapsed && vertical ? [] : segments.flatMap(([a, z, px]) => ageTicks(birth, a, z, px, vertical ? 24 : 34));
  const ageT = (a: number) => T(new Date(birth.getTime() + a * YEAR));
  const tickLabels = ticks.filter((t, i) => i === 0 || Math.abs(T(t.date) - T(ticks[i - 1].date)) >= (vertical ? 15 : collapsed ? 60 : 40));
  const ageLabels = ages.filter((a, i) => i === 0 || Math.abs(ageT(a) - ageT(ages[i - 1])) >= (vertical ? 15 : 22));
  const breakAt = T(split);
  const breakVisible = breakAt > G.t0 + 4 && breakAt < G.t1 - 4;
  const inT = (t: number) => t >= G.t0 - 1 && t <= G.t1 + 1;

  const hit = useCallback(
    (px: number, py: number): Mark | null => {
      const t = vertical ? py : px;
      const c = vertical ? px : py;
      if (collapsed) {
        // Each lane is one thin row: take the row under the pointer, then the nearest event in time within it.
        const lane = lanes.find((l) => c >= layout[l.id].c0 - 1.5 && c <= layout[l.id].c1 + 1.5);
        if (!lane) return null;
        let best: Mark | null = null;
        let bestD = 10;
        for (const m of visible) {
          if (m.lane !== lane.id) continue;
          const t1 = target(m.start);
          const t2 = m.end ? Math.max(t1, target(m.end)) : t1;
          // Point events win over long bars they sit on, so a visit can be picked inside a condition's span.
          const d = (t < t1 ? t1 - t : t > t2 ? t - t2 : 0) + (m.end && t2 - t1 > 6 ? 2 : 0);
          if (d < bestD) {
            bestD = d;
            best = m;
          }
        }
        return best;
      }
      const lane = lanes.find((l) => c >= layout[l.id].c0 - LANE_GAP / 2 && c <= layout[l.id].c1 + LANE_GAP / 2);
      if (!lane) return null;
      const L = layout[lane.id];
      let best: Mark | null = null;
      let bestD = 12;
      for (const m of visible) {
        if (m.lane !== lane.id) continue;
        const r = L.rows[Math.min(m.row, L.rows.length - 1)];
        const t1 = target(m.start);
        const t2 = m.end ? Math.max(t1 + 3, target(m.end)) : t1;
        let d = t < t1 ? t1 - t : t > t2 ? t - t2 : 0;
        const dc = Math.max(0, Math.abs(c - r.c) - r.size / 2);
        d += dc * 1.5;
        // Inset medications win over the condition band they sit in.
        if (m.inset && d === 0) d = -1;
        if (d < bestD) {
          bestD = d;
          best = m;
        }
      }
      return best;
    },
    [lanes, layout, visible, target, vertical, collapsed, lens, lensOn]
  );

  const point = (e: React.MouseEvent) => {
    const r = svgRef.current!.getBoundingClientRect();
    return { px: e.clientX - r.left, py: e.clientY - r.top };
  };
  const clampT = (t: number) => Math.max(G.t0, Math.min(G.t1, t));

  // Pointer moves are handled once per animation frame.
  const moveRaf = useRef(0);
  const moveAt = useRef<{ px: number; py: number } | null>(null);
  const onMove = (e: React.MouseEvent) => {
    if (pickingRef.current) return;
    moveAt.current = point(e);
    if (moveRaf.current) return;
    moveRaf.current = requestAnimationFrame(() => {
      moveRaf.current = 0;
      const at = moveAt.current;
      if (at && !pickingRef.current) handleMove(at.px, at.py);
    });
  };
  const handleMove = (px: number, py: number) => {
    const t = vertical ? py : px;
    setHover({ t, c: vertical ? px : py });
    const drag = dragRef.current;
    if (drag && !collapsed) {
      if (Math.abs(t - drag.a) > 4) drag.moved = true;
      if (drag.moved) {
        setBrush({ a: drag.a, b: clampT(t) });
        setTip(null);
        return;
      }
    }
    const m = hit(px, py);
    setTip(m ? { x: px, y: py, mark: m } : null);
  };

  const onDown = (e: React.MouseEvent) => {
    const { px, py } = point(e);
    const t = vertical ? py : px;
    if (t < G.t0 || t > G.t1) return;
    dragRef.current = { a: t, moved: false };
  };

  const onUp = (e: React.MouseEvent) => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (!drag) return;
    const { px, py } = point(e);
    if (drag.moved) {
      const t = clampT(vertical ? py : px);
      const a = Math.min(drag.a, t);
      const z = Math.max(drag.a, t);
      setBrush(null);
      if (z - a > 10 && target.invert(z).getTime() - target.invert(a).getTime() > 20 * DAY) {
        const g0 = f0 + ((a - G.t0) / tLen) * (f1 - f0);
        const g1 = f0 + ((z - G.t0) / tLen) * (f1 - f0);
        glide();
        if (1 / (g1 - g0) <= maxZoom) setZoom({ f0: g0, f1: g1 });
        else zoomTo(maxZoom, ((a + z) / 2 - G.t0) / tLen);
      }
      return;
    }
    setBrush(null);
    const m = hit(px, py);
    if (m) onSelect(m.id);
  };

  const sel = selected ? byId.get(selected) ?? null : null;

  // Date picker: the orange date pill is a handle. Dragging it snaps from event to event across every lane, one notch
  // per event at its date; events on the same day are fanned out a few pixels apart so each has its own notch.
  const detents = useMemo(() => {
    const laneOrder = new Map(lanes.map((l, i) => [l.id, i]));
    const pts = visible
      .map((m) => ({ m, p: target(m.start), day: m.start.toISOString().slice(0, 10) }))
      .filter((x) => x.p >= G.t0 - 1 && x.p <= G.t1 + 1)
      .sort((a, z) => a.p - z.p || laneOrder.get(a.m.lane)! - laneOrder.get(z.m.lane)! || a.m.row - z.m.row);
    const gap = collapsed ? 5 : 8;
    const out: { id: string; p: number }[] = [];
    for (let i = 0; i < pts.length; ) {
      let j = i;
      while (j < pts.length && pts[j].day === pts[i].day) j++;
      for (let k = i; k < j; k++) out.push({ id: pts[k].m.id, p: pts[i].p + (k - i - (j - i - 1) / 2) * gap });
      i = j;
    }
    return out;
  }, [visible, target, lanes, collapsed, G.t0, G.t1]);
  const [pick, setPick] = useState<number | null>(null);
  const [bump, setBump] = useState(0);
  // Pointer over the pill or the selection line: the pill lifts and the line thickens, ready to be picked up.
  const [pickHover, setPickHover] = useState(false);
  const pickingRef = useRef(false);
  const pickedRef = useRef<string | null>(null);
  // The first notch of a drag adds one history entry, so Back returns to where the drag began; later notches replace it.
  const firstStepRef = useRef(false);
  const tipAt = (id: string, p: number): Tip | null => {
    const m = byId.get(id);
    if (!m) return null;
    return vertical ? { x: collapsed ? w - 4 : G.c0, y: p, mark: m } : { x: p, y: collapsed ? 4 : 40, mark: m };
  };
  /** Move the picker to a notch: select its event (as a step, not a history entry) and give the notch a click. */
  const [pickedId, setPickedId] = useState<string | null>(null);
  const commit = useRef<{ id: string; push: boolean; raf: number }>({ id: '', push: false, raf: 0 });
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  /** Tell the record, once per frame and as low-priority work, so the pill never waits for the tabs to render. */
  const commitSelect = (id: string, push: boolean) => {
    const c = commit.current;
    c.id = id;
    c.push = c.push || push;
    if (c.raf) return;
    c.raf = requestAnimationFrame(() => {
      const { id: next, push: first } = c;
      c.raf = 0;
      c.push = false;
      startTransition(() => onSelectRef.current(next, !first));
    });
  };
  const landedRef = useRef<string | null>(null);
  const land = (d: { id: string; p: number }) => {
    if (d.id === landedRef.current) return;
    landedRef.current = d.id;
    setPick(d.p);
    setTip(tipAt(d.id, d.p));
    if (d.id === pickedRef.current) return;
    pickedRef.current = d.id;
    setPickedId(d.id);
    setBump((n) => n + 1);
    (navigator as Navigator & { vibrate?: (ms: number) => boolean }).vibrate?.(4);
    commitSelect(d.id, firstStepRef.current);
    firstStepRef.current = false;
  };
  const startPick = (e: React.PointerEvent) => {
    if (e.button !== 0 || !detents.length) return;
    e.stopPropagation();
    e.preventDefault();
    const svg = svgRef.current!;
    const list = detents;
    pickingRef.current = true;
    pickedRef.current = selected;
    landedRef.current = null;
    firstStepRef.current = true;
    setHover(null);
    // Entrance animations in the details are skipped while the picker moves, so each step lands at once.
    document.body.classList.add('tl-picking');
    const move = (ev: { clientX: number; clientY: number }) => {
      const r = svg.getBoundingClientRect();
      const t = Math.max(G.t0, Math.min(G.t1, vertical ? ev.clientY - r.top : ev.clientX - r.left));
      let best = list[0];
      for (const d of list) if (Math.abs(d.p - t) < Math.abs(best.p - t)) best = d;
      land(best);
    };
    const up = () => {
      pickingRef.current = false;
      document.body.classList.remove('tl-picking');
      setPick(null);
      setPickedId(null);
      setTip(null);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    move(e);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  const stepPick = (dir: number) => {
    if (!detents.length) return;
    const i = detents.findIndex((d) => d.id === selected);
    const next = detents[i < 0 ? (dir > 0 ? 0 : detents.length - 1) : Math.max(0, Math.min(detents.length - 1, i + dir))];
    pickedRef.current = selected;
    landedRef.current = null;
    land(next);
    window.setTimeout(() => {
      if (!pickingRef.current) {
        setPick(null);
        setPickedId(null);
        setTip(null);
      }
    }, 900);
  };
  const selAnchor = () => {
    if (!sel) return 0.5;
    const a = (target(sel.start) - G.t0) / tLen;
    return a >= 0 && a <= 1 ? a : 0.5;
  };

  // Keep the selection in view by panning the zoom window to it.
  useEffect(() => {
    if (!sel || !zoom) return;
    const t = target(sel.start);
    if (t >= G.t0 + 12 && t <= G.t1 - 12) return;
    glide();
    panTo((base(sel.start) - G.t0) / tLen - (zoom.f1 - zoom.f0) / 2);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  // The scroll wheel (and a pinch) zooms around the pointer; shift + wheel or a sideways swipe pans when zoomed.
  // Wheel events are summed and applied once per animation frame.
  const wheel = useRef({ zoom: 0, pan: 0, anchor: 0.5, raf: 0 });
  const zoomNow = useRef({ zoomTo, panTo, zoomFactor, zoom, tLen });
  zoomNow.current = { zoomTo, panTo, zoomFactor, zoom, tLen };
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const acc = wheel.current;
    const onWheel = (e: WheelEvent) => {
      const r = el.getBoundingClientRect();
      const pos = vertical ? e.clientY - r.top : e.clientX - r.left;
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
      const dx = e.deltaX * unit;
      const dy = e.deltaY * unit;
      e.preventDefault();
      if ((e.shiftKey || Math.abs(dx) > Math.abs(dy)) && !e.ctrlKey) acc.pan += Math.abs(dx) > Math.abs(dy) ? dx : dy;
      else acc.zoom += dy * (e.ctrlKey ? 0.01 : 0.0025);
      acc.anchor = Math.max(0, Math.min(1, (pos - G.t0) / zoomNow.current.tLen));
      if (acc.raf) return;
      acc.raf = requestAnimationFrame(() => {
        acc.raf = 0;
        const z = zoomNow.current;
        if (acc.zoom) z.zoomTo(z.zoomFactor * Math.exp(-acc.zoom), acc.anchor);
        else if (acc.pan && z.zoom) z.panTo(z.zoom.f0 + (acc.pan / z.tLen) * (z.zoom.f1 - z.zoom.f0));
        acc.zoom = 0;
        acc.pan = 0;
      });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', onWheel);
      cancelAnimationFrame(acc.raf);
      acc.raf = 0;
    };
  }, [vertical, G.t0]);

  /* ---------------------------------------------------------------- marks */

  const drawMark = (m: Mark) => {
    const r = rowOf(m);
    const t1 = T(m.start);
    const cc = r.c;
    const cs = r.size;
    const op = (m.faded ? 0.55 : 1) * (dim(m) ? 0.62 : 1);
    const key = m.id;
    if (collapsed) {
      const t2 = m.end ? Math.max(t1 + 1.5, T(m.end)) : t1;
      if (m.shape === 'bar' && t2 - t1 > 2) {
        const thick = m.band ? cs * 0.9 : cs * 0.55;
        return <rect key={key} {...along(t1, t2, cc - thick / 2, thick)} fill={m.colour} fillOpacity={m.band ? 0.35 : 1} opacity={op} />;
      }
      const big = !m.synthetic;
      return vertical ? (
        <line key={key} x1={cc - cs / 2} x2={cc + cs / 2} y1={t1} y2={t1} stroke={m.colour} strokeWidth={big ? 2 : 1.2} opacity={op} />
      ) : (
        <line key={key} x1={t1} x2={t1} y1={cc - cs / 2} y2={cc + cs / 2} stroke={m.colour} strokeWidth={big ? 2 : 1.2} opacity={op} />
      );
    }
    const s = Math.max(4, Math.min(m.big ? 8.5 : 6.5, cs * 0.46 + (m.big ? 2 : 1)));
    const cx = X(t1, cc);
    const cy = Y(t1, cc);
    switch (m.shape) {
      case 'tick': {
        const hw = Math.max(3.5, Math.min(cs * 0.45, 10));
        return vertical ? (
          <line key={key} x1={cc - hw} x2={cc + hw} y1={t1} y2={t1} stroke={m.colour} strokeWidth={2.3} opacity={op} />
        ) : (
          <line key={key} x1={t1} x2={t1} y1={cc - hw} y2={cc + hw} stroke={m.colour} strokeWidth={2.3} opacity={op} />
        );
      }
      case 'dot':
        return <circle key={key} cx={cx} cy={cy} r={s - 0.5} fill={m.colour} opacity={op} />;
      case 'ring':
        return <circle key={key} cx={cx} cy={cy} r={s - 0.5} fill="var(--tl-bg, var(--bg))" stroke={m.colour} strokeWidth={2.4} opacity={op} />;
      case 'diamond':
        return <rect key={key} x={cx - s} y={cy - s} width={s * 2} height={s * 2} transform={`rotate(45 ${cx} ${cy})`} fill={m.colour} opacity={op} />;
      case 'tri':
        return <path key={key} d={`M${cx},${cy - s - 1} L${cx + s},${cy + s - 1} L${cx - s},${cy + s - 1} Z`} fill={m.colour} opacity={op} />;
      case 'cross':
        return (
          <g key={key} stroke={m.colour} strokeWidth={2.2} opacity={op}>
            <line x1={cx - s} x2={cx + s} y1={cy - s} y2={cy + s} />
            <line x1={cx - s} x2={cx + s} y1={cy + s} y2={cy - s} />
          </g>
        );
      case 'square':
        return m.outline ? (
          <rect key={key} x={cx - s + 1} y={cy - s + 1} width={(s - 1) * 2} height={(s - 1) * 2} fill="var(--tl-bg, var(--bg))" stroke={m.colour} strokeWidth={2} opacity={op} />
        ) : (
          <rect key={key} x={cx - s} y={cy - s} width={s * 2} height={s * 2} fill={m.colour} opacity={op} />
        );
      case 'bar': {
        const t2 = Math.max(t1 + 3, T(m.end ?? m.start));
        // Conditions are solid lines in their body-system colour; the medications that treat them run as a thinner
        // line just beneath. Every bar has round ends.
        if (m.band) {
          const thick = Math.max(3.5, Math.min(cs * 0.3, 6));
          return <rect key={key} {...along(t1, t2, cc - thick / 2 - 1.5, thick)} rx={thick / 2} fill={m.colour} opacity={op} />;
        }
        if (m.inset) {
          const line = Math.max(3.5, Math.min(cs * 0.3, 6));
          const thick = Math.max(2, line * 0.5);
          return <rect key={key} {...along(t1, t2, cc + line / 2 + 0.5, thick)} rx={thick / 2} fill={m.colour} opacity={op * 0.8} />;
        }
        const thin = m.lane === 'visits';
        const thick = thin ? Math.max(3.5, Math.min(cs * 0.55, 8)) : Math.max(4, Math.min(cs * 0.5, 8));
        return (
          <rect
            key={key}
            {...along(t1, t2, cc - thick / 2, thick)}
            rx={thick / 2}
            fill={m.outline ? 'var(--tl-bg, var(--bg))' : m.colour}
            stroke={m.outline ? (m.kind === 'radiation' ? 'var(--c-path)' : m.colour) : 'none'}
            strokeWidth={1.6}
            opacity={op}
          />
        );
      }
    }
  };

  // Names written on the chart: conditions inside their band, drugs and long-term medications beside their bar.
  const labelled = useMemo(
    () =>
      collapsed
        ? []
        : visible.filter((m) => {
            if (!m.label || !['problems', 'cancer'].includes(m.lane) || m.kind === 'diagnosis' || m.kind === 'outcome') return false;
            if (m.kind !== 'drug') return true;
            return !visible.some((o) => o.kind === 'drug' && o.row === m.row && o.start < m.start);
          }),
    [collapsed, visible]
  );
  // Every condition, medication and drug keeps its name: at least 10.5 px however thin its row. Names that would sit
  // on top of each other (drugs started together) are joined into one label; any that still collide are dropped.
  type Spec = { m: Mark; text: string; at: number; c: number; anchor: 'start' | 'end'; fs: number; len: number; alt: { at: number; anchor: 'start' | 'end'; len: number } };
  const labelSpecs = useMemo(() => {
    const specs: Spec[] = [];
    for (const m of labelled) {
      const r = rowOf(m);
      const fs = Math.max(10.5, Math.min(12.5, r.size * 0.9));
      const cw = fs * 0.56;
      const startT = T(m.start);
      const room = startT - 7 - (G.t0 + 2);
      const before = room >= Math.min(m.label!.length * cw, 110);
      const afterAt = Math.max(G.t0 + 3, T(m.end ?? m.start) + 7);
      const pre = { at: startT - 7, anchor: 'end' as const, len: room };
      const post = { at: afterAt, anchor: 'start' as const, len: G.t1 - afterAt };
      const first = before ? pre : post;
      specs.push({ m, text: m.label!, c: r.c, fs, ...first, alt: before ? post : pre });
    }
    const merged: Spec[] = [];
    for (const sp of specs.sort((a, z) => a.c - z.c)) {
      const twin = merged.find((o) => o.m.lane === sp.m.lane && o.anchor === sp.anchor && Math.abs(o.at - sp.at) < 6 && Math.abs(o.c - sp.c) < sp.fs + 1);
      if (twin && !sp.m.band && !twin.m.band) {
        twin.text = `${twin.text} + ${sp.text}`;
        twin.c = (twin.c + sp.c) / 2;
        twin.len = Math.max(twin.len, sp.len);
      } else merged.push({ ...sp });
    }
    const placed: { t0: number; t1: number; c0: number; c1: number }[] = [];
    const out: Spec[] = [];
    // Conditions first, so their names win over medication names when space is short.
    for (const sp of [...merged.filter((x) => x.m.band), ...merged.filter((x) => !x.m.band)]) {
      const cw = sp.fs * 0.56;
      for (const pos of [{ at: sp.at, anchor: sp.anchor, len: sp.len }, sp.alt]) {
        const chars = Math.floor(pos.len / cw);
        if (chars < 4) continue;
        const text = sp.text.length > chars ? `${sp.text.slice(0, chars - 1)}…` : sp.text;
        const w0 = text.length * cw;
        const box = { t0: pos.anchor === 'end' ? pos.at - w0 : pos.at, t1: pos.anchor === 'end' ? pos.at : pos.at + w0, c0: sp.c - sp.fs / 2, c1: sp.c + sp.fs / 2 };
        if (placed.some((p) => p.t0 < box.t1 && box.t0 < p.t1 && p.c0 < box.c1 && box.c0 < p.c1)) continue;
        placed.push(box);
        out.push({ ...sp, ...pos, text });
        break;
      }
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [labelled, layout, T, G.t0, G.t1]);
  const labelFor = (sp: Spec) => {
    const { m, text, at, c, anchor, fs } = sp;
    const op = dim(m) ? 0.7 : 1;
    const cls = m.band ? 'tl-band-label' : 'tl-bar-label';
    const style = { fontSize: fs, ...(m.band ? { fill: m.colour } : {}) };
    if (vertical) {
      const x = c - fs * 0.35;
      return (
        <text key={`l${m.id}`} x={x} y={at} transform={`rotate(90 ${x} ${at})`} textAnchor={anchor} className={cls} style={style} opacity={op}>
          {text}
        </text>
      );
    }
    return (
      <text key={`l${m.id}`} x={at} y={c + fs * 0.35} textAnchor={anchor} className={cls} style={style} opacity={op}>
        {text}
      </text>
    );
  };

  const highlight = (m: Mark, colour: string, strong: boolean) => {
    const r = rowOf(m);
    const t1 = T(m.start);
    if (collapsed) {
      const t2 = m.end ? Math.max(t1 + 2, T(m.end)) : t1;
      const L = layout[m.lane];
      return <rect {...along(t1 - 3, t2 + 3, L.c0 - 2, L.c1 - L.c0 + 4)} rx={2} fill="none" stroke={colour} strokeWidth={strong ? 1.8 : 1.1} />;
    }
    if (m.shape === 'bar') {
      const t2 = Math.max(t1 + 3, T(m.end ?? m.start));
      const thick = Math.max(12, Math.min(r.size, 22) + 2);
      return <rect {...along(t1 - 3, t2 + 3, r.c - thick / 2, thick)} rx={3} fill="none" stroke={colour} strokeWidth={strong ? 1.8 : 1.1} />;
    }
    return <circle cx={X(t1, r.c)} cy={Y(t1, r.c)} r={10} fill="none" stroke={colour} strokeWidth={strong ? 2 : 1.1} />;
  };

  /* ---------------------------------------------------------------- frame */

  const cur = (pickedId && byId.get(pickedId)) || sel;
  const selT = cur ? T(cur.start) : null;
  const selIn = selT !== null && inT(selT);
  const endMark = marks.find((m) => m.id === 'end');
  const dxT = T(dx);
  const endT = endMark ? T(endMark.start) : null;
  const cEnd = layout[lanes[lanes.length - 1].id].c1;
  const line = (t: number, c0: number, c1: number, props: React.SVGProps<SVGLineElement>) =>
    vertical ? <line x1={c0} x2={c1} y1={t} y2={t} {...props} /> : <line x1={t} x2={t} y1={c0} y2={c1} {...props} />;

  // Lanes, their names and dividers, the grid and the axis: rebuilt only when the scale or layout change.
  const frameLayer = useMemo(
    () => (
      <>
          {/* Lanes: dividers, names. */}
          {lanes.map((l, i) => {
            const L = layout[l.id];
            const on = lensOn && lensLanes.has(l.id);
            if (collapsed) {
              return (
                <g key={l.id}>
                  <rect {...along(G.t0, G.t1, L.c0, L.c1 - L.c0)} className="tl-strip-row" />
                  {!vertical && (
                    <text x={G.t0 - 8} y={(L.c0 + L.c1) / 2 + 3.2} textAnchor="end" className={`tl-strip-name${on ? ' on' : ''}`}>
                      {STRIP_NAME[l.id]}
                    </text>
                  )}
                </g>
              );
            }
            return (
              <g key={l.id}>
                {i > 0 &&
                  (vertical ? (
                    <line x1={L.c0 - LANE_GAP / 2} x2={L.c0 - LANE_GAP / 2} y1={G.t0 - 4} y2={G.t1} className="tl-lane-rule" />
                  ) : (
                    <line x1={4} x2={G.t1} y1={L.c0 - LANE_GAP / 2} y2={L.c0 - LANE_GAP / 2} className="tl-lane-rule" />
                  ))}
                {vertical ? (
                  <g onDoubleClick={(e) => (e.stopPropagation(), focusLane(l.id))} className="tl-lane-hit">
                    <title>Double-click to give this lane more room; drag the divider beside it to resize</title>
                    <rect x={L.c0} y={G.t0 - 70} width={L.c1 - L.c0} height={64} fill="transparent" />
                    <LaneHeading label={l.label.replace(' and ', ' & ')} c0={L.c0} c1={L.c1} bottom={G.t0 - 8} on={on} />
                  </g>
                ) : (
                  <g onDoubleClick={(e) => (e.stopPropagation(), focusLane(l.id))} className="tl-lane-hit">
                    <title>Double-click to give this lane more room; drag the divider below it to resize</title>
                    <rect x={0} y={L.c0} width={G.t0 - 70} height={Math.max(14, L.c1 - L.c0)} fill="transparent" />
                    {(() => {
                      const perLine = Math.floor((G.t0 - 18) / 7);
                      const wrapped = wrapWords(l.label, perLine);
                      // A squeezed lane keeps its name to one line.
                      const lines =
                        wrapped.length * 14 + 4 <= L.c1 - L.c0 ? wrapped : [l.label.length > perLine ? `${l.label.slice(0, perLine - 1)}…` : l.label];
                      return (
                        <>
                          <text className={`tl-lane-name${on ? ' on' : ''}`}>
                            {lines.length < wrapped.length && <title>{l.label}</title>}
                            {lines.map((ln, li) => (
                              <tspan key={li} x={6} y={L.c0 + 15 + li * 14}>
                                {ln}
                              </tspan>
                            ))}
                          </text>
                          {l.note && L.c1 - L.c0 >= 19 + lines.length * 14 && (
                            <text x={6} y={L.c0 + 15 + lines.length * 14} className="tl-lane-note">
                              {l.note}
                            </text>
                          )}
                        </>
                      );
                    })()}
                    {l.rowNames?.map((n, ri) =>
                      n && L.rows[ri].size >= 8.5 && L.rows[ri].c - L.c0 > 18 + (wrapWords(l.label, Math.floor((G.t0 - 18) / 7)).length + (l.note ? 1 : 0)) * 14 ? (
                        <text key={ri} x={G.t0 - 8} y={L.rows[ri].c + 3.5} textAnchor="end" className="tl-row-name">
                          {n}
                        </text>
                      ) : null
                    )}
                  </g>
                )}
              </g>
            );
          })}

          {/* Lane dividers to drag, drawn above the names so they can be grabbed. */}
          {!collapsed &&
            lanes.slice(0, -1).map((l, i) => {
              const divider = layout[l.id].c1 + LANE_GAP / 2;
              return (
                <rect
                  key={`grip${l.id}`}
                  className={`tl-lane-grip ${vertical ? 'v' : 'h'}`}
                  {...(vertical ? { x: divider - 4, y: 34, width: 8, height: G.t0 - 38 } : { x: 0, y: divider - 4, width: G.t0 - 4, height: 8 })}
                  onPointerDown={(e) => startLaneDrag(i, e)}
                  onMouseDown={(e) => e.stopPropagation()}
                  onDoubleClick={(e) => (e.stopPropagation(), setMults({}))}
                >
                  <title>Drag to resize these lanes; double-click to reset all lanes</title>
                </rect>
              );
            })}

          {/* Time grid and axis. */}
          {!collapsed && (
            <g className="grid">{ticks.map((t) => (inT(T(t.date)) ? <g key={t.date.getTime()}>{line(T(t.date), G.c0, cEnd, {})}</g> : null))}</g>
          )}
          {vertical && !collapsed && (
            <>
              <text x={8} y={G.t0 - 10} className="tl-axis-head">
                age
              </text>
              <text x={G.c0 - 8} y={G.t0 - 10} textAnchor="end" className="tl-axis-head">
                year
              </text>
            </>
          )}
          <g>
            {ageLabels.map((a) =>
              inT(ageT(a)) ? (
                <text
                  key={`a${a}`}
                  x={vertical ? 8 : ageT(a)}
                  y={vertical ? ageT(a) + 4 : collapsed ? 16 : 15}
                  textAnchor={vertical || a === 0 ? 'start' : 'middle'}
                  className={collapsed ? 'tl-age small' : 'tl-age'}
                >
                  {a === 0 ? 'birth' : a}
                </text>
              ) : null
            )}
            {!collapsed &&
              tickLabels.map((t) =>
                inT(T(t.date)) ? (
                  <text
                    key={t.date.getTime()}
                    x={vertical ? G.c0 - 8 : T(t.date)}
                    y={vertical ? T(t.date) + 4 : collapsed ? cEnd + 12 : 34}
                    textAnchor={vertical ? 'end' : 'middle'}
                    className={collapsed ? 'tl-year small' : 'tl-year'}
                  >
                    {t.label}
                  </text>
                ) : null
              )}
          </g>
          {breakVisible && !collapsed && (
            <g stroke="var(--ink-2)" strokeWidth={1.2}>
              {line(breakAt - 2, G.c0 - 6, G.c0 + 4, {})}
              {line(breakAt + 2, G.c0 - 6, G.c0 + 4, {})}
            </g>
          )}
          {inT(dxT) && (
            <g>
              {line(dxT, G.c0 - (collapsed ? 2 : 4), cEnd + (collapsed ? 2 : 0), { stroke: 'var(--ink)', strokeDasharray: '3 3', strokeWidth: 1.2 })}
              {!collapsed &&
                (vertical ? (
                  <text x={cEnd} y={dxT - 5} textAnchor="end" className="tl-marker-label">
                    Diagnosis
                  </text>
                ) : (
                  <text x={dxT + 5} y={G.c0 + 10} className="tl-marker-label">
                    Diagnosis
                  </text>
                ))}
            </g>
          )}
          {endMark && endT !== null && inT(endT) && (
            <g>
              {line(endT, G.c0 - (collapsed ? 2 : 4), cEnd + (collapsed ? 2 : 0), {
                stroke: endMark.shape === 'cross' ? 'var(--c-alert)' : 'var(--ink-3)',
                strokeDasharray: '3 3',
                strokeWidth: 1.2,
              })}
              {!collapsed &&
                (vertical ? (
                  <text x={cEnd} y={endT + 15} textAnchor="end" className="tl-marker-label">
                    {endMark.label}
                  </text>
                ) : (
                  <text x={endT - 5} y={G.c0 + 10} textAnchor="end" className="tl-marker-label">
                    {endMark.label}
                  </text>
                ))}
            </g>
          )}

      </>
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lanes, layout, lensOn, lensLanes, collapsed, vertical, w, h, zoom, T, mults]
  );

  // The notches shown under the axis while the picker moves; drawn once per drag, not per step.
  const picking = pick !== null;
  const ridges = useMemo(
    () =>
      picking
        ? detents.map((d) =>
            vertical ? (
              <line key={d.id} x1={collapsed ? 0 : G.c0 - 7} x2={collapsed ? 3 : G.c0 - 2} y1={d.p} y2={d.p} className="tl-ridge" />
            ) : (
              <line key={d.id} x1={d.p} x2={d.p} y1={collapsed ? 20 : 42} y2={collapsed ? 23 : 47} className="tl-ridge" />
            )
          )
        : null,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [picking, detents, vertical, collapsed]
  );
  const miniAt = useCallback((d: Date) => (base(d) - G.t0) / tLen, [base, G.t0, tLen]);
  const miniPan = useCallback((start: number) => panTo(start), [panTo]);

  // The marks and their names are the heaviest part of the chart; they are rebuilt only when the scale, layout, data
  // or open tab change, not on every pointer move.
  const marksLayer = useMemo(
    () => (
      <>
        {visible.filter((m) => m.band).map(drawMark)}
        {visible.filter((m) => !m.band).map(drawMark)}
        {labelSpecs.map(labelFor)}
      </>
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visible, T, layout, lens, collapsed, vertical, labelSpecs]
  );

  const iconSize = 14;
  const controls = (
    <div className={`tl-controls${controlsHost ? ' in-head' : `${collapsed ? ' collapsed' : ''}${vertical ? ' v' : ' h'}`}`}>
      {!collapsed && (
        <div className="tl-ctl-group tl-zoom" role="group" aria-label="Zoom">
          <button className="tl-ctl" aria-label="Zoom out" title="Zoom out" disabled={!zoom} onClick={() => zoomTo(zoomFactor / 2, selAnchor(), true)}>
            <Minus size={iconSize} strokeWidth={1.8} />
          </button>
          <input
            type="range"
            className="tl-zoom-range"
            aria-label="Zoom level"
            title="Zoom (or drag along the timeline)"
            min={0}
            max={Math.log2(maxZoom)}
            step={0.05}
            value={Math.log2(zoomFactor)}
            onChange={(e) => zoomTo(2 ** Number(e.target.value), selAnchor())}
          />
          <button className="tl-ctl" aria-label="Zoom in" title="Zoom in" disabled={zoomFactor >= maxZoom} onClick={() => zoomTo(zoomFactor * 2, selAnchor(), true)}>
            <Plus size={iconSize} strokeWidth={1.8} />
          </button>
          <button className="tl-ctl tl-ctl-num num" title={zoom ? 'Show the whole life' : 'Whole life shown'} disabled={!zoom} onClick={() => zoomTo(1, 0.5, true)}>
            {zoomFactor < 9.95 ? zoomFactor.toFixed(1) : Math.round(zoomFactor)}×
          </button>
        </div>
      )}
      <div className="tl-ctl-group">
        <button
          className="tl-ctl"
          onClick={() => onOrientation(vertical ? 'top' : 'left')}
          title={vertical ? 'Move the timeline to the top, tabs below' : 'Move the timeline to the left, tabs beside it'}
          aria-label={vertical ? 'Move the timeline to the top' : 'Move the timeline to the left'}
        >
          {vertical ? <PanelTop size={iconSize} strokeWidth={1.6} aria-hidden /> : <PanelLeft size={iconSize} strokeWidth={1.6} aria-hidden />}
        </button>
      </div>
      {(!collapsed || showCollapse) && (
      <div className="tl-ctl-group">
        {!collapsed && (
          <button className="tl-ctl tl-ctl-text" aria-expanded={keyOpen} onClick={() => setKeyOpen((v) => !v)} title="What the colours and shapes mean">
            Key
          </button>
        )}
        {showCollapse && (
        <button
          className="tl-ctl"
          onClick={() => onCollapsed(!collapsed)}
          title={collapsed ? 'Expand the timeline' : 'Collapse the timeline to a strip'}
          aria-label={collapsed ? 'Expand the timeline' : 'Collapse the timeline'}
        >
          {vertical ? (
            collapsed ? <ChevronRight size={iconSize} strokeWidth={1.8} /> : <ChevronLeft size={iconSize} strokeWidth={1.8} />
          ) : collapsed ? (
            <ChevronDown size={iconSize} strokeWidth={1.8} />
          ) : (
            <ChevronUp size={iconSize} strokeWidth={1.8} />
          )}
        </button>
        )}
      </div>
      )}
    </div>
  );

  return (
    <div className={`tl ${vertical ? 'tl-v' : 'tl-h'}${collapsed ? ' tl-collapsed' : ''}`}>
      <div ref={wrapRef} className="tl-plot">
        <svg
          ref={svgRef}
          className="chart tl-svg absolute inset-0 block"
          width={w}
          height={h}
          role="img"
          aria-label={`Patient lifetime timeline, birth at the ${vertical ? 'top' : 'left'}${collapsed ? ', collapsed' : ''}`}
          onMouseMove={onMove}
          onMouseDown={onDown}
          onMouseUp={onUp}
          onMouseLeave={() => {
            cancelAnimationFrame(moveRaf.current);
            moveRaf.current = 0;
            setTip(null);
            setHover(null);
            setBrush(null);
            dragRef.current = null;
          }}
          onDoubleClick={() => zoomTo(1, 0.5, true)}
          style={{ cursor: tip ? 'pointer' : collapsed ? 'default' : vertical ? 'ns-resize' : 'ew-resize' }}
        >
          <defs>
            <clipPath id={clipId}>
              <rect {...along(G.t0 - 2, G.t1 + 2, G.c0 - 4, cEnd - G.c0 + 8)} />
            </clipPath>
          </defs>

          {/* Hover: the lane and the time column under the pointer are shaded. */}
          {hover &&
            hover.t >= G.t0 &&
            hover.t <= G.t1 &&
            (() => {
              const lane = lanes.find((l) => hover.c >= layout[l.id].c0 - LANE_GAP / 2 && hover.c <= layout[l.id].c1 + LANE_GAP / 2);
              const edges = [G.t0, ...ticks.map((tk) => T(tk.date)).filter((v) => v > G.t0 && v < G.t1), G.t1].sort((a, z) => a - z);
              let a0 = G.t0;
              let a1 = G.t1;
              for (let i = 0; i < edges.length - 1; i++) {
                if (hover.t >= edges[i] && hover.t <= edges[i + 1]) {
                  a0 = edges[i];
                  a1 = edges[i + 1];
                  break;
                }
              }
              const L = lane ? layout[lane.id] : null;
              return (
                <g pointerEvents="none">
                  {!collapsed && <rect {...along(a0, a1, G.c0 - 4, cEnd - G.c0 + 8)} className="tl-hover-col" />}
                  {L && <rect {...along(collapsed ? G.t0 : 0, G.t1, L.c0 - (collapsed ? 0 : LANE_GAP / 2), L.c1 - L.c0 + (collapsed ? 0 : LANE_GAP))} className="tl-hover-lane" />}
                </g>
              );
            })()}

          {frameLayer}

          {/* Marks. */}
          <g clipPath={`url(#${clipId})`} pointerEvents="none">
            {marksLayer}
            {cur && selIn && (
              <g>
                {line(selT!, G.c0 - 4, cEnd + 2, { className: `tl-sel-line${collapsed ? ' thick' : ''}${pickHover || pick !== null ? ' up' : ''}` })}
                {highlight(cur, 'var(--accent)', true)}
              </g>
            )}
            {tip && tip.mark.id !== cur?.id && highlight(tip.mark, 'var(--ink-2)', false)}
          </g>
          {/* The date picker: a pill on the axis to drag along; notches show while it moves. */}
          {(() => {
            const idle = !cur || !selIn;
            const at = pick ?? (idle ? (inT(dxT) ? dxT : (G.t0 + G.t1) / 2) : selT!);
            const label = d3.utcFormat(vertical && collapsed ? '%b %Y' : '%-d %b %Y')(cur?.start ?? dx);
            const box = vertical
              ? collapsed
                ? { x: 2, y: at - 8, width: w - 4, height: 16 }
                : { x: 4, y: at - 9, width: G.c0 - 8, height: 18 }
              : collapsed
                ? { x: Math.max(0, Math.min(w - 82, at - 40)), y: 5, width: 80, height: 15 }
                : { x: Math.max(0, Math.min(w - 90, at - 44)), y: 21, width: 88, height: 18 };
            const band = vertical
              ? collapsed
                ? null
                : { x: 0, y: G.t0, width: G.c0 - 4, height: tLen }
              : collapsed
                ? { x: G.t0 - 6, y: 3, width: tLen + 12, height: 18 }
                : { x: G.t0 - 6, y: 19, width: tLen + 12, height: 22 };
            const ridge = (p: number, on: boolean, k: string) =>
              vertical ? (
                <line key={k} x1={collapsed ? 0 : G.c0 - 7} x2={collapsed ? 3 : G.c0 - 2} y1={p} y2={p} className={`tl-ridge${on ? ' on' : ''}`} />
              ) : (
                <line key={k} x1={p} x2={p} y1={collapsed ? 20 : 42} y2={collapsed ? 23 : 47} className={`tl-ridge${on ? ' on' : ''}`} />
              );
            return (
              <g>
                {band && (
                  <rect
                    {...band}
                    fill="transparent"
                    className="tl-pick-band"
                    onPointerDown={startPick}
                    onMouseDown={(e) => e.stopPropagation()}
                    onDoubleClick={(e) => e.stopPropagation()}
                  />
                )}
                {pick !== null && ridges}
                {pick !== null && pickedId && ridge(detents.find((d) => d.id === pickedId)?.p ?? pick, true, 'ridge-on')}
                {!idle && pick === null && (
                  <rect
                    {...along(selT! - 5, selT! + 5, G.c0 - 4, cEnd - G.c0 + 8)}
                    fill="transparent"
                    className="tl-pick-line"
                    onPointerEnter={() => setPickHover(true)}
                    onPointerLeave={() => setPickHover(false)}
                    onPointerDown={startPick}
                    onMouseDown={(e) => e.stopPropagation()}
                    onDoubleClick={(e) => e.stopPropagation()}
                  >
                    <title>Drag to move through the events</title>
                  </rect>
                )}
                <g
                  className="tl-picker"
                  role="slider"
                  tabIndex={0}
                  aria-label="Pick an event by date"
                  aria-valuetext={cur ? `${cur.title}, ${d3.utcFormat('%-d %B %Y')(cur.start)}` : 'No event selected'}
                  onPointerDown={startPick}
                  onPointerEnter={() => setPickHover(true)}
                  onPointerLeave={() => setPickHover(false)}
                  onMouseDown={(e) => e.stopPropagation()}
                  onDoubleClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => {
                    const back = vertical ? 'ArrowUp' : 'ArrowLeft';
                    const fwd = vertical ? 'ArrowDown' : 'ArrowRight';
                    if (e.key === back || e.key === fwd) {
                      e.preventDefault();
                      e.stopPropagation();
                      stepPick(e.key === fwd ? 1 : -1);
                    }
                  }}
                >
                  <g className={`tl-pill-lift${pickHover || pick !== null ? ' up' : ''}`}>
                  <g key={bump} className={bump ? 'tl-detent' : undefined}>
                    <rect {...box} rx={box.height / 2} className={idle && pick === null ? 'tl-pill idle' : 'tl-pill'} />
                    <text x={box.x + box.width / 2} y={box.y + box.height / 2 + (collapsed ? 3.5 : 4)} textAnchor="middle" className={`tl-cursor-label${collapsed ? ' small' : ''}`}>
                      {label}
                    </text>
                  </g>
                  </g>
                </g>
              </g>
            );
          })()}

          {brush && (
            <rect
              {...along(Math.min(brush.a, brush.b), Math.max(brush.a, brush.b), G.c0 - 4, cEnd - G.c0 + 8)}
              fill="var(--accent-wash)"
              opacity={0.55}
              stroke="var(--accent)"
            />
          )}
        </svg>
        {controlsHost ? createPortal(controls, controlsHost) : controls}
        {zoom && !collapsed && (
          <MiniMap
            marks={marks}
            at={miniAt}
            f0={f0}
            f1={f1}
            start={G.t0}
            length={tLen}
            vertical={vertical}
            onPan={miniPan}
            zoomed
          />
        )}
        {keyOpen && !collapsed && <TimelineKey onClose={() => setKeyOpen(false)} />}
        {tip && (
          <div
            className="tl-tip"
            style={
              collapsed && !vertical
                ? { left: Math.max(4, Math.min(tip.x + 14, w - 320)), top: h + 6 }
                : { left: Math.max(4, Math.min(tip.x + 14, w - 320)), top: Math.max(4, Math.min(tip.y + 14, h - 110)) }
            }
          >
            <div className="font-medium">{tip.mark.title}</div>
            {tip.mark.lines.map((l, i) => (
              <div key={i} className="t-muted text-[12px]">
                {l}
              </div>
            ))}
            <div className="t-faint mt-1 text-[11px]">{tip.mark.synthetic ? 'Synthetic · ' : ''}Click to open</div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Words into lines of at most `perLine` characters (a longer word gets a line of its own). */
function wrapWords(text: string, perLine: number): string[] {
  const lines: string[] = [];
  for (const wd of text.split(' ')) {
    const lastLine = lines[lines.length - 1];
    if (lastLine && lastLine.length + 1 + wd.length <= perLine) lines[lines.length - 1] = `${lastLine} ${wd}`;
    else lines.push(wd);
  }
  return lines;
}

/** A lane's name above its column: on one or more lines when the column is wide enough, otherwise turned upright. */
function LaneHeading({ label, c0, c1, bottom, on }: { label: string; c0: number; c1: number; bottom: number; on: boolean }) {
  const width = c1 - c0;
  const cls = `tl-lane-name${on ? ' on' : ''}`;
  const across = wrapWords(label, Math.floor(width / 7));
  if (across.every((ln) => ln.length * 7 <= width + 4) && across.length * 14 <= 62) {
    return (
      <text className={cls} textAnchor="middle">
        {across.map((ln, i) => (
          <tspan key={i} x={(c0 + c1) / 2} y={bottom - (across.length - 1 - i) * 14}>
            {ln}
          </tspan>
        ))}
      </text>
    );
  }
  // Too narrow to write across: turn it upright, on as many lines as the column holds.
  const room = 62;
  const lines = wrapWords(label, Math.max(4, Math.floor(room / 7)));
  const fits = Math.max(1, Math.floor((width + 6) / 13));
  const shown = lines.length <= fits ? lines : [label.length * 7 > room ? `${label.slice(0, Math.floor(room / 7) - 1)}…` : label];
  const cx = (c0 + c1) / 2;
  return (
    <text className={cls} transform={`rotate(-90 ${cx} ${bottom})`}>
      <title>{label}</title>
      {shown.map((ln, i) => (
        <tspan key={i} x={cx} y={bottom + (i - (shown.length - 1) / 2) * 13 + 4}>
          {ln}
        </tspan>
      ))}
    </text>
  );
}

/** The whole range in miniature beside (or under) the plot, with the zoomed window on it; drag to move it. */
const MiniMap = memo(function MiniMap({
  marks,
  at,
  f0,
  f1,
  start,
  length,
  vertical,
  onPan,
  zoomed,
}: {
  marks: Mark[];
  at: (d: Date) => number;
  f0: number;
  f1: number;
  start: number;
  length: number;
  vertical: boolean;
  onPan: (start: number) => void;
  zoomed: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const grab = useRef<number | null>(null);
  const span = f1 - f0;
  const pos = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return vertical ? (e.clientY - r.top) / r.height : (e.clientX - r.left) / r.width;
  };
  const style = vertical ? { top: start, height: length, right: 2, width: MINI } : { left: start, width: length, bottom: 2, height: MINI };
  return (
    <div
      ref={ref}
      className={`tl-mini${zoomed ? ' on' : ''}`}
      style={style}
      title="Drag to move the zoomed window"
      onPointerDown={(e) => {
        const f = pos(e);
        const inside = f >= f0 && f <= f1;
        grab.current = inside ? f - f0 : span / 2;
        if (!inside) onPan(f - span / 2);
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => grab.current !== null && onPan(pos(e) - grab.current)}
      onPointerUp={(e) => {
        grab.current = null;
        e.currentTarget.releasePointerCapture(e.pointerId);
      }}
    >
      <svg className="absolute inset-0 h-full w-full" viewBox={vertical ? '0 0 12 1000' : '0 0 1000 12'} preserveAspectRatio="none" aria-hidden>
        {marks.map((m) => {
          const f = at(m.start) * 1000;
          const a = m.synthetic ? 4 : 1;
          const z = m.synthetic ? 8 : 11;
          return vertical ? (
            <line key={m.id} x1={a} x2={z} y1={f} y2={f} stroke={m.synthetic ? 'var(--ink-3)' : 'var(--ink)'} opacity={m.synthetic ? 0.5 : 0.9} vectorEffect="non-scaling-stroke" />
          ) : (
            <line key={m.id} x1={f} x2={f} y1={a} y2={z} stroke={m.synthetic ? 'var(--ink-3)' : 'var(--ink)'} opacity={m.synthetic ? 0.5 : 0.9} vectorEffect="non-scaling-stroke" />
          );
        })}
      </svg>
      <div
        className="tl-mini-window"
        style={vertical ? { top: `${f0 * 100}%`, height: `${span * 100}%`, left: 0, right: 0 } : { left: `${f0 * 100}%`, width: `${span * 100}%`, top: 0, bottom: 0 }}
      />
    </div>
  );
});

function KeyItem({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      {children}
      {label}
    </span>
  );
}

/** What the colours and shapes mean, and how to drive the timeline; opened from the Key button. */
function TimelineKey({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    const onDown = (e: PointerEvent) => {
      const t = e.target as HTMLElement;
      if (!ref.current?.contains(t) && !t.closest('.tl-controls')) onClose();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('pointerdown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('pointerdown', onDown);
    };
  }, [onClose]);
  return (
    <div ref={ref} className="tl-key rise" role="dialog" aria-label="Timeline key">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-x-4 gap-y-1.5 text-[12px]">
        <KeyItem label="Wellness visit">
          <span className="swatch" style={{ background: VISIT_COLOUR[0], width: 3, height: 12 }} />
        </KeyItem>
        <KeyItem label="Office visit">
          <span className="swatch" style={{ background: VISIT_COLOUR[1], width: 3, height: 12 }} />
        </KeyItem>
        <KeyItem label="Emergency or inpatient">
          <span className="swatch" style={{ background: VISIT_COLOUR[2], width: 3, height: 12 }} />
        </KeyItem>
        <KeyItem label="Immunisation">
          <span className="swatch" style={{ background: 'var(--c-vax)', borderRadius: 5 }} />
        </KeyItem>
        {Object.entries(SYSTEMS).map(([k, v]) => (
          <KeyItem key={k} label={v.label}>
            <span className="swatch" style={{ background: v.colour, width: 14, height: 9, opacity: 0.85 }} />
          </KeyItem>
        ))}
        <KeyItem label="Condition (band) and its medication (bar)">
          <svg width="22" height="12">
            <rect x="0.5" y="0.5" width="21" height="11" rx="2" fill="var(--sys-circ)" fillOpacity="0.34" stroke="var(--sys-circ)" />
            <rect x="3" y="7" width="16" height="3" fill="var(--sys-circ)" />
          </svg>
        </KeyItem>
        {Object.entries(CLASS_STYLE).map(([k, v]) => (
          <KeyItem key={k} label={v.label}>
            <span className="swatch" style={{ background: v.fill, border: k === 'hormone' ? '1px solid var(--ink)' : undefined, width: 14, height: 9 }} />
          </KeyItem>
        ))}
        <KeyItem label="Radiotherapy">
          <span className="swatch" style={{ border: '1.5px solid var(--c-path)', width: 14, height: 9 }} />
        </KeyItem>
        <KeyItem label="Recurrence or metastasis">
          <svg width="11" height="11"><path d="M5.5,0 L11,10 L0,10 Z" fill="var(--c-alert)" /></svg>
        </KeyItem>
        <KeyItem label="Tumour free">
          <svg width="11" height="11"><circle cx="5.5" cy="5.5" r="4" fill="none" stroke="var(--c-good)" strokeWidth="2" /></svg>
        </KeyItem>
        <KeyItem label="Radiology · pathology · report">
          <span className="flex gap-0.5">
            <span className="swatch" style={{ background: 'var(--c-rad)' }} />
            <span className="swatch" style={{ background: 'var(--c-path)' }} />
            <span className="swatch" style={{ border: '1px solid var(--ink-2)' }} />
          </span>
        </KeyItem>
        <KeyItem label="Tumour board note">
          <span className="swatch" style={{ background: 'var(--accent)', borderRadius: 5 }} />
        </KeyItem>
      </div>
      <p className="t-faint mt-3 text-[11.5px] leading-snug">
        Click a mark to open it. Drag along the timeline to zoom in; double-click it, or press the zoom factor, to see
        the whole life again. Pinch to zoom and swipe to move when zoomed. Drag the divider beside a lane&apos;s name to
        give it more room, or double-click the name. Arrow keys step through the open tab.
      </p>
    </div>
  );
}
