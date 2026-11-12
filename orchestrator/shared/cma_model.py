"""Patch the generated HDS CMA model without modifying the vendored release."""
from __future__ import annotations


def repair_social_determinant_metadata_join(model: dict) -> None:
    """Join social_determinant to sdoh_datasetmetadata on the int64 key, not the string name.

    The vendored relationship joins social_determinant.name (string) to
    sdoh_datasetmetadata.sdoh_datasetmetadata_id (int64). Power BI cannot match
    the two types, so the relationship filters nothing.
    """
    relationships = [
        r for r in model["model"]["relationships"]
        if r["fromTable"] == "social_determinant" and r["toTable"] == "sdoh_datasetmetadata"
    ]
    if len(relationships) != 1:
        raise ValueError("CMA social_determinant metadata relationship shape changed")
    relationship = relationships[0]
    if relationship["fromColumn"] == "sdoh_datasetmetadata_id":
        return
    if relationship["fromColumn"] != "name":
        raise ValueError("CMA social_determinant metadata relationship shape changed")
    relationship["fromColumn"] = "sdoh_datasetmetadata_id"


# Fact-to-dimension links the CMA report never filters through in reverse
# filter one way. condition_occurrence, cost and visit_occurrence filter person
# (and through person each other), and person filters location, so those links
# keep bothDirections. Dimension-to-dimension links keep bothDirections too.
_ONE_WAY_LINKS = frozenset({
    ("procedure_occurrence", "person"),
    ("measurement", "person"),
    ("care_plan_activities", "care_plan"),
    ("care_plan_addresses", "care_plan"),
    ("care_plan_goal", "care_plan"),
    ("social_determinant", "sdoh_fips"),
    ("social_determinant", "sdoh_datasetmetadata"),
    ("social_determinant", "sdoh_category"),
    ("social_determinant", "sdoh_unitofmeasure"),
})


def set_fact_to_dimension_one_way(model: dict) -> None:
    """Set crossFilteringBehavior to oneDirection on the fact-to-dimension links.

    The report needs no reverse filtering on these links, and bothDirections
    adds query cost.
    """
    relationships = [
        r for r in model["model"]["relationships"]
        if (r["fromTable"], r["toTable"]) in _ONE_WAY_LINKS
    ]
    if len(relationships) != len(_ONE_WAY_LINKS):
        raise ValueError("CMA fact-to-dimension relationship shape changed")
    for relationship in relationships:
        relationship["crossFilteringBehavior"] = "oneDirection"


def orient_person_location_link(model: dict) -> None:
    """Make person.location_id the foreign key to location.location_id.

    The vendored relationship has location on the key side, which leaves the
    one side (person.location_id) non-unique. Idempotent.
    """
    relationships = model["model"]["relationships"]
    if any(r["fromTable"] == "person" and r["toTable"] == "location" for r in relationships):
        return
    reversed_links = [
        r for r in relationships
        if r["fromTable"] == "location" and r["toTable"] == "person"
    ]
    if len(reversed_links) != 1 or reversed_links[0]["fromColumn"] != "location_id" or reversed_links[0]["toColumn"] != "location_id":
        raise ValueError("CMA location-to-person relationship shape changed")
    reversed_links[0].update(fromTable="person", fromColumn="location_id", toTable="location", toColumn="location_id")


def activate_care_plan_person_link(model: dict) -> None:
    """Activate care_plan.person_id -> person.person_id with bothDirections.

    The vendored link is inactive, so care-plan fields do not filter person and
    care-plan charts count every patient. Idempotent.
    """
    links = [
        r for r in model["model"]["relationships"]
        if r["fromTable"] == "care_plan" and r["toTable"] == "person"
    ]
    if len(links) != 1 or links[0]["fromColumn"] != "person_id" or links[0]["toColumn"] != "person_id":
        raise ValueError("CMA care_plan-to-person relationship shape changed")
    links[0].pop("isActive", None)
    links[0]["crossFilteringBehavior"] = "bothDirections"
