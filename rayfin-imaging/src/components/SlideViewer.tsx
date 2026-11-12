import OpenSeadragon from 'openseadragon';
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  type ReactNode,
} from 'react';

import {
  lakehouseUrl,
  loadViaProxy,
  PROXY_SCHEME,
  type Slide,
  type TileAccess,
} from '@/lib/catalog';

export interface ViewState {
  x: number;
  y: number;
  /** Image zoom: 1 = one screen pixel per scanned pixel (full objective magnification). */
  zoom: number;
}

export interface ViewerStatus {
  magnification: number | null;
  umPerPixel: number | null;
  tilesLoaded: number;
  tilesFailed: number;
  firstTileMs: number | null;
  touring: boolean;
}

export interface SlideViewerHandle {
  home: () => void;
  zoomToMagnification: (mag: number) => void;
  getView: () => ViewState | null;
  flyTo: (view: ViewState) => void;
  startTour: () => void;
  stopTour: () => void;
}

export interface ViewerPin {
  id: string;
  title: string;
  x: number;
  y: number;
}

interface SlideViewerProps {
  slide: Slide;
  access: TileAccess;
  pins: ViewerPin[];
  onStatus: (status: ViewerStatus) => void;
  onPinClick?: (id: string) => void;
  onAccessExpired?: () => void;
  children?: ReactNode;
  /** Fluorescence slides: marker id -> shown. */
  channelVisibility?: Record<string, boolean>;
}

const NORMAL_ANIMATION = 1.2;
const TOUR_ANIMATION = 2.6;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = window.setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      window.clearTimeout(t);
      reject(new DOMException('aborted', 'AbortError'));
    });
  });
}

/** `tilesPath` is relative to the slide folder: `slide_files` or `channels/<marker>/slide_files`. */
function buildTileSource(
  slide: Slide,
  accessRef: { current: TileAccess },
  tilesPath = 'slide_files'
): OpenSeadragon.TileSource {
  const source = new OpenSeadragon.TileSource({
    width: slide.width,
    height: slide.height,
    tileSize: slide.tileSize,
    tileOverlap: slide.overlap,
    minLevel: 0,
    maxLevel: slide.levels - 1,
  } as unknown as OpenSeadragon.TileSourceOptions);

  source.getTileUrl = (level: number, x: number, y: number) =>
    lakehouseUrl(accessRef.current, slide, `${tilesPath}/${level}/${x}_${y}.${slide.format}`);

  type Job = {
    src: string;
    userData: { aborted?: boolean };
    finish: (data: HTMLImageElement | null, request: null, error: string) => void;
  };
  const defaultStart = source.downloadTileStart.bind(source);
  // Proxy mode: tiles arrive as base64 from the `getTiles` Rayfin function.
  source.downloadTileStart = (ctx: OpenSeadragon.ImageJob) => {
    const job = ctx as unknown as Job;
    if (!job.src.startsWith(PROXY_SCHEME)) {
      defaultStart(ctx);
      return;
    }
    const image = new Image();
    job.userData.aborted = false;
    loadViaProxy(job.src)
      .then((dataUrl) => {
        if (job.userData.aborted) return;
        image.onload = () => job.finish(image, null, '');
        image.onerror = () => job.finish(null, null, 'Tile decode failed');
        image.src = dataUrl;
      })
      .catch((error) => job.finish(null, null, String(error)));
  };
  const defaultAbort = source.downloadTileAbort.bind(source);
  source.downloadTileAbort = (ctx: OpenSeadragon.ImageJob) => {
    const job = ctx as unknown as Job;
    if (job.src.startsWith(PROXY_SCHEME)) {
      job.userData.aborted = true;
      return;
    }
    defaultAbort(ctx);
  };
  return source;
}

