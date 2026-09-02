# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

class OpenAIConstants:
    """
    Class representing constants for OpenAI.
    """

    # Default temperature for generating text (controls randomness)
    DEFAULT_TEMPERATURE = 0

    # Default top-p value for generating text (controls diversity via nucleus sampling)
    DEFAULT_TOP_P = 0.95

    # Default frequency penalty for generating text (penalizes new tokens based on their frequency)
    DEFAULT_FREQUENCY_PENALTY = 0

    # Default presence penalty for generating text (penalizes new tokens based on their presence)
    DEFAULT_PRESENCE_PENALTY = 0

    # Default stop token for generating text (determines when to stop generating text)
    DEFAULT_STOP = None

    # Default stream mode for generating text (determines if the response should be streamed)
    DEFAULT_STREAM = False

    # Default model name for generating text
    MODEL_NAME = "gpt-4o"

    # System message for the AI assistant (provides context for the assistant)
    SYSTEM_MESSAGE = "You are an AI assistant that helps people find information in JSON format."

    # Default OpenAI tool for JSON formatting
    DEFAULT_OPEN_AI_TOOL_JSON = "analysis_schema_json"
    
    # Type of assistant (e.g., code interpreter)
    ASSISTANT_TYPE = "code_interpreter"