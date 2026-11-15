export const CANONICAL_STAGE_KEYS = [
  "phase_1_workspace",
  "phase_1_base_infra",
  "phase_1_fhir",
  "phase_1_dicom",
  "phase_2_rti_ingest",
  "phase_3_hds_source",
  "phase_2_rti_enrichment",
  "phase_3_hds_pipelines",
  "phase_4_imaging",
  "phase_4_ontology",
  "phase_2_agents",
  "phase_4_agents",
  "phase_5_alerts",
  "phase_6_quality",
  "phase_7_payer_ops",
  "addon_databricks",
  "addon_cardiology",
  "addon_rayfin",
] as const;

export type CanonicalStageKey = typeof CANONICAL_STAGE_KEYS[number];

export const isCanonicalStageKey = (key: string): key is CanonicalStageKey =>
  (CANONICAL_STAGE_KEYS as readonly string[]).includes(key);

export const STAGE_KEY_PATTERNS: Array<{ stageKey: string; patterns: RegExp[] }> = [
  { stageKey: "phase_1_workspace", patterns: [/fabric\s*workspace/i, /phase\s*1a/i] },
  { stageKey: "phase_1_base_infra", patterns: [/base\s*azure\s*infrastructure/i, /azure\s*infrastructure/i, /shared\s*hds\s*infrastructure/i, /emulator\s*infra/i, /phase\s*1b/i] },
  { stageKey: "phase_1_fhir", patterns: [/fhir\s*infrastructure\s*scaffold/i, /fhir\s*service/i, /synthea/i, /phase\s*1c/i] },
  { stageKey: "phase_1_dicom", patterns: [/dicom\s*loader/i, /imagingstudy/i, /phase\s*1d/i] },
  { stageKey: "phase_2_rti_ingest", patterns: [/fabric\s*rti\s*ingest/i, /phase\s*2a/i, /phase\s*2:\s*fabric\s*rti(?!\s*enrichment)/i, /eventhouse/i, /eventstream/i] },
  { stageKey: "phase_3_hds_source", patterns: [/hds\s*source/i, /phase\s*2b/i] },
  { stageKey: "phase_2_rti_enrichment", patterns: [/fabric\s*rti\s*enrichment/i, /phase\s*2c/i, /rti\s*phase\s*2/i, /rti\s*enrichment/i] },
  { stageKey: "phase_3_hds_pipelines", patterns: [/hds\s*pipelines?/i, /dicom\s*shortcut/i, /row\s*gates/i, /phase\s*3a/i] },
  { stageKey: "phase_4_imaging", patterns: [/imaging\s*&\s*reporting/i, /imaging/i, /cohorting/i, /dicom\s*viewer/i, /phase\s*4a/i] },
  { stageKey: "phase_4_ontology", patterns: [/ontology\s*deployment/i, /clinical\s*device\s*ontology/i, /deviceassociation/i, /phase\s*4:\s*ontology(?![_\s-]*aware)/i, /phase\s*4b/i, /^ontology$/i] },
  { stageKey: "phase_2_agents", patterns: [/phase\s*2:\s*data\s*agents/i] },
  { stageKey: "phase_4_agents", patterns: [/ontology-aware\s*(?:clinical\s*)?data\s*agents/i, /phase\s*4:\s*data\s*agents/i, /data\s*agents/i, /patient\s*360/i, /conversational/i, /phase\s*4c/i] },
  { stageKey: "phase_5_alerts", patterns: [/data\s*activator/i, /reflex/i, /clinicalalert(?:activator)?/i, /phase\s*5/i] },
  { stageKey: "phase_6_quality", patterns: [/cms\s*quality/i, /quality\s*measures/i, /population\s*health/i, /scorecard/i, /\bpdc\b/i, /phase\s*6/i] },
  { stageKey: "phase_7_payer_ops", patterns: [/payer\s*rti/i, /claim\s*stream/i, /claim-stream/i, /payer\s*ops/i, /healthcareops(?:agent)?/i, /graph\s*agent/i, /phase\s*7/i] },
  { stageKey: "addon_databricks", patterns: [/^add-on:\s*databricks$/i, /^databricks$/i] },
  { stageKey: "addon_cardiology", patterns: [/add-on:\s*cardiology/i, /\bcardiology\b/i] },
  { stageKey: "addon_rayfin", patterns: [/add-on:\s*rayfin/i, /\brayfin(_apps)?\b/i] },
];

export function getStageKeyForPhase(phaseName: string): string | null {
  if (!phaseName) return null;
  const normalized = phaseName.trim();
  if (isCanonicalStageKey(normalized)) {
    return normalized;
  }
  const addonKey = `addon_${normalized.toLowerCase()}`;
  if (isCanonicalStageKey(addonKey)) {
    return addonKey;
  }
  for (const { stageKey, patterns } of STAGE_KEY_PATTERNS) {
    for (const pat of patterns) {
      if (pat.test(normalized)) {
        return stageKey;
      }
    }
  }
  return null;
}

