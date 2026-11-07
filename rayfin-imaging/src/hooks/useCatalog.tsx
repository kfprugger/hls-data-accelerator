import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type Context,
  type ReactNode,
} from 'react';

import { fetchCatalog, type SlideCatalog } from '@/lib/catalog';
import { fetchVolumeCatalog, type VolumeCatalog } from '@/lib/volumes';

/** Refresh well before the 55-minute OneLake SAS expires. */
const REFRESH_MS = 35 * 60_000;
/** Reuse a cached catalog only while its signed access is valid for at least this long. */
const MIN_REMAINING_MS = 15 * 60_000;

interface CatalogState<T> {
  catalog: T | null;
  loading: boolean;
  error: string | null;
  loadMs: number | null;
  reload: () => Promise<void>;
}

interface CatalogSpec<T> {
  name: string;
  cacheKey: string;
  fetch: () => Promise<T>;
  /** ISO expiry of the catalog's signed access; empty when access is not time-limited. */
  expiresOn: (catalog: T) => string;
}

/** Session-scoped cache so reloads render instantly while a fresh catalog loads. */
function readCache<T>(spec: CatalogSpec<T>): T | null {
  try {
    const cached = JSON.parse(sessionStorage.getItem(spec.cacheKey) ?? 'null') as T | null;
    if (!cached) return null;
    const expires = spec.expiresOn(cached);
    if (expires && !(Date.parse(expires) - Date.now() > MIN_REMAINING_MS)) return null;
    return cached;
  } catch {
    return null;
  }
}

function makeProvider<T>(spec: CatalogSpec<T>, Ctx: Context<CatalogState<T> | undefined>) {
  return function Provider({ children }: { children: ReactNode }) {
    const [catalog, setCatalog] = useState<T | null>(() => readCache(spec));
    const [loading, setLoading] = useState(() => catalog === null);
    const [error, setError] = useState<string | null>(null);
    const [loadMs, setLoadMs] = useState<number | null>(null);

    const reload = useCallback(async () => {
      const started = performance.now();
      try {
        const next = await spec.fetch();
        setCatalog(next);
        sessionStorage.setItem(spec.cacheKey, JSON.stringify(next));
        setError(null);
        setLoadMs(Math.round(performance.now() - started));
      } catch (err) {
        console.error(`Failed to load ${spec.name}`, err);
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }, []);

    useEffect(() => {
      void reload();
      const timer = window.setInterval(() => void reload(), REFRESH_MS);
      return () => window.clearInterval(timer);
    }, [reload]);

    return <Ctx.Provider value={{ catalog, loading, error, loadMs, reload }}>{children}</Ctx.Provider>;
  };
}

function makeHook<T>(name: string, Ctx: Context<CatalogState<T> | undefined>) {
  return function useIt(): CatalogState<T> {
    const ctx = useContext(Ctx);
    if (!ctx) throw new Error(`${name} hook must be used within its provider`);
    return ctx;
  };
}

const SlideCtx = createContext<CatalogState<SlideCatalog> | undefined>(undefined);
const VolumeCtx = createContext<CatalogState<VolumeCatalog> | undefined>(undefined);

export const CatalogProvider = makeProvider<SlideCatalog>(
  {
    name: 'slide catalog',
    cacheKey: 'atlas.catalog',
    fetch: fetchCatalog,
    expiresOn: (c) => (c.tileAccess.mode === 'sas' ? c.tileAccess.expiresOn : ''),
  },
  SlideCtx
);
export const useCatalog = makeHook('useCatalog', SlideCtx);

export const VolumeCatalogProvider = makeProvider<VolumeCatalog>(
  {
    name: 'volume catalog',
    cacheKey: 'atlas.volumes',
    fetch: fetchVolumeCatalog,
    expiresOn: (c) => c.access.expiresOn,
  },
  VolumeCtx
);
export const useVolumeCatalog = makeHook('useVolumeCatalog', VolumeCtx);
