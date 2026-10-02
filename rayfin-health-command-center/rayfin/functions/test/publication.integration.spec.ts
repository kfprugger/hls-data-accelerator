// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { Connection, Request } from 'tedious';
import { executeProcedure, type SqlRow, type SqlSettings } from '../src/sql';
import { parseSnapshotPayload } from '../src/snapshot-payload';

// Explicit opt-in: this republishes the current real Gold snapshot once. It never
// substitutes fixture data or impersonated principals for live security evidence.
// SQL_WRITER_TOKEN is the app identity's token (the AppBackend owner, as Functions use it);
// SQL_PUBLISHER_EMAIL is a person enrolled with grant-writer.sql.
const enabled = process.env.RAYFIN_SQL_INTEGRATION === '1';
function settings(tokenVariable: string): SqlSettings {
    const server = process.env.SQL_SERVER;
    const database = process.env.SQL_DATABASE;
    const token = process.env[tokenVariable];
    if (!server || !database || !token) throw new Error(`SQL_SERVER, SQL_DATABASE and ${tokenVariable} are required`);
    return { server, database, token };
}
function query(connectionSettings: SqlSettings, statement: string): Promise<SqlRow[]> {
    return new Promise((resolve, reject) => {
        const connection = new Connection({
            server: connectionSettings.server,
            authentication: { type: 'azure-active-directory-access-token', options: { token: connectionSettings.token } },
            options: { database: connectionSettings.database, encrypt: true, trustServerCertificate: false, requestTimeout: 60_000 },
        });
        const rows: SqlRow[] = [];
        const finish = (error?: Error) => {
            connection.close();
            if (error) reject(error); else resolve(rows);
        };
        connection.on('error', finish);
        connection.connect((error) => {
            if (error) { finish(error); return; }
            const request = new Request(statement, (requestError) => finish(requestError ?? undefined));
            request.on('row', (columns) => rows.push(Object.fromEntries(columns.map((column) => [column.metadata.colName, column.value]))));
            connection.execSql(request);
        });
    });
}
const selectPublication = `SELECT id,version,payloadJson,syncRunId,publisherId,CONVERT(nvarchar(33),capturedAt,127) AS capturedAt
    FROM dbo.PublishedSnapshots WHERE id='00000000-0000-0000-0000-000000000001'`;

describe.skipIf(!enabled)('live SQL publication permission and state invariants', () => {
    it('denies viewers and unenrolled publishers, elects one concurrent winner, and retains that complete winner after rejection', async () => {
        const observer = settings('SQL_OBSERVER_TOKEN');
        const writer = settings('SQL_WRITER_TOKEN');
        const viewer = settings('SQL_VIEWER_TOKEN');
        const publisherId = process.env.SQL_PUBLISHER_EMAIL;
        if (!publisherId) throw new Error('SQL_PUBLISHER_EMAIL is required');
        const [before] = await query(observer, selectPublication);
        if (!before) throw new Error('Run the real in-app Sync from Gold once before this opt-in verification');
        const payloadJson = String(before.payloadJson);
        const payload = parseSnapshotPayload(payloadJson);
        const expectedVersion = Number(before.version);
        const denied = await executeProcedure(viewer, 'dbo.GetHealthSyncAccess');
        expect(denied.canSync).toBe(false);
        await expect(executeProcedure(viewer, 'dbo.PublishHealthSnapshot', { payloadJson, expectedVersion, publisherId })).rejects.toMatchObject({ number: 229 });
        await expect(executeProcedure(writer, 'dbo.PublishHealthSnapshot', { payloadJson, expectedVersion, publisherId: 'not-enrolled@example.invalid' })).rejects.toMatchObject({ number: 51003 });
        await expect(query(viewer, `UPDATE dbo.PublishedSnapshots SET version=version WHERE id='00000000-0000-0000-0000-000000000001'`)).rejects.toMatchObject({ number: 229 });
        await expect(query(writer, `UPDATE dbo.PublishedSnapshots SET version=version WHERE id='00000000-0000-0000-0000-000000000001'`)).rejects.toMatchObject({ number: 229 });
        expect((await query(observer, selectPublication))[0]).toEqual(before);

        const results = await Promise.all([
            executeProcedure(writer, 'dbo.PublishHealthSnapshot', { payloadJson, expectedVersion, publisherId }),
            executeProcedure(writer, 'dbo.PublishHealthSnapshot', { payloadJson, expectedVersion, publisherId }),
        ]);
        expect(results.map((row) => row.status).sort()).toEqual(['conflict', 'published']);
        expect(results.map((row) => row.version)).toEqual([expectedVersion + 1, expectedVersion + 1]);
        const [winner] = await query(observer, selectPublication);
        expect(winner.payloadJson).toBe(payloadJson);
        expect(winner.publisherId).toBe(publisherId);
        expect(winner.version).toBe(expectedVersion + 1);
        const [audit] = await query(observer, `SELECT r.status,r.expectedVersion,r.publishedVersion,r.publisherId,r.kpiRows,r.seriesRows,r.worklistRows
            FROM dbo.SyncRuns r JOIN dbo.PublishedSnapshots p ON p.syncRunId=r.id`);
        expect(audit).toEqual({ status: 'succeeded', expectedVersion, publishedVersion: expectedVersion + 1,
            publisherId, kpiRows: payload.kpis.length, seriesRows: payload.series.length, worklistRows: payload.worklist.length });

        // Bypass the JS validator deliberately to prove the SQL boundary itself rejects partial publication.
        await expect(executeProcedure(writer, 'dbo.PublishHealthSnapshot', {
            payloadJson: JSON.stringify({ schemaVersion: 1, kpis: [], series: [], worklist: [] }), expectedVersion: expectedVersion + 1, publisherId,
        })).rejects.toMatchObject({ number: 51001 });
        expect((await query(observer, selectPublication))[0]).toEqual(winner);
        const [failed] = await query(observer, `SELECT TOP (1) status,kpiRows,seriesRows,worklistRows,publisherId
            FROM dbo.SyncRuns WHERE status=N'failed' AND expectedVersion=${expectedVersion + 1} ORDER BY completedAt DESC`);
        expect(failed).toEqual({ status: 'failed', kpiRows: 0, seriesRows: 0, worklistRows: 0, publisherId });
    }, 180_000);
});
