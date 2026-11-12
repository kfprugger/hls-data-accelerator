import { useCallback, useEffect, useState } from 'react';

import type { WardFlowTriageReview } from '../../rayfin/data/WardFlowTriageReview';
import { useAuth } from '@/hooks/AuthContext';
import { LOCAL_DATA } from '@/lib/localMode';
import type { TriageEvaluationDraft } from '@/lib/wardflow';
import { getRayfinClient } from '@/services/rayfin/RayfinClientService';

export type ReviewRow = Pick<
  WardFlowTriageReview,
  | 'id'
  | 'runId'
  | 'subjectId'
  | 'initials'
  | 'careSetting'
  | 'condition'
  | 'score'
  | 'stage'
  | 'recommendedAction'
  | 'conclusion'
  | 'draft'
  | 'evidenceJson'
  | 'confidence'
  | 'model'
  | 'approvalState'
  | 'requestedBy'
  | 'requestedAt'
  | 'approverId'
  | 'resolvedAt'
  | 'resolutionNote'
  | 'runtimeTokens'
>;

const FIELDS = [
  'id',
  'runId',
  'subjectId',
  'initials',
  'careSetting',
  'condition',
  'score',
  'stage',
  'recommendedAction',
  'conclusion',
  'draft',
  'evidenceJson',
  'confidence',
  'model',
  'approvalState',
  'requestedBy',
  'requestedAt',
  'approverId',
  'resolvedAt',
  'resolutionNote',
  'runtimeTokens',
] as const;

const LOCAL_STORAGE_KEY = 'wardflow.triageReviews.v1';

function readLocalReviews(): ReviewRow[] {
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ReviewRow[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeLocalReviews(rows: ReviewRow[]): void {
  try {
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(rows));
  } catch {
    // Ignore storage quota errors
  }
}

export function useWardFlowReviews() {
  const { user } = useAuth();
  const [reviews, setReviews] = useState<ReviewRow[]>(() => readLocalReviews());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const actor = (user?.email || user?.name || 'Fabric Clinician').slice(0, 128);

  const refresh = useCallback(async () => {
    if (LOCAL_DATA) {
      setReviews(readLocalReviews());
      setLoading(false);
      return;
    }
    try {
      const rows = await getRayfinClient()
        .data.WardFlowTriageReview.select([...FIELDS])
        .orderBy({ requestedAt: 'desc' })
        .execute();
      const typed = rows as ReviewRow[];
      setReviews(typed);
      writeLocalReviews(typed);
      setError(null);
    } catch (err) {
      const fallback = readLocalReviews();
      if (fallback.length) setReviews(fallback);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createReview = useCallback(
    async (draft: TriageEvaluationDraft): Promise<ReviewRow> => {
      const now = new Date();
      const payload: Omit<ReviewRow, 'id'> = {
        runId: draft.runId,
        subjectId: draft.subjectId,
        initials: draft.initials,
        careSetting: draft.careSetting,
        condition: draft.condition.slice(0, 160),
        score: Number(draft.afterScore.toFixed(2)),
        stage: draft.afterStage,
        recommendedAction: draft.recommendedAction,
        conclusion: draft.conclusion.slice(0, 500),
        draft: draft.draft.slice(0, 1000),
        evidenceJson: JSON.stringify(draft.evidence).slice(0, 1000),
        confidence: Number(draft.confidence.toFixed(3)),
        model: draft.model.slice(0, 64),
        approvalState: draft.recommendedAction === 'monitor' ? 'monitored' : 'pending',
        requestedBy: actor,
        requestedAt: now,
        runtimeTokens: draft.runtimeTokens,
      };

      if (!LOCAL_DATA) {
        try {
          const created = (await getRayfinClient().data.WardFlowTriageReview.create(payload)) as ReviewRow;
          setReviews((prev) => {
            const next = [created, ...prev.filter((r) => r.id !== created.id)];
            writeLocalReviews(next);
            return next;
          });
          setError(null);
          return created;
        } catch (err) {
          console.warn('Rayfin SQL WardFlowTriageReview write fell back to local state:', err);
        }
      }

      const localRow: ReviewRow = { id: crypto.randomUUID(), ...payload };
      setReviews((prev) => {
        const next = [localRow, ...prev];
        writeLocalReviews(next);
        return next;
      });
      return localRow;
    },
    [actor],
  );

  const resolveReview = useCallback(
    async (id: string, state: 'approved' | 'rejected', note?: string): Promise<void> => {
      const resolvedAt = new Date();
      const resolutionNote = (
        note ||
        (state === 'approved'
          ? 'Approved by authenticated clinician; simulated notification recorded.'
          : 'Rejected by authenticated clinician; no outreach dispatched.')
      ).slice(0, 500);

      if (!LOCAL_DATA) {
        try {
          await getRayfinClient().data.WardFlowTriageReview.update(
            { id },
            { approvalState: state, approverId: actor, resolvedAt, resolutionNote },
          );
        } catch (err) {
          console.warn('Rayfin SQL WardFlowTriageReview update fell back to local state:', err);
        }
      }

      setReviews((prev) => {
        const next = prev.map((r) =>
          r.id === id ? { ...r, approvalState: state, approverId: actor, resolvedAt, resolutionNote } : r,
        );
        writeLocalReviews(next);
        return next;
      });
    },
    [actor],
  );

  return { reviews, loading, error, actor, refresh, createReview, resolveReview };
}
