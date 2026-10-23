import { Button, Checkbox, Chip, FormControl, FormControlLabel, FormLabel, MenuItem, Select, TextField, Typography } from "@mui/material";
import { Close, DeleteOutlined, ExpandLess, ExpandMore, OpenInNew, Sync, Visibility } from "@mui/icons-material";
import { makeStyles } from "@griffel/react";
import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";


import { listDeployments, getTeardownBatch, deleteDeployment, clearAllDeployments, type DeploymentSummary } from "../api";
import { listMockDeployments } from "../mockDeployment";
import { MockDataBanner } from "../components/MockDataBanner";
import { AzureBadge, FabricBadge } from "../components/TypeBadges";

const useStyles = makeStyles({
    header: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: "16px",
    },
    list: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        marginTop: "12px",
    },
    card: {
        backgroundColor: "var(--m3-colorNeutralBackground1)",
        border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        borderRadius: "16px",
        overflow: "hidden",
        transition: "box-shadow 0.2s ease",
        ":hover": {
            boxShadow: "0 2px 6px #00000016",
        },
    },
    cardRow: {
        display: "flex",
        alignItems: "center",
        padding: `${"12px"} ${"24px"}`,
        gap: "16px",
    },
    instanceId: {
        fontFamily: "'Cascadia Code', 'Consolas', monospace",
        fontSize: "12px",
        color: "var(--m3-colorNeutralForeground2)",
        minWidth: "180px",
    },
    runName: {
        fontWeight: 600,
        fontSize: "12px",
        color: "var(--m3-colorNeutralForeground1)",
        minWidth: "180px",
        cursor: "pointer",
        transition: "color 0.2s",
        ":hover": {
            color: "var(--m3-colorBrandForeground1)",
            textDecoration: "underline",
        },
    },
    workspace: {
        flex: 1,
        fontWeight: 600,
    },
    actions: {
        display: "flex",
        gap: "8px",
        alignItems: "center",
    },
    infoPanel: {
        padding: `${"12px"} ${"24px"}`,
        backgroundColor: "var(--m3-colorNeutralBackground3)",
        borderTop: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        display: "flex",
        gap: "28px",
        flexWrap: "wrap",
        fontSize: "12px",
    },
    linkGroup: {
        display: "flex",
        flexDirection: "column",
        gap: "4px",
    },
    linkLabel: {
        color: "var(--m3-colorNeutralForeground3)",
        fontSize: "11px",
        fontWeight: 600,
    },
    link: {
        display: "inline-flex",
        alignItems: "center",
        gap: "8px",
        color: "var(--m3-colorBrandForeground1)",
        textDecoration: "none",
        fontSize: "12px",
        ":hover": {
            textDecoration: "underline",
        },
    },
    filterRow: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "16px",
        marginBottom: "12px",
        flexWrap: "wrap" as const,
    },
    listHeader: {
        display: "flex",
        alignItems: "center",
        padding: `0 ${"24px"}`,
        gap: "16px",
        color: "var(--m3-colorNeutralForeground3)",
        fontSize: "12px",
        fontWeight: 600,
        marginBottom: "8px",
    },
});

function statusColor(s: string): "success" | "error" | "info" | "warning" | "default" {
    if (s === "Completed")
        return "success";
    if (s === "Failed" || s === "Terminated")
        return "error";
    if (s === "Running")
        return "info";
    if (s === "Suspended")
        return "warning";
    return "default";
}

function isRunningTeardownBatch(deployment: DeploymentSummary): boolean {
  const cs = deployment.customStatus as Record<string, unknown> | null;
  return cs?.runType === "teardownBatch" && deployment.runtimeStatus === "Running";
}

async function hydrateRunningTeardownBatches(deployments: DeploymentSummary[]): Promise<DeploymentSummary[]> {
  const hydrated = await Promise.all(
    deployments.map(async (deployment) => {
      if (!isRunningTeardownBatch(deployment)) return deployment;
      try {
        const status = await getTeardownBatch(deployment.instanceId);
        return status.batch ?? deployment;
      } catch {
        return deployment;
      }
    })
  );
  return hydrated;
}

