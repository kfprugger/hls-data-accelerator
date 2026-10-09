import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { requestJson, type AuthContext } from './api';
import { useAppState } from './AppState';
import { setHostedHistoryMode } from './formHistory';

type Tool = 'az' | 'azps';
interface Identity { hosted: boolean; email: string; oid: string; tid: string; notice: string }
interface Code { session_id: string; user_code: string; verification_uri: string; expires_in: number }
interface Status { status: 'pending' | 'succeeded' | 'failed'; error?: string; error_hint?: string }
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
    const [tenant, setTenant] = useState('');
    const [subscription, setSubscription] = useState('');
    const [code, setCode] = useState<Code | null>(null);
    const [tool, setTool] = useState<Tool | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const [remaining, setRemaining] = useState(0);
    const reservation = useRef(false);
    useEffect(() => {
        const controller = new AbortController();
        requestJson<Identity>('/api/hosted/whoami', { signal: controller.signal })
            .then(value => { setIdentity(value); setHostedHistoryMode(value.hosted); })
            .catch(cause => { if (!controller.signal.aborted)
            setError(cause instanceof Error ? cause.message : 'Unable to read sandbox identity'); });
        return () => controller.abort();
    }, []);
    useEffect(() => {
        setTenant(value => value || authContext?.cli.tenantId || authContext?.pwsh.tenantId || '');
        setSubscription(value => value || authContext?.cli.subscriptionId || authContext?.pwsh.subscriptionId || '');
    }, [authContext]);
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
