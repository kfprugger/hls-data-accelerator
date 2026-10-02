import {
    UserDataFunctions, AudienceType, type RayfinContext, UserDataFunctionInternalError,
} from '@microsoft/fabric-user-data-functions';
import type { AppSchema } from '../../data/schema.js';
import { NOT_CONFIGURED, publishSnapshot, readSyncAccess, tokenEmail, type PublicationPorts } from './publication.js';
import { executeProcedure, type SqlSettings } from './sql.js';

const udf = new UserDataFunctions();

function settings(ctx: RayfinContext<AppSchema, AudienceType.Sql>): SqlSettings {
    let server: string;
    let database: string;
    try {
        server = ctx.Secrets.SQL_SERVER;
        database = ctx.Secrets.SQL_DATABASE;
    } catch {
        // An unset secret throws the same error class as a missing token; keep the causes distinct.
        throw new UserDataFunctionInternalError(NOT_CONFIGURED);
    }
    if (!server || !database) throw new UserDataFunctionInternalError(NOT_CONFIGURED);
    return { server, database, token: ctx.Tokens.Sql };
}

/** SQL runs as the app identity; the writer allowlist is read with the caller's own Rayfin token. */
function ports(ctx: RayfinContext<AppSchema, AudienceType.Sql>): PublicationPorts {
    return {
        callerEmail: () => tokenEmail(ctx.accessToken),
        writerRows: () => ctx.getDataClient().SnapshotWriter.select(['email']).execute(),
        execute: (procedure, publication) => executeProcedure(settings(ctx), procedure, publication),
    };
}

udf.func('getSyncAccess', async (ctx: RayfinContext<AppSchema, AudienceType.Sql>): Promise<{
    canSync: boolean; version: number; publisherId: string; unavailableReason?: string;
}> => readSyncAccess(ports(ctx)), []);

udf.func('publishSnapshot', async (payloadJson: string, expectedVersion: number, ctx: RayfinContext<AppSchema, AudienceType.Sql>): Promise<{
    status: 'published' | 'conflict' | 'denied'; version: number; capturedAt: string;
    kpiRows: number; seriesRows: number; worklistRows: number; publisherId: string;
}> => publishSnapshot(ports(ctx), payloadJson, expectedVersion), []);
