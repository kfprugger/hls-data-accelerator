# DTT --- Engineering Guide

The **Developer Handbook** for the Data Transformation Toolkit (DTT).
Covers architecture, configuration, runtime APIs, test-kit APIs, testing, contributing, and CI/CD.

For a high-level user overview, see the [README](../README.md).

---

# Part 1 — Introduction & Architecture

## System Overview

DTT (Data Transformation Toolkit) is a spec-driven, Spark-based system that transforms source data into target models using configuration-driven execution.

It operates through:

- **Configuration inputs** — Adapter, EnvConfig, DBSemantics, Schema files
- **Spec compilation** — Configuration files are compiled into DTT and RMT JSON specs
- **Execution via DMF and RMT** — DMF runs data transformation; RMT manages reference mappings
- **Output generation** — Transformed data + reference data

DTT runs on **Microsoft Fabric**, **Azure Synapse Analytics**, or any **Apache Spark cluster**.

## DTT Common Library

DTT Common is a shared Python library that provides common utilities, processors, and readers for data source integration and transformation.

### Features

- **Data Readers** — Table, Query, and Storage readers for Spark data access
- **Column Processing** — Expression builders and column selectors for data transformation
- **Exception Handling** — Custom exception hierarchy for DTT components
- **Logging** — Azure Application Insights integration with custom logging utilities
- **Data Utilities** — DataFrame and Spark configuration utilities

## Project Structure

```
HDS.IndustryAI.DTT-Download/
├── src/                              # Source code (packaged as 'dtt' wheel)
│   ├── common/                       # Shared library
│   │   ├── model/                    #   Data models (ImmutableModel, configs, enums)
│   │   ├── reader/                   #   Data readers (TableReader, QueryReader, StorageReader)
│   │   ├── processor/                #   Base processors and transformation steps
│   │   ├── utils/                    #   Logging, DataFrame utils, Spark utils
│   │   └── exceptions/               #   Custom exception hierarchy
│   ├── configuration_compiler/       # Spec compilation engine
│   │   ├── api.py                    #   Public API (persist_dtt_spec, persist_rmt_spec, ...)
│   │   ├── validation/               #   Config validation logic
│   │   ├── graph/                    #   Dependency graph resolution
│   │   ├── runtime/                  #   Runtime compilation logic
│   │   ├── spec_models/              #   Pydantic models for specs
│   │   ├── config_files_models/      #   Pydantic models for config files
│   │   └── column_transformation/    #   Column-level transformation logic
│   ├── dmf/                          # Data Mapping Framework
│   │   ├── api/                       #   Public entry points
│   │   ├── workflow/                  #   DMFApplication — main orchestrator
│   │   ├── runners/                   #   FabricRunner for Spark/Fabric execution
│   │   ├── transformations/           #   Transformation implementations
│   │   ├── reference_values/          #   Reference value lookups
│   │   ├── ids_mapping/               #   ID harmonization logic
│   │   ├── last_processed_line_computer/  # Incremental-load bookkeeping
│   │   ├── model/                    #   DMF-specific data models
│   │   └── utils/                    #   DMF utilities
│   └── rmt/                          # Reference Mapping Toolkit
│       ├── runners/                  #   Runner, FabricRunner — RMT orchestrators
│       ├── app/                      #   Application entry points
│       ├── core/                     #   Core RMT logic
│       ├── file_model/               #   File-based data models
│       ├── filesystem/               #   File system abstraction
│       ├── source_processor/         #   Source data processing
│       ├── contract/                 #   Interface contracts
│       └── tools/                    #   RMT utility tools
├── requirements/                     # Dependency files (see Part 7)
├── scripts/
│   └── pr_pipeline.py                # Internal wheel-comparison helper
├── setup.py                          # Package configuration (name: dtt, version: 0.3.2)
└── Makefile                          # Build automation (see Part 7)
```

### Core Modules

| Module | Purpose |
|---|---|
| **`common`** | Shared models, readers, processors, utilities, and exception hierarchy |
| **`configuration_compiler`** | Compiles configuration files into DTT/RMT JSON specifications |
| **`dmf`** | Data Mapping Framework — executes transformation workflows via Spark |
| **`rmt`** | Reference Mapping Toolkit — manages reference data tables and value mappings |

---

# Part 2 — How DTT Works (Conceptual)

