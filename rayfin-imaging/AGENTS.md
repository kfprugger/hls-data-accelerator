# AGENTS.md

This project ships agent context: skills under `.agents/skills/` and MCP servers in `.mcp.json`. Load them before writing code.

**Setting the project up in someone's Fabric tenant?** Follow `README.md` → "Setup guide for an AI agent" step by step.
Ask the user for their Fabric workspace name first; never guess it and never reuse IDs from another tenant.

## Project

React + TypeScript (Vite) medical image viewer ("Rayfin Imaging") backed by **Project Rayfin**, with four tabs:
Overview, Pathology (OpenSeadragon deep zoom of H&E and multiplex immunofluorescence slides), 3D and 4D imaging
(NiiVue volume rendering, MPR, fusion, 4D playback, tractography, plus a sprite-based rotating MIP), and a plain-language
Guide for non-clinical viewers. The repository contains no image data: `pipeline/` downloads it from public sources.
Images live in a Fabric Lakehouse; `getSlideCatalog` and `getVolumeCatalog` read the manifests from OneLake as the
app identity and sign read-only, folder-scoped SAS tokens so the browser streams directly from OneLake. Shared pins
are stored in the `SlidePin` entity. Production auth is Fabric Entra SSO; local dev uses a mock sign-in flow.

## Repo map

- `src/` – React UI
- `src/components/ui/` – Radix-based UI components (shadcn)
- `src/components/` – App components (AppShell, SlideViewer, VolumeViewer, MipViewer, Panel, LakehouseImage, AuthPage)
- `src/hooks/` – React hooks (useCatalog / useVolumeCatalog, usePins, useTheme, AuthContext)
- `src/pages/` – Tabs (Overview, Pathology, Volumes, Guide) and AuthCallback
- `src/content/guide.ts` – Plain-language notes for laypeople, keyed by slide/study/layer/marker id; add an entry when a
  catalog item is added (missing ids fall back to the catalog description). Shown in the Guide tab, the "In plain
  words" panel section and control tooltips
- `scripts/setup_fabric.py` – finds/creates the workspace and Lakehouse, writes `fabric.env` and the
  `<lakehouse-config>` block in `rayfin/functions/src/function_app.ts`
- `pipeline/` – Python image pipeline: `download_slides.py` (TCGA), `download_data.py` (all other public sources),
  DZI tiling, multiplex IF, OneLake upload; `pipeline/volumes/` has one `build_*.py` per study (NIfTI, 4D NIfTI, TRK,
  MIP sprites), then `build_manifest.py` and `upload_volumes.sh`. IDs come from `fabric.env` via `fabric_config.py` /
  `fabric_env.sh`
- `src/services/` – Service layer (ServiceContainer, Rayfin services, auth services)
- `rayfin/rayfin.yml` – Rayfin configuration (auth, data, functions, static hosting)
- `rayfin/functions/` – Functions (`getSlideCatalog`, `getVolumeCatalog`, `getTiles`)
- `rayfin/data/` – Entities (export from `rayfin/data/schema.ts`)

## UI (Radix-based shadcn/ui)

This project uses **Radix-based UI components** styled with **Tailwind CSS v4**.

- UI components live in `src/components/ui/`
- Utility helper lives in `src/lib/utils.ts` (`cn`)
- Add a component: `npx shadcn@latest add <component>`

Key config/files:

- Global styles + Tailwind import: `src/styles/theme.css`
- Path alias `@/*` → `src/*`: `tsconfig.json`
- Vite plugins + alias: `vite.config.ts`
- shadcn registry/config: `components.json`

## Architecture

### Service Layer

- **ServiceContainer**: Singleton that initializes and provides access to services; auto-detects local vs. production and selects the appropriate auth service
- **RayfinClientService**: Manages the RayfinClient singleton instance
- **lib/catalog.ts**: Calls `getSlideCatalog`, builds OneLake tile URLs, batches `getTiles` proxy calls
- **lib/volumes.ts**: Calls `getVolumeCatalog`, builds signed OneLake URLs for NIfTI layers and timeline frames
- **usePins**: `SlidePin` CRUD via the DataApi fluent interface

### Auth Service Layer

