import sys
import json
import base64
import requests
import time
import subprocess
import argparse

def get_fabric_token():
    res = subprocess.run(["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com", "-o", "json"], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("Failed to get az token")
    return json.loads(res.stdout)["accessToken"]

def wait_for_lro(loc, headers):
    while True:
        time.sleep(3)
        op = requests.get(loc, headers=headers).json()
        if op["status"] in ["Succeeded", "Completed"]:
            return op
        if op["status"] in ["Failed", "Cancelled"]:
            raise RuntimeError(f"LRO failed: {op}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--ontology-id", required=True)
    parser.add_argument("--graph-id", required=True)
    args = parser.parse_args()

    token = get_fabric_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    ws_id = args.workspace_id
    ont_id = args.ontology_id
    graph_id = args.graph_id
    
    print(f"Getting Ontology {ont_id} definition...")
    r = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/ontologies/{ont_id}/getDefinition", headers=headers)
    if r.status_code == 200:
        ont_def = r.json()
    else:
        loc = r.headers.get("Location")
        if not loc: loc = f"https://api.fabric.microsoft.com/v1/operations/{r.headers.get('x-ms-operation-id')}"
        wait_for_lro(loc, headers)
        res_uri = loc if loc.endswith("/result") else loc + "/result"
        ont_def = requests.get(res_uri, headers=headers).json()

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
    r = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/items/{graph_id}/getDefinition", headers=headers)
    if r.status_code == 200:
        graph_def_orig = r.json()
    else:
        loc = r.headers.get("Location")
        if not loc: loc = f"https://api.fabric.microsoft.com/v1/operations/{r.headers.get('x-ms-operation-id')}"
        wait_for_lro(loc, headers)
        res_uri = loc if loc.endswith("/result") else loc + "/result"
        graph_def_orig = requests.get(res_uri, headers=headers).json()
        
    with open(f".graph_backup_{graph_id}.json", "w") as f:
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
    })
    
    if r.status_code == 200:
        print("GraphModel updated directly.")
    elif r.status_code == 202:
        loc = r.headers.get("Location")
        if not loc: loc = f"https://api.fabric.microsoft.com/v1/operations/{r.headers.get('x-ms-operation-id')}"
        wait_for_lro(loc, headers)
        print("GraphModel update LRO completed.")
    else:
        raise RuntimeError(f"Update failed: {r.status_code} {r.text}")

    print("Triggering graph refresh...")
    r = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/graphModels/{graph_id}/jobs/refreshGraph/instances", headers=headers)
    if r.status_code == 202:
        loc = r.headers.get("Location")
        if loc:
            job_id = loc.split('/')[-1]
            loc = f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/graphModels/{graph_id}/jobs/instances/{job_id}"
            while True:
                time.sleep(5)
                op = requests.get(loc, headers=headers).json()
                if op["status"] in ["Completed", "Succeeded"]:
                    print("Graph refresh completed.")
                    break
                if op["status"] in ["Failed", "Cancelled"]:
                    raise RuntimeError(f"Refresh job failed: {op['status']}")
                print("Refresh status:", op["status"])
    else:
        raise RuntimeError(f"Failed to start refresh: {r.status_code} {r.text}")

if __name__ == "__main__":
    main()
