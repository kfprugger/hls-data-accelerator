import { DRAG_MODE, Niivue, SHOW_RENDER, SLICE_TYPE } from '@niivue/niivue';
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react';

import { layerFile, volumeUrl, type FolderAccess, type VolumeStudy } from '@/lib/volumes';

export type ViewMode = 'render' | 'multiplanar' | 'axial' | 'coronal' | 'sagittal';

export interface ColourPreset {
  id: string;
  label: string;
  colormap: string;
  calMin?: number;
  calMax?: number;
  /** Gradient-weighted opacity: edges stay, uniform interiors turn see-through. */
  glass?: { gradientOpacity: number; silhouette: number };
}

export interface LayerSetting {
  visible: boolean;
  opacity: number;
  colormap?: string;
}

export interface ClipSetting {
  on: boolean;
  depth: number;
  /** Which way the cut faces: front (coronal), side (sagittal) or top (axial). */
  face: 'front' | 'side' | 'top';
}

export interface VolumeViewerStatus {
  loading: boolean;
  error: string | null;
  loadMs: number | null;
  location: string | null;
}

export interface VolumeViewerHandle {
  resetView: () => void;
  saveImage: () => void;
}

interface Props {
  study: VolumeStudy;
  access: FolderAccess;
  frameIndex: number;
  view: ViewMode;
  preset: ColourPreset | null;
  layers: Record<string, LayerSetting>;
  clip: ClipSetting;
  spin: boolean;
  onStatus: (status: VolumeViewerStatus) => void;
}

const SLICE: Record<ViewMode, SLICE_TYPE> = {
  render: SLICE_TYPE.RENDER,
  multiplanar: SLICE_TYPE.MULTIPLANAR,
  axial: SLICE_TYPE.AXIAL,
  coronal: SLICE_TYPE.CORONAL,
  sagittal: SLICE_TYPE.SAGITTAL,
};

/** Default camera: patient facing the viewer, slightly from above. */
const HOME = { azimuth: 180, elevation: 12 };
const CLIP_ANGLES: Record<ClipSetting['face'], [number, number]> = {
  front: [180, 0],
  side: [270, 0],
  top: [0, 90],
};

/** Camera azimuth/elevation that looks onto the exposed cut surface for each clip direction. */
const CLIP_CAMERA: Record<ClipSetting['face'], [number, number]> = {
  front: [180, 12],
  side: [90, 8],
  top: [180, -80],
};

function themeColours(): { back: number[]; font: number[] } {
  const dark = document.documentElement.dataset.theme === 'dark';
  return dark
    ? { back: [0.078, 0.078, 0.075, 1], font: [0.94, 0.93, 0.9, 1] }
    : { back: [0.914, 0.902, 0.863, 1], font: [0.08, 0.08, 0.07, 1] };
}

/** Point the camera at the cut surface when clipping, otherwise at the patient's front. */
function faceCamera(nv: Niivue, clip: ClipSetting, home: { azimuth: number; elevation: number } = HOME): void {
  if (!clip.on) {
    nv.setRenderAzimuthElevation(home.azimuth, home.elevation);
    return;
  }
  const view = CLIP_CAMERA[clip.face];
  nv.setRenderAzimuthElevation(view[0], view[1]);
}

