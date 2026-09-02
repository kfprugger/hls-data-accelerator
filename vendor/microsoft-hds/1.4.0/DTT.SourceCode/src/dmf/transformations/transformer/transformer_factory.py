from dmf.model.target_configuration.target_configuration import TargetConfiguration
from dmf.transformations.transformer.duration_transformer import DurationTransformer
from dmf.transformations.transformer.simple_transformer import SimpleTransformer
from dmf.transformations.transformer.transformer import Transformer


class TransformerFactory:

    @staticmethod
    def get_instance(config: TargetConfiguration, id: str) -> Transformer:
        if config.temporal_tables_semantics:
            return DurationTransformer(id, config.target_id)
        return SimpleTransformer(id, config.target_id)
