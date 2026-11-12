import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { DocSection as Section, DocSpec as Spec } from '@/components/Doc';
import { useCatalog, useVolumeCatalog } from '@/hooks/useCatalog';
import { formatBytes } from '@/lib/catalog';
import { formatMb } from '@/lib/volumes';

const IMAGE_TYPES = [
  {
    type: 'Whole-slide pathology',
    examples: 'H&E histology, brightfield',
    stored: 'Aperio SVS (pyramidal TIFF)',
    served: 'Deep Zoom (DZI) pyramid of 1024 px JPEG tiles',
    viewer: 'OpenSeadragon, WebGL',
  },
  {
    type: 'CT and CT angiography',
    examples: 'Whole body, contrast-enhanced',
    stored: 'DICOM, NIfTI',
    served: 'NIfTI, 16-bit Hounsfield units',
    viewer: 'NiiVue volume rendering and MPR',
  },
  {
    type: 'PET',
    examples: '18F-FDG, body-weight SUV',
    stored: 'DICOM (Bq/ml)',
    served: 'NIfTI SUV overlay',
    viewer: 'NiiVue colour overlay on CT',
  },
  {
    type: 'MRI, including 4D series',
    examples: 'Fetal face, body and brain atlases, one volume per week',
    stored: 'NIfTI',
    served: 'NIfTI per time point',
    viewer: 'NiiVue with timeline playback',
  },
  {
    type: 'Segmentations',
    examples: 'Lesion masks, organ and vessel labels',
    stored: 'DICOM SEG, NIfTI masks',
    served: 'NIfTI label map plus colour table',
    viewer: 'NiiVue label overlay',
  },
  {
    type: 'Colour volumes',
    examples: 'Cryosection photography',
    stored: 'PNG sections',
    served: 'RGBA NIfTI with transparent background',
    viewer: 'NiiVue true-colour rendering',
  },
  {
    type: 'Multiplexed immunofluorescence',
    examples: 'CyCIF, 36 protein markers on one section',
    stored: 'DICOM slide microscopy, one image per marker',
    served: 'One coloured Deep Zoom pyramid per marker',
    viewer: 'OpenSeadragon, additive blending with marker toggles',
  },
  {
    type: '4D CT with RT structures',
    examples: 'Respiratory-gated, ten breathing phases',
    stored: 'DICOM CT and RTSTRUCT per phase',
    served: '4D NIfTI plus 4D label map',
    viewer: 'NiiVue, breathing playback in 3D',
  },
  {
    type: 'Diffusion tractography',
    examples: 'White-matter fibre bundles',
    stored: 'TRK streamlines',
    served: 'Thinned TRK per bundle group',
    viewer: 'NiiVue fibre rendering, direction-coloured',
  },
];

const CAPABILITIES = [
  ['One viewer', 'Pathology and radiology in the same browser app, Microsoft Entra sign-in, no install'],
  ['MPR', 'Axial, coronal and sagittal planes linked to a 3D view, with crosshair navigation'],
  ['MIP', 'Rotating maximum intensity projections: PET (SUV) and bone-subtracted CT angiography'],
  ['Volume rendering', 'CT transfer functions (bone, vessels, arteries, muscle, skin, glass lungs), true-colour volumes, clip planes'],
  ['Image fusion', 'PET over CT with SUV window, colour map and opacity; segmentations over CT and MRI'],
  ['4D', 'Breathing lungs in real time, and week-by-week growth timelines for the fetal brain and body'],
  ['Deep zoom', 'Gigapixel slides streamed tile by tile, magnification presets, scale bar, guided tour'],
  ['Collaboration', 'Shared pins stored in the app database, deep links to the exact view'],
];

