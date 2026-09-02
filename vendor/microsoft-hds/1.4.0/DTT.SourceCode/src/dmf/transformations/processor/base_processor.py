from abc import ABC, abstractmethod


class BaseProcessor(ABC):
    @abstractmethod
    def process(self):
        raise NotImplementedError()

    @abstractmethod
    def read(self):
        raise NotImplementedError()
