#!/usr/bin/env node
// Register the actual static hosting origin on the active Rayfin deployment of the
// app in the current directory, without re-applying the data model.
//
// Usage (from the app root): node register_rayfin_hosting_origin.mjs https://<origin>
//
// `rayfin up staticapp deploy` performs this update only best-effort, and a full
// `rayfin up` re-applies the data model. This calls the installed CLI's own
// `updateHostingRedirectSettings`, which reads the workload's recorded runtime
// settings and posts them back with only `auth` (from rayfin.yml) and the deploy's
// package versions overlaid, then reads the settings back to confirm the origin.
// RAYFIN_TOKEN (Fabric audience) and RAYFIN_WORKSPACE_ID must be set; the token is
// never printed.
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { pathToFileURL } from 'node:url';

function fail(message) {
  console.error(`register hosting origin: ${message}`);
  process.exit(1);
}

const expected = process.argv[2];
if (process.argv.length !== 3 || !expected) fail('expected exactly one argument: the https hosting origin');
let parsed;
try {
  parsed = new URL(expected);
} catch {
  fail(`not a URL: ${expected}`);
}
if (parsed.protocol !== 'https:' || parsed.origin !== expected) fail(`not an exact https origin: ${expected}`);
if (!process.env.RAYFIN_TOKEN) fail('RAYFIN_TOKEN is not set');
const workspaceId = process.env.RAYFIN_WORKSPACE_ID;
if (!workspaceId) fail('RAYFIN_WORKSPACE_ID is not set');

// The CLI's package exports only its entry points; load the helpers from the
// version installed for this app.
const cliRoot = dirname(createRequire(join(process.cwd(), 'package.json')).resolve('@microsoft/rayfin-cli/package.json'));
const load = (path) => import(pathToFileURL(join(cliRoot, 'dist', path)).href);

try {
  const [staticapp, remote, envFabric, config, versions, constants, project, hosting, http] = await Promise.all([
    load('commands/up/up-staticapp.js'),
    load('utils/remote-endpoint-utils.js'),
    load('utils/env-fabric-utils.js'),
    load('utils/config-utils.js'),
    load('utils/package-versions.js'),
    load('config/constants.js'),
    load('utils/project-utils.js'),
    load('utils/hosting-url-utils.js'),
    load('utils/http-client.js'),
  ]);
  const functions = {
    updateHostingRedirectSettings: staticapp.updateHostingRedirectSettings,
    getActiveDeploymentEnvVars: remote.getActiveDeploymentEnvVars,
    getRemoteRuntimeSettingsUrl: remote.getRemoteRuntimeSettingsUrl,
    getRemoteAuthorizationHeader: remote.getRemoteAuthorizationHeader,
    resolveDeploymentEnvFile: envFabric.resolveDeploymentEnvFile,
    loadRayfinConfig: config.loadRayfinConfig,
    resolveDeclaredPackageVersions: versions.resolveDeclaredPackageVersions,
    findRayfinProjectRoot: project.findRayfinProjectRoot,
    addAllowedRedirectUri: hosting.addAllowedRedirectUri,
    fabricFetch: http.fabricFetch,
    throwIfNotOk: http.throwIfNotOk,
  };
  for (const [name, value] of Object.entries(functions)) {
    if (typeof value !== 'function') fail(`installed Rayfin CLI does not provide ${name}`);
  }
  if (!constants.MONIKER_HEADER) fail('installed Rayfin CLI does not provide MONIKER_HEADER');

  // Target: the registry deployment `up staticapp deploy` uses, which must also be the
  // one the settings URL is built from, in the caller's workspace, serving this origin.
  const projectRoot = functions.findRayfinProjectRoot(process.cwd(), { verbose: false, silent: true });
  const deployment = (await functions.resolveDeploymentEnvFile({ projectRoot, nonInteractive: true }))?.deployment;
  const active = functions.getActiveDeploymentEnvVars();
  if (!deployment?.rayfinItemId || !deployment.fabricWorkspaceId) fail('no deployed Rayfin item in rayfin/.deployments.json');
  if (!active || active.rayfinItemId !== deployment.rayfinItemId || active.fabricWorkspaceId !== deployment.fabricWorkspaceId) {
    fail('registry deployment and runtime settings target differ');
  }
  if (deployment.fabricWorkspaceId !== workspaceId) fail('active deployment is not in RAYFIN_WORKSPACE_ID');
  if (!deployment.hostingUrl || new URL(deployment.hostingUrl).origin !== expected) {
    fail(`active deployment does not record hosting origin ${expected}`);
  }

  const rayfinConfig = functions.loadRayfinConfig(projectRoot, { silent: true });
  const services = rayfinConfig?.services;
  if (!Array.isArray(services?.auth?.allowedRedirectUris)) fail('rayfin.yml has no services.auth.allowedRedirectUris');
  if (functions.addAllowedRedirectUri(services, expected) !== services) fail(`rayfin.yml allowedRedirectUris does not include ${expected}`);

  const settingsUrl = functions.getRemoteRuntimeSettingsUrl();
  if (!settingsUrl) fail('could not resolve the runtime settings endpoint');
  const headers = {
    Authorization: await functions.getRemoteAuthorizationHeader(),
    'Content-Type': 'application/json',
    [constants.MONIKER_HEADER]: deployment.rayfinItemId,
  };
  await functions.updateHostingRedirectSettings({
    settingsUrl,
    headers,
    updatedServices: services,
    packageVersions: functions.resolveDeclaredPackageVersions(projectRoot, services),
  });

  const recorded = JSON.parse(await functions.throwIfNotOk(
    await functions.fabricFetch(settingsUrl, { headers }),
    'Runtime settings read-back failed',
  )).serviceSettings;
  if (!Array.isArray(recorded?.auth?.allowedRedirectUris) || functions.addAllowedRedirectUri(recorded, expected) !== recorded) {
    fail(`runtime settings do not list ${expected} after the update`);
  }
  console.log(`Registered hosting origin ${expected}`);
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}
