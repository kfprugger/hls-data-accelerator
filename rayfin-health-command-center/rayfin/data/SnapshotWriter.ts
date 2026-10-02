import { entity, authenticated, uuid, text } from '@microsoft/rayfin-core';

/**
 * Snapshot publication allowlist. Each signed-in user can read only their own row, so the
 * trusted function learns whether the caller may publish; no role can write it through the API.
 * Database administrators enroll writers with `rayfin/functions/sql/grant-writer.sql`.
 */
@entity('SnapshotWriter')
@authenticated('read', { policy: (claims, item) => claims.email.eq(item.email) })
export class SnapshotWriter {
    @uuid() id!: string;

    @text({ max: 200, unique: true }) email!: string;
}
