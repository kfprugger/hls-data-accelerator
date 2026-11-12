import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist';

import { STORE_NAME } from '@/lib/localMode';

type PdfJs = typeof import('pdfjs-dist');

// Decoders and standard fonts, copied next to the app by the pdfjs-assets plugin in vite.config.ts.
const PDFJS_ASSETS = new URL(`${import.meta.env.BASE_URL}pdfjs/`, window.location.origin).href;
const FILES: [kind: string, dir: string, names: string[]][] = [
  ['wasmUrl', 'wasm/', ['jbig2.wasm', 'openjpeg.wasm', 'qcms_bg.wasm']],
  [
    'standardFontDataUrl',
    'standard_fonts/',
    [
      'FoxitDingbats.pfb', 'FoxitFixed.pfb', 'FoxitFixedBold.pfb', 'FoxitFixedBoldItalic.pfb', 'FoxitFixedItalic.pfb',
      'FoxitSerif.pfb', 'FoxitSerifBold.pfb', 'FoxitSerifBoldItalic.pfb', 'FoxitSerifItalic.pfb', 'FoxitSymbol.pfb',
      'LiberationSans-Bold.ttf', 'LiberationSans-BoldItalic.ttf', 'LiberationSans-Italic.ttf', 'LiberationSans-Regular.ttf',
    ],
  ],
];
const files = new Map<string, Uint8Array>();

/** Hands PDF.js its decoders and fonts from memory, so nothing is fetched from the app host at render time. */
class MemoryBinaryData {
  constructor(_options: unknown) {}
  async fetch({ kind, filename }: { kind: string; filename: string }): Promise<Uint8Array> {
    const hit = files.get(`${kind}/${filename}`);
    if (hit) return hit.slice();
    const dir = FILES.find(([k]) => k === kind)?.[1] ?? '';
    const res = await fetch(`${PDFJS_ASSETS}${dir}${filename}`);
    if (!res.ok) throw new Error(`${filename}: HTTP ${res.status}`);
    return new Uint8Array(await res.arrayBuffer());
  }
}

// PDF.js stays out of the main bundle. The static host's sign-in lasts about an hour while a page can stay open much
// longer, so the code, its worker and its data files are all loaded when a record first opens, not when a report
// is first scrolled to.
let warm: Promise<PdfJs> | null = null;
export function warmPdfJs(): Promise<PdfJs> {
  warm ??= (async () => {
    const [lib, worker] = await Promise.all([import('pdfjs-dist'), import('pdfjs-dist/build/pdf.worker.min.mjs?url')]);
    lib.GlobalWorkerOptions.workerPort ??= new Worker(worker.default, { type: 'module' });
    await Promise.all(
      FILES.flatMap(([kind, dir, names]) =>
        names.map(async (name) => {
          if (files.has(`${kind}/${name}`)) return;
          const res = await fetch(`${PDFJS_ASSETS}${dir}${name}`);
          if (res.ok) files.set(`${kind}/${name}`, new Uint8Array(await res.arrayBuffer()));
        })
      )
    );
    return lib;
  })().catch((err) => {
    warm = null;
    throw err;
  });
  return warm;
}

/**
 * Draws the scanned report with PDF.js instead of the browser's PDF plug-in, which is missing or blocked in many
 * places (embedded browsers, managed Edge that opens PDFs externally). The file is read once, when the section comes
 * near the viewport.
 */
const pad = 10;

