import { useTheme, type Theme } from '@/hooks/useTheme';

const OPTIONS: { value: Theme; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

export function ThemeToggle() {
  const { theme, setTheme, variant } = useTheme();
  if (variant === 'daylight') {
    return (
      <span
        className="daylight-theme-pill shrink-0"
        aria-label="Daylight theme active"
        title="Daylight theme (med-1109)"
      >
        Daylight
      </span>
    );
  }
  return (
    <div className="seg shrink-0" role="group" aria-label="Colour theme">
      {OPTIONS.map((o) => (
        <button key={o.value} onClick={() => setTheme(o.value)} aria-pressed={theme === o.value}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
