from pyspark.sql import SparkSession
from configuration_compiler.common import Common


class ConfigurationContentWrapper:
    adaptor_file_content: str | None = None
    target_db_semantics_content: str | None = None
    target_db_schema_content: str | None = None
    db_schema_config_content: str | None = None
    env_config_content: str | None = None

    def __init__(self) -> None:
        raise NotImplementedError("This class is not meant to be instantiated directly.")

    def _validate_content(self) -> None:
        if not self.adaptor_file_content:
            raise ValueError("DMF adaptor file content is required.")
        if not self.target_db_semantics_content:
            raise ValueError("Target DB semantics file content is required.")
        if not self.target_db_schema_content:
            raise ValueError("Target DB schema file content is required.")
        if not self.db_schema_config_content:
            raise ValueError("DB schema config content is required.")
        if not self.env_config_content:
            raise ValueError("Environment config file content is required.")

    @staticmethod
    def _get_file_content(spark: SparkSession, file_location: str, file_content: str, fail_if_missing_path=True) -> str:
        content = file_content or Common.read_configuration_file(spark, file_location, fail_if_missing_path)
        if not content and fail_if_missing_path:
            raise ValueError(f"File {file_location} does not exist or empty.")
        return content

    @staticmethod
    def _validate_either_path_or_content(path_arg: str, content_arg: str, file_type: str):
        if path_arg and content_arg:
            raise ValueError(f"Cannot provide both path argument and content argument for {file_type}")
        if not path_arg and not content_arg:
            raise ValueError(f"Must provide either path argument or content argument for {file_type}")

    def _set_file_content(
        self,
        spark: SparkSession,
        adaptor_path: str = "",
        target_db_semantics_path: str = "",
        target_db_schema_path: str = "",
        db_schema_config_path: str = "",
        env_config_path: str = "",
        adaptor_content: str = "",
        target_db_semantics_content: str = "",
        target_db_schema_content: str = "",
        db_schema_config_content: str = "",
        env_config_content: str = "",
    ) -> None:
        for path_param, content_param, file_type in [
            (adaptor_path, adaptor_content, "adaptor"),
            (target_db_semantics_path, target_db_semantics_content, "target DB semantics"),
            (target_db_schema_path, target_db_schema_content, "target DB schema"),
            (db_schema_config_path, db_schema_config_content, "target DB schema config"),
            (env_config_path, env_config_content, "environment config"),
        ]:
            ConfigurationContentWrapper._validate_either_path_or_content(path_param, content_param, file_type)

        self.adaptor_file_content = ConfigurationContentWrapper._get_file_content(spark, adaptor_path, adaptor_content)
        self.target_db_semantics_content = ConfigurationContentWrapper._get_file_content(
            spark, target_db_semantics_path, target_db_semantics_content
        )
        self.target_db_schema_content = ConfigurationContentWrapper._get_file_content(
            spark, target_db_schema_path, target_db_schema_content
        )
        self.db_schema_config_content = ConfigurationContentWrapper._get_file_content(
            spark, db_schema_config_path, db_schema_config_content
        )
        self.env_config_content = ConfigurationContentWrapper._get_file_content(
            spark, env_config_path, env_config_content
        )


class RmtConfigurationContentWrapper(ConfigurationContentWrapper):
    def __init__(
        self,
        spark: SparkSession,
        adaptor_path: str = "",
        target_db_semantics_path: str = "",
        target_db_schema_path: str = "",
        db_schema_config_path: str = "",
        env_config_path: str = "",
        adaptor_content: str = "",
        target_db_semantics_content: str = "",
        target_db_schema_content: str = "",
        db_schema_config_content: str = "",
        env_config_content: str = "",
    ) -> None:
        self._set_file_content(
            spark,
            adaptor_path,
            target_db_semantics_path,
            target_db_schema_path,
            db_schema_config_path,
            env_config_path,
            adaptor_content,
            target_db_semantics_content,
            target_db_schema_content,
            db_schema_config_content,
            env_config_content,
        )
        self._validate_content()


class DttConfigurationContentWrapper(RmtConfigurationContentWrapper):
    target_db_semantics_config_content: str | None = None

    def __init__(
        self,
        spark: SparkSession,
        adaptor_path: str = "",
        target_db_semantics_path: str = "",
        target_db_semantics_config_path: str = "",
        target_db_schema_path: str = "",
        db_schema_config_path: str = "",
        env_config_path: str = "",
        dmf_adaptor_content: str = "",
        target_db_semantics_content: str = "",
        target_db_semantics_config_content: str = "",
        target_db_schema_content: str = "",
        db_schema_config_content: str = "",
        env_config_content: str = "",
    ) -> None:
        super(DttConfigurationContentWrapper, self).__init__(
            spark,
            adaptor_path,
            target_db_semantics_path,
            target_db_schema_path,
            db_schema_config_path,
            env_config_path,
            dmf_adaptor_content,
            target_db_semantics_content,
            target_db_schema_content,
            db_schema_config_content,
            env_config_content,
        )
        
        ConfigurationContentWrapper._validate_either_path_or_content(
            target_db_semantics_config_path, target_db_semantics_config_content, "target DB semantics config"
        )

        self.target_db_semantics_config_content = ConfigurationContentWrapper._get_file_content(
            spark,
            target_db_semantics_config_path,
            target_db_semantics_config_content,
            fail_if_missing_path=False,
        )
