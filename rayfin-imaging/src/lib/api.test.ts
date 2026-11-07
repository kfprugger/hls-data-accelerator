import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as localModeModule from './localMode';
import {
  fetchCohort,
  fetchPatient,
  fetchDataMap,
  fetchWardFlowCohort,
  fetchAlertStopwatch,
  str,
  num,
  parseJson,
  fileUrl,
} from './api';

vi.mock('@/lib/localMode', () => ({
  LOCAL_DATA: true,
  STORE_NAME: 'work/',
  localApi: vi.fn(),
}));

describe('src/lib/api.ts Core Rayfin UDFs and helpers (R-2, FR-7)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('helper utilities', () => {
    it('str handles null, undefined, empty string and non-empty values', () => {
      expect(str(null)).toBeNull();
      expect(str(undefined)).toBeNull();
      expect(str('')).toBeNull();
      expect(str('TCGA-G6-A8L6')).toBe('TCGA-G6-A8L6');
      expect(str(123)).toBe('123');
    });

    it('num parses numbers and handles invalid values', () => {
      expect(num(null)).toBeNull();
      expect(num(undefined)).toBeNull();
      expect(num('')).toBeNull();
      expect(num('invalid')).toBeNull();
      expect(num(42)).toBe(42);
      expect(num('84.0')).toBe(84.0);
    });

    it('parseJson parses JSON strings with fallback', () => {
      expect(parseJson('{"key":"value"}', {})).toEqual({ key: 'value' });
      expect(parseJson('invalid json', { fallback: true })).toEqual({ fallback: true });
      expect(parseJson(null, { fallback: true })).toEqual({ fallback: true });
    });

    it('fileUrl constructs SAS or plain URLs', () => {
      const accessWithoutSas = { baseUrl: 'https://storage.example.com', query: '', expiresOn: '', scope: 'slides', silo: 'imaging' as const };
      expect(fileUrl(accessWithoutSas, 'slide.dzi')).toBe('https://storage.example.com/slide.dzi');

      const accessWithSas = { baseUrl: 'https://storage.example.com', query: 'sig=123', expiresOn: '', scope: 'slides', silo: 'imaging' as const };
      expect(fileUrl(accessWithSas, 'slide.dzi')).toBe('https://storage.example.com/slide.dzi?sig=123');
    });
  });

  describe('local API fetchers', () => {
    it('fetchAlertStopwatch calls localApi in local data mode', async () => {
      const mockResult = {
        patientId: 'TCGA-G6-A8L6',
        patientName: 'Marcus Vance',
        deviceId: 'MASIMO-RADIUS7-0101',
        alertTier: 'CRITICAL',
        spo2: 84.0,
        pulseRate: 115,
        totalElapsedSeconds: 18.4,
        totalElapsedFormatted: '18.4s',
        beats: [],
        measuredAt: '2026-11-07T12:00:18.400Z',
        source: 'local',
      };
      const spy = vi.spyOn(localModeModule, 'localApi').mockResolvedValue(mockResult);

      const res = await fetchAlertStopwatch('TCGA-G6-A8L6');
      expect(spy).toHaveBeenCalledWith('getAlertStopwatch?patientId=TCGA-G6-A8L6');
      expect(res.totalElapsedSeconds).toBe(18.4);
      expect(res.patientId).toBe('TCGA-G6-A8L6');
    });

    it('fetchCohort calls localApi getCohort', async () => {
      const mockCohort = {
        patients: [],
        provenance: { workspace: '', endpoint: '', database: '', queries: [], totalMs: 0, showcaseSql: '', servedAt: '' },
      };
      const spy = vi.spyOn(localModeModule, 'localApi').mockResolvedValue(mockCohort);

      const res = await fetchCohort();
      expect(spy).toHaveBeenCalledWith('getCohort');
      expect(res).toEqual(mockCohort);
    });

    it('fetchPatient calls localApi getPatient', async () => {
      const mockPatient = {
        patient: {},
        header: {},
        diagnoses: [],
        treatments: [],
        followUps: [],
        biomarkers: [],
        observations: [],
        encounters: [],
        conditions: [],
        medications: [],
        immunizations: [],
        imagingStudies: [],
        labResults: [],
        notes: [],
        timeline: [],
        access: { slide: { baseUrl: '', query: '' } },
        provenance: { workspace: '', database: '', queries: [], totalMs: 0, servedAt: '' },
      };
      const spy = vi.spyOn(localModeModule, 'localApi').mockResolvedValue(mockPatient);

      const res = await fetchPatient('TCGA-G6-A8L6');
      expect(spy).toHaveBeenCalledWith('getPatient?patientId=TCGA-G6-A8L6');
      expect(res).toEqual(mockPatient);
    });

    it('fetchDataMap calls localApi getDataMap', async () => {
      const mockDataMap = {
        workspace: { id: '', name: '', portalUrl: '' },
        patient360: { id: '', name: '', portalUrl: '', sqlEndpoint: '', shortcuts: [] },
        zeroCopy: { copiesMade: 0 as const, shortcutCount: 0, sourceSilos: [], physicalBytesInPatient360: 0 as const },
        silos: [],
        provenance: { workspace: '', database: '', queries: [], totalMs: 0, servedAt: '' },
      };
      const spy = vi.spyOn(localModeModule, 'localApi').mockResolvedValue(mockDataMap);

      const res = await fetchDataMap();
      expect(spy).toHaveBeenCalledWith('getDataMap');
      expect(res).toEqual(mockDataMap);
    });

    it('fetchWardFlowCohort calls localApi getWardFlowCohort', async () => {
      const mockWardFlow = {
        workspaceId: 'local',
        workspaceName: '',
        sqlEndpoint: '',
        database: '',
        goldRefreshedAt: null,
        servedAt: '',
        totalMs: 0,
        subjects: [],
        enrollableCount: 0,
      };
      const spy = vi.spyOn(localModeModule, 'localApi').mockResolvedValue(mockWardFlow);

      const res = await fetchWardFlowCohort();
      expect(spy).toHaveBeenCalledWith('getWardFlowCohort');
      expect(res).toEqual(mockWardFlow);
    });
  });
});
