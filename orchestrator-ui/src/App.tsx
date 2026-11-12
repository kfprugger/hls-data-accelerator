import { Button, CircularProgress, Typography } from "@mui/material";
import { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import { Layout } from "./components/Layout";
import { RouteErrorBoundary } from "./components/RouteErrorBoundary";
import { AppStateProvider } from "./AppState";
import { AuthenticationProvider } from './AuthenticationState';
import { DeploymentDraftProvider } from './DeploymentDraft';

const Preflight = lazy(() => import("./pages/Preflight").then((m) => ({ default: m.Preflight })));
const DeployWizard = lazy(() => import("./pages/DeployWizard").then((m) => ({ default: m.DeployWizard })));
const PhaseMonitor = lazy(() => import("./pages/PhaseMonitor").then((m) => ({ default: m.PhaseMonitor })));
const DeploymentHistory = lazy(() => import("./pages/DeploymentHistory").then((m) => ({ default: m.DeploymentHistory })));
const TeardownView = lazy(() => import("./pages/TeardownView").then((m) => ({ default: m.TeardownView })));
const TeardownMonitor = lazy(() => import("./pages/TeardownMonitor").then((m) => ({ default: m.TeardownMonitor })));
const TeardownBatch = lazy(() => import("./pages/TeardownBatch").then((m) => ({ default: m.TeardownBatch })));

function PageLoading() {
    return (<div style={{ minHeight: 280, display: "grid", placeItems: "center" }}>
      <CircularProgress aria-label={"Loading page..."} size={32}/>
    </div>);
}

function NotFound() {
    return (<div style={{ display: "grid", gap: 12 }}>
      <Typography component="div" variant="h5">Page not found</Typography>
      <Typography component="span" variant="body2">The requested orchestrator page does not exist.</Typography>
      <Button component={"a"} href="/deploy" variant="contained">
        Go to Deploy
      </Button>
    </div>);
}

export function App() {
    return (<AppStateProvider>
      <AuthenticationProvider>
      <DeploymentDraftProvider>
      <BrowserRouter>
        <RouteErrorBoundary>
          <Suspense fallback={<PageLoading />}>
            <Routes>
              <Route element={<Layout />}>
                <Route path="/" element={<Navigate to="/deploy" replace/>}/>
                <Route path="/preflight" element={<Preflight />}/>
                <Route path="/deploy" element={<DeployWizard />}/>
                <Route path="/monitor/:instanceId" element={<PhaseMonitor />}/>
                <Route path="/history" element={<DeploymentHistory />}/>
                <Route path="/teardown" element={<TeardownView />}/>
                <Route path="/teardown/monitor" element={<TeardownMonitor />}/>
                <Route path="/teardown/batch/:batchId" element={<TeardownBatch />}/>
                <Route path="*" element={<NotFound />}/>
              </Route>
            </Routes>
          </Suspense>
        </RouteErrorBoundary>
      </BrowserRouter>
      </DeploymentDraftProvider>
      </AuthenticationProvider>
    </AppStateProvider>);
}
