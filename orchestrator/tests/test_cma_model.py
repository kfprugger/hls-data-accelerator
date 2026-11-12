from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from shared.cma_model import (
    activate_care_plan_person_link,
    orient_person_location_link,
    repair_social_determinant_metadata_join,
    set_fact_to_dimension_one_way,
)

CMA_MODEL = (
    Path(__file__).resolve().parents[2]
    / "vendor/microsoft-hds/1.4.0/HDS.SourceCode/hds-build-artifacts/healthcare-artifacts"
    / "1.4.0/care-management-analytics/Datasets/CareManagementAnalytics/model.bim"
)


def _column_type(model: dict, table: str, column: str) -> str:
    t = next(t for t in model["model"]["tables"] if t["name"] == table)
    return next(c["dataType"] for c in t["columns"] if c["name"] == column)


class CmaModelJoinRepairTests(unittest.TestCase):
    def setUp(self):
        self.model = json.loads(CMA_MODEL.read_text(encoding="utf-8"))

    def test_metadata_join_key_types_match_after_repair(self):
        repair_social_determinant_metadata_join(self.model)
        rel = next(
            r for r in self.model["model"]["relationships"]
            if r["toTable"] == "sdoh_datasetmetadata"
        )
        from_type = _column_type(self.model, rel["fromTable"], rel["fromColumn"])
        to_type = _column_type(self.model, rel["toTable"], rel["toColumn"])
        self.assertEqual(from_type, to_type)
        self.assertEqual(rel["fromColumn"], "sdoh_datasetmetadata_id")

    def test_repair_is_idempotent(self):
        repair_social_determinant_metadata_join(self.model)
        once = copy.deepcopy(self.model)
        repair_social_determinant_metadata_join(self.model)
        self.assertEqual(self.model, once)

    def test_unexpected_relationship_shape_is_rejected(self):
        self.model["model"]["relationships"] = [
            r for r in self.model["model"]["relationships"]
            if r["toTable"] != "sdoh_datasetmetadata"
        ]
        with self.assertRaises(ValueError):
            repair_social_determinant_metadata_join(self.model)


class FactToDimensionOneWayTests(unittest.TestCase):
    def setUp(self):
        self.model = json.loads(CMA_MODEL.read_text(encoding="utf-8"))
        orient_person_location_link(self.model)

    def _behavior(self, from_table, to_table):
        rel = next(
            r for r in self.model["model"]["relationships"]
            if r["fromTable"] == from_table and r["toTable"] == to_table
        )
        return rel["crossFilteringBehavior"]

    def test_fact_to_dimension_links_filter_one_way(self):
        set_fact_to_dimension_one_way(self.model)
        self.assertEqual(self._behavior("measurement", "person"), "oneDirection")
        self.assertEqual(self._behavior("social_determinant", "sdoh_category"), "oneDirection")

    def test_dimension_to_dimension_link_keeps_both_directions(self):
        set_fact_to_dimension_one_way(self.model)
        self.assertEqual(self._behavior("zip_to_fips_mapping", "patient_location_zip"), "bothDirections")

    def test_report_filter_links_keep_both_directions(self):
        set_fact_to_dimension_one_way(self.model)
        for from_table, to_table in (
            ("condition_occurrence", "person"),
            ("cost", "person"),
            ("visit_occurrence", "person"),
            ("person", "location"),
        ):
            self.assertEqual(self._behavior(from_table, to_table), "bothDirections", from_table)

    def test_one_way_patch_is_idempotent(self):
        set_fact_to_dimension_one_way(self.model)
        once = copy.deepcopy(self.model)
        set_fact_to_dimension_one_way(self.model)
        self.assertEqual(self.model, once)

    def test_missing_fact_link_is_rejected(self):
        self.model["model"]["relationships"] = [
            r for r in self.model["model"]["relationships"]
            if r["fromTable"] != "measurement"
        ]
        with self.assertRaises(ValueError):
            set_fact_to_dimension_one_way(self.model)

    def test_location_link_points_person_key_to_location(self):
        orient_person_location_link(self.model)
        set_fact_to_dimension_one_way(self.model)
        rel = next(
            r for r in self.model["model"]["relationships"]
            if r["fromTable"] == "person" and r["toTable"] == "location"
        )
        self.assertEqual(rel["fromColumn"], "location_id")
        self.assertEqual(rel["toColumn"], "location_id")
        self.assertEqual(rel["crossFilteringBehavior"], "bothDirections")

    def test_location_orientation_is_idempotent(self):
        orient_person_location_link(self.model)
        once = copy.deepcopy(self.model)
        orient_person_location_link(self.model)
        self.assertEqual(self.model, once)

    def test_unexpected_location_link_shape_is_rejected(self):
        self.model["model"]["relationships"] = [
            r for r in self.model["model"]["relationships"]
            if not (r["fromTable"] in ("location", "person") and r["toTable"] in ("location", "person"))
        ]
        with self.assertRaises(ValueError):
            orient_person_location_link(self.model)


class CarePlanPersonLinkTests(unittest.TestCase):
    def setUp(self):
        self.model = json.loads(CMA_MODEL.read_text(encoding="utf-8"))

    def _link(self):
        return next(
            r for r in self.model["model"]["relationships"]
            if r["fromTable"] == "care_plan" and r["toTable"] == "person"
        )

    def test_care_plan_link_is_active_and_filters_both_ways(self):
        activate_care_plan_person_link(self.model)
        rel = self._link()
        self.assertTrue(rel.get("isActive", True))
        self.assertEqual(rel["crossFilteringBehavior"], "bothDirections")

    def test_unexpected_care_plan_link_shape_is_rejected(self):
        self._link()["toColumn"] = "location_id"
        with self.assertRaises(ValueError):
            activate_care_plan_person_link(self.model)


if __name__ == "__main__":
    unittest.main()
