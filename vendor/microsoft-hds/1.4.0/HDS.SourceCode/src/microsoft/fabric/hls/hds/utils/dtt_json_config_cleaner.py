import json
from pyspark.sql import SparkSession
from typing import Dict
from microsoft.fabric.hls.hds.utils.mssparkutils_client_base import MSSparkUtilsClientBase
from microsoft.fabric.hls.hds.utils.logging_helper import LoggingHelper
from microsoft.fabric.hls.hds.global_constants.global_constants import GlobalConstants


class JsonConfigCleaner:
    def __init__(self, spark: SparkSession, mssparkutils_client: MSSparkUtilsClientBase):
        self.spark = spark
        self.mssparkutils_client = mssparkutils_client
        self._logger = LoggingHelper.get_generic_logger(
            spark, self.__class__.__name__, GlobalConstants.LOGGING_LEVEL
        )

    def _looks_like_json_path(self, s: str) -> bool:
        """Cheap check for .json file paths."""
        return isinstance(s, str) and s.strip().lower().endswith(".json")

    def _looks_like_json_string(self, s: str) -> bool:
        """Cheap pre-check to avoid raising on plain text."""
        if not isinstance(s, str):
            return False
        s = s.lstrip()
        return s.startswith("{") or s.startswith("[")


    def recursively_remove_key(self, obj, keys_to_remove=None):
        if keys_to_remove is None:
            keys_to_remove = {"isPrimaryKey", "IsPrimaryKey"}
        """Recursively removes specified keys from JSON-like dictionaries or lists."""
        if isinstance(obj, dict):
            return {
                k: self.recursively_remove_key(v, keys_to_remove)
                for k, v in obj.items()
                if k not in keys_to_remove
            }
        elif isinstance(obj, list):
            return [self.recursively_remove_key(item, keys_to_remove) for item in obj]
        return obj

    def clean_config_files_dict(self, config_files: Dict[str, str]) -> None:
        """
        Cleans all values in the input config_files dict in-place.

        - If the value is a path (ending with `.json`), reads from file, cleans, and overwrites the file.
        - If the value is a raw JSON string, parses, cleans, and updates the dict in-place.
        - If the value is neither a .json path nor a JSON string, skip with a warning (non-fatal).
        """
        for key, value in config_files.items():
            # 1) Type gate
            if not isinstance(value, str):
                self._logger.warning(f"[{key}] Skipped: config value is not a string (type={type(value)}).")
                continue

            val = value.strip()

            # 2) File path branch
            if self._looks_like_json_path(val):
                self._logger.info(f"[{key}] Reading JSON file from path: {val}")
                try:
                    file_content_rows = self.spark.read.text(val, wholetext=True).collect()
                except Exception as e:
                    # True I/O/Spark issue -> error
                    self._logger.error(f"[{key}] Failed to read file path {val}: {e}")
                    continue

                if not file_content_rows:
                    # Expected-but-unhappy path -> warning (don’t fail the run)
                    self._logger.warning(f"[{key}] No content found in file: {val}")
                    continue

                file_content = file_content_rows[0][0]
                try:
                    json_data = json.loads(file_content)
                except Exception as e:
                    # Malformed content in a .json file -> error (actionable)
                    self._logger.error(f"[{key}] Malformed JSON in file {val}: {e}")
                    continue

                cleaned_data = self.recursively_remove_key(json_data)
                cleaned_str = json.dumps(cleaned_data, indent=2)
                try:
                    self.mssparkutils_client.fs_put(val, cleaned_str, overwrite=True)
                    self._logger.info(f"[{key}] Cleaned and overwritten file successfully.")
                except Exception as e:
                    self._logger.error(f"[{key}] Failed to write cleaned JSON to {val}: {e}")
                continue  # done with file branch

            # 3) Raw JSON string branch (cheap pre-check prevents false positives)
            if self._looks_like_json_string(val):
                try:
                    json_data = json.loads(val)
                except Exception as e:
                    # Looks like JSON but not valid -> warning, skip
                    self._logger.warning(f"[{key}] Provided string appears to be JSON but is malformed: {e}")
                    continue

                cleaned_data = self.recursively_remove_key(json_data)
                config_files[key] = json.dumps(cleaned_data, indent=2)
                self._logger.info(f"[{key}] Cleaned JSON string updated in-place.")
                continue

            # 4) Neither file nor JSON -> soft skip
            self._logger.warning(f"[{key}] Skipped: value is neither a .json path nor a JSON string.")