## Execution Model

End-to-end flow:

    Config Files → Spec Compilation → RMT → DMF → Output

Steps:

1. Load configuration files
2. Compile DTT and RMT specs
3. Execute RMT (reference mappings)
4. Execute DMF (data transformations)
5. Write outputs

**Data flow notes:**

- Source data is read via adapter configuration
- Data is transformed using compiled specs
- Outputs are written to target storage
- Secondary lake is used for reference data

## Configuration System

Core configuration inputs:

- **Adapter configuration** — defines source domain
- **EnvConfig** — defines data paths and types
- **DBSemantics** — defines reference tables and fields
- **Schema files** — define target structure

These act as the input contract controlling execution.

---

# Part 3 — Reference Mapping (RMT) Concepts

## Reference Mapping Tool (RMT)

RMT is a tool to create a reference mapping file (Delta) from one or more mapping definitions files.

### Reference Mapping File

The reference mapping file is consumed by DMF to transform source reference values into target reference values.

**Schema:**

    source_domain | source_value | target_table | target_field | target_value

| Field | Meaning |
|---|---|
| `source_domain` | Name of the source domain DMF will transform. Taken from the Adapter file of DMF. |
| `source_value` | Value in the source field that is mapped to a target reference table |
| `target_table` | Target reference table name |
| `target_field` | Target reference field name |
| `target_value` | Value in the target reference table matching `source_value` |

### Mapping Definitions File

Mapping definition files contain the input mapping definitions that RMT uses to create the reference mapping file.

- One file per target reference table. File name must match the target reference table name.
- JSON format.
- Each file contains **either** `values` **or** `query` — not both.

#### Values Mapping Definition File

`values`: list of mapping values. Each entry contains:

- `targetKey` — target key value (integer)
- `sourceKeys` — list of corresponding source values for that target value (integer or string)

Example — `Gender.json`:

```json
{
    "values": [
        { "targetKey": 1, "sourceKeys": [104800000, "male"] },
        { "targetKey": 2, "sourceKeys": [104800001] }
    ]
}
```

#### Query Mapping Definition File

`tables`: list of input delta files. Each entry contains:

- `path` — path for the input delta file
- `name` — name to be used in the SQL

`sql`: SQL query executed on input files. The query must return `source_value` and `target_value` columns.

Example — `concept.json`:

```json
{
    "Predefined": [
        {
            "tables": [
                { "name": "concept",              "path": "/tests/data/sample1/mapping_data/concept" },
                { "name": "concept_relationship", "path": "/tests/data/sample1/mapping_data/concept_relationship" },
                { "name": "vocabulary",           "path": "/tests/data/sample1/mapping_data/vocabulary" }
            ],
            "sql": "select cr.concept_id_2 as target_value, concat_ws('<->', c.concept_code, fv.Fhir_Uri) as source_value from concept c inner join vocabulary fv on c.vocabulary_id = fv.vocabulary_id left outer join concept_relationship cr on c.concept_id = cr.concept_id_1 and cr.relationship_id = 'Maps to' Union select c.concept_id as target_value, concat_ws('<->', c.concept_code, fv.Fhir_Uri, 'NH') as source_value from CONCEPT c inner join vocabulary fv on c.vocabulary_id = fv.vocabulary_id"
        }
    ]
}
```

The example produces rows like:

    source_domain = {app argument} | source_value | target_table = concept | target_field = conceptId (from DBSemantics) | target_value

---

# Part 4 — Environment Setup

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Python** | **3.10 or 3.11** | PySpark 3.4.x does not support Python 3.12+. The Makefile enforces `>=3.10, <4.0`. |
| **PySpark** | 3.4.2 | Required for runtime and import validation |
| **Java** | 11 (recommended), 17, or 21 | Required by PySpark. Set `JAVA_HOME`. |
| **pip** | Latest | |
| **Make** | Any (Linux/macOS or WSL) | The Makefile uses POSIX shell; not Windows-native. |
| **Git** | Any | |

## Getting Started

### Clone the Repository

```bash
git clone <repo-url>
cd HDS.IndustryAI.DTT-Download
```

### Set Up the Environment (Linux / macOS / WSL)

```bash
make setup
source .venv/bin/activate
pip install -r requirements/requirements.txt
pip install pyspark==3.4.2 delta-spark==2.4.0
```

