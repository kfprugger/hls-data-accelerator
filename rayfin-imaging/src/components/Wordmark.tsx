export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex shrink-0 items-center gap-2.5 whitespace-nowrap">
      <span aria-hidden className="block h-2.5 w-2.5" style={{ background: 'var(--accent)' }} />
      <span className="text-[17px] font-semibold" style={{ fontFamily: 'var(--font-display)' }}>
        Rayfin Patient 360 &amp; WardFlow
      </span>
      {!compact && <span className="t-faint hidden text-[11.5px] sm:inline">on Microsoft Fabric</span>}
    </div>
  );
}
