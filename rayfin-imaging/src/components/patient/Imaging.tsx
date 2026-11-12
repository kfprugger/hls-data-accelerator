import { DRAG_MODE, MULTIPLANAR_TYPE, Niivue, SHOW_RENDER, SLICE_TYPE } from '@niivue/niivue';
import OpenSeadragon from 'openseadragon';
import { useEffect, useMemo, useRef, useState } from 'react';

import { Scrubber, type ScrubItem } from '@/components/Scrubber';
import { fileUrl, num, parseJson, str, type FileAccess, type PatientBundle, type Row } from '@/lib/api';
import { fmtBytes, fmtDate, fmtDay, fmtMs, fmtNum } from '@/lib/format';
import { STORE_NAME } from '@/lib/localMode';

/* ================================================================== Pathology */

type Hotspot = { x: number; y: number; kind: string };

interface SlideStatus {
  magnification: number | null;
  umPerPx: number | null;
  tiles: number;
  firstTileMs: number | null;
  touring: boolean;
}

const MAGS = [1.25, 5, 10, 20, 40];

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const t = window.setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      window.clearTimeout(t);
      reject(new DOMException('aborted', 'AbortError'));
    });
  });
}

function niceScale(umPerPx: number): { um: number; px: number } {
  const target = umPerPx * 110;
  const steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000];
  const um = steps.find((s) => s >= target) ?? 10000;
  return { um, px: um / umPerPx };
}

/** Short name for a slide on the scrubber: section code and what it shows. */
function slideTick(s: Row): string {
  if (s.role === 'diagnostic') return 'DX1 · diagnostic';
  const section = str(s.section) ?? '';
  const normal = /normal/i.test(str(s.sample_type) ?? '');
  const where = section.startsWith('T') ? 'top' : section.startsWith('B') ? 'bottom' : '';
  return `${section} · ${normal ? 'normal' : 'tumour'}${where ? ` ${where}` : ''}`;
}

