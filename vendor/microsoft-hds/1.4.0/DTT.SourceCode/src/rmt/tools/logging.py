"""
This package creates global Logger
"""

from common.utils.logging import Logger as CommonLogger

from rmt.core.logger import IRMTLogger


class RMTCommonLogger(IRMTLogger):

    def __init__(self):
        CommonLogger.init_logger()
        self._logger = CommonLogger

    def info(self, message: str):
        self._logger.info(message)

    def error(self, message: str):
        self._logger.error(message)

    def debug(self, message: str):
        self._logger.debug(message)

    def warn(self, message: str):
        self._logger.warn(message)

    def exception(self, message: str):
        self._logger.exception(message)


class Logger:
    _logger = None

    @classmethod
    def init_logger(cls) -> IRMTLogger:
        cls._logger = RMTCommonLogger()
        return cls._logger

    @staticmethod
    def info(message: str):
        Logger._logger.info(message)

    @staticmethod
    def error(message: str):
        Logger._logger.error(message)

    @staticmethod
    def debug(message: str):
        Logger._logger.debug(message)

    @staticmethod
    def warn(message: str):
        Logger._logger.warn(message)

    @staticmethod
    def exception(message: str):
        Logger._logger.exception(message)
