import { authenticated, date, decimal, entity, int, set, text, uuid } from '@microsoft/rayfin-core';

/**
 * A governed WardFlow / Caldova cardiology triage review and human-approval record.
 * Stored in the Rayfin Fabric SQL database so every clinician sees pending drafts,
 * approvals, rejections, and audit history without requiring an Azure Container App.
 */
@entity()
@authenticated('*')
export class WardFlowTriageReview {
  @uuid() id!: string;
  @text({ min: 1, max: 64 }) runId!: string;
  @text({ min: 1, max: 64 }) subjectId!: string;
  @text({ min: 1, max: 32 }) initials!: string;
  @text({ min: 1, max: 32 }) careSetting!: string;
  @text({ min: 1, max: 160 }) condition!: string;
  @decimal({ precision: 6, scale: 2 }) score!: number;
  @text({ min: 1, max: 32 }) stage!: string;
  @set('monitor', 'clinical-outreach', 'escalate-in-person')
  recommendedAction!: 'monitor' | 'clinical-outreach' | 'escalate-in-person';
  @text({ min: 1, max: 500 }) conclusion!: string;
  @text({ min: 1, max: 1000 }) draft!: string;
  @text({ min: 1, max: 1000 }) evidenceJson!: string;
  @decimal({ precision: 5, scale: 3 }) confidence!: number;
  @text({ min: 1, max: 64 }) model!: string;
  @set('pending', 'approved', 'rejected', 'monitored')
  approvalState!: 'pending' | 'approved' | 'rejected' | 'monitored';
  @text({ max: 128 }) requestedBy!: string;
  @date() requestedAt!: Date;
  @text({ max: 128, optional: true }) approverId?: string;
  @date({ optional: true }) resolvedAt?: Date;
  @text({ max: 500, optional: true }) resolutionNote?: string;
  @int() runtimeTokens!: number;
}
