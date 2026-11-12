# Public patient imaging in 2D, 3D and 4D on Microsoft Fabric (Rayfin)

A browser-based medical image viewer built as a [Project Rayfin](https://www.npmjs.com/package/@microsoft/rayfin-cli)
app on Microsoft Fabric. Gigapixel pathology slides and 3D/4D radiology volumes live in a **Fabric
Lakehouse** in *your* workspace and stream from OneLake straight into the browser, with no image
server in between.

> [!IMPORTANT]
> **For demonstration, education and research only.** This is not a medical device and must not be used for
> diagnosis, treatment or any clinical decision.
>
> **This repository hosts no data.** It contains only code, plus a few screenshots of the app for this README. Every image is downloaded by the setup
> pipeline directly from its original public publisher (listed under [Data sources](#data-sources)),
> under that publisher's licence, into your own Fabric Lakehouse.
>
> **Pull requests are welcome** to improve the viewer, the pipeline or this guide. See
> [Contributing](#contributing).

## Screenshots

| | |
|---|---|
| ![Pathology: invasive breast carcinoma (H&E) at 5×, with the plain-language explanation](docs/screenshots/pathology-he.jpg) | ![Pathology: 36-plex immunofluorescence of colorectal cancer, with marker switches](docs/screenshots/pathology-multiplex.jpg) |
| **Pathology:** gigapixel H&E slide with deep zoom and a plain-language explanation | **Multiplex immunofluorescence:** one colour per protein marker, switched on and off |
| ![3D: whole-body CT angiography with 107 labelled structures](docs/screenshots/ct-angiography-3d.jpg) | ![4D: breathing lungs rendered as glass around the tumour, airway and heart](docs/screenshots/breathing-lungs-4d.jpg) |
| **3D:** whole-body CT angiography with 107 labelled organs, vessels and bones | **4D:** breathing lungs as glass, with the tumour, airway and heart inside |
| ![3D: fetal face rebuilt from MRI](docs/screenshots/fetal-face-3d.jpg) | |
| **3D:** a fetal face rebuilt from MRI | |

The screenshots show public data credited under [Data attribution](#data-attribution): TCGA, HTAN (CC BY 4.0),
TotalSegmentator (CC BY 4.0), TCIA 4D-Lung (CC BY 3.0) and the KCL craniofacial fetal MRI atlas (CC0).

## What you get

Four tabs, with collapsible side panels and a light/dark theme:

| Tab | What it shows |
|---|---|
| **Overview** | What the app is, what image types it reads, where the data sits in the Lakehouse (live sizes), and every dataset with its licence and citation. |
| **Pathology** | 13 TCGA cancer slides (H&E) and a 36-plex immunofluorescence slide in an OpenSeadragon deep-zoom viewer: magnification presets, guided tour, scale bar, minimap, marker switches, shared pins and deep links. |
| **3D and 4D imaging** | NiiVue (WebGL 2): 3D volume rendering, MPR, single planes, rotating MIP, clip planes, colour transfer functions, layers (PET over CT, labelled anatomy), 4D playback and fibre tractography. |
| **Guide** | Plain-language explanations of every image, control and term, for viewers without medical training. |

| 3D/4D study | What makes it worth showing |
|---|---|
| Whole-body FDG PET/CT | PET (SUV) over CT, 54 tumour deposits, expert lesion masks, rotating MIP |
| Whole-body CT angiography | 107 organs, vessels, bones and muscles labelled in colour; bone-free arterial MIP |
| Visible Human Female, body and head | true-colour volumes from 5,186 cryosection photographs |
| Breathing lungs, 4D CT | ten breathing phases; lungs rendered as glass around the tumour, airway and heart |
| Brain wiring, DTI tractography | 33,000 colour-coded fibre pathways from 1,065 people |
| Fetal face and head | a fetal face in 3D from MRI, with 45 craniofacial landmarks |
| Fetal body growth, 22 to 38 weeks | the trunk with nine labelled organs, week by week |
| Fetal brain development, 21 to 36 weeks | a 0.5 mm MRI atlas: the cortex folds as the brain grows 6.6-fold |

---

## Setup guide for an AI agent

These steps are written so an AI coding agent (or a person) can take a fresh clone to a working app
in the user's own Fabric tenant. Run them in order from the repository root. Each step says what to
check before moving on.

### Step 0 — Ask the user (do not guess)

Ask these questions and wait for the answers before running anything that touches Fabric:

1. **What is the name of the Fabric workspace to deploy into?** It is used for the Lakehouse and the app.
2. **Does that workspace already exist?** If not, **which Fabric capacity should it use?** Step 4 lists
   the capacities the user can see. Any paid capacity (F2 or larger) or a trial works.
3. **Which datasets should be loaded?** The default is all of them (about 25 GB to download and
   37 GB to store in OneLake). The Visible Human Female alone is 16.5 GB; skipping it is the quickest
   way to cut time and space. See [Data sources](#data-sources).
4. Optionally, a Lakehouse name (default `imaging_lakehouse`) and an app item name (default `rayfin-imaging`).

Tell the user that signing in (steps 3 and 7) opens a browser window they must complete themselves.

### Step 1 — Check prerequisites

| Tool | Version | Check |
|---|---|---|
| Node.js | 20, 22 or 24 (the Rayfin CLI does not support other majors) | `node -v` |
| Python | 3.11 or newer | `python3 --version` |
| Azure CLI | any recent | `az version` |
| AzCopy | v10 | `azcopy --version` |
| Disk space | about 60 GB free for everything, about 25 GB without the Visible Human | |
| Fabric | a workspace on an **active** capacity; Fabric Apps (Rayfin) enabled in the tenant | |

The tenant setting **"Use short-lived user-delegated SAS tokens"** (Fabric admin portal, OneLake settings)
lets the browser stream straight from OneLake. Without it the app still works through a slower proxy
function. Ask a Fabric admin to enable it if it is off.

### Step 2 — Install dependencies

```bash
npm install
(cd rayfin/functions && npm install)
python3 -m venv .venv
.venv/bin/pip install -r pipeline/requirements.txt
```

Check that `npx rayfin --version` prints a version, and that `.venv/bin/python -c "import openslide, nibabel, idc_index"` exits cleanly.

### Step 3 — Sign in

```bash
az login                 # used by the setup script, AzCopy and the Lakehouse table loads
npx rayfin login         # used by `rayfin up`; opens a browser account picker
```

Use the same account for both. It must be able to create items in the target workspace (Admin, Member or Contributor).

### Step 4 — Prepare the workspace and Lakehouse

```bash
# Look first (read-only): shows the workspace, its capacity and whether the Lakehouse exists.
.venv/bin/python scripts/setup_fabric.py --workspace "<workspace name>" --dry-run

# Existing workspace:
.venv/bin/python scripts/setup_fabric.py --workspace "<workspace name>"

# New workspace (the error message from --dry-run lists the capacity IDs you can use):
.venv/bin/python scripts/setup_fabric.py --workspace "<workspace name>" --create --capacity-id <capacity GUID>
```

The script finds or creates the workspace and assigns a capacity if it has none. It then creates the
Lakehouse (`--lakehouse <name>` to change the name) and writes the IDs to two places:

- `fabric.env` at the repository root (git-ignored), read by every pipeline script
- the `<lakehouse-config>` block in `rayfin/functions/src/function_app.ts`, used by the deployed functions

If it reports that the capacity is paused, ask the user to resume it in the Azure portal, then run it again.

### Step 5 — Download the public data

Everything lands in `work/`, which is git-ignored. Downloads can be resumed: re-running skips files that already exist.

```bash
.venv/bin/python pipeline/download_slides.py                  # 13 TCGA H&E slides from the NCI GDC (about 1.6 GB)
.venv/bin/python pipeline/download_data.py all                # all other sources (about 23 GB)
# or choose: petct lung4d multiplex vhp tracts fetal
```

The whole-body CT angiography is fetched later by its builder (`build_totalseg.py`), which reads one
subject out of the Zenodo archive with HTTP range requests.

### Step 6 — Build, upload and register the data

```bash
# Pathology slides
.venv/bin/python pipeline/generate_tiles.py --raw work/raw --out work/lakehouse   # Deep Zoom tiles (minutes per slide)
.venv/bin/python pipeline/build_multiplex.py                                      # immunofluorescence marker pyramids
.venv/bin/python pipeline/generate_tiles.py --raw work/raw --out work/lakehouse --only none   # add it to the manifest
pipeline/upload_to_onelake.sh --raw
.venv/bin/python pipeline/register_catalog_table.py                               # Delta table `slides`

# 3D and 4D volumes: run the builders for the datasets you downloaded
.venv/bin/python pipeline/volumes/build_petct.py
.venv/bin/python pipeline/volumes/build_totalseg.py
.venv/bin/python pipeline/volumes/build_visible_human.py
.venv/bin/python pipeline/volumes/build_lung4d.py
.venv/bin/python pipeline/volumes/build_tractography.py
.venv/bin/python pipeline/volumes/build_fetal_face.py
.venv/bin/python pipeline/volumes/build_fetal_body.py
.venv/bin/python pipeline/volumes/build_fetal_atlas.py
.venv/bin/python pipeline/volumes/build_mip.py          # after PET/CT and CT angiography
.venv/bin/python pipeline/volumes/build_manifest.py
pipeline/volumes/upload_volumes.sh --raw
.venv/bin/python pipeline/volumes/register_volume_table.py                        # Delta table `volumes`
```

- **Builders:** skip the builder of any dataset you did not download. The manifest lists only studies that were built.
- **`--raw`:** this flag also copies the original files into `Files/raw/` for lineage. Leave it off to save space.
- **Check:** the Lakehouse in Fabric shows `Files/slides`, `Files/volumes`, `Files/manifest.json` and the `slides` and `volumes` tables.

### Step 7 — Deploy the app

```bash
npx rayfin up -w "<workspace name>" -y
```

This creates the Rayfin app item, its database (shared pins), the functions and the static site. Then:

- **Check:** the command ends with *"Your app is live at: https://…fabricapps.net"*. Give that URL to the user. It needs Fabric (Entra) sign-in.
- **`rayfin.yml`:** the first deploy appends the hosting URL to `rayfin/rayfin.yml` (`allowedRedirectUris`). Keep it locally, but don't commit it to a public fork.
- **Redeploying:** after a code change, run `npx rayfin up -w "<workspace name>" -y` again. Add `--exclude-services functions` when only the UI changed.

### Step 8 — Verify

Open the URL and sign in, then check each tab:

- **Overview:** lists the datasets and Lakehouse sizes.
- **Pathology:** each slide opens and zooms.
- **3D and 4D imaging:** each built study renders.

If a tab says it could not read the catalog, check two things:

- **IDs:** step 4 wrote the right IDs, and step 7 was run after step 4.
- **Access:** the deploying account (the app identity) can read the workspace.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `rayfin` errors about the Node version | Use Node 20, 22 or 24. |
| `CapacityNotActive` or "capacity is paused" | Resume the capacity in the Azure portal. |
| The functions log "Lakehouse not configured" | Run step 4, then redeploy (step 7). |
| Tiles load slowly through the proxy | Enable the tenant setting "Use short-lived user-delegated SAS tokens". |
| An IDC download fails | Re-run `download_data.py <dataset>`: it resumes. IDC data is served from public cloud buckets and needs no login. |
| Upload scripts say WORKSPACE_ID is not set | Run step 4, or export `WORKSPACE_ID` and `LAKEHOUSE_ID`. |

---

## Data sources

All data is public, de-identified and downloaded from its publisher at setup time. **This repository
contains none of it.** Every licence below allows reuse with attribution, including commercial use.
Check the current terms at each source before you rely on them.

| Dataset | Used for | Licence | Downloaded by | Size |
|---|---|---|---|---|
| [The Cancer Genome Atlas](https://portal.gdc.cancer.gov/) (NCI GDC, open access) | 13 H&E slides | NIH GDC open access, attribution | `download_slides.py` | 1.6 GB |
| [HTAN HMS CyCIF](https://portal.imaging.datacommons.cancer.gov/collections/htan_hms/) via NCI Imaging Data Commons | 36-plex immunofluorescence slide (8 markers shown) | CC BY 4.0 | `download_data.py multiplex` | 2.9 GB |
| [TCIA FDG-PET-CT-Lesions](https://doi.org/10.7937/gkr0-xv29) via IDC | whole-body PET/CT | CC BY 4.0 | `download_data.py petct` | 0.3 GB |
| [TotalSegmentator v2.0.1](https://zenodo.org/records/10047292) | CT angiography with 107 labels | CC BY 4.0 | `build_totalseg.py` | 0.1 GB |
| [NLM Visible Human Project](https://www.nlm.nih.gov/research/visible/) | Visible Human Female | Public domain (NLM terms) | `download_data.py vhp` | 16.5 GB |
| [TCIA 4D-Lung](https://doi.org/10.7937/K9/TCIA.2016.ELN8YGLE) via IDC | breathing 4D CT | CC BY 3.0 | `download_data.py lung4d` | 0.8 GB |
| [HCP1065 tractography atlas](https://brain.labsolver.org/hcp_trk_atlas.html) and [TemplateFlow](https://www.templateflow.org/) ICBM 2009a | tractography | CC BY-SA 4.0; ICBM template permissive with attribution | `download_data.py tracts` | 0.6 GB |
| [dHCP fetal brain atlas](https://gin.g-node.org/kcl_cdb/fetal_brain_mri_atlas) (King's College London) | fetal brain | CC0 | `download_data.py fetal` | 0.25 GB |
| [KCL 0.55T fetal body atlas](https://gin.g-node.org/kcl_cdb/055t_fetal_mri_atlases) | fetal body | CC0 | `download_data.py fetal` | 0.1 GB |
| [KCL craniofacial fetal atlas](https://gin.g-node.org/kcl_cdb/craniofacial_fetal_mri_atlas) | fetal face | CC0 | `download_data.py fetal` | 0.02 GB |

The exact series, instances and files are pinned in `pipeline/download_data.py`, `pipeline/slides.json`
and `pipeline/sources/`. Each dataset's citation is shown in the app (the study's About tab, and the Overview) and under
[Data attribution](#data-attribution).

## Open-source software

The app and pipeline use only open-source software:

- **Viewers:** [NiiVue](https://github.com/niivue/niivue) (BSD-2-Clause) and [OpenSeadragon](https://openseadragon.github.io/) (BSD-3-Clause).
- **UI:** React, React Router, Radix UI, shadcn/ui and Tailwind CSS (all MIT).
- **Fonts:** Fira Sans, Fira Sans Condensed and Fira Mono, via @fontsource (SIL OFL 1.1).
- **Fabric SDK:** the Rayfin SDK and CLI packages (`@microsoft/rayfin-*`, `@microsoft/fabric-user-data-functions`) are MIT-licensed on npm, as are the agent skills they generate under `.agents/skills/`.
- **Python pipeline:** OpenSlide (LGPL-2.1, used as an unmodified library), nibabel (MIT), SimpleITK (Apache-2.0), pydicom (MIT), NumPy, SciPy and pandas (BSD), Pillow (MIT-CMU), idc-index (MIT), remotezip (MIT), and the Azure SDKs (MIT).
- **Audit:** a licence audit of every installed npm package found only permissive licences: MIT, ISC, Apache-2.0, BSD, 0BSD, BlueOak, MPL-2.0, OFL-1.1, CC-BY-4.0 and Unlicense.

Running the app needs a **Microsoft Fabric** subscription, which is a commercial cloud service. This
repository contains no Microsoft proprietary code; it only calls Fabric's public APIs and SDKs.

This project's own code is released under the [MIT License](LICENSE).

## Contributing

Pull requests are welcome, whether new public datasets, viewer features, accessibility, pipeline
robustness or clearer docs. Please:

- **Data:** only add datasets that are public, need no login or data-use agreement, and whose licence
  allows reuse including commercial use (CC0, public domain, CC BY, CC BY-SA). No non-commercial
  (NC) or no-derivatives (ND) data.
- **Commits:** never commit images, derived data, workspace or Lakehouse IDs, hosting URLs or keys.
  `work/`, `fabric.env`, `rayfin/.env*` and `rayfin/.deployments.json` are ignored for this reason.
  Reset the `<lakehouse-config>` block in `function_app.ts` to its zero GUIDs before committing.
- **Plain-language notes:** add an explanation for any new slide or study in `src/content/guide.ts`.
- **Checks:** run `npx tsc -b` and `npm test` before opening the PR.

---

## How it works

```
Public sources (GDC, IDC, Zenodo, NLM, GIN, GitHub, TemplateFlow)
        │  pipeline/download_slides.py, pipeline/download_data.py
        ▼
work/  (local only)  ── pipeline/generate_tiles.py, build_multiplex.py, volumes/build_*.py
        │                → Deep Zoom pyramids, NIfTI volumes, TRK fibres, MIP sprites, manifests
        │  upload_to_onelake.sh, volumes/upload_volumes.sh (AzCopy)
        ▼
Fabric Lakehouse (your workspace)
   ├─ Files/slides/…, Files/manifest.json          slide tiles and catalog
   ├─ Files/volumes/…, Files/volumes/manifest.json volumes and catalog
   ├─ Files/raw/…                                  originals (optional, --raw)
   └─ Tables/slides, Tables/volumes                catalogs as Delta tables (SQL / Power BI)
        ▲
        │  Rayfin functions getSlideCatalog / getVolumeCatalog (app identity):
        │  read the manifests and sign 55-minute, read-only, folder-scoped OneLake SAS tokens
        ▼
Browser (Rayfin static hosting, Entra sign-in): React + OpenSeadragon + NiiVue
        └─ streams only the tiles and volumes in view straight from OneLake
           (fallback: the getTiles function proxies tiles if SAS is unavailable)
```

Shared pins are stored in the app's own database through Rayfin's data API, with row-level security
per author.

## Demo script (about 12 minutes)

1. **Overview**: one Lakehouse holds gigapixel slides and whole-body scans, all public data, served from OneLake.
2. **Pathology** › *Invasive Breast Carcinoma*: zoom from fat lobules to tumour cells at 40×. Press **Tour** on *Clear Cell Renal Carcinoma*.
3. Pin a region, then open the slide in a second browser to show the pin is shared.
4. *Colorectal Cancer, 36-plex CyCIF*: switch on **CD8a** and **CD68** to show immune cells in the tumour.
5. **3D and 4D imaging** › *Whole-body FDG PET/CT*: press **Spin**, then open **MIP** and **MPR**.
6. *Whole-body CT angiography*: untick **CT**, turn on **Clip**, then open **MIP** for the arteries.
7. *Breathing lungs, 4D CT*: glass lungs breathe around the tumour. Press **Spin**.
8. *Brain wiring*: rotate the fibres and switch bundle groups off in Details › Controls.
9. *Visible Human Female*: drag the clip slider through the body in true colour.
10. *Fetal face*, *Fetal body growth* and *Fetal brain development*: press **Play**.
11. **Guide**: the plain-language explanations for a non-clinical audience.

## Local development

```bash
npm run dev          # Rayfin local backend + Vite, with a mock sign-in
npx tsc -b && npm test
```

The local backend has no Lakehouse data. Use a deployed app to see images.

## Repo map

- `scripts/setup_fabric.py` – workspace, capacity and Lakehouse setup; writes `fabric.env` and the function config block
- `pipeline/` – downloads (`download_slides.py`, `download_data.py`), slide tiling, multiplex IF, uploads, Delta tables
- `pipeline/volumes/` – one `build_*.py` per 3D/4D study, MIP sprites, manifest, upload, Delta table
- `rayfin/rayfin.yml` – Rayfin config (Fabric SSO, data, functions, protected static hosting)
- `rayfin/functions/src/function_app.ts` – `getSlideCatalog`, `getVolumeCatalog`, `getTiles`
- `rayfin/data/SlidePin.ts` – shared pin entity
- `src/pages/` – Overview, Pathology, Volumes (3D and 4D) and Guide
- `src/components/SlideViewer.tsx`, `VolumeViewer.tsx`, `MipViewer.tsx` – OpenSeadragon, NiiVue and MIP viewers
- `src/content/guide.ts` – the plain-language text
- `AGENTS.md`, `.agents/skills/` – context for AI coding agents

## Data attribution

- **Pathology:** in whole or part based upon data generated by the [TCGA Research Network](https://www.cancer.gov/tcga), via the NCI Genomic Data Commons.
- **Multiplex IF:** Human Tumor Atlas Network (HTAN), HMS Tissue Atlas, CyCIF of colorectal cancer (CC BY 4.0), via the NCI Imaging Data Commons.
- **PET/CT:** Gatidis S, Kuestner T. *A whole-body FDG-PET/CT dataset with manually annotated tumor lesions (FDG-PET-CT-Lesions)*. The Cancer Imaging Archive, 2022. https://doi.org/10.7937/gkr0-xv29 (CC BY 4.0).
- **CT angiography:** Wasserthal J, et al. *TotalSegmentator*. Radiology: AI, 2023. https://doi.org/10.1148/ryai.230024; dataset https://zenodo.org/records/10047292 (CC BY 4.0).
- **Visible Human Female:** U.S. National Library of Medicine, Visible Human Project.
- **4D CT:** Hugo GD, Weiss E, Sleeman WC, et al. *Data from 4D Lung Imaging of NSCLC Patients*. The Cancer Imaging Archive, 2016. https://doi.org/10.7937/K9/TCIA.2016.ELN8YGLE (CC BY 3.0).
- **Tractography:**
  - Yeh FC. *Population-based tract-to-region connectome of the human brain and its hierarchical topology*. Nat Commun 13, 4933 (2022). https://doi.org/10.1038/s41467-022-32595-4 (CC BY-SA 4.0).
  - Data were provided in part by the Human Connectome Project, WU-Minn Consortium (1U54MH091657).
  - ICBM 2009a template via TemplateFlow.
- **Fetal brain:** Uus A, Kyriakopoulou V, Cordero Grande L, et al. *Multi-channel spatio-temporal MRI atlas of the normal fetal brain development from the developing Human Connectome Project*. G-Node, 2023. https://doi.org/10.12751/g-node.ysgsy1 (CC0). Tissue labels: Uus AU, et al. *BOUNTI*. eLife 12:RP88818 (2023).
- **Fetal body:** Uus A, Aviles Verdera J, Payette K, et al. *Normative growth models for T2w 0.55T fetal brain and body MRI*. ISMRM 2024, 0819 (CC0). Organ labels: Uus AU, Hall M, et al. Sci Rep 14, 6637 (2024). https://doi.org/10.1038/s41598-024-57087-x
- **Fetal face:** Matthew J, Uus A, De Souza L, et al. *Craniofacial phenotyping with fetal MRI*. BMC Med Imaging 24, 52 (2024). https://doi.org/10.1186/s12880-024-01230-7 (CC0).

For demonstration, education and research only. Not a medical device and not for diagnosis.
