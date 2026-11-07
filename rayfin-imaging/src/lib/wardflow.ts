/**
 * WardFlow / Caldova Cardiology domain engine for the Rayfin Fabric app.
 *
 * Implements:
 * - Pure multi-measure deterioration scoring (SCAI 2022 + CardShock 2015 + NEWS2 + INTERMACS citations)
 * - Bazett rate-corrected ECG waveform synthesis (milliseconds domain)
 * - Stevenson 2x2 hemodynamic quadrant classification (Warm/Cold x Dry/Wet)
 * - 7-Beat governed agentic operations loop (Change -> Notice -> Decide -> Approve -> Act -> Adapt -> Prove)
 * - CMS Hospital Cost Report 2024 & MEDPAR DRG episode economics
 * - Multi-registry QA abstraction drafts (NY DOH-2254a, NCDR CathPCI, STS Adult Cardiac, GWTG-HF, TJC)
 *
 * SYNTHETIC DATA ONLY. Not a medical device and not for clinical use.
 */
import type { WardFlowSubject } from '@/lib/api';

export const SCORING_VERSION = 'caldova-deterioration-1.0.0';
export type Stage = 'stable' | 'at-risk' | 'concerning' | 'critical';
export type ScaiStage = 'A' | 'B' | 'C' | 'D' | 'E';

export interface MeasureSpec {
  key: string;
  label: string;
  unit: string;
  weight: number;
  normal: number;
  concerning: number;
  direction: 'higher-is-worse' | 'lower-is-worse';
  citation: string;
}

export const DEFAULT_MEASURES: MeasureSpec[] = [
  {
    key: 'lactate',
    label: 'Lactate',
    unit: 'mmol/L',
    weight: 0.30,
    normal: 1.0,
    concerning: 4.0,
    direction: 'higher-is-worse',
    citation: 'SCAI 2022 CSWG consensus (Kapur et al., JACC 2022;80:185-198) & CardShock (Harjola et al., EJHF 2015;17:501-509): lactate >= 4.0 mmol/L marks severe hypoperfusion.',
  },
  {
    key: 'map',
    label: 'Mean arterial pressure',
    unit: 'mmHg',
    weight: 0.25,
    normal: 85,
    concerning: 60,
    direction: 'lower-is-worse',
    citation: 'SCAI 2022 CSWG consensus (Kapur et al., JACC 2022;80:185-198): persistent hypotension with MAP < 60 mmHg defines classic/deteriorating cardiogenic shock.',
  },
  {
    key: 'pulseRate',
    label: 'Pulse rate',
    unit: '/min',
    weight: 0.15,
    normal: 75,
    concerning: 130,
    direction: 'higher-is-worse',
    citation: 'NEWS2 (Royal College of Physicians, 2017) & SCAI Stage B tachycardia criterion: heart/pulse rate > 130 /min scores maximum acute illness points (3 pts).',
  },
  {
    key: 'deviceFlow',
    label: 'Device flow index',
    unit: '%',
    weight: 0.20,
    normal: 100,
    concerning: 60,
    direction: 'lower-is-worse',
    citation: 'ISHLT/INTERMACS MCS surveillance & SHOCK Trial Registry CPO correlate (Fincke et al., JACC 2004;44:340-348): >= 40% reduction from baseline pump flow index.',
  },
  {
    key: 'spo2',
    label: 'Oxygen saturation',
    unit: '%',
    weight: 0.10,
    normal: 97,
    concerning: 88,
    direction: 'lower-is-worse',
    citation: 'NEWS2 SpO2 Scale 1/2 (Royal College of Physicians, 2017): SpO2 <= 88% represents severe hypoxemia.',
  },
];

export interface DerivedScore {
  subjectId: string;
  score: number | null;
  stage: Stage | null;
  scai: ScaiStage;
  confidence: 'complete' | 'partial' | 'none';
  criteriaMet: string[];
  contributions: Record<string, number>;
  missingInputs: string[];
  scoringVersion: string;
}

