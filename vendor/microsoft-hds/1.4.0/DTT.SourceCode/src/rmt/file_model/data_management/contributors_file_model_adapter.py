from typing import Dict

from rmt.core.data_management.contributor import Contributor, KeysRange
from rmt.file_model.data_management.contributors_file_model import ContributorFileModel, ContributorsFileModel


class ContributorsFileModelAdapter:

    @staticmethod
    def to_core_model(file_model: ContributorsFileModel) -> Dict[str, Contributor]:
        return {k.contributor: ContributorsFileModelAdapter.contributor_file_model_to_core_model(k) for k in file_model.contributors}

    @staticmethod
    def contributor_file_model_to_core_model(file_model: ContributorFileModel) -> Contributor:
        return Contributor(name=file_model.contributor, keys_range=KeysRange(file_model.idRange.min, file_model.idRange.max))
