import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { PlainWords, PlainWordsLink } from '@/components/PlainWords';
import { MIP_COLORMAPS, MipViewer, type MipColormap } from '@/components/MipViewer';
import { DetailsPanel, ListColumn, PanelRow, PanelSection, useDetailsPanel, WorkspaceHeader } from '@/components/Panel';
import {
  VolumeViewer,
  type ClipSetting,
  type ColourPreset,
  type LayerSetting,
  type ViewMode,
  type VolumeViewerHandle,
  type VolumeViewerStatus,
} from '@/components/VolumeViewer';
import { RENDER_PRESET_NOTES, studyNote, TIPS, WINDOW_NOTES } from '@/content/guide';
import { useVolumeCatalog } from '@/hooks/useCatalog';
import { useMaximise } from '@/hooks/useMaximise';
import {
  formatMb,
  frameBytes,
  volumeUrl,
  type FolderAccess,
  type VolumeCatalog,
  type VolumeStudy,
} from '@/lib/volumes';

type PageView = ViewMode | 'mip';

const VIEWS: { id: PageView; label: string }[] = [
  { id: 'render', label: '3D' },
  { id: 'mip', label: 'MIP' },
  { id: 'multiplanar', label: 'MPR' },
  { id: 'axial', label: 'Axial' },
  { id: 'coronal', label: 'Coronal' },
  { id: 'sagittal', label: 'Sagittal' },
];

/** Colour transfer functions for 3D CT rendering (NiiVue colour maps with their HU ranges). */
const CT_RENDER: ColourPreset[] = [
  { id: 'bone', label: 'Bone', colormap: 'ct_bones', calMin: 180, calMax: 600 },
  {
    id: 'lungs',
    label: 'Lungs (glass)',
    colormap: 'ct_lung_glass',
    calMin: -1000,
    calMax: -300,
    glass: { gradientOpacity: 0.5, silhouette: 0.25 },
  },
  { id: 'contrast', label: 'Vessels and bone', colormap: 'ct_w_contrast', calMin: 50, calMax: 1000 },
  { id: 'artery', label: 'Arteries', colormap: 'ct_artery', calMin: 114, calMax: 800 },
  { id: 'muscle', label: 'Muscle', colormap: 'ct_muscles', calMin: -100, calMax: 246 },
  { id: 'skin', label: 'Skin', colormap: 'ct_surface', calMin: -600, calMax: 100 },
];
/** Greyscale windows for 2D CT reading. */
const CT_WINDOWS: ColourPreset[] = [
  { id: 'soft', label: 'Soft tissue', colormap: 'gray', calMin: -160, calMax: 240 },
  { id: 'lung', label: 'Lung', colormap: 'gray', calMin: -1350, calMax: 150 },
  { id: 'bonew', label: 'Bone', colormap: 'gray', calMin: -450, calMax: 1050 },
];
const MRI: ColourPreset[] = [{ id: 'gray', label: 'Greyscale', colormap: 'gray' }];
/** 3D MRI: translucent shows depth; solid gives sharp cut faces when clipping. */
const MRI_RENDER: ColourPreset[] = [
  { id: 'gray', label: 'Translucent', colormap: 'gray' },
  { id: 'solid', label: 'Solid', colormap: 'mri_solid' },
  { id: 'sepia', label: 'Skin tone', colormap: 'mri_sepia' },
];
const OVERLAY_MAPS = [
  { id: 'hot', label: 'Hot' },
  { id: 'inferno', label: 'Inferno' },
  { id: 'plasma', label: 'Plasma' },
  { id: 'ge_color', label: 'GE colour' },
  { id: 'turbo', label: 'Turbo' },
];

function viewsFor(study: VolumeStudy) {
  return VIEWS.filter((v) => (v.id === 'mip' ? !!study.mip : !study.views || study.views.includes(v.id)));
}

function presetsFor(study: VolumeStudy, view: PageView): ColourPreset[] {
  const kind = study.layers[0]?.kind;
  if (kind === 'ct') return view === 'render' ? CT_RENDER : CT_WINDOWS;
  if (kind === 'mri') return view === 'render' ? MRI_RENDER : MRI;
  return [];
}

