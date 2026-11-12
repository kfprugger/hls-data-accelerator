import { Alert, Box, Button, Card, CardHeader, Checkbox, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, FormControlLabel, FormHelperText, FormLabel, MenuItem, Radio, RadioGroup, Select, TextField, Tooltip, Typography } from "@mui/material";
import { Add, Bolt, CheckCircleOutlined, Close, ContentPaste, ExpandLess, ExpandMore, PlayArrow, RadioButtonUnchecked, Science, Settings, Sync } from "@mui/icons-material";
import { makeStyles } from "@griffel/react";
import { useState, useEffect, useMemo, useRef, type PointerEvent as ReactPointerEvent } from "react";
import { useNavigate } from "react-router-dom";


import { startDeployment, listCapacities, checkExistingDeployment, resumeCapacity, pauseCapacity, listFhirRegions, listSubscriptions, listDeployments, type DeploymentConfig, type FabricCapacity, type ExistingDeploymentInfo } from "../api";
import { startMockDeployment } from "../mockDeployment";
import { useAppState } from "../AppState";
import { HistoryInput } from "../components/HistoryInput";
import { getHistory, getTagHistory, addTagToHistory } from "../formHistory";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { AzureIcon, FabricIcon } from "../components/BrandIcons";
import { AddonFields, getAddonOptions } from "../components/AddonFields";
import { GuidedDeployment } from '../components/GuidedDeployment';
import { useDeploymentDraft } from '../DeploymentDraft';

const useStyles = makeStyles({
    form: {
        display: "flex",
        flexDirection: "column",
        gap: "24px",
        marginTop: "24px",
    },
    section: {
        marginBottom: "0",
        transition: "box-shadow 0.2s ease",
        overflow: "visible",
        ":hover": {
            boxShadow: "0 4px 12px #00000018",
        },
    },
    sectionFullWidth: {
        gridColumn: "1 / -1",
    },
    sectionHeader: {
        cursor: "default",
    },
    fieldGroup: {
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        padding: `0 ${"24px"} ${"16px"}`,
        overflow: "visible",
    },
    subscriptionRow: {
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "16px",
        overflow: "visible",
    },
    capacityFieldRow: {
        display: "flex",
        alignItems: "center",
        gap: "8px",
    },
    fieldLabelWithIcon: {
        display: "inline-flex",
        alignItems: "center",
        gap: "12px",
    },
    labelSeparator: {
        width: "1px",
        height: "14px",
        backgroundColor: "var(--m3-colorNeutralStroke2)",
        flexShrink: 0,
    },
    actions: {
        display: "flex",
        gap: "16px",
        marginTop: "32px",
    },
    error: {
        color: "var(--m3-colorStatusDangerForeground1)",
        fontSize: "12px",
        marginTop: "12px",
    },
    checkboxGroup: {
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        padding: `0 ${"24px"} ${"16px"}`,
    },
    dataStrategyControl: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        padding: "16px",
        backgroundColor: "var(--m3-colorNeutralBackground1)",
        border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        borderRadius: "16px",
    },
    dataStrategyChoice: {
        display: "flex",
        flexDirection: "column",
        gap: "4px",
    },
    dataStrategyDescription: {
        marginLeft: "32px",
        color: "var(--m3-colorNeutralForeground3)",
    },
    reseedWarning: {
        marginTop: "8px",
    },
    stickyHeader: {
        position: "sticky",
        top: 0,
        zIndex: 10,
        backgroundColor: "var(--m3-colorNeutralBackground1)",
        paddingBottom: "8px",
    },
    summarySidebar: {
        position: "sticky",
        top: "32px",
        height: "fit-content",
        maxHeight: "calc(100vh - 100px)",
        overflowY: "auto",
    },
    compactField: {
        "@media (min-width: 1200px)": {
            padding: `0 ${"16px"} ${"12px"}`,
        },
    },
    cardRequired: {
        borderLeft: `3px solid ${"var(--m3-colorBrandStroke1)"}`,
    },
    cardOptional: {
        borderLeft: `3px solid ${"var(--m3-colorNeutralStroke2)"}`,
    },
});

function TagHistoryPanel({ onSelect }: {
    onSelect: (tags: Record<string, string>) => void;
}) {
    const [tagHistory, setTagHistory] = useState<Array<Record<string, string>>>([]);
    const [loaded, setLoaded] = useState(false);
    useEffect(() => {
        getTagHistory()
            .then((h) => {
            setTagHistory(h.filter((t) => Object.keys(t).length > 0));
            setLoaded(true);
        })
            .catch(() => setLoaded(true));
    }, []);
    if (!loaded || tagHistory.length === 0)
        return null;
    return (<div style={{
            marginBottom: "12px",
            padding: `${"8px"} ${"16px"}`,
            backgroundColor: "var(--m3-colorNeutralBackground3)",
            borderRadius: "16px",
            fontSize: "12px",
        }}>
      <Typography style={{ marginBottom: "4px", display: "block" }} component="span" variant="caption" sx={{
        fontWeight: 600
    }}>
        Previously used tags:
      </Typography>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
        {tagHistory.map((tags, i) => {
            const label = Object.entries(tags).map(([k, v]) => `${k}:${v}`).join(", ");
            return (<Button key={i} onClick={() => onSelect(tags)} style={{
                    fontSize: "12px",
                    padding: `2px ${"12px"}`,
                    border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
                    borderRadius: "16px",
                }} variant="text" size="small">
              {label}
            </Button>);
        })}
      </div>
    </div>);
}

function getRectIntersection(rx: number, ry: number, rw: number, rh: number, tx: number, ty: number) {
  const cx = rx + rw / 2;
  const cy = ry + rh / 2;
  const dx = tx - cx;
  const dy = ty - cy;
  if (dx === 0 && dy === 0) return { x: cx, y: cy };

  const absDx = Math.abs(dx);
  const absDy = Math.abs(dy);
  const txLimit = rw / (2 * absDx);
  const tyLimit = rh / (2 * absDy);
  const t = Math.min(txLimit, tyLimit);

  return {
    x: cx + t * dx,
    y: cy + t * dy,
  };
}

const AZURE_REGION_LABELS: Record<string, string> = {
  australiaeast: "Australia East",
  canadacentral: "Canada Central",
  centralindia: "Central India",
  eastus: "East US",
  eastus2: "East US 2",
  francecentral: "France Central",
  germanywestcentral: "Germany West Central",
  japaneast: "Japan East",
  koreacentral: "Korea Central",
  northcentralus: "North Central US",
  northeurope: "North Europe",
  qatarcentral: "Qatar Central",
  southcentralus: "South Central US",
  southeastasia: "Southeast Asia",
  swedencentral: "Sweden Central",
  switzerlandnorth: "Switzerland North",
  uksouth: "UK South",
  westcentralus: "West Central US",
  westeurope: "West Europe",
  westus2: "West US 2",
  westus3: "West US 3",
};

function normalizeAzureLocation(location: string): string {
  return location.replace(/\s/g, "").toLowerCase();
}

function formatAzureLocationLabel(location: string): string {
  const normalized = normalizeAzureLocation(location);
  return AZURE_REGION_LABELS[normalized] ?? location;
}

function normalizeFhirRegionList(regions: string[]): string[] {
  return Array.from(new Set(regions.map(normalizeAzureLocation).filter(Boolean))).sort();
}

