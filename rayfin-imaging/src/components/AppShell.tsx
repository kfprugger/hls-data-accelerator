import { useEffect, useState } from 'react';
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
  { to: '/', label: 'Overview', title: 'Overview', active: (p: string) => p === '/' },
  { to: '/patients', label: 'Patient 360', title: 'Patient 360 (Oncology Cohort)', active: (p: string) => p.startsWith('/patients') || p.startsWith('/p/') },
  { to: '/wardflow', label: 'Cardiology', title: 'WardFlow Cardiology', active: (p: string) => p.startsWith('/wardflow') },
  { to: '/pathology', label: 'Pathology', title: 'Digital Pathology', active: (p: string) => p.startsWith('/pathology') },
  { to: '/volumes', label: '3D/4D Imaging', title: '3D and 4D Imaging', active: (p: string) => p.startsWith('/volumes') },
  { to: '/data', label: 'Data Map', title: 'Where the Data Lives (OneLake Architecture)', active: (p: string) => p.startsWith('/data') },
  { to: '/guide', label: 'Guide', title: 'Clinical Guide & Sources', active: (p: string) => p.startsWith('/guide') || p.startsWith('/sources') },
  { to: '/standards', label: 'Standards', title: 'Standards (FHIR & DICOM)', active: (p: string) => p.startsWith('/standards') },
  { to: '/ask', label: 'Ask Data Agent', title: 'Ask Data Agent', active: (p: string) => p.startsWith('/ask') },
];

const WORKSPACE_ID = import.meta.env.VITE_FABRIC_WORKSPACE_ID as string | undefined;
const WORKSPACE_NAME = (import.meta.env.VITE_FABRIC_WORKSPACE_NAME as string | undefined) ?? 'Fabric workspace';

function ShellHeader() {
  const { user, signOut } = useAuth();
  const { catalog } = useCatalog();
  const { pathname } = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const portalUrl = catalog?.lakehouse.portalUrl ?? (WORKSPACE_ID ? `https://app.fabric.microsoft.com/groups/${WORKSPACE_ID}` : undefined);
  const portalLabel = catalog ? `${catalog.lakehouse.workspaceName}/${catalog.lakehouse.lakehouseName}` : WORKSPACE_NAME;

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  return (
    <header className="hair w-full max-w-full shrink-0 border-b bg-[var(--surface,#ffffff)] z-30 relative">
      <div className="flex h-14 w-full max-w-full min-w-0 items-center gap-2 sm:gap-3 px-3 sm:px-4">
        <Wordmark compact />
        <nav
          className="hidden md:flex h-full min-w-0 flex-1 items-stretch gap-1 lg:gap-1.5 xl:gap-2 overflow-x-auto"
          aria-label="Sections"
        >
          {TABS.map((t) => (
            <Link
              key={t.to}
              to={t.to}
              title={t.title}
              className={`tab whitespace-nowrap px-1.5 lg:px-2 text-[12.5px] lg:text-[13px] ${t.active(pathname) ? 'active' : ''}`}
            >
              {t.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-2.5 text-[12px]">
          <div
            className="group relative flex items-center"
            tabIndex={0}
            role="region"
            aria-label="100% synthetic / public de-identified data notice"
          >
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-teal-600/30 dark:border-teal-400/30 bg-teal-50 dark:bg-teal-950/40 px-2 sm:px-2.5 py-0.5 text-[11px] font-medium text-teal-800 dark:text-teal-300 transition-colors shadow-2xs select-none cursor-help"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-teal-500 animate-pulse shrink-0" aria-hidden="true" />
              <span className="hidden sm:inline">100% synthetic / public de-identified data</span>
              <span className="inline sm:hidden font-mono text-[10px] font-semibold tracking-wider">SYNTHETIC</span>
            </span>
            <div
              role="tooltip"
              className="pointer-events-none absolute right-0 top-full mt-1.5 hidden w-72 max-w-[calc(100vw-32px)] rounded-md border border-[var(--line)] bg-[var(--surface,#ffffff)] dark:bg-slate-900 p-2.5 text-[11.5px] leading-relaxed text-[var(--ink)] shadow-lg group-hover:block group-focus:block z-50 text-left"
            >
              <div className="font-semibold text-teal-700 dark:text-teal-400 mb-1 flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-teal-500 inline-block" />
                HIPAA Safe Harbor (§164.514)
              </div>
              TCGA open research data de-identified per HIPAA Safe Harbor (§164.514) combined with Synthea algorithmic synthetic profiles. Zero live patient data.
            </div>
          </div>
          {LOCAL_DATA ? (
            <span className="t-muted t-mono hidden 2xl:inline text-[11px]" title="Local mode: data is read from the work/ folder on this computer">
              local mode · work/
            </span>
          ) : (
            portalUrl && (
              <a
                href={portalUrl}
                target="_blank"
                rel="noreferrer"
                className="link t-muted t-mono hidden 2xl:inline text-[11px]"
                title={catalog?.lakehouse.oneLakePath}
              >
                {portalLabel}
              </a>
            )
          )}
          {user && !LOCAL_DATA && (
            <>
              <span className="t-faint hidden 2xl:inline text-[11px]">{user.email || user.name}</span>
              <button onClick={() => void signOut()} className="link t-muted text-[11.5px]">
                Sign out
              </button>
            </>
          )}
          <ThemeToggle />
          <button
            type="button"
            className="md:hidden flex items-center gap-1 rounded border border-[var(--line)] px-2 py-1 text-[12px] font-medium text-[var(--ink)] hover:bg-[var(--surface-muted)] focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
            onClick={() => setMobileMenuOpen((o) => !o)}
            aria-expanded={mobileMenuOpen}
            aria-label="Toggle navigation sections"
          >
            <span>Sections</span>
            <span aria-hidden="true" className="text-[10px]">{mobileMenuOpen ? '▲' : '▼'}</span>
          </button>
        </div>
      </div>

      {/* Mobile horizontal tab bar for quick swiping */}
      <nav
        className="flex md:hidden h-10 w-full max-w-full items-stretch gap-1 overflow-x-auto border-t border-[var(--line)] px-2 bg-[var(--surface-muted,#f8fafc)] dark:bg-slate-900/60"
        aria-label="Mobile quick sections"
      >
        {TABS.map((t) => (
          <Link
            key={t.to}
            to={t.to}
            className={`tab whitespace-nowrap px-2 text-[12px] ${t.active(pathname) ? 'active' : ''}`}
          >
            {t.label}
          </Link>
        ))}
      </nav>

      {/* Mobile dropdown sheet */}
      {mobileMenuOpen && (
        <div
          className="md:hidden border-t border-[var(--line)] bg-[var(--surface,#ffffff)] dark:bg-slate-900 px-4 py-3 shadow-lg"
          aria-label="Mobile sections menu"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {TABS.map((t) => (
              <Link
                key={t.to}
                to={t.to}
                onClick={() => setMobileMenuOpen(false)}
                className={`flex items-center justify-between rounded px-3 py-2 text-[13px] transition-colors ${
                  t.active(pathname)
                    ? 'bg-[var(--surface-muted,#f1f5f9)] font-semibold text-[var(--accent,#b0450a)]'
                    : 'text-[var(--ink-2)] hover:bg-[var(--surface-muted)]'
                }`}
              >
                <span>{t.title}</span>
                {t.active(pathname) && <span className="text-[11px] text-[var(--accent)] font-mono">active</span>}
              </Link>
            ))}
          </div>
        </div>
      )}
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
