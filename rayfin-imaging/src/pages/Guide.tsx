import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { DocSection, DocSpec } from '@/components/Doc';
import {
  GLOSSARY,
  LICENCE_TERMS,
  MARKER_NOTES,
  MIP_COLOUR_NOTES,
  MULTIPLEX_BASICS,
  PATHOLOGY_BASICS,
  PATHOLOGY_CONTROLS,
  RENDER_PRESET_LABELS,
  RENDER_PRESET_NOTES,
  slideNote,
  studyNote,
  VIEW_TERMS,
  VOLUME_CONTROLS,
  WINDOW_NOTES,
  type ImageNote,
  type Term,
} from '@/content/guide';
import { useCatalog, useVolumeCatalog } from '@/hooks/useCatalog';
import { studyPath } from '@/lib/volumes';

const CONTENTS = [
  ['pathology', 'Reading a slide'],
  ['markers', 'Fluorescence markers'],
  ['pathology-controls', 'Pathology controls'],
  ['views', 'Ways to view a scan'],
  ['volume-controls', '3D and 4D controls'],
  ['images', 'Each image explained'],
  ['licences', 'Licences'],
  ['glossary', 'Words you will see'],
] as const;

const WINDOW_LABELS: Record<string, string> = { soft: 'Soft tissue', lung: 'Lung', bonew: 'Bone', gray: 'Greyscale (MRI)' };

function Terms({ items }: { items: Term[] }) {
  return (
    <dl className="hair border-b">
      {items.map((t) => (
        <DocSpec key={t.term} term={t.term}>
          {t.text}
        </DocSpec>
      ))}
    </dl>
  );
}