export function PathologyPanel({
  slide,
  slides,
  onSlide,
  access,
  stepper = true,
}: {
  slide: Row;
  slides: Row[];
  onSlide: (id: string) => void;
  access: FileAccess;
  /** Draw the slide slider; off when the record's tab already steps through slides. */
  stepper?: boolean;
}) {
  const wellRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null);
  const tourRef = useRef<AbortController | null>(null);
  const accessRef = useRef(access);
  accessRef.current = access;
  const [status, setStatus] = useState<SlideStatus>({ magnification: null, umPerPx: null, tiles: 0, firstTileMs: null, touring: false });
  const [til, setTil] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const statusRef = useRef(status);
  const emit = (patch: Partial<SlideStatus>) => {
    statusRef.current = { ...statusRef.current, ...patch };
    setStatus(statusRef.current);
  };

  const sid = str(slide.slide_id)!;
  const objective = num(slide.objective_power) ?? 40;
  const mpp = num(slide.mpp);
  const hotspots = parseJson<Hotspot[]>(slide.hotspots, []);
  const hasTil = !!str(slide.til_overlay_path);

  // The lymphocyte map exists only for the diagnostic slide.
  useEffect(() => setTil(false), [slide.slide_id]);

  useEffect(() => {
    if (!hostRef.current) return;
    const opened = performance.now();
    statusRef.current = { magnification: null, umPerPx: null, tiles: 0, firstTileMs: null, touring: false };
    setStatus(statusRef.current);
    const source = new OpenSeadragon.TileSource({
      width: num(slide.width)!,
      height: num(slide.height)!,
      tileSize: 1022,
      tileOverlap: 1,
      minLevel: 0,
      maxLevel: num(slide.levels)! - 1,
    } as unknown as OpenSeadragon.TileSourceOptions);
    source.getTileUrl = (level: number, x: number, y: number) =>
      fileUrl(accessRef.current, `slides/${sid}/slide_files/${level}/${x}_${y}.jpg`);

    const viewer = OpenSeadragon({
      element: hostRef.current,
      tileSources: source as unknown as OpenSeadragon.TileSourceOptions,
      showNavigationControl: false,
      showNavigator: true,
      navigatorPosition: 'BOTTOM_RIGHT',
      navigatorSizeRatio: 0.16,
      navigatorAutoFade: false,
      navigatorBackground: '#faf9f5',
      navigatorBorderColor: '#141413',
      navigatorDisplayRegionColor: '#b0450a',
      animationTime: 1.2,
      springStiffness: 6.5,
      blendTime: 0.2,
      maxZoomPixelRatio: 2,
      minZoomImageRatio: 0.6,
      visibilityRatio: 0.4,
      imageLoaderLimit: 12,
      timeout: 60_000,
      gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
      crossOriginPolicy: 'Anonymous',
    });
    viewerRef.current = viewer;
    const update = () => {
      const item = viewer.world.getItemAt(0);
      if (!item) return;
      const z = item.viewportToImageZoom(viewer.viewport.getZoom(true));
      emit({ magnification: objective * z, umPerPx: mpp ? mpp / z : null });
    };
    viewer.addHandler('animation', update);
    viewer.addHandler('open', update);
    viewer.addHandler('resize', update);
    viewer.addHandler('tile-loaded', () =>
      emit({ tiles: statusRef.current.tiles + 1, firstTileMs: statusRef.current.firstTileMs ?? Math.round(performance.now() - opened) })
    );
    viewer.addHandler('canvas-press', () => tourRef.current?.abort());
    viewer.addHandler('canvas-scroll', () => tourRef.current?.abort());
    return () => {
      tourRef.current?.abort();
      viewer.destroy();
      viewerRef.current = null;
    };
    // The viewer is rebuilt only for a new slide; refreshed SAS tokens are read through accessRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  // AI lymphocyte map: one transparent PNG placed over the slide in viewport units.
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !hasTil) return;
    let item: OpenSeadragon.TiledImage | null = null;
    if (til) {
      viewer.addTiledImage({
        tileSource: { type: 'image', url: fileUrl(accessRef.current, str(slide.til_overlay_path)!) } as unknown as OpenSeadragon.TileSourceOptions,
        x: num(slide.til_x) ?? 0,
        y: num(slide.til_y) ?? 0,
        width: num(slide.til_width) ?? 1,
        opacity: 0.85,
        success: (e: { item: OpenSeadragon.TiledImage }) => {
          item = e.item;
        },
      } as unknown as OpenSeadragon.TiledImageOptions);
    }
    return () => {
      if (item && viewerRef.current) viewerRef.current.world.removeItem(item);
    };
  }, [til, sid, hasTil, slide]);

  const zoomTo = (imageZoom: number, center?: OpenSeadragon.Point) => {
    const viewer = viewerRef.current;
    const item = viewer?.world.getItemAt(0);
    if (!viewer || !item) return;
    if (center) viewer.viewport.panTo(center);
    viewer.viewport.zoomTo(item.imageToViewportZoom(imageZoom));
  };

  const tour = () => {
    tourRef.current?.abort();
    const controller = new AbortController();
    tourRef.current = controller;
    const stops = [...hotspots.filter((h) => h.kind === 'lymphocytes').slice(0, 2), ...hotspots.filter((h) => h.kind !== 'lymphocytes').slice(0, 2)];
    emit({ touring: true });
    void (async () => {
      try {
        viewerRef.current?.viewport.goHome();
        await sleep(1500, controller.signal);
        for (const h of stops) {
          const pt = new OpenSeadragon.Point(h.x, h.y);
          zoomTo(2.5 / objective, pt);
          await sleep(2500, controller.signal);
          zoomTo(10 / objective, pt);
          await sleep(2500, controller.signal);
          zoomTo(1, pt);
          await sleep(3800, controller.signal);
        }
        viewerRef.current?.viewport.goHome();
      } catch {
        // Tour cancelled.
      } finally {
        if (tourRef.current === controller) {
          tourRef.current = null;
          emit({ touring: false });
        }
      }
    })();
  };

  const scale = status.umPerPx ? niceScale(status.umPerPx) : null;
  const gp = ((num(slide.width) ?? 0) * (num(slide.height) ?? 0)) / 1e9;
  const tilPct = num(slide.til_positive_fraction);

  return (
    <div className="min-w-0">
      <div className="mb-2 flex items-baseline gap-3">
        <h3 className="text-[15px] font-medium">{slide.role === 'frozen' ? 'Frozen section, H&E' : 'Diagnostic H&E slide'}</h3>
        <span className="mono t-faint truncate">{str(slide.barcode)}</span>
        <span className="src ml-auto"><span className="swatch sw-pathology" />imaging_lakehouse/Files/slides</span>
      </div>
      {stepper && slides.length > 1 && (
        <Scrubber
          name="Slides"
          gutter={92}
          leading={
            <>
              <div className="text-[12px]" style={{ color: 'var(--ink)' }}>
                {slides.length} slides
              </div>
              <div>same specimen</div>
            </>
          }
          items={slides.map((s, i) => ({
            id: str(s.slide_id)!,
            at: 0.1 + (0.8 * i) / (slides.length - 1),
            label: `${slideTick(s)}: ${str(s.specimen)}`,
            tick: slideTick(s),
          }))}
          selected={str(slide.slide_id)}
          onSelect={onSlide}
        />
      )}
      <div className="t-muted mb-2 text-[12.5px]">
        {str(slide.specimen)}
        {slide.role === 'frozen' ? '. Frozen sections are cut from the same tissue that was sequenced; the diagnostic slide is the fixed, paraffin-embedded section.' : ''}
      </div>
      <div className="toolbar mb-2">
        <div className="seg" role="group" aria-label="Magnification">
          {MAGS.map((m) => (
            <button key={m} onClick={() => zoomTo(m / objective)} aria-pressed={!!status.magnification && Math.abs(status.magnification - m) / m < 0.08}>
              {m}×
            </button>
          ))}
        </div>
        <button className="btn" onClick={() => viewerRef.current?.viewport.goHome()}>Fit</button>
        {hasTil && (
          <button className="btn" aria-pressed={til} onClick={() => setTil((v) => !v)} style={til ? { borderColor: 'var(--ink)' } : undefined}>
            {til ? 'Hide' : 'Show'} AI lymphocyte map
          </button>
        )}
        <button className={status.touring ? 'btn btn-ink' : 'btn btn-primary'} onClick={() => (status.touring ? tourRef.current?.abort() : tour())}>
          {status.touring ? 'Stop tour' : 'Tour'}
        </button>
        <button className="btn ml-auto" onClick={() => setExpanded((v) => !v)}>{expanded ? 'Close' : 'Expand'}</button>
      </div>
      <div ref={wellRef} className={`well ${expanded ? 'expanded' : ''}`} style={{ height: expanded ? undefined : 560 }}>
        <div ref={hostRef} className="slide-canvas absolute inset-0" />
        {expanded && (
          <button className="btn absolute right-3 top-3 z-10" onClick={() => setExpanded(false)}>Close</button>
        )}
        {til && (
          <div className="overlay-legend">
            <div className="font-medium">Lymphocyte probability</div>
            <div className="mt-1 flex items-center gap-1.5">
              <span className="swatch" style={{ background: 'rgb(20,160,170)' }} /> low
              <span className="swatch ml-2" style={{ background: 'rgb(250,225,60)' }} /> high
            </div>
            <div className="mt-1 text-[10.5px]">50 µm grid · Stony Brook Inception-V4</div>
          </div>
        )}
        <div className="overlay-note">
          {status.magnification ? `${fmtNum(status.magnification, status.magnification < 10 ? 2 : 1)}×` : ''}
          {scale && (
            <span className="ml-3 inline-flex items-center gap-1.5 align-middle">
              <span style={{ display: 'inline-block', width: scale.px, height: 5, border: '1px solid #f1efe8', borderTop: 0 }} />
              {scale.um >= 1000 ? `${scale.um / 1000} mm` : `${scale.um} µm`}
            </span>
          )}
        </div>
      </div>
      <div className="t-faint mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
        <span className="num">{fmtNum(num(slide.width), 0)} × {fmtNum(num(slide.height), 0)} px ({fmtNum(gp, 1)} gigapixels)</span>
        <span>{fmtNum(num(slide.tile_count), 0)} tiles in {num(slide.levels)} levels; {status.tiles} loaded{status.firstTileMs ? `, first in ${fmtMs(status.firstTileMs)}` : ''}</span>
        <span>Original {fmtBytes(num(slide.raw_bytes))} Aperio SVS stays in Files/raw</span>
        {tilPct !== null && <span>AI flags {fmtNum(tilPct * 100, 1)}% of tissue tiles as lymphocyte-rich</span>}
      </div>
    </div>
  );
}

