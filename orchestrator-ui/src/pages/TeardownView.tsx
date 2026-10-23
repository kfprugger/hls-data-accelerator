import { Button, Card, CardHeader, Checkbox, Chip, FormControl, FormControlLabel, FormHelperText, FormLabel, MenuItem, Select, TextField, Tooltip, Typography } from "@mui/material";
import { DeleteOutlined, ExpandLess, ExpandMore, Link, Lock, LockOpen, Search, Sync } from "@mui/icons-material";
import { makeStyles } from "@griffel/react";
import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";


import {
  getDeploymentCapacity,
  getLocks,
  listSubscriptions,
  reconcileTeardowns,
  setLock,
  startTeardown,
  startTeardownBatch,
  type DeploymentCapacityMapping,
  type TeardownRequest,
} from "../api";
import { useAppState } from "../AppState";
import { typeBadge } from "../components/TypeBadges";
import { MockDataBanner } from "../components/MockDataBanner";
import {
  getMockSubscriptions,
  scanForTeardownCandidates,
  startMockTeardown,
  type TeardownCandidate,
  type MockSubscription,
} from "../mockDeployment";

const useStyles = makeStyles({
    header: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "24px",
    },
    scanControls: {
        display: "flex",
        alignItems: "flex-end",
        gap: "24px",
        marginBottom: "24px",
    },
    candidateList: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
    },
    candidateCard: {
        transition: "box-shadow 0.2s ease, transform 0.15s ease",
        cursor: "pointer",
        ":hover": {
            boxShadow: "0 2px 6px #00000016",
            transform: "translateY(-1px)",
        },
    },
    candidateCardSelected: {
        border: `2px solid ${"var(--m3-colorPaletteRedForeground1)"}`,
        boxShadow: "0 4px 12px #00000018",
    },
    candidateCardPaired: {
        borderLeft: `3px solid ${"var(--m3-colorBrandStroke1)"}`,
        backgroundColor: "var(--m3-colorBrandBackground2)",
    },
    candidateRow: {
        display: "flex",
        alignItems: "center",
        gap: "16px",
        width: "100%",
    },
    candidateInfo: {
        flex: 1,
        display: "flex",
        flexDirection: "column",
        gap: "4px",
    },
    candidateName: {
        display: "flex",
        alignItems: "center",
        gap: "12px",
    },
    artifactList: {
        padding: `${"12px"} ${"24px"}`,
        backgroundColor: "var(--m3-colorNeutralBackground3)",
        borderTop: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        fontSize: "12px",
        lineHeight: "1.6",
        fontFamily: "'Cascadia Code', 'Consolas', monospace",
        maxHeight: "200px",
        overflowY: "auto" as const,
    },
    actions: {
        display: "flex",
        gap: "16px",
        marginTop: "28px",
    },
    warning: {
        padding: "16px",
        backgroundColor: "var(--m3-colorStatusDangerBackground1)",
        borderLeft: `4px solid ${"var(--m3-colorStatusDangerBorderActive)"}`,
        borderRadius: "16px",
        color: "var(--m3-colorStatusDangerForeground1)",
        fontSize: "14px",
        fontWeight: 600,
        marginBottom: "24px",
    },
    error: {
        color: "var(--m3-colorStatusDangerForeground1)",
        fontSize: "12px",
        marginTop: "12px",
    },
    sectionTitle: {
        marginTop: "28px",
        marginBottom: "12px",
    },
    sectionDesc: {
        color: "var(--m3-colorNeutralForeground3)",
        marginBottom: "12px",
        display: "block" as const,
    },
    emptyState: {
        padding: "28px",
        textAlign: "center" as const,
        color: "var(--m3-colorNeutralForeground3)",
    },
    scanStatus: {
        marginBottom: "24px",
        padding: `${"12px"} ${"16px"}`,
        backgroundColor: "var(--m3-colorNeutralBackground3)",
        borderRadius: "16px",
        border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "24px",
        flexWrap: "wrap" as const,
    },
    scanMeta: {
        display: "flex",
        alignItems: "center",
        gap: "12px",
        flexWrap: "wrap" as const,
    },
});

function statusBadge(status: string) {
    switch (status) {
        case "full":
            return <Chip component="span" size="small" variant="filled" color="success" label={<>Full Deploy</>}/>;
        case "partial":
            return <Chip component="span" size="small" variant="filled" color="warning" label={<>Partial</>}/>;
        case "orphaned":
            return <Chip component="span" size="small" variant="filled" color="error" label={<>Orphaned</>}/>;
        case "active":
            return <Chip component="span" size="small" variant="filled" color="default" label={<>Active</>}/>;
        default:
            return <Chip component="span" size="small" variant="filled" color="default" label={<>{status}</>}/>;
    }
}

