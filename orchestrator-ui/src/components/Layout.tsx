import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AppBar, Alert, Box, Button, Chip, Drawer, IconButton, Stack, Toolbar, Typography, useMediaQuery } from '@mui/material';
import { Close, DarkMode, LightMode, Login, RocketLaunch, History, DeleteOutlined, FactCheck, MonitorHeart } from '@mui/icons-material';
import { useAppState } from '../AppState';
import { useAuthentication } from '../AuthenticationState';
import { HostedSignIn } from './HostedSignIn';

const destinations = [
    { path: '/deploy', label: 'Deploy', icon: <RocketLaunch /> },
    { path: '/preflight', label: 'Validate', icon: <FactCheck /> },
    { path: '/history', label: 'History', icon: <History /> },
    { path: '/teardown', label: 'Teardown', icon: <DeleteOutlined /> },
];
export function Layout() {
    const navigate = useNavigate();
    const location = useLocation();
    const state = useAppState();
    const auth = useAuthentication();
    const [open, setOpen] = useState(false);
    useEffect(() => {
      const show = () => setOpen(true);
      window.addEventListener('hls-open-authentication', show);
      return () => window.removeEventListener('hls-open-authentication', show);
    }, []);
    const phone = useMediaQuery('(max-width:599px)');
    const large = useMediaQuery('(min-width:1200px)');
    const ready = Boolean(state.authContext?.ready);
    const partial = Boolean(state.authContext?.cli.loggedIn || state.authContext?.pwsh.loggedIn);
    const status = auth.busy ? 'Signing in' : auth.error || (state.authContext?.cli.loggedIn && state.authContext?.pwsh.loggedIn && !ready) ? 'Needs attention' : ready ? 'Ready' : partial ? 'Partially connected' : 'Sign-in required';
    const subscription = state.subscriptions.find(item => item.id === state.selectedSubscription);
    const subscriptionName = subscription?.name || state.authContext?.cli.subscriptionName || 'No subscription selected';
    const subscriptionId = subscription?.id || state.authContext?.cli.subscriptionId || '';
    const tenant = subscription?.tenantId || state.authContext?.cli.tenantId || auth.tenant;
    const dark = localStorage.getItem('orchestrator-theme') === 'dark' || (!localStorage.getItem('orchestrator-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
    function toggleTheme() { localStorage.setItem('orchestrator-theme', dark ? 'light' : 'dark'); window.dispatchEvent(new Event('orchestrator-theme-change')); }
    const links = [...destinations];
    if (location.pathname.startsWith('/monitor/'))
        links.splice(2, 0, { path: location.pathname, label: 'Run detail', icon: <MonitorHeart /> });
    return <Box sx={{
        minHeight: '100dvh', bgcolor: 'background.default', color: 'text.primary'
    }}>
    <AppBar position="sticky" color="inherit" elevation={0} sx={{
        borderBottom: 1, borderColor: 'divider'
    }}>
      <Toolbar sx={{
        gap: 1.5, flexWrap: 'wrap', py: 1
    }}>
        <Typography component="h1" variant="h6" sx={{
        flexGrow: 1, fontSize: { xs: 18, md: 24 }
    }}>HLS Data Accelerator</Typography>
        <IconButton aria-label={dark ? 'Use light theme' : 'Use dark theme'} onClick={toggleTheme}>{dark ? <LightMode /> : <DarkMode />}</IconButton>
        <Button variant="contained" startIcon={<Login />} onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open} sx={{
        minWidth: { xs: '100%', sm: 'auto' }
    }}>Sandbox & sign-in · {status}</Button>
      </Toolbar>
      <Stack direction="row" spacing={1} sx={{
        px: { xs: 2, md: 3 }, pb: 1.5, flexWrap: 'wrap', rowGap: 1
    }}>
        <Chip variant="outlined" label={`Target: ${subscriptionName}`} onClick={() => setOpen(true)} sx={{
        maxWidth: '100%'
    }}/>
        <Typography variant="caption" sx={{
        alignSelf: 'center', overflowWrap: 'anywhere'
    }}>Tenant {tenant || 'not selected'} · Subscription {subscriptionId || 'not selected'}</Typography>
      </Stack>
    </AppBar>
    <Box sx={{
        display: 'flex', maxWidth: 1920, mx: 'auto'
    }}>
      <Box component="nav" aria-label="Main navigation" sx={{
        ...large ? { width: 160, flexShrink: 0, p: 2, position: 'sticky', top: 125, alignSelf: 'flex-start' } : { position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 1100, bgcolor: 'background.paper', borderTop: 1, borderColor: 'divider', display: 'flex', overflowX: 'auto', px: 1, pt: 1, pb: 'max(8px, env(safe-area-inset-bottom))' }
    }}>
        {links.map(item => <Button key={item.path} startIcon={large ? item.icon : undefined} variant={location.pathname.startsWith(item.path) ? 'contained' : 'text'} aria-current={location.pathname.startsWith(item.path) ? 'page' : undefined} onClick={() => navigate(item.path)} sx={{
        mb: large ? 1 : 0, width: large ? '100%' : 'auto', flex: large ? undefined : '1 0 auto', px: 1.5
    }}>{item.label}</Button>)}
      </Box>
      <Box component="main" sx={{
        flex: 1, minWidth: 0, p: { xs: 2, sm: 3, lg: 4 }, pb: large ? 4 : 12
    }}>
        {!ready && <Alert severity="warning" action={<Button onClick={() => setOpen(true)}>Connect</Button>} sx={{
        mb: 3
    }}>Connect your deployment credentials before validating or deploying. Your form remains available.</Alert>}
        <Outlet />
      </Box>
    </Box>
    <Drawer anchor="right" open={open} onClose={() => setOpen(false)} ModalProps={{ keepMounted: true }} slotProps={{ paper: { role: 'dialog', 'aria-modal': true, 'aria-labelledby': 'sandbox-flyout-title', sx: { width: phone ? '100%' : 480, maxWidth: '100vw', p: { xs: 2, sm: 3 }, paddingBottom: 'max(24px, env(safe-area-inset-bottom))' } } }}>
      <Stack direction="row" sx={{
        alignItems: "center",
        justifyContent: "space-between",
        mb: 3
    }}><Typography id="sandbox-flyout-title" variant="h6">Sandbox & sign-in</Typography><IconButton aria-label="Hide sign-in flyout" onClick={() => setOpen(false)}><Close /></IconButton></Stack>
      <HostedSignIn />
    </Drawer>
  </Box>;
}
