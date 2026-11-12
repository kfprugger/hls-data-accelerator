import { Button, Card, CardHeader, Typography } from "@mui/material";
import React from "react";


interface State { error: Error | null }

export class RouteErrorBoundary extends React.Component<React.PropsWithChildren, State> {
    state: State = { error: null };
    static getDerivedStateFromError(error: Error): State {
        return { error };
    }
    componentDidCatch(error: Error) {
        // Keep this visible in dev tools without crashing the whole app shell.
        console.error("Route render failed", error);
    }
    render() {
        if (!this.state.error)
            return this.props.children;
        return (<Card style={{ margin: "28px" }}>
        <CardHeader title={<Typography component="span" variant="body2" sx={{
            fontWeight: 600
        }}>Page failed to render</Typography>} subheader={"The app shell is still running. Use the safe navigation below or reload after fixing the route issue."}/>
        <div style={{ display: "grid", gap: "12px", padding: `0 ${"24px"} ${"16px"}` }}>
          <Typography style={{ color: "var(--m3-colorStatusDangerForeground1)" }} component="span" variant="caption">{this.state.error.message}</Typography>
          <div style={{ display: "flex", gap: "12px" }}>
            <Button onClick={() => window.location.assign("/history")} variant="contained">Open History</Button>
            <Button onClick={() => window.location.reload()} variant="text">Reload</Button>
          </div>
        </div>
      </Card>);
    }
}
