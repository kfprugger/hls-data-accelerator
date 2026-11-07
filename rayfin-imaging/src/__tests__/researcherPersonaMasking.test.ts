import { describe, it, expect } from 'vitest';
import { resolve } from 'path';
import { createLocalApi } from '../../local/api';

describe('Researcher persona PHI server-side masking', () => {
  const workDir = resolve(__dirname, '../../work');
  const api = createLocalApi(workDir);

  it('getCohort in researcher mode does not contain Vance', async () => {
    const res = await api.getCohort('http://localhost', 'researcher');
    const json = JSON.stringify(res);
    expect(json).not.toContain('Vance');
    expect(json).not.toContain('Marcus');
    const marcusPatient = res.patients.find((p) => p.patient_id === 'TCGA-G6-A8L6');
    expect(marcusPatient).toBeDefined();
    expect(marcusPatient?.display_name).toBe('TCGA-G6-A8L6');
  });

  it('getPatient in researcher mode does not contain Vance', async () => {
    const res = await api.getPatient('TCGA-G6-A8L6', 'http://localhost', 'researcher');
    const json = JSON.stringify(res);
    expect(json).not.toContain('Vance');
    expect(json).not.toContain('Marcus');
    expect(res.isDeidentified).toBe(true);
    expect(res.persona).toBe('researcher');
    expect(res.patient.display_name).toBe('TCGA-G6-A8L6');
    expect(res.header.display_name).toBe('TCGA-G6-A8L6');
  });

  it('getAlertStopwatch in researcher mode does not contain Vance', async () => {
    const res = await api.getAlertStopwatch('TCGA-G6-A8L6', 'researcher');
    const json = JSON.stringify(res);
    expect(json).not.toContain('Vance');
    expect(json).not.toContain('Marcus');
    expect(res.patientId).toBe('TCGA-G6-A8L6');
    expect(res.patientName).toBe('TCGA-G6-A8L6');
  });

  it('getAlertStopwatch in nurse mode retains identified patient name', async () => {
    const res = await api.getAlertStopwatch('TCGA-G6-A8L6', 'nurse');
    expect(res.patientName).toBe('Marcus Vance');
  });

  it('getStandardsMapping in researcher mode does not contain Vance', async () => {
    const res = await api.getStandardsMapping('TCGA-G6-A8L6', 'researcher');
    const json = JSON.stringify(res);
    expect(json).not.toContain('Vance');
    expect(json).not.toContain('Marcus');
    expect(res.patient.display_name).toBe('TCGA-G6-A8L6');
  });

  it('getStandardsMapping in nurse mode retains identified patient name', async () => {
    const res = await api.getStandardsMapping('TCGA-G6-A8L6', 'nurse');
    expect(res.patient.display_name).toBe('Marcus Vance');
  });

  it('askDataAgent in researcher mode does not contain Vance', async () => {
    const res = await api.askDataAgent('Show Marcus Vance vital signs and cancer stage', 'researcher');
    const json = JSON.stringify(res);
    expect(json).not.toContain('Vance');
    expect(json).not.toContain('Marcus');
    expect(res.answer).not.toContain('Vance');
    expect(res.generatedQuery).not.toContain('Vance');
  });
});
