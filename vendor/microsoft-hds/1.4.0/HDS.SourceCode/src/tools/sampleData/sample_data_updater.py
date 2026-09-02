import json
import sys
import glob
import os
from utils import Utils
from patient_utils import PatientUtils
            
def find_keyword_in_file(sample_data_file, keyword):
    print (f"Finding keyword in {sample_data_file}")
    ids = []
    with open(sample_data_file, 'r', encoding='utf-8-sig') as f:
        recordcount = 0
        for line in f:
            if line.lower().find(keyword.lower()) != -1:
                json_dict = Utils.load_record(line)
                recordcount += 1
                ids.append(json_dict['id'])
        print(f"Found keyword in {recordcount} records")
    return ids
        
def keyword_record_lookup(keyword_lookup_args):
    sample_data_path = keyword_lookup_args['sample_data_path']
    data_type_imports = keyword_lookup_args['imports']
    output_path = keyword_lookup_args['output_path']
    records_dict = {}
    
    for data_type_import in data_type_imports:
        data_type = data_type_import['data_type']
        data_files = glob.glob(f"{sample_data_path}/{data_type}*.ndjson")
        for data_file in data_files:
            records_dict[data_file] = find_keyword_in_file(data_file, "cesarean")
            
    with open(f"{output_path}/keyword_records.json", 'w') as f:
        json.dump(records_dict, f, indent=2)
        
def filter_records(sample_data_path, data_type, record_ids, output_path):
    data_files = glob.glob(f"{sample_data_path}/{data_type}*.ndjson")
    for data_file in data_files:
        print(f"Filtering records in {data_file}")
        removed_count = 0
        file_name = os.path.basename(data_file)
        file_path = f"{output_path}/{file_name}"
        with open(data_file, 'r') as infile, open(file_path, 'w') as outfile:
            for line in infile:
                json_dict = Utils.load_record(line)
                if json_dict['id'] not in record_ids:
                    outfile.write(json.dumps(json_dict) + '\n')
                else:
                    removed_count += 1
        print(f"Removed {removed_count} records from path: {data_file}")
        print(f"New records file saved to {file_path}")
        
def reference_record_ids(sample_data_path, data_type, record_ids, reference_path, output_path):
    data_files = glob.glob(f"{sample_data_path}/{data_type}*.ndjson")
    reference_record_ids_path = f"{output_path}/reference_record_ids.json"
    for data_file in data_files:
        print(f"Finding reference record ids in {data_file}")
        with open(data_file, 'r') as infile:
            for line in infile:
                json_dict = Utils.load_record(line)
                if json_dict['id'] in record_ids:
                    reference_id = Utils.get_nested_value(json_dict, reference_path)
                    reference_record_id = Utils.parse_reference_id(reference_id)
                    with open(reference_record_ids_path, 'a') as f:
                        f.write(f"{reference_record_id}\n")
        print(f"Reference record ids file saved to {reference_record_ids_path}")

def remove_records(remove_records_args):
    sample_data_path = remove_records_args['sample_data_path']
    data_type = remove_records_args['data_type']
    record_ids_path = remove_records_args['record_ids_path']
    output_path = remove_records_args['output_path']
    
    record_ids = Utils.import_record_ids(record_ids_path)
    filter_records(sample_data_path, data_type, record_ids, output_path)
    pass

def find_reference_records(find_reference_records_args):
    sample_data_path = find_reference_records_args['sample_data_path']
    data_type = find_reference_records_args['data_type']
    record_ids_path = find_reference_records_args['record_ids_path']
    reference_path = find_reference_records_args['reference_path']
    output_path = find_reference_records_args['output_path']
    
    record_ids = Utils.import_record_ids(record_ids_path)
    reference_record_ids(sample_data_path, data_type, record_ids, reference_path, output_path)

def perform_operation(operation):
    operation_name = operation["operation_name"]
    output_dir = operation["output_dir"]

    operation['output_path'] = Utils.create_output_path(output_dir, operation_name)
    
    if operation_name == "keyword_lookup":
        keyword_record_lookup(operation)
    elif operation_name == "update_patient_deceased_on_encounter":
        PatientUtils.update_patient_deceased_on_encounter(operation)
    elif operation_name == "remove_records":
        remove_records(operation)
    elif operation_name == "find_reference_records_on_record_id":
        find_reference_records(operation)
    else:
        print(f"Unsupported Operation: {operation_name}")

if __name__ == "__main__":
    if len(sys.argv) < 1:
        print(
            f"Usage: sample_data_updater.py <sample_data_operations_path>| Received {sys.argv}"
        )
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        sample_data_operations = json.load(f)
        
    for operation in sample_data_operations:
        perform_operation(operation)