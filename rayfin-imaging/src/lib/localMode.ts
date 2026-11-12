/**
 * Local mode (`npm run dev:local`): the app runs on this computer with no Fabric capacity, sign-in or backend.
 * The Vite dev server answers the function calls with DuckDB over work/tables and serves the silos' files from
 * work/ (see local/plugin.ts). VITE_LOCAL_DATA is a build-time constant, off in production builds.
 */
export const LOCAL_DATA = import.meta.env.VITE_LOCAL_DATA === '1';

export const LOCAL_USER = { id: 'local-user', email: '', name: 'Local user' };

/** Where files and tables are read from, for loading messages. */
export const STORE_NAME = LOCAL_DATA ? 'work/' : 'OneLake';

export async function localApi<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/local-api/${path}`, init);
  if (!res.ok) {
    const detail = (await res.json().catch(() => null)) as { error?: string } | null;
    throw new Error(detail?.error ?? `Local API ${path} returned ${res.status}`);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
