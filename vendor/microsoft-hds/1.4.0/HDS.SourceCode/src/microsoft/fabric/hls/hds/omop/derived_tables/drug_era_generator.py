# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
This module provides a DrugEraGenerator class that generates a drug era
table based on the OMOP CDM drug exposure data using PySpark sql.

The logic of the processing is adapted from the OHDSI (Observational Health Data Sciences and
Informatics) drug era script for SQL databases. The original script can be found here:
https://github.com/OHDSI/ETL-CMS/blob/master/SQL/create_CDMv5_drug_era_non_stockpile.sql
"""
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import lit
from pyspark.sql.utils import AnalysisException
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants
from microsoft.fabric.hls.hds.omop.constants import OMOPConstants
from microsoft.fabric.hls.hds.utils.dataframe_utils import append_unique_to_delta_managed_using_name, find_managed_delta_table_using_name
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper


class DrugEraGenerator:
    """
    A class to generate the drug era table using PySpark based on the OMOP
    CDM drug exposure data.

    This class reads the data from the provided database containing the CDM
    schema, processes it, and generates the drug era table. It takes a Spark
    session and the name of the database as input.
    """

    def __init__(self, spark_session: SparkSession, database_name: str):
        """
        Initialize the DrugEraGenerator class with the provided Spark session and database name.

        :param spark_session: The Spark session.
        :param database_name: The name of the database containing the CDM schema.
        """
        self.spark_session = spark_session
        self.database_name = database_name
        self._logger = LoggingHelper.get_fhirtoomop_logger(
            self.spark_session, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL)

    def normalize_drug_exposure_end_dates(self) -> DataFrame:
        """
            Normalize the drug exposure end date by setting it to the
            existing end date, adding days supply, or adding one day
            to the start date, whichever is appropriate based on the data available.

            :return: A DataFrame with the processed drug exposure data, including the
                      ingredient_concept_id for each drug exposure.
        """
        self._logger.info(
            LoggingConstants.NORMALIZE_DRUG_EXPOSURE_START_INFO_MSG.format(
                self.database_name, OMOPConstants.DRUG_EXPOSURE_TABLE_NAME))
        query = f"""
                    SELECT
                        d.{OMOPConstants.DRUG_EXPOSURE_ID},
                        d.{OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                        c.{OMOPConstants.CONCEPT_ID} AS {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                        d.{OMOPConstants.DRUG_EXPOSURE_START_DATE} AS {OMOPConstants.DRUG_EXPOSURE_START_DATE},
                        d.{OMOPConstants.DRUG_EXPOSURE_DAYS_SUPPLY} AS {OMOPConstants.DRUG_EXPOSURE_DAYS_SUPPLY},
                        COALESCE(
                            NULLIF({OMOPConstants.DRUG_EXPOSURE_END_DATE}, NULL),
                            NULLIF(date_add({OMOPConstants.DRUG_EXPOSURE_START_DATE}, {
                                   OMOPConstants.DRUG_EXPOSURE_DAYS_SUPPLY}), {OMOPConstants.DRUG_EXPOSURE_START_DATE}),
                            date_add(
                                {OMOPConstants.DRUG_EXPOSURE_START_DATE}, 1)
                        ) AS {OMOPConstants.DRUG_EXPOSURE_END_DATE}
                    FROM `{self.database_name}`.`{OMOPConstants.DRUG_EXPOSURE_TABLE_NAME}` d
                        JOIN `{self.database_name}`.`{OMOPConstants.CONCEPT_ANCESTOR_TABLE_NAME}` ca ON ca.{OMOPConstants.CONCEPT_ANCESTOR_DESCENDANT_CONCEPT_ID} = d.{OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID}
                        JOIN `{self.database_name}`.`{OMOPConstants.CONCEPT_TABLE_NAME}` c ON ca.{OMOPConstants.CONCEPT_ANCESTOR_ANCESTOR_CONCEPT_ID} = c.{OMOPConstants.CONCEPT_ID}
                    WHERE c.{OMOPConstants.CONCEPT_VOCABULARY_ID} = '{OMOPConstants.RXNORM_VOCABULARY}'
                        AND c.{OMOPConstants.CONCEPT_CLASS_ID} = '{OMOPConstants.INGREDIENT_CLASS}'
                        AND d.{OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID} != 0
                        AND coalesce(d.{OMOPConstants.DRUG_EXPOSURE_DAYS_SUPPLY},0) >= 0
                """
        pre_drug_target_df = self.spark_session.sql(query)

        self._logger.info(LoggingConstants.NORMALIZE_DRUG_EXPOSURE_END_INFO_MSG.format(
            self.database_name, OMOPConstants.DRUG_EXPOSURE_TABLE_NAME))
        return pre_drug_target_df

    def group_overlapping_exposures(self, pre_drug_target_df: DataFrame) -> DataFrame:
        """
        Group overlapping drug exposures into one exposure to avoid double-counting non-gap days.

        :param normalized_df: The DataFrame with normalized drug exposure end dates.
        :return: A DataFrame of the grouped overlapping exposures with columns: row_number, person_id, drug_concept_id,
        drug_sub_exposure_start_date, drug_sub_exposure_end_date, and drug_exposure_count.
        """

        self._logger.info(
            LoggingConstants.GROUP_OVERLAPPING_EXPOSURES_START_INFO_MSG)

        pre_drug_target_df.createOrReplaceTempView(
            OMOPConstants.CTE_PRE_DRUG_TARGET_NAME)

        sub_exposure_end_dates_query = f"""
                    SELECT
                        {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                        {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                        {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE} AS {OMOPConstants.END_DATE_ALIAS}
                    FROM
                    (
                        SELECT
                            {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                            {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                            {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE},
                            {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE},
                                MAX({OMOPConstants.SUB_EXPOSURE_START_ORDINAL}) OVER (
                                    PARTITION BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS}
                                    ORDER BY {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE}, {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE} ROWS unbounded preceding
                                ) AS {OMOPConstants.SUB_EXPOSURE_START_ORDINAL},
                                ROW_NUMBER() OVER (
                                    PARTITION BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS}
                                    ORDER BY {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE}, {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE}
                                    ) AS {OMOPConstants.SUB_EXPOSURE_OVERALL_ORDINAL}
                        FROM (
                            SELECT
                                {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                                {OMOPConstants.DRUG_EXPOSURE_START_DATE} AS {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE},
                                -1 AS {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE},
                                ROW_NUMBER() OVER (
                                    PARTITION BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS}
                                    ORDER BY {OMOPConstants.DRUG_EXPOSURE_START_DATE}) AS {OMOPConstants.SUB_EXPOSURE_START_ORDINAL}
                                FROM {OMOPConstants.CTE_PRE_DRUG_TARGET_NAME}

                            UNION ALL

                            SELECT
                                {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                                {OMOPConstants.DRUG_EXPOSURE_END_DATE},
                                1 AS {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE}, NULL
                            FROM {OMOPConstants.CTE_PRE_DRUG_TARGET_NAME}
                        ) RAWDATA
                    ) e
                    WHERE (2 * e.{OMOPConstants.SUB_EXPOSURE_START_ORDINAL}) - e.{OMOPConstants.SUB_EXPOSURE_OVERALL_ORDINAL} = 0
                """

        # Execute cteSubExposureEndDates script
        sub_exposure_end_dates_df = self.spark_session.sql(
            sub_exposure_end_dates_query)
        sub_exposure_end_dates_df.createOrReplaceTempView(
            OMOPConstants.CTE_SUB_EXPOSURE_END_DATES_NAME)

        drug_exposure_ends_query = f"""
                                    SELECT
                                        dt.{OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                        dt.{OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS} as {OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID}, -- Renamed ingredient_concept_id to drug_concept_id
                                        dt.{OMOPConstants.DRUG_EXPOSURE_START_DATE},
                                        MIN(e.{OMOPConstants.END_DATE_ALIAS}) AS {OMOPConstants.DRUG_SUB_EXPOSURE_END_DATE}
                                    FROM {OMOPConstants.CTE_PRE_DRUG_TARGET_NAME} dt
                                    JOIN {OMOPConstants.CTE_SUB_EXPOSURE_END_DATES_NAME} e
                                        ON dt.{OMOPConstants.DRUG_EXPOSURE_PERSON_ID} = e.{OMOPConstants.DRUG_EXPOSURE_PERSON_ID}
                                        AND dt.{OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS} = e.{OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS}
                                        AND e.{OMOPConstants.END_DATE_ALIAS} >= dt.{OMOPConstants.DRUG_EXPOSURE_START_DATE}
                                    GROUP BY
                                        dt.{OMOPConstants.DRUG_EXPOSURE_ID},
                                        dt.{OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                        dt.{OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                                        dt.{OMOPConstants.DRUG_EXPOSURE_START_DATE}
                                    """
        # Execute cteDrugExposureEnds script
        drug_exposure_ends_df = self.spark_session.sql(
            drug_exposure_ends_query)
        drug_exposure_ends_df.createOrReplaceTempView(
            OMOPConstants.CTE_DRUG_EXPOSURE_ENDS)

        sub_exposures_query = f"""
                                SELECT ROW_NUMBER() OVER (
                                    PARTITION BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID}, {OMOPConstants.DRUG_SUB_EXPOSURE_END_DATE}
                                    ORDER BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}
                                    ) as {OMOPConstants.SUB_EXPOSURE_ROW_NUMBER},
                                    {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                    {OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID},
                                    MIN({OMOPConstants.DRUG_EXPOSURE_START_DATE}) AS {OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE},
                                    {OMOPConstants.DRUG_SUB_EXPOSURE_END_DATE}, COUNT(*) AS {OMOPConstants.DRUG_EXPOSURE_COUNT}
                                FROM {OMOPConstants.CTE_DRUG_EXPOSURE_ENDS}
                                GROUP BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID}, {OMOPConstants.DRUG_SUB_EXPOSURE_END_DATE}
                                -- ORDER BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID}
                                """
        # Execute cteSubExposures script
        sub_exposures_df = self.spark_session.sql(sub_exposures_query)

        # Drop the temporary views
        self.spark_session.catalog.dropTempView(
            OMOPConstants.CTE_PRE_DRUG_TARGET_NAME)
        self.spark_session.catalog.dropTempView(
            OMOPConstants.CTE_SUB_EXPOSURE_END_DATES_NAME)
        self.spark_session.catalog.dropTempView(
            OMOPConstants.CTE_DRUG_EXPOSURE_ENDS)

        self._logger.info(
            LoggingConstants.GROUP_OVERLAPPING_EXPOSURES_END_INFO_MSG)
        return sub_exposures_df

    def calculate_final_drug_eras_with_gap_days(self, sub_exposures_df: DataFrame) -> DataFrame:
        """
        Calculate final drug eras with gap days.

        :param sub_exposures_df: The DataFrame with grouped overlapping exposures.
        :return: A DataFrame with final drug eras and gap days.
        """
        self._logger.info(
            LoggingConstants.CALCULATE_FINAL_DRUG_ERAS_START_INFO_MSG)
        sub_exposures_df.createOrReplaceTempView(
            OMOPConstants.CTE_SUB_EXPOSURES)

        final_target_query = f"""
                                SELECT
                                    {OMOPConstants.SUB_EXPOSURE_ROW_NUMBER},
                                    {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                    {OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID} as {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                                    {OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE},
                                    {OMOPConstants.DRUG_SUB_EXPOSURE_END_DATE},
                                    {OMOPConstants.DRUG_EXPOSURE_COUNT},
                                    datediff({OMOPConstants.DRUG_SUB_EXPOSURE_END_DATE}, {OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE}) AS {OMOPConstants.DRUG_ERA_DAYS_EXPOSED}
                                FROM {OMOPConstants.CTE_SUB_EXPOSURES}
                              """
        # Execute cteFinalTarget script
        final_target_df = self.spark_session.sql(final_target_query)
        final_target_df.createOrReplaceTempView(OMOPConstants.CTE_FINAL_TARGET)

        end_dates_query = f"""
                            SELECT
                                {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                                date_add({OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE}, -30) AS {OMOPConstants.END_DATE_ALIAS} -- unpad the end date
                            FROM
                            (
                                SELECT
                                    {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                    {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                                    {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE},
                                    {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE},
                                MAX({OMOPConstants.SUB_EXPOSURE_START_ORDINAL}) OVER (
                                    PARTITION BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS}
                                    ORDER BY {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE}, {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE} ROWS UNBOUNDED PRECEDING
                                    ) AS {OMOPConstants.SUB_EXPOSURE_START_ORDINAL},
                                    ROW_NUMBER() OVER (
                                        PARTITION BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS}
                                        ORDER BY {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE}, {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE}
                                        ) AS {OMOPConstants.SUB_EXPOSURE_OVERALL_ORDINAL}
                                FROM (
                                    SELECT
                                        {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                        {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                                        {OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE} AS {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_DATE},
                                        -1 AS {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE},
                                    ROW_NUMBER() OVER (
                                        PARTITION BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS}
                                        ORDER BY {OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE}
                                        ) AS {OMOPConstants.SUB_EXPOSURE_START_ORDINAL}
                                    FROM {OMOPConstants.CTE_FINAL_TARGET}

                                    UNION ALL

                                    SELECT
                                        {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                        {OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                                        date_add(
                                            {OMOPConstants.DRUG_SUB_EXPOSURE_END_DATE}, 30),
                                        1 AS {OMOPConstants.DRUG_SUB_EXPOSURE_EVENT_TYPE},
                                        NULL
                                    FROM {OMOPConstants.CTE_FINAL_TARGET}
                                ) RAWDATA
                            ) e
                            WHERE (2 * e.{OMOPConstants.SUB_EXPOSURE_START_ORDINAL}) - e.{OMOPConstants.SUB_EXPOSURE_OVERALL_ORDINAL} = 0
                           """
        # Execute cteEndDates script
        end_dates_df = self.spark_session.sql(end_dates_query)
        end_dates_df.createOrReplaceTempView(OMOPConstants.CTE_END_DATES)

        drug_era_ends_query = f"""
                                SELECT
                                    ft.{OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                    ft.{OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS} as {OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID},
                                    ft.{OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE},
                                    MIN(e.{OMOPConstants.END_DATE_ALIAS}) AS {OMOPConstants.DRUG_ERA_END_DATE},
                                    {OMOPConstants.DRUG_EXPOSURE_COUNT},
                                    {OMOPConstants.DRUG_ERA_DAYS_EXPOSED}
                                FROM {OMOPConstants.CTE_FINAL_TARGET} ft
                                JOIN {OMOPConstants.CTE_END_DATES} e ON ft.{OMOPConstants.DRUG_EXPOSURE_PERSON_ID} = e.{OMOPConstants.DRUG_EXPOSURE_PERSON_ID}
                                    AND ft.{OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS} = e.{OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS}
                                    AND e.{OMOPConstants.END_DATE_ALIAS} >= ft.{OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE}
                                GROUP BY
                                    ft.{OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                    ft.{OMOPConstants.INGREDIENT_CONCEPT_ID_ALIAS},
                                    ft.{OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE},
                                    {OMOPConstants.DRUG_EXPOSURE_COUNT},
                                    {OMOPConstants.DRUG_ERA_DAYS_EXPOSED}
                               """
        # Execute cteDrugEraEnds script
        drug_era_ends_df = self.spark_session.sql(drug_era_ends_query)
        drug_era_ends_df.createOrReplaceTempView(
            OMOPConstants.CTE_DRUG_ERA_ENDS)

        final_drug_era_query = f"""
                                   SELECT
                                    ROW_NUMBER() OVER (ORDER BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}) {OMOPConstants.DRUG_ERA_ID},
                                    {OMOPConstants.DRUG_EXPOSURE_PERSON_ID},
                                    {OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID},
                                    MIN({OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE}) AS {OMOPConstants.DRUG_ERA_START_DATE},
                                    {OMOPConstants.DRUG_ERA_END_DATE},
                                    SUM({OMOPConstants.DRUG_EXPOSURE_COUNT}) AS {OMOPConstants.DRUG_EXPOSURE_COUNT},
                                    datediff({OMOPConstants.DRUG_ERA_END_DATE}, MIN({OMOPConstants.DRUG_SUB_EXPOSURE_START_DATE}))-SUM({OMOPConstants.DRUG_ERA_DAYS_EXPOSED}) as {OMOPConstants.DRUG_ERA_GAP_DAYS}
                                    FROM {OMOPConstants.CTE_DRUG_ERA_ENDS} dee
                                    GROUP BY {OMOPConstants.DRUG_EXPOSURE_PERSON_ID}, {OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID}, {OMOPConstants.DRUG_ERA_END_DATE}
                                """
        # Execute cteFinalDrugEra script
        final_drug_era_df = self.spark_session.sql(final_drug_era_query)

        # Drop the temporary views
        self.spark_session.catalog.dropTempView(
            OMOPConstants.CTE_SUB_EXPOSURES)
        self.spark_session.catalog.dropTempView(OMOPConstants.CTE_FINAL_TARGET)
        self.spark_session.catalog.dropTempView(OMOPConstants.CTE_END_DATES)
        self.spark_session.catalog.dropTempView(
            OMOPConstants.CTE_DRUG_ERA_ENDS)

        self._logger.info(
            LoggingConstants.CALCULATE_FINAL_DRUG_ERAS_END_INFO_MSG)

        return final_drug_era_df

    def generate_drug_era_table(self):
        """
        Generate the drug_era table.

        This function reads the necessary input data from drug_exposure, concecpt_ancestor and concept OMOP standard tables, processes it using
        the defined functions, and writes the final DataFrame to the drug_era table.
        """
        is_successful = False
        message = None

        try:
            self._logger.info(LoggingConstants.GENERATE_DRUG_ERAS_START_INFO_MSG.format(
                self.database_name, OMOPConstants.DRUG_ERA_TABLE_NAME))
            normalized_df = self.normalize_drug_exposure_end_dates()
            sub_exposures_df = self.group_overlapping_exposures(normalized_df)
            drug_era_df = self.calculate_final_drug_eras_with_gap_days(
                sub_exposures_df=sub_exposures_df)

            drug_era_delta_table = find_managed_delta_table_using_name(
                spark_session=self.spark_session,
                delta_table_name=OMOPConstants.DRUG_ERA_TABLE_NAME,
                delta_database=self.database_name)

            if drug_era_df.count() > 0:
                if drug_era_delta_table is not None:
                    drug_era_delta_table.delete(lit(True))
                    self._logger.info(
                        LoggingConstants.DELETE_EXISTING_DRUG_ERAS_INFO_MSG)
                else:
                    self._logger.info(
                        LoggingConstants.DRUG_ERA_TABLE_DOES_NOT_EXIST_INFO_MSG.format(self.database_name, OMOPConstants.DRUG_ERA_TABLE_NAME))

                append_unique_to_delta_managed_using_name(spark_session=self.spark_session,
                                               data_manager_logger=self._logger,
                                               df_to_process=drug_era_df,
                                               delta_table_name=OMOPConstants.DRUG_ERA_TABLE_NAME,
                                               unique_columns=[
                                                   OMOPConstants.DRUG_ERA_ID,
                                                   OMOPConstants.DRUG_EXPOSURE_DRUG_CONCEPT_ID],
                                               delta_database=self.database_name)
                self._logger.info(LoggingConstants.GENERATE_DRUG_ERAS_END_INFO_MSG.format(
                    self.database_name, OMOPConstants.DRUG_ERA_TABLE_NAME))
                message = LoggingConstants.GENERATE_DRUG_ERAS_END_INFO_MSG.format(
                    self.database_name, OMOPConstants.DRUG_ERA_TABLE_NAME)
            else:
                self._logger.info(
                    LoggingConstants.GENERATE_DRUG_ERAS_SKIPPED_INFO_MSG)
                message = LoggingConstants.GENERATE_DRUG_ERAS_SKIPPED_INFO_MSG
            is_successful = True
        except AnalysisException as analysis_exception:
            self._logger.error(
                f"{LoggingConstants.TABLE_OR_VIEW_NOT_FOUND_ERR_MSG.format(db=self.database_name)}: {str(analysis_exception)}")
            message = LoggingConstants.TABLE_OR_VIEW_NOT_FOUND_ERR_MSG.format(
                db=self.database_name)
        except Exception as exception:
            self._logger.error(str(exception))
            message = f"{LoggingConstants.GENERATE_DRUG_ERAS_UNEXPECTED_ERR_MSG}: {str(exception)}"

        return is_successful, message
