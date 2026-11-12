import { Alert, Box, Button, Card, CardHeader, Chip, CircularProgress, Link, Typography } from "@mui/material";
import { makeStyles } from "@griffel/react";
import { useState } from "react";

import {
  continueDatabricksAddon,
  startAddons,
  type AddonName,
  type AddonOptions,
  type DeploymentConfig,
  type DeploymentStatus,
} from "../api";
import { AddonFields, getAddonOptions } from "./AddonFields";

const ADDONS: Array<{ name: AddonName; label: string; field: "deploy_databricks" | "deploy_rayfin_apps" | "deploy_cardiology" }> = [
  { name: "databricks", label: "Azure Databricks", field: "deploy_databricks" },
  { name: "rayfin", label: "Rayfin apps", field: "deploy_rayfin_apps" },
  { name: "cardiology", label: "Cardiology app", field: "deploy_cardiology" },
];

const STATUS_COLORS = {
    pending: "default",
    running: "info",
    paused: "warning",
    succeeded: "success",
    failed: "error",
} as const;

const useStyles = makeStyles({
    card: {
        marginBottom: "16px",
    },
    body: {
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        padding: `0 ${"24px"} ${"16px"}`,
    },
    addon: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
    },
    row: {
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "12px",
    },
    detail: {
        whiteSpace: "pre-wrap",
        overflowWrap: "anywhere",
        color: "var(--m3-colorNeutralForeground2)",
    },
    form: {
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        borderTop: `1px solid ${"var(--m3-colorNeutralStroke2)"}`,
        paddingTop: "16px",
    },
});

interface AddonPanelProps {
  instanceId: string;
  status: DeploymentStatus;
  onRefresh: () => Promise<void>;
}

export function AddonPanel({ instanceId, status, onRefresh }: AddonPanelProps) {
    const styles = useStyles();
    const savedConfig = (status.customStatus as Record<string, unknown> | null)?.deployConfig as DeploymentConfig | undefined;
    const [options, setOptions] = useState<AddonOptions>(() => ({
        ...getAddonOptions(savedConfig),
        deploy_databricks: false,
        deploy_rayfin_apps: false,
        deploy_cardiology: false,
    }));
    const [formOpen, setFormOpen] = useState(false);
    const [pending, setPending] = useState<"start" | "continue" | null>(null);
    const [error, setError] = useState("");
    const [message, setMessage] = useState("");
    const addons = status.customStatus?.addons ?? {};
    const hasActiveAddon = Object.values(addons).some((addon) => ["pending", "running", "paused"].includes(addon.status));
    const canAdd = status.runtimeStatus === "Completed" && !hasActiveAddon;
    const unavailable = ADDONS.filter(({ name }) => addons[name] && addons[name].status !== "failed").map(({ name }) => name);
    const selected = ADDONS.filter(({ name, field }) => options[field] && !unavailable.includes(name)).map(({ name }) => name);
    const runAction = async (action: "start" | "continue") => {
        if (pending || (action === "start" && (!canAdd || selected.length === 0)))
            return;
        setPending(action);
        setError("");
        setMessage("");
        try {
            if (action === "continue") {
                await continueDatabricksAddon(instanceId);
                setMessage("Databricks continuation requested. Follow its status and phase logs below.");
            }
            else {
                await startAddons(instanceId, {
                    ...getAddonOptions(options),
                    addons: selected,
                    deploy_databricks: selected.includes("databricks"),
                    deploy_rayfin_apps: selected.includes("rayfin"),
                    deploy_cardiology: selected.includes("cardiology"),
                });
                setFormOpen(false);
                setOptions((previous) => ({ ...previous, deploy_databricks: false, deploy_rayfin_apps: false, deploy_cardiology: false }));
                setMessage("Add-on deployment requested. Follow its status and phase logs below.");
            }
            await onRefresh();
        }
        catch (cause) {
            setError(cause instanceof Error ? cause.message : "The add-on request failed.");
        }
        finally {
            setPending(null);
        }
    };
    return (<Card className={styles.card}>
      <CardHeader title={<Typography component="div" variant="subtitle1">Deployment add-ons</Typography>} subheader={"Add-ons use this deployment's resources. Progress and logs appear with the deployment phases below."}/>
      <div className={styles.body}>
        {ADDONS.map(({ name, label, field }) => {
            const addon = addons[name];
            return (<div key={name} className={styles.addon}>
              <div className={styles.row}>
                <Typography component="span" variant="body2" sx={{
                fontWeight: 600
            }}>{label}</Typography>
                <Chip component="span" size="small" variant="filled" color={addon ? STATUS_COLORS[addon.status] : "default" as any} label={<>
                  {addon?.status ?? "Not added"}
                </>}/>
                {canAdd && (!addon || addon.status === "failed") && (<Button onClick={() => {
                        setOptions((previous) => ({ ...previous, [field]: true }));
                        setFormOpen(true);
                        setError("");
                        setMessage("");
                    }} disabled={pending !== null} variant="text" size="small">
                    {addon?.status === "failed" ? "Retry" : "Add"} {label}
                  </Button>)}
              </div>
              {addon?.detail && <Typography className={styles.detail} component="div" variant="caption">{addon.detail}</Typography>}
              {addon?.resources && Object.entries(addon.resources).map(([key, value]) => (<Typography key={key} className={styles.detail} component="div" variant="caption">
                  {key}: {/^https?:\/\//i.test(value)
                        ? <Link href={value} target="_blank" rel="noopener noreferrer">{value}</Link> : value}
                </Typography>))}
              {name === "databricks" && addon?.status === "paused" && (<Alert severity={"warning"}>
                  <Box>
                    <Typography component="div" variant="body2">
                      Automatic metastore assignment needs a Databricks account admin. Have an account admin assign
                      the regional Unity Catalog metastore to this workspace, then select Continue. The run waits
                      for up to 24 hours; details above identify the required action.
                    </Typography>
                    <Button onClick={() => void runAction("continue")} style={{ marginTop: "12px" }} disabled={pending !== null} variant="contained">
                      {pending === "continue" ? "Continuing…" : "Continue Databricks"}
                    </Button>
                  </Box>
                </Alert>)}
            </div>);
        })}
        {!canAdd && (<Typography className={styles.detail} component="span" variant="caption">
            {hasActiveAddon
                ? "An add-on is active. Wait for it to finish before starting another."
                : "Add-ons can be added once the base deployment is Completed."}
          </Typography>)}
        {formOpen && canAdd && (<form className={styles.form} onSubmit={(event) => { event.preventDefault(); void runAction("start"); }}>
            <Typography component="span" variant="body2" sx={{
            fontWeight: 600
        }}>Configure add-ons for this deployment</Typography>
            <AddonFields value={options} onChange={(patch) => setOptions((previous) => ({ ...previous, ...patch }))} disabled={pending !== null} unavailable={unavailable} adminGroup={savedConfig?.admin_security_group}/>
            <div className={styles.row}>
              <Button type="submit" disabled={pending !== null || selected.length === 0} variant="contained">
                {pending === "start" ? "Starting add-ons…" : "Start selected add-ons"}
              </Button>
              <Button type="button" onClick={() => setFormOpen(false)} disabled={pending !== null} variant="text">Cancel</Button>
            </div>
          </form>)}
        {pending && (<div className={styles.row} role="status" aria-live="polite">
            <CircularProgress size={20}/>
            <Typography component="span" variant="body2">{pending === "start" ? "Starting add-ons…" : "Continuing Databricks…"}</Typography>
          </div>)}
        {error && <Alert severity={"error"}><Box>{error}</Box></Alert>}
        {message && <Alert severity={"info"}><Box>{message}</Box></Alert>}
      </div>
    </Card>);
}
