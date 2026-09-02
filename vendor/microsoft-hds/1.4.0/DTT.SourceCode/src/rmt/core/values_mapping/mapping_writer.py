from pyspark.sql import DataFrame

from rmt.core.values_mapping.mapping_schema import MappingSchema


class MappingWriter:
    @staticmethod
    def overwrite(updates_df: DataFrame, file_path: str, number_of_partition_files=-1):
        try:
            if number_of_partition_files > 0:
                updates_df = updates_df.repartition(number_of_partition_files)
            df_writer = updates_df.write.format("delta").mode("overwrite")
            df_writer = df_writer.partitionBy(*MappingSchema.partitions)
            df_writer.save(file_path)
        except Exception as e:
            raise Exception(f"Error overwriting mapping file: '{file_path}'.") from e
