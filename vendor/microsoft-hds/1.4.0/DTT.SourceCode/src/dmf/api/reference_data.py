from pyspark.sql import DataFrame

from common.utils.logging import Logger
from dmf.model.internal.source_to_reference_mapping_extended import SourceToReferenceMappingExtended
from dmf.model.reference_values_configuration import ReferenceValuesConfiguration
from dmf.reference_values.reference_values_enricher import ReferenceValuesEnricher




def map_source_to_reference_values(source_df: DataFrame,
                                   source_domain: str,
                                   default_reference_value: int,
                                   source_column_name: str,
                                   reference_table_name: str,
                                   reference_field_name: str,
                                   mapped_column_name: str,
                                   secondary_lake_location: str) -> DataFrame:
    """
    Maps source values to reference values.
    Parameters:
        source_df (DataFrame): A dataframe containing the source values that need to be mapped.
        source_domain (str): The source domain, as configured in DTT configuration.
        default_reference_value (int): The default reference value that will be used in case the source value is not
            found in the reference values mapping.
        source_column_name (str): A name of the column containing the source values.
        reference_table_name (str): A name of the table containing the reference values.
        reference_field_name (str): A name of the column in the reference table containing the reference values.
        mapped_column_name (str): A name of the column in the output DataFrame that will contain the reference values that match the source values.
        secondary_lake_location (str): Absolute path of the location of the secondary lake.
    Returns:
        DataFrame: The original DataFrame with column containing the reference values that match the source values.
    """

    Logger.init_logger()
    config = ReferenceValuesConfiguration(secondary_lake_location=secondary_lake_location,
                                          default_value=default_reference_value,
                                          source_domain=source_domain,
                                          fail_upon_missing_reference_values=False)

    enricher = ReferenceValuesEnricher.create_from_mapping_file(source_df.sparkSession, config)

    source_to_reference_mapping = SourceToReferenceMappingExtended(source_field_name=source_column_name,
                                                                   target_reference_table_name=reference_table_name,
                                                                   target_reference_field_name=reference_field_name,
                                                                   mapped_column_name=mapped_column_name)

    return enricher.enrich(source_df=source_df,
                           source_to_reference_mappings=frozenset([source_to_reference_mapping]),
                           replace_values_in_src_column=False)
