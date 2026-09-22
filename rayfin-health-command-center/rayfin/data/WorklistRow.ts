import { entity, authenticated, uuid, text, decimal, boolean, int, date, set } from '@microsoft/rayfin-core';

/**
 * A worklist row: a high-cost member for the payer lens, or a heavy imaging
 * acquisition for the medtech lens. Identifiers are masked by the sync before
 * they are written, so the app database never stores a raw member id or name.
 */
@entity('WorklistRow')
@authenticated('*')
export class WorklistRow {
    @uuid() id!: string;

    @set('payer', 'provider', 'medtech')
    lens!: 'payer' | 'provider' | 'medtech';

    /** highCostMember | heavyAcquisition */
    @text({ max: 32 }) kind!: string;

    /** Masked identifier or initials — never the raw value. */
    @text({ max: 64 }) subject!: string;

    @text({ max: 64, optional: true }) segment?: string;

    @decimal() primaryValue!: number;

    @text({ max: 16 }) primaryUnit!: string;

    @decimal({ optional: true }) secondaryValue?: number;

    @text({ max: 16, optional: true }) secondaryUnit?: string;

    @boolean({ optional: true }) flagged?: boolean;

    @int() rank!: number;

    @date() capturedAt!: Date;
}