export const SlideViewer = forwardRef<SlideViewerHandle, SlideViewerProps>(function SlideViewer(
  { slide, access, pins, onStatus, onPinClick, onAccessExpired, children, channelVisibility },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<OpenSeadragon.Viewer | null>(null);
  const accessRef = useRef(access);
  const channelVisRef = useRef(channelVisibility);
  channelVisRef.current = channelVisibility;
  const statusRef = useRef<ViewerStatus>({
    magnification: null,
    umPerPixel: null,
    tilesLoaded: 0,
    tilesFailed: 0,
    firstTileMs: null,
    touring: false,
  });
  const tourRef = useRef<AbortController | null>(null);
  const onStatusRef = useRef(onStatus);
  const onPinClickRef = useRef(onPinClick);
  const onExpiredRef = useRef(onAccessExpired);
  onStatusRef.current = onStatus;
  onPinClickRef.current = onPinClick;
  onExpiredRef.current = onAccessExpired;
  accessRef.current = access;

  const emit = (patch: Partial<ViewerStatus>) => {
    statusRef.current = { ...statusRef.current, ...patch };
    onStatusRef.current(statusRef.current);
  };

  const setAnimation = (seconds: number) => {
    const vp = viewerRef.current?.viewport as unknown as {
      centerSpringX: { animationTime: number };
      centerSpringY: { animationTime: number };
      zoomSpring: { animationTime: number };
    };
    if (!vp) return;
    vp.centerSpringX.animationTime = seconds;
    vp.centerSpringY.animationTime = seconds;
    vp.zoomSpring.animationTime = seconds;
  };

  useEffect(() => {
    if (!containerRef.current) return;
    const opened = performance.now();
    statusRef.current = {
      magnification: null,
      umPerPixel: null,
      tilesLoaded: 0,
      tilesFailed: 0,
      firstTileMs: null,
      touring: false,
    };

    const viewer = OpenSeadragon({
      element: containerRef.current,
      // Fluorescence: one tiled image per marker, added together like light ('lighter' compositing).
      tileSources: (slide.channels?.length
        ? slide.channels.map((ch) => ({
            tileSource: buildTileSource(slide, accessRef, `channels/${ch.id}/slide_files`),
            compositeOperation: 'lighter',
            opacity: (channelVisRef.current?.[ch.id] ?? ch.visible) ? 1 : 0,
          }))
        : buildTileSource(slide, accessRef)) as unknown as OpenSeadragon.TileSourceOptions,
      // Composite operations need the canvas drawer.
      ...(slide.channels?.length ? { drawer: 'canvas' } : {}),
      showNavigationControl: false,
      showNavigator: true,
      navigatorPosition: 'BOTTOM_LEFT',
      navigatorSizeRatio: 0.15,
      navigatorAutoFade: false,
      navigatorBackground: '#faf9f5',
      navigatorBorderColor: '#141413',
      navigatorDisplayRegionColor: '#f26419',
      animationTime: NORMAL_ANIMATION,
      springStiffness: 6.5,
      blendTime: 0.25,
      maxZoomPixelRatio: 2,
      minZoomImageRatio: 0.6,
      visibilityRatio: 0.4,
      imageLoaderLimit: 12,
      timeout: 60_000,
      smoothTileEdgesMinZoom: 1.1,
      immediateRender: false,
      gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
      // OneLake answers simple GETs with `Access-Control-Allow-Origin: *`, so tiles stay untainted
      // and OpenSeadragon can keep its WebGL drawer.
      crossOriginPolicy: 'Anonymous',
    });
    viewerRef.current = viewer;

    const updateZoom = () => {
      const vp = viewer.viewport;
      const item = viewer.world.getItemAt(0);
      if (!item) return;
      const imageZoom = item.viewportToImageZoom(vp.getZoom(true));
      emit({
        magnification: slide.objectivePower ? slide.objectivePower * imageZoom : null,
        umPerPixel: slide.mpp ? slide.mpp / imageZoom : null,
      });
    };

    let failuresSinceRefresh = 0;
    viewer.addHandler('animation', updateZoom);
    viewer.addHandler('open', updateZoom);
    viewer.addHandler('resize', updateZoom);
    viewer.addHandler('tile-loaded', () => {
      failuresSinceRefresh = 0;
      emit({
        tilesLoaded: statusRef.current.tilesLoaded + 1,
        firstTileMs: statusRef.current.firstTileMs ?? Math.round(performance.now() - opened),
      });
    });
    viewer.addHandler('canvas-press', () => tourRef.current?.abort());
    viewer.addHandler('canvas-scroll', () => tourRef.current?.abort());
    viewer.addHandler('tile-load-failed', () => {
      emit({ tilesFailed: statusRef.current.tilesFailed + 1 });
      failuresSinceRefresh += 1;
      if (failuresSinceRefresh === 6) onExpiredRef.current?.();
    });

    return () => {
      tourRef.current?.abort();
      viewer.destroy();
      viewerRef.current = null;
    };
    // The viewer is rebuilt only when the slide changes; access changes are read through accessRef.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slide.id]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || !slide.channels?.length || !channelVisibility) return;
    slide.channels.forEach((ch, i) => {
      viewer.world.getItemAt(i)?.setOpacity(channelVisibility[ch.id] ? 1 : 0);
    });
  }, [channelVisibility, slide.channels]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const elements = pins.map((pin) => {
      const el = document.createElement('button');
      el.className = 'slide-pin';
      el.title = pin.title;
      el.innerHTML = `<span class="slide-pin-dot"></span><span class="slide-pin-label">${pin.title
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')}</span>`;
      new OpenSeadragon.MouseTracker({
        element: el,
        clickHandler: () => onPinClickRef.current?.(pin.id),
      });
      viewer.addOverlay({
        element: el,
        location: new OpenSeadragon.Point(pin.x, pin.y),
        placement: OpenSeadragon.Placement.CENTER,
        checkResize: false,
      });
      return el;
    });
    return () => elements.forEach((el) => viewerRef.current?.removeOverlay(el));
  }, [pins, slide.id]);

  const zoomToImageZoom = (imageZoom: number, center?: OpenSeadragon.Point) => {
    const viewer = viewerRef.current;
    const item = viewer?.world.getItemAt(0);
    if (!viewer || !item) return;
    if (center) viewer.viewport.panTo(center);
    viewer.viewport.zoomTo(item.imageToViewportZoom(imageZoom), undefined, false);
  };

  useImperativeHandle(ref, () => ({
    home: () => viewerRef.current?.viewport.goHome(),
    zoomToMagnification: (mag: number) => {
      if (!slide.objectivePower) return;
      zoomToImageZoom(mag / slide.objectivePower);
    },
    getView: () => {
      const viewer = viewerRef.current;
      const item = viewer?.world.getItemAt(0);
      if (!viewer || !item) return null;
      const c = viewer.viewport.getCenter(true);
      return { x: c.x, y: c.y, zoom: item.viewportToImageZoom(viewer.viewport.getZoom(true)) };
    },
    flyTo: (view: ViewState) => {
      zoomToImageZoom(view.zoom, new OpenSeadragon.Point(view.x, view.y));
    },
    startTour: () => {
      tourRef.current?.abort();
      const controller = new AbortController();
      tourRef.current = controller;
      const { signal } = controller;
      const objective = slide.objectivePower ?? 40;
      const stops = slide.hotspots.slice(0, 4);
      emit({ touring: true });
      setAnimation(TOUR_ANIMATION);
      void (async () => {
        try {
          viewerRef.current?.viewport.goHome();
          await sleep(1800, signal);
          for (const spot of stops) {
            const point = new OpenSeadragon.Point(spot.x, spot.y);
            zoomToImageZoom(2.5 / objective, point);
            await sleep(2800, signal);
            zoomToImageZoom(10 / objective, point);
            await sleep(2800, signal);
            zoomToImageZoom(1, point);
            await sleep(4200, signal);
            zoomToImageZoom(1.25 / objective, point);
            await sleep(2400, signal);
          }
          viewerRef.current?.viewport.goHome();
        } catch {
          // Tour cancelled.
        } finally {
          setAnimation(NORMAL_ANIMATION);
          if (tourRef.current === controller) {
            tourRef.current = null;
            emit({ touring: false });
          }
        }
      })();
    },
    stopTour: () => tourRef.current?.abort(),
  }));

  return (
    <div className="relative h-full w-full">
      <div
        ref={containerRef}
        className={`absolute inset-0 slide-canvas ${slide.kind === 'fluorescence' ? 'slide-canvas-dark' : ''}`}
      />
      {children}
    </div>
  );
});
