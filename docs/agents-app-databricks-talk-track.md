# Agents, Ops Agents, and the Command Center — Talk Track

Subject: Fabric Data Agents, Operations Agents, and the Rayfin Health Command Center in
`med-0906`, plus a closing segment on the Azure Databricks destination.

## Title options

1. *Five Agents, One Gold Layer, and the Part That Still Needs a Human*
2. *We Asked Five Fabric Agents the Same Question. Two Lied Politely.*
3. *Agents, Alerts, and an App — What Actually Answers in Fabric*

## Viewing outcome

After watching, you can tell the difference between a Fabric agent that is deployed and a
Fabric agent that actually answers, and you know which three checks separate them.

## Runtime

Target 9:15. Narration is 1,295 words, which lands at roughly 143 words per minute.

---

## 0:00–0:25 — Cold open

**On screen**
- Split view: the MCP response from Payer Ops Triage showing `CLAIM_SUBMITTED: 228,081`,
  next to the same agent's earlier answer reading "No data was returned."

**Say**

> Same agent. Same question. Same data underneath. One of these answers is right, and the
> other one is the reason people quietly stop trusting agents.
>
> Both of those came out of this workspace today. In the next nine minutes I'll show you
> the three checks that tell you which one you've actually deployed.

**Evidence**
- Live MCP probe of Payer Ops Triage, before and after the instruction repair.

---

## 0:25–1:05 — Context and boundary

**On screen**
- The `med-0906` workspace list, filtered to agents and the app.

**Say**
>
> This is the HLS Data Accelerator reference workspace. Everything in it is synthetic —
> Synthea patients, an emulated Masimo device feed, generated claims. No real patient data
> touches this, and nothing here is a medical device or clinical decision support.
>
> Standing it up creates billable Azure and Fabric resources, so treat it as a lab, not a
> landing zone.
>
> There are five Data Agents, two Operations Agents, and one app. They all read the same
> Gold layer. That shared foundation is the whole point.

**Evidence**
- `README.md` boundaries section; workspace item inventory.

---

## 1:05–2:20 — Chapter 1: what a Data Agent is actually bound to

**On screen**
- `getDefinition` output for Clinical Triage, with the published `datasource.json` tree
  expanded to show selected tables and functions.

**Say**

> A Fabric Data Agent is a published question-answering surface over sources you pick. The
> word doing the work there is *pick*.
>
> Clinical Triage is bound to two Eventhouse tables, five KQL helper functions, eleven
> curated Silver tables, and the clinical ontology. Not the whole lakehouse. Eleven tables.
>
> Patient 360 used to be bound to a hundred and eighty-nine. It still answered, but every
> question dragged the entire FHIR catalog into scope. We cut it to the same eleven.
>
> Here's the first check: open the published definition, not the draft, and count what's
> actually selected. Draft and published drift, and the portal shows you the draft.

**Evidence**
- Data agent `getDefinition` parts under `Files/Config/published/`.

**Fallback**
- If `getDefinition` is slow, show the saved definition JSON captured before recording.

---

## 2:20–3:20 — Chapter 2: ask all five the same way

**On screen**
- Five MCP responses side by side: imaging modality counts, patients by gender, current
  device and alert counts, claim events by type, distinct patients in the ontology.

**Say**

> Every published agent exposes an MCP endpoint, so you can ask all five from a script
> instead of clicking through five chat panes.
>
> Imaging comes back with CT fifty, DX forty-two, CR eight, and it names the aggregate it
> used. Patient 360 gives fifty-nine female, forty-one male. Clinical Triage reports a
> hundred devices reporting right now. Payer counts two hundred twenty-eight thousand claim
> events. The graph agent counts a hundred distinct patients in the ontology.
>
> Three of those five were wrong this morning.
>
> Payer refused a claim-count question while two hundred thousand claim rows sat in the
> table it was already bound to. Its instructions were a wall of "always call this function,
> never call that one," so it never reached for the raw table. The graph agent reported one
> patient, because it counted the rows a sample query returned instead of running a count.
>
> Second check: ask the question a human would ask, then verify the number against the
> source yourself. Groundedness is not the same as correctness.

**Evidence**
- MCP JSON-RPC probes against each published agent; KQL and DAX counts run independently.

