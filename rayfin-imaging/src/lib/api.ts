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
export type Provenance = PatientBundle['provenance'];
export type FileAccess = PatientBundle['access']['slide'];
export type Row = PatientBundle['patient'];
export type Cell = Row[string];
export type Silo = 'clinical' | 'genomics' | 'imaging';

export const SILO_NAMES: Record<Silo, string> = {
  clinical: 'clinical_lakehouse',
  genomics: 'genomics_lakehouse',
  imaging: 'imaging_lakehouse',
};

export async function fetchCohort(): Promise<Cohort> {
  if (LOCAL_DATA) return localApi('getCohort');
  return getRayfinClient().functions.getCohort.invoke(undefined, { timeoutMs: 90_000 });
}

export async function fetchPatient(patientId: string): Promise<PatientBundle> {
  if (LOCAL_DATA) return localApi(`getPatient?patientId=${encodeURIComponent(patientId)}`);
  return getRayfinClient().functions.getPatient.invoke({ patientId }, { timeoutMs: 90_000 });
}

export async function fetchDataMap(): Promise<DataMap> {
  if (LOCAL_DATA) return localApi('getDataMap');
  return getRayfinClient().functions.getDataMap.invoke(undefined, { timeoutMs: 90_000 });
}

export async function fetchWardFlowCohort(): Promise<WardFlowCohortSnapshot> {
  if (LOCAL_DATA) return localApi('getWardFlowCohort');
  return getRayfinClient().functions.getWardFlowCohort.invoke(undefined, { timeoutMs: 90_000 });
}

export async function fetchStandardsMapping(patientId: string): Promise<StandardsMapping> {
  if (LOCAL_DATA) return localApi(`getStandardsMapping?patientId=${encodeURIComponent(patientId)}`);
  return getRayfinClient().functions.getStandardsMapping.invoke({ patientId }, { timeoutMs: 90_000 });
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
