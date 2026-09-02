from typing import List, Set, Tuple

from rmt.core import logger
from rmt.core.core_exceptions import UpdateError, UpdateValueError
from rmt.core.data_management.abstract_authoring_data_reader import AbstractAuthoringDataReader
from rmt.core.data_management.abstract_authoring_mapping_reader import AbstractAuthoringMappingReader
from rmt.core.data_management.abstract_contributors_reader import AbstractContributorsReader
from rmt.core.data_management.abstract_repository_folder_table_data_reader import AbstractRepositoryFolderTableDataReader
from rmt.core.data_management.abstract_repository_folder_table_data_writer import AbstractRepositoryFolderTableDataWriter
from rmt.core.data_management.abstract_repository_folder_table_mapping_reader import AbstractRepositoryFolderTableMappingReader
from rmt.core.data_management.abstract_repository_folder_table_mapping_writer import AbstractRepositoryFolderTableMappingWriter
from rmt.core.data_management.authoring_data_adapter import AuthoringDataAdapter
from rmt.core.data_management.authoring_mapping_adapter import AuthoringMappingAdapter
from rmt.core.data_management.contributor import Contributor, ContributorType
from rmt.core.data_management.contributor_repository_updater import ContributorRepositoryUpdater
from rmt.core.data_management.primitive_types import TableName
from rmt.core.data_management.repository import Repository
from rmt.core.data_management.table_data import TableData
from rmt.core.data_management.table_mapping import TableMapping
from rmt.core.data_management.tables_validator import TablesValidator


