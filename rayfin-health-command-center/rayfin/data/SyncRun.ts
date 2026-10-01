import { entity, authenticated, uuid, text, int, date, set } from '@microsoft/rayfin-core';

/** Publication attempts; only a successful transaction advances the snapshot. */
@entity('SyncRun')
@authenticated('read')
export class SyncRun {
    @uuid() id!: string;

    @date() startedAt!: Date;

    @date({ optional: true }) completedAt?: Date;

    @set('running', 'succeeded', 'failed')
    status!: 'running' | 'succeeded' | 'failed';

    @int() kpiRows!: number;

    @int() seriesRows!: number;

    @int() worklistRows!: number;

    /** Semantic models the run read from, comma separated. */
    @text({ max: 200 }) sources!: string;

    @text({ max: 500, optional: true }) error?: string;

    /** SQL-authenticated identity, never supplied by the browser. */
    @text({ max: 200, optional: true }) publisherId?: string;

    @int({ optional: true }) expectedVersion?: number;

    @int({ optional: true }) publishedVersion?: number;
}
