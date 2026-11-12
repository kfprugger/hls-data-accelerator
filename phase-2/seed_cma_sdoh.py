#!/usr/bin/env python3
"""Seed small deterministic SDOH tables for Healthcare Data Solutions CMA demos.

Designed for Fabric notebook/Spark execution against healthcare1_msft_gold_cma.
Rows follow the vendor Gold ETL format that the CMA model joins expect:
social_determinant holds one row per county and measure, with location_type
COUNTYFIPS, the county FIPS code in location_value, and the subcategory key in
category_id.
The pure row builders are intentionally dependency-free for local unit tests.
"""
from __future__ import annotations

import json
from datetime import datetime

# Covers every Atlanta ZIP that Synthea assigns. Each ZIP maps to the county
# that holds most of its land area (Census 2020 ZCTA-to-county relationships).
ATLANTA_ZIP_FIPS = {
    "30032": ("13089", "DeKalb County"),
    "30033": ("13089", "DeKalb County"),
    "30060": ("13067", "Cobb County"),
    "30080": ("13067", "Cobb County"),
    "30082": ("13067", "Cobb County"),
    "30144": ("13067", "Cobb County"),
    "30303": ("13121", "Fulton County"),
    "30305": ("13121", "Fulton County"),
    "30306": ("13121", "Fulton County"),
    "30307": ("13089", "DeKalb County"),
    "30308": ("13121", "Fulton County"),
    "30309": ("13121", "Fulton County"),
    "30310": ("13121", "Fulton County"),
    "30311": ("13121", "Fulton County"),
    "30312": ("13121", "Fulton County"),
    "30313": ("13121", "Fulton County"),
    "30314": ("13121", "Fulton County"),
    "30315": ("13121", "Fulton County"),
    "30316": ("13089", "DeKalb County"),
    "30317": ("13089", "DeKalb County"),
    "30318": ("13121", "Fulton County"),
    "30319": ("13089", "DeKalb County"),
    "30322": ("13089", "DeKalb County"),
    "30324": ("13121", "Fulton County"),
    "30326": ("13121", "Fulton County"),
    "30327": ("13121", "Fulton County"),
    "30328": ("13121", "Fulton County"),
    "30329": ("13089", "DeKalb County"),
    "30331": ("13121", "Fulton County"),
    "30332": ("13121", "Fulton County"),
    "30334": ("13121", "Fulton County"),
    "30336": ("13121", "Fulton County"),
    "30339": ("13067", "Cobb County"),
    "30342": ("13121", "Fulton County"),
    "30344": ("13121", "Fulton County"),
    "30354": ("13121", "Fulton County"),
    "30363": ("13121", "Fulton County"),
}

SDOH_CATEGORIES = [
    (1, "Economic Stability", "Synthetic economic stability indicators"),
    (2, "Health Care Access and Quality", "Synthetic access indicators"),
    (3, "Neighborhood and Built Environment", "Synthetic built-environment indicators"),
]

SDOH_MEASURES = [
    (1, 1, "Median household income", "ACS_MEDIAN_HH_INC", "USD", "US dollars"),
    (2, 1, "Population below poverty", "SAIPE_TOT_POV", "Index", "0-100 index"),
    (3, 2, "Food access research atlas", "FFR16", "Index", "0-100 index"),
    (4, 3, "Non-metro indicator", "Nonmetro2013", "Index", "binary indicator"),
    (5, 3, "Population-weighted arsenic exposure", "NEPHTN_ARSENIC_MEAN_POP", "Index", "synthetic exposure index"),
    (6, 3, "Observed rehospitalization rate", "LTC_AVG_OBS_REHOSP_RATE", "Index", "synthetic rehospitalization rate"),
]

# The vendor ETL copies the dataset's location StandardColumnName into
# location_type and routes only "%fips%" types into sdoh_fips.
LOCATION_TYPE = "COUNTYFIPS"

SDOH_SOURCE_BANNER = (
    "INFO: CMA SDOH seed uses no external SDOH sources. "
    "Values are deterministic synthetic county-level indicators for the counties of Synthea patient ZIP codes."
)



def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _subcategory_id(category_id: int) -> int:
    # Each synthetic category has one subcategory. The ETL keys facts by subcategory.
    return category_id * 10


