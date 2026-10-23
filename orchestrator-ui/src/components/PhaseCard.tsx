import { Box, Button, Card, CardHeader, Chip, LinearProgress, Paper, Typography } from "@mui/material";
import { Cancel, CheckCircle, ExpandLess, ExpandMore, InfoOutlined, PauseCircleOutlined, Schedule, Sync, Warning } from "@mui/icons-material";
import { makeStyles } from "@griffel/react";
import { useState, useEffect, useRef, useCallback } from "react";


import type { PhaseInfo, PhaseSubStep, PhaseSubStepStatus } from "../api";
import { getPhaseLogs } from "../api";
import type { PhaseLog } from "../mockDeployment";
import { useReducedMotion } from "../hooks/useReducedMotion";

const useStyles = makeStyles({
    card: {
        marginBottom: "12px",
        transition: "box-shadow 0.2s ease, transform 0.15s ease",
        cursor: "pointer",
        ":hover": {
            boxShadow: "0 2px 6px #00000016",
            transform: "translateY(-1px)",
        },
        ":focus-visible": {
            outline: `2px solid ${"var(--m3-colorBrandStroke1)"}`,
            outlineOffset: "2px",
        },
    },
    cardActive: {
        border: `1px solid ${"var(--m3-colorBrandForeground1)"}`,
        boxShadow: "0 4px 12px #00000018",
    },
    row: {
        display: "flex",
        alignItems: "center",
        gap: "16px",
    },
    duration: {
        marginLeft: "auto",
        color: "var(--m3-colorNeutralForeground3)",
        fontSize: "12px",
    },
    chevron: {
        marginLeft: "12px",
        color: "var(--m3-colorNeutralForeground3)",
        fontSize: "14px",
    },
    logPanel: {
        maxHeight: "240px",
        overflowY: "auto",
        padding: `${"12px"} ${"24px"}`,
        backgroundColor: "var(--m3-colorNeutralBackground3)",
        borderTop: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        fontFamily: "'Cascadia Code', 'Consolas', 'Courier New', monospace",
        fontSize: "12px",
        lineHeight: "1.6",
    },
    logLine: {
        display: "flex",
        gap: "12px",
        alignItems: "baseline",
    },
    logTime: {
        color: "var(--m3-colorNeutralForeground4)",
        flexShrink: 0,
        minWidth: "85px",
    },
    logInfo: { color: "var(--m3-colorNeutralForeground2)" },
    logSuccess: { color: "var(--m3-colorPaletteGreenForeground1)" },
    logWarn: { color: "var(--m3-colorPaletteYellowForeground1)" },
    logError: { color: "var(--m3-colorPaletteRedForeground1)" },
    emptyLog: {
        color: "var(--m3-colorNeutralForeground4)",
        fontStyle: "italic",
    },
    warningBanner: {
        backgroundColor: "var(--m3-colorStatusWarningBackground1)",
        borderLeft: `3px solid ${"var(--m3-colorPaletteYellowForeground1)"}`,
        padding: `${"8px"} ${"16px"}`,
        fontSize: "12px",
        color: "var(--m3-colorNeutralForeground1)",
    },
    subStepPills: {
        display: "flex",
        flexWrap: "wrap" as const,
        gap: "8px",
        padding: `0 ${"24px"} ${"8px"}`,
    },
    subStepPill: {
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        maxWidth: "220px",
        padding: `2px ${"8px"}`,
        borderRadius: "999px",
        border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        backgroundColor: "var(--m3-colorNeutralBackground2)",
        fontSize: "11px",
        color: "var(--m3-colorNeutralForeground2)",
    },
    subStepPillWarning: {
        border: `1px solid ${"var(--m3-colorPaletteYellowBorderActive)"}`,
        backgroundColor: "var(--m3-colorStatusWarningBackground1)",
        color: "var(--m3-colorNeutralForeground1)",
    },
    subStepPillFailed: {
        border: `1px solid ${"var(--m3-colorPaletteRedBorderActive)"}`,
        backgroundColor: "var(--m3-colorPaletteRedBackground1)",
        color: "var(--m3-colorPaletteRedForeground1)",
    },
    subStepDetailPanel: {
        display: "flex",
        flexDirection: "column" as const,
        gap: "8px",
        padding: `${"8px"} ${"24px"}`,
        backgroundColor: "var(--m3-colorNeutralBackground2)",
        borderTop: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
    },
    subStepDetail: {
        padding: `${"8px"} ${"16px"}`,
        borderRadius: "16px",
        borderLeft: `3px solid ${"var(--m3-colorPaletteYellowBorderActive)"}`,
        backgroundColor: "var(--m3-colorStatusWarningBackground1)",
    },
    subStepDetailFailed: {
        borderLeftColor: "var(--m3-colorPaletteRedBorderActive)",
        backgroundColor: "var(--m3-colorPaletteRedBackground1)",
    },
    infoButton: {
        minWidth: "24px",
        width: "24px",
        height: "24px",
        color: "var(--m3-colorNeutralForeground3)",
    },
    infoPopoverContent: {
        maxWidth: "320px",
        whiteSpace: "normal" as const,
        lineHeight: "1.4",
    },
});

