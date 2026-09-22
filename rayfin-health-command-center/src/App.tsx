//-----------------------------------------------------------------------
// BrakeKat Health Command Center
//
// One surface, three lenses — Payer, Provider, MedTech — rendered from the
// app's own database. The database is filled by an in-app sync that reads the
// Direct Lake semantic models over the med-0906 Gold lakehouses.
//-----------------------------------------------------------------------

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, Database, HeartPulse, RefreshCw, ScanLine, Wallet } from "lucide-react";

import { useAuth } from "@/hooks/auth.context";
import { formatStored, useSnapshot, type SeriesRecord, type WorklistRecord } from "@/hooks/use-snapshot";
import { syncFromGold } from "@/lib/sync-gold";
import { ACCENT, type Accent } from "@/components/accent";
import { DataRows, Gauge, Kpi, Panel, RankedBars, Skeleton } from "@/components/visuals";
import { cn } from "@/lib/utils";

const LENSES = [
    { id: "payer" as const, label: "Payer", icon: Wallet, blurb: "Claims economics, segment margin and high-cost exposure" },
    { id: "provider" as const, label: "Provider", icon: HeartPulse, blurb: "Care gaps, readmission risk and Stars performance" },
    { id: "medtech" as const, label: "MedTech", icon: ScanLine, blurb: "Imaging fleet throughput and DICOM volume" },
];

const HEADLINE: Record<Accent, { metric: string; label: string }> = {
    payer: { metric: "leakage", label: "Revenue leakage in play" },
    provider: { metric: "openGaps", label: "Open care gaps" },
    medtech: { metric: "files", label: "DICOM instances indexed" },
};