`make setup` creates `.venv/` and upgrades `pip`, `setuptools`, `wheel`, and `build`. Runtime dependencies must be installed separately via `requirements.txt` (the Makefile does not install them automatically).

### Set Up the Environment (Windows PowerShell)

The Makefile is **not compatible with Windows natively**. Use manual steps:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip setuptools wheel build
pip install -r requirements\requirements.txt
pip install pyspark==3.4.2 delta-spark==2.4.0
```

### Verify Installation

```bash
python -c "import common; import configuration_compiler; import dmf; import rmt; print('DTT installed successfully!')"
```

## Development Environment (WSL)

Recommended setup when working in a Windows IDE with code cloned and running in WSL.

1. Install WSL on Windows — see the [Microsoft WSL install guide](https://docs.microsoft.com/en-us/windows/wsl/install).
2. Install Ubuntu 22.04 from the Microsoft Store (or `wsl --install -d ubuntu-22.04`). Use a Linux username matching your MSFT alias to avoid friction later.
3. In the Ubuntu terminal:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt upgrade
sudo apt install software-properties-common python3.10 python3.10-venv openjdk-11-jdk make -y

# verify
java --version        # openjdk 11.x
python3.10 --version  # Python 3.10.x

# clone and set up
git clone <repo-url>
cd <repo-name>
make setup
source .venv/bin/activate
pip install -r requirements/requirements.txt
pip install pyspark==3.4.2 delta-spark==2.4.0
```

---

# Part 5 — Using DTT

DTT exposes **two API surfaces**:

- **5.1 Runtime API** — the primary interface for running transformations in Fabric/Synapse/Spark environments.
- **5.2 Test-Kit API** — used from within the `dtt_test_kit` framework for writing end-to-end tests.

## 5.1 Runtime API

### Configuration Compiler (`configuration_compiler.api`)

Compile configuration files into transformation and mapping specs.

| Function | Description |
|---|---|
| `persist_dtt_spec(spark, out_path, ...)` | Generate and persist a DTT transformation spec |
| `persist_rmt_spec(spark, out_path, ...)` | Generate and persist an RMT reference mapping spec |
| `generate_dtt_specs(spark, dtt_spec_out_path, rmt_spec_out_path, ...)` | Convenience wrapper — generates both specs |
| `get_proposed_paths(...)` | Returns proposed mapping paths for a source-to-target field mapping |

Example:

```python
from pyspark.sql import SparkSession
from configuration_compiler.api import persist_dtt_spec, persist_rmt_spec, generate_dtt_specs

spark = SparkSession.builder.getOrCreate()

persist_dtt_spec(
    spark=spark,
    out_path="path/to/dtt_spec.json",
    dmf_adaptor_file_location="path/to/adaptor.json",
    target_db_semantics_file_location="path/to/semantics.json",
    target_db_semantics_config_file_location="path/to/semantics_config.json",
    target_db_schema_file_location="path/to/schema.json",
    db_schema_config_location="path/to/schema_config.json",
    env_config_file_location="path/to/env_config.json",
)

persist_rmt_spec(
    spark=spark,
    out_path="path/to/rmt_spec.json",
    adaptor_file_location="path/to/adaptor.json",
    target_db_semantics_file_location="path/to/semantics.json",
    target_db_schema_file_location="path/to/schema.json",
    db_schema_config_location="path/to/schema_config.json",
    env_config_file_location="path/to/env_config.json",
)

# Or generate both at once:
generate_dtt_specs(
    spark=spark,
    dtt_spec_out_path="path/to/dtt_spec.json",
    rmt_spec_out_path="path/to/rmt_spec.json",
    dmf_adaptor_file_location="path/to/adaptor.json",
    target_db_semantics_file_location="path/to/semantics.json",
    target_db_semantics_config_file_location="path/to/semantics_config.json",
    target_db_schema_file_location="path/to/schema.json",
    db_schema_config_location="path/to/schema_config.json",
    env_config_file_location="path/to/env_config.json",
)
```

### DMF — Data Mapping Framework

Runs data transformation workflows using a compiled DTT spec.

| Class / Method | Description |
|---|---|
| `dmf.runners.fabric.fabric_runner.FabricRunner.run(spark, transformation_spec_path)` | Execute a full DMF transformation workflow |
| `dmf.workflow.dmf_application.DMFApplication.start_with_transformation_spec_content(spark, content)` | Start DMF with spec content string (lower-level API) |

