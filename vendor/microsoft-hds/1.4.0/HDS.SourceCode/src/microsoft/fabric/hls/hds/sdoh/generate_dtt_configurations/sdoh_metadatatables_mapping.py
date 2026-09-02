# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

import json
class SDOHMetaDataTablesMapping:
    """
    A class that represents the mapping of SDOH metadata tables.

    Attributes:
        mapping (dict): A dictionary that stores the mapping of SDOH metadata tables.

    Methods:
        __init__(config_file): Initializes an instance of the SDOHMetaDataTablesMapping class.
        get_mapping(): Returns the mapping of SDOH metadata tables.
    """

    def __init__(self,spark, config_file):
        """
        Initializes an instance of the SDOHMetaDataTablesMapping class.

        Args:
            spark : SparkSession a SparkSession object to interact with the Spark cluster
            config_file (str): The path to the configuration file.

        """
        # Initialize an empty dictionary to store the mapping
        self.mapping = {}
        df_metadata_Tables = spark.read.text(
            config_file, wholetext=True).collect()[0][0]
        self.mapping = json.loads(df_metadata_Tables)

    def get_mapping(self):
        """
        Returns the mapping of SDOH metadata tables.

        Returns:
            dict: The mapping of SDOH metadata tables.

        """
        return self.mapping
