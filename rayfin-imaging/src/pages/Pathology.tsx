import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';

import { PlainWords, PlainWordsLink } from '@/components/PlainWords';
import { LakehouseImage } from '@/components/LakehouseImage';
import { DetailsPanel, ListColumn, PanelRow, PanelSection, useDetailsPanel, WorkspaceHeader } from '@/components/Panel';
import {
  SlideViewer,
  type SlideViewerHandle,
  type ViewerStatus,
  type ViewState,
} from '@/components/SlideViewer';
import { MARKER_NOTES, slideNote, TIPS } from '@/content/guide';
import { useCatalog } from '@/hooks/useCatalog';
import { useMaximise } from '@/hooks/useMaximise';
import { usePins } from '@/hooks/usePins';
import {
  formatBytes,
  formatGigapixels,
  formatPhysicalSize,
  type Slide,
  type SlideCatalog,
} from '@/lib/catalog';

const NICE_UM = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000];

function ScaleBar({ umPerPixel }: { umPerPixel: number | null }) {
  if (!umPerPixel) return null;
  const um = [...NICE_UM].reverse().find((n) => n <= 110 * umPerPixel) ?? NICE_UM[0];
  return (
    <span className="flex items-center gap-2">
      <span className="scalebar inline-block" style={{ width: um / umPerPixel }} />
      <span>{um >= 1000 ? `${um / 1000} mm` : `${um} µm`}</span>
    </span>
  );
}

function markerLabel(name: string): string {
  return name.replace('Aortic smooth muscle actin', 'SMA').replace('Antigen Ki67', 'Ki-67');
}

/** Marker switches with what each one shows, in plain words, and its on-screen colour. */
function MarkerControls({
  channels,
  visible,
  onToggle,
  onAll,
  onReset,
}: {
  channels: NonNullable<Slide['channels']>;
  visible: Record<string, boolean>;
  onToggle: (id: string) => void;
  onAll: () => void;
  onReset: () => void;
}) {
  return (
    <>
      <ul className="space-y-3">
        {channels.map((c) => {
          const note = MARKER_NOTES[c.id];
          return (
            <li key={c.id}>
              <label className="flex items-center gap-2 text-[13px]">
                <input type="checkbox" className="check" checked={!!visible[c.id]} onChange={() => onToggle(c.id)} />
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: c.color }} />
                <span className="font-medium">{markerLabel(c.name)}</span>
              </label>
              <p className="t-faint mt-1 pl-6 text-[11.5px] leading-snug">{note ? `${note.shows} ${note.why}` : c.meaning}</p>
            </li>
          );
        })}
      </ul>
      <div className="mt-3 flex gap-4 pl-6 text-[12px]">
        <button type="button" className="link t-muted" title={TIPS.markersAll} onClick={onAll}>
          Show all
        </button>
        <button type="button" className="link t-muted" title={TIPS.markersReset} onClick={onReset}>
          Reset
        </button>
        <Link to="/guide#markers" className="link t-muted ml-auto">
          What are markers?
        </Link>
      </div>
    </>
  );
}

function formatMag(mag: number): string {
  return `${mag < 10 ? mag.toFixed(1) : mag.toFixed(0)}×`;
}

function readView(params: URLSearchParams): ViewState | null {
  const x = Number(params.get('x'));
  const y = Number(params.get('y'));
  const z = Number(params.get('z'));
  return params.has('x') && Number.isFinite(x) && Number.isFinite(y) && z > 0 ? { x, y, zoom: z } : null;
}

