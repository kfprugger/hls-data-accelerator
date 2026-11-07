import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';

import { AppShell } from '@/components/AppShell';
import { AuthPage } from '@/components/AuthPage';
import { useAuth } from '@/hooks/AuthContext';
import { AuthCallback } from '@/pages/AuthCallback.tsx';
import { DataMap } from '@/pages/DataMap';
import { Guide } from '@/pages/Guide';
import { Overview } from '@/pages/Overview';
import { Pathology } from '@/pages/Pathology';
import { Patients } from '@/pages/Patients';
import { Sources } from '@/pages/Sources';
import { Volumes } from '@/pages/Volumes';
import { WardFlow } from '@/pages/WardFlow';
import { Standards } from '@/pages/Standards';

interface AuthRedirectState {
  from?: string;
}

function resolveReturnPath(state: unknown): string {
  const from = (state as AuthRedirectState | null)?.from;

  if (typeof from !== 'string' || !from.startsWith('/')) return '/';
  if (from.startsWith('//') || from.startsWith('/\\')) return '/';
  if (
    from === '/auth' ||
    from.startsWith('/auth/') ||
    from.startsWith('/auth?')
  ) {
    return '/';
  }

  return from;
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="t-faint">Loading</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    const redirectState: AuthRedirectState = {
      from: `${location.pathname}${location.search}`,
    };
    return <Navigate to="/auth" replace state={redirectState} />;
  }

  return <>{children}</>;
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="t-faint">Loading</div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to={resolveReturnPath(location.state)} replace />;
  }

  return <>{children}</>;
}

function OverviewOrLegacySlide() {
  const { search } = useLocation();
  if (new URLSearchParams(search).has('slide')) return <Navigate to={`/pathology${search}`} replace />;
  return <Overview />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route
          path="/auth"
          element={
            <PublicRoute>
              <AuthPage />
            </PublicRoute>
          }
        />
        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<OverviewOrLegacySlide />} />
          <Route path="patients" element={<Patients />} />
          <Route path="p/:id" element={<Patients />} />
          <Route path="wardflow" element={<WardFlow />} />
          <Route path="pathology" element={<Pathology />} />
          <Route path="volumes" element={<Volumes />} />
          <Route path="data" element={<DataMap />} />
          <Route path="guide" element={<Guide />} />
          <Route path="sources" element={<Sources />} />
          <Route path="standards" element={<Standards />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
