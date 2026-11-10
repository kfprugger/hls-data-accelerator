import { Connection, Request, TYPES } from 'tedious';

export interface SqlSettings {
    server: string;
    database: string;
    token: string;
}
export type SqlRow = Record<string, unknown>;
export type Procedure = 'dbo.GetHealthSyncAccess' | 'dbo.PublishHealthSnapshot';
/** `publisherId` is the caller's allowlisted email, verified by the function before publication. */
export interface Publication { payloadJson: string; expectedVersion: number; publisherId: string }

/** Fabric reports `serverFqdn` as `host,1433` (optionally `tcp:`-prefixed); tedious needs host and port separately. */
export function parseServer(value: string): { host: string; port: number } {
    const [host, port] = value.trim().replace(/^tcp:/i, '').split(',');
    return { host, port: port ? Number(port) : 1433 };
}

/** Each call opens its own session with the invocation's app-identity SQL token; no token-bearing shared pool. */
export function executeProcedure(settings: SqlSettings, procedure: Procedure, publication?: Publication): Promise<SqlRow> {
    const { host, port } = parseServer(settings.server);
    return new Promise((resolve, reject) => {
        const connection = new Connection({
            server: host,
            authentication: { type: 'azure-active-directory-access-token', options: { token: settings.token } },
            options: {
                database: settings.database,
                port,
                encrypt: true,
                trustServerCertificate: false,
                connectTimeout: 30_000,
                requestTimeout: 60_000,
            },
        });
        let settled = false;
        let result: SqlRow | undefined;
        const finish = (error?: Error) => {
            if (settled) return;
            settled = true;
            connection.close();
            if (error) reject(error);
            else if (!result) reject(new Error('SQL publication returned no result'));
            else resolve(result);
        };
        connection.on('error', finish);
        connection.connect((error) => {
            if (error) { finish(error); return; }
            const request = new Request(procedure, (requestError) => finish(requestError ?? undefined));
            request.on('row', (columns: Array<{ metadata: { colName: string }; value: unknown }>) => {
                result = Object.fromEntries(columns.map((column) => [column.metadata.colName, column.value]));
            });
            if (publication) {
                request.addParameter('payloadJson', TYPES.NVarChar, publication.payloadJson, { length: Infinity });
                request.addParameter('expectedVersion', TYPES.Int, publication.expectedVersion);
                request.addParameter('publisherId', TYPES.NVarChar, publication.publisherId, { length: 200 });
            }
            connection.callProcedure(request);
        });
    });
}

export function isSqlPermissionDenied(error: unknown): boolean {
    if (!error || typeof error !== 'object') return false;
    const number = 'number' in error ? error.number : undefined;
    return number === 229 || number === 51003;
}
