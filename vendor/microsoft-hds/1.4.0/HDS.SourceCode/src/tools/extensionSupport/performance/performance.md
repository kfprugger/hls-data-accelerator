# Performance

## Reading schemas

For measuring performance of the extension schema we will load several files using different schemas (original, full extension, minimal extension).

For this we will load schemas from the avro files:

```python

from pyspark.sql import types as T
from pyspark.sql import functions as F
import json

simple_schema_content = spark.sparkContext.wholeTextFiles(
            'abfss://dmytro_workspace@msit-onelake.dfs.fabric.microsoft.com/flatten.Lakehouse/Files/datamanager/.internal/.configuration/fhir_2_omop/transformation/flatten/fhir4.3/schema/patient.avsc').collect()[0][1]

simple_java_schema_type = spark.\
            _jvm.org.apache.spark.sql.avro.SchemaConverters.toSqlType(
                spark._jvm.org.apache.avro.Schema.Parser().parse(simple_schema_content) 
            )

simple_json_schema = json.loads(simple_java_schema_type.dataType().json())
simple_schema = T.StructType.fromJson(simple_json_schema)

```

## Executing performance test on simple file

We will load a several files starting from about dozen records up to 10000 records to measure average values of loading file with provided schema, and preserving file with provided schemas.    

```python
import time
input_file = 'Files/exportlandingzone/simlest/Patient.ndjson'


start_time_load = time.time()
df_simple = spark.read.format('json').json(input_file,simple_schema)
end_time_load = time.time()
load_time = end_time_load-start_time_load

print (f'Original Schema load time: {load_time}. Count: {df_simple.count()}. Time per row - {load_time/df_simple.count()}')

```

Than we will measure save time in delta format (in that case append mode for simplicity):

```
start_time_write = time.time()
df_simple.write.format('delta').mode('append').save(f'Files/checkpoint/performance/{resoutrceType}_simple.delta')
end_time_write = time.time()
write_time = end_time_write-start_time_write

print (f'Original Schema write time: {write_time}. Count: {df_simple.count()}. Time per row - {write_time/df_simple.count()}')
```

### Results of loading files:

Type | File size | Original Schema time(s) | Full Schema time(s) | Partial Schema time(s) |
--- | --- | --- | --- | --- |
Patient - test data (full load time) | 6 records | 0.111 | 4.052 | 0.312 |
Patient - test data (load per record) | 6 records | 0.0185 | 0.675 | 0.052 |
Patient - test data (full write time) | 6 records | 2.720 | 53.133 |5.373  |
Patient - test data (write per record) | 6 records | 0.453 | 8.855 | 0.895 |
Patient -1k rec load| 1111 records | 0.105 | 2.846 | 0.282 |
Patient -1k rec load per row| 1111 records | 9.441e-05 | 0.003 | 0.00025 |
Patient -1 rec write| 1111 records | 2.896 | 39.808 | 6.005 |
Patient -1 rec write per row | 1111 records | 0.0026 | 0.036 | 0.005 |
Patient -11k rec load| 11213 records | 0.364966 | 3.737882 | 0.296803 |
Patient -11k rec load per row| 11213 records | 0.000033 | 0.000333 | 0.000026 |
Patient -11k rec write| 11213 records | 5.462525 | 100.611278 | 14.713146 |
Patient -11k rec write per row | 11213 records | 0.000487 | 0.008973 | 0.001312 |
