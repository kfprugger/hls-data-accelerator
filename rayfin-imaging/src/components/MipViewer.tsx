import { useEffect, useRef, useState } from 'react';

export type MipColormap = 'inverted' | 'gray' | 'hot' | 'inferno';

export const MIP_COLORMAPS: { id: MipColormap; label: string }[] = [
  { id: 'inverted', label: 'Inverted grey' },
  { id: 'gray', label: 'Grey' },
  { id: 'hot', label: 'Hot' },
  { id: 'inferno', label: 'Inferno' },
];

interface MipSprite {
  sprite: string;
  frames: number;
  cols: number;
  frameWidth: number;
  frameHeight: number;
}

interface Props {
  url: string;
  mip: MipSprite;
  colormap: MipColormap;
  spin: boolean;
  /** Gamma applied on top of the colour map; below 1 lifts faint uptake. */
  gamma: number;
  onLoaded?: (ms: number) => void;
}

/** 256-entry RGB lookup table for a colour map. */
function makeLut(cmap: MipColormap, gamma: number): Uint8ClampedArray {
  const lut = new Uint8ClampedArray(256 * 3);
  const stops: Record<MipColormap, [number, number, number, number][]> = {
    gray: [[0, 0, 0, 0], [1, 255, 255, 255]],
    inverted: [[0, 255, 255, 255], [1, 0, 0, 0]],
    hot: [[0, 0, 0, 0], [0.38, 230, 0, 0], [0.75, 255, 210, 0], [1, 255, 255, 255]],
    inferno: [[0, 0, 0, 4], [0.25, 87, 16, 110], [0.5, 188, 55, 84], [0.75, 249, 142, 9], [1, 252, 255, 164]],
  };
  const s = stops[cmap];
  for (let i = 0; i < 256; i++) {
    const t = Math.pow(i / 255, gamma);
    let k = 0;
    while (k < s.length - 2 && t > s[k + 1][0]) k++;
    const [t0, r0, g0, b0] = s[k];
    const [t1, r1, g1, b1] = s[k + 1];
    const f = (t - t0) / (t1 - t0 || 1);
    lut[i * 3] = r0 + (r1 - r0) * f;
    lut[i * 3 + 1] = g0 + (g1 - g0) * f;
    lut[i * 3 + 2] = b0 + (b1 - b0) * f;
  }
  return lut;
}

/**
 * Rotating maximum intensity projection: the pipeline renders the volume from N angles into one sprite
 * sheet; this view shows one angle at a time. Drag sideways to rotate.
 */
export function MipViewer({ url, mip, colormap, spin, gamma, onLoaded }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const pixelsRef = useRef<Uint8ClampedArray | null>(null);
  const [frame, setFrame] = useState(0);
  const [ready, setReady] = useState(false);
  const drag = useRef<{ x: number; frame: number } | null>(null);

  // Load the sprite once and keep its grey values.
  useEffect(() => {
    let cancelled = false;
    const started = performance.now();
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      if (cancelled) return;
      const c = document.createElement('canvas');
      c.width = img.width;
      c.height = img.height;
      const ctx = c.getContext('2d', { willReadFrequently: true })!;
      ctx.drawImage(img, 0, 0);
      const rgba = ctx.getImageData(0, 0, img.width, img.height).data;
      const grey = new Uint8ClampedArray(img.width * img.height);
      for (let i = 0; i < grey.length; i++) grey[i] = rgba[i * 4];
      pixelsRef.current = grey;
      setReady(true);
      onLoaded?.(Math.round(performance.now() - started));
    };
    img.src = url;
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  // Draw the current frame through the colour map, fitted to the canvas.
  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    const grey = pixelsRef.current;
    if (!canvas || !wrap || !grey || !ready) return;
    const { frameWidth: w, frameHeight: h, cols } = mip;
    const sheetW = w * cols;
    const fx = (frame % cols) * w;
    const fy = Math.floor(frame / cols) * h;
    const lut = makeLut(colormap, gamma);
    const frameImg = new ImageData(w, h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const v = grey[(fy + y) * sheetW + fx + x];
        const o = (y * w + x) * 4;
        frameImg.data[o] = lut[v * 3];
        frameImg.data[o + 1] = lut[v * 3 + 1];
        frameImg.data[o + 2] = lut[v * 3 + 2];
        frameImg.data[o + 3] = 255;
      }
    }
    const off = document.createElement('canvas');
    off.width = w;
    off.height = h;
    off.getContext('2d')!.putImageData(frameImg, 0, 0);
    const dpr = window.devicePixelRatio || 1;
    const cw = wrap.clientWidth;
    const ch = wrap.clientHeight;
    canvas.width = cw * dpr;
    canvas.height = ch * dpr;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = colormap === 'inverted' ? '#ffffff' : '#000000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    const scale = Math.min((cw * 0.94) / w, (ch * 0.94) / h) * dpr;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(off, (canvas.width - w * scale) / 2, (canvas.height - h * scale) / 2, w * scale, h * scale);
  }, [frame, colormap, gamma, mip, ready]);

  // Redraw on resize.
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const ro = new ResizeObserver(() => setFrame((f) => f));
    ro.observe(wrap);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!spin) return;
    const t = window.setInterval(() => setFrame((f) => (f + 1) % mip.frames), 90);
    return () => window.clearInterval(t);
  }, [spin, mip.frames]);

  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const step = Math.round((e.clientX - drag.current.x) / 8);
    setFrame((((drag.current.frame - step) % mip.frames) + mip.frames) % mip.frames);
  };

  return (
    <div
      ref={wrapRef}
      className="absolute inset-0 cursor-ew-resize select-none"
      style={{ background: colormap === 'inverted' ? '#fff' : '#000' }}
      onPointerDown={(e) => {
        drag.current = { x: e.clientX, frame };
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
      }}
      onPointerMove={onPointerMove}
      onPointerUp={() => (drag.current = null)}
    >
      <canvas ref={canvasRef} className="h-full w-full" />
      <div
        className="pointer-events-none absolute bottom-3 left-4 text-[12px] tabular-nums"
        style={{ color: colormap === 'inverted' ? '#57564f' : '#b9b6ac' }}
      >
        {Math.round((360 * frame) / mip.frames)}° · drag to rotate
      </div>
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center text-[13px]" style={{ color: '#8a887e' }}>
          Loading projection…
        </div>
      )}
    </div>
  );
}