def build_zip_to_fips_rows(zips: list[str] | None = None) -> list[dict]:
    selected = sorted(set(zips or ATLANTA_ZIP_FIPS.keys()))
    rows = []
    for zip_code in selected:
        county_fips, county = ATLANTA_ZIP_FIPS.get(zip_code, ("13121", "Fulton County"))
        rows.append({
            "id": f"GA-{zip_code}",
            "zip": zip_code,
            "stateAbbreviation": "GA",
            "countyFips": county_fips,
            "countyName": county,
            "SourceTable": "SyntheticSdohSeed",
            "SourceModifiedOn": _now(),
        })
    return rows


def build_sdoh_dimension_rows() -> dict[str, list[dict]]:
    now = _now()
    return {
        "sdoh_category": [
            {
                "category_id": category_id,
                "category_name": name,
                "category_description": description,
                "subcategory_id": _subcategory_id(category_id),
                "subcategory_name": name,
                "subcategory_description": description,
                "SourceTable": "SyntheticSdohSeed",
                "SourceModifiedOn": now,
            }
            for category_id, name, description in SDOH_CATEGORIES
        ],
        "sdoh_unitofmeasure": [
            {"unit_of_measure_id": 1, "name": "US Dollars", "abbreviation": "USD", "description": "US dollars", "SourceTable": "SyntheticSdohSeed", "SourceModifiedOn": now},
            {"unit_of_measure_id": 2, "name": "Index", "abbreviation": "Index", "description": "Synthetic 0-100 score", "SourceTable": "SyntheticSdohSeed", "SourceModifiedOn": now},
        ],
        "sdoh_datasetmetadata": [
            {"sdoh_datasetmetadata_id": 1, "dataset_name": "Synthetic Atlanta SDOH Seed", "publisher_name": "BrakeKat synthetic emulator", "published_date": now[:10], "SourceTable": "SyntheticSdohSeed", "SourceModifiedOn": now}
        ],
        "sdoh_fips": [
            {"fips_code": fips, "locationType": LOCATION_TYPE, "SourceTable": "SyntheticSdohSeed", "SourceModifiedOn": now}
            for fips in sorted({fips for fips, _ in ATLANTA_ZIP_FIPS.values()})
        ],
    }


def build_social_determinant_rows(zip_rows: list[dict]) -> list[dict]:
    """Emit one row per county and measure, the grain of a county-level SDOH dataset."""
    now = _now()
    rows = []
    row_id = 1
    for county_fips in sorted({zip_row["countyFips"] for zip_row in zip_rows}):
        seed = sum(ord(ch) for ch in county_fips)
        values = {
            "ACS_MEDIAN_HH_INC": 52000 + (seed % 34) * 1000,
            "SAIPE_TOT_POV": 8 + (seed % 18),
            "FFR16": 45 + (seed % 41),
            "Nonmetro2013": seed % 2,
            "NEPHTN_ARSENIC_MEAN_POP": 5 + (seed % 26),
            "LTC_AVG_OBS_REHOSP_RATE": 10 + (seed % 21),
        }
        for measure_id, category_id, description, name, unit_name, _ in SDOH_MEASURES:
            unit_id = 1 if unit_name == "USD" else 2
            rows.append({
                "social_determinant_id": row_id,
                "sdoh_datasetmetadata_id": 1,
                "category_id": _subcategory_id(category_id),
                "unit_of_measure_id": unit_id,
                "name": name,
                "description": description,
                "value": str(values[name]),
                "value_as_number": float(values[name]),
                "location_type": LOCATION_TYPE,
                "location_value": county_fips,
                "location_JSON": json.dumps({LOCATION_TYPE: county_fips}, separators=(",", ":")),
                "harmonization_key": name,
                "SourceTable": "SyntheticSdohSeed",
                "SourceModifiedOn": now,
            })
            row_id += 1
    return rows


def write_spark_tables(spark, rows_by_table: dict[str, list[dict]]) -> None:
    for table_name, rows in rows_by_table.items():
        df = spark.createDataFrame(rows)
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)


def main() -> None:
    zip_rows = build_zip_to_fips_rows()
    dims = build_sdoh_dimension_rows()
    social_rows = build_social_determinant_rows(zip_rows)
    rows_by_table = {"zip_to_fips_mapping": zip_rows, **dims, "social_determinant": social_rows}

    try:
        spark  # type: ignore[name-defined]
    except NameError as exc:
        raise SystemExit("Run this script in a Fabric Spark notebook attached to healthcare1_msft_gold_cma.") from exc

    print(SDOH_SOURCE_BANNER)
    write_spark_tables(spark, rows_by_table)  # type: ignore[name-defined]
    print("Seeded CMA SDOH tables:")
    for table_name, rows in rows_by_table.items():
        print(f"  {table_name}: {len(rows)}")


if __name__ == "__main__":
    main()
