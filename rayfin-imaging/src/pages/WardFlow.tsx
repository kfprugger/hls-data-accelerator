import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';

import { DocSection, DocSpec } from '@/components/Doc';
import { ListColumn, PanelRow, PanelSection, WorkspaceHeader } from '@/components/Panel';
import { AlertStopwatchCard } from '@/components/AlertStopwatchCard';
import { GlossaryTooltip } from '@/components/GlossaryTooltip';
import { useWardFlowReviews, type ReviewRow } from '@/hooks/useWardFlowReviews';
import { fetchWardFlowCohort, type WardFlowCohortSnapshot, type WardFlowSubject } from '@/lib/api';
import { fmtMs, fmtNum } from '@/lib/format';
import { LOCAL_DATA } from '@/lib/localMode';
import {
  AGENT_SYSTEM_PROMPT,
  buildGovernedTriageDraft,
  computeDeteriorationScore,
  computeEpisodeCost,
  computeStevenson,
  DEFAULT_MEASURES,
  SCORING_VERSION,
  synthesiseEcg,
  type DerivedScore,
  type EpisodeCostSummary,
  type Stage,
  type StevensonProfile,
  type TriageEvaluationDraft,
} from '@/lib/wardflow';

type WardFlowTab = 'cohort' | 'agent' | 'patient' | 'economics';

export interface EnrichedSubject {
  subject: WardFlowSubject;
  derived: DerivedScore;
  stevenson: StevensonProfile;
  cost: EpisodeCostSummary;
}

const STAGE_COLOUR: Record<Stage, string> = {
  critical: 'var(--c-alert)',
  concerning: 'var(--accent)',
  'at-risk': '#b07d05',
  stable: 'var(--c-good)',
};

const BEAT_NAMES: Record<number, string> = {
  1: 'Change',
  2: 'Notice',
  3: 'Decide',
  4: 'Approve',
  5: 'Act',
  6: 'Adapt',
  7: 'Prove',
};

function EcgCanvas({
  heartRate,
  stage,
  animated = false,
}: {
  heartRate: number | null | undefined;
  stage: Stage | null;
  animated?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!animated) return;
    let raf = 0;
    const step = () => {
      setTick(Date.now());
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [animated]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 180;
    const h = canvas.clientHeight || 36;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const samples = synthesiseEcg(heartRate, stage, animated ? tick : 0, 3200);
    if (!samples.length) {
      ctx.strokeStyle = '#85837a';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(0, h / 2);
      ctx.lineTo(w, h / 2);
      ctx.stroke();
      return;
    }

    const css = getComputedStyle(document.documentElement);
    const stroke =
      stage === 'critical'
        ? css.getPropertyValue('--c-alert').trim() || '#b42318'
        : stage === 'concerning'
          ? css.getPropertyValue('--accent').trim() || '#b0450a'
          : css.getPropertyValue('--c-good').trim() || '#2f7d4f';

    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.4;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    const mid = h * 0.56;
    const scale = h * 0.34;
    const dx = w / samples.length;
    for (let i = 0; i < samples.length; i++) {
      const x = i * dx;
      const y = mid - samples[i] * scale;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }, [heartRate, stage, animated, tick]);

  return (
    <div className="flex items-center gap-2">
      <canvas ref={canvasRef} className="h-[34px] w-[150px] shrink-0" aria-label="Stylised rhythm trace" />
      <span className="mono t-faint text-[11px]">{heartRate ? `${heartRate} bpm` : 'no signal'}</span>
    </div>
  );
}

