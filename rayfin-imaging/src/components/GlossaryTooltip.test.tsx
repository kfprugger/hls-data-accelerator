import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GlossaryTooltip } from './GlossaryTooltip';

describe('GlossaryTooltip', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders trigger with term label and ARIA attributes', () => {
    render(<GlossaryTooltip term="OneLake" />);
    const trigger = screen.getByRole('button', { name: /OneLake: Microsoft Fabric glossary definition/i });
    expect(trigger).toBeDefined();
    expect(trigger.getAttribute('tabIndex')).toBe('0');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
  });

  it('renders custom children if supplied', () => {
    render(<GlossaryTooltip term="shortcut">Custom Shortcut Badge</GlossaryTooltip>);
    expect(screen.getByText('Custom Shortcut Badge')).toBeDefined();
  });

  it('opens tooltip after hover debounce delay', async () => {
    render(<GlossaryTooltip term="Direct Lake" />);
    const trigger = screen.getByRole('button');

    fireEvent.mouseEnter(trigger);
    expect(screen.queryByRole('tooltip')).toBeNull();

    act(() => {
      vi.advanceTimersByTime(120);
    });

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip).toBeDefined();
    expect(tooltip.textContent).toContain('Ultra-fast Power BI query mode');
  });

  it('opens immediately on focus and closes on blur', async () => {
    render(<GlossaryTooltip term="Eventhouse" />);
    const trigger = screen.getByRole('button');

    fireEvent.focus(trigger);
    act(() => {
      vi.advanceTimersByTime(10);
    });

    expect(screen.getByRole('tooltip')).toBeDefined();
    expect(screen.getByRole('tooltip').textContent).toContain('Real-Time Intelligence database engine');

    fireEvent.blur(trigger);
    act(() => {
      vi.advanceTimersByTime(10);
    });

    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('dismisses immediately on Escape key press (NFR-1)', async () => {
    render(<GlossaryTooltip term="Activator" />);
    const trigger = screen.getByRole('button');

    fireEvent.focus(trigger);
    act(() => {
      vi.advanceTimersByTime(10);
    });
    expect(screen.getByRole('tooltip')).toBeDefined();

    fireEvent.keyDown(trigger, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('dismisses via global Escape key when opened on hover without element focus (P1-1)', async () => {
    render(<GlossaryTooltip term="Activator" />);
    const trigger = screen.getByRole('button');

    fireEvent.mouseEnter(trigger);
    act(() => {
      vi.advanceTimersByTime(120);
    });
    expect(screen.getByRole('tooltip')).toBeDefined();

    // Press Escape globally on window
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('toggles on click and prevents default / stops propagation (P1-2)', async () => {
    const parentClick = vi.fn();
    render(
      <div onClick={parentClick}>
        <GlossaryTooltip term="OneLake" />
      </div>
    );
    const trigger = screen.getByRole('button');

    fireEvent.click(trigger);
    expect(screen.getByRole('tooltip')).toBeDefined();
    expect(parentClick).not.toHaveBeenCalled();

    fireEvent.click(trigger);
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('toggles on Enter / Space key press for keyboard accessibility', async () => {
    render(<GlossaryTooltip term="Data Agent" />);
    const trigger = screen.getByRole('button');

    fireEvent.keyDown(trigger, { key: 'Enter' });
    expect(screen.getByRole('tooltip')).toBeDefined();
    expect(screen.getByRole('tooltip').textContent).toContain('Fabric AI agent');

    fireEvent.keyDown(trigger, { key: ' ' });
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('cancels pending open timer if mouse leaves before debounce expires', async () => {
    render(<GlossaryTooltip term="Ontology" />);
    const trigger = screen.getByRole('button');

    fireEvent.mouseEnter(trigger);
    act(() => {
      vi.advanceTimersByTime(40);
    });
    fireEvent.mouseLeave(trigger);
    act(() => {
      vi.advanceTimersByTime(150);
    });

    expect(screen.queryByRole('tooltip')).toBeNull();
  });
});
