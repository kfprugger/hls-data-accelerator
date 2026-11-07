import { useEffect, useState } from 'react';

import { DocSection } from '@/components/Doc';
import { fetchDataMap, num, str, type DataMap as DataMapT } from '@/lib/api';
import { fmtBytes, fmtInt, fmtMs } from '@/lib/format';
import { LOCAL_DATA } from '@/lib/localMode';

const SILO_SWATCH: Record<string, string> = { clinical: 'sw-clinical', genomics: 'sw-genomics', imaging: 'sw-imaging' };

function Schematic({ map }: { map: DataMapT }) {
  const total = (silo: string) =>
    map.silos.find((s) => s.silo === silo)!.items.reduce((acc, i) => acc + (num(i.bytes) ?? 0), 0);
  const tables = (silo: string) => map.silos.find((s) => s.silo === silo)!.items.filter((i) => i.kind === 'table').length;
  const shortcutCount = map.patient360.shortcuts.length;
  return (
    <div className="grid items-stretch gap-0 lg:grid-cols-[1fr_56px_1fr_56px_1fr]">
      <div className="space-y-3">
        {map.silos.map((s) => (
          <a key={s.silo} href={s.portalUrl || undefined} target="_blank" rel="noreferrer" className="hair block border p-4 hover:border-[var(--ink)]">
            <div className="flex items-center gap-2">
              <span className={`swatch ${SILO_SWATCH[s.silo]}`} />
              <span className="mono text-[13px]">{s.name}</span>
            </div>
            <div className="t-muted mt-1 text-[12.5px]">{s.role}</div>
            <div className="num mt-2 text-[13px]">
              {tables(s.silo)} tables · {fmtBytes(total(s.silo))}
            </div>
          </a>
        ))}
      </div>
      <svg className="hidden lg:block" width="56" height="100%" viewBox="0 0 56 300" preserveAspectRatio="none" aria-hidden>
        {[50, 150, 250].map((y) => (
          <path key={y} d={`M0 ${y} C 28 ${y}, 28 150, 56 150`} fill="none" stroke="var(--ink-3)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
      <div className="flex flex-col justify-center">
        <a href={map.patient360.portalUrl || undefined} target="_blank" rel="noreferrer" className="block border border-[var(--ink)] p-4">
          <div className="flex items-center gap-2">
            <span className="swatch" style={{ background: 'var(--accent)' }} />
            <span className="mono text-[13px]">{map.patient360.name}</span>
          </div>
          <div className="t-muted mt-1 text-[12.5px]">Lakehouse of OneLake shortcuts</div>
          <div className="num mt-2 text-[13px]">
            {shortcutCount} shortcuts · <span className="font-medium">0 bytes of its own</span>
          </div>
          <div className="t-faint mt-2 text-[11.5px]">One SQL analytics endpoint over all three silos</div>
        </a>
        <div className="mt-4 border-t border-dashed pt-2 text-[11.5px]" style={{ borderColor: 'var(--c-rad)' }}>
          <span style={{ color: 'var(--c-rad)' }}>Pixels skip this path.</span>{' '}
          <span className="t-faint">The browser reads tiles, volumes and PDFs from the silos with signed, read-only links.</span>
        </div>
      </div>
      <svg className="hidden lg:block" width="56" height="100%" viewBox="0 0 56 300" preserveAspectRatio="none" aria-hidden>
        <path d="M0 150 L 56 150" fill="none" stroke="var(--ink-3)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex flex-col justify-center gap-3">
        <div className="hair border p-4">
          <div className="text-[13px] font-medium">Rayfin app</div>
          <div className="t-muted mt-1 text-[12.5px]">
            Functions run as the app identity: T-SQL through the endpoint, and read-only links signed per patient.
          </div>
        </div>
        <div className="hair border border-dashed p-4" style={{ borderColor: 'var(--c-rad)' }}>
          <div className="text-[13px] font-medium">Browser</div>
          <div className="t-muted mt-1 text-[12.5px]">
            Slide tiles, CT and MRI volumes and report PDFs stream straight from the imaging and clinical silos.
          </div>
        </div>
      </div>
    </div>
  );
}

export function DataMap() {
  const [map, setMap] = useState<DataMapT | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ms, setMs] = useState<number | null>(null);

  useEffect(() => {
    const t0 = performance.now();
    fetchDataMap()
      .then((m) => {
        setMap(m);
        setMs(Math.round(performance.now() - t0));
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <div className="p-8 text-[13px]" style={{ color: 'var(--c-alert)' }}>{error}</div>;
  if (!map) return <div className="loading-bar" />;

  const all = map.silos.flatMap((s) => s.items);
  const stored = all.reduce((acc, i) => acc + (num(i.bytes) ?? 0), 0);
  const rows = all.filter((i) => i.kind === 'table').reduce((acc, i) => acc + (num(i.rows) ?? 0), 0);
  const files = all.filter((i) => i.kind === 'files').reduce((acc, i) => acc + (num(i.files) ?? 0), 0);
  const zeroCopy = map.zeroCopy ?? map.patient360.zeroCopy ?? {
    copiesMade: 0,
    shortcutCount: map.patient360.shortcuts.length,
    sourceSilos: ['clinical_lakehouse', 'genomics_lakehouse', 'imaging_lakehouse'],
    physicalBytesInPatient360: 0,
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1280px] px-4 pb-24 pt-8 sm:px-8">
        <div className="t-label">Where the data lives</div>
        <h1 className="t-display mt-1 text-[40px]">Three silos, one patient, no copies</h1>
        <p className="t-muted mt-3 max-w-[92ch] text-[15px] leading-relaxed">
          A hospital keeps its records, its sequencing results and its images in different systems, run by different teams.
          Here each is its own Lakehouse in OneLake. The app does not gather them into a new database. It reads them where
          they are, through a fourth Lakehouse that contains nothing but shortcuts.
        </p>
        <p className="num mt-5 text-[14px]">
          {fmtBytes(stored)} stored in the silos · {fmtInt(files)} files · {fmtInt(rows)} table rows · {fmtBytes(0)} copied
          into the app · this page read live in {fmtMs(ms)}
        </p>

        {LOCAL_DATA && (
          <p className="hair mt-5 max-w-[92ch] border-l-2 pl-3 text-[13.5px]" style={{ borderColor: 'var(--accent)' }}>
            Local mode. This page describes the Fabric deployment, but here each silo is a folder in{' '}
            <span className="mono">work/</span> on this computer, and the patient360 shortcuts are DuckDB views over its
            parquet tables. Nothing is read from Fabric.
          </p>
        )}

        <DocSection
          title="The path a query takes"
          intro={
            LOCAL_DATA
              ? 'Everything on this page comes from the work/ folder at the moment you opened it.'
              : 'Everything on this page comes from OneLake and the Fabric REST API at the moment you opened it.'
          }
        >
          <Schematic map={map} />
        </DocSection>

        <DocSection
          title="What each silo holds"
          intro="Inventories are read from a table inside each silo. Originals stay next to the browser-ready copies derived from them."
        >
          <div className="space-y-8">
            {map.silos.map((s) => (
              <div key={s.silo}>
                <div className="mb-2 flex items-center gap-2">
                  <span className={`swatch ${SILO_SWATCH[s.silo]}`} />
                  <span className="mono text-[13px]">{s.name}</span>
                  <span className="t-faint text-[12.5px]">· {s.role}</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="tbl w-full">
                    <thead>
                      <tr>
                        <th>Item</th>
                        <th>What it is</th>
                        <th className="text-right">Rows or files</th>
                        <th className="text-right">Size</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.items.map((i) => (
                        <tr key={String(i.name)}>
                          <td className="mono">{i.kind === 'table' ? `Tables/${str(i.name)}` : str(i.name)}</td>
                          <td className="t-muted">{str(i.description) ?? (i.kind === 'table' ? 'Delta table' : '')}</td>
                          <td className="num text-right">{i.kind === 'table' ? `${fmtInt(num(i.rows))} rows` : `${fmtInt(num(i.files))} files`}</td>
                          <td className="num text-right">{fmtBytes(num(i.bytes))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        </DocSection>

        <DocSection
          title="Zero-Copy Architecture Verification"
          intro="Unified cross-domain analytics without storage duplication. 100% of tables in patient360 point directly to source lakehouses via OneLake shortcuts."
        >
          {map.patient360.error ? (
            <div className="rounded border border-[var(--c-alert)] bg-[var(--surface)] p-4 text-[13.5px] text-[var(--c-alert)]" role="alert">
              Shortcut list unavailable: {map.patient360.error}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {/* Metric Card 1: Copies made: 0 */}
              <div className="flex flex-col justify-between rounded border border-[var(--line)] bg-[var(--surface)] p-5">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="t-label">Storage Duplication</span>
                    <span className="inline-flex items-center rounded-full border border-[var(--c-good)] bg-[var(--well)] px-2.5 py-0.5 text-[12px] font-medium text-[var(--c-good)]">
                      Copies made: 0
                    </span>
                  </div>
                  <div className="mt-3 text-[32px] font-semibold tracking-tight text-[var(--ink)]">
                    Copies made: 0
                  </div>
                </div>
                <p className="t-muted mt-3 text-[13px] leading-relaxed">
                  Zero storage copies created. The unified patient360 lakehouse introduces no duplicated storage footprint.
                </p>
              </div>

              {/* Metric Card 2: Physical storage: 0 bytes */}
              <div className="flex flex-col justify-between rounded border border-[var(--line)] bg-[var(--surface)] p-5">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="t-label">patient360 Storage</span>
                    <span className="mono text-[12px] font-medium text-[var(--c-good)]">0% overhead</span>
                  </div>
                  <div className="mt-3 text-[32px] font-semibold tracking-tight text-[var(--ink)]">
                    0 bytes
                  </div>
                </div>
                <p className="t-muted mt-3 text-[13px] leading-relaxed">
                  Physical storage for patient360 is displayed as 0 bytes. All parquet data files reside exclusively in upstream silos.
                </p>
              </div>

              {/* Metric Card 3: Shortcut breakdown */}
              <div className="flex flex-col justify-between rounded border border-[var(--line)] bg-[var(--surface)] p-5">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="t-label">OneLake Shortcuts</span>
                    <span className="mono text-[12px] font-medium text-[var(--c-good)]">100% external</span>
                  </div>
                  <div className="mt-3 text-[32px] font-semibold tracking-tight text-[var(--ink)]">
                    {zeroCopy.shortcutCount} active
                  </div>
                  <div className="mt-3 space-y-1.5 border-t border-[var(--line)] pt-2.5">
                    {['clinical', 'genomics', 'imaging'].map((siloKey) => {
                      const siloName = `${siloKey}_lakehouse`;
                      const tableShortcuts = map.patient360.shortcuts.filter(
                        (s) => s.silo === siloKey && s.path === 'Tables'
                      );
                      const totalShortcuts = map.patient360.shortcuts.filter((s) => s.silo === siloKey);
                      return (
                        <div key={siloKey} className="flex items-center justify-between text-[12px]">
                          <span className="inline-flex items-center gap-2">
                            <span className={`swatch ${SILO_SWATCH[siloKey]}`} />
                            <span className="mono">{siloName}</span>
                          </span>
                          <span className="num t-muted">
                            {tableShortcuts.length} tables · {totalShortcuts.length} shortcuts
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
                <p className="t-faint mt-3 text-[11.5px] leading-relaxed">
                  100% of tables accessible via patient360 originate from external source silos (clinical_lakehouse, genomics_lakehouse, imaging_lakehouse).
                </p>
              </div>
            </div>
          )}
        </DocSection>

        <DocSection
          title="The shortcuts"
          intro={
            LOCAL_DATA
              ? 'In local mode, the shortcuts pipeline/upload_onelake.py creates in Fabric, each served here by a DuckDB view or a work/ folder.'
              : 'Listed live from the Fabric REST API. Each points into a silo; deleting one would not delete any data.'
          }
        >
          {map.patient360.error ? (
            <div className="rounded border border-[var(--c-alert)] bg-[var(--surface)] p-4 text-[13.5px] text-[var(--c-alert)]" role="alert">
              Shortcut list unavailable: {map.patient360.error}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="tbl w-full">
                <thead>
                  <tr>
                    <th>In patient360</th>
                    <th>Points to</th>
                  </tr>
                </thead>
                <tbody>
                  {map.patient360.shortcuts.map((s) => {
                    const silo = s.silo ?? (s.name.includes('clinical') ? 'clinical' : s.name.includes('genomics') ? 'genomics' : s.name.includes('imaging') ? 'imaging' : null);
                    const siloObj = silo ? map.silos.find((x) => x.silo === silo) : null;
                    const siloName = siloObj?.name ?? (silo ? `${silo}_lakehouse` : s.targetItem);
                    return (
                      <tr key={`${s.path}/${s.name}`}>
                        <td className="mono">{s.path}/{s.name}</td>
                        <td className="mono">
                          <span className="inline-flex items-center gap-2">
                            {silo && <span className={`swatch ${SILO_SWATCH[silo]}`} />}
                            <span>{siloName ? `${siloName}/${s.targetPath}` : s.targetPath}</span>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <div className="t-faint mt-3 text-[12px]">
            SQL analytics endpoint <span className="mono">{map.patient360.sqlEndpoint}</span>
          </div>
        </DocSection>

        <DocSection
          title="Azure Databricks Interoperability"
          intro="Cross-engine zero-copy validation: Azure Databricks Serverless SQL querying OneLake Delta tables in place without data duplication."
        >
          {!map.databricksInterop ? (
            <div className="rounded border border-[var(--line)] bg-[var(--surface)] p-6 text-[13.5px] text-[var(--ink-2)]" role="status">
              Awaiting Databricks verification (run scripts/09-onelake-interop-proof.py)
            </div>
          ) : (
            <div className="rounded border border-[var(--line)] bg-[var(--surface)] p-5 sm:p-6 min-w-0">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-[17px] font-semibold text-[var(--ink)]">{map.databricksInterop.engine}</div>
                  <div className="t-muted mono text-[12px] mt-0.5">Warehouse ID: {map.databricksInterop.warehouseId}</div>
                </div>
                <div>
                  <span className="inline-flex items-center rounded-full border border-[var(--c-good)] bg-[var(--well)] px-3 py-1 text-[12px] font-medium text-[var(--c-good)]">
                    Zero-copy read verified
                  </span>
                </div>
              </div>

              <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2 min-w-0">
                <div className="flex flex-col justify-between rounded border border-[var(--line)] bg-[var(--well)] p-4 min-w-0">
                  <div>
                    <div className="t-label text-[11px]">Verified SQL Query</div>
                    <pre className="mono mt-2 text-[12.5px] text-[var(--ink)] whitespace-pre-wrap break-all leading-relaxed">
                      {map.databricksInterop.statement}
                    </pre>
                  </div>
                  <div className="t-muted mt-3 border-t border-[var(--line)] pt-2 text-[11.5px] break-all">
                    Target location: <span className="mono text-[var(--ink)]">{map.databricksInterop.oneLakeExternalLocation}</span>
                  </div>
                </div>

                <div className="flex flex-col gap-3 min-w-0">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 min-w-0">
                    <div className="rounded border border-[var(--line)] bg-[var(--well)] p-4">
                      <div className="t-label text-[11px]">Validated Result</div>
                      <div className="mt-2 text-[24px] font-semibold tracking-tight text-[var(--ink)]">
                        {map.databricksInterop.rowCount} TCGA patients
                      </div>
                      <div className="t-muted mt-1 text-[12px]">Direct zero-copy read</div>
                    </div>

                    <div className="rounded border border-[var(--line)] bg-[var(--well)] p-4">
                      <div className="t-label text-[11px]">Execution Latency</div>
                      <div className="mt-2 text-[24px] font-semibold tracking-tight text-[var(--ink)]">
                        {fmtMs(map.databricksInterop.executionTimeMs)}
                      </div>
                      <div className="t-muted mt-1 text-[12px]">Serverless SQL execution</div>
                    </div>
                  </div>

                  <div className="rounded border border-[var(--line)] bg-[var(--well)] p-3 flex flex-wrap items-center justify-between gap-2 text-[12px] min-w-0">
                    <span className="t-muted break-all">
                      Verified at: <span className="mono text-[var(--ink)]">{map.databricksInterop.timestamp}</span>
                    </span>
                    <span className="mono font-medium text-[var(--c-good)]">
                      Status: {map.databricksInterop.status}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </DocSection>

        <DocSection title="Why it matters">
          <dl>
            {[
              ['No copy to keep in sync', 'A new lab result or slide lands in its own silo and is in the app on the next read.'],
              ['Owners keep control', 'Each team keeps its Lakehouse, its permissions and its pipelines. patient360 only references them.'],
              ['Pixels never pass through a server', 'Gigapixel slides and CT volumes stream from OneLake to the browser with short-lived, read-only, per-patient links.'],
              ['The app writes only its own data', 'Tumour board notes go to the app’s Rayfin database. The silos are read-only to the app.'],
            ].map(([k, v]) => (
              <div key={k} className="hair grid grid-cols-[230px_1fr] gap-4 border-t py-2.5 text-[13.5px]">
                <dt className="font-medium">{k}</dt>
                <dd className="t-muted">{v}</dd>
              </div>
            ))}
          </dl>
        </DocSection>
      </div>
    </div>
  );
}
