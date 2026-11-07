// @vitest-environment jsdom
import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import OpenSeadragon from 'openseadragon';
import { Niivue } from '@niivue/niivue';

import { MultimodalHero, buildSafeAssetUrl } from '../MultimodalHero';
import type { FileAccess, PatientBundle } from '@/lib/api';
import type * as ApiModule from '@/lib/api';

const osdDestroyMock = vi.fn();
const nvDestroyMock = vi.fn();

vi.mock('@niivue/niivue', () => {
  return {
    Niivue: vi.fn().mockImplementation(() => ({
      attachToCanvas: vi.fn().mockResolvedValue(undefined),
      loadVolumes: vi.fn().mockResolvedValue(undefined),
      setSliceType: vi.fn(),
      destroy: nvDestroyMock,
    })),
    DRAG_MODE: { pan: 1 },
    MULTIPLANAR_TYPE: { GRID: 1 },
    SHOW_RENDER: { ALWAYS: 1 },
    SLICE_TYPE: { RENDER: 1, MULTIPLANAR: 2, AXIAL: 3 },
  };
});

interface OSDWithTileSource {
  TileSource: unknown;
}

vi.mock('openseadragon', () => {
  const OSDMock = vi.fn().mockImplementation(() => ({
    destroy: osdDestroyMock,
    addHandler: vi.fn(),
    viewport: {
      goHome: vi.fn(),
      zoomTo: vi.fn(),
    },
    world: {
      getItemAt: vi.fn().mockReturnValue({
        imageToViewportZoom: vi.fn().mockReturnValue(1),
      }),
    },
  }));
  const target = OSDMock as unknown as OSDWithTileSource;
  target.TileSource = vi.fn().mockImplementation(() => ({}));
  return {
    default: OSDMock,
  };
});

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof ApiModule>('@/lib/api');
  return {
    ...actual,
    fetchDataMap: vi.fn().mockResolvedValue({
      silos: [
        {
          silo: 'genomics',
          items: [
            { kind: 'table', name: 'somatic_mutation', bytes: 5287 },
            { kind: 'table', name: 'molecular_profile', bytes: 8952 },
            { kind: 'table', name: 'cohort_reference', bytes: 33961 },
          ],
        },
      ],
    }),
  };
});

const baseBundle: PatientBundle = {
  patient: {
    patient_id: 'TCGA-G6-A8L6',
    display_name: 'Marcus Vance',
    cancer_type: 'Kidney Renal Clear Cell Carcinoma',
    stage: 'Stage III',
    t_stage: 'T3a',
    n_stage: 'N0',
    m_stage: 'M0',
    tissue_of_origin: 'Kidney, NOS',
    sex: 'male',
    age_at_diagnosis: 58,
    race: 'white',
    country: 'United States',
    vital_status: 'Alive',
    days_to_last_contact: 1240,
    days_to_death: null,
    diagnosis_date: '2011-04-12',
  },
  header: {},
  profile: {
    subtype: 'KIRC_Clear_Cell',
    tmb: 1.8,
    mutation_count: 47,
  },
  drivers: [
    { gene: 'VHL', protein_change: 'p.R82Afs*50', mutation_type: 'Frame_Shift_Del', vaf: 0.44 },
    { gene: 'PBRM1', protein_change: 'p.Y409Tfs*29', mutation_type: 'Frame_Shift_Del', vaf: 0.39 },
    { gene: 'SETD2', protein_change: 'p.P2380Tfs*31', mutation_type: 'Frame_Shift_Ins', vaf: 0.36 },
  ],
  radiologySeries: [
    {
      series_uid: '1.3.6.1.4.1.14519.5.2.1.2825765788.1',
      modality: 'CT',
      volume_path: 'radiology/tcga-g6-a8l6/volume.nii.gz',
      volume_bytes: 6200000,
      raw_bytes: 72000000,
      images: 72,
      slice_thickness_mm: 2.5,
    },
  ],
  radiologyStudies: [],
  slide: {
    slide_id: 'kidney-kirc',
    barcode: 'TCGA-G6-A8L6-01A-01-TS1',
    role: 'diagnostic',
    width: 68357,
    height: 52028,
    levels: 10,
    raw_bytes: 210450000,
    objective_power: 40,
  },
  slides: [],
  diagnoses: [],
  treatments: [],
  followUps: [],
  biomarkers: [],
  observations: [],
  encounters: [],
  conditions: [],
  medications: [],
  immunizations: [],
  allergies: [],
  procedures: [],
  careplans: [],
  report: { text: '', pdfPath: null, pdfBytes: null, gdcFileId: null, source: null },
  summary: null,
  mutationMap: { chromosomes: [], positions: [], types: [], typeNames: [] },
  mutationCounts: [],
  segments: [],
  copyNumber: [],
  expression: [],
  immuneCells: [],
  reference: [],
  access: {
    slide: { baseUrl: 'https://storage.azure.com/imaging/Files', query: 'st=2026-11-07&se=2026-11-08', expiresOn: '', scope: '', silo: 'imaging' },
    radiology: { baseUrl: 'https://storage.azure.com/imaging/Files', query: 'st=2026-11-07&se=2026-11-08', expiresOn: '', scope: '', silo: 'imaging' },
    report: { baseUrl: 'https://storage.azure.com/clinical/Files', query: '', expiresOn: '', scope: '', silo: 'clinical' },
  },
  provenance: {
    workspace: 'test-ws',
    endpoint: 'test-ep',
    database: 'test-db',
    queries: [],
    totalMs: 15,
    showcaseSql: '',
    servedAt: '2026-11-07T00:00:00Z',
  },
};

