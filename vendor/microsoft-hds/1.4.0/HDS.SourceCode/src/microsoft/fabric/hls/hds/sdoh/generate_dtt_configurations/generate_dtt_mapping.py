# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

class DTTMappingGenerator:
    """
    This class is used to generate DTT adapter configuration mapping for source to target tanles and teir attributes.
    It is responsible for generating DTT mapping configurations based on the provided source-to-target mappings,
    queries, and table name.

    Attributes:
        arrSDOHsourceToTargetMapping (dict): A dictionary containing the source-to-target mappings.
        queries (str): The queries associated with the source tables.
        tableName (str): The name of the target table.

    Methods:
        generate_dtt_mapping: Generates DTT mapping configurations based on the provided attributes.
    """

    def __init__(self, arrSDOHsourceToTargetMapping=None, queries=None, tableName=''):
        
        if arrSDOHsourceToTargetMapping is None:
         arrSDOHsourceToTargetMapping = {}
        if queries is None:
         queries = ''
         
        self.arrSDOHsourceToTargetMapping = arrSDOHsourceToTargetMapping
        self.queries = queries
        self.tableName = tableName

    def generate_dtt_mapping(self):
        """
        Generates DTT mapping configurations based on the provided source-to-target mappings,
        queries, and table name.

        Returns:
           generator: A generator that yields DTT mapping configurations.
        """
        for SourceTable, mappings in self.arrSDOHsourceToTargetMapping.items():
            yield {
                "tableName": f"{self.tableName}_{SourceTable}" if self.tableName else SourceTable,
                "query": self.queries[SourceTable],
                "modifiedonField": "modifiedon",
                "targetAnchorTables": [
                    {
                        "tableName": mappings[0]['targettable'] if mappings and len(mappings) > 0 else None
                    }
                ],
                "enabled": True,
                "sourceFields": [
                    {
                        "fieldName": mapping['sourcefield'],
                        "fieldType": mapping['fieldType'],
                        "enabled": True,
                        "targetFields": {
                            "fields": [
                                {
                                    "tableName": mapping['targettable'],
                                    "fieldName": mapping['targetfield'],
                                     **({"targetField": mapping.get('targetField')} if mapping.get('targetField') is not None else {})
                                }
                            ]
                        }
                    } for mapping in mappings
                ]
            }