Example:

```python
from pyspark.sql import SparkSession
from dmf.runners.fabric.fabric_runner import FabricRunner

spark = SparkSession.builder.getOrCreate()
FabricRunner.run(
    spark=spark,
    transformation_spec_path="path/to/dtt_spec.json",
)
```

> **Note — Fabric/Synapse only:** `FabricRunner.run()` calls `RuntimeUtilities.is_runtime_environment()` and **exits silently with `sys.exit(0)`** when invoked outside Fabric/Synapse (logging `"FabricRunner should be executed from Fabric only"`). On a standalone workstation no transformation runs and no exception is raised. For local execution, call `DMFApplication.start_with_transformation_spec_content(spark, content)` directly.

**What DMF does under the hood:**

1. Parses the transformation spec
2. Validates source data against the schema
3. Performs ID harmonization (mapping source IDs to target IDs)
4. Applies column transformations
5. Processes and writes target data

### RMT — Reference Mapping Toolkit

Manage reference data tables and value mappings.

| Method | Description |
|---|---|
| `FabricRunner.create_reference_values_mapping(spark, rmt_spec_path, ...)` | Create reference value mappings from definitions |
| `FabricRunner.create_reference_data_tables(spark, rmt_spec_path, target_path, ...)` | Create reference data tables from source folders |
| `FabricRunner.update_staging_reference_data(spark, rmt_spec_path, ...)` | Update staging reference data from authoring data |
| `FabricRunner.generate_reference_data_authoring_files(spark, rmt_spec_path, ...)` | Generate authoring files from staging data |

Example:

```python
from pyspark.sql import SparkSession
from rmt.runners.fabric_runner import FabricRunner

spark = SparkSession.builder.getOrCreate()

# 1. Create reference value mappings
FabricRunner.create_reference_values_mapping(
    spark=spark,
    rmt_spec_path="path/to/rmt_spec.json",
    ordered_mapping_definitions_folders=["path/to/mapping_defs/"],
    staging_reference_data_folder_path="path/to/staging/",
)

# 2. Create reference data tables from source data
FabricRunner.create_reference_data_tables(
    spark=spark,
    rmt_spec_path="path/to/rmt_spec.json",
    target_path="path/to/output/",
    reference_tables_folders_paths=["path/to/reference_data_folder/"],
    staging_reference_data_folder_path="path/to/staging/",
)

# 3. Update staging reference data from authoring files
FabricRunner.update_staging_reference_data(
    spark=spark,
    rmt_spec_path="path/to/rmt_spec.json",
    authoring_folder_path="path/to/authoring/",
    staging_reference_data_folder_path="path/to/staging/",
)

# 4. Generate authoring files from staging data
FabricRunner.generate_reference_data_authoring_files(
    spark=spark,
    rmt_spec_path="path/to/rmt_spec.json",
    staging_reference_data_folder_path="path/to/staging/",
    target_authoring_folder_path="path/to/authoring_output/",
)
```

**RMT run parameters (detail):**

- `rmt_spec_path` *(mandatory)* — path to the compiled RMT spec JSON (produced by `configuration_compiler.api.persist_rmt_spec`). RMT reads the source domain, reference tables, and secondary-lake path from this spec.
- `ordered_mapping_definitions_folders` *(optional)* — list of folders containing mapping-definitions files. Order matters: if the same file name (= same reference table) appears in more than one folder, later entries take precedence.
- `staging_reference_data_folder_path` *(optional)* — folder where staging reference data is kept and/or updated.
- `number_of_partition_files` *(optional)* — defaults to `-1` (Spark default partition count).
- `target_path`, `reference_tables_folders_paths`, `authoring_folder_path`, `target_authoring_folder_path` — used only by the specific methods that accept them (see the method signatures above).

> The raw-config inputs (`Adapter.json`, `DBSemantics.json`, `EnvConfig.json`) are **not** passed directly to `FabricRunner`. They are consumed at spec-compilation time by `configuration_compiler.api.persist_rmt_spec`, and their relevant contents are baked into the `rmt_spec_path` JSON that `FabricRunner` then reads.

### Common Library (`common`)