function statusIcon(status: string, hasWarnings?: boolean) {
    if (status === "succeeded" && hasWarnings) {
        return <Warning style={{ color: "var(--m3-colorPaletteYellowForeground1)" }}/>;
    }
    switch (status) {
        case "succeeded":
            return <CheckCircle style={{ color: "var(--m3-colorPaletteGreenForeground1)" }}/>;
        case "failed":
            return <Cancel style={{ color: "var(--m3-colorPaletteRedForeground1)" }}/>;
        case "running":
            return <Sync style={{ color: "var(--m3-colorPaletteBlueForeground2)" }}/>;
        case "waiting_for_input":
            return <PauseCircleOutlined style={{ color: "var(--m3-colorPaletteYellowForeground1)" }}/>;
        case "skipped":
            return <Schedule style={{ color: "var(--m3-colorNeutralForeground3)" }}/>;
        default:
            return <Schedule />;
    }
}

function statusBadge(status: string, hasWarnings?: boolean) {
    if (status === "succeeded" && hasWarnings) {
        return <Chip component="span" size="small" variant="filled" color="warning" label={<>warnings</>}/>;
    }
    const colorMap: Record<string, "success" | "error" | "info" | "warning" | "default"> = {
        succeeded: "success",
        failed: "error",
        running: "info",
        waiting_for_input: "warning",
        skipped: "default",
        pending: "default",
    };
    return <Chip component="span" size="small" variant="filled" color={colorMap[status] || "default" as any} label={<>{status}</>}/>;
}

function subStepBadgeColor(status: PhaseSubStepStatus): "success" | "error" | "info" | "warning" | "default" {
    if (status === "succeeded")
        return "success";
    if (status === "failed")
        return "error";
    if (status === "warning")
        return "warning";
    if (status === "running")
        return "info";
    return "default";
}

function subStepLabel(subStep: PhaseSubStep): string {
  const duration = formatDuration(subStep.duration);
  return duration ? `${subStep.name} · ${duration}` : subStep.name;
}

function isActionSubStep(subStep: PhaseSubStep): boolean {
  return subStep.status === "failed" || subStep.status === "warning";
}

function formatDuration(duration?: number | string): string {
  if (duration === undefined || duration === null || duration === "") return "";
  // If it's already a formatted string from the backend (e.g. "10.2 min", "0 min")
  if (typeof duration === "string") {
    // Try to parse "X.X min" format → convert to seconds
    const minMatch = duration.match(/([\d.]+)\s*min/i);
    if (minMatch) {
      const mins = parseFloat(minMatch[1]);
      if (!isNaN(mins)) {
        const totalSec = mins * 60;
        if (totalSec < 60) return `${Math.round(totalSec)}s`;
        return `${Math.floor(mins)}m ${Math.round((mins % 1) * 60)}s`;
      }
    }
    return duration; // Return as-is if we can't parse
  }
  // Numeric seconds
  if (isNaN(duration)) return "";
  if (duration < 60) return `${duration.toFixed(0)}s`;
  const mins = Math.floor(duration / 60);
  const secs = duration % 60;
  return `${mins}m ${secs.toFixed(0)}s`;
}

