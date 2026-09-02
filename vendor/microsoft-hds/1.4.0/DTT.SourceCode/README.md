# DTT — Data Transformation Toolkit

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: TBD](https://img.shields.io/badge/License-TBD-lightgrey.svg)](#license)

DTT (Data Transformation Toolkit) is a **Spark-based Python toolkit** for building **spec-driven data transformation pipelines**, primarily for healthcare data workflows.

It enables you to:

- Compile configuration into transformation specifications (DTT + RMT specs)
- Execute data transformation workflows using Spark (DMF)
- Manage reference mappings and reference data pipelines (RMT)

DTT runs on **Microsoft Fabric**, **Azure Synapse**, or any **Apache Spark** environment.

---

## Table of Contents

- [Who is this for?](#who-is-this-for)
- [Architecture](#architecture)
- [Core Modules](#core-modules)
- [Getting Started](#getting-started)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Verify Prerequisites](#2-verify-prerequisites)
  - [3. Install Missing Prerequisites](#3-install-missing-prerequisites)
  - [4. Clone the Repository](#4-clone-the-repository)
  - [5. Set Up the Environment](#5-set-up-the-environment)
  - [6. Build & Install](#6-build--install)
  - [7. Verify Installation](#7-verify-installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## Who is this for?

- Data engineers working with Spark-based pipelines
- Teams implementing healthcare data transformation workflows
- Developers needing a spec-driven transformation framework

---

## Architecture

DTT follows a **spec-driven pipeline**. Configuration files are compiled into runnable specs, then executed by the DMF and RMT runtimes against Spark.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DTT (Data Transformation Toolkit)                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐      ┌─────────────────────┐      ┌──────────────┐  │
│  │  Configuration │      │   Configuration     │      │     Specs    │  │
│  │     Files      │ ───▶ │     Compiler        │ ───▶ │  (DTT + RMT) │  │
│  │ (JSON/YAML)    │      │  (validate, graph)  │      │    (JSON)    │  │
│  └────────────────┘      └─────────────────────┘      └──────┬───────┘  │
│                                                                │          │
│                            ┌───────────────────────────────────┤          │
│                            ▼                                   ▼          │
│                 ┌──────────────────┐              ┌──────────────────┐   │
│                 │    DMF Runtime   │              │    RMT Runtime   │   │
│                 │  (Data Mapping   │              │ (Reference       │   │
│                 │   Framework)     │              │  Mapping)        │   │
│                 │                  │              │                  │   │
│                 │ • Validate       │              │ • Create value   │   │
│                 │ • ID harmonize   │              │   mappings       │   │
│                 │ • Transform      │              │ • Manage refdata │   │
│                 │ • Write output   │              │ • Stage/author   │   │
│                 └────────┬─────────┘              └────────┬─────────┘   │
│                          │                                  │             │
│                          └────────────┬─────────────────────┘             │
│                                       ▼                                   │
│                        ┌──────────────────────────┐                       │
│                        │   Apache Spark Engine    │                       │
│                        │  (Fabric / Synapse /     │                       │
│                        │   Standalone Spark)      │                       │
│                        └──────────────┬───────────┘                       │
│                                       ▼                                   │
│                        ┌──────────────────────────┐                       │
│                        │        Outputs:          │                       │
│                        │ Transformed + Reference  │                       │
│                        │    Data (Delta Lake)     │                       │
│                        └──────────────────────────┘                       │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

Configuration inputs define behavior; specs act as execution contracts; DMF transforms data; RMT manages reference mappings.

---

## Core Modules

| Module | Purpose |
|---|---|
| **`common`** | Shared models, readers, processors, utilities, and exception hierarchy |
| **`configuration_compiler`** | Compiles configuration files into DTT/RMT JSON specifications |
| **`dmf`** | Data Mapping Framework — executes transformation workflows via Spark |
| **`rmt`** | Reference Mapping Toolkit — manages reference data tables and value mappings |

See the [Engineering Guide](wiki/dtt_engineering_guide.md#part-1--introduction--architecture) for the full module breakdown.

---

## Getting Started

Follow these steps in order. Every downstream section (Development, Usage, Validation) assumes this is complete.

### 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Python** | **3.10 or 3.11** | PySpark 3.4.x does not support Python 3.12+ |
| **PySpark** | 3.4.2 | Required for runtime and import validation |
| **Java** | 11 (recommended), 17, or 21 | Required by PySpark. Set `JAVA_HOME`. |
| **pip** | Latest | |
| **Make** | Any (Linux/macOS or WSL) | Makefile uses POSIX shell; not Windows-native |
| **Git** | Any | |

### 2. Verify Prerequisites

**Linux / macOS / WSL:**

```bash
python3.10 --version       # or python3.11 --version
java -version              # expect 11.x, 17.x, or 21.x
echo $JAVA_HOME
pip --version
make --version
git --version
```

**Windows PowerShell:**

```powershell
py -3.10 --version
java -version
$env:JAVA_HOME
pip --version
git --version
```

If any command fails, see step 3.

### 3. Install Missing Prerequisites

| OS | Python 3.10 | Java 11 | Make |
|---|---|---|---|
| **Ubuntu / Debian (incl. WSL)** | `sudo add-apt-repository ppa:deadsnakes/ppa -y && sudo apt update && sudo apt install python3.10 python3.10-venv -y` | `sudo apt install openjdk-11-jdk -y` | `sudo apt install make -y` |
| **macOS** | `brew install python@3.10` | `brew install openjdk@11` | Preinstalled (Xcode Command Line Tools) |
| **Windows** | [python.org installer](https://www.python.org/downloads/release/python-3100/) or `winget install Python.Python.3.10` | `winget install Microsoft.OpenJDK.11` or [Eclipse Temurin](https://adoptium.net/) | Use WSL or [GnuWin32 Make](http://gnuwin32.sourceforge.net/packages/make.htm) |

### 4. Clone the Repository

```bash
git clone <repo-url>
cd HDS.IndustryAI.DTT-Download
```

### 5. Set Up the Environment

**Linux / macOS / WSL:**

```bash
make setup
source .venv/bin/activate
pip install -r requirements/requirements.txt
pip install pyspark==3.4.2 delta-spark==2.4.0
```

> `make setup` creates `.venv/` and installs build tools only (`pip`, `setuptools`, `wheel`, `build`). Runtime dependencies are installed separately via `requirements.txt`.

**Windows PowerShell:**

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip setuptools wheel build
pip install -r requirements\requirements.txt
pip install pyspark==3.4.2 delta-spark==2.4.0
```

> The Makefile is **not compatible with Windows natively**. Use WSL, Git Bash, or the manual PowerShell commands above.

### 6. Build & Install

```bash
make build       # produces dist/dtt-0.3.2-py3-none-any.whl
make install     # force-reinstalls the wheel into .venv
```

Manual (Windows or without Make):

```bash
python -m build --wheel --outdir dist
pip install --force-reinstall dist/dtt-0.3.2-py3-none-any.whl
```

### 7. Verify Installation

```bash
python -c "import common; import configuration_compiler; import dmf; import rmt; print('DTT installed successfully!')"
```

---

## Usage

### Compile Configuration

```python
from pyspark.sql import SparkSession
from configuration_compiler.api import persist_dtt_spec, persist_rmt_spec

spark = SparkSession.builder.getOrCreate()
persist_dtt_spec(spark=spark, out_path="dtt_spec.json", ...)
persist_rmt_spec(spark=spark, out_path="rmt_spec.json", ...)
```

### Run DMF

```python
from dmf.runners.fabric.fabric_runner import FabricRunner
FabricRunner.run(spark=spark, transformation_spec_path="dtt_spec.json")
```

### Run RMT

```python
from rmt.runners.fabric_runner import FabricRunner
FabricRunner.create_reference_values_mapping(spark=spark, rmt_spec_path="rmt_spec.json", ...)
```

> **Note — Fabric/Synapse only:** `rmt.runners.fabric_runner` imports `notebookutils` at module load time, so this snippet **fails at the `import` statement** on a standalone workstation with `ImportError: NotebookUtilsFileSystemClient requires Azure Fabric or Synapse as runtime`. For local execution, use the underlying `rmt.runners.runner.Runner` class directly (supply your own file-system client) or run inside a Fabric/Synapse notebook.

For full parameter details and advanced workflows, see the [Engineering Guide — Part 5: Using DTT](wiki/dtt_engineering_guide.md#part-5--using-dtt).

---

## Project Structure

```
HDS.IndustryAI.DTT-Download/
├── src/                   # Core toolkit code (common, configuration_compiler, dmf, rmt)
├── requirements/          # Dependency files (runtime, dev, test, build, pre-commit)
├── scripts/               # Internal automation helpers
├── wiki/                  # Engineering documentation
├── setup.py               # Package metadata (name: dtt, version: 0.3.2)
└── Makefile               # Build automation
```

For the full tree with submodule details, see the [Engineering Guide — Project Structure](wiki/dtt_engineering_guide.md#project-structure).

---

## Troubleshooting

| Issue | Solution |
|---|---|
| PySpark not found | `pip install pyspark==3.4.2 delta-spark==2.4.0` |
| `JAVA_HOME` not set | Install Java 11+ and configure the environment variable |
| Python version error | Use Python 3.10 or 3.11 only |
| `make setup` creates a Python 3.12+ venv (PySpark will fail later) | The Makefile prefers 3.10/3.11 but falls back to newer versions if those aren't installed. Force the desired interpreter explicitly: `PYTHON_CMD=python3.10 make setup` (or install Python 3.10/3.11 via step 3). |
| `make lint` / `make lint-install` exit with *"pre-commit not installed"* | Run `pip install -r requirements/dev-requirements.txt` first. |
| `make` not found on Windows | Use WSL, Git Bash, or manual commands |
| Import errors for `notebookutils` / `mssparkutils` | Expected locally — these are Fabric/Synapse runtime-only |
| `ImportError: NotebookUtilsFileSystemClient requires Azure Fabric or Synapse as runtime` when importing `rmt.runners.fabric_runner` | `FabricRunner` eagerly imports Fabric-only modules. Run inside Fabric/Synapse, or use `rmt.runners.runner.Runner` with your own file-system client for local execution. |

Full troubleshooting matrix: see the [Engineering Guide — Troubleshooting](wiki/dtt_engineering_guide.md#troubleshooting).

---

## Known Limitations

- Requires PySpark 3.4.x (Python 3.10 or 3.11 only)
- Fabric/Synapse-specific modules (`notebookutils`, `mssparkutils`) are not available locally
- `rmt.runners.fabric_runner.FabricRunner` cannot be imported outside Fabric/Synapse (eager `notebookutils` import). Use `rmt.runners.runner.Runner` for local runs.
- Requires valid configuration files before execution
- The Makefile is POSIX-only (use WSL/Git Bash on Windows)

---

## License

Please refer to Microsoft license terms available here: https://go.microsoft.com/fwlink/?LinkId=2369925