| Sub-module | Description |
|---|---|
| `common.model` | Data models — `ImmutableModel`, `BaseDataFeedConfiguration`, `DataAccessDefinition`, enums |
| `common.reader` | Data readers — `ReaderFactory`, `TableReader`, `QueryReader`, `StorageReader` |
| `common.processor` | Base processors and transformation step helpers |
| `common.utils` | Logging (`Logger`, `IDTTLogger`), DataFrame utils, Spark utils |
| `common.exceptions` | Custom exception hierarchy for processors and steps |

> **Note:** All runtime examples require valid configuration/spec files and a running Spark environment.

---

## 5.2 Test-Kit API

The test-kit (`dtt_test_kit`) provides a higher-level `DTTApplication` wrapper used inside end-to-end tests. It is **separate from the runtime API above** — use the test-kit only when authoring tests in the E2E project.

### API Quick Reference

| Method | Subsystem | Purpose |
|---|---|---|
| `run_dmf()` | dmf | Execute DMF transformations |
| `run_rmt()` | rmt | Execute RMT reference mapping |
| `compile_dmf_spec()` | configuration | Compile transformation spec from configs |
| `compile_rmt_spec()` | configuration | Compile RMT spec from configs |
| `read_from_source()` | data | Read DataFrame from source |
| `read_from_target()` | data | Read DataFrame from target storage |
| `read_from_secondary_lake()` | data | Read DataFrame from secondary lake |

### DTTApplication Class

`DTTApplication` is composed of five sub-instances, each dedicated to a DTT component or helper:

1. **`dmf`** — executes the DMF.
   - `run_dmf(transformation_spec_path)`:
     - `transformation_spec_path` *(optional)* — pass if the test needs to compile the spec manually before execution. If omitted, the spec-compilation function is called automatically.
2. **`rmt`** — executes the RMT explicitly when needed.
   - `run_rmt(mapping_definitions_folders, rmt_spec_path, number_of_partition_files)`:
     - `mapping_definitions_folders` *(mandatory)* — list of mapping folder directories.
     - `rmt_spec_path` *(optional)* — pass if the test needs to compile the spec manually before execution.
     - `number_of_partition_files` *(optional)* — defaults to `-1` (Spark default).
3. **`configuration`** — manages configuration file access and compilation.
   - `compile_dmf_spec()` — compiles the transformation spec by reading configs from the test working directory and saving the spec there.
   - `compile_rmt_spec()` — compiles the RMT spec the same way.
   - `get_adapter_content()` — returns adapter content as a string.
   - `save_adapter(adapter_data)` — saves content to the adapter file.
   - `get_transformation_spec_config()` — returns the transformation spec as a `DataFeedConfiguration` model.
   - `set_env_config_data_source_path(data_source_path, table_name)` — sets source path in EnvConfig (table-specific optional).
   - `set_env_config_data_source_type(data_source_type, table_name)` — sets source type in EnvConfig.
   - `get_adapter_model()` — returns the adapter as a model.
   - `get_env_config_model()` — returns the env config as a model.
4. **`db`** — creates databases for sustainability tests.
   - `build_sus_dataverse_db()` — builds a sustainability-dataverse db using the name from conftest.
   - `build_sus_dataverse_temp_db()` — builds a temp db and copies source data into the test working directory.
   - `get_db_name()` — returns the db name.
5. **`data`** — reads DataFrames from source/target/secondary_lake by table name (paths are resolved from the configuration).
   - `read_from_source(table_name)` — reads from db/storage/query based on adapter config.
   - `read_from_target(table_name)` — reads from target path in EnvConfig.
   - `read_from_secondary_lake(table_name)` — reads from secondary_lake path in EnvConfig.

---

# Part 6 — Testing

## Testing Framework

**Test flow at a glance:**

1. Load configs
2. Compile specs
3. Run RMT
4. Run DMF
5. Validate outputs

### Fixtures

| Fixture | Scope | Auto-used | Purpose |
|---|---|---|---|
| `run_rmt_for_all_industries` | session | ✅ | Runs RMT and creates reference mapping for each industry |
| `clone_refdata_folders_locally` | session | ✅ | Clones Cloud Industries / Reference_tables folders locally |
| `dtt_app` | function | — | Returns a `DTTApplication` instance with config copied to test dir |
| `env_based_working_dir` | session | — | Absolute test directory path based on environment |
| `working_dir` | session | — | Relative test directory path |
| `spark` | session | — | Configured Spark instance |
| `configuration_storage` | session | — | Storage client depending on environment |

