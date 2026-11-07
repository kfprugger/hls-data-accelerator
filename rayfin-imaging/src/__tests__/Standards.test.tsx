// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { FhirMappingCard } from '../components/standards/FhirMappingCard';
import { DicomMappingCard } from '../components/standards/DicomMappingCard';
import { Standards } from '../pages/Standards';
import * as apiModule from '@/lib/api';
import type { StandardsMapping } from '@/lib/api';

vi.mock('@/hooks/useCohort', () => ({
  useCohort: () => ({
    cohort: {
      patients: [
        { patient_id: 'TCGA-G6-A8L6', display_name: 'Marcus Vance' },
        { patient_id: 'TCGA-A1-A0SK', display_name: 'Genevieve Holt' },
      ],
    },
    loading: false,
    error: null,
  }),
}));

const mockMapping: StandardsMapping = {
  patientId: 'TCGA-G6-A8L6',
  patient: {
    patient_id: 'TCGA-G6-A8L6',
    display_name: 'Marcus Vance',
    sex: 'Male',
    cancer_type: 'Clear cell renal cell carcinoma',
    organ: 'Kidney',
    diagnosis_date: '2011-04-07',
    icd10: 'C64.9',
  },
  diagnoses: [
    {
      patient_id: 'TCGA-G6-A8L6',
      seq: 1,
      classification: 'primary',
      primary_diagnosis: 'Clear cell renal cell carcinoma',
      icd10: 'C64.9',
      stage: 'Stage I',
    },
  ],
  radiologyStudies: [
    {
      patient_id: 'TCGA-G6-A8L6',
      study_uid: '1.3.6.1.4.1.14519.5.2.1.4872083899',
      date: '2011-03-31',
      modalities: 'CT',
      body_part: 'Kidney',
    },
  ],
  radiologySeries: [
    {
      patient_id: 'TCGA-G6-A8L6',
      study_uid: '1.3.6.1.4.1.14519.5.2.1.4872083899',
      series_uid: '1.3.6.1.4.1.14519.5.2.1.4872083899.1',
      modality: 'CT',
      description: 'OMNIPAQUE 300',
      manufacturer: 'Siemens',
      model: 'Somatom Definition',
      slice_thickness_mm: 1.5,
      kvp: 120,
      contrast: 'Omnipaque 300',
      body_part: 'Kidney',
      images: 140,
      dims: '[180, 180, 166]',
      spacing_mm: '[1.5, 1.5, 1.5]',
      volume_path: 'volumes/totalseg-ct-angio/ct.nii.gz',
    },
  ],
  fhir: {
    patientResource: {
      resourceType: 'Patient',
      id: 'TCGA-G6-A8L6',
      name: [{ use: 'official', text: 'Marcus Vance', family: 'Vance', given: ['Marcus'] }],
      gender: 'male',
      birthDate: '1956-04-12',
    },
    conditionResource: {
      resourceType: 'Condition',
      id: 'cond-tcga-g6-a8l6-primary',
      code: {
        coding: [{ system: 'http://hl7.org/fhir/sid/icd-10-cm', code: 'C64.9', display: 'Clear cell renal cell carcinoma' }],
        text: 'Clear cell renal cell carcinoma',
      },
      subject: { reference: 'Patient/TCGA-G6-A8L6', display: 'Marcus Vance' },
      recordedDate: '2011-04-07',
    },
    mappings: [
      { fhirPath: 'Patient.gender', deltaTable: 'clinical_lakehouse.dbo.patient', deltaColumn: 'sex', description: 'Gender mapping' },
      { fhirPath: 'Patient.name[0].text', deltaTable: 'clinical_lakehouse.dbo.patient', deltaColumn: 'display_name', description: 'Name mapping' },
      { fhirPath: 'Condition.code.coding[0].display', deltaTable: 'clinical_lakehouse.dbo.diagnoses', deltaColumn: 'primary_diagnosis', description: 'Primary dx mapping' },
      { fhirPath: 'Condition.code.coding[0].code', deltaTable: 'clinical_lakehouse.dbo.diagnoses', deltaColumn: 'icd10', description: 'ICD10 mapping' },
    ],
  },
  dicom: {
    tags: [
      { tag: '(0010,0020)', name: 'PatientID', value: 'TCGA-G6-A8L6', mappedTable: 'radiology_study', mappedColumn: 'patient_id' },
      { tag: '(0020,000D)', name: 'StudyInstanceUID', value: '1.3.6.1.4.1.14519.5.2.1.4872083899', mappedTable: 'radiology_study', mappedColumn: 'study_uid' },
      { tag: '(0020,000E)', name: 'SeriesInstanceUID', value: '1.3.6.1.4.1.14519.5.2.1.4872083899.1', mappedTable: 'radiology_series', mappedColumn: 'series_uid' },
      { tag: '(0008,0060)', name: 'Modality', value: 'CT', mappedTable: 'radiology_series', mappedColumn: 'modality' },
      { tag: '(0018,0050)', name: 'SliceThickness', value: 1.5, mappedTable: 'radiology_series', mappedColumn: 'slice_thickness_mm' },
      { tag: '(0018,0060)', name: 'KVP', value: 120, mappedTable: 'radiology_series', mappedColumn: 'kvp' },
    ],
    mappings: [
      { dicomTag: '(0020,000D)', tagName: 'StudyInstanceUID', deltaTable: 'imaging_lakehouse.dbo.radiology_study', deltaColumn: 'study_uid' },
      { dicomTag: '(0020,000E)', tagName: 'SeriesInstanceUID', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'series_uid' },
      { dicomTag: '(0008,0060)', tagName: 'Modality', deltaTable: 'imaging_lakehouse.dbo.radiology_series', deltaColumn: 'modality' },
    ],
  },
};

