# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
Module with a class containing constants used through out the cms cclf claims data ingestion package
"""
class CmsCclfConstants:
    """
    Constants related to CMS CCLF (Claims Data Ingestion) module.
    """

    CMS_CCLF_MAX_FILE_SIZE_IN_MB = 75
    CMS_CCLF_DROP_FOLDER_TO_DELTA_TABLES_CHECKPOINT_FOLDER = "cclf_drop_folder_to_delta_tables"
    CMS_CCLF_COLUMN_SPECIFICATION = 'col_specs'
    CMS_CCLF_FIELD_NAMES = 'field_names' 
    CMS_CCLF_FILE_PATH_NAME = 'filePath'
    CMS_CCLF_FILE_TYPE_NAME = 'file_type'
    CMS_CCLF_CLAIMS_NAME = 'claims'
    CMS_CCLF_ROW_VALUE = 'value'
    CMS_CCLF_FILES_PATH_GLOB_FILTER = 'pathGlobFilter'
    CMS_CCLF_FILE_FORMAT = 'text'
    CMS_CCLF_FILE_INGEST = 'ingest'
    CMS_CCLF_READ_DATA_FILES_DF = "read_data_files_to_df_stream"
    CMS_CCLF_FILE = "cms cclf file"
    CMS_CCLF_PROCESS = "process"
    CMS_CCLF_FILE_SPECIFIC_NAME = "file specific"
    CMS_CCLF_PROCESS_NAME = "_process_cms_cclf_batch_records"
    CMS_CCLF_BATCH_PROCESSING_STARTED = "started batch processing of cms cclf files: "
    CMS_CCLF_BATCH_PROCESSING_COMPLETED = "completed batch processing of cms cclf files"
    CMS_CCLF_SPARK_READ_STARTED = "Spark read streaming started "    
    CMS_CCLF_SPARK_READ_COMPLETED = "Spark read streaming completed "
    CMS_CCLF_FILE_CONFIG_NAME = 'cclf_file_config.json'
    CMS_CCLF_MAX_FILES_PER_TRIGGER = 1000
    FAILED_NUM_RETRIES = 3
    # Define constants for table names
    CCLF1_CLAIMS_HEADER = "ClaimsCclfHeader"
    CCLF2_CLAIMS_LINE_ITEM_DETAILS = "ClaimsCclfLineItemDetails"
    CCLF3_PROCEDURE_CODE = "ClaimsCclfProcedureCode"
    CCLF4_DIAGNOSIS_CODE = "ClaimsCclfDiagnosisCode"
    CCLF5_PHYSICIANS_FILE = "ClaimsCclfPhysiciansFile"
    CCLF6_DME_FILE = "ClaimsCclfDMEFile"
    CCLF7_PARTD_FILE = "ClaimsCclfPartDFile"
    CCLF8_BENEFICIARY_DEMOGRAPHICS_FILE = "ClaimsCclfBeneficiaryDemographicsFile"
    CCLF9_BENEFICIARY_XREF_FILE = "ClaimsCclfBeneficiaryXREFFile"
   
    Files_Config = {
        'cclf1': lambda: [CmsCclfConstants.CCLF1_CLAIMS_HEADER, '*.T1000001'],
        'cclf2': lambda: [CmsCclfConstants.CCLF2_CLAIMS_LINE_ITEM_DETAILS, '*.T1000002'],
        'cclf3': lambda: [CmsCclfConstants.CCLF3_PROCEDURE_CODE, '*.T1000003'],
        'cclf4': lambda: [CmsCclfConstants.CCLF4_DIAGNOSIS_CODE, '*.T1000004'],        
        'cclf5': lambda: [CmsCclfConstants.CCLF5_PHYSICIANS_FILE, '*.T1000005'],        
        'cclf6': lambda: [CmsCclfConstants.CCLF6_DME_FILE, '*.T1000006'],
        'cclf7': lambda: [CmsCclfConstants.CCLF7_PARTD_FILE, '*.T1000007'],
        'cclf8': lambda: [CmsCclfConstants.CCLF8_BENEFICIARY_DEMOGRAPHICS_FILE, '*.T1000008'],
        'cclf9': lambda: [CmsCclfConstants.CCLF9_BENEFICIARY_XREF_FILE, '*.T1000009'],
    }
    STATE_STARTED = 'started'
    STATE_COMPLETED = 'completed'
    HEADERTABLE_SCHEMA_CREATEDDATE = "createdDatetime"

    ID_COLUMN_NAME = "id"
    SOURCE_SYSTEM_COLUMN_NAME = "sourceSystem"
    
    #constants used for fhir ndjson conversion
    CCLF_TO_FHIR_CHECKPOINT_FOLDER = "cclf_delta_tables_to_fhir"
    AVRO_SCHEMA_FILE_EXT = ".avsc"
    CCLF_TO_FHIR_MAPPING_FILE_NAME = "cclf_fhir_mapping.json"

    FHIR_EOB_ELEMENT = "ExplanationOfBenefit"
    
    MAX_RECORDS_PER_NDJSON = 1000
    
    FHIR_LANDING_ZONE_ROOT_FOLDER = "FHIR-NDJSON"
    FHIR_NAMESPACE ="FHIR-HDS"
    
    GROUP_BY_ELEMENTS = {
        'ExplanationOfBenefit': ['currentClaimUniqueIdentifier',SOURCE_SYSTEM_COLUMN_NAME]
    }
    VIEWNAME = "ClaimDeltaView"
    CLAIMS_DELTA_VIEWNAME = "`{lakehouse_name}`.{view_name}" 
    SELECT_QUERY_CLAIMSVIEW = "SELECT * FROM {view_name}" 
    CCLF_TABLES_LIST = [
        CCLF1_CLAIMS_HEADER,
        CCLF2_CLAIMS_LINE_ITEM_DETAILS,
        CCLF3_PROCEDURE_CODE,
        CCLF4_DIAGNOSIS_CODE,
        CCLF5_PHYSICIANS_FILE,
        CCLF6_DME_FILE,
        CCLF7_PARTD_FILE,
        CCLF8_BENEFICIARY_DEMOGRAPHICS_FILE
    ]
    SELECT_CLAIMS_QUERY = f"""
    WITH filteredCh AS (
        SELECT *
        FROM {CCLF1_CLAIMS_HEADER}
        WHERE createdDatetime >= '{{minCreatedDatetime}}'
    ),
    filteredLd AS (
        SELECT *
        FROM {CCLF2_CLAIMS_LINE_ITEM_DETAILS}
        WHERE createdDatetime >= '{{minCreatedDatetime}}'
    ),
    filteredPc AS (
        SELECT *
        FROM {CCLF3_PROCEDURE_CODE}
        WHERE createdDatetime >= '{{minCreatedDatetime}}'
    ),
    filteredDc AS (
        SELECT *
        FROM {CCLF4_DIAGNOSIS_CODE}
        WHERE createdDatetime >= '{{minCreatedDatetime}}'
    ),
    filteredPf AS (
        SELECT *
        FROM {CCLF5_PHYSICIANS_FILE}
        WHERE createdDatetime >= '{{minCreatedDatetime}}'
    ),
    filteredDm AS (
        SELECT *
        FROM {CCLF6_DME_FILE}
        WHERE createdDatetime >= '{{minCreatedDatetime}}'
    ),
    filteredPd AS (
        SELECT *
        FROM {CCLF7_PARTD_FILE}
        WHERE createdDatetime >= '{{minCreatedDatetime}}'
    ),
    filteredBf AS (
        SELECT *
        FROM {CCLF8_BENEFICIARY_DEMOGRAPHICS_FILE}
        WHERE createdDatetime >= '{{minCreatedDatetime}}'
    ),
    filteredBx AS (
        SELECT *
        FROM {CCLF9_BENEFICIARY_XREF_FILE}
        WHERE createdDatetime >= '{{minCreatedDatetime}}'
    )
    SELECT 
        ch.currentClaimUniqueIdentifier, ch.sourceSystem, ld.claimLineNumber, ld.claimLineFromDate, ld.claimLineThruDate, ld.productRevenueCenterCode,
        ld.claimLineInstitutionalRevenueCenterDate, ld.hcpcsCode, ld.claimLineServiceUnitQuantity,
        ld.coveredPaidAmount, ld.firstModifierCode, ld.secondModifierCode, ld.thirdModifierCode,
        ld.fourthModifierCode, ld.fifthModifierCode, ld.claimRevenueApcHippsCode,
        ld.claimFacilityProviderOscarNumber,
        pc.procedureCode, pc.procedurePerformedDate, pc.beneficiaryEquitableBichicnNumber,
        pc.icdVersionIndicator,
        dc.claimProductTypeCode, dc.claimValueSequenceNumber, dc.diagnosisCode, dc.claimPresentOnAdmissionIndicator,
        pf.claimCarrierPaymentDenialCode, pf.claimDispositionCode, pf.claimLineAllowedChargesAmount, pf.renderingProviderTypeCode, pf.renderingProviderFipsStateCode, pf.claimLineProviderSpecialtyCode,
        pf.claimProviderTaxNumber, pf.renderingProviderNpiNumber, pf.claimLineProcessingIndicatorCode, pf.hcpcsFirstModifierCode,
        pf.hcpcsSecondModifierCode, pf.hcpcsThirdModifierCode, pf.hcpcsFourthModifierCode, pf.hcpcsFifthModifierCode, pf.claimDiagnosisFirstCode, pf.claimDiagnosisSecondCode,
        pf.claimDiagnosisThirdCode, pf.claimDiagnosisFourthCode, pf.claimDiagnosisFifthCode, pf.claimDiagnosisSixthCode, pf.claimDiagnosisSeventhCode, pf.claimDiagnosisEighthCode,
        pf.claimDiagnosisNinthCode, pf.claimDiagnosisTenthCode, pf.claimDiagnosisEleventhCode, pf.claimDiagnosisTwelfthCode, pf.hcpcsBetosCode, pf.claimRenderingProviderNpiNumber,
        pf.claimReferringProviderNpiNumber, pf.claimContractNumber,
        dm.paytoProviderNpiNumber, dm.claimPrimaryPayerCode, dm.orderingProviderNpiNumber, dm.claimProcessingIndicatorCode, dm.claimPaytoProviderNpiNumber, dm.claimOrderingProviderNpiNumber, dm.claimLineNchPaymentAmount,
        dm.claimPlaceOfServiceCode, dm.claimFederalTypeServiceCode,
        pd.providerServiceIdentifierQualifierCode, pd.claimDispensingStatusCode, pd.claimDispenseAsWrittenDawProductSelectionCode, pd.claimLineDaysSupplyQuantity, pd.claimLineBeneficiaryPaymentAmount, 
        pd.providerPrescribingIdQualifierCode, pd.claimLinePrescriptionServiceReferenceNumber, pd.claimLinePrescriptionFillNumber, pd.claimPrescribingProviderGenericIdNumber, pd.ndcCode, pd.claimServiceProviderGenericIdNumber,
        pd.claimPharmacyServiceTypeCode,
        bf.dateBeneficiaryEnrolledInHospice, bf.dateBeneficiaryEndedHospice,
        bf.beneficiaryFipsStateCode, bf.beneficiaryFipsCountyCode, bf.beneficiaryFipsZipCode,
        bf.beneficiaryDateOfBirth, bf.beneficiarySexCode, bf.beneficiaryRaceCode, bf.beneficiaryAge, bf.beneficiaryMedicareStatusCode,
        bf.beneficiaryDualStatusCode, bf.beneficiaryDeathDate, bf.beneficiaryFirstName, bf.beneficiaryMiddleName, bf.beneficiaryLastName,
        bf.beneficiaryOriginalEntitlementReasonCode, bf.beneficiaryEntitlementBuyinIndicator, bf.beneEntitlementPartABeginDate, bf.beneEntitlementPartBBeginDate,
        bf.beneficiaryDerivedMailingLineOneAddress, bf.beneficiaryDerivedMailingLineTwoAddress, bf.beneficiaryDerivedMailingLineThreeAddress,
        bf.beneficiaryDerivedMailingLineFourAddress, bf.beneficiaryDerivedMailingLineFiveAddress, bf.beneficiaryDerivedMailingLineSixAddress,
        bf.beneficiaryCity, bf.beneficiaryState, bf.beneficiaryZipCode, bf.beneficiaryZipCodeExt,
        bx.hicnMbiXrefIndicator, bx.currentBeneficiaryIdentifier, bx.previousBeneficiaryIdentifier, bx.previousIdentifierEffectiveDate, bx.previousIdentifierObsoleteDate, bx.beneficiaryRailroadBoardNumber
    FROM filteredCh ch
    LEFT JOIN filteredLd ld 
        ON ch.currentClaimUniqueIdentifier = ld.currentClaimUniqueIdentifier
    LEFT JOIN filteredPc pc 
        ON ch.currentClaimUniqueIdentifier = pc.currentClaimUniqueIdentifier
    LEFT JOIN filteredDc dc 
        ON ch.currentClaimUniqueIdentifier = dc.currentClaimUniqueIdentifier
    LEFT JOIN filteredPf pf 
        ON ch.currentClaimUniqueIdentifier = pf.currentClaimUniqueIdentifier
    LEFT JOIN filteredDm dm 
        ON ch.currentClaimUniqueIdentifier = dm.currentClaimUniqueIdentifier
    LEFT JOIN filteredPd pd 
        ON ch.currentClaimUniqueIdentifier = pd.currentClaimUniqueIdentifier
    LEFT JOIN filteredBf bf 
     ON ch.medicareBeneficiaryIdentifier = bf.medicareBeneficiaryIdentifier
    LEFT JOIN filteredBx bx 
     ON bf.medicareBeneficiaryIdentifier = bx.currentBeneficiaryIdentifier
    """