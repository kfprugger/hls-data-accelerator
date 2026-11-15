import fs from "node:fs";
import path from "node:path";
import { describe, it, expect } from "vitest";
import {
  getStageKeyForPhase,
  calculateEta,
  CANONICAL_STAGE_KEYS,
  type StageEtaEntry,
} from "./stageMapping";

describe("stageMapping - getStageKeyForPhase", () => {
  it("does not map Synthetic FHIR Demo Enrichment to a stage key (N-1)", () => {
    expect(getStageKeyForPhase("Synthetic FHIR Demo Enrichment")).toBeNull();
  });

  it("does not map Phase 1: FHIR $export (catch-up) to a stage key (N-1)", () => {
    expect(getStageKeyForPhase("Phase 1: FHIR $export (catch-up)")).toBeNull();
  });

  it("does not map Databricks: Preserve FHIR export to a stage key (N-1)", () => {
    expect(getStageKeyForPhase("Databricks: Preserve FHIR export")).toBeNull();
  });

  it("does not match bare enrichment (R-5)", () => {
    expect(getStageKeyForPhase("enrichment")).toBeNull();
  });

  it("reconciles Phase 2: Fabric RTI to phase_2_rti_ingest (R-5)", () => {
    expect(getStageKeyForPhase("Phase 2: Fabric RTI")).toBe("phase_2_rti_ingest");
    expect(getStageKeyForPhase("Phase 2: Fabric RTI Ingest")).toBe("phase_2_rti_ingest");
  });

  it("reconciles Shared HDS Infrastructure to phase_1_base_infra (R-5)", () => {
    expect(getStageKeyForPhase("Shared HDS Infrastructure")).toBe("phase_1_base_infra");
    expect(getStageKeyForPhase("Phase 1: Shared HDS Infrastructure")).toBe("phase_1_base_infra");
  });

  it("reconciles FHIR Infrastructure Scaffold to phase_1_fhir (R-5)", () => {
    expect(getStageKeyForPhase("FHIR Infrastructure Scaffold")).toBe("phase_1_fhir");
    expect(getStageKeyForPhase("Phase 1: FHIR Infrastructure Scaffold")).toBe("phase_1_fhir");
  });

  it("distinguishes Phase 2 Data Agents from Phase 4 Ontology-Aware Data Agents (R-6)", () => {
    expect(getStageKeyForPhase("Phase 2: Data Agents")).toBe("phase_2_agents");
    expect(getStageKeyForPhase("Phase 4: Ontology-Aware Data Agents")).toBe("phase_4_agents");
    expect(getStageKeyForPhase("Phase 4: Data Agents")).toBe("phase_4_agents");
  });

  it("maps all canonical stage keys to themselves", () => {
    for (const key of CANONICAL_STAGE_KEYS) {
      expect(getStageKeyForPhase(key)).toBe(key);
    }
  });

  it("maps add-ons accurately", () => {
    expect(getStageKeyForPhase("Add-on: Databricks")).toBe("addon_databricks");
    expect(getStageKeyForPhase("Add-on: Cardiology")).toBe("addon_cardiology");
    expect(getStageKeyForPhase("Add-on: Rayfin")).toBe("addon_rayfin");
    expect(getStageKeyForPhase("databricks")).toBe("addon_databricks");
    expect(getStageKeyForPhase("cardiology")).toBe("addon_cardiology");
    expect(getStageKeyForPhase("rayfin")).toBe("addon_rayfin");
  });
});

