//-----------------------------------------------------------------------
// Reads the current snapshot out of the app database.
//
// The dashboard never queries a semantic model directly; it reads the rows the
// Gold sync wrote. That keeps render cheap, gives every figure a capture time,
// and means the panels have a single, inspectable source.
//-----------------------------------------------------------------------

import { useCallback, useEffect, useState } from "react";

import { getRayfinClient } from "@/lib/rayfin-client";

export interface KpiRecord {
    id: string;
    lens: string;
    metricKey: string;
    label: string;
    value: number;
    unit: string;
    caption?: string;
    rank: number;
    sourceModel: string;
    capturedAt: string;
}

export interface SeriesRecord {
    id: string;
    lens: string;
    series: string;
    label: string;
    value: number;
    unit: string;
    detail?: string;
    rank: number;
}

export interface WorklistRecord {
    id: string;
    lens: string;
    kind: string;
    subject: string;
    segment?: string;
    primaryValue: number;
    primaryUnit: string;
    secondaryValue?: number;
    secondaryUnit?: string;
    flagged?: boolean;
    rank: number;
}

export interface SyncRecord {
    id: string;
    startedAt: string;
    completedAt?: string;
    status: string;
    kpiRows: number;
    seriesRows: number;
    worklistRows: number;
    sources: string;
    error?: string;
}

export interface Snapshot {
    kpis: KpiRecord[];
    series: SeriesRecord[];
    worklist: WorklistRecord[];
    lastRun?: SyncRecord;
}

export interface SnapshotState {
    snapshot: Snapshot;
    isLoading: boolean;
    /** Set when the database itself could not be read. */
    error?: Error;
    reload: () => Promise<void>;
}

const EMPTY: Snapshot = { kpis: [], series: [], worklist: [] };

/**
 * Loads the app-database snapshot after Fabric SSO completes. Before that
 * handoff the DAB endpoint sees an anonymous request and returns 401; the old
 * hook cached that failure forever because authentication never retriggered it.
 */
export function useSnapshot(enabled: boolean): SnapshotState {
    const [snapshot, setSnapshot] = useState<Snapshot>(EMPTY);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<Error | undefined>();

    const reload = useCallback(async () => {
        if (!enabled) return;
        setIsLoading(true);
        setError(undefined);
        try {
            const client = getRayfinClient();
            const [kpis, series, worklist, runs] = await Promise.all([
                client.data.KpiSnapshot
                    .select(["id", "lens", "metricKey", "label", "value", "unit", "caption", "rank", "sourceModel", "capturedAt"])
                    .orderBy({ rank: "asc" }).execute(),
                client.data.SeriesPoint
                    .select(["id", "lens", "series", "label", "value", "unit", "detail", "rank"])
                    .orderBy({ rank: "asc" }).execute(),
                client.data.WorklistRow
                    .select(["id", "lens", "kind", "subject", "segment", "primaryValue", "primaryUnit", "secondaryValue", "secondaryUnit", "flagged", "rank"])
                    .orderBy({ rank: "asc" }).execute(),
                client.data.SyncRun
                    .select(["id", "startedAt", "completedAt", "status", "kpiRows", "seriesRows", "worklistRows", "sources", "error"])
                    .orderBy({ startedAt: "desc" }).first(1).execute(),
            ]);
            setSnapshot({
                kpis: kpis as unknown as KpiRecord[],
                series: series as unknown as SeriesRecord[],
                worklist: worklist as unknown as WorklistRecord[],
                lastRun: (runs as unknown as SyncRecord[])[0],
            });
        } catch (err) {
            setError(err instanceof Error ? err : new Error(String(err)));
            setSnapshot(EMPTY);
        } finally {
            setIsLoading(false);
        }
    }, [enabled]);

    useEffect(() => {
        if (enabled) {
            void reload();
        } else {
            setIsLoading(false);
            setError(undefined);
            setSnapshot(EMPTY);
        }
    }, [enabled, reload]);

    return { snapshot, isLoading, error, reload };
}

/** Formats a stored value using the unit the sync recorded alongside it. */
export function formatStored(value: number, unit: string): string {
    if (unit === "money") {
        return value >= 1000
            ? `$${new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value)}`
            : `$${value.toFixed(0)}`;
    }
    if (unit === "percent") return `${(value * 100).toFixed(1)}%`;
    if (unit === "ratio") return value.toFixed(2);
    return value >= 10000
        ? new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value)
        : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}
