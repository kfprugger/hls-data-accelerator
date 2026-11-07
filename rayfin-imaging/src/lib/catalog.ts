import type { AppFunctionsSchema } from '../../rayfin/functions/src/types';
import { getRayfinClient } from '@/services/rayfin/RayfinClientService';

export type SlideCatalog = AppFunctionsSchema['getSlideCatalog']['output'];
export type Slide = SlideCatalog['slides'][number];
export type TileAccess = SlideCatalog['tileAccess'];

/** Tile paths in proxy mode are `proxy://<slideId>/<path>`; OpenSeadragon only needs a unique key. */
export const PROXY_SCHEME = 'proxy://';

export async function fetchCatalog(): Promise<SlideCatalog> {
  return getRayfinClient().functions.getSlideCatalog.invoke(undefined, {
    timeoutMs: 60_000,
  });
}

/** Builds a URL for a file inside the Lakehouse `Files/slides` folder. */
export function lakehouseUrl(access: TileAccess, slide: Slide, path: string): string {
  if (access.mode === 'sas') {
    return `${access.baseUrl}/slides/${slide.id}/${path}?${access.query}`;
  }
  return `${PROXY_SCHEME}${slide.id}/${path}`;
}

type Pending = {
  path: string;
  resolve: (dataUrl: string) => void;
  reject: (error: unknown) => void;
};

const BATCH_SIZE = 12;
const queues = new Map<string, Pending[]>();
let flushTimer: number | undefined;

function flush(): void {
  flushTimer = undefined;
  for (const [slideId, queue] of queues) {
    queues.delete(slideId);
    for (let i = 0; i < queue.length; i += BATCH_SIZE) {
      const batch = queue.slice(i, i + BATCH_SIZE);
      getRayfinClient()
        .functions.getTiles.invoke(
          { slideId, paths: batch.map((p) => p.path) },
          { timeoutMs: 60_000 }
        )
        .then((tiles) => {
          const byPath = new Map(tiles.map((t) => [t.path, t]));
          for (const p of batch) {
            const tile = byPath.get(p.path);
            if (tile) p.resolve(`data:${tile.contentType};base64,${tile.data}`);
            else p.reject(new Error(`Tile ${p.path} missing`));
          }
        })
        .catch((error) => batch.forEach((p) => p.reject(error)));
    }
  }
}

/** Loads a Lakehouse file through the `getTiles` function, batching concurrent requests. */
export function loadViaProxy(proxyUrl: string): Promise<string> {
  const [slideId, ...rest] = proxyUrl.slice(PROXY_SCHEME.length).split('/');
  return new Promise((resolve, reject) => {
    const queue = queues.get(slideId) ?? [];
    queue.push({ path: rest.join('/'), resolve, reject });
    queues.set(slideId, queue);
    flushTimer ??= window.setTimeout(flush, 25);
  });
}

export function formatGigapixels(slide: Slide): string {
  return `${((slide.width * slide.height) / 1e9).toFixed(2)} GP`;
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`;
  return `${(bytes / 1e3).toFixed(0)} KB`;
}

/** Physical tissue dimensions, e.g. "18.4 × 21.0 mm". */
export function formatPhysicalSize(slide: Slide): string | null {
  if (!slide.mpp) return null;
  const w = (slide.width * slide.mpp) / 1000;
  const h = (slide.height * slide.mpp) / 1000;
  return `${w.toFixed(1)} × ${h.toFixed(1)} mm`;
}
