//-----------------------------------------------------------------------
// Presentation primitives for the command center: KPI tiles, ranked bars,
// a radial gauge and the loading/empty states they share.
//-----------------------------------------------------------------------

import { motion } from "framer-motion";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { ACCENT, type Accent } from "./accent";

interface PanelProps {
    title: string;
    subtitle?: string;
    accent: Accent;
    children: ReactNode;
    className?: string;
}

export function Panel({ title, subtitle, accent, children, className }: PanelProps) {
    return (
        <motion.section
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
            className={cn(
                "relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04] p-5 backdrop-blur-xl",
                "ring-1 ring-inset", ACCENT[accent].ring, className,
            )}
        >
            <div
                aria-hidden
                className={cn(
                    "pointer-events-none absolute -right-16 -top-20 h-44 w-44 rounded-full bg-gradient-to-br opacity-20 blur-3xl",
                    ACCENT[accent].from, ACCENT[accent].to,
                )}
            />
            <header className="mb-4">
                <h3 className="text-sm font-semibold tracking-wide text-white/90">{title}</h3>
                {subtitle && <p className="mt-0.5 text-xs text-white/45">{subtitle}</p>}
            </header>
            {children}
        </motion.section>
    );
}

interface KpiProps {
    label: string;
    value: string;
    caption?: string;
    accent: Accent;
    index?: number;
}

export function Kpi({ label, value, caption, accent, index = 0 }: KpiProps) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.4, delay: index * 0.05, ease: "easeOut" }}
            className={cn(
                "group relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-xl",
                "transition-transform duration-300 hover:-translate-y-1", ACCENT[accent].glow,
            )}
        >
            <div
                aria-hidden
                className={cn("absolute inset-x-0 top-0 h-px bg-gradient-to-r opacity-80", ACCENT[accent].from, ACCENT[accent].to)}
            />
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-white/45">{label}</p>
            <p className="mt-2 bg-gradient-to-br from-white to-white/60 bg-clip-text text-3xl font-semibold text-transparent tabular-nums">
                {value}
            </p>
            {caption && <p className={cn("mt-1 text-xs", ACCENT[accent].text)}>{caption}</p>}
        </motion.div>
    );
}

interface BarDatum {
    label: string;
    value: number;
    display: string;
    meta?: string;
}

export function RankedBars({ rows, accent, emptyLabel = "No rows returned" }: { rows: BarDatum[]; accent: Accent; emptyLabel?: string }) {
    if (rows.length === 0) return <Empty label={emptyLabel} />;
    const max = rows.reduce((acc, r) => Math.max(acc, r.value), 0) || 1;

    return (
        <ul className="space-y-3">
            {rows.map((row, i) => (
                <li key={`${row.label}-${i}`}>
                    <div className="mb-1 flex items-baseline justify-between gap-3">
                        <span className="truncate text-sm text-white/80">{row.label}</span>
                        <span className="shrink-0 text-sm font-semibold tabular-nums text-white">{row.display}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/10">
                        <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${Math.max(3, (row.value / max) * 100)}%` }}
                            transition={{ duration: 0.7, delay: i * 0.04, ease: "easeOut" }}
                            className={cn("h-full rounded-full bg-gradient-to-r", ACCENT[accent].from, ACCENT[accent].to)}
                        />
                    </div>
                    {row.meta && <p className="mt-1 text-[11px] text-white/40">{row.meta}</p>}
                </li>
            ))}
        </ul>
    );
}

/** Radial gauge used for the star rating and collection-rate dials. */
export function Gauge({ value, max, label, caption, accent }: { value: number; max: number; label: string; caption: string; accent: Accent }) {
    const pctFilled = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
    const radius = 52;
    const circumference = 2 * Math.PI * radius;

    return (
        <div className="flex items-center gap-5">
            <div className="relative h-32 w-32 shrink-0">
                <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
                    <circle cx="64" cy="64" r={radius} fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth="10" />
                    <motion.circle
                        cx="64" cy="64" r={radius} fill="none" strokeWidth="10" strokeLinecap="round"
                        stroke={ACCENT[accent].stroke}
                        strokeDasharray={circumference}
                        initial={{ strokeDashoffset: circumference }}
                        animate={{ strokeDashoffset: circumference * (1 - pctFilled) }}
                        transition={{ duration: 0.9, ease: "easeOut" }}
                    />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-semibold tabular-nums text-white">{label}</span>
                </div>
            </div>
            <p className="text-sm leading-relaxed text-white/55">{caption}</p>
        </div>
    );
}

export function DataRows({ head, rows, emptyLabel = "No rows returned" }: { head: string[]; rows: ReactNode[][]; emptyLabel?: string }) {
    if (rows.length === 0) return <Empty label={emptyLabel} />;

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
                <thead>
                    <tr className="text-[11px] uppercase tracking-[0.12em] text-white/40">
                        {head.map((h) => (
                            <th key={h} className="pb-2 pr-4 font-medium last:pr-0">{h}</th>
                        ))}
                    </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                    {rows.map((cells, i) => (
                        <motion.tr
                            key={i}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ duration: 0.3, delay: i * 0.03 }}
                            className="transition-colors hover:bg-white/5"
                        >
                            {cells.map((cell, j) => (
                                <td key={j} className="py-2.5 pr-4 text-white/80 last:pr-0">{cell}</td>
                            ))}
                        </motion.tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export function Empty({ label }: { label: string }) {
    return (
        <div className="rounded-xl border border-dashed border-white/10 px-4 py-8 text-center text-sm text-white/35">
            {label}
        </div>
    );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
    return (
        <div className="space-y-3">
            {Array.from({ length: rows }).map((_, i) => (
                <div key={i} className="h-9 animate-pulse rounded-lg bg-white/[0.06]" />
            ))}
        </div>
    );
}
