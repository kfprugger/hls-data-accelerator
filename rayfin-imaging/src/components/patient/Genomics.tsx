import { useEffect, useMemo, useRef, useState } from 'react';

import { num, parseJson, str, type PatientBundle, type Row } from '@/lib/api';
import { fmtNum, ordinal } from '@/lib/format';

/* GRCh37 chromosome lengths (the PanCancer Atlas coordinates). */
const CHROMS: [string, number][] = [
  ['1', 249250621], ['2', 243199373], ['3', 198022430], ['4', 191154276], ['5', 180915260], ['6', 171115067],
  ['7', 159138663], ['8', 146364022], ['9', 141213431], ['10', 135534747], ['11', 135006516], ['12', 133851895],
  ['13', 115169878], ['14', 107349540], ['15', 102531392], ['16', 90354753], ['17', 81195210], ['18', 78077248],
  ['19', 59128983], ['20', 63025520], ['21', 48129895], ['22', 51304566], ['X', 155270560],
];
const OFFSET: Record<string, number> = {};
let acc = 0;
for (const [c, len] of CHROMS) {
  OFFSET[c] = acc;
  acc += len;
}
const GENOME = acc;

const TRUNCATING = /Nonsense|Frame_Shift|Splice|Nonstop|Translation_Start/;
const PROTEIN = /Missense|Nonsense|Frame_Shift|In_Frame|Splice_Site|Nonstop|Translation_Start/;

/** Mutation classes follow the cBioPortal convention; truncating uses the ink colour so it reads in both themes. */
function typeColour(t: string): string {
  if (TRUNCATING.test(t)) return 'var(--ink)';
  if (/Missense/.test(t)) return 'var(--c-good)';
  if (/In_Frame/.test(t)) return '#b07a35';
  return 'var(--ink-3)';
}

function resolveColour(c: string, css: CSSStyleDeclaration): string {
  const m = /^var\((--[\w-]+)\)$/.exec(c);
  return m ? css.getPropertyValue(m[1]).trim() : c;
}

function typeLabel(t: string): string {
  return t.replace(/_Mutation$/, '').replace(/_/g, ' ').replace('Frame Shift', 'Frameshift').replace(/^(\w)/, (m) => m.toUpperCase());
}

const EXPRESSION_GROUPS: { title: string; note: string; genes: [string, string][] }[] = [
  {
    title: 'Therapy targets',
    note: 'kinases and receptors with approved drugs',
    genes: [['ERBB2', 'HER2'], ['EGFR', 'EGFR'], ['MET', 'MET'], ['FGFR3', 'FGFR3'], ['KIT', 'KIT'], ['VEGFA', 'VEGF-A'], ['ESR1', 'ER'], ['PGR', 'PR'], ['AR', 'AR']],
  },
  {
    title: 'Antibody-drug conjugate targets',
    note: 'surface proteins that ADCs bind',
    genes: [['TACSTD2', 'TROP2'], ['NECTIN4', 'Nectin-4'], ['FOLR1', 'FRα'], ['CLDN18', 'Claudin 18'], ['CD276', 'B7-H3'], ['MSLN', 'Mesothelin'], ['DLL3', 'DLL3']],
  },
  {
    title: 'Immune checkpoints and T cells',
    note: '',
    genes: [['CD274', 'PD-L1'], ['PDCD1', 'PD-1'], ['CTLA4', 'CTLA-4'], ['LAG3', 'LAG-3'], ['CD8A', 'CD8'], ['GZMB', 'Granzyme B']],
  },
  {
    title: 'DNA repair',
    note: 'mismatch repair and homologous recombination',
    genes: [['MLH1', 'MLH1'], ['MSH2', 'MSH2'], ['MSH6', 'MSH6'], ['PMS2', 'PMS2'], ['BRCA1', 'BRCA1'], ['BRCA2', 'BRCA2']],
  },
];

/* ------------------------------------------------------------------ cohort strip */