export function ReportPdf({
  url,
  onPages,
  page = 1,
  onPage,
}: {
  url: string;
  onPages?: (n: number) => void;
  /** Page to show (1-based); scrolling the scan reports the page in view through onPage. */
  page?: number;
  onPage?: (n: number) => void;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const pagesRef = useRef<HTMLDivElement>(null);
  const shown = useRef(1);
  const steering = useRef(0);
  const [near, setNear] = useState(false);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && setNear(true), {
      root: el.closest('#patient-scroll'),
      rootMargin: '800px 0px',
    });
    io.observe(el);
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width / 8) * 8));
    ro.observe(el);
    return () => {
      io.disconnect();
      ro.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!near) return;
    let cancelled = false;
    let task: ReturnType<PdfJs['getDocument']> | null = null;
    (async () => {
      const lib = await warmPdfJs();
      const res = await fetch(url);
      if (!res.ok) throw new Error(res.status === 403 ? 'the signed link has expired; reload the page' : `HTTP ${res.status}`);
      const data = new Uint8Array(await res.arrayBuffer());
      if (cancelled) return;
      task = lib.getDocument({
        data,
        wasmUrl: `${PDFJS_ASSETS}wasm/`,
        standardFontDataUrl: `${PDFJS_ASSETS}standard_fonts/`,
        useWorkerFetch: false,
        BinaryDataFactory: MemoryBinaryData,
      });
      const d = await task.promise;
      if (cancelled) return;
      setDoc(d);
      onPages?.(d.numPages);
    })().catch((err) => !cancelled && setError(err instanceof Error ? err.message : String(err)));
    return () => {
      cancelled = true;
      void task?.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, near]);

  // Scroll to the requested page; ignore the scroll events that this causes.
  useEffect(() => {
    const box = boxRef.current;
    const target = pagesRef.current?.children[page - 1] as HTMLElement | undefined;
    if (!box || !target || page === shown.current) return;
    shown.current = page;
    steering.current = Date.now();
    box.scrollTo({ top: target.offsetTop - pad, behavior: 'smooth' });
  }, [page, doc]);

  const onScroll = () => {
    const box = boxRef.current;
    const kids = pagesRef.current?.children;
    if (!box || !kids || Date.now() - steering.current < 700) return;
    const mid = box.scrollTop + box.clientHeight / 3;
    let n = 1;
    for (let i = 0; i < kids.length; i++) if ((kids[i] as HTMLElement).offsetTop <= mid) n = i + 1;
    if (n !== shown.current) {
      shown.current = n;
      onPage?.(n);
    }
  };

  const pageWidth = Math.max(0, width - pad * 2);
  return (
    <div ref={boxRef} onScroll={onScroll} className="hair relative h-[420px] overflow-y-auto border" style={{ background: 'var(--plate)' }}>
      {error ? (
        <div className="t-faint p-4 text-[13px]">The scanned report could not be shown here ({error}). Use “Open in a new tab”.</div>
      ) : !doc || pageWidth === 0 ? (
        <div className="t-faint p-4 text-[13px]">Reading the scan from {STORE_NAME}…</div>
      ) : (
        <div ref={pagesRef} className="flex flex-col" style={{ padding: pad, gap: pad }}>
          {Array.from({ length: doc.numPages }, (_, i) => (
            <PdfPage key={i} doc={doc} n={i + 1} width={pageWidth} />
          ))}
        </div>
      )}
    </div>
  );
}

function PdfPage({ doc, n, width }: { doc: PDFDocumentProxy; n: number; width: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [height, setHeight] = useState(Math.round(width * 1.294));

  useEffect(() => {
    let cancelled = false;
    let task: RenderTask | null = null;
    (async () => {
      const page = await doc.getPage(n);
      const canvas = ref.current;
      if (cancelled || !canvas) return;
      const base = page.getViewport({ scale: 1 });
      const scale = width / base.width;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const viewport = page.getViewport({ scale: scale * dpr });
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      setHeight(Math.round(base.height * scale));
      task = page.render({ canvas, viewport });
      await task.promise;
    })().catch((err) => {
      if (!cancelled && (err as { name?: string })?.name !== 'RenderingCancelledException') console.warn('Report page render failed', err);
    });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [doc, n, width]);

  return (
    <canvas
      ref={ref}
      role="img"
      aria-label={`Scanned pathology report, page ${n} of ${doc.numPages}`}
      className="hair block border bg-white"
      style={{ width, height }}
    />
  );
}
