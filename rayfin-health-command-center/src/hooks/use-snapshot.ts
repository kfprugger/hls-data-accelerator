//-----------------------------------------------------------------------
// All three lenses derive from one validated, immutable publication read.
// Sync attempts are separate provenance, never the source of capture time.
//-----------------------------------------------------------------------

import { useCallback, useEffect, useRef, useState } from "react";

import { getRayfinClient } from "@/lib/rayfin-client";
import {
    parseSnapshotPayload, type KpiSeed, type SeriesSeed, type WorklistSeed,
} from "../../rayfin/functions/src/snapshot-payload";

export type KpiRecord = KpiSeed & { id: string; capturedAt: string };
export type SeriesRecord = SeriesSeed & { id: string };
export type WorklistRecord = WorklistSeed & { id: string };

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
    version: number;
    capturedAt?: string;
    publisherId?: string;
    sources?: string;
    syncRunId?: string;
    lastRun?: SyncRecord;
}

export interface SnapshotState {
    snapshot: Snapshot;
    isLoading: boolean;
    error?: Error;
    reload: () => Promise<void>;
}

export const PUBLISHED_SNAPSHOT_ID = "00000000-0000-0000-0000-000000000001";
const EMPTY: Snapshot = { kpis: [], series: [], worklist: [], version: 0 };

function dateString(value: string | Date): string {
    // SQL stores SYSUTCDATETIME() in datetime2; DAB may omit its UTC suffix.
    const utc = typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value) ? `${value}Z` : value;
    const date = new Date(utc);
    if (!Number.isFinite(date.getTime())) throw new Error("The database returned an invalid capture date.");
    return date.toISOString();
}

/** Reads only; neither mounting nor reloading can seed an empty database. */
export function useSnapshot(enabled: boolean): SnapshotState {
    const [snapshot, setSnapshot] = useState<Snapshot>(EMPTY);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<Error | undefined>();
    const request = useRef(0);

    const reload = useCallback(async () => {
        if (!enabled) return;
        const current = ++request.current;
        setIsLoading(true);
        setError(undefined);
        try {
            const client = getRayfinClient();
            const rows = await client.data.PublishedSnapshot
                .select(["id", "version", "payloadJson", "capturedAt", "syncRunId", "publisherId", "sources"])
                .where({ id: PUBLISHED_SNAPSHOT_ID }).first(1).execute();
            const row = rows[0];
            let next = EMPTY;
            if (row) {
                if (!Number.isInteger(row.version) || row.version < 1) throw new Error("The database returned an invalid publication version.");
                const payload = parseSnapshotPayload(row.payloadJson);
                const capturedAt = dateString(row.capturedAt);
                next = {
                    version: row.version, capturedAt, publisherId: row.publisherId,
                    sources: row.sources, syncRunId: row.syncRunId,
                    kpis: payload.kpis.map((kpi) => ({ ...kpi, id: `${row.version}/${kpi.lens}/${kpi.metricKey}`, capturedAt })),
                    series: payload.series.map((series) => ({ ...series, id: `${row.version}/${series.series}/${series.rank}` })),
                    worklist: payload.worklist.map((worklist) => ({ ...worklist, id: `${row.version}/${worklist.kind}/${worklist.rank}` })),
                };
            }
            if (request.current !== current) return;
            setSnapshot((previous) => previous.version > next.version ? previous : next);

            // A failed provenance read cannot discard a valid publication.
            const runs = await client.data.SyncRun
                .select(["id", "startedAt", "completedAt", "status", "kpiRows", "seriesRows", "worklistRows", "sources", "error"])
                .orderBy({ startedAt: "desc" }).first(1).execute();
            const run = runs[0];
            const lastRun = run ? {
                ...run, startedAt: dateString(run.startedAt),
                completedAt: run.completedAt ? dateString(run.completedAt) : undefined,
            } : undefined;
            if (request.current === current) setSnapshot((previous) => ({ ...previous, lastRun }));
        } catch (err) {
            if (request.current === current) setError(err instanceof Error ? err : new Error(String(err)));
        } finally {
            if (request.current === current) setIsLoading(false);
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
        return () => { request.current += 1; };
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
