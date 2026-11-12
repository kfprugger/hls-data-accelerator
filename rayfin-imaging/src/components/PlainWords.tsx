import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import type { ImageNote } from '@/content/guide';

/** Plain-language explanation of the open image, for the top of the details panel. */
export function PlainWords({ note, guideHref, children }: { note: ImageNote; guideHref: string; children?: ReactNode }) {
  return (
    <div className="t-muted text-[13px] leading-relaxed">
      <p>{note.plain}</p>
      {note.lookFor.length > 0 && (
        <>
          <div className="t-label mb-1.5 mt-4">Things to try</div>
          <ul className="list-disc space-y-1.5 pl-4">
            {note.lookFor.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </>
      )}
      {children}
      <Link to={guideHref} className="link mt-4 inline-block text-[12.5px]">
        Guide to every control and term
      </Link>
    </div>
  );
}

/** Header link that opens the details panel at its plain-language section. */
export function PlainWordsLink({ onOpen }: { onOpen: () => void }) {
  return (
    <button type="button" className="link t-muted mt-2 text-[12.5px]" onClick={onOpen}>
      In plain words
    </button>
  );
}
