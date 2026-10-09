import { Button, Card, CardHeader, Chip, CircularProgress, Typography } from "@mui/material";
import { Sync, Visibility } from "@mui/icons-material";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";


import { getTeardownBatch, type TeardownBatchStatus } from "../api";

function statusColor(status: string): "success" | "warning" | "error" | "info" | "default" {
    if (status === "Completed")
        return "success";
    if (status === "Running")
        return "info";
    if (status === "Failed" || status === "Terminated")
        return "error";
    return "default";
}

export function TeardownBatch() {
    const { batchId = "" } = useParams<{
        batchId: string;
    }>();
    const navigate = useNavigate();
    const [batch, setBatch] = useState<TeardownBatchStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const refresh = () => {
        if (!batchId)
            return;
        setLoading(true);
        setError("");
        getTeardownBatch(batchId)
            .then(setBatch)
            .catch((e) => setError(e instanceof Error ? e.message : "Unable to load teardown batch"))
            .finally(() => setLoading(false));
    };
    useEffect(() => {
        refresh();
        const timer = window.setInterval(refresh, 5000);
        return () => window.clearInterval(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [batchId]);
    return (<div style={{ display: "grid", gap: "16px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <Typography component="div" variant="h5">Teardown Batch</Typography>
          <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="div" variant="caption">{batchId}</Typography>
        </div>
        <Button onClick={refresh} disabled={loading} variant="text" startIcon={<Sync />}>Refresh</Button>
      </div>

      {loading && !batch && <CircularProgress aria-label={"Loading teardown batch..."} size={32}/>}
      {error && <Typography style={{ color: "var(--m3-colorStatusDangerForeground1)" }} component="span" variant="body2">{error}</Typography>}

      {batch && (<>
          <Card>
            <CardHeader title={<Typography component="span" variant="body2" sx={{
            fontWeight: 600
        }}>Summary</Typography>} subheader={`${batch.summary.completed}/${batch.summary.total} complete · ${batch.summary.running} running · ${batch.summary.failed} failed`}/>
          </Card>
          {batch.children.map((child) => {
                const cs = child.customStatus ?? {};
                const display = String(cs.displayName || cs.workspaceName || cs.resourceGroupName || child.instanceId);
                return (<Card key={child.instanceId}>
                <div style={{ display: "flex", alignItems: "center", gap: "16px", padding: "24px" }}>
                  <div style={{ flex: 1 }}>
                    <Typography component="div" variant="body2" sx={{
                    fontWeight: 600
                }}>{display}</Typography>
                    <Typography style={{ color: "var(--m3-colorNeutralForeground3)" }} component="span" variant="caption">{String(cs.detail || child.instanceId)}</Typography>
                  </div>
                  <Chip component="span" size="small" variant="filled" color={statusColor(child.runtimeStatus) as any} label={<>{child.runtimeStatus}</>}/>
                  <Button onClick={() => navigate(`/monitor/${child.instanceId}`)} variant="text" startIcon={<Visibility />}>View</Button>
                </div>
              </Card>);
            })}
        </>)}
    </div>);
}