/* ================================================================== Radiology */

type View = 'render' | 'multiplanar' | 'axial' | 'coronal' | 'sagittal';
type Preset = { id: string; label: string; colormap: string; calMin?: number; calMax?: number; glass?: boolean };

const CT_3D: Preset[] = [
  { id: 'contrast', label: 'Vessels and bone', colormap: 'ct_w_contrast', calMin: 50, calMax: 1000 },
  { id: 'bone', label: 'Bone', colormap: 'ct_bones', calMin: 180, calMax: 600 },
  { id: 'air', label: 'Air (lungs, bowel)', colormap: 'ct_lung_glass', calMin: -1000, calMax: -300, glass: true },
  { id: 'skin', label: 'Skin', colormap: 'ct_surface', calMin: -600, calMax: 100 },
];
const CT_2D: Preset[] = [
  { id: 'soft', label: 'Soft tissue', colormap: 'gray', calMin: -160, calMax: 240 },
  { id: 'lung', label: 'Lung', colormap: 'gray', calMin: -1350, calMax: 150 },
  { id: 'bonew', label: 'Bone', colormap: 'gray', calMin: -450, calMax: 1050 },
];
const MR: Preset[] = [{ id: 'gray', label: 'Greyscale', colormap: 'gray' }];

const SLICE: Record<View, SLICE_TYPE> = {
  render: SLICE_TYPE.RENDER,
  multiplanar: SLICE_TYPE.MULTIPLANAR,
  axial: SLICE_TYPE.AXIAL,
  coronal: SLICE_TYPE.CORONAL,
  sagittal: SLICE_TYPE.SAGITTAL,
};

