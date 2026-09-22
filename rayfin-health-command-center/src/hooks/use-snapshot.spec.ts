import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { useSnapshot } from "@/hooks/use-snapshot";

const executeKpis = vi.fn();
const executeSeries = vi.fn();
const executeWorklist = vi.fn();
const executeRuns = vi.fn();
const mockGetClient = vi.fn();

function query(execute: Mock) {
    const builder = {
        select: vi.fn(),
        orderBy: vi.fn(),
        first: vi.fn(),
        execute,
    };
    builder.select.mockReturnValue(builder);
    builder.orderBy.mockReturnValue(builder);
    builder.first.mockReturnValue(builder);
    return builder;
}

const kpis = query(executeKpis);
const series = query(executeSeries);
const worklist = query(executeWorklist);
const runs = query(executeRuns);

vi.mock("@/lib/rayfin-client", () => ({
    getRayfinClient: () => mockGetClient(),
}));

describe("useSnapshot authentication gate", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        executeKpis.mockResolvedValue([]);
        executeSeries.mockResolvedValue([]);
        executeWorklist.mockResolvedValue([]);
        executeRuns.mockResolvedValue([]);
        mockGetClient.mockReturnValue({
            data: {
                KpiSnapshot: kpis,
                SeriesPoint: series,
                WorklistRow: worklist,
                SyncRun: runs,
            },
        });
    });

    it("does not call the authenticated database before Fabric SSO completes", () => {
        const { result } = renderHook(() => useSnapshot(false));

        expect(result.current.isLoading).toBe(false);
        expect(mockGetClient).not.toHaveBeenCalled();
        expect(executeKpis).not.toHaveBeenCalled();
    });

    it("loads once when authentication changes from false to true", async () => {
        const { result, rerender } = renderHook(
            ({ enabled }) => useSnapshot(enabled),
            { initialProps: { enabled: false } },
        );

        expect(mockGetClient).not.toHaveBeenCalled();
        rerender({ enabled: true });

        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(mockGetClient).toHaveBeenCalledOnce();
        expect(executeKpis).toHaveBeenCalledOnce();
        expect(executeSeries).toHaveBeenCalledOnce();
        expect(executeWorklist).toHaveBeenCalledOnce();
        expect(executeRuns).toHaveBeenCalledOnce();
        expect(result.current.error).toBeUndefined();
    });
});