export const VolumeViewer = forwardRef<VolumeViewerHandle, Props>(function VolumeViewer(
  { study, access, frameIndex, view, preset, layers, clip, spin, onStatus },
  ref
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nvRef = useRef<Niivue | null>(null);
  const indexRef = useRef<Record<string, number>>({});
  const meshIndexRef = useRef<Record<string, number>>({});
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const loadedRef = useRef<{ key: string; frame: number } | null>(null);
  const statusRef = useRef<VolumeViewerStatus>({ loading: true, error: null, loadMs: null, location: null });
  const settingsRef = useRef({ view, preset, layers, clip });
  const onStatusRef = useRef(onStatus);
  settingsRef.current = { view, preset, layers, clip };
  onStatusRef.current = onStatus;

  const frames4d = study.timeline?.mode === 'frames4d';
  // Identity of the loaded data, not just the study id: a refreshed catalog can rename or replace files.
  const dataKey = useMemo(
    () => JSON.stringify([study.id, study.layers.map((l) => [l.id, l.file, l.lut]), study.timeline?.frames.length ?? 0]),
    [study]
  );

  /** Show one time point of every 4D layer. */
  const showFrame = (nv: Niivue, frame: number) => {
    if (!frames4d) return;
    for (const layer of study.layers) {
      const i = indexRef.current[layer.id];
      const vol = i === undefined ? undefined : nv.volumes[i];
      if (layer.frames4d && vol && (vol.nFrame4D ?? 1) > 1) {
        nv.setFrame4D(vol.id, Math.min(frame, (vol.nFrame4D ?? 1) - 1));
      }
    }
  };

  const emit = (patch: Partial<VolumeViewerStatus>) => {
    statusRef.current = { ...statusRef.current, ...patch };
    onStatusRef.current(statusRef.current);
  };

  /** Push the current React settings into NiiVue without reloading data. */
  const apply = () => {
    const nv = nvRef.current;
    if (!nv || nv.volumes.length === 0) return;
    const { view: v, preset: p, layers: ls, clip: c } = settingsRef.current;
    const idx = indexRef.current;
    for (const layer of study.layers) {
      const i = idx[layer.id];
      if (i === undefined || !nv.volumes[i]) continue;
      const vol = nv.volumes[i];
      const s = ls[layer.id];
      if (i === 0 && p && layer.kind !== 'rgba') {
        vol.colormap = p.colormap;
        if (p.calMin !== undefined) vol.cal_min = p.calMin;
        if (p.calMax !== undefined) vol.cal_max = p.calMax;
      }
      if (layer.kind === 'overlay' && s?.colormap) vol.colormap = s.colormap;
      vol.opacity = s && !s.visible ? 0 : (s?.opacity ?? 1);
    }
    for (const [id, mi] of Object.entries(meshIndexRef.current)) {
      const mesh = nv.meshes[mi];
      const s = ls[id];
      if (!mesh) continue;
      mesh.visible = s ? s.visible : true;
      mesh.opacity = s?.opacity ?? 1;
    }
    nv.opts.isColorbar = study.layers.some((l) => l.kind === 'overlay' && ls[l.id]?.visible);
    for (const [id, i] of Object.entries(idx)) {
      if (nv.volumes[i]) nv.volumes[i].colorbarVisible = study.layers.find((l) => l.id === id)?.kind === 'overlay';
    }
    // Single-plane cine has nothing to cross-reference: hide the crosshair.
    nv.opts.crosshairWidth = study.views && study.views.length === 1 ? 0 : 1;
    const glass = p?.glass ?? { gradientOpacity: 0, silhouette: 0 };
    if (nv.opts.gradientOpacity !== glass.gradientOpacity || nv.opts.renderSilhouette !== glass.silhouette) {
      void nv.setGradientOpacity(glass.gradientOpacity, glass.silhouette);
    }
    nv.updateGLVolume();
    nv.setSliceType(SLICE[v]);
    const [az, el] = CLIP_ANGLES[c.face];
    nv.setClipPlane(c.on ? [c.depth, az, el] : [2, 0, 0]);
  };

  // Create the NiiVue instance once.
  useEffect(() => {
    if (!canvasRef.current) return;
    const { back, font } = themeColours();
    const nv = new Niivue({
      backColor: back,
      fontColor: font,
      show3Dcrosshair: false,
      crosshairColor: [0.95, 0.39, 0.1, 1],
      crosshairWidth: 1,
      isOrientCube: true,
      isColorbar: false,
      colorbarHeight: 0.025,
      colorbarWidth: 0.4,
      fontMinPx: 12,
      fontSizeScaling: 0.3,
      multiplanarShowRender: SHOW_RENDER.ALWAYS,
      dragMode: DRAG_MODE.pan,
      dragAndDropEnabled: false,
      loadingText: '',
      // Fully transparent: the cut surface itself shows the anatomy.
      clipPlaneColor: [0, 0, 0, 0],
      // The cut goes through every layer (labels, PET), not just the base volume.
      isClipAllVolumes: true,
      isAntiAlias: true,
    });
    nvRef.current = nv;
    // Lung parenchyma (about -950 to -450 HU) in pink; air and soft tissue transparent. Spans -1000..-300 HU.
    nv.addColormap('ct_lung_glass', {
      min: -1000,
      max: -300,
      R: [0, 0, 236, 244, 0, 0],
      G: [0, 0, 150, 176, 0, 0],
      B: [0, 0, 170, 192, 0, 0],
      A: [0, 0, 140, 220, 0, 0],
      I: [0, 20, 60, 150, 200, 255],
    });
    // Opaque greyscale for MRI: a clip shows the cut face itself instead of a haze of the tissue behind it.
    nv.addColormap('mri_solid', {
      R: [0, 8, 40, 255],
      G: [0, 8, 40, 255],
      B: [0, 8, 40, 255],
      A: [0, 0, 255, 255],
      I: [0, 8, 40, 255],
    });
    // Warm skin tones with lighting, in the style of 3D obstetric ultrasound. The gradual opacity ramp spreads
    // the surface over a few samples, which avoids wood-grain banding on smooth skin.
    nv.addColormap('mri_sepia', {
      R: [0, 90, 200, 245, 255],
      G: [0, 55, 140, 205, 240],
      B: [0, 30, 80, 150, 210],
      A: [0, 0, 40, 160, 255],
      I: [0, 8, 45, 110, 255],
    });
    void nv.attachToCanvas(canvasRef.current).then(() => {
      nv.onLocationChange = (data: unknown) => {
        const d = data as { string?: string };
        emit({ location: d.string ?? null });
      };
    });
    const observer = new MutationObserver(() => {
      const c = themeColours();
      nv.opts.backColor = c.back;
      nv.opts.fontColor = c.font;
      nv.drawScene();
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => {
      observer.disconnect();
      nvRef.current = null;
      try {
        nv.gl?.getExtension('WEBGL_lose_context')?.loseContext();
      } catch {
        // Context already gone.
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // (Re)load data when the study or timeline frame changes. Loads are serialised.
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      const nv = nvRef.current;
      if (!nv || cancelled) return;
      const sameStudy = loadedRef.current?.key === dataKey;
      const camera = sameStudy
        ? { az: nv.scene.renderAzimuth, el: nv.scene.renderElevation, scale: nv.scene.volScaleMultiplier }
        : null;
      emit({ loading: true, error: null });
      const started = performance.now();
      try {
        const entries = study.layers
          .filter((layer) => layer.kind !== 'tracts')
          .map((layer) => ({ layer, file: layerFile(study, layer, frameIndex) }))
          .filter((e): e is { layer: (typeof study.layers)[number]; file: string } => !!e.file);
        const tracts = study.layers.filter((l) => l.kind === 'tracts' && l.file);
        if (!sameStudy) {
          for (const m of [...nv.meshes]) nv.removeMesh(m);
          meshIndexRef.current = {};
        }
        const s = settingsRef.current.layers;
        await nv.loadVolumes(
          entries.map(({ layer, file }, i) => ({
            url: volumeUrl(access, file),
            name: file.split('/').pop() ?? file,
            colormap: layer.kind === 'overlay' ? (s[layer.id]?.colormap ?? layer.colormap ?? 'hot') : 'gray',
            ...(layer.calMin !== undefined ? { cal_min: layer.calMin } : {}),
            ...(layer.calMax !== undefined ? { cal_max: layer.calMax } : {}),
            opacity: i === 0 ? 1 : (layer.opacity ?? 1),
          }))
        );
        if (cancelled) return;
        indexRef.current = Object.fromEntries(entries.map(({ layer }, i) => [layer.id, i]));
        await Promise.all(
          entries.map(async ({ layer }, i) => {
            if (layer.kind === 'labels' && layer.lut && nv.volumes[i]) {
              await nv.volumes[i].setColormapLabelFromUrl(volumeUrl(access, layer.lut));
            }
          })
        );
        if (cancelled) return;
        if (!sameStudy && tracts.length) {
          await nv.loadMeshes(
            tracts.map((l) => ({ url: volumeUrl(access, l.file!), name: l.file!.split('/').pop() ?? l.file! }))
          );
          meshIndexRef.current = Object.fromEntries(tracts.map((l, i) => [l.id, i]));
          for (const m of nv.meshes) {
            nv.setMeshProperty(m.id as unknown as number, 'fiberColor', 'Global');
            nv.setMeshProperty(m.id as unknown as number, 'fiberRadius', 0.35);
          }
        }
        if (cancelled) return;
        if (!sameStudy) {
          await nv.setVolumeRenderIllumination(study.layers[0]?.kind === 'rgba' ? 0.35 : 0.55);
        }
        showFrame(nv, frameIndex);
        if (camera) {
          nv.scene.volScaleMultiplier = camera.scale;
          nv.setRenderAzimuthElevation(camera.az, camera.el);
        } else {
          faceCamera(nv, settingsRef.current.clip, study.defaultCamera);
        }
        loadedRef.current = { key: dataKey, frame: frameIndex };
        apply();
        emit({ loading: false, loadMs: Math.round(performance.now() - started) });
      } catch (err) {
        console.error('Volume load failed', err);
        if (!cancelled) emit({ loading: false, error: err instanceof Error ? err.message : String(err) });
      }
    };
    queueRef.current = queueRef.current.then(run, run);
    return () => {
      cancelled = true;
    };
    // The SAS query is read at load time; a refreshed token does not require reloading loaded data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataKey, frames4d ? 0 : frameIndex]);

  // 4D files: switch frames in place, instantly.
  useEffect(() => {
    const nv = nvRef.current;
    if (frames4d && nv && loadedRef.current?.key === dataKey) showFrame(nv, frameIndex);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frameIndex]);

  // Settings that do not need a reload.
  useEffect(() => {
    apply();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, preset, layers, clip]);

  // Turning the cut on, or changing its direction, swings the camera round to face it.
  useEffect(() => {
    const nv = nvRef.current;
    if (nv && nv.volumes.length) faceCamera(nv, clip, study.defaultCamera);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clip.on, clip.face]);

  // Auto-rotate.
  useEffect(() => {
    if (!spin) return;
    let raf = 0;
    const tick = () => {
      const nv = nvRef.current;
      if (nv && nv.volumes.length) {
        nv.setRenderAzimuthElevation((nv.scene.renderAzimuth + 0.35) % 360, nv.scene.renderElevation);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [spin]);

  useImperativeHandle(ref, () => ({
    resetView: () => {
      const nv = nvRef.current;
      if (!nv) return;
      nv.scene.volScaleMultiplier = 1;
      nv.scene.pan2Dxyzmm = [0, 0, 0, 1];
      faceCamera(nv, settingsRef.current.clip, study.defaultCamera);
    },
    saveImage: () => {
      void nvRef.current?.saveScene(`${study.id}.png`);
    },
  }));

  return (
    <div className="volume-canvas relative h-full w-full">
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
    </div>
  );
});
