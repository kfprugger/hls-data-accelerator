//-----------------------------------------------------------------------
// Formatting + row-shaping helpers for query results.
//-----------------------------------------------------------------------

import type { CachedQueryResult } from "@microsoft/fabric-app-data";

/** A query row keyed by its undecorated column name. */
export type Row = Record<string, unknown>;

/**
 * Converts a row-major SDK result into objects keyed by column name, with the
 * DAX decoration stripped: `[totalPaid]` and `care_gaps[gap_type]` both become
 * the bare identifier the UI reads. Returns [] while loading or on error, so
 * callers never branch on query status.
 */
export function rowsOf(result: CachedQueryResult | undefined): Row[] {
    if (!result || result.status !== "success") return [];

    const keys = result.table.columns.map((col) => {
        const bracketed = col.name.match(/\[([^\]]+)\]\s*$/);
        return bracketed ? bracketed[1] : col.name;
    });

    return result.table.rows.map((cells) => {
        const row: Row = {};
        keys.forEach((key, i) => { row[key] = cells[i]; });
        return row;
    });
}

/** First normalized row of a single-row KPI query. */
export function firstRow(result: CachedQueryResult | undefined): Row {
    return rowsOf(result)[0] ?? {};
}

export function num(value: unknown, fallback = 0): number {
    const n = typeof value === "number" ? value : Number(value);
    return Number.isFinite(n) ? n : fallback;
}

export function str(value: unknown, fallback = "—"): string {
    if (value === null || value === undefined || value === "") return fallback;
    return String(value);
}

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** Compact currency above $1k, exact dollars below, so KPI tiles never wrap. */
export function money(value: unknown): string {
    const n = num(value);
    return n >= 1000 ? `$${compact.format(n)}` : `$${n.toFixed(0)}`;
}


/** Compact counts above 10k so five-figure volumes stay one glyph wide. */
export function count(value: unknown): string {
    const n = num(value);
    return n >= 10000 ? compact.format(n) : whole.format(n);
}

export function pct(value: unknown, digits = 1): string {
    return `${(num(value) * 100).toFixed(digits)}%`;
}


/** Demo data is synthetic, but member identifiers are still masked on screen. */
export function maskId(value: unknown): string {
    const s = str(value, "");
    if (s.length <= 8) return s || "—";
    return `${s.slice(0, 4)}…${s.slice(-4)}`;
}

/** "Emanuel231 Schoen8" -> "E. S." */
export function maskName(value: unknown): string {
    const s = str(value, "");
    if (!s || s === "—") return "—";
    return s
        .split(/\s+/)
        .filter(Boolean)
        .map((part) => `${part.replace(/[^A-Za-z]/g, "").charAt(0).toUpperCase()}.`)
        .join(" ");
}

