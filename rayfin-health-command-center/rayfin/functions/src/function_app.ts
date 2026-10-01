import {
    UserDataFunctions, AudienceType, type RayfinContext,
    UserDataFunctionInternalError, UserDataFunctionInvalidInputError,
} from '@microsoft/fabric-user-data-functions';
import type { AppSchema } from '../../data/schema.js';
import { parseSnapshotPayload, validateExpectedVersion } from './snapshot-payload.js';
import { executeProcedure, isSqlPermissionDenied, type SqlRow, type SqlSettings } from './sql.js';

const udf = new UserDataFunctions();

function settings(ctx: RayfinContext<AppSchema>): SqlSettings {
    const server = ctx.getSecret('SQL_SERVER') ?? process.env.SQL_SERVER;
    const database = ctx.getSecret('SQL_DATABASE') ?? process.env.SQL_DATABASE;
    if (!server || !database) throw new UserDataFunctionInternalError('Snapshot SQL connection is not configured.');
    return { server, database, token: ctx.getToken(AudienceType.Sql) };
}

function metadata(row: SqlRow) {
    for (const key of ['version', 'kpiRows', 'seriesRows', 'worklistRows']) {
        if (typeof row[key] !== 'number' || !Number.isInteger(row[key]) || row[key] < 0) {
            throw new UserDataFunctionInternalError('SQL returned invalid publication metadata.');
        }
    }
    if (typeof row.publisherId !== 'string' || typeof row.capturedAt !== 'string') {
        throw new UserDataFunctionInternalError('SQL returned invalid publication provenance.');
    }
    return {
        version: row.version as number, capturedAt: row.capturedAt,
        kpiRows: row.kpiRows as number, seriesRows: row.seriesRows as number,
        worklistRows: row.worklistRows as number, publisherId: row.publisherId,
    };
}

async function access(connection: SqlSettings) {
    const row = await executeProcedure(connection, 'dbo.GetHealthSyncAccess');
    if (typeof row.canSync !== 'boolean') throw new UserDataFunctionInternalError('SQL returned invalid sync permission.');
    return { canSync: row.canSync, ...metadata(row) };
}

udf.func('getSyncAccess', async (ctx: RayfinContext<AppSchema>): Promise<{
    canSync: boolean; version: number; publisherId: string;
}> => {
    try {
        const result = await access(settings(ctx));
        return { canSync: result.canSync, version: result.version, publisherId: result.publisherId };
    } catch {
        throw new UserDataFunctionInternalError('Unable to check server sync permissions. No publication was attempted.');
    }
}, [udf.connection({ audienceType: AudienceType.Sql })]);

udf.func('publishSnapshot', async (payloadJson: string, expectedVersion: number, ctx: RayfinContext<AppSchema>): Promise<{
    status: 'published' | 'conflict' | 'denied'; version: number; capturedAt: string;
    kpiRows: number; seriesRows: number; worklistRows: number; publisherId: string;
}> => {
    const connection = settings(ctx);
    let permission: Awaited<ReturnType<typeof access>>;
    try { permission = await access(connection); }
    catch { throw new UserDataFunctionInternalError('Unable to check server sync permissions. No publication was attempted.'); }
    if (!permission.canSync) {
        const { canSync: _canSync, ...current } = permission;
        return { status: 'denied', ...current };
    }
    let canonicalPayload: string;
    try {
        validateExpectedVersion(expectedVersion);
        canonicalPayload = JSON.stringify(parseSnapshotPayload(payloadJson));
    } catch (error) {
        throw new UserDataFunctionInvalidInputError(error instanceof Error ? error.message : 'Invalid snapshot.');
    }
    try {
        const row = await executeProcedure(connection, 'dbo.PublishHealthSnapshot', { payloadJson: canonicalPayload, expectedVersion });
        if (row.status !== 'published' && row.status !== 'conflict') throw new Error('Invalid SQL publication status');
        return { status: row.status, ...metadata(row) };
    } catch (error) {
        if (isSqlPermissionDenied(error)) {
            // SQL rechecks permission at EXEC time, including revocation after the preflight.
            const { canSync: _canSync, ...current } = await access(connection);
            return { status: 'denied', ...current };
        }
        // A lost response can follow a successful commit; never claim it was rolled back.
        throw new UserDataFunctionInternalError('Publication outcome could not be confirmed. Reload the published snapshot before retrying.');
    }
}, [udf.connection({ audienceType: AudienceType.Sql })]);
