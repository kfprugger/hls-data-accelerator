import sys
import logging
import uuid
import inspect
from microsoft.fabric.hls.hds.global_constants.logging_constants import LoggingConstants as LC

class WorkerExecutionLogger:
    """
    A logger class designed to log operations without Spark dependencies.
    This logger supports logging to the console and includes additional metadata
    such as pipeline run IDs and unique run IDs for better traceability.
    """

    def __init__(self, logger_name: str, log_level: int = logging.DEBUG, **kwargs):
        """
        Initializes the WorkerExecutionLogger instance.

        Args:
            logger_name (str): The name of the logger, typically used to identify the source of logs.
            log_level (int): The default logging level (e.g., DEBUG, INFO). Defaults to logging.DEBUG.
            **kwargs: Additional optional arguments:
                - pipeline_run_id (str): An identifier for the pipeline run.
                - run_id (str): A unique identifier for the current run. If not provided, a UUID is generated.
        """
        self._logger_name = logger_name
        self._log_level = log_level
        self._pipeline_run_id = kwargs.get("pipeline_run_id")  # Optional pipeline run ID
        self._run_id = kwargs.get("run_id", str(uuid.uuid4()))  # Generate a unique run ID if not provided

        # Define the log format for console output
        log_format = logging.Formatter("%(asctime)s::%(name)s::%(levelname)s::%(message)s")

        # Create a console handler to output logs to stdout
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_format)

        # Create a logger name for stdout using a predefined format
        stdout_logger_name = LC.ConsoleLoggerName.format(logger_name=logger_name)
        self._stdout_logger = logging.getLogger(stdout_logger_name)
        self._stdout_logger.setLevel(logging.DEBUG)  # Default to DEBUG level for the logger

        # Clear any existing handlers to avoid duplicate log entries
        if self._stdout_logger.hasHandlers():
            self._stdout_logger.handlers.clear()
        self._stdout_logger.addHandler(console_handler)

        # Prevent log messages from propagating to the root logger
        self._stdout_logger.propagate = False

    def debug(self, message: str, *args, **kwargs):
        """
        Logs a message at the DEBUG level.

        Args:
            message (str): The message to log.
            *args: Additional positional arguments for the logger.
            **kwargs: Additional keyword arguments for the logger.
        """
        self._log_message(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        """
        Logs a message at the INFO level.

        Args:
            message (str): The message to log.
            *args: Additional positional arguments for the logger.
            **kwargs: Additional keyword arguments for the logger.
        """
        self._log_message(logging.INFO, message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        """
        Logs a message at the WARNING level.

        Args:
            message (str): The message to log.
            *args: Additional positional arguments for the logger.
            **kwargs: Additional keyword arguments for the logger.
        """
        self._log_message(logging.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        """
        Logs a message at the ERROR level.

        Args:
            message (str): The message to log.
            *args: Additional positional arguments for the logger.
            **kwargs: Additional keyword arguments for the logger.
        """
        self._log_message(logging.ERROR, message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs):
        """
        Logs a message at the CRITICAL level.

        Args:
            message (str): The message to log.
            *args: Additional positional arguments for the logger.
            **kwargs: Additional keyword arguments for the logger.
        """
        self._log_message(logging.CRITICAL, message, *args, **kwargs)

    def _log_message(self, level: int, message: str, *args, **kwargs):
        """
        Internal helper method to log a message with additional metadata.

        Args:
            level (int): The logging level (e.g., DEBUG, INFO).
            message (str): The message to log.
            *args: Additional positional arguments for the logger.
            **kwargs: Additional keyword arguments for the logger.
        """
        # Retrieve the calling function's name for better traceability
        func = inspect.currentframe().f_back.f_code
        # Format the log message to include the function name, run ID, and the actual message
        logging_message = f"{func.co_name}::{LC.RunId}::{self._run_id}::{message}"
        # Log the message at the specified level
        self._stdout_logger.log(level, logging_message, *args, **kwargs)

    def set_run_id(self, run_id: str) -> None:
        """
        Updates the run ID for the logger.

        Args:
            run_id (str): The new run ID to set.
        """
        self._run_id = run_id