export function DeployWizard() {
    const styles = useStyles();
    const reducedMotion = useReducedMotion();
    const navigate = useNavigate();
    const { selectedSubscription, setSelectedSubscription, subscriptions: ctxSubscriptions, capacities: ctxCapacities, authContext } = useAppState();
    const { draft, saveDraft } = useDeploymentDraft();
    const [subscriptions, setSubscriptions] = useState<Array<{
        id: string;
        name: string;
        tenantId?: string;
    }>>([]);
    const [loading, setLoading] = useState(false);
    const [deploymentStartMessage, setDeploymentStartMessage] = useState("");
    const [error, setError] = useState("");
    const [capacities, setCapacities] = useState<FabricCapacity[]>([]);
    const [selectedCapacity, setSelectedCapacity] = useState(draft?.selectedCapacity || '');
    const [pauseAfterDeploy, setPauseAfterDeploy] = useState(draft?.pauseAfterDeploy || false);
    const [capacityRefreshing, setCapacityRefreshing] = useState(false);
    const [resumingCapacity, setResumingCapacity] = useState(false);
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [existingDeployCollapsed, setExistingDeployCollapsed] = useState(false);
    const [showSummary] = useState(true);
    const [initializing, setInitializing] = useState(true);
    const [loadWarning, setLoadWarning] = useState("");
    const [showResourcePreview, setShowResourcePreview] = useState(false);
    const [resourcePreviewMode, setResourcePreviewMode] = useState<"cards" | "graph">("cards");
    const [resourceGraphZoom, setResourceGraphZoom] = useState(1);
    const [graphNodeOffsets, setGraphNodeOffsets] = useState<Record<string, {
        x: number;
        y: number;
    }>>({});
    const [graphLabelOffsets, setGraphLabelOffsets] = useState<Record<string, {
        x: number;
        y: number;
    }>>({});
    const [graphDrag, setGraphDrag] = useState<{
        kind: "node" | "label" | "pan";
        id: string;
        startX: number;
        startY: number;
        baseX: number;
        baseY: number;
    } | null>(null);
    const graphDragRef = useRef<{
        kind: "node" | "label" | "pan";
        id: string;
        startX: number;
        startY: number;
        baseX: number;
        baseY: number;
    } | null>(null);
    const miniMapDraggingRef = useRef(false);
    const [spacePressed, setSpacePressed] = useState(false);
    const [deepCheckingExisting, setDeepCheckingExisting] = useState(false);
    const [fhirRegions, setFhirRegions] = useState<string[] | null>(null); // null = not loaded yet
    const [skipGroup1Collapsed, setSkipGroup1Collapsed] = useState(false);
    const [skipGroup2Collapsed, setSkipGroup2Collapsed] = useState(false);
    const [skipGroup3Collapsed, setSkipGroup3Collapsed] = useState(false);
    const [skipGroup4Collapsed, setSkipGroup4Collapsed] = useState(false);
    const [autoExportXlsx, setAutoExportXlsx] = useState(() => localStorage.getItem("autoExportXlsx") === "true");
    const [autoExportCsv, setAutoExportCsv] = useState(() => localStorage.getItem("autoExportCsv") === "true");
    useEffect(() => {
        localStorage.setItem("autoExportXlsx", String(autoExportXlsx));
    }, [autoExportXlsx]);
    useEffect(() => {
        localStorage.setItem("autoExportCsv", String(autoExportCsv));
    }, [autoExportCsv]);
    const graphContainerRef = useRef<HTMLDivElement>(null);
    const [scrollState, setScrollState] = useState({
        scrollLeft: 0,
        scrollTop: 0,
        clientWidth: 0,
        clientHeight: 0,
    });
    const [miniMapDragging, setMiniMapDragging] = useState(false);
    const [miniMapCollapsed, setMiniMapCollapsed] = useState(false);
    const handleGraphScroll = () => {
        const el = graphContainerRef.current;
        if (el) {
            setScrollState({
                scrollLeft: el.scrollLeft,
                scrollTop: el.scrollTop,
                clientWidth: el.clientWidth,
                clientHeight: el.clientHeight,
            });
        }
    };
    useEffect(() => {
        if (showResourcePreview && resourcePreviewMode === "graph") {
            const timer = setTimeout(() => {
                handleGraphScroll();
            }, 60);
            return () => clearTimeout(timer);
        }
    }, [showResourcePreview, resourcePreviewMode, resourceGraphZoom]);
    useEffect(() => {
        if (!showResourcePreview || resourcePreviewMode !== "graph") {
            setSpacePressed(false);
            return;
        }
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.code === "Space" && !["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement)?.tagName || "")) {
                e.preventDefault();
                setSpacePressed(true);
            }
        };
        const onKeyUp = (e: KeyboardEvent) => {
            if (e.code === "Space") {
                setSpacePressed(false);
            }
        };
        window.addEventListener("keydown", onKeyDown);
        window.addEventListener("keyup", onKeyUp);
        return () => {
            window.removeEventListener("keydown", onKeyDown);
            window.removeEventListener("keyup", onKeyUp);
        };
    }, [showResourcePreview, resourcePreviewMode]);
    const handleMiniMapPointer = (event: React.PointerEvent<SVGSVGElement> | ReactPointerEvent) => {
        const el = graphContainerRef.current;
        if (!el)
            return;
        const rect = event.currentTarget.getBoundingClientRect();
        const clickX = ((event.clientX - rect.left) / rect.width) * GRAPH_WIDTH;
        const clickY = ((event.clientY - rect.top) / rect.height) * GRAPH_HEIGHT;
        const nextLeft = clickX * resourceGraphZoom - el.clientWidth / 2;
        const nextTop = clickY * resourceGraphZoom - el.clientHeight / 2;
        el.scrollTo({
            left: Math.max(0, nextLeft),
            top: Math.max(0, nextTop),
            behavior: "auto",
        });
        setScrollState({
            scrollLeft: el.scrollLeft,
            scrollTop: el.scrollTop,
            clientWidth: el.clientWidth,
            clientHeight: el.clientHeight,
        });
    };
    const handleMiniMapPointerDown = (event: ReactPointerEvent) => {
        miniMapDraggingRef.current = true;
        setMiniMapDragging(true);
        try { event.currentTarget.setPointerCapture(event.pointerId); } catch {}
        handleMiniMapPointer(event);
    };
    const handleMiniMapPointerMove = (event: ReactPointerEvent) => {
        if (miniMapDraggingRef.current || miniMapDragging) {
            handleMiniMapPointer(event);
        }
    };
    const handleMiniMapPointerUp = (event: ReactPointerEvent) => {
        miniMapDraggingRef.current = false;
        setMiniMapDragging(false);
        try { event.currentTarget.releasePointerCapture(event.pointerId); } catch {}
    };
    const getCapacitySelectionValue = (capacity: FabricCapacity) => {
        return capacity.id || `${capacity.subscription}:${capacity.resourceGroup}:${capacity.name}`;
    };
    const getShortSubscriptionId = (subscriptionId?: string) => {
        if (!subscriptionId)
            return "";
        return subscriptionId.slice(0, 8);
    };
    const getCapacityFallbackParts = (value: string) => {
        if (!value)
            return null;
        if (value.startsWith("/subscriptions/")) {
            const segments = value.split("/").filter(Boolean);
            const subscriptionId = segments[1] ?? "";
            const capacityName = segments[segments.length - 1] ?? value;
            return { capacityName, subscriptionId, subscriptionName: "" };
        }
        const parts = value.split(":");
        if (parts.length >= 3) {
            return {
                subscriptionId: parts[0],
                subscriptionName: "",
                capacityName: parts[2],
            };
        }
        return {
            subscriptionId: "",
            subscriptionName: "",
            capacityName: value,
        };
    };
    const formatSubscriptionReference = (subscriptionName?: string, subscriptionId?: string) => {
        const shortId = getShortSubscriptionId(subscriptionId);
        if (subscriptionName && shortId)
            return `${subscriptionName} (${shortId})`;
        if (subscriptionName)
            return subscriptionName;
        if (shortId)
            return `Sub ${shortId}`;
        return "";
    };
    const isTrialCapacity = (capacity: FabricCapacity) => (capacity.sku ?? "").toUpperCase().startsWith("FT");
    const isUsableCapacity = (capacity: FabricCapacity) => {
        const sku = (capacity.sku ?? "").toUpperCase();
        return sku.startsWith("F") && !sku.startsWith("FT") && sku !== "PP3";
    };
    const usableCapacities = capacities.filter(isUsableCapacity);
    const onlyTrialCapacitiesDetected = capacities.length > 0 && capacities.every(isTrialCapacity);
    const formatCapacityRegionLabel = (capacity: FabricCapacity) => {
        const region = capacity.location ? formatAzureLocationLabel(capacity.location) : "Unknown region";
        return region;
    };
    const formatCapacityMenuLabel = (capacity: FabricCapacity) => {
        const subscriptionLabel = formatSubscriptionReference(capacity.subscriptionName, capacity.subscription);
        const regionLabel = formatCapacityRegionLabel(capacity);
        const suffix = subscriptionLabel ? ` • ${subscriptionLabel}` : "";
        return `${capacity.name} — ${capacity.sku} (${capacity.state ?? "Unknown"}) • ${regionLabel}${suffix}`;
    };
    const formatSelectedCapacityLabel = (value: string) => {
        const capacity = findCapacity(value);
        if (capacity) {
            const subscriptionLabel = formatSubscriptionReference(capacity.subscriptionName, capacity.subscription);
            const regionLabel = formatCapacityRegionLabel(capacity);
            return subscriptionLabel ? `${capacity.name} — ${regionLabel} (${subscriptionLabel})` : `${capacity.name} — ${regionLabel}`;
        }
        const fallback = getCapacityFallbackParts(value);
        if (!fallback)
            return "";
        const subscriptionLabel = formatSubscriptionReference(fallback.subscriptionName, fallback.subscriptionId);
        return subscriptionLabel ? `${fallback.capacityName} (${subscriptionLabel})` : fallback.capacityName;
    };
    const findCapacity = (value: string) => {
        return capacities.find((capacity) => {
            const selectionValue = getCapacitySelectionValue(capacity);
            return selectionValue === value || capacity.name === value;
        });
    };
    const refreshCapacities = () => {
        if (subscriptions.length === 0)
            return;
        setCapacityRefreshing(true);
        listCapacities()
            .then((allCaps) => {
            setCapacities(allCaps);
            // Update selected capacity state if it still exists
            if (selectedCapacity) {
                const updated = allCaps.find((capacity) => {
                    const selectionValue = getCapacitySelectionValue(capacity);
                    return selectionValue === selectedCapacity || capacity.name === selectedCapacity;
                });
                if (updated && selectedCapacity !== getCapacitySelectionValue(updated)) {
                    setSelectedCapacity(getCapacitySelectionValue(updated));
                }
                else if (!updated) {
                    setSelectedCapacity("");
                }
            }
            if (allCaps.length === 0) {
                setError("Unable to load Fabric capacities right now.");
                setLoadWarning("Unable to load Fabric capacities right now.");
            }
            else if (allCaps.every(isTrialCapacity)) {
                setError("Only Fabric trial capacities (FT*) were detected. Healthcare Data Solutions requires a paid Fabric F-SKU capacity.");
                setLoadWarning("Only Fabric trial capacities (FT*) were detected. Select or create a paid Fabric F-SKU capacity before deploying.");
            }
            else {
                setError("");
                setLoadWarning("");
            }
        })
            .catch(() => {
            setError("Failed to refresh capacity state. Try again.");
            setLoadWarning("Unable to load Fabric capacities right now.");
        })
            .finally(() => setCapacityRefreshing(false));
    };
    // Fetch real subscriptions on mount — prefer context prefetch if available
    useEffect(() => {
        if (ctxSubscriptions.length > 0) {
            setSubscriptions(ctxSubscriptions);
            if (!selectedSubscription)
                setSelectedSubscription(ctxSubscriptions[0].id);
            return;
        }
        listSubscriptions()
            .then((subs) => {
            if (subs.length > 0) {
                setSubscriptions(subs);
                setLoadWarning("");
                if (!selectedSubscription) {
                    setSelectedSubscription(subs[0].id);
                }
            }
            else {
                setSubscriptions([]);
                setLoadWarning("Sign in to Azure to load your accessible subscriptions.");
                setInitializing(false);
            }
        })
            .catch(() => {
            setSubscriptions([]);
            setLoadWarning("Live Azure subscription scan unavailable. Sign in and refresh to retry.");
            setInitializing(false);
        });
    }, [ctxSubscriptions]); // eslint-disable-line react-hooks/exhaustive-deps
    // Fetch Fabric capacities across all subscriptions
    useEffect(() => {
        if (subscriptions.length === 0)
            return;
        // Seed from the app-wide prefetch if available, then refresh in background.
        // Do NOT auto-select a capacity — the user must choose one explicitly so this
        // UI is safe to use across multiple users / tenants without leaking a default.
        if (ctxCapacities.length > 0 && capacities.length === 0) {
            setCapacities(ctxCapacities);
            setLoadWarning("");
            setInitializing(false);
            return;
        }
        setCapacityRefreshing(true);
        // Scan all accessible subscriptions since the capacity may live outside the currently selected Azure context.
        listCapacities()
            .then((allCaps) => {
            setCapacities(allCaps);
            if (allCaps.length === 0) {
                setLoadWarning("Unable to load Fabric capacities right now.");
            }
            else if (allCaps.every(isTrialCapacity)) {
                setLoadWarning("Only Fabric trial capacities (FT*) were detected. Healthcare Data Solutions requires a paid Fabric F-SKU capacity.");
            }
            else {
                setLoadWarning("");
            }
        })
            .catch(() => {
            setCapacities([]);
            setLoadWarning("Unable to load Fabric capacities right now.");
        })
            .finally(() => {
            setCapacityRefreshing(false);
            setInitializing(false);
        });
    }, [subscriptions]); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (!selectedCapacity || capacities.length === 0)
            return;
        const matched = capacities.find((capacity) => {
            const selectionValue = getCapacitySelectionValue(capacity);
            return selectionValue === selectedCapacity || capacity.name === selectedCapacity;
        });
        if (matched && selectedCapacity !== getCapacitySelectionValue(matched)) {
            setSelectedCapacity(getCapacitySelectionValue(matched));
        }
    }, [capacities, selectedCapacity]); // eslint-disable-line react-hooks/exhaustive-deps
    // Fetch AHDS FHIR-supported regions once on mount (independent of mock mode).
    // Falls back to the currently published FHIR service region list when the
    // backend is unreachable so validation still works in mock / offline mode.
    const FHIR_FALLBACK_REGIONS = [
        "australiaeast", "canadacentral", "centralindia", "eastus", "eastus2",
        "francecentral", "germanywestcentral", "japaneast", "koreacentral",
        "northcentralus", "northeurope", "qatarcentral", "southcentralus",
        "southeastasia", "swedencentral", "switzerlandnorth", "uksouth",
        "westcentralus", "westeurope", "westus2", "westus3",
    ];
    useEffect(() => {
        listFhirRegions().then((regions) => {
            setFhirRegions(normalizeFhirRegionList(regions.length > 0 ? regions : FHIR_FALLBACK_REGIONS));
        });
    }, []); // eslint-disable-line react-hooks/exhaustive-deps
    const supportedFhirRegionIds = useMemo(() => new Set((fhirRegions ?? []).map(normalizeAzureLocation)), [fhirRegions]);
    const fhirRegionLabels = useMemo(() => (fhirRegions ?? []).map(formatAzureLocationLabel), [fhirRegions]);
    const [showJsonEditor, setShowJsonEditor] = useState(false);
    const [config, setConfig] = useState<DeploymentConfig>(draft?.config || {
        expected_tenant_id: "",
        expected_subscription_id: "",
        resource_group_name: "",
        location: "eastus",
        admin_security_group: "",
        fabric_workspace_name: "",
        patient_count: 100,
        tags: { SecurityControl: "Ignore" },
        scaffolding_only: false,
        skip_base_infra: false,
        skip_fhir: false,
        skip_dicom: false,
        skip_fabric: false,
        alert_email: "",
        capacity_subscription_id: "",
        capacity_resource_group: "",
        capacity_name: "",
        pause_capacity_after_deploy: false,
        reuse_patients: false,
        reseed_data: false,
        use_cached_synthea: false,
        // Granular component toggles
        skip_synthea: false,
        skip_device_assoc: false,
        skip_fhir_export: false,
        skip_rti_phase2: false,
        skip_hds_pipelines: false,
        skip_hds_source: false,
        skip_data_agents: false,
        skip_imaging: false,
        skip_ontology: false,
        skip_activator: false,
        skip_quality_measures: false,
        require_bronze_clinical_fhir: false,
        require_bronze_imaging_dicom: false,
        skip_phase7: false,
        skip_payer_rti: false,
        skip_payer_activator: false,
        skip_ops_agent: false,
        skip_graph_agent: false,
        payer_ops_email: "",
        claim_event_rate_per_minute: 60,
        ...getAddonOptions(),
    });
    useEffect(() => {
        const subscriptionId = selectedSubscription || authContext?.cli.subscriptionId || authContext?.pwsh.subscriptionId || "";
        const tenantId = subscriptions.find((item) => item.id === subscriptionId)?.tenantId
            || ctxSubscriptions.find((item) => item.id === subscriptionId)?.tenantId
            || authContext?.cli.tenantId || authContext?.pwsh.tenantId || "";
        setConfig((current) => ({ ...current, expected_tenant_id: tenantId, expected_subscription_id: subscriptionId }));
    }, [authContext, selectedSubscription, subscriptions, ctxSubscriptions]);
    const [useNamingConvention, setUseNamingConvention] = useState(draft?.useNamingConvention ?? true);
    const [useTags, setUseTags] = useState(true);
    const [tagRows, setTagRows] = useState<Array<{
        name: string;
        value: string;
    }>>(Object.entries(draft?.config.tags || { SecurityControl: 'Ignore' }).map(([name, value]) => ({ name, value })));
    const [namingPrefix, setNamingPrefix] = useState(draft?.namingPrefix || '');
    const [lastWorkspaceName, setLastWorkspaceName] = useState("");
    const hydratedTargetRef = useRef("");
    useEffect(() => {
        const activeSub = (selectedSubscription || authContext?.cli.subscriptionId || authContext?.pwsh.subscriptionId || "").trim().toLowerCase();
        const activeTid = (subscriptions.find((item) => item.id === selectedSubscription)?.tenantId
            || ctxSubscriptions.find((item) => item.id === selectedSubscription)?.tenantId
            || authContext?.cli.tenantId || authContext?.pwsh.tenantId || "").trim().toLowerCase();
        const hydrateKey = `${activeTid}:${activeSub}`;
        if (hydratedTargetRef.current === hydrateKey)
            return;
        let cancelled = false;
        Promise.all([
            listDeployments().catch(() => []),
            getHistory("naming-prefix").catch(() => []),
            getHistory("location").catch(() => []),
            getHistory("admin-security-group").catch(() => []),
            getHistory("alert-email").catch(() => []),
            getHistory("payer-ops-email").catch(() => []),
            getHistory("cardiology-location").catch(() => []),
            getHistory("cardiology-app-users").catch(() => []),
            getHistory("cardiology-reviewer-users").catch(() => []),
            getTagHistory().catch(() => []),
        ]).then(([deps, prefixHist, locHist, groupHist, alertHist, payerHist, cardioLocHist, cardioUsersHist, cardioRevHist, tagHist]) => {
            if (cancelled)
                return;
            hydratedTargetRef.current = hydrateKey;
            const deployRuns = deps.filter((d) => {
                const cs = (d.customStatus ?? {}) as Record<string, unknown>;
                return d.name !== "teardown_orchestrator" && cs.runType !== "teardown" && cs.runType !== "teardownBatch";
            });
            const matchingRun = deployRuns.find((d) => {
                const cs = (d.customStatus ?? {}) as Record<string, unknown>;
                const dc = (cs.deployConfig ?? {}) as Partial<DeploymentConfig>;
                const runSub = String(dc.expected_subscription_id || cs.subscriptionId || cs.capacitySubscriptionId || "").trim().toLowerCase();
                const runTid = String(dc.expected_tenant_id || "").trim().toLowerCase();
                if (activeSub && runSub)
                    return runSub === activeSub;
                if (activeTid && runTid)
                    return runTid === activeTid;
                return false;
            }) || deployRuns[0];

            const cs = ((matchingRun?.customStatus ?? {}) as Record<string, unknown>);
            const pc = ((cs.deployConfig ?? {}) as Partial<DeploymentConfig>);
            const latestWs = String(pc.fabric_workspace_name || cs.workspaceName || prefixHist[0] || "").trim();
            if (latestWs) {
                setLastWorkspaceName(latestWs);
            }

            const savedCap = String(pc.capacity_name || cs.capacityName || "").trim();
            setSelectedCapacity((prev) => prev || savedCap);
            setConfig((prev) => {
                const nextLoc = prev.location && prev.location !== "eastus" ? prev.location : (pc.location || locHist[0] || prev.location);
                const nextGroup = prev.admin_security_group || pc.admin_security_group || groupHist[0] || "";
                const nextAlert = prev.alert_email || pc.alert_email || alertHist[0] || "";
                const nextPayer = prev.payer_ops_email || pc.payer_ops_email || payerHist[0] || "";
                const nextCardioLoc = prev.cardiology_location && prev.cardiology_location !== "eastus2"
                    ? prev.cardiology_location
                    : (pc.cardiology_location || cardioLocHist[0] || prev.cardiology_location || "eastus2");
                const nextCardioUsers = (prev.cardiology_app_users && prev.cardiology_app_users.length > 0)
                    ? prev.cardiology_app_users
                    : (pc.cardiology_app_users && pc.cardiology_app_users.length > 0 ? pc.cardiology_app_users : cardioUsersHist);
                const nextCardioRev = (prev.cardiology_reviewer_users && prev.cardiology_reviewer_users.length > 0)
                    ? prev.cardiology_reviewer_users
                    : (pc.cardiology_reviewer_users && pc.cardiology_reviewer_users.length > 0 ? pc.cardiology_reviewer_users : (cardioRevHist.length > 0 ? cardioRevHist : nextCardioUsers));
                return {
                    ...prev,
                    location: nextLoc,
                    admin_security_group: nextGroup,
                    alert_email: nextAlert,
                    payer_ops_email: nextPayer,
                    capacity_name: prev.capacity_name || savedCap,
                    capacity_resource_group: prev.capacity_resource_group || String(pc.capacity_resource_group || cs.capacityResourceGroup || ""),
                    capacity_subscription_id: prev.capacity_subscription_id || String(pc.capacity_subscription_id || cs.capacitySubscriptionId || ""),
                    databricks_environment: prev.databricks_environment || pc.databricks_environment || "dev",
                    databricks_admin_group: prev.databricks_admin_group || pc.databricks_admin_group || "",
                    cardiology_location: nextCardioLoc,
                    cardiology_app_users: nextCardioUsers,
                    cardiology_reviewer_users: nextCardioRev,
                    cardiology_chat_model: prev.cardiology_chat_model || pc.cardiology_chat_model || "",
                    cardiology_chat_model_version: prev.cardiology_chat_model_version || pc.cardiology_chat_model_version || "",
                };
            });
            const restoredTags = (pc.tags && Object.keys(pc.tags).length > 0)
                ? pc.tags
                : (tagHist[0] && Object.keys(tagHist[0]).length > 0 ? tagHist[0] : null);
            if (restoredTags) {
                setTagRows((prev) => {
                    const isDefaultOnly = prev.length === 1 && prev[0].name === "SecurityControl" && prev[0].value === "Ignore";
                    if (!isDefaultOnly)
                        return prev;
                    return Object.entries(restoredTags).map(([name, value]) => ({ name, value }));
                });
            }
        });
        return () => {
            cancelled = true;
        };
    }, [selectedSubscription, authContext, subscriptions, ctxSubscriptions]);
    useEffect(() => {
        saveDraft({ config, namingPrefix, useNamingConvention, selectedCapacity, pauseAfterDeploy });
    }, [config, namingPrefix, useNamingConvention, selectedCapacity, pauseAfterDeploy, saveDraft]);
    const [existingDeploy, setExistingDeploy] = useState<ExistingDeploymentInfo | null>(null);
    const [checkingExisting, setCheckingExisting] = useState(false);
    const [overridePriorSettings, setOverridePriorSettings] = useState(false);
    // Determine which card needs attention next
    const activeCardIndex = useNamingConvention && !namingPrefix ? 0
        : !useNamingConvention && (!config.resource_group_name || !config.fabric_workspace_name) ? 1
            : !selectedCapacity || !config.admin_security_group ? 1
                : !config.fabric_workspace_name && !useNamingConvention ? 2
                    : !config.patient_count || (!config.skip_activator && !config.alert_email?.trim()) ? 3
                        : -1; // all filled — no glow
    // Calculate completion status for cards
    const getCardCompletion = (cardIndex: number): {
        complete: number;
        total: number;
    } => {
        switch (cardIndex) {
            case 0: // Naming
                return { complete: (!useNamingConvention || !!namingPrefix) ? 1 : 0, total: 1 };
            case 1: // Azure Config
                const azureFields = [selectedSubscription, selectedCapacity, config.admin_security_group];
                if (!useNamingConvention)
                    azureFields.push(config.resource_group_name);
                return { complete: azureFields.filter(Boolean).length, total: azureFields.length };
            case 2: // Fabric Config
                return { complete: config.fabric_workspace_name ? 1 : 0, total: 1 };
            case 3: // Data Config
                const requiredDataFields: (string | number | null)[] = [config.patient_count];
                if (!config.skip_activator) {
                    requiredDataFields.push(config.alert_email?.trim() || null);
                }
                if (!config.skip_phase7 && !config.skip_payer_activator) {
                    requiredDataFields.push(config.payer_ops_email?.trim() || config.alert_email?.trim() || null);
                }
                return { complete: requiredDataFields.filter(Boolean).length, total: requiredDataFields.length };
            default:
                return { complete: 0, total: 0 };
        }
    };
    // Estimated duration — medians from 17 historical runs (med-0714..0720).
    // HDS phase is decomposed: a DICOM-independent base (clinical + OMOP ingestion,
    // shortcuts, row gates ~34m) plus the imaging ingestion sub-pipeline (~25m) that
    // only fires when DICOM data exists — mirrors deploy_hds_pipelines.run gating.
    const getEstimatedDurationMinutes = (): number => {
        let minutes = 3; // base Azure infrastructure
        if (!config.skip_fhir)
            minutes += 6 + (config.skip_synthea ? 0 : Math.ceil(config.patient_count / 10));
        if (!config.skip_fhir && !config.skip_synthea && config.use_cached_synthea)
            minutes -= 8;
        if (!config.skip_fhir && !config.skip_device_assoc)
            minutes += 1;
        if (!config.skip_dicom)
            minutes += 8;
        if (!config.skip_fabric)
            minutes += 1;
        if (!config.skip_fabric && !config.skip_rti_phase2)
            minutes += 13;
        if (config.scaffolding_only)
            minutes += 45; // HDS source artifact publication without pipeline runs
        if (!config.skip_hds_pipelines) {
            minutes += 34; // clinical + OMOP ingestion, shortcuts, row gates
            if (!config.skip_dicom)
                minutes += 25; // imaging ingestion sub-pipeline
        }
        if (!config.skip_imaging)
            minutes += 9;
        if (!config.skip_ontology)
            minutes += 4;
        if (!config.skip_data_agents)
            minutes += 1;
        if (!config.skip_activator)
            minutes += 1;
        if (!config.skip_quality_measures)
            minutes += 4;
        if (!config.skip_phase7)
            minutes += 46;
        return Math.max(3, minutes);
    };
    const getEstimatedDuration = (): string => {
        const minutes = getEstimatedDurationMinutes();
        return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m`;
    };
    const applyPreset = (preset: "demo" | "full" | "scaffold" | "infra" | "repair" | "data") => {
        setShowAdvanced(preset !== "demo");
        setConfig((prev) => {
            const base: DeploymentConfig = {
                ...prev,
                // Presets must never override a patient count the user explicitly entered.
                // Only supply a preset default when no value is set yet.
                patient_count: prev.patient_count || (preset === "demo" ? 25 : 100),
                scaffolding_only: false,
                skip_base_infra: false,
                skip_fhir: false,
                skip_dicom: false,
                skip_fabric: false,
                skip_synthea: false,
                skip_device_assoc: false,
                skip_fhir_export: false,
                skip_rti_phase2: false,
                skip_hds_source: false,
                skip_hds_pipelines: false,
                skip_data_agents: false,
                skip_imaging: false,
                skip_ontology: false,
                skip_activator: !prev.alert_email,
                skip_quality_measures: false,
                skip_phase7: false,
                skip_payer_rti: false,
                skip_payer_activator: !prev.alert_email && !prev.payer_ops_email,
                skip_ops_agent: false,
                skip_graph_agent: false,
                payer_ops_email: prev.payer_ops_email || "",
                claim_event_rate_per_minute: prev.claim_event_rate_per_minute || 60,
            };
            if (preset === "demo") {
                return { ...base, skip_imaging: true, skip_quality_measures: true, skip_payer_activator: !prev.alert_email && !prev.payer_ops_email };
            }
            if (preset === "scaffold") {
                return {
                    ...base,
                    scaffolding_only: true,
                    reuse_patients: false,
                    reseed_data: false,
                    use_cached_synthea: false,
                    skip_synthea: true,
                    skip_device_assoc: true,
                    skip_dicom: true,
                    skip_fhir_export: true,
                    skip_rti_phase2: true,
                    skip_hds_pipelines: true,
                    skip_data_agents: true,
                    skip_imaging: true,
                    skip_ontology: true,
                    skip_activator: true,
                    skip_quality_measures: true,
                    skip_payer_activator: true,
                };
            }
            if (preset === "infra") {
                return {
                    ...base,
                    reuse_patients: false,
                    reseed_data: false,
                    skip_fhir: true,
                    skip_dicom: true,
                    skip_fabric: true,
                    skip_synthea: true,
                    skip_device_assoc: true,
                    skip_fhir_export: true,
                    skip_rti_phase2: true,
                    skip_hds_pipelines: true,
                    skip_data_agents: true,
                    skip_hds_source: true,
                    skip_imaging: true,
                    skip_ontology: true,
                    skip_activator: true,
                    skip_quality_measures: true,
                    skip_phase7: true,
                    skip_payer_rti: true,
                    skip_payer_activator: true,
                    skip_ops_agent: true,
                    skip_graph_agent: true,
                };
            }
            if (preset === "repair") {
                return { ...base, reuse_patients: true, reseed_data: false, skip_synthea: true, skip_device_assoc: true, skip_phase7: true, skip_payer_rti: true, skip_payer_activator: true, skip_ops_agent: true, skip_graph_agent: true };
            }
            if (preset === "data") {
                return { ...base, reuse_patients: false, reseed_data: false, skip_base_infra: true, skip_fhir: true, skip_dicom: true, skip_synthea: true, skip_device_assoc: true, skip_phase7: true, skip_payer_rti: true, skip_payer_activator: true, skip_ops_agent: true, skip_graph_agent: true };
            }
            return { ...base, skip_activator: false, skip_payer_activator: false };
        });
    };
    const enabledComponents = [
        [!config.skip_base_infra, "Infrastructure"],
        [config.scaffolding_only, "Zero-data scaffolding"],
        [!config.skip_fhir, "FHIR"],
        [!config.skip_synthea, "Synthea"],
        [!config.skip_dicom, "DICOM"],
        [!config.skip_fabric, "Fabric RTI"],
        [!config.skip_hds_source, "Microsoft HDS source artifacts"],
        [!config.skip_hds_pipelines, "HDS Pipelines"],
        [!config.skip_data_agents, "Data Agents"],
        [!config.skip_imaging, "Imaging"],
        [!config.skip_ontology, "Ontology"],
        [!config.skip_activator && !!config.alert_email, "Alerts"],
        [!config.skip_quality_measures, "Quality"],
        [!config.skip_phase7 && !config.skip_payer_rti, "Payer RTI"],
        [!config.skip_phase7 && !config.skip_payer_activator, "Payer Activator"],
        [!config.skip_phase7 && !config.skip_ops_agent, "Ops Agents"],
        [!config.skip_phase7 && !config.skip_graph_agent, "Graph Agent"],
    ].filter(([enabled]) => enabled).map(([, label]) => label as string);
    const uniqueSuffix = "<rg-hash>";
    const appName = `masimo-${uniqueSuffix}`;
    const hdsWorkspaceName = `hdws-${uniqueSuffix}`;
    const fhirServiceName = `fhir-${uniqueSuffix}`;
    const storageAccountName = `stfhir${uniqueSuffix}`;
    const prospectiveAzureAssets = [
        { enabled: true, section: "Core & Security", type: "Resource group", name: config.resource_group_name || "rg-<deployment>" },
        { enabled: !config.skip_base_infra, section: "Core & Security", type: "Key Vault", name: `${appName}-kv` },
        { enabled: !config.skip_base_infra, section: "Core & Security", type: "Container Registry", name: `${appName}acr` },
        { enabled: !config.skip_fhir, section: "Core & Security", type: "Managed Identity", name: "id-aci-fhir-jobs" },
        { enabled: !config.skip_fhir, section: "Clinical & Storage", type: "AHDS Workspace", name: hdsWorkspaceName },
        { enabled: !config.skip_fhir, section: "Clinical & Storage", type: "FHIR R4 Service", name: fhirServiceName },
        { enabled: !config.skip_fhir, section: "Clinical & Storage", type: "ADLS Gen2 Storage", name: storageAccountName },
        { enabled: !config.skip_fhir, section: "Clinical & Storage", type: "Blob Container", name: "synthea-output" },
        { enabled: !config.skip_fhir, section: "Clinical & Storage", type: "Blob Container", name: "fhir-export" },
        { enabled: !config.skip_dicom, section: "Clinical & Storage", type: "Blob Container", name: "dicom-output" },
        { enabled: !config.skip_base_infra, section: "Streaming & Producers", type: "Event Hubs Namespace", name: `${appName}-eh-ns` },
        { enabled: !config.skip_base_infra, section: "Streaming & Producers", type: "Event Hub", name: "telemetry-stream" },
        { enabled: !config.skip_phase7 && !config.skip_payer_rti && !config.skip_base_infra, section: "Streaming & Producers", type: "Event Hub", name: "claim-stream" },
        { enabled: !config.skip_base_infra, section: "Streaming & Producers", type: "SAS Auth Rule", name: "emulator-access" },
        { enabled: !config.scaffolding_only && !config.skip_base_infra, section: "Streaming & Producers", type: "ACI Container Group", name: "masimo-emulator-grp" },
        { enabled: !config.scaffolding_only && !config.skip_phase7 && !config.skip_payer_rti && !config.skip_base_infra, section: "Streaming & Producers", type: "ACI Container Group", name: "claim-emulator-grp" },
        { enabled: !config.skip_synthea, section: "Data Loaders & Viewer", type: "ACI Job", name: "synthea-generator-job" },
        { enabled: !config.skip_fhir && !config.skip_synthea, section: "Data Loaders & Viewer", type: "ACI Job", name: "fhir-loader-job" },
        { enabled: !config.skip_dicom, section: "Data Loaders & Viewer", type: "ACI Job", name: "dicom-loader-job" },
        { enabled: !config.skip_imaging, section: "Data Loaders & Viewer", type: "Container App", name: "hds-dicom-proxy" },
        { enabled: !config.skip_imaging, section: "Data Loaders & Viewer", type: "Static Web App", name: "OHIF DICOM viewer" },
    ].filter((asset) => asset.enabled);
    const prospectiveFabricAssets = [
        { enabled: true, section: "Workspace & Lakehouses", type: "Fabric Workspace", name: config.fabric_workspace_name || "<workspace>" },
        { enabled: true, section: "Workspace & Lakehouses", type: "Workspace Identity", name: `${config.fabric_workspace_name || "<workspace>"} identity` },
        { enabled: !config.skip_hds_source, section: "Workspace & Lakehouses", type: "Bronze Lakehouse", name: "healthcare1_msft_bronze" },
        { enabled: !config.skip_hds_source, section: "Workspace & Lakehouses", type: "Silver Lakehouse", name: "healthcare1_msft_silver" },
        { enabled: !config.skip_imaging, section: "Workspace & Lakehouses", type: "Gold Lakehouse", name: "healthcare1_reporting_gold" },
        { enabled: !config.skip_fhir_export, section: "Workspace & Lakehouses", type: "OneLake Shortcut", name: "FHIR-HDS → fhir-export" },
        { enabled: !config.skip_hds_pipelines, section: "Workspace & Lakehouses", type: "OneLake Shortcut", name: "DICOM-HDS → dicom-output" },
        { enabled: !config.skip_hds_source, section: "Pipelines & Notebooks", type: "Data Pipeline", name: "Clinical foundation ingestion" },
        { enabled: !config.skip_hds_source, section: "Pipelines & Notebooks", type: "Data Pipeline", name: "Imaging + clinical ingestion" },
        { enabled: !config.skip_hds_source, section: "Pipelines & Notebooks", type: "Data Pipeline", name: "OMOP analytics pipeline" },
        { enabled: !config.skip_ontology, section: "Pipelines & Notebooks", type: "Spark Notebook", name: "create_device_association_table" },
        { enabled: !config.skip_quality_measures, section: "Pipelines & Notebooks", type: "Power BI Report", name: "Population Health & Quality" },
        { enabled: !config.skip_fabric, section: "Real-Time Intelligence", type: "Eventstream", name: "MasimoTelemetryStream" },
        { enabled: !config.skip_fabric, section: "Real-Time Intelligence", type: "Eventhouse", name: "MasimoEventhouse" },
        { enabled: !config.skip_fabric, section: "Real-Time Intelligence", type: "KQL Database", name: "MasimoKQLDB" },
        { enabled: !config.skip_fabric, section: "Real-Time Intelligence", type: "KQL Table", name: "TelemetryRaw" },
        { enabled: !config.skip_fabric, section: "Real-Time Intelligence", type: "KQL Table", name: "AlertHistory" },
        { enabled: !config.skip_phase7 && !config.skip_payer_rti, section: "Real-Time Intelligence", type: "KQL Tables (4)", name: "claims_events, fraud_scores, highcost_alerts, care_gap_alerts" },
        { enabled: !config.skip_ontology, section: "AI Agents, Ontology & Alerts", type: "Fabric IQ Ontology", name: "ClinicalDeviceOntology" },
        { enabled: !config.skip_data_agents, section: "AI Agents, Ontology & Alerts", type: "Data Agents (2)", name: "Patient 360 & Clinical Triage" },
        { enabled: !config.skip_imaging, section: "AI Agents, Ontology & Alerts", type: "Data Agent", name: "Multi-Layer Imaging Cohort" },
        { enabled: !config.skip_phase7 && !config.skip_ops_agent, section: "AI Agents, Ontology & Alerts", type: "Data & Ops Agents", name: "Payer Ops Triage & HealthcareOpsAgent" },
        { enabled: !config.skip_phase7 && !config.skip_graph_agent, section: "AI Agents, Ontology & Alerts", type: "Data Agent", name: "Healthcare Graph Agent" },
        { enabled: !config.skip_activator && !!config.alert_email, section: "AI Agents, Ontology & Alerts", type: "Data Activator", name: "ClinicalAlertActivator" },
        { enabled: !config.skip_phase7 && !config.skip_payer_activator, section: "AI Agents, Ontology & Alerts", type: "Data Activator", name: "PayerOpsActivator" },
    ].filter((asset) => asset.enabled);
    const prospectiveAddonAssets = [
        { enabled: !!config.deploy_databricks, section: "Azure Databricks", type: "Workspace & Catalog", name: `hlsdbx-${uniqueSuffix}-ws (hls_${config.databricks_environment || "dev"})` },
        { enabled: !!config.deploy_databricks, section: "Azure Databricks", type: "Lakeflow Pipelines (5)", name: "hls-bronze/silver-files, hls-bronze/silver-streams, hls-gold-products" },
        { enabled: !!config.deploy_databricks, section: "Azure Databricks", type: "AI/BI Dashboards (4)", name: "Executive, Clinical Triage, Payer & Quality, Imaging & Graph" },
        { enabled: !!config.deploy_databricks, section: "Azure Databricks", type: "AI/BI Genie Spaces (5)", name: "Patient 360, Clinical Triage, Imaging, Payer Ops, Healthcare Graph" },
        { enabled: !!config.deploy_rayfin_apps, section: "Rayfin Fabric Apps", type: "Fabric App + SQL DB", name: "rayfin-health-command-center" },
        { enabled: !!config.deploy_rayfin_apps, section: "Rayfin Fabric Apps", type: "Fabric App + SQL DB", name: "rayfin-clinical-triage-app" },
        { enabled: !!config.deploy_cardiology, section: "WardFlow Cardiology", type: "Resource Group", name: `rg-${config.fabric_workspace_name || "med"}-cardio (${config.cardiology_location || "eastus2"})` },
        { enabled: !!config.deploy_cardiology, section: "WardFlow Cardiology", type: "Container App + Easy Auth", name: `${config.cardiology_prefix || "cardio"}-app` },
        { enabled: !!config.deploy_cardiology, section: "WardFlow Cardiology", type: "Azure AI Foundry", name: `${config.cardiology_chat_model || "gpt-5.6-luna"} (DataZoneStandard)` },
        { enabled: !!config.deploy_cardiology, section: "WardFlow Cardiology", type: "Container Apps Job", name: "masimo-fhir-aggregator (5-min cron)" },
    ].filter((asset) => asset.enabled);
    const anyAddonsEnabled = Boolean(config.deploy_databricks || config.deploy_rayfin_apps || config.deploy_cardiology);
    const graphNodes = [
        { id: "synthea", title: "Synthea", subtitle: "Patient generator", label: "Synthea\nPatient generator", group: "External", x: 30, y: 110, enabled: !config.skip_synthea },
        { id: "tcia", title: "TCIA Archive", subtitle: "DICOM studies", label: "TCIA Archive\nDICOM studies", group: "External", x: 30, y: 260, enabled: !config.skip_dicom },
        { id: "fhir", title: "FHIR R4 Service", subtitle: fhirServiceName, label: `FHIR R4 Service\n${fhirServiceName}`, group: "Azure", x: 330, y: 110, enabled: !config.skip_fhir },
        { id: "dicom-loader", title: "DICOM Loader", subtitle: "TCIA → ADLS ACI", label: "DICOM Loader\nTCIA → ADLS ACI", group: "Azure", x: 330, y: 260, enabled: !config.skip_dicom },
        { id: "emulator", title: "Masimo Emulator", subtitle: "100-device ACI", label: "Masimo Emulator\n100-device ACI", group: "Azure", x: 330, y: 460, enabled: !config.scaffolding_only && !config.skip_base_infra },
        { id: "claimemulator", title: "Claim Emulator", subtitle: "EDI 837 ACI", label: "Claim Emulator\nEDI 837 ACI", group: "Azure", x: 330, y: 640, enabled: !config.scaffolding_only && !config.skip_phase7 && !config.skip_payer_rti && !config.skip_base_infra },
        { id: "adls", title: "ADLS Gen2 Storage", subtitle: storageAccountName, label: `ADLS Gen2 Storage\n${storageAccountName}`, group: "Azure", x: 630, y: 185, enabled: !config.skip_fhir || !config.skip_dicom },
        { id: "eventhub", title: "Event Hub", subtitle: "telemetry-stream", label: "Event Hub\ntelemetry-stream", group: "Azure", x: 630, y: 460, enabled: !config.skip_base_infra },
        { id: "claimhub", title: "Event Hub", subtitle: "claim-stream", label: "Event Hub\nclaim-stream", group: "Azure", x: 630, y: 640, enabled: !config.skip_phase7 && !config.skip_payer_rti && !config.skip_base_infra },
        { id: "bronze", title: "Bronze Lakehouse", subtitle: "healthcare1_msft_bronze", label: "Bronze Lakehouse\nhealthcare1_msft_bronze", group: "Fabric", x: 930, y: 110, enabled: !config.skip_hds_source },
        { id: "eventstream", title: "Eventstream", subtitle: "MasimoTelemetryStream", label: "Eventstream\nMasimoTelemetryStream", group: "Fabric", x: 930, y: 460, enabled: !config.skip_fabric },
        { id: "silver", title: "Silver Lakehouse", subtitle: "Clinical + Imaging", label: "Silver Lakehouse\nClinical + Imaging", group: "Fabric", x: 1230, y: 110, enabled: !config.skip_hds_source },
        { id: "eventhouse", title: "Eventhouse KQL", subtitle: "MasimoKQLDB", label: "Eventhouse KQL\nMasimoKQLDB", group: "Fabric", x: 1230, y: 460, enabled: !config.skip_fabric },
        { id: "payerkql", title: "Payer RTI KQL", subtitle: "claims + fraud + gaps", label: "Payer RTI KQL\nclaims + fraud + gaps", group: "Fabric", x: 1230, y: 640, enabled: !config.skip_phase7 && !config.skip_payer_rti },
        { id: "gold", title: "Gold Lakehouse", subtitle: "OMOP + Reporting Gold", label: "Gold Lakehouse\nOMOP + Reporting Gold", group: "Fabric", x: 1530, y: 110, enabled: !config.skip_hds_source },
        { id: "reporting", title: "Reporting & OHIF", subtitle: "Direct Lake + Viewer", label: "Reporting & OHIF\nDirect Lake + Viewer", group: "Fabric+Azure", x: 1530, y: 280, enabled: !config.skip_imaging },
        { id: "ontology", title: "Fabric IQ Ontology", subtitle: "ClinicalDeviceOntology", label: "Fabric IQ Ontology\nClinicalDeviceOntology", group: "Fabric", x: 1530, y: 460, enabled: !config.skip_ontology },
        { id: "payerops", title: "Payer Ops & Reflex", subtitle: "Worklist + Activator", label: "Payer Ops & Reflex\nWorklist + Activator", group: "Fabric", x: 1530, y: 640, enabled: !config.skip_phase7 && (!config.skip_ops_agent || !config.skip_payer_activator) },
        { id: "quality", title: "CMS Quality & Star", subtitle: "eCQM + HEDIS Report", label: "CMS Quality & Star\neCQM + HEDIS Report", group: "Fabric", x: 1830, y: 110, enabled: !config.skip_quality_measures },
        { id: "agents", title: "Clinical Data Agents", subtitle: "Patient 360 + Triage", label: "Clinical Data Agents\nPatient 360 + Triage", group: "Fabric", x: 1830, y: 280, enabled: !config.skip_data_agents },
        { id: "activator", title: "Data Activator", subtitle: "ClinicalAlertActivator", label: "Data Activator\nClinicalAlertActivator", group: "Fabric", x: 1830, y: 460, enabled: !config.skip_activator && !!config.alert_email },
        { id: "graphagent", title: "Healthcare Graph", subtitle: "Ontology Graph Agent", label: "Healthcare Graph\nOntology Graph Agent", group: "Fabric", x: 1830, y: 640, enabled: !config.skip_phase7 && !config.skip_graph_agent },
        { id: "databricks", title: "Azure Databricks", subtitle: "Lakeflow + AI/BI + Genie", label: "Azure Databricks\nLakeflow + AI/BI + Genie", group: "Addon", x: 2130, y: 185, enabled: !!config.deploy_databricks },
        { id: "rayfin", title: "Rayfin Fabric Apps", subtitle: "Command + Triage Apps", label: "Rayfin Fabric Apps\nCommand + Triage Apps", group: "Addon", x: 2130, y: 420, enabled: !!config.deploy_rayfin_apps },
        { id: "cardiology", title: "WardFlow Cardiology", subtitle: "Container App + Foundry", label: "WardFlow Cardiology\nContainer App + Foundry", group: "Addon", x: 2130, y: 600, enabled: !!config.deploy_cardiology },
    ].filter((node) => node.enabled);
    const positionedGraphNodes = graphNodes.map((node) => {
        const offset = graphNodeOffsets[node.id] ?? { x: 0, y: 0 };
        return { ...node, x: node.x + offset.x, y: node.y + offset.y };
    });
    const graphNodeIds = new Set(positionedGraphNodes.map((node) => node.id));
    const graphEdges: Array<{ id: string; from: string; to: string; label: string; lx?: number; ly?: number; curvature?: number }> = [
        { id: "synthea-fhir", from: "synthea", to: "fhir", label: "FHIR bundles", lx: 0, ly: -20 },
        { id: "tcia-loader", from: "tcia", to: "dicom-loader", label: "TCIA studies", lx: 0, ly: -20 },
        { id: "fhir-adls", from: "fhir", to: "adls", label: "$export NDJSON", lx: 0, ly: -22 },
        { id: "loader-adls", from: "dicom-loader", to: "adls", label: "DICOM + manifest", lx: 0, ly: 22 },
        { id: "emulator-eventhub", from: "emulator", to: "eventhub", label: "Masimo vitals", lx: 0, ly: -20 },
        { id: "claimemulator-claimhub", from: "claimemulator", to: "claimhub", label: "EDI 837 claims", lx: 0, ly: -20 },
        { id: "adls-bronze", from: "adls", to: "bronze", label: "OneLake shortcut", lx: 0, ly: -22 },
        { id: "eventhub-eventstream", from: "eventhub", to: "eventstream", label: "telemetry hub", lx: 0, ly: -20 },
        { id: "claimhub-eventstream", from: "claimhub", to: "eventstream", label: "claim stream", lx: 0, ly: 24 },
        { id: "bronze-silver", from: "bronze", to: "silver", label: "HDS pipelines", lx: 0, ly: -20 },
        { id: "eventstream-eventhouse", from: "eventstream", to: "eventhouse", label: "TelemetryRaw", lx: 0, ly: -20 },
        { id: "eventstream-payerkql", from: "eventstream", to: "payerkql", label: "claims_events", lx: 0, ly: 24 },
        { id: "silver-gold", from: "silver", to: "gold", label: "OMOP + Gold", lx: 0, ly: -20 },
        { id: "silver-reporting", from: "silver", to: "reporting", label: "Direct Lake", lx: 0, ly: -20 },
        { id: "silver-eventhouse", from: "silver", to: "eventhouse", label: "KQL shortcuts", lx: -54, ly: 0 },
        { id: "payerkql-payerops", from: "payerkql", to: "payerops", label: "risk worklists", lx: 0, ly: -20 },
        { id: "gold-quality", from: "gold", to: "quality", label: "CMS eCQMs", lx: 0, ly: -20 },
        { id: "gold-reporting", from: "gold", to: "reporting", label: "Gold cohorts", lx: 54, ly: 0 },
        { id: "eventhouse-ontology", from: "eventhouse", to: "ontology", label: "telemetry bind", lx: 0, ly: -20 },
        { id: "eventhouse-agents", from: "eventhouse", to: "agents", label: "live vitals", lx: -10, ly: -22, curvature: -30 },
        { id: "eventhouse-activator", from: "eventhouse", to: "activator", label: "fn_ClinicalAlerts", lx: 0, ly: 38, curvature: 55 },
        { id: "ontology-agents", from: "ontology", to: "agents", label: "semantic bind", lx: 0, ly: 22 },
        { id: "ontology-graphagent", from: "ontology", to: "graphagent", label: "graph model", lx: 0, ly: 24 },
        { id: "adls-databricks", from: "adls", to: "databricks", label: "UC Volumes", lx: 620, ly: 8, curvature: -110 },
        { id: "gold-rayfin", from: "gold", to: "rayfin", label: "Gold snapshots", lx: 180, ly: -18, curvature: -20 },
        { id: "eventhouse-cardiology", from: "eventhouse", to: "cardiology", label: "FHIR + KQL + Gold", lx: 330, ly: -20, curvature: 30 },
    ].filter((edge) => graphNodeIds.has(edge.from) && graphNodeIds.has(edge.to));
    const graphNodeById = new Map(positionedGraphNodes.map((node) => [node.id, node]));
    const GRAPH_WIDTH = anyAddonsEnabled ? 2350 : 2050;
    const GRAPH_HEIGHT = 760;
    const NODE_WIDTH = 176;
    const NODE_HEIGHT = 68;
    const getEdgeGeom = (edge: typeof graphEdges[0]) => {
        const from = graphNodeById.get(edge.from)!;
        const to = graphNodeById.get(edge.to)!;
        const fromCenterX = from.x + NODE_WIDTH / 2;
        const fromCenterY = from.y + NODE_HEIGHT / 2;
        const toCenterX = to.x + NODE_WIDTH / 2;
        const toCenterY = to.y + NODE_HEIGHT / 2;
        const startPt = getRectIntersection(from.x, from.y, NODE_WIDTH, NODE_HEIGHT, toCenterX, toCenterY);
        const endPt = getRectIntersection(to.x, to.y, NODE_WIDTH, NODE_HEIGHT, fromCenterX, fromCenterY);
        const dx = endPt.x - startPt.x;
        const dy = endPt.y - startPt.y;
        const len = Math.hypot(dx, dy) || 1;
        const startGap = 6;
        const endGap = 10;
        const x1 = startPt.x + (dx / len) * startGap;
        const y1 = startPt.y + (dy / len) * startGap;
        const x2 = endPt.x - (dx / len) * endGap;
        const y2 = endPt.y - (dy / len) * endGap;
        const curvature = edge.curvature ?? 0;
        let cx = (x1 + x2) / 2;
        let cy = (y1 + y2) / 2;
        if (curvature !== 0) {
            const lineDx = x2 - x1;
            const lineDy = y2 - y1;
            const lineLen = Math.hypot(lineDx, lineDy) || 1;
            const nx = -lineDy / lineLen;
            const ny = lineDx / lineLen;
            cx = cx + nx * curvature;
            cy = cy + ny * curvature;
        }
        const labelOffset = graphLabelOffsets[edge.id] ?? { x: 0, y: 0 };
        const midX = 0.25 * x1 + 0.5 * cx + 0.25 * x2 + (edge.lx ?? 0) + labelOffset.x;
        const midY = 0.25 * y1 + 0.5 * cy + 0.25 * y2 + (edge.ly ?? 0) + labelOffset.y;
        const labelWidth = Math.max(88, edge.label.length * 6.2 + 18);
        return {
            pathD: `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`,
            midX,
            midY,
            labelWidth,
        };
    };
    const graphLabelVisible = resourceGraphZoom >= 0.7;
    const graphColor = (group: string) => group === "Azure"
        ? "var(--m3-colorPaletteBlueBackground2)" : group === "External"
        ? "var(--m3-colorNeutralBackground3)" : group === "Fabric+Azure"
        ? "var(--m3-colorPalettePurpleBackground2)" : group === "Addon"
        ? "var(--m3-colorPaletteGreenBackground2)" : "var(--m3-colorBrandBackground2)";
    const getGraphPointer = (event: ReactPointerEvent, svg: SVGSVGElement) => {
        const rect = svg.getBoundingClientRect();
        return {
            x: ((event.clientX - rect.left) / rect.width) * GRAPH_WIDTH,
            y: ((event.clientY - rect.top) / rect.height) * GRAPH_HEIGHT,
        };
    };
    const startGraphPan = (event: ReactPointerEvent<SVGSVGElement>) => {
        const el = graphContainerRef.current;
        if (!el)
            return;
        event.preventDefault();
        try { event.currentTarget.setPointerCapture(event.pointerId); } catch {}
        const dragState = {
            kind: "pan" as const,
            id: "canvas",
            startX: event.clientX,
            startY: event.clientY,
            baseX: el.scrollLeft,
            baseY: el.scrollTop,
        };
        graphDragRef.current = dragState;
        setGraphDrag(dragState);
    };
    const startGraphNodeDrag = (event: ReactPointerEvent<SVGGElement>, nodeId: string) => {
        if (spacePressed || event.button === 1)
            return;
        const svg = event.currentTarget.ownerSVGElement;
        if (!svg)
            return;
        event.preventDefault();
        event.stopPropagation();
        try { svg.setPointerCapture(event.pointerId); } catch {}
        const point = getGraphPointer(event, svg);
        const base = graphNodeOffsets[nodeId] ?? { x: 0, y: 0 };
        const dragState = { kind: "node" as const, id: nodeId, startX: point.x, startY: point.y, baseX: base.x, baseY: base.y };
        graphDragRef.current = dragState;
        setGraphDrag(dragState);
    };
    const startGraphLabelDrag = (event: ReactPointerEvent<SVGGElement>, edgeId: string) => {
        if (spacePressed || event.button === 1)
            return;
        const svg = event.currentTarget.ownerSVGElement;
        if (!svg)
            return;
        event.preventDefault();
        event.stopPropagation();
        try { svg.setPointerCapture(event.pointerId); } catch {}
        const point = getGraphPointer(event, svg);
        const base = graphLabelOffsets[edgeId] ?? { x: 0, y: 0 };
        const dragState = { kind: "label" as const, id: edgeId, startX: point.x, startY: point.y, baseX: base.x, baseY: base.y };
        graphDragRef.current = dragState;
        setGraphDrag(dragState);
    };
    const updateGraphDrag = (event: ReactPointerEvent<SVGSVGElement>) => {
        const activeDrag = graphDragRef.current ?? graphDrag;
        if (!activeDrag)
            return;
        if (activeDrag.kind === "pan") {
            const el = graphContainerRef.current;
            if (!el)
                return;
            el.scrollLeft = Math.max(0, activeDrag.baseX - (event.clientX - activeDrag.startX));
            el.scrollTop = Math.max(0, activeDrag.baseY - (event.clientY - activeDrag.startY));
            setScrollState({
                scrollLeft: el.scrollLeft,
                scrollTop: el.scrollTop,
                clientWidth: el.clientWidth,
                clientHeight: el.clientHeight,
            });
            return;
        }
        const point = getGraphPointer(event, event.currentTarget);
        const next = { x: activeDrag.baseX + point.x - activeDrag.startX, y: activeDrag.baseY + point.y - activeDrag.startY };
        if (activeDrag.kind === "node") {
            setGraphNodeOffsets((prev) => ({ ...prev, [activeDrag.id]: next }));
        }
        else {
            setGraphLabelOffsets((prev) => ({ ...prev, [activeDrag.id]: next }));
        }
    };
    const endGraphDrag = (event: ReactPointerEvent<SVGSVGElement>) => {
        try {
            if ((graphDragRef.current || graphDrag) && event.currentTarget.hasPointerCapture(event.pointerId)) {
                event.currentTarget.releasePointerCapture(event.pointerId);
            }
        } catch {}
        graphDragRef.current = null;
        setGraphDrag(null);
    };
    const resetGraphLayout = () => {
        setGraphNodeOffsets({});
        setGraphLabelOffsets({});
        graphDragRef.current = null;
        setGraphDrag(null);
    };
    const copyDeploymentPlan = () => {
        const plan = {
            resourceGroup: config.resource_group_name,
            workspace: config.fabric_workspace_name,
            subscription: selectedSubscription,
            location: config.location,
            capacity: selectedCapacity ? formatSelectedCapacityLabel(selectedCapacity) : "",
            patientCount: config.patient_count,
            estimatedDuration: getEstimatedDuration(),
            components: enabledComponents,
            azureAssets: prospectiveAzureAssets,
            fabricAssets: prospectiveFabricAssets,
            tags: config.tags,
        };
        navigator.clipboard?.writeText(JSON.stringify(plan, null, 2)).catch(() => undefined);
    };
    const update = (field: keyof DeploymentConfig, value: unknown) => {
        setConfig((prev) => {
            const next = { ...prev, [field]: value };
            if (field === "reuse_patients" && value) {
                next.reseed_data = false;
                next.use_cached_synthea = false;
                next.skip_synthea = true;
                next.skip_device_assoc = true;
            }
            if (field === "reseed_data" && value) {
                next.reuse_patients = false;
            }
            // ── Dependency auto-toggle rules ──
            // When a component is disabled, auto-disable its dependents.
            // When re-enabled, dependents stay as-is (user re-enables manually).
            // skip_fhir → forces skip_synthea, skip_device_assoc, skip_fhir_export
            if (field === "skip_fhir" && value) {
                next.skip_synthea = true;
                next.skip_device_assoc = true;
                next.skip_fhir_export = true;
            }
            // skip_synthea → forces skip_device_assoc (no patients = no devices)
            if (field === "skip_synthea" && value) {
                next.skip_device_assoc = true;
            }
            if (field === "skip_phase7" && value) {
                next.skip_payer_rti = true;
                next.skip_payer_activator = true;
                next.skip_ops_agent = true;
                next.skip_graph_agent = true;
            }
            // skip_dicom → forces skip_imaging (Imaging Toolkit needs DICOM studies).
            // HDS pipelines are NOT force-skipped: clinical + OMOP ingestion run off FHIR
            // data and stay enabled; only the imaging ingestion sub-pipeline is gated
            // backend-side by skip_dicom (see deploy_hds_pipelines.run).
            if (field === "skip_dicom" && value) {
                next.skip_imaging = true;
            }
            // skip_fabric (RTI) → forces skip_fhir_export, skip_rti_phase2, skip_activator
            if (field === "skip_fabric" && value) {
                next.skip_fhir_export = true;
                next.skip_rti_phase2 = true;
                next.skip_activator = true;
                next.skip_phase7 = true;
                next.skip_payer_rti = true;
                next.skip_payer_activator = true;
                next.skip_ops_agent = true;
                next.skip_graph_agent = true;
            }
            // skip_base_infra → forces skip_synthea, skip_fhir, skip_dicom, skip_device_assoc
            if (field === "skip_base_infra" && value) {
                next.skip_fhir = true;
                next.skip_synthea = true;
                next.skip_device_assoc = true;
                next.skip_dicom = true;
                next.skip_fhir_export = true;
                next.skip_hds_pipelines = true;
                next.skip_imaging = true;
            }
            // Re-enabling a parent → unblock children (restore to not-skipped)
            if (field === "skip_fhir" && !value) {
                next.skip_synthea = false;
                next.skip_device_assoc = false;
                next.skip_fhir_export = false;
            }
            if (field === "skip_synthea" && !value) {
                next.skip_device_assoc = false;
            }
            if (field === "skip_dicom" && !value) {
                next.skip_imaging = false;
            }
            if (field === "skip_fabric" && !value) {
                next.skip_fhir_export = false;
                next.skip_rti_phase2 = false;
                next.skip_activator = false;
            }
            if (field === "skip_base_infra" && !value) {
                next.skip_fhir = false;
                next.skip_synthea = false;
                next.skip_device_assoc = false;
                next.skip_dicom = false;
                next.skip_fhir_export = false;
                next.skip_hds_pipelines = false;
                next.skip_imaging = false;
            }
            if (field === "skip_phase7" && !value) {
                next.skip_payer_rti = false;
                next.skip_payer_activator = !next.alert_email && !next.payer_ops_email;
                next.skip_ops_agent = false;
                next.skip_graph_agent = false;
            }
            // A reseed is authoritative: it cannot reuse data and must run every
            // stage required to replace FHIR data and refresh downstream tables.
            if (next.reseed_data) {
                next.reuse_patients = false;
                next.skip_fhir = false;
                next.skip_synthea = false;
                next.skip_device_assoc = false;
                next.skip_fhir_export = false;
                next.skip_hds_pipelines = false;
            }
            if (next.use_cached_synthea) {
                next.patient_count = 100;
            }
            if (next.scaffolding_only) {
                next.reseed_data = false;
                next.reuse_patients = false;
            }
            return next;
        });
    };
    // Check for existing deployment when workspace/RG names are set
    useEffect(() => {
        const ws = config.fabric_workspace_name;
        const rg = config.resource_group_name;
        if (!ws && !rg) {
            setExistingDeploy(null);
            return;
        }
        const abortController = new AbortController();
        const timer = setTimeout(() => {
            setCheckingExisting(true);
            checkExistingDeployment(ws, rg, abortController.signal)
                .then((info) => {
                if (abortController.signal.aborted)
                    return;
                setExistingDeploy(info);
                if (info) {
                    setOverridePriorSettings(false);
                    // Auto-populate prior settings without overwriting a data strategy the user
                    // selected while this debounced lookup was in flight.
                    const pc = info.priorConfig;
                    setConfig((prev) => {
                        const strategySelected = prev.reuse_patients || prev.reseed_data;
                        const reseedSelected = prev.reseed_data;
                        return {
                            ...prev,
                            location: pc?.location || prev.location,
                            admin_security_group: pc?.admin_security_group || prev.admin_security_group,
                            alert_email: pc?.alert_email || prev.alert_email,
                            payer_ops_email: pc?.payer_ops_email || prev.payer_ops_email,
                            patient_count: reseedSelected ? prev.patient_count : pc?.patient_count || prev.patient_count,
                            reuse_patients: strategySelected ? prev.reuse_patients : true,
                            reseed_data: prev.reseed_data,
                            use_cached_synthea: reseedSelected ? prev.use_cached_synthea : strategySelected ? prev.use_cached_synthea : false,
                            skip_synthea: reseedSelected ? false : strategySelected ? prev.skip_synthea : true,
                            skip_device_assoc: reseedSelected ? false : strategySelected ? prev.skip_device_assoc : true,
                        };
                    });
                    if (pc) {
                        if (pc.capacity_name) {
                            setSelectedCapacity(pc.capacity_name);
                        }
                        // Restore tags
                        if (pc.tags && Object.keys(pc.tags).length > 0) {
                            setUseTags(true);
                            setTagRows(Object.entries(pc.tags).map(([name, value]) => ({ name, value })));
                        }
                    }
                }
            })
                .catch(() => {
                if (!abortController.signal.aborted)
                    setExistingDeploy(null);
            })
                .finally(() => {
                if (!abortController.signal.aborted)
                    setCheckingExisting(false);
            });
        }, 500); // debounce
        return () => {
            clearTimeout(timer);
            abortController.abort();
        };
    }, [config.fabric_workspace_name, config.resource_group_name]); // eslint-disable-line react-hooks/exhaustive-deps
    // When naming prefix changes, auto-derive RG and workspace names
    const handleNamingChange = (prefix: string) => {
        // Azure resource names: max 90 chars, alphanumeric + dashes
        const sanitized = prefix.replace(/[^a-zA-Z0-9-]/g, "").substring(0, 40);
        setNamingPrefix(sanitized);
        if (useNamingConvention && sanitized) {
            setConfig((prev) => ({
                ...prev,
                resource_group_name: `rg-${sanitized}`,
                fabric_workspace_name: sanitized,
            }));
        }
    };
    const handleNamingToggle = (checked: boolean) => {
        setUseNamingConvention(checked);
        if (checked && namingPrefix) {
            setConfig((prev) => ({
                ...prev,
                resource_group_name: `rg-${namingPrefix}`,
                fabric_workspace_name: namingPrefix,
            }));
        }
    };
    // Sync tagRows → config.tags
    const syncTags = (rows: Array<{
        name: string;
        value: string;
    }>) => {
        const parsed: Record<string, string> = {};
        for (const row of rows) {
            if (row.name.trim()) {
                parsed[row.name.trim()] = row.value.trim();
            }
        }
        update("tags", parsed);
    };
    const updateTagRow = (index: number, field: "name" | "value", val: string) => {
        setTagRows((prev) => {
            const next = [...prev];
            next[index] = { ...next[index], [field]: val };
            syncTags(next);
            return next;
        });
    };
    const addTagRow = () => {
        setTagRows((prev) => [...prev, { name: "", value: "" }]);
    };
    const removeTagRow = (index: number) => {
        setTagRows((prev) => {
            const next = prev.filter((_, i) => i !== index);
            if (next.length === 0)
                next.push({ name: "", value: "" });
            syncTags(next);
            return next;
        });
    };
    const buildDeploymentConfig = (): DeploymentConfig => {
        const cap = findCapacity(selectedCapacity);
        const fallbackCapacity = getCapacityFallbackParts(selectedCapacity);
        const subscriptionId = selectedSubscription || config.expected_subscription_id || authContext?.cli.subscriptionId || authContext?.pwsh.subscriptionId || '';
        const tenantId = subscriptions.find((item) => item.id === subscriptionId)?.tenantId
            || ctxSubscriptions.find((item) => item.id === subscriptionId)?.tenantId
            || config.expected_tenant_id || authContext?.cli.tenantId || authContext?.pwsh.tenantId || '';
        return {
            ...config, ...getAddonOptions(config),
            expected_tenant_id: tenantId,
            expected_subscription_id: subscriptionId,
            patient_count: config.use_cached_synthea ? 100 : config.patient_count,
            reseed_data: !config.scaffolding_only && config.reseed_data,
            reuse_patients: !config.scaffolding_only && !config.reseed_data && config.reuse_patients,
            skip_fhir: config.reseed_data && !config.scaffolding_only ? false : config.skip_fhir,
            skip_synthea: config.reseed_data && !config.scaffolding_only ? false : config.skip_synthea,
            skip_device_assoc: config.reseed_data && !config.scaffolding_only ? false : config.skip_device_assoc,
            skip_fhir_export: config.reseed_data && !config.scaffolding_only ? false : config.skip_fhir_export,
            skip_hds_pipelines: config.reseed_data && !config.scaffolding_only ? false : config.skip_hds_pipelines,
            location: normalizeAzureLocation(config.location),
            capacity_name: cap?.name ?? fallbackCapacity?.capacityName ?? selectedCapacity,
            capacity_resource_group: cap?.resourceGroup ?? config.capacity_resource_group ?? '',
            capacity_subscription_id: cap?.subscription ?? fallbackCapacity?.subscriptionId ?? selectedSubscription,
            pause_capacity_after_deploy: pauseAfterDeploy,
        };
    };
    const startActualDeployment = async () => {
        setLoading(true);
        setDeploymentStartMessage("Validating local auth and starting the backend deployment run…");
        setError("");
        try {
            const deployConfig = buildDeploymentConfig();
            if (!deployConfig.expected_tenant_id || !deployConfig.expected_subscription_id) {
                throw new Error("Sign in to Azure and select a deployment subscription before deploying.");
            }
            // Save tags to history before deploying
            if (Object.keys(config.tags).length > 0) {
                addTagToHistory(config.tags);
            }
            const { instanceId } = await startDeployment(deployConfig);
            navigate(`/monitor/${instanceId}`);
        }
        catch (e) {
            setError(e instanceof Error ? e.message : "Unknown error");
            setDeploymentStartMessage("");
        }
        finally {
            setLoading(false);
        }
    };
    const runLiveExistingValidation = async () => {
        if (!config.fabric_workspace_name && !config.resource_group_name)
            return;
        setDeepCheckingExisting(true);
        try {
            const info = await checkExistingDeployment(config.fabric_workspace_name, config.resource_group_name, undefined, true);
            if (info)
                setExistingDeploy(info);
        }
        finally {
            setDeepCheckingExisting(false);
        }
    };
    const handleMockDeploy = () => {
        // For mock mode, auto-fill workspace name if empty
        const mockConfig = {
            ...config,
            location: normalizeAzureLocation(config.location),
            fabric_workspace_name: config.fabric_workspace_name || "med-device-rti-hds-demo",
        };
        const instanceId = startMockDeployment(mockConfig);
        navigate(`/monitor/${instanceId}`);
    };
    const locationUnsupported = fhirRegions !== null &&
        !config.skip_fhir &&
        !supportedFhirRegionIds.has(normalizeAzureLocation(config.location));
    const validationErrors = useMemo(() => {
        const issues: string[] = [];
        if (!selectedSubscription)
            issues.push("Select an Azure subscription.");
        if (!selectedCapacity)
            issues.push("Select a Fabric capacity.");
        if (onlyTrialCapacitiesDetected)
            issues.push("Only Fabric trial capacities (FT*) were detected. Healthcare Data Solutions requires a paid Fabric F-SKU capacity.");
        const selectedCap = findCapacity(selectedCapacity);
        if (selectedCap && !isUsableCapacity(selectedCap))
            issues.push(`Selected Fabric capacity ${selectedCap.name} uses unsupported SKU ${selectedCap.sku || "unknown"}. Select a paid Fabric F-SKU capacity.`);
        if (!config.admin_security_group?.trim())
            issues.push("Admin Security Group is required.");
        if (useNamingConvention && !namingPrefix.trim())
            issues.push("Deployment Name is required when naming convention is enabled.");
        if (!useNamingConvention && !config.resource_group_name?.trim())
            issues.push("Resource Group Name is required.");
        if (!config.fabric_workspace_name?.trim())
            issues.push("Fabric workspace name is required.");
        if (!config.skip_activator && !config.alert_email?.trim())
            issues.push("Alert email is required.");
        if (!config.patient_count || config.patient_count < 1)
            issues.push("Patient count must be at least 1.");
        if (locationUnsupported)
            issues.push(`Not an acceptable region. Please select a supported AHDS FHIR region.`);
        return issues;
    }, [
        selectedSubscription,
        selectedCapacity,
        capacities,
        onlyTrialCapacitiesDetected,
        config.admin_security_group,
        config.resource_group_name,
        config.fabric_workspace_name,
        config.alert_email,
        config.patient_count,
        config.location,
        config.skip_fhir,
        useNamingConvention,
        namingPrefix,
        locationUnsupported,
    ]);
    useEffect(() => {
        if (!error)
            return;
        setError("");
    }, [
        selectedSubscription,
        selectedCapacity,
        config.admin_security_group,
        config.resource_group_name,
        config.fabric_workspace_name,
        config.alert_email,
        config.patient_count,
        config.location,
        useNamingConvention,
        namingPrefix,
    ]); // eslint-disable-line react-hooks/exhaustive-deps
    return (<GuidedDeployment config={buildDeploymentConfig()} errors={validationErrors} starting={loading} onStart={startActualDeployment} onUpdateConfig={(patch) => setConfig((prev) => ({ ...prev, ...patch }))}><div className="deployment-workspace" style={{ display: "flex", flexWrap: "wrap", gap: "32px", position: "relative" }}>
      {/* Main content area */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {loadWarning && (<div style={{
                marginBottom: "12px",
                padding: `${"8px"} ${"16px"}`,
                backgroundColor: "var(--m3-colorStatusWarningBackground1)",
                borderLeft: `4px solid ${"var(--m3-colorStatusWarningBorderActive)"}`,
                borderRadius: "16px",
            }}>
            <Typography component="span" variant="caption">{loadWarning}</Typography>
          </div>)}
        <div className={styles.stickyHeader}>
          <Typography component="div" variant="h5">Deployment Settings</Typography>
        </div>

        {/* Responsive grid: auto-flow dense packing eliminates wasted space */}
        <style>{`
        .deploy-form-grid {
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin-top: 16px;
        }
        .deploy-form-grid > * {
          animation: deploy-card-in 0.5s ease both;
        }
        .deploy-columns-row {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .deploy-column {
          display: flex;
          flex-direction: column;
          gap: 16px;
          min-width: 0;
        }
        .deploy-column > * {
          animation: deploy-card-in 0.5s ease both;
        }
        .deploy-column > *:nth-child(1) { animation-delay: 0.05s; }
        .deploy-column > *:nth-child(2) { animation-delay: 0.12s; }
        .deploy-column > *:nth-child(3) { animation-delay: 0.19s; }
        @keyframes deploy-card-in {
          from { opacity: 0; transform: translateY(16px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .deploy-card-active {
          outline: 3px solid ${"var(--m3-colorBrandStroke1)"} !important;
          outline-offset: 4px;
          animation: deploy-card-in 0.5s ease both, deploy-card-pulse 2s ease-in-out 0.6s infinite !important;
        }
        @keyframes deploy-card-pulse {
          0%, 100% { box-shadow: 0 0 16px ${"var(--m3-colorBrandBackground2)"}; outline-color: ${"var(--m3-colorBrandStroke1)"}; }
          50%      { box-shadow: 0 0 36px ${"var(--m3-colorBrandBackground2Hover)"}; outline-color: ${"var(--m3-colorBrandStroke2)"}; }
        }
        @media (min-width: 1200px) {
          .deploy-columns-row {
            flex-direction: row;
            align-items: flex-start;
          }
          .deploy-column {
            flex: 1;
          }
        }
        /* Compact padding on wide screens */
        @media (min-width: 1400px) {
          .deploy-compact-padding .fui-CardHeader {
            padding: 12px 16px;
          }
          .deploy-compact-padding .deploy-field-group {
            padding: 0 16px 12px;
          }
        }
        /* Tall cards span 2 rows for better visual hierarchy */
        .deploy-card-tall {
          grid-row: span 2;
        }
        /* Sticky card headers */
        .deploy-card-sticky-header .fui-CardHeader {
          position: sticky;
          top: 0;
          z-index: 5;
          background-color: inherit;
          border-bottom: 1px solid ${"var(--m3-colorNeutralStroke2)"};
        }
        /* Collapsible section animation */
        .deploy-collapsible-content {
          overflow: hidden;
          transition: max-height 0.3s ease, opacity 0.3s ease;
        }
        .deploy-collapsible-collapsed {
          max-height: 0 !important;
          opacity: 0;
        }
        /* Advanced options toggle */
        .deploy-advanced-toggle {
          margin: 12px 0;
          padding: 10px 16px;
          background: ${"var(--m3-colorNeutralBackground3)"};
          border: 1px solid ${"var(--m3-colorNeutralStroke2)"};
          border-radius: 6px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: space-between;
          transition: all 0.2s;
          color: ${"var(--m3-colorNeutralForeground1)"};
        }
        .deploy-advanced-toggle:hover {
          background: ${"var(--m3-colorNeutralBackground4)"};
          border-color: ${"var(--m3-colorBrandStroke1)"};
        }
        .deploy-advanced-toggle svg {
          color: ${"var(--m3-colorNeutralForeground2)"};
        }
        ${reducedMotion ? `
        .deploy-form-grid > *,
        .deploy-card-active,
        .deploy-collapsible-content,
        .deploy-advanced-toggle {
          animation: none !important;
          transition: none !important;
        }
        ` : ""}
        @media (prefers-reduced-motion: reduce) {
          .deploy-form-grid > *,
          .deploy-card-active,
          .deploy-collapsible-content {
            animation: none !important;
            transition: none !important;
          }
        }
      `}</style>

        {initializing ? (<div className={`${styles.form} deploy-form-grid`}>
            <Card className={styles.section}><CardHeader title={<Typography component="div" variant="subtitle1">Loading deployment configuration...</Typography>}/></Card>
            <Card className={styles.section}><CardHeader title={<Typography component="div" variant="subtitle1">Loading capacities and subscriptions...</Typography>}/></Card>
            <Card className={styles.section}><CardHeader title={<Typography component="div" variant="subtitle1">Preparing defaults...</Typography>}/></Card>
          </div>) : (<div className={`${styles.form} deploy-form-grid deploy-compact-padding`}>
            {/* Deployment Presets */}
            <Card className={`${styles.section} ${styles.sectionFullWidth}`} style={{ overflow: "visible" }}>
              <CardHeader title={<div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Typography component="div" variant="subtitle1">Deployment Presets</Typography>
                    <Chip component="span" size="small" variant="filled" color="primary" icon={<Bolt />} label={<>Fast start</>}/>
                  </div>} subheader={"Choose a safe default profile, then fine-tune individual components below."}/>
              <div className={styles.fieldGroup}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "12px" }}>
                  <Button onClick={() => applyPreset("demo")} variant="outlined">Demo / fastest</Button>
                  <Button onClick={() => applyPreset("full")} variant="outlined">Full platform</Button>
                  <Button onClick={() => applyPreset("scaffold")} variant="outlined">Scaffolding / no data</Button>
                  <Button onClick={() => applyPreset("infra")} variant="outlined">Infra only</Button>
                  <Button onClick={() => applyPreset("repair")} variant="outlined">Resume / repair</Button>
                  <Button onClick={() => applyPreset("data")} variant="outlined">Data pipeline only</Button>
                </div>
                <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">
                  Current plan enables {enabledComponents.length} component(s): {enabledComponents.slice(0, 8).join(", ")}{enabledComponents.length > 8 ? ` +${enabledComponents.length - 8} more` : ""}.
                </Typography>
                {config.scaffolding_only && (<Typography style={{ color: "var(--m3-colorPaletteBlueForeground2)" }} component="span" variant="caption">
                    Zero-data mode deploys Azure/Fabric infrastructure, Microsoft HDS source artifacts, RTI schemas, Eventstreams, and payer definitions. It does not launch Synthea, DICOM, telemetry, claim producers, exports, or ingestion/materialization pipelines.
                  </Typography>)}
              </div>
            </Card>

            <div className="deploy-columns-row">
              <div className="deploy-column">
                {/* Naming Convention */}
                <Card className={`${styles.section} ${styles.cardRequired}${activeCardIndex === 0 ? " deploy-card-active" : ""}`} style={{ overflow: "visible" }}>
                  <CardHeader className={styles.sectionHeader} title={<div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Typography component="div" variant="subtitle1">Naming Convention</Typography>
                        {(() => {
                    const { complete, total } = getCardCompletion(0);
                    return complete === total ? (<Chip component="span" size="small" variant="filled" color="success" icon={<CheckCircleOutlined />} label={<>Complete</>}/>) : (<Chip component="span" size="small" variant="filled" color="default" icon={<RadioButtonUnchecked />} label={<>{complete}/{total}</>}/>);
                })()}
                      </div>} subheader={"Auto-generate consistent names for Azure and Fabric resources"}/>
                  <div className={styles.fieldGroup}>
                    <FormControlLabel label={"Use naming convention (recommended)"} control={<Checkbox checked={useNamingConvention} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return handleNamingToggle(!!d.checked);
                }}/>}/>
                    {useNamingConvention && (<>
                        <FormControl required><FormLabel id="field-deploywizard-1-label" htmlFor="field-deploywizard-1">{<Tooltip title={"Enter a short prefix like 'rojo-0404'. The Resource Group will be 'rg-rojo-0404' and the Fabric Workspace will be 'rojo-0404'."} describeChild><Box component="span">
                              <span className={styles.fieldLabelWithIcon}>
                                <img src="/icon-deployment.svg" alt="" width={16} height={16}/>
                                <span className={styles.labelSeparator}/>
                                Deployment Name
                              </span>
                            </Box></Tooltip>}</FormLabel>
                          <HistoryInput field="naming-prefix" value={namingPrefix} onChange={(v) => handleNamingChange(v)} suggestions={lastWorkspaceName ? [lastWorkspaceName] : undefined} suggestionsLabel="Most recent deployment" placeholder="e.g. rojo-0404" id="field-deploywizard-1"/>
                          {!namingPrefix && lastWorkspaceName && (<Box sx={{ mt: 1, display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                              <Chip size="small" color="primary" variant="outlined" label={`Load last deployment (${lastWorkspaceName})`} onClick={() => handleNamingChange(lastWorkspaceName)}/>
                            </Box>)}
                        </FormControl>
                        {namingPrefix && (<div style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "4px",
                        padding: `${"8px"} ${"16px"}`,
                        backgroundColor: "var(--m3-colorNeutralBackground3)",
                        borderRadius: "16px",
                        fontSize: "12px",
                    }}>
                            <Typography component="span" variant="caption">
                              <Typography component="span" variant="caption" sx={{
                        fontWeight: 600
                    }}>Resource Group:</Typography> rg-{namingPrefix}
                            </Typography>
                            <Typography component="span" variant="caption">
                              <Typography component="span" variant="caption" sx={{
                        fontWeight: 600
                    }}>Fabric Workspace:</Typography> {namingPrefix}
                            </Typography>
                          </div>)}
                      </>)}
                  </div>
                </Card>

                {/* Azure Configuration */}
                <Card className={`${styles.section} ${styles.cardRequired}${activeCardIndex === 1 ? " deploy-card-active" : ""}`} style={{ overflow: "visible" }}>
                  <CardHeader className={styles.sectionHeader} title={<div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Typography component="div" variant="subtitle1">Azure Configuration</Typography>
                        {(() => {
                    const { complete, total } = getCardCompletion(1);
                    return complete === total ? (<Chip component="span" size="small" variant="filled" color="success" icon={<CheckCircleOutlined />} label={<>Complete</>}/>) : (<Chip component="span" size="small" variant="filled" color="default" icon={<RadioButtonUnchecked />} label={<>{complete}/{total}</>}/>);
                })()}
                      </div>} subheader={"Target Azure subscription and resource group settings"}/>
                  <div className={styles.fieldGroup}>

                    {existingDeploy?.priorConfig && (<div style={{
                    padding: "16px",
                    backgroundColor: "var(--m3-colorNeutralBackground4)",
                    borderLeft: `4px solid ${"var(--m3-colorBrandStroke1)"}`,
                    borderRadius: "16px",
                    marginBottom: "12px",
                }}>
                        <div onClick={() => setExistingDeployCollapsed(!existingDeployCollapsed)} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
                          <Typography component="span" variant="caption" sx={{
                    fontWeight: 600
                }}>
                            <Chip style={{ marginRight: 6 }} component="span" size="small" variant="filled" color="default" label={<>Auto-populated</>}/>
                            Settings from prior deployment
                          </Typography>
                          {existingDeployCollapsed ? <ExpandMore /> : <ExpandLess />}
                        </div>
                        <div className={`deploy-collapsible-content${existingDeployCollapsed ? " deploy-collapsible-collapsed" : ""}`} style={{ maxHeight: existingDeployCollapsed ? "0" : "200px" }}>
                          <Typography style={{ marginTop: 8 }} component="div" variant="caption">
                            Restored from deployment <strong>{existingDeploy.instanceId}</strong>
                          </Typography>
                          <FormControlLabel label={"Override previous settings"} control={<Checkbox checked={overridePriorSettings} onChange={(event) => {
                        const d = { checked: event.target.checked };
                        return setOverridePriorSettings(!!d.checked);
                    }} style={{ marginTop: "8px" }}/>}/>
                        </div>
                      </div>)}
                    <FormControl><FormLabel id="field-deploywizard-2-label" htmlFor="field-deploywizard-2">{<Tooltip title={"Azure subscription where infrastructure resources will be deployed. This selection also applies to the Teardown tab."} describeChild><Box component="span">
                          <span className={styles.fieldLabelWithIcon}>
                            <img src="/azure_logo.svg" alt="" width={16} height={16}/>
                            <span className={styles.labelSeparator}/>
                            Azure Subscription
                          </span>
                        </Box></Tooltip>}</FormLabel>
                      <Select value={[selectedSubscription][0] ?? ""} displayEmpty onChange={(event) => {
                const data = { optionValue: event.target.value };
                return setSelectedSubscription(data.optionValue as string);
            }} id="field-deploywizard-2" labelId="field-deploywizard-2-label">
                        {subscriptions.map((s) => (<MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>))}
                      </Select>
                    </FormControl>
                    <FormControl><FormLabel id="field-deploywizard-3-label" htmlFor="field-deploywizard-3">{<Tooltip title={"The Fabric capacity backing the workspace. Used to pause billing after deployment. Capacities are scanned across all subscriptions."} describeChild><Box component="span">
                          <span className={styles.fieldLabelWithIcon}>
                            <img src="/fabric_16_color.svg" alt="" width={16} height={16}/>
                            <span className={styles.labelSeparator}/>
                            Fabric Capacity
                          </span>
                        </Box></Tooltip>}</FormLabel>
                      <div className={styles.capacityFieldRow}>
                        <Select style={{ flex: 1 }} disabled={(usableCapacities.length === 0 && capacityRefreshing) || onlyTrialCapacitiesDetected} value={(selectedCapacity ? [selectedCapacity] : [])[0] ?? ""} displayEmpty onChange={(event) => {
                const data = { optionValue: event.target.value };
                return setSelectedCapacity(data.optionValue as string);
            }} id="field-deploywizard-3" labelId="field-deploywizard-3-label">
                          {usableCapacities.map((c) => (<MenuItem key={getCapacitySelectionValue(c)} value={getCapacitySelectionValue(c)}>
                              {formatCapacityMenuLabel(c)}
                            </MenuItem>))}
                        </Select>
                        <Tooltip title={"Refresh capacity status"} describeChild>
                          <Button onClick={refreshCapacities} style={capacityRefreshing ? { animation: "spin 1s linear infinite" } : undefined} disabled={capacityRefreshing} variant="text" size="small" startIcon={<Sync />}/>
                        </Tooltip>
                        {(() => {
                const cap = findCapacity(selectedCapacity);
                if (!cap)
                    return null;
                const isActive = cap.state === "Active";
                const isPaused = cap.state === "Paused" || cap.state === "Suspended";
                const isResuming = cap.state === "Resuming" || resumingCapacity;
                return (<>
                              {/* Status badge — always visible */}
                              {isActive && !resumingCapacity && (<Chip component="span" size="small" variant="filled" color="success" label={<>Active</>}/>)}
                              {isResuming && (<Chip style={{ animation: "pulse 1.5s ease-in-out infinite" }} component="span" size="small" variant="filled" color="warning" label={<>
                                  {cap.state === "Active" ? "Active ✓" : "Resuming…"}
                                </>}/>)}
                              {isPaused && !resumingCapacity && (<Chip component="span" size="small" variant="filled" color="error" label={<>{cap.state}</>}/>)}
                              {/* Resume button — only when not active and not already resuming */}
                              {!isActive && (<Tooltip title={`Resume capacity "${cap.name}" (currently ${cap.state})`} describeChild>
                                  <Button onClick={async () => {
                            setResumingCapacity(true);
                            setError("");
                            try {
                                await resumeCapacity(cap.subscription, cap.resourceGroup, cap.name);
                                // Poll capacity status until Active (max 3 min)
                                let elapsed = 0;
                                const capName = cap.name;
                                const poll = setInterval(() => {
                                    elapsed += 5;
                                    refreshCapacities();
                                    if (elapsed >= 180) {
                                        clearInterval(poll);
                                        setResumingCapacity(false);
                                    }
                                }, 5000);
                                const checkActive = setInterval(() => {
                                    setCapacities((current) => {
                                        const fresh = current.find((c) => c.name === capName);
                                        if (fresh?.state === "Active") {
                                            clearInterval(poll);
                                            clearInterval(checkActive);
                                            setResumingCapacity(false);
                                        }
                                        return current;
                                    });
                                }, 3000);
                                setTimeout(() => clearInterval(checkActive), 180000);
                            }
                            catch (e) {
                                setError(e instanceof Error ? e.message : "Failed to resume capacity");
                                setResumingCapacity(false);
                            }
                        }} disabled={resumingCapacity} variant="contained" size="small" startIcon={<PlayArrow />}>
                                    {resumingCapacity ? "Resuming…" : "Resume"}
                                  </Button>
                                </Tooltip>)}
                              {isActive && showAdvanced && (<Tooltip title={`Pause capacity "${cap.name}" now. Confirm because this can interrupt Fabric workloads.`} describeChild>
                                  <Button onClick={async () => {
                            if (!window.confirm(`Pause Fabric capacity ${cap.name}? This may interrupt active Fabric workloads.`))
                                return;
                            setError("");
                            try {
                                await pauseCapacity(cap.subscription, cap.resourceGroup, cap.name);
                                await refreshCapacities();
                            }
                            catch (e) {
                                setError(e instanceof Error ? e.message : "Failed to pause capacity");
                            }
                        }} variant="outlined" size="small">
                                    Pause now
                                  </Button>
                                </Tooltip>)}
                            </>);
            })()}
                      </div>
                    </FormControl>
                    <FormControl><FormLabel id="field-deploywizard-4-label" htmlFor="field-deploywizard-4">{<Tooltip title={"Azure resource group where Event Hub, ACR, FHIR Service, and ACI containers are deployed."} describeChild><Box component="span">
                          <span className={styles.fieldLabelWithIcon}>
                            <img src="/icon-resource-group.svg" alt="" width={16} height={16}/>
                            <span className={styles.labelSeparator}/>
                            Resource Group Name
                          </span>
                        </Box></Tooltip>}</FormLabel>
                      <HistoryInput field="resource-group" value={config.resource_group_name} onChange={(v) => update("resource_group_name", v)} disabled={useNamingConvention} placeholder={useNamingConvention ? "Set via naming convention above" : "e.g. rg-medtech-rti-fhir"} id="field-deploywizard-4"/>
                    </FormControl>
                    <FormControl error={(locationUnsupported ? "error" : undefined) === "error"}><FormLabel id="field-deploywizard-5-label" htmlFor="field-deploywizard-5">{<Tooltip title={"Azure region for all resources. Must support FHIR Service and Event Hubs."} describeChild><Box component="span">
                          <span className={styles.fieldLabelWithIcon}>
                            <img src="/icon-location.svg" alt="" width={16} height={16}/>
                            <span className={styles.labelSeparator}/>
                            Location
                          </span>
                        </Box></Tooltip>}</FormLabel>
                      <HistoryInput field="location" value={config.location} onChange={(v) => update("location", v)} disabled={!!existingDeploy?.priorConfig && !overridePriorSettings} suggestions={fhirRegionLabels} suggestionsLabel="Supported AHDS FHIR regions" id="field-deploywizard-5"/>
                    <FormHelperText>{locationUnsupported
                ? `Not an acceptable region. Please select from the following: ${fhirRegionLabels.join(", ")}`
                : undefined}</FormHelperText></FormControl>
                    <FormControl><FormLabel id="field-deploywizard-6-label" htmlFor="field-deploywizard-6">{<Tooltip title={"Entra ID security group granted admin access to FHIR Service and Key Vault."} describeChild><Box component="span">
                          <span className={styles.fieldLabelWithIcon}>
                            <img src="/icon-groups.svg" alt="" width={16} height={16}/>
                            <span className={styles.labelSeparator}/>
                            Admin Security Group
                          </span>
                        </Box></Tooltip>}</FormLabel>
                      <HistoryInput field="admin-security-group" value={config.admin_security_group} onChange={(v) => update("admin_security_group", v)} disabled={!!existingDeploy?.priorConfig && !overridePriorSettings} id="field-deploywizard-6"/>
                    </FormControl>
                    {/* Advanced Options Toggle */}
                    <div className="deploy-advanced-toggle" onClick={() => setShowAdvanced(!showAdvanced)}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Settings style={{ fontSize: 16, color: "var(--m3-colorBrandForeground1)" }}/>
                        <Typography component="span" variant="body2" sx={{
                fontWeight: 600
            }}>Advanced Options</Typography>
                      </div>
                      {showAdvanced ? <ExpandLess /> : <ExpandMore />}
                    </div>
                    <div className={`deploy-collapsible-content${!showAdvanced ? " deploy-collapsible-collapsed" : ""}`} style={{ maxHeight: showAdvanced ? "800px" : "0" }}>
                      <FormControlLabel label={"Add resource tags"} control={<Checkbox checked={useTags} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    setUseTags(!!d.checked);
                    if (!d.checked) {
                        update("tags", {});
                        setTagRows([{ name: "", value: "" }]);
                    }
                }}/>}/>
                      {useTags && (<div>
                          <TagHistoryPanel onSelect={(tags) => {
                    const rows = Object.entries(tags).map(([name, value]) => ({ name, value }));
                    if (rows.length === 0)
                        rows.push({ name: "", value: "" });
                    setTagRows(rows);
                    syncTags(rows);
                }}/>
                          <div style={{
                    display: "grid",
                    gridTemplateColumns: "1fr auto 1fr auto",
                    gap: `${"8px"} ${"12px"}`,
                    alignItems: "center",
                    marginBottom: "8px",
                }}>
                            <Typography component="span" variant="caption" sx={{
                    fontWeight: 600
                }}>Name</Typography>
                            <span />
                            <Typography component="span" variant="caption" sx={{
                    fontWeight: 600
                }}>Value</Typography>
                            <span />
                          </div>
                          {tagRows.map((row, i) => (<div key={i} style={{
                        display: "grid",
                        gridTemplateColumns: "1fr auto 1fr auto",
                        gap: `${"8px"} ${"12px"}`,
                        alignItems: "center",
                        marginBottom: "8px",
                    }}>
                              <TextField value={row.name} onChange={(event) => {
                        const d = { value: event.target.value };
                        return updateTagRow(i, "name", d.value);
                    }} placeholder="e.g. SecurityControl" fullWidth size="small"/>
                              <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="body2">:</Typography>
                              <TextField value={row.value} onChange={(event) => {
                        const d = { value: event.target.value };
                        return updateTagRow(i, "value", d.value);
                    }} placeholder="e.g. Ignore" fullWidth size="small"/>
                              <Button onClick={() => removeTagRow(i)} disabled={tagRows.length === 1 && !row.name && !row.value} variant="text" size="small" startIcon={<Close />}/>
                            </div>))}
                          <Button onClick={addTagRow} style={{ marginTop: "8px" }} variant="text" size="small" startIcon={<Add />}>
                            Add tag
                          </Button>
                        </div>)}
                    </div>
                  </div>
                </Card>
              </div>

              <div className="deploy-column">
                {/* Fabric Configuration */}
                <Card className={`${styles.section} ${styles.cardRequired}${activeCardIndex === 2 ? " deploy-card-active" : ""}`}>
                  <CardHeader className={styles.sectionHeader} title={<div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Typography component="div" variant="subtitle1">Fabric Configuration</Typography>
                        {(() => {
                    const { complete, total } = getCardCompletion(2);
                    return complete === total ? (<Chip component="span" size="small" variant="filled" color="success" icon={<CheckCircleOutlined />} label={<>Complete</>}/>) : (<Chip component="span" size="small" variant="filled" color="default" icon={<RadioButtonUnchecked />} label={<>{complete}/{total}</>}/>);
                })()}
                      </div>} subheader={"Microsoft Fabric workspace where RTI, Lakehouses, and Data Agents are deployed"}/>
                  <div className={styles.fieldGroup}>
                    <FormControl required={!useNamingConvention}><FormLabel id="field-deploywizard-7-label" htmlFor="field-deploywizard-7">{<Tooltip title={"The Fabric workspace must already exist. Eventhouse, KQL databases, Eventstream, Lakehouses, and Data Agents will be created here."} describeChild><Box component="span">
                          <span className={styles.fieldLabelWithIcon}>
                            <img src="/fabric_16_color.svg" alt="" width={16} height={16}/>
                            <span className={styles.labelSeparator}/>
                            Fabric Workspace Name
                          </span>
                        </Box></Tooltip>}</FormLabel>
                      <HistoryInput field="fabric-workspace" value={config.fabric_workspace_name} onChange={(v) => update("fabric_workspace_name", v)} disabled={useNamingConvention} placeholder={useNamingConvention ? "Set via naming convention above" : "e.g. med-device-rti-hds"} id="field-deploywizard-7"/>
                    </FormControl>
                    {selectedCapacity && showAdvanced && (<FormControlLabel label={`Pause capacity "${formatSelectedCapacityLabel(selectedCapacity)}" after successful deployment`} control={<Checkbox checked={pauseAfterDeploy} onChange={(event) => {
                        const d = { checked: event.target.checked };
                        return setPauseAfterDeploy(!!d.checked);
                    }}/>}/>)}
                  </div>
                </Card>

                {/* Data Configuration */}
                <Card className={`${styles.section} ${styles.cardRequired}${activeCardIndex === 3 ? " deploy-card-active" : ""}`} style={{ overflow: "visible" }}>
                  <CardHeader className={styles.sectionHeader} title={<div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Typography component="div" variant="subtitle1">Data Configuration</Typography>
                        {(() => {
                    const { complete, total } = getCardCompletion(3);
                    return complete === total ? (<Chip component="span" size="small" variant="filled" color="success" icon={<CheckCircleOutlined />} label={<>Complete</>}/>) : (<Chip component="span" size="small" variant="filled" color="error" label={<>Required</>}/>);
                })()}
                      </div>} subheader={"Synthetic patient data generation and alerting"}/>
                  <div className={styles.fieldGroup}>

                    {/* Existing deployment detection banner */}
                    {checkingExisting && (<div style={{
                    padding: "12px",
                    backgroundColor: "var(--m3-colorNeutralBackground4)",
                    borderLeft: `4px solid ${"var(--m3-colorBrandStroke1)"}`,
                    borderRadius: "16px",
                    marginBottom: "12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                }}>
                        <Chip component="span" size="small" variant="filled" color="default" label={<>Checking</>}/>
                        <Typography component="span" variant="caption">Checking local deployment history...</Typography>
                      </div>)}

                    {existingDeploy && (<div style={{
                    padding: "16px",
                    backgroundColor: "var(--m3-colorStatusWarningBackground1)",
                    borderLeft: `4px solid ${"var(--m3-colorStatusWarningBorderActive)"}`,
                    borderRadius: "16px",
                    marginBottom: "12px",
                }}>
                        <div onClick={() => setExistingDeployCollapsed(!existingDeployCollapsed)} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
                          <Typography component="span" variant="body2" sx={{
                    fontWeight: 600
                }}>
                            Previous deployment detected
                          </Typography>
                          {existingDeployCollapsed ? <ExpandMore /> : <ExpandLess />}
                        </div>
                        <div className={`deploy-collapsible-content${existingDeployCollapsed ? " deploy-collapsible-collapsed" : ""}`} style={{ maxHeight: existingDeployCollapsed ? "0" : "640px" }}>
                          <Typography style={{ marginTop: 4, color: "var(--m3-colorNeutralForeground2)" }} component="div" variant="caption">
                            Workspace <strong>{existingDeploy.workspaceName}</strong> was deployed on{" "}
                            {new Date(existingDeploy.createdTime).toLocaleString()}
                          </Typography>
                          <Button onClick={runLiveExistingValidation} style={{ marginTop: "12px" }} disabled={deepCheckingExisting} variant="outlined" size="small">
                            {deepCheckingExisting ? "Validating live Azure/FHIR state…" : "Run live Azure/FHIR validation"}
                          </Button>
                          {existingDeploy.azureRgExists && (<>
                              <Typography style={{ marginTop: 4 }} component="div" variant="caption">
                                FHIR: <strong>{existingDeploy.fhirPatientCount}</strong> patients,{" "}
                                <strong>{existingDeploy.fhirDeviceCount}</strong> Masimo devices
                              </Typography>
                              <Tooltip title={"FHIR $export writes NDJSON files to ADLS Gen2. HDS pipelines, Bronze Lakehouse shortcuts, and Silver/Gold tables all depend on this data. If 0, the $export has not run yet — it will be triggered automatically on deploy."} describeChild>
                                <Typography style={{
                        marginTop: 4,
                        padding: `${"4px"} ${"12px"}`,
                        borderRadius: "16px",
                        backgroundColor: (existingDeploy.exportedFiles ?? 0) === 0
                            ? "var(--m3-colorStatusDangerBackground1)" : "transparent",
                        cursor: "help",
                    }} component="div" variant="caption">
                                  {(existingDeploy.exportedFiles ?? 0) === 0 && (<Chip style={{ marginRight: 6 }} component="span" size="small" variant="filled" color="error" label={<>Critical</>}/>)}
                                  Storage: <strong>{existingDeploy.exportedFiles ?? 0}</strong> exported FHIR files,{" "}
                                  <strong>{existingDeploy.dicomStudies ?? 0}</strong> DICOM imaging blobs
                                  {(existingDeploy.exportedFiles ?? 0) === 0 && (<span style={{ color: "var(--m3-colorStatusDangerForeground1)", marginLeft: 6 }}>
                                      — $export required for HDS pipelines
                                    </span>)}
                                </Typography>
                              </Tooltip>
                              <Typography style={{ marginTop: 2 }} component="div" variant="caption">
                                {existingDeploy.emulatorRunning ? (<>Emulator: <strong style={{ color: "var(--m3-colorPaletteGreenForeground1)" }}>running</strong> ({existingDeploy.emulatorDeviceCount ?? 100} devices streaming telemetry)</>) : (<>Emulator: <strong style={{ color: "var(--m3-colorStatusDangerForeground1)" }}>stopped</strong></>)}
                              </Typography>
                            </>)}
                          <div className={styles.dataStrategyControl}>
                            <Typography component="span" variant="body2" sx={{
                    fontWeight: 600
                }}>Existing FHIR data strategy</Typography>
                            <RadioGroup aria-label="Existing FHIR data strategy" value={config.reseed_data ? "reseed" : config.reuse_patients ? "reuse" : ""} onChange={(_event, value) => {
                    const data = { value: value };
                    return update(data.value === "reseed" ? "reseed_data" : "reuse_patients", true);
                }}>
                              <div className={styles.dataStrategyChoice}>
                                <FormControlLabel label={"Keep and reuse current data"} control={<Radio value="reuse"/>}/>
                                <Typography className={styles.dataStrategyDescription} component="span" variant="caption">
                                  Keep the existing {existingDeploy.fhirPatientCount} patients and {existingDeploy.fhirDeviceCount} devices. Patient Count is not applied.
                                </Typography>
                              </div>
                              <div className={styles.dataStrategyChoice}>
                                <FormControlLabel label={"Reseed and replace data"} control={<Radio value="reseed"/>}/>
                                <Typography className={styles.dataStrategyDescription} component="span" variant="caption">
                                  Delete the current FHIR data, then load the selected final patient total.
                                </Typography>
                              </div>
                            </RadioGroup>
                            {config.scaffolding_only && (<Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">
                                Data loading remains disabled in zero-data scaffolding mode.
                              </Typography>)}
                            {config.reseed_data && (<Alert className={styles.reseedWarning} severity={"warning"}>
                                <Box>
                                  <Typography component="span" variant="body2" sx={{
                        fontWeight: 600
                    }}>Permanent data replacement: </Typography>
                                  Reseeding permanently replaces all FHIR data before loading the final Patient Count below. Synthea/FHIR loading, FHIR export, and downstream HDS pipelines rerun.
                                </Box>
                              </Alert>)}
                          </div>
                        </div>
                      </div>)}

                    <FormControl><FormLabel id="field-deploywizard-8-label" htmlFor="field-deploywizard-8">{<Tooltip title={"Number of synthetic patients generated by Synthea. More patients = longer FHIR load time. 100 patients ≈ 15 min."} describeChild><Box component="span">
                          <span className={styles.fieldLabelWithIcon}>
                            <img src="/icon-patient.svg" alt="" width={14} height={14}/>
                            <span className={styles.labelSeparator}/>
                            Patient Count{config.scaffolding_only ? " (not used in zero-data mode)" : config.reuse_patients ? " (not changed — reusing existing)" : config.reseed_data && config.use_cached_synthea ? " (final replacement total — cached at 100)" : config.use_cached_synthea ? " (fixed cached total)" : config.reseed_data ? " (final replacement total)" : " (final total to load)"}
                          </span>
                        </Box></Tooltip>}</FormLabel>
                      <TextField value={config.patient_count} onChange={(event) => {
                const d = { value: event.target.value === "" ? null : Number(event.target.value), displayValue: event.target.value };
                // Respect what the user enters: prefer the numeric value, else parse the
                // typed display string; never silently snap back to a default.
                const parsed = d.value ?? (d.displayValue != null ? parseInt(d.displayValue, 10) : NaN);
                if (!Number.isNaN(parsed))
                    update("patient_count", parsed);
            }} disabled={config.scaffolding_only || config.reuse_patients || config.use_cached_synthea} fullWidth size="small" type="number" slotProps={{ htmlInput: { min: 10, max: 10000, step: 10 } }} id="field-deploywizard-8"/>
                    </FormControl>
                    <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "8px", marginBottom: "12px" }}>
                      <FormControlLabel label={"Use cached canonical Synthea fixture (fixed at 100 patients)"} control={<Checkbox checked={config.use_cached_synthea} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("use_cached_synthea", !!d.checked);
                }} disabled={config.reuse_patients || config.skip_synthea}/>} disabled={config.reuse_patients || config.skip_synthea}/>
                      <Typography style={{ color: "var(--m3-colorNeutralForeground3)", paddingLeft: 28 }} component="span" variant="caption">
                        {config.scaffolding_only
                ? "No patient bundles are generated or loaded in scaffolding-only mode."
                : config.use_cached_synthea
                    ? "The cached canonical fixture contains exactly 100 patients. Patient Count is locked to 100; the FHIR loader still runs."
                    : "Generates new randomized patient and medical device telemetry data on-the-fly using an Azure Synthea container."}
                      </Typography>
                    </div>
                    <FormControl required><FormLabel id="field-deploywizard-9-label" htmlFor="field-deploywizard-9">{<Tooltip title={"Email address for clinical alert notifications via Data Activator (Reflex)."} describeChild><Box component="span">
                          Alert Email
                        </Box></Tooltip>}</FormLabel>
                      <HistoryInput field="alert-email" value={config.alert_email} onChange={(v) => update("alert_email", v)} placeholder="operator@example.com" type="email" id="field-deploywizard-9"/>
                    </FormControl>
                  </div>
                </Card>

                {/* Phase & Component Control */}
                <Card className={`${styles.section} ${styles.cardOptional}`}>
                  <CardHeader className={styles.sectionHeader} title={<div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Typography component="div" variant="subtitle1">Phase &amp; Component Control</Typography>
                        <Chip component="span" size="small" variant="filled" color="default" label={<>Optional</>}/>
                      </div>} subheader={<span className={styles.fieldLabelWithIcon}>
                        <img src="/icon-phases.svg" alt="" width={14} height={14}/>
                        <span className={styles.labelSeparator}/>
                        Toggle individual components — dependencies auto-adjust
                      </span>}/>
                  <div className={styles.checkboxGroup}>
                    {/* ── Group 1: Infrastructure & Data Ingestion (Phase 1) ── */}
                    <div onClick={() => setSkipGroup1Collapsed(!skipGroup1Collapsed)} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 12px",
                backgroundColor: "var(--m3-colorNeutralBackground3)",
                borderRadius: "16px",
                cursor: "pointer",
                userSelect: "none",
                marginTop: "8px",
                borderLeft: `4px solid ${"var(--m3-colorBrandStroke1)"}`
            }}>
                      <Typography style={{ color: "var(--m3-colorBrandForeground1)" }} component="span" variant="body2" sx={{
                fontWeight: 600
            }}>
                        1. Data Fabric Foundation
                      </Typography>
                      {skipGroup1Collapsed ? <ExpandMore /> : <ExpandLess />}
                    </div>
                    <div className={`deploy-collapsible-content ${skipGroup1Collapsed ? "deploy-collapsible-collapsed" : ""}`} style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "8px 12px 12px", transition: "all 0.3s ease" }}>
                      <Tooltip title={"Skip Event Hub, ACR, emulator ACI, Storage, and Bicep infra"} describeChild>
                        <FormControlLabel label={`${config.scaffolding_only ? "Azure Infrastructure Scaffold" : "Azure Synthetic Data Foundation"}${existingDeploy ? " (already deployed)" : ""}`} control={<Checkbox checked={!config.skip_base_infra} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_base_infra", !d.checked);
                }}/>}/>
                      </Tooltip>
                      <Tooltip title={"Skip FHIR R4 service deployment and data loading"} describeChild>
                        <FormControlLabel label={`FHIR Service + Data Loading${existingDeploy ? " (already deployed)" : ""}`} control={<Checkbox checked={!config.skip_fhir} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_fhir", !d.checked);
                }} disabled={config.skip_base_infra}/>} disabled={config.skip_base_infra}/>
                      </Tooltip>
                      <div style={{ paddingLeft: 24, display: "flex", flexDirection: "column", gap: "8px" }}>
                        <Tooltip title={"Skip Synthea patient generation — use existing patients"} describeChild>
                          <FormControlLabel label={"Synthea Patient Generation"} control={<Checkbox checked={!config.skip_synthea} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_synthea", !d.checked);
                }} disabled={config.scaffolding_only || config.skip_fhir}/>} disabled={config.scaffolding_only || config.skip_fhir}/>
                        </Tooltip>
                        {!config.skip_synthea && (<Tooltip title={"Use the cached canonical fixture of exactly 100 patients instead of starting the generation container. Patient Count is locked to 100."} describeChild>
                            <FormControlLabel label={"Use cached canonical fixture (fixed at 100 patients)"} control={<Checkbox checked={config.use_cached_synthea} onChange={(event) => {
                        const d = { checked: event.target.checked };
                        return update("use_cached_synthea", !!d.checked);
                    }} style={{ marginLeft: 24 }} disabled={config.skip_fhir || config.reuse_patients}/>} disabled={config.skip_fhir || config.reuse_patients}/>
                          </Tooltip>)}
                        <Tooltip title={"Skip Device and/or DICOM patient cohort association mapping"} describeChild>
                          <FormControlLabel label={"Device and/or DICOM Association"} control={<Checkbox checked={!config.skip_device_assoc} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_device_assoc", !d.checked);
                }} disabled={config.skip_synthea || config.skip_fhir}/>} disabled={config.skip_synthea || config.skip_fhir}/>
                        </Tooltip>
                      </div>
                      <Tooltip title={"Skip TCIA DICOM download, re-tagging, ADLS upload, and FHIR ImagingStudy creation"} describeChild>
                        <FormControlLabel label={"DICOM Download + Upload"} control={<Checkbox checked={!config.skip_dicom} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_dicom", !d.checked);
                }} disabled={config.scaffolding_only || config.skip_base_infra}/>} disabled={config.scaffolding_only || config.skip_base_infra}/>
                      </Tooltip>
                    </div>

                    {/* ── Group 2: Active Patient Telemetry (Phase 2) ── */}
                    <div onClick={() => setSkipGroup2Collapsed(!skipGroup2Collapsed)} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 12px",
                backgroundColor: "var(--m3-colorNeutralBackground3)",
                borderRadius: "16px",
                cursor: "pointer",
                userSelect: "none",
                marginTop: "12px",
                borderLeft: `4px solid ${"var(--m3-colorPalettePurpleBorderActive)"}`
            }}>
                      <Typography style={{ color: "var(--m3-colorBrandForeground1)" }} component="span" variant="body2" sx={{
                fontWeight: 600
            }}>
                        2. Active Patient Telemetry
                      </Typography>
                      {skipGroup2Collapsed ? <ExpandMore /> : <ExpandLess />}
                    </div>
                    <div className={`deploy-collapsible-content ${skipGroup2Collapsed ? "deploy-collapsible-collapsed" : ""}`} style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "8px 12px 12px", transition: "all 0.3s ease" }}>
                      <Tooltip title={"Skip Masimo Eventhouse, KQL database/functions, Eventstream topology, core dashboard, and FHIR $export"} describeChild>
                        <FormControlLabel label={"Fabric RTI ingest (Eventhouse + Eventstream)"} control={<Checkbox checked={!config.skip_fabric} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_fabric", !d.checked);
                }}/>}/>
                      </Tooltip>
                      <div style={{ paddingLeft: 24 }}>
                        <Tooltip title={"Skip FHIR $export to ADLS Gen2 — HDS pipelines need this data"} describeChild>
                          <FormControlLabel label={"FHIR $export to ADLS"} control={<Checkbox checked={!config.skip_fhir_export} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_fhir_export", !d.checked);
                }} disabled={config.scaffolding_only || config.skip_fabric || config.skip_fhir}/>} disabled={config.scaffolding_only || config.skip_fabric || config.skip_fhir}/>
                        </Tooltip>
                      </div>
                      <Tooltip title={"Skip RTI Phase 2 — KQL→Silver shortcuts and enriched alert functions"} describeChild>
                        <FormControlLabel label={"RTI Phase 2 (Shortcuts + Enrichment)"} control={<Checkbox checked={!config.skip_rti_phase2} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_rti_phase2", !d.checked);
                }} disabled={config.scaffolding_only || config.skip_fabric}/>} disabled={config.scaffolding_only || config.skip_fabric}/>
                      </Tooltip>
                    </div>

                    {/* ── Group 3: HDS Bridge, Semantic UX, and Analytics (Phases 3-6) ── */}
                    <div onClick={() => setSkipGroup3Collapsed(!skipGroup3Collapsed)} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 12px",
                backgroundColor: "var(--m3-colorNeutralBackground3)",
                borderRadius: "16px",
                cursor: "pointer",
                userSelect: "none",
                marginTop: "12px",
                borderLeft: `4px solid ${"var(--m3-colorPaletteTealBorderActive)"}`
            }}>
                      <Typography style={{ color: "var(--m3-colorBrandForeground1)" }} component="span" variant="body2" sx={{
                fontWeight: 600
            }}>
                        3. HDS Bridge, Semantic UX &amp; Analytics (Phases 3-6)
                      </Typography>
                      {skipGroup3Collapsed ? <ExpandMore /> : <ExpandLess />}
                    </div>
                    <div className={`deploy-collapsible-content ${skipGroup3Collapsed ? "deploy-collapsible-collapsed" : ""}`} style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "8px 12px 12px", transition: "all 0.3s ease" }}>
                      <Tooltip title={config.skip_dicom
                ? "Runs clinical + OMOP ingestion and row gates. Imaging ingestion is auto-excluded because DICOM loading is off."
                : "Skip DICOM shortcut creation, HDS clinical/imaging/OMOP pipeline triggers, and row-count gates"} describeChild>
                        <FormControlLabel label={<span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                              HDS Bridge + Row Gates
                              {config.skip_dicom
                    ? <Chip component="span" size="small" variant="filled" color="warning" label={<>imaging excluded (no DICOM) · ~34m</>}/> : <Chip component="span" size="small" variant="filled" color="default" label={<>~59m</>}/>}
                            </span>} control={<Checkbox checked={!config.skip_hds_pipelines} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_hds_pipelines", !d.checked);
                }} disabled={config.scaffolding_only}/>} disabled={config.scaffolding_only}/>
                      </Tooltip>
                      <Tooltip title={"Skip Cohorting Agent, OHIF DICOM Viewer, PBI Imaging Report"} describeChild>
                        <FormControlLabel label={"Imaging Toolkit (Cohorting, Viewer, Report)"} control={<Checkbox checked={!config.skip_imaging} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_imaging", !d.checked);
                }} disabled={config.skip_dicom}/>} disabled={config.skip_dicom}/>
                      </Tooltip>
                      <Tooltip title={"Skip ClinicalDeviceOntology (9 entities), DeviceAssociation table, agent binding"} describeChild>
                        <FormControlLabel label={"Ontology + Agent Binding"} control={<Checkbox checked={!config.skip_ontology} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_ontology", !d.checked);
                }} disabled={config.scaffolding_only}/>} disabled={config.scaffolding_only}/>
                      </Tooltip>
                      <Tooltip title={"Skip Patient 360 + Clinical Triage Data Agents deployed after ontology"} describeChild>
                        <FormControlLabel label={"Ontology-aware Data Agents"} control={<Checkbox checked={!config.skip_data_agents} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_data_agents", !d.checked);
                }} disabled={config.scaffolding_only}/>} disabled={config.scaffolding_only}/>
                      </Tooltip>
                      <Tooltip title={`Skip Data Activator Reflex + email rule${!config.alert_email ? " (no alert email set)" : ""}`} describeChild>
                        <FormControlLabel label={"Data Activator (Email Alerts)"} control={<Checkbox checked={!config.skip_activator} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_activator", !d.checked);
                }} disabled={config.scaffolding_only || config.skip_fabric || !config.alert_email}/>} disabled={config.scaffolding_only || config.skip_fabric || !config.alert_email}/>
                      </Tooltip>
                      <Tooltip title={"Skip Population Health & Quality Dashboard — claims materialization, Star Ratings, HCC risk adjustment, readmission risk model, cost & utilization analytics, and Power BI report"} describeChild>
                        <FormControlLabel label={"Population Health & Quality Dashboard (10-page report)"} control={<Checkbox checked={!config.skip_quality_measures} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_quality_measures", !d.checked);
                }} disabled={config.scaffolding_only}/>} disabled={config.scaffolding_only}/>
                      </Tooltip>
                    </div>

                    {/* ── Group 4: Payer RTI & Ops (Phase 7) ── */}
                    <div onClick={() => setSkipGroup4Collapsed(!skipGroup4Collapsed)} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 12px",
                backgroundColor: "var(--m3-colorNeutralBackground3)",
                borderRadius: "16px",
                cursor: "pointer",
                userSelect: "none",
                marginTop: "12px",
                borderLeft: `4px solid ${"var(--m3-colorPaletteBerryBorderActive)"}`
            }}>
                      <Typography style={{ color: "var(--m3-colorBrandForeground1)" }} component="span" variant="body2" sx={{
                fontWeight: 600
            }}>
                        4. Payer RTI &amp; Ops (Phase 7)
                      </Typography>
                      {skipGroup4Collapsed ? <ExpandMore /> : <ExpandLess />}
                    </div>
                    <div className={`deploy-collapsible-content ${skipGroup4Collapsed ? "deploy-collapsible-collapsed" : ""}`} style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "8px 12px 12px", transition: "all 0.3s ease" }}>
                      <Tooltip title={"Skip Phase 7 entirely"} describeChild>
                        <FormControlLabel label={"Payer RTI & Ops (Phase 7)"} control={<Checkbox checked={!config.skip_phase7} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_phase7", !d.checked);
                }} disabled={config.skip_fabric}/>} disabled={config.skip_fabric}/>
                      </Tooltip>
                      <div style={{ paddingLeft: 24, display: "flex", flexDirection: "column", gap: "8px" }}>
                        <Tooltip title={config.scaffolding_only ? "Deploy claim-stream, payer KQL scoring, and Eventstream definitions without the claim emulator" : "Deploy claim-stream, payer KQL scoring, claim emulator, and Eventstream extension"} describeChild>
                          <FormControlLabel label={config.scaffolding_only ? "Payer RTI scoring + claim stream (no producer)" : "Payer RTI scoring + claim stream"} control={<Checkbox checked={!config.skip_payer_rti} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_payer_rti", !d.checked);
                }} disabled={config.skip_phase7}/>} disabled={config.skip_phase7}/>
                        </Tooltip>
                        <Tooltip title={"Deploy PayerOpsActivator Reflex email alerts"} describeChild>
                          <FormControlLabel label={"Payer Ops Activator"} control={<Checkbox checked={!config.skip_payer_activator} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_payer_activator", !d.checked);
                }} disabled={config.scaffolding_only || config.skip_phase7 || (!config.alert_email && !config.payer_ops_email)}/>} disabled={config.scaffolding_only || config.skip_phase7 || (!config.alert_email && !config.payer_ops_email)}/>
                        </Tooltip>
                        <Tooltip title={"Deploy HealthcareOpsAgent and Payer Ops Triage"} describeChild>
                          <FormControlLabel label={"HealthcareOpsAgent + Payer Ops Triage"} control={<Checkbox checked={!config.skip_ops_agent} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_ops_agent", !d.checked);
                }} disabled={config.skip_phase7}/>} disabled={config.skip_phase7}/>
                        </Tooltip>
                        <Tooltip title={"Deploy Healthcare Graph Agent shell and manual ontology attach instructions"} describeChild>
                          <FormControlLabel label={"Healthcare Graph Agent shell"} control={<Checkbox checked={!config.skip_graph_agent} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return update("skip_graph_agent", !d.checked);
                }} disabled={config.skip_phase7}/>} disabled={config.skip_phase7}/>
                        </Tooltip>
                        <FormControl><FormLabel id="field-deploywizard-10-label" htmlFor="field-deploywizard-10">{"Payer Ops Email"}</FormLabel>
                          <HistoryInput field="payer-ops-email" type="email" value={config.payer_ops_email} onChange={(value) => update("payer_ops_email", value)} placeholder={config.alert_email || "ops@example.com"} disabled={config.skip_phase7 || config.skip_payer_activator} suggestions={config.alert_email ? [config.alert_email] : []} suggestionsLabel="Alert email" id="field-deploywizard-10"/>
                        </FormControl>
                        <FormControl><FormLabel id="field-deploywizard-11-label" htmlFor="field-deploywizard-11">{"Claim event rate/min"}</FormLabel>
                          <TextField value={config.claim_event_rate_per_minute} onChange={(event) => {
                const d = { value: event.target.value === "" ? null : Number(event.target.value), displayValue: event.target.value };
                return update("claim_event_rate_per_minute", Number(d.value ?? d.displayValue ?? 60));
            }} disabled={config.scaffolding_only || config.skip_phase7 || config.skip_payer_rti} fullWidth size="small" type="number" slotProps={{ htmlInput: { min: 1, max: 1000 } }} id="field-deploywizard-11"/>
                        </FormControl>
                      </div>
                    </div>
                  </div>
                </Card>
              </div>
            </div>

            <Card className={`${styles.section} ${styles.cardOptional}`}>
              <CardHeader title={<Typography component="div" variant="subtitle1">Optional add-ons</Typography>} subheader={"Run these after the base deployment, or add them later from a completed deployment's monitor."}/>
              <div className={styles.fieldGroup}>
                <AddonFields value={config} onChange={(patch) => setConfig((previous) => ({ ...previous, ...patch }))} disabled={loading} adminGroup={config.admin_security_group}/>
              </div>
            </Card>

            {error && <div className={styles.error} ref={(el) => el?.scrollIntoView({ behavior: "smooth" })}>{error}</div>}
          </div>)}

        {/* Actions */}
        {validationErrors.length > 0 && !initializing && (<div style={{
                marginTop: "24px",
                padding: `${"8px"} ${"16px"}`,
                backgroundColor: "var(--m3-colorStatusWarningBackground1)",
                borderLeft: `4px solid ${"var(--m3-colorStatusWarningBorderActive)"}`,
                borderRadius: "16px",
            }}>
            <Typography component="div" variant="caption" sx={{
                fontWeight: 600
            }}>Complete these required fields before deployment:</Typography>
            {validationErrors.map((issue) => (<Typography key={issue} style={{ color: "var(--m3-colorNeutralForeground2)" }} component="div" variant="caption">• {issue}</Typography>))}
          </div>)}

        {/* Advanced JSON Configuration Editor */}
        <div style={{ marginTop: "16px", marginBottom: "16px" }}>
          <Button onClick={() => setShowJsonEditor(v => !v)} style={{ color: "var(--m3-colorBrandForeground1)", paddingLeft: 0 }} variant="text" size="small">
            {showJsonEditor ? "Hide Raw JSON Configuration" : "Advanced: View/Edit Raw JSON Configuration"}
          </Button>

          {showJsonEditor && (<div style={{ marginTop: "12px" }}>
              <Typography style={{ color: "var(--m3-colorNeutralForeground3)", display: "block", marginBottom: "4px" }} component="span" variant="caption">
                Directly edit parameters. Note: invalid JSON will prevent deployment.
              </Typography>
              <textarea value={JSON.stringify(config, null, 2)} onChange={(e) => {
                try {
                    const parsed = JSON.parse(e.target.value);
                    parsed.reseed_data = parsed.reseed_data === true;
                    if (parsed.scaffolding_only) {
                        Object.assign(parsed, {
                            reuse_patients: false,
                            reseed_data: false,
                            use_cached_synthea: false,
                            skip_synthea: true,
                            skip_device_assoc: true,
                            skip_dicom: true,
                            skip_hds_source: false,
                            skip_fhir_export: true,
                            skip_rti_phase2: true,
                            skip_hds_pipelines: true,
                            skip_data_agents: true,
                            skip_imaging: true,
                            skip_ontology: true,
                            skip_activator: true,
                            skip_quality_measures: true,
                            skip_payer_activator: true,
                        });
                    }
                    else if (parsed.reseed_data) {
                        Object.assign(parsed, {
                            reuse_patients: false,
                            skip_fhir: false,
                            skip_synthea: false,
                            skip_device_assoc: false,
                            skip_fhir_export: false,
                            skip_hds_pipelines: false,
                        });
                    }
                    else if (parsed.reuse_patients) {
                        Object.assign(parsed, {
                            reseed_data: false,
                            use_cached_synthea: false,
                            skip_synthea: true,
                            skip_device_assoc: true,
                        });
                    }
                    if (parsed.use_cached_synthea) {
                        parsed.patient_count = 100;
                    }
                    setConfig({ ...parsed, ...getAddonOptions(parsed) });
                }
                catch {
                    // Keep typing, don't crash on invalid JSON.
                }
            }} style={{
                width: "100%",
                height: "220px",
                fontFamily: "'Cascadia Code', 'Consolas', monospace",
                fontSize: "12px",
                backgroundColor: "#0a0a0a",
                color: "#00f07f", // console green
                border: `1px solid ${"var(--m3-colorNeutralStroke1)"}`,
                borderRadius: "16px",
                padding: "16px",
                boxShadow: "inset 0 0 10px rgba(0,0,0,0.5)",
                outline: "none",
                resize: "vertical"
            }}/>
            </div>)}
        </div>
        <div className={styles.actions}>
          <Tooltip title={"Preview the Azure and Fabric assets that this configuration will deploy"} describeChild>
            <Button onClick={() => setShowResourcePreview(true)} disabled={validationErrors.length > 0} variant="outlined" startIcon={<ContentPaste />}>
              Preview resources
            </Button>
          </Tooltip>
          <Tooltip title={"Run a simulated deployment to preview the UI (no Azure/Fabric resources created)"} describeChild>
            <Button onClick={handleMockDeploy} variant="outlined" size="small" startIcon={<Science />}>
              Mock Deploy
            </Button>
          </Tooltip>
        </div>
      </div>

      {/* Summary Sidebar (wide screens only) */}
      {showSummary && (<div className={styles.summarySidebar} style={{
                width: "280px",
            }}>
          <style>{`
            @media (max-width: 1199px) {
              .${styles.summarySidebar} {
                width: 100% !important;
                position: static !important;
                max-height: none !important;
              }
            }
          `}</style>
          <Card>
            <CardHeader action={<Button onClick={copyDeploymentPlan} variant="text" size="small" startIcon={<ContentPaste />}>Copy plan</Button>} title={<Typography component="div" variant="subtitle1">Deployment Review</Typography>}/>
            <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <Typography component="div" variant="caption" sx={{
                fontWeight: 600
            }}>Deployment Name</Typography>
                <Typography style={{ color: "var(--m3-colorNeutralForeground2)" }} component="div" variant="caption">
                  {namingPrefix || config.fabric_workspace_name || "<not set>"}
                </Typography>
              </div>
              <div>
                <Typography component="div" variant="caption" sx={{
                fontWeight: 600
            }}>Subscription</Typography>
                <Typography style={{ color: "var(--m3-colorNeutralForeground2)" }} component="div" variant="caption">
                  {subscriptions.find(s => s.id === selectedSubscription)?.name?.substring(0, 25) || "<not selected>"}
                </Typography>
              </div>
              <div>
                <Typography component="div" variant="caption" sx={{
                fontWeight: 600
            }}>Capacity</Typography>
                <Typography style={{ color: "var(--m3-colorNeutralForeground2)" }} component="div" variant="caption">
                  {selectedCapacity ? formatSelectedCapacityLabel(selectedCapacity) : "<not selected>"}
                </Typography>
              </div>
              <div>
                <Typography component="div" variant="caption" sx={{
                fontWeight: 600
            }}>{config.reseed_data ? "Final Patient Count" : "Patient Count"}</Typography>
                <Typography style={{ color: "var(--m3-colorNeutralForeground2)" }} component="div" variant="caption">
                  {config.reuse_patients
                ? `${existingDeploy?.fhirPatientCount ?? config.patient_count} (kept)`
                : config.reseed_data
                    ? `${config.patient_count} (replacement total)`
                    : config.patient_count}
                </Typography>
              </div>
              <div style={{ borderTop: `1px solid ${"var(--m3-colorNeutralStroke2)"}`, paddingTop: 12, marginTop: 4 }}>
                <Typography component="div" variant="caption" sx={{
                fontWeight: 600
            }}>Estimated Duration</Typography>
                <Typography style={{ color: "var(--m3-colorBrandForeground1)", marginTop: 4 }} component="div" variant="body2" sx={{
                fontWeight: "bold"
            }}>
                  {getEstimatedDuration()}
                </Typography>
              </div>
              <div>
                <Typography component="div" variant="caption" sx={{
                fontWeight: 600
            }}>Risk / readiness</Typography>
                <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4 }}>
                  {validationErrors.length === 0 ? (<Chip component="span" size="small" variant="filled" color="success" label={<>Required fields complete</>}/>) : (<Chip component="span" size="small" variant="filled" color="warning" label={<>{validationErrors.length} required field(s) missing</>}/>)}
                  {locationUnsupported && <Chip component="span" size="small" variant="filled" color="error" label={<>Unsupported AHDS FHIR region</>}/>}
                  {config.patient_count > 500 && <Chip component="span" size="small" variant="filled" color="warning" label={<>Large patient load</>}/>}
                  {existingDeploy && !overridePriorSettings && <Chip component="span" size="small" variant="filled" color="default" label={<>Existing deployment detected</>}/>}
                  {pauseAfterDeploy && <Chip component="span" size="small" variant="filled" color="default" label={<>Capacity pause after deploy</>}/>}
                </div>
              </div>
              <div>
                <Typography style={{ marginBottom: 4 }} component="div" variant="caption" sx={{
                fontWeight: 600
            }}>Components</Typography>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  {!config.skip_base_infra && <Typography component="span" variant="caption">✓ Infrastructure</Typography>}
                  {!config.skip_fhir && <Typography component="span" variant="caption">✓ FHIR Service</Typography>}
                  {!config.skip_dicom && <Typography component="span" variant="caption">✓ DICOM Loader</Typography>}
                  {!config.skip_fabric && <Typography component="span" variant="caption">✓ Fabric RTI</Typography>}
                  {!config.skip_hds_pipelines && <Typography component="span" variant="caption">✓ HDS Pipelines</Typography>}
                  {!config.skip_data_agents && <Typography component="span" variant="caption">✓ Data Agents</Typography>}
                  {!config.skip_imaging && <Typography component="span" variant="caption">✓ Imaging Toolkit</Typography>}
                  {!config.skip_ontology && <Typography component="span" variant="caption">✓ Ontology</Typography>}
                  {!config.skip_activator && config.alert_email && <Typography component="span" variant="caption">✓ Alerts</Typography>}
                  {!config.skip_quality_measures && <Typography component="span" variant="caption">✓ Pop Health</Typography>}
                </div>
              </div>

              <div style={{ borderTop: `1px solid ${"var(--m3-colorNeutralStroke2)"}`, paddingTop: 12, marginTop: 4 }}>
                <Typography style={{ marginBottom: 8 }} component="div" variant="caption" sx={{
                fontWeight: 600
            }}>Auto Export Options</Typography>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <FormControlLabel label={"Auto Export Results to .XLSX"} control={<Checkbox checked={autoExportXlsx} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return setAutoExportXlsx(!!d.checked);
                }}/>}/>
                  <FormControlLabel label={"Auto Export Results to .CSV"} control={<Checkbox checked={autoExportCsv} onChange={(event) => {
                    const d = { checked: event.target.checked };
                    return setAutoExportCsv(!!d.checked);
                }}/>}/>
                </div>
              </div>

              {Object.keys(config.tags).length > 0 && (<div>
                  <Typography component="div" variant="caption" sx={{
                    fontWeight: 600
                }}>Tags</Typography>
                  {Object.entries(config.tags).slice(0, 3).map(([k, v]) => (<Typography key={k} style={{ color: "var(--m3-colorNeutralForeground3)" }} component="div" variant="caption">
                      {k}: {v}
                    </Typography>))}
                  {Object.keys(config.tags).length > 3 && (<Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">+{Object.keys(config.tags).length - 3} more</Typography>)}
                </div>)}
            </div>
          </Card>
        </div>)}

      <Dialog open={showResourcePreview} onClose={() => {
            const data = { open: false };
            setShowResourcePreview(data.open);
        }} fullWidth maxWidth="xl" slotProps={{ paper: { sx: { maxWidth: "1440px", width: "calc(100vw - 32px)", m: 2, overflowX: "hidden" } } }}>
        <Box sx={{ width: "100%", overflowX: "hidden" }}>
          <DialogTitle sx={{ pb: 1, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 1.5 }}>
            <Box>
              <Typography variant="h6" component="div" sx={{ fontWeight: 700 }}>Prospective deployment resources</Typography>
              <Typography variant="body2" sx={{ color: "var(--m3-colorNeutralForeground2)", mt: 0.5 }}>
                Generated from current wizard settings before deployment. Tokens marked <Chip component="span" size="small" label={uniqueSuffix} sx={{ fontFamily: "monospace", fontSize: "11px", height: 20, mx: 0.5 }}/> resolve to the deterministic 13-character Bicep <code>uniqueString(resourceGroup().id)</code> suffix.
              </Typography>
            </Box>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
              <Button onClick={() => setResourcePreviewMode("cards")} variant={resourcePreviewMode === "cards" ? "contained" : "outlined"} size="small">Resource boxes</Button>
              <Button onClick={() => setResourcePreviewMode("graph")} variant={resourcePreviewMode === "graph" ? "contained" : "outlined"} size="small">Interconnection graph</Button>
              {resourcePreviewMode === "graph" && (<>
                  <Button onClick={() => setResourceGraphZoom((z) => Math.max(0.6, Math.round((z - 0.15) * 100) / 100))} variant="outlined" size="small" sx={{ minWidth: 36, px: 1 }}>−</Button>
                  <Chip component="span" size="small" variant="filled" color="default" label={<>{Math.round(resourceGraphZoom * 100)}%</>}/>
                  <Button onClick={() => setResourceGraphZoom((z) => Math.min(2.0, Math.round((z + 0.15) * 100) / 100))} variant="outlined" size="small" sx={{ minWidth: 36, px: 1 }}>+</Button>
                  <Button onClick={() => setResourceGraphZoom(0.75)} variant="text" size="small">Fit width</Button>
                  <Button onClick={() => setResourceGraphZoom(1)} variant="text" size="small">100%</Button>
                  <Button onClick={resetGraphLayout} variant="text" size="small">Reset layout</Button>
                </>)}
            </Box>
          </DialogTitle>
          <DialogContent dividers sx={{ overflowX: "hidden", pt: 2 }}>
            {loading && deploymentStartMessage && (<div role="status" aria-live="polite" style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px", padding: "12px 16px", borderRadius: "12px", backgroundColor: "var(--m3-colorBrandBackground2)", border: `1px solid ${"var(--m3-colorBrandStroke1)"}` }}>
                <CircularProgress size={18}/>
                <Typography component="span" variant="caption">{deploymentStartMessage}</Typography>
              </div>)}

            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 1, mb: 2, px: 1.5, py: 1, borderRadius: "12px", backgroundColor: "var(--m3-colorNeutralBackground2)", border: "1px solid var(--m3-colorNeutralStroke2)" }}>
              <Typography variant="caption" sx={{ color: "var(--m3-colorNeutralForeground2)", fontWeight: 500 }}>
                <strong>Data flow:</strong> Synthea / TCIA &amp; Emulators → Azure FHIR / ADLS &amp; Event Hubs → Fabric Medallion Lakehouses &amp; Eventhouse KQL → Ontology, Data Agents, Activator &amp; Optional Add-ons
              </Typography>
              <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                <Chip size="small" variant="outlined" label={`${prospectiveAzureAssets.length} Azure`}/>
                <Chip size="small" variant="outlined" color="primary" label={`${prospectiveFabricAssets.length} Fabric`}/>
                {prospectiveAddonAssets.length > 0 && <Chip size="small" variant="outlined" color="success" label={`${prospectiveAddonAssets.length} Add-on`}/>}
              </Box>
            </Box>

            {resourcePreviewMode === "cards" ? (<div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(340px, 1fr))`, gap: "16px", alignItems: "start" }}>
                {/* Column 1: Azure Resource Group */}
                <div style={{ border: `1.5px solid ${"var(--m3-colorPaletteBlueBorderActive)"}`, borderRadius: "16px", padding: "16px", backgroundColor: "var(--m3-colorNeutralBackground2)" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <AzureIcon size={18}/>
                      <Typography component="div" variant="subtitle2" sx={{ fontWeight: 700 }}>Azure Resource Group</Typography>
                    </div>
                    <Chip component="span" size="small" variant="filled" color="default" label={<>{prospectiveAzureAssets.length} assets</>}/>
                  </div>
                  <Typography component="div" variant="caption" sx={{ fontFamily: "monospace", fontWeight: 700, color: "var(--m3-colorPaletteBlueForeground2)", mb: 1.5, display: "block" }}>
                    {config.resource_group_name || "rg-<deployment>"} • {formatAzureLocationLabel(config.location)}
                  </Typography>
                  {Array.from(new Set(prospectiveAzureAssets.map((a) => a.section))).map((section) => (
                    <div key={section} style={{ marginTop: "12px" }}>
                      <Typography component="div" variant="caption" sx={{ fontWeight: 700, fontSize: "10px", letterSpacing: 0.6, textTransform: "uppercase", color: "var(--m3-colorNeutralForeground3)", mb: 0.75 }}>
                        {section}
                      </Typography>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "6px" }}>
                        {prospectiveAzureAssets.filter((a) => a.section === section).map((asset) => (
                          <div key={`${asset.type}-${asset.name}`} style={{ padding: "8px 10px", borderRadius: "10px", backgroundColor: "var(--m3-colorNeutralBackground1)", border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`, display: "flex", flexDirection: "column", gap: "2px" }}>
                            <Typography style={{ color: "var(--m3-colorNeutralForeground3)", fontSize: "10px", fontWeight: 600, textTransform: "uppercase", lineHeight: 1.2 }} component="div" variant="caption">{asset.type}</Typography>
                            <Typography style={{ overflowWrap: "anywhere", fontFamily: "monospace", fontSize: "12px", lineHeight: 1.35 }} component="div" variant="caption" sx={{ fontWeight: 700, color: "var(--m3-colorNeutralForeground1)" }}>{asset.name}</Typography>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Column 2: Fabric Workspace */}
                <div style={{ border: `1.5px solid ${"var(--m3-colorBrandStroke1)"}`, borderRadius: "16px", padding: "16px", backgroundColor: "var(--m3-colorNeutralBackground2)" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <FabricIcon size={18}/>
                      <Typography component="div" variant="subtitle2" sx={{ fontWeight: 700 }}>Fabric Workspace</Typography>
                    </div>
                    <Chip component="span" size="small" variant="filled" color="primary" label={<>{prospectiveFabricAssets.length} assets</>}/>
                  </div>
                  <Typography component="div" variant="caption" sx={{ fontFamily: "monospace", fontWeight: 700, color: "var(--m3-colorBrandForeground1)", mb: 1.5, display: "block" }}>
                    {config.fabric_workspace_name || "<workspace>"} {selectedCapacity ? `• ${formatSelectedCapacityLabel(selectedCapacity)}` : ""}
                  </Typography>
                  {Array.from(new Set(prospectiveFabricAssets.map((a) => a.section))).map((section) => (
                    <div key={section} style={{ marginTop: "12px" }}>
                      <Typography component="div" variant="caption" sx={{ fontWeight: 700, fontSize: "10px", letterSpacing: 0.6, textTransform: "uppercase", color: "var(--m3-colorNeutralForeground3)", mb: 0.75 }}>
                        {section}
                      </Typography>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "6px" }}>
                        {prospectiveFabricAssets.filter((a) => a.section === section).map((asset) => (
                          <div key={`${asset.type}-${asset.name}`} style={{ padding: "8px 10px", borderRadius: "10px", backgroundColor: "var(--m3-colorNeutralBackground1)", border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`, display: "flex", flexDirection: "column", gap: "2px" }}>
                            <Typography style={{ color: "var(--m3-colorNeutralForeground3)", fontSize: "10px", fontWeight: 600, textTransform: "uppercase", lineHeight: 1.2 }} component="div" variant="caption">{asset.type}</Typography>
                            <Typography style={{ overflowWrap: "anywhere", fontFamily: "monospace", fontSize: "12px", lineHeight: 1.35 }} component="div" variant="caption" sx={{ fontWeight: 700, color: "var(--m3-colorNeutralForeground1)" }}>{asset.name}</Typography>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Column 3: Optional Add-ons (when enabled) */}
                {prospectiveAddonAssets.length > 0 && (
                  <div style={{ border: `1.5px solid ${"var(--m3-colorPaletteGreenBorderActive)"}`, borderRadius: "16px", padding: "16px", backgroundColor: "var(--m3-colorNeutralBackground2)" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <Bolt sx={{ fontSize: 18, color: "var(--m3-colorPaletteGreenForeground1)" }}/>
                        <Typography component="div" variant="subtitle2" sx={{ fontWeight: 700 }}>Post-Deploy Add-ons</Typography>
                      </div>
                      <Chip component="span" size="small" variant="filled" color="success" label={<>{prospectiveAddonAssets.length} assets</>}/>
                    </div>
                    <Typography component="div" variant="caption" sx={{ fontFamily: "monospace", fontWeight: 700, color: "var(--m3-colorPaletteGreenForeground1)", mb: 1.5, display: "block" }}>
                      {[config.deploy_databricks && "Databricks", config.deploy_rayfin_apps && "Rayfin Apps", config.deploy_cardiology && "Cardiology"].filter(Boolean).join(" • ")}
                    </Typography>
                    {Array.from(new Set(prospectiveAddonAssets.map((a) => a.section))).map((section) => (
                      <div key={section} style={{ marginTop: "12px" }}>
                        <Typography component="div" variant="caption" sx={{ fontWeight: 700, fontSize: "10px", letterSpacing: 0.6, textTransform: "uppercase", color: "var(--m3-colorNeutralForeground3)", mb: 0.75 }}>
                          {section}
                        </Typography>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "6px" }}>
                          {prospectiveAddonAssets.filter((a) => a.section === section).map((asset) => (
                            <div key={`${asset.type}-${asset.name}`} style={{ padding: "8px 10px", borderRadius: "10px", backgroundColor: "var(--m3-colorNeutralBackground1)", border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`, display: "flex", flexDirection: "column", gap: "2px" }}>
                              <Typography style={{ color: "var(--m3-colorNeutralForeground3)", fontSize: "10px", fontWeight: 600, textTransform: "uppercase", lineHeight: 1.2 }} component="div" variant="caption">{asset.type}</Typography>
                              <Typography style={{ overflowWrap: "anywhere", fontFamily: "monospace", fontSize: "12px", lineHeight: 1.35 }} component="div" variant="caption" sx={{ fontWeight: 700, color: "var(--m3-colorNeutralForeground1)" }}>{asset.name}</Typography>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>) : (<div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: "8px", minWidth: 0, width: "100%" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
                  <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">
                    Tip: click and drag the canvas (or hold <strong>Space + drag</strong> anywhere) to pan like Visio/Draw.io, drag any node or label pill to reposition it, or use the mini-map.
                  </Typography>
                  <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600 }}>
                      <span style={{ width: 12, height: 12, borderRadius: 4, backgroundColor: "var(--m3-colorNeutralBackground3)", border: "1px solid var(--m3-colorNeutralStroke1)" }}/> External Sources
                    </span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600 }}>
                      <span style={{ width: 12, height: 12, borderRadius: 4, backgroundColor: "var(--m3-colorPaletteBlueBackground2)", border: "1px solid var(--m3-colorPaletteBlueBorderActive)" }}/> Azure Resource Group
                    </span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600 }}>
                      <span style={{ width: 12, height: 12, borderRadius: 4, backgroundColor: "var(--m3-colorBrandBackground2)", border: "1px solid var(--m3-colorBrandStroke1)" }}/> Fabric Workspace
                    </span>
                    {anyAddonsEnabled && (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600 }}>
                        <span style={{ width: 12, height: 12, borderRadius: 4, backgroundColor: "var(--m3-colorPaletteGreenBackground2)", border: "1px solid var(--m3-colorPaletteGreenBorderActive)" }}/> Post-Deploy Add-ons
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ position: "relative", minWidth: 0, width: "100%" }}>
                  <div ref={graphContainerRef} onScroll={handleGraphScroll} style={{ border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`, borderRadius: "16px", backgroundColor: "var(--m3-colorNeutralBackground2)", overflow: "auto", padding: "12px", maxHeight: "64vh", width: "100%", maxWidth: "100%" }}>
                    <svg viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`} width={GRAPH_WIDTH * resourceGraphZoom} height={GRAPH_HEIGHT * resourceGraphZoom} role="img" aria-label="Prospective deployment interconnection graph" style={{ display: "block", width: `${GRAPH_WIDTH * resourceGraphZoom}px`, minWidth: `${GRAPH_WIDTH * resourceGraphZoom}px`, height: `${GRAPH_HEIGHT * resourceGraphZoom}px`, minHeight: `${GRAPH_HEIGHT * resourceGraphZoom}px`, maxWidth: "none", flexShrink: 0, cursor: graphDrag ? "grabbing" : "grab", touchAction: "none" }} onPointerDown={startGraphPan} onPointerMove={updateGraphDrag} onPointerUp={endGraphDrag} onPointerCancel={endGraphDrag}>
                    <defs>
                      <marker id="resource-preview-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
                        <path d="M0,0 L0,6 L9,3 z" fill={"var(--m3-colorNeutralForeground2)"}/>
                      </marker>
                    </defs>

                    {/* Zone 0: External Feeds */}
                    <rect x="16" y="20" width="204" height="330" rx="16" fill={"var(--m3-colorNeutralBackground3)"} stroke={"var(--m3-colorNeutralStroke2)"} strokeWidth="1.25" opacity="0.45"/>
                    <text x="32" y="48" fill={"var(--m3-colorNeutralForeground2)"} fontSize="14" style={{ fontWeight: "700", letterSpacing: 0.4 }}>EXTERNAL FEEDS</text>

                    {/* Zone 1: Azure Resource Group (contains ALL Azure producers, loaders, storage, and Event Hubs) */}
                    <rect x="312" y="20" width="512" height="716" rx="18" fill={"var(--m3-colorPaletteBlueBackground2)"} stroke={"var(--m3-colorPaletteBlueBorderActive)"} strokeWidth="1.5" opacity="0.28"/>
                    <text x="332" y="48" fill={"var(--m3-colorPaletteBlueForeground2)"} fontSize="16" style={{ fontWeight: "700" }}>Azure resource group: {config.resource_group_name || "rg-<deployment>"}</text>
                    <rect x="324" y="64" width="200" height="656" rx="12" fill={"var(--m3-colorNeutralBackground1)"} stroke={"var(--m3-colorNeutralStroke2)"} strokeWidth="1" opacity="0.22"/>
                    <text x="338" y="84" fill={"var(--m3-colorNeutralForeground3)"} fontSize="10" letterSpacing="0.8" style={{ userSelect: "none", fontWeight: "700" }}>FHIR &amp; ACI PRODUCERS</text>
                    <rect x="616" y="64" width="196" height="656" rx="12" fill={"var(--m3-colorNeutralBackground1)"} stroke={"var(--m3-colorNeutralStroke2)"} strokeWidth="1" opacity="0.22"/>
                    <text x="630" y="84" fill={"var(--m3-colorNeutralForeground3)"} fontSize="10" letterSpacing="0.8" style={{ userSelect: "none", fontWeight: "700" }}>ADLS GEN2 &amp; EVENT HUBS</text>

                    {/* Zone 2: Microsoft Fabric Workspace (contains Bronze/Eventstream, Silver/Eventhouse/PayerKQL, Gold/Ontology/Reporting/PayerOps, Quality/Agents/Activator/Graph) */}
                    <rect x="912" y="20" width="1112" height="716" rx="18" fill={"var(--m3-colorBrandBackground2)"} stroke={"var(--m3-colorBrandStroke1)"} strokeWidth="1.5" opacity="0.32"/>
                    <text x="932" y="48" fill={"var(--m3-colorBrandForeground1)"} fontSize="16" style={{ fontWeight: "700" }}>Fabric workspace: {config.fabric_workspace_name || "<workspace>"}</text>

                    {/* Fabric Inner Sub-Lanes */}
                    <rect x="922" y="64" width="192" height="656" rx="12" fill={"var(--m3-colorNeutralBackground1)"} stroke={"var(--m3-colorNeutralStroke2)"} strokeWidth="1" opacity="0.22"/>
                    <text x="936" y="84" fill={"var(--m3-colorNeutralForeground3)"} fontSize="10" letterSpacing="0.8" style={{ userSelect: "none", fontWeight: "700" }}>BRONZE &amp; EVENTSTREAM</text>

                    <rect x="1218" y="64" width="196" height="656" rx="12" fill={"var(--m3-colorNeutralBackground1)"} stroke={"var(--m3-colorNeutralStroke2)"} strokeWidth="1" opacity="0.22"/>
                    <text x="1232" y="84" fill={"var(--m3-colorNeutralForeground3)"} fontSize="10" letterSpacing="0.8" style={{ userSelect: "none", fontWeight: "700" }}>SILVER &amp; EVENTHOUSE KQL</text>

                    <rect x="1518" y="64" width="196" height="656" rx="12" fill={"var(--m3-colorNeutralBackground1)"} stroke={"var(--m3-colorNeutralStroke2)"} strokeWidth="1" opacity="0.22"/>
                    <text x="1532" y="84" fill={"var(--m3-colorNeutralForeground3)"} fontSize="10" letterSpacing="0.8" style={{ userSelect: "none", fontWeight: "700" }}>GOLD, ONTOLOGY &amp; BI</text>

                    <rect x="1818" y="64" width="196" height="656" rx="12" fill={"var(--m3-colorNeutralBackground1)"} stroke={"var(--m3-colorNeutralStroke2)"} strokeWidth="1" opacity="0.22"/>
                    <text x="1832" y="84" fill={"var(--m3-colorNeutralForeground3)"} fontSize="10" letterSpacing="0.8" style={{ userSelect: "none", fontWeight: "700" }}>AI AGENTS &amp; ACTIVATOR</text>

                    {/* Zone 3: Optional Post-Deploy Add-ons */}
                    {anyAddonsEnabled && (<>
                        <rect x="2112" y="20" width="212" height="716" rx="18" fill={"var(--m3-colorPaletteGreenBackground2)"} stroke={"var(--m3-colorPaletteGreenBorderActive)"} strokeWidth="1.5" opacity="0.28"/>
                        <text x="2128" y="48" fill={"var(--m3-colorPaletteGreenForeground1)"} fontSize="15" style={{ fontWeight: "700" }}>Optional Add-ons</text>
                      </>)}

                    {/* 1. Render all edge paths */}
                    {graphEdges.map((edge) => {
                const { pathD } = getEdgeGeom(edge);
                return (<path key={`path-${edge.id}`} d={pathD} stroke={"var(--m3-colorNeutralForeground2)"} strokeWidth="2" fill="none" markerEnd="url(#resource-preview-arrow)" opacity="0.72"/>);
            })}

                    {/* 2. Render all node boxes with pure SVG text (zero foreignObject clipping) */}
                    {positionedGraphNodes.map((node) => (<g key={node.id} onPointerDown={(event) => startGraphNodeDrag(event, node.id)} style={{ cursor: "move" }}>
                        <rect x={node.x} y={node.y} width={NODE_WIDTH} height={NODE_HEIGHT} rx="12" fill={graphColor(node.group)} stroke={"var(--m3-colorNeutralStroke1)"} strokeWidth="1.5"/>
                        <text x={node.x + NODE_WIDTH / 2} y={node.y + 28} textAnchor="middle" fill={"var(--m3-colorNeutralForeground1)"} fontSize="12.5" style={{ fontWeight: 700, userSelect: "none" }}>
                          {node.title}
                        </text>
                        <text x={node.x + NODE_WIDTH / 2} y={node.y + 47} textAnchor="middle" fill={"var(--m3-colorNeutralForeground2)"} fontSize="11" style={{ fontFamily: "monospace", fontWeight: 600, userSelect: "none" }}>
                          {node.subtitle.length > 23 ? `${node.subtitle.slice(0, 22)}…` : node.subtitle}
                        </text>
                      </g>))}

                    {/* 3. Render all edge labels on top */}
                    {graphLabelVisible && graphEdges.map((edge) => {
                const { midX, midY, labelWidth } = getEdgeGeom(edge);
                return (<g key={`label-${edge.id}`} onPointerDown={(event) => startGraphLabelDrag(event, edge.id)} style={{ cursor: "move" }}>
                          <rect x={midX - labelWidth / 2} y={midY - 11} width={labelWidth} height="22" rx="11" fill={"var(--m3-colorNeutralBackground1)"} stroke={"var(--m3-colorBrandStroke1)"} strokeWidth="1.1" opacity="0.96"/>
                          <text x={midX} y={midY + 4} textAnchor="middle" fill={"var(--m3-colorNeutralForeground1)"} fontSize="11" style={{ userSelect: "none", fontWeight: "700" }}>{edge.label}</text>
                        </g>);
            })}
                    </svg>
                  </div>

                  {/* Floating Interconnection Mini-Map (pinned to outer wrapper so it stays fixed while scrolling/panning) */}
                  {miniMapCollapsed ? (<Button onClick={() => setMiniMapCollapsed(false)} style={{
                    position: "absolute",
                    bottom: 16,
                    right: 16,
                    zIndex: 10,
                    backgroundColor: "var(--m3-colorNeutralBackground1)",
                    border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
                    boxShadow: "0 8px 24px #00000022",
                    backdropFilter: "blur(8px)",
                    opacity: 0.95,
                    padding: "6px 10px",
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 10,
                    fontWeight: 600,
                }} variant="text" size="small">
                      Show Mini-Map
                    </Button>) : (<div style={{ position: "absolute", bottom: 16, right: 16, width: 210, height: 112, backgroundColor: "var(--m3-colorNeutralBackground1)", border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`, borderRadius: "14px", boxShadow: "0 8px 24px #00000022", padding: 6, display: "flex", flexDirection: "column", gap: 4, zIndex: 10, pointerEvents: "auto", backdropFilter: "blur(8px)", opacity: 0.95 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" }}>
                        <Typography style={{ color: "var(--m3-colorNeutralForeground3)", fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5 }} component="span" variant="caption" sx={{
                    fontWeight: 600
                }}>Interconnection Mini-Map</Typography>
                        <Button onClick={() => setMiniMapCollapsed(true)} style={{ minWidth: "auto", padding: 2, height: 16, width: 16 }} variant="text" size="small" startIcon={<Close style={{ fontSize: 10 }}/>}/>
                      </div>
                      <div style={{ flex: 1, position: "relative", border: `1px dashed ${"var(--m3-colorNeutralStroke3)"}`, borderRadius: "8px", overflow: "hidden", backgroundColor: "var(--m3-colorNeutralBackground2)" }}>
                        <svg viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`} style={{ width: "100%", height: "100%", cursor: "crosshair", touchAction: "none" }} onPointerDown={handleMiniMapPointerDown} onPointerMove={handleMiniMapPointerMove} onPointerUp={handleMiniMapPointerUp}>
                          <rect x="312" y="20" width="512" height="716" rx="35" fill={"var(--m3-colorPaletteBlueBackground2)"} opacity="0.28"/>
                          <rect x="912" y="20" width="1112" height="716" rx="35" fill={"var(--m3-colorBrandBackground2)"} opacity="0.32"/>
                          {anyAddonsEnabled && <rect x="2112" y="20" width="212" height="716" rx="35" fill={"var(--m3-colorPaletteGreenBackground2)"} opacity="0.28"/>}
                          {graphEdges.map((edge) => {
                    const { pathD } = getEdgeGeom(edge);
                    return <path key={`mini-path-${edge.id}`} d={pathD} stroke={"var(--m3-colorNeutralForeground3)"} strokeWidth="12" fill="none" opacity="0.45"/>;
                })}
                          {positionedGraphNodes.map((node) => (<rect key={`mini-node-${node.id}`} x={node.x} y={node.y} width={NODE_WIDTH} height={NODE_HEIGHT} rx="25" fill={graphColor(node.group)} opacity="0.85"/>))}
                          {/* Active Viewport Tracking Indicator */}
                          <rect x={resourceGraphZoom > 0 ? scrollState.scrollLeft / resourceGraphZoom : 0} y={resourceGraphZoom > 0 ? scrollState.scrollTop / resourceGraphZoom : 0} width={Math.min(GRAPH_WIDTH, resourceGraphZoom > 0 ? scrollState.clientWidth / resourceGraphZoom : GRAPH_WIDTH)} height={Math.min(GRAPH_HEIGHT, resourceGraphZoom > 0 ? scrollState.clientHeight / resourceGraphZoom : GRAPH_HEIGHT)} fill="rgba(98, 100, 167, 0.1)" stroke={"var(--m3-colorBrandStroke1)"} strokeWidth="20" rx="18" style={{ transition: "stroke 0.25s, fill 0.25s" }}/>
                        </svg>
                      </div>
                    </div>)}
                </div>
              </div>)}
          </DialogContent>
          <DialogActions sx={{ px: 3, py: 1.5 }}>
            {existingDeploy && (<Button onClick={runLiveExistingValidation} disabled={deepCheckingExisting} variant="text">
                {deepCheckingExisting ? "Validating live state…" : "Run live validation"}
              </Button>)}
            <Button onClick={copyDeploymentPlan} disabled={loading} variant="text">Copy plan</Button>
            <Button onClick={() => setShowResourcePreview(false)} disabled={loading} variant="contained">Close preview</Button>
          </DialogActions>
        </Box>
      </Dialog>
    </div></GuidedDeployment>);
}
