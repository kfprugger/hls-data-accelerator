from abc import ABC, abstractmethod

from dmf.transformations.model.transformation_types import TransformationData, TransformationMetaData


class Transformer(ABC):

    @abstractmethod
    def transform(self, data: TransformationData, metadata: TransformationMetaData):
        raise NotImplementedError()
