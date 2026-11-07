import { useEffect, useState, useTransition } from 'react';
import { useSearchParams } from 'react-router-dom';

import { DicomMappingCard } from '@/components/standards/DicomMappingCard';
import { FhirMappingCard } from '@/components/standards/FhirMappingCard';
import { useCohort } from '@/hooks/useCohort';
import { fetchStandardsMapping, type StandardsMapping } from '@/lib/api';

const DEFAULT_PATIENT_ID = 'TCGA-G6-A8L6';

export function Standards() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { cohort } = useCohort();
  const [, startTransition] = useTransition();

  const patientId = searchParams.get('patientId') || DEFAULT_PATIENT_ID;
  const activeTabParam = searchParams.get('tab') || 'fhir';

  const [activeTab, setActiveTab] = useState<'fhir' | 'dicom'>(
    activeTabParam === 'dicom' ? 'dicom' : 'fhir',
  );
  const [data, setData] = useState<StandardsMapping | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchStandardsMapping(patientId)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : String(err);
          setError(msg);
          setData(null);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [patientId]);

  const handlePatientChange = (newPatientId: string) => {
    startTransition(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set('patientId', newPatientId);
        return next;
      });
    });
  };

  const handleTabChange = (tab: 'fhir' | 'dicom') => {
    setActiveTab(tab);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('tab', tab);
      return next;
    });
  };

  const handleResetToDefault = () => {
    handlePatientChange(DEFAULT_PATIENT_ID);
  };

  // Patients list for dropdown
  const cohortPatients = cohort?.patients ?? [
    { patient_id: 'TCGA-G6-A8L6', display_name: 'Marcus Vance' },
  ];

  const selectedPatient = cohortPatients.find((p) => p.patient_id === patientId);
  const selectedLabel = selectedPatient
    ? `${selectedPatient.patient_id} (${selectedPatient.display_name})`
    : patientId;

  return (
    <main
      role="main"
      className="w-full max-w-7xl mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6 overflow-x-hidden"
    >
      {/* Page Header */}
      <header className="flex flex-col gap-2 border-b pb-4 border-[var(--hair)]">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-[var(--ink)]">
              Standards Interoperability Lineage
            </h1>
            <p className="text-[13px] text-[var(--ink-muted)] mt-1">
              Field-level transformation proof: FHIR R4 clinical resources &amp; DICOM radiology tags to conformed Microsoft Fabric Delta Lake tables.
            </p>
          </div>

          {/* Patient Selector */}
          <div className="flex items-center gap-3">
            <label
              htmlFor="standards-patient-select"
              className="text-[12.5px] font-medium text-[var(--ink)] whitespace-nowrap"
            >
              Cohort Patient:
            </label>
            <select
              id="standards-patient-select"
              value={patientId}
              onChange={(e) => handlePatientChange(e.target.value)}
              className="px-3 py-1.5 rounded text-[13px] mono border border-[var(--hair)] bg-[var(--surface)] text-[var(--ink)] hover:border-[var(--ink-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] cursor-pointer"
              aria-label="Select cohort patient"
            >
              {cohortPatients.map((p) => (
                <option key={p.patient_id} value={p.patient_id}>
                  {p.patient_id} ({p.display_name})
                </option>
              ))}
              {!selectedPatient && (
                <option value={patientId}>{selectedLabel}</option>
              )}
            </select>
          </div>
        </div>

        {/* View Switcher Tabs */}
        <div
          role="tablist"
          aria-label="Standards View Tabs"
          className="flex items-center gap-2 mt-4 border-b border-[var(--hair)]"
        >
          <button
            role="tab"
            id="tab-fhir"
            aria-selected={activeTab === 'fhir'}
            aria-controls="panel-fhir"
            tabIndex={0}
            onClick={() => handleTabChange('fhir')}
            className={`px-4 py-2 text-[13px] font-medium border-b-2 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
              activeTab === 'fhir'
                ? 'border-[var(--accent)] text-[var(--accent)] font-semibold'
                : 'border-transparent text-[var(--ink-muted)] hover:text-[var(--ink)]'
            }`}
          >
            FHIR R4 Clinical Standards
          </button>
          <button
            role="tab"
            id="tab-dicom"
            aria-selected={activeTab === 'dicom'}
            aria-controls="panel-dicom"
            tabIndex={0}
            onClick={() => handleTabChange('dicom')}
            className={`px-4 py-2 text-[13px] font-medium border-b-2 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
              activeTab === 'dicom'
                ? 'border-[var(--accent)] text-[var(--accent)] font-semibold'
                : 'border-transparent text-[var(--ink-muted)] hover:text-[var(--ink)]'
            }`}
          >
            DICOM Imaging Standards
          </button>
        </div>
      </header>

      {/* Error / Not Found Banner */}
      {error && (
        <section
          role="alert"
          className="hair border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 p-4 rounded flex flex-col sm:flex-row sm:items-center justify-between gap-4"
        >
          <div className="flex items-center gap-3">
            <span className="text-amber-600 dark:text-amber-400 text-lg font-bold" aria-hidden>
              ⚠️
            </span>
            <div>
              <div className="text-[13px] font-semibold text-amber-800 dark:text-amber-300">
                Patient not found in standards catalog
              </div>
              <p className="text-[12px] text-amber-700 dark:text-amber-400 mt-0.5">
                The identifier <span className="mono font-semibold">{patientId}</span> does not match any subject in the active cohort tables.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleResetToDefault}
            className="px-3 py-1.5 rounded text-[12.5px] font-medium bg-amber-600 hover:bg-amber-700 text-white transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 cursor-pointer shrink-0"
          >
            Reset to Marcus Vance
          </button>
        </section>
      )}

      {/* Loading State */}
      {loading && !data && !error && (
        <div className="py-12 flex flex-col items-center justify-center gap-2 text-[var(--ink-muted)]">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-[var(--accent)] border-t-transparent" />
          <p className="text-[13px] mono">Loading standards lineage mapping for {patientId}...</p>
        </div>
      )}

      {/* Main Content Panels */}
      {data && (
        <div className="flex flex-col gap-6">
          <div
            id="panel-fhir"
            role="tabpanel"
            aria-labelledby="tab-fhir"
            hidden={activeTab !== 'fhir'}
          >
            {activeTab === 'fhir' && <FhirMappingCard mapping={data} />}
          </div>

          <div
            id="panel-dicom"
            role="tabpanel"
            aria-labelledby="tab-dicom"
            hidden={activeTab !== 'dicom'}
          >
            {activeTab === 'dicom' && <DicomMappingCard mapping={data} />}
          </div>
        </div>
      )}
    </main>
  );
}
export default Standards;