function CohortStrip({ quantiles, value, log }: { quantiles: number[]; value: number | null; log?: boolean }) {
  if (!quantiles.length || value === null) return null;
  const t = (v: number) => (log ? Math.log10(1 + Math.max(0, v)) : v);
  const lo = t(quantiles[0]);
  const hi = Math.max(t(quantiles[quantiles.length - 1]), t(value));
  const pos = (v: number) => ((t(v) - lo) / (hi - lo || 1)) * 100;
  return (
    <div className="relative mt-2 h-[14px]">
      <div className="absolute left-0 right-0 top-[6px] h-px" style={{ background: 'var(--line-strong)' }} />
      {quantiles.filter((_, i) => i % 2 === 0).map((q, i) => (
        <span key={i} className="absolute top-[3px] h-[7px] w-px" style={{ left: `${pos(q)}%`, background: 'var(--ink-3)', opacity: 0.45 }} />
      ))}
      <span className="absolute top-[3px] h-[7px] w-[2px]" style={{ left: `${pos(quantiles[50])}%`, background: 'var(--ink-2)' }} />
      <span
        className="absolute top-0 h-[13px] w-[13px] -translate-x-1/2 rounded-full"
        style={{ left: `${pos(value)}%`, background: 'var(--accent)', border: '2px solid var(--bg)' }}
      />
    </div>
  );
}

