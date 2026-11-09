const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function parseDate(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const s = /^\d{4}$/.test(iso.trim()) ? `${iso.trim()}-01-01` : iso.slice(0, 10);
  const d = new Date(`${s}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDate(iso: string | null | undefined): string {
  const d = parseDate(iso);
  return d ? `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}` : '';
}

export function fmtMonth(iso: string | null | undefined): string {
  const d = parseDate(iso);
  return d ? `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}` : '';
}

/** "2 years 3 months", "5 months", "12 days" from a day count. */
export function fmtSpan(days: number | null | undefined): string {
  if (days === null || days === undefined || !Number.isFinite(days)) return '';
  const d = Math.abs(days);
  if (d < 45) return `${Math.round(d)} days`;
  const months = Math.round(d / 30.44);
  if (months < 24) return `${months} months`;
  const y = Math.floor(months / 12);
  const m = months % 12;
  const ys = `${y} ${y === 1 ? 'year' : 'years'}`;
  return m ? `${ys} ${m} ${m === 1 ? 'month' : 'months'}` : ys;
}

/** Day offset from diagnosis, e.g. "day 482", "day −7". */
export function fmtDay(day: number | null | undefined): string {
  if (day === null || day === undefined) return '';
  return `day ${day < 0 ? '−' : ''}${Math.abs(Math.round(day)).toLocaleString('en-GB')}`;
}

export function fmtBytes(bytes: number | null | undefined, digits?: number): string {
  if (!bytes) return '0 B';
  if (bytes >= 1e12) return `${(bytes / 1e12).toFixed(digits ?? 2)} TB`;
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(digits ?? 1)} GB`;
  if (bytes >= 1e6) {
    const d = digits !== undefined ? digits : (bytes / 1e6) % 1 === 0 ? 0 : 1;
    return `${(bytes / 1e6).toFixed(d)} MB`;
  }
  if (bytes >= 1e3) {
    const d = digits !== undefined ? digits : (bytes / 1e3) % 1 === 0 ? 0 : 1;
    return `${(bytes / 1e3).toFixed(d)} KB`;
  }
  return `${bytes} B`;
}

export function fmtInt(n: number | null | undefined): string {
  return n === null || n === undefined ? '' : Math.round(n).toLocaleString('en-GB');
}

export function fmtNum(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '';
  return n.toLocaleString('en-GB', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '';
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

export function ordinal(n: number): string {
  const r = Math.round(n);
  const s = r % 100 >= 11 && r % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[r % 10] ?? 'th';
  return `${r}${s}`;
}

/** "Stage IIIC" -> "IIIC"; keeps FIGO/AJCC prefix out of tight spaces. */
export function shortStage(stage: string | null | undefined): string {
  return stage ? stage.replace(/^Stage\s+/i, '') : '';
}

/** GDC vocabulary to plain words: "Surgery, NOS" -> "Surgery". */
export function plain(text: string | null | undefined): string {
  if (!text) return '';
  return text
    .replace(/,\s*NOS\b/g, '')
    .replace(/\bNOS\b/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

export function sentence(text: string | null | undefined): string {
  const t = plain(text);
  return t ? t.charAt(0).toUpperCase() + t.slice(1).toLowerCase() : '';
}

export function fmtMoney(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '';
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
}

/** Whole years between birth and a date. */
export function ageAt(date: Date | null, birth: Date): number | null {
  if (!date) return null;
  return Math.floor((date.getTime() - birth.getTime()) / (365.25 * 86_400_000));
}

/** "39 min", "3 h 8 min", "16 days". */
export function fmtDuration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes)) return '';
  if (minutes < 60) return `${Math.round(minutes)} min`;
  if (minutes < 24 * 60) {
    const h = Math.floor(minutes / 60);
    const m = Math.round(minutes % 60);
    return m ? `${h} h ${m} min` : `${h} h`;
  }
  const d = Math.round(minutes / (24 * 60));
  return `${d} ${d === 1 ? 'day' : 'days'}`;
}
