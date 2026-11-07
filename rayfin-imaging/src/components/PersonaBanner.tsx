import { usePersona } from '@/hooks/usePersona';
import { LOCAL_DATA } from '@/lib/localMode';

export function PersonaBanner() {
  const { details, isNurse, togglePersona } = usePersona();

  const isGreen = details.badgeColor === 'green';

  return (
    <div
      data-testid="persona-banner"
      className="w-full shrink-0 border-b border-border/60 bg-muted/40 px-3 sm:px-5 py-2 text-xs transition-colors"
      role="region"
      aria-label="Active Security Persona"
    >
      <div className="flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2 sm:gap-3">
          <div className="flex items-center gap-1.5 font-mono text-[11.5px] text-muted-foreground">
            <span className="font-semibold text-foreground/90">{details.email}</span>
          </div>

          <span className="text-muted-foreground/40 hidden sm:inline" aria-hidden="true">
            ·
          </span>

          <span
            data-testid="persona-badge"
            className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${
              isGreen
                ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30'
                : 'bg-purple-500/15 text-purple-700 dark:text-purple-300 border-purple-500/30'
            }`}
          >
            {details.badgeLabel}
          </span>
        </div>

        {LOCAL_DATA && (
          <div className="flex shrink-0 items-center">
            <button
              type="button"
              data-testid="persona-toggle"
              onClick={togglePersona}
              className="inline-flex cursor-pointer items-center justify-center rounded-md border border-input bg-background px-3 py-1 text-[11.5px] font-medium shadow-2xs hover:bg-accent hover:text-accent-foreground active:scale-[0.98] transition-all"
            >
              {isNurse ? 'Switch to Researcher Persona' : 'Switch to Nurse Persona'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
