import { entity, authenticated, uuid, text, int, date } from '@microsoft/rayfin-core';

/** One immutable-at-read publication shared by all three dashboard lenses. */
@entity('PublishedSnapshot')
@authenticated('read')
export class PublishedSnapshot {
    @uuid() id!: string;

    @int() version!: number;

    @text() payloadJson!: string;

    @date() capturedAt!: Date;

    @uuid() syncRunId!: string;

    @text({ max: 200 }) publisherId!: string;

    @text({ max: 200 }) sources!: string;
}
