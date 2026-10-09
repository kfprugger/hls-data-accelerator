# Build context: HLS repo contents at the context root. Do not use the emulator root
# .dockerignore: Dockerfile.dockerignore beside this file is the runtime-only allowlist.
# WardFlow cardiology source comes from the pinned bundle image published by
# Deploy-HostedOrchestrator.ps1 -PublishWardflowBundle (hosted/sandbox/wardflow-bundle.Dockerfile).
# Example: docker build --platform linux/amd64 --build-arg WARDFLOW_BUNDLE_IMAGE=<acr>/hls-wardflow-bundle:<commit> -f hosted/sandbox/Dockerfile .
ARG WARDFLOW_BUNDLE_IMAGE
FROM ${WARDFLOW_BUNDLE_IMAGE} AS wardflow
FROM node:20-bookworm-slim AS node
FROM node AS ui
WORKDIR /ui
COPY orchestrator-ui/package*.json ./
RUN npm ci
COPY orchestrator-ui/ ./
RUN npm run build

FROM python:3.13-slim-bookworm
ARG TARGETARCH=amd64
ARG DATABRICKS_CLI_VERSION=0.278.0
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
    AZURE_EXTENSION_DIR=/opt/azure-cli-extensions AZURE_CORE_COLLECT_TELEMETRY=no \
    AZURE_CORE_LOGIN_EXPERIENCE_V2=off AZURE_BICEP_USE_BINARY_FROM_PATH=true \
    DATABRICKS_AUTH_TYPE=azure-cli WARDFLOW_ROOT=/app/wardflow
COPY --from=node /usr/local/ /usr/local/
# Node's yarn executable is a symlink into /opt, which /usr/local alone does not include.
COPY --from=node /opt/yarn-v1.22.22/ /opt/yarn-v1.22.22/
RUN test "$TARGETARCH" = amd64 \
 && apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg git bash jq unzip tar libicu72 libssl3 libgssapi-krb5-2 unixodbc \
 && curl -fsSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/microsoft.deb \
 && dpkg -i /tmp/microsoft.deb && rm /tmp/microsoft.deb \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/azure-cli.gpg \
 && echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/azure-cli.gpg] https://packages.microsoft.com/repos/azure-cli/ bookworm main' > /etc/apt/sources.list.d/azure-cli.list \
 && apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends powershell=7.6.6-1.deb azure-cli=2.91.0-1~bookworm msodbcsql18 \
 && rm -rf /var/lib/apt/lists/*
RUN yarn --version \
 && pwsh -NoProfile -NonInteractive -Command "\$ErrorActionPreference='Stop'; & yarn --version | Out-Null; if (\$LASTEXITCODE -ne 0) { throw 'Yarn cannot run in the viewer build pipeline' }"
# Only the Az modules the phase scripts use (Accounts, Resources, Storage), at the versions Az 16.4.0 bundles.
# The full Az rollup took over an hour to install from PSGallery inside ACR Tasks.
RUN pwsh -NoProfile -NonInteractive -Command "\$ErrorActionPreference='Stop'; foreach (\$m in @(@('Az.Accounts','5.5.3'), @('Az.Resources','10.2.1'), @('Az.Storage','9.7.2'))) { Install-PSResource -Name \$m[0] -Version \$m[1] -Repository PSGallery -Scope AllUsers -TrustRepository -AcceptLicense }; Import-Module Az.Accounts, Az.Resources, Az.Storage"
RUN az extension add --name authV2 --version 1.0.1 --yes \
 && az extension add --name automation --version 0.2.2 --yes \
 && az extension add --name microsoft-fabric --version 1.0.0b1 --allow-preview true --yes \
 && az extension add --name resource-graph --version 2.1.1 --yes \
 && az extension add --name containerapp --version 1.3.0b4 --allow-preview true --yes \
 && az bicep install --version v0.48.1 \
 && install /root/.azure/bin/bicep /usr/local/bin/bicep \
 && chmod -R a+rX /opt/azure-cli-extensions \
 && rm -rf /root/.azure
RUN curl -fsSL https://github.com/Azure/azure-storage-azcopy/releases/download/v10.32.8/azcopy_linux_amd64_10.32.8.tar.gz -o /tmp/azcopy.tar.gz \
 && mkdir /tmp/azcopy && tar -xzf /tmp/azcopy.tar.gz -C /tmp/azcopy --strip-components=1 \
 && install /tmp/azcopy/azcopy /usr/local/bin/azcopy \
 && curl -fsSL "https://github.com/databricks/cli/releases/download/v${DATABRICKS_CLI_VERSION}/databricks_cli_${DATABRICKS_CLI_VERSION}_linux_amd64.zip" -o /tmp/databricks.zip \
 && unzip /tmp/databricks.zip -d /tmp/databricks \
 && install /tmp/databricks/databricks /usr/local/bin/databricks \
 && rm -rf /tmp/azcopy* /tmp/databricks*
RUN useradd --create-home --uid 10001 --shell /bin/bash hls \
 && mkdir -p /app/hls-data-accelerator /app/wardflow /data \
 && chown -R hls:hls /app /data
# Keep the viewer deployer and its compatible OHIF pin reproducible; don't bootstrap moving toolkit main.
RUN git init /app/FabricDicomCohortingToolkit \
 && git -C /app/FabricDicomCohortingToolkit remote add origin https://github.com/kfprugger/FabricDicomCohortingToolkit.git \
 && git -C /app/FabricDicomCohortingToolkit fetch --depth 1 origin a7b04c54b8c799676371a36f603d83dcdec932b0 \
 && git -C /app/FabricDicomCohortingToolkit checkout --detach FETCH_HEAD \
 && test "$(git -C /app/FabricDicomCohortingToolkit rev-parse HEAD)" = a7b04c54b8c799676371a36f603d83dcdec932b0 \
 && chown -R hls:hls /app/FabricDicomCohortingToolkit
WORKDIR /app/hls-data-accelerator
COPY orchestrator/requirements.lock hosted/sandbox/addon-requirements.txt /tmp/requirements/
RUN python -m venv orchestrator/.venv \
 && orchestrator/.venv/bin/pip install --no-cache-dir --require-hashes --only-binary=:all: -r /tmp/requirements/requirements.lock \
 && orchestrator/.venv/bin/pip install --no-cache-dir -r /tmp/requirements/addon-requirements.txt \
 && rm -rf /tmp/requirements
# Copy only allowlisted runtime inputs.
COPY --chown=hls:hls . /app/hls-data-accelerator/
COPY --from=wardflow --chown=hls:hls /wardflow/ /app/wardflow/
RUN test -s /app/wardflow/.pinned-commit \
 && chmod +x hosted/sandbox/entrypoint.sh \
 && chown -R hls:hls orchestrator/.venv \
 && chown hls:hls /app/hls-data-accelerator/orchestrator
COPY --from=ui --chown=hls:hls /ui/dist /app/hls-data-accelerator/orchestrator-ui/dist
ENV HOME=/home/hls AZURE_CONFIG_DIR=/home/hls/.azure HLS_DATA_DIR=/data \
    PATH=/app/hls-data-accelerator/orchestrator/.venv/bin:$PATH
USER hls
WORKDIR /app/hls-data-accelerator/orchestrator
EXPOSE 7071
STOPSIGNAL SIGTERM
ENTRYPOINT ["/app/hls-data-accelerator/hosted/sandbox/entrypoint.sh"]
