import { useRef, type ReactNode } from 'react';

export type ScrubItem = {
  id: string;
  /** Position along the track, 0 to 1. Items outside the range are counted at the ends instead of drawn. */
  at: number;
  /** Shown under the handle when selected, and read out by screen readers. */
  label: string;
  /** Short text under the track for this item (for few, evenly spaced items such as slides or pages). */
  tick?: string;
};

/**
 * A draggable track of instances: one tick per item, a handle on the selected one. Dragging or clicking selects the
 * nearest item; arrow keys, Home and End step through them. The same control steps through timeline events, slides,
 * scan timepoints and report pages.
 */
export function Scrubber({
  items,
  selected,
  onSelect,
  name,
  gutter = 0,
  rightPad = 0,
  leading,
  onBefore,
  onAfter,
}: {
  items: ScrubItem[];
  selected: string | null;
  onSelect: (id: string) => void;
  /** Accessible name, e.g. "Visits". */
  name: string;
  /** Left space before the track (lines the track up with a chart's plot area). */
  gutter?: number;
  rightPad?: number;
  /** Content in the gutter. */
  leading?: ReactNode;
  onBefore?: () => void;
  onAfter?: () => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const inView = items.filter((i) => i.at >= 0 && i.at <= 1);
  const before = items.filter((i) => i.at < 0).length;
  const after = items.filter((i) => i.at > 1).length;
  const idx = items.findIndex((i) => i.id === selected);
  const cur = idx >= 0 ? items[idx] : null;
  const labelled = items.some((i) => i.tick);

  const pick = (clientX: number) => {
    const r = trackRef.current?.getBoundingClientRect();
    if (!r || !inView.length) return;
    const f = (clientX - r.left) / r.width;
    let best = inView[0];
    for (const i of inView) if (Math.abs(i.at - f) < Math.abs(best.at - f)) best = i;
    if (best.id !== selected) onSelect(best.id);
  };

  const onKey = (e: React.KeyboardEvent) => {
    const step = (d: number) => {
      const next = items[Math.max(0, Math.min(items.length - 1, (idx < 0 ? 0 : idx) + d))];
      if (next) onSelect(next.id);
    };
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') step(-1);
    else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') step(1);
    else if (e.key === 'Home') items[0] && onSelect(items[0].id);
    else if (e.key === 'End') items[items.length - 1] && onSelect(items[items.length - 1].id);
    else return;
    e.preventDefault();
    e.stopPropagation();
  };

  const pct = (f: number) => `${(Math.max(0, Math.min(1, f)) * 100).toFixed(3)}%`;
  const thumbAt = cur ? Math.max(0, Math.min(1, cur.at)) : null;
  const edge = thumbAt === null ? 'center' : thumbAt < 0.08 ? 'start' : thumbAt > 0.92 ? 'end' : 'center';

  return (
    <div className="scrub" style={{ paddingRight: rightPad }}>
      {gutter > 0 && (
        <div className="scrub-lead" style={{ width: gutter }}>
          {leading}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div
          ref={trackRef}
          className={`scrub-track${labelled ? ' labelled' : ''}`}
          role="slider"
          tabIndex={0}
          aria-label={name}
          aria-valuemin={1}
          aria-valuemax={items.length}
          aria-valuenow={idx + 1}
          aria-valuetext={cur?.label}
          onKeyDown={onKey}
          onPointerDown={(e) => {
            dragging.current = true;
            e.currentTarget.setPointerCapture(e.pointerId);
            e.currentTarget.focus();
            pick(e.clientX);
          }}
          onPointerMove={(e) => dragging.current && pick(e.clientX)}
          onPointerUp={(e) => {
            dragging.current = false;
            e.currentTarget.releasePointerCapture(e.pointerId);
          }}
        >
          <div className="scrub-rule" />
          {inView.map((i) => (
            <div key={i.id} className="scrub-tick" style={{ left: pct(i.at) }} />
          ))}
          {labelled &&
            inView.map((i) => (
              <div key={`t${i.id}`} className={`scrub-ticklabel${i.id === selected ? ' on' : ''}`} style={{ left: pct(i.at) }}>
                {i.tick}
              </div>
            ))}
          {thumbAt !== null && (
            <div className="scrub-thumb" style={{ left: pct(thumbAt) }}>
              {!labelled && <div className={`scrub-caption ${edge}`}>{cur?.label}</div>}
            </div>
          )}
        </div>
        {(before > 0 || after > 0) && (
          <div className="scrub-edges">
            {before > 0 ? (
              <button className="link t-muted" onClick={onBefore}>
                ‹ {before} earlier, outside this view
              </button>
            ) : (
              <span />
            )}
            {after > 0 && (
              <button className="link t-muted" onClick={onAfter}>
                {after} later, outside this view ›
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
