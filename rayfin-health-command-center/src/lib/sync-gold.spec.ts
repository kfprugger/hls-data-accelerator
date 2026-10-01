import { beforeEach, describe, expect, it, vi } from "vitest";
import { syncFromGold, SyncDeniedError, SyncConflictError } from "@/lib/sync-gold";
import { goldResults } from "@/test/snapshot-fixtures";
import { PAYER_KPIS, PROVIDER_KPIS, MEDTECH_KPIS, CARE_GAPS, HIGH_COST_MEMBERS } from "@/lib/queries";

const { access, publish, query, semanticModel, write } = vi.hoisted(() => ({
    access: vi.fn(), publish: vi.fn(), query: vi.fn(), semanticModel: vi.fn(), write: vi.fn(),
}));
vi.mock("@/lib/rayfin-client", () => ({
    getRayfinClient: () => ({
        functions: { getSyncAccess: { invoke: access }, publishSnapshot: { invoke: publish } },
        data: new Proxy({}, { get: () => ({ create: write, update: write, delete: write }) }),
    }),
}));
vi.mock("@/lib/fabric-client", () => ({ getFabricClient: () => ({ semanticModel }) }));

let results: ReturnType<typeof goldResults>;
beforeEach(() => {
    vi.clearAllMocks();
    results = goldResults();
    access.mockResolvedValue({ canSync: true, version: 7, publisherId: "synthetic-writer" });
    semanticModel.mockReturnValue({ query });
    query.mockImplementation(async (dax: string) => results.get(dax));
    publish.mockResolvedValue({ status: "published", version: 8, capturedAt: "2026-09-30T12:00:00Z", kpiRows: 14, seriesRows: 5, worklistRows: 2, publisherId: "synthetic-writer" });
});

describe("trusted sync publication", () => {
    it("denies a viewer before source queries and without any mutation", async () => {
        access.mockResolvedValue({ canSync: false, version: 7, publisherId: "synthetic-viewer" });
        await expect(syncFromGold()).rejects.toBeInstanceOf(SyncDeniedError);
        expect(query).not.toHaveBeenCalled();
        expect(publish).not.toHaveBeenCalled();
        expect(write).not.toHaveBeenCalled();
    });

    it("waits for the server decision before any source read", async () => {
        let resolve!: (value: { canSync: boolean; version: number; publisherId: string }) => void;
        access.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
        const syncing = syncFromGold();
        expect(query).not.toHaveBeenCalled();
        resolve({ canSync: true, version: 12, publisherId: "synthetic-writer" });
        await syncing;
        expect(publish.mock.calls[0][0].expectedVersion).toBe(12);
    });

    it("publishes one complete masked payload using the captured expected version", async () => {
        await expect(syncFromGold()).resolves.toMatchObject({ status: "published", version: 8 });
        expect(query).toHaveBeenCalledTimes(10);
        expect(publish).toHaveBeenCalledOnce();
        const input = publish.mock.calls[0][0];
        const payload = JSON.parse(input.payloadJson);
        expect(input.expectedVersion).toBe(7);
        expect(payload.kpis.find((kpi: { metricKey: string }) => kpi.metricKey === "totalPaid").value).toBe(1000);
        expect(payload.kpis.find((kpi: { metricKey: string }) => kpi.metricKey === "files").value).toBe(6);
        expect(payload.worklist.map((row: { subject: string }) => row.subject)).toEqual(["synt…5678", "S. P."]);
        expect(input.payloadJson).not.toContain("synthetic-member-12345678");
        expect(input.payloadJson).not.toContain("Synthetic Person");
        expect(write).not.toHaveBeenCalled();
    });

    it.each([PAYER_KPIS, PROVIDER_KPIS, MEDTECH_KPIS])("does not publish an empty required KPI result %#", async (spec) => {
        results.get(spec.query)!.table.rows = [];
        await expect(syncFromGold()).rejects.toThrow(/required KPI/);
        expect(publish).not.toHaveBeenCalled();
    });

    it.each([null, undefined, "", " ", NaN, Infinity, true])("does not turn invalid numeric value %s into zero", async (value) => {
        results.get(PAYER_KPIS.query)!.table.rows[0][0] = value;
        await expect(syncFromGold()).rejects.toThrow(/numeric value/);
        expect(publish).not.toHaveBeenCalled();
    });

    it("rejects a missing column even when that optional query has no rows", async () => {
        results.get(CARE_GAPS.query)!.table.rows = [];
        results.get(CARE_GAPS.query)!.table.columns = [];
        await expect(syncFromGold()).rejects.toThrow(/columns/);
        expect(publish).not.toHaveBeenCalled();
    });

    it("allows valid zero KPIs and schema-valid empty chart/worklist results", async () => {
        for (const [dax, result] of results) {
            if ([PAYER_KPIS.query, PROVIDER_KPIS.query, MEDTECH_KPIS.query].includes(dax)) {
                result.table.rows[0] = result.table.rows[0].map(() => 0);
            } else result.table.rows = [];
        }
        await syncFromGold();
        const payload = JSON.parse(publish.mock.calls[0][0].payloadJson);
        expect(payload.kpis.every((kpi: { value: number }) => kpi.value === 0)).toBe(true);
        expect(payload.series).toEqual([]);
        expect(payload.worklist).toEqual([]);
    });

    it("never exposes a short member identifier in the persisted payload", async () => {
        results.get(HIGH_COST_MEMBERS.query)!.table.rows[0][0] = "1234";
        await syncFromGold();
        expect(JSON.parse(publish.mock.calls[0][0].payloadJson).worklist[0].subject).toBe("…");
    });

    it.each(["denied", "conflict"])("surfaces the actual server %s without direct database writes", async (status) => {
        publish.mockResolvedValue({ status, version: 9 });
        await expect(syncFromGold()).rejects.toBeInstanceOf(status === "denied" ? SyncDeniedError : SyncConflictError);
        expect(write).not.toHaveBeenCalled();
    });

    it("does not publish when a source fails", async () => {
        query.mockRejectedValueOnce(new Error("Source unavailable"));
        await expect(syncFromGold()).rejects.toThrow("Source unavailable");
        expect(publish).not.toHaveBeenCalled();
    });
});
