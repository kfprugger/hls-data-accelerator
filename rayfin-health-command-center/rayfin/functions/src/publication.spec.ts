// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { publishSnapshot, readSyncAccess, tokenEmail, type PublicationPorts } from './publication';
import type { Procedure, Publication, SqlRow } from './sql';
import { snapshot } from '../test/snapshot-fixture';

const appMayPublish: SqlRow = {
    canSync: true, version: 4, publisherId: 'earlier@contoso.test', capturedAt: '2026-10-01T00:00:00Z',
    kpiRows: 14, seriesRows: 1, worklistRows: 2,
};
const payloadJson = JSON.stringify(snapshot());

function harness(options: {
    caller: string | null;
    rows: Array<{ email?: unknown }> | Error;
    sqlAccess?: SqlRow;
    publishError?: unknown;
}) {
    const calls: Array<{ procedure: Procedure; publication?: Publication }> = [];
    const ports: PublicationPorts = {
        callerEmail: () => options.caller,
        writerRows: async () => {
            if (options.rows instanceof Error) throw options.rows;
            return options.rows;
        },
        execute: async (procedure, publication) => {
            calls.push({ procedure, publication });
            if (procedure === 'dbo.GetHealthSyncAccess') return options.sqlAccess ?? appMayPublish;
            if (options.publishError) throw options.publishError;
            return {
                status: 'published', version: 5, publisherId: publication!.publisherId, capturedAt: '2026-10-02T00:00:00Z',
                kpiRows: 14, seriesRows: 1, worklistRows: 2,
            };
        },
    };
    return { ports, published: () => calls.filter((call) => call.procedure === 'dbo.PublishHealthSnapshot') };
}

describe('publication authorization under the shared app identity', () => {
    beforeEach(() => { vi.spyOn(console, 'error').mockImplementation(() => undefined); });
    afterEach(() => { vi.restoreAllMocks(); });

    it('denies a signed-in viewer even though the app identity may publish', async () => {
        const { ports, published } = harness({ caller: 'viewer@contoso.test', rows: [] });
        expect(await readSyncAccess(ports)).toEqual({ canSync: false, version: 4, publisherId: 'viewer@contoso.test' });
        expect(await publishSnapshot(ports, payloadJson, 4)).toMatchObject({ status: 'denied', version: 4, publisherId: 'viewer@contoso.test' });
        expect(published()).toEqual([]);
    });

    it('ignores allowlist rows that do not belong to the token holder', async () => {
        const { ports, published } = harness({ caller: 'viewer@contoso.test', rows: [{ email: 'writer@contoso.test' }] });
        expect((await readSyncAccess(ports)).canSync).toBe(false);
        expect((await publishSnapshot(ports, payloadJson, 4)).status).toBe('denied');
        expect(published()).toEqual([]);
    });

    it('publishes as the enrolled email when the token email matches case-insensitively', async () => {
        const { ports, published } = harness({ caller: 'Writer@Contoso.test', rows: [{ email: 'writer@contoso.test' }] });
        expect((await readSyncAccess(ports)).canSync).toBe(true);
        expect(await publishSnapshot(ports, payloadJson, 4)).toMatchObject({ status: 'published', version: 5, publisherId: 'writer@contoso.test' });
        expect(published().map((call) => call.publication?.publisherId)).toEqual(['writer@contoso.test']);
    });

    it('denies an enrolled caller when the app identity cannot publish', async () => {
        const { ports, published } = harness({
            caller: 'writer@contoso.test', rows: [{ email: 'writer@contoso.test' }], sqlAccess: { ...appMayPublish, canSync: false },
        });
        expect((await readSyncAccess(ports)).canSync).toBe(false);
        expect((await publishSnapshot(ports, payloadJson, 4)).status).toBe('denied');
        expect(published()).toEqual([]);
    });

    it('reports a SQL allowlist or role rejection at execution time as denied, not as an unknown outcome', async () => {
        const { ports } = harness({ caller: 'writer@contoso.test', rows: [{ email: 'writer@contoso.test' }], publishError: { number: 51003 } });
        expect(await publishSnapshot(ports, payloadJson, 4)).toMatchObject({ status: 'denied', version: 4, publisherId: 'writer@contoso.test' });
    });

    it('surfaces a failed or unidentifiable caller check instead of deciding, and never publishes', async () => {
        const lookupFails = harness({ caller: 'writer@contoso.test', rows: new Error('data API unavailable') });
        expect(await readSyncAccess(lookupFails.ports)).toEqual({ canSync: false, version: 0, publisherId: '', unavailableReason: 'writer-lookup-failed' });
        await expect(publishSnapshot(lookupFails.ports, payloadJson, 4)).rejects.toThrow('(writer-lookup-failed). No publication was attempted.');
        expect(lookupFails.published()).toEqual([]);

        const anonymous = harness({ caller: null, rows: [{ email: 'writer@contoso.test' }] });
        expect((await readSyncAccess(anonymous.ports)).unavailableReason).toBe('caller-identity-unavailable');
        await expect(publishSnapshot(anonymous.ports, payloadJson, 4)).rejects.toThrow('(caller-identity-unavailable)');
        expect(anonymous.published()).toEqual([]);
    });
});

describe('tokenEmail', () => {
    const token = (claims: object) => `e30.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.signature`;

    it('reads only a non-empty email claim and rejects malformed tokens', () => {
        expect(tokenEmail(token({ email: ' writer@contoso.test ' }))).toBe('writer@contoso.test');
        expect(tokenEmail(token({ sub: 'user-1', email: '' }))).toBeNull();
        expect(tokenEmail('not-a-jwt')).toBeNull();
        expect(tokenEmail('e30.%%%.signature')).toBeNull();
    });
});
