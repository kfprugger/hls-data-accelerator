import { useCallback, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

export function PanelSection({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="hair border-t px-5 py-5 first:border-t-0">
      <div className="t-label mb-3 flex items-baseline justify-between gap-3">
        <span>{title}</span>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function PanelRow({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[100px_1fr] gap-3 py-1 text-[12.5px]">
      <dt className="t-faint">{term}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

/** A setting remembered across slides, studies and visits. */
export function useStoredState<T extends string>(key: string, initial: () => T, allowed: readonly T[]): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const stored = localStorage.getItem(key) as T | null;
    return stored && allowed.includes(stored) ? stored : initial();
  });
  const set = useCallback(
    (v: T) => {
      setValue(v);
      localStorage.setItem(key, v);
    },
    [key]
  );
  return [value, set];
}

/** A collapsed side panel: a slim rail that opens it again. */
function Rail({ side, label, onOpen }: { side: 'left' | 'right'; label: string; onOpen: () => void }) {
  return (
    <button
      type="button"
      className={`rail hair shrink-0 ${side === 'left' ? 'border-r' : 'border-l'}`}
      onClick={onOpen}
      title={`Show ${label.toLowerCase()}`}
      aria-label={`Show ${label.toLowerCase()}`}
      aria-expanded={false}
    >
      <span aria-hidden className="rail-chevron">
        {side === 'left' ? '›' : '‹'}
      </span>
      <span className="rail-label">{label}</span>
    </button>
  );
}

/** Narrow, searchable list column used by the Patients, Pathology and 3D/4D workspaces. */
export function ListColumn({
  label = 'List',
  query,
  onQuery,
  placeholder,
  count,
  children,
  collapsed,
  onToggle,
  rail,
}: {
  /** What the list holds, e.g. "Slides"; shown on the collapsed rail when no custom rail is passed. */
  label?: string;
  query: string;
  onQuery: (q: string) => void;
  placeholder: string;
  count: string;
  children: ReactNode;
  collapsed?: boolean;
  onToggle?: () => void;
  /** Compact content shown when the column is collapsed (Patient 360 initials rail). */
  rail?: ReactNode;
}) {
  const [state, setState] = useStoredState<'open' | 'closed'>('atlas.list', () => 'open', ['open', 'closed']);
  const isCollapsed = collapsed !== undefined ? collapsed : state === 'closed';
  const handleToggle = onToggle ?? (() => setState(isCollapsed ? 'open' : 'closed'));

  if (isCollapsed) {
    if (rail) {
      return (
        <aside className="hair flex w-[52px] shrink-0 flex-col items-center border-r">
          <button className="list-toggle mt-3" onClick={handleToggle} aria-label="Show the patient list" title="Show the patient list">
            ›
          </button>
          <div className="mt-2 min-h-0 w-full flex-1 overflow-y-auto pb-3">{rail}</div>
        </aside>
      );
    }
    return <Rail side="left" label={label} onOpen={handleToggle} />;
  }

  return (
    <aside className="hair flex w-[300px] shrink-0 flex-col border-r">
      <div className="hair border-b p-3">
        <div className="flex items-center gap-2">
          <input
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder={placeholder}
            aria-label={placeholder}
            className="field"
          />
          <button
            type="button"
            className={rail ? 'list-toggle' : 'icon-btn'}
            onClick={handleToggle}
            title={`Hide ${label.toLowerCase()}`}
            aria-label={`Hide ${label.toLowerCase()}`}
            aria-expanded
          >
            ‹
          </button>
        </div>
        <div className="t-faint mt-2 text-[11.5px]">{count}</div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto py-1">{children}</div>
    </aside>
  );
}
export type DetailsTab = 'about' | 'controls';

const DETAILS_TABS: readonly { id: DetailsTab; label: string }[] = [
  { id: 'about', label: 'About' },
  { id: 'controls', label: 'Controls' },
];

export interface DetailsPanelState {
  open: boolean;
  tab: DetailsTab;
  setTab: (v: DetailsTab) => void;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  setOpen: (o: boolean) => void;
  show: (t: DetailsTab) => void;
}

/** Open/closed state and active tab of the right-hand details panel, remembered across workspaces. */
export function useDetailsPanel(): DetailsPanelState {
  const [state, setState] = useStoredState<'open' | 'closed'>(
    'atlas.details',
    () => (window.innerWidth >= 1500 ? 'open' : 'closed'),
    ['open', 'closed']
  );
  const [tab, setTab] = useStoredState<DetailsTab>('atlas.detailsTab', () => 'about', ['about', 'controls']);
  const scrollRef = useRef<HTMLDivElement>(null);
  const open = state === 'open';
  return {
    open,
    tab,
    setTab,
    scrollRef,
    setOpen: (o: boolean) => setState(o ? 'open' : 'closed'),
    /** Open the panel on a tab, scrolled to the top. */
    show: (t: DetailsTab) => {
      setState('open');
      setTab(t);
      requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: 0 }));
    },
  };
}
/** Right-hand panel with two tabs: About (the plain-language story and facts) and Controls. Collapses to a rail. */
export function DetailsPanel({ panel, about, controls }: { panel: DetailsPanelState; about: ReactNode; controls: ReactNode }) {
  if (!panel.open) return <Rail side="right" label="Details" onOpen={() => panel.setOpen(true)} />;
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    const next = DETAILS_TABS[(DETAILS_TABS.findIndex((t) => t.id === panel.tab) + 1) % DETAILS_TABS.length];
    panel.setTab(next.id);
    document.getElementById(`details-tab-${next.id}`)?.focus();
  };
  return (
    <aside className="hair flex w-[330px] shrink-0 flex-col border-l" aria-label="Details">
      <div className="hair flex h-11 shrink-0 items-stretch gap-5 border-b pl-5 pr-3" role="tablist" aria-label="Details" onKeyDown={onKey}>
        {DETAILS_TABS.map((t) => (
          <button
            key={t.id}
            id={`details-tab-${t.id}`}
            type="button"
            role="tab"
            aria-selected={panel.tab === t.id}
            aria-controls="details-tabpanel"
            tabIndex={panel.tab === t.id ? 0 : -1}
            className={`tab ${panel.tab === t.id ? 'active' : ''}`}
            onClick={() => panel.setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
        <button
          type="button"
          className="icon-btn ml-auto self-center"
          onClick={() => panel.setOpen(false)}
          title="Hide details"
          aria-label="Hide details"
          aria-expanded
        >
          ›
        </button>
      </div>
      <div
        ref={panel.scrollRef}
        id="details-tabpanel"
        role="tabpanel"
        aria-labelledby={`details-tab-${panel.tab}`}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        {panel.tab === 'about' ? about : controls}
      </div>
    </aside>
  );
}

export function WorkspaceHeader({
  title,
  meta,
  description,
  explain,
  aside,
}: {
  title: string;
  meta: ReactNode;
  description: string;
  /** Plain-language explanation shown below the description. */
  explain?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <div className="workspace-header hair flex flex-wrap shrink-0 items-start gap-4 sm:gap-8 border-b px-5 pb-4 pt-4">
      <div className="min-w-0 flex-1">
        <h1 className="t-display text-[28px]">{title}</h1>
        <div className="t-faint mt-1 text-[12.5px]">{meta}</div>
        <p className="t-muted mt-2 max-w-[110ch] text-[13.5px]">{description}</p>
        {explain}
      </div>
      {aside}
    </div>
  );
}
