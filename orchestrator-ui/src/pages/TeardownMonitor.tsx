import { Button, Card, CardHeader, Checkbox, Chip, FormControlLabel, Tooltip, Typography } from "@mui/material";
import { Cancel, CheckCircle, Close, Sync } from "@mui/icons-material";
import { makeStyles } from "@griffel/react";
import { useEffect, useState, useCallback } from "react";


import { typeBadge } from "../components/TypeBadges";
import { requestJson, requestVoid, listDeployments } from "../api";
import {
  listMockTeardowns,
  getMockTeardownInstance,
  type TeardownInstance,
} from "../mockDeployment";

const TRACK_HEIGHT = 6;
const DOT_SIZE = 22;
const DOT_BORDER = 3;
const DOT_TOTAL = DOT_SIZE + DOT_BORDER * 2;
const TRACK_CENTER = 32;
const TRACK_TOP = TRACK_CENTER - TRACK_HEIGHT / 2;
const DOT_TOP = TRACK_CENTER - DOT_TOTAL / 2;

const useStyles = makeStyles({
    container: {
        display: "flex",
        flexDirection: "column",
        gap: "28px",
    },
    instanceCard: {
        marginBottom: "24px",
    },
    milestoneTrack: {
        position: "relative" as const,
        height: "85px",
        margin: `${"16px"} ${"24px"}`,
    },
    trackLine: {
        position: "absolute" as const,
        top: `${TRACK_TOP}px`,
        left: "3%",
        right: "3%",
        height: `${TRACK_HEIGHT}px`,
        borderRadius: "3px",
        backgroundColor: "var(--m3-colorNeutralStroke2)",
        zIndex: 0,
    },
    trackFill: {
        position: "absolute" as const,
        top: `${TRACK_TOP}px`,
        right: "3%",
        height: `${TRACK_HEIGHT}px`,
        borderRadius: "3px",
        transition: "width 0.6s ease",
        zIndex: 1,
        filter: "drop-shadow(0 0 6px currentColor)",
    },
    milestoneContainer: {
        position: "absolute" as const,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        zIndex: 2,
        transform: "translateX(-50%)",
        top: `${DOT_TOP}px`,
    },
    milestoneDot: {
        width: `${DOT_TOTAL}px`,
        height: `${DOT_TOTAL}px`,
        boxSizing: "border-box",
        borderRadius: "50%",
        border: `${DOT_BORDER}px solid ${"var(--m3-colorNeutralBackground1)"}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "13px",
        fontWeight: 700,
        transition: "all 0.3s ease",
        boxShadow: "0 1px 3px #00000012",
    },
    dotPending: {
        backgroundColor: "var(--m3-colorNeutralStroke2)",
        color: "var(--m3-colorNeutralForeground4)",
    },
    dotRunning: {
        backgroundColor: "var(--m3-colorPaletteRedForeground1)",
        color: "var(--m3-colorNeutralForegroundOnBrand)",
        boxShadow: `0 0 0 3px ${"var(--m3-colorPaletteRedBackground1)"}, ${"0 2px 6px #00000016"}`,
    },
    dotDeleted: {
        backgroundColor: "var(--m3-colorPaletteRedForeground1)",
        color: "var(--m3-colorNeutralForegroundOnBrand)",
    },
    dotSkipped: {
        backgroundColor: "var(--m3-colorNeutralStroke2)",
        color: "var(--m3-colorNeutralForeground4)",
    },
    milestoneLabel: {
        marginTop: "12px",
        fontSize: "12px",
        color: "var(--m3-colorNeutralForeground3)",
        textAlign: "center" as const,
        whiteSpace: "normal" as const,
        maxWidth: "100px",
        lineHeight: "18px",
    },
    labelActive: {
        color: "var(--m3-colorPaletteRedForeground1)",
        fontWeight: 600,
    },
    logPanel: {
        maxHeight: "200px",
        overflowY: "auto" as const,
        padding: `${"12px"} ${"24px"}`,
        backgroundColor: "var(--m3-colorNeutralBackground3)",
        borderTop: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        fontFamily: "'Cascadia Code', 'Consolas', monospace",
        fontSize: "12px",
        lineHeight: "1.6",
    },
    logInfo: { color: "var(--m3-colorNeutralForeground2)" },
    logSuccess: { color: "var(--m3-colorPaletteGreenForeground1)" },
    statusRow: {
        display: "flex",
        justifyContent: "space-between",
        padding: `${"8px"} ${"24px"}`,
        borderTop: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
    },
    emptyState: {
        padding: "32px",
        textAlign: "center" as const,
        color: "var(--m3-colorNeutralForeground3)",
    },
    headerRow: {
        display: "flex",
        alignItems: "center",
        gap: "16px",
    },
});

function TeardownInstanceCard({ instance, onDismiss }: {
    instance: TeardownInstance;
    onDismiss?: () => void;
}) {
    const styles = useStyles();
    const deletedCount = instance.steps.filter((s) => s.status === "deleted").length;
    const total = instance.steps.length;
    const progressPct = total > 0 ? deletedCount / total : 0;
    const typeLabel = typeBadge(instance.candidateType);
    const statusBadge = instance.status === "completed"
        ? <Chip component="span" size="small" variant="filled" color="error" label={<>Deleted</>}/> : instance.status === "failed"
        ? <Chip component="span" size="small" variant="filled" color="warning" label={<>Failed</>}/> : <Chip component="span" size="small" variant="outlined" color="error" label={<>Deleting…</>}/>;
    return (<Card className={styles.instanceCard}>
      <CardHeader action={instance.status === "completed" && onDismiss ? (<Tooltip title={"Dismiss and archive this teardown"} describeChild>
              <Button onClick={onDismiss} variant="text" size="small" startIcon={<Close />}>
                Dismiss
              </Button>
            </Tooltip>) : undefined} title={<div className={styles.headerRow}>
            {typeLabel}
            <Typography component="span" variant="body2" sx={{
            fontWeight: "bold"
        }}>{instance.candidateName}</Typography>
            {statusBadge}
          </div>} avatar={instance.status === "completed"
            ? <CheckCircle style={{ color: "var(--m3-colorPaletteGreenForeground1)", fontSize: 24 }}/>
            : instance.status === "running"
                ? <Sync style={{ color: "var(--m3-colorPaletteRedForeground1)", fontSize: 24 }}/>
                : <Cancel style={{ color: "var(--m3-colorPaletteRedForeground1)", fontSize: 24 }}/>}/>

      {instance.status === "running" && (<div style={{ padding: `0 ${"16px"}` }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
             <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">Teardown Progress</Typography>
             <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">{deletedCount} / {total} phases</Typography>
          </div>
          <div style={{ width: "100%", height: "6px", backgroundColor: "var(--m3-colorNeutralBackground3)", borderRadius: "3px", overflow: "hidden" }}>
             <div style={{ width: `${progressPct * 100}%`, height: "100%", backgroundColor: "var(--m3-colorPaletteRedForeground1)", transition: "width 0.3s ease" }}/>
          </div>
        </div>)}
    </Card>);
}

export function TeardownMonitor() {
    const styles = useStyles();
    const [instances, setInstances] = useState<TeardownInstance[]>([]);
    const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
    const [operatorMode, setOperatorMode] = useState(false);
    // Load dismissed from backend on mount
    useEffect(() => {
        requestJson<string[]>("/api/dismissed-teardowns", { timeoutMs: 5000, retry: 1 })
            .then((ids: string[]) => {
            if (ids.length > 0)
                setDismissedIds(new Set(ids));
        })
            .catch(() => {
            try {
                const saved = localStorage.getItem("teardown-dismissed");
                if (saved)
                    setDismissedIds(new Set(JSON.parse(saved)));
            }
            catch { /* ignore */ }
        });
    }, []);
    const dismiss = (id: string) => {
        setDismissedIds((prev) => {
            const next = new Set(prev);
            next.add(id);
            // Persist to backend
            requestVoid(`/api/dismissed-teardowns/${encodeURIComponent(id)}`, { method: "POST", timeoutMs: 5000 }).catch(() => { });
            localStorage.setItem("teardown-dismissed", JSON.stringify([...next]));
            return next;
        });
    };
    const poll = useCallback(() => {
        // 1. Gather mock teardowns
        const allMocks = listMockTeardowns();
        const mockInstances = allMocks.map((inst) => getMockTeardownInstance(inst.instanceId) ?? inst);
        // 2. Fetch real teardowns from the backend
        listDeployments()
            .then((realDeployments) => {
            const realTeardowns = realDeployments.filter((d) => {
                const cs = d.customStatus;
                return ((cs?.runType as string) === "teardown" ||
                    d.name === "teardown_orchestrator" ||
                    d.instanceId.toLowerCase().startsWith("teardown"));
            });
            const mappedReal: TeardownInstance[] = realTeardowns.map((d) => {
                const cs = d.customStatus || {};
                const logs = (cs.logs as Array<{
                    level: "info" | "warn" | "error" | "success";
                    message: string;
                }>) || [];
                const outputPhases = (d as any).output?.phases || [];
                // Map backend runtimeStatus to teardown instance status
                let status: "running" | "completed" | "failed" = "running";
                if (d.runtimeStatus === "Completed")
                    status = "completed";
                else if (d.runtimeStatus === "Failed" || d.runtimeStatus === "Terminated")
                    status = "failed";
                // Map candidate type
                let candidateType: "fabric" | "azure" | "spn" = "azure";
                if (d.instanceId.toLowerCase().includes("fabric"))
                    candidateType = "fabric";
                else if (d.instanceId.toLowerCase().includes("spn"))
                    candidateType = "spn";
                return {
                    instanceId: d.instanceId,
                    candidateName: (cs.displayName as string) || d.instanceId,
                    candidateType,
                    status,
                    steps: outputPhases.map((p: any) => ({
                        name: p.phase,
                        status: p.status === "succeeded" ? "deleted" : p.status === "running" ? "running" : p.status === "skipped" ? "skipped" : "pending",
                        logs: logs.map((l) => ({
                            timestamp: d.lastUpdatedTime || new Date().toISOString(),
                            level: l.level || "info",
                            message: l.message
                        }))
                    })),
                    startedAt: d.createdTime || new Date().toISOString()
                };
            });
            // Combine both real and mock instances
            setInstances([...mappedReal, ...mockInstances]);
        })
            .catch(() => {
            // Fall back to just mock instances if API is down
            setInstances(mockInstances);
        });
    }, []);
    useEffect(() => {
        poll();
        const interval = setInterval(poll, 500);
        return () => clearInterval(interval);
    }, [poll]);
    const visible = instances.filter((i) => !dismissedIds.has(i.instanceId));
    const activeCount = visible.filter((i) => i.status === "running").length;
    const completedCount = visible.filter((i) => i.status === "completed").length;
    return (<div className={styles.container}>
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "16px" }}>
          <Typography component="div" variant="h5">Teardown Monitor</Typography>
          <FormControlLabel label={"Operator mode"} control={<Checkbox checked={operatorMode} onChange={(event) => {
                const d = { checked: event.target.checked };
                return setOperatorMode(!!d.checked);
            }}/>}/>
        </div>
        <Typography style={{ marginTop: "8px" }} component="div" variant="caption">
          {visible.length === 0
            ? "No teardowns in progress. Start one from the Teardown tab."
            : `${activeCount} active, ${completedCount} completed`}
        </Typography>
      </div>

      {visible.length === 0 && (<div className={styles.emptyState}>
          <Typography component="span" variant="body2">Select resources on the Teardown tab and click Delete to start teardown.</Typography>
        </div>)}

      {visible.map((inst) => (<TeardownInstanceCard key={inst.instanceId} instance={inst} onDismiss={() => dismiss(inst.instanceId)}/>))}
    </div>);
}
