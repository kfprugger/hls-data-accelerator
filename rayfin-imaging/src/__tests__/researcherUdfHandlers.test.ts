// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DataLakeServiceClient } from '../../rayfin/functions/node_modules/@azure/storage-file-datalake/dist/esm/index.js';
import {
  getCohortHandler,
  getPatientHandler,
  getWardFlowCohortHandler,
  type PoolSource,
} from '../../rayfin/functions/src/function_app';

/** Unsigned JWT carrying the claims the function app reads (signature is not checked server-side). */
function token(claims: Record<string, string>): string {
  const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString('base64url');
  return `${b64({ alg: 'none' })}.${b64(claims)}.sig`;
}

const RESEARCHER = token({ oid: 'researcher-oid', upn: 'researcher-demo@contoso.example' });
const NURSE = token({ oid: 'nurse-oid', upn: 'nurse@contoso.example' });

const IDENTIFIED = {
  patient_id: 'TCGA-G6-A8L6',
  display_name: 'Marcus Vance',
  birth_date: '1956-04-12',
  diagnosis_date: '2011-06-02',
  last_contact_date: '2014-09-30',
  death_date: null,
};
const DEIDENTIFIED = {
  patient_id: 'TCGA-G6-A8L6',
  display_name: 'TCGA-G6-A8L6',
  birth_date: '1956',
  diagnosis_date: '2011-01-01',
  last_contact_date: '2014-09-30',
  death_date: null,
};

/** Routes each SQL text to canned rows; records which statements ran. */
function fakePool(seen: string[]): PoolSource {
  const rowsFor = (text: string): Record<string, unknown>[] => {
    if (/FROM dbo\.patient_deidentified p\b/.test(text) || /FROM dbo\.patient p\b/.test(text)) {
      const p = text.includes('patient_deidentified') ? DEIDENTIFIED : IDENTIFIED;
      return [{ ...p, cancer_type: 'Kidney', thumbnail_path: null, radiology_series: 0 }];
    }
    if (text.includes('FROM dbo.patient_deidentified ')) return [DEIDENTIFIED];
    if (text.includes('FROM dbo.patient ')) return [IDENTIFIED];
    if (text.includes('FROM dbo.encounter ')) return [{ encounter_id: 'e1', start: '2012-03-04T10:00:00', stop: '2012-03-05' }];
    if (text.includes('FROM dbo.observation ')) return [{ date: '2012-03-04', name: 'Hemoglobin', value: 11.2 }];
    if (text.includes('FROM dbo.medication ')) return [{ encounter_id: 'e1', start: '2012-03-04', stop: '2012-09-01' }];
    if (text.includes('cardiology_subject') || text.includes('FullName')) {
      return [{ subject_id: '0efc0058-f344-5439-a7cc-30425ed7ba71', initials: 'MV', FullName: 'Marcus123 Vance456' }];
    }
    if (text.includes('COUNT(*) AS cnt')) return [{ cnt: 1 }];
    return [];
  };
  const pool = {
    connected: true,
    request() {
      const req = {
        input: () => req,
        query: async (text: string) => {
          seen.push(text);
          return { recordset: rowsFor(text) };
        },
      };
      return req;
    },
  };
  return async () => pool as never;
}

function ctx(sqlToken: string) {
  return { Tokens: { Sql: sqlToken, Storage: sqlToken } } as never;
}

describe('UDF handlers mask PHI for researchers', () => {
  beforeEach(() => {
    // No network: SAS signing fails fast and the handler returns unsigned access.
    vi.spyOn(DataLakeServiceClient.prototype, 'getUserDelegationKey').mockRejectedValue(new Error('offline'));
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getCohort serves de-identified names to a researcher token and reports the tier', async () => {
    const seen: string[] = [];
    const res = await getCohortHandler(ctx(RESEARCHER), 'nurse', fakePool(seen));
    expect(JSON.stringify(res.patients)).not.toContain('Marcus');
    expect(res.isDeidentified).toBe(true);
    expect(res.persona).toBe('researcher');
    expect(seen.some((s) => s.includes('patient_deidentified'))).toBe(true);
  });

  it('getCohort keeps identified data for a nurse token and lets the client downgrade only', async () => {
    const nurse = await getCohortHandler(ctx(NURSE), 'nurse', fakePool([]));
    expect(nurse.patients[0].display_name).toBe('Marcus Vance');
    expect(nurse.isDeidentified).toBe(false);
    const downgraded = await getCohortHandler(ctx(NURSE), 'researcher', fakePool([]));
    expect(JSON.stringify(downgraded.patients)).not.toContain('Marcus');
    expect(downgraded.persona).toBe('researcher');
  });

  it('getPatient reduces names and clinical event dates to year for a researcher', async () => {
    const res = await getPatientHandler('TCGA-G6-A8L6', ctx(RESEARCHER), 'nurse', fakePool([]));
    const json = JSON.stringify(res);
    expect(json).not.toContain('Marcus');
    expect(res.isDeidentified).toBe(true);
    expect(res.patient.display_name).toBe('TCGA-G6-A8L6');
    expect(res.patient.last_contact_date).toBe('2014');
    expect(res.patient.diagnosis_date).toBe('2011');
    expect(res.encounters[0].start).toBe('2012');
    expect(res.encounters[0].stop).toBe('2012');
    expect(res.observations[0].date).toBe('2012');
    expect(res.medications[0].start).toBe('2012');
    expect(res.medications[0].stop).toBe('2012');
  });

  it('getPatient never upgrades a researcher token to identified data', async () => {
    const res = await getPatientHandler('TCGA-G6-A8L6', ctx(RESEARCHER), 'nurse', fakePool([]));
    expect(res.persona).toBe('researcher');
    expect(JSON.stringify(res)).not.toContain('Vance');
  });

  it('getPatient keeps full dates for a nurse token', async () => {
    const res = await getPatientHandler('TCGA-G6-A8L6', ctx(NURSE), 'nurse', fakePool([]));
    expect(res.patient.display_name).toBe('Marcus Vance');
    expect(res.encounters[0].start).toBe('2012-03-04T10:00:00');
    expect(res.medications[0].stop).toBe('2012-09-01');
  });

  it('getWardFlowCohort nulls fullName for a researcher token', async () => {
    const researcher = await getWardFlowCohortHandler(ctx(RESEARCHER), fakePool([]));
    expect(researcher.subjects[0].fullName).toBeNull();
    const nurse = await getWardFlowCohortHandler(ctx(NURSE), fakePool([]));
    expect(nurse.subjects[0].fullName).toBe('Marcus Vance');
  });
});