function normaliseMeasure(value: number, spec: MeasureSpec): number {
  const span = spec.concerning - spec.normal;
  if (span === 0) return 0;
  const raw = (value - spec.normal) / span;
  return Math.max(0, Math.min(1, raw));
}

export function computeDeteriorationScore(
  subject: Pick<WardFlowSubject, 'id' | 'observations' | 'deviceKind'>,
  measures: MeasureSpec[] = DEFAULT_MEASURES,
): DerivedScore {
  const contributions: Record<string, number> = {};
  const criteriaMet: string[] = [];
  const missingInputs: string[] = [];

  let weighted = 0;
  let availableWeight = 0;

  for (const spec of measures) {
    const value = subject.observations[spec.key];
    if (value === null || value === undefined || !Number.isFinite(value)) {
      missingInputs.push(spec.key);
      continue;
    }
    const n = normaliseMeasure(value, spec);
    const contribution = n * spec.weight * 100;
    contributions[spec.key] = Number(contribution.toFixed(2));
    weighted += contribution;
    availableWeight += spec.weight;

    if (n >= 0.75) {
      criteriaMet.push(
        `${spec.label} ${value} ${spec.unit} is at or beyond the demonstration concerning threshold (${spec.concerning} ${spec.unit})`,
      );
    }
  }

  if (availableWeight === 0) {
    return {
      subjectId: subject.id,
      score: null,
      stage: null,
      scai: 'A',
      confidence: 'none',
      criteriaMet: [],
      contributions: {},
      missingInputs,
      scoringVersion: SCORING_VERSION,
    };
  }

  const score = Math.round((weighted / availableWeight) * 10) / 10;
  const stage: Stage = score >= 80 ? 'critical' : score >= 60 ? 'concerning' : score >= 40 ? 'at-risk' : 'stable';
  const lac = subject.observations.lactate ?? 1.2;
  const map = subject.observations.map ?? 80;
  const hasMcs = !!subject.deviceKind;
  const scai: ScaiStage =
    lac > 8 || (score >= 88 && hasMcs) ? 'E'
    : score >= 78 || (lac >= 4.0 && map < 62) ? 'D'
    : score >= 58 || lac >= 2.2 || map < 68 ? 'C'
    : score >= 38 || map < 75 ? 'B'
    : 'A';

  return {
    subjectId: subject.id,
    score,
    stage,
    scai,
    confidence: missingInputs.length === 0 ? 'complete' : 'partial',
    criteriaMet,
    contributions,
    missingInputs,
    scoringVersion: SCORING_VERSION,
  };
}

/**
 * Bazett rate-corrected ECG waveform synthesis in the millisecond domain.
 * Stylised demonstration waveform only; never diagnostic.
 */
const SAMPLE_RATE = 250;
const PR_MS = 160;
const QRS_MS = 90;
const QTC_MS = 400;

export function synthesiseEcg(
  heartRate: number | null | undefined,
  stage: Stage | null,
  startMs = 0,
  windowMs = 3600,
): number[] {
  if (heartRate === null || heartRate === undefined || !Number.isFinite(heartRate) || heartRate <= 0) {
    return [];
  }
  const hr = Math.min(220, Math.max(25, heartRate));
  const amp = stage === 'critical' ? 0.76 : stage === 'concerning' ? 0.86 : stage === 'at-risk' ? 0.94 : 1.0;
  const rr = 60000 / hr;
  const qt = QTC_MS * Math.sqrt(rr / 1000);
  const needed = PR_MS + qt;
  const available = rr * 0.9;
  const k = needed > available ? available / needed : 1;

  const count = Math.round((windowMs / 1000) * SAMPLE_RATE);
  const out: number[] = new Array(count);

  const rAt = PR_MS;
  const qAt = rAt - QRS_MS * 0.35;
  const sAt = rAt + QRS_MS * 0.45;
  const tAt = qAt + qt * 0.62;

  const bump = (t: number, cMs: number, wMs: number, h: number) =>
    h * Math.exp(-((t - cMs * k) ** 2) / (2 * (wMs * k) ** 2));

  for (let i = 0; i < count; i++) {
    const tMs = startMs + (i / SAMPLE_RATE) * 1000;
    const c = ((tMs % rr) + rr) % rr;
    out[i] =
      (bump(c, 28, 22, 0.13) +
        bump(c, qAt, QRS_MS * 0.09, -0.09) +
        bump(c, rAt, QRS_MS * 0.11, 1.0) +
        bump(c, sAt, QRS_MS * 0.12, -0.22) +
        bump(c, tAt, qt * 0.13, 0.24)) *
      amp;
  }
  return out;
}

