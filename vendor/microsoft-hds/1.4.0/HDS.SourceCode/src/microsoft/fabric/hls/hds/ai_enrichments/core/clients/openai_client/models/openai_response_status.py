# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
from dataclasses import dataclass
from enum import Enum

@dataclass
class OpenAIResponseStatus(Enum):
    SUCCESS = "Success"  # Indicates a successful response
    FAILURE = "Failure"  # Indicates a failed response