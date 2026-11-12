import { bridgeFabricCallback } from '@microsoft/rayfin-auth-provider-fabric';
import { createRoot } from 'react-dom/client';
import { ErrorBoundary } from 'react-error-boundary';
import { Toaster } from 'sonner';

import App from './App.tsx';
import { ErrorFallback } from './ErrorFallback.tsx';
import { AuthProvider } from './hooks/AuthContext.tsx';
import { ServiceContainer } from './services/ServiceContainer';

import './main.css';
import './styles/theme.css';
import './index.css';
import '@fontsource/fira-sans/400.css';
import '@fontsource/fira-sans/500.css';
import '@fontsource/fira-sans/600.css';
import '@fontsource/fira-sans-condensed/500.css';
import '@fontsource/fira-sans-condensed/600.css';
import '@fontsource/fira-mono/400.css';
import './atlas.css';

document.body.classList.add('atlas');

// Backward compat: old Fabric Portal may redirect the popup to the bare origin
// with handoff params in the URL hash. Bridge the code to the opener and close.
if (bridgeFabricCallback()) {
  // Popup is closing; skip the rest of the bootstrap.
} else {
  // Initialize the service container (creates RayfinClient and services).
  await ServiceContainer.create();

  createRoot(document.getElementById('root')!).render(
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <AuthProvider>
        <App />
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              fontFamily: 'var(--font)',
              fontSize: 13,
              borderRadius: 3,
              background: 'var(--bg)',
              border: '1px solid var(--ink)',
              color: 'var(--ink)',
              boxShadow: 'none',
            },
          }}
        />
      </AuthProvider>
    </ErrorBoundary>
  );
}