/** Stevenson 2x2 hemodynamic profile (Warm/Cold x Dry/Wet). */
export interface StevensonProfile {
  quadrant: 'Warm-Dry' | 'Warm-Wet' | 'Cold-Dry' | 'Cold-Wet';
  subtitle: string;
  perfusion: number; // -1 cold .. +1 warm
  congestion: number; // -1 dry .. +1 wet
}

export function computeStevenson(subject: WardFlowSubject, score: DerivedScore): StevensonProfile {
  const lac = subject.observations.lactate ?? 1.3;
  const map = subject.observations.map ?? 78;
  const pressors = score.stage === 'critical' ? 2 : score.stage === 'concerning' ? 1 : 0;
  const lacScore = Math.max(0, Math.min(1, (lac - 1) / 5));
  const mapScore = Math.max(0, Math.min(1, (88 - map) / 30));
  const coldness = lacScore * 0.55 + mapScore * 0.3 + (pressors / 3) * 0.15;
  const perfusion = Number((1 - 2 * coldness).toFixed(2));

  const hf = /heart failure|shock|cardiomyopathy/i.test(subject.conditionDisplay) ? 0.25 : 0.05;
  const stageWet = score.stage === 'critical' ? 0.65 : score.stage === 'concerning' ? 0.45 : score.stage === 'at-risk' ? 0.25 : 0.1;
  const wetness = Math.min(1, hf + stageWet);
  const congestion = Number((-1 + 2 * wetness).toFixed(2));

  const warm = perfusion >= 0;
  const wet = congestion >= 0;
  const quadrant = warm && !wet ? 'Warm-Dry' : warm && wet ? 'Warm-Wet' : !warm && !wet ? 'Cold-Dry' : 'Cold-Wet';
  const subtitle =
    quadrant === 'Warm-Dry' ? 'Compensated perfusion'
    : quadrant === 'Warm-Wet' ? 'Volume overloaded · diuresis target'
    : quadrant === 'Cold-Dry' ? 'Hypoperfused · euvolemic'
    : 'Cardiogenic shock · hypoperfused + congested';
  return { quadrant, subtitle, perfusion, congestion };
}

/** Episode cost breakdown anchored to public CMS Hospital Cost Report 2024 & MEDPAR DRG rates. */
export interface EpisodeCostSummary {
  drgCode: string;
  drgLabel: string;
  losHours: number;
  actualCostUsd: number;
  expectedDrgPaymentUsd: number;
  varianceUsd: number;
  mcsLabel: string;
}

