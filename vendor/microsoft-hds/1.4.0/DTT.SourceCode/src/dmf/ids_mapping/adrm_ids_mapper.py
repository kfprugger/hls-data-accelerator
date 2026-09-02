import os
from typing import Optional, Tuple

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import LongType, StringType, StructField, StructType

from common.model.data_access_definition import DataAccessDefinition, DataSourceTypeEnum
from common.utils.logging import Logger
from common.reader.reader import Reader
from common.reader.reader_factory import ReaderFactory
from dmf.utils.dataframe_utils import DataFrameUtils
from dmf.utils.global_constants import GlobalConstants
from dmf.utils.logging_utils import SyntheticId, Timed


@SyntheticId
class AdrmIdsMapper:
    DATA_FORMAT = "DELTA"
    SCHEMA = StructType([
        StructField(GlobalConstants.INTERNAL_ID_COLUMN_NAME, StringType(), False),
        StructField(GlobalConstants.EXTERNAL_ID_COLUMN_NAME, StringType(), False),
        StructField(GlobalConstants.ADRM_ID_COLUMN_NAME, LongType(), False),
        StructField(GlobalConstants.FEED_ID_COLUMN_NAME, StringType(), False)
    ])

    @Timed(Logger)
    def map(self,
            spark: SparkSession,
            given_df: DataFrame,
            feed_id: str,
            internal_id_column_name: str,
            external_id_column_name: Optional[str],
            id_mapping_table_name: str,
            id_mapping_table_db_name: Optional[str],
            id_mapping_tables_location: str,
            id_mapping_table_entity_type: DataSourceTypeEnum,
            fast=False):

        Logger.info(
            f"ID Mapper [{self.id}] Mapping IDs (id_mapping_table_name='{id_mapping_table_name}', type='{id_mapping_table_entity_type}', "
            f"internal_id_column='{internal_id_column_name}', external_id_column='{external_id_column_name}')")

        if not external_id_column_name:
            external_id_column_name = AdrmIdsMapper._dummy_external_id_column_name(internal_id_column_name)
            given_df = given_df.dropDuplicates([internal_id_column_name]).\
                select("*", F.lit("").cast(StringType()).alias(external_id_column_name))
        else:
            given_df = given_df.dropDuplicates([internal_id_column_name, external_id_column_name])
            self._validate_all_external_ids_contain_values(given_df, external_id_column_name)
            self._validate_all_ids_are_unique(given_df, internal_id_column_name)
            self._validate_all_ids_are_unique(given_df, external_id_column_name)

        # Cast ID columns just in case they are not strings
        given_df = given_df. \
            select("*",
                   F.col(internal_id_column_name).cast(StringType()).alias(internal_id_column_name + '_temp'),
                   F.col(external_id_column_name).cast(StringType()).alias(external_id_column_name + '_temp')). \
            drop(internal_id_column_name). \
            drop(external_id_column_name). \
            withColumnRenamed(internal_id_column_name + '_temp', internal_id_column_name). \
            withColumnRenamed(external_id_column_name + '_temp', external_id_column_name)

        if id_mapping_table_entity_type == DataSourceTypeEnum.TABLE:
            if id_mapping_table_db_name is None:
                raise ValueError(
                    "id_mapping_table_db_name must be specified when id_mapping_table_entity_type is TABLE")
            AdrmIdsMapper._create_id_mapping_table(spark, id_mapping_table_db_name, id_mapping_table_name,
                                                   id_mapping_tables_location)
            mapping_table_owner = id_mapping_table_db_name
        elif id_mapping_table_entity_type == DataSourceTypeEnum.STORAGE:
            mapping_table_owner = AdrmIdsMapper.specific_table_location(id_mapping_tables_location,
                                                                        id_mapping_table_name)
        else:
            raise ValueError(f"Invalid value for mapping_entity_type: {id_mapping_table_entity_type}")

        reader: Reader = ReaderFactory.get_instance(DataAccessDefinition(data_source_type=id_mapping_table_entity_type,
                                                                         data_source_id=id_mapping_table_name,
                                                                         data_source_owner_id=mapping_table_owner,
                                                                         data_format=AdrmIdsMapper.DATA_FORMAT
                                                                         ))

        id_mapping_table_df = reader.read(spark)
        if not id_mapping_table_df:
            id_mapping_table_df = DataFrameUtils.create_empty_df(spark=spark, schema=AdrmIdsMapper.SCHEMA)

        (id_mapping_column_in_use, data_id_column_in_use) = AdrmIdsMapper._get_id_columns_in_use(
            id_mapping_table_df,
            internal_id_column_name,
            external_id_column_name)
        given_data_with_unmapped_ids_in_current_feed_df = \
            AdrmIdsMapper._get_unmapped_ids_in_current_feed(given_df, id_mapping_table_df, id_mapping_column_in_use,
                                                            data_id_column_in_use,
                                                            feed_id)

        # if and ID mapping does not exist in the current feed, it is required to check if it has already been mapped
        # in other feeds and if it was then that mapped value should be used
        remaining_unmapped_ids_df, mapped_ids_from_other_feeds_df = \
            AdrmIdsMapper._map_ids_from_other_feeds(given_data_with_unmapped_ids_in_current_feed_df,
                                                    id_mapping_table_df,
                                                    internal_id_column_name,
                                                    external_id_column_name,
                                                    id_mapping_column_in_use,
                                                    data_id_column_in_use,
                                                    feed_id)

        new_mapped_df = \
            AdrmIdsMapper._create_id_mapping(remaining_unmapped_ids_df,
                                             id_mapping_table_df,
                                             internal_id_column_name,
                                             external_id_column_name,
                                             feed_id,
                                             fast,
                                             id_mapping_table_name)

        AdrmIdsMapper._save_mappings(spark,
                                     mapped_ids_from_other_feeds_df.unionByName(new_mapped_df),
                                     id_mapping_tables_location, id_mapping_table_name)

    @staticmethod
    def specific_table_location(root: str, table_name: str):
        return os.path.join(root, table_name)

    @staticmethod
    def _should_map_to_ids_from_another_feed(internal_id_column_name: str, external_id_column_name: str):
        return AdrmIdsMapper._dummy_external_id_column_name(internal_id_column_name) != external_id_column_name

    @staticmethod
    def _dummy_external_id_column_name(internal_id_column_name: str) -> str:
        return internal_id_column_name + "_ext"

    @staticmethod
    def _create_id_mapping_table(spark: SparkSession, db_name: str, id_mapping_table_name: str,
                                 id_mapping_tables_location: str):

        table_location = os.path.join(id_mapping_tables_location, id_mapping_table_name)
        sql_str = f"""
                create external table if not exists {db_name}.{id_mapping_table_name} \
                ( \
                    {GlobalConstants.INTERNAL_ID_COLUMN_NAME} STRING, \
                    {GlobalConstants.EXTERNAL_ID_COLUMN_NAME} STRING, \
                    {GlobalConstants.ADRM_ID_COLUMN_NAME} BIGINT, \
                    {GlobalConstants.FEED_ID_COLUMN_NAME} STRING \
                ) \
                USING {AdrmIdsMapper.DATA_FORMAT} \
                PARTITIONED BY ({GlobalConstants.FEED_ID_COLUMN_NAME}) \
                LOCATION '{table_location}'
            """

        spark.sql(sql_str)

    @staticmethod
    def _validate_all_external_ids_contain_values(df: DataFrame, external_id_column_name):

        if (df.filter(F.col(external_id_column_name).isNull() | (F.col(external_id_column_name) == F.lit('')))
                .limit(1)
                .count() > 0):
            raise ValueError(f"Column '{external_id_column_name}' is only partially filled with real values. "
                             f"Please either fix the data so all entries have a value in the '{external_id_column_name}' "
                             f"column or remove the '{external_id_column_name}' column.")

    @staticmethod
    def _create_id_mapping(unmapped_ids_df: DataFrame, id_mapping_table_df: DataFrame,
                           internal_id_column_name: str, external_id_column_name: str, feed_id: str,
                           fast: bool, id_mapping_table_name: str) -> DataFrame:

        AdrmIdsMapper._validate_mapping_creation_allowed(
            AdrmIdsMapper._get_id_mapping_table_current_feed_df(
                id_mapping_table_df,
                feed_id),
            internal_id_column_name,
            external_id_column_name,
            unmapped_ids_df,
            id_mapping_table_name)

        calculated_long_id_column_name = "calc_long_id"

        max_adrm_id = id_mapping_table_df.select(F.max(GlobalConstants.ADRM_ID_COLUMN_NAME)).collect()[0][0]

        if not max_adrm_id:
            max_adrm_id = 0

        summed_columns = ['max_adrm_id', 'const_one', 'long_id']

        expression = '+'.join(summed_columns)

        ids_to_map = unmapped_ids_df.select(internal_id_column_name, external_id_column_name) \
            .filter(F.col(internal_id_column_name).isNotNull()) \
            .filter(F.col(external_id_column_name).isNotNull())
        if fast:
            generated_ids_df: DataFrame = ids_to_map \
                .select("*", F.lit(max_adrm_id).alias("max_adrm_id"), F.lit(1).alias("const_one"),
                        F.monotonically_increasing_id().alias("long_id")) \
                .select("*", F.expr(expression).alias(calculated_long_id_column_name))
        else:
            if DataFrameUtils.is_not_empty(ids_to_map):
                generated_ids_df: DataFrame = ids_to_map \
                    .select("*",
                            F.lit(max_adrm_id).alias("max_adrm_id"),
                            F.lit(1).alias("const_one")) \
                    .rdd.zipWithUniqueId().toDF() \
                    .select("*", F.col('_1.*'), F.col('_2').alias("long_id")) \
                    .select("*", F.expr(expression).alias(calculated_long_id_column_name))
            else:
                generated_ids_df: DataFrame = ids_to_map \
                    .select("*", F.lit(None).cast(LongType()).alias(calculated_long_id_column_name))

        return generated_ids_df \
            .select(F.col(internal_id_column_name).alias(GlobalConstants.INTERNAL_ID_COLUMN_NAME),
                    F.col(external_id_column_name).alias(GlobalConstants.EXTERNAL_ID_COLUMN_NAME),
                    F.col(calculated_long_id_column_name).alias(GlobalConstants.ADRM_ID_COLUMN_NAME),
                    F.lit(feed_id).alias(GlobalConstants.FEED_ID_COLUMN_NAME))

    @staticmethod
    def _validate_mapping_creation_allowed(id_mapping_table_df: DataFrame,
                                           internal_id_column_name: str,
                                           external_id_column_name: str,
                                           unmapped_ids_df: DataFrame,
                                           id_mapping_table_name: str):
        def _mapping_table_has_values_in_external_id_column(id_mapping_table_df: DataFrame) -> bool:
            return (id_mapping_table_df.
                    filter(F.col(GlobalConstants.EXTERNAL_ID_COLUMN_NAME).isNotNull() &
                           (F.col(GlobalConstants.EXTERNAL_ID_COLUMN_NAME) != F.lit(""))).limit(1).count() == 1)

        def _current_data_has_no_values_in_external_id_column(df: DataFrame, external_id_column_name: str) -> bool:
            return (df.filter(F.col(external_id_column_name).isNotNull() &
                              (F.col(external_id_column_name) != F.lit(""))).limit(1).count() == 0)

        if (_mapping_table_has_values_in_external_id_column(id_mapping_table_df) and
                _current_data_has_no_values_in_external_id_column(unmapped_ids_df, external_id_column_name)):
            unrecognized_ids_df = \
                unmapped_ids_df.join(id_mapping_table_df,
                                     id_mapping_table_df[GlobalConstants.INTERNAL_ID_COLUMN_NAME] ==
                                     unmapped_ids_df[internal_id_column_name],
                                     "anti")
            if unrecognized_ids_df.limit(1).count() == 1:
                raise ValueError(f"Unable to execute IDs mapping for table {id_mapping_table_name}."
                                 f"Reason: Current data set contains more IDs in column {internal_id_column_name} than"
                                 f"can be processed correctly.")

    @staticmethod
    def _get_id_mapping_table_current_feed_df(id_mapping_table_df: DataFrame, feed_id: str) -> DataFrame:
        return id_mapping_table_df.where(f"{GlobalConstants.FEED_ID_COLUMN_NAME} == '{feed_id}'")

    @staticmethod
    def _map_ids_from_other_feeds(unmapped_ids_in_current_feed_df: DataFrame,
                                  id_mapping_table_df: DataFrame,
                                  internal_id_column_name: str,
                                  external_id_column_name: str,
                                  id_mapping_column_in_use: str,
                                  data_id_column_in_use: str,
                                  feed_id: str) -> Tuple[DataFrame, DataFrame]:
        if not AdrmIdsMapper._should_map_to_ids_from_another_feed(internal_id_column_name, external_id_column_name):
            return (
                unmapped_ids_in_current_feed_df,
                unmapped_ids_in_current_feed_df.sparkSession.createDataFrame(data=[], schema=AdrmIdsMapper.SCHEMA)
            )

        id_mapping_table_other_feeds_df = id_mapping_table_df. \
            where(f"{GlobalConstants.FEED_ID_COLUMN_NAME} != '{feed_id}'")

        attempted_mapped_ids_from_other_feeds_df = \
            AdrmIdsMapper._join_with_existing_ids(unmapped_ids_in_current_feed_df, id_mapping_table_other_feeds_df,
                                                  id_mapping_column_in_use, data_id_column_in_use)

        unmapped_ids_from_other_feeds_df = attempted_mapped_ids_from_other_feeds_df.filter(
            f"{GlobalConstants.ADRM_ID_COLUMN_NAME} is null"). \
            select(unmapped_ids_in_current_feed_df.columns)

        mapped_ids_from_other_feeds_df = attempted_mapped_ids_from_other_feeds_df. \
            filter(f"{GlobalConstants.ADRM_ID_COLUMN_NAME} is not null"). \
            select(F.col(internal_id_column_name).alias(GlobalConstants.INTERNAL_ID_COLUMN_NAME),
                   F.col(external_id_column_name).alias(GlobalConstants.EXTERNAL_ID_COLUMN_NAME),
                   F.col(GlobalConstants.ADRM_ID_COLUMN_NAME),
                   F.lit(feed_id).alias(GlobalConstants.FEED_ID_COLUMN_NAME))

        return (unmapped_ids_from_other_feeds_df, mapped_ids_from_other_feeds_df)

    @staticmethod
    def _get_unmapped_ids_in_current_feed(source_df: DataFrame, id_mapping_table_df: DataFrame,
                                          id_mapping_column_in_use: str, data_id_column_in_use: str,
                                          feed_id: str) -> DataFrame:
        id_mapping_table_current_feed_df = AdrmIdsMapper._get_id_mapping_table_current_feed_df(id_mapping_table_df,
                                                                                               feed_id)

        attempted_mapped_ids_in_current_feed_df = AdrmIdsMapper._join_with_existing_ids(source_df,
                                                                                        id_mapping_table_current_feed_df,
                                                                                        id_mapping_column_in_use,
                                                                                        data_id_column_in_use)

        return attempted_mapped_ids_in_current_feed_df.filter(
            f"{GlobalConstants.ADRM_ID_COLUMN_NAME} is null") \
            .select(*source_df.columns)

    @staticmethod
    def _save_mappings(spark: SparkSession, df: DataFrame, id_mapping_tables_location: str, id_mapping_table_name: str):
        location = AdrmIdsMapper.specific_table_location(id_mapping_tables_location, id_mapping_table_name)

        df. \
            write. \
            mode("append"). \
            format(AdrmIdsMapper.DATA_FORMAT). \
            partitionBy(GlobalConstants.FEED_ID_COLUMN_NAME). \
            save(location)

    @staticmethod
    def _join_with_existing_ids(unmapped_ids: DataFrame, mapping_table_df: DataFrame,
                                id_mapping_column_in_use: str, data_id_column_in_use: str) -> DataFrame:
        return unmapped_ids.join(mapping_table_df,
                                 on=[unmapped_ids[data_id_column_in_use] == mapping_table_df[id_mapping_column_in_use]],
                                 how="left"
                                 ).drop(GlobalConstants.INTERNAL_ID_COLUMN_NAME,
                                        GlobalConstants.EXTERNAL_ID_COLUMN_NAME)

    @staticmethod
    def is_external_id_mapped(mapping_df: DataFrame) -> bool:
        return not mapping_df.filter(
            (F.col(GlobalConstants.EXTERNAL_ID_COLUMN_NAME) != "") &
            (F.col(GlobalConstants.EXTERNAL_ID_COLUMN_NAME).isNotNull())
        ).limit(1).isEmpty()

    @staticmethod
    def _get_id_columns_in_use(mapping_table_df: DataFrame, internal_id_column_name: str, external_id_column_name) -> \
            Tuple[str, str]:
        if AdrmIdsMapper.is_external_id_mapped(mapping_table_df):
            return (GlobalConstants.EXTERNAL_ID_COLUMN_NAME, external_id_column_name)
        else:
            return (GlobalConstants.INTERNAL_ID_COLUMN_NAME, internal_id_column_name)

    @staticmethod
    def get_mapping_table_name(target_table_name: str) -> str:
        return target_table_name.upper() + GlobalConstants.ID_MAPPING_TABLE_NAME_SUFFIX

    @staticmethod
    def _validate_all_ids_are_unique(df: DataFrame, ids_column_name: str):
        # This method validates that all ids are unique
        # Group by the id column and count occurrences
        duplicate_count_df = df.groupBy(ids_column_name).agg(F.count(ids_column_name).alias('count'))

        # Filter to find ids with more than one occurrence
        duplicate_ids = duplicate_count_df.filter(F.col('count') > 1)

        # If any duplicates are found, raise an exception
        if duplicate_ids.count() > 0:
            raise ValueError(f"Column '{ids_column_name}' contains duplicate values. "
                             f"Please ensure all values are unique.")
