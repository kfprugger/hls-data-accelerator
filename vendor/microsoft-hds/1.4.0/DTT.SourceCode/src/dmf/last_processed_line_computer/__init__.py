"""
this package can run as a spark job and compute the last processed line for each source table.
This data is used later as input for processors reading the different source table in order to filter their input data.

1. dmf-configuration/dmfAdaptof.json is parsed to compute for each source table which target tables are effected
2. for rach source table all target tables are queried for the latest SourceModifiedOn and then the latest value of
    those is returned. For empty tables, datetime.min is returned

the main entry point:
compute_last_processed_line_for_all_source_tables.compute_last_processed_line_for_all_source_tables
"""