describe("stageMapping - calculateEta (R-7)", () => {
  it("returns zero when not running", () => {
    const res = calculateEta({
      isRunning: false,
      activePhases: [{ phase: "Phase 1: Fabric Workspace", status: "running" }],
      stageEtas: {},
    });
    expect(res.etaMinutes).toBe(0);
    expect(res.etaLearnedRuns).toBe(0);
  });

  it("accumulates medians of pending stages in addition to running stage", () => {
    const stageEtas: Record<string, StageEtaEntry> = {
      phase_1_workspace: { median_minutes: 2.0, sample_count: 5 },
      phase_1_base_infra: { median_minutes: 10.0, sample_count: 5 },
      phase_1_fhir: { median_minutes: 20.0, sample_count: 8 },
    };

    const activePhases = [
      { phase: "Phase 1: Fabric Workspace", status: "succeeded" },
      { phase: "Phase 1: Base Azure Infrastructure", status: "running" },
      { phase: "Phase 1: FHIR Service + Synthea + Loader", status: "pending" },
    ];

    // Running phase: phase_1_base_infra (median 10.0 min) -> 10.0 * 0.65 = 6.5 min
    // Pending phase: phase_1_fhir (median 20.0 min) -> 20.0 min
    // Succeeded phase: ignored
    // Total remaining = 6.5 + 20.0 = 26.5 min -> rounded to 27 min
    const res = calculateEta({
      isRunning: true,
      activePhases,
      stageEtas,
      elapsedMinutes: 5,
    });

    expect(res.etaMinutes).toBe(27);
    expect(res.etaLearnedRuns).toBe(8);
  });

  it("uses step weight fallback for pending stages without learned samples", () => {
    const stageEtas: Record<string, StageEtaEntry> = {
      phase_1_workspace: { median_minutes: 2.0, sample_count: 5 },
    };

    const activePhases = [
      { phase: "Phase 1: Fabric Workspace", status: "running" },
      { phase: "Custom Step Without Etas", status: "pending" },
    ];

    const fallbackWeights: Record<string, number> = {
      "Custom Step Without Etas": 15,
    };

    const res = calculateEta({
      isRunning: true,
      activePhases,
      stageEtas,
      elapsedMinutes: 1,
      getStepWeightFallback: (phase) => fallbackWeights[phase] ?? 5,
    });

    // Running: 2.0 * 0.65 = 1.3 min
    // Pending: fallback weight 15 min
    // Total = 16.3 min -> 16 min
    expect(res.etaMinutes).toBe(16);
    expect(res.etaLearnedRuns).toBe(5);
  });

  it("uses learned phase_4_imaging value for the 4a imaging template row (N-3)", () => {
    const activePhases = [
      { id: "phase_4_imaging", phase: "4a. Semantic Intelligence & UX: Custom SWA Viewer & Direct Lake", status: "running" },
    ];
    const stageEtas = {
      phase_4_imaging: { median_minutes: 30, sample_count: 5 },
    };
    const res = calculateEta({
      isRunning: true,
      activePhases,
      stageEtas,
      elapsedMinutes: 5,
      getStageKey: getStageKeyForPhase,
      getStepWeightFallback: () => 10,
    });
    // Learned median 30 min (running -> 30 * 0.65 = 19.5 -> rounded to 20):
    expect(res.etaLearnedRuns).toBe(5);
    expect(res.etaMinutes).toBe(20);
  });

  it("selects phase_4_agents or phase_2_agents median for 4c row based on skip_ontology (F-2)", () => {
    const activePhases = [
      { id: "phase_4_agents", phase: "4c. Semantic Intelligence & UX: Conversational Data Agents", status: "pending" },
    ];
    const stageEtas = {
      phase_4_agents: { median_minutes: 2, sample_count: 4 },
      phase_2_agents: { median_minutes: 3, sample_count: 4 },
    };
    const normalRes = calculateEta({
      isRunning: true,
      activePhases,
      stageEtas,
      elapsedMinutes: 0,
      getStageKey: getStageKeyForPhase,
      getStepWeightFallback: () => 1,
    });
    // normal run selects phase_4_agents only (2 min, not 5 min)
    expect(normalRes.etaMinutes).toBe(2);
    expect(normalRes.etaLearnedRuns).toBe(4);

    const skipOntologyRes = calculateEta({
      isRunning: true,
      activePhases,
      stageEtas,
      elapsedMinutes: 0,
      getStageKey: getStageKeyForPhase,
      getStepWeightFallback: () => 1,
      config: { skip_ontology: true },
    });
    // skip-ontology run selects phase_2_agents only (3 min, not 5 min)
    expect(skipOntologyRes.etaMinutes).toBe(3);
    expect(skipOntologyRes.etaLearnedRuns).toBe(4);
  });

  it("computes ETA for add-on running row (N-2)", () => {
    const activePhases = [
      { phase: "1a. Data Fabric Foundation: Fabric Workspace", status: "succeeded" },
      { phase: "Add-on: Databricks", status: "running" },
    ];
    const stageEtas = {
      addon_databricks: { median_minutes: 40, sample_count: 3 },
    };
    const res = calculateEta({
      isRunning: true,
      activePhases,
      stageEtas,
      elapsedMinutes: 5,
      getStageKey: getStageKeyForPhase,
      getStepWeightFallback: () => 15,
    });
    // 40 * 0.65 = 26 min
    expect(res.etaMinutes).toBe(26);
    expect(res.etaLearnedRuns).toBe(3);
  });

  it("ignores failed add-on row and keeps only newest add-on row (F-1: S2 and S3)", () => {
    const stageEtas = {
      addon_databricks: { median_minutes: 40, sample_count: 5 },
      addon_rayfin: { median_minutes: 20, sample_count: 5 },
    };

    // S3: Databricks failed, Rayfin running (20m * 0.65 = 13m)
    const s3Phases = [
      { phase: "Add-on: Databricks", status: "failed" },
      { phase: "Add-on: Rayfin", status: "running" },
    ];
    const s3Res = calculateEta({
      isRunning: true,
      activePhases: s3Phases,
      stageEtas,
      elapsedMinutes: 60,
    });
    expect(s3Res.etaMinutes).toBe(13);

    // S2: old failed Databricks row + new running Databricks row (40m * 0.65 = 26m)
    const s2Phases = [
      { phase: "Add-on: Databricks", status: "failed" },
      { phase: "Add-on: Databricks", status: "running" },
    ];
    const s2Res = calculateEta({
      isRunning: true,
      activePhases: s2Phases,
      stageEtas,
      elapsedMinutes: 60,
    });
    expect(s2Res.etaMinutes).toBe(26);
  });

  it("calculates ETA for 4c pending under skip-ontology and normal configurations (F-2)", () => {
    const stageEtas = {
      phase_4_agents: { median_minutes: 3, sample_count: 5 },
      phase_2_agents: { median_minutes: 2, sample_count: 5 },
    };
    const activePhases = [
      { id: "phase_4_agents", phase: "4c. Semantic Intelligence & UX: Conversational Data Agents", status: "pending" },
    ];

    const skipRes = calculateEta({
      isRunning: true,
      activePhases,
      stageEtas,
      elapsedMinutes: 60,
      config: { skip_ontology: true },
    });
    expect(skipRes.etaMinutes).toBe(2);

    const normalRes = calculateEta({
      isRunning: true,
      activePhases,
      stageEtas,
      elapsedMinutes: 60,
      config: { skip_ontology: false },
    });
    expect(normalRes.etaMinutes).toBe(3);
  });

  it("includes queued add-ons in ETA calculation (F-3)", () => {
    const stageEtas = {
      addon_databricks: { median_minutes: 40, sample_count: 5 },
      addon_rayfin: { median_minutes: 20, sample_count: 5 },
      addon_cardiology: { median_minutes: 15, sample_count: 5 },
    };
    // Databricks running + Rayfin and Cardiology queued as pending
    const activePhases = [
      { phase: "Add-on: Databricks", status: "running" },
      { phase: "Add-on: Rayfin", status: "pending" },
      { phase: "Add-on: Cardiology", status: "pending" },
    ];
    const res = calculateEta({
      isRunning: true,
      activePhases,
      stageEtas,
      elapsedMinutes: 60,
    });
    // 40 * 0.65 (26) + 20 + 15 = 61 min
    expect(res.etaMinutes).toBe(61);
    expect(res.etaLearnedRuns).toBe(5);
  });
});

describe("stageMapping - shared fixture: stage_title_keys.json (N-5, F-4)", () => {
  const fixturePath = path.resolve(__dirname, "../../orchestrator/tests/fixtures/stage_title_keys.json");
  const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf-8")) as Array<{ title: string; key: string | null; emitted?: boolean }>;

  it.each(fixture)("maps '$title' to '$key' (emitted=$emitted)", ({ title, key }) => {
    expect(getStageKeyForPhase(title)).toBe(key);
  });

  it("covers both emitted titles and pattern probes (F-4)", () => {
    const emitted = fixture.filter((item) => item.emitted === true);
    const probes = fixture.filter((item) => item.emitted === false);
    expect(emitted.length).toBe(28);
    expect(probes.length).toBe(89);
    expect(fixture.length).toBe(117);
  });
});
