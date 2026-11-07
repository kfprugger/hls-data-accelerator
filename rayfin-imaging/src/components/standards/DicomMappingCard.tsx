import { useState } from 'react';
import type { StandardsMapping } from '@/lib/api';

interface DicomMappingCardProps {
  mapping: StandardsMapping;
}

export function DicomMappingCard({ mapping }: DicomMappingCardProps) {
  const [copied, setCopied] = useState(false);
  const [activeHighlight, setActiveHighlight] = useState<string | null>(null);

  const { radiologyStudies, radiologySeries, dicom } = mapping;

  const hasImaging = radiologyStudies.length > 0 || radiologySeries.length > 0;

  if (!hasImaging || dicom.tags.length === 0) {
    return (
      <div className="hair border p-8 rounded text-center bg-[var(--surface)]">
        <div className="text-amber-600 dark:text-amber-400 font-medium text-[14px] mb-2">
          No imaging study available for this subject in imaging_lakehouse
        </div>
        <p className="text-[12.5px] text-[var(--ink-muted)] max-w-md mx-auto">
          This cohort participant does not have associated radiological DICOM CT or MRI series registered in the imaging silo. Switch back to the FHIR R4 Clinical Standards tab to view clinical interoperability mappings.
        </p>
      </div>
    );
  }

  const handleCopyTags = async () => {
    const lines = dicom.tags.map((t) => `${t.tag} ${t.name}: ${t.value ?? 'NULL'}`);
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  const primaryStudy = radiologyStudies[0] ?? {};
  const primarySeries = radiologySeries[0] ?? {};

  return (
    <div className="flex flex-col gap-6">
      {/* Mapping Badges Bar */}
      <div className="hair border p-4 bg-[var(--surface-subtle)] rounded">
        <div className="text-[12px] font-semibold uppercase tracking-wider text-[var(--ink-muted)] mb-2.5">
          Conformed Field-Level Lineage (DICOM Standard Tags → Delta Lake)
        </div>
        <div className="flex flex-wrap gap-2">
          {dicom.mappings.map((m) => {
            const isHovered = activeHighlight === m.dicomTag;
            return (
              <button
                key={m.dicomTag}
                type="button"
                onMouseEnter={() => setActiveHighlight(m.dicomTag)}
                onMouseLeave={() => setActiveHighlight(null)}
                onClick={() => setActiveHighlight(isHovered ? null : m.dicomTag)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[11.5px] mono border transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] ${
                  isHovered
                    ? 'bg-[var(--accent)] text-white border-[var(--accent)]'
                    : 'bg-[var(--surface)] text-[var(--ink)] border-[var(--hair)] hover:border-[var(--ink-muted)]'
                }`}
                aria-pressed={isHovered}
              >
                <span className="font-semibold">{m.dicomTag} {m.tagName}</span>
                <span className="opacity-60">→</span>
                <span>{m.deltaColumn}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Split Comparison Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* Left Pane: DICOM Tag Dataset */}
        <section
          aria-label="Key DICOM Dataset Tags"
          className="hair border rounded overflow-hidden flex flex-col bg-[var(--surface)] min-w-0"
        >
          <div className="flex items-center justify-between px-4 py-3 border-b bg-[var(--surface-subtle)] shrink-0">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-purple-500" aria-hidden />
              <h3 className="text-[13px] font-semibold text-[var(--ink)]">
                DICOM Tag Dataset (Key Headers)
              </h3>
            </div>
            <button
              type="button"
              onClick={handleCopyTags}
              className="px-2.5 py-1 rounded text-[12px] mono border border-[var(--hair)] hover:border-[var(--ink-muted)] bg-[var(--surface)] text-[var(--ink)] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] cursor-pointer"
            >
              {copied ? '✓ Copied Tags' : 'Copy Tags'}
            </button>
          </div>

          <div className="p-4 overflow-x-auto min-w-0">
            <div className="border border-[var(--hair)] rounded overflow-x-auto bg-[#1a1b26] text-[#c0caf5]">
              <table className="w-full text-left text-[12px] mono divide-y divide-[#24283b]">
                <thead className="bg-[#1f2335] text-[#7aa2f7]">
                  <tr>
                    <th className="px-3 py-2 font-medium">Tag</th>
                    <th className="px-3 py-2 font-medium">Name</th>
                    <th className="px-3 py-2 font-medium">Raw Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#24283b]">
                  {dicom.tags.map((t) => {
                    const isRowHighlighted = activeHighlight === t.tag;
                    return (
                      <tr
                        key={t.tag}
                        className={`transition-colors ${
                          isRowHighlighted ? 'bg-purple-900/50 text-white font-semibold' : ''
                        }`}
                      >
                        <td className="px-3 py-2 text-[#bb9af7]">{t.tag}</td>
                        <td className="px-3 py-2 font-medium">{t.name}</td>
                        <td className="px-3 py-2 text-[#73daca] break-all">
                          {t.tag}: {t.name}: {t.value !== null ? String(t.value) : 'NULL'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Right Pane: Imaging Delta Tables */}
        <section
          aria-label="Imaging Delta Lake Tables Lineage"
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
              imaging_lakehouse.dbo
            </span>
          </div>

          <div className="p-4 flex flex-col gap-6 overflow-x-auto min-w-0">
            {/* imaging_lakehouse.dbo.radiology_study */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-[12.5px] font-medium mono text-[var(--ink)]">
                  imaging_lakehouse.dbo.radiology_study
                </h4>
                <span className="text-[11px] mono text-[var(--ink-muted)]">
                  {radiologyStudies.length} {radiologyStudies.length === 1 ? 'record' : 'records'}
                </span>
              </div>
              <div className="border border-[var(--hair)] rounded overflow-x-auto">
                <table className="w-full text-left text-[12px] mono divide-y divide-[var(--hair)]">
                  <thead className="bg-[var(--surface-subtle)] text-[var(--ink-muted)]">
                    <tr>
                      <th className="px-3 py-2 font-medium">Column</th>
                      <th className="px-3 py-2 font-medium">Mapped Value</th>
                      <th className="px-3 py-2 font-medium">DICOM Header Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--hair)] bg-[var(--surface)]">
                    <tr
                      className={
                        activeHighlight === '(0010,0020)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">patient_id</td>
                      <td className="px-3 py-2">{String(primaryStudy.patient_id ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0010,0020) PatientID</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === '(0020,000D)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">study_uid</td>
                      <td className="px-3 py-2 text-purple-600 dark:text-purple-400 font-medium break-all">
                        {String(primaryStudy.study_uid ?? '')}
                      </td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0020,000D) StudyInstanceUID</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === '(0008,0020)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">date</td>
                      <td className="px-3 py-2">{String(primaryStudy.date ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0008,0020) StudyDate</td>
                    </tr>
                    <tr>
                      <td className="px-3 py-2 font-semibold">modalities</td>
                      <td className="px-3 py-2">{String(primaryStudy.modalities ?? 'CT')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0008,0060) Modality</td>
                    </tr>
                    <tr>
                      <td className="px-3 py-2 font-semibold">body_part</td>
                      <td className="px-3 py-2">{String(primaryStudy.body_part ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0018,0015) BodyPartExamined</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* imaging_lakehouse.dbo.radiology_series */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-[12.5px] font-medium mono text-[var(--ink)]">
                  imaging_lakehouse.dbo.radiology_series
                </h4>
                <span className="text-[11px] mono text-[var(--ink-muted)]">
                  {radiologySeries.length} {radiologySeries.length === 1 ? 'record' : 'records'}
                </span>
              </div>
              <div className="border border-[var(--hair)] rounded overflow-x-auto">
                <table className="w-full text-left text-[12px] mono divide-y divide-[var(--hair)]">
                  <thead className="bg-[var(--surface-subtle)] text-[var(--ink-muted)]">
                    <tr>
                      <th className="px-3 py-2 font-medium">Column</th>
                      <th className="px-3 py-2 font-medium">Mapped Value</th>
                      <th className="px-3 py-2 font-medium">DICOM Header Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--hair)] bg-[var(--surface)]">
                    <tr
                      className={
                        activeHighlight === '(0020,000E)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">series_uid</td>
                      <td className="px-3 py-2 text-purple-600 dark:text-purple-400 font-medium break-all">
                        {String(primarySeries.series_uid ?? '')}
                      </td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0020,000E) SeriesInstanceUID</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === '(0008,0060)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">modality</td>
                      <td className="px-3 py-2">{String(primarySeries.modality ?? 'CT')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0008,0060) Modality</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === '(0018,0050)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">slice_thickness_mm</td>
                      <td className="px-3 py-2">{String(primarySeries.slice_thickness_mm ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0018,0050) SliceThickness</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === '(0018,0060)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">kvp</td>
                      <td className="px-3 py-2">{String(primarySeries.kvp ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0018,0060) KVP</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === '(0008,0070)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">manufacturer</td>
                      <td className="px-3 py-2">{String(primarySeries.manufacturer ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0008,0070) Manufacturer</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === '(0008,1090)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">model</td>
                      <td className="px-3 py-2">{String(primarySeries.model ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0008,1090) ManufacturerModelName</td>
                    </tr>
                    <tr
                      className={
                        activeHighlight === '(0018,0010)'
                          ? 'bg-purple-50 dark:bg-purple-950/40'
                          : ''
                      }
                    >
                      <td className="px-3 py-2 font-semibold">contrast</td>
                      <td className="px-3 py-2">{String(primarySeries.contrast ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">(0018,0010) ContrastBolusAgent</td>
                    </tr>
                    <tr>
                      <td className="px-3 py-2 font-semibold">images</td>
                      <td className="px-3 py-2">{String(primarySeries.images ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">InstanceCount</td>
                    </tr>
                    <tr>
                      <td className="px-3 py-2 font-semibold">dims</td>
                      <td className="px-3 py-2">{String(primarySeries.dims ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">Rows, Columns, Slices</td>
                    </tr>
                    <tr>
                      <td className="px-3 py-2 font-semibold">spacing_mm</td>
                      <td className="px-3 py-2">{String(primarySeries.spacing_mm ?? '')}</td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">PixelSpacing</td>
                    </tr>
                    <tr>
                      <td className="px-3 py-2 font-semibold">volume_path</td>
                      <td className="px-3 py-2 break-all text-[var(--ink-muted)]">
                        {String(primarySeries.volume_path ?? '')}
                      </td>
                      <td className="px-3 py-2 text-[var(--ink-muted)]">OneLake Target Parquet / File</td>
                    </tr>
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
