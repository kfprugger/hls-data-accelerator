import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { requestJson, type AuthContext } from './api';
import { useAppState } from './AppState';
import { setHostedHistoryMode } from './formHistory';

type Tool = 'az' | 'azps';
interface Identity { hosted: boolean; email: string; oid: string; tid: string; notice: string }
interface Code { session_id: string; user_code: string; verification_uri: string; expires_in: number }
interface Status { status: 'pending' | 'succeeded' | 'failed'; error?: string; error_hint?: string }
interface Target { tenant_id: string; subscription_id: string }
interface Pending extends Target { session_id: string; tool: Tool; user_code: string | null; verification_uri: string | null; expires_in: number }
interface SavedState { target: Target | null; pending: Pending | null }
function draftKey(identity: Identity) { return `hls-auth-target:${identity.tid}:${identity.oid}`; }
function readDraft(identity: Identity): Target | null {
    try {
        const value = JSON.parse(sessionStorage.getItem(draftKey(identity)) || 'null');
        return value && typeof value.tenant_id === 'string' && typeof value.subscription_id === 'string'
            ? { tenant_id: value.tenant_id, subscription_id: value.subscription_id } : null;
    } catch { return null; }
}
interface Authentication {
  identity: Identity | null; tenant: string; subscription: string; setTenant: (value: string) => void; setSubscription: (value: string) => void;
  code: Code | null; tool: Tool | null; busy: boolean; error: string; message: string; remaining: number;
  begin: (tool: Tool) => Promise<void>; logout: () => Promise<void>;
}
const Context = createContext<Authentication | null>(null);
export function useAuthentication() {
  const value = useContext(Context);
  if (!value) throw new Error('AuthenticationProvider is required');
  return value;
}
export function AuthenticationProvider({ children }: {
    children: ReactNode;
}) {
    const { authContext, refreshAuthContext } = useAppState();
    const refresh = useRef(refreshAuthContext);
    refresh.current = refreshAuthContext;
    const [identity, setIdentity] = useState<Identity | null>(null);
    const [tenant, setTenantValue] = useState('');
    const [subscription, setSubscriptionValue] = useState('');
    const target = useRef<Target>({ tenant_id: '', subscription_id: '' });
    const [code, setCode] = useState<Code | null>(null);
    const [tool, setTool] = useState<Tool | null>(null);
    const [busy, setBusy] = useState(true);
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const [remaining, setRemaining] = useState(0);
    const reservation = useRef(false);
    function applyTarget(value: Target, remember = false) {
        const pair = { tenant_id: value.tenant_id, subscription_id: value.subscription_id };
        target.current = pair;
        if (remember && identity?.hosted) {
            try { sessionStorage.setItem(draftKey(identity), JSON.stringify(pair)); }
            catch { setError('This browser blocks temporary target recovery. Wait for the fields to save before refreshing.'); }
        }
        setTenantValue(value.tenant_id);
        setSubscriptionValue(value.subscription_id);
    }
    const setTenant = (value: string) => applyTarget({ ...target.current, tenant_id: value }, true);
    const setSubscription = (value: string) => applyTarget({ ...target.current, subscription_id: value }, true);
    useEffect(() => {
        const controller = new AbortController();
        let timer: ReturnType<typeof setTimeout>;
        const restore = async (owner: Identity) => {
            const state = await requestJson<SavedState>('/api/auth/state', { signal: controller.signal });
            if (controller.signal.aborted) return;
            const saved = state.pending || readDraft(owner) || state.target;
            if (saved) applyTarget(saved);
            if (state.pending) {
                reservation.current = true;
                setBusy(true); setTool(state.pending.tool);
                // The pending request already saved this exact pair on the server.
                try { sessionStorage.removeItem(draftKey(owner)); } catch { /* Server state remains authoritative. */ }
                if (state.pending.user_code && state.pending.verification_uri) {
                    setRemaining(state.pending.expires_in);
                    setCode({ session_id: state.pending.session_id, user_code: state.pending.user_code,
                        verification_uri: state.pending.verification_uri, expires_in: state.pending.expires_in });
                } else timer = setTimeout(() => { void restore(owner).catch(fail); }, 1000);
            } else { reservation.current = false; setBusy(false); }
        };
        const fail = (cause: unknown) => {
            if (controller.signal.aborted) return;
            setBusy(false); reservation.current = false;
            setError(cause instanceof Error ? cause.message : 'Unable to restore sandbox sign-in state');
        };
        requestJson<Identity>('/api/hosted/whoami', { signal: controller.signal })
            .then(async value => {
                if (controller.signal.aborted) return;
                setIdentity(value); setHostedHistoryMode(value.hosted);
                if (value.hosted) {
                    const draft = readDraft(value);
                    if (draft) applyTarget(draft);
                    await restore(value);
                } else setBusy(false);
            }).catch(fail);
        return () => { controller.abort(); clearTimeout(timer); };
    }, []);
    useEffect(() => {
        applyTarget({ tenant_id: target.current.tenant_id || authContext?.cli.tenantId || authContext?.pwsh.tenantId || '',
            subscription_id: target.current.subscription_id || authContext?.cli.subscriptionId || authContext?.pwsh.subscriptionId || '' });
    }, [authContext]);
    useEffect(() => {
        const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
        if (!identity?.hosted || busy || !uuid.test(tenant.trim()) || !uuid.test(subscription.trim())) return;
        const controller = new AbortController();
        const timer = setTimeout(() => {
            void requestJson('/api/auth/target', { method: 'PUT', signal: controller.signal,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tenant_id: tenant.trim(), subscription_id: subscription.trim() }),
            }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Unable to remember deployment target'); });
        }, 250);
        return () => { controller.abort(); clearTimeout(timer); };
    }, [identity?.hosted, busy, tenant, subscription]);
    useEffect(() => {
        if (!code)
            return;
        const controller = new AbortController();
        const deadline = Date.now() + code.expires_in * 1000;
        let timer: ReturnType<typeof setTimeout>;
        const clock = setInterval(() => setRemaining(Math.max(0, Math.ceil((deadline - Date.now()) / 1000))), 1000);
        async function poll() {
            let result: Status;
            try {
                result = await requestJson<Status>(`/api/auth/device-login/${code!.session_id}`, { signal: controller.signal });
            } catch (cause) {
                if (controller.signal.aborted) return;
                const detail = cause instanceof Error ? cause.message : 'Unable to check sign-in';
                if (Date.now() < deadline) {
                    setError(`Status temporarily unavailable: ${detail}. Your existing sign-in is still active; retrying without creating another code.`);
                    timer = setTimeout(poll, 5000);
                    return;
                }
                setError('Device code expired while status was unavailable. Start a new sign-in.');
                setCode(null); setBusy(false); reservation.current = false;
                return;
            }
            if (controller.signal.aborted) return;
            setError('');
            if (result.status === 'pending' && Date.now() < deadline) {
                timer = setTimeout(poll, 2500);
                return;
            }
            setCode(null); setBusy(false); reservation.current = false;
            if (result.status === 'succeeded') {
                setMessage(`${tool === 'az' ? 'Azure CLI' : 'Az PowerShell'} sign-in complete.`);
                try { await refresh.current(); }
                catch (cause) { setError(`Sign-in succeeded, but the account context could not be refreshed. Use Refresh sign-in status. ${cause instanceof Error ? cause.message : ''}`); }
            } else {
                setError([result.error_hint, result.error || 'Device code expired. Start a new sign-in.'].filter(Boolean).join(' '));
            }
        }
        void poll();
        return () => { controller.abort(); clearTimeout(timer); clearInterval(clock); };
    }, [code, tool]);
    async function begin(selected: Tool) {
        if (reservation.current)
            return;
        reservation.current = true;
        setBusy(true);
        setTool(selected);
        setError('');
        setMessage('');
        try {
            const cached = await requestJson<AuthContext>('/api/auth/context?force=true');
            const context = selected === 'az' ? cached.cli : cached.pwsh;
            if (context.loggedIn) {
                setMessage(`${selected === 'az' ? 'Azure CLI' : 'Az PowerShell'} is already signed in as ${context.user}. Sign out first if you need to change that account or tenant.`);
                try { await refresh.current(); }
                finally { setBusy(false); reservation.current = false; }
                return;
            }
            const next = await requestJson<Code>('/api/auth/device-login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, timeoutMs: 60000,
                body: JSON.stringify({ tenant_id: tenant.trim(), subscription_id: subscription.trim(), tool: selected }) });
            setRemaining(next.expires_in);
            setCode(next);
        }
        catch (cause) {
            setError(cause instanceof Error ? cause.message : 'Unable to begin sign-in');
            setBusy(false);
            reservation.current = false;
        }
    }
    async function logout() {
        if (reservation.current)
            return;
        reservation.current = true;
        setBusy(true);
        setError('');
        setMessage('');
        try {
            await requestJson('/api/auth/logout', { method: 'POST', timeoutMs: 90000 });
            setCode(null);
            await refresh.current();
        }
        catch (cause) {
            setError(cause instanceof Error ? cause.message : 'Unable to sign out');
        }
        finally {
            setBusy(false);
            reservation.current = false;
        }
    }
    return <Context.Provider value={{ identity, tenant, subscription, setTenant, setSubscription, code, tool, busy, error, message, remaining, begin, logout }}>{children}</Context.Provider>;
}