export function computeEpisodeCost(subject: WardFlowSubject, score: DerivedScore, index: number): EpisodeCostSummary {
  const losHours = 48 + ((index * 19) % 120);
  const days = losHours / 24;
  const hasVad = /ventricular assist/i.test(subject.deviceKind ?? '');
  const hasBalloon = /balloon/i.test(subject.deviceKind ?? '');
  const mcsLabel = hasVad ? 'LVAD / Impella' : hasBalloon ? 'IABP' : subject.deviceKind ? 'Cardiac Monitor' : 'None';

  const drgCode = hasVad ? '001' : hasBalloon ? '215' : score.stage === 'critical' || score.stage === 'concerning' ? '291' : '292';
  const drgMap: Record<string, { label: string; payment: number }> = {
    '001': { label: 'Heart transplant or implant of heart assist system w/ MCC', payment: 415000 },
    '215': { label: 'Other heart assist system implant', payment: 285000 },
    '291': { label: 'Heart failure & shock w/ MCC', payment: 14600 },
    '292': { label: 'Heart failure & shock w/ CC', payment: 9300 },
  };
  const drg = drgMap[drgCode];
  const roomPerDay = subject.careSetting === 'inpatient' ? 9200 : subject.careSetting === 'outpatient' ? 2300 : 1400;
  const deviceCost = hasVad ? 195000 + days * 1200 : hasBalloon ? 4500 + days * 800 : 0;
  const ancillary = days * (480 + 380 + (score.stage === 'critical' ? 640 : 0));
  const actualCostUsd = Math.round(days * roomPerDay + deviceCost + ancillary);
  const expectedDrgPaymentUsd = drg.payment;
  return {
    drgCode,
    drgLabel: drg.label,
    losHours,
    actualCostUsd,
    expectedDrgPaymentUsd,
    varianceUsd: actualCostUsd - expectedDrgPaymentUsd,
    mcsLabel,
  };
}

export const AGENT_SYSTEM_PROMPT = `You are a clinical operations triage agent for a cardiology service.
DRAFT an outreach action for a clinician to approve, using the supplied synthetic
subject, transition and derived measures. This is a demonstration, not medical
advice or a clinically validated triage protocol.

You do NOT contact anyone. You prepare; a clinician approves. Never state or imply
that contact, notification or treatment has already happened.

DEMONSTRATION routing policy (the application's chosen workflow, not treatment):
- critical + inpatient: escalate-in-person. Request immediate bedside review by
  the attending team; do not substitute generic outreach for that review.
- critical + outpatient or home-monitored: clinical-outreach. Request urgent
  clinician review/contact without prescribing treatment or asserting delivery.
- concerning: clinical-outreach, including incomplete telemetry. Request review
  and verification of missing readings; missing inputs do not establish stability.
- at-risk or stable: monitor. Describe continued surveillance without inventing
  an outreach requirement.`;

export interface TriageEvaluationDraft {
  runId: string;
  subjectId: string;
  initials: string;
  careSetting: string;
  condition: string;
  beforeScore: number;
  afterScore: number;
  beforeStage: Stage;
  afterStage: Stage;
  trippedObservations: Record<string, number | null>;
  recommendedAction: 'monitor' | 'clinical-outreach' | 'escalate-in-person';
  conclusion: string;
  draft: string;
  evidence: string[];
  confidence: number;
  model: string;
  runtimeTokens: number;
  beats: Array<{ beat: number; name: string; status: 'done' | 'halted' | 'skipped'; detail: string; at: string }>;
}

/**
 * Executes Beats 1–4 of the governed WardFlow cardiology loop for a selected subject:
 * injects a correlated physiological deterioration, recomputes the grounded score,
 * drafts the clinician-gated recommendation, and halts at Beat 4 awaiting human review.
 */
