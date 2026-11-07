export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex shrink-0 items-center gap-2 whitespace-nowrap min-w-0">
      <span aria-hidden className="block h-2.5 w-2.5 shrink-0" style={{ background: 'var(--accent)' }} />
      <span className="text-[14px] sm:text-[17px] font-semibold truncate max-w-[130px] sm:max-w-none" style={{ fontFamily: 'var(--font-display)' }}>
        Rayfin Patient 360 &amp; WardFlow
      </span>
      {!compact && <span className="t-faint hidden text-[11.5px] sm:inline">on Microsoft Fabric</span>}
    </div>
  );
}
