# Build the full pinned viewer outside the credential-bearing 4 GiB runtime sandbox.
FROM node:20-bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /viewer
RUN git init . \
 && git remote add origin https://github.com/OHIF/Viewers.git \
 && git fetch --depth 1 origin 9a2d2c3d136725b2b322a47340ecf684e55dd253 \
 && git checkout --detach FETCH_HEAD \
 && test "$(git rev-parse HEAD)" = 9a2d2c3d136725b2b322a47340ecf684e55dd253
RUN git init /toolkit \
 && git -C /toolkit remote add origin https://github.com/kfprugger/FabricDicomCohortingToolkit.git \
 && git -C /toolkit fetch --depth 1 origin a7b04c54b8c799676371a36f603d83dcdec932b0 \
 && git -C /toolkit checkout --detach FETCH_HEAD \
 && cp /toolkit/dicom-viewer/ohif/app-config.js platform/app/public/config/default.js
RUN yarn install --frozen-lockfile
WORKDIR /viewer/platform/app
RUN NODE_ENV=production node --max_old_space_size=8096 ../../node_modules/webpack/bin/webpack.js --config .webpack/webpack.pwa.js \
 && test -s dist/index.html \
 && printf '%s' 9a2d2c3d136725b2b322a47340ecf684e55dd253 > dist/.source-revision \
 && cp /toolkit/dicom-viewer/ohif/staticwebapp.config.json dist/staticwebapp.config.json
FROM scratch
COPY --from=build /viewer/platform/app/dist/ /viewer/
LABEL org.opencontainers.image.source="https://github.com/OHIF/Viewers" \
      org.opencontainers.image.revision="9a2d2c3d136725b2b322a47340ecf684e55dd253"