- **RayfinAuthService**: Fabric Entra authentication operations (production)
- **RayfinFabricAuthService**: Delegates to `@microsoft/rayfin-auth-provider-fabric` SDK for Entra flows
- **MockAuthService**: Local development mock authentication (email/password via local backend)
- **AuthContext**: React context for auth state management

### Routing

- `/auth` – Public auth page (Fabric sign-in or mock sign-in; redirects to `/` if authenticated)
- `/auth/callback` – Fabric Entra OAuth callback
- `/` – Overview (legacy `/?slide=` links redirect to `/pathology`)
- `/pathology?slide=<id>` – slide list + viewer (optional `x`, `y`, `z` deep-link view)
- `/volumes?study=<id>&t=<frame>` – volume list + 3D/4D viewer
- `/guide#<section>` – plain-language guide (sections: pathology, markers, pathology-controls, views, volume-controls,
  images, licences, glossary)

### Key files

- `rayfin/data/SlidePin.ts` – Shared pin entity; authenticated read, author-only create/update/delete
- `rayfin/functions/src/function_app.ts` – OneLake catalog + SAS signing (app identity) and tile proxy. Workspace and
  Lakehouse IDs live only in its `<lakehouse-config>` block, which `scripts/setup_fabric.py` rewrites
- `src/components/SlideViewer.tsx` – OpenSeadragon viewer, tour, pins overlays; multiplex slides add one tiled image
  per marker (`compositeOperation: 'lighter'`, canvas drawer)
- `src/components/VolumeViewer.tsx` – NiiVue wrapper; studies are data-driven from `Files/volumes/manifest.json`.
  Layers with `frames4d` are one 4D NIfTI switched with `setFrame4D`; `tracts` layers load as meshes; colour presets
  may set `glass` (gradient opacity + silhouette)
- `src/components/MipViewer.tsx` – rotating MIP from the study's `mip` sprite sheet (NiiVue has no MIP mode)
- `src/services/ServiceContainer.ts` – Service initialization with auth-mode detection

## NiiVue notes

- Per-label alpha in a label colour table is ignored in 3D renders; use layer opacity or a CT transfer function.
- Label maps must be integer NIfTI, or 3D renders draw a box.
- An opaque background volume hides meshes (tracts) in 3D; such studies hide the T1 by default.
- The built-in `gray` colour map is only half opaque, so a clip shows a blurred blend of tissue behind the cut; the
  `mri_solid` map (MRI "Solid" preset) gives sharp cut faces. `isClipAllVolumes` is on so clips cut overlays too.
- Catalog data is cached per session; `VolumeViewer` reloads when a study's layer files change, not just its id.

## Environment

- `.env` – Default Fabric API configuration
- `.env.local` – Local overrides (git-ignored, generated by `rayfin dev`)
- `rayfin/.env` – Runtime + deployment env (managed by Rayfin CLI)
- `rayfin/.deployments.json` – Registry of all Fabric workspace deployments (managed by Rayfin CLI)

## Code conventions

- Data: never commit images or derived data (`work/` is git-ignored). Add only datasets that are public and whose
  licence allows reuse including commercial use (CC0, public domain, CC BY, CC BY-SA); no non-commercial (NC) or
  no-derivatives (ND) licences, nothing behind a login or data-use agreement. Credit each source in its `study.json`
  and in the README.
- Code: only open-source dependencies with permissive or weak-copyleft licences; nothing proprietary.
- Never commit tenant-specific values (workspace/lakehouse IDs, hosting URLs, keys). `fabric.env`, `rayfin/.env*` and
  `rayfin/.deployments.json` are git-ignored; reset the `<lakehouse-config>` block to its zero GUIDs before committing.
- TypeScript strict mode; prefer small functional React components.
- Keep UI logic in `src/`; keep data model code in `rayfin/data/`.
- Services follow the singleton pattern via `ServiceContainer`.
- `ServiceContainer` auto-selects `MockAuthService` for localhost backends and `RayfinAuthService` for production.

## Generated files (do not edit)

- `rayfin/.temp/` – Rayfin/DAB config generation output
- `dist/` – Vite build output
- `.env.local` – Local environment overrides (git-ignored, script-managed)
- `fabric.env` – Workspace/Lakehouse IDs written by `scripts/setup_fabric.py` (git-ignored)
