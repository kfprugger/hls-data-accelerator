import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { goldResults, publication } from "@/test/snapshot-fixtures";

const mocks = vi.hoisted(() => ({ access: vi.fn(), publish: vi.fn(), read: vi.fn(), runs: vi.fn(), query: vi.fn(), write: vi.fn() }));
vi.mock("@/hooks/auth.context", () => ({ useAuth: () => ({ isAuthenticated: true, isLoading: false }) }));
vi.mock("@/lib/fabric-client", () => ({ getFabricClient: () => ({ semanticModel: () => ({ query: mocks.query }) }) }));
vi.mock("@/lib/rayfin-client", () => {
    function entity(execute: typeof mocks.read) {
        const builder = {
            select: () => builder, where: () => builder, first: () => builder, orderBy: () => builder, execute,
            create: mocks.write, update: mocks.write, delete: mocks.write,
        };
        return builder;
    }
    return { getRayfinClient: () => ({
        data: { PublishedSnapshot: entity(mocks.read), SyncRun: entity(mocks.runs) },
        functions: { getSyncAccess: { invoke: mocks.access }, publishSnapshot: { invoke: mocks.publish } },
    }) };
});

beforeEach(() => {
    vi.clearAllMocks();
    mocks.access.mockResolvedValue({ canSync: true, version: 1, publisherId: "synthetic-writer" });
    mocks.read.mockResolvedValue([publication(1)]);
    mocks.runs.mockResolvedValue([]);
    const results = goldResults();
    mocks.query.mockImplementation(async (dax: string) => results.get(dax));
    mocks.publish.mockResolvedValue({ status: "published", version: 2 });
});
afterEach(cleanup);

describe("dashboard publication lifecycle", () => {
    it("mounts an empty database as a read-only viewer with zero source reads or writes", async () => {
        mocks.read.mockResolvedValue([]);
        mocks.access.mockResolvedValue({ canSync: false, version: 0, publisherId: "synthetic-viewer" });
        render(<App />);
        await waitFor(() => expect(screen.getByRole("button", { name: "Sync from Gold" })).toBeDisabled());
        await screen.findByText("Read-only viewer");
        expect(mocks.query).not.toHaveBeenCalled();
        expect(mocks.publish).not.toHaveBeenCalled();
        expect(mocks.write).not.toHaveBeenCalled();
    });

    it("allows an authorized writer to seed only after explicitly choosing sync", async () => {
        mocks.read.mockResolvedValue([]);
        mocks.access.mockResolvedValue({ canSync: true, version: 0, publisherId: "synthetic-writer" });
        mocks.publish.mockImplementation(async () => {
            mocks.read.mockResolvedValue([publication(1)]);
            return { status: "published", version: 1 };
        });
        render(<App />);
        const sync = screen.getByRole("button", { name: "Sync from Gold" });
        await waitFor(() => expect(sync).toBeEnabled());
        expect(mocks.query).not.toHaveBeenCalled();
        expect(mocks.publish).not.toHaveBeenCalled();
        fireEvent.click(sync);
        await screen.findByText(/Publication v1/);
        expect(mocks.query).toHaveBeenCalledTimes(10);
        expect(mocks.publish).toHaveBeenCalledOnce();
        expect(mocks.write).not.toHaveBeenCalled();
    });

    it.each(["conflict", "failure", "denied"])("preserves the displayed publication when publication returns %s", async (status) => {
        render(<App />);
        await screen.findByText(/Publication v1/);
        const sync = screen.getByRole("button", { name: "Sync from Gold" });
        await waitFor(() => expect(sync).toBeEnabled());
        // A concurrent writer may have changed the database; a failed attempt must
        // not swap the viewer's generation or pretend our payload was published.
        mocks.read.mockResolvedValue([publication(9)]);
        if (status === "failure") mocks.publish.mockRejectedValue(new Error("Database unavailable"));
        else mocks.publish.mockResolvedValue({ status, version: 9 });
        fireEvent.click(sync);
        await screen.findByText(/Sync not published:/);
        expect(screen.getByText(/Publication v1/)).toBeInTheDocument();
        expect(screen.queryByText(/Publication v9/)).not.toBeInTheDocument();
        expect(mocks.read).toHaveBeenCalledOnce();
        expect(mocks.write).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Provider" }));
        await screen.findByText("Synthetic measure");
        expect(screen.getByText(/Publication v1/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "MedTech" }));
        await screen.findByText("Modality mix");
        expect(screen.getByText(/Publication v1/)).toBeInTheDocument();
    });
});
