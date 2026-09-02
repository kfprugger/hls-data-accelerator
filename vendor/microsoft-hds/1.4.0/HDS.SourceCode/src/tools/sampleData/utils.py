import json
import re
import glob
import os
import time

class Utils:
    @staticmethod
    def parse_reference_id(reference_id):
        if reference_id:
            try:
                return reference_id.split('/')[1]
            except:
                pass
        return reference_id
    
    @staticmethod
    def create_output_path(output_dir, operation_name):
        timestamp = int(time.time())
        output_path = f"{output_dir}/{operation_name}/{timestamp}"
        os.makedirs(output_path, exist_ok=True)
        return output_path
    
    @staticmethod
    def load_record(data):
        try:
            return json.loads(data)
        except Exception:
            corrected_json_string = re.sub(r'\\(?![bfnrtu"])', r'\\\\', data)
            return json.loads(corrected_json_string)

    @staticmethod
    def get_nested_value(json_dict, path):
        keys = path.split('.')
        value = json_dict
        try:
            for key in keys:
                value = value[key]
            return value
        except:
            return None

    @staticmethod
    def import_data(sample_data_file, fields, accumulator):
        print (f"Importing data from {sample_data_file}")
        with open(sample_data_file, 'r', encoding='utf-8-sig') as f:
            record_count = 0
            for line in f:
                record_count += 1
                json_dict = Utils.load_record(line)
                record = {}
                for key, value in fields.items():
                    record[key] = Utils.get_nested_value(json_dict, value)
                record['source_file'] = sample_data_file
                accumulator[json_dict['id']] = record
            print(f"Imported {record_count} records")
        return accumulator
    
    @staticmethod
    def import_data_types(data_type_imports, sample_data_path):
        data = {}

        for data_type_import in data_type_imports:
            data_type = data_type_import['data_type']
            fields = data_type_import['fields']
            print(f"Importing {data_type} data")
            accumulator = {}
            data_files = glob.glob(f"{sample_data_path}/{data_type}*.ndjson")
            for data_file in data_files:
                accumulator = Utils.import_data(data_file, fields, accumulator)
            data[data_type] = accumulator
            print(f"Total number of {data_type} resources: {len(accumulator)}")

        return data

    @staticmethod
    def import_record_ids(record_ids_path):
        record_ids = []
        with open(record_ids_path, 'r') as f:
            for line in f:
                record_ids.append(line.strip())
        print(f"Total number of record_ids: {len(record_ids)}")
        return record_ids