export function Pathology() {
  const { catalog, loading, error, reload } = useCatalog();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState('');

  const slides = catalog?.slides ?? [];
  const selected = slides.find((s) => s.id === params.get('slide')) ?? slides[0] ?? null;
  // Deep-link coordinates apply only to the slide they were copied from, on first open.
  const [initialView] = useState(() => readView(params));

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return slides;
    return slides.filter((s) =>
      [s.title, s.organ, s.diagnosis, s.project, s.case].some((v) => v.toLowerCase().includes(q))
    );
  }, [slides, query]);

  const select = (s: Slide) => setParams({ slide: s.id });

  if (!catalog) {
    return (
      <div className="flex h-full items-center justify-center">
        {error && !loading ? (
          <div className="text-center">
            <p className="font-medium">The slide catalog could not be read from the Lakehouse.</p>
            <p className="t-faint mt-2 max-w-md break-all text-[12px]">{error}</p>
            <button onClick={() => void reload()} className="btn btn-ink mt-5">
              Try again
            </button>
          </div>
        ) : (
          <p className="t-faint">Reading slide catalog from OneLake…</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <ListColumn
        label="Slides"
        query={query}
        onQuery={setQuery}
        placeholder="Search slides"
        count={`${filtered.length} of ${slides.length} slides`}
      >
        {filtered.map((s) => (
          <button key={s.id} className="list-row" aria-current={s.id === selected?.id} onClick={() => select(s)}>
            <LakehouseImage access={catalog.tileAccess} slide={s} path="thumbnail.jpg" alt="" className="list-thumb" loading="lazy" />
            <span className="min-w-0">
              <span className="block truncate text-[13.5px] font-medium">{s.title}</span>
              <span className="t-faint block truncate text-[11.5px]">
                {s.organ} · {s.kind === 'fluorescence' ? `${s.markersAvailable}-plex IF` : `${s.objectivePower}× H&E`} · {formatGigapixels(s)}
              </span>
            </span>
          </button>
        ))}
        {filtered.length === 0 && <p className="t-faint px-4 py-6 text-[12.5px]">No slides match “{query}”.</p>}
      </ListColumn>

      {selected && (
        <SlideWorkspace
          key={selected.id}
          slide={selected}
          catalog={catalog}
          initialView={selected.id === params.get('slide') ? initialView : null}
          onReload={reload}
        />
      )}
    </div>
  );
}

function SlideWorkspace({
  slide,
  catalog,
  initialView,
  onReload,
}: {
  slide: Slide;
  catalog: SlideCatalog;
  initialView: ViewState | null;
  onReload: () => Promise<void>;
}) {
  const viewerRef = useRef<SlideViewerHandle>(null);
  const [status, setStatus] = useState<ViewerStatus | null>(null);
  const maximise = useMaximise<HTMLDivElement>();
  const details = useDetailsPanel();
  const [pinTitle, setPinTitle] = useState('');
  const [pinNote, setPinNote] = useState('');
  const [saving, setSaving] = useState(false);
  const { pins, addPin, removePin, currentUserId, error: pinsError } = usePins(slide.id);
  const [channels, setChannels] = useState<Record<string, boolean>>(() =>
    Object.fromEntries((slide.channels ?? []).map((c) => [c.id, c.visible]))
  );
  const fluorescence = slide.kind === 'fluorescence' && !!slide.channels?.length;
  const toggleMarker = (id: string) => setChannels((v) => ({ ...v, [id]: !v[id] }));
  const showAllMarkers = () => setChannels(Object.fromEntries((slide.channels ?? []).map((c) => [c.id, true])));
  const resetMarkers = () => setChannels(Object.fromEntries((slide.channels ?? []).map((c) => [c.id, c.visible])));

  const viewerPins = useMemo(
    () => pins.map((p) => ({ id: p.id, title: p.title, x: Number(p.x), y: Number(p.y) })),
    [pins]
  );

  useEffect(() => {
    if (!initialView) return;
    const t = window.setTimeout(() => viewerRef.current?.flyTo(initialView), 900);
    return () => window.clearTimeout(t);
  }, [initialView]);

  const onPinClick = useCallback(
    (id: string) => {
      const pin = pins.find((p) => p.id === id);
      if (pin) viewerRef.current?.flyTo({ x: Number(pin.x), y: Number(pin.y), zoom: Number(pin.zoom) });
    },
    [pins]
  );

  const savePin = async () => {
    const view = viewerRef.current?.getView();
    if (!view || !pinTitle.trim()) return;
    setSaving(true);
    try {
      await addPin({ title: pinTitle.trim(), note: pinNote.trim(), ...view });
      setPinTitle('');
      setPinNote('');
      toast.success('Pin saved to the app database');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save pin');
    } finally {
      setSaving(false);
    }
  };

  const copyLink = async () => {
    const view = viewerRef.current?.getView();
    const url = new URL(window.location.href);
    url.search = '';
    url.searchParams.set('slide', slide.id);
    if (view) {
      url.searchParams.set('x', view.x.toFixed(5));
      url.searchParams.set('y', view.y.toFixed(5));
      url.searchParams.set('z', view.zoom.toFixed(5));
    }
    await navigator.clipboard.writeText(url.toString());
    toast('Link to this view copied');
  };

  const mag = status?.magnification ?? null;
  const presets = [1.25, 5, 10, 20, 40].filter((m) => !slide.objectivePower || m <= slide.objectivePower);
  const physical = formatPhysicalSize(slide);

  return (
    <div ref={maximise.ref} className={`flex min-w-0 flex-1 flex-col ${maximise.on ? 'workspace-max' : ''}`}>
      <WorkspaceHeader
        title={slide.title}
        meta={
          <>
            {slide.organ} · {slide.diagnosis} · <span className="t-mono">{slide.case}</span>
          </>
        }
        description={slide.blurb}
        explain={<PlainWordsLink onOpen={() => details.show('about')} />}
      />

      <div className="hair flex min-h-12 shrink-0 flex-wrap items-center gap-2 border-b px-4 py-2">
        <div className="seg" role="group" aria-label="Magnification">
          {presets.map((m) => (
            <button
              key={m}
              onClick={() => viewerRef.current?.zoomToMagnification(m)}
              title={TIPS.magnification(m)}
              aria-pressed={mag != null && Math.abs(mag - m) / m < 0.04}
            >
              {m}×
            </button>
          ))}
        </div>
        <button
          onClick={() => (status?.touring ? viewerRef.current?.stopTour() : viewerRef.current?.startTour())}
          className={`btn ${status?.touring ? 'btn-ink' : 'btn-primary'}`}
          title={TIPS.tour}
        >
          {status?.touring ? 'Stop tour' : 'Tour'}
        </button>
        <button onClick={() => viewerRef.current?.home()} className="btn" title={TIPS.fit}>
          Fit
        </button>
        <button onClick={() => void copyLink()} className="btn" title={TIPS.copyLink}>
          Copy link
        </button>
        <button onClick={maximise.toggle} className={`btn ${maximise.on ? 'btn-ink' : ''}`} aria-pressed={maximise.on} title={maximise.on ? TIPS.exitFullScreen : TIPS.fullScreen}>
          {maximise.on ? 'Exit full screen' : 'Full screen'}
        </button>
      </div>

      {fluorescence && (
        <div className="hair flex shrink-0 flex-wrap items-center gap-2 border-b px-4 py-2">
          <span className="t-faint mr-1 text-[12px]">
            Markers ({slide.channels!.length} of {slide.markersAvailable ?? slide.channels!.length})
          </span>
          {slide.channels!.map((c) => (
            <button
              key={c.id}
              className="marker-chip"
              aria-pressed={channels[c.id]}
              title={MARKER_NOTES[c.id] ? `${MARKER_NOTES[c.id].shows} ${MARKER_NOTES[c.id].why}` : c.meaning}
              onClick={() => toggleMarker(c.id)}
            >
              <span className="swatch" style={{ background: c.color, color: c.color }} />
              {markerLabel(c.name)}
            </button>
          ))}
          <button className="link t-muted ml-2 text-[12px]" title={TIPS.markersAll} onClick={showAllMarkers}>
            all
          </button>
          <button className="link t-muted text-[12px]" title={TIPS.markersReset} onClick={resetMarkers}>
            reset
          </button>
          <Link to="/guide#markers" className="link t-muted ml-auto text-[12px]">
            What are markers?
          </Link>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="relative min-h-0 flex-1">
            <SlideViewer
              channelVisibility={fluorescence ? channels : undefined}
              ref={viewerRef}
              slide={slide}
              access={catalog.tileAccess}
              pins={viewerPins}
              onStatus={setStatus}
              onPinClick={onPinClick}
              onAccessExpired={() => void onReload()}
            />
          </div>
          <div className="statusbar flex h-9 shrink-0 items-center gap-6 px-4 text-[12.5px]">
            <span className="w-14 text-[14px] font-semibold">{mag != null ? formatMag(mag) : '…'}</span>
            <ScaleBar umPerPixel={status?.umPerPixel ?? null} />
            <span className="t-muted">{(status?.tilesLoaded ?? 0).toLocaleString()} tiles loaded</span>
            {status?.firstTileMs != null && <span className="t-faint">first tile {status.firstTileMs} ms</span>}
            {!!status?.tilesFailed && <span className="t-accent">{status.tilesFailed} failed</span>}
            <span className="t-faint ml-auto hidden lg:inline">Scroll to zoom · drag to pan · double-click to zoom in</span>
          </div>
        </div>

        <DetailsPanel
          panel={details}
          about={
            <>
                <PanelSection title="In plain words">
                  <PlainWords note={slideNote(slide.id, slide.kind)} guideHref={fluorescence ? '/guide#markers' : '/guide#pathology-controls'} />
                </PanelSection>

                <PanelSection title="Specimen">
                  <dl>
                    <PanelRow term="Project">{slide.project}</PanelRow>
                    <PanelRow term="Case">
                      <span className="t-mono">{slide.case}</span>
                    </PanelRow>
                    <PanelRow term="Scanner">
                      {slide.vendor ? `${slide.vendor[0].toUpperCase()}${slide.vendor.slice(1)}, ` : ''}
                      {slide.objectivePower}× objective
                    </PanelRow>
                    <PanelRow term="Resolution">{slide.mpp ? `${slide.mpp.toFixed(3)} µm per pixel` : 'not recorded'}</PanelRow>
                    <PanelRow term="Pixels">
                      {slide.width.toLocaleString()} × {slide.height.toLocaleString()}
                    </PanelRow>
                    <PanelRow term="Area">{physical ?? 'not recorded'}</PanelRow>
                    <PanelRow term="Pyramid">
                      {slide.levels} levels, {slide.tileCount.toLocaleString()} tiles
                    </PanelRow>
                    <PanelRow term="Source file">
                      {fluorescence ? `${slide.sourceFile}, ${formatBytes(slide.rawSizeBytes)}` : `${formatBytes(slide.rawSizeBytes)} Aperio SVS`}
                    </PanelRow>
                    {slide.license && <PanelRow term="Licence">{slide.license}</PanelRow>}
                  </dl>
                </PanelSection>

                <PanelSection title="Storage">
                  <div className="text-[12.5px]">
                    {catalog.lakehouse.workspaceName}/<span className="font-semibold">{catalog.lakehouse.lakehouseName}</span>
                  </div>
                  <ul className="t-muted t-mono mt-2 space-y-1 break-all text-[11.5px]">
                    <li>Files/{slide.raw}</li>
                    <li>Files/{fluorescence ? `${slide.tiles}/<marker>/slide.dzi` : slide.dzi}</li>
                    <li>Files/{slide.tiles}/</li>
                  </ul>
                  <div className="mt-3 flex gap-4 text-[12.5px]">
                    <a href={catalog.lakehouse.portalUrl} target="_blank" rel="noreferrer" className="link">
                      Open in Fabric ↗
                    </a>
                    <a href={slide.sourceUrl} target="_blank" rel="noreferrer" className="link">
                      {slide.sourceUrl.includes('gdc.cancer.gov') ? 'GDC record ↗' : 'Source ↗'}
                    </a>
                  </div>
                </PanelSection>
            </>
          }
          controls={
            <>
              {fluorescence && (
                <PanelSection title={`Markers (${slide.channels!.length} of ${slide.markersAvailable ?? slide.channels!.length})`}>
                  <MarkerControls
                    channels={slide.channels!}
                    visible={channels}
                    onToggle={toggleMarker}
                    onAll={showAllMarkers}
                    onReset={resetMarkers}
                  />
                </PanelSection>
              )}

                <PanelSection title={`Pins (${pins.length})`} aside={<span>shared with all viewers</span>}>
                  {pinsError && <p className="t-accent text-[12px]">{pinsError}</p>}
                  {pins.length === 0 && !pinsError && (
                    <p className="t-faint text-[12.5px]">No pins yet. Zoom to a region and give it a name.</p>
                  )}
                  <ul>
                    {pins.map((pin) => (
                      <li key={pin.id} className="hair flex items-start gap-3 border-b py-2.5 last:border-b-0">
                        <span className="mt-[6px] h-2 w-2 shrink-0 rounded-full" style={{ background: 'var(--accent)' }} />
                        <button className="min-w-0 flex-1 text-left" onClick={() => onPinClick(pin.id)}>
                          <span className="block truncate text-[13px] font-medium hover:underline">{pin.title}</span>
                          {pin.note && <span className="t-muted block text-[12px]">{pin.note}</span>}
                          <span className="t-faint block text-[11.5px]">
                            {slide.objectivePower ? `${formatMag(slide.objectivePower * Number(pin.zoom))} · ` : ''}
                            {pin.authorName}
                          </span>
                        </button>
                        {pin.createdBy === currentUserId && (
                          <button
                            onClick={() => void removePin(pin.id).catch((e) => toast.error(String(e)))}
                            className="link t-faint text-[11.5px]"
                          >
                            remove
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                  <div className="mt-4 space-y-2">
                    <input
                      value={pinTitle}
                      onChange={(e) => setPinTitle(e.target.value.slice(0, 120))}
                      placeholder="Name this view"
                      aria-label="Pin name"
                      className="field"
                      onKeyDown={(e) => e.key === 'Enter' && void savePin()}
                    />
                    <input
                      value={pinNote}
                      onChange={(e) => setPinNote(e.target.value.slice(0, 500))}
                      placeholder="Note (optional)"
                      aria-label="Pin note"
                      className="field"
                    />
                    <button
                      onClick={() => void savePin()}
                      disabled={saving || !pinTitle.trim()}
                      className="btn btn-ink w-full justify-center"
                    >
                      {saving ? 'Saving…' : 'Pin this view'}
                    </button>
                  </div>
                </PanelSection>

                <PanelSection title="Moving around">
                  <p className="t-muted text-[12.5px] leading-relaxed">
                    Scroll to zoom, drag to pan, double-click to zoom in. The magnification buttons jump to what a
                    microscope lens of that power would show; Tour flies through the most cell-dense areas.
                  </p>
                </PanelSection>
            </>
          }
        />
      </div>
    </div>
  );
}
