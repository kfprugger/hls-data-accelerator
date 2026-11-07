import {
  memo,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { getGlossaryDefinition, type GlossaryTerm } from '@/lib/glossary';

export interface GlossaryTooltipProps {
  term: GlossaryTerm | string;
  children?: ReactNode;
  className?: string;
  definition?: string;
  showIcon?: boolean;
}

interface Coords {
  top: number;
  left: number;
  placement: 'top' | 'bottom';
}

export const GlossaryTooltip = memo(function GlossaryTooltip({
  term,
  children,
  className = '',
  definition: customDefinition,
  showIcon = false,
}: GlossaryTooltipProps) {
  const tooltipId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);

  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const openTimerRef = useRef<number | null>(null);
  const closeTimerRef = useRef<number | null>(null);

  const definition = customDefinition ?? getGlossaryDefinition(term);

  const clearTimers = useCallback(() => {
    if (openTimerRef.current !== null) {
      window.clearTimeout(openTimerRef.current);
      openTimerRef.current = null;
    }
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const triggerRect = triggerRef.current.getBoundingClientRect();
    const tooltipEl = tooltipRef.current;

    const tooltipWidth = tooltipEl ? tooltipEl.offsetWidth : 280;
    const tooltipHeight = tooltipEl ? tooltipEl.offsetHeight : 90;
    const margin = 8;
    const padding = 12;

    // Default above, flip below if not enough room on top
    let placement: 'top' | 'bottom' = 'top';
    let top = triggerRect.top - tooltipHeight - margin;

    if (top < padding) {
      placement = 'bottom';
      top = triggerRect.bottom + margin;
    }

    // Horizontal centering with viewport clamping
    const maxLeft = Math.max(padding, window.innerWidth - tooltipWidth - padding);
    let left = triggerRect.left + triggerRect.width / 2 - tooltipWidth / 2;
    if (left < padding) left = padding;
    if (left > maxLeft) left = maxLeft;
    setCoords({ top, left, placement });
  }, []);

  const openTooltip = useCallback(
    (delay = 100) => {
      clearTimers();
      openTimerRef.current = window.setTimeout(() => {
        setIsOpen(true);
      }, delay);
    },
    [clearTimers]
  );

  const closeTooltip = useCallback(
    (immediate = false) => {
      clearTimers();
      if (immediate) {
        setIsOpen(false);
      } else {
        closeTimerRef.current = window.setTimeout(() => {
          setIsOpen(false);
        }, 80);
      }
    },
    [clearTimers]
  );

  // Position calculation and global Escape dismissal whenever opened
  useEffect(() => {
    if (isOpen) {
      updatePosition();
      const onScrollOrResize = () => updatePosition();
      const onGlobalKeyDown = (e: globalThis.KeyboardEvent) => {
        if (e.key === 'Escape') closeTooltip(true);
      };
      window.addEventListener('scroll', onScrollOrResize, true);
      window.addEventListener('resize', onScrollOrResize);
      window.addEventListener('keydown', onGlobalKeyDown);
      return () => {
        window.removeEventListener('scroll', onScrollOrResize, true);
        window.removeEventListener('resize', onScrollOrResize);
        window.removeEventListener('keydown', onGlobalKeyDown);
      };
    } else {
      setCoords(null);
    }
  }, [isOpen, updatePosition, closeTooltip]);

  // Clean up timers on unmount
  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  const handleKeyDown = (e: KeyboardEvent<HTMLSpanElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      closeTooltip(true);
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      setIsOpen((prev) => !prev);
    }
  };

  const content = children ?? term;

  return (
    <>
      <span
        ref={triggerRef}
        role="button"
        tabIndex={0}
        aria-describedby={isOpen ? tooltipId : undefined}
        aria-expanded={isOpen}
        aria-label={`${typeof content === 'string' ? content : term}: Microsoft Fabric glossary definition`}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        onMouseEnter={() => openTooltip(100)}
        onMouseLeave={() => closeTooltip(false)}
        onFocus={() => openTooltip(0)}
        onBlur={() => closeTooltip(true)}
        onKeyDown={handleKeyDown}
        className={`glossary-tooltip-trigger inline-flex items-center gap-1 cursor-help border-b border-dotted border-current/70 hover:border-current focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)] transition-colors ${className}`}
        data-glossary-term={term}
      >
        <span>{content}</span>
        {showIcon && (
          <span
            className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[var(--well,#f1f5f9)] text-[9.5px] font-mono text-[var(--ink-3,#64748b)] border border-[var(--line,#cbd5e1)]"
            aria-hidden="true"
          >
            ?
          </span>
        )}
      </span>

      {isOpen &&
        definition &&
        createPortal(
          <div
            ref={tooltipRef}
            id={tooltipId}
            role="tooltip"
            aria-live="polite"
            className="glossary-tooltip-popup pointer-events-none fixed z-[9999] max-w-[320px] rounded-lg border border-[var(--line,#e2e8f0)] bg-[var(--surface,#ffffff)] dark:bg-slate-900 dark:border-slate-700 p-3 text-[12px] leading-relaxed text-[var(--ink,#0f172a)] dark:text-slate-100 shadow-xl transition-opacity animate-in fade-in-0 zoom-in-95 duration-100"
            style={{
              top: coords ? `${coords.top}px` : '-9999px',
              left: coords ? `${coords.left}px` : '-9999px',
              visibility: coords ? 'visible' : 'hidden',
            }}
          >
            <div className="flex items-center gap-1.5 pb-1 mb-1 border-b border-[var(--line,#e2e8f0)] dark:border-slate-800 text-[10.5px] font-semibold uppercase tracking-wider text-[var(--accent)]">
              <span>Microsoft Fabric</span>
              <span className="text-[var(--ink-3,#94a3b8)]">·</span>
              <span className="text-[var(--ink,#0f172a)] dark:text-slate-200">{term}</span>
            </div>
            <div className="font-normal text-[12px] text-[var(--ink-2,#334155)] dark:text-slate-300">
              {definition}
            </div>
          </div>,
          document.body
        )}
    </>
  );
});
