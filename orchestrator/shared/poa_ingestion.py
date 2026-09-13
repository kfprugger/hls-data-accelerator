"""Correct generated HDS outreach adapters while preserving the immutable vendor release."""
from __future__ import annotations


def map_marketing_created_on(adapter: dict) -> int:
    """Preserve event timestamps on MarketingCampaignTask for downstream fact ingestion."""
    changed = 0
    for source in adapter["sourceTables"]:
        if not any(t.get("tableName") == "MarketingCampaignTask" for t in source.get("targetAnchorTables", [])):
            continue
        if any(target.get("tableName") == "MarketingCampaignTask" and target.get("fieldName") == "CreatedOn"
               for field in source.get("sourceFields", []) for target in field.get("targetFields", {}).get("fields", [])):
            continue
        field = next((f for f in source.get("sourceFields", []) if f.get("fieldName") == "CreatedOn" and f.get("fieldType") == "timestamp"), None)
        if field is None:
            continue
        field["targetFields"]["fields"].append({"tableName": "MarketingCampaignTask", "fieldName": "CreatedOn"})
        changed += 1
    return changed