describe('FhirMappingCard component', () => {
  it('renders FHIR R4 JSON and conformed Delta table records', () => {
    render(<FhirMappingCard mapping={mockMapping} />);

    // Verify FHIR R4 JSON content
    expect(screen.getByText(/resourceType": "Patient"/)).toBeDefined();
    expect(screen.getAllByText(/Marcus Vance/).length).toBeGreaterThan(0);
    expect(screen.getByText(/resourceType": "Condition"/)).toBeDefined();

    // Verify conformed Delta table values
    expect(screen.getAllByText('Marcus Vance').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Clear cell renal cell carcinoma').length).toBeGreaterThan(0);

    // Verify mapping badges
    expect(screen.getAllByText('Patient.gender').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Condition.code.coding[0].display').length).toBeGreaterThan(0);
  });
});

describe('DicomMappingCard component', () => {
  it('renders key DICOM tags and imaging Delta table rows', () => {
    render(<DicomMappingCard mapping={mockMapping} />);

    expect(screen.getByText('(0010,0020)')).toBeDefined();
    expect(screen.getByText('(0020,000D)')).toBeDefined();
    expect(screen.getAllByText(/Modality/).length).toBeGreaterThan(0);

    const expectedStudyUid = String(mockMapping.radiologyStudies[0].study_uid);
    const expectedSeriesUid = String(mockMapping.radiologySeries[0].series_uid);
    expect(screen.getAllByText(expectedStudyUid).length).toBeGreaterThan(0);
    expect(screen.getAllByText(expectedSeriesUid).length).toBeGreaterThan(0);
  });

  it('renders empty state when no radiology study exists', () => {
    const emptyImagingMapping: StandardsMapping = {
      ...mockMapping,
      radiologyStudies: [],
      radiologySeries: [],
      dicom: { tags: [], mappings: [] },
    };

    render(<DicomMappingCard mapping={emptyImagingMapping} />);
    expect(
      screen.getByText('No imaging study available for this subject in imaging_lakehouse'),
    ).toBeDefined();
  });
});

describe('Standards Page', () => {
  beforeEach(() => {
    vi.spyOn(apiModule, 'fetchStandardsMapping').mockResolvedValue(mockMapping);
  });

  it('loads and displays patient selector and toggles tabs', async () => {
    render(
      <MemoryRouter initialEntries={['/standards']}>
        <Standards />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Standards Interoperability Lineage/)).toBeDefined();
    });

    const select = screen.getByLabelText(/Cohort Patient/i) as HTMLSelectElement;
    expect(select.value).toBe('TCGA-G6-A8L6');

    // Click DICOM tab
    const dicomTab = screen.getByRole('tab', { name: /DICOM Imaging Standards/i });
    fireEvent.click(dicomTab);

    expect(screen.getByText(/DICOM Tag Dataset/i)).toBeDefined();
  });

  it('renders fallback banner when patient is not found', async () => {
    vi.spyOn(apiModule, 'fetchStandardsMapping').mockRejectedValue(
      new Error('Patient not found in standards catalog'),
    );

    render(
      <MemoryRouter initialEntries={['/standards?patientId=TCGA-ZZ-9999']}>
        <Standards />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Patient not found in standards catalog')).toBeDefined();
    });

    const resetBtn = screen.getByRole('button', { name: /Reset to Marcus Vance/i });
    expect(resetBtn).toBeDefined();
  });
});
