import { DRAG_MODE, MULTIPLANAR_TYPE, Niivue, SHOW_RENDER, SLICE_TYPE } from '@niivue/niivue';
import OpenSeadragon from 'openseadragon';
import { memo, useEffect, useMemo, useRef, useState } from 'react';

import {
  fetchDataMap,
  num,
  str,
  type FileAccess,
  type PatientBundle,
} from '@/lib/api';
import { fmtBytes, fmtMonth, fmtNum } from '@/lib/format';
import { LOCAL_DATA } from '@/lib/localMode';

/**
 * Safely constructs a file URL ensuring:
 * 1. The relative path contains no path traversal sequences ('../' or '..\\')
 * 2. The relative path does not use non-allowed schemes (javascript:, data:, file:, http:, etc.)
 * 3. Base URL uses allowed scheme (http: or https:)
 */
export function buildSafeAssetUrl(access: FileAccess | undefined | null, path: string): string {
  if (!access || !access.baseUrl) {
    throw new Error('Invalid file access: missing baseUrl');
  }
  if (!path || typeof path !== 'string') {
    throw new Error('Invalid path: path must be a non-empty string');
  }

  // Reject path traversal sequences
  if (
    path.includes('..') ||
    /(\/|^)\.\.(\/|$)/.test(path) ||
    path.includes('\\..') ||
    path.includes('..\\')
  ) {
    throw new Error(`Path traversal sequence detected in asset path: "${path}"`);
  }

  // Reject non-allowed schemes in relative path
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(path)) {
    throw new Error(`Non-allowed scheme detected in asset path: "${path}"`);
  }

  // Normalize path removing leading slashes
  const cleanPath = path.replace(/^\/+/, '');

  // Verify access.baseUrl protocol if absolute
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(access.baseUrl)) {
    try {
      const url = new URL(access.baseUrl);
      if (!['http:', 'https:'].includes(url.protocol)) {
        throw new Error(`Non-allowed scheme in baseUrl: "${access.baseUrl}"`);
      }
    } catch (e) {
      if (e instanceof Error && e.message.includes('Non-allowed scheme')) throw e;
      // If parsing fails for non-standard local URL, continue
    }
  }

  return access.query ? `${access.baseUrl}/${cleanPath}?${access.query}` : `${access.baseUrl}/${cleanPath}`;
}

const TRUNCATING = /Nonsense|Frame_Shift|Splice|Nonstop|Translation_Start/;
const PROTEIN = /Missense|Nonsense|Frame_Shift|In_Frame|Splice_Site|Nonstop|Translation_Start/;

function typeColour(t: string): string {
  if (TRUNCATING.test(t)) return 'var(--ink)';
  if (/Missense/.test(t)) return 'var(--c-good)';
  if (/In_Frame/.test(t)) return '#b07a35';
  return 'var(--ink-3)';
}

function typeLabel(t: string): string {
  return t
    .replace(/_Mutation$/, '')
    .replace(/_/g, ' ')
    .replace('Frame Shift', 'Frameshift')
    .replace(/^(\w)/, (m) => m.toUpperCase());
}

type RadView = 'render' | 'multiplanar' | 'axial';
type Preset = { id: string; label: string; colormap: string; calMin?: number; calMax?: number; glass?: boolean };

const CT_PRESETS: Preset[] = [
  { id: 'contrast', label: 'Vessels and bone', colormap: 'ct_w_contrast', calMin: 50, calMax: 1000 },
  { id: 'bone', label: 'Bone', colormap: 'ct_bones', calMin: 180, calMax: 600 },
  { id: 'air', label: 'Air (lungs, bowel)', colormap: 'ct_lung_glass', calMin: -1000, calMax: -300, glass: true },
  { id: 'soft', label: 'Soft tissue', colormap: 'gray', calMin: -160, calMax: 240 },
];

const MAGS = [1.25, 5, 10, 20, 40];

/* ------------------------------------------------------------------ Patient summary bar */