describe('MultimodalHero Security - asset URL generation and parameter validation', () => {
  const validAccess: FileAccess = {
    baseUrl: 'https://example.com/imaging/Files',
    query: 'sig=validtoken',
    expiresOn: '',
    scope: '',
    silo: 'imaging',
  };

  it('security: constructs valid file URLs with and without query parameters', () => {
    const urlWithQuery = buildSafeAssetUrl(validAccess, 'slides/s1/slide_files/0/0_0.jpg');
    expect(urlWithQuery).toBe('https://example.com/imaging/Files/slides/s1/slide_files/0/0_0.jpg?sig=validtoken');

    const urlWithoutQuery = buildSafeAssetUrl({ ...validAccess, query: '' }, 'radiology/series1/volume.nii.gz');
    expect(urlWithoutQuery).toBe('https://example.com/imaging/Files/radiology/series1/volume.nii.gz');
  });

  it('security: sanitizes relative paths and rejects path traversal sequences', () => {
    expect(() => buildSafeAssetUrl(validAccess, '../secret.key')).toThrow(/traversal/i);
    expect(() => buildSafeAssetUrl(validAccess, 'slides/../../etc/passwd')).toThrow(/traversal/i);
    expect(() => buildSafeAssetUrl(validAccess, '..\\windows\\system32')).toThrow(/traversal/i);
    expect(() => buildSafeAssetUrl(validAccess, 'sub/..\\something')).toThrow(/traversal/i);
  });

  it('security: rejects non-allowed schemes in asset paths', () => {
    expect(() => buildSafeAssetUrl(validAccess, 'javascript:alert(1)')).toThrow(/non-allowed scheme/i);
    expect(() => buildSafeAssetUrl(validAccess, 'data:text/html,<script>alert(1)</script>')).toThrow(/non-allowed scheme/i);
    expect(() => buildSafeAssetUrl(validAccess, 'file:///etc/passwd')).toThrow(/non-allowed scheme/i);
    expect(() => buildSafeAssetUrl(validAccess, 'https://malicious.org/exploit.nii.gz')).toThrow(/non-allowed scheme/i);
    expect(() => buildSafeAssetUrl(validAccess, 'http://malicious.org/exploit.nii.gz')).toThrow(/non-allowed scheme/i);
  });

  it('security: rejects missing or invalid access configurations', () => {
    expect(() => buildSafeAssetUrl(null, 'valid/path.jpg')).toThrow(/invalid file access/i);
    const emptyBaseAccess: FileAccess = { baseUrl: '', query: '', expiresOn: '', scope: '', silo: 'imaging' };
    expect(() => buildSafeAssetUrl(emptyBaseAccess, 'valid/path.jpg')).toThrow(/invalid file access/i);
    const ftpBaseAccess: FileAccess = { baseUrl: 'ftp://invalidscheme.com', query: '', expiresOn: '', scope: '', silo: 'imaging' };
    expect(() => buildSafeAssetUrl(ftpBaseAccess, 'valid/path.jpg')).toThrow(/non-allowed scheme/i);
  });
});