**Fallback**
- If an agent times out, show the captured transcript and say the endpoint was slow, not
  that the answer was wrong.

---

## 3:20–4:40 — Chapter 3: Operations Agents, and what "Inactive" means

**On screen**
- Both Operations Agents in the item list showing `state: Inactive`, then the OpsAgentKQL
  database with `agent_ops_stream_health` and `agent_deterioration_findings`.

**Say**

> Operations Agents are the other half. A Data Agent answers when you ask. An Operations
> Agent is supposed to watch and tell you.
>
> We have two. Healthcare Ops watches ingestion health. Clinical Deterioration watches the
> device feed for sustained SpO2 drops.
>
> Both return a clean definition over the API. Both have exactly one knowledge source. Both
> are sitting at Inactive, and I'm not going to dress that up.
>
> Playbook generation and Start have no public API right now. An operator opens the agent in
> the portal, generates the playbook, and starts it. Until someone does, these two are
> configured, not running.
>
> What we could fix is the part underneath. The generator needs physical alert columns, not
> prose, so there are now two materialized tables feeding it — stream health across three
> streams, and a hundred deterioration findings with forty-five sitting at concern or
> escalate.
>
> And the alerting path that does work is the Activator next to it. One of ours was an empty
> shell — no source, no rule, no recipient. It now runs a KQL query every fifteen minutes
> and emails a monitored alias when devices cross the line.
>
> Third check: state, not existence. An agent item in a workspace tells you someone deployed
> something. It doesn't tell you anything is watching.

**Evidence**
- `GET /operationsAgents/{id}` properties; OpsAgentKQL table counts; Reflex definition.

**Fallback**
- If the ops database is slow, show the captured row counts and say they were read earlier.

---

## 4:40–6:30 — Chapter 4: the app, and why it has its own database

**On screen**
- The Health Command Center in the workspace, cycling Payer, Provider, MedTech lenses.
  Then the four entity files in `rayfin/data/`.

**Say**

> Agents answer questions people know how to ask. An app has to answer the ones they don't.
>
> This is a Rayfin app in the same workspace. Three lenses over one Gold layer. Payer gets
> paid against billed, collection rate, PMPM, revenue at risk. Provider gets open care gaps,
> Stars, readmission risk. MedTech gets study volume, modality mix, DICOM instance counts.
>
> The first version queried the semantic models on every render. It looked fine and it was
> wrong in a way that's easy to miss — nothing to inspect, no capture time, no record of
> where a number came from.
>
> So it has its own database now. Four tables: the KPI snapshot, the series behind each
> chart, the worklist rows, and a sync record. A single module reads the Direct Lake models,
> masks member IDs and patient names, replaces the snapshot, and writes down what it did.
> The dashboard only ever reads those tables.
>
> That buys three things. Every figure has a timestamp. The database never holds a raw
> identifier. And when a number looks wrong, you query the table instead of re-deriving it.
>
> One honest note: the tables are empty until someone opens the app inside the workspace.
> Writes need a Fabric sign-in, so it fills itself on first load. I have not watched that
> run, and I'm not going to tell you I did.

**Evidence**
- `rayfin/data/*.ts`; applied DAB config; `src/lib/sync-gold.ts`; live data-plane 401.

**Fallback**
- If the app is empty, show the banner explaining why and the `SyncRun` table definition.
  Do not claim a sync succeeded.

---

## 6:30–7:10 — Mid-video reset and limitations

**On screen**
- The graph query returning 100 Patient nodes, with the `coveredBy` edge at zero.

**Say**

> Back to the opening question. Three checks: what's actually selected in the published
> definition, whether the answer survives verification against the source, and whether the
> thing is in a running state.
>
> Where this environment still falls short. Both Operations Agents need a human in the
> portal. The app database is empty until first sign-in. The claims-to-payer edge in the
> ontology reads zero, because the Gold claim rows carry no usable payer key — I could have
> invented one and made the graph look complete. I'd rather you see the gap.
>
> And all of it is synthetic. A hundred patients. Good enough to prove plumbing, not good
> enough to prove clinical anything.

**Evidence**
- GQL edge counts; `fact_claim` coverage columns.

---

## 7:10–7:50 — Verdict

