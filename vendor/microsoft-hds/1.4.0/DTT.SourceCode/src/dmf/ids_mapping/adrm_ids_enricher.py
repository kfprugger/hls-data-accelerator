from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from dmf.ids_mapping.adrm_ids_mapper import AdrmIdsMapper
from dmf.utils.global_constants import GlobalConstants


class AdrmIdsEnricher:

    @staticmethod
    def enrich(source_df: DataFrame, feed_id: str, id_column_name: str, id_mapping_df: DataFrame,
               required_adrm_id_col_name: str) -> DataFrame:
        """Enriches the source dataframe with the ADRM ids from the id mapping dataframe.
        A left join is important here because some of the source ids might not be NULL foreign keys
        and the corresponding rows must be kept.
        A subsequent filter will be applied to remove the rows with NULL ADRM ids because of conditional
        mapping"""
        id_mapping_df = id_mapping_df.filter(F.col(GlobalConstants.FEED_ID_COLUMN_NAME) == feed_id)
        if AdrmIdsMapper.is_external_id_mapped(id_mapping_df):
            id_mapping_column = GlobalConstants.EXTERNAL_ID_COLUMN_NAME
        else:
            id_mapping_column = GlobalConstants.INTERNAL_ID_COLUMN_NAME
        join_df = source_df.join(
            id_mapping_df,
            on=(source_df[id_column_name] == id_mapping_df[id_mapping_column]),
            how="left")
        return join_df.select(*source_df.columns, join_df[f"{GlobalConstants.ADRM_ID_COLUMN_NAME}"]
                              .alias(required_adrm_id_col_name))