function themeBack(): number[] {
  return document.documentElement.dataset.theme === 'dark' ? [0.05, 0.05, 0.047, 1] : [0.914, 0.902, 0.863, 1];
}

function defaultPreset(series: Row, organ: string): string {
  if (series.modality !== 'CT') return 'gray';
  if (/lung/i.test(organ) || /colon/i.test(organ)) return 'air';
  return 'contrast';
}

export function RadiologyPanel({
  b,
  seriesKey,
  onSeries,
  stepper = true,
}: {
  b: PatientBundle;
  seriesKey: string | null;
  onSeries: (k: string) => void;
  /** Draw the scan timepoint slider; off when the record's tab already steps through scans. */
  stepper?: boolean;
}) {
  const series = b.radiologySeries;
  const organ = str(b.patient.organ) ?? '';
  const current = series.find((s) => s.series_key === seriesKey) ?? series.find((s) => s.role === 'primary') ?? series[0];
  const isCt = current?.modality === 'CT';
  const [view, setView] = useState<View>('render');
  const [presetId, setPresetId] = useState('contrast');
  const [labels, setLabels] = useState(true);
  const [spin, setSpin] = useState(false);
  const [clip, setClip] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [load, setLoad] = useState<{ loading: boolean; ms: number | null; error: string | null }>({ loading: true, ms: null, error: null });
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nvRef = useRef<Niivue | null>(null);
  const keyRef = useRef<string | null>(null);

  const presets = isCt ? (view === 'render' ? CT_3D : CT_2D) : MR;
  const preset = presets.find((p) => p.id === presetId) ?? presets[0];
  const measures = parseJson<Record<string, { volumeMl: number; components: number }>>(current?.ai_measures, {});
  const lut = useMemo(() => (current?.labels_lut_path ? current.labels_lut_path : null), [current]);

  useEffect(() => {
    if (!current) return;
    setView(current.modality === 'CT' ? 'render' : 'multiplanar');
    setPresetId(defaultPreset(current, organ));
    setClip(false);
  }, [current?.series_uid]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!canvasRef.current) return;
    const nv = new Niivue({
      backColor: themeBack(),
      show3Dcrosshair: false,
      crosshairColor: [1, 0.561, 0.322, 1],
      crosshairWidth: 1,
      isOrientCube: true,
      multiplanarShowRender: SHOW_RENDER.ALWAYS,
      // MPR as a 2 × 2 grid (axial, coronal, sagittal, 3D), each view the same size.
      multiplanarLayout: MULTIPLANAR_TYPE.GRID,
      multiplanarEqualSize: true,
      dragMode: DRAG_MODE.pan,
      dragAndDropEnabled: false,
      loadingText: '',
      clipPlaneColor: [0, 0, 0, 0],
      isClipAllVolumes: true,
      fontMinPx: 12,
    });
    nv.addColormap('ct_lung_glass', {
      min: -1000,
      max: -300,
      R: [0, 0, 236, 244, 0, 0],
      G: [0, 0, 150, 176, 0, 0],
      B: [0, 0, 170, 192, 0, 0],
      A: [0, 0, 140, 220, 0, 0],
      I: [0, 20, 60, 150, 200, 255],
    });
    nvRef.current = nv;
    void nv.attachToCanvas(canvasRef.current);
    const observer = new MutationObserver(() => {
      nv.opts.backColor = themeBack();
      nv.drawScene();
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => {
      observer.disconnect();
      nvRef.current = null;
    };
  }, []);

  const apply = () => {
    const nv = nvRef.current;
    if (!nv || !nv.volumes.length) return;
    const vol = nv.volumes[0];
    vol.colormap = preset.colormap;
    if (preset.calMin !== undefined) vol.cal_min = preset.calMin;
    if (preset.calMax !== undefined) vol.cal_max = preset.calMax;
    if (nv.volumes[1]) nv.volumes[1].opacity = labels ? (view === 'render' ? 0.9 : 0.45) : 0;
    void nv.setGradientOpacity(preset.glass ? 0.5 : 0, preset.glass ? 0.25 : 0);
    nv.updateGLVolume();
    nv.setSliceType(SLICE[view]);
    nv.setClipPlane(clip ? [0.1, 180, 0] : [2, 0, 0]);
    nv.setRenderAzimuthElevation(clip ? 180 : nv.scene.renderAzimuth || 180, clip ? 12 : nv.scene.renderElevation || 12);
  };

  useEffect(() => {
    const nv = nvRef.current;
    if (!nv || !current) return;
    const key = String(current.series_uid);
    let cancelled = false;
    setLoad({ loading: true, ms: null, error: null });
    const t0 = performance.now();
    const volPath = String(current.volume_path);
    const lblPath = current.labels_path ? String(current.labels_path) : null;
    const volumes = [{ url: fileUrl(b.access.radiology, volPath), name: 'volume.nii.gz', colormap: 'gray' }];
    if (lblPath) volumes.push({ url: fileUrl(b.access.radiology, lblPath), name: 'labels.nii.gz', colormap: 'gray' });
    void (async () => {
      try {
        await nv.loadVolumes(volumes);
        if (cancelled) return;
        if (lut && nv.volumes[1]) await nv.volumes[1].setColormapLabelFromUrl(fileUrl(b.access.radiology, String(lut)));
        await nv.setVolumeRenderIllumination(0.55);
        keyRef.current = key;
        nv.setRenderAzimuthElevation(180, 12);
        apply();
        setLoad({ loading: false, ms: Math.round(performance.now() - t0), error: null });
      } catch (err) {
        if (!cancelled) setLoad({ loading: false, ms: null, error: err instanceof Error ? err.message : String(err) });
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.series_uid]);

  useEffect(() => {
    apply();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, presetId, labels, clip]);

  useEffect(() => {
    if (!spin) return;
    let raf = 0;
    const tick = () => {
      const nv = nvRef.current;
      if (nv?.volumes.length) nv.setRenderAzimuthElevation((nv.scene.renderAzimuth + 0.35) % 360, nv.scene.renderElevation);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [spin]);

  useEffect(() => {
    const id = window.setTimeout(() => nvRef.current?.resizeListener(), 60);
    return () => window.clearTimeout(id);
  }, [expanded]);

  if (!current) return <div className="t-faint text-[13px]">No radiology for this patient.</div>;
  const segNames = Object.keys(measures);
  const colourFor = (name: string) =>
    /tumor|mass|nodule/i.test(name) ? 'rgb(255,143,82)' : /cyst/i.test(name) ? 'rgb(90,160,230)' : /liver/i.test(name) ? 'rgb(196,120,90)' : /lung/i.test(name) ? 'rgb(120,170,210)' : 'rgb(214,150,120)';

  return (
    <div className="min-w-0">
      <div className="mb-2 flex items-baseline gap-3">
        <h3 className="text-[15px] font-medium">
          {current.modality === 'CT' ? 'CT' : 'MRI'} {(num(current.day) ?? 0) <= 0 ? 'before treatment' : `on ${fmtDay(num(current.day))}`}
        </h3>
        <span className="t-faint truncate text-[12.5px]">{str(current.description)}</span>
        <span className="src ml-auto"><span className="swatch sw-radiology" />imaging_lakehouse/Files/radiology</span>
      </div>
      {stepper && series.length > 1 && (
        <Scrubber
          name="Scan timepoints"
          gutter={92}
          leading={
            <>
              <div className="text-[12px]" style={{ color: 'var(--ink)' }}>
                {series.length} scans
              </div>
              <div>by day</div>
            </>
          }
          items={timepointItems(series)}
          selected={String(current.series_key)}
          onSelect={onSeries}
        />
      )}
      <div className="toolbar mb-2">
        <div className="seg" role="group" aria-label="View">
          {(
            [
              ['render', '3D'],
              ['multiplanar', 'MPR'],
              ['axial', 'Axial'],
              ['coronal', 'Coronal'],
            ] as [View, string][]
          ).map(([v, l]) => (
            <button key={v} aria-pressed={view === v} onClick={() => setView(v)}>
              {l}
            </button>
          ))}
        </div>
        {presets.length > 1 && (
          <select className="field !h-[30px] !w-auto" value={preset.id} onChange={(e) => setPresetId(e.target.value)} aria-label="Window">
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        )}
        {current.labels_path && (
          <button className="btn" aria-pressed={labels} onClick={() => setLabels((v) => !v)} style={labels ? { borderColor: 'var(--ink)' } : undefined}>
            AI segmentation {labels ? 'on' : 'off'}
          </button>
        )}
        {view === 'render' && (
          <>
            <button className="btn" aria-pressed={clip} onClick={() => setClip((v) => !v)}>{clip ? 'Uncut' : 'Cut'}</button>
            <button className={spin ? 'btn btn-ink' : 'btn'} onClick={() => setSpin((v) => !v)}>{spin ? 'Stop' : 'Spin'}</button>
          </>
        )}
        <button className="btn ml-auto" onClick={() => setExpanded((v) => !v)}>{expanded ? 'Close' : 'Expand'}</button>
      </div>
      <div className={`well well-dark ${expanded ? 'expanded' : ''}`} style={{ height: expanded ? undefined : 'clamp(640px, 82vh, 980px)' }}>
        <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
        {expanded && (
          <button className="btn absolute right-3 top-3 z-10" onClick={() => setExpanded(false)}>Close</button>
        )}
        {labels && segNames.length > 0 && (
          <div className="overlay-legend">
            <div className="font-medium">AI segmentation</div>
            {segNames.map((n) => (
              <div key={n} className="mt-1 flex items-center gap-1.5">
                <span className="swatch" style={{ background: colourFor(n) }} />
                <span>{n}</span>
                <span className="num ml-auto pl-3">{fmtNum(measures[n].volumeMl, 1)} mL</span>
              </div>
            ))}
            <div className="mt-1 max-w-[220px] text-[10.5px]">{str(current.ai_algorithm)}</div>
          </div>
        )}
        <div className="overlay-note">
          {load.loading ? `Streaming from ${STORE_NAME}` : load.error ? `Could not load: ${load.error}` : `${fmtBytes(num(current.volume_bytes))} in ${fmtMs(load.ms)}`}
        </div>
      </div>
      <div className="t-faint mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
        <span>
          {fmtDate(str(current.date))} · {fmtDay(num(current.day))}
        </span>
        <span>{[str(current.manufacturer), str(current.model)].filter(Boolean).join(' ')}</span>
        <span>
          {num(current.images)} images{num(current.slice_thickness_mm) ? `, ${num(current.slice_thickness_mm)} mm slices` : ''}
          {num(current.field_strength_t) ? `, ${num(current.field_strength_t)} T` : ''}
        </span>
        <span>Original {fmtBytes(num(current.raw_bytes))} DICOM ({num(current.raw_files)} files) stays in Files/raw</span>
      </div>
    </div>
  );
}

/** Scan timepoints placed by day relative to diagnosis. */
function timepointItems(series: Row[]): ScrubItem[] {
  const days = series.map((s) => num(s.day) ?? 0);
  const lo = Math.min(...days);
  const hi = Math.max(...days);
  return series.map((s, i) => ({
    id: String(s.series_key),
    at: hi > lo ? 0.07 + (0.86 * (days[i] - lo)) / (hi - lo) : 0.5,
    label: `${fmtDate(str(s.date))}, ${fmtDay(days[i])}: ${str(s.description) ?? ''}`,
    tick: fmtDay(days[i]),
  }));
}

/** What the AI measured across the scan timepoints, or that no segmentation is published. */
export function RadiologyFootnotes({ b }: { b: PatientBundle }) {
  const series = b.radiologySeries;
  const ai = series.find((s) => s.ai_measures);
  const liver = series.filter((s) => s.ai_measures && /liver/i.test(String(s.ai_measures)));
  return (
    <>
      {liver.length > 1 && (
        <p className="mt-4 max-w-[90ch] text-[13.5px]">
          AI-measured liver volume:{' '}
          {liver
            .map((s) => `${fmtNum(parseJson<Record<string, { volumeMl: number }>>(s.ai_measures, {}).Liver?.volumeMl, 0)} mL on ${fmtDay(num(s.day))}`)
            .join(', then ')}
          . Step between the scans to compare.
        </p>
      )}
      {!ai && series.length > 0 && (
        <p className="t-faint mt-3 text-[12px]">No AI segmentation is published for this patient's scan in NCI Imaging Data Commons.</p>
      )}
    </>
  );
}