export default function App() {
    const [lens, setLens] = useState<Accent>("payer");
    const [syncing, setSyncing] = useState(false);
    const [syncError, setSyncError] = useState<string | undefined>();
    const autoSyncTried = useRef(false);
    const { isAuthenticated, isLoading: authLoading, error: authError } = useAuth();
    const { snapshot, isLoading: snapshotLoading, error, reload } = useSnapshot(isAuthenticated);
    const { kpis, series, worklist, lastRun } = snapshot;

    const isLoading = authLoading || snapshotLoading;
    const empty = isAuthenticated && !snapshotLoading && kpis.length === 0;

    const runSync = useCallback(async () => {
        if (!isAuthenticated) {
            setSyncError("Fabric sign-in has not completed. Open the app from the med-0906 workspace.");
            return;
        }
        setSyncing(true);
        setSyncError(undefined);
        try {
            await syncFromGold();
            await reload();
        } catch (err) {
            setSyncError(err instanceof Error ? err.message : String(err));
        } finally {
            setSyncing(false);
        }
    }, [isAuthenticated, reload]);

    // First run against a fresh database: fill it from Gold without making an
    // operator find the button. Only attempted once per session, and only when
    // the database read itself succeeded.
    useEffect(() => {
        if (autoSyncTried.current || authLoading || !isAuthenticated || snapshotLoading || error || !empty || syncing) return;
        autoSyncTried.current = true;
        void runSync();
    }, [authLoading, isAuthenticated, snapshotLoading, error, empty, syncing, runSync]);

    const kpisFor = useCallback(
        (which: Accent) => kpis.filter((k) => k.lens === which).sort((a, b) => a.rank - b.rank),
        [kpis],
    );
    const seriesFor = useCallback(
        (which: Accent, name: string) => series.filter((s) => s.lens === which && s.series === name).sort((a, b) => a.rank - b.rank),
        [series],
    );
    const worklistFor = useCallback(
        (kind: string) => worklist.filter((w) => w.kind === kind).sort((a, b) => a.rank - b.rank),
        [worklist],
    );

    const headline = useMemo(() => {
        const spec = HEADLINE[lens];
        const record = kpis.find((k) => k.lens === lens && k.metricKey === spec.metric);
        const caption = record?.caption ?? (empty ? "Database is empty — run a sync" : "—");
        return { value: record ? formatStored(record.value, record.unit) : "—", label: spec.label, sub: caption };
    }, [lens, kpis, empty]);

    const stars = kpis.find((k) => k.lens === "provider" && k.metricKey === "stars");
    const capturedAt = lastRun?.completedAt ?? lastRun?.startedAt;

    return (
        <div className="min-h-screen bg-[#070b16] text-white">
            <BackdropGlow accent={lens} />

            <div className="relative mx-auto w-full max-w-7xl px-6 py-8">
                <header className="flex flex-wrap items-start justify-between gap-6">
                    <div>
                        <p className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.3em] text-white/40">
                            <Activity className="h-3.5 w-3.5" /> BrakeKat Health Command Center
                        </p>
                        <h1 className="mt-3 text-4xl font-semibold tracking-tight">
                            <span className="bg-gradient-to-r from-white via-white to-white/50 bg-clip-text text-transparent">
                                One Gold layer.
                            </span>{" "}
                            <span className={cn("bg-gradient-to-r bg-clip-text text-transparent", ACCENT[lens].from, ACCENT[lens].to)}>
                                Three businesses.
                            </span>
                        </h1>
                        <p className="mt-2 max-w-2xl text-sm text-white/50">
                            Payer economics, provider quality and imaging operations are served from this app's own
                            database, refreshed from the Direct Lake models over{" "}
                            <span className="text-white/75">healthcare1_reporting_gold</span>.
                        </p>
                    </div>

                    <motion.div
                        key={headline.value}
                        initial={{ opacity: 0, scale: 0.96 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ duration: 0.4 }}
                        className={cn(
                            "rounded-2xl border border-white/10 bg-white/[0.05] px-6 py-4 text-right backdrop-blur-xl",
                            ACCENT[lens].glow,
                        )}
                    >
                        <p className="text-[11px] uppercase tracking-[0.16em] text-white/40">{headline.label}</p>
                        <p className="mt-1 text-4xl font-semibold tabular-nums">{headline.value}</p>
                        <p className={cn("mt-1 text-xs", ACCENT[lens].text)}>{headline.sub}</p>
                    </motion.div>
                </header>

                <nav className="mt-8 flex flex-wrap items-center gap-2">
                    {LENSES.map((item) => {
                        const Icon = item.icon;
                        const active = lens === item.id;
                        return (
                            <button
                                key={item.id}
                                onClick={() => setLens(item.id)}
                                className={cn(
                                    "group relative flex items-center gap-2.5 rounded-xl border px-4 py-2.5 text-sm transition-all",
                                    active
                                        ? "border-white/20 bg-white/10 text-white"
                                        : "border-white/5 bg-white/[0.02] text-white/55 hover:border-white/15 hover:text-white/85",
                                )}
                            >
                                <Icon className={cn("h-4 w-4", active && ACCENT[item.id].text)} />
                                <span className="font-medium">{item.label}</span>
                                {active && (
                                    <motion.span
                                        layoutId="lens-underline"
                                        className={cn("absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-gradient-to-r", ACCENT[item.id].from, ACCENT[item.id].to)}
                                    />
                                )}
                            </button>
                        );
                    })}

                    <div className="ml-auto flex items-center gap-3 text-xs text-white/40">
                        <span className="flex items-center gap-1.5">
                            <Database className="h-3.5 w-3.5" />
                            {capturedAt ? `synced ${new Date(capturedAt).toLocaleString()}` : "never synced"}
                        </span>
                        <button
                            onClick={runSync}
                            disabled={syncing || authLoading || !isAuthenticated}
                            className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 transition-colors hover:border-white/25 hover:text-white/80 disabled:opacity-50"
                        >
                            <RefreshCw className={cn("h-3.5 w-3.5", syncing && "animate-spin")} />
                            {syncing ? "Syncing from Gold" : "Sync from Gold"}
                        </button>
                    </div>
                </nav>

                <p className="mt-3 text-sm text-white/40">{LENSES.find((l) => l.id === lens)?.blurb}</p>

                {!authLoading && (authError || !isAuthenticated || error || syncError || empty) && (
                    <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="mt-5 flex flex-wrap items-start gap-3 rounded-xl border border-amber-300/25 bg-amber-300/[0.07] px-4 py-3 text-sm text-amber-100/90"
                    >
                        <Activity className="mt-0.5 h-4 w-4 shrink-0" />
                        <span>
                            {authError
                                ? `Fabric sign-in failed: ${authError.message}`
                                : !isAuthenticated
                                    ? "Open this app from the med-0906 workspace so Fabric can sign you in and connect the database."
                                    : error
                                        ? `The app database could not be read (${error.message}).`
                                        : syncError
                                            ? `Sync failed: ${syncError}`
                                            : "The app database has no snapshot yet. Syncing from Gold will load the Direct Lake models into it."}
                        </span>
                    </motion.div>
                )}

                <AnimatePresence mode="wait">
                    <motion.div
                        key={lens}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={{ duration: 0.28 }}
                        className="mt-6 space-y-5"
                    >
                        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                            {isLoading
                                ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-28 animate-pulse rounded-2xl bg-white/[0.06]" />)
                                : kpisFor(lens).slice(0, 4).map((k, i) => (
                                    <Kpi
                                        key={k.id}
                                        accent={lens}
                                        index={i}
                                        label={k.label}
                                        value={formatStored(k.value, k.unit)}
                                        caption={k.caption}
                                    />
                                ))}
                        </div>

                        {lens === "payer" && (
                            <div className="grid gap-5 lg:grid-cols-2">
                                <Panel accent="payer" title="Paid by line of business" subtitle="Segment measures captured from the Gold claims star schema">
                                    {isLoading ? <Skeleton /> : <Bars rows={seriesFor("payer", "payerSegment")} accent="payer" />}
                                </Panel>

                                <Panel accent="payer" title="Highest-cost members" subtitle="agg_high_cost_claimants · identifiers masked at sync time">
                                    {isLoading ? <Skeleton rows={5} /> : (
                                        <DataRows
                                            head={["Member", "Payer", "Paid", "Claims", "Stop-loss"]}
                                            rows={worklistFor("highCostMember").map((r) => [
                                                <span className="font-mono text-xs">{r.subject}</span>,
                                                r.segment ?? "—",
                                                <span className="tabular-nums">{formatStored(r.primaryValue, r.primaryUnit)}</span>,
                                                <span className="tabular-nums">{formatStored(r.secondaryValue ?? 0, r.secondaryUnit ?? "count")}</span>,
                                                r.flagged
                                                    ? <span className="rounded-md bg-sky-400/15 px-2 py-0.5 text-xs text-sky-300">Yes</span>
                                                    : <span className="text-white/35">No</span>,
                                            ])}
                                        />
                                    )}
                                </Panel>
                            </div>
                        )}

                        {lens === "provider" && (
                            <>
                                <div className="grid gap-5 lg:grid-cols-3">
                                    <Panel accent="provider" title="Star rating" subtitle="Weighted CMS Stars across measured domains">
                                        <Gauge
                                            accent="provider"
                                            value={stars?.value ?? 0}
                                            max={5}
                                            label={stars ? stars.value.toFixed(1) : "—"}
                                            caption={stars?.caption ?? "Run a sync to load Stars performance."}
                                        />
                                    </Panel>

                                    <Panel accent="provider" title="Care gaps by measure" subtitle="care_gaps · Gold quality layer" className="lg:col-span-2">
                                        {isLoading ? <Skeleton rows={5} /> : <Bars rows={seriesFor("provider", "careGap")} accent="provider" />}
                                    </Panel>
                                </div>

                                <div className="grid gap-5 lg:grid-cols-2">
                                    <Panel accent="provider" title="Readmission risk tiers" subtitle="readmission_risk_scores">
                                        {isLoading ? <Skeleton /> : (
                                            <DataRows
                                                head={["Tier", "Encounters", "Detail"]}
                                                rows={seriesFor("provider", "riskTier").map((r) => [
                                                    r.label,
                                                    <span className="tabular-nums">{formatStored(r.value, r.unit)}</span>,
                                                    <span className="text-white/50">{r.detail ?? "—"}</span>,
                                                ])}
                                            />
                                        )}
                                    </Panel>

                                    <Panel accent="provider" title="Weakest Stars measures" subtitle="star_rating_detail · lowest rated first">
                                        {isLoading ? <Skeleton /> : (
                                            <DataRows
                                                head={["Measure", "Rating"]}
                                                rows={seriesFor("provider", "starMeasure").map((r) => [
                                                    r.label,
                                                    <span className="tabular-nums">{r.value.toFixed(1)} ★</span>,
                                                ])}
                                            />
                                        )}
                                    </Panel>
                                </div>
                            </>
                        )}

                        {lens === "medtech" && (
                            <div className="grid gap-5 lg:grid-cols-2">
                                <Panel accent="medtech" title="Modality mix" subtitle="ImagingStudy · Gold imaging projections">
                                    {isLoading ? <Skeleton rows={4} /> : <Bars rows={seriesFor("medtech", "modality")} accent="medtech" />}
                                </Panel>

                                <Panel accent="medtech" title="Heaviest acquisitions" subtitle="Highest instance counts · names masked at sync time">
                                    {isLoading ? <Skeleton rows={5} /> : (
                                        <DataRows
                                            head={["Patient", "Age band", "Instances", "Studies"]}
                                            rows={worklistFor("heavyAcquisition").map((r: WorklistRecord) => [
                                                <span className="font-mono text-xs">{r.subject}</span>,
                                                r.segment ?? "—",
                                                <span className="tabular-nums">{formatStored(r.primaryValue, r.primaryUnit)}</span>,
                                                <span className="tabular-nums">{formatStored(r.secondaryValue ?? 0, r.secondaryUnit ?? "count")}</span>,
                                            ])}
                                        />
                                    )}
                                </Panel>
                            </div>
                        )}
                    </motion.div>
                </AnimatePresence>

                <footer className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-white/5 pt-5 text-xs text-white/35">
                    <span>App database · KpiSnapshot · SeriesPoint · WorklistRow · SyncRun</span>
                    <span>Source · Direct Lake over healthcare1_reporting_gold</span>
                    {lastRun && <span>Last run wrote {lastRun.kpiRows + lastRun.seriesRows + lastRun.worklistRows} rows</span>}
                    <span className="ml-auto">Synthetic demonstration data — identifiers masked</span>
                </footer>
            </div>
        </div>
    );
}

function Bars({ rows, accent }: { rows: SeriesRecord[]; accent: Accent }) {
    return (
        <RankedBars
            accent={accent}
            rows={rows.map((r) => ({
                label: r.label,
                value: r.value,
                display: formatStored(r.value, r.unit),
                meta: r.detail,
            }))}
            emptyLabel="No snapshot rows — run a sync"
        />
    );
}

function BackdropGlow({ accent }: { accent: Accent }) {
    return (
        <div aria-hidden className="pointer-events-none fixed inset-0 overflow-hidden">
            <div className="absolute left-1/2 top-0 h-[40rem] w-[70rem] -translate-x-1/2 -translate-y-1/3 rounded-full bg-[radial-gradient(ellipse_at_center,rgba(56,189,248,0.10),transparent_65%)]" />
            <motion.div
                key={accent}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6 }}
                className={cn(
                    "absolute -bottom-40 right-0 h-[32rem] w-[32rem] rounded-full bg-gradient-to-br opacity-[0.12] blur-3xl",
                    ACCENT[accent].from, ACCENT[accent].to,
                )}
            />
        </div>
    );
}