function SummaryHeaderBar({ b }: { b: PatientBundle }) {
  const p = b.patient;
  const prof = b.profile ?? {};
  const tnm = [str(p.t_stage), str(p.n_stage), str(p.m_stage)].filter(Boolean).join(' ');
  const stage = str(p.stage) ? `stage ${str(p.stage)?.replace(/^Stage\s+/i, '')}` : null;
  const site = str(p.tissue_of_origin) ?? '';
  const disease = `${str(p.cancer_type) ?? ''}${stage ? `, ${stage}` : ''}${tnm ? ` (${tnm})` : ''}${site ? `, ${site}` : ''}`;
  const sex = str(p.sex)?.toLowerCase() === 'female' ? 'woman' : 'man';
  const person = [`${num(p.age_at_diagnosis)}-year-old ${sex} at diagnosis`, str(p.race), str(p.country)]
    .filter(Boolean)
    .join(' · ');
  const days = num(p.days_to_last_contact) ?? 0;
  const isDead = str(p.vital_status) === 'Dead';
  const outcome = isDead
    ? { label: 'Died', value: `${num(p.days_to_death) ?? 0} days after diagnosis`, alert: true }
    : { label: 'Last contact', value: `Alive, ${days} days after diagnosis`, alert: false };

  return (
    <div className="mb-6 rounded-lg border hair bg-[var(--card)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[18px] font-medium leading-snug">{disease}</div>
          <div className="t-muted mt-1 text-[13px]">{person}</div>
        </div>
        <div className="flex flex-wrap items-center gap-6 text-[12.5px]">
          <div>
            <span className="t-faint mr-1.5">Diagnosed:</span>
            <span>{fmtMonth(str(p.diagnosis_date))}</span>
          </div>
          <div>
            <span className="t-faint mr-1.5">{outcome.label}:</span>
            <span style={{ color: outcome.alert ? 'var(--c-alert)' : undefined }}>{outcome.value}</span>
          </div>
          <div>
            <span className="t-faint mr-1.5">Subtype:</span>
            <span className="mono">{str(prof.subtype)?.replace(/_/g, ' ') ?? '–'}</span>
          </div>
          <div>
            <span className="t-faint mr-1.5">TMB:</span>
            <span className="num font-medium">{fmtNum(num(prof.tmb), 1)} / Mb</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Streaming Badge */

function StreamBadge({ sizeLabel }: { sizeLabel: string }) {
  const prefix = LOCAL_DATA ? 'Cataloged in OneLake: ' : 'Streamed from OneLake, never copied: ';
  const title = LOCAL_DATA
    ? 'Cataloged in Microsoft OneLake; rendered from local cache without dataset replication'
    : 'Streamed on demand from Microsoft OneLake without local dataset replication';

  return (
    <div
      className="inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-[11px] mono font-medium shadow-xs"
      style={{
        background: 'var(--well-subtle, rgba(0, 0, 0, 0.03))',
        borderColor: 'var(--line)',
        color: 'var(--ink)',
      }}
      title={title}
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
      <span>
        {prefix}<strong>{sizeLabel}</strong>
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ Fallback Card */

function LocalFallbackCard({
  modalityName,
  pills,
}: {
  modalityName: string;
  pills: { label: string; value: string }[];
}) {
  return (
    <div className="flex flex-col justify-between rounded-md border hair bg-[var(--well,rgba(0,0,0,0.02))] p-5 min-h-[340px]">
      <div>
        <div className="mb-3 flex items-center gap-2">
          <span className="inline-flex h-2 w-2 rounded-full bg-amber-500" />
          <span className="text-[12.5px] font-semibold uppercase tracking-wider text-[var(--ink-2)]">
            {modalityName} Catalog Metadata
          </span>
        </div>
        <div className="mb-5 rounded border border-amber-500/20 bg-amber-50/70 p-3 text-[12px] leading-relaxed text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <strong>Local mode: pixel files not downloaded</strong> (run{' '}
          <code className="rounded bg-amber-200/50 px-1 py-0.5 mono text-[11px] dark:bg-amber-900/50">
            pipeline/download_data.py
          </code>{' '}
          or{' '}
          <code className="rounded bg-amber-200/50 px-1 py-0.5 mono text-[11px] dark:bg-amber-900/50">
            pipeline/download_slides.py
          </code>{' '}
          to view pixels).
        </div>
      </div>

      <div>
        <div className="t-label mb-2 text-[11px]">Cataloged asset properties</div>
        <div className="flex flex-wrap gap-2">
          {pills.map((p, idx) => (
            <div
              key={idx}
              className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11.5px] mono"
              style={{
                background: 'var(--bg)',
                borderColor: 'var(--line)',
                color: 'var(--ink)',
              }}
            >
              <span className="t-faint">{p.label}:</span>
              <span className="font-medium truncate max-w-[200px]" title={p.value}>
                {p.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Radiology Pane */

function RadiologyHeroPane({ b }: { b: PatientBundle }) {
  const seriesList = b.radiologySeries ?? [];
  const series = seriesList[0] ?? null;
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const nvRef = useRef<Niivue | null>(null);

  const [view, setView] = useState<RadView>('render');
  const [presetId, setPresetId] = useState('contrast');
  const [pixelStatus, setPixelStatus] = useState<'checking' | 'available' | 'missing'>('checking');
  const [webglError, setWebglError] = useState(false);

  const volBytes = num(series?.volume_bytes);
  const rawBytes = num(series?.raw_bytes);
  const sizeBadge = `${fmtBytes(volBytes, 1)} volume (${fmtBytes(rawBytes, 1)} raw DICOM)`;

  // Check file presence
  useEffect(() => {
    if (!series || !series.volume_path) {
      setPixelStatus('missing');
      return;
    }
    let active = true;
    try {
      const url = buildSafeAssetUrl(b.access.radiology, String(series.volume_path));
      fetch(url, { method: 'HEAD' })
        .then((res) => {
          if (!active) return;
          setPixelStatus(res.ok ? 'available' : 'missing');
        })
        .catch(() => {
          if (!active) return;
          setPixelStatus('missing');
        });
    } catch {
      setPixelStatus('missing');
    }
    return () => {
      active = false;
    };
  }, [series, b.access.radiology]);

  // Lifecycle & Niivue setup
  useEffect(() => {
    if (pixelStatus !== 'available' || !canvasRef.current || !series) return;

    let nv: Niivue | null = null;
    try {
      nv = new Niivue({
        backColor: [0.05, 0.05, 0.047, 1],
        show3Dcrosshair: false,
        crosshairColor: [1, 0.561, 0.322, 1],
        isOrientCube: true,
        multiplanarShowRender: SHOW_RENDER.ALWAYS,
        multiplanarLayout: MULTIPLANAR_TYPE.GRID,
        dragMode: DRAG_MODE.pan,
        dragAndDropEnabled: false,
        loadingText: '',
      });
      nvRef.current = nv;
      void nv.attachToCanvas(canvasRef.current);

      const volUrl = buildSafeAssetUrl(b.access.radiology, String(series.volume_path));
      void nv
        .loadVolumes([{ url: volUrl, name: 'volume.nii.gz', colormap: 'ct_w_contrast' }])
        .then(() => {
          if (nvRef.current && nv) {
            nv.setSliceType(view === 'render' ? SLICE_TYPE.RENDER : SLICE_TYPE.MULTIPLANAR);
          }
        })
        .catch(() => {
          setPixelStatus('missing');
        });
    } catch {
      setWebglError(true);
      setPixelStatus('missing');
    }

    return () => {
      if (nvRef.current) {
        try {
          const destroyable = nvRef.current as unknown as { destroy?: () => void };
          if (typeof destroyable.destroy === 'function') {
            destroyable.destroy();
          }
        } catch {
          // ignore
        }
        nvRef.current = null;
      }
    };
  }, [pixelStatus, series, b.access.radiology, view]);
  return (
    <div className="flex flex-col min-w-0 w-full rounded-lg border hair bg-[var(--card)] p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--ink)]">Radiology</h2>
          <div className="t-muted text-[12px]">3D CT anatomical scan</div>
        </div>
        {series && <StreamBadge sizeLabel={sizeBadge} />}
      </div>

      {!series ? (
        <div className="flex h-[360px] items-center justify-center rounded-md border hair bg-[var(--well,rgba(0,0,0,0.02))] p-6 text-center text-[13px] t-muted">
          No radiology series available for this patient
        </div>
      ) : webglError ? (
        <div className="flex flex-col justify-center rounded-md border hair bg-[var(--well,rgba(0,0,0,0.02))] p-6 text-center text-[13px] t-muted min-h-[340px]">
          <div className="mb-2 font-medium text-[var(--c-alert)]">WebGL is unavailable in this environment</div>
          <div className="text-[12px] t-faint">Series UID: {str(series.series_uid)}</div>
        </div>
      ) : pixelStatus === 'available' ? (
        <div className="flex flex-col gap-2">
          <div className="toolbar flex items-center justify-between text-[12px]">
            <div className="seg" role="group" aria-label="View mode">
              <button aria-pressed={view === 'render'} onClick={() => setView('render')}>
                3D
              </button>
              <button aria-pressed={view === 'multiplanar'} onClick={() => setView('multiplanar')}>
                MPR
              </button>
            </div>
            <select
              className="field !h-[28px] !w-auto text-[12px]"
              value={presetId}
              onChange={(e) => setPresetId(e.target.value)}
              aria-label="Window preset"
            >
              {CT_PRESETS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div className="well well-dark relative h-[340px] w-full rounded overflow-hidden">
            <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
          </div>
        </div>
      ) : (
        <LocalFallbackCard
          modalityName="Radiology (3D CT)"
          pills={[
            { label: 'Series UID', value: str(series.series_uid) ?? '–' },
            { label: 'Modality', value: str(series.modality) ?? 'CT' },
            {
              label: 'Dimensions',
              value: `${num(series.images) ?? 0} slices${num(series.slice_thickness_mm) ? `, ${num(series.slice_thickness_mm)} mm` : ''}`,
            },
            { label: 'Cataloged file size', value: sizeBadge },
          ]}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Pathology Pane */

function PathologyHeroPane({ b }: { b: PatientBundle }) {
  const slide = b.slide ?? b.slides?.[0] ?? null;
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null);

  const [pixelStatus, setPixelStatus] = useState<'checking' | 'available' | 'missing'>('checking');
  const slideBytes = num(slide?.raw_bytes);
  const sizeBadge = `${fmtBytes(slideBytes, 1)} slide`;

  // Check file presence
  useEffect(() => {
    if (!slide) {
      setPixelStatus('missing');
      return;
    }
    let active = true;
    try {
      const sid = str(slide.slide_id);
      const url = buildSafeAssetUrl(b.access.slide, `slides/${sid}/slide_files/0/0_0.jpg`);
      fetch(url, { method: 'HEAD' })
        .then((res) => {
          if (!active) return;
          setPixelStatus(res.ok ? 'available' : 'missing');
        })
        .catch(() => {
          if (!active) return;
          setPixelStatus('missing');
        });
    } catch {
      setPixelStatus('missing');
    }
    return () => {
      active = false;
    };
  }, [slide, b.access.slide]);

  // Lifecycle & OpenSeadragon setup
  useEffect(() => {
    if (pixelStatus !== 'available' || !hostRef.current || !slide) return;

    let viewer: OpenSeadragon.Viewer | null = null;
    try {
      const sid = str(slide.slide_id);
      const source = new OpenSeadragon.TileSource({
        width: num(slide.width)!,
        height: num(slide.height)!,
        tileSize: 1022,
        tileOverlap: 1,
        minLevel: 0,
        maxLevel: (num(slide.levels) ?? 1) - 1,
      } as unknown as OpenSeadragon.TileSourceOptions);

      source.getTileUrl = (level: number, x: number, y: number) =>
        buildSafeAssetUrl(b.access.slide, `slides/${sid}/slide_files/${level}/${x}_${y}.jpg`);

      viewer = OpenSeadragon({
        element: hostRef.current,
        tileSources: source as unknown as OpenSeadragon.TileSourceOptions,
        showNavigationControl: false,
        showNavigator: true,
        navigatorPosition: 'BOTTOM_RIGHT',
        navigatorSizeRatio: 0.18,
        animationTime: 1.0,
        springStiffness: 6.0,
        timeout: 60_000,
        gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
        crossOriginPolicy: 'Anonymous',
      });
      viewerRef.current = viewer;

      viewer.addHandler('open-failed', () => {
        setPixelStatus('missing');
      });
      viewer.addHandler('tile-load-failed', () => {
        setPixelStatus('missing');
      });
    } catch {
      setPixelStatus('missing');
    }

    return () => {
      if (viewerRef.current) {
        try {
          viewerRef.current.destroy();
        } catch {
          // ignore
        }
        viewerRef.current = null;
      }
    };
  }, [pixelStatus, slide, b.access.slide]);

  return (
    <div className="flex flex-col min-w-0 w-full rounded-lg border hair bg-[var(--card)] p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--ink)]">Pathology</h2>
          <div className="t-muted text-[12px]">H&E whole-slide microscopy</div>
        </div>
        {slide && <StreamBadge sizeLabel={sizeBadge} />}
      </div>

      {!slide ? (
        <div className="flex h-[360px] items-center justify-center rounded-md border hair bg-[var(--well,rgba(0,0,0,0.02))] p-6 text-center text-[13px] t-muted">
          No whole-slide imaging available for this patient
        </div>
      ) : pixelStatus === 'available' ? (
        <div className="flex flex-col gap-2">
          <div className="toolbar flex items-center gap-1.5 text-[12px]">
            <div className="seg" role="group" aria-label="Magnification">
              {MAGS.map((m) => (
                <button
                  key={m}
                  onClick={() => {
                    if (viewerRef.current) {
                      const item = viewerRef.current.world.getItemAt(0);
                      if (item) {
                        const objective = num(slide.objective_power) ?? 40;
                        viewerRef.current.viewport.zoomTo(item.imageToViewportZoom(m / objective));
                      }
                    }
                  }}
                >
                  {m}×
                </button>
              ))}
            </div>
            <button
              className="btn btn-sm ml-auto"
              onClick={() => viewerRef.current?.viewport.goHome()}
              title="Reset zoom"
            >
              Reset
            </button>
          </div>
          <div ref={hostRef} className="well relative h-[340px] w-full rounded overflow-hidden" />
        </div>
      ) : (
        <LocalFallbackCard
          modalityName="Pathology (H&E Slide)"
          pills={[
            { label: 'Slide ID', value: str(slide.slide_id) ?? str(slide.barcode) ?? '–' },
            { label: 'Modality', value: slide.role === 'frozen' ? 'Frozen H&E section' : 'Diagnostic H&E slide' },
            {
              label: 'Dimensions',
              value: `${num(slide.width) ?? 0} × ${num(slide.height) ?? 0} px (${num(slide.levels) ?? 0} levels)`,
            },
            { label: 'Cataloged file size', value: sizeBadge },
          ]}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Genomics Pane */

function GenomicsHeroPane({
  b,
  genomicsDeltaBytes,
}: {
  b: PatientBundle;
  genomicsDeltaBytes?: number;
}) {
  const drivers = b.drivers ?? [];
  const prof = b.profile ?? {};

  const [deltaBytes, setDeltaBytes] = useState<number>(() => genomicsDeltaBytes ?? 48200);

  useEffect(() => {
    if (genomicsDeltaBytes !== undefined) {
      setDeltaBytes(genomicsDeltaBytes);
      return;
    }
    let active = true;
    fetchDataMap()
      .then((map) => {
        if (!active) return;
        const genomicsSilo = map.silos.find((s) => s.silo === 'genomics');
        if (genomicsSilo?.items) {
          const total = genomicsSilo.items
            .filter((i) => i.kind === 'table')
            .reduce((sum, item) => sum + (num(item.bytes) ?? 0), 0);
          if (total > 0) setDeltaBytes(total);
        }
      })
      .catch(() => {
        // keep initial default
      });
    return () => {
      active = false;
    };
  }, [genomicsDeltaBytes]);

  const proteinDrivers = useMemo(
    () => drivers.filter((d) => PROTEIN.test(String(d.mutation_type ?? ''))),
    [drivers]
  );

  const sizeBadge = `${fmtBytes(deltaBytes, 1)} Delta`;

  return (
    <div className="flex flex-col min-w-0 w-full rounded-lg border hair bg-[var(--card)] p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--ink)]">Genomics</h2>
          <div className="t-muted text-[12px]">Somatic driver alterations</div>
        </div>
        <StreamBadge sizeLabel={sizeBadge} />
      </div>

      {drivers.length === 0 && proteinDrivers.length === 0 ? (
        <div className="flex flex-col justify-center rounded-md border hair bg-[var(--well,rgba(0,0,0,0.02))] p-6 text-center text-[13px] t-muted min-h-[340px]">
          <p className="text-[14px] font-semibold text-[var(--ink)]">No somatic driver mutations detected</p>
          <div className="mt-2 text-[12px] t-faint">
            Molecular subtype: <span className="mono">{str(prof.subtype)?.replace(/_/g, ' ') ?? '–'}</span> · TMB:{' '}
            <span className="num">{fmtNum(num(prof.tmb), 1)} / Mb</span>
          </div>
        </div>
      ) : (
        <div className="flex flex-col justify-between rounded-md border hair bg-[var(--well,rgba(0,0,0,0.02))] p-4 min-h-[340px]">
          <div className="overflow-x-auto">
            <table className="tbl w-full text-left text-[12.5px]">
              <thead>
                <tr>
                  <th className="py-1">Gene</th>
                  <th className="py-1">Change</th>
                  <th className="py-1">Type</th>
                  <th className="py-1 text-right">VAF</th>
                </tr>
              </thead>
              <tbody>
                {proteinDrivers.map((m, i) => {
                  const vaf = num(m.vaf);
                  return (
                    <tr key={`${str(m.gene)}-${i}`} className="hover:bg-[var(--line-subtle)]">
                      <td className="font-semibold text-[var(--ink)]">{str(m.gene)}</td>
                      <td className="mono text-[12px]">{str(m.protein_change) ?? '–'}</td>
                      <td>
                        <span className="inline-flex items-center gap-1.5 text-[11.5px]">
                          <span
                            className="inline-block h-2 w-2 rounded-full"
                            style={{ background: typeColour(String(m.mutation_type)) }}
                          />
                          {typeLabel(String(m.mutation_type))}
                        </span>
                      </td>
                      <td className="text-right">
                        {vaf !== null && (
                          <div className="inline-flex items-center justify-end gap-1.5">
                            <span className="hbar w-[44px]">
                              <span style={{ left: 0, width: `${Math.min(100, vaf * 100)}%`, background: 'var(--ink-2)' }} />
                            </span>
                            <span className="num text-[11.5px] font-medium">{Math.round(vaf * 100)}%</span>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="hair mt-4 border-t pt-3 flex flex-wrap items-center justify-between gap-2 text-[12px]">
            <div>
              <span className="t-faint mr-1">Molecular Subtype:</span>
              <span className="mono font-medium">{str(prof.subtype)?.replace(/_/g, ' ') ?? '–'}</span>
            </div>
            <div>
              <span className="t-faint mr-1">TMB:</span>
              <span className="num font-medium">{fmtNum(num(prof.tmb), 1)} / Mb</span>
            </div>
            <div>
              <span className="t-faint mr-1">Total Somatic:</span>
              <span className="num font-medium">{fmtNum(num(prof.mutation_count), 0)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Main MultimodalHero Component */

export const MultimodalHero = memo(function MultimodalHero({
  b,
  genomicsDeltaBytes,
}: {
  b: PatientBundle;
  genomicsDeltaBytes?: number;
}) {
  return (
    <div className="multimodal-hero-container w-full min-w-0">
      <SummaryHeaderBar b={b} />

      <div className="grid grid-cols-1 min-[1200px]:grid-cols-3 gap-6 items-start w-full min-w-0">
        <RadiologyHeroPane b={b} />
        <PathologyHeroPane b={b} />
        <GenomicsHeroPane b={b} genomicsDeltaBytes={genomicsDeltaBytes} />
      </div>
    </div>
  );
});