interface PhaseCardProps {
  phase: PhaseInfo;
  logs?: PhaseLog[];
  defaultExpanded?: boolean;
  autoScroll?: boolean;
  instanceId?: string;
}

const PHASE_TOOLTIPS: Record<string, string> = {
  "Phase 1: Fabric Workspace": "Workspace validation, capacity assignment, and managed identity provisioning",
  "Phase 1: Base Azure Infrastructure": "Event Hub, ACR, Storage, Key Vault, and Masimo emulator ACI",
  "Phase 1: FHIR Service + Synthea + Loader": "FHIR infrastructure, Synthea patients, FHIR Loader upload, and device associations",
  "Phase 1: Shared HDS Infrastructure": "Shared HDS workspace and storage prerequisites when FHIR is bypassed",
  "Phase 1: DICOM Loader": "TCIA download, patient-preserving re-tagging, ADLS upload, and FHIR ImagingStudy creation",
  "Phase 2: Fabric RTI": "Masimo Eventhouse, KQL database/functions, Eventstream topology, dashboard, and FHIR $export",
  "Phase 2: Fabric RTI (auto)": "Post-HDS bronze shortcuts, KQL shortcuts, enriched alerts, and Clinical Alerts Map",
  "Phase 3: HDS Source Deployment": "Build and deploy Microsoft HDS/DTT v1.4.0 source, publish the Fabric environment, run the master deployer, and validate managed-equivalent artifacts.",
  "Phase 3: DICOM Shortcut + HDS Pipelines": "DICOM shortcut; optional SDoH/claims sidecars; Clinical → CMA → Imaging → OMOP safe ordering; and row-count gates",
  "Phase 4: Imaging & Reporting": "Cohorting Agent, OHIF DICOM Viewer, Direct Lake imaging report, and proxy/index validation",
  "Phase 4: Ontology": "DeviceAssociation table, ClinicalDeviceOntology, and clinical agent binding",
  "Phase 4: Ontology-Aware Data Agents": "Patient 360 + Clinical Triage agents bound to ClinicalDeviceOntology",
  "Phase 5: Data Activator": "ClinicalAlertActivator Reflex + email notification rules",
  "Phase 6: CMS Quality & Claims": "Claims star schema, quality measures, Star Ratings, HCC risk, DevicePayerOntology, and Power BI report",
  "Phase 7: Payer RTI & Ops": "Claim stream, payer scoring, activator, HealthcareOpsAgent, and graph agent",
};

function defaultSubStepsForPhase(phaseName: string): PhaseSubStep[] {
  const canonical = canonicalPhaseName(phaseName);
  if (!canonical.includes("dicom shortcut") || !canonical.includes("hds pipeline")) {
    return [];
  }
  return [
    { name: "Optional SDoH/claims sidecars", status: "pending", detail: "Discovered from live Fabric DataPipeline items and invoked best-effort before the Clinical wait.", updatedAt: "" },
    { name: "Clinical Pipeline", status: "pending", detail: "Blocking Clinical/Silver readiness gate.", updatedAt: "" },
    { name: "CMA Pipeline", status: "pending", detail: "Optional non-blocking Silver consumer after Clinical/Silver readiness; does not wait for OMOP.", updatedAt: "" },
    { name: "Imaging Pipeline", status: "pending", detail: "Blocking imaging pipeline after Clinical completes.", updatedAt: "" },
    { name: "OMOP Pipeline", status: "pending", detail: "Blocking Gold OMOP pipeline after Clinical and Imaging complete.", updatedAt: "" },
  ];
}

function formatLogTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", { hour12: false });
  } catch {
    return "";
  }
}
function canonicalPhaseName(name: string): string {
  return name
    .toLowerCase()
    .replace(/^(phase\s*\d+:|\d+[a-z]?\.\s*[^:]+:)/i, "")
    .replace(/\s*\(auto\)\s*/i, "")
    .trim();
}

