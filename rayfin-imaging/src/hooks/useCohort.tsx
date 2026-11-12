import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';

import { fetchCohort, fetchPatient, type Cohort, type PatientBundle } from '@/lib/api';

/** Signed URLs last 55 minutes; refetch well before. */
const MAX_AGE_MS = 30 * 60_000;

interface CohortState {
  cohort: Cohort | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  /** Patient bundles already read this session, keyed by id. */
  getPatient: (id: string) => Promise<PatientBundle>;
  peekPatient: (id: string) => PatientBundle | null;
}

const Ctx = createContext<CohortState | undefined>(undefined);

type Entry = { at: number; promise: Promise<PatientBundle>; value: PatientBundle | null };

export function CohortProvider({ children }: { children: ReactNode }) {
  const [cohort, setCohort] = useState<Cohort | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const cache = useRef(new Map<string, Entry>());

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setCohort(await fetchCohort());
      setError(null);
    } catch (err) {
      console.error('Cohort load failed', err);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const getPatient = useCallback((id: string) => {
    const hit = cache.current.get(id);
    if (hit && Date.now() - hit.at < MAX_AGE_MS) return hit.promise;
    const entry: Entry = { at: Date.now(), promise: fetchPatient(id), value: null };
    entry.promise.then(
      (v) => (entry.value = v),
      () => cache.current.delete(id)
    );
    cache.current.set(id, entry);
    return entry.promise;
  }, []);

  const peekPatient = useCallback((id: string) => {
    const hit = cache.current.get(id);
    return hit && Date.now() - hit.at < MAX_AGE_MS ? hit.value : null;
  }, []);

  return (
    <Ctx.Provider value={{ cohort, loading, error, reload, getPatient, peekPatient }}>{children}</Ctx.Provider>
  );
}

export function useCohort(): CohortState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useCohort must be used within CohortProvider');
  return ctx;
}

/** Loads one patient; keeps showing the previous patient until the next one arrives. */
export function usePatient(id: string | null) {
  const { getPatient, peekPatient } = useCohort();
  const [bundle, setBundle] = useState<PatientBundle | null>(() => (id ? peekPatient(id) : null));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadMs, setLoadMs] = useState<number | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    const cached = peekPatient(id);
    if (cached) {
      setBundle(cached);
      setLoadMs(null);
      setError(null);
      return;
    }
    setLoading(true);
    const t0 = performance.now();
    getPatient(id)
      .then((b) => {
        if (cancelled) return;
        setBundle(b);
        setError(null);
        setLoadMs(Math.round(performance.now() - t0));
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : String(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id, getPatient, peekPatient]);

  return { bundle: bundle && bundle.patient.patient_id === id ? bundle : null, stale: bundle, loading, error, loadMs };
}
