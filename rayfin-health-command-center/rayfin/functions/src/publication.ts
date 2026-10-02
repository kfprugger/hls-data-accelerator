import { UserDataFunctionInternalError, UserDataFunctionInvalidInputError } from '@microsoft/fabric-user-data-functions';
import { parseSnapshotPayload, validateExpectedVersion } from './snapshot-payload.js';
import { isSqlPermissionDenied, type Procedure, type Publication, type SqlRow } from './sql.js';

export const NOT_CONFIGURED = 'Snapshot SQL connection is not configured.';

/**
 * One invocation's two identities, injected so the authorization rules are testable.
 * Under `functions.auth.type: application`, SQL runs as the app identity (the AppBackend
 * item owner) for every caller; only the Rayfin token identifies the person who invoked.
 */
export interface PublicationPorts {
    /** `email` claim of the invocation's Rayfin token, or null when absent. */
    callerEmail(): string | null;
    /** The caller's SnapshotWriter rows, read with that same Rayfin token under the entity's read policy. */
    writerRows(): Promise<ReadonlyArray<{ email?: unknown }>>;
    /** Runs a publication procedure on the app SQL database as the app identity. */
    execute(procedure: Procedure, publication?: Publication): Promise<SqlRow>;
}

export interface SyncAccessResult { canSync: boolean; version: number; publisherId: string; unavailableReason?: string }
export interface PublicationResult {
    status: 'published' | 'conflict' | 'denied'; version: number; capturedAt: string;
    kpiRows: number; seriesRows: number; worklistRows: number; publisherId: string;
}

/** An access check that could not complete; `reason` is an operator-facing cause code. */
class AccessCheckError extends Error {
    constructor(readonly reason: string, options?: ErrorOptions) {
        super(`Sync access check failed: ${reason}`, options);
    }
}

/**
 * `email` claim of a Rayfin access token. The payload is not signature-checked here; the writer
 * lookup is authenticated with this same token, so a forged claim cannot get past that call.
 */
export function tokenEmail(accessToken: string): string | null {
    const payload = accessToken.split('.')[1];
    if (!payload) return null;
    try {
        const claims: unknown = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
        const email = (claims as { email?: unknown } | null)?.email;
        return typeof email === 'string' && email.trim() !== '' ? email.trim() : null;
    } catch {
        return null;
    }
}

/** Operator-facing cause code; never carries server names, tokens, payloads, or SQL text. */
function failureReason(error: unknown): string {
    if (error instanceof AccessCheckError) return error.reason;
    if (error instanceof UserDataFunctionInternalError && error.message === NOT_CONFIGURED) return 'sql-connection-not-configured';
    // Reading a declared ctx.Tokens audience throws this when the host delivered no token for it.
    if (error instanceof UserDataFunctionInvalidInputError) return 'sql-token-unavailable';
    const driverError = error as { number?: unknown; code?: unknown } | null;
    if (typeof driverError?.number === 'number') return `sql-error-${driverError.number}`;
    if (typeof driverError?.code === 'string') return `sql-${driverError.code.toLowerCase()}`;
    return 'unexpected';
}

/**
 * The caller's enrolled email, or null when not allowlisted. A row counts only when it matches
 * the token's own email claim, so a read policy that leaked other writers' rows still fails closed.
 */
async function verifiedWriter(ports: PublicationPorts): Promise<string | null> {
    const caller = ports.callerEmail();
    if (!caller) throw new AccessCheckError('caller-identity-unavailable');
    let rows: ReadonlyArray<{ email?: unknown }>;
    try {
        rows = await ports.writerRows();
    } catch (error) {
        throw new AccessCheckError('writer-lookup-failed', { cause: error });
    }
    const normalized = caller.toLowerCase();
    const match = rows.find((row) => typeof row.email === 'string' && row.email.trim().toLowerCase() === normalized);
    return match ? (match.email as string).trim() : null;
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

/** Whether the app identity may still execute the publisher, plus the current snapshot's metadata. */
async function appAccess(ports: PublicationPorts): Promise<SyncAccess> {
    const row = await ports.execute('dbo.GetHealthSyncAccess');
    if (typeof row.canSync !== 'boolean') throw new UserDataFunctionInternalError('SQL returned invalid sync permission.');
    return { canSync: row.canSync, ...metadata(row) };
}

function denied(current: SyncAccess, caller: string): PublicationResult {
    const { version, capturedAt, kpiRows, seriesRows, worklistRows } = current;
    return { status: 'denied', version, capturedAt, kpiRows, seriesRows, worklistRows, publisherId: caller };
}

/** Writer only when the caller is allowlisted AND the app identity can publish. */
export async function readSyncAccess(ports: PublicationPorts): Promise<SyncAccessResult> {
    try {
        const [writer, current] = await Promise.all([verifiedWriter(ports), appAccess(ports)]);
        return { canSync: writer !== null && current.canSync, version: current.version, publisherId: ports.callerEmail() ?? '' };
    } catch (error) {
        // A read-only answer with a cause code: the client SDK drops error bodies, so a thrown
        // error would reach the UI only as a bare HTTP status.
        const reason = failureReason(error);
        console.error(`[getSyncAccess] sync access unavailable: ${reason}`);
        return { canSync: false, version: 0, publisherId: '', unavailableReason: reason };
    }
}

export async function publishSnapshot(ports: PublicationPorts, payloadJson: string, expectedVersion: number): Promise<PublicationResult> {
    let writer: string | null;
    let permission: SyncAccess;
    try {
        [writer, permission] = await Promise.all([verifiedWriter(ports), appAccess(ports)]);
    } catch (error) {
        const reason = failureReason(error);
        console.error(`[publishSnapshot] sync access check failed: ${reason}`);
        throw new UserDataFunctionInternalError(`Unable to check server sync permissions (${reason}). No publication was attempted.`);
    }
    const caller = ports.callerEmail() ?? '';
    if (writer === null || !permission.canSync) return denied(permission, caller);
    let canonicalPayload: string;
    try {
        validateExpectedVersion(expectedVersion);
        canonicalPayload = JSON.stringify(parseSnapshotPayload(payloadJson));
    } catch (error) {
        throw new UserDataFunctionInvalidInputError(error instanceof Error ? error.message : 'Invalid snapshot.');
    }
    try {
        const row = await ports.execute('dbo.PublishHealthSnapshot', { payloadJson: canonicalPayload, expectedVersion, publisherId: writer });
        if (row.status !== 'published' && row.status !== 'conflict') throw new Error('Invalid SQL publication status');
        return { status: row.status, ...metadata(row) };
    } catch (error) {
        // SQL rechecks the role and the allowlist at EXEC time, including revocation after the preflight.
        if (isSqlPermissionDenied(error)) return denied(await appAccess(ports), caller);
        // A lost response can follow a successful commit; never claim it was rolled back.
        throw new UserDataFunctionInternalError('Publication outcome could not be confirmed. Reload the published snapshot before retrying.');
    }
}