function getPhaseTooltip(phaseName: string): string {
  const exact = PHASE_TOOLTIPS[phaseName];
  if (exact) return exact;

  const canonical = canonicalPhaseName(phaseName);
  const match = Object.entries(PHASE_TOOLTIPS)
    .map(([key, value]) => ({ keyCanonical: canonicalPhaseName(key), value }))
    .sort((a, b) => b.keyCanonical.length - a.keyCanonical.length)
    .find(({ keyCanonical }) => canonical.includes(keyCanonical) || keyCanonical.includes(canonical));
  return match?.value ?? phaseName;
}


export function PhaseCard({ phase, logs = [], defaultExpanded, autoScroll = true, instanceId }: PhaseCardProps) {
    const styles = useStyles();
    const reducedMotion = useReducedMotion();
    const tooltip = getPhaseTooltip(phase.phase);
    const isActive = phase.status === "running" || phase.status === "waiting_for_input";
    const reportedSubSteps = phase.subSteps ?? [];
    const subSteps = reportedSubSteps.length > 0 ? reportedSubSteps : defaultSubStepsForPhase(phase.phase);
    const actionSubSteps = subSteps.filter(isActionSubStep);
    const hasWarnings = (phase.warnings?.length ?? 0) > 0 || actionSubSteps.length > 0;
    const [expanded, setExpanded] = useState(defaultExpanded ?? isActive);
    const previousStatusRef = useRef(phase.status);
    const logPanelRef = useRef<HTMLDivElement>(null);
    const followingLogs = useRef(true);
    const [fetchedLogs, setFetchedLogs] = useState<PhaseLog[] | null>(null);
    const [fetchingLogs, setFetchingLogs] = useState(false);
    const hasFetched = useRef(false);
    // Fetch per-phase logs from backend when card is expanded and we have no logs
    const fetchPhaseLogs = useCallback(async () => {
        if (!instanceId || hasFetched.current || fetchingLogs)
            return;
        if (phase.status === "pending")
            return;
        hasFetched.current = true;
        setFetchingLogs(true);
        try {
            const result = await getPhaseLogs(instanceId, phase.phase);
            if (result.length > 0) {
                setFetchedLogs(result as PhaseLog[]);
            }
        }
        catch {
            // non-fatal
        }
        finally {
            setFetchingLogs(false);
        }
    }, [instanceId, phase.phase, phase.status, fetchingLogs]);
    useEffect(() => {
        if (expanded && logs.length === 0 && !fetchedLogs && instanceId) {
            fetchPhaseLogs();
        }
    }, [expanded, logs.length, fetchedLogs, instanceId, fetchPhaseLogs]);
    const displayLogs = logs.length > 0 ? logs : (fetchedLogs ?? []);
    // Auto-expand when phase becomes active, then auto-collapse once that active work succeeds.
    useEffect(() => {
        if (isActive) {
            setExpanded(true);
        }
    }, [isActive]);
    useEffect(() => {
        const previousStatus = previousStatusRef.current;
        if (previousStatus !== phase.status) {
            if (phase.status === "succeeded") {
                setExpanded(false);
            }
            previousStatusRef.current = phase.status;
        }
    }, [phase.status]);
    // Auto-scroll only the log panel, never the whole page.
    useEffect(() => {
        if (!autoScroll || !followingLogs.current || !expanded || !logPanelRef.current)
            return;
        const panel = logPanelRef.current;
        panel.scrollTo({
            top: panel.scrollHeight,
            behavior: reducedMotion ? "auto" : "smooth",
        });
    }, [displayLogs.length, expanded, autoScroll, reducedMotion]);
    const logLevelStyle = (level: PhaseLog["level"]) => {
        switch (level) {
            case "success": return styles.logSuccess;
            case "warn": return styles.logWarn;
            case "error": return styles.logError;
            default: return styles.logInfo;
        }
    };
    const logPrefix = (level: PhaseLog["level"]) => {
        switch (level) {
            case "success": return "✓";
            case "warn": return "⚠";
            case "error": return "✗";
            default: return "›";
        }
    };
    return (<Card id={`phase-card-${phase.phase.replace(/\s+/g, "-")}`} className={`${styles.card} ${isActive ? styles.cardActive : ""}`} onClick={() => setExpanded((v) => !v)} role="button" tabIndex={0} aria-expanded={expanded} onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setExpanded((v) => !v);
            }
        }}>
        <CardHeader title={<div className={styles.row}>
              <Typography component="span" variant="body2" sx={{
            fontWeight: 600
        }}>{phase.phase}</Typography>
              {statusBadge(phase.status, hasWarnings)}
              <Typography className={styles.duration} component="span" variant="caption">
                {formatDuration(phase.duration)}
              </Typography>
              <Box component="details">
                <Box component="summary">
                  <Button className={styles.infoButton} aria-label={`About ${phase.phase}`} onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()} variant="text" size="small" startIcon={<InfoOutlined />}/>
                </Box>
                <Paper className={styles.infoPopoverContent} onClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()} elevation={3}>
                  <Typography component="div" variant="body2" sx={{
            fontWeight: 600
        }}>{phase.phase}</Typography>
                  <Typography component="span" variant="caption">{tooltip}</Typography>
                </Paper>
              </Box>
              <span className={styles.chevron}>
                {expanded ? <ExpandLess /> : <ExpandMore />}
              </span>
            </div>} avatar={statusIcon(phase.status, hasWarnings)}/>
        {phase.status === "running" && <LinearProgress variant="indeterminate"/>}
        {subSteps.length > 0 && (<div className={styles.subStepPills} aria-label="Pipeline sub-steps">
            {subSteps.map((subStep) => (<span key={subStep.name} className={`${styles.subStepPill} ${subStep.status === "failed" ? styles.subStepPillFailed : subStep.status === "warning" ? styles.subStepPillWarning : ""}`} title={subStep.detail || subStep.name}>
                <Chip component="span" size="small" variant="filled" color={subStepBadgeColor(subStep.status) as any} label={<>{subStep.status}</>}/>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{subStepLabel(subStep)}</span>
              </span>))}
          </div>)}
        {expanded && (phase.warnings?.length ?? 0) > 0 && (<div className={styles.warningBanner}>
            {(phase.warnings ?? []).map((w, i) => (<div key={i}>⚠ {w}</div>))}
          </div>)}
        {expanded && actionSubSteps.length > 0 && (<div className={styles.subStepDetailPanel}>
            {actionSubSteps.map((subStep) => (<div key={subStep.name} className={`${styles.subStepDetail} ${subStep.status === "failed" ? styles.subStepDetailFailed : ""}`}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                  <Chip component="span" size="small" variant="filled" color={subStepBadgeColor(subStep.status) as any} label={<>{subStep.status}</>}/>
                  <Typography component="span" variant="caption" sx={{
                fontWeight: 600
            }}>{subStep.name}</Typography>
                  {subStep.duration && <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">{formatDuration(subStep.duration)}</Typography>}
                  {subStep.runId && <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">run {subStep.runId}</Typography>}
                  {subStep.url && (<a href={subStep.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} style={{ color: "var(--m3-colorBrandForeground1)", fontSize: "11px" }}>
                      Open
                    </a>)}
                </div>
                {subStep.detail && (<Typography style={{ marginTop: "4px", color: "var(--m3-colorNeutralForeground2)" }} component="div" variant="caption">
                    {subStep.detail}
                  </Typography>)}
              </div>))}
          </div>)}
        {expanded && (<div className={styles.logPanel} ref={logPanelRef} tabIndex={0} aria-label={`${phase.phase} logs`} onScroll={() => { const panel = logPanelRef.current; if (panel) followingLogs.current = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 48; }}>
            {displayLogs.length === 0 && (<div className={styles.emptyLog}>
                {fetchingLogs
                    ? "Loading logs…"
                    : phase.status === "pending"
                        ? "Waiting to start…"
                        : phase.status === "succeeded" || phase.status === "skipped"
                            ? "Completed — no logs available for this phase."
                            : phase.status === "running"
                                ? "Waiting for output…"
                                : "No logs available"}
              </div>)}
            {displayLogs.map((log, i) => (<div key={i} className={styles.logLine}>
                <span className={styles.logTime}>{formatLogTime(log.timestamp)}</span>
                <span className={logLevelStyle(log.level)}>
                  {logPrefix(log.level)} {log.message}
                </span>
              </div>))}
          </div>)}
    </Card>);
}
