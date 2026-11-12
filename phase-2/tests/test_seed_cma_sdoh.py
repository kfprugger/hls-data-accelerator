from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PHASE2_DIR = Path(__file__).resolve().parents[1]


def load_seed_module():
    module_name = "seed_cma_sdoh_under_test"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, PHASE2_DIR / "seed_cma_sdoh.py")
    if spec is None or spec.loader is None:
        raise AssertionError("could not load seed_cma_sdoh.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class CmaSdohSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seed = load_seed_module()
        self.addCleanup(sys.modules.pop, "seed_cma_sdoh_under_test", None)

    def test_zip_to_fips_rows_are_deduplicated_sorted_and_default_unknown_zip_to_fulton(self) -> None:
        with patch.object(self.seed, "_now", return_value="2026-07-01T12:00:00"):
            rows = self.seed.build_zip_to_fips_rows(["30309", "99999", "30309", "30080"])

        self.assertEqual(["30080", "30309", "99999"], [row["zip"] for row in rows])
        self.assertEqual(
            {
                "id": "GA-30080",
                "zip": "30080",
                "stateAbbreviation": "GA",
                "countyFips": "13067",
                "countyName": "Cobb County",
                "SourceTable": "SyntheticSdohSeed",
                "SourceModifiedOn": "2026-07-01T12:00:00",
            },
            rows[0],
        )
        self.assertEqual("13121", rows[2]["countyFips"])
        self.assertEqual("Fulton County", rows[2]["countyName"])

    def test_seed_rows_match_every_cma_model_join_key(self) -> None:
        with patch.object(self.seed, "_now", return_value="2026-07-01T12:00:00"):
            zip_rows = self.seed.build_zip_to_fips_rows()
            dims = self.seed.build_sdoh_dimension_rows()
            social_rows = self.seed.build_social_determinant_rows(zip_rows)

        self.assertEqual(
            {"sdoh_category", "sdoh_unitofmeasure", "sdoh_datasetmetadata", "sdoh_fips"},
            set(dims),
        )
        keys = {
            "fips_code": [row["fips_code"] for row in dims["sdoh_fips"]],
            "subcategory_id": [row["subcategory_id"] for row in dims["sdoh_category"]],
            "unit_of_measure_id": [row["unit_of_measure_id"] for row in dims["sdoh_unitofmeasure"]],
            "sdoh_datasetmetadata_id": [row["sdoh_datasetmetadata_id"] for row in dims["sdoh_datasetmetadata"]],
        }
        for key, values in keys.items():
            self.assertEqual(len(values), len(set(values)), key)

        # Many-side columns of the SDOH links in the CMA relationships.tmdl.
        joins = [
            ("zip_to_fips_mapping.countyFips", [row["countyFips"] for row in zip_rows], "fips_code"),
            ("social_determinant.location_value", [row["location_value"] for row in social_rows], "fips_code"),
            ("social_determinant.category_id", [row["category_id"] for row in social_rows], "subcategory_id"),
            ("social_determinant.unit_of_measure_id", [row["unit_of_measure_id"] for row in social_rows], "unit_of_measure_id"),
            ("social_determinant.sdoh_datasetmetadata_id", [row["sdoh_datasetmetadata_id"] for row in social_rows], "sdoh_datasetmetadata_id"),
        ]
        for column, values, key in joins:
            self.assertEqual(set(), set(values) - set(keys[key]), column)

        # The vendor ETL routes only "%fips%" location types into sdoh_fips.
        location_types = {row["location_type"] for row in social_rows} | {row["locationType"] for row in dims["sdoh_fips"]}
        self.assertEqual(set(), {value for value in location_types if "fips" not in value.lower()})

    def test_social_determinant_rows_are_one_per_county_and_measure(self) -> None:
        zip_rows = [
            {"zip": "30309", "countyFips": "13121"},
            {"zip": "30303", "countyFips": "13121"},
            {"zip": "30032", "countyFips": "13089"},
        ]

        with patch.object(self.seed, "_now", return_value="2026-07-01T12:00:00"):
            rows = self.seed.build_social_determinant_rows(zip_rows)
            dims = self.seed.build_sdoh_dimension_rows()

        # Two ZIPs in one county must not double-count that county's values.
        measures = [measure[3] for measure in self.seed.SDOH_MEASURES]
        self.assertCountEqual(
            [(fips, name) for fips in ("13089", "13121") for name in measures],
            [(row["location_value"], row["name"]) for row in rows],
        )
        ids = [row["social_determinant_id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        units = {row["unit_of_measure_id"]: row["abbreviation"] for row in dims["sdoh_unitofmeasure"]}
        income = next(row for row in rows if row["name"] == "ACS_MEDIAN_HH_INC")
        self.assertEqual("USD", units[income["unit_of_measure_id"]])

    def test_zip_table_covers_every_atlanta_zip_synthea_assigns(self) -> None:
        # Atlanta, GA rows of Synthea's geography/zipcodes.csv. A patient in an
        # unmapped ZIP gets no county and no SDOH values.
        synthea_atlanta_zips = {
            "30032", "30303", "30305", "30306", "30307", "30308", "30309", "30310",
            "30311", "30312", "30313", "30314", "30315", "30316", "30317", "30318",
            "30319", "30324", "30326", "30327", "30331", "30332", "30334", "30336",
            "30342", "30344", "30354", "30363",
        }

        self.assertEqual(set(), synthea_atlanta_zips - set(self.seed.ATLANTA_ZIP_FIPS))


if __name__ == "__main__":
    unittest.main()
