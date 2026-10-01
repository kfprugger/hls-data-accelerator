-- unity_catalog_bootstrap.sql
-- Run once per environment as a metastore admin, after databricks-foundation.bicep.
-- Placeholders are substituted by scripts/04-unity-catalog-bootstrap.sh.
--   ${ENVIRONMENT}          dev | test | prod
--   ${ACCESS_CONNECTOR_ID}  /subscriptions/.../accessConnectors/<name>
--   ${MANAGED_LOCATION_URL} abfss://databricks-managed@<account>.dfs.core.windows.net
--   ${FHIR_EXPORT_URL}      abfss://fhir-export@<account>.dfs.core.windows.net
--   ${DICOM_OUTPUT_URL}     abfss://dicom-output@<account>.dfs.core.windows.net
--   ${ADMIN_GROUP}          Databricks account group for platform admins
--   ${WORKLOAD_PRINCIPAL}   service principal application ID used by bundles and jobs

-- 1. The storage credential is created through the Unity Catalog API by
-- scripts/04-unity-catalog-bootstrap.sh. Databricks SQL does not implement
-- CREATE STORAGE CREDENTIAL.

-- 2. External locations are created through the Unity Catalog API by the
-- bootstrap script. The read-only source locations use skip_validation because
-- Unity Catalog's create-time validator requires write/delete access even when
-- the requested location is read-only. Azure RBAC remains read-only on source.

-- 3. The managed location was API-created and validated with container-scoped write access.
-- 4. The catalog replaces the Fabric workspace as the governance boundary.
CREATE CATALOG IF NOT EXISTS hls_${ENVIRONMENT}
  MANAGED LOCATION '${MANAGED_LOCATION_URL}/${ENVIRONMENT}/'
  COMMENT 'HLS Data Accelerator ${ENVIRONMENT} medallion estate';

CREATE SCHEMA IF NOT EXISTS hls_${ENVIRONMENT}.bronze COMMENT 'Replayable raw source data';
CREATE SCHEMA IF NOT EXISTS hls_${ENVIRONMENT}.silver COMMENT 'Normalized clinical, imaging, telemetry, payer products';
CREATE SCHEMA IF NOT EXISTS hls_${ENVIRONMENT}.gold   COMMENT 'OMOP, quality, risk, utilization products';
CREATE SCHEMA IF NOT EXISTS hls_${ENVIRONMENT}.ops    COMMENT 'Alert candidates, worklists, operational state';
CREATE SCHEMA IF NOT EXISTS hls_${ENVIRONMENT}.meta   COMMENT 'Run lineage, manifests, validation results';

CREATE VOLUME IF NOT EXISTS hls_${ENVIRONMENT}.meta.ingestion_state
  COMMENT 'Managed Auto Loader schemas and ingestion state';

-- 5. Least privilege: readers read, the workload principal owns pipeline writes.
GRANT USE CATALOG, USE SCHEMA, SELECT ON CATALOG hls_${ENVIRONMENT} TO `${ADMIN_GROUP}`;
GRANT ALL PRIVILEGES ON CATALOG hls_${ENVIRONMENT} TO `${WORKLOAD_PRINCIPAL}`;
GRANT READ FILES ON EXTERNAL LOCATION `hls_${ENVIRONMENT}_fhir_export` TO `${WORKLOAD_PRINCIPAL}`;
GRANT READ FILES ON EXTERNAL LOCATION `hls_${ENVIRONMENT}_dicom_output` TO `${WORKLOAD_PRINCIPAL}`;
GRANT CREATE EXTERNAL VOLUME, READ FILES, WRITE FILES
  ON EXTERNAL LOCATION `hls_${ENVIRONMENT}_managed` TO `${WORKLOAD_PRINCIPAL}`;

-- 6. Governed handles for the source bytes OHIF and the imaging pipeline both use.
CREATE EXTERNAL VOLUME IF NOT EXISTS hls_${ENVIRONMENT}.bronze.fhir_export
  LOCATION '${FHIR_EXPORT_URL}/'
  COMMENT 'Governed read-only handle to FHIR $export NDJSON';

CREATE EXTERNAL VOLUME IF NOT EXISTS hls_${ENVIRONMENT}.bronze.dicom_source
  LOCATION '${DICOM_OUTPUT_URL}/'
  COMMENT 'Governed read-only handle to re-tagged DICOM objects';