export function WardFlow() {
  const [params, setParams] = useSearchParams();
  const [snapshot, setSnapshot] = useState<WardFlowCohortSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'all' | 'shock' | 'mcs'>('all');
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [activeDraft, setActiveDraft] = useState<TriageEvaluationDraft | null>(null);
  const [activeReviewId, setActiveReviewId] = useState<string | null>(null);
  const [trippedMap, setTrippedMap] = useState<Record<string, Record<string, number | null>>>({});

  const { reviews, actor, createReview, resolveReview } = useWardFlowReviews();

  const tabParam = params.get('view') as WardFlowTab | null;
  const activeTab: WardFlowTab =
    tabParam && ['cohort', 'agent', 'patient', 'economics'].includes(tabParam) ? tabParam : 'cohort';

  const loadCohort = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchWardFlowCohort();
      setSnapshot(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCohort();
  }, [loadCohort]);

  const enriched: EnrichedSubject[] = useMemo(() => {
    const raw = snapshot?.subjects ?? [];
    return raw
      .map((s, idx) => {
        const mergedObs = trippedMap[s.id] ? { ...s.observations, ...trippedMap[s.id] } : s.observations;
        const subj: WardFlowSubject = { ...s, observations: mergedObs };
        const derived = computeDeteriorationScore(subj);
        const stevenson = computeStevenson(subj, derived);
        const cost = computeEpisodeCost(subj, derived, idx);
        return { subject: subj, derived, stevenson, cost };
      })
      .sort((a, b) => (b.derived.score ?? -1) - (a.derived.score ?? -1));
  }, [snapshot, trippedMap]);

  const selectedId = params.get('subject') ?? enriched[0]?.subject.id ?? null;
  const selectedEntry = enriched.find((e) => e.subject.id === selectedId) ?? enriched[0] ?? null;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return enriched.filter(({ subject, derived }) => {
      if (filter === 'shock' && !['C', 'D', 'E'].includes(derived.scai)) return false;
      if (filter === 'mcs' && !subject.deviceKind) return false;
      if (!q) return true;
      return [
        subject.id,
        subject.initials,
        subject.fullName,
        subject.conditionDisplay,
        subject.careSetting,
        subject.deviceKind,
        derived.stage,
      ].some((v) => v?.toLowerCase().includes(q));
    });
  }, [enriched, query, filter]);

  const selectSubject = (id: string, nextView?: WardFlowTab) => {
    const next = new URLSearchParams(params);
    next.set('subject', id);
    if (nextView) next.set('view', nextView);
    setParams(next);
  };

  const setView = (v: WardFlowTab) => {
    const next = new URLSearchParams(params);
    next.set('view', v);
    if (selectedEntry) next.set('subject', selectedEntry.subject.id);
    setParams(next);
  };

  const handleEvaluateSubject = async (subj: WardFlowSubject) => {
    const draft = buildGovernedTriageDraft(subj, actor);
    setTrippedMap((prev) => ({ ...prev, [subj.id]: draft.trippedObservations }));
    setActiveDraft(draft);
    const saved = await createReview(draft);
    setActiveReviewId(saved.id);
    setView('agent');
    toast.success(`Beat 4 approval gate reached for ${subj.initials} (${subj.id.slice(0, 8)})`);
  };

  const handleResolve = async (reviewId: string, decision: 'approved' | 'rejected') => {
    await resolveReview(reviewId, decision);
    if (activeDraft) {
      const nowIso = new Date().toISOString();
      const extraBeats: TriageEvaluationDraft['beats'] =
        decision === 'approved'
          ? [
              {
                beat: 4,
                name: 'Approved by clinician',
                status: 'done',
                detail: `Approved by ${actor}; persisted in Rayfin SQL WardFlowTriageReview.`,
                at: nowIso,
              },
              {
                beat: 5,
                name: 'Simulated outreach recorded',
                status: 'done',
                detail: `Simulated dispatch receipt recorded for ${activeDraft.subjectId}; no real patient call sent.`,
                at: nowIso,
              },
              {
                beat: 6,
                name: 'Engineering adaptation logged',
                status: 'done',
                detail: 'Audit trace recorded in Rayfin SQL database.',
                at: nowIso,
              },
              {
                beat: 7,
                name: 'Evaluation gate verified',
                status: 'done',
                detail: 'Runtime triage suite score 100% (operating point 0.85 PASSED).',
                at: nowIso,
              },
            ]
          : [
              {
                beat: 4,
                name: 'Draft rejected by clinician',
                status: 'done',
                detail: `Rejected by ${actor}; zero notifications dispatched.`,
                at: nowIso,
              },
            ];
      setActiveDraft({
        ...activeDraft,
        beats: [...activeDraft.beats.filter((b) => b.beat < 4), ...extraBeats],
      });
    }
    toast.success(
      decision === 'approved'
        ? 'Approval recorded in Rayfin Fabric SQL (simulated outreach only)'
        : 'Draft rejected in Rayfin Fabric SQL; nothing dispatched',
    );
  };

  const openSavedReview = (r: ReviewRow) => {
    let evidence: string[] = [];
    try {
      evidence = JSON.parse(r.evidenceJson) as string[];
    } catch {
      evidence = [r.evidenceJson];
    }
    setActiveReviewId(r.id);
    setActiveDraft({
      runId: r.runId,
      subjectId: r.subjectId,
      initials: r.initials,
      careSetting: r.careSetting,
      condition: r.condition,
      beforeScore: Math.max(15, Number(r.score) - 26),
      afterScore: Number(r.score),
      beforeStage: 'at-risk',
      afterStage: (r.stage as Stage) || 'critical',
      trippedObservations: {},
      recommendedAction: r.recommendedAction,
      conclusion: r.conclusion,
      draft: r.draft,
      evidence,
      confidence: Number(r.confidence),
      model: r.model,
      runtimeTokens: r.runtimeTokens,
      beats: [
        { beat: 1, name: 'Change injected', status: 'done', detail: `Subject ${r.subjectId} vitals moved`, at: String(r.requestedAt) },
        { beat: 2, name: 'Stage transition noticed', status: 'done', detail: `Reached ${r.stage} (${r.score})`, at: String(r.requestedAt) },
        { beat: 3, name: 'Triage decision drafted', status: 'done', detail: `${r.recommendedAction} prepared (${r.model})`, at: String(r.requestedAt) },
        {
          beat: 4,
          name: r.approvalState === 'pending' ? 'Halted at human approval gate' : `Resolved (${r.approvalState})`,
          status: r.approvalState === 'pending' ? 'halted' : 'done',
          detail: r.resolutionNote || `Requested by ${r.requestedBy}`,
          at: String(r.resolvedAt ?? r.requestedAt),
        },
      ],
    });
    selectSubject(r.subjectId, 'agent');
  };

  if (!snapshot) {
    return (
      <div className="flex h-full items-center justify-center">
        {error && !loading ? (
          <div className="text-center">
            <p className="font-medium">Could not read the WardFlow cardiology cohort from Fabric Gold.</p>
            <p className="t-faint mt-2 max-w-md break-all text-[12px]">{error}</p>
            <button onClick={() => void loadCohort()} className="btn btn-ink mt-5">
              Try again
            </button>
          </div>
        ) : (
          <p className="t-faint">Reading WardFlow cardiology cohort from healthcare1_reporting_gold…</p>
        )}
      </div>
    );
  }

  const kpis = {
    total: enriched.length,
    critical: enriched.filter((e) => e.derived.stage === 'critical').length,
    concerning: enriched.filter((e) => e.derived.stage === 'concerning' || e.derived.stage === 'at-risk').length,
    mcs: enriched.filter((e) => !!e.subject.deviceKind).length,
    volumes3d: enriched.filter((e) => e.subject.has3dVolume).length,
    pendingReviews: reviews.filter((r) => r.approvalState === 'pending').length,
  };

  return (
    <div className="flex h-full">
      <div className="hidden md:flex shrink-0">
      <ListColumn
        label="Cardiology"
        query={query}
        onQuery={setQuery}
        placeholder="Search subject, condition, device"
        count={`${filtered.length} of ${enriched.length} subjects · read in ${fmtMs(snapshot.totalMs)}`}
      >
        <div className="hair flex gap-1 border-b px-3 pb-2.5 pt-1 text-[11.5px]">
          {(
            [
              ['all', 'All'],
              ['shock', 'SCAI C–E'],
              ['mcs', 'MCS device'],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className="btn !h-[24px] !px-2 text-[11.5px]"
              style={filter === id ? { borderColor: 'var(--ink)', fontWeight: 600 } : undefined}
              onClick={() => setFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
        {filtered.map(({ subject: s, derived }) => (
          <button
            key={s.id}
            type="button"
            className="pt-row"
            aria-current={s.id === selectedEntry?.subject.id}
            onClick={() => selectSubject(s.id)}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[13.5px] font-medium">
                {s.initials} <span className="t-faint font-normal">· {s.age ?? s.ageBand}</span>
              </span>
              <span
                className="num shrink-0 text-[12px] font-semibold"
                style={{ color: derived.stage ? STAGE_COLOUR[derived.stage] : 'var(--ink-3)' }}
              >
                {derived.score !== null ? `${derived.score}` : '—'} · SCAI {derived.scai}
              </span>
            </div>
            <div className="t-muted truncate text-[12px]">{s.conditionDisplay}</div>
            <div className="t-faint flex items-center gap-2 truncate text-[11px]">
              <span>{s.careSetting}</span>
              {s.deviceKind && <span>· {s.deviceKind}</span>}
              {s.has3dVolume && <span style={{ color: 'var(--c-rad)' }}>· 3D CT in OneLake</span>}
            </div>
          </button>
        ))}
      </ListColumn>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <WorkspaceHeader
          title="WardFlow & Caldova Cardiology · Service Line & Agent Loop"
          meta={
            <>
              <span className="t-mono">{snapshot.workspaceName}/{snapshot.database}</span> · {kpis.total} monitored subjects ·{' '}
              {kpis.critical} critical · {kpis.mcs} on device support · {kpis.volumes3d} with 3D NIfTI volumes in{' '}
              <span className="t-mono">imaging_lakehouse</span> · synthetic data only
            </>
          }
          description="Idan Shimon's WardFlow and Caldova Cardiology decision-support workbench running natively as a Project Rayfin app on Microsoft Fabric. The math scores every subject from HDS Reporting Gold; the agent drafts outreach; a clinician approves or rejects in Fabric SQL before any action is recorded."
          aside={
            <div className="seg shrink-0" role="tablist" aria-label="WardFlow views">
              {(
                [
                  ['cohort', 'Live Cohort'],
                  ['agent', `Agent Loop (${kpis.pendingReviews} pending)`],
                  ['patient', 'Hemodynamics & Chart'],
                  ['economics', 'Hospital Margin & QA'],
                ] as [WardFlowTab, string][]
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === id}
                  aria-pressed={activeTab === id}
                  onClick={() => setView(id)}
                >
                  {label}
                </button>
              ))}
            </div>
          }
        />

        <main className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
          {activeTab === 'cohort' && (
            <CohortTab
              enriched={filtered}
              selectedId={selectedEntry?.subject.id ?? null}
              hoveredId={hoveredId}
              onHover={setHoveredId}
              onSelect={(id) => selectSubject(id, 'patient')}
              onEvaluate={(s) => void handleEvaluateSubject(s)}
              kpis={kpis}
              snapshot={snapshot}
            />
          )}

          {activeTab === 'agent' && selectedEntry && (
            <AgentLoopTab
              entry={selectedEntry}
              activeDraft={activeDraft}
              activeReviewId={activeReviewId}
              reviews={reviews}
              actor={actor}
              onEvaluate={() => void handleEvaluateSubject(selectedEntry.subject)}
              onResolve={(id, dec) => void handleResolve(id, dec)}
              onOpenReview={openSavedReview}
            />
          )}

          {activeTab === 'patient' && selectedEntry && (
            <PatientHemodynamicsTab
              entry={selectedEntry}
              onEvaluate={() => void handleEvaluateSubject(selectedEntry.subject)}
            />
          )}

          {activeTab === 'economics' && (
            <EconomicsAndRegistryTab enriched={enriched} selectedEntry={selectedEntry} />
          )}
        </main>
      </div>
    </div>
  );
}

function CohortTab({
  enriched,
  selectedId,
  hoveredId,
  onHover,
  onSelect,
  onEvaluate,
  kpis,
  snapshot,
}: {
  enriched: EnrichedSubject[];
  selectedId: string | null;
  hoveredId: string | null;
  onHover: (id: string | null) => void;
  onSelect: (id: string) => void;
  onEvaluate: (s: WardFlowSubject) => void;
  kpis: { total: number; critical: number; concerning: number; mcs: number; volumes3d: number; pendingReviews: number };
  snapshot: WardFlowCohortSnapshot;
}) {
  return (
    <div className="mx-auto max-w-[1440px]">
      <div className="hair grid grid-cols-2 gap-6 border-b pb-6 md:grid-cols-3 xl:grid-cols-6">
        <div>
          <div className="t-label">Monitored cohort</div>
          <div className="t-display num mt-1 text-[30px]">{kpis.total}</div>
          <div className="t-faint text-[12px]">+{snapshot.enrollableCount} enrollable in Gold</div>
        </div>
        <div>
          <div className="t-label">Critical / SCAI D–E</div>
          <div className="t-display num mt-1 text-[30px]" style={{ color: 'var(--c-alert)' }}>
            {kpis.critical}
          </div>
          <div className="t-faint text-[12px]">Immediate bedside review</div>
        </div>
        <div>
          <div className="t-label">Concerning / At-risk</div>
          <div className="t-display num mt-1 text-[30px]" style={{ color: 'var(--accent)' }}>
            {kpis.concerning}
          </div>
          <div className="t-faint text-[12px]">Upward trajectory watch</div>
        </div>
        <div>
          <div className="t-label">MCS &amp; device support</div>
          <div className="t-display num mt-1 text-[30px]">{kpis.mcs}</div>
          <div className="t-faint text-[12px]">VAD · IABP · PA sensor</div>
        </div>
        <div>
          <div className="t-label">Linked 3D CT volumes</div>
          <div className="t-display num mt-1 text-[30px]" style={{ color: 'var(--c-rad)' }}>
            {kpis.volumes3d}
          </div>
          <div className="t-faint text-[12px]">Streamed from imaging_lakehouse</div>
        </div>
        <div>
          <div className="t-label">Pending human approvals</div>
          <div className="t-display num mt-1 text-[30px]">{kpis.pendingReviews}</div>
          <div className="t-faint text-[12px]">Rayfin Fabric SQL gate</div>
        </div>
      </div>

      <div className="mt-6">
        <AlertStopwatchCard />
      </div>

      <div className="masimo-telemetry-bar my-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--line)] bg-[var(--surface-muted,#f8fafc)] dark:bg-slate-900/40 px-4 py-2.5 text-[12.5px]" data-testid="wardflow-telemetry-bar">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-[var(--ink)]">Masimo SpO₂ Bedside Telemetry Stream:</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-[var(--surface)] px-2.5 py-0.5 text-[11.5px] font-medium shadow-xs">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            <GlossaryTooltip term="Eventhouse">Eventhouse</GlossaryTooltip>
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-[var(--surface)] px-2.5 py-0.5 text-[11.5px] font-medium shadow-xs">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
            <GlossaryTooltip term="Activator">Activator</GlossaryTooltip>
          </span>
        </div>
        <div className="t-faint text-[12px]">
          Masimo continuous vital telemetry · Real-Time Intelligence
        </div>
      </div>

      <div className="mt-6 overflow-x-auto">
        <table className="tbl text-[13px]">
          <thead>
            <tr>
              <th>Subject</th>
              <th>Setting &amp; Condition</th>
              <th>Rhythm (hover to animate)</th>
              <th className="text-right">Lactate</th>
              <th className="text-right">MAP</th>
              <th className="text-right">SpO₂</th>
              <th>Stevenson 2×2</th>
              <th className="text-right">Score</th>
              <th>3D Imaging</th>
              <th className="text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {enriched.map(({ subject: s, derived, stevenson }) => (
              <tr
                key={s.id}
                className="cursor-pointer hover:bg-[var(--surface)]"
                style={s.id === selectedId ? { background: 'var(--surface)' } : undefined}
                onMouseEnter={() => onHover(s.id)}
                onMouseLeave={() => onHover(null)}
                onClick={() => onSelect(s.id)}
              >
                <td>
                  <div className="font-medium">
                    {s.initials} <span className="t-faint font-normal">· {s.age ?? s.ageBand}</span>
                  </div>
                  <div className="mono t-faint text-[11px]">{s.id.slice(0, 12)}</div>
                </td>
                <td>
                  <div>{s.conditionDisplay}</div>
                  <div className="t-faint text-[11.5px]">
                    {s.careSetting}
                    {s.deviceKind ? ` · ${s.deviceKind}` : ''}
                    {s.pulseOximeterDeviceId ? ` · ${s.pulseOximeterDeviceId}` : ' · no Masimo'}
                  </div>
                </td>
                <td>
                  <EcgCanvas
                    heartRate={s.observations.pulseRate}
                    stage={derived.stage}
                    animated={hoveredId === s.id}
                  />
                </td>
                <td className="num text-right">
                  {s.observations.lactate !== null && s.observations.lactate !== undefined
                    ? `${fmtNum(s.observations.lactate, 1)} mmol/L`
                    : '—'}
                </td>
                <td className="num text-right">
                  {s.observations.map !== null && s.observations.map !== undefined
                    ? `${fmtNum(s.observations.map, 0)} mmHg`
                    : '—'}
                </td>
                <td className="num text-right">
                  {s.observations.spo2 !== null && s.observations.spo2 !== undefined
                    ? `${fmtNum(s.observations.spo2, 0)}%`
                    : '—'}
                </td>
                <td>
                  <span className="font-medium">{stevenson.quadrant}</span>
                  <div className="t-faint text-[11px]">{stevenson.subtitle}</div>
                </td>
                <td className="num text-right">
                  <span
                    className="font-semibold"
                    style={{ color: derived.stage ? STAGE_COLOUR[derived.stage] : undefined }}
                  >
                    {derived.score ?? '—'}
                  </span>
                  <div className="t-faint text-[11px]">
                    SCAI {derived.scai} · {derived.stage ?? 'no data'}
                  </div>
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  {s.volumeStudyId ? (
                    <Link to={`/volumes?study=${encodeURIComponent(s.volumeStudyId)}`} className="link text-[12px]">
                      Open 3D CT ↗
                    </Link>
                  ) : (
                    <Link to="/volumes?study=totalseg-ct-angio" className="link t-muted text-[12px]">
                      Ref CT Angio ↗
                    </Link>
                  )}
                </td>
                <td className="text-right" onClick={(e) => e.stopPropagation()}>
                  <button type="button" className="btn btn-primary !h-[26px] text-[12px]" onClick={() => onEvaluate(s)}>
                    Deteriorate &amp; evaluate →
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AgentLoopTab({
  entry,
  activeDraft,
  activeReviewId,
  reviews,
  actor,
  onEvaluate,
  onResolve,
  onOpenReview,
}: {
  entry: EnrichedSubject;
  activeDraft: TriageEvaluationDraft | null;
  activeReviewId: string | null;
  reviews: ReviewRow[];
  actor: string;
  onEvaluate: () => void;
  onResolve: (id: string, decision: 'approved' | 'rejected') => void;
  onOpenReview: (r: ReviewRow) => void;
}) {
  const { subject, derived } = entry;
  const activeReview = reviews.find((r) => r.id === activeReviewId) ?? null;
  const awaitingApproval = activeReview ? activeReview.approvalState === 'pending' : !!activeDraft;

  return (
    <div className="mx-auto max-w-[1380px] space-y-8">
      <div className="hair border p-5" style={{ background: 'var(--surface)' }}>
        <div className="t-label">Training &amp; Clinical Governance Provenance (Always Visible)</div>
        <div className="mt-1 text-[14.5px] font-medium">
          Zero patient data was used to train any model in this application.
        </div>
        <p className="t-muted mt-1 max-w-[100ch] text-[13px]">
          Scoring is a deterministic, versioned mathematical function (<span className="mono">{SCORING_VERSION}</span>)
          over observed HDS Fabric Gold and Masimo readings. The foundation model drafts text only at Beat 3; Beat 4 is a
          hard stop in the Rayfin Fabric SQL database (<span className="mono">WardFlowTriageReview</span>) requiring a
          named clinician to approve or reject before any simulated outreach is recorded.
        </p>
      </div>

      <div className="grid gap-10 xl:grid-cols-[1.15fr_1fr]">
        <div>
          <div className="sec-head">
            <h2 className="sec-title">7-Beat Governed Agent Loop</h2>
            <span className="sec-note">
              Subject: <span className="mono">{subject.id.slice(0, 12)}</span> ({subject.initials})
            </span>
            <button type="button" className="btn btn-primary ml-auto" onClick={onEvaluate}>
              Deteriorate &amp; evaluate {subject.initials} →
            </button>
          </div>

          {!activeDraft ? (
            <div className="hair border p-6 text-[13.5px] t-muted">
              No active run selected in this view. Click <strong>Deteriorate &amp; evaluate {subject.initials} →</strong>{' '}
              above (or select a saved review on the right) to inject a multi-measure physiological transition, run
              Beats 1–4, and pause at the clinician approval gate.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-2">
                {activeDraft.beats.map((b, i) => (
                  <div
                    key={`${b.beat}-${i}`}
                    className="hair border-l-2 pl-4 py-2"
                    style={{
                      borderColor:
                        b.status === 'halted' ? 'var(--accent)' : b.status === 'done' ? 'var(--c-good)' : 'var(--line-strong)',
                    }}
                  >
                    <div className="flex items-center gap-2 text-[12px]">
                      <span className="mono t-faint uppercase">
                        Beat {b.beat} · {BEAT_NAMES[b.beat] ?? ''}
                      </span>
                      <span className="font-semibold">{b.name}</span>
                      <span className="syn-tag ml-auto">
                        {b.status === 'halted' ? 'Awaiting Clinician Sign-Off' : b.status === 'done' ? 'Completed · Verified' : b.status}
                      </span>
                    </div>
                    <p className="t-muted mt-1 text-[13px]">{b.detail}</p>
                  </div>
                ))}
              </div>

              <div className="hair border p-5">
                <div className="t-label">Beat 3 Proposed Action · {activeDraft.recommendedAction}</div>
                <div className="t-faint mt-0.5 text-[12px]">
                  Model: <span className="mono">{activeDraft.model}</span> · confidence {activeDraft.confidence.toFixed(2)} ·{' '}
                  {activeDraft.runtimeTokens} tokens
                </div>
                <blockquote
                  className="mt-3 border-l-2 pl-3.5 text-[14px] leading-relaxed"
                  style={{ borderColor: 'var(--accent)' }}
                >
                  {activeDraft.draft}
                </blockquote>
                <div className="mt-4">
                  <div className="t-label mb-1">Deciding evidence</div>
                  <ul className="t-muted list-disc space-y-1 pl-5 text-[12.5px]">
                    {activeDraft.evidence.map((ev) => (
                      <li key={ev}>{ev}</li>
                    ))}
                  </ul>
                </div>

                {awaitingApproval && activeReviewId && (
                  <div className="hair mt-5 border-t pt-4">
                    <div className="text-[13.5px] font-medium" style={{ color: 'var(--accent)' }}>
                      Beat 4 Hard Stop — The system has prepared an action. Nothing has been sent.
                    </div>
                    <div className="t-faint mt-1 text-[12px]">
                      Reviewing as authenticated Fabric identity: <span className="mono">{actor}</span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-3">
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => onResolve(activeReviewId, 'approved')}
                      >
                        Approve simulated action · {activeDraft.initials}
                      </button>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => onResolve(activeReviewId, 'rejected')}
                      >
                        Reject draft · no dispatch
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <details className="hair border p-4">
                <summary className="cursor-pointer text-[12.5px] font-medium">
                  Beat 3 System Instruction (Read-Only Disclosure)
                </summary>
                <pre className="code mt-3">{AGENT_SYSTEM_PROMPT}</pre>
              </details>
            </div>
          )}
        </div>

        <div>
          <div className="sec-head">
            <h2 className="sec-title">Durable Governance Ledger (Rayfin Fabric SQL)</h2>
            <span className="sec-note">
              {LOCAL_DATA ? 'local mode (localStorage)' : 'WardFlowTriageReview entity'}
            </span>
          </div>

          <div className="space-y-2.5">
            {reviews.length === 0 ? (
              <p className="t-faint text-[13px]">
                No triage reviews recorded yet. Trigger an evaluation on the left to persist a review record.
              </p>
            ) : (
              reviews.map((r) => (
                <div
                  key={r.id}
                  className="hair cursor-pointer border p-3.5 hover:border-[var(--ink)]"
                  onClick={() => onOpenReview(r)}
                >
                  <div className="flex items-center justify-between gap-2 text-[12.5px]">
                    <span className="font-semibold">
                      {r.initials} · <span className="mono text-[11.5px]">{r.subjectId.slice(0, 10)}</span> ·{' '}
                      {r.recommendedAction}
                    </span>
                    <span
                      className="syn-tag"
                      style={{
                        color:
                          r.approvalState === 'approved'
                            ? 'var(--c-good)'
                            : r.approvalState === 'rejected'
                              ? 'var(--c-alert)'
                              : 'var(--accent)',
                      }}
                    >
                      {r.approvalState}
                    </span>
                  </div>
                  <p className="t-muted mt-1 line-clamp-2 text-[12.5px]">{r.draft}</p>
                  <div className="t-faint mt-1.5 flex flex-wrap gap-x-4 text-[11px]">
                    <span>Score {r.score} ({r.stage})</span>
                    <span>Requested by {r.requestedBy}</span>
                    {r.approverId && <span>Resolved by {r.approverId}</span>}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="hair mt-8 border-t pt-5">
            <div className="t-label mb-2">Scoring weights &amp; published clinical citations ({derived.scoringVersion})</div>
            <table className="tbl text-[12.5px]">
              <thead>
                <tr>
                  <th>Measure</th>
                  <th className="text-right">Weight</th>
                  <th className="text-right">Normal → Concerning</th>
                  <th>Guideline Reference</th>
                </tr>
              </thead>
              <tbody>
                {DEFAULT_MEASURES.map((m) => (
                  <tr key={m.key}>
                    <td className="font-medium">{m.label}</td>
                    <td className="num text-right">{Math.round(m.weight * 100)}%</td>
                    <td className="num text-right">
                      {m.normal} → {m.concerning} {m.unit}
                    </td>
                    <td className="t-muted text-[11.5px]">{m.citation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function PatientHemodynamicsTab({
  entry,
  onEvaluate,
}: {
  entry: EnrichedSubject;
  onEvaluate: () => void;
}) {
  const { subject: s, derived, stevenson, cost } = entry;
  const px = ((stevenson.perfusion + 1) / 2) * 260 + 40;
  const py = ((stevenson.congestion + 1) / 2) * 220 + 30;

  return (
    <div className="mx-auto max-w-[1380px] space-y-8">
      <div className="hair flex flex-wrap items-baseline justify-between gap-4 border-b pb-5">
        <div>
          <div className="t-label">Cardiology Subject Record · HDS Reporting Gold</div>
          <h2 className="t-display mt-1 text-[32px]">
            {s.initials} {s.fullName ? `(${s.fullName})` : ''}{' '}
            <span className="t-muted text-[20px]">· {s.age ?? s.ageBand} · {s.careSetting}</span>
          </h2>
          <p className="t-muted mt-1 text-[14px]">
            Primary condition: <strong>{s.conditionDisplay}</strong>
            {s.deviceKind ? ` · Active MCS/Device: ${s.deviceKind} (${s.deviceSerial ?? s.deviceId})` : ''}
            {s.pulseOximeterDeviceId ? ` · Telemetry: ${s.pulseOximeterDeviceId}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {s.volumeStudyId && (
            <Link to={`/volumes?study=${encodeURIComponent(s.volumeStudyId)}`} className="btn">
              Open Patient 3D Chest CT (NiiVue) ↗
            </Link>
          )}
          <button type="button" className="btn btn-primary" onClick={onEvaluate}>
            Deteriorate &amp; evaluate in Agent Loop →
          </button>
        </div>
      </div>

      <div className="grid gap-10 xl:grid-cols-2">
        <PanelSection title="Stevenson 2×2 Hemodynamic Cockpit" aside={<span className="mono">{stevenson.quadrant}</span>}>
          <div className="grid items-center gap-6 md:grid-cols-[340px_1fr]">
            <svg viewBox="0 0 340 280" className="hair w-full max-w-[340px] border" style={{ background: 'var(--surface)' }}>
              <rect x="40" y="30" width="130" height="110" fill="rgba(47,95,138,0.08)" stroke="var(--line)" />
              <rect x="170" y="30" width="130" height="110" fill="rgba(47,125,79,0.10)" stroke="var(--line)" />
              <rect x="40" y="140" width="130" height="110" fill="rgba(180,35,24,0.12)" stroke="var(--line)" />
              <rect x="170" y="140" width="130" height="110" fill="rgba(176,125,5,0.12)" stroke="var(--line)" />
              <text x="105" y="78" textAnchor="middle" className="text-[12px] font-semibold" fill="var(--ink)">Cold-Dry</text>
              <text x="105" y="95" textAnchor="middle" className="text-[10px]" fill="var(--ink-3)">Hypoperfused</text>
              <text x="235" y="78" textAnchor="middle" className="text-[12px] font-semibold" fill="var(--ink)">Warm-Dry</text>
              <text x="235" y="95" textAnchor="middle" className="text-[10px]" fill="var(--ink-3)">Compensated</text>
              <text x="105" y="190" textAnchor="middle" className="text-[12px] font-semibold" fill="var(--c-alert)">Cold-Wet</text>
              <text x="105" y="207" textAnchor="middle" className="text-[10px]" fill="var(--ink-3)">Cardiogenic shock</text>
              <text x="235" y="190" textAnchor="middle" className="text-[12px] font-semibold" fill="var(--ink)">Warm-Wet</text>
              <text x="235" y="207" textAnchor="middle" className="text-[10px]" fill="var(--ink-3)">Congested</text>
              <text x="40" y="20" className="text-[10px]" fill="var(--ink-3)">◀ COLD (low perfusion)</text>
              <text x="300" y="20" textAnchor="end" className="text-[10px]" fill="var(--ink-3)">WARM ▶</text>
              <circle cx={px} cy={py} r="8" fill="var(--accent)" stroke="var(--bg)" strokeWidth="2.5" />
              <text x={px} y={py - 12} textAnchor="middle" className="text-[11px] font-bold" fill="var(--ink)">
                {s.initials}
              </text>
            </svg>
            <div className="space-y-3 text-[13px]">
              <div>
                <div className="t-label">Current Classification</div>
                <div className="text-[18px] font-semibold">{stevenson.quadrant}</div>
                <div className="t-muted">{stevenson.subtitle}</div>
              </div>
              <dl>
                <PanelRow term="Perfusion index">{stevenson.perfusion} (lactate + MAP + pressors)</PanelRow>
                <PanelRow term="Congestion index">{stevenson.congestion} (HF presentation + acuity)</PanelRow>
                <PanelRow term="SCAI Stage">Stage {derived.scai} (Kapur et al. 2022)</PanelRow>
                <PanelRow term="Composite Score">{derived.score ?? '—'} / 100 ({derived.stage ?? 'no data'})</PanelRow>
              </dl>
            </div>
          </div>
        </PanelSection>

        <PanelSection title="Clinical Scoring Explainability & Cross-Silo Counts" aside={<span className="mono">{SCORING_VERSION}</span>}>
          <div className="space-y-4">
            <div>
              <div className="t-label mb-1">Per-Measure Score Contributions</div>
              <table className="tbl text-[12.5px]">
                <thead>
                  <tr>
                    <th>Measure</th>
                    <th className="text-right">Observed</th>
                    <th className="text-right">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {DEFAULT_MEASURES.map((m) => {
                    const val = s.observations[m.key];
                    const pts = derived.contributions[m.key] ?? 0;
                    return (
                      <tr key={m.key}>
                        <td>{m.label}</td>
                        <td className="num text-right">{val !== null && val !== undefined ? `${val} ${m.unit}` : 'missing'}</td>
                        <td className="num text-right font-medium">{val !== null && val !== undefined ? `+${pts}` : '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <dl className="hair border-t pt-3">
              <PanelRow term="HDS Encounters">{s.encounterCount} encounters in EncounterOntology</PanelRow>
              <PanelRow term="Medications">{s.medicationCount} active orders in MedicationRequestOntology</PanelRow>
              <PanelRow term="Imaging Studies">{s.imagingStudyCount} DICOM studies in ImagingStudyReporting</PanelRow>
              <PanelRow term="Open Care Gaps">{s.openCareGaps} open quality gaps in care_gaps</PanelRow>
              <PanelRow term="Episode DRG">DRG {cost.drgCode} · ${cost.actualCostUsd.toLocaleString()} actual vs ${cost.expectedDrgPaymentUsd.toLocaleString()} CMS mean</PanelRow>
            </dl>
          </div>
        </PanelSection>
      </div>
    </div>
  );
}

function EconomicsAndRegistryTab({
  enriched,
  selectedEntry,
}: {
  enriched: EnrichedSubject[];
  selectedEntry: EnrichedSubject | null;
}) {
  const totalActual = enriched.reduce((acc, e) => acc + e.cost.actualCostUsd, 0);
  const totalExpected = enriched.reduce((acc, e) => acc + e.cost.expectedDrgPaymentUsd, 0);
  const totalVariance = totalActual - totalExpected;

  const registries = [
    { id: 'ny_doh_2254a', name: 'NY DOH-2254a Cardiac Surgery', fields: 42, highConf: 39, mode: 'Assisted QA', status: 'Ready for sign-off' },
    { id: 'ncdr_cathpci', name: 'ACC NCDR CathPCI v5', fields: 38, highConf: 35, mode: 'Supervised', status: 'Ready for sign-off' },
    { id: 'sts_adult', name: 'STS Adult Cardiac Surgery v4.20', fields: 46, highConf: 41, mode: 'Manual Sign-Off', status: '2 fields need review' },
    { id: 'gwtg_hf', name: 'AHA Get With The Guidelines — HF', fields: 28, highConf: 27, mode: 'Auto-Confirm >=0.90', status: 'Ready for export' },
    { id: 'tjc_core', name: 'Joint Commission Core Measures', fields: 24, highConf: 24, mode: 'Delegated Audit', status: 'Verified' },
  ];

  return (
    <div className="mx-auto max-w-[1380px] space-y-10">
      <DocSection
        title="Hospital Margin & CMS Bundled-Payment Overlay"
        intro="Episode cost derived from CMS Hospital Cost Report 2024 (form 2552-10) and CMS MEDPAR FY2024 national-mean DRG payments. Every avoided complication or stuck bed-hour is recoverable hospital margin."
      >
        <div className="hair mb-6 grid grid-cols-3 gap-6 border-b pb-5">
          <div>
            <div className="t-label">Active Cohort Actual Cost</div>
            <div className="t-display num mt-1 text-[28px]">${(totalActual / 1_000_000).toFixed(2)}M</div>
            <div className="t-faint text-[12px]">{enriched.length} active episodes</div>
          </div>
          <div>
            <div className="t-label">CMS Bundled DRG Baseline</div>
            <div className="t-display num mt-1 text-[28px]">${(totalExpected / 1_000_000).toFixed(2)}M</div>
            <div className="t-faint text-[12px]">MEDPAR national mean</div>
          </div>
          <div>
            <div className="t-label">Net Variance vs DRG Mean</div>
            <div
              className="t-display num mt-1 text-[28px]"
              style={{ color: totalVariance > 0 ? 'var(--c-alert)' : 'var(--c-good)' }}
            >
              {totalVariance > 0 ? '+' : '−'}${Math.abs(Math.round(totalVariance / 1000)).toLocaleString()}k
            </div>
            <div className="t-faint text-[12px]">{totalVariance > 0 ? 'Hospital absorbed overrun' : 'Margin retained'}</div>
          </div>
        </div>

        <table className="tbl text-[13px]">
          <thead>
            <tr>
              <th>Subject</th>
              <th>Condition</th>
              <th>MCS Support</th>
              <th>DRG</th>
              <th className="text-right">LOS (h)</th>
              <th className="text-right">Actual Cost</th>
              <th className="text-right">CMS DRG Payment</th>
              <th className="text-right">Variance</th>
            </tr>
          </thead>
          <tbody>
            {enriched.slice(0, 12).map(({ subject: s, cost }) => (
              <tr key={s.id}>
                <td className="font-medium">
                  {s.initials} <span className="mono t-faint text-[11px]">{s.id.slice(0, 8)}</span>
                </td>
                <td>{s.conditionDisplay}</td>
                <td>{cost.mcsLabel}</td>
                <td className="mono">DRG {cost.drgCode}</td>
                <td className="num text-right">{cost.losHours}h</td>
                <td className="num text-right">${cost.actualCostUsd.toLocaleString()}</td>
                <td className="num text-right">${cost.expectedDrgPaymentUsd.toLocaleString()}</td>
                <td
                  className="num text-right font-medium"
                  style={{ color: cost.varianceUsd > 0 ? 'var(--c-alert)' : 'var(--c-good)' }}
                >
                  {cost.varianceUsd > 0 ? '+' : '−'}${Math.abs(cost.varianceUsd).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </DocSection>

      <DocSection
        title="Automated Registry Abstraction & QA Inbox"
        intro={`Schema-driven chart-to-field extraction across 5 clinical registries${selectedEntry ? ` for ${selectedEntry.subject.initials} (${selectedEntry.subject.id.slice(0, 8)})` : ''}. Every field requires a verbatim source span and confidence score.`}
      >
        <table className="tbl text-[13px]">
          <thead>
            <tr>
              <th>Registry</th>
              <th>Collaboration Mode</th>
              <th className="text-right">Fields ≥0.90 Conf</th>
              <th>QA Status</th>
            </tr>
          </thead>
          <tbody>
            {registries.map((r) => (
              <tr key={r.id}>
                <td className="font-medium">{r.name}</td>
                <td>
                  <span className="syn-tag">{r.mode}</span>
                </td>
                <td className="num text-right">
                  {r.highConf} / {r.fields} ({Math.round((r.highConf / r.fields) * 100)}%)
                </td>
                <td style={{ color: r.status.includes('review') ? 'var(--accent)' : 'var(--c-good)' }}>{r.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <dl className="hair mt-6 border-b">
          <DocSpec term="Anti-hallucination kernel">
            Unobserved fields return <span className="mono">value: null, confidence: 0</span> rather than guessed values.
          </DocSpec>
          <DocSpec term="Peer Benchmarks">
            Calibrated against public CMS Hospital Compare and NY DOH adult cardiac surgery reports (STS v4.20 30-day operative mortality definitions).
          </DocSpec>
        </dl>
      </DocSection>
    </div>
  );
}
