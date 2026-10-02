import {
    UserDataFunctions, AudienceType, type RayfinContext,
    UserDataFunctionInternalError, UserDataFunctionInvalidInputError,
} from '@microsoft/fabric-user-data-functions';
import type { AppSchema } from '../../data/schema.js';
import { parseSnapshotPayload, validateExpectedVersion } from './snapshot-payload.js';
import { executeProcedure, isSqlPermissionDenied, type SqlRow, type SqlSettings } from './sql.js';

const udf = new UserDataFunctions();
const NOT_CONFIGURED = 'Snapshot SQL connection is not configured.';

function settings(ctx: RayfinContext<AppSchema>): SqlSettings {
    const server = ctx.getSecret('SQL_SERVER') ?? process.env.SQL_SERVER;
    const database = ctx.getSecret('SQL_DATABASE') ?? process.env.SQL_DATABASE;
    if (!server || !database) throw new UserDataFunctionInternalError(NOT_CONFIGURED);
    return { server, database, token: ctx.getToken(AudienceType.Sql) };
}

/** Operator-facing cause code; never carries server names, tokens, payloads, or SQL text. */
function failureReason(error: unknown): string {
    if (error instanceof UserDataFunctionInternalError && error.message === NOT_CONFIGURED) return 'sql-connection-not-configured';
    // RayfinContext.getToken throws this when the host delivered no OBO token for the SQL audience.
    if (error instanceof UserDataFunctionInvalidInputError) return 'sql-token-unavailable';
    const driverError = error as { number?: unknown; code?: unknown } | null;
    if (typeof driverError?.number === 'number') return `sql-error-${driverError.number}`;
    if (typeof driverError?.code === 'string') return `sql-${driverError.code.toLowerCase()}`;
    return 'unexpected';
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

interface SyncAccess {
    canSync: boolean; version: number; capturedAt: string;
    kpiRows: number; seriesRows: number; worklistRows: number; publisherId: string;
}

async function access(connection: SqlSettings): Promise<SyncAccess> {
    const row = await executeProcedure(connection, 'dbo.GetHealthSyncAccess');
    if (typeof row.canSync !== 'boolean') throw new UserDataFunctionInternalError('SQL returned invalid sync permission.');
    return { canSync: row.canSync, ...metadata(row) };
}

udf.func('getSyncAccess', async (ctx: RayfinContext<AppSchema>): Promise<{
    canSync: boolean; version: number; publisherId: string; unavailableReason?: string;
}> => {
    try {
        const result = await access(settings(ctx));
        return { canSync: result.canSync, version: result.version, publisherId: result.publisherId };
    } catch (error) {
        // A read-only answer with a cause code: the client SDK drops error bodies, so a thrown
        // error would reach the UI only as a bare HTTP status.
        const reason = failureReason(error);
        console.error(`[getSyncAccess] sync access unavailable: ${reason}`);
        return { canSync: false, version: 0, publisherId: '', unavailableReason: reason };
    }
}, [udf.connection({ audienceType: AudienceType.Sql })]);

udf.func('publishSnapshot', async (payloadJson: string, expectedVersion: number, ctx: RayfinContext<AppSchema>): Promise<{
    status: 'published' | 'conflict' | 'denied'; version: number; capturedAt: string;
    kpiRows: number; seriesRows: number; worklistRows: number; publisherId: string;
}> => {
    let connection: SqlSettings;
    let permission: SyncAccess;
    try {
        connection = settings(ctx);
        permission = await access(connection);
    } catch (error) {
        const reason = failureReason(error);
        console.error(`[publishSnapshot] sync access check failed: ${reason}`);
        throw new UserDataFunctionInternalError(`Unable to check server sync permissions (${reason}). No publication was attempted.`);
    }
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