export function Volumes() {
  const { catalog, loading, error, reload } = useVolumeCatalog();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState('');

  const studies = catalog?.studies ?? [];
  const requested = params.get('study');
  const selected = studies.find((s) => s.id === requested || (requested === 'cohort' && (s.id.startsWith('cohort-') || s.category.toLowerCase().includes('cohort')))) ?? studies[0] ?? null;

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (s: VolumeStudy) =>
      !q || [s.title, s.subtitle, s.modality, s.category, s.subject].some((v) => v.toLowerCase().includes(q));
    const out = new Map<string, VolumeStudy[]>();
    for (const s of studies.filter(match)) out.set(s.category, [...(out.get(s.category) ?? []), s]);
    return [...out.entries()];
  }, [studies, query]);
  const shown = groups.reduce((n, [, g]) => n + g.length, 0);

  if (!catalog) {
    return (
      <div className="flex h-full items-center justify-center">
        {error && !loading ? (
          <div className="text-center">
            <p className="font-medium">The volume catalog could not be read from the Lakehouse.</p>
            <p className="t-faint mt-2 max-w-md break-all text-[12px]">{error}</p>
            <button onClick={() => void reload()} className="btn btn-ink mt-5">
              Try again
            </button>
          </div>
        ) : (
          <p className="t-faint">Reading volume catalog from OneLake…</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        <ListColumn
          label="Studies"
          query={query}
          onQuery={setQuery}
          placeholder="Search studies"
          count={`${shown} of ${studies.length} studies`}
        >
          {groups.map(([category, items]) => (
            <div key={category}>
              <div className="list-heading">{category}</div>
              {items.map((s) => (
                <button
                  key={s.id}
                  className="list-row"
                  aria-current={s.id === selected?.id}
                  onClick={() => setParams({ study: s.id })}
                >
                  <img src={volumeUrl(catalog.access, s.thumbnail)} alt="" className="list-thumb" loading="lazy" />
                  <span className="min-w-0">
                    <span className="block text-[13.5px] font-medium leading-snug">{s.title}</span>
                    <span className="t-faint block truncate text-[11.5px]">{s.modality}</span>
                  </span>
                </button>
              ))}
            </div>
          ))}
          {shown === 0 && <p className="t-faint px-4 py-6 text-[12.5px]">No studies match “{query}”.</p>}
        </ListColumn>

        {selected && (
          <StudyWorkspace
            key={`${selected.id}:${selected.layers.map((l) => l.id).join(',')}`}
            study={selected}
            catalog={catalog}
          />
        )}
      </div>
    </div>
  );
}

function StudyWorkspace({ study, catalog }: { study: VolumeStudy; catalog: VolumeCatalog }) {
  const viewerRef = useRef<VolumeViewerHandle>(null);
  const [params, setParams] = useSearchParams();
  const timeline = study.timeline;
  const [view, setView] = useState<PageView>((study.defaultView as PageView) ?? 'render');
  const [volumeView, setVolumeView] = useState<ViewMode>(() =>
    study.defaultView && study.defaultView !== 'mip' ? (study.defaultView as ViewMode) : 'render'
  );
  const [mipColormap, setMipColormap] = useState<MipColormap>((study.mip?.colormap as MipColormap) ?? 'inverted');
  const chooseView = (v: PageView) => {
    setView(v);
    if (v !== 'mip') setVolumeView(v);
  };
  const [presetIds, setPresetIds] = useState<Record<string, string>>({});
  const [layers, setLayers] = useState<Record<string, LayerSetting>>(() =>
    Object.fromEntries(
      study.layers.map((l) => [l.id, { visible: l.visible ?? true, opacity: l.opacity ?? 1, colormap: l.colormap }])
    )
  );
  const [clip, setClip] = useState<ClipSetting>(() => study.defaultClip ?? { on: false, depth: 0, face: 'front' });
  const [spin, setSpin] = useState(false);
  // Cine studies (e.g. the breathing lungs) start playing straight away.
  const [playing, setPlaying] = useState(!!study.timeline?.loop);
  const maximise = useMaximise<HTMLDivElement>();
  const details = useDetailsPanel();
  const [status, setStatus] = useState<VolumeViewerStatus>({ loading: true, error: null, loadMs: null, location: null });

  const initialFrame = useMemo(() => {
    if (!timeline) return 0;
    const wanted = Number(params.get('t') ?? timeline.initial);
    const i = timeline.frames.findIndex((f) => f.value === wanted);
    return i >= 0 ? i : 0;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [study.id]);
  const [frameIndex, setFrameIndex] = useState(initialFrame);
  const frame = timeline?.frames[frameIndex];

  const presets = presetsFor(study, view);
  const mode = view === 'render' ? 'render' : '2d';
  const fallback =
    mode === 'render'
      ? (study.defaultPreset ?? (study.layers.some((l) => l.kind === 'labels' && l.visible) ? 'bone' : undefined))
      : undefined;
  const preset =
    presets.find((p) => p.id === (presetIds[mode] ?? fallback)) ?? presets[0] ?? null;

  // Keep the shared link in step with the timeline (not while a cine is playing).
  useEffect(() => {
    if (!timeline || !frame || playing) return;
    const next = new URLSearchParams(params);
    next.set('study', study.id);
    next.set('t', String(frame.value));
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frameIndex, playing]);

  // Timeline playback. 4D files switch frames in place at the study's frame rate; per-file timelines
  // advance once the current frame has loaded.
  const inPlace = timeline?.mode === 'frames4d';
  useEffect(() => {
    if (!playing || !timeline || status.loading) return;
    const delay = inPlace ? 1000 / (timeline.fps ?? 10) : 700;
    const t = window.setTimeout(() => setFrameIndex((i) => (i + 1) % timeline.frames.length), delay);
    return () => window.clearTimeout(t);
  }, [playing, timeline, status.loading, frameIndex, inPlace]);

  const setLayer = (id: string, patch: Partial<LayerSetting>) =>
    setLayers((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));

  const servedBytes = frameBytes(study, frameIndex);
  const note = studyNote(study.id, study.description);
  const presetNote = preset ? (mode === 'render' ? RENDER_PRESET_NOTES : WINDOW_NOTES)[preset.id] : undefined;
  const hint =
    view === 'mip'
      ? `${study.mip?.label ?? 'Maximum intensity projection'} · drag sideways to rotate`
      : view === 'render'
      ? 'Drag to rotate · scroll to zoom · right-drag to pan'
      : 'Click to move the cursor · scroll to change slice · right-drag to pan';

  return (
    <div ref={maximise.ref} className={`flex min-w-0 flex-1 flex-col ${maximise.on ? 'workspace-max' : ''}`}>
      <WorkspaceHeader
        title={study.title}
        meta={
          <>
            {study.modality} · {study.subject}
          </>
        }
        description={study.description}
        explain={<PlainWordsLink onOpen={() => details.show('about')} />}
      />

      <div className="hair flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b px-4 py-2">
        <div className="seg" role="group" aria-label="View">
          {viewsFor(study).map((v) => (
            <button key={v.id} aria-pressed={view === v.id} onClick={() => chooseView(v.id)} title={TIPS.views[v.label]}>
              {v.label}
            </button>
          ))}
        </div>

        {view === 'mip' && (
          <label className="flex items-center gap-2 text-[12.5px]">
            <span className="t-faint">Colour</span>
            <select
              className="field h-[30px] w-auto py-0 pr-7"
              value={mipColormap}
              onChange={(e) => setMipColormap(e.target.value as MipColormap)}
              title={mipColormap === 'inverted' ? 'Dark means high, as PET is usually read' : 'Bright means high'}
            >
              {MIP_COLORMAPS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
        )}

        {view !== 'mip' && presets.length > 1 && (
          <label className="flex items-center gap-2 text-[12.5px]">
            <span className="t-faint">{view === 'render' ? 'Colour' : 'Window'}</span>
            <select
              className="field h-[30px] w-auto py-0 pr-7"
              value={preset?.id}
              onChange={(e) => setPresetIds((p) => ({ ...p, [mode]: e.target.value }))}
              title={presetNote}
            >
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        )}

        <div className={`flex items-center gap-2 ${view === 'mip' || (study.views && !study.views.includes('render')) ? 'hidden' : ''}`}>
          <button className={`btn ${clip.on ? 'btn-ink' : ''}`} aria-pressed={clip.on} title={TIPS.clip} onClick={() => setClip((c) => ({ ...c, on: !c.on }))}>
            Clip
          </button>
          {clip.on && (
            <>
              <div className="seg" role="group" aria-label="Clip direction" title={TIPS.clipFace}>
                {(['front', 'side', 'top'] as const).map((f) => (
                  <button key={f} aria-pressed={clip.face === f} onClick={() => setClip((c) => ({ ...c, face: f }))}>
                    {f[0].toUpperCase() + f.slice(1)}
                  </button>
                ))}
              </div>
              <input
                type="range"
                className="range w-28"
                min={-0.5}
                max={0.5}
                step={0.01}
                value={clip.depth}
                aria-label="Clip depth"
                title={TIPS.clipDepth}
                onChange={(e) => setClip((c) => ({ ...c, depth: Number(e.target.value) }))}
              />
            </>
          )}
        </div>

        <button className={`btn ${spin ? 'btn-ink' : ''}`} aria-pressed={spin} title={TIPS.spin} onClick={() => setSpin((s) => !s)} disabled={view !== 'render' && view !== 'multiplanar' && view !== 'mip'}>
          Spin
        </button>
        <button className="btn" title={TIPS.reset} onClick={() => viewerRef.current?.resetView()}>
          Reset
        </button>

        <div className="ml-auto flex items-center gap-2">
          <button className="btn" title={TIPS.saveImage} onClick={() => viewerRef.current?.saveImage()}>
            Save image
          </button>
          <button className={`btn ${maximise.on ? 'btn-ink' : ''}`} aria-pressed={maximise.on} title={maximise.on ? TIPS.exitFullScreen : TIPS.fullScreen} onClick={maximise.toggle}>
            {maximise.on ? 'Exit full screen' : 'Full screen'}
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="relative min-h-0 flex-1">
            <VolumeViewer
              ref={viewerRef}
              study={study}
              access={catalog.access}
              frameIndex={frameIndex}
              view={volumeView}
              preset={preset}
              layers={layers}
              clip={clip}
              spin={spin && view !== 'mip'}
              onStatus={setStatus}
            />
            {view === 'mip' && study.mip && (
              <MipViewer
                url={volumeUrl(catalog.access, study.mip.sprite)}
                mip={study.mip}
                colormap={mipColormap}
                spin={spin}
                gamma={mipColormap === 'inverted' || mipColormap === 'gray' ? 0.85 : 0.7}
              />
            )}
            {status.loading && !playing && view !== 'mip' && (
              <div className="statusbar absolute left-4 top-4 border px-3 py-1.5 text-[12.5px]">
                Loading {formatMb(servedBytes)} from OneLake…
              </div>
            )}
            {status.error && (
              <div className="absolute inset-x-4 top-4 border px-3 py-2 text-[12.5px]" style={{ background: 'var(--bg)', borderColor: 'var(--accent)' }}>
                Could not load this study: {status.error}
              </div>
            )}
          </div>

          {timeline && frame && (
            <div className="statusbar flex shrink-0 items-center gap-4 px-4 py-2.5">
              <button className={`btn ${playing ? 'btn-ink' : 'btn-primary'} w-[72px] justify-center`} title={TIPS.play} onClick={() => setPlaying((p) => !p)}>
                {playing ? 'Pause' : 'Play'}
              </button>
              <div className="min-w-0 flex-1">
                <input
                  type="range"
                  className="range w-full"
                  min={0}
                  max={timeline.frames.length - 1}
                  step={1}
                  value={frameIndex}
                  aria-label={timeline.label}
                  onChange={(e) => {
                    setPlaying(false);
                    setFrameIndex(Number(e.target.value));
                  }}
                />
                <div className="mt-1 flex justify-between">
                  {timeline.frames.map((f, i) => (
                    <button key={f.value} className="timeline-tick" aria-current={i === frameIndex} onClick={() => { setPlaying(false); setFrameIndex(i); }}>
                      {f.value}
                    </button>
                  ))}
                </div>
              </div>
              <div className="w-[170px] shrink-0 text-right">
                <div className="t-display text-[22px] font-semibold">{frame.label}</div>
                <div className="t-faint text-[11.5px]">
                  {timeline.label}
                  {frame.note ? ` · ${frame.note}` : ''}
                </div>
              </div>
            </div>
          )}

          <div className="statusbar flex h-9 shrink-0 items-center gap-6 px-4 text-[12.5px]">
            <span className="t-muted">
              {study.dims.join(' × ')} voxels · {formatMm(study.spacingMm[0])} mm
            </span>
            <span className="t-faint">
              {formatMb(servedBytes)}
              {status.loadMs != null && !status.loading ? ` in ${(status.loadMs / 1000).toFixed(1)} s` : ''}
            </span>
            {status.location && view !== 'render' && <span className="t-mono t-muted truncate text-[11.5px]">{status.location}</span>}
            <span className="t-faint ml-auto hidden truncate lg:inline">{hint}</span>
          </div>
        </div>

        <DetailsPanel
          panel={details}
          about={
            <>
                <PanelSection title="In plain words">
                  <PlainWords note={note} guideHref="/guide#volume-controls" />
                </PanelSection>

                <PanelSection title="Study">
                  <dl>
                    <PanelRow term="Modality">{study.modality}</PanelRow>
                    <PanelRow term="Subject">{study.subject}</PanelRow>
                    {study.scanner && <PanelRow term="Scanner">{study.scanner}</PanelRow>}
                    {study.patientId && (
                      <PanelRow term="Case">
                        <span className="t-mono">{study.patientId}</span>
                      </PanelRow>
                    )}
                    <PanelRow term="Grid">
                      {study.dims.join(' × ')} at {study.spacingMm.map(formatMm).join(' × ')} mm
                    </PanelRow>
                    {study.stats &&
                      Object.entries(study.stats).map(([k, v]) => (
                        <PanelRow key={k} term={statLabel(k)}>
                          {v.toLocaleString()}
                        </PanelRow>
                      ))}
                  </dl>
                </PanelSection>

                <PanelSection title="Source and licence">
                  <p className="text-[12.5px]">{study.source}</p>
                  <p className="mt-2 text-[12.5px]">
                    <span className="t-faint">Licence </span>
                    {study.license}
                  </p>
                  <p className="t-faint mt-2 text-[11.5px]">{study.citation}</p>
                  <a href={study.sourceUrl} target="_blank" rel="noreferrer" className="link mt-3 inline-block text-[12.5px]">
                    Dataset page ↗
                  </a>
                </PanelSection>

                <PanelSection title="Storage">
                  <div className="text-[12.5px]">
                    {catalog.lakehouse.workspaceName}/<span className="font-semibold">{catalog.lakehouse.lakehouseName}</span>
                  </div>
                  <dl className="mt-2">
                    <PanelRow term="Served">
                      <span className="t-mono text-[11.5px]">Files/volumes/{study.id}/</span>
                      <span className="t-faint block text-[11.5px]">{formatMb(study.sizeBytes)} NIfTI</span>
                    </PanelRow>
                    <PanelRow term="Original">
                      <span className="t-mono text-[11.5px]">Files/{study.rawPath}</span>
                      <span className="t-faint block text-[11.5px]">
                        {study.rawFiles.toLocaleString()} files, {formatMb(study.rawSizeBytes)}
                      </span>
                    </PanelRow>
                  </dl>
                  <a href={catalog.lakehouse.portalUrl} target="_blank" rel="noreferrer" className="link mt-3 inline-block text-[12.5px]">
                    Open in Fabric ↗
                  </a>
                </PanelSection>
            </>
          }
          controls={
            <>
                <PanelSection title="Layers">
                  <ul className="space-y-3">
                    {study.layers.map((l, i) => (
                      <li key={l.id}>
                        <label className="flex items-center gap-2 text-[13px]">
                          <input
                            type="checkbox"
                            className="check"
                            checked={layers[l.id]?.visible ?? true}
                            onChange={(e) => setLayer(l.id, { visible: e.target.checked })}
                          />
                          <span className="font-medium">{l.label}</span>
                          {l.unit && <span className="t-faint text-[11.5px]">{l.unit}</span>}
                        </label>
                        {note.layers?.[l.id] && <p className="t-faint mt-1 pl-6 text-[11.5px] leading-snug">{note.layers[l.id]}</p>}
                        {i > 0 && (
                          <div className="mt-1.5 flex items-center gap-3 pl-6">
                            <input
                              type="range"
                              className="range flex-1"
                              min={0}
                              max={1}
                              step={0.05}
                              value={layers[l.id]?.opacity ?? 1}
                              aria-label={`${l.label} opacity`}
                              onChange={(e) => setLayer(l.id, { opacity: Number(e.target.value) })}
                            />
                            {l.kind === 'overlay' && (
                              <select
                                className="field h-[28px] w-auto py-0 text-[12px]"
                                value={layers[l.id]?.colormap ?? l.colormap}
                                onChange={(e) => setLayer(l.id, { colormap: e.target.value })}
                                aria-label={`${l.label} colour map`}
                              >
                                {OVERLAY_MAPS.map((m) => (
                                  <option key={m.id} value={m.id}>
                                    {m.label}
                                  </option>
                                ))}
                              </select>
                            )}
                          </div>
                        )}
                        {l.kind === 'overlay' && l.calMin !== undefined && (
                          <div className="t-faint mt-1 pl-6 text-[11.5px]">
                            Shown from {l.calMin} to {l.calMax} {l.unit}
                          </div>
                        )}
                        {l.kind === 'labels' && l.lut && <LabelLegend access={catalog.access} lut={l.lut} />}
                      </li>
                    ))}
                  </ul>
                </PanelSection>

                <PanelSection title="Current view">
                  <dl>
                    <PanelRow term="View">{TIPS.views[VIEWS.find((x) => x.id === view)?.label ?? ''] ?? view}</PanelRow>
                    {presetNote && view !== 'mip' && <PanelRow term={preset?.label ?? 'Colour'}>{presetNote}</PanelRow>}
                    {clip.on && view !== 'mip' && <PanelRow term="Clip">Cutting from the {clip.face}; the slider moves the cut.</PanelRow>}
                    <PanelRow term="Mouse">{hint}</PanelRow>
                  </dl>
                </PanelSection>
            </>
          }
        />
      </div>
    </div>
  );
}

const STAT_LABELS: Record<string, string> = {
  lesions: 'Lesions',
  lesionVolumeMl: 'Lesion volume, ml',
  suvMax: 'SUVmax',
  injectedMBq: 'Injected, MBq',
  structures: 'Structures',
  weeks: 'Weeks',
  brainVolumeMlStart: 'Brain, first week, ml',
  brainVolumeMlEnd: 'Brain, last week, ml',
  phases: 'Phases',
  lungVolumeChangeMl: 'Lung volume change, ml',
  tumourMotionMm: 'Tumour motion, mm',
  organs: 'Organs labelled',
  lungVolumeMlStart: 'Lungs, first week, ml',
  lungVolumeMlEnd: 'Lungs, last week, ml',
  landmarks: 'Facial landmarks',
  headVolumeMl: 'Head volume, ml',
  bundles: 'Fibre bundles',
  streamlines: 'Streamlines shown',
};

/** Voxel sizes without floating-point noise: 0.15630000000000002 -> 0.1563. */
function formatMm(mm: number): string {
  return String(Number(mm.toFixed(4)));
}

function statLabel(key: string): string {
  return STAT_LABELS[key] ?? key;
}

type Lut = { R: number[]; G: number[]; B: number[]; A: number[]; labels: string[] };

/** Swatches grouped by colour, so a 117-label table reads as a short legend. */
function LabelLegend({ access, lut }: { access: FolderAccess; lut: string }) {
  const [groups, setGroups] = useState<{ colour: string; names: string[] }[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetch(volumeUrl(access, lut))
      .then((r) => r.json() as Promise<Lut>)
      .then((t) => {
        const byColour = new Map<string, string[]>();
        t.labels.forEach((name, i) => {
          if (!name || !t.A[i]) return;
          const colour = `rgb(${t.R[i]} ${t.G[i]} ${t.B[i]})`;
          const names = byColour.get(colour) ?? [];
          if (!names.includes(name)) byColour.set(colour, [...names, name]);
        });
        if (!cancelled) setGroups([...byColour.entries()].map(([colour, names]) => ({ colour, names })));
      })
      .catch(() => setGroups([]));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lut]);
  if (groups.length === 0) return null;
  const shown = groups.slice(0, 14);
  return (
    <ul className="mt-2 space-y-1 pl-6">
      {shown.map((g) => (
        <li key={g.colour} className="flex items-start gap-2 text-[11.5px]">
          <span className="mt-[3px] h-2.5 w-2.5 shrink-0" style={{ background: g.colour }} />
          <span className="t-muted min-w-0">
            {g.names.length > 2 ? `${g.names[0]} and ${g.names.length - 1} more` : g.names.join(', ')}
          </span>
        </li>
      ))}
      {groups.length > shown.length && <li className="t-faint text-[11.5px]">{groups.length - shown.length} more colours</li>}
    </ul>
  );
}
