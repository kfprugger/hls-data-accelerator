import { Alert, Box, Button, Card, CardHeader, Chip, Typography } from "@mui/material";
import { CancelOutlined, CheckCircleOutlined, ContentPaste, OpenInNew, Sync, WarningAmber } from "@mui/icons-material";
import { makeStyles } from "@griffel/react";
import { useMemo, useState } from "react";


import { useAppState } from "../AppState";

const useStyles = makeStyles({
    header: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        gap: "24px",
        marginBottom: "24px",
    },
    grid: {
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
        gap: "24px",
    },
    cardBody: {
        padding: `0 ${"24px"} ${"24px"}`,
        display: "grid",
        gap: "12px",
    },
    kv: {
        display: "grid",
        gridTemplateColumns: "112px 1fr",
        gap: "12px",
        fontSize: "12px",
    },
    label: {
        color: "var(--m3-colorNeutralForeground3)",
        fontWeight: 600,
    },
    value: {
        overflowWrap: "anywhere",
        fontFamily: "'Cascadia Code', 'Consolas', monospace",
    },
    command: {
        padding: "16px",
        borderRadius: "16px",
        backgroundColor: "var(--m3-colorNeutralBackground3)",
        border: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        fontFamily: "'Cascadia Code', 'Consolas', monospace",
        fontSize: "12px",
        whiteSpace: "pre-wrap",
    },
    actionRow: {
        display: "flex",
        gap: "12px",
        flexWrap: "wrap",
        alignItems: "center",
    },
});

const PREFLIGHT_ANIMATION_CSS = `
@keyframes preflight-pulse {
  0% { opacity: 0.65; transform: scale(0.98); }
  50% { opacity: 1; transform: scale(1.02); }
  100% { opacity: 0.65; transform: scale(0.98); }
}
@keyframes preflight-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.preflight-loading-icon {
  animation: preflight-spin 1.4s linear infinite !important;
}
.preflight-card-pulse {
  animation: preflight-pulse 1.8s ease-in-out infinite !important;
}
`;

function statusBadge(ok: boolean, pending = false) {
    if (pending) {
        return (<Chip className="preflight-card-pulse" style={{ padding: "6px 12px", fontSize: "14px" }} component="span" size="small" variant="filled" color="default" icon={<Sync className="preflight-loading-icon"/>} label={<>
        Validating context...
      </>}/>);
    }
    return ok
        ? <Chip style={{ padding: "6px 12px", fontSize: "14px" }} component="span" size="small" variant="filled" color="success" icon={<CheckCircleOutlined />} label={<>Ready for Deployment</>}/> : <Chip style={{ padding: "6px 12px", fontSize: "14px" }} component="span" size="small" variant="filled" color="error" icon={<CancelOutlined />} label={<>Needs attention</>}/>;
}

function checkBadge(ok: boolean, pending = false) {
    if (pending) {
        return (<Chip className="preflight-card-pulse" component="span" size="small" variant="filled" color="default" icon={<Sync className="preflight-loading-icon"/>} label={<>
        Checking
      </>}/>);
    }
    return ok
        ? <Chip component="span" size="small" variant="filled" color="success" icon={<CheckCircleOutlined />} label={<>Pass</>}/> : <Chip component="span" size="small" variant="filled" color="warning" icon={<WarningAmber />} label={<>Fix</>}/>;
}

function copy(text: string) {
  navigator.clipboard?.writeText(text).catch(() => undefined);
}

