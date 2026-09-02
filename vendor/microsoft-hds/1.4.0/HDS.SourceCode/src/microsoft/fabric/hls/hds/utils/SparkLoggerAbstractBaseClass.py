import abc
from typing import Mapping

class ABCSparkLogger(abc.ABC):
    """
    Abstract base class for Spark Logging
    """
    @abc.abstractmethod
    def info(self, message: str, extra: Mapping[str, object] | None = None):
        pass

    @abc.abstractmethod
    def error(self, message: str, extra: Mapping[str, object] | None = None):
        pass

    @abc.abstractmethod
    def debug(self, message: str, extra: Mapping[str, object] | None = None):
        pass

    @abc.abstractmethod
    def warning(self, message: str, extra: Mapping[str, object] | None = None):
        pass

    @abc.abstractmethod
    def critical(self, message: str, extra: Mapping[str, object] | None = None):
        pass
