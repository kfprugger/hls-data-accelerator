from datetime import datetime
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pyspark.sql import SparkSession

from dmf.model.data_feed_configuration import DataFeedConfiguration
from dmf.model.source_configuration import SourceConfiguration
from common.utils.logging import Logger
from dmf.reference_values.reference_values_enricher import ReferenceValuesEnricher
from dmf.transformations.processor.source_processor import SourceProcessor
from dmf.transformations.processor.target_processor import TargetProcessor
from dmf.transformations.processor.temp_view_creator import TempViewCreator
from dmf.utils.utils import parallel_process
from dmf.workflow.ids_mapping_orchestrator import IdsMappingOrchestrator
from dmf.workflow.processors_scheduler import TargetProcessorScheduler
from dmf.model.validation.dmf_config_validator import DMFConfigValidator
from dmf.utils.global_constants import GlobalConstants


class DMFApplication:
    DEFAULT_SPARK_SQL_SHUFFLE_PARTITIONS = 1000

    @staticmethod
    def start_with_transformation_spec_content(spark: SparkSession, transformation_spec_content: str):
        """This method is intended to use from within synapse, as synapse requires quite a lot of ceremony in order to
        read files from a local file system. Hence, the files are read in synapse and their content is passed directly
        as strings
        """
        try:
            # Initiate the logger just in case a client uses this method directly
            Logger.init_logger()
            config = DataFeedConfiguration.from_str(transformation_spec_content)

        except Exception as e:
            Logger.error(f"an error accrued while parsing the configuration files.{e}")
            Logger.error(traceback.format_exc())
            raise

        DMFApplication._start(config, spark)

    @staticmethod
    def _start(config: DataFeedConfiguration, spark: SparkSession):

        DMFConfigValidator(config).validate()

        source_processors: List[SourceProcessor]

        should_override_sql_shuffle_partitions, spark_sql_shuffle_partitions_orig = \
            DMFApplication._handle_spark_session_parameters(spark, config)

        try:
            Logger.info("DTT started")
            DMFApplication._set_secondary_lake_location(config, spark)
            source_processors = DMFApplication._validate_source_data(spark, config)
            mapping_table_access_definitions = IdsMappingOrchestrator.map_source_ids_to_target_ids(
                spark, config, source_processors)
            target_processors: List[TargetProcessor] = []
            for source_processor in source_processors:
                source_processor.id_mapping_definitions = mapping_table_access_definitions
                generated_processors = source_processor.process()
                target_processors.extend(generated_processors)
            if target_processors:
                TargetProcessorScheduler.schedule(target_processors)
        except Exception as e:
            Logger.error(f"DMF exited with error. {e}")
            raise SystemExit("DMF exited with error") from e
        finally:
            if should_override_sql_shuffle_partitions:
                Logger.info(f"Setting spark.sql.shuffle.partitions back to {spark_sql_shuffle_partitions_orig}")
                spark.conf.set("spark.sql.shuffle.partitions", spark_sql_shuffle_partitions_orig)

        Logger.info("DMF finished successfully")

    @staticmethod
    def _handle_spark_session_parameters(spark: SparkSession, config: DataFeedConfiguration) -> (bool, str):
        spark_sql_shuffle_partitions_orig = spark.conf.get("spark.sql.shuffle.partitions")

        try:
            dtt_dmf_sql_shuffle_partitions = (
                int(spark.conf.get(GlobalConstants.SPARK_CONFIG_DTT_DMF_SQL_SHUFFLE_PARTITIONS)))

        except Exception as e:
            Logger.warn(f"Unable to parse {GlobalConstants.SPARK_CONFIG_DTT_DMF_SQL_SHUFFLE_PARTITIONS}. {e}")
            dtt_dmf_sql_shuffle_partitions = None

        should_override_sql_shuffle_partitions = (dtt_dmf_sql_shuffle_partitions is not None) and \
                                                 (str(dtt_dmf_sql_shuffle_partitions) != spark_sql_shuffle_partitions_orig)

        if not should_override_sql_shuffle_partitions:
            dtt_dmf_sql_shuffle_partitions = DMFApplication.DEFAULT_SPARK_SQL_SHUFFLE_PARTITIONS

        Logger.info(f"Changing spark.sql.shuffle.partitions from {spark_sql_shuffle_partitions_orig} "
                    f"to {dtt_dmf_sql_shuffle_partitions}")
        spark.conf.set("spark.sql.shuffle.partitions", dtt_dmf_sql_shuffle_partitions)

        spark.conf.set(
            GlobalConstants.SPARK_CONFIG_ADAPTER_NAME_VARIABLE, config.feed_id)
        spark.conf.set(
            GlobalConstants.SPARK_CONFIG_DTT_START_EXECUTION_TIMESTAMP,
            datetime.now().strftime('%d:%m:%y %H:%M:%S'))

        return should_override_sql_shuffle_partitions, spark_sql_shuffle_partitions_orig

    @staticmethod
    def _validate_source_data(spark: SparkSession, config: DataFeedConfiguration) -> List[SourceProcessor]:
        # the "view only" source processors need to run before any other transformations because they create the
        # necessary spark views needed by the transformations that use queries rather than table names

        DMFApplication._prepare_views(config, spark)
        reference_values_enricher = ReferenceValuesEnricher.create_from_mapping_file(spark,
                                                                                     config.reference_values_configuration)

        source_configs: list[SourceConfiguration] = [c for c in config.source_configurations if not c.create_view_only]
        if not source_configs:
            raise ValueError(
                f"Transformation spec error. Could not find a table in the transformation spec configuration "
                f"{config.source_configurations}")
        with ThreadPoolExecutor(max_workers=len(source_configs), thread_name_prefix="data_validation") \
                as executor:
            def _validate(source_config):
                try:
                    processor = SourceProcessor(spark, source_config, reference_values_enricher)
                    Logger.info(f"validate {processor}")
                    return processor, processor.validate()
                except Exception as e:
                    raise RuntimeError("An error occured while validating source entity") from e

            results = parallel_process(executor, _validate, source_configs)

        if not all(result for _, result in results):
            raise ValueError(
                "Data validation in one of the adapter's source tables failed. Please check the logs for more information.")

        return list(processor for processor, _ in results)

    @staticmethod
    def _prepare_views(config, spark):
        view_only_source_configs = [c for c in config.source_configurations if c.create_view_only]
        if not view_only_source_configs:
            return
        with ThreadPoolExecutor(max_workers=len(view_only_source_configs), thread_name_prefix="view_creator") \
                as executor:

            def _prepare_view(source_config):
                view_creator = TempViewCreator(spark, source_config,
                                               source_config.data_access_definition.data_source_id)
                result = view_creator.read()
                if result:
                    Logger.info(f"{view_creator} view creation complete: {result}")
                else:
                    Logger.error(f"{view_creator} view creation failed: {result}")
                return result

            view_creation_results = parallel_process(executor, _prepare_view, view_only_source_configs)

            if not all(view_creation_results):
                raise ValueError("Some Spark temporary views were not created. "
                                 "Please check the logs for view creation errors.")

    @staticmethod
    def _set_secondary_lake_location(config, spark):
        # TODO this is only to support wrting to tables. should be removed when DMF will support writing to delta files only
        try:
            if spark:
                spark.conf.set(GlobalConstants.SPARK_CONFIG_SECONDARY_LAKE_ROOT_VARIABLE,
                               str(config.reference_values_configuration.secondary_lake_location))
        except Exception as e:
            Logger.warn(f"an error accrued while setting the secondary lake location.{e}")
            raise