export function buildGovernedTriageDraft(subject: WardFlowSubject, actorName: string): TriageEvaluationDraft {
  const nowIso = new Date().toISOString();
  const before = computeDeteriorationScore(subject);
  const beforeScore = before.score ?? 28;
  const beforeStage = before.stage ?? 'stable';

  const curLac = subject.observations.lactate ?? 1.4;
  const curMap = subject.observations.map ?? 78;
  const curPr = subject.observations.pulseRate ?? 82;
  const curSpo2 = subject.observations.spo2 ?? 96;
  const curFlow = subject.observations.deviceFlow ?? (subject.deviceKind ? 92 : null);

  const trippedObservations: Record<string, number | null> = {
    lactate: Number(Math.max(curLac + 2.6, 4.3).toFixed(2)),
    map: Number(Math.min(curMap - 18, 57).toFixed(1)),
    pulseRate: Math.round(Math.max(curPr + 34, 128)),
    spo2: Number(Math.min(curSpo2 - 6, 89).toFixed(1)),
    deviceFlow: curFlow !== null ? Number(Math.min(curFlow - 28, 58).toFixed(1)) : null,
  };

  const after = computeDeteriorationScore({
    id: subject.id,
    deviceKind: subject.deviceKind,
    observations: trippedObservations,
  });
  const afterScore = after.score ?? 82;
  const afterStage = after.stage ?? 'critical';

  const recommendedAction: TriageEvaluationDraft['recommendedAction'] =
    afterStage === 'critical' && subject.careSetting === 'inpatient'
      ? 'escalate-in-person'
      : afterStage === 'critical' || afterStage === 'concerning'
        ? 'clinical-outreach'
        : 'monitor';

  const reviewerRole = subject.attendingRole ?? 'attending cardiologist';
  const evidence = [
    `Composite deterioration score moved ${beforeScore} (${beforeStage}) → ${afterScore} (${afterStage}, SCAI ${after.scai})`,
    `Lactate ${trippedObservations.lactate} mmol/L, MAP ${trippedObservations.map} mmHg, PR ${trippedObservations.pulseRate} /min, SpO2 ${trippedObservations.spo2}%`,
    ...(trippedObservations.deviceFlow !== null ? [`Device flow index ${trippedObservations.deviceFlow}% (${subject.deviceKind})`] : []),
    ...after.criteriaMet,
  ];

  const conclusion = `${subject.id} (${subject.initials}, ${subject.careSetting}) crossed from ${beforeStage} (${beforeScore}) to ${afterStage} (${afterScore}); ${recommendedAction} prepared for ${reviewerRole} review.`;
  const draft = `${subject.id} (${subject.initials}, ${subject.conditionDisplay}): score rose ${beforeScore} → ${afterScore} (${afterStage}, lactate ${trippedObservations.lactate} mmol/L, MAP ${trippedObservations.map} mmHg). Proposed action: ${recommendedAction} by ${reviewerRole}. Synthetic demonstration draft awaiting clinician approval; no contact has been made.`;

  const runId = `run_${Date.now().toString(36)}_${subject.id.slice(0, 6)}`;
  const beats: TriageEvaluationDraft['beats'] = [
    {
      beat: 1,
      name: 'Change injected',
      status: 'done',
      detail: `lactate ${curLac} → ${trippedObservations.lactate} mmol/L · MAP ${curMap} → ${trippedObservations.map} mmHg · PR ${curPr} → ${trippedObservations.pulseRate} /min`,
      at: nowIso,
    },
    {
      beat: 2,
      name: 'Stage transition noticed',
      status: 'done',
      detail: `Rule rule.deterioration.stage-transition fired: ${beforeStage} (${beforeScore}) → ${afterStage} (${afterScore}, SCAI ${after.scai})`,
      at: nowIso,
    },
    {
      beat: 3,
      name: 'Triage decision drafted',
      status: 'done',
      detail: `Prepared ${recommendedAction} draft grounded in ${evidence.length} observed measures (confidence ${after.confidence === 'complete' ? '0.94' : '0.82'})`,
      at: nowIso,
    },
    {
      beat: 4,
      name: 'Halted at human approval gate',
      status: 'halted',
      detail: `Awaiting ${actorName} (${reviewerRole}) approval in Rayfin Fabric SQL. Nothing has been dispatched.`,
      at: nowIso,
    },
  ];

  return {
    runId,
    subjectId: subject.id,
    initials: subject.initials,
    careSetting: subject.careSetting,
    condition: subject.conditionDisplay,
    beforeScore,
    afterScore,
    beforeStage,
    afterStage,
    trippedObservations,
    recommendedAction,
    conclusion,
    draft,
    evidence,
    confidence: after.confidence === 'complete' ? 0.94 : 0.82,
    model: 'gpt-5.6-luna (governed-rayfin-triage)',
    runtimeTokens: 640,
    beats,
  };
}