export interface StageEtaEntry {
  median_minutes?: number;
  sample_count?: number;
}

export interface CalculateEtaParams {
  isRunning: boolean;
  activePhases: Array<{ id?: string; phase: string; status?: string }>;
  stageEtas: Record<string, StageEtaEntry | undefined>;
  elapsedMinutes?: number;
  getStageKey?: (phase: string) => string | null;
  getStepWeightFallback?: (phase: string) => number;
  config?: { skip_ontology?: boolean };
}

export interface CalculateEtaResult {
  etaMinutes: number;
  etaLearnedRuns: number;
}

export function calculateEta({
  isRunning,
  activePhases,
  stageEtas,
  elapsedMinutes = 0,
  getStageKey = getStageKeyForPhase,
  getStepWeightFallback = () => 1,
  config,
}: CalculateEtaParams): CalculateEtaResult {
  if (!isRunning || !activePhases || activePhases.length === 0) {
    return { etaMinutes: 0, etaLearnedRuns: 0 };
  }

  const isAddon = (p: { id?: string; phase: string }): boolean => {
    if (p.id?.startsWith("addon_")) return true;
    if (/^add-on:/i.test(p.phase)) return true;
    const key = getStageKey(p.phase);
    return Boolean(key?.startsWith("addon_"));
  };

  const getAddonKey = (p: { id?: string; phase: string }): string => {
    if (p.id?.startsWith("addon_")) return p.id;
    const key = getStageKey(p.phase);
    if (key?.startsWith("addon_")) return key;
    return p.phase.toLowerCase().trim();
  };

  // Keep only the newest row for each add-on title
  const seenAddonKeys = new Set<string>();
  const deduplicatedPhases: Array<{ id?: string; phase: string; status?: string }> = [];
  for (let i = activePhases.length - 1; i >= 0; i--) {
    const p = activePhases[i];
    if (isAddon(p)) {
      const key = getAddonKey(p);
      if (seenAddonKeys.has(key)) {
        continue;
      }
      seenAddonKeys.add(key);
    }
    deduplicatedPhases.unshift(p);
  }

  const completedBeforeActions = deduplicatedPhases.filter((p) => p.status === "succeeded" || p.status === "skipped").length;
  const remainingWorkPhases = deduplicatedPhases.filter((p) => p.status !== "succeeded" && p.status !== "skipped" && p.status !== "failed");
  const completedOrPartial = completedBeforeActions + (remainingWorkPhases.some((p) => p.status === "running") ? 0.35 : 0);
  const remainingCount = Math.max(remainingWorkPhases.length - (remainingWorkPhases.some((p) => p.status === "running") ? 0.35 : 0), 0);
  const fallbackEtaMinutes = isRunning && elapsedMinutes > 0 && completedOrPartial > 0
    ? Math.min(180, Math.max(1, Math.round((remainingCount / completedOrPartial) * elapsedMinutes)))
    : 0;

  let totalRemaining = 0;
  const learnedRunsList: number[] = [];
  let hasLearnedStage = false;

  for (const p of deduplicatedPhases) {
    if (p.status === "succeeded" || p.status === "skipped" || p.status === "failed") {
      continue;
    }
    let stageKey = p.id && isCanonicalStageKey(p.id) ? p.id : getStageKey(p.phase);
    if ((stageKey === "phase_4_agents" || p.id === "phase_4_agents" || /4c\b/i.test(p.phase)) && config?.skip_ontology) {
      stageKey = "phase_2_agents";
    }
    const entry = stageKey ? stageEtas[stageKey] : undefined;
    let stageDurationMinutes: number;

    if (entry && typeof entry.median_minutes === "number" && (entry.sample_count ?? 0) >= 3 && !isNaN(entry.median_minutes)) {
      stageDurationMinutes = Math.max(0.5, entry.median_minutes);
      learnedRunsList.push(entry.sample_count ?? 0);
      hasLearnedStage = true;
    } else {
      stageDurationMinutes = getStepWeightFallback(p.phase);
    }

    if (p.status === "running") {
      totalRemaining += Math.max(0.2, stageDurationMinutes * 0.65);
    } else {
      // Pending stages add their full medians / weights
      totalRemaining += stageDurationMinutes;
    }
  }

  if (hasLearnedStage && totalRemaining > 0) {
    const calculatedEta = Math.min(180, Math.max(1, Math.round(totalRemaining)));
    const maxRuns = learnedRunsList.length > 0 ? Math.max(...learnedRunsList) : 0;
    return { etaMinutes: calculatedEta, etaLearnedRuns: maxRuns };
  }

  return { etaMinutes: fallbackEtaMinutes, etaLearnedRuns: 0 };
}
