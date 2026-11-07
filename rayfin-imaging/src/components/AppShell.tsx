import { Link, Outlet, useLocation } from 'react-router-dom';

import { ThemeToggle } from '@/components/ThemeToggle';
import { Wordmark } from '@/components/Wordmark';
import { useAuth } from '@/hooks/AuthContext';
import { CatalogProvider, useCatalog, VolumeCatalogProvider } from '@/hooks/useCatalog';
import { CohortProvider } from '@/hooks/useCohort';
import { LOCAL_DATA } from '@/lib/localMode';
import { PersonaBanner } from '@/components/PersonaBanner';
import { PersonaProvider } from '@/hooks/usePersona';

const TABS = [
  { to: '/', label: 'Overview', active: (p: string) => p === '/' },
  { to: '/patients', label: 'Patients (360)', active: (p: string) => p.startsWith('/patients') || p.startsWith('/p/') },
  { to: '/wardflow', label: 'WardFlow Cardiology', active: (p: string) => p.startsWith('/wardflow') },
  { to: '/pathology', label: 'Pathology', active: (p: string) => p.startsWith('/pathology') },
  { to: '/volumes', label: '3D and 4D imaging', active: (p: string) => p.startsWith('/volumes') },
  { to: '/data', label: 'Where the data lives', active: (p: string) => p.startsWith('/data') },
  { to: '/guide', label: 'Guide & Sources', active: (p: string) => p.startsWith('/guide') || p.startsWith('/sources') },
];

const WORKSPACE_ID = import.meta.env.VITE_FABRIC_WORKSPACE_ID as string | undefined;
const WORKSPACE_NAME = (import.meta.env.VITE_FABRIC_WORKSPACE_NAME as string | undefined) ?? 'Fabric workspace';

function ShellHeader() {
  const { user, signOut } = useAuth();
  const { catalog } = useCatalog();
  const { pathname } = useLocation();
  const portalUrl = catalog?.lakehouse.portalUrl ?? (WORKSPACE_ID ? `https://app.fabric.microsoft.com/groups/${WORKSPACE_ID}` : undefined);
  const portalLabel = catalog ? `${catalog.lakehouse.workspaceName}/${catalog.lakehouse.lakehouseName}` : WORKSPACE_NAME;

  return (
    <header className="hair w-full max-w-full shrink-0 overflow-x-hidden border-b">
      <div className="flex h-14 w-full max-w-full min-w-0 items-center gap-2 sm:gap-6 px-2.5 sm:px-5">
        <Wordmark compact />
        <nav className="flex h-full min-w-0 flex-1 items-stretch gap-3 sm:gap-5 overflow-x-auto" aria-label="Sections">
          {TABS.map((t) => (
            <Link key={t.to} to={t.to} className={`tab whitespace-nowrap ${t.active(pathname) ? 'active' : ''}`}>
              {t.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-5 text-[12.5px]">
          {LOCAL_DATA ? (
            <span className="t-muted t-mono hidden xl:inline" title="Local mode: data is read from the work/ folder on this computer">
              local mode · work/
            </span>
          ) : (
            portalUrl && (
              <a
                href={portalUrl}
                target="_blank"
                rel="noreferrer"
                className="link t-muted t-mono hidden xl:inline"
                title={catalog?.lakehouse.oneLakePath}
              >
                {portalLabel}
              </a>
            )
          )}
          {user && !LOCAL_DATA && (
            <>
              <span className="t-faint hidden 2xl:inline">{user.email || user.name}</span>
              <button onClick={() => void signOut()} className="link t-muted">
                Sign out
              </button>
            </>
          )}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}

export function AppShell() {
  return (
    <CatalogProvider>
      <VolumeCatalogProvider>
        <PersonaProvider>
          <CohortProvider>
            <div className="flex h-screen flex-col">
              <PersonaBanner />
              <ShellHeader />
              <div className="min-h-0 flex-1">
                <Outlet />
              </div>
            </div>
          </CohortProvider>
        </PersonaProvider>
      </VolumeCatalogProvider>
    </CatalogProvider>
  );
}