describe('MultimodalHero Lifecycle - memory cleanup and canvas unmount', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('unmount: destroys OpenSeadragon and Niivue instances on component unmount', async () => {
    let unmountFn: () => void = () => {};

    await act(async () => {
      const { unmount } = render(<MultimodalHero b={baseBundle} />);
      unmountFn = unmount;
    });

    // Verify viewers were initialized
    expect(Niivue).toHaveBeenCalled();
    expect(OpenSeadragon).toHaveBeenCalled();

    // Perform unmount
    act(() => {
      unmountFn();
    });

    // Verify both viewers were destroyed and cleaned up cleanly
    expect(nvDestroyMock).toHaveBeenCalled();
    expect(osdDestroyMock).toHaveBeenCalled();
  });
});

describe('MultimodalHero Rendering and Edge Cases', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders all three modality panes with Streamed from OneLake badges', async () => {
    await act(async () => {
      render(<MultimodalHero b={baseBundle} genomicsDeltaBytes={48200} />);
    });

    // Modality headers
    expect(screen.getByRole('heading', { name: 'Radiology' })).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Pathology' })).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Genomics' })).toBeDefined();

    // Streamed from OneLake badges
    const badges = screen.getAllByText(/Streamed from OneLake, never copied:/i);
    expect(badges.length).toBe(3);
    expect(screen.getAllByText(/6\.2 MB volume \(72\.0 MB raw DICOM\)/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/210\.\d MB slide/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/48\.2 KB Delta/i).length).toBeGreaterThanOrEqual(1);
    // Drivers listed
    expect(screen.getByText('VHL')).toBeDefined();
    expect(screen.getByText('PBRM1')).toBeDefined();
    expect(screen.getByText('SETD2')).toBeDefined();
    expect(screen.getByText('44%')).toBeDefined();
  });

  it('renders designed fallback card when local mode pixel files are absent', async () => {
    await act(async () => {
      render(<MultimodalHero b={baseBundle} />);
    });

    // Fallback message should be present
    const fallbackMessages = screen.getAllByText(/Local mode: pixel files not downloaded/i);
    expect(fallbackMessages.length).toBeGreaterThanOrEqual(2);

    // Metadata pills should be preserved
    expect(screen.getByText('1.3.6.1.4.1.14519.5.2.1.2825765788.1')).toBeDefined();
    expect(screen.getByText('kidney-kirc')).toBeDefined();
  });

  it('E-8: displays empty state when patient has no radiology series', async () => {
    const noRadBundle: PatientBundle = {
      ...baseBundle,
      radiologySeries: [],
    };

    await act(async () => {
      render(<MultimodalHero b={noRadBundle} />);
    });

    expect(screen.getByText('No radiology series available for this patient')).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Pathology' })).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Genomics' })).toBeDefined();
  });

  it('E-9: displays empty state when patient has zero driver mutations', async () => {
    const noDriversBundle: PatientBundle = {
      ...baseBundle,
      drivers: [],
    };

    await act(async () => {
      render(<MultimodalHero b={noDriversBundle} />);
    });

    expect(screen.getByText('No somatic driver mutations detected')).toBeDefined();
    expect(screen.getAllByText(/KIRC Clear Cell/i).length).toBeGreaterThanOrEqual(1);
  });

  it('displays empty state when patient has no pathology slide', async () => {
    const noSlideBundle: PatientBundle = {
      ...baseBundle,
      slide: null,
      slides: [],
    };

    await act(async () => {
      render(<MultimodalHero b={noSlideBundle} />);
    });

    expect(screen.getByText('No whole-slide imaging available for this patient')).toBeDefined();
  });
});
