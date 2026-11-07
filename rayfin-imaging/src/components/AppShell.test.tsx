// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { AppShell } from './AppShell';

vi.mock('@/hooks/AuthContext', () => ({
  useAuth: () => ({ user: null, signOut: vi.fn() }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/hooks/useCatalog', () => ({
  useCatalog: () => ({ catalog: null }),
  CatalogProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  VolumeCatalogProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/hooks/useCohort', () => ({
  useCohort: () => ({ patients: [], selected: null, select: vi.fn() }),
  CohortProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/hooks/usePersona', () => ({
  usePersona: () => ({ persona: 'nurse', togglePersona: vi.fn() }),
  PersonaProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/components/PersonaBanner', () => ({
  PersonaBanner: () => <div data-testid="mock-persona-banner" />,
}));

describe('AppShell Synthetic Data Badge', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it('renders the 100% synthetic data badge with accessible notice and tooltip', () => {
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    const badgeRegion = screen.getByRole('region', {
      name: /100% synthetic \/ public de-identified data notice/i,
    });
    expect(badgeRegion).toBeDefined();

    expect(screen.getByText('100% synthetic / public de-identified data')).toBeDefined();
    expect(screen.getByText('SYNTHETIC')).toBeDefined();

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip.textContent).toContain('TCGA open research data de-identified per HIPAA Safe Harbor (§164.514)');
    expect(tooltip.textContent).toContain('Synthea algorithmic synthetic profiles');
    expect(tooltip.textContent).toContain('Zero live patient data');
  });
});