export function Overview() {
  const { catalog: slides } = useCatalog();
  const { catalog: volumes } = useVolumeCatalog();

  const s = useMemo(() => {
    const all = slides?.slides ?? [];
    return {
      count: all.length,
      organs: new Set(all.map((x) => x.organ)).size,
      gigapixels: all.reduce((n, x) => n + (x.width * x.height) / 1e9, 0),
      tiles: all.reduce((n, x) => n + x.tileCount, 0),
      tilesBytes: all.reduce((n, x) => n + (x.tilesBytes ?? 0), 0),
      raw: all.reduce((n, x) => n + x.rawSizeBytes, 0),
      objectives: [...new Set(all.map((x) => x.objectivePower).filter(Boolean))].sort().map((o) => `${o}×`).join(' and '),
      mpp: all.map((x) => x.mpp ?? 0).filter(Boolean),
    };
  }, [slides]);

  const v = useMemo(() => {
    const all = volumes?.studies ?? [];
    return {
      count: all.length,
      modalities: [...new Set(all.map((x) => x.modality))],
      categories: [...new Set(all.map((x) => x.category))],
      served: all.reduce((n, x) => n + x.sizeBytes, 0),
      // The two Visible Human studies share one source; count each original folder once.
      raw: [...new Map(all.map((x) => [x.rawPath, x])).values()].reduce((n, x) => n + x.rawSizeBytes, 0),
      rawFiles: [...new Map(all.map((x) => [x.rawPath, x])).values()].reduce((n, x) => n + x.rawFiles, 0),
      frames: all.reduce((n, x) => n + (x.timeline?.frames.length ?? 1), 0),
      longestTimeline: Math.max(0, ...all.map((x) => x.timeline?.frames.length ?? 0)),
    };
  }, [volumes]);

  const datasets = useMemo(() => {
    const rows: { name: string; use: string; license: string; citation: string; url: string }[] = [];
    const he = slides?.slides.filter((x) => x.kind !== 'fluorescence') ?? [];
    if (he.length) {
      rows.push({
        name: 'The Cancer Genome Atlas (TCGA), NCI Genomic Data Commons',
        use: `${he.length} diagnostic H&E whole-slide images across ${new Set(he.map((x) => x.organ)).size} organ sites`,
        license: 'NIH open access (GDC data use policy)',
        citation: 'The results shown here are in whole or part based upon data generated by the TCGA Research Network: https://www.cancer.gov/tcga',
        url: 'https://portal.gdc.cancer.gov/',
      });
    }
    for (const x of slides?.slides.filter((y) => y.kind === 'fluorescence') ?? []) {
      rows.push({
        name: x.source,
        use: x.title,
        license: x.license ?? 'CC BY 4.0',
        citation: 'Human Tumor Atlas Network (HTAN), HMS Tissue Atlas, CyCIF of colorectal cancer. https://humantumoratlas.org',
        url: x.sourceUrl,
      });
    }
    const bySource = new Map<
      string,
      { name: string; uses: string[]; license: string; citation: string; url: string }
    >();
    for (const st of volumes?.studies ?? []) {
      const e = bySource.get(st.sourceUrl) ?? {
        name: st.source,
        uses: [],
        license: st.license,
        citation: st.citation,
        url: st.sourceUrl,
      };
      e.uses.push(st.title);
      bySource.set(st.sourceUrl, e);
    }
    for (const e of bySource.values()) rows.push({ ...e, use: e.uses.join('; ') });
    return rows;
  }, [slides, volumes, s.count, s.organs]);

  const lake = slides?.lakehouse ?? volumes?.lakehouse;
  const mppRange = s.mpp.length ? `${Math.min(...s.mpp).toFixed(3)} to ${Math.max(...s.mpp).toFixed(3)} µm per pixel` : '…';

  return (
    <div className="h-full overflow-y-auto">
      <main className="mx-auto max-w-[1240px] px-6 pb-24">
        <section className="grid gap-x-16 gap-y-8 pb-12 pt-14 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div>
            <h1 className="t-display max-w-[24ch] text-[44px] md:text-[54px]">
              Multi-modal Patient 360, WardFlow Cardiology &amp; 2D/3D/4D Imaging on Microsoft Fabric.
            </h1>
            <p className="t-muted mt-6 max-w-[68ch] text-[15px]">
              Built on Project Rayfin, this unified app brings together longitudinal oncology records (15 TCGA patients
              joined across clinical, genomics and imaging Lakehouses via OneLake shortcuts), Idan Shimon&apos;s WardFlow
              &amp; Caldova Cardiology 7-beat governed decision-support workbench over HDS Reporting Gold, and
              zero-server OpenSeadragon pathology + NiiVue 3D/4D radiology streaming directly from OneLake.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/patients" className="btn btn-ink h-10 px-4 text-[13.5px]">
                Open Patient 360 (15 TCGA Records)
              </Link>
              <Link to="/wardflow" className="btn btn-primary h-10 px-4 text-[13.5px]">
                Open WardFlow Cardiology &amp; Agent Loop
              </Link>
              <Link to="/pathology" className="btn h-10 px-4 text-[13.5px]">
                Open 2D Pathology
              </Link>
              <Link to="/volumes" className="btn h-10 px-4 text-[13.5px]">
                Open 3D and 4D Imaging
              </Link>
            </div>
          </div>
          <dl className="hair self-end border-b">
            <Spec term="Pathology slides">{slides ? `${s.count} slides, ${s.gigapixels.toFixed(1)} gigapixels` : '…'}</Spec>
            <Spec term="Volumes">{volumes ? `${v.count} studies, ${v.frames} volumes` : '…'}</Spec>
            <Spec term="Stored in OneLake">
              {slides && volumes ? formatMb(s.raw + s.tilesBytes + v.raw + v.served) : '…'}
            </Spec>
            <Spec term="Workspace">{lake ? lake.workspaceName : '…'}</Spec>
            <Spec term="Lakehouse">{lake ? lake.lakehouseName : '…'}</Spec>
          </dl>
        </section>

        <Section title="What it views" intro="Each format is converted once in the pipeline, then served in a form the browser can stream.">
          <table className="data-table">
            <thead>
              <tr>
                <th>Image type</th>
                <th>Stored as</th>
                <th>Served as</th>
                <th>Rendered with</th>
              </tr>
            </thead>
            <tbody>
              {IMAGE_TYPES.map((t) => (
                <tr key={t.type}>
                  <td>
                    <div className="font-medium">{t.type}</div>
                    <div className="t-faint text-[12px]">{t.examples}</div>
                  </td>
                  <td>{t.stored}</td>
                  <td>{t.served}</td>
                  <td>{t.viewer}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Viewer capabilities" intro="The tools an enterprise imaging viewer is judged on, and where to see them here.">
          <dl className="hair border-b">
            {CAPABILITIES.map(([k, v]) => (
              <Spec key={k} term={k}>
                {v}
              </Spec>
            ))}
          </dl>
        </Section>

        <Section
          title="Where the data lives"
          intro={
            lake ? (
              <>
                One Lakehouse in the <span className="t-mono">{lake.workspaceName}</span> workspace.{' '}
                <a href={lake.portalUrl} target="_blank" rel="noreferrer" className="link">
                  Open in Fabric ↗
                </a>
              </>
            ) : undefined
          }
        >
          <table className="data-table">
            <thead>
              <tr>
                <th>Location</th>
                <th>Contents</th>
                <th className="text-right">Files</th>
                <th className="text-right">Size</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="t-mono text-[12px]">Files/raw/</td>
                <td>Original pathology slides (SVS, DICOM)</td>
                <td className="text-right">{s.count || '…'}</td>
                <td className="text-right">{slides ? formatBytes(s.raw) : '…'}</td>
              </tr>
              <tr>
                <td className="t-mono text-[12px]">Files/slides/</td>
                <td>Deep Zoom tile pyramids and thumbnails</td>
                <td className="text-right">{slides ? s.tiles.toLocaleString() : '…'}</td>
                <td className="text-right">{slides && s.tilesBytes ? formatBytes(s.tilesBytes) : '…'}</td>
              </tr>
              <tr>
                <td className="t-mono text-[12px]">Files/raw/volumes/</td>
                <td>Original volume sources: DICOM, NIfTI, cryosection PNGs</td>
                <td className="text-right">{volumes ? v.rawFiles.toLocaleString() : '…'}</td>
                <td className="text-right">{volumes ? formatMb(v.raw) : '…'}</td>
              </tr>
              <tr>
                <td className="t-mono text-[12px]">Files/volumes/</td>
                <td>Browser-ready NIfTI volumes, colour tables, thumbnails</td>
                <td className="text-right">{volumes ? `${v.count} studies` : '…'}</td>
                <td className="text-right">{volumes ? formatMb(v.served) : '…'}</td>
              </tr>
              <tr>
                <td className="t-mono text-[12px]">Tables/slides, Tables/volumes</td>
                <td>Delta tables of the two catalogs, queryable from SQL and Power BI</td>
                <td className="text-right">{slides && volumes ? `${s.count + v.count} rows` : '…'}</td>
                <td />
              </tr>
              <tr>
                <td className="t-mono text-[12px]">SlidePin</td>
                <td>Shared pathology pins, in the Rayfin app database (Fabric SQL)</td>
                <td />
                <td />
              </tr>
            </tbody>
          </table>
        </Section>

        <Section title="Collections" intro="Size and acquisition metadata, read live from the two catalogs.">
          <div className="grid gap-10 xl:grid-cols-2">
            <div>
              <h3 className="mb-2 font-medium">Pathology</h3>
              <dl className="hair border-b">
                <Spec term="Slides">{s.count || '…'}</Spec>
                <Spec term="Organ sites">{s.organs || '…'}</Spec>
                <Spec term="Pixels">{slides ? `${s.gigapixels.toFixed(1)} gigapixels` : '…'}</Spec>
                <Spec term="Scan magnification">{s.objectives || '…'}</Spec>
                <Spec term="Resolution">{mppRange}</Spec>
                <Spec term="Stain">Haematoxylin and eosin</Spec>
              </dl>
            </div>
            <div>
              <h3 className="mb-2 font-medium">3D and 4D imaging</h3>
              <dl className="hair border-b">
                <Spec term="Studies">
                  {volumes ? `${v.count} (${v.categories.join(', ')})` : '…'}
                </Spec>
                <Spec term="Modalities">{volumes ? v.modalities.join('; ') : '…'}</Spec>
                <Spec term="Volumes">{volumes ? `${v.frames}${v.longestTimeline ? `, including ${/^(8|11|18)/.test(String(v.longestTimeline)) ? 'an' : 'a'} ${v.longestTimeline}-step timeline` : ''}` : '…'}</Spec>
                <Spec term="Served to browser">{volumes ? formatMb(v.served) : '…'}</Spec>
                <Spec term="Original sources">{volumes ? `${formatMb(v.raw)} in ${v.rawFiles.toLocaleString()} files` : '…'}</Spec>
              </dl>
            </div>
          </div>
        </Section>

        <Section
          title="Datasets"
          intro="All data is public and de-identified. Each source is credited as its licence requires. The code repository hosts no data: everything is downloaded from these publishers."
        >
          <table className="data-table">
            <thead>
              <tr>
                <th>Dataset</th>
                <th>Used for</th>
                <th>Licence</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((d) => (
                <tr key={d.url}>
                  <td className="w-[38%]">
                    <a href={d.url} target="_blank" rel="noreferrer" className="link font-medium">
                      {d.name}
                    </a>
                    <div className="t-faint mt-1 text-[11.5px]">{d.citation}</div>
                  </td>
                  <td>{d.use}</td>
                  <td className="w-[18%]">
                    <div>{d.license}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="How it works">
          <ol className="max-w-[72ch] list-decimal space-y-3 pl-5 text-[14px]">
            <li>
              A Python pipeline in the repository downloads each dataset, converts it for the web and uploads both the
              originals and the converted files to the Lakehouse.
            </li>
            <li>The app is a Rayfin Fabric app. Users sign in with Microsoft Entra; the app itself is protected.</li>
            <li>
              Two Rayfin functions, <span className="t-mono">getSlideCatalog</span> and{' '}
              <span className="t-mono">getVolumeCatalog</span>, read the catalogs from OneLake as the app identity and sign
              read-only, folder-scoped tokens that expire within the hour. Original files are never exposed.
            </li>
            <li>
              The browser streams Deep Zoom tiles into OpenSeadragon and NIfTI volumes into NiiVue directly from
              OneLake, using the GPU for rendering.
            </li>
            <li>Pins are written to the app database through Rayfin's data API, with row-level security per author.</li>
          </ol>
        </Section>

        <Section title="Notes">
          <ul className="t-muted max-w-[72ch] list-disc space-y-3 pl-5 text-[14px]">
            <li>For demonstration, education and research only. Not a medical device and not for diagnosis.</li>
            <li>Needs a browser with WebGL 2 (current Edge, Chrome, Safari or Firefox).</li>
            <li>
              Openly licensed 3D ultrasound of a whole fetus is not published, so the fetal studies use MRI atlases from
              King's College London: the face, the body with its organs, and the brain. Ultrasound exported as NIfTI
              from a clinical system can be added to the same catalog and plays on the same timeline.
            </li>
            <li>
              Every dataset used here is public and its licence allows reuse with attribution, including commercial use.
              This project's code hosts none of the data.
            </li>
            <li>
              New slides or studies appear in the tabs as soon as their files and catalog entries are in the Lakehouse.
              The app has no fixed list.
            </li>
          </ul>
        </Section>
      </main>
    </div>
  );
}
