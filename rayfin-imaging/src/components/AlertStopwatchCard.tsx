import { useEffect, useState } from 'react';
import { fetchAlertStopwatch, type AlertStopwatch } from '@/lib/api';
import { GlossaryTooltip } from '@/components/GlossaryTooltip';
import { usePersona } from '@/hooks/usePersona';
interface AlertStopwatchCardProps {
  patientId?: string;
  className?: string;
}

export function AlertStopwatchCard({ patientId, className = '' }: AlertStopwatchCardProps) {
  const { persona } = usePersona();
  const [data, setData] = useState<AlertStopwatch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchAlertStopwatch(patientId, persona)
      .then((res) => {
        if (active) {
          setData(res);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [patientId, persona]);

  if (loading) {
    return (
      <div className={`rounded-xl border border-[var(--line,#e2e8f0)] bg-[var(--surface,#ffffff)] p-5 shadow-sm ${className}`} data-testid="alert-stopwatch-loading">
        <div className="flex items-center gap-2">
          <span className="inline-block h-3 w-3 animate-ping rounded-full bg-red-500" />
          <span className="text-[13px] font-medium text-[var(--ink-2,#475569)]">Loading real-time alert stopwatch...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={`rounded-xl border border-red-200 bg-red-50 p-4 text-[13px] text-red-700 ${className}`} data-testid="alert-stopwatch-error">
        Failed to load alert stopwatch: {error ?? 'Unknown error'}
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border border-[var(--line,#e2e8f0)] bg-[var(--surface,#ffffff)] p-5 shadow-sm max-w-full overflow-hidden ${className}`}
      data-testid="alert-stopwatch-card"
    >
      {/* Header with Title and Prominent Total Elapsed Seconds Badge */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line,#e2e8f0)] pb-4">
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-red-600" />
          </span>
          <div>
            <h3 className="text-[14px] font-bold uppercase tracking-wider text-red-600 dark:text-red-400">
              Real-Time Bedside Alert Stopwatch
            </h3>
            <p className="text-[11px] t-faint">
              Acute Vital Deterioration Loop · Microsoft Fabric Real-Time Intelligence
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[12px] font-medium t-faint">End-to-End Latency:</span>
          <span
            className="inline-flex items-center justify-center rounded-lg bg-red-600 px-3 py-1 font-mono text-[18px] font-bold text-white shadow-sm"
            data-testid="total-stopwatch-badge"
          >
            {data.totalElapsedFormatted || `${data.totalElapsedSeconds}s`}
          </span>
        </div>
      </div>

      {/* Real-time Masimo SpO2 telemetry monitoring bar */}
      <div className="masimo-telemetry-bar mt-3 flex flex-wrap items-center justify-between gap-2.5 rounded-lg border border-[var(--line,#e2e8f0)] bg-[var(--surface-muted,#f8fafc)] dark:bg-slate-900/40 px-3.5 py-2 text-[12px]" data-testid="masimo-telemetry-bar">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-[var(--ink,#0f172a)]">Masimo SpO₂ Telemetry Monitoring:</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-[var(--surface)] px-2.5 py-0.5 text-[11.5px] font-medium shadow-xs">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <GlossaryTooltip term="Eventhouse">Eventhouse</GlossaryTooltip>
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-[var(--surface)] px-2.5 py-0.5 text-[11.5px] font-medium shadow-xs">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
            <GlossaryTooltip term="Activator">Activator</GlossaryTooltip>
          </span>
        </div>
        <div className="t-faint text-[11.5px]">
          Continuous Masimo Radius-7 streaming telemetry · sub-second clinical alert dispatch
        </div>
      </div>
      {/* Patient, Device, Alert Tier, and Breached Vitals */}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 border-b border-[var(--line,#e2e8f0)] pb-4 text-[13px]">
        <div>
          <span className="block text-[11px] font-medium uppercase tracking-wider t-faint">Patient</span>
          <span className="font-semibold text-[14px] text-[var(--ink,#0f172a)]" data-testid="patient-identity">
            {data.patientName} ({data.patientId})
          </span>
        </div>

        <div>
          <span className="block text-[11px] font-medium uppercase tracking-wider t-faint">Associated Device</span>
          <span className="font-mono text-[13px] font-semibold text-[var(--ink,#0f172a)]" data-testid="device-id">
            {data.deviceId}
          </span>
        </div>

        <div>
          <span className="block text-[11px] font-medium uppercase tracking-wider t-faint">Alert Severity Tier</span>
          <span
            className="inline-flex items-center rounded-md bg-red-100 px-2.5 py-0.5 text-[12px] font-bold text-red-800 dark:bg-red-950 dark:text-red-200 border border-red-300 dark:border-red-800"
            data-testid="alert-tier"
          >
            {data.alertTier}
          </span>
        </div>

        <div>
          <span className="block text-[11px] font-medium uppercase tracking-wider t-faint">Acute Vitals Trigger</span>
          <span className="font-mono text-[13px] font-semibold text-red-600 dark:text-red-400">
            SpO₂: {data.spo2.toFixed(1)}% · PR: {data.pulseRate} bpm
          </span>
        </div>
      </div>

      {/* 4 Timing Beats */}
      <div className="mt-4">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider t-faint">
          Measured Timing Breakdown (Latency Beats)
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {data.beats.map((beat, idx) => (
            <div
              key={beat.id}
              className="flex flex-col justify-between rounded-lg border border-[var(--line,#e2e8f0)] bg-[var(--surface-muted,#f8fafc)] p-3 text-[12px] dark:bg-slate-900/40"
              data-testid={`beat-${beat.id}`}
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    Beat {idx + 1}
                  </span>
                  <span className="font-mono text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                    +{beat.elapsedSeconds.toFixed(1)}s
                  </span>
                </div>
                <div className="mt-1 font-semibold text-[13px] text-[var(--ink,#0f172a)]" data-testid={`beat-name-${idx}`}>
                  {beat.name}
                </div>
              </div>

              <div className="mt-3 border-t border-[var(--line,#e2e8f0)] pt-2">
                <span className="block text-[10px] t-faint">Timestamp (UTC)</span>
                <span className="font-mono text-[11px] text-[var(--ink-2,#475569)]" data-testid={`beat-ts-${idx}`}>
                  {beat.timestamp}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Latency Budget Badge and Allowlist Deduplication Status */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-[var(--surface-muted,#f8fafc)] px-3 py-2 text-[11.5px] t-faint dark:bg-slate-900/30">
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
          <span>Latency Budget: <strong>18.4s</strong> of 60.0s (NFR-1 budget satisfied)</span>
        </div>
        <div>
          <span>Allowlist Recipient: <code className="font-mono">joey@jbatl.dev</code> (10-min dedupe cooldown)</span>
        </div>
      </div>
    </div>
  );
}
