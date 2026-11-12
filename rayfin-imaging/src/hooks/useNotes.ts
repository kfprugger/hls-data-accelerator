import { useCallback, useEffect, useMemo, useState } from 'react';

import illustrative from '../../pipeline/tumour_board_notes.json';
import type { TumorBoardNote } from '../../rayfin/data/TumorBoardNote';
import { useAuth } from '@/hooks/AuthContext';
import { LOCAL_DATA, localApi } from '@/lib/localMode';
import { getRayfinClient } from '@/services/rayfin/RayfinClientService';

export type Note = Pick<TumorBoardNote, 'id' | 'patientId' | 'body' | 'createdBy' | 'authorName' | 'createdAt' | 'eventId'>;

const FIELDS = ['id', 'patientId', 'body', 'createdBy', 'authorName', 'createdAt', 'eventId'] as const;

/** Notes live in the app's Rayfin database; in local mode, in work/local/notes.json through the dev server. */
const notesApi = {
  list: async (patientId: string): Promise<Note[]> =>
    LOCAL_DATA
      ? localApi<Note[]>(`notes?patientId=${encodeURIComponent(patientId)}`)
      : ((await getRayfinClient()
          .data.TumorBoardNote.select([...FIELDS])
          .where({ patientId: { eq: patientId } })
          .orderBy({ createdAt: 'asc' })
          .execute()) as Note[]),
  create: async (note: Omit<Note, 'id'>): Promise<Note> =>
    LOCAL_DATA
      ? localApi<Note>('notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(note) })
      : ((await getRayfinClient().data.TumorBoardNote.create(note)) as Note),
  remove: async (id: string): Promise<void> => {
    if (LOCAL_DATA) await localApi<void>(`notes/${encodeURIComponent(id)}`, { method: 'DELETE' });
    else await getRayfinClient().data.TumorBoardNote.delete({ id });
  },
};

/** The tumour board notes for one patient: the only data the app writes. */
export function useNotes(patientId: string) {
  const { user } = useAuth();
  const [notes, setNotes] = useState<Note[]>([]);
  const [error, setError] = useState<string | null>(null);
  const me = LOCAL_DATA ? user?.id : (getRayfinClient().auth.getSession().user?.id ?? user?.id);

  const refresh = useCallback(async () => {
    try {
      setNotes(await notesApi.list(patientId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [patientId]);

  useEffect(() => {
    setNotes([]);
    void refresh();
  }, [refresh]);

  const add = useCallback(
    async (body: string, eventId?: string): Promise<Note | null> => {
      if (!body.trim() || !me) return null;
      try {
        const created = await notesApi.create({
          patientId,
          body: body.trim().slice(0, 1000),
          createdBy: me,
          authorName: (user?.name || user?.email || 'Fabric user').slice(0, 128),
          createdAt: new Date(),
          ...(eventId ? { eventId } : {}),
        });
        setNotes((n) => [...n, created]);
        setError(null);
        return created;
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        return null;
      }
    },
    [patientId, me, user]
  );

  /** The demo's illustrative case-review note for this patient, if it has one. */
  const sample = (illustrative.notes as Record<string, string>)[patientId] ?? null;

  const addIllustrative = useCallback(async (): Promise<Note | null> => {
    if (!sample || !me) return null;
    try {
      const created = await notesApi.create({ patientId, body: sample, createdBy: me, authorName: illustrative.author, createdAt: new Date() });
      setNotes((n) => [...n, created]);
      setError(null);
      return created;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return null;
    }
  }, [patientId, me, sample]);

  const remove = useCallback(async (id: string) => {
    try {
      await notesApi.remove(id);
      setNotes((n) => n.filter((x) => x.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);
  return useMemo(
    () => ({ notes, error, me, add, remove, addIllustrative: sample ? addIllustrative : null }),
    [notes, error, me, add, remove, addIllustrative, sample]
  );
}

export interface NotesState {
  notes: Note[];
  error: string | null;
  me: string | undefined;
  add: (body: string, eventId?: string) => Promise<Note | null>;
  remove: (id: string) => Promise<void>;
  addIllustrative: (() => Promise<Note | null>) | null;
}
