"""
api.py
-------

This module provides the main API for generating and persisting DTT and RMT specifications from given configuration files.
It also provides an API for getting proposed paths for a given source table and target field.

Functions
---------
persist_dtt_spec
    Generates a DTT spec from the given configuration files and persists it to the given path.

persist_rmt_spec
    Generates an RMT spec from the given configuration files and persists it to the given path.

generate_dtt_specs
    Generates DTT and RMT specs from the given configuration files and persists them to the given paths.
    merely calls persist_dtt_spec and persist_rmt_spec.

get_proposed_paths
    Returns a ProposedPathsResponse object containing the proposed paths from the source table to the target field.
    used by the VsCode extension UI to get proposed paths for a given source table and target field.

_persist_model(config, out_path, exclude=None):
    Persists the given Pydantic model to the given path.

_get_notebookutils():
    Returns the notebookutils module if it is loaded, otherwise returns None.

"""
from pathlib import Path
import sys
from pyspark.sql import SparkSession
from configuration_compiler.configuration_content_wrapper import (
    DttConfigurationContentWrapper,
    RmtConfigurationContentWrapper,
)
from configuration_compiler.column_transformation.proposed_paths_generator import ProposedPathsResponse
from configuration_compiler.data_feed_configuration_compiler import DataFeedConfigurationCompiler
from configuration_compiler.mount_helpers import LocalFileSystemAccess

from configuration_compiler.path_helpers import uri_parent_path
from configuration_compiler.rmt_configuration_compiler import RMTConfigurationCompiler
from pydantic.main import BaseModel


def persist_dtt_spec(
    spark: SparkSession,
    out_path: str,
    dmf_adaptor_file_location: str = "",
    target_db_semantics_file_location: str = "",
    target_db_semantics_config_file_location: str = "",
    target_db_schema_file_location: str = "",
    db_schema_config_location: str = "",
    env_config_file_location: str = "",
    adaptor_file_content: str = "",
    target_db_semantics_file_content: str = "",
    target_db_semantics_config_file_content: str = "",
    target_db_schema_file_content: str = "",
    db_schema_config_content: str = "",
    env_config_file_content: str = "",
):
    """Generates a DTT spec from the given configuration files and persists it to the given path.
    Arguments:
        spark: SparkSession
        out_path: str, where to persist the spec
        adaptor_file_location: str, path to the adaptor configuration file
        target_db_semantics_file_location: str, path to the target DB semantics file
        target_db_semantics_config_file_location: str, path to the target DB semantics config file
        target_db_schema_file_location: str, path to the target DB schema file
        db_schema_config_location: str, path to the DB schema config file
        env_config_file_location: str, path to the environment config file
        adaptor_file_content: str, content of the adaptor configuration file
        target_db_semantics_file_content: str, content of the target DB semantics file
        target_db_semantics_config_file_content: str, content of the target DB semantics config file
        target_db_schema_file_content: str, content of the target DB schema file
        db_schema_config_content: str, content of the DB schema config file
        env_config_file_content: str, content of the environment config file
    """

    config_content_wrapper = DttConfigurationContentWrapper(
        spark=spark,
        adaptor_path=dmf_adaptor_file_location,
        target_db_semantics_path=target_db_semantics_file_location,
        target_db_semantics_config_path=target_db_semantics_config_file_location,
        target_db_schema_path=target_db_schema_file_location,
        db_schema_config_path=db_schema_config_location,
        env_config_path=env_config_file_location,
        dmf_adaptor_content=adaptor_file_content,
        target_db_semantics_content=target_db_semantics_file_content,
        target_db_semantics_config_content=target_db_semantics_config_file_content,
        target_db_schema_content=target_db_schema_file_content,
        db_schema_config_content=db_schema_config_content,
        env_config_content=env_config_file_content,
    )
    config = DataFeedConfigurationCompiler.compile_configuration(config_content_wrapper)

    out_path_parent = uri_parent_path(out_path)
    with LocalFileSystemAccess(out_path_parent, mode="w", notebookutils=_get_notebookutils()) as lfs:
        out_path_local = lfs.adapt_to_local_path(out_path)
        _persist_model(config, out_path_local)