**Details:**

1. **`run_rmt_for_all_industries`** *(auto-used, session-scoped)* — runs RMT for each industry in the `mapping_data` folder; cleaned up at session end.
2. **`clone_refdata_folders_locally`** *(auto-used, session-scoped)* — copies Cloud Industries and Reference_tables folders from the local RefData repo to the E2E workspace folder when running locally.
3. **`dtt_app`** *(function-scoped)* — starts and returns a `DTTApplication` instance. Copies config files and generated reference mapping into each test directory. Takes two markers:
   - `adapter_dir_path` *(mandatory)*
   - `storage_data_source_path` *(optional)*
4. **`env_based_working_dir`** *(session-scoped)* — absolute test directory path based on environment.
5. **`working_dir`** *(session-scoped)* — relative test directory path.
6. **`spark`** *(session-scoped)* — configured Spark instance.
7. **`configuration_storage`** *(session-scoped)* — storage client based on environment.

### Writing Your First Test

Tests live in the `tests` directory. Each test is a regular Python test file.

1. Create a new file in `tests/` with prefix `test_***.py`.
2. Add the `dtt_app` fixture.
3. Add the pytest marker `adapter_dir_path` with an adapter path from the `DTTPaths` class. Required to resolve configuration files.
4. If the test needs to override the source data path, add the pytest marker `storage_data_source_path`.
5. Call `dtt_app.dmf.run_dmf()` to run the transformation.

Example — HLC test:

```python
import pytest

from dtt_test_kit.app.dtt_application import DTTApplication
from dtt_test_kit.utils.dtt_constants import DTTPaths


@pytest.mark.adapter_dir_path(DTTPaths.HLC_Clinical_Analytics_ADAPTER_DIR)
@pytest.mark.storage_data_source_path(DTTPaths.HLC_DATA_SOURCE_fhir_5)
def test_fhir_omop_scale_5(dtt_app: DTTApplication):
    # Act
    dtt_app.dmf.run_dmf()

    # Assert
    target_condition_occurrence = dtt_app.data.read_from_target("condition_occurrence")
    assert target_condition_occurrence.count() == 96
```

> **Note:** The main repo (`HDS.IndustryAI.DTT-Download`) does not currently ship a test suite. Test infrastructure (`pytest`, `pytest-cov`) is available via `requirements/test-requirements.txt` for future use. The test-kit API documented above is consumed by the separate E2E project.

---

# Part 7 — Contributing & Tooling

## Developer Workflow

New contributors:

