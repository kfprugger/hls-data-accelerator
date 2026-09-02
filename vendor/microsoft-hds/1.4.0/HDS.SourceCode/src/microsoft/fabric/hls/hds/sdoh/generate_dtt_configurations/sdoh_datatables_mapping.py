# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import json


class SDOHdataTablesMapping:
    """
    A class that represents the mapping of SDOH data tables.

    Attributes:
        mapping (dict): A dictionary that stores the mapping of SDOH data tables.

    Methods:
        __init__(config_file): Initializes an instance of the SDOHdataTablesMapping class.
        get_mapping(): Returns the mapping of SDOH data tables.
    """

    def __init__(self, spark, config_file):
        """
        Initializes an instance of the SDOHdataTablesMapping class.

        Args:
            spark : SparkSession a SparkSession object to interact with the Spark cluster
            config_file (str): The path to the configuration file.

        """
        self.mapping = {}
        df_data_Tables = spark.read.text(
            config_file, wholetext=True).collect()[0][0]
        self.mapping = json.loads(df_data_Tables)

    def get_mapping(self):
        """
        Returns the mapping of SDOH data tables.

        Returns:
            dict: The mapping of SDOH data tables.

        """
        return self.mapping
