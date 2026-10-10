import { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Chip, CircularProgress, Divider, Link, Stack, TextField, Typography } from '@mui/material';
import { useAuthentication } from '../AuthenticationState';
import { useAppState } from '../AppState';

export function HostedSignIn() {
    const auth = useAuthentication();
    const { authContext, refreshAuthContext } = useAppState();
    const [copyError, setCopyError] = useState('');
    const bottom = useRef<HTMLDivElement>(null);
    const followSignIn = useRef(false);
    useEffect(() => {
        if (!followSignIn.current) return;
        bottom.current?.scrollIntoView({ block: 'end', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
        if (!auth.busy) followSignIn.current = false;
    }, [auth.busy, auth.code?.session_id, auth.error, auth.message]);
    const disabled = auth.busy;
    return <Stack spacing={3}>
    <Box><Typography variant="overline">Portal account</Typography><Typography sx={{
        overflowWrap: 'anywhere'
    }}>{auth.identity?.email || 'Local operator'}</Typography></Box>
    <Alert severity="info">{auth.identity?.notice || 'Local deployment uses this machine’s Azure credentials.'}</Alert>
    <Box><Typography variant="overline">Deployment account</Typography><Typography sx={{
        overflowWrap: 'anywhere'
    }}>{authContext?.cli.user || authContext?.pwsh.user || 'Not signed in'}</Typography></Box>
    {authContext?.issues.map((issue, index) => <Alert key={`${issue}-${index}`} severity="warning">{issue}</Alert>)}
    <Divider />
    <TextField label="Deployment tenant ID" value={auth.tenant} disabled={disabled} onChange={event => auth.setTenant(event.target.value)} fullWidth/>
    <TextField label="Deployment subscription ID" value={auth.subscription} disabled={disabled} onChange={event => auth.setSubscription(event.target.value)} fullWidth/>
    {(['az', 'azps'] as const).map(tool => {
            const context = tool === 'az' ? authContext?.cli : authContext?.pwsh;
            const label = tool === 'az' ? 'Azure CLI' : 'Az PowerShell';
            return <Stack spacing={1} key={tool}>
        <Stack direction="row" sx={{
                alignItems: "center",
                justifyContent: "space-between"
            }}><Typography sx={{
                fontWeight: 600
            }}>{label}</Typography><Chip label={context?.loggedIn ? 'Signed in' : 'Sign-in required'} color={context?.loggedIn ? 'success' : 'warning'} size="small"/></Stack>
        <Typography variant="body2" sx={{
                overflowWrap: 'anywhere'
            }}>{context?.user || 'Separate credential cache'}</Typography>
        <Typography variant="caption" sx={{ overflowWrap: 'anywhere' }}>Tenant: {context?.tenantId || 'not signed in'} · Subscription: {context?.subscriptionName || context?.subscriptionId || 'not selected'}</Typography>
        {!context?.loggedIn && <Button variant="contained" disabled={disabled || !auth.tenant.trim() || !auth.subscription.trim()} onClick={() => { followSignIn.current = true; void auth.begin(tool); }}>Sign in to {label}</Button>}
      </Stack>;
        })}
    {auth.busy && <Stack direction="row" spacing={1} sx={{
        alignItems: "center"
    }}><CircularProgress size={20}/><Typography role="status">{auth.code ? 'Waiting for sign-in' : 'Requesting device code'}</Typography></Stack>}
    {auth.code && <Alert severity="info"><Stack spacing={1}>
      <Typography>Enter this code in Microsoft device sign-in:</Typography>
      <Typography component="strong" variant="h5" sx={{
            letterSpacing: 2
        }}>{auth.code.user_code}</Typography>
      <Button variant="outlined" onClick={() => { void navigator.clipboard.writeText(auth.code!.user_code).catch(() => setCopyError('Unable to copy. Select the code and copy it manually.')); }}>Copy code</Button>
      <Link href={auth.code.verification_uri} target="_blank" rel="noopener noreferrer">Open Microsoft device sign-in</Link>
      <Button variant="outlined" onClick={() => { followSignIn.current = true; void auth.reissue(); }}>Get a new code</Button>
      <Typography variant="caption">Use this if Microsoft rejects the code. It replaces only this pending sign-in and keeps the other tool’s login.</Typography>
      <Typography variant="body2">Expires in {Math.floor(auth.remaining / 60)}:{String(auth.remaining % 60).padStart(2, '0')}. You may hide this panel; sign-in continues.</Typography>
    </Stack></Alert>}
    {copyError && <Alert severity="warning">{copyError}</Alert>}
    {auth.error && <Alert severity="error">{auth.error}</Alert>}
    {auth.message && <Alert severity="success">{auth.message}</Alert>}
    <Button variant="outlined" disabled={disabled} onClick={() => void refreshAuthContext()}>Refresh sign-in status</Button>
    <Button color="error" disabled={disabled} onClick={() => void auth.logout()}>Sign out of Azure tools</Button>
    {auth.identity?.hosted && <Link href="/gateway/me">Manage private sandbox</Link>}
    <Box ref={bottom} aria-hidden="true" />
  </Stack>;
}