1. Complete **[Part 4 — Environment Setup](#part-4--environment-setup)** first (creates `.venv` and installs build tools via `make setup`, plus runtime deps).
2. Install pre-commit git hooks:

```bash
make lint-install
```

3. Create a feature branch, make changes, run `make lint` before committing.

## Requirements Files

| File | Purpose |
|---|---|
| `requirements/requirements.txt` | Runtime dependencies |
| `requirements/dev-requirements.txt` | Full dev environment (runtime + test + lint) |
| `requirements/test-requirements.txt` | Test dependencies (`pytest`, `pyspark`, etc.) |
| `requirements/build-requirements.txt` | Build tools (`wheel`) |
| `requirements/pre-commit-requirements.txt` | Pre-commit hooks |

For development, install all dev dependencies:

```bash
pip install -r requirements/dev-requirements.txt
```

## Make Targets

> **Windows note:** The Makefile uses POSIX shell commands and is not compatible with Windows Command Prompt or PowerShell. Use WSL, Git Bash, or the manual commands shown in Part 4.

| Target | Purpose |
|---|---|
| `make help` | Show all available targets |
| `make setup` | Create `.venv` + install build tools (pip, setuptools, wheel, build) |
| `make build` | Build the wheel into `dist/` |
| `make install` | Install the built wheel into the venv |
| `make rebuild` | `clean` → `setup` → `build` (full clean rebuild) |
| `make clean` | Remove build artifacts; preserves venv |
| `make clean-all` | Remove build artifacts AND venv |
| `make reset` | `clean-all` → `setup` (full environment reset) |
| `make lint` | Run pre-commit checks on all files |
| `make lint-install` | Install pre-commit git hooks |

> `make setup` installs **build tooling only**, not runtime dependencies. After `make setup`, install runtime deps with `pip install -r requirements/requirements.txt` (plus PySpark and Delta as needed).

## Code Style

- **isort** — import sorting (line length: 180)
- **flake8** — style checking (max line length: 350, ignoring F811)
- **black** — available in `pre-commit-requirements.txt` but **not wired into `.pre-commit-config.yaml`**. Run manually (`black src/`) if desired; it is not enforced by `make lint`.
- **pre-commit** — automated checks on commit (currently: `pre-commit-hooks`, `flake8`, `isort`)

## Linting

```bash
# run pre-commit checks on all files
make lint

# run with an explicit pre-commit config
make lint PRE_COMMIT_CONFIG=.pre-commit-config.yaml
```

## Building the Package

```bash
make build
# output: dist/dtt-0.3.2-py3-none-any.whl

make install
# force-reinstalls the built wheel into .venv
```

Manual (Windows or without Make):

```bash
python -m build --wheel --outdir dist
pip install --force-reinstall dist/dtt-0.3.2-py3-none-any.whl
```

---

# Part 8 — Validation & CI/CD

## Local Validation

Validate a local build before opening a PR using the Make targets:

```bash
make rebuild        # clean → setup → build (full clean wheel build)
make install        # force-reinstall the built wheel into .venv
make lint           # run pre-commit checks on all files
```

Between them these targets cover: environment recreation, wheel build, wheel install, and code-style/static checks.

> An internal migration helper (`scripts/pr_pipeline.py`) exists for comparing wheel contents against a reference tree. It is **not part of the supported user workflow** and may be removed in a later release.

## PySpark Environment Variables

If Spark-backed code fails because PySpark can't find Python:

**Linux / macOS:**

```bash
export PYSPARK_PYTHON=$(pwd)/.venv/bin/python3
export PYSPARK_DRIVER_PYTHON=$(pwd)/.venv/bin/python3
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk
```

**Windows PowerShell:**

```powershell
$env:PYSPARK_PYTHON = "$(Get-Location)\.venv\Scripts\python.exe"
$env:PYSPARK_DRIVER_PYTHON = "$(Get-Location)\.venv\Scripts\python.exe"
$env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-11.0.x-hotspot"
```

## Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| `ModuleNotFoundError: No module named 'pyspark'` | PySpark not installed | `pip install pyspark==3.4.2` |
| `JAVA_HOME is not set` | Java not configured | Install Java 11+ and set `JAVA_HOME` |
| `java.lang.UnsupportedClassVersionError` | Wrong Java version | Use Java 11, 17, or 21 |
| Import errors for `notebookutils` / `mssparkutils` | Fabric/Synapse runtime-only modules | Expected locally; ignore for non-Fabric execution. |
| `No module named 'delta'` | Delta Lake not installed | `pip install delta-spark==2.4.0 deltalake==0.10.1` |
| Wheel build fails | Missing build tools | `pip install --upgrade build wheel setuptools` |
| `make` not found (Windows) | GNU Make not installed | Use WSL/Git Bash, or manual commands (Part 4) |
| Makefile errors on Windows | POSIX shell not available | Use WSL, Git Bash, or the manual Windows steps |
| `make setup` creates a Python 3.12+ venv | Makefile detection falls back past 3.10/3.11 | Override explicitly: `PYTHON_CMD=python3.10 make setup`. PySpark 3.4.x will fail at runtime on 3.12+. |
| `make lint` / `make lint-install` exit with *"pre-commit not installed"* | Dev dependencies not installed into the venv | `pip install -r requirements/dev-requirements.txt` before running lint targets. |
| `packaging` version conflict warning | `requirements.txt` pins `packaging==23.1` vs. `build`/`wheel` wanting `>=24.0` | Non-blocking warning; safe to ignore |
| Python 3.12+ / 3.14 errors | PySpark 3.4.x incompatible | Use Python 3.10 or 3.11 |

---

# Part 9 — Known Gaps

Areas not yet fully documented; to be filled in as understanding deepens:

- Performance characteristics
- Scaling limits
- Error handling strategy details
- Automated test suite for the main repo (currently tests live in the separate E2E project)