**On screen**
- Workspace list with the agents, ops agents, and app visible together.

**Say**

> If you're evaluating Fabric agents, this is a good pattern to copy and a bad one to trust
> blindly. Bind agents to curated projections, not whole lakehouses. Verify answers against
> the source before anyone demos them. Give the app its own store so figures have a time and
> a lineage.
>
> If you're looking for something you can point at production PHI next quarter, this isn't
> it, and it doesn't claim to be.
>
> Try it yourself this way: pick one agent, ask it a counting question, then run the count
> in KQL. If the two disagree, you've learned more in five minutes than a demo will teach
> you in an hour.

---

## 7:50–9:15 — Just one more thing: Azure Databricks

**On screen**
- The `azure-databricks/` directory, then the Unity Catalog schemas, then the validator
  output showing 17 passed.

**Say**

> One more thing.
>
> Everything you just saw lands in Fabric. A fair question is whether the accelerator is
> really about Fabric, or about the healthcare data estate underneath it.
>
> So we built the same destination on Azure Databricks. Same Azure Health Data Services,
> same ADLS, same Event Hubs, same DICOM source. Different destination: Premium workspace,
> Unity Catalog, Lakeflow pipelines, Delta medallion, Databricks SQL.
>
> It's deployed. Bronze, Silver, stream freshness, and Gold gates all passed, and the live
> validator came back seventeen for seventeen against a hundred patients, eight hundred
> eighty-three encounters, and a hundred thirty-eight thousand deduplicated telemetry
> events.
>
> Two details worth stealing. The access connector gets read on the source account and write
> only on its own managed container, and the Event Hubs policy is listen-only — no send
> rights to the emulator feed. And the clinical alert ships paused, with a named recipient,
> because an alert that emails on first deploy is how you teach people to ignore alerts.
>
> What I won't claim: the Microsoft HDS deployment artifacts are Fabric-specific. They do
> not port. We reimplemented that layer against the observable contract, and the Databricks
> side carries its own gates.
>
> So the honest version is this. The domain model travels. The destination is a choice. If
> you're already on Databricks, you don't have to give up the healthcare plumbing to keep
> your lakehouse.

**Evidence**
- `azure-databricks/` package and `CHANGELOG.md` deployment entry; `07-validate-deployment.py`
  results recorded at deployment time.

**Fallback**
- If the Databricks workspace is stopped, present this as the recorded deployment result and
  say so. Do not imply a live run during the recording.

---

## Source ledger

| Claim | Class | Source |
|---|---|---|
| Five Data Agents, bound sources and selections | Verified current | `getDefinition` published parts |
| MCP answers and their numbers | Verified current | Live MCP JSON-RPC probes |
| Counter-checks for those numbers | Verified current | KQL and DAX run independently |
| Ops agents at Inactive, one knowledge source | Verified current | `GET /operationsAgents/{id}` |
| Playbook generation and Start are portal-only | Limitation | No public Fabric API |
| OpsAgentKQL tables and row counts | Verified current | KQL queries |
| Activator source, rule, recipient | Verified current | Reflex `getDefinition` |
| App entities, permissions, anonymous 401 | Verified current | DAB config and data-plane probe |
| App database empty until first in-portal sync | Limitation | No CLI write path |
| Ontology graph node and edge counts | Verified current | GQL queries |
| `coveredBy` zero for lack of payer key | Limitation | `fact_claim` columns |
| Databricks deployment and 17/17 validation | Configured, recorded | `CHANGELOG.md`, validator output |
| HDS artifacts do not port to Databricks | Design intent | `azure-databricks/` docs |

## Recording gates

1. Capacity active; both Eventstreams showing sources and destinations at Running.
2. Fresh telemetry within the last five minutes before claiming the feed is live.
3. Agent MCP probes run once before recording; keep transcripts for fallback.
4. Edge on the Work — BrakeKat profile, 2560×1440, 100% zoom.
5. No GUIDs, subscription identifiers, or recipient addresses on screen.

## Read-aloud checklist

- First twenty-five seconds name the tension and promise a judgment.
- Every chapter returns to the same throughline: deployed is not the same as answering.
- Limitations appear inside the story, not stacked at the end.
- No claim of a live run that was not performed during recording.
- The close gives one concrete test the viewer can run.
