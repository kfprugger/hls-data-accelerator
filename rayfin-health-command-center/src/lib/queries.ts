//-----------------------------------------------------------------------
// BrakeKat Health Command Center — DAX query catalog.
//
// Every query below is served by a Direct Lake semantic model sitting on a
// Gold lakehouse in the med-0906 workspace:
//
//   popHealthGold -> "Population Health & Quality Semantic Model"
//                    (Direct Lake over healthcare1_reporting_gold)
//   imagingGold   -> "ImagingReport"
//                    (Direct Lake over the Gold imaging projections)
//
// Connection aliases are declared in fabric.yaml and compiled into
// src/fabric.generated.ts by `fabric-app-data generate`.
//-----------------------------------------------------------------------

export type Connection = "popHealthGold" | "imagingGold";

export interface Q {
    connection: Connection;
    query: string;
}

const q = (connection: Connection, query: string): Q => ({ connection, query });

/* ---------------------------------------------------------------- payer -- */

export const PAYER_KPIS = q(
    "popHealthGold",
    `EVALUATE ROW(
        "totalPaid", [Total Paid],
        "totalBilled", [Total Billed],
        "leakage", [Revenue Leakage],
        "collectionRate", [Collection Rate],
        "denialRate", [Denial Rate],
        "totalClaims", [Total Claims],
        "pmpm", [PMPM],
        "highCostMembers", [High Cost Member Count],
        "revenueAtRisk", [Total Revenue at Risk]
    )`,
);

/** Segment rollup built from the per-segment measures: grouping fact_claim by
 *  dim_payer[payer_category] returns the grand total for every row because the
 *  claim-to-payer relationship is not usable in this model. */
export const PAYER_SEGMENTS = q(
    "popHealthGold",
    `EVALUATE UNION(
        ROW("segment", "Medicare",   "paid", [Total Paid (Medicare)],   "quality", [Quality Rate (Medicare)],   "collection", [Collection Rate (Medicare)],   "raf", [Average RAF (Medicare)],   "pmpm", [PMPM (Medicare)]),
        ROW("segment", "Medicaid",   "paid", [Total Paid (Medicaid)],   "quality", [Quality Rate (Medicaid)],   "collection", [Collection Rate (Medicaid)],   "raf", [Average RAF (Medicaid)],   "pmpm", [PMPM (Medicaid)]),
        ROW("segment", "Commercial", "paid", [Total Paid (Commercial)], "quality", [Quality Rate (Commercial)], "collection", [Collection Rate (Commercial)], "raf", [Average RAF (Commercial)], "pmpm", [PMPM (Commercial)])
    )`,
);

export const HIGH_COST_MEMBERS = q(
    "popHealthGold",
    `EVALUATE TOPN(8,
        SELECTCOLUMNS(agg_high_cost_claimants,
            "member", agg_high_cost_claimants[patient_id],
            "payer", agg_high_cost_claimants[payer_category],
            "paid", agg_high_cost_claimants[total_paid],
            "claims", agg_high_cost_claimants[claim_count],
            "stopLoss", agg_high_cost_claimants[is_stop_loss]
        ),
        [paid], DESC)`,
);

/* ------------------------------------------------------------- provider -- */

export const PROVIDER_KPIS = q(
    "popHealthGold",
    `EVALUATE ROW(
        "openGaps", [Open Care Gaps],
        "qualityRate", [Quality Rate],
        "stars", [Overall Star Rating],
        "avgRaf", [Average RAF Score],
        "avgReadmit", [Avg Readmission Risk],
        "alos", [ALOS],
        "starOpp", [Star Improvement Opportunity],
        "patientsMeasured", [Patients Measured]
    )`,
);

export const CARE_GAPS = q(
    "popHealthGold",
    `EVALUATE TOPN(8,
        SUMMARIZECOLUMNS(care_gaps[gap_type], "gaps", [Care Gap Count]),
        [gaps], DESC)`,
);

export const READMISSION_TIERS = q(
    "popHealthGold",
    `EVALUATE SUMMARIZECOLUMNS(
        readmission_risk_scores[risk_tier],
        "encounters", [Readmission Encounter Count],
        "avgRisk", [Avg Readmission Risk]
    )`,
);

export const STAR_MEASURES = q(
    "popHealthGold",
    `EVALUATE TOPN(6,
        SUMMARIZECOLUMNS(star_rating_detail[measure_name], "rating", [Measure Star Rating]),
        [rating], ASC)`,
);

/* -------------------------------------------------------------- medtech -- */

export const MEDTECH_KPIS = q(
    "imagingGold",
    `EVALUATE ROW(
        "studies", [Total Studies],
        "patients", [Total Patients],
        "files", [Total DICOM Files],
        "perPatient", [Studies per Patient],
        "perStudy", [Files per Study],
        "avgAge", [Avg Age]
    )`,
);

export const MODALITY_MIX = q(
    "imagingGold",
    `EVALUATE TOPN(8,
        SUMMARIZECOLUMNS(
            ImagingStudy[ModalityName],
            ImagingStudy[Modality],
            "studies", [Total Studies],
            "files", [Total DICOM Files],
            "patients", [Total Patients]
        ),
        [studies], DESC)`,
);

export const HEAVIEST_STUDIES = q(
    "imagingGold",
    `EVALUATE TOPN(8,
        SUMMARIZECOLUMNS(
            Patient[FullName],
            Patient[AgeRange],
            "studies", [Patient Studies],
            "files", [Patient DICOM Files]
        ),
        [files], DESC)`,
);
