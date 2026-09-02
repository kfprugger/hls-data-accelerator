import json
from pathlib import Path
from typing import Optional, Union
from pyspark.sql import SparkSession
from py4j.protocol import Py4JJavaError


class Common:
    @staticmethod
    def parse_json_str(json_str: str) -> Union[dict, list[dict]]:
        return json.loads(json_str)

    @staticmethod
    def read_configuration_file(spark: SparkSession, file_path: str, fail_if_missing=True) -> Optional[str]:
        """Reads a configuration file from the given path. Uses SparkContext.wholeTextFiles to read the file."""
        rdd = spark.sparkContext.wholeTextFiles(file_path)
        try:
            return rdd.collect()[0][1]
        except Py4JJavaError as err:
            if "Input path does not exist" in str(err):
                if fail_if_missing:
                    raise FileNotFoundError(f"file {file_path} does not exist") from err
                return None
            raise err
        

    @staticmethod
    def read_local_configuration_file(file_path: Path, fail_if_missing=True) -> Optional[str]:
        """Reads a configuration file from the given path. Uses built-in open to read the file."""
        if not file_path.exists():
            if fail_if_missing:
                raise FileNotFoundError(f"file {file_path} does not exist")
            return None
        with open(file_path, encoding="utf-8") as fh:
            return fh.read()
