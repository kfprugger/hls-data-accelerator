from pyspark.sql import SparkSession
from common.utils.logging import Logger
from dmf.model.source_configuration import SourceConfiguration
from common.reader.reader import Reader
from common.reader.reader_factory import ReaderFactory


class TempViewCreator:
    def __init__(self, spark: SparkSession, config: SourceConfiguration, view_name):
        self._spark: SparkSession = spark
        self._config: SourceConfiguration = config
        self.view_name = view_name

    def read(self) -> bool:
        reader: Reader = ReaderFactory.get_instance(self._config.data_access_definition)
        df = reader.read(self._spark)
        if not df:
            Logger.warn(
                f"Could not access data source on '{self._config.data_access_definition.data_source_id}'"
                " when creating Spark temp view '{view_name}'"
            )
            return False

        df.createOrReplaceTempView(self.view_name)
        return True

    def __str__(self):
        return f"TempViewCreator[view_name={self.view_name}]"