def persist_rmt_spec(
    spark: SparkSession,
    out_path: str,
    adaptor_file_location: str = "",
    target_db_semantics_file_location: str = "",
    env_config_file_location: str = "",
    target_db_schema_file_location: str = "",
    db_schema_config_location: str = "",
    adaptor_file_content: str = "",
    target_db_semantics_file_content: str = "",
    target_db_schema_file_content: str = "",
    db_schema_config_content: str = "",
    env_config_file_content: str = "",
):
    """Generates an RMT spec from the given configuration files and persists it to the given path.
    Arguments:
        spark: SparkSession
        out_path: str, where to persist the spec
        adaptor_file_location: str, path to the adaptor configuration file
        target_db_semantics_file_location: str, path to the target DB semantics file
        env_config_file_location: str, path to the environment config file
        target_db_schema_file_location: str, path to the target DB schema file
        db_schema_config_location: str, path to the DB schema config file
        dmf_adaptor_file_content: str, content of the adaptor configuration file
        target_db_semantics_file_content: str, content of the target DB semantics file
        target_db_schema_file_content: str, content of the target DB schema file
        db_schema_config_content: str, content of the DB schema config file
        env_config_file_content: str, content of the environment config file
    """

    config_content_wrapper = RmtConfigurationContentWrapper(
        spark=spark,
        adaptor_path=adaptor_file_location,
        target_db_semantics_path=target_db_semantics_file_location,
        target_db_schema_path=target_db_schema_file_location,
        db_schema_config_path=db_schema_config_location,
        env_config_path=env_config_file_location,
        adaptor_content=adaptor_file_content,
        target_db_semantics_content=target_db_semantics_file_content,
        target_db_schema_content=target_db_schema_file_content,
        db_schema_config_content=db_schema_config_content,
        env_config_content=env_config_file_content,
    )
    config = RMTConfigurationCompiler.compile_rmt_model(config_content_wrapper)

    out_path_parent = uri_parent_path(out_path)
    with LocalFileSystemAccess(out_path_parent, mode="w", notebookutils=_get_notebookutils()) as lfs:
        out_path_local = lfs.adapt_to_local_path(out_path)
        _persist_model(config, out_path_local)


def generate_dtt_specs(
    spark: SparkSession,
    dtt_spec_out_path: str,
    rmt_spec_out_path: str,
    dmf_adaptor_file_location: str,
    target_db_semantics_file_location: str,
    target_db_semantics_config_file_location: str,
    target_db_schema_file_location: str,
    db_schema_config_location: str,
    env_config_file_location: str,
):
    """Generates DTT and RMT specs from the given configuration files and persists them to the given paths.
    Arguments:
        spark: SparkSession
        dtt_spec_out_path: str, where to persist the DTT spec
        rmt_spec_out_path: str, where to persist the RMT spec
        adaptor_file_location: str, path to the adaptor configuration file
        target_db_semantics_file_location: str, path to the target DB semantics file
        target_db_semantics_config_file_location: str, path to the target DB semantics config file
        target_db_schema_file_location: str, path to the target DB schema file
        db_schema_config_location: str, path to the DB schema config file
        env_config_file_location: str, path to the environment config file
    """
    persist_dtt_spec(
        spark=spark,
        out_path=dtt_spec_out_path,
        dmf_adaptor_file_location=dmf_adaptor_file_location,
        target_db_semantics_file_location=target_db_semantics_file_location,
        target_db_semantics_config_file_location=target_db_semantics_config_file_location,
        target_db_schema_file_location=target_db_schema_file_location,
        db_schema_config_location=db_schema_config_location,
        env_config_file_location=env_config_file_location,
    )
    persist_rmt_spec(
        spark=spark,
        out_path=rmt_spec_out_path,
        adaptor_file_location=dmf_adaptor_file_location,
        target_db_semantics_file_location=target_db_semantics_file_location,
        env_config_file_location=env_config_file_location,
        target_db_schema_file_location=target_db_schema_file_location,
        db_schema_config_location=db_schema_config_location,
    )


def get_proposed_paths(
    dmf_adaptor_file_location: str,
    target_db_semantics_file_location: str,
    target_db_schema_file_location: str,
    db_schema_config_location: str,
    source_table_name: str,
    source_field_name: str,
    target_table_name: str,
    target_field_name: str,
) -> ProposedPathsResponse:
    parent_path_uri = uri_parent_path(dmf_adaptor_file_location)
    with LocalFileSystemAccess(parent_path_uri, mode="r", notebookutils=_get_notebookutils()) as lfs:
        return DataFeedConfigurationCompiler.get_proposed_paths(
            adaptor_file_location=lfs.adapt_to_local_path(dmf_adaptor_file_location),
            target_db_semantics_file_location=lfs.adapt_to_local_path(target_db_semantics_file_location),
            target_db_schema_file_location=lfs.adapt_to_local_path(target_db_schema_file_location),
            db_schema_config_location=lfs.adapt_to_local_path(db_schema_config_location),
            source_table_name=source_table_name,
            source_field_name=source_field_name,
            target_table_name=target_table_name,
            target_field_name=target_field_name,
        )


def _persist_model(config: BaseModel, out_path: Path, exclude=None):
    json_str = config.model_dump_json(indent=2, by_alias=True, exclude=exclude)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json_str)


def _get_notebookutils():
    if "notebookutils" in sys.modules:
        return sys.modules["notebookutils"]
    return None
