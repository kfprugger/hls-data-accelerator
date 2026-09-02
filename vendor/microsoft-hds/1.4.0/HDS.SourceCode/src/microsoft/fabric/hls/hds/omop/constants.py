# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module defining constants for OMOP derived tables genration
"""

# pylint: disable=R0903 # too-few-public-methods


class OMOPConstants:
    """Constants used by OMOP library"""

    # Drug exposure table name
    DRUG_EXPOSURE_TABLE_NAME = "drug_exposure"
    # Drug era table name
    DRUG_ERA_TABLE_NAME = "drug_era"
    # Concept table name
    CONCEPT_TABLE_NAME = "concept"
    # Concept ancestor table name
    CONCEPT_ANCESTOR_TABLE_NAME = "concept_ancestor"

    # Drug exposure table column names
    DRUG_EXPOSURE_DRUG_CONCEPT_ID = "drug_concept_id"
    DRUG_EXPOSURE_ID = "drug_exposure_id"
    DRUG_EXPOSURE_PERSON_ID = "person_id"
    DRUG_EXPOSURE_START_DATE = "drug_exposure_start_date"
    DRUG_EXPOSURE_END_DATE = "drug_exposure_end_date"
    DRUG_EXPOSURE_DAYS_SUPPLY = "days_supply"

    # Concept table column names
    CONCEPT_ID = "concept_id"
    CONCEPT_CLASS_ID = "concept_class_id"
    CONCEPT_VOCABULARY_ID = "vocabulary_id"

    # Concept ancestor table column names
    CONCEPT_ANCESTOR_ANCESTOR_CONCEPT_ID = "ancestor_concept_id"
    CONCEPT_ANCESTOR_DESCENDANT_CONCEPT_ID = "descendant_concept_id"

    RXNORM_VOCABULARY = 'RxNorm'
    INGREDIENT_CLASS = 'Ingredient'
    INGREDIENT_CONCEPT_ID_ALIAS = 'ingredient_concept_id'

    # Common Table Expression (CTE) names
    CTE_PRE_DRUG_TARGET_NAME = "ctePreDrugTarget"
    CTE_SUB_EXPOSURE_END_DATES_NAME = "cteSubExposureEndDates"
    CTE_DRUG_EXPOSURE_ENDS = "cteDrugExposureEnds"
    CTE_SUB_EXPOSURES = "cteSubExposures"
    CTE_FINAL_TARGET = "cteFinalTarget"
    CTE_END_DATES = "cteEndDates"
    CTE_DRUG_ERA_ENDS = "cteDrugEraEnds"

    # Common Table Expression (CTE) column names
    DRUG_SUB_EXPOSURE_START_DATE = "drug_sub_exposure_start_date"
    DRUG_SUB_EXPOSURE_END_DATE = "drug_sub_exposure_end_date"
    DRUG_EXPOSURE_COUNT = "drug_exposure_count"
    DRUG_SUB_EXPOSURE_EVENT_DATE = "event_date"
    DRUG_SUB_EXPOSURE_EVENT_TYPE = "event_type"
    SUB_EXPOSURE_START_ORDINAL = "start_ordinal"
    SUB_EXPOSURE_OVERALL_ORDINAL = "overall_ord"
    SUB_EXPOSURE_ROW_NUMBER = "row_number"

    END_DATE_ALIAS = "end_date"

    # Drug era table column names
    DRUG_ERA_DAYS_EXPOSED = "days_exposed"
    DRUG_ERA_START_DATE = "drug_era_start_date"
    DRUG_ERA_END_DATE = "drug_era_end_date"
    DRUG_ERA_GAP_DAYS = "gap_days"
    DRUG_ERA_ID = "drug_era_id"
