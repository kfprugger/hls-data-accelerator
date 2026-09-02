from pathlib import Path
from typing import List, Any, Optional

from common.utils.logging import Logger
from dmf.utils.utils import T


class Common:
    @staticmethod
    def read_configuration_file(file_path: Path) -> str:
        Logger.info(f"Configuration will be read from file '{file_path}'")
        with open(file_path) as fh:
            return fh.read()

    @staticmethod
    def build_and_condition_from_list(conditional_values: List[Any], left_prefix: Optional[T],
                                      right_prefix: Optional[T], comparison="=") -> str:
        if not conditional_values:
            raise ValueError("No conditional values provided")

        if left_prefix:
            left_prefix = f"{left_prefix}."
        else:
            left_prefix = ""
        if right_prefix:
            right_prefix = f"{right_prefix}."
        else:
            right_prefix = ""

        return " AND ".join([f"{left_prefix}{value} {comparison} {right_prefix}{value}" for value in conditional_values])
