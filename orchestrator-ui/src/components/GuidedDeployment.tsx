import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Alert, Box, Button, Card, Chip, CircularProgress, Stack, Step, StepButton, Stepper, Typography } from '@mui/material';
import type { DeploymentConfig } from '../api';
import { useAppState } from '../AppState';

interface Check { name: string; status: string; message?: string; detail?: string }
interface Result { passed: boolean; checks: Check[]; failures: string[] }
const steps = ['Connect', 'Configure', 'Validate', 'Review', 'Deploy'];
const connect = () => window.dispatchEvent(new Event('hls-open-authentication'));

function TargetReview({ config }: { config: DeploymentConfig }) {
  const target = {
    Tenant: config.expected_tenant_id,
    Subscription: config.expected_subscription_id,
    'Resource group': config.resource_group_name,
    Region: config.location,
    'Fabric workspace': config.fabric_workspace_name,
    'Fabric capacity': config.capacity_name,
    'Capacity subscription': config.capacity_subscription_id,
    Patients: config.patient_count,
  };
  return <>
    <Alert severity="info">Changes will be made in the target below, not in the hosting tenant.</Alert>
    {Object.entries(target).map(([label, value]) => <Box key={label}>
      <Typography variant="overline">{label}</Typography>
      <Typography sx={{ overflowWrap: 'anywhere' }}>{String(value || 'Not selected')}</Typography>
    </Box>)}
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
      <Chip label="Fabric foundation" />
      {config.deploy_databricks && <Chip label="Databricks" />}
      {config.deploy_rayfin_apps && <Chip label="Rayfin apps" />}
      {config.deploy_cardiology && <Chip label="Cardiology" />}
    </Stack>
  </>;
}

