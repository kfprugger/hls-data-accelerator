# 013: Patient 360 Data Agent Live Fix — Root Cause Analysis & Notes

## Root Cause Analysis (FR-1 / E-1)

### 1. Root Cause of `invalid_prompt` on Assistants API
In `scripts/verify_data_agent_qa.py` (added during ticket 005), the query execution method `execute_query` called the Fabric Data Agent OpenAI Assistants endpoint:
- Endpoint: `/v1/workspaces/{ws_id}/dataagents/{agent_id}/aiassistant/openai`
- In the initial implementation, `verify_data_agent_qa.py` attempted to create a run via `POST /threads/{th_id}/runs` passing the Fabric Data Agent UUID as `assistant_id`: `{"assistant_id": agent_id}` without resolving the underlying Azure OpenAI Assistant resource via `POST /assistants`.
- Furthermore, the required header `OpenAI-Beta: assistants=v2` and query parameter `stage=production` were omitted.
- Because `assistant_id` was not an Azure OpenAI Assistant identifier (it was a raw Fabric UUID) and headers were missing, Azure OpenAI Assistants API rejected the run creation with HTTP 400 BadRequest:
```json
{
  "run_status": "failed",
  "last_error": {
    "code": "invalid_prompt",
    "message": "Status code BadRequest: OpenAI request to 'openai/threads/thread_VNKGnphaZg2MYqdbdyQuz7l9/runs' failed."
  }
}
```
- This failure manifested immediately after tool steps `analyze.database.fewshots.loading` because the initial run setup on the unauthenticated/unresolved assistant failed when invoking downstream model inference.
- Resolving the assistant first via `POST /assistants` (with `params={"api-version": "2024-05-01-preview", "stage": "production"}` and `OpenAI-Beta: assistants=v2`) obtains the real Azure OpenAI assistant ID (`asst_O4lAFKQYAyiv6guApNZqI3CC`), allowing the run to execute, evaluate few-shots, generate SQL via `analyze.database.nl2code`, and execute the query via `analyze.database.execute`.

### 2. Root Cause of Missing Marcus Vance Diagnosis
In `phase-2/deploy-data-agents.ps1`:
- The Lakehouse data source instructions and 16 few-shots in `Files/Config/published/lakehouse-tables-healthcare1_msft_silver/fewshots.json` were strictly focused on the 100 Synthea device-monitored patients linked via `dbo.Basic` (`WHERE JSON_VALUE(code_string, '$.coding[0].code') = 'device-assoc'`).
- The instructions instructed the agent:
  `You can get patient name directly from subject_string display field WITHOUT joining to dbo.Patient!`
