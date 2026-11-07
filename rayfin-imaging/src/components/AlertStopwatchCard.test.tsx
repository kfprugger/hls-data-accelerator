// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { AlertStopwatchCard } from './AlertStopwatchCard';
import * as apiModule from '@/lib/api';

const mockStopwatchData: apiModule.AlertStopwatch = {
  patientId: 'TCGA-G6-A8L6',
  patientName: 'Marcus Vance',
  deviceId: 'MASIMO-RADIUS7-0101',
  alertTier: 'CRITICAL',
  spo2: 84.0,
  pulseRate: 115,
  totalElapsedSeconds: 18.4,
  totalElapsedFormatted: '18.4s',
  beats: [
    {
      id: 'telemetry_emitted',
      name: 'Telemetry Emitted',
      timestamp: '2026-11-07T12:00:00.000Z',
      elapsedSeconds: 0.0,
      status: 'completed',
    },
    {
      id: 'eventstream_enqueued',
      name: 'Eventstream Enqueued',
      timestamp: '2026-11-07T12:00:02.300Z',
      elapsedSeconds: 2.3,
      status: 'completed',
    },
    {
      id: 'kql_detected',
      name: 'KQL Detected',
      timestamp: '2026-11-07T12:00:08.100Z',
      elapsedSeconds: 8.1,
      status: 'completed',
    },
    {
      id: 'activator_dispatched',
      name: 'Activator Dispatched',
      timestamp: '2026-11-07T12:00:18.400Z',
      elapsedSeconds: 18.4,
      status: 'completed',
    },
  ],
  measuredAt: '2026-11-07T12:00:18.400Z',
  source: 'Recorded local benchmark fixture',
};

describe('AlertStopwatchCard component (FR-6, E-2, E-8)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state initially', () => {
    vi.spyOn(apiModule, 'fetchAlertStopwatch').mockReturnValue(new Promise(() => {}));
    render(<AlertStopwatchCard patientId="TCGA-G6-A8L6" />);
    expect(screen.getByTestId('alert-stopwatch-loading')).toBeDefined();
  });

  it('renders patient identity, device ID, alert tier, and total stopwatch badge', async () => {
    vi.spyOn(apiModule, 'fetchAlertStopwatch').mockResolvedValue(mockStopwatchData);
    render(<AlertStopwatchCard patientId="TCGA-G6-A8L6" />);

    await waitFor(() => {
      expect(screen.queryByTestId('alert-stopwatch-loading')).toBeNull();
    });

    // Check patient name and ID
    const patientElem = screen.getByTestId('patient-identity');
    expect(patientElem.textContent).toContain('Marcus Vance (TCGA-G6-A8L6)');

    // Check device ID
    const deviceElem = screen.getByTestId('device-id');
    expect(deviceElem.textContent).toBe('MASIMO-RADIUS7-0101');

    // Check alert severity tier
    const tierElem = screen.getByTestId('alert-tier');
    expect(tierElem.textContent).toBe('CRITICAL');

    // Check total elapsed stopwatch badge
    const badgeElem = screen.getByTestId('total-stopwatch-badge');
    expect(badgeElem.textContent).toBe('18.4s');
  });

  it('displays all 4 timing beats with non-zero timestamps and beat names', async () => {
    vi.spyOn(apiModule, 'fetchAlertStopwatch').mockResolvedValue(mockStopwatchData);
    render(<AlertStopwatchCard patientId="TCGA-G6-A8L6" />);

    await waitFor(() => {
      expect(screen.queryByTestId('alert-stopwatch-loading')).toBeNull();
    });

    // Verify 4 timing beats
    expect(screen.getByText('Telemetry Emitted')).toBeDefined();
    expect(screen.getByText('Eventstream Enqueued')).toBeDefined();
    expect(screen.getByText('KQL Detected')).toBeDefined();
    expect(screen.getByText('Activator Dispatched')).toBeDefined();

    // Verify non-zero timestamps
    expect(screen.getByText('2026-11-07T12:00:00.000Z')).toBeDefined();
    expect(screen.getByText('2026-11-07T12:00:02.300Z')).toBeDefined();
    expect(screen.getByText('2026-11-07T12:00:08.100Z')).toBeDefined();
    expect(screen.getByText('2026-11-07T12:00:18.400Z')).toBeDefined();
  });

  it('renders error state when fetch fails', async () => {
    vi.spyOn(apiModule, 'fetchAlertStopwatch').mockRejectedValue(new Error('Network error'));
    render(<AlertStopwatchCard patientId="TCGA-G6-A8L6" />);

    await waitFor(() => {
      expect(screen.getByTestId('alert-stopwatch-error')).toBeDefined();
    });
    expect(screen.getByText(/Failed to load alert stopwatch: Network error/)).toBeDefined();
  });
});