class RepositoryUpdater:
    """
    This class support the user story of updating
    the repository folder (=staging as currently apear in API, just different terminology)
    The class is responsible for updating the repository folder with the data and mapping of the customer contributor
    as read from the authoring data and mapping files (the csv files)
    for each given table data of customer it will override the data of the customer for that table in repository folder
    same for mapping. note we are only writing customer data and mapping to the repository folder
    if a customer authoring data for some table is same as the customer data for that table in repository
    it will not update the repository folder.same for mapping.
    if a customer authoring data or mapping for some table is not valid it will not update the repository folder at all
    and write an error to the log
    for the user to be able to follow errors and fix them we want to collect as much errors as we can
    and not stop at the first error.so first checking authoring data and mapping and then write all errors
    if all authoring data and mapping is valid then continue read from repository folder the data and mapping
    for the tables which appear in the authoring data and mapping, from all contributors to the repository class
    which represents the repository folder.
    then update the repository class with the customer data and mapping and get what was actually changed
    then validate the tables that was changed (with all data and mapping from all contributors)
    and if valid write the those tables data and mapping to the repository folder
    validations (as explained above are done first on the authoring data and mapping and then with all data and mapping from all contributors in the repository folder)
    1. each table data has unique keys and unique names
    2. each table mapping has unique source values across all target keys (no same source value for different target keys)
    3. each mapping target key must exist in the table data keys
    4. each data key from some contributor must be in the range of the contributor keys
    5. each contributor name in the authoring data and mapping must be a valid contributor name
    (the authoring data and mapping contains data and mapping from all contributors only for the user to follow, when we read we ignore
    authoring data and mapping from other contributors than the customer contributor, still we validate the contributors names
    in the authoring data and mapping to make sure the data or mapping is not corrupted)
    """

    @staticmethod
    def update_repository_folder_reference_data(
        authoring_data_reader: AbstractAuthoringDataReader,
        authoring_mapping_reader: AbstractAuthoringMappingReader,
        repository_contributors_reader: AbstractContributorsReader,
        repository_folder_table_mapping_reader: AbstractRepositoryFolderTableMappingReader,
        repository_folder_table_data_reader: AbstractRepositoryFolderTableDataReader,
        repository_folder_table_mapping_writer: AbstractRepositoryFolderTableMappingWriter,
        repository_folder_table_data_writer: AbstractRepositoryFolderTableDataWriter,
    ):
        # read contributors
        contributors = repository_contributors_reader.read()

        for contributor in contributors:
            if contributor.name == ContributorType.Customer.name:
                customer_contributor = contributor
                break
        if customer_contributor is None:
            logger.error("Customer contributor not found")
            return

        authoring_valid = True
        # read authoring table mapping
        try:
            customer_table_mapping_list, mapping_authoring_errors = RepositoryUpdater._get_customer_table_mapping_list(authoring_mapping_reader, customer_contributor, contributors)
            for error in mapping_authoring_errors:
                logger.error(f"{error}")
        except ValueError as e:
            logger.error(f"Error reading customer mapping authoring: {e}")
            authoring_valid = False

        # read authoring table data
        try:
            customer_table_data_list, data_authroing_errors = RepositoryUpdater._get_customer_table_date_list(authoring_data_reader, customer_contributor, contributors)
            for error in data_authroing_errors:
                logger.error(f"{error}")
        except ValueError as e:
            logger.error(f"Error reading customer data authoring: {e}")
            authoring_valid = False

        # return if not any authoring is not valid
        if not authoring_valid:
            raise UpdateError("No data was updated. Validation errors found.")

        # create repository and read data and mapping of the relevant tables from repository folder to repository class
        repository = RepositoryUpdater._get_repository_with_tables_data_and_mapping(contributors, repository_folder_table_mapping_reader, repository_folder_table_data_reader)

        # complete table data and mapping list of customer from repository (for deleted tables)
        customer_table_data_list = RepositoryUpdater._complete_table_data_list_of_contributor_from_repository(customer_contributor, repository, customer_table_data_list)

        customer_table_mapping_list = RepositoryUpdater._complete_table_mapping_list_of_contributor_from_repository(customer_contributor, repository, customer_table_mapping_list)

        # update repository with the customer data and mapping (and get what was updated)
        customer_repository_updater = ContributorRepositoryUpdater(repository, customer_contributor)
        updated_table_mapping_list = customer_repository_updater.set_table_mapping_list(customer_table_mapping_list)
        updated_table_data_list = customer_repository_updater.set_table_data_list(customer_table_data_list)

        # get union of updated table names
        updated_tables_names = RepositoryUpdater._get_table_names(updated_table_data_list, updated_table_mapping_list)

        # validate updated tables and if valid, write to updated data and mapping to repository folder
        tables_validator = TablesValidator(repository)
        if tables_validator.validate_tables(updated_tables_names) and len(mapping_authoring_errors + data_authroing_errors) == 0:
            logger.info("Validation passed. Updating repository folder with the updated data and mapping.")
            repository_folder_table_mapping_writer.write(customer_contributor.name, updated_table_mapping_list)
            repository_folder_table_data_writer.write(customer_contributor.name, updated_table_data_list)
        else:
            if tables_validator.validation_errors:
                for error in tables_validator.validation_errors:
                    logger.error(f"{error}")
            raise UpdateError("No data was updated. Validation errors found.")

    @staticmethod
    def _get_table_names(table_data_list: List[TableData], table_mapping_list: List[TableMapping]) -> Set[TableName]:
        return set([table_data.table_name for table_data in table_data_list] + [table_mapping.table_name for table_mapping in table_mapping_list])

    @staticmethod
    def _get_customer_table_date_list(
        authoring_data_reader: AbstractAuthoringDataReader, customer_contributor: Contributor, contributors: Set[Contributor]
    ) -> Tuple[List[TableData], List[UpdateValueError]]:
        authoring_data_entries, read_errors = authoring_data_reader.read(customer_contributor, contributors)
        authoring_data_adapter = AuthoringDataAdapter(contributors)
        table_data_list, convert_errors = authoring_data_adapter.get_table_data_for_contributor(authoring_data_entries, customer_contributor)
        return table_data_list, read_errors + convert_errors

    @staticmethod
    def _get_customer_table_mapping_list(
        authoring_mapping_reader: AbstractAuthoringMappingReader, customer_contributor: Contributor, contributors: Set[Contributor]
    ) -> Tuple[List[TableMapping], List[UpdateValueError]]:
        authoring_mapping_entries, read_errors = authoring_mapping_reader.read(customer_contributor, contributors)
        authoring_mapping_adapter = AuthoringMappingAdapter(contributors)
        table_mapping_list, convert_errors = authoring_mapping_adapter.get_table_mapping_for_contributor(authoring_mapping_entries, customer_contributor)
        return table_mapping_list, read_errors + convert_errors

    @staticmethod
    def _complete_table_data_list_of_contributor_from_repository(customer_contributor: Contributor, repository: Repository, table_data_list: List[TableData]) -> List[TableData]:

        repository_table_names = repository.get_data_table_names_for_contributor(customer_contributor)
        authoring_table_names = set([table_data.table_name for table_data in table_data_list])
        for table_name in repository_table_names:
            if table_name not in authoring_table_names:
                table_data = TableData(table_name)
                table_data_list.append(table_data)
        return table_data_list

    @staticmethod
    def _complete_table_mapping_list_of_contributor_from_repository(
        customer_contributor: Contributor, repository: Repository, table_mapping_list: List[TableMapping]
    ) -> List[TableMapping]:

        repository_table_names = repository.get_mapping_table_names_for_contributor(customer_contributor)
        authoring_table_names = set([table_mapping.table_name for table_mapping in table_mapping_list])
        for table_name in repository_table_names:
            if table_name not in authoring_table_names:
                table_mapping = TableMapping(table_name)
                table_mapping_list.append(table_mapping)
        return table_mapping_list

    @staticmethod
    def _get_repository_with_tables_data_and_mapping(
        contributors: Set[Contributor],
        repository_folder_table_mapping_reader: AbstractRepositoryFolderTableMappingReader,
        repository_folder_table_data_reader: AbstractRepositoryFolderTableDataReader,
    ) -> Repository:
        repository = Repository(contributors)

        for contributor in contributors:
            table_data_list = repository_folder_table_data_reader.read(contributor.name)
            repository.add_table_data_list(contributor, table_data_list)

            table_mapping_list = repository_folder_table_mapping_reader.read(contributor.name)
            repository.add_table_mapping_list(contributor, table_mapping_list)

        return repository
