from typing import Optional

from pyspark.sql import SparkSession


class SparkUtils:
    @staticmethod
    def get_spark_conf(spark: SparkSession):
        return spark.sparkContext.getConf()

    @staticmethod
    def get_runtime_total_spark_pool_size(spark: SparkSession) -> Optional[int]:
        num_instances = SparkUtils.get_spark_conf(spark).get("spark.executor.instances")
        executor_cores = SparkUtils.get_spark_conf(spark).get("spark.executor.cores")

        if num_instances is None or executor_cores is None:
            return None
        return int(num_instances) * int(executor_cores)
