from abc import ABC, abstractmethod

class TokenProvider(ABC):

    @abstractmethod
    def get_token(self) -> str:
        pass