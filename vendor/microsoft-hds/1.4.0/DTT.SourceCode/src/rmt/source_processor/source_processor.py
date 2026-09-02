from common.exceptions.processor.processor_exceptions import BaseProcessorException
from common.exceptions.processor.steps.base_processing_step_exception import BaseProcessingStepException
from common.processor.base_source_processor import BaseSourceProcessor
from common.reader.reader import Reader
from common.reader.reader_factory import ReaderFactory
from pyspark.sql import DataFrame

from rmt.core.core_exceptions import NoSourceDataError
from rmt.core.data_export.source_values_reader import SourceValuesReader
from rmt.core.data_export.source_values_schema import SourceValuesSchema
from rmt.source_processor.distinct_source_reference_values_selector import DistinctSourceReferenceValuesSelector
from rmt.tools.logging import Logger


class BaseRmtProcessorException(BaseProcessorException):
    """Base class exceptions for RmtProcessor."""

    pass


class RmtProcessException(BaseRmtProcessorException):
    """Exception raised when RMT process failed."""

    pass


class SourceProcessor(BaseSourceProcessor, SourceValuesReader):

    def _select_distinct_source_reference_values(self) -> DataFrame:
        return DistinctSourceReferenceValuesSelector.get_distinct_values(self.df, self.source_config.source_to_reference_mappings)

    def process(self) -> DataFrame:
        try:
            if self.is_empty:
                Logger.warn(f"SourceProcessor has no data to process, source_config: {self.source_config}")
                return None
            self.df = self._build_column_expressions()
            self.df = self._select_specific_columns()
            self.df = self._select_distinct_source_reference_values()
            if self.df is None:
                return self.get_empty_distinct_values_df()
            return self.df
        except BaseProcessingStepException as ex:
            raise RmtProcessException(message="Failed to complete process successfully.", context=ex.context)

    def read_source_distinct_values(self) -> DataFrame:
        df = self.process()
        if df is None:
            raise NoSourceDataError(self.source_config.source_id, self.source_config.data_access_definition.data_source_id)

        return df

    def validate(self) -> bool:
        return self.read()

    def get_empty_distinct_values_df(self) -> DataFrame:
        return self._spark.createDataFrame([], SourceValuesSchema.schema)

    def read(self) -> bool:
        self.is_empty = False
        if not self._read_inner():
            self.is_empty = True

        return not self.is_empty

    def _read_inner(self) -> bool:
        reader: Reader = ReaderFactory.get_instance(self.source_config.data_access_definition)
        self.df = reader.read(self._spark)

        return True if self.df else False
