import { entity, authenticated, uuid, text, int, date, set } from '@microsoft/rayfin-core';

/**
 * Provenance for one Gold-to-app sync. The dashboard reads the newest
 * succeeded run to show how fresh its figures are, and a failed run keeps its
 * error text so a stale dashboard can explain itself instead of going quiet.
 */
@entity('SyncRun')
@authenticated('*')
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
}
