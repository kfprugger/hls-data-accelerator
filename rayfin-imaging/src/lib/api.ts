import type { AppFunctionsSchema } from '../../rayfin/functions/src/types';
import { LOCAL_DATA, localApi } from '@/lib/localMode';
import { getRayfinClient } from '@/services/rayfin/RayfinClientService';

export type Cohort = AppFunctionsSchema['getCohort']['output'];
export type CohortPatient = Cohort['patients'][number];
export type PatientBundle = AppFunctionsSchema['getPatient']['output'];
export type DataMap = AppFunctionsSchema['getDataMap']['output'];
export type ZeroCopySummary = DataMap['zeroCopy'];
export type DatabricksInteropProof = NonNullable<DataMap['databricksInterop']>;
export type WardFlowCohortSnapshot = AppFunctionsSchema['getWardFlowCohort']['output'];
export type WardFlowSubject = WardFlowCohortSnapshot['subjects'][number];
export type StandardsMapping = AppFunctionsSchema['getStandardsMapping']['output'];
export type AlertStopwatch = AppFunctionsSchema['getAlertStopwatch']['output'];
export type AlertStopwatchBeat = AlertStopwatch['beats'][number];
export type AskDataAgentResponse = AppFunctionsSchema['askDataAgent']['output'];
export type Provenance = PatientBundle['provenance'];
export type FileAccess = PatientBundle['access']['slide'];
export type Row = PatientBundle['patient'];
export type Cell = Row[string];
export type Silo = 'clinical' | 'genomics' | 'imaging';
export type Persona = 'nurse' | 'researcher';

// Hosted mode never restores a stored persona: the server decides the tier from the caller's token.
let currentPersona: Persona =
  LOCAL_DATA && typeof window !== 'undefined' && window.localStorage?.getItem('rayfin_active_persona') === 'researcher'
    ? 'researcher'
    : 'nurse';

export function getActivePersona(): Persona {
  return currentPersona;
}

export function setActivePersona(p: Persona): void {
  currentPersona = p;
}

export const SILO_NAMES: Record<Silo, string> = {
  clinical: 'clinical_lakehouse',
  genomics: 'genomics_lakehouse',
  imaging: 'imaging_lakehouse',
};

export async function fetchCohort(persona?: Persona): Promise<Cohort> {
  const p = persona ?? currentPersona;
  if (LOCAL_DATA) {
    const query = p === 'researcher' ? '?persona=researcher' : '';
    return localApi(`getCohort${query}`, { headers: { 'x-rayfin-persona': p } });
  }
  return getRayfinClient().functions.getCohort.invoke({ persona: p }, { timeoutMs: 90_000 });
}

export async function fetchPatient(patientId: string, persona?: Persona): Promise<PatientBundle> {
  const p = persona ?? currentPersona;
  if (LOCAL_DATA) {
    const query = `patientId=${encodeURIComponent(patientId)}${p === 'researcher' ? '&persona=researcher' : ''}`;
    return localApi(`getPatient?${query}`, { headers: { 'x-rayfin-persona': p } });
  }
  return getRayfinClient().functions.getPatient.invoke({ patientId, persona: p }, { timeoutMs: 90_000 });
}

export async function fetchDataMap(): Promise<DataMap> {
  if (LOCAL_DATA) return localApi('getDataMap');
  return getRayfinClient().functions.getDataMap.invoke(undefined, { timeoutMs: 90_000 });
}

export async function fetchWardFlowCohort(): Promise<WardFlowCohortSnapshot> {
  if (LOCAL_DATA) return localApi('getWardFlowCohort');
  return getRayfinClient().functions.getWardFlowCohort.invoke(undefined, { timeoutMs: 90_000 });
}

export async function fetchStandardsMapping(patientId: string, persona?: Persona): Promise<StandardsMapping> {
  const p = persona ?? currentPersona;
  if (LOCAL_DATA) {
    const query = `patientId=${encodeURIComponent(patientId)}${p === 'researcher' ? '&persona=researcher' : ''}`;
    return localApi(`getStandardsMapping?${query}`, { headers: { 'x-rayfin-persona': p } });
  }
  return getRayfinClient().functions.getStandardsMapping.invoke({ patientId, persona: p }, { timeoutMs: 90_000 });
}

export async function fetchAlertStopwatch(patientId?: string, persona?: Persona): Promise<AlertStopwatch> {
  const p = persona ?? currentPersona;
  if (LOCAL_DATA) {
    const parts: string[] = [];
    if (patientId) parts.push(`patientId=${encodeURIComponent(patientId)}`);
    if (p === 'researcher') parts.push('persona=researcher');
    const query = parts.length > 0 ? `?${parts.join('&')}` : '';
    return localApi(`getAlertStopwatch${query}`, { headers: { 'x-rayfin-persona': p } });
  }
  return getRayfinClient().functions.getAlertStopwatch.invoke({ patientId: patientId ?? '', persona: p }, { timeoutMs: 90_000 });
}

export async function askDataAgent(question: string, persona?: Persona): Promise<AskDataAgentResponse> {
  const trimmed = question.trim();
  if (!trimmed) {
    throw new Error('empty_question');
  }
  if (question.length > 500) {
    throw new Error('question_too_long');
  }
  const p = persona ?? currentPersona;
  if (LOCAL_DATA) {
    return localApi<AskDataAgentResponse>('askDataAgent', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-rayfin-persona': p,
      },
      body: JSON.stringify({ question, persona: p }),
    });
  }
  return getRayfinClient().functions.askDataAgent.invoke({ question }, { timeoutMs: 120_000 });
}

/** URL of a file in a silo's Files area, signed with the read-only SAS from the function (unsigned in local mode). */
export function fileUrl(access: FileAccess, path: string): string {
  return access.query ? `${access.baseUrl}/${path}?${access.query}` : `${access.baseUrl}/${path}`;
}

export function str(v: Cell | undefined): string | null {
  return v === null || v === undefined || v === '' ? null : String(v);
}

export function num(v: Cell | undefined): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export function parseJson<T>(v: Cell | undefined, fallback: T): T {
  if (typeof v !== 'string') return fallback;
  try {
    return JSON.parse(v) as T;
  } catch {
    return fallback;
  }
}
