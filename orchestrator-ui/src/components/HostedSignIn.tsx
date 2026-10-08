import { useEffect, useState } from "react";
import { Button, Card, Field, Input, Link, MessageBar, MessageBarBody, Spinner, Subtitle1, Text, makeStyles, tokens } from "@fluentui/react-components";
import { requestJson } from "../api";
import { useAppState } from "../AppState";
import { setHostedHistoryMode } from "../formHistory";

interface PortalUser { hosted: boolean; email: string; oid: string; tid: string; notice: string }
interface DeviceCode { session_id: string; user_code: string; verification_uri: string; expires_in: number }
interface LoginStatus { status: "pending" | "succeeded" | "failed"; error?: string; error_hint?: string }
const useStyles = makeStyles({
  card: { marginBottom: tokens.spacingVerticalL, display: "flex", gap: tokens.spacingVerticalM },
  fields: { display: "flex", flexWrap: "wrap", gap: tokens.spacingHorizontalL },
  field: { flexGrow: 1, minWidth: "240px" },
  actions: { display: "flex", flexWrap: "wrap", alignItems: "center", gap: tokens.spacingHorizontalM },
});

export function HostedSignIn() {
  const styles = useStyles();
  const { authContext, refreshAuthContext } = useAppState();
  const [user, setUser] = useState<PortalUser | null>(null);
  const [tenant, setTenant] = useState("");
  const [subscription, setSubscription] = useState("");
  const [code, setCode] = useState<DeviceCode | null>(null);
  const [tool, setTool] = useState<"az" | "azps" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    requestJson<PortalUser>("/api/hosted/whoami", { signal: controller.signal })
      .then((identity) => { setUser(identity); setHostedHistoryMode(identity.hosted); })
      .catch(() => { /* Fail closed: never persist hosted history in this browser. */ });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    setTenant((current) => current || authContext?.cli.tenantId || authContext?.pwsh.tenantId || "");
    setSubscription((current) => current || authContext?.cli.subscriptionId || authContext?.pwsh.subscriptionId || "");
  }, [authContext]);

  useEffect(() => {
    if (!code) return;
    const controller = new AbortController();
    let timer: number;
    const deadline = Date.now() + code.expires_in * 1000;
    const poll = async () => {
      try {
        const result = await requestJson<LoginStatus>(`/api/auth/device-login/${code.session_id}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (result.status === "pending" && Date.now() < deadline) {
          timer = window.setTimeout(poll, 2500);
          return;
        }
        setCode(null);
        setBusy(false);
        if (result.status === "succeeded") {
          setMessage(`${tool === "az" ? "Azure CLI" : "Az PowerShell"} sign-in complete.`);
          await refreshAuthContext();
        } else {
          setError([result.error_hint, result.error || "Device code expired. Start a new sign-in."].filter(Boolean).join(" "));
        }
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "Unable to check sign-in status.");
        setBusy(false);
        setCode(null);
      }
    };
    void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  // refreshAuthContext is an AppState action whose identity changes on refresh.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, tool]);

  if (!user?.hosted) return null;
  const begin = async (selectedTool: "az" | "azps") => {
    setError(""); setMessage(""); setBusy(true); setTool(selectedTool);
    try {
      const next = await requestJson<DeviceCode>("/api/auth/device-login", {
        method: "POST", headers: { "Content-Type": "application/json" }, timeoutMs: 60000,
        body: JSON.stringify({ tenant_id: tenant.trim(), subscription_id: subscription.trim(), tool: selectedTool }),
      });
      setCode(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to begin sign-in."); setBusy(false);
    }
  };
  const logout = async () => {
    setBusy(true); setError(""); setMessage("");
    try {
      await requestJson("/api/auth/logout", { method: "POST", timeoutMs: 90000 });
      setCode(null);
      await refreshAuthContext();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to sign out.");
    } finally { setBusy(false); }
  };
  return <Card className={styles.card}>
    <Subtitle1>Private sandbox · {user.email}</Subtitle1>
    <Text>{user.notice}</Text>
    {!authContext?.ready && <>
      <Text>Sign in to both Azure tools using the same deployment tenant and subscription. This may differ from your portal account.</Text>
      <div className={styles.fields}>
        <Field className={styles.field} label="Deployment tenant ID" required><Input value={tenant} disabled={busy} onChange={(_, data) => setTenant(data.value)} /></Field>
        <Field className={styles.field} label="Deployment subscription ID" required><Input value={subscription} disabled={busy} onChange={(_, data) => setSubscription(data.value)} /></Field>
      </div>
      <div className={styles.actions}>
        <Button appearance="primary" disabled={busy || !tenant.trim() || !subscription.trim()} onClick={() => void begin("az")}>Sign in to Azure CLI</Button>
        <Button appearance="primary" disabled={busy || !tenant.trim() || !subscription.trim()} onClick={() => void begin("azps")}>Sign in to Az PowerShell</Button>
        {busy && <Spinner size="tiny" label={code ? "Waiting for sign-in" : "Requesting device code"} />}
      </div>
    </>}
    {code && <MessageBar intent="info"><MessageBarBody>Open <Link href={code.verification_uri} target="_blank" rel="noopener noreferrer">Microsoft device sign-in</Link> in a new tab and enter <strong>{code.user_code}</strong>. This page will update automatically.</MessageBarBody></MessageBar>}
    {message && <MessageBar intent="success"><MessageBarBody>{message}</MessageBarBody></MessageBar>}
    {error && <MessageBar intent="error"><MessageBarBody>{error}</MessageBarBody></MessageBar>}
    <div className={styles.actions}>
      <Button disabled={busy} onClick={() => void logout()}>Sign out of Azure tools</Button>
      <Button disabled={busy} onClick={() => { void refreshAuthContext().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Unable to refresh authentication.")); }}>Refresh sign-in status</Button>
    </div>
  </Card>;
}
