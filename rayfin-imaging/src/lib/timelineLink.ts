import type { MarkKind } from '@/components/patient/Timeline';

/** Ask the Lifetime timeline to select an event and show its detail panel. */
export type OpenRequest = {
  /** Exact mark id, e.g. `v:<encounter_id>`. */
  id?: string;
  /** Otherwise the kind and title of the mark, nearest to `at`. */
  kind?: MarkKind;
  title?: string;
  at?: string | null;
  /** Mark to use when nothing matches (e.g. the visit where an item was recorded). */
  fallback?: string;
};

export const OPEN_EVENT = 'p360:open';

export function openInTimeline(req: OpenRequest): void {
  window.dispatchEvent(new CustomEvent<OpenRequest>(OPEN_EVENT, { detail: req }));
}
