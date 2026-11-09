// @vitest-environment jsdom
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { PersonaBanner } from './PersonaBanner';
import { PersonaProvider, usePersona } from '@/hooks/usePersona';

function ReportServed({ persona }: { persona: 'nurse' | 'researcher' }) {
  const { reportServedPersona } = usePersona();
  return (
    <button type="button" data-testid="report-served" onClick={() => reportServedPersona(persona)}>
      report
    </button>
  );
}

// Mock LOCAL_DATA as true
vi.mock('@/lib/localMode', () => ({
  LOCAL_DATA: true,
}));

describe('PersonaBanner Component', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    }));
  });

  it('renders default Nurse Persona with account, green badge, and toggle button', () => {
    render(
      <PersonaProvider>
        <PersonaBanner />
      </PersonaProvider>
    );

    expect(screen.getByText('Clinical user')).toBeDefined();

    // Verify Nurse Persona badge
    const badge = screen.getByTestId('persona-badge');
    expect(badge.textContent).toBe('Nurse Persona (Full Clinical PHI)');
    expect(badge.className).toContain('emerald');

    // Verify toggle button
    const toggleBtn = screen.getByTestId('persona-toggle');
    expect(toggleBtn.textContent).toBe('Switch to Researcher Persona');
  });

  it('waits for the server-reported tier after toggling the requested persona', async () => {
    render(
      <PersonaProvider>
        <PersonaBanner />
        <ReportServed persona="researcher" />
      </PersonaProvider>
    );

    const toggleBtn = screen.getByTestId('persona-toggle');

    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.getByTestId('persona-badge').textContent).toBe('Nurse Persona (Full Clinical PHI)');
    await act(async () => {
      fireEvent.click(screen.getByTestId('report-served'));
    });

    expect(screen.getByText('researcher-demo')).toBeDefined();

    // Badge updates to Researcher Persona with purple theme
    const badge = screen.getByTestId('persona-badge');
    expect(badge.textContent).toBe('Researcher Persona (De-identified - HIPAA Safe)');
    expect(badge.className).toContain('purple');

    // Toggle button label updates
    expect(toggleBtn.textContent).toBe('Switch to Nurse Persona');

    // Toggle back to Nurse
    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.getByText('Clinical user')).toBeDefined();
    expect(badge.textContent).toBe('Nurse Persona (Full Clinical PHI)');
    expect(badge.className).toContain('emerald');
  });

  it('shows the tier the server served, not the requested persona', async () => {
    render(
      <PersonaProvider>
        <PersonaBanner />
        <ReportServed persona="researcher" />
      </PersonaProvider>
    );

    // Requested persona is nurse; the server answered with de-identified data.
    await act(async () => {
      fireEvent.click(screen.getByTestId('report-served'));
    });

    const badge = screen.getByTestId('persona-badge');
    expect(badge.textContent).toBe('Researcher Persona (De-identified - HIPAA Safe)');
    expect(badge.className).toContain('purple');
  });

  it('maintains responsive layout container classes for 1280px and 360px viewports', () => {
    const { container } = render(
      <PersonaProvider>
        <PersonaBanner />
      </PersonaProvider>
    );

    const banner = screen.getByTestId('persona-banner');
    expect(banner.className).toContain('w-full');
    expect(banner.className).toContain('shrink-0');

    // Inner container must use flex-wrap to prevent horizontal overflow
    const inner = container.querySelector('.flex-wrap');
    expect(inner).not.toBeNull();
  });
});
