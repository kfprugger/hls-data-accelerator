# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
module defining constants for flattening work
"""
import re
from pyspark.sql.types import ArrayType, BooleanType, StructType, StructField, StringType, TimestampType
from microsoft.fabric.hls.hds.flatten.multi_thread_strategy import MultithreadStrategy

# pylint: disable=R0903 # too-few-public-methods


class FlattenConstants:
    """Constants used by flatten library"""
    # Dataframe AVRO schema format
    SCHEMA_TYPE_AVRO: str = "avro"
    # internal library configuration used
    CONFIG_TYPE_LIBRARY: str = "LIB"
    # main configuration file columns
    MAIN_CONFIG_ATTR_COLUMN_SCHEMA: str = "flattenSchemaFile"
    MAIN_CONFIG_ATTR_NAME: str = "name"
    MAIN_CONFIG_ATTR_APPEND: str = "retainSourceColumns"
    MAIN_CONFIG_ATTR_APPEND_DEFAULT: bool = True
    MAIN_CONFIG_ATTR_STRINGIFY: str = "stringifyComplexTypes"
    MAIN_CONFIG_ATTR_STRINGIFY_DEFAULT: bool = True
    MAIN_CONFIG_ATTR_AUTO_FLATTEN: str = "autoFlattenStruct"
    MAIN_CONFIG_ATTR_AUTO_FLATTEN_DEFAULT: bool = False

    # main configuration file sections
    MAIN_CONFIG_SECT_CHILDREN: str = "children"
    MAIN_CONFIG_SECT_RESOURCES: str = "resources"
    MAIN_CONFIG_SECT_SCHEMA: str = "schema"
    # schema section attributes
    SCHEMA_CONFIG_ATTR_PATH: str = "path"
    SCHEMA_CONFIG_ATTR_TYPE: str = "type"
    # column config file sections
    COLUMN_CONFIG_SECT_COLUMNS: str = "columns"
    COLUMN_CONFIG_SECT_EXPLODE: str = "explode"
    COLUMN_CONFIG_SECT_NORM: str = "normalization"
    # column config file column attributes
    COLUMN_CONFIG_ATTR_NAME: str = "name"
    COLUMN_CONFIG_ATTR_STYLE: str = "style"
    COLUMN_CONFIG_ATTR_EXPRESSION: str = "expression"
    COLUMN_CONFIG_ATTR_FLATTEN: str = "flatten"
    # column config file flatten types
    COLUMN_FLATTEN_TYPE_STRUCT: str = "struct"
    # column config column expression types
    COLUMN_FUNCTION_COLUMN: str = "col"
    COLUMN_FUNCTION_EXPRESSION: str = "expr"
    # columns explode section attributes
    EXPLODE_SECT_ATTR_NAME: str = "name"
    EXPLODE_SECT_ATTR_INDEX: str = "indexColumn"
    EXPLODE_SECT_ATTR_EXPRESSION: str = "expression"
    # index column default name
    INDEX_COLUMN_DEFAULT: str = "index"
    # Date patterns
    RE_DATE_YEAR: str = r"^\d{4}$"
    RE_DATE_YEAR_MONTH: str = r"^\d{4}-\d{2}$"
    RE_DATE_YEAR_MONTH_DAY: str = r"^\d{4}-\d{2}-\d{2}$"
    RE_DATE_TIME_PART: str = r"(.)*\d{2}:\d{2}:\d{2}(.)*"
    RE_DATE_FULL_PARTS: str = r"(\d{4}-\d{2}-\d{2})(T|\s)?(\d{2}:\d{2}:\d{2})(\.\d+)?(.*)"
    
    # Valid FHIR types
    VALID_FHIR_TYPES: str =\
        "(Account|ActivityDefinition|AdministrableProductDefinition|" + \
        "AdverseEvent|AllergyIntolerance|Appointment|AppointmentResponse|" +\
        "AuditEvent|Basic|Binary|BiologicallyDerivedProduct|BodyStructure|" +\
        "Bundle|CapabilityStatement|CarePlan|CareTeam|CatalogEntry|ChargeItem|" +\
        "ChargeItemDefinition|Citation|Claim|ClaimResponse|ClinicalImpression|" +\
        "ClinicalUseDefinition|CodeSystem|Communication|CommunicationRequest|" +\
        "CompartmentDefinition|Composition|ConceptMap|Condition|Consent|" +\
        "Contract|Coverage|CoverageEligibilityRequest|CoverageEligibilityResponse|" +\
        "DetectedIssue|Device|DeviceDefinition|DeviceMetric|DeviceRequest|" +\
        "DeviceUseStatement|DiagnosticReport|DocumentManifest|DocumentReference|" +\
        "Encounter|Endpoint|EnrollmentRequest|EnrollmentResponse|EpisodeOfCare|" +\
        "EventDefinition|Evidence|EvidenceReport|EvidenceVariable|ExampleScenario|" +\
        "ExplanationOfBenefit|FamilyMemberHistory|Flag|Goal|GraphDefinition|Group|" +\
        "GuidanceResponse|HealthcareService|ImagingStudy|Immunization|" +\
        "ImmunizationEvaluation|ImmunizationRecommendation|ImplementationGuide|" +\
        "Ingredient|InsurancePlan|Invoice|Library|Linkage|List|Location|" +\
        "ManufacturedItemDefinition|Measure|MeasureReport|Media|Medication|" +\
        "MedicationAdministration|MedicationDispense|MedicationKnowledge|" +\
        "MedicationRequest|MedicationStatement|MedicinalProductDefinition|" +\
        "MessageDefinition|MessageHeader|MolecularSequence|NamingSystem|" +\
        "NutritionOrder|NutritionProduct|Observation|ObservationDefinition|" +\
        "OperationDefinition|OperationOutcome|Organization|" +\
        "OrganizationAffiliation|PackagedProductDefinition|Patient|" +\
        "PaymentNotice|PaymentReconciliation|Person|PlanDefinition|Practitioner|" +\
        "PractitionerRole|Procedure|Provenance|Questionnaire|QuestionnaireResponse|" +\
        "RegulatedAuthorization|RelatedPerson|RequestGroup|ResearchDefinition|" +\
        "ResearchElementDefinition|ResearchStudy|ResearchSubject|RiskAssessment|" +\
        "Schedule|SearchParameter|ServiceRequest|Slot|Specimen|SpecimenDefinition|" +\
        "StructureDefinition|StructureMap|Subscription|SubscriptionStatus|" +\
        "SubscriptionTopic|Substance|SubstanceDefinition|SupplyDelivery|" +\
        "SupplyRequest|Task|TerminologyCapabilities|TestReport|TestScript|" +\
        "ValueSet|VerificationResult|VisionPrescription)"
    
    REFERENCE_NORMALIZATION_PATTERN_LITERAL = re.compile(r'((http|https):\/\/([A-Za-z0-9\-\\\.\:\%\$]*\/)+)?' + VALID_FHIR_TYPES + r'\/([A-Za-z0-9\-\.]{1,64})(\/_history\/[A-Za-z0-9\-\.]{1,64})?')
    REFERENCE_NORMALIZATION_PATTERN_LOGICAL = re.compile(r'(?:((http|https):\/\/[A-Za-z0-9\-\\\.\:\%\$]*\/))?(' + VALID_FHIR_TYPES + r')\?identifier=(?:(.*)\|)?(.*)')
    # FHIR Type pattern
    RE_VALID_FHIR_TYPES: str = f"^{VALID_FHIR_TYPES}$"
    
    # id and type constants for normalization of references
    NORMALIZE_ID: str = "id"
    NORMALIZE_TYPE: str = "type"
    
    # normalize config
    NORM_CONF_NAME: str = "name"
    NORM_CONF_EXPRESSION: str = "expression"
    NORM_CONF_TYPE: str = "type"
    NORM_CONF_REFERENCE: str = "reference"
    NORM_CONF_NESTED_REFERENCE: str = "nestedReference"
    NORM_CONF_NESTED_ARRAY: str = "nestedArray"
    NORM_CONF_TYPE_DATE: str = "date"
    NORM_CONF_TYPE_RESOURCE: str = "resource"
    NORM_CONF_REFERENCE_ID: str = "resourceId"
    NORM_CONF_REFERENCE_TYPE: str = "resourceType"
    NORM_CONF_PRESERVE_OLD_VALUE: str = "preservePreviousValue"
    NORM_CONF_SOURCE_SYSTEM: str = "sourceSystem"
    
    NORM_CONF_ATTR_NESTED_ARRAY_DEFAULT: bool = False
    
    PERIOD_SCHEMA = StructType([
        StructField("extension", StringType(), True),
        StructField("id", StringType(), True),
        StructField("start", TimestampType(), True),  # Using TimestampType for start
        StructField("end", TimestampType(), True)     # Using TimestampType for end
    ])

    # Define the Identifier Reference schema
    IDENTIFIER_REFERENCE_SCHEMA = StructType([
        StructField("extension", StringType(), True),
        StructField("id", StringType(), True),
        StructField("reference", StringType(), True),
        StructField("type", StringType(), True),
        StructField("identifier", StructType([
            StructField("extension", StringType(), True),
            StructField("use", StringType(), True),
            StructField("type", StringType(), True),
            StructField("value", StringType(), True),
            StructField("system", StringType(), True),
            StructField("period", StringType(), True),
            StructField("assigner", StringType(), True)
        ]), True),
        StructField("display", StringType(), True)
    ])
    
    # Normlization UDF schemas
    CODEABLE_CONCEPT_SCHEMA = StructType([
        StructField("extension", StringType(), True),
        StructField("id", StringType(), True),
        StructField("coding", ArrayType(StructType([
            StructField("extension", StringType(), True),
            StructField("id", StringType(), True),
            StructField("system", StringType(), True),
            StructField("version", StringType(), True),
            StructField("code", StringType(), True),
            StructField("display", StringType(), True),
            StructField("userSelected", BooleanType(), True)
        ])), True),
        StructField("text", StringType(), True)
    ])
    
    # Define the identifier schema separately
    NORM_IDENTIFIER_SCHEMA = StructType([
        StructField("extension", StringType(), True),
        StructField("use", StringType(), True),
        StructField("value", StringType(), True),
        StructField("system", StringType(), True),
        StructField("type", CODEABLE_CONCEPT_SCHEMA, True),  # This would be a complex type in a complete schema
        StructField("period", PERIOD_SCHEMA, True),  # This would be a complex type in a complete schema
        StructField("assigner", IDENTIFIER_REFERENCE_SCHEMA, True)
    ])

    # Use the identifier schema within the main schema
    NORM_REF_STRUCT_UDF_SCHEMA = StructType([
        StructField("reference", StringType(), True),
        StructField("type", StringType(), True),
        StructField("identifier", NORM_IDENTIFIER_SCHEMA, True),
        StructField("display", StringType(), True),
        StructField("extension", StringType(), True),
        StructField("id", StringType(), True),
        StructField("idOrig", StringType(), True),
        StructField("msftSourceReference", StringType(), True),
    ])
    
    # Define the schema for the output of the ref array UDF normalization
    NORM_REF_ARRAY_UDF_SCHEMA = ArrayType(NORM_REF_STRUCT_UDF_SCHEMA)
    
    NORM_IDENTIFIER_ARRAY_SCHEMA = ArrayType(NORM_IDENTIFIER_SCHEMA)
    
    # Postfix for preserved 'previous' column contained original values
    NORM_COPY_POSTFIX: str = "Orig"
    # public UDF function names
    NORM_UDF_NORM_DATE: str = "norm_date"
    NORM_UDF_NORM_ID_TYPE: str = "norm_id_type"
    NORM_UDF_NORM_REFERENCE: str = "norm_ref"
    NORM_UDF_FLATTEN_GET_REF_TYPE: str = "get_ref_type"
    NORM_UDF_FLATTEN_GET_REF_ID: str = "get_ref_id"
    NORM_UDF_NORM_REFERENCE_STRUCT: str = "norm_ref_struct"
    NORM_UDF_NORM_REFERENCE_ARRAY: str = "norm_ref_array"
    NORM_UDF_NORM_RESOURCE_ID: str = "norm_resource_id"
    
    # flatten manager constants
    DEFAULT_NUMBER_OF_WORKERS: int = 8
    DEFAULT_MULTITHREAD_STRATEGY: int = MultithreadStrategy.ONE_THREAD_PER_RESOURCE

    # orchestrator constants
    DEFAULT_UNIQUE_RESOURCE_COLUMNS = ["id"]
    CHILD_UNIQUE_COLUMN_ADDITION = ["index"]

    # input format of resources collection
    PATH = "path"
    TYPE = "resourceType"
    
    #flatten config generator constants
    REFERENCE_NORMALIZATION = "ReferenceNormalization"
    BASE_REFERENCE_NORMALIZATION_COMPONENTS = ['name', 'type']
    BASE_REFERENCE_NORMALIZATION_DEFAULTS = ['', 'reference']
    REFERENCE_NORM_NESTED_REF = "nestedReference"
    REFERENCE_NORM_NESTED_ARRAY = "nestedArray"
    
    DATE_NORMALIZATION = "DateNormalization"
    DATE_NORMALIZATION_COMPONENTS = ['name', 'type']
    DATE_NORMALIZATION_DEFAULTS = ['', 'date']
    
    ID_NORMALIZATION = "IdNormalization"
    ID_NORMALIZATION_COMPONENTS = ['name', 'type', 'resourceId', 'resourceType', 'sourceSystem']
    ID_NORMALIZATION_DEFAULTS = ['id', 'resource', 'id', '', 'msftSourceSystem']
    
    FLATTENING_CONFIG = "FlatteningConfig"
    FLATTENING_CONFIG_COMPONENTS = ['name', 'retainSourceColumns', 'autoFlattenStruct', 'stringifyComplexTypes', 'columns', 'normalization']
    FLATTENING_CONFIG_DEFAULTS = ['', True, False, True, [], []]
    
    AVRO_SCHEMA_NAME = 'name'
    AVRO_SCHEMA_TYPE = 'type'
    AVRO_SCHEMA_LOGICAL_TYPE = 'logicalType'
    AVRO_SCHEMA_NULL_STRING = 'null'
    AVRO_SCHEMA_FIELDS = 'fields'
    AVRO_SCHEMA_RECORD = 'record'
    AVRO_SCHEMA_ARRAY = 'array'
    AVRO_SCHEMA_ITEMS = 'items'
    AVRO_SCHEMA_DATE_TYPES = ['int', 'long']
    AVRO_SCHEMA_DATE_LOGICAL_TYPES = ['date', 'timestamp-millis', 'timestamp-micros']
    
    FHIR_TYPE_PERIOD = 'Period'
    FHIR_TYPE_PERIOD_START = 'start'
    FHIR_TYPE_PERIOD_END = 'end'
    
    FHIR_TYPE_ATTACHMENT = 'Attachment'
    FHIR_TYPE_ATTACHMENT_CREATION = 'creation'
    
    FHIR_TYPE_SIGNATURE = 'Signature'
    FHIR_TYPE_SIGNATURE_WHEN = 'when'
    FHIR_TYPE_SIGNATURE_WHO = 'who'
    FHIR_TYPE_SIGNATURE_ON_BEHALF_OF = 'onBehalfOf'
    
    FHIR_TYPE_ANNOTATION = 'Annotation'
    FHIR_TYPE_ANNOTATION_TYPE = 'time'
    FHIR_TYPE_ANNOTATION_AUTHOR_REF = 'authorReference'
    
    FHIR_TYPE_IDENTIFIER = 'Identifier'
    FHIR_TYPE_IDENTIFIER_ASSIGNER = 'assigner'
    
    FHIR_TYPE_REFERENCE = 'Reference'
    
    FHIR_TYPE_CODEABLE_REFERENCE = 'CodeableReference'
    FHIR_TYPE_COD_REF_REFERENCE = 'reference'

    NORMALIZATION_MAX_NESTING_LEVEL = 2
    
    DEFAULT_EXTEND_WITH_DEFAULT_RULES = True
    EXTEND_WITH_DEFAULT_RULES_PROPERTY = 'extendWithDefaultRules'
    
    IS_PARENT_ARRAY = 'isParentArray'
    FIELD_NAME_PREFIX = 'fieldNamePrefix'
    
    META_LAST_UPDATED_FIELD_NAME = 'meta_lastUpdated'
    META_LAST_UPDATED_FIELD_EXP = 'meta.lastUpdated' 
    
    COLUMN_CONFIG = 'ColumnConfig'
    COLUMN_CONFIG_COMPONENTS = [COLUMN_CONFIG_ATTR_NAME, COLUMN_CONFIG_ATTR_STYLE, COLUMN_CONFIG_ATTR_EXPRESSION]
    COLUMN_CONFIG_DEFAULTS = ['', 'col', '']
    
    FHIR_STRING_TYPE = 'string'
    FHIR_DECIMAL_TYPE = 'decimal'
    FHIR_BOOL_TYPE = 'boolean'
    FHIR_INT_TYPE = 'int'
    
    # Normalization
    FHIR_IDENTIFIER_TYPE_CODING_SYSTEM_URL = "http://terminology.hl7.org/CodeSystem/v2-0203"
    FHIR_IDENTIFIER_TYPE_CODING_CODE = "fhirId"
    FHIR_IDENTIFIER_TYPE_CODING_DISPLAY = "FHIR Id"
    FHIR_IDENTIFIER_TYPE_TEXT = "FHIR Id"
    
    