export function TeardownView() {
    const styles = useStyles();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const scanPollRef = useRef<number | null>(null);
    const activeScanIdRef = useRef<string | null>(null);
    const hasInitializedRef = useRef(false);
    const normalizeResourceId = useCallback((id: string) => id.replace(/^\//, ""), []);
    const { selectedSubscription, setSelectedSubscription, teardownScan, refreshTeardownScan, subscriptions: ctxSubscriptions } = useAppState();
    const [loading, setLoading] = useState(false);
    const [scanning, setScanning] = useState(false);
    const [error, setError] = useState("");
    const [subscriptions, setSubscriptions] = useState<MockSubscription[]>(getMockSubscriptions());
    const [candidates, setCandidates] = useState<TeardownCandidate[]>([]);
    const [candidateScope, setCandidateScope] = useState<{
        subscriptionId: string;
        expectedTenantId?: string;
    }>({ subscriptionId: "" });
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
    const [lockedIds, setLockedIds] = useState<Set<string>>(new Set());
    const [scanned, setScanned] = useState(false);
    const [usingMock, setUsingMock] = useState(false);
    const [showAllHDS, setShowAllHDS] = useState(() => searchParams.get("allHds") === "1");
    const [capacityMappings, setCapacityMappings] = useState<Map<string, DeploymentCapacityMapping>>(new Map());
    const capacityFetchedRef = useRef<Set<string>>(new Set());
    const [scanPhase, setScanPhase] = useState("");
    const [scanMessage, setScanMessage] = useState("");
    const [scanCounts, setScanCounts] = useState({ fabric: 0, azure: 0, spn: 0 });
    const [dryRun, setDryRun] = useState(true);
    const [frontEndResourceGroups, setFrontEndResourceGroups] = useState("");
    // Load locks from backend on mount
    useEffect(() => {
        getLocks()
            .then((ids: string[]) => {
            if (ids.length > 0)
                setLockedIds(new Set(ids.map(normalizeResourceId)));
        })
            .catch(() => {
            // Fall back to localStorage
            try {
                const saved = localStorage.getItem("teardown-locks");
                if (saved)
                    setLockedIds(new Set(JSON.parse(saved).map((id: string) => normalizeResourceId(id))));
            }
            catch { /* ignore */ }
        });
    }, [normalizeResourceId]);
    useEffect(() => {
        const initialExpanded = searchParams.get("expanded") ?? "";
        if (initialExpanded) {
            setExpandedIds(new Set(initialExpanded.split(",").filter(Boolean)));
        }
        const sub = searchParams.get("subscription") ?? "";
        if (sub && !selectedSubscription) {
            setSelectedSubscription(sub);
        }
        // Read initial URL state once on mount.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    // Persist locks to backend (and localStorage fallback) whenever they change
    const persistLocks = useCallback((ids: Set<string>, prevIds: Set<string>) => {
        // Find added and removed locks
        for (const id of ids) {
            if (!prevIds.has(id)) {
                setLock(id, true).catch(() => { });
            }
        }
        for (const id of prevIds) {
            if (!ids.has(id)) {
                setLock(id, false).catch(() => { });
            }
        }
        localStorage.setItem("teardown-locks", JSON.stringify([...ids]));
    }, [normalizeResourceId]);
    useEffect(() => {
        // Guard against React StrictMode double-mount
        if (hasInitializedRef.current)
            return;
        hasInitializedRef.current = true;
        // Prefer context subscriptions (fetched at app mount); fall back to /api/scan
        if (ctxSubscriptions.length > 0) {
            setSubscriptions(ctxSubscriptions);
            if (!selectedSubscription)
                setSelectedSubscription(ctxSubscriptions[0].id);
        }
        else {
            listSubscriptions()
                .then((subs: MockSubscription[]) => {
                if (subs.length > 0) {
                    setSubscriptions(subs);
                    if (!selectedSubscription)
                        setSelectedSubscription(subs[0].id);
                }
            })
                .catch(() => { });
        }
        // If a global scan is already running or completed, seed UI from it.
        // Otherwise stay idle until the user clicks Scan Resources.
        if (teardownScan.status === "completed" || teardownScan.status === "running") {
            setCandidates((teardownScan.candidates as TeardownCandidate[]) ?? []);
            setCandidateScope({ subscriptionId: teardownScan.subscriptionId, expectedTenantId: teardownScan.expectedTenantId });
            setScanCounts(teardownScan.counts);
            setScanPhase(teardownScan.phase || teardownScan.status);
            setScanMessage(teardownScan.message || "Resource scan running...");
            if (teardownScan.status === "completed") {
                setScanned(true);
                setScanning(false);
            }
            else {
                setScanning(true);
            }
        }
    }, []); // eslint-disable-line react-hooks/exhaustive-deps
    // Keep candidates in sync with the global background scan
    useEffect(() => {
        if (teardownScan.status === "completed" || teardownScan.status === "running") {
            setCandidateScope({ subscriptionId: teardownScan.subscriptionId, expectedTenantId: teardownScan.expectedTenantId });
        }
        if (teardownScan.status === "completed") {
            setCandidates((teardownScan.candidates as TeardownCandidate[]) ?? []);
            setScanCounts(teardownScan.counts);
            setScanPhase(teardownScan.phase || "completed");
            setScanMessage(teardownScan.message || "Resource scan completed.");
            setError("");
            setScanned(true);
            setScanning(false);
        }
        else if (teardownScan.status === "running") {
            setCandidates((teardownScan.candidates as TeardownCandidate[]) ?? []);
            setScanCounts(teardownScan.counts);
            setScanPhase(teardownScan.phase || "running");
            setScanMessage(teardownScan.message || "Scanning resources...");
            setError("");
            setScanning(true);
        }
        else if (teardownScan.status === "failed") {
            setScanning(false);
            if (!candidates.length)
                setError(teardownScan.error || "Background scan failed");
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [teardownScan.status, teardownScan.candidates, teardownScan.counts, teardownScan.phase, teardownScan.message, teardownScan.subscriptionId, teardownScan.expectedTenantId]);
    useEffect(() => {
        return () => {
            if (scanPollRef.current) {
                window.clearInterval(scanPollRef.current);
                scanPollRef.current = null;
            }
            activeScanIdRef.current = null;
        };
    }, []);
    useEffect(() => {
        const azureRgs = candidates.filter((candidate) => candidate.type === "azure");
        for (const rg of azureRgs) {
            if (capacityFetchedRef.current.has(rg.name)) {
                continue;
            }
            capacityFetchedRef.current.add(rg.name);
            getDeploymentCapacity(rg.name)
                .then((mapping) => {
                if (mapping) {
                    setCapacityMappings((prev) => {
                        const next = new Map(prev);
                        next.set(rg.name, mapping);
                        return next;
                    });
                }
            })
                .catch(() => { });
        }
    }, [candidates]);
    useEffect(() => {
        const next = new URLSearchParams();
        if (selectedSubscription)
            next.set("subscription", selectedSubscription);
        if (showAllHDS)
            next.set("allHds", "1");
        if (expandedIds.size > 0)
            next.set("expanded", Array.from(expandedIds).join(","));
        setSearchParams(next, { replace: true });
    }, [selectedSubscription, showAllHDS, expandedIds, setSearchParams]);
    const handleScan = () => {
        if (!selectedSubscription) {
            setScanning(false);
            setError("Select a subscription before scanning resources.");
            return;
        }
        if (scanPollRef.current) {
            window.clearInterval(scanPollRef.current);
            scanPollRef.current = null;
        }
        activeScanIdRef.current = Math.random().toString(36).slice(2);
        setScanning(true);
        setScanned(false);
        setUsingMock(false);
        setError("");
        setSelectedIds(new Set());
        setCandidates([]);
        setCapacityMappings(new Map());
        capacityFetchedRef.current = new Set();
        setScanPhase("starting");
        setScanMessage("Starting teardown scan...");
        setScanCounts({ fabric: 0, azure: 0, spn: 0 });
        refreshTeardownScan(selectedSubscription);
    };
    const handleMockScan = () => {
        setError("Demo mode: showing mock teardown candidates only. No live resources are listed.");
        setCandidates(scanForTeardownCandidates(selectedSubscription));
        setCandidateScope({ subscriptionId: selectedSubscription });
        setScanned(true);
        setScanning(false);
        setUsingMock(true);
        setSelectedIds(new Set());
        setCapacityMappings(new Map());
        capacityFetchedRef.current = new Set();
    };
    const toggleSelected = (id: string) => {
        if (lockedIds.has(normalizeResourceId(id)))
            return;
        const candidate = candidates.find((c) => c.id === id);
        setSelectedIds((prev) => {
            const next = new Set(prev);
            const selecting = !next.has(id);
            if (selecting) {
                next.add(id);
                // Auto-select matching SPNs when a Fabric workspace is selected
                if (candidate?.type === "fabric") {
                    const matchingSpns = candidates.filter((c) => c.type === "spn" && c.name === candidate.name && !lockedIds.has(normalizeResourceId(c.id)));
                    for (const spn of matchingSpns) {
                        next.add(spn.id);
                    }
                }
            }
            else {
                next.delete(id);
                // Auto-deselect matching SPNs when a Fabric workspace is deselected
                if (candidate?.type === "fabric") {
                    const matchingSpns = candidates.filter((c) => c.type === "spn" && c.name === candidate.name);
                    for (const spn of matchingSpns) {
                        next.delete(spn.id);
                    }
                }
            }
            return next;
        });
    };
    const selectAll = () => {
        setSelectedIds(new Set(candidates.filter((c) => !lockedIds.has(normalizeResourceId(c.id))).map((c) => c.id)));
    };
    const deselectAll = () => {
        setSelectedIds(new Set());
    };
    const toggleLocked = (id: string) => {
        setLockedIds((prev) => {
            const next = new Set(prev);
            const candidate = candidates.find((c) => c.id === id);
            const normalizedId = normalizeResourceId(id);
            const locking = !next.has(normalizedId);
            if (locking) {
                next.add(normalizedId);
                setSelectedIds((sel) => {
                    const nextSel = new Set(sel);
                    nextSel.delete(id);
                    return nextSel;
                });
                if (candidate?.type === "fabric") {
                    const matchingSpns = candidates.filter((c) => c.type === "spn" && c.name === candidate.name);
                    for (const spn of matchingSpns) {
                        next.add(normalizeResourceId(spn.id));
                        setSelectedIds((sel) => {
                            const nextSel = new Set(sel);
                            nextSel.delete(spn.id);
                            return nextSel;
                        });
                    }
                }
            }
            else {
                next.delete(normalizedId);
                if (candidate?.type === "fabric") {
                    const matchingSpns = candidates.filter((c) => c.type === "spn" && c.name === candidate.name);
                    for (const spn of matchingSpns) {
                        next.delete(normalizeResourceId(spn.id));
                    }
                }
            }
            persistLocks(next, prev);
            return next;
        });
    };
    const unlocked = candidates.filter((c) => !lockedIds.has(normalizeResourceId(c.id)));
    const allSelected = unlocked.length > 0 && selectedIds.size === unlocked.length;
    const someSelected = selectedIds.size > 0 && selectedIds.size < unlocked.length;
    const toggleExpanded = (id: string) => {
        setExpandedIds((prev) => {
            const next = new Set(prev);
            if (next.has(id))
                next.delete(id);
            else
                next.add(id);
            return next;
        });
    };
    const handleTeardown = async () => {
        if (selectedIds.size === 0) {
            setError("Select at least one resource to tear down.");
            return;
        }
        if (!candidateScope.subscriptionId) {
            setError("The subscription for these scan results is unknown. Select a subscription and scan resources again before teardown.");
            return;
        }
        if (scanning) {
            setError("Wait for the resource scan to finish before teardown.");
            return;
        }
        const selected = candidates.filter((c) => selectedIds.has(c.id));
        const names = selected.map((c) => `${c.type}: ${c.name}${c.resourceCount !== undefined ? ` (${c.resourceCount} item/resource${c.resourceCount === 1 ? "" : "s"})` : ""}${c.detail ? ` — ${c.detail}` : ""}`).join("\n  ");
        if (dryRun) {
            window.alert(`Dry run only — no resources will be deleted.\n\nPlanned targets:\n  ${names}\n\nTurn off Dry run when you are ready to execute teardown.`);
            return;
        }
        const confirmation = window.confirm(`Permanently delete ${selectedIds.size} resource(s)?\n\nImpact preview:\n  ${names}\n\nEach target runs in its own teardown job. Paired workspace + Azure RG deletes are grouped when both are selected. This action cannot be undone.\n\nAre you sure you want to continue?`);
        if (!confirmation)
            return;
        setLoading(true);
        setError("");
        if (usingMock) {
            for (const candidate of selected)
                startMockTeardown(candidate);
            setLoading(false);
            navigate("/teardown/monitor");
            return;
        }
        const scope = {
            subscription_id: candidateScope.subscriptionId,
            ...(candidateScope.expectedTenantId ? { expected_tenant_id: candidateScope.expectedTenantId } : {}),
            discover_front_ends: true,
        };
        const extraGroups = [...new Set(frontEndResourceGroups.split(",").map((name) => name.trim()).filter(Boolean))];
        // Group selection into independent teardown jobs so multiple workspaces
        // and multiple Azure RGs each run in their own parallel pipeline rather
        // than being forced through a single sequential request.
        //
        // Pairing rule: a Fabric workspace and an Azure RG that deploy together
        // (same capacityMapping) are submitted as ONE job so the backend can keep
        // them logically linked in the history view.
        const jobs: TeardownRequest[] = [];
        const selectedFabric = selected.filter((c) => c.type === "fabric");
        const selectedAzure = selected.filter((c) => c.type === "azure");
        const pairedRgNames = new Set<string>();
        for (const ws of selectedFabric) {
            // Find a paired Azure RG that maps to this workspace AND is also selected
            const pairedRg = [...capacityMappings.entries()].find(([rgName, m]) => m.workspaceName === ws.name && selectedAzure.some((a) => a.name === rgName));
            const rgName = pairedRg?.[0] ?? "";
            if (rgName)
                pairedRgNames.add(rgName);
            jobs.push({
                ...scope,
                ...(rgName ? { front_end_resource_groups: extraGroups } : {}),
                fabric_workspace_name: ws.name,
                resource_group_name: rgName,
                delete_workspace: true,
                delete_azure_rg: !!rgName,
            });
        }
        // Any Azure RG that wasn't paired becomes its own standalone job
        for (const rg of selectedAzure) {
            if (pairedRgNames.has(rg.name))
                continue;
            jobs.push({
                ...scope,
                front_end_resource_groups: extraGroups,
                fabric_workspace_name: "",
                resource_group_name: rg.name,
                delete_workspace: false,
                delete_azure_rg: true,
            });
        }
        // Use the backend batch endpoint for multi-job teardowns so operators get
        // one durable page with every child job instead of a generic history jump.
        try {
            if (jobs.length === 1) {
                const result = await startTeardown(jobs[0]);
                setLoading(false);
                navigate(`/monitor/${encodeURIComponent(result.instanceId)}`);
            }
            else {
                const result = await startTeardownBatch(jobs);
                setLoading(false);
                navigate(`/teardown/batch/${encodeURIComponent(result.batchId)}`);
            }
            return;
        }
        catch {
            setError("Backend teardown API unavailable. Running mock teardown monitor.");
            for (const candidate of selected) {
                startMockTeardown(candidate);
            }
        }
        setLoading(false);
        navigate("/teardown/monitor");
    };
    const renderCandidate = (c: TeardownCandidate) => {
        const isSelected = selectedIds.has(c.id);
        const isExpanded = expandedIds.has(c.id);
        const isLocked = lockedIds.has(normalizeResourceId(c.id));
        const isPaired = pairedIds.has(c.id);
        const openHistoryForCandidate = (event: React.MouseEvent) => {
            event.stopPropagation();
            const query = c.type === "azure" ? c.name : c.name;
            navigate(`/history?type=teardown&q=${encodeURIComponent(query)}`);
        };
        const colorIdx = pairColorIndex.get(c.id) ?? 0;
        const pairColor = PAIR_COLORS[colorIdx % PAIR_COLORS.length];
        // For paired Azure RGs, look up the matching workspace name for the tooltip
        const pairedWorkspaceName = isPaired && c.type === "azure" && capacityMappings.has(c.name)
            ? capacityMappings.get(c.name)!.workspaceName
            : undefined;
        const pairedRgName = isPaired && c.type === "fabric"
            ? [...capacityMappings.entries()].find(([, m]) => m.workspaceName === c.name)?.[0]
            : undefined;
        return (<Card key={c.id} className={`${styles.candidateCard} ${isSelected ? styles.candidateCardSelected : ""} ${isPaired && !isSelected ? styles.candidateCardPaired : ""}`} role="button" tabIndex={0} onClick={() => toggleSelected(c.id)} onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggleSelected(c.id);
                }
            }} style={{
                ...(isLocked ? { opacity: 0.6 } : {}),
                ...(isPaired && !isSelected
                    ? {
                        backgroundColor: pairColor.bg,
                        borderLeft: `3px solid ${pairColor.border}`,
                    }
                    : {}),
            }}>
        <CardHeader title={<div className={styles.candidateRow}>
              <Checkbox checked={isSelected} onClick={(e) => e.stopPropagation()} onChange={(event) => {
                    const data = { checked: event.target.checked };
                    setSelectedIds((prev) => {
                        const next = new Set(prev);
                        if (data.checked)
                            next.add(c.id);
                        else
                            next.delete(c.id);
                        return next;
                    });
                    if (c.type === "fabric") {
                        const matchingSpns = candidates.filter((sp) => sp.type === "spn" && sp.name === c.name && !lockedIds.has(normalizeResourceId(sp.id)));
                        if (matchingSpns.length) {
                            setSelectedIds((prev) => {
                                const next = new Set(prev);
                                for (const spn of matchingSpns) {
                                    if (data.checked)
                                        next.add(spn.id);
                                    else
                                        next.delete(spn.id);
                                }
                                return next;
                            });
                        }
                    }
                }} disabled={isLocked}/>
              <div className={styles.candidateInfo}>
                <div className={styles.candidateName}>
                  {typeBadge(c.type)}
                  <Button onClick={openHistoryForCandidate} style={{ padding: 0, minWidth: 0 }} variant="text" size="small">
                    <Typography component="span" variant="body2" sx={{
                    fontWeight: 600,
                    textDecoration: "underline"
                }}>{c.name}</Typography>
                  </Button>
                  {statusBadge(c.status)}
                  {c.previouslyDeployed && <Chip component="span" size="small" variant="filled" color="default" label={<>Previously Deployed</>}/>}
                  {isLocked && <Chip component="span" size="small" variant="filled" color="default" label={<>Locked</>}/>}
                </div>
                <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">
                  {c.detail}
                </Typography>
                {c.type === "fabric" && isPaired && pairedRgName && capacityMappings.has(pairedRgName) && (() => {
                    const m = capacityMappings.get(pairedRgName)!;
                    return (<div style={{ display: "flex", gap: "12px", alignItems: "center", marginTop: 2 }}>
                      <Chip component="span" size="small" variant="filled" color="primary" label={<>Fabric Capacity</>}/>
                      <Typography component="span" variant="caption">{m.capacityName}</Typography>
                    </div>);
                })()}
                {c.resourceCount !== undefined && c.type === "azure" && (<Typography component="span" variant="caption">
                    Resources discovered: {c.resourceCount}
                  </Typography>)}
                {c.resourceCount !== undefined && c.type !== "azure" && (<Typography component="span" variant="caption">
                    Resources: {c.resourceCount}/{c.expectedCount}
                  </Typography>)}
              </div>
              {isPaired && (<Tooltip title={pairedWorkspaceName
                        ? `Linked with Fabric workspace: ${pairedWorkspaceName}`
                        : pairedRgName
                            ? `Linked with Azure RG: ${pairedRgName}`
                            : "Linked deployment"} describeChild>
                  <div style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "3px",
                        padding: `2px ${"12px"}`,
                        borderRadius: "16px",
                        backgroundColor: pairColor.badge,
                        color: pairColor.badgeText,
                        fontSize: "11px",
                        fontWeight: 600,
                        cursor: "default",
                        whiteSpace: "nowrap" as const,
                    }}>
                    <Link style={{ fontSize: "11px" }}/>
                    <span>{pairedWorkspaceName ?? pairedRgName ?? "Linked"}</span>
                  </div>
                </Tooltip>)}
              <Tooltip title={isLocked ? "Unlock to allow teardown" : "Lock to prevent accidental deletion"} describeChild>
                <Button onClick={(e) => {
                    e.stopPropagation();
                    toggleLocked(c.id);
                }} style={isLocked ? { color: "var(--m3-colorPaletteRedForeground1)" } : undefined} variant="text" size="small" startIcon={isLocked ? <Lock /> : <LockOpen />}/>
              </Tooltip>
              <Button onClick={(e) => {
                    e.stopPropagation();
                    toggleExpanded(c.id);
                }} variant="text" size="small" startIcon={isExpanded ? <ExpandLess /> : <ExpandMore />}/>
            </div>}/>
        {isExpanded && c.matchedArtifacts && (<div className={styles.artifactList}>
            {c.matchedArtifacts.map((a, i) => (<div key={i}>• {a}</div>))}
          </div>)}
      </Card>);
    };
    // Compute paired IDs: Azure RG ↔ Fabric workspace that share a name via capacity mapping
    // Assign each pair a unique color index for visual distinction
    const pairedIds = new Set<string>();
    const pairColorIndex = new Map<string, number>(); // candidate id → color index
    let pairIdx = 0;
    for (const [rgName, mapping] of capacityMappings) {
        if (mapping.workspaceName) {
            const rgCandidate = candidates.find((c) => c.type === "azure" && c.name === rgName);
            const wsCandidate = candidates.find((c) => c.type === "fabric" && c.name === mapping.workspaceName);
            if (rgCandidate && wsCandidate) {
                pairedIds.add(rgCandidate.id);
                pairedIds.add(wsCandidate.id);
                pairColorIndex.set(rgCandidate.id, pairIdx);
                pairColorIndex.set(wsCandidate.id, pairIdx);
                pairIdx++;
            }
        }
    }
    // Palette of distinct accent colors for paired deployments
    const PAIR_COLORS: Array<{
        border: string;
        bg: string;
        badge: string;
        badgeText: string;
    }> = [
        { border: "var(--m3-colorBrandStroke1)", bg: "var(--m3-colorBrandBackground2)", badge: "var(--m3-colorBrandBackground)", badgeText: "var(--m3-colorNeutralForegroundOnBrand)" },
        { border: "var(--m3-colorPalettePurpleForeground2)", bg: "var(--m3-colorPalettePurpleBackground2)", badge: "var(--m3-colorPalettePurpleForeground2)", badgeText: "#fff" },
        { border: "var(--m3-colorPaletteTealForeground2)", bg: "var(--m3-colorPaletteTealBackground2)", badge: "var(--m3-colorPaletteTealForeground2)", badgeText: "#fff" },
        { border: "var(--m3-colorPaletteMarigoldForeground2)", bg: "var(--m3-colorPaletteMarigoldBackground2)", badge: "var(--m3-colorPaletteMarigoldForeground2)", badgeText: "#fff" },
        { border: "var(--m3-colorPaletteBerryForeground2)", bg: "var(--m3-colorPaletteBerryBackground2)", badge: "var(--m3-colorPaletteBerryForeground2)", badgeText: "#fff" },
    ];
    const sortCandidatesDesc = (items: TeardownCandidate[]) => [...items].sort((a, b) => b.name.localeCompare(a.name, undefined, { numeric: true, sensitivity: "base" }));
    const allFabricCandidates = sortCandidatesDesc(candidates.filter((c) => c.type === "fabric"));
    // Default: only show workspaces with all 3 criteria (qualified). When showAllHDS is on, also show partial HDS workspaces.
    const qualifiedFabricCandidates = sortCandidatesDesc(allFabricCandidates.filter((c) => c.qualified !== false));
    const partialHdsCandidates = sortCandidatesDesc(allFabricCandidates.filter((c) => c.qualified === false));
    const fabricCandidates = showAllHDS && !scanning ? allFabricCandidates : qualifiedFabricCandidates;
    const azureCandidates = sortCandidatesDesc(candidates.filter((c) => c.type === "azure"));
    // SPNs: show orphaned identities by default even when their workspace is gone;
    // active SPNs stay tied to qualified workspaces unless the operator opts into all partial deployments.
    const qualifiedWsNames = new Set(qualifiedFabricCandidates.map((c) => c.name));
    const allSpnCandidates = sortCandidatesDesc(candidates.filter((c) => c.type === "spn"));
    const spnCandidates = showAllHDS && !scanning
        ? allSpnCandidates
        : sortCandidatesDesc(allSpnCandidates.filter((c) => c.status === "orphaned" || qualifiedWsNames.has(c.name)));
    const handleReconcile = async () => {
        setLoading(true);
        setError("");
        try {
            const result = await reconcileTeardowns();
            setScanMessage(result.reconciled ? `Reconciled ${result.reconciled} teardown run(s).` : "No interrupted teardown runs needed reconciliation.");
        }
        catch {
            setError("Unable to reconcile teardown history right now.");
        }
        finally {
            setLoading(false);
        }
    };
    return (<div>
      {usingMock && <MockDataBanner />}
      <div className={styles.header}>
        <Typography component="div" variant="h5">Teardown — Resource Scanner</Typography>
      </div>

      {/* Subscription selector + scan */}
      <div className={styles.scanControls}>
        <FormControl style={{ minWidth: 300 }}><FormLabel id="field-teardownview-1-label" htmlFor="field-teardownview-1">{"Azure Subscription"}</FormLabel>
          <Select value={[selectedSubscription][0] ?? ""} displayEmpty onChange={(event) => {
            const data = { optionValue: event.target.value };
            return setSelectedSubscription(data.optionValue as string);
        }} id="field-teardownview-1" labelId="field-teardownview-1-label">
            {subscriptions.map((s) => (<MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>))}
          </Select>
        </FormControl>
        <Button onClick={handleScan} disabled={scanning || !selectedSubscription} variant="contained" startIcon={scanning ? <Sync /> : <Search />}>
          {scanning ? "Scanning…" : "Scan Resources"}
        </Button>
        <Button onClick={handleReconcile} disabled={loading || scanning} variant="outlined" startIcon={<Sync />}>
          Reconcile history
        </Button>
        <Tooltip title={"Demo mode uses generated teardown candidates and never lists live resources."} describeChild>
          <Button onClick={handleMockScan} disabled={scanning} variant="outlined">
            Use demo data
          </Button>
        </Tooltip>
      </div>

      {scanning && (<div className={styles.scanStatus}>
          <div>
            <Typography component="span" variant="body2" sx={{
                fontWeight: 600
            }}>{scanMessage || "Scanning resources..."}</Typography>
            <Typography style={{ color: "var(--m3-colorNeutralForeground3)", display: "block" }} component="span" variant="caption">
              Fully-qualified candidates appear below as discovered. Partial matches will appear after the scan completes.
            </Typography>
          </div>
          <div className={styles.scanMeta}>
            <Chip component="span" size="small" variant="filled" color="primary" label={<>{scanPhase || "starting"}</>}/>
            <Chip component="span" size="small" variant="filled" color="default" label={<>Fabric {scanCounts.fabric}</>}/>
            <Chip component="span" size="small" variant="filled" color="default" label={<>Azure {scanCounts.azure}</>}/>
            <Chip component="span" size="small" variant="filled" color="default" label={<>Entra {scanCounts.spn}</>}/>
          </div>
        </div>)}

      {scanned && candidates.length > 0 && (<div style={{
                display: "flex",
                alignItems: "center",
                gap: "16px",
                marginBottom: "16px",
                padding: `${"12px"} ${"16px"}`,
                backgroundColor: "var(--m3-colorNeutralBackground3)",
                borderRadius: "16px",
            }}>
          <FormControlLabel label={allSelected
                ? "Deselect all"
                : lockedIds.size > 0
                    ? `Select all unlocked (${unlocked.length} of ${candidates.length})`
                    : `Select all (${candidates.length} resources)`} control={<Checkbox checked={(allSelected ? true : someSelected ? "mixed" : false) === true} onChange={() => (allSelected ? deselectAll() : selectAll())} indeterminate={(allSelected ? true : someSelected ? "mixed" : false) === "mixed"}/>}/>
        </div>)}

      {!scanned && !scanning && !error && (<div className={styles.candidateList}>
          <Card>
            <CardHeader title={<Typography component="span" variant="body2" sx={{
                    fontWeight: 600
                }}>Ready to scan live resources</Typography>} subheader={"Live teardown discovery is intentionally on demand because it enumerates Fabric workspaces, Azure resources, and Entra identities."}/>
          </Card>
          <Card><CardHeader title={<Typography component="span" variant="body2">Scanning discovers Fabric, Azure, and identity artifacts.</Typography>}/></Card>
        </div>)}

      {scanned && candidates.length === 0 && (<div className={styles.emptyState}>No matching deployment resources found.</div>)}

      {(fabricCandidates.length > 0 || partialHdsCandidates.length > 0) && (<>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "28px", marginBottom: "4px" }}>
            <Typography className={styles.sectionTitle} style={{ marginTop: 0, marginBottom: 0 }} component="div" variant="subtitle1">
              Fabric Workspaces ({fabricCandidates.length})
            </Typography>
            {!scanning && partialHdsCandidates.length > 0 && (<FormControlLabel label={`Show all HDS workspaces (${partialHdsCandidates.length} partial)`} control={<Checkbox checked={showAllHDS} onChange={(event) => {
                        const d = { checked: event.target.checked };
                        return setShowAllHDS(!!d.checked);
                    }}/>}/>)}
          </div>
          <Typography className={styles.sectionDesc} component="span" variant="caption">
            Workspaces with HDS, MasimoEventhouse, and fn_ClinicalAlerts deployed
          </Typography>
          <div className={styles.candidateList}>
            {fabricCandidates.map(renderCandidate)}
          </div>
          {fabricCandidates.length === 0 && (<div className={styles.emptyState} style={{ padding: "16px" }}>
              No fully-qualified workspaces found. {partialHdsCandidates.length > 0 ? "Enable \"Show all HDS workspaces\" to see partial deployments." : ""}
            </div>)}
        </>)}

      {azureCandidates.length > 0 && (<>
          <Typography className={styles.sectionTitle} component="div" variant="subtitle1">
            Azure Resource Groups ({azureCandidates.length})
          </Typography>
          <Typography className={styles.sectionDesc} component="span" variant="caption">
            Resource groups with Event Hub, ACR, FHIR Service, and emulator resources (expected: 11)
          </Typography>
          <div className={styles.candidateList}>
            {azureCandidates.map(renderCandidate)}
          </div>
        </>)}

      {spnCandidates.length > 0 && (<>
          <Typography className={styles.sectionTitle} component="div" variant="subtitle1">
            Workspace Identity SPNs ({spnCandidates.length}{!showAllHDS && allSpnCandidates.length > spnCandidates.length ? ` of ${allSpnCandidates.length}` : ""})
          </Typography>
          <Typography className={styles.sectionDesc} component="span" variant="caption">
            App registrations matching workspace identity naming from prior deployments
            {!showAllHDS && allSpnCandidates.length > spnCandidates.length && (<> — {allSpnCandidates.length - spnCandidates.length} hidden (partial workspaces)</>)}
          </Typography>
          <div className={styles.candidateList}>
            {spnCandidates.map(renderCandidate)}
          </div>
        </>)}

      {selectedIds.size > 0 && (() => {
            const selected = candidates.filter((c) => selectedIds.has(c.id));
            const hasFabric = selected.some((c) => c.type === "fabric");
            const hasAzure = selected.some((c) => c.type === "azure");
            const hasBoth = hasFabric && hasAzure;
            const mode = hasBoth
                ? "Teardown-All"
                : hasFabric
                    ? "Fabric Teardown"
                    : hasAzure
                        ? "Azure Teardown"
                        : "SPN Cleanup";
            return (<>
            <div className={styles.warning} style={{ marginTop: "28px" }}>
              {selectedIds.size} resource(s) selected for deletion.
              {hasBoth && " Both Fabric workspace and Azure RG selected — will run Teardown-All (complete cleanup)."}
              {dryRun ? " Dry run is ON, so the next click only previews the plan." : " This action cannot be undone."}
            </div>
            <Card style={{ marginTop: "12px" }}>
              <CardHeader title={<Typography component="span" variant="body2" sx={{
                        fontWeight: 600
                    }}>Teardown plan</Typography>}/>
              <div style={{ padding: `0 ${"24px"} ${"16px"}`, display: "grid", gap: "8px" }}>
                <Typography component="span" variant="caption">Scan subscription: {candidateScope.subscriptionId || "Unknown — scan resources again"}</Typography>
                {hasAzure && (<FormControl><FormLabel id="field-teardownview-2-label" htmlFor="field-teardownview-2">{"Additional front-end resource groups (optional)"}</FormLabel>
                    <TextField value={frontEndResourceGroups} onChange={(event) => {
                        const data = { value: event.target.value };
                        return setFrontEndResourceGroups(data.value);
                    }} placeholder="rg-cardiology, rg-dicom-viewer" fullWidth size="small" id="field-teardownview-2"/>
                  <FormHelperText>{"Comma-separated names. Discovery remains enabled; only groups tied to each deployment are deleted."}</FormHelperText></FormControl>)}
                {selected.slice(0, 8).map((item) => (<Typography key={item.id} component="span" variant="caption">{item.type.toUpperCase()} · {item.name}</Typography>))}
                {selected.length > 8 && <Typography component="span" variant="caption">+{selected.length - 8} more target(s)</Typography>}
                <FormControlLabel label={"Dry run — preview only, do not delete resources"} control={<Checkbox checked={dryRun} onChange={(event) => {
                        const data = { checked: event.target.checked };
                        return setDryRun(!!data.checked);
                    }}/>}/>
              </div>
            </Card>
            <div className={styles.actions}>
              <Button onClick={handleTeardown} style={{ backgroundColor: "var(--m3-colorPaletteRedBackground3)" }} disabled={loading || scanning} variant="contained" startIcon={<DeleteOutlined />}>
                {loading ? "Starting teardown…" : dryRun ? `Preview ${selectedIds.size} resource(s)` : `${mode}: Delete ${selectedIds.size} resource(s)`}
              </Button>
              <Button onClick={deselectAll} variant="text">
                Clear selection
              </Button>
            </div>
          </>);
        })()}

      {error && <div className={styles.error}>{error}</div>}
    </div>);
}
