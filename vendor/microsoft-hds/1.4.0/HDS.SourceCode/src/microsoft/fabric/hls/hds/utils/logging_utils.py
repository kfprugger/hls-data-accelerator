import json
from typing import Dict, Optional
from sempy.fabric import FabricRestClient
from pyspark.sql import SparkSession
from microsoft.fabric.hls.hds.utils.data_manager_logger import DataManagerLogger
from microsoft.fabric.hls.hds.utils.fabric_utils import FabricClientUtils
from microsoft.fabric.hls.hds.utils.mssparkutils_client import MSSparkUtilsClient

class LoggingUtils:

    @staticmethod
    def log_runtime_info(
        spark: SparkSession,
        fabric_rest_client: FabricRestClient,
        spark_utils_client: Optional[MSSparkUtilsClient],
        path_to_packages: Optional[str],
        activity_name: Optional[str],
        logger: DataManagerLogger) -> None:
        """
        Description: Log runtime info associated with the service
        Args:
            spark (SparkSession): The spark session
            spark_utils_client (Optional[MSSparkUtilsClient]): A spark utils client
            fabric_rest_client (FabricRestClient): A Fabric REST client
            path_to_packages (Optional[str]): The relative path to installed custom packages
            activity_name (Optional[str]): The name associated with the activity
            logger (DataManagerLogger): A logger
        """
        
        runtime_info = {}
        
        try:
            spark_context_config = spark.sparkContext.getConf()
            artifact_id = FabricClientUtils.get_artifact_id()
            capacity_id = spark_context_config.get("spark.hadoop.trident.capacity.id")
            capacities = FabricClientUtils.list_capacities()
            capacity_details = capacities[capacities["Id"] == capacity_id].squeeze().to_dict()
            spark_compute_details = {}
            spark_pool_details = {}
            workspace_spark_settings = {}
            context_config = {}
            runtime_context = {}
            
            try:
                environment_details = json.loads(spark_context_config.get("spark.fabric.environmentDetails"))
                
                if environment_details is not None:
                    
                    if "id" in environment_details and "workspaceId" in environment_details:
                        environment_id = environment_details["id"].replace("-", "")
                        workspace_id = environment_details["workspaceId"].replace("-", "")
                        spark_compute_details = FabricClientUtils.get_spark_compute_details(fabric_rest_client, workspace_id, environment_id)
                
                        spark_pool_details = {}
                        if "id" in spark_compute_details['instancePool']:
                            pool_id = spark_compute_details['instancePool']['id'].replace("-", "")
                            spark_pool_details = FabricClientUtils.get_spark_pool_details(fabric_rest_client, workspace_id, pool_id)
            except:
                pass

            try:
                workspace_spark_settings = FabricClientUtils.get_workspace_spark_settings(fabric_rest_client, workspace_id)
            except:
                pass
            
            if path_to_packages and spark_utils_client:
                packages = [file.name for file in spark_utils_client.fs_ls(path_to_packages)]
            else:
                packages = []

            try:
                context_config = LoggingUtils.get_context_config(spark)
            except:
                pass
            
            try:
                runtime_context = spark_utils_client.get_runtime_context() if spark_utils_client is not None else {}
            except:
                pass
            
            runtime_info = {
                "context": runtime_context,
                "activity_name": activity_name,
                "artifact_id": artifact_id,
                "workspace_id": workspace_id,
                "workspace_spark_settings": workspace_spark_settings,
                "capacity": capacity_details,
                "compute": spark_compute_details,
                "pool": spark_pool_details,
                "packages": packages,
                "config": context_config,
            }
            
            logger.info(f"Spark runtime config: {json.dumps(runtime_info)}")
            
        except Exception as ex:
            logger.error(f"Unable to log runtime info: {ex}")
    
    
    @staticmethod
    def get_context_config(spark: SparkSession) -> Dict:
        
        # Curated list of settings of interest
        log_settings = set([
            "spark.app.id",
            "spark.driver.cores",
            "spark.executor.cores",
            "spark.fabric.environmentDetails",
            "spark.microsoft.delta.merge.lowShuffle.enabled",
            "spark.databricks.delta.optimizeWrite.binSize",
            "spark.databricks.delta.optimizeWrite.enabled",
            "spark.databricks.delta.optimizeWrite.partitioned.enabled",
            "spark.ms.autotune.appEvent.enabled",
            "spark.ms.autotune.baseline-models-dir",
            "spark.ms.autotune.enabled",
            "spark.ms.autotune.queryEvent.enabled",
            "spark.ms.autotune.queryTuning.enabled",
            "spark.synapse.workspace.name",
            "spark.synapse.workspace.tenantId",
            "spark.synapse.vegas.cacheSize",
            "spark.synapse.vegas.consistent.hash",
            "spark.synapse.vegas.hash.placement",
            "spark.synapse.vegas.useCache",
            "spark.tracking.driverLogUrl",
            "spark.hadoop.parquet.block.size",
            "spark.hadoop.synapse.vfs.enabled.extensions",
            "spark.sql.parquet.footerCache.size",
            "spark.sql.parquet.vorder.autoEncoding",
            "spark.sql.parquet.vorder.dictionaryPageSize",
            "spark.sql.parquet.vorder.enabled",
        ])
        
        conf_settings = {}
        for setting_key, setting_value  in spark.sparkContext.getConf().getAll():
            if setting_key in log_settings:
                conf_settings[setting_key] = setting_value

        return conf_settings
