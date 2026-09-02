import os
import json
import glob
from dateutil.relativedelta import relativedelta
from datetime import datetime
from utils import Utils

class PatientUtils:
    @staticmethod
    def get_invalid_patient_encounter_records(resources, output_path):
        patient_resources = resources['Patient']
        encounter_resources = resources['Encounter']
        invalid_records = []
        for encounter_id, encounter_record in encounter_resources.items():
            encounter_patient_id = Utils.parse_reference_id(encounter_record['patient_id'])
            if encounter_patient_id in patient_resources:
                patient_record = patient_resources[encounter_patient_id]
                if patient_record['deceasedDateTime'] is not None:
                    if encounter_record['end'] > patient_record['deceasedDateTime']:
                        invalid_record = {
                            'encounter_id': encounter_id,
                            'patient_id': encounter_patient_id,
                            'patient_source_file': patient_record['source_file'],
                            'encounter_source_file': encounter_record['source_file'],
                            'patient_deceasedDateTime': patient_record['deceasedDateTime'],
                            'encounter_end': encounter_record['end']
                        }
                        invalid_records.append(invalid_record)

        with open(f"{output_path}/invalid_records.json", 'w') as f:
            json.dump(invalid_records, f, indent=2)
        return invalid_records

    @staticmethod
    def patient_deceased_updates(invalid_records, output_path):
        oldest_encounter_end_per_patient = {}
        for record in invalid_records:
            patient_id = record['patient_id']
            encounter_end = datetime.fromisoformat(record['encounter_end'])
            if patient_id not in oldest_encounter_end_per_patient or encounter_end > oldest_encounter_end_per_patient[patient_id]:
                oldest_encounter_end_per_patient[patient_id] = encounter_end

        for patient_id, encounter_end in oldest_encounter_end_per_patient.items():
            new_deceased_time = oldest_encounter_end_per_patient[patient_id] + relativedelta(years=1)
            oldest_encounter_end_per_patient[patient_id] = new_deceased_time.isoformat()

        with open(f"{output_path}/patient_deceased_updates.json", 'w') as f:
            json.dump(oldest_encounter_end_per_patient, f, indent=2)

        return oldest_encounter_end_per_patient

    @staticmethod
    def update_patient_information(sample_data_file, output_path, field, patient_updates):
        print (f"Updating patient data in {sample_data_file}")
        file_name = os.path.basename(sample_data_file)
        updated_path = f"{output_path}/updated"
        os.makedirs(f"{updated_path}", exist_ok=True)
        updated_records = 0
        updated_file_path = f"{updated_path}/{file_name}"
        with open(sample_data_file, 'r') as infile, open(updated_file_path, 'w') as outfile:
            for line in infile:
                patient_record = json.loads(line)
                if field in patient_record and patient_record['id'] in patient_updates:
                    updated_records += 1
                    patient_record[field] = patient_updates[patient_record['id']]
                outfile.write(json.dumps(patient_record) + '\n')
        print(f"Updated {updated_records} records to path: {updated_file_path}")
    
    @staticmethod
    def update_patient_deceased_on_encounter(update_args):
        sample_data_path = update_args['sample_data_path']
        data_type_imports = [
            {
                'data_type': 'Patient',
                'fields': {
                    'id': 'id',
                    'deceasedDateTime': 'deceasedDateTime'
                }
            },
            {
                'data_type': 'Encounter',
                'fields': {
                    'id': 'id',
                    'patient_id': 'subject.reference',
                    'end': 'period.end'
                }
            }
        ]
        output_path = update_args['output_path']

        data_records = Utils.import_data_types(data_type_imports, sample_data_path)
        invalid_records = PatientUtils.get_invalid_patient_encounter_records(data_records, output_path)
        patient_updates = PatientUtils.patient_deceased_updates(invalid_records, output_path)

        patient_data_files = glob.glob(f"{sample_data_path}/Patient*.ndjson")
        for patient_file in patient_data_files:
            PatientUtils.update_patient_information(patient_file, output_path, 'deceasedDateTime', patient_updates)