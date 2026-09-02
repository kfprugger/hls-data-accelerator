# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
import re
from abc import ABC, abstractmethod

class IScrub(ABC):
    """
    Interface for scrubbing sensitive information from messages.

    This interface defines a single method, `scrub`, which takes a message as input and returns a scrubbed version of the message.
    """
    @abstractmethod
    def scrub(self, msg: str):
        pass

class GuidScrubber(IScrub):
    """
    Scrubber for Globally Unique Identifiers (GUIDs).

    This class implements the `IScrub` interface. It scrubs GUIDs from messages by replacing them with a mask.

    Attributes:
        pattern (re.Pattern): The regex pattern for matching GUIDs.
        mask (str): The mask to replace GUIDs with.
    """
    # This pattern will match both hyphenated and non-hyphenated GUIDs
    pattern = re.compile(r'[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}|[0-9a-f]{32}', re.IGNORECASE)
    mask = "[guid redacted]"

    def scrub(self, msg: str) -> str:
        """
        Scrub GUIDs from a message.

        This method overrides the `scrub` method in the `IScrub` interface. It replaces all GUIDs in the message with the mask.

        Args:
            msg (str): The message to scrub.

        Returns:
            str: The scrubbed message.
        """
        return re.sub(self.pattern, self.mask, msg)