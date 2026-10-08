import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Link,
  MessageBar,
  MessageBarBody,
  Spinner,
  Subtitle1,
  Text,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
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
  pending: "subtle",
  running: "informative",
  paused: "warning",
  succeeded: "success",
  failed: "danger",
} as const;

const useStyles = makeStyles({
  card: {
    marginBottom: tokens.spacingVerticalM,
  },
  body: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    padding: `0 ${tokens.spacingHorizontalL} ${tokens.spacingVerticalM}`,
  },
  addon: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
  },
  row: {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
  detail: {
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
    color: tokens.colorNeutralForeground2,
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    borderTop: `1px solid ${tokens.colorNeutralStroke2}`,
    paddingTop: tokens.spacingVerticalM,
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
    if (pending || (action === "start" && (!canAdd || selected.length === 0))) return;
    setPending(action);
    setError("");
    setMessage("");
    try {
      if (action === "continue") {
        await continueDatabricksAddon(instanceId);
        setMessage("Databricks continuation requested. Follow its status and phase logs below.");
      } else {
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
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The add-on request failed.");
    } finally {
      setPending(null);
    }
  };

  return (
    <Card className={styles.card}>
      <CardHeader
        header={<Subtitle1>Deployment add-ons</Subtitle1>}
        description="Add-ons use this deployment's resources. Progress and logs appear with the deployment phases below."
      />
      <div className={styles.body}>
        {ADDONS.map(({ name, label, field }) => {
          const addon = addons[name];
          return (
            <div key={name} className={styles.addon}>
              <div className={styles.row}>
                <Text weight="semibold">{label}</Text>
                <Badge color={addon ? STATUS_COLORS[addon.status] : "subtle"}>
                  {addon?.status ?? "Not added"}
                </Badge>
                {canAdd && (!addon || addon.status === "failed") && (
                  <Button
                    size="small"
                    disabled={pending !== null}
                    onClick={() => {
                      setOptions((previous) => ({ ...previous, [field]: true }));
                      setFormOpen(true);
                      setError("");
                      setMessage("");
                    }}
                  >
                    {addon?.status === "failed" ? "Retry" : "Add"} {label}
                  </Button>
                )}
              </div>
              {addon?.detail && <Text block size={200} className={styles.detail}>{addon.detail}</Text>}
              {addon?.resources && Object.entries(addon.resources).map(([key, value]) => (
                <Text key={key} block size={200} className={styles.detail}>
                  {key}: {/^https?:\/\//i.test(value)
                    ? <Link href={value} target="_blank" rel="noopener noreferrer">{value}</Link>
                    : value}
                </Text>
              ))}
              {name === "databricks" && addon?.status === "paused" && (
                <MessageBar intent="warning">
                  <MessageBarBody>
                    <Text block>
                      Automatic metastore assignment needs a Databricks account admin. Have an account admin assign
                      the regional Unity Catalog metastore to this workspace, then select Continue. The run waits
                      for up to 24 hours; details above identify the required action.
                    </Text>
                    <Button
                      appearance="primary"
                      disabled={pending !== null}
                      onClick={() => void runAction("continue")}
                      style={{ marginTop: tokens.spacingVerticalS }}
                    >
                      {pending === "continue" ? "Continuing…" : "Continue Databricks"}
                    </Button>
                  </MessageBarBody>
                </MessageBar>
              )}
            </div>
          );
        })}
        {!canAdd && (
          <Text size={200} className={styles.detail}>
            {hasActiveAddon
              ? "An add-on is active. Wait for it to finish before starting another."
              : "Add-ons can be added once the base deployment is Completed."}
          </Text>
        )}
        {formOpen && canAdd && (
          <form className={styles.form} onSubmit={(event) => { event.preventDefault(); void runAction("start"); }}>
            <Text weight="semibold">Configure add-ons for this deployment</Text>
            <AddonFields
              value={options}
              onChange={(patch) => setOptions((previous) => ({ ...previous, ...patch }))}
              disabled={pending !== null}
              unavailable={unavailable}
              adminGroup={savedConfig?.admin_security_group}
            />
            <div className={styles.row}>
              <Button type="submit" appearance="primary" disabled={pending !== null || selected.length === 0}>
                {pending === "start" ? "Starting add-ons…" : "Start selected add-ons"}
              </Button>
              <Button type="button" disabled={pending !== null} onClick={() => setFormOpen(false)}>Cancel</Button>
            </div>
          </form>
        )}
        {pending && (
          <div className={styles.row} role="status" aria-live="polite">
            <Spinner size="tiny" />
            <Text>{pending === "start" ? "Starting add-ons…" : "Continuing Databricks…"}</Text>
          </div>
        )}
        {error && <MessageBar intent="error"><MessageBarBody>{error}</MessageBarBody></MessageBar>}
        {message && <MessageBar intent="info"><MessageBarBody>{message}</MessageBarBody></MessageBar>}
      </div>
    </Card>
  );
}
