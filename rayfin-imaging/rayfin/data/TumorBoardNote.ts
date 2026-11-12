import { authenticated, date, entity, text, uuid } from '@microsoft/rayfin-core';

/**
 * A note left on a patient for the tumour board, shared with everyone signed in to the app.
 * Patient data itself is never written: it is read in place from the OneLake silos.
 * Only the author can change or remove their own notes. `eventId` anchors the note to an event on the patient's
 * timeline (a mark id such as `v:<encounter_id>`); notes without one are about the case as a whole.
 */
@entity()
@authenticated('read')
@authenticated(['create', 'update', 'delete'], {
  policy: (claims, item) => claims.sub.eq(item.createdBy),
})
export class TumorBoardNote {
  @uuid() id!: string;
  @text({ min: 1, max: 64 }) patientId!: string;
  @text({ min: 1, max: 1000 }) body!: string;
  @text({ max: 128 }) createdBy!: string;
  @text({ max: 128 }) authorName!: string;
  @date() createdAt!: Date;
  @text({ max: 200, optional: true }) eventId?: string;
}
