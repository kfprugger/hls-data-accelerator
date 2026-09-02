import abc


class IRMTLogger(abc.ABC):
    @abc.abstractmethod
    def info(self, message: str):
        pass

    @abc.abstractmethod
    def error(self, message: str):
        pass

    @abc.abstractmethod
    def debug(self, message: str):
        pass

    @abc.abstractmethod
    def warn(self, message: str):
        pass

    @abc.abstractmethod
    def exception(self, message: str):
        pass


logger: IRMTLogger = None


def set_logger(_logger: IRMTLogger):
    global logger
    logger = _logger


def info(message: str):
    logger.info(message)


@abc.abstractmethod
def error(message: str):
    logger.error(message)


@abc.abstractmethod
def debug(message: str):
    logger.debug(message)


@abc.abstractmethod
def warn(message: str):
    logger.warn(message)


@abc.abstractmethod
def exception(message: str):
    logger.exception(message)