export function GuidedDeployment({ children, config, errors, starting, onStart }: {
  children: ReactNode;
  config: DeploymentConfig;
  errors: string[];
  starting: boolean;
  onStart: () => Promise<void>;
}) {
  const { authContext } = useAppState();
  const [step, setStep] = useState(1);
  const [result, setResult] = useState<Result | null>(null);
  const [validated, setValidated] = useState('');
  const [confirmed, setConfirmed] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const fingerprint = JSON.stringify(config);
  const authenticationKey = JSON.stringify({ cli: authContext?.cli, pwsh: authContext?.pwsh, aligned: authContext?.aligned, ready: authContext?.ready });
  const validationKey = JSON.stringify({ fingerprint, authenticationKey });
  const latestValidation = useRef(validationKey);
  latestValidation.current = validationKey;
  const controller = useRef<AbortController | null>(null);
  const ready = Boolean(authContext?.ready);
  const canDeploy = Boolean(ready && errors.length === 0 && result?.passed && validated === validationKey);

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { setValidated(''); setConfirmed(''); setResult(null); }, [authenticationKey, fingerprint]);

  async function validate() {
    controller.current?.abort();
    const requestController = new AbortController();
    controller.current = requestController;
    const signal = requestController.signal;
    setBusy(true);
    setError('');
    setResult(null);
    setConfirmed('');
    const timer = setTimeout(() => requestController.abort(), 300000);
    try {
      const response = await fetch('/api/deploy/preflight', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: fingerprint, signal,
      });
      const body = await response.json();
      if (!Array.isArray(body.checks)) throw new Error(body.detail || body.error || 'Preflight returned an invalid response');
      if (response.status !== 422 && !response.ok) throw new Error('Preflight failed; retry after checking the connection.');
      if (latestValidation.current !== validationKey) throw new Error('Configuration or deployment credentials changed during preflight. Validate again.');
      setResult({ ...body, failures: Array.isArray(body.failures) ? body.failures : [], passed: response.ok && body.passed === true });
      setValidated(validationKey);
    } catch (cause) {
      setError(signal.aborted ? 'Validation was cancelled or timed out. Retry when the backend is available.' : cause instanceof Error ? cause.message : 'Unable to validate');
    } finally {
      clearTimeout(timer);
      setBusy(false);
    }
  }

  return <Stack spacing={3}>
    <Typography variant="h5" component="h2">New deployment</Typography>
    <Stepper nonLinear activeStep={step} alternativeLabel sx={{ overflowX: 'auto', '& .MuiStep-root': { minWidth: 72 }, '& .MuiStepLabel-label': { fontSize: { xs: 11, sm: 14 } } }}>
      {steps.map((name, index) => <Step key={name} completed={index === 0 ? ready : index === 2 ? canDeploy : false}>
        <StepButton disabled={starting || busy || (index === 4 && (!canDeploy || confirmed !== validationKey))} onClick={() => setStep(index)}>{name}</StepButton>
      </Step>)}
    </Stepper>

    {step === 0 && <Card><Stack spacing={2}>
      <Typography variant="h6">Connect your deployment account</Typography>
      <Typography>The portal account owns the sandbox; Azure CLI and PowerShell supply the permissions used for deployment. Both must target the same tenant and subscription.</Typography>
      <Chip label={ready ? 'Both tools ready' : 'Connections need attention'} color={ready ? 'success' : 'warning'} />
      <Button variant="contained" onClick={connect}>Open Sandbox & sign-in</Button>
      <Button onClick={() => setStep(1)}>Configure deployment</Button>
    </Stack></Card>}

    <Box hidden={step !== 1}>{children}</Box>
    {step === 1 && <Button variant="contained" onClick={() => setStep(2)}>Continue to validation</Button>}

    {step === 2 && <Card><Stack spacing={2}>
      <Typography variant="h6">Validate prerequisites</Typography>
      {!ready && <Alert severity="warning" action={<Button onClick={connect}>Connect</Button>}>Both Azure tools must be signed in before validating.</Alert>}
      {errors.length > 0 && <Alert severity="warning">
        <Typography>Fix these configuration fields:</Typography>
        <ul>{errors.map(message => <li key={message}>{message}</li>)}</ul>
        <Button onClick={() => setStep(1)}>Return to configuration</Button>
      </Alert>}
      <Button variant="contained" disabled={!ready || errors.length > 0 || busy} onClick={() => void validate()}>{busy ? 'Validating…' : 'Run preflight'}</Button>
      {busy && <CircularProgress size={24} aria-label="Checking deployment prerequisites" />}
      {error && <Alert severity="error">{error}</Alert>}
      {result?.checks.map((check, index) => <Alert key={check.name + index} severity={check.status === 'pass' ? 'success' : check.status === 'fail' ? 'error' : 'warning'}>
        <strong>{check.name}</strong> — {check.message || check.detail}
      </Alert>)}
      {result?.failures.map((failure, index) => <Alert key={`${failure}-${index}`} severity="error">{failure}</Alert>)}
      {result && validated !== validationKey && <Alert severity="warning">Configuration or credentials changed. Run preflight again.</Alert>}
      <Button disabled={!canDeploy || busy} onClick={() => setStep(3)}>Continue to review</Button>
    </Stack></Card>}

    {(step === 3 || step === 4) && <Card><Stack spacing={2}>
      <Typography variant="h6">{step === 3 ? 'Review deployment target' : 'Deploy reviewed configuration'}</Typography>
      <TargetReview config={config} />
      {!canDeploy && <Alert severity="warning">
        Validate this exact configuration and its credentials before deploying.
        <Button onClick={() => setStep(2)}>Go to validation</Button>
      </Alert>}
      {step === 3
        ? <Button variant="contained" disabled={!canDeploy} onClick={() => { setConfirmed(validationKey); setStep(4); }}>Confirm review</Button>
        : <Button variant="contained" disabled={!canDeploy || confirmed !== validationKey || starting} onClick={() => void onStart()}>{starting ? 'Starting deployment…' : 'Deploy to this subscription'}</Button>}
    </Stack></Card>}
    {step > 0 && <Button disabled={starting || busy} onClick={() => setStep(step - 1)}>Back</Button>}
  </Stack>;
}
