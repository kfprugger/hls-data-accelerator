//-----------------------------------------------------------------------
// BrakeKat Health Command Center
//
// One surface, three lenses — Payer, Provider, MedTech — all served by
// Direct Lake semantic models over the med-0906 Gold lakehouses.
//-----------------------------------------------------------------------

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, HeartPulse, RefreshCw, ScanLine, Wallet } from "lucide-react";

import { useSemanticModelQuery, clearQueryCache } from "@/hooks/use-semantic-model-query";
import {
    CARE_GAPS, HEAVIEST_STUDIES, HIGH_COST_MEMBERS, MEDTECH_KPIS, MODALITY_MIX,
    PAYER_KPIS, PAYER_SEGMENTS, PROVIDER_KPIS, READMISSION_TIERS, STAR_MEASURES,
} from "@/lib/queries";
import { count, firstRow, maskId, maskName, money, num, pct, rowsOf } from "@/lib/format";
import { ACCENT, type Accent } from "@/components/accent";
import { DataRows, Gauge, Kpi, Panel, RankedBars, Skeleton } from "@/components/visuals";
import { cn } from "@/lib/utils";

const LENSES = [
    { id: "payer" as const, label: "Payer", icon: Wallet, blurb: "Claims economics, segment margin and high-cost exposure" },
    { id: "provider" as const, label: "Provider", icon: HeartPulse, blurb: "Care gaps, readmission risk and Stars performance" },
    { id: "medtech" as const, label: "MedTech", icon: ScanLine, blurb: "Imaging fleet throughput and DICOM volume" },
];

