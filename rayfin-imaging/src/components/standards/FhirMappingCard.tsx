import { useState } from 'react';
import type { StandardsMapping } from '@/lib/api';

interface FhirMappingCardProps {
  mapping: StandardsMapping;
}

export function FhirMappingCard({ mapping }: FhirMappingCardProps) {
  const [copied, setCopied] = useState(false);
  const [patientCollapsed, setPatientCollapsed] = useState(false);
  const [conditionCollapsed, setConditionCollapsed] = useState(false);
  const [activeHighlight, setActiveHighlight] = useState<string | null>(null);

  const { patient, diagnoses, fhir } = mapping;

  const handleCopy = async () => {
    const fullBundle = {
      resourceType: 'Bundle',
      type: 'collection',
      entry: [
        { resource: fhir.patientResource },
        { resource: fhir.conditionResource },
      ],
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(fullBundle, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  const patientJsonStr = JSON.stringify(fhir.patientResource, null, 2);
  const conditionJsonStr = JSON.stringify(fhir.conditionResource, null, 2);

  return (
    <div className="flex flex-col gap-6">
      {/* Mapping Badges Bar */}
      <div className="hair border p-4 bg-[var(--surface-subtle)] rounded">
        <div className="text-[12px] font-semibold uppercase tracking-wider text-[var(--ink-muted)] mb-2.5">
          Conformed Field-Level Lineage (FHIR R4 → Delta Lake)
        </div>
        <div className="flex flex-wrap gap-2">
          {fhir.mappings.map((m) => {
            const isHovered = activeHighlight === m.fhirPath;
            return (
              <button
                key={m.fhirPath}
                type="button"
                onMouseEnter={() => setActiveHighlight(m.fhirPath)}
                onMouseLeave={() => setActiveHighlight(null)}
                onClick={() => setActiveHighlight(isHovered ? null : m.fhirPath)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[11.5px] mono border transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
                  isHovered
                    ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                    : 'bg-[var(--surface)] text-[var(--ink)] border-[var(--hair)] hover:border-[var(--ink-muted)]'
                }`}
                title={m.description}
                aria-pressed={isHovered}
              >
                <span className="font-semibold">{m.fhirPath}</span>
                <span className="opacity-60">→</span>
                <span>{m.deltaColumn}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Split Comparison Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* Left Pane: FHIR R4 JSON */}
        <section
          aria-label="FHIR R4 Standard Input JSON"
          className="hair border rounded overflow-hidden flex flex-col bg-[var(--surface)] min-w-0"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b bg-[var(--surface-subtle)] shrink-0">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" aria-hidden />
              <h3 className="text-[13px] font-semibold text-[var(--ink)]">
                FHIR R4 JSON Resource Bundle
              </h3>
            </div>
            <button
              type="button"
              onClick={handleCopy}
              className="px-2.5 py-1 rounded text-[12px] mono border border-[var(--hair)] hover:border-[var(--ink-muted)] bg-[var(--surface)] text-[var(--ink)] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] cursor-pointer"
            >
              {copied ? '✓ Copied clean JSON' : 'Copy JSON'}
            </button>
          </div>

          <div className="p-4 flex flex-col gap-4 overflow-x-auto min-w-0">
            {/* Patient Resource Tree */}
            <div className="border border-[var(--hair)] rounded overflow-hidden">
              <div
                className="flex items-center justify-between px-3 py-2 bg-[var(--surface-subtle)] cursor-pointer select-none"
                onClick={() => setPatientCollapsed(!patientCollapsed)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setPatientCollapsed(!patientCollapsed);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-expanded={!patientCollapsed}
                aria-label="Toggle FHIR Patient Resource"
              >
                <span className="text-[12px] font-medium mono text-[var(--ink)]">
                  Resource: Patient (ID: {String(patient.patient_id)})
                </span>
                <span className="text-[11px] mono text-[var(--ink-muted)]">
                  {patientCollapsed ? '+ Expand' : '− Collapse'}
                </span>
              </div>
              {!patientCollapsed && (
                <pre
                  className={`p-3 text-[12px] mono leading-relaxed overflow-x-auto bg-[#1a1b26] text-[#c0caf5] transition-colors ${
                    activeHighlight?.startsWith('Patient.') ? 'ring-2 ring-emerald-400' : ''
                  }`}
                >
                  <code>{patientJsonStr}</code>
                </pre>
              )}
            </div>

            {/* Condition Resource Tree */}
            <div className="border border-[var(--hair)] rounded overflow-hidden">
              <div
                className="flex items-center justify-between px-3 py-2 bg-[var(--surface-subtle)] cursor-pointer select-none"
                onClick={() => setConditionCollapsed(!conditionCollapsed)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setConditionCollapsed(!conditionCollapsed);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-expanded={!conditionCollapsed}
                aria-label="Toggle FHIR Condition Resource"
              >
                <span className="text-[12px] font-medium mono text-[var(--ink)]">
                  Resource: Condition (Primary Oncological Diagnosis)
                </span>
                <span className="text-[11px] mono text-[var(--ink-muted)]">
                  {conditionCollapsed ? '+ Expand' : '− Collapse'}
                </span>
              </div>
              {!conditionCollapsed && (
                <pre
                  className={`p-3 text-[12px] mono leading-relaxed overflow-x-auto bg-[#1a1b26] text-[#c0caf5] transition-colors ${
                    activeHighlight?.startsWith('Condition.') ? 'ring-2 ring-emerald-400' : ''
                  }`}
                >
                  <code>{conditionJsonStr}</code>
                </pre>
              )}
            </div>
          </div>
        </section>

        {/* Right Pane: Conformed Delta Tables */}
        <section
          aria-label="Conformed Delta Lake Table Lineage"
          className="hair border rounded overflow-hidden flex flex-col bg-[var(--surface)] min-w-0"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b bg-[var(--surface-subtle)] shrink-0">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500" aria-hidden />
              <h3 className="text-[13px] font-semibold text-[var(--ink)]">
                Conformed Delta Lake Tables (OneLake)
              </h3>
            </div>
            <span className="text-[11.5px] mono text-[var(--ink-muted)]">
              clinical_lakehouse.dbo
            </span>
          </div>

          <div className="p-4 flex flex-col gap-6 overflow-x-auto min-w-0">
            {/* clinical_lakehouse.dbo.patient */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-[12.5px] font-medium mono text-[var(--ink)]">
                  clinical_lakehouse.dbo.patient
                </h4>
                <span className="text-[11px] mono text-[var(--ink-muted)]">1 record</span>
              </div>
              <div className="border border-[var(--hair)] rounded overflow-x-auto">
                <table className="w-full text-left text-[12px] mono divide-y divide-[var(--hair)]">
                  <thead className="bg-[var(--surface-subtle)] text-[var(--ink-muted)]">
                    <tr>
                      <th className="px-3 py-2 font-medium">Column</th>
                      <th className="px-3 py-2 font-medium">Mapped Value</th>
                      <th className="px-3 py-2 font-medium">FHIR Source Path</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--hair)] bg-[var(--surface)]">
                    <tr
                      className={
                        activeHighlight === 'Patient.identifier[0].value'
                          ? 'bg-emerald-50 dark:bg-emerald-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">patient_id</td>
                      <td className="px-3 py-2">{String(patient.patient_id ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">Patient.identifier[0].value</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === 'Patient.name[0].text'
                          ? 'bg-emerald-50 dark:bg-emerald-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">display_name</td>
                      <td className="px-3 py-2 text-emerald-600 dark:text-emerald-400 font-medium">
                        {String(patient.display_name ?? '')}
                      </td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">Patient.name[0].text</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === 'Patient.gender'
                          ? 'bg-emerald-50 dark:bg-emerald-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">sex</td>
                      <td className="px-3 py-2">{String(patient.sex ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">Patient.gender</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === 'Condition.recordedDate'
                          ? 'bg-emerald-50 dark:bg-emerald-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">diagnosis_date</td>
                      <td className="px-3 py-2">{String(patient.diagnosis_date ?? patient.year_of_diagnosis ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">Condition.recordedDate</td>
                    </tr>
                    <tr>
                      <td className="px-3 py-2 font-semibold">organ</td>
                      <td className="px-3 py-2">{String(patient.organ ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">Condition.bodySite</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* clinical_lakehouse.dbo.diagnoses */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-[12.5px] font-medium mono text-[var(--ink)]">
                  clinical_lakehouse.dbo.diagnoses
                </h4>
                <span className="text-[11px] mono text-[var(--ink-muted)]">
                  {diagnoses.length} {diagnoses.length === 1 ? 'record' : 'records'}
                </span>
              </div>
              <div className="border border-[var(--hair)] rounded overflow-x-auto">
                <table className="w-full text-left text-[12px] mono divide-y divide-[var(--hair)]">
                  <thead className="bg-[var(--surface-subtle)] text-[var(--ink-muted)]">
                    <tr>
                      <th className="px-3 py-2 font-medium">primary_diagnosis</th>
                      <th className="px-3 py-2 font-medium">icd10</th>
                      <th className="px-3 py-2 font-medium">classification</th>
                      <th className="px-3 py-2 font-medium">stage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--hair)] bg-[var(--surface)]">
                    {diagnoses.length > 0 ? (
                      diagnoses.map((d, idx) => (
                        <tr
                          key={idx}
                          className={
                            activeHighlight?.startsWith('Condition.code')
                              ? 'bg-emerald-50 dark:bg-emerald-950/40'
                              : ''
                          }
                        >
                          <td className="px-3 py-2 font-semibold text-blue-600 dark:text-blue-400">
                            {String(d.primary_diagnosis ?? patient.primary_diagnosis ?? patient.cancer_type ?? '')}
                          </td>
                          <td className="px-3 py-2">{String(d.icd10 ?? patient.icd10 ?? 'C64.9')}</td>
                          <td className="px-3 py-2">{String(d.classification ?? 'primary')}</td>
                          <td className="px-3 py-2">{String(d.stage ?? patient.stage ?? '')}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="px-3 py-2 font-semibold text-blue-600 dark:text-blue-400">
                          {String(patient.primary_diagnosis ?? patient.cancer_type ?? 'Clear cell renal cell carcinoma')}
                        </td>
                        <td className="px-3 py-2">{String(patient.icd10 ?? 'C64.9')}</td>
                        <td className="px-3 py-2">primary</td>
                        <td className="px-3 py-2">{String(patient.stage ?? '')}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