function Metric({ label, value, unit, pct, quantiles, raw, log, note }: {
  label: string;
  value: string;
  unit?: string;
  pct?: number | null;
  quantiles?: number[];
  raw?: number | null;
  log?: boolean;
  note?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="t-label">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        <span className="t-display num text-[24px]">{value}</span>
        {unit && <span className="t-faint text-[12px]">{unit}</span>}
      </div>
      {quantiles && <CohortStrip quantiles={quantiles} value={raw ?? null} log={log} />}
      <div className="t-faint mt-1 text-[11.5px]">
        {pct !== null && pct !== undefined ? `${ordinal(pct)} percentile` : ''}
        {note ? (pct !== null && pct !== undefined ? ` · ${note}` : note) : ''}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ genome plot */

function GenomePlot({ b }: { b: PatientBundle }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(1000);
  const [hover, setHover] = useState<{ x: number; text: string } | null>(null);
  const H = 264;
  const L = 74;
  const CN_TOP = 18;
  const CN_H = 90;
  const MUT_TOP = 150;
  const MUT_H = 92;

  const [themeTick, setThemeTick] = useState(0);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(600, e.contentRect.width)));
    ro.observe(el);
    // The canvas reads theme colours when it draws; redraw when the theme changes.
    const mo = new MutationObserver(() => setThemeTick((t) => t + 1));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => {
      ro.disconnect();
      mo.disconnect();
    };
  }, []);

  const muts = useMemo(() => {
    const m = b.mutationMap;
    const rows = m.chromosomes
      .map((c, i) => ({ c, g: (OFFSET[c] ?? NaN) + m.positions[i], t: m.typeNames[m.types[i]] ?? '' }))
      .filter((r) => Number.isFinite(r.g))
      .sort((a, z) => a.g - z.g);
    return rows.map((m, i) => ({ ...m, dist: i === 0 || rows[i - 1].c !== m.c ? null : m.g - rows[i - 1].g }));
  }, [b]);

  const drivers = useMemo(
    () =>
      b.drivers
        .filter((d) => PROTEIN.test(String(d.mutation_type)) && OFFSET[String(d.chromosome)] !== undefined)
        .slice(0, 12)
        .map((d) => ({ gene: String(d.gene), g: OFFSET[String(d.chromosome)] + Number(d.start_pos), t: String(d.mutation_type) })),
    [b]
  );

  const x = (g: number) => L + (g / GENOME) * (width - L - 8);

  // Gene labels go on up to three rows; a label that fits on none is left off (its tick stays).
  const labelRows = useMemo(() => {
    const rows: number[][] = [[], [], []];
    return [...drivers]
      .sort((a, z) => a.g - z.g)
      .map((d) => {
        const px = L + (d.g / GENOME) * (width - L - 8);
        const half = d.gene.length * 3.4 + 4;
        const row = rows.findIndex((r) => r.every((other) => Math.abs(other - px) > half * 2));
        if (row >= 0) rows[row].push(px);
        return { d, row };
      });
  }, [drivers, width]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = H * dpr;
    const ctx = canvas.getContext('2d')!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, H);
    const css = getComputedStyle(document.documentElement);
    const v = (n: string) => css.getPropertyValue(n).trim();

    // Chromosome bands.
    CHROMS.forEach(([c, len], i) => {
      if (i % 2 === 0) {
        ctx.fillStyle = v('--surface');
        ctx.fillRect(x(OFFSET[c]), CN_TOP, x(OFFSET[c] + len) - x(OFFSET[c]), CN_H);
        ctx.fillRect(x(OFFSET[c]), MUT_TOP, x(OFFSET[c] + len) - x(OFFSET[c]), MUT_H);
      }
    });

    // Copy number: log2 ratio, clipped to ±1.5.
    const cy = (s: number) => CN_TOP + CN_H / 2 - (Math.max(-1.5, Math.min(1.5, s)) / 1.5) * (CN_H / 2);
    ctx.strokeStyle = v('--line-strong');
    ctx.beginPath();
    ctx.moveTo(L, cy(0));
    ctx.lineTo(width - 8, cy(0));
    ctx.stroke();
    for (const s of b.segments) {
      const c = String(s.chromosome);
      if (OFFSET[c] === undefined) continue;
      const mean = Number(s.segment_mean);
      const x1 = x(OFFSET[c] + Number(s.start_pos));
      const x2 = Math.max(x1 + 1, x(OFFSET[c] + Number(s.end_pos)));
      ctx.fillStyle = mean > 0.2 ? v('--c-gain') : mean < -0.2 ? v('--c-loss') : v('--ink-3');
      const y = cy(mean);
      if (Math.abs(mean) > 0.2) {
        ctx.globalAlpha = 0.18;
        ctx.fillRect(x1, Math.min(y, cy(0)), x2 - x1, Math.abs(y - cy(0)));
        ctx.globalAlpha = 1;
      }
      ctx.fillRect(x1, y - 1.5, x2 - x1, 3);
    }

    // Mutations: rainfall (distance to the previous mutation, log scale). Clusters fall to the bottom.
    const my = (d: number | null) => (d === null ? MUT_TOP + 6 : MUT_TOP + MUT_H - 4 - (Math.log10(Math.max(1, d)) / 8.5) * (MUT_H - 10));
    const r = muts.length > 3000 ? 1.1 : muts.length > 500 ? 1.6 : 2.4;
    const colourCache = new Map<string, string>();
    for (const m of muts) {
      let fill = colourCache.get(m.t);
      if (!fill) {
        fill = resolveColour(typeColour(m.t), css);
        colourCache.set(m.t, fill);
      }
      ctx.fillStyle = fill;
      ctx.globalAlpha = muts.length > 3000 ? 0.55 : 0.85;
      ctx.beginPath();
      ctx.arc(x(m.g), my(m.dist), r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }, [b, muts, width, themeTick]);

  const onMove = (e: React.MouseEvent) => {
    const rect = wrapRef.current!.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const g = ((px - L) / (width - L - 8)) * GENOME;
    const chrom = CHROMS.find(([c, len]) => g >= OFFSET[c] && g < OFFSET[c] + len);
    if (!chrom) return setHover(null);
    const pos = g - OFFSET[chrom[0]];
    const seg = b.segments.find((s) => String(s.chromosome) === chrom[0] && pos >= Number(s.start_pos) && pos <= Number(s.end_pos));
    const mean = seg ? Number(seg.segment_mean) : null;
    const state = mean === null ? 'no segment' : mean > 0.2 ? 'gain' : mean < -0.2 ? 'loss' : 'neutral';
    setHover({ x: px, text: `chr${chrom[0]}:${fmtNum(pos / 1e6, 1)} Mb · copy number ${state}${mean !== null ? ` (log2 ${fmtNum(mean, 2)})` : ''}` });
  };

  return (
    <div ref={wrapRef} className="relative" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <canvas ref={canvasRef} style={{ width, height: H }} className="block" />
      <svg className="chart pointer-events-none absolute inset-0" width={width} height={H}>
        <text x={0} y={CN_TOP + 12} className="tl-lane-label">Copy number</text>
        <text x={0} y={CN_TOP + 26} style={{ fontSize: 10 }}>gain above,</text>
        <text x={0} y={CN_TOP + 38} style={{ fontSize: 10 }}>loss below</text>
        <text x={0} y={MUT_TOP + 12} className="tl-lane-label">Mutations</text>
        <text x={0} y={MUT_TOP + 26} style={{ fontSize: 10 }}>{fmtNum(muts.length, 0)}</text>
        {CHROMS.map(([c, len]) => (
          <text key={c} x={(x(OFFSET[c]) + x(OFFSET[c] + len)) / 2} y={H - 4} textAnchor="middle" style={{ fontSize: 10 }}>
            {c}
          </text>
        ))}
        {labelRows.map(({ d, row }, i) => (
          <g key={`${d.gene}${i}`}>
            <line x1={x(d.g)} x2={x(d.g)} y1={MUT_TOP - 4} y2={MUT_TOP + MUT_H} stroke="var(--ink)" strokeWidth={0.6} strokeDasharray="2 2" />
            {row >= 0 && (
              <text x={x(d.g)} y={MUT_TOP - 7 - row * 11} textAnchor="middle" style={{ fill: 'var(--ink)', fontSize: 10.5, fontWeight: 500 }}>
                {d.gene}
              </text>
            )}
          </g>
        ))}
      </svg>
      {hover && (
        <div className="tl-tip mono" style={{ left: Math.min(hover.x + 12, width - 330), top: 4 }}>
          {hover.text}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ alterations, expression, immune */

function Alterations({ b }: { b: PatientBundle }) {
  const muts = b.drivers.filter((d) => PROTEIN.test(String(d.mutation_type)));
  const cna = b.copyNumber.filter((c) => c.is_driver_gene);
  const tests = b.biomarkers.filter((t) => str(t.gene));
  return (
    <div className="min-w-0">
      <div className="t-label mb-2">Driver gene alterations</div>
      <table className="tbl">
        <thead>
          <tr>
            <th>Gene</th>
            <th>Change</th>
            <th>Type</th>
            <th className="w-[110px]">Allele fraction</th>
          </tr>
        </thead>
        <tbody>
          {muts.slice(0, 14).map((m, i) => {
            const vaf = num(m.vaf);
            return (
              <tr key={`${m.gene}${i}`}>
                <td className="font-medium">{str(m.gene)}</td>
                <td className="mono">{str(m.protein_change)}</td>
                <td>
                  <span className="flex items-center gap-1.5">
                    <span className="swatch" style={{ background: typeColour(String(m.mutation_type)) }} />
                    {typeLabel(String(m.mutation_type))}
                  </span>
                </td>
                <td>
                  {vaf !== null && (
                    <span className="flex items-center gap-2">
                      <span className="hbar w-[60px]">
                        <span style={{ left: 0, width: `${vaf * 100}%`, background: 'var(--ink-2)' }} />
                      </span>
                      <span className="num t-muted">{Math.round(vaf * 100)}%</span>
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
          {cna.slice(0, 10).map((c) => (
            <tr key={`cn${c.gene}`}>
              <td className="font-medium">{str(c.gene)}</td>
              <td className="mono">{num(c.alteration) === 2 ? 'amp' : 'del'}</td>
              <td>
                <span className="flex items-center gap-1.5">
                  <span className="swatch" style={{ background: num(c.alteration) === 2 ? 'var(--c-gain)' : 'var(--c-loss)' }} />
                  {str(c.call)}
                </span>
              </td>
              <td />
            </tr>
          ))}
          {muts.length + cna.length === 0 && (
            <tr>
              <td colSpan={4} className="t-faint">No protein-changing mutation in a known driver gene.</td>
            </tr>
          )}
        </tbody>
      </table>
      {muts.length > 14 && <div className="t-faint mt-1.5 text-[11.5px]">{muts.length - 14} more driver-gene mutations not shown.</div>}
      {tests.length > 0 && (
        <div className="mt-4">
          <div className="t-label mb-1.5">Confirmed by clinical testing</div>
          {tests.map((t, i) => (
            <div key={i} className="flex items-baseline gap-2 py-0.5 text-[12.5px]">
              <span className="swatch sw-clinical" />
              <span className="font-medium">{str(t.gene)}</span>
              <span>{str(t.result)}</span>
              <span className="t-faint">
                {[str(t.method), str(t.intensity), str(t.exon) && `exon ${str(t.exon)}`, str(t.variant_type)].filter(Boolean).join(' · ')}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Expression({ b, cancer }: { b: PatientBundle; cancer: string }) {
  const z = new Map(b.expression.map((e) => [String(e.gene), num(e.z_score)]));
  return (
    <div className="min-w-0">
      <div className="t-label mb-2">RNA expression against other {cancer.toLowerCase()} tumours (z-score)</div>
      <div className="space-y-4">
        {EXPRESSION_GROUPS.map((g) => (
          <div key={g.title}>
            <div className="text-[12.5px] font-medium">
              {g.title}
              {g.note && <span className="t-faint font-normal"> · {g.note}</span>}
            </div>
            <div className="mt-1 space-y-[3px]">
              {g.genes.map(([gene, label]) => {
                const v = z.get(gene);
                if (v === undefined || v === null) return null;
                const c = Math.max(-3, Math.min(3, v));
                const strong = Math.abs(v) >= 2;
                return (
                  <div key={gene} className="grid grid-cols-[92px_1fr_40px] items-center gap-2 text-[12px]">
                    <span className={strong ? 'font-medium' : 't-muted'} title={gene}>{label}</span>
                    <span className="relative h-[10px]">
                      <span className="absolute left-1/2 top-0 h-full w-px" style={{ background: 'var(--line-strong)' }} />
                      <span
                        className="absolute top-[1px] h-[8px]"
                        style={{
                          left: c >= 0 ? '50%' : `${50 + (c / 3) * 50}%`,
                          width: `${(Math.abs(c) / 3) * 50}%`,
                          background: c >= 0 ? (strong ? 'var(--c-gen)' : 'var(--ink-3)') : strong ? 'var(--c-loss)' : 'var(--line-strong)',
                        }}
                      />
                    </span>
                    <span className="num t-muted text-right">{Math.abs(v) < 0.05 ? '0.0' : `${v > 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const CELL_GROUPS: { label: string; colour: string; cells: string[] }[] = [
  { label: 'CD8 T cells', colour: '#1d7a6f', cells: ['T Cells CD8'] },
  { label: 'CD4 T cells', colour: '#5cae9f', cells: ['T Cells CD4 Naive', 'T Cells CD4 Memory Resting', 'T Cells CD4 Memory Activated', 'T Cells Follicular Helper'] },
  { label: 'Regulatory T', colour: '#a7d3c9', cells: ['T Cells Regulatory Tregs', 'T Cells gamma delta'] },
  { label: 'B and plasma', colour: '#8a3f86', cells: ['B Cells Naive', 'B Cells Memory', 'Plasma Cells'] },
  { label: 'NK cells', colour: '#c58ac0', cells: ['NK Cells Resting', 'NK Cells Activated'] },
  { label: 'Macrophages M2', colour: '#9a6a2f', cells: ['Macrophages M2'] },
  { label: 'Macrophages M0/M1', colour: '#cfa36a', cells: ['Macrophages M0', 'Macrophages M1', 'Monocytes'] },
  { label: 'Dendritic, mast, granulocytes', colour: '#a39f93', cells: ['Dendritic Cells Resting', 'Dendritic Cells Activated', 'Mast Cells Resting', 'Mast Cells Activated', 'Eosinophils', 'Neutrophils'] },
];

function Immune({ b, prof }: { b: PatientBundle; prof: Row }) {
  const frac = new Map(b.immuneCells.map((c) => [String(c.cell_type), num(c.fraction) ?? 0]));
  const groups = CELL_GROUPS.map((g) => ({ ...g, value: g.cells.reduce((s, c) => s + (frac.get(c) ?? 0), 0) }));
  const total = groups.reduce((s, g) => s + g.value, 0) || 1;
  const leuk = num(prof.leukocyte_fraction);
  const til = num(b.slide?.til_positive_fraction);
  return (
    <div className="min-w-0">
      <div className="t-label mb-2">Tumour immune microenvironment</div>
      <dl className="kv">
        <dt>Leukocyte fraction</dt>
        <dd className="num">{leuk !== null ? `${fmtNum(leuk * 100, 0)}% of cells (methylation)` : '–'}</dd>
        <dt>Lymphocytes on slide</dt>
        <dd className="num">{til !== null ? `${fmtNum(til * 100, 1)}% of tissue tiles (AI, pathology)` : '–'}</dd>
        <dt>T-cell clones</dt>
        <dd className="num">{num(prof.tcr_richness) !== null ? `${fmtNum(num(prof.tcr_richness), 0)} distinct TCRs in tumour RNA` : '–'}</dd>
      </dl>
      {frac.size > 0 && (
        <>
          <div className="mt-4 text-[12.5px] font-medium">Immune cell mix (CIBERSORT, share of leukocytes)</div>
          <div className="mt-1.5 flex h-[14px] w-full overflow-hidden">
            {groups.map((g) => (
              <span key={g.label} title={`${g.label}: ${fmtNum((g.value / total) * 100, 0)}%`} style={{ width: `${(g.value / total) * 100}%`, background: g.colour }} />
            ))}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11.5px]">
            {groups.map((g) => (
              <span key={g.label} className="flex items-center gap-1.5">
                <span className="swatch" style={{ background: g.colour }} />
                <span className="t-muted truncate">{g.label}</span>
                <span className="num ml-auto">{fmtNum((g.value / total) * 100, 0)}%</span>
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function GenomicsSection({ b }: { b: PatientBundle }) {
  const prof = b.profile ?? {};
  const ref = useMemo(
    () => Object.fromEntries(b.reference.map((r) => [String(r.metric), { n: num(r.n) ?? 0, q: parseJson<number[]>(r.quantiles_json, []) }])),
    [b]
  );
  const cancer = str(b.patient.cancer_type) ?? 'same-type';
  const n = num(prof.cohort_size) ?? ref.TMB_NONSYNONYMOUS?.n ?? 0;
  const counts = b.mutationCounts.map((c) => ({ t: String(c.mutation_type), n: num(c.n) ?? 0 }));
  const protein = counts.filter((c) => PROTEIN.test(c.t)).reduce((s, c) => s + c.n, 0);
  const msi = str(prof.msi_status);
  return (
    <div>
      <div className="sec-head">
        <h2 className="sec-title">Somatic Mutations &amp; Molecular Drivers</h2>
        <span className="sec-note">
          Whole-exome sequencing, copy number and RNA of the same tumour sample as the slide, compared with {fmtNum(n, 0)} other{' '}
          {cancer.toLowerCase()} tumours in TCGA.
        </span>
        <span className="src ml-auto"><span className="swatch sw-genomics" />genomics_lakehouse</span>
      </div>
      <div className="grid grid-cols-2 gap-x-10 gap-y-5 md:grid-cols-3 xl:grid-cols-6">
        <Metric
          label="Tumour mutation burden"
          value={fmtNum(num(prof.tmb), 1)}
          unit="per Mb"
          pct={num(prof.tmb_percentile)}
          quantiles={ref.TMB_NONSYNONYMOUS?.q}
          raw={num(prof.tmb)}
          log
          note={(num(prof.tmb) ?? 0) >= 10 ? 'TMB-high (10 or more)' : undefined}
        />
        <Metric label="Mutations" value={fmtNum(num(prof.mutation_count), 0)} unit="somatic" note={`${fmtNum(protein, 0)} change a protein`} />
        <Metric
          label="Microsatellites"
          value={msi === 'MSI-high' ? 'MSI-high' : 'Stable'}
          note={`MANTIS score ${fmtNum(num(prof.msi_mantis), 2)} (0.4 or more is unstable)`}
        />
        <Metric
          label="Genome altered"
          value={`${fmtNum((num(prof.fraction_genome_altered) ?? 0) * 100, 0)}%`}
          pct={num(prof.fga_percentile)}
          quantiles={ref.FRACTION_GENOME_ALTERED?.q}
          raw={num(prof.fraction_genome_altered)}
        />
        <Metric label="Aneuploidy" value={fmtNum(num(prof.aneuploidy_score), 0)} unit="arms" quantiles={ref.ANEUPLOIDY_SCORE?.q} raw={num(prof.aneuploidy_score)} />
        <Metric label="HRD score" value={fmtNum(num(prof.hrd_score), 0)} note="42 or more suggests HR deficiency" />
      </div>
      <div className="t-faint mt-2 flex items-center gap-2 text-[11.5px]">
        <span className="inline-block h-[10px] w-[10px] rounded-full" style={{ background: 'var(--accent)' }} />
        this patient on the distribution of {cancer.toLowerCase()} tumours in TCGA; the darker tick is the median
      </div>

      <div className="mt-7">
        <div className="mb-1 flex items-baseline gap-3">
          <div className="text-[13px] font-medium">Whole genome</div>
          <div className="t-faint text-[11.5px]">
            Top: copy number by segment. Bottom: every somatic mutation, placed by its distance to the previous one; tight clusters
            sit low.
          </div>
        </div>
        <GenomePlot b={b} />
        <div className="t-faint mt-1 flex flex-wrap gap-x-4 text-[11.5px]">
          {[
            ['Missense', 'var(--c-good)'],
            ['Truncating', 'var(--ink)'],
            ['In-frame', '#b07a35'],
            ['Silent or non-coding', 'var(--ink-3)'],
          ].map(([l, c]) => (
            <span key={l} className="flex items-center gap-1.5">
              <span className="inline-block h-[8px] w-[8px] rounded-full" style={{ background: c }} />
              {l}
            </span>
          ))}
          <span className="flex items-center gap-1.5"><span className="swatch" style={{ background: 'var(--c-gain)' }} />Gain</span>
          <span className="flex items-center gap-1.5"><span className="swatch" style={{ background: 'var(--c-loss)' }} />Loss</span>
        </div>
      </div>

      <div className="mt-8 grid gap-x-12 gap-y-8 xl:grid-cols-3">
        <Alterations b={b} />
        <Expression b={b} cancer={cancer} />
        <Immune b={b} prof={prof} />
      </div>
    </div>
  );
}