export default function App() {
    const [lens, setLens] = useState<Accent>("payer");

    const payerKpis = useSemanticModelQuery(PAYER_KPIS);
    const payerSegments = useSemanticModelQuery(PAYER_SEGMENTS);
    const highCost = useSemanticModelQuery(HIGH_COST_MEMBERS);
    const providerKpis = useSemanticModelQuery(PROVIDER_KPIS);
    const careGaps = useSemanticModelQuery(CARE_GAPS);
    const readmission = useSemanticModelQuery(READMISSION_TIERS);
    const stars = useSemanticModelQuery(STAR_MEASURES);
    const medtechKpis = useSemanticModelQuery(MEDTECH_KPIS);
    const modality = useSemanticModelQuery(MODALITY_MIX);
    const heaviest = useSemanticModelQuery(HEAVIEST_STUDIES);

    const all = [payerKpis, payerSegments, highCost, providerKpis, careGaps, readmission, stars, medtechKpis, modality, heaviest];
    const isLoading = all.some((r) => r.isLoading);
    const failed = all.filter((r) => r.error).length;

    // The Gold models are reached through the Fabric host's postMessage proxy, so
    // every query fails when the app is opened outside the portal. Showing zeroes
    // in that state reads as "the business has no claims" — say the real reason.
    const disconnected = !isLoading && failed === all.length;

    /** Blanks every formatted figure while the Fabric data plane is unreachable,
     *  so a disconnected app never renders a plausible-looking zero. */
    const show = (text: string) => (disconnected ? "—" : text);

    const refreshAll = () => {
        clearQueryCache();
        for (const r of all) void r.refetch();
    };

    const payer = firstRow(payerKpis.data);
    const provider = firstRow(providerKpis.data);
    const medtech = firstRow(medtechKpis.data);

    const segmentRows = rowsOf(payerSegments.data);
    const gapRows = rowsOf(careGaps.data);
    const tierRows = rowsOf(readmission.data);
    const starRows = rowsOf(stars.data);
    const modalityRows = rowsOf(modality.data);
    const heaviestRows = rowsOf(heaviest.data);
    const highCostRows = rowsOf(highCost.data);

    const headline = useMemo(() => {
        if (disconnected) return { value: "—", label: "Waiting for Fabric", sub: "Open this app inside the workspace" };
        if (lens === "payer") return { value: money(payer.leakage), label: "Revenue leakage in play", sub: `${count(payer.totalClaims)} claims adjudicated` };
        if (lens === "provider") return { value: count(provider.openGaps), label: "Open care gaps", sub: `${count(provider.patientsMeasured)} patients measured` };
        return { value: count(medtech.files), label: "DICOM instances indexed", sub: `${count(medtech.studies)} studies across the fleet` };
    }, [disconnected, lens, payer, provider, medtech]);

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
                            Payer economics, provider quality and imaging operations read from the same Direct Lake
                            models over <span className="text-white/75">healthcare1_reporting_gold</span>. No copies, no
                            extracts — the Gold lakehouse is the app.
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
                        {failed > 0 && !disconnected && <span className="text-amber-300/80">{failed} query error(s)</span>}
                        <button
                            onClick={refreshAll}
                            className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 transition-colors hover:border-white/25 hover:text-white/80"
                        >
                            <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} />
                            {isLoading ? "Refreshing" : "Refresh"}
                        </button>
                    </div>
                </nav>

                <p className="mt-3 text-sm text-white/40">{LENSES.find((l) => l.id === lens)?.blurb}</p>

                {disconnected && (
                    <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="mt-5 flex flex-wrap items-center gap-3 rounded-xl border border-amber-300/25 bg-amber-300/[0.07] px-4 py-3 text-sm text-amber-100/90"
                    >
                        <Activity className="h-4 w-4 shrink-0" />
                        <span>
                            Not connected to Fabric. The Gold semantic models are reached through the workspace host,
                            so open <span className="font-medium">rayfin-health-command-center</span> from the med-0906
                            workspace to load live data. Figures below stay blank until then.
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
                        {lens === "payer" && (
                            <>
                                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                                    <Kpi accent="payer" index={0} label="Total paid" value={show(money(payer.totalPaid))} caption={show(`of ${money(payer.totalBilled)} billed`)} />
                                    <Kpi accent="payer" index={1} label="Collection rate" value={show(pct(payer.collectionRate))} caption={show(`denial rate ${pct(payer.denialRate)}`)} />
                                    <Kpi accent="payer" index={2} label="PMPM" value={show(money(payer.pmpm))} caption="per member per month" />
                                    <Kpi accent="payer" index={3} label="Revenue at risk" value={show(money(payer.revenueAtRisk))} caption={show(`${count(payer.highCostMembers)} high-cost members`)} />
                                </div>

                                <div className="grid gap-5 lg:grid-cols-2">
                                    <Panel accent="payer" title="Paid by line of business" subtitle="Segment measures from the Gold claims star schema">
                                        {payerSegments.isLoading ? <Skeleton /> : (
                                            <RankedBars
                                                accent="payer"
                                                rows={segmentRows.map((r) => ({
                                                    label: String(r.segment),
                                                    value: num(r.paid),
                                                    display: money(r.paid),
                                                    meta: `collection ${pct(r.collection)} · quality ${pct(r.quality)} · RAF ${num(r.raf).toFixed(2)}`,
                                                }))}
                                            />
                                        )}
                                    </Panel>

                                    <Panel accent="payer" title="Highest-cost members" subtitle="agg_high_cost_claimants · identifiers masked">
                                        {highCost.isLoading ? <Skeleton rows={5} /> : (
                                            <DataRows
                                                head={["Member", "Payer", "Paid", "Claims", "Stop-loss"]}
                                                rows={highCostRows.map((r) => [
                                                    <span className="font-mono text-xs">{maskId(r.member)}</span>,
                                                    String(r.payer ?? "—"),
                                                    <span className="tabular-nums">{money(r.paid)}</span>,
                                                    <span className="tabular-nums">{count(r.claims)}</span>,
                                                    r.stopLoss ? <span className="rounded-md bg-sky-400/15 px-2 py-0.5 text-xs text-sky-300">Yes</span> : <span className="text-white/35">No</span>,
                                                ])}
                                            />
                                        )}
                                    </Panel>
                                </div>
                            </>
                        )}

                        {lens === "provider" && (
                            <>
                                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                                    <Kpi accent="provider" index={0} label="Open care gaps" value={show(count(provider.openGaps))} caption="actionable outreach list" />
                                    <Kpi accent="provider" index={1} label="Quality rate" value={show(pct(provider.qualityRate))} caption={show(`${count(provider.patientsMeasured)} patients measured`)} />
                                    <Kpi accent="provider" index={2} label="Avg readmission risk" value={show(pct(provider.avgReadmit))} caption={show(`ALOS ${num(provider.alos).toFixed(1)} days`)} />
                                    <Kpi accent="provider" index={3} label="Average RAF" value={show(num(provider.avgRaf).toFixed(3))} caption="risk-adjusted acuity" />
                                </div>

                                <div className="grid gap-5 lg:grid-cols-3">
                                    <Panel accent="provider" title="Star rating" subtitle="Weighted CMS Stars across measured domains" className="lg:col-span-1">
                                        <Gauge
                                            accent="provider"
                                            value={num(provider.stars)}
                                            max={5}
                                            label={show(num(provider.stars).toFixed(1))}
                                            caption={disconnected ? "Open inside Fabric to load Stars performance." : `${count(provider.starOpp)} points of improvement opportunity remain before the next Stars threshold.`}
                                        />
                                    </Panel>

                                    <Panel accent="provider" title="Care gaps by measure" subtitle="care_gaps · Gold quality layer" className="lg:col-span-2">
                                        {careGaps.isLoading ? <Skeleton rows={5} /> : (
                                            <RankedBars
                                                accent="provider"
                                                rows={gapRows.map((r) => ({
                                                    label: String(r.gap_type ?? "Unknown"),
                                                    value: num(r.gaps),
                                                    display: count(r.gaps),
                                                }))}
                                            />
                                        )}
                                    </Panel>
                                </div>

                                <div className="grid gap-5 lg:grid-cols-2">
                                    <Panel accent="provider" title="Readmission risk tiers" subtitle="readmission_risk_scores">
                                        {readmission.isLoading ? <Skeleton /> : (
                                            <DataRows
                                                head={["Tier", "Encounters", "Avg risk"]}
                                                rows={tierRows.map((r) => [
                                                    String(r.risk_tier ?? "—"),
                                                    <span className="tabular-nums">{count(r.encounters)}</span>,
                                                    <span className="tabular-nums">{pct(r.avgRisk)}</span>,
                                                ])}
                                            />
                                        )}
                                    </Panel>

                                    <Panel accent="provider" title="Weakest Stars measures" subtitle="star_rating_detail · lowest rated first">
                                        {stars.isLoading ? <Skeleton /> : (
                                            <DataRows
                                                head={["Measure", "Rating"]}
                                                rows={starRows.map((r) => [
                                                    String(r.measure_name ?? "—"),
                                                    <span className="tabular-nums">{num(r.rating).toFixed(1)} ★</span>,
                                                ])}
                                            />
                                        )}
                                    </Panel>
                                </div>
                            </>
                        )}

                        {lens === "medtech" && (
                            <>
                                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                                    <Kpi accent="medtech" index={0} label="Imaging studies" value={show(count(medtech.studies))} caption={show(`${count(medtech.patients)} distinct patients`)} />
                                    <Kpi accent="medtech" index={1} label="DICOM instances" value={show(count(medtech.files))} caption={show(`${num(medtech.perStudy).toFixed(0)} per study`)} />
                                    <Kpi accent="medtech" index={2} label="Studies per patient" value={show(num(medtech.perPatient).toFixed(2))} caption="fleet utilization" />
                                    <Kpi accent="medtech" index={3} label="Average patient age" value={show(num(medtech.avgAge).toFixed(1))} caption="imaged cohort" />
                                </div>

                                <div className="grid gap-5 lg:grid-cols-2">
                                    <Panel accent="medtech" title="Modality mix" subtitle="ImagingStudy · Gold imaging projections">
                                        {modality.isLoading ? <Skeleton rows={4} /> : (
                                            <RankedBars
                                                accent="medtech"
                                                rows={modalityRows.map((r) => ({
                                                    label: `${r.ModalityName ?? r.Modality}`,
                                                    value: num(r.studies),
                                                    display: count(r.studies),
                                                    meta: `${count(r.files)} instances · ${count(r.patients)} patients`,
                                                }))}
                                            />
                                        )}
                                    </Panel>

                                    <Panel accent="medtech" title="Heaviest acquisitions" subtitle="Highest instance counts · names masked">
                                        {heaviest.isLoading ? <Skeleton rows={5} /> : (
                                            <DataRows
                                                head={["Patient", "Age band", "Studies", "Instances"]}
                                                rows={heaviestRows.map((r) => [
                                                    <span className="font-mono text-xs">{maskName(r.FullName)}</span>,
                                                    String(r.AgeRange ?? "—"),
                                                    <span className="tabular-nums">{count(r.studies)}</span>,
                                                    <span className="tabular-nums">{count(r.files)}</span>,
                                                ])}
                                            />
                                        )}
                                    </Panel>
                                </div>
                            </>
                        )}
                    </motion.div>
                </AnimatePresence>

                <footer className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-white/5 pt-5 text-xs text-white/35">
                    <span>Direct Lake · Population Health &amp; Quality Semantic Model</span>
                    <span>Direct Lake · ImagingReport</span>
                    <span>Workspace med-0906 · healthcare1_reporting_gold</span>
                    <span className="ml-auto">Synthetic demonstration data — identifiers masked</span>
                </footer>
            </div>
        </div>
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