function ImageEntry({
  title,
  meta,
  note,
  to,
}: {
  title: string;
  meta: string;
  note: ImageNote;
  to: string;
}) {
  return (
    <article className="hair border-t py-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h3 className="text-[16px] font-semibold">{title}</h3>
        <Link to={to} className="link text-[12.5px]">
          Open
        </Link>
      </div>
      <div className="t-faint mt-0.5 text-[12px]">
        {meta}
      </div>
      <p className="t-muted mt-2 text-[13.5px]">{note.plain}</p>
      {note.lookFor.length > 0 && (
        <ul className="t-muted mt-2 list-disc space-y-1 pl-5 text-[13px]">
          {note.lookFor.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function Guide() {
  const { catalog: slides } = useCatalog();
  const { catalog: volumes } = useVolumeCatalog();
  const { hash } = useLocation();
  const multiplex = slides?.slides.find((s) => s.kind === 'fluorescence' && s.channels?.length);
  const markers = multiplex?.channels
    ? multiplex.channels.map((c) => ({ id: c.id, colour: c.color }))
    : Object.keys(MARKER_NOTES).map((id) => ({ id, colour: undefined }));

  // Router links with a hash land at the top of this scroll container; jump to the section once it exists.
  useEffect(() => {
    if (!hash) return;
    const t = window.setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' }), 50);
    return () => window.clearTimeout(t);
  }, [hash, slides, volumes]);

  return (
    <div className="h-full overflow-y-auto">
      <main className="mx-auto max-w-[1240px] px-6 pb-24">
        <section className="pb-10 pt-14">
          <h1 className="t-display max-w-[24ch] text-[44px] md:text-[54px]">What you are looking at, in plain words.</h1>
          <p className="t-muted mt-6 max-w-[68ch] text-[15px]">
            You do not need medical training to use this app. This guide explains what each image shows, what every
            button and setting does, and the words you will meet along the way. The same explanations appear beside
            each image: click <span className="font-medium">In plain words</span> under its title. Resting the pointer
            on any control also shows what it does.
          </p>
          <nav aria-label="Guide contents" className="mt-8 flex flex-wrap gap-x-5 gap-y-2 text-[13px]">
            {CONTENTS.map(([id, label]) => (
              <a key={id} href={`#${id}`} className="link">
                {label}
              </a>
            ))}
          </nav>
        </section>

        <DocSection id="pathology" title="Reading a slide" intro="Pathology is the study of tissue under the microscope.">
          <div className="t-muted max-w-[72ch] space-y-3 text-[14px]">
            {PATHOLOGY_BASICS.map((p) => (
              <p key={p}>{p}</p>
            ))}
          </div>
        </DocSection>

        <DocSection id="markers" title="Fluorescence markers" intro="The marker chips above the colorectal CyCIF slide.">
          <p className="t-muted max-w-[72ch] text-[14px]">{MULTIPLEX_BASICS}</p>
          <table className="data-table mt-6">
            <thead>
              <tr>
                <th>Marker</th>
                <th>What it shows</th>
                <th>Why it matters</th>
              </tr>
            </thead>
            <tbody>
              {markers.map(({ id, colour }) => {
                const m = MARKER_NOTES[id];
                if (!m) return null;
                return (
                  <tr key={id}>
                    <td className="whitespace-nowrap font-medium">
                      {colour && <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: colour }} />}
                      {m.name}
                    </td>
                    <td>{m.shows}</td>
                    <td className="t-muted">{m.why}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </DocSection>

        <DocSection id="pathology-controls" title="Pathology controls" intro="Everything on the Pathology tab, left to right.">
          <Terms items={PATHOLOGY_CONTROLS} />
        </DocSection>

        <DocSection
          id="views"
          title="Ways to view a scan"
          intro="CT and MRI scanners record a stack of thin slices. The viewer can show them as flat slices or rebuild them in 3D."
        >
          <Terms items={VIEW_TERMS} />
        </DocSection>

        <DocSection id="volume-controls" title="3D and 4D controls" intro="Everything on the 3D and 4D imaging tab.">
          <Terms items={VOLUME_CONTROLS} />
          <h3 className="t-label mb-2 mt-8">Colour settings in 3D</h3>
          <Terms items={Object.entries(RENDER_PRESET_NOTES).map(([id, text]) => ({ term: RENDER_PRESET_LABELS[id] ?? id, text }))} />
          <h3 className="t-label mb-2 mt-8">Windows in 2D views</h3>
          <Terms items={Object.entries(WINDOW_NOTES).map(([id, text]) => ({ term: WINDOW_LABELS[id] ?? id, text }))} />
          <h3 className="t-label mb-2 mt-8">MIP colours</h3>
          <Terms items={MIP_COLOUR_NOTES} />
        </DocSection>

        <DocSection id="images" title="Each image explained" intro="What each slide and scan shows, and what to try.">
          <h3 className="t-label mb-1">Pathology slides</h3>
          {slides ? (
            slides.slides.map((s) => (
              <ImageEntry
                key={s.id}
                title={s.title}
                meta={`${s.organ} · ${s.kind === 'fluorescence' ? 'multiplexed immunofluorescence' : 'H&E stain'}`}
                note={slideNote(s.id, s.kind)}
                to={`/pathology?slide=${s.id}`}
              />
            ))
          ) : (
            <p className="t-faint py-4 text-[13px]">Reading the slide catalog…</p>
          )}
          {[{ heading: '3D and 4D studies', items: volumes?.studies }].map(({ heading, items }) => (
            <div key={heading}>
              <h3 className="t-label mb-1 mt-10">{heading}</h3>
              {items ? (
                items.map((s) => (
                  <ImageEntry
                    key={s.id}
                    title={s.title}
                    meta={`${s.modality} · ${s.license}`}
                    note={studyNote(s.id, s.description)}
                    to={studyPath(s)}
                  />
                ))
              ) : (
                <p className="t-faint py-4 text-[13px]">Reading the volume catalog…</p>
              )}
            </div>
          ))}
        </DocSection>

        <DocSection
          id="licences"
          title="Licences"
          intro="All data here is public and comes from its original publishers; this app hosts none of it."
        >
          <Terms items={LICENCE_TERMS} />
        </DocSection>

        <DocSection id="glossary" title="Words you will see">
          <Terms items={GLOSSARY} />
        </DocSection>

        <p className="t-faint hair border-t pt-6 text-[12.5px]">
          For demonstration, education and research only. Not medical advice, not a medical device and not for diagnosis.
        </p>
      </main>
    </div>
  );
}
