import type { ReactNode } from 'react';

/** Editorial section: title and intro on the left, content on the right. Used by Overview and Guide. */
export function DocSection({
  id,
  title,
  intro,
  children,
}: {
  id?: string;
  title: string;
  intro?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} className="hair grid scroll-mt-4 gap-x-16 gap-y-4 border-t py-10 lg:grid-cols-[260px_minmax(0,1fr)]">
      <div>
        <h2 className="t-display text-[24px]">{title}</h2>
        {intro && <p className="t-muted mt-2 text-[13px]">{intro}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

export function DocSpec({ term, children }: { term: ReactNode; children: ReactNode }) {
  return (
    <div className="hair grid grid-cols-[170px_1fr] gap-4 border-t py-2 text-[13.5px]">
      <dt className="t-faint">{term}</dt>
      <dd>{children}</dd>
    </div>
  );
}
