import sys
import json
import base64
import requests
import time
import subprocess
import shutil
import argparse
import os
from pathlib import Path

def get_fabric_token():
    az = shutil.which("az") or "az"
    res = subprocess.run([az, "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com", "-o", "json"], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to get az token: {res.stderr.strip()}")
    return json.loads(res.stdout)["accessToken"]

def wait_for_lro(loc, headers, timeout_seconds=1200, interval_seconds=3):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(min(interval_seconds, max(0, deadline - time.monotonic())))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            response = requests.get(loc, headers=headers, timeout=min(60, remaining))
        except requests.exceptions.SSLError:
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            continue
        if response.status_code in (429, 500, 502, 503, 504):
            continue
        response.raise_for_status()
        op = response.json()
        if time.monotonic() >= deadline:
            break
        status = op.get("status")
        if status in ("Succeeded", "Completed"):
            return op
        if status in ("Failed", "Cancelled", "Canceled", "Deduped"):
            raise RuntimeError(f"Operation did not succeed: {op}")
    raise TimeoutError(f"Operation did not complete within {timeout_seconds} seconds: {loc}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--ontology-id", required=True)
    parser.add_argument("--graph-id", required=True)
    parser.add_argument("--skip-refresh", action="store_true", help="Materialize definition; the caller owns the subsequent refresh")
    parser.add_argument("--if-empty", action="store_true", help="Preserve an existing populated graph definition")
    args = parser.parse_args()

    token = get_fabric_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "x-ms-fabric-skill": "fabriciq-ontology-cli"}
    ws_id = args.workspace_id
    ont_id = args.ontology_id
    graph_id = args.graph_id
    
    print(f"Getting Ontology {ont_id} definition...")
    r = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/ontologies/{ont_id}/getDefinition", headers=headers, timeout=60)
    if r.status_code == 200:
        ont_def = r.json()
    elif r.status_code == 202:
        loc = r.headers.get("Location")
        if not loc: loc = f"https://api.fabric.microsoft.com/v1/operations/{r.headers.get('x-ms-operation-id')}"
        wait_for_lro(loc, headers)
        res_uri = loc if loc.endswith("/result") else loc + "/result"
        result = requests.get(res_uri, headers=headers, timeout=60)
        result.raise_for_status()
        ont_def = result.json()
    else:
        r.raise_for_status()

    entities = {}
    relationships = []
    bindings = {}
    contexts = {}
    
    for p in ont_def['definition']['parts']:
        path = p['path']
        payload = json.loads(base64.b64decode(p['payload']).decode('utf-8'))
        
        if path.startswith("EntityTypes/") and path.endswith("definition.json"):
            entities[payload['id']] = payload
        elif "DataBindings/" in path:
            ent_id = path.split('/')[1]
            bindings[ent_id] = payload
        elif path.startswith("RelationshipTypes/") and path.endswith("definition.json"):
            relationships.append(payload)
        elif "Contextualizations/" in path:
            rel_id = path.split('/')[1]
            contexts[rel_id] = payload

    nodeTypes = []
    edgeTypes = []
    nodeTables = []
    edgeTables = []
    dataSources = []
    
    ds_map = {}
    
    def get_ds_name(workspace_id, item_id, table_name):
        key = f"{workspace_id}_{item_id}_{table_name}"
        if key not in ds_map:
            ds_name = f"ds_{len(ds_map)}"
            ds_map[key] = ds_name
            dataSources.append({
                "name": ds_name,
                "type": "DeltaTable",
                "properties": {
                    "path": f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/{item_id}/Tables/{table_name}"
                }
            })
        return ds_map[key]

    for ent_id, ent in entities.items():
        bind = bindings.get(ent_id)
        if not bind: continue
        
        cfg = bind.get("dataBindingConfiguration", {})
        sourceProps = cfg.get("sourceTableProperties", {})
        if sourceProps.get("sourceType") != "LakehouseTable":
            continue
            
        ds_name = get_ds_name(sourceProps["workspaceId"], sourceProps["itemId"], sourceProps["sourceTableName"])
        
        props = []
        prop_maps = []
        for pb in cfg.get("propertyBindings", []):
            spid = pb["targetPropertyId"]
            scol = pb["sourceColumnName"]
            prop_def = next((p for p in ent["properties"] if p["id"] == spid), None)
            if prop_def:
                t = prop_def.get("valueType", "String")
                if t.lower() in ["bigint", "long", "integer", "int"]: t = "INT"
                elif t.lower() in ["double", "float", "decimal"]: t = "FLOAT"
                elif t.lower() in ["boolean"]: t = "BOOLEAN"
                else: t = "STRING"
                props.append({
                    "name": prop_def["name"],
                    "type": t
                })
                prop_maps.append({
                    "propertyName": prop_def["name"],
                    "sourceColumn": scol
                })
                
        pk_prop_id = ent.get("entityIdParts", [])[0] if ent.get("entityIdParts") else None
        pk_prop = next((p for p in ent["properties"] if p["id"] == pk_prop_id), None) if pk_prop_id else None
        
        nodeTypes.append({
            "alias": ent["name"],
            "labels": [ent["name"]],
            "properties": props,
            "primaryKeyProperties": [pk_prop["name"]] if pk_prop else []
        })
        
        nodeTables.append({
            "id": f"nt_{ent['name']}",
            "nodeTypeAlias": ent["name"],
            "dataSourceName": ds_name,
            "propertyMappings": prop_maps
        })

    for rel in relationships:
        ctx = contexts.get(rel["id"])
        if not ctx: continue
        
        source_ent = entities.get(rel["source"]["entityTypeId"])
        target_ent = entities.get(rel["target"]["entityTypeId"])
        if not source_ent or not target_ent: continue
        
        if rel["source"]["entityTypeId"] not in bindings or bindings[rel["source"]["entityTypeId"]]["dataBindingConfiguration"]["sourceTableProperties"].get("sourceType") != "LakehouseTable": continue
        if rel["target"]["entityTypeId"] not in bindings or bindings[rel["target"]["entityTypeId"]]["dataBindingConfiguration"]["sourceTableProperties"].get("sourceType") != "LakehouseTable": continue

        table_props = ctx.get("dataBindingTable", {})
        if table_props.get("sourceType") != "LakehouseTable": continue
        
        ds_name = get_ds_name(table_props["workspaceId"], table_props["itemId"], table_props["sourceTableName"])
        
        edgeTypes.append({
            "alias": rel["name"],
            "labels": [rel["name"]],
            "properties": [],
            "sourceNodeType": { "alias": source_ent["name"] },
            "destinationNodeType": { "alias": target_ent["name"] }
        })
        
        src_cols = [b["sourceColumnName"] for b in ctx.get("sourceKeyRefBindings", [])]
        tgt_cols = [b["sourceColumnName"] for b in ctx.get("targetKeyRefBindings", [])]
        
        edgeTables.append({
            "id": f"et_{rel['name']}",
            "edgeTypeAlias": rel["name"],
            "dataSourceName": ds_name,
            "propertyMappings": [],
            "sourceNodeKeyColumns": src_cols,
            "destinationNodeKeyColumns": tgt_cols
        })
        
    graphTypeJson = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/graphIndex/definition/graphType/1.0.0/schema.json",
        "nodeTypes": nodeTypes,
        "edgeTypes": edgeTypes
    }
    dataSourcesJson = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/graphIndex/definition/dataSources/1.0.0/schema.json",
        "dataSources": dataSources
    }
    graphDefinitionJson = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/graphIndex/definition/graphDefinition/1.0.0/schema.json",
        "nodeTables": nodeTables,
        "edgeTables": edgeTables
    }

    print("Backing up GraphModel...")
    r = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/items/{graph_id}/getDefinition", headers=headers, timeout=60)
    if r.status_code == 200:
        graph_def_orig = r.json()
    elif r.status_code == 202:
        loc = r.headers.get("Location")
        if not loc: loc = f"https://api.fabric.microsoft.com/v1/operations/{r.headers.get('x-ms-operation-id')}"
        wait_for_lro(loc, headers)
        res_uri = loc if loc.endswith("/result") else loc + "/result"
        result = requests.get(res_uri, headers=headers, timeout=60)
        result.raise_for_status()
        graph_def_orig = result.json()
    else:
        r.raise_for_status()

    original_type = next((p for p in graph_def_orig['definition']['parts'] if p['path'] == 'graphType.json'), None)
    if args.if_empty and original_type:
        current_type = json.loads(base64.b64decode(original_type['payload']))
        if current_type.get('nodeTypes'):
            print("Existing populated graph definition preserved.")
            return
    if not nodeTypes or not nodeTables:
        raise RuntimeError("Ontology has no materializable Lakehouse nodes; refusing an empty graph definition")
        
    backup_dir = Path(os.environ.get("HLS_DATA_DIR") or ".")
    backup_dir.mkdir(parents=True, exist_ok=True)
    with (backup_dir / f".graph_backup_{graph_id}.json").open("w") as f:
        json.dump(graph_def_orig, f, indent=2)

    parts = graph_def_orig['definition']['parts']
    for p in parts:
        if p['path'] == 'graphType.json':
            p['payload'] = base64.b64encode(json.dumps(graphTypeJson).encode('utf-8')).decode('utf-8')
        elif p['path'] == 'dataSources.json':
            p['payload'] = base64.b64encode(json.dumps(dataSourcesJson).encode('utf-8')).decode('utf-8')
        elif p['path'] == 'graphDefinition.json':
            p['payload'] = base64.b64encode(json.dumps(graphDefinitionJson).encode('utf-8')).decode('utf-8')
            
    print("Updating GraphModel definition...")
    r = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/items/{graph_id}/updateDefinition", headers=headers, json={
        "definition": {
            "parts": parts
        }
    }, timeout=60)
    
    if r.status_code == 200:
        print("GraphModel updated directly.")
    elif r.status_code == 202:
        loc = r.headers.get("Location")
        if not loc: loc = f"https://api.fabric.microsoft.com/v1/operations/{r.headers.get('x-ms-operation-id')}"
        wait_for_lro(loc, headers)
        print("GraphModel update LRO completed.")
    else:
        raise RuntimeError(f"Update failed: {r.status_code} {r.text}")
    if args.skip_refresh:
        print("Graph definition materialized; caller must verify the subsequent refresh.")
        return

    print("Triggering graph refresh...")
    r = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/graphModels/{graph_id}/jobs/refreshGraph/instances", headers=headers, timeout=60)
    if r.status_code == 202:
        loc = r.headers.get("Location")
        if not loc:
            raise RuntimeError("Graph refresh accepted without a Location; completion cannot be verified")
        job_id = loc.rstrip('/').split('/')[-1]
        loc = f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/graphModels/{graph_id}/jobs/instances/{job_id}"
        wait_for_lro(loc, headers, timeout_seconds=1200, interval_seconds=5)
        print("Graph refresh completed.")
    else:
        raise RuntimeError(f"Failed to start refresh: {r.status_code} {r.text}")

if __name__ == "__main__":
    main()
