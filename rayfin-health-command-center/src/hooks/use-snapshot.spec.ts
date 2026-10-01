import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { useSnapshot } from "@/hooks/use-snapshot";
import { publication } from "@/test/snapshot-fixtures";

const executeSnapshot = vi.fn();
const executeRuns = vi.fn();
const mockGetClient = vi.fn();

function query(execute: Mock) {
    const builder = { select: vi.fn(), where: vi.fn(), orderBy: vi.fn(), first: vi.fn(), execute };
    for (const method of [builder.select, builder.where, builder.orderBy, builder.first]) method.mockReturnValue(builder);
    return builder;
}
const published = query(executeSnapshot);
const runs = query(executeRuns);

vi.mock("@/lib/rayfin-client", () => ({ getRayfinClient: () => mockGetClient() }));

describe("published snapshot reads", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        executeSnapshot.mockResolvedValue([publication(1)]);
        executeRuns.mockResolvedValue([]);
        mockGetClient.mockReturnValue({ data: { PublishedSnapshot: published, SyncRun: runs } });
    });

    it("does not access the database before Fabric SSO, then reads all lenses from one generation", async () => {
        const { result, rerender } = renderHook(({ enabled }) => useSnapshot(enabled), { initialProps: { enabled: false } });
        expect(mockGetClient).not.toHaveBeenCalled();
        rerender({ enabled: true });
        await waitFor(() => expect(result.current.snapshot.version).toBe(1));
        expect(result.current.snapshot.kpis.filter((kpi) => kpi.unit !== "percent").every((kpi) => kpi.value === 100)).toBe(true);
        expect(new Set(result.current.snapshot.kpis.map((kpi) => kpi.lens))).toEqual(new Set(["payer", "provider", "medtech"]));
        expect(result.current.snapshot.series[0].value).toBe(10);
        expect(result.current.snapshot.worklist[0].primaryValue).toBe(1000);
        expect(executeSnapshot).toHaveBeenCalledOnce();
    });

    it("retains all previous panels and version when a reload is invalid or unavailable", async () => {
        const { result } = renderHook(() => useSnapshot(true));
        await waitFor(() => expect(result.current.isLoading).toBe(false));
        const original = result.current.snapshot;
        executeSnapshot.mockResolvedValueOnce([{ ...publication(2), payloadJson: '{"schemaVersion":1,"kpis":[],"series":[],"worklist":[]}' }]);
        await act(() => result.current.reload());
        expect(result.current.error).toBeInstanceOf(Error);
        expect(result.current.snapshot).toEqual(original);
        executeSnapshot.mockRejectedValueOnce(new Error("Database unavailable"));
        await act(() => result.current.reload());
        expect(result.current.snapshot).toEqual(original);
    });

    it("shows a newer failed attempt without moving the publication capture time", async () => {
        executeSnapshot.mockResolvedValue([{ ...publication(1), capturedAt: "2026-09-29T12:00:00.000" }]);
        executeRuns.mockResolvedValue([{ id: "failed", startedAt: "2026-09-30T12:00:00Z", completedAt: "2026-09-30T12:01:00Z", status: "failed", kpiRows: 0, seriesRows: 0, worklistRows: 0, sources: "popHealthGold,imagingGold", error: "Source query failed" }]);
        const { result } = renderHook(() => useSnapshot(true));
        await waitFor(() => expect(result.current.snapshot.lastRun?.status).toBe("failed"));
        expect(result.current.snapshot.capturedAt).toBe("2026-09-29T12:00:00.000Z");
        expect(result.current.snapshot.version).toBe(1);
        expect(result.current.snapshot.kpis.every((kpi) => kpi.capturedAt === result.current.snapshot.capturedAt)).toBe(true);
    });

    it("does not let a slower stale reload overwrite a newer publication", async () => {
        const { result } = renderHook(() => useSnapshot(true));
        await waitFor(() => expect(result.current.isLoading).toBe(false));
        let resolveOlder!: (value: ReturnType<typeof publication>[]) => void;
        executeSnapshot.mockReturnValueOnce(new Promise((resolve) => { resolveOlder = resolve; }));
        let older!: Promise<void>;
        act(() => { older = result.current.reload(); });
        executeSnapshot.mockResolvedValueOnce([publication(3)]);
        await act(() => result.current.reload());
        await act(async () => { resolveOlder([publication(2)]); await older; });
        expect(result.current.snapshot.version).toBe(3);
        expect(result.current.snapshot.series[0].value).toBe(30);
        expect(result.current.snapshot.worklist[0].primaryValue).toBe(3000);
    });

    it("does not repopulate protected data after authentication is lost during a read", async () => {
        let resolve!: (value: ReturnType<typeof publication>[]) => void;
        executeSnapshot.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
        const { result, rerender } = renderHook(({ enabled }) => useSnapshot(enabled), { initialProps: { enabled: true } });
        rerender({ enabled: false });
        await act(async () => { resolve([publication(1)]); });
        expect(result.current.snapshot.version).toBe(0);
        expect(result.current.snapshot.kpis).toEqual([]);
    });
});