- When demo presenters asked about TCGA oncology research patients (such as Marcus Vance), the agent attempted to find the patient name in `Condition.subject_string.display` or `Basic.subject_string.display`. But in FHIR HDS Silver Lakehouse:
  - `dbo.Patient`: holds all 115 patients, with patient names in `name_string` (`[{"text": "Marcus Vance", ...}]`).
  - `dbo.Condition`: holds conditions (including Marcus Vance's Clear cell renal cell carcinoma `C46.9`), with `subject_string.display = null`.
- Without explicit instructions or few-shots showing how to join `dbo.Patient` to `dbo.Condition` on `p.idOrig = COALESCE(REPLACE(NULLIF(JSON_VALUE(c.subject_string, '$.msftSourceReference'), ''), 'Patient/', ''), NULLIF(JSON_VALUE(c.subject_string, '$.idOrig'), ''))` filtered by `p.name_string LIKE '%Marcus%' AND p.name_string LIKE '%Vance%'`, the agent failed to find Marcus Vance.

### 3. Draft Test Evidence (Before vs After)

#### Before Fix
Command:
```bash
AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL HLS_BIND_INTERFACE=en0 python scripts/verify_data_agent_qa.py --query "How many distinct patients are in the Patient table?" --json
```
Raw Output:
```json
{
  "question": "How many distinct patients are in the Patient table?",
  "answer": "",
  "generatedQuery": "",
  "queryLanguage": "",
  "execution_time_ms": 13938,
  "is_error": true,
  "error": "no query text in run steps",
  "raw_steps": {
    "object": "list",
    "data": [
      {
        "id": "step_fabvRLaPhxYed6qH6CnZKydXsFI1",
        "assistant_id": "9f091d45-2f69-4fa9-961e-64930a02f4b4",
        "status": "completed",
        "object": "thread.run.step",
        "type": "tool_calls",
        "step_details": {
          "type": "tool_calls",
          "tool_calls": [
            {
              "type": "function",
              "function": {
                "name": "analyze.database.fewshots.loading",
                "arguments": "{\"datasource_name\":\"MasimoEventhouse\",\"datasource_type\":\"Kusto\",\"datasource_artifact_id\":\"bf7ee3b0-0423-4111-a295-9f62afd6216f\",\"datasource_workspace_id\":\"f306e105-78fd-4b16-bfbe-2b556d493cb7\"}",
                "output": "Loaded 7 fewshots"
              }
            }
          ]
        }
      },
      {
        "id": "step_fabVnREy4TcyImaaXXPZ5Aluy3vW",
        "assistant_id": "9f091d45-2f69-4fa9-961e-64930a02f4b4",
        "status": "completed",
        "object": "thread.run.step",
        "type": "tool_calls",
        "step_details": {
          "type": "tool_calls",
          "tool_calls": [
            {
              "type": "function",
              "function": {
                "name": "analyze.database.fewshots.loading",
                "arguments": "{\"datasource_name\":\"healthcare1_msft_silver\",\"datasource_type\":\"LakehouseTables\",\"datasource_artifact_id\":\"5c69a4c9-e851-4b4d-a12d-3c2ac65c4af6\",\"datasource_workspace_id\":\"f306e105-78fd-4b16-bfbe-2b556d493cb7\"}",
                "output": "Loaded 16 fewshots"
              }
            }
          ]
        }
      }
    ]
  },
  "run_status": "failed",
  "last_error": {
    "code": "invalid_prompt",
    "message": "Status code BadRequest: OpenAI request to 'openai/threads/thread_VNKGnphaZg2MYqdbdyQuz7l9/runs' failed."
  }
}
```

#### After Fix
Command:
```bash
AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL HLS_BIND_INTERFACE=en0 python scripts/verify_data_agent_qa.py --query "How many distinct patients are in the Patient table?" --json
```
Raw Output:
```json
{
  "question": "How many distinct patients are in the Patient table?",
  "answer": "There are 115 distinct patients in the Patient table.",
  "generatedQuery": "SELECT COUNT(DISTINCT idOrig) AS distinct_patient_count\nFROM dbo.Patient;",
  "queryLanguage": "SQL",
  "execution_time_ms": 21651,
  "is_error": false
}
```

And for Marcus Vance:
Command:
```bash
AZURE_CONFIG_DIR=$HOME/.azure-isolated/JBATL HLS_BIND_INTERFACE=en0 python scripts/verify_data_agent_qa.py --query "What cancer diagnosis does the patient Marcus Vance have?" --json
```
Raw Output:
```json
{
  "question": "What cancer diagnosis does the patient Marcus Vance have?",
  "answer": "Patient Marcus Vance has the cancer diagnosis:\n\n- **Clear cell renal cell carcinoma**",
  "generatedQuery": "SELECT DISTINCT\n    p.idOrig AS patient_idOrig,\n    JSON_VALUE(c.code_string, '$.coding[0].display') AS diagnosis_display\nFROM dbo.Patient p\nINNER JOIN dbo.Condition c\n    ON COALESCE(\n           REPLACE(\n               NULLIF(JSON_VALUE(c.subject_string, '$.msftSourceReference'), ''),\n               'Patient/',\n               ''\n           ),\n           NULLIF(JSON_VALUE(c.subject_string, '$.idOrig'), '')\n       ) = p.idOrig\nWHERE p.name_string LIKE '%Marcus%'\n  AND p.name_string LIKE '%Vance%'\n  AND (\n        LOWER(JSON_VALUE(c.code_string, '$.coding[0].display')) LIKE '%malignancy%'\n     OR LOWER(JSON_VALUE(c.code_string, '$.coding[0].display')) LIKE '%carcinoma%'\n     OR LOWER(JSON_VALUE(c.code_string, '$.coding[0].display')) LIKE '%lymphoma%'\n     OR LOWER(JSON_VALUE(c.code_string, '$.coding[0].display')) LIKE '%leukemia%'\n     OR LOWER(JSON_VALUE(c.code_string, '$.coding[0].display')) LIKE '%sarcoma%'\n     OR LOWER(JSON_VALUE(c.code_string, '$.coding[0].display')) LIKE '%myeloma%'\n     OR LOWER(JSON_VALUE(c.code_string, '$.coding[0].display')) LIKE '%neoplasm%'\n     OR LOWER(JSON_VALUE(c.code_string, '$.coding[0].display')) LIKE '%neoplasms%'\n  );",
  "queryLanguage": "SQL",
  "execution_time_ms": 26370,
  "is_error": false
}
```
