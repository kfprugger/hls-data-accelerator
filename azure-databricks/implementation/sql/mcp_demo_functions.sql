-- Bounded provider-data tools for the APIM -> Databricks MCP demonstration.
-- ${ENVIRONMENT} is substituted by scripts/10-deploy-mcp-demo.sh.
-- The function returns aggregate synthetic data only; no patient identifiers.

CREATE OR REPLACE FUNCTION hls_${ENVIRONMENT}.ops.get_imaging_modality_counts()
RETURNS TABLE (
  modality_code STRING,
  study_count BIGINT,
  patient_count BIGINT,
  governed_data_source STRING
)
LANGUAGE SQL
COMMENT 'Bounded synthetic-provider imaging counts for the Intermountain MCP demonstration; returns no patient identifiers.'
RETURN
  SELECT
    modality_code,
    COUNT(DISTINCT imaging_study_resource_id) AS study_count,
    COUNT(DISTINCT patient_id) AS patient_count,
    'hls_${ENVIRONMENT}.gold.agent_imaging_cohort' AS governed_data_source
  FROM hls_${ENVIRONMENT}.gold.agent_imaging_cohort
  WHERE modality_code IS NOT NULL
  GROUP BY modality_code
  ORDER BY modality_code;