export function Preflight() {
    const styles = useStyles();
    const { authContext, authContextLoading, refreshAuthContext, subscriptions, capacities, selectedSubscription, } = useAppState();
    const [refreshing, setRefreshing] = useState(false);
    const cliOk = !!authContext?.cli.installed && !!authContext?.cli.loggedIn;
    const pwshOk = !!authContext?.pwsh.installed && !!authContext?.pwsh.loggedIn;
    const aligned = !!authContext?.aligned.subscription && !!authContext?.aligned.tenant;
    const targetSubscriptionId = selectedSubscription || authContext?.cli.subscriptionId || authContext?.pwsh.subscriptionId || "<subscription-id>";
    const targetTenantId = authContext?.cli.tenantId || authContext?.pwsh.tenantId || "<tenant-id>";
    const targetContextReady = cliOk && pwshOk && aligned && !!selectedSubscription;
    const allReady = !!authContext?.ready && aligned && !!selectedSubscription;
    const selectedSubName = subscriptions.find((s) => s.id === selectedSubscription)?.name || authContext?.cli.subscriptionName || "Not selected";
    const readinessChecks = useMemo(() => [
        { label: "Azure CLI installed and logged in", ok: cliOk, detail: authContext?.cli.error || authContext?.cli.user || "" },
        { label: "Az PowerShell installed and logged in", ok: pwshOk, detail: authContext?.pwsh.error || authContext?.pwsh.user || "" },
        { label: "CLI and PowerShell tenant aligned", ok: aligned, detail: authContext?.cli.tenantId || authContext?.pwsh.tenantId || "" },
        { label: "Target subscription selected", ok: !!selectedSubscription, detail: selectedSubName },
        { label: "Selected context ready for deployment", ok: targetContextReady, detail: targetSubscriptionId },
        { label: "Subscriptions loaded", ok: subscriptions.length > 0, detail: `${subscriptions.length} subscription(s)` },
        { label: "Fabric capacities discoverable", ok: capacities.length > 0, detail: `${capacities.length} capacity candidate(s)` },
    ], [aligned, authContext, capacities.length, cliOk, pwshOk, selectedSubName, selectedSubscription, subscriptions.length, targetContextReady, targetSubscriptionId]);
    const isolationCommand = `# Run from the repository root. Optional: isolate Azure CLI state for this project.\ncd /path/to/hls-data-accelerator\nexport AZURE_CONFIG_DIR="$PWD/.pi-run/azure-profile"\nmkdir -p "$AZURE_CONFIG_DIR"\n\n# Sign in or reuse cached credentials for your tenant/subscription.\naz login --tenant ${targetTenantId}\naz account set --subscription ${targetSubscriptionId}\n\n# Align Az PowerShell to the same tenant/subscription used by Azure CLI.\npwsh -NoProfile -Command 'Connect-AzAccount -Tenant ${targetTenantId} -Subscription ${targetSubscriptionId}'`;
    const onRefresh = async () => {
        setRefreshing(true);
        try {
            await refreshAuthContext();
        }
        finally {
            setRefreshing(false);
        }
    };
    return (<div>
      <style>{PREFLIGHT_ANIMATION_CSS}</style>
      <div className={styles.header}>
        <div>
          <Typography component="div" variant="h5">Deployment Preflight</Typography>
          <Typography style={{ color: "var(--m3-colorNeutralForeground2)", marginTop: "8px" }} component="div" variant="body2">
            Validate Azure CLI, Az PowerShell, tenant/subscription alignment, and Fabric discovery before starting a deployment.
          </Typography>
        </div>
        <div className={styles.actionRow}>
          {statusBadge(allReady, authContextLoading || refreshing)}
          <Button onClick={onRefresh} disabled={authContextLoading || refreshing} variant="text" startIcon={<Sync />}>
            Refresh context
          </Button>
        </div>
      </div>

      {!allReady && (<Alert style={{ marginBottom: "24px" }} severity={"warning"}>
          <Box>
            Preflight found items to fix before a real deployment. Use the remediation command below from an isolated terminal.
          </Box>
        </Alert>)}

      <div className={styles.grid}>
        <Card>
          <CardHeader action={statusBadge(cliOk && pwshOk && aligned, authContextLoading || refreshing)} title={<Typography component="div" variant="subtitle1">Azure context</Typography>}/>
          <div className={styles.cardBody}>
            <div className={styles.kv}><span className={styles.label}>CLI user</span><span className={styles.value}>{authContext?.cli.user || "Not logged in"}</span></div>
            <div className={styles.kv}><span className={styles.label}>Pwsh user</span><span className={styles.value}>{authContext?.pwsh.user || "Not logged in"}</span></div>
            <div className={styles.kv}><span className={styles.label}>Tenant</span><span className={styles.value}>{authContext?.cli.tenantId || authContext?.pwsh.tenantId || "Unknown"}</span></div>
            <div className={styles.kv}><span className={styles.label}>Subscription</span><span className={styles.value}>{selectedSubName}</span></div>
          </div>
        </Card>

        <Card>
          <CardHeader title={<Typography component="div" variant="subtitle1">Readiness checklist</Typography>}/>
          <div className={styles.cardBody}>
            {readinessChecks.map((check) => (<div key={check.label} className={styles.actionRow} style={{ justifyContent: "space-between" }}>
                <div>
                  <Typography component="div" variant="caption" sx={{
            fontWeight: 600
        }}>{check.label}</Typography>
                  <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">{check.detail || "—"}</Typography>
                </div>
                {checkBadge(check.ok, authContextLoading || refreshing)}
              </div>))}
          </div>
        </Card>

        <Card>
          <CardHeader title={<Typography component="div" variant="subtitle1">Operator links</Typography>}/>
          <div className={styles.cardBody}>
            <Button component={"a"} href="https://portal.azure.com/#view/Microsoft_Azure_Billing/SubscriptionsBlade" target="_blank" variant="text" startIcon={<OpenInNew />}>Azure subscriptions</Button>
            <Button component={"a"} href="https://app.fabric.microsoft.com/home?experience=fabric-developer" target="_blank" variant="text" startIcon={<OpenInNew />}>Fabric portal</Button>
            <Button component={"a"} href="https://learn.microsoft.com/en-us/powershell/azure/authenticate-azureps" target="_blank" variant="text" startIcon={<OpenInNew />}>Az PowerShell auth docs</Button>
          </div>
        </Card>
      </div>

      <Card style={{ marginTop: "24px" }}>
        <CardHeader action={<Button onClick={() => copy(isolationCommand)} variant="text" startIcon={<ContentPaste />}>Copy</Button>} title={<Typography component="div" variant="subtitle1">Isolated Azure terminal command</Typography>}/>
        <div className={styles.cardBody}>
          <div className={styles.command}>{isolationCommand}</div>
          <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">
            This optional command uses a project-local Azure CLI profile under <code>.pi-run/azure-profile</code> and aligns Az PowerShell to the same tenant/subscription. Replace placeholders if the context above is not loaded yet.
          </Typography>
        </div>
      </Card>
    </div>);
}