export function DeploymentHistory() {
    const styles = useStyles();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const signatureRef = useRef("");
    const [deployments, setDeployments] = useState<DeploymentSummary[]>([]);
    const [usingMock, setUsingMock] = useState(false);
    const [loading, setLoading] = useState(true);
    const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
        const raw = searchParams.get("expanded") ?? "";
        return new Set(raw ? raw.split(",").filter(Boolean) : []);
    });
    const [runFilter, setRunFilter] = useState<"all" | "deployment" | "teardown">(() => (searchParams.get("type") as "all" | "deployment" | "teardown") || "all");
    const [nameFilter, setNameFilter] = useState(() => searchParams.get("q") ?? "");
    const [dateFrom, setDateFrom] = useState(() => searchParams.get("from") ?? "");
    const [dateTo, setDateTo] = useState(() => searchParams.get("to") ?? "");
    const [liveUpdates, setLiveUpdates] = useState(() => searchParams.get("live") !== "0");
    const [compareIds, setCompareIds] = useState<Set<string>>(new Set());
    const [relatedFor, setRelatedFor] = useState<string | null>(null);
    const [error, setError] = useState("");
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
    const refresh = useCallback(() => {
        setError("");
        const mockDeps = listMockDeployments();
        listDeployments()
            .then(async (real) => {
            const merged = [...mockDeps, ...(await hydrateRunningTeardownBatches(real))];
            const nextSignature = merged
                .map((d) => `${d.instanceId}|${d.runtimeStatus}|${d.lastUpdatedTime ?? ""}`)
                .sort()
                .join(";");
            if (nextSignature !== signatureRef.current) {
                signatureRef.current = nextSignature;
                setDeployments(merged);
            }
            setUsingMock(mockDeps.length > 0 && real.length === 0);
        })
            .catch(() => {
            setError("Unable to refresh deployment history from backend.");
            const fallbackSignature = mockDeps
                .map((d) => `${d.instanceId}|${d.runtimeStatus}|${d.lastUpdatedTime ?? ""}`)
                .sort()
                .join(";");
            if (fallbackSignature !== signatureRef.current) {
                signatureRef.current = fallbackSignature;
                setDeployments(mockDeps);
            }
            setUsingMock(mockDeps.length > 0);
        })
            .finally(() => setLoading(false));
    }, []);
    useEffect(() => {
        refresh();
    }, [refresh]);
    useEffect(() => {
        if (!liveUpdates)
            return;
        const interval = setInterval(() => {
            if (typeof document !== "undefined" && document.visibilityState === "hidden")
                return;
            refresh();
        }, 5000);
        return () => clearInterval(interval);
    }, [refresh, liveUpdates]);
    useEffect(() => {
        const next = new URLSearchParams();
        next.set("type", runFilter);
        if (nameFilter)
            next.set("q", nameFilter);
        else
            next.delete("q");
        if (dateFrom)
            next.set("from", dateFrom);
        else
            next.delete("from");
        if (dateTo)
            next.set("to", dateTo);
        else
            next.delete("to");
        if (expandedIds.size > 0)
            next.set("expanded", Array.from(expandedIds).join(","));
        else
            next.delete("expanded");
        next.set("live", liveUpdates ? "1" : "0");
        setSearchParams(next, { replace: true });
    }, [runFilter, nameFilter, dateFrom, dateTo, expandedIds, liveUpdates, setSearchParams]);
    const handleClearAll = async () => {
        if (!window.confirm(`Delete ALL ${deployments.length} deployment records? This cannot be undone.`))
            return;
        try {
            await clearAllDeployments();
        }
        catch {
            setError("Failed to clear deployment history.");
        }
        refresh();
    };
    const handleDelete = async (instanceId: string) => {
        if (!window.confirm(`Delete deployment record "${instanceId}"?`))
            return;
        try {
            await deleteDeployment(instanceId);
        }
        catch {
            setError(`Failed to delete deployment ${instanceId}.`);
        }
        refresh();
    };
    const toggleCompare = (instanceId: string, checked: boolean) => {
        setCompareIds((prev) => {
            const next = new Set(prev);
            if (checked) {
                if (next.size >= 2 && !next.has(instanceId))
                    next.delete(Array.from(next)[0]);
                next.add(instanceId);
            }
            else {
                next.delete(instanceId);
            }
            return next;
        });
    };
    const comparedRuns = Array.from(compareIds)
        .map((id) => deployments.find((deployment) => deployment.instanceId === id))
        .filter(Boolean) as DeploymentSummary[];
    const filteredDeployments = deployments.filter((deployment) => {
        const cs = deployment.customStatus as Record<string, unknown> | null;
        const isTeardown = (cs?.runType as string) === "teardown"
            || deployment.name === "teardown_orchestrator"
            || deployment.instanceId.toLowerCase().startsWith("teardown");
        if (runFilter === "teardown" && !isTeardown)
            return false;
        if (runFilter === "deployment" && isTeardown)
            return false;
        // Name filter: match against instanceId, workspace name, or RG name
        if (nameFilter) {
            const q = nameFilter.toLowerCase();
            const ws = ((cs?.workspaceName as string) || "").toLowerCase();
            const rg = ((cs?.resourceGroupName as string) || "").toLowerCase();
            const displayName = ((cs?.displayName as string) || "").toLowerCase();
            const id = deployment.instanceId.toLowerCase();
            if (!ws.includes(q) && !rg.includes(q) && !displayName.includes(q) && !id.includes(q))
                return false;
        }
        // Date range filter
        if (dateFrom && deployment.createdTime) {
            const created = new Date(deployment.createdTime);
            const from = new Date(dateFrom);
            if (created < from)
                return false;
        }
        if (dateTo && deployment.createdTime) {
            const created = new Date(deployment.createdTime);
            const to = new Date(dateTo);
            to.setDate(to.getDate() + 1); // include the full end day
            if (created >= to)
                return false;
        }
        return true;
    }).sort((a, b) => {
        const ta = a.createdTime ? new Date(a.createdTime).getTime() : 0;
        const tb = b.createdTime ? new Date(b.createdTime).getTime() : 0;
        return tb - ta;
    });
    return (<div>
      <div className={styles.header}>
        {usingMock && <MockDataBanner />}
        <Typography component="div" variant="h5">Run History</Typography>
        <div style={{ display: "flex", gap: "12px" }}>
          <FormControlLabel label={"Live"} control={<Checkbox checked={liveUpdates} onChange={(event) => {
                const d = { checked: event.target.checked };
                return setLiveUpdates(!!d.checked);
            }}/>}/>
          <Button onClick={refresh} variant="text" startIcon={<Sync />}>
            Refresh
          </Button>
          {deployments.length > 0 && (<Button onClick={handleClearAll} variant="text" startIcon={<DeleteOutlined />}>
              Clear All
            </Button>)}
        </div>
      </div>

      {error && (<Typography style={{ color: "var(--m3-colorStatusDangerForeground1)", marginBottom: "12px", display: "block" }} component="span" variant="caption">
          {error}
        </Typography>)}

      <div className={styles.filterRow}>
        <FormControl style={{ minWidth: 160 }}><FormLabel id="field-deploymenthistory-1-label" htmlFor="field-deploymenthistory-1">{"Type"}</FormLabel>
          <Select value={[runFilter][0] ?? ""} displayEmpty onChange={(event) => {
            const data = { optionValue: event.target.value };
            return setRunFilter((data.optionValue as "all" | "deployment" | "teardown") ?? "all");
        }} id="field-deploymenthistory-1" labelId="field-deploymenthistory-1-label">
            <MenuItem value="all">All runs</MenuItem>
            <MenuItem value="deployment">Deployments</MenuItem>
            <MenuItem value="teardown">Teardowns</MenuItem>
          </Select>
        </FormControl>
        <FormControl style={{ minWidth: 200, flex: 1 }}><FormLabel id="field-deploymenthistory-2-label" htmlFor="field-deploymenthistory-2">{"Search"}</FormLabel>
          <TextField value={nameFilter} onChange={(event) => {
            const d = { value: event.target.value };
            return setNameFilter(d.value);
        }} placeholder="Filter by name, workspace, or RG..." type="search" fullWidth size="small" id="field-deploymenthistory-2"/>
        </FormControl>
        <FormControl style={{ minWidth: 150 }}><FormLabel id="field-deploymenthistory-3-label" htmlFor="field-deploymenthistory-3">{"From"}</FormLabel>
          <TextField type="date" value={dateFrom} onChange={(event) => {
            const d = { value: event.target.value };
            return setDateFrom(d.value);
        }} fullWidth size="small" id="field-deploymenthistory-3"/>
        </FormControl>
        <FormControl style={{ minWidth: 150 }}><FormLabel id="field-deploymenthistory-4-label" htmlFor="field-deploymenthistory-4">{"To"}</FormLabel>
          <TextField type="date" value={dateTo} onChange={(event) => {
            const d = { value: event.target.value };
            return setDateTo(d.value);
        }} fullWidth size="small" id="field-deploymenthistory-4"/>
        </FormControl>
        <Typography style={{ color: "var(--m3-colorNeutralForeground3)", alignSelf: "flex-end", paddingBottom: 6 }} component="span" variant="caption">
          {filteredDeployments.length} of {deployments.length}
        </Typography>
      </div>

      {comparedRuns.length > 0 && (<div className={styles.card} style={{ marginBottom: "16px" }}>
          <div className={styles.cardRow} style={{ alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <Typography component="div" variant="body2" sx={{
                fontWeight: 600
            }}>Run compare</Typography>
              <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">
                Select up to two runs to compare status, timings, workspace, resource group, and phase counts.
              </Typography>
            </div>
            <Button onClick={() => setCompareIds(new Set())} variant="text">Clear compare</Button>
          </div>
          <div className={styles.infoPanel}>
            {comparedRuns.map((run) => {
                const cs = run.customStatus as Record<string, unknown> | null;
                return (<div key={run.instanceId} className={styles.linkGroup} style={{ minWidth: 240 }}>
                  <span className={styles.linkLabel}>{run.instanceId}</span>
                  <Typography component="span" variant="caption">Status: {run.runtimeStatus}</Typography>
                  <Typography component="span" variant="caption">Workspace: {(cs?.workspaceName as string) || "—"}</Typography>
                  <Typography component="span" variant="caption">RG: {(cs?.resourceGroupName as string) || "—"}</Typography>
                  <Typography component="span" variant="caption">Phases: {(cs?.completedPhases as number) ?? 0}/{(cs?.totalPhases as number) ?? 0}</Typography>
                  <Typography component="span" variant="caption">Updated: {run.lastUpdatedTime ? new Date(run.lastUpdatedTime).toLocaleString() : "—"}</Typography>
                </div>);
            })}
          </div>
        </div>)}

      <div className={styles.list}>
        {loading && (<>
            <div className={styles.card}><div className={styles.cardRow}><Typography component="span" variant="body2">Loading deployment history...</Typography></div></div>
            <div className={styles.card}><div className={styles.cardRow}><Typography component="span" variant="body2">Loading deployment history...</Typography></div></div>
            <div className={styles.card}><div className={styles.cardRow}><Typography component="span" variant="body2">Loading deployment history...</Typography></div></div>
          </>)}
        {!loading && filteredDeployments.length > 0 && (<div className={styles.listHeader}>
            <div style={{ width: 32 }}/> {/* Checkbox placeholder */}
            <div style={{ minWidth: 180 }}>Deployment Name</div>
            <div style={{ flex: 1 }}>Workspace / Resource Group</div>
            <div style={{ width: 100 }}>Type</div>
            <div style={{ width: 100 }}>Status</div>
            <div style={{ width: 60 }}>Progress</div>
            <div style={{ width: 150 }}>Created</div>
            <div style={{ width: 120 }}>Actions</div>
          </div>)}
        {!loading && filteredDeployments.map((d) => {
            const cs = d.customStatus as Record<string, unknown> | null;
            const workspace = (cs?.workspaceName as string) || "";
            const rgName = (cs?.resourceGroupName as string) || "";
            const isTeardown = (cs?.runType as string) === "teardown"
                || d.name === "teardown_orchestrator"
                || d.instanceId.toLowerCase().startsWith("teardown");
            const displayName = (cs?.displayName as string)
                || (workspace && rgName ? `${workspace} + ${rgName}` : workspace || rgName || "—");
            const completed = (cs?.completedPhases as number) ?? 0;
            const total = (cs?.totalPhases as number) ?? 0;
            const isMock = d.instanceId.startsWith("mock-");
            const isExpanded = expandedIds.has(d.instanceId);
            const links = cs?.links as Record<string, string> | undefined;
            const relatedCount = deployments.filter((other) => {
                if (other.instanceId === d.instanceId)
                    return false;
                const otherCs = other.customStatus as Record<string, unknown> | null;
                return !!((workspace && otherCs?.workspaceName === workspace) ||
                    (rgName && otherCs?.resourceGroupName === rgName));
            }).length;
            return (<div key={d.instanceId} className={styles.card}>
              <div className={styles.cardRow}>
                <div style={{ width: 32 }}>
                  <Checkbox checked={compareIds.has(d.instanceId)} onChange={(event) => {
                    const data = { checked: event.target.checked };
                    return toggleCompare(d.instanceId, !!data.checked);
                }} aria-label={`Compare ${d.instanceId}`}/>
                </div>
                <div className={styles.runName} style={{ minWidth: 180 }} onClick={() => navigate(`/monitor/${d.instanceId}`)} title="Click to view run details">
                  {workspace || (cs?.deployConfig as any)?.fabric_workspace_name || d.instanceId}
                  {isMock && (<Chip style={{ marginLeft: 6 }} component="span" size="small" variant="filled" color="default" label={<>mock</>}/>)}
                </div>
                <Typography className={styles.workspace} style={{ flex: 1, cursor: isTeardown ? "pointer" : "default", textDecoration: isTeardown ? "underline" : "none" }} onClick={isTeardown ? () => navigate(`/monitor/${d.instanceId}`) : undefined} component="span" variant="body2">{displayName}{relatedCount > 0 && <Button onClick={(event) => { event.stopPropagation(); setRelatedFor(d.instanceId); }} style={{ marginLeft: 6, padding: 0, minWidth: 0 }} variant="text" size="small"><Chip component="span" size="small" variant="filled" color="default" label={<>{relatedCount} related</>}/></Button>}</Typography>
                <div style={{ width: 100 }}>
                  <Chip component="span" size="small" variant="filled" color={isTeardown ? "warning" : "primary" as any} label={<>
                    {isTeardown ? "Teardown" : "Deployment"}
                  </>}/>
                </div>
                <div style={{ width: 100 }}>
                  <Chip component="span" size="small" variant="filled" color={statusColor(d.runtimeStatus) as any} label={<>{d.runtimeStatus}</>}/>
                </div>
                <div style={{ width: 60 }}>
                  {total > 0 && (<Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">
                      {completed}/{total}
                    </Typography>)}
                </div>
                <Typography style={{ color: "var(--m3-colorNeutralForeground3)", width: 150 }} component="span" variant="caption">
                  {d.createdTime ? new Date(d.createdTime).toLocaleString() : "—"}
                </Typography>
                <div className={styles.actions} style={{ width: 120 }}>
                  <Button onClick={() => toggleExpanded(d.instanceId)} variant="text" size="small" startIcon={isExpanded ? <ExpandLess /> : <ExpandMore />}>
                    Info
                  </Button>
                  <Button onClick={() => navigate(`/monitor/${d.instanceId}`)} variant="text" size="small" startIcon={<Visibility />}>
                    View
                  </Button>
                  <Button onClick={() => handleDelete(d.instanceId)} variant="text" size="small" startIcon={<Close />}/>
                </div>
              </div>

              {isExpanded && (<div className={styles.infoPanel}>
                  {rgName && (<div className={styles.linkGroup}>
                      <span className={styles.linkLabel}>Azure Resource Group</span>
                      <a href={links?.azurePortal || `https://portal.azure.com/#browse/resourcegroups/filterValue/${rgName}`} target="_blank" rel="noopener noreferrer" className={styles.link}>
                        <AzureBadge /> {rgName} <OpenInNew style={{ fontSize: 12 }}/>
                      </a>
                    </div>)}
                  {workspace && workspace !== "—" && (<div className={styles.linkGroup}>
                      <span className={styles.linkLabel}>Fabric Workspace</span>
                      <a href={links?.fabricWorkspace || `https://app.fabric.microsoft.com/?experience=fabric-developer`} target="_blank" rel="noopener noreferrer" className={styles.link}>
                        <FabricBadge /> {workspace} <OpenInNew style={{ fontSize: 12 }}/>
                      </a>
                    </div>)}
                  <div className={styles.linkGroup}>
                    <span className={styles.linkLabel}>Instance ID</span>
                    <Typography component="span" variant="caption" sx={{
                        fontFamily: "monospace"
                    }}>{d.instanceId}</Typography>
                  </div>
                  <div className={styles.linkGroup}>
                    <span className={styles.linkLabel}>Created</span>
                    <Typography component="span" variant="caption">
                      {d.createdTime ? new Date(d.createdTime).toLocaleString() : "—"}
                    </Typography>
                  </div>
                </div>)}
            </div>);
        })}
        {filteredDeployments.length === 0 && (<Typography style={{ textAlign: "center", padding: "28px", color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="body2">
            No runs found for the selected filter.
          </Typography>)}
      </div>
      {relatedFor && (() => {
            const base = deployments.find((run) => run.instanceId === relatedFor);
            const baseCs = base?.customStatus as Record<string, unknown> | null;
            const baseWs = (baseCs?.workspaceName as string) || "";
            const baseRg = (baseCs?.resourceGroupName as string) || "";
            const related = deployments.filter((run) => {
                if (run.instanceId === relatedFor)
                    return true;
                const cs = run.customStatus as Record<string, unknown> | null;
                return !!((baseWs && cs?.workspaceName === baseWs) || (baseRg && cs?.resourceGroupName === baseRg));
            });
            return (<div style={{ position: "fixed", right: 24, top: 96, width: 420, maxHeight: "75vh", overflow: "auto", background: "var(--m3-colorNeutralBackground1)", border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`, borderRadius: "16px", boxShadow: "0 8px 24px #00000022", zIndex: 100, padding: "24px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <Typography component="span" variant="body2" sx={{
                    fontWeight: 600
                }}>Related run timeline</Typography>
              <Button onClick={() => setRelatedFor(null)} variant="text" size="small">Close</Button>
            </div>
            <div style={{ display: "grid", gap: "12px" }}>
              {related.map((run) => {
                    const cs = run.customStatus as Record<string, unknown> | null;
                    const label = (cs?.displayName as string) || (cs?.workspaceName as string) || (cs?.resourceGroupName as string) || run.instanceId;
                    return (<Button key={run.instanceId} onClick={() => navigate(`/monitor/${run.instanceId}`)} style={{ justifyContent: "flex-start" }} variant="text">
                    {new Date(run.createdTime || "").toLocaleString()} · {run.runtimeStatus} · {label}
                  </Button>);
                })}
            </div>
          </div>);
        })()}
    </div>);
}
