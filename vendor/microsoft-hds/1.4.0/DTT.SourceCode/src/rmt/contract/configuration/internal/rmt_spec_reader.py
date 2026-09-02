import json

import rmt.core.logger as logger
from rmt.contract.configuration.internal.model_internal import ModelInternal
from rmt.filesystem.file_system_client import FileSystemClient


class RMTSpecReader:
    @staticmethod
    def read(file_path: str, file_system_client: FileSystemClient) -> ModelInternal:
        logger.info("Reading RMT Spec")
        try:
            rmt_spec_content = file_system_client.get_file_content_from_path(file_path)
            rmt_spec_json = json.loads(rmt_spec_content)
            return ModelInternal(**rmt_spec_json)
        except Exception as e:
            raise IOError(f"Error reading RMT Spec from '{file_path}'") from e
