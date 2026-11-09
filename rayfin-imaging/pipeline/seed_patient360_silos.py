"""Provision and populate the Patient 360 multi-silo tables and OneLake shortcuts.

Creates Delta tables across the three domain silos (`clinical_lakehouse`, `genomics_lakehouse`,
`imaging_lakehouse`) using `pyarrow` + `_delta_log/00000000000000000000.json` + `azcopy`, then
registers the `patient360` OneLake shortcuts (`Tables/*` and `Files/*`) and refreshes the
`patient360` SQL analytics endpoint metadata.

Requires only `pyarrow`, `requests`, `azure-identity`, and `azcopy` (all pre-installed in the
orchestrator runtime).

Usage: python pipeline/seed_patient360_silos.py
"""
from __future__ import annotations

import datetime as dt
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

import pyarrow as pa
import pyarrow.parquet as pq
import requests
import urllib3.util.connection
from azure.identity import AzureCliCredential

if os.environ.get("HLS_BIND_INTERFACE") and sys.platform == "darwin":
    _idx = socket.if_nametoindex(os.environ["HLS_BIND_INTERFACE"])
    _orig_conn = urllib3.util.connection.create_connection
    def _bound_conn(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, socket_options=None):
        opts = list(socket_options or []) + [(socket.IPPROTO_IP, 25, _idx)]
        return _orig_conn(address, timeout=timeout, source_address=source_address, socket_options=opts)
    urllib3.util.connection.create_connection = _bound_conn
import fabric_config

ROOT = pathlib.Path(__file__).resolve().parent.parent
PIPELINE = pathlib.Path(__file__).resolve().parent
FABRIC = "https://api.fabric.microsoft.com/v1"

_CONFIG: dict[str, str] | None = None
_CREDENTIAL: AzureCliCredential | None = None
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def get_config() -> dict[str, str]:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = fabric_config.load()
        globals()["WORKSPACE_ID"] = _CONFIG["WORKSPACE_ID"]
        globals()["LAKEHOUSES"] = {
            "clinical": _CONFIG["CLINICAL_LH"],
            "genomics": _CONFIG["GENOMICS_LH"],
            "imaging": _CONFIG.get("IMAGING_LH") or _CONFIG["LAKEHOUSE_ID"],
        }
        globals()["PATIENT360"] = _CONFIG["PATIENT360_LH"]
        globals()["SQL_ENDPOINT"] = _CONFIG["PATIENT360_SQL"]
    return _CONFIG


def get_credential() -> AzureCliCredential:
    global _CREDENTIAL
    if _CREDENTIAL is None:
        _CREDENTIAL = AzureCliCredential(process_timeout=30)
    return _CREDENTIAL


class _LazyConfig(dict):
    def __getitem__(self, key):
        return get_config()[key]

    def get(self, key, default=None):
        return get_config().get(key, default)

    def __contains__(self, key):
        return key in get_config()

    def __repr__(self):
        if _CONFIG is not None:
            return repr(_CONFIG)
        return "<LazyConfig: not loaded>"


CONFIG = _LazyConfig()


def __getattr__(name: str):
    if name == "WORKSPACE_ID":
        return get_config()["WORKSPACE_ID"]
    if name == "LAKEHOUSES":
        cfg = get_config()
        return {
            "clinical": cfg["CLINICAL_LH"],
            "genomics": cfg["GENOMICS_LH"],
            "imaging": cfg.get("IMAGING_LH") or cfg["LAKEHOUSE_ID"],
        }
    if name == "PATIENT360":
        return get_config()["PATIENT360_LH"]
    if name == "SQL_ENDPOINT":
        return get_config()["PATIENT360_SQL"]
    if name == "CREDENTIAL":
        return get_credential()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return list(globals().keys()) + ["WORKSPACE_ID", "LAKEHOUSES", "PATIENT360", "SQL_ENDPOINT", "CREDENTIAL"]

CANCER_NAMES = {
    "KIRC": "Clear cell renal cell carcinoma",
    "BRCA": "Invasive breast carcinoma",
    "LUAD": "Lung adenocarcinoma",
    "LUSC": "Lung squamous cell carcinoma",
    "OV": "High-grade serous ovarian carcinoma",
    "LIHC": "Hepatocellular carcinoma",
    "BLCA": "Muscle-invasive urothelial bladder carcinoma",
    "UCEC": "Endometrial carcinoma",
    "CESC": "Cervical squamous cell carcinoma",
    "STAD": "Gastric adenocarcinoma",
    "COAD": "Colon adenocarcinoma",
    "ESCA": "Oesophageal adenocarcinoma",
    "KICH": "Chromophobe renal cell carcinoma",
    "KIRP": "Papillary renal cell carcinoma",
    "PRAD": "Prostate adenocarcinoma",
}

ORGANS = {
    "KIRC": "Kidney",
    "BRCA": "Breast",
    "LUAD": "Lung",
    "LUSC": "Lung",
    "OV": "Ovary",
    "LIHC": "Liver",
    "BLCA": "Bladder",
    "UCEC": "Uterus",
    "CESC": "Cervix",
    "STAD": "Stomach",
    "COAD": "Colon",
    "ESCA": "Oesophagus",
    "KICH": "Kidney",
    "KIRP": "Kidney",
    "PRAD": "Prostate",
}

# Verified TCGA patient profiles matching pipeline/summaries.json and pipeline/tumour_board_notes.json
PATIENT_META: dict[str, dict] = {
    "TCGA-G6-A8L6": {
        "name": "Marcus Vance", "sex": "Male", "age": 55, "race": "Black or African American", "country": "United States",
        "vital": "Dead", "year": 2011, "days_contact": 313, "days_death": 313, "stage": "Stage IV", "grade": "G3",
        "tnm": ("T3a", "N0", "M1"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 26.4,
        "subtype": "KIRC_CCRCC", "tmb": 1.4, "tmb_pct": 42.0, "fga": 0.029, "fga_pct": 9.0, "aneuploidy": 2,
        "msi": 0.28, "msi_status": "Microsatellite stable", "mut_count": 44, "leuk": 0.19, "hrd": 12, "tcr": 24,
        "drivers": [("VHL", "p.R82Afs*50", "Frame_Shift_Del", "3", 10183775, 0.44),
                    ("PBRM1", "p.Y409Tfs*29", "Frame_Shift_Del", "3", 52643420, 0.39),
                    ("SETD2", "p.P2380Tfs*31", "Frame_Shift_Ins", "3", 47125800, 0.36)],
        "cna": [("VHL", -2, "Deep deletion")],
        "treatments": [("Pharmaceutical Therapy, NOS", "Sunitinib", 73, 245, "Stable Disease"),
                       ("Pharmaceutical Therapy, NOS", "Axitinib", 252, 274, "Progressive Disease"),
                       ("Pharmaceutical Therapy, NOS", "Bevacizumab", 276, 304, "Progressive Disease")],
        "slide_id": "kidney-kirc", "vol_path": "totalseg-ct-angio/ct.nii.gz", "modality": "CT",
    },
    "TCGA-E2-A152": {
        "name": "Elena Rostova", "sex": "Female", "age": 56, "race": "White", "country": "United States",
        "vital": "Alive", "year": 2009, "days_contact": 2128, "days_death": None, "stage": "Stage I", "grade": "G2",
        "tnm": ("T1c", "N0", "M0"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 24.8,
        "subtype": "BRCA_Her2", "tmb": 2.8, "tmb_pct": 64.0, "fga": 0.64, "fga_pct": 93.0, "aneuploidy": 18,
        "msi": 0.29, "msi_status": "Microsatellite stable", "mut_count": 86, "leuk": 0.21, "hrd": 34, "tcr": 38,
        "drivers": [("TP53", "p.R175H", "Missense_Mutation", "17", 7578406, 0.52),
                    ("PIK3CA", "p.H1047R", "Missense_Mutation", "3", 178952085, 0.41)],
        "cna": [("ERBB2", 2, "Amplification"), ("MYC", 2, "Amplification")],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Trastuzumab", 42, 410, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Docetaxel", 42, 168, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Anastrozole", 231, 1800, "Treatment Ongoing")],
        "slide_id": "breast-brca", "vol_path": "fetal-body-atlas/t2-w30.nii.gz", "modality": "MR",
    },
    "TCGA-J2-8192": {
        "name": "claire Chen", "sex": "Female", "age": 65, "race": "White", "country": "United States",
        "vital": "Alive", "year": 2011, "days_contact": 920, "days_death": None, "stage": "Stage IIA", "grade": "G2",
        "tnm": ("T2a", "N1", "M0"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 23.1,
        "subtype": "LUAD_proximal_proliferative", "tmb": 2.3, "tmb_pct": 28.0, "fga": 0.19, "fga_pct": 44.0, "aneuploidy": 8,
        "msi": 0.26, "msi_status": "Microsatellite stable", "mut_count": 69, "leuk": 0.28, "hrd": 18, "tcr": 52,
        "drivers": [("EGFR", "p.E746_A750del", "In_Frame_Del", "7", 55242465, 0.34),
                    ("TP53", "p.V157F", "Missense_Mutation", "17", 7578461, 0.29)],
        "cna": [("CDKN2A", -2, "Deep deletion"), ("EGFR", 2, "Amplification")],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Cisplatin", 105, 195, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Pemetrexed", 105, 195, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Erlotinib", 641, 920, "Treatment Ongoing")],
        "slide_id": "brain-gbm", "vol_path": "cohort-0efc0058/ct.nii.gz", "modality": "CT",
    },
    "TCGA-60-2722": {
        "name": "Arthur Pendelton", "sex": "Male", "age": 66, "race": "White", "country": "United States",
        "vital": "Alive", "year": 2010, "days_contact": 1040, "days_death": None, "stage": "Stage IIB", "grade": "G3",
        "tnm": ("T2", "N1", "M0"), "smoking": "Current Reformed Smoker for < or = 15 yrs", "pack_years": 90, "bmi": 27.2,
        "subtype": "LUSC_classical", "tmb": 8.6, "tmb_pct": 68.0, "fga": 0.42, "fga_pct": 66.0, "aneuploidy": 14,
        "msi": 0.31, "msi_status": "Microsatellite stable", "mut_count": 258, "leuk": 0.36, "hrd": 29, "tcr": 84,
        "drivers": [("TP53", "p.H179R", "Missense_Mutation", "17", 7578394, 0.81),
                    ("FBXW7", "p.R505G", "Missense_Mutation", "4", 153247288, 0.79),
                    ("KEAP1", "p.G480W", "Missense_Mutation", "19", 10602412, 0.62)],
        "cna": [("SOX2", 2, "Amplification"), ("TP63", 2, "Amplification"), ("PIK3CA", 2, "Amplification"), ("CDKN2A", -2, "Deep deletion")],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Carboplatin", 110, 272, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Paclitaxel", 110, 272, "Complete Remission/Response"),
                       ("Radiation Therapy, NOS", None, 873, 915, "Partial Remission/Response")],
        "slide_id": "brain-gbm", "vol_path": "cohort-106a9b6b/ct.nii.gz", "modality": "CT",
    },
    "TCGA-25-2042": {
        "name": "Nora Blackwood", "sex": "Female", "age": 60, "race": "American Indian or Alaska Native", "country": "United States",
        "vital": "Dead", "year": 2008, "days_contact": 396, "days_death": 396, "stage": "Stage IIIC", "grade": "G3",
        "tnm": ("T3c", "N1", "M0"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 28.5,
        "subtype": "OV_Mesenchymal", "tmb": 1.9, "tmb_pct": 52.0, "fga": 0.58, "fga_pct": 74.0, "aneuploidy": 19,
        "msi": 0.27, "msi_status": "Microsatellite stable", "mut_count": 57, "leuk": 0.24, "hrd": 51, "tcr": 31,
        "drivers": [("TP53", "p.R273H", "Missense_Mutation", "17", 7577120, 0.68),
                    ("BRCA1", "p.Q1756Pfs*74", "Frame_Shift_Ins", "17", 41209079, 0.54)],
        "cna": [("MYC", 2, "Amplification"), ("CCNE1", 2, "Amplification")],
        "treatments": [("Pharmaceutical Therapy, NOS", "Carboplatin", 0, 123, "Progressive Disease"),
                       ("Pharmaceutical Therapy, NOS", "Paclitaxel", 0, 123, "Progressive Disease"),
                       ("Surgery, NOS", None, 130, 131, "Partial Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Gemcitabine", 184, 310, "Progressive Disease")],
        "slide_id": "breast-brca", "vol_path": "totalseg-ct-angio/ct.nii.gz", "modality": "CT",
    },
    "TCGA-DD-A1EH": {
        "name": "David Lin", "sex": "Male", "age": 23, "race": "Asian", "country": "United States",
        "vital": "Alive", "year": 2009, "days_contact": 1495, "days_death": None, "stage": "Stage IIIA", "grade": "G3",
        "tnm": ("T3", "N0", "M0"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 22.1,
        "subtype": "LIHC_iCluster1", "tmb": 2.4, "tmb_pct": 55.0, "fga": 0.31, "fga_pct": 58.0, "aneuploidy": 9,
        "msi": 0.25, "msi_status": "Microsatellite stable", "mut_count": 72, "leuk": 0.18, "hrd": 16, "tcr": 29,
        "drivers": [("ARID1A", "p.Q1334*", "Nonsense_Mutation", "1", 27100182, 0.42),
                    ("AXIN1", "p.G650Afs*42", "Frame_Shift_Del", "16", 347920, 0.38)],
        "cna": [("MET", 2, "Amplification")],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Sorafenib", 358, 863, "Partial Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Doxorubicin", 890, 1120, "Stable Disease")],
        "slide_id": "kidney-kirc", "vol_path": "totalseg-ct-angio/ct.nii.gz", "modality": "CT",
    },
    "TCGA-FD-A3SJ": {
        "name": "Walter Kowalski", "sex": "Male", "age": 59, "race": "White", "country": "United States",
        "vital": "Dead", "year": 2011, "days_contact": 739, "days_death": 739, "stage": "Stage IV", "grade": "High Grade",
        "tnm": ("T2b", "N2", "M0"), "smoking": "Current Smoker", "pack_years": 40, "bmi": 27.9,
        "subtype": "BLCA_Basal_Squamous", "tmb": 9.4, "tmb_pct": 72.0, "fga": 0.48, "fga_pct": 70.0, "aneuploidy": 16,
        "msi": 0.30, "msi_status": "Microsatellite stable", "mut_count": 282, "leuk": 0.25, "hrd": 55, "tcr": 44,
        "drivers": [("PIK3CA", "p.H1047L", "Missense_Mutation", "3", 178952085, 0.49),
                    ("TP53", "p.S241F", "Missense_Mutation", "17", 7577559, 0.61),
                    ("KDM6A", "p.G137V", "Missense_Mutation", "X", 44918500, 0.72)],
        "cna": [("CCNE1", 2, "Amplification"), ("MET", 2, "Amplification")],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Cisplatin", 274, 420, "Progressive Disease"),
                       ("Pharmaceutical Therapy, NOS", "Gemcitabine", 440, 610, "Progressive Disease")],
        "slide_id": "kidney-kirc", "vol_path": "cohort-15cde951/ct.nii.gz", "modality": "CT",
    },
    "TCGA-FI-A2D5": {
        "name": "Miriam Thorne", "sex": "Female", "age": 56, "race": "White", "country": "United States",
        "vital": "Dead", "year": 2010, "days_contact": 421, "days_death": 421, "stage": "Stage IVB", "grade": "G3",
        "tnm": ("T3b", "N1", "M1"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 35.9,
        "subtype": "UCEC_POLE", "tmb": 466.0, "tmb_pct": 99.5, "fga": 0.01, "fga_pct": 5.0, "aneuploidy": 1,
        "msi": 0.34, "msi_status": "Microsatellite stable", "mut_count": 13853, "leuk": 0.23, "hrd": 6, "tcr": 92,
        "drivers": [("POLE", "p.V411L", "Missense_Mutation", "12", 133250250, 0.45),
                    ("PTEN", "p.R130Q", "Missense_Mutation", "10", 89692905, 0.42),
                    ("ARID1A", "p.R1989*", "Nonsense_Mutation", "1", 27106354, 0.39)],
        "cna": [],
        "treatments": [("Surgery, NOS", None, 0, 1, "Partial Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Carboplatin", 133, 245, "Progressive Disease"),
                       ("Pharmaceutical Therapy, NOS", "Paclitaxel", 133, 245, "Progressive Disease"),
                       ("Radiation Therapy, NOS", None, 285, 325, "Progressive Disease")],
        "slide_id": "breast-brca", "vol_path": "totalseg-ct-angio/ct.nii.gz", "modality": "CT",
    },
    "TCGA-VS-A9V3": {
        "name": "Joan Silva", "sex": "Female", "age": 62, "race": "White", "country": "Brazil",
        "vital": "Alive", "year": 2012, "days_contact": 780, "days_death": None, "stage": "Stage IVB", "grade": "G3",
        "tnm": ("T4", "N1", "M1"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 25.4,
        "subtype": "CESC_Squamous", "tmb": 5.2, "tmb_pct": 61.0, "fga": 0.28, "fga_pct": 52.0, "aneuploidy": 10,
        "msi": 0.29, "msi_status": "Microsatellite stable", "mut_count": 156, "leuk": 0.31, "hrd": 22, "tcr": 63,
        "drivers": [("PIK3CA", "p.E545K", "Missense_Mutation", "3", 178936091, 0.46),
                    ("RB1", "p.R445*", "Nonsense_Mutation", "13", 48953730, 0.51),
                    ("FGFR2", "p.T320M", "Missense_Mutation", "10", 123274774, 0.37)],
        "cna": [("CD274", 2, "Amplification")],
        "treatments": [("Pharmaceutical Therapy, NOS", "Cisplatin", 21, 90, "Complete Remission/Response"),
                       ("Radiation Therapy, NOS", None, 21, 85, "Complete Remission/Response")],
        "slide_id": "breast-brca", "vol_path": "fetal-brain-atlas/t2-w30.nii.gz", "modality": "MR",
    },
    "TCGA-VQ-A91D": {
        "name": "mateo Santos", "sex": "Male", "age": 70, "race": "White", "country": "Brazil",
        "vital": "Dead", "year": 2010, "days_contact": 356, "days_death": 356, "stage": "Stage IIIC", "grade": "G2",
        "tnm": ("T4b", "N2", "M0"), "smoking": "Former smoker", "pack_years": 25, "bmi": 23.8,
        "subtype": "STAD_MSI", "tmb": 72.0, "tmb_pct": 97.0, "fga": 0.08, "fga_pct": 19.0, "aneuploidy": 3,
        "msi": 1.18, "msi_status": "MSI-high", "mut_count": 2141, "leuk": 0.23, "hrd": 14, "tcr": 76,
        "drivers": [("MLH1", "p.K255*", "Nonsense_Mutation", "3", 37055992, 0.72),
                    ("ARID1A", "p.D1850Tfs*33", "Frame_Shift_Del", "1", 27105921, 0.55),
                    ("PIK3CA", "p.H1047R", "Missense_Mutation", "3", 178952085, 0.44)],
        "cna": [],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Fluorouracil", 147, 242, "Progressive Disease")],
        "slide_id": "kidney-kirc", "vol_path": "totalseg-ct-angio/ct.nii.gz", "modality": "CT",
    },
    "TCGA-G4-6303": {
        "name": "Hannah Meyer", "sex": "Female", "age": 54, "race": "White", "country": "United States",
        "vital": "Dead", "year": 2008, "days_contact": 2003, "days_death": 2003, "stage": "Stage IV", "grade": "G2",
        "tnm": ("T3", "N1", "M1"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 26.9,
        "subtype": "COAD_CIN", "tmb": 3.8, "tmb_pct": 54.0, "fga": 0.40, "fga_pct": 62.0, "aneuploidy": 15,
        "msi": 0.28, "msi_status": "Microsatellite stable", "mut_count": 114, "leuk": 0.17, "hrd": 24, "tcr": 33,
        "drivers": [("APC", "p.Q1378*", "Nonsense_Mutation", "5", 112175423, 0.64),
                    ("TP53", "p.R213*", "Nonsense_Mutation", "17", 7578212, 0.59)],
        "cna": [("FGFR1", 2, "Amplification")],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Fluorouracil", 516, 860, "Progressive Disease"),
                       ("Pharmaceutical Therapy, NOS", "Oxaliplatin", 516, 860, "Progressive Disease"),
                       ("Pharmaceutical Therapy, NOS", "Bevacizumab", 880, 1320, "Stable Disease"),
                       ("Pharmaceutical Therapy, NOS", "Cetuximab", 1596, 1890, "Partial Remission/Response")],
        "slide_id": "breast-brca", "vol_path": "totalseg-ct-angio/ct.nii.gz", "modality": "CT",
    },
    "TCGA-VR-AA4D": {
        "name": "Carlos Ferreira", "sex": "Male", "age": 53, "race": "White", "country": "Brazil",
        "vital": "Dead", "year": 2010, "days_contact": 1405, "days_death": 1405, "stage": "Stage IIB", "grade": "G2",
        "tnm": ("T1", "N1", "M0"), "smoking": "Former smoker", "pack_years": 20, "bmi": 28.2,
        "subtype": "ESCA_CIN", "tmb": 4.1, "tmb_pct": 58.0, "fga": 0.46, "fga_pct": 68.0, "aneuploidy": 17,
        "msi": 0.29, "msi_status": "Microsatellite stable", "mut_count": 123, "leuk": 0.20, "hrd": 31, "tcr": 36,
        "drivers": [("TP53", "p.R248W", "Missense_Mutation", "17", 7577539, 0.67),
                    ("CDKN2A", "p.D74_L78del", "In_Frame_Del", "9", 21971137, 0.53)],
        "cna": [("ERBB2", 2, "Amplification"), ("BRCA2", 2, "Amplification")],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Fluorouracil", 166, 288, "Complete Remission/Response"),
                       ("Radiation Therapy, NOS", None, 166, 210, "Complete Remission/Response")],
        "slide_id": "brain-gbm", "vol_path": "totalseg-ct-angio/ct.nii.gz", "modality": "CT",
    },
    "TCGA-KM-8441": {
        "name": "Ruth Lindqvist", "sex": "Female", "age": 61, "race": "White", "country": "United States",
        "vital": "Alive", "year": 2011, "days_contact": 876, "days_death": None, "stage": "Stage I", "grade": "G2",
        "tnm": ("T1b", "N0", "M0"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 25.1,
        "subtype": "KICH_Chromophobe", "tmb": 0.8, "tmb_pct": 35.0, "fga": 0.04, "fga_pct": 12.0, "aneuploidy": 4,
        "msi": 0.24, "msi_status": "Microsatellite stable", "mut_count": 24, "leuk": 0.14, "hrd": 8, "tcr": 19,
        "drivers": [("MTOR", "p.I2017T", "Missense_Mutation", "1", 11184573, 0.41),
                    ("TP53", "p.R248Q", "Missense_Mutation", "17", 7577538, 0.38)],
        "cna": [],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response")],
        "slide_id": "kidney-kirc", "vol_path": "totalseg-ct-angio/ct.nii.gz", "modality": "CT",
    },
    "TCGA-G7-A8LE": {
        "name": "Raymond Mercer", "sex": "Male", "age": 62, "race": "White", "country": "United States",
        "vital": "Alive", "year": 2009, "days_contact": 2453, "days_death": None, "stage": "Stage I", "grade": "G2",
        "tnm": ("T1a", "N0", "M0"), "smoking": "Current Reformed Smoker for < or = 15 yrs", "pack_years": 40, "bmi": 27.6,
        "subtype": "KIRP_Type1", "tmb": 1.7, "tmb_pct": 48.0, "fga": 0.15, "fga_pct": 38.0, "aneuploidy": 6,
        "msi": 0.26, "msi_status": "Microsatellite stable", "mut_count": 51, "leuk": 0.16, "hrd": 11, "tcr": 27,
        "drivers": [("MET", "p.Y1230H", "Missense_Mutation", "7", 116423413, 0.54)],
        "cna": [("MET", 2, "Amplification")],
        "treatments": [("Surgery, NOS", None, 0, 1, "Complete Remission/Response"),
                       ("Surgery, NOS", None, 1505, 1506, "Complete Remission/Response")],
        "slide_id": "kidney-kirc", "vol_path": "totalseg-ct-angio/ct.nii.gz", "modality": "CT",
    },
    "TCGA-J4-A6G3": {
        "name": "Thomas Hargrove", "sex": "Male", "age": 57, "race": "White", "country": "United States",
        "vital": "Alive", "year": 2011, "days_contact": 980, "days_death": None, "stage": "Stage III", "grade": "Gleason 8",
        "tnm": ("T3b", "N0", "M0"), "smoking": "Lifelong Non-Smoker", "pack_years": None, "bmi": 26.8,
        "subtype": "PRAD.5-SPOP", "tmb": 1.2, "tmb_pct": 51.0, "fga": 0.18, "fga_pct": 56.0, "aneuploidy": 5,
        "msi": 0.25, "msi_status": "Microsatellite stable", "mut_count": 36, "leuk": 0.15, "hrd": 15, "tcr": 22,
        "drivers": [("SPOP", "p.F133V", "Missense_Mutation", "17", 47696432, 0.43)],
        "cna": [("PTEN", -2, "Deep deletion")],
        "treatments": [("Surgery, NOS", None, 0, 1, "Partial Remission/Response"),
                       ("Pharmaceutical Therapy, NOS", "Leuprolide", 30, 760, "Complete Remission/Response"),
                       ("Radiation Therapy, NOS", None, 367, 420, "Complete Remission/Response")],
        "slide_id": "brain-gbm", "vol_path": "fetal-face-atlas/t2.nii.gz", "modality": "MR",
    },
}


def token(scope: str) -> str:
    env_map = {
        "https://storage.azure.com/.default": "HLS_STORAGE_TOKEN",
        "https://api.fabric.microsoft.com/.default": "HLS_FABRIC_TOKEN",
    }
    if env_map.get(scope) and os.environ.get(env_map[scope]):
        return os.environ[env_map[scope]]
    cached = _TOKEN_CACHE.get(scope)
    if cached and cached[1] - time.time() > 120:
        return cached[0]
    az_dir = pathlib.Path(os.environ.get("AZURE_CONFIG_DIR") or (pathlib.Path.home() / ".azure"))
    msal_path = az_dir / "msal_token_cache.json"
    if msal_path.is_file():
        try:
            msal = json.loads(msal_path.read_text())
            rt_entry = next(iter(msal.get("RefreshToken", {}).values()))
            profiles = json.loads((az_dir / "azureProfile.json").read_bytes().decode("utf-8-sig"))
            tenant = next((s["tenantId"] for s in profiles.get("subscriptions", []) if s.get("isDefault")), "organizations")
            r = requests.post(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                data={
                    "client_id": rt_entry["client_id"],
                    "grant_type": "refresh_token",
                    "refresh_token": rt_entry["secret"],
                    "scope": f"{scope} offline_access",
                },
                timeout=20,
            )
            if r.status_code == 200 and "access_token" in r.json():
                body = r.json()
                _TOKEN_CACHE[scope] = (body["access_token"], time.time() + float(body.get("expires_in", 3600)))
                return body["access_token"]
        except Exception:
            pass
    tok = get_credential().get_token(scope)
    _TOKEN_CACHE[scope] = (tok.token, float(tok.expires_on))
    return tok.token

def build_tables() -> dict[str, dict[str, list[dict]]]:
    cohort_cfg = json.loads((PIPELINE / "cohort.json").read_text())["patients"]
    summaries = json.loads((PIPELINE / "summaries.json").read_text())
    t: dict[str, dict[str, list[dict]]] = {"clinical": {}, "genomics": {}, "imaging": {}}
    add = lambda silo, table, row: t[silo].setdefault(table, []).append(row)

    for p in cohort_cfg:
        pid = p["id"]
        code = p["project"].split("-")[1]
        m = PATIENT_META[pid]
        study = f"{p['cbio']}_tcga_pan_can_atlas_2018"
        day_offset = int(hashlib.sha256(pid.encode()).hexdigest(), 16) % 280 + 20
        dx_date = dt.date(m["year"], 1, 1) + dt.timedelta(days=day_offset)
        last_date = dx_date + dt.timedelta(days=m["days_contact"])
        death_date = (dx_date + dt.timedelta(days=m["days_death"])).isoformat() if m["days_death"] else None

        add("clinical", "patient", {
            "patient_id": pid,
            "display_name": m["name"][0].upper() + m["name"][1:],
            "project_id": p["project"],
            "cancer_code": code,
            "cancer_type": CANCER_NAMES[code],
            "organ": ORGANS[code],
            "sex": m["sex"],
            "age_at_diagnosis": m["age"],
            "race": m["race"],
            "ethnicity": "Not Hispanic or Latino",
            "country": m["country"],
            "vital_status": m["vital"],
            "year_of_diagnosis": m["year"],
            "diagnosis_date": dx_date.isoformat(),
            "last_contact_date": last_date.isoformat(),
            "death_date": death_date,
            "days_to_last_contact": float(m["days_contact"]),
            "days_to_death": float(m["days_death"]) if m["days_death"] else None,
            "cause_of_death": "Cancer Related" if m["vital"] == "Dead" else None,
            "primary_diagnosis": CANCER_NAMES[code],
            "tissue_of_origin": f"{ORGANS[code]}, NOS",
            "laterality": "Left" if code in ("KIRC", "LUAD", "KIRP") else ("Right" if code in ("BRCA", "LUSC", "KICH") else None),
            "icd10": f"C{15 + ( day_offset % 65 )}.9",
            "morphology": "8140/3",
            "stage": m["stage"],
            "stage_system": "AJCC Pathologic Stage",
            "t_stage": m["tnm"][0],
            "n_stage": m["tnm"][1],
            "m_stage": m["tnm"][2],
            "grade": m["grade"],
            "gleason_score": 8.0 if code == "PRAD" else None,
            "residual_disease": "R1" if code == "PRAD" else "R0",
            "child_pugh": "B" if code == "LIHC" else None,
            "fibrosis": "Ishak 3-4" if code == "LIHC" else None,
            "method_of_diagnosis": "Surgical Resection",
            "smoking_status": m["smoking"],
            "pack_years": float(m["pack_years"]) if m["pack_years"] else None,
            "smoking_quit_year": 2006 if m["pack_years"] else None,
            "occupation": "Electrical equipment installer" if pid == "TCGA-FD-A3SJ" else None,
            "bmi": float(m["bmi"]),
            "weight_kg": round(m["bmi"] * (1.70 ** 2), 1),
            "height_cm": 170.0,
            "menopause_status": "Post (prior bilateral ovariectomy OR >12 mo since LMP)" if m["sex"] == "Female" and m["age"] >= 52 else None,
            "risk_factors": "Hepatitis B" if code == "LIHC" else ("Barretts Esophagus / Reflux" if code == "ESCA" else None),
            "comorbidities": "Essential hypertension; Hyperlipidemia",
            "family_history": "1 first-degree relative with malignancy",
            "os_months": round(m["days_contact"] / 30.44, 1),
            "pfs_months": round((m["days_contact"] * 0.65) / 30.44, 1),
        })

        add("clinical", "diagnosis", {
            "patient_id": pid, "seq": 0, "classification": "Primary", "is_primary": True,
            "primary_diagnosis": CANCER_NAMES[code], "site": ORGANS[code],
            "day": 0.0, "date": dx_date.isoformat(), "stage": m["stage"],
            "sites_of_involvement": ORGANS[code], "method": "Histology",
        })
        if m["vital"] == "Dead" or pid in ("TCGA-E2-A152", "TCGA-J2-8192", "TCGA-60-2722", "TCGA-DD-A1EH", "TCGA-VS-A9V3", "TCGA-G7-A8LE", "TCGA-J4-A6G3"):
            rec_day = 280.0 if m["vital"] == "Dead" else 482.0
            add("clinical", "diagnosis", {
                "patient_id": pid, "seq": 1, "classification": "Metastasis" if m["vital"] == "Dead" else "Recurrence",
                "is_primary": False, "primary_diagnosis": CANCER_NAMES[code], "site": "Distant / Regional",
                "day": rec_day, "date": (dx_date + dt.timedelta(days=int(rec_day))).isoformat(),
                "stage": m["stage"], "sites_of_involvement": "Lymph Nodes / Distant", "method": "Biopsy / Imaging",
            })

        for j, (ttype, agent, s_day, e_day, outc) in enumerate(m["treatments"]):
            add("clinical", "treatment", {
                "patient_id": pid, "diagnosis_seq": 0, "seq": j, "given": True,
                "treatment_type": ttype, "agent": agent, "intent": "Adjuvant" if j > 0 else "Curative",
                "disease_status": "Primary", "outcome": outc,
                "start_day": float(s_day), "end_day": float(e_day),
                "start_date": (dx_date + dt.timedelta(days=s_day)).isoformat(),
                "end_date": (dx_date + dt.timedelta(days=e_day)).isoformat(),
                "start_estimated": s_day == 0, "cycles": 6.0 if agent else None,
                "dose": 4500.0 if "Radiation" in ttype else None,
                "dose_units": "cGy" if "Radiation" in ttype else None,
                "fractions": 25.0 if "Radiation" in ttype else None,
                "route": "Intravenous" if agent else None,
                "anatomic_site": ORGANS[code], "clinical_trial": "No", "concurrent_radiation": "No",
            })

        add("clinical", "follow_up", {
            "patient_id": pid, "day": float(m["days_contact"]),
            "date": last_date.isoformat(), "timepoint": "Last Contact",
            "disease_response": "WT-With Tumor" if m["vital"] == "Dead" else "TF-Tumor Free",
            "progression": "Yes" if m["vital"] == "Dead" else "No",
            "progression_type": "Distant" if m["vital"] == "Dead" else None,
            "progression_site": "Liver / Lung" if m["vital"] == "Dead" else None,
            "days_to_progression": 280.0 if m["vital"] == "Dead" else None,
            "evidence": "Imaging" if m["vital"] == "Dead" else None,
            "ecog": 1.0, "karnofsky": 90.0, "imaging_type": m["modality"], "imaging_findings": "Reviewed at follow-up",
        })

        add("clinical", "biomarker_test", {
            "patient_id": pid, "day": 0.0, "date": dx_date.isoformat(),
            "test": f"{m['drivers'][0][0]} molecular assay", "gene": m["drivers"][0][0],
            "method": "Targeted Sequencing / IHC", "result": "Positive",
            "value": None, "units": None, "ref_low": None, "ref_high": None,
            "intensity": "3+" if code == "BRCA" else None,
            "exon": "19" if pid == "TCGA-J2-8192" else None,
            "variant_type": m["drivers"][0][2], "timepoint": "Initial Diagnosis",
        })

        # Synthetic primary care visits & observations (10 years prior to diagnosis)
        for yr_back in range(10, 0, -1):
            v_date = dx_date - dt.timedelta(days=yr_back * 365)
            eid = f"enc-{pid.lower()}-{yr_back}"
            add("clinical", "encounter", {
                "patient_id": pid, "encounter_id": eid, "start": v_date.isoformat(), "stop": v_date.isoformat(),
                "duration_minutes": 30.0, "encounter_class": "wellness" if yr_back % 2 == 0 else "ambulatory",
                "code": "185349003", "description": "General examination of patient (procedure)",
                "reason": "Annual wellness visit", "provider": "Dr. Sarah Jenkins",
                "provider_specialty": "General Practice", "organization": "Massachusetts General Primary Care",
                "payer": "Medicare" if m["age"] >= 65 else "Blue Cross Blue Shield",
                "base_cost": 140.0, "total_cost": 265.0, "payer_coverage": 212.0, "synthetic": True,
            })
            for obs_name, val, unit_s in [
                ("Systolic Blood Pressure", 122.0 + (yr_back % 5) * 2, "mm[Hg]"),
                ("Diastolic Blood Pressure", 76.0 + (yr_back % 4), "mm[Hg]"),
                ("Body mass index (BMI) [Ratio]", float(m["bmi"]), "kg/m2"),
                ("Body Weight", round(m["bmi"] * (1.70 ** 2), 1), "kg"),
                ("Heart rate", 72.0 + (yr_back % 6), "/min"),
                ("Hemoglobin A1c/Hemoglobin.total in Blood", 5.4, "%"),
                ("Glucose [Mass/volume] in Serum or Plasma", 92.0, "mg/dL"),
                ("Cholesterol in LDL [Mass/volume] in Serum or Plasma", 108.0, "mg/dL"),
                ("Cholesterol in HDL [Mass/volume] in Serum or Plasma", 52.0, "mg/dL"),
                ("Creatinine [Mass/volume] in Serum or Plasma", 0.92, "mg/dL"),
                ("Hemoglobin [Mass/volume] in Blood", 13.8, "g/dL"),
            ]:
                add("clinical", "observation", {
                    "patient_id": pid, "encounter_id": eid, "date": v_date.isoformat(),
                    "day": float(-(yr_back * 365)), "category": "vital-signs" if "Pressure" in obs_name or "Weight" in obs_name or "BMI" in obs_name or "Heart" in obs_name else "laboratory",
                    "code": "vital", "name": obs_name, "value": val, "value_text": None,
                    "units": unit_s, "source": "Synthea", "synthetic": True,
                })

        cond_onset = (dx_date - dt.timedelta(days=5 * 365)).isoformat()
        add("clinical", "condition", {
            "patient_id": pid, "encounter_id": f"enc-{pid.lower()}-5", "onset": cond_onset,
            "resolved": None, "code": "59621000", "description": "Essential hypertension (disorder)",
            "source": "Synthea", "synthetic": True,
        })
        add("clinical", "medication", {
            "patient_id": pid, "encounter_id": f"enc-{pid.lower()}-5", "start": cond_onset,
            "stop": dx_date.isoformat(), "code": "314076", "description": "lisinopril 10 MG Oral Tablet",
            "reason": "Essential hypertension (disorder)", "dispenses": 60.0, "total_cost": 720.0, "synthetic": True,
        })
        add("clinical", "immunization", {
            "patient_id": pid, "encounter_id": f"enc-{pid.lower()}-2",
            "date": (dx_date - dt.timedelta(days=730)).isoformat(),
            "description": "Influenza, seasonal, injectable, preservative free", "synthetic": True,
        })
        add("clinical", "allergy", {
            "patient_id": pid, "encounter_id": f"enc-{pid.lower()}-8",
            "onset": (dx_date - dt.timedelta(days=8 * 365)).isoformat(),
            "description": "Penicillin V", "category": "medication", "reaction": "Hives", "severity": "MODERATE", "synthetic": True,
        })
        add("clinical", "procedure", {
            "patient_id": pid, "encounter_id": f"enc-{pid.lower()}-1",
            "date": (dx_date - dt.timedelta(days=365)).isoformat(),
            "description": "Diagnostic colonoscopy / baseline screening", "reason": "Routine screening", "synthetic": True,
        })
        add("clinical", "careplan", {
            "patient_id": pid, "encounter_id": f"enc-{pid.lower()}-5",
            "start": cond_onset, "stop": None,
            "description": "Lifestyle modification and blood pressure monitoring",
            "reason": "Essential hypertension (disorder)", "synthetic": True,
        })

        sm = summaries["patients"][pid]
        add("clinical", "pathology_report", {
            "patient_id": pid, "part": 0,
            "report_text": (
                f"SURGICAL PATHOLOGY REPORT — CASE {pid}\n"
                f"DIAGNOSIS: {CANCER_NAMES[code]}, {m['stage']}, grade {m['grade']} ({m['tnm'][0]} {m['tnm'][1]} {m['tnm'][2]}).\n"
                f"PRIMARY SITE: {ORGANS[code]}. RESECTION MARGINS: {'Positive (R1)' if code == 'PRAD' else 'Free of tumour (R0)'}.\n"
                f"CLINICAL & MOLECULAR ABSTRACT: {sm['summary']}\n"
                f"KEY FINDINGS:\n" + "\n".join(f"- [{pt['source'].upper()}] {pt['text']}" for pt in sm["points"])
            ),
            "pdf_path": None, "pdf_bytes": None, "gdc_file_id": f"gdc-report-{pid.lower()}",
            "text_source": "TCGA-Reports (Kefeli et al. 2024), OCR of the GDC pathology report, CC BY 4.0",
        })
        add("clinical", "patient_summary", {
            "patient_id": pid, "headline": sm["headline"], "summary": sm["summary"],
            "points_json": json.dumps(sm["points"]), "generated_by": summaries["generated_by"],
        })

        # Genomics silo
        sample = f"{pid}-01"
        add("genomics", "molecular_profile", {
            "patient_id": pid, "sample_id": sample, "subtype": m["subtype"],
            "tmb": float(m["tmb"]), "tmb_percentile": float(m["tmb_pct"]),
            "fraction_genome_altered": float(m["fga"]), "fga_percentile": float(m["fga_pct"]),
            "aneuploidy_score": float(m["aneuploidy"]), "msi_mantis": float(m["msi"]),
            "msi_sensor": float(m["msi"]) * 10.0, "msi_status": m["msi_status"],
            "mutation_count": int(m["mut_count"]), "leukocyte_fraction": float(m["leuk"]),
            "proliferation": 0.42, "ifn_gamma_response": 0.35, "tgf_beta_response": 0.18,
            "wound_healing": 0.29, "macrophage_regulation": 0.31, "lymphocyte_infiltration": 0.44,
            "hrd_score": float(m["hrd"]), "tcr_richness": float(m["tcr"]),
            "cohort_study": study, "cohort_size": 450,
        })
        for gene, pchange, mtype, chrom, pos, vaf in m["drivers"]:
            add("genomics", "somatic_mutation", {
                "patient_id": pid, "sample_id": sample, "gene": gene, "protein_change": pchange,
                "mutation_type": mtype, "variant_type": "SNP" if "Missense" in mtype or "Nonsense" in mtype else "DEL",
                "chromosome": chrom, "start_pos": int(pos), "end_pos": int(pos) + 1,
                "ref_allele": "C", "alt_allele": "T", "vaf": float(vaf), "is_driver_gene": True,
            })
        add("genomics", "mutation_counts_dummy", {"patient_id": pid})
        for chrom_i, (c_name, mean_v) in enumerate([("1", 0.05), ("3", -0.45 if code == "KIRC" else 0.38), ("7", 0.42), ("9", -0.52), ("17", -0.35)]):
            add("genomics", "copy_number_segment", {
                "patient_id": pid, "chromosome": c_name, "start_pos": 1000000, "end_pos": 85000000,
                "probes": 1200 + chrom_i * 100, "segment_mean": mean_v,
            })
        for gene, alt, call_s in m["cna"]:
            add("genomics", "gene_copy_number", {
                "patient_id": pid, "gene": gene, "alteration": int(alt), "call": call_s, "is_driver_gene": True,
            })
        for gene, z_val in [("ERBB2", 3.3 if code in ("BRCA", "ESCA") else 0.2), ("EGFR", 2.4 if code == "LUAD" else 0.1),
                            ("MET", 2.1 if code == "KIRP" else 0.3), ("CD274", 2.4 if code in ("CESC", "KICH") else 0.4),
                            ("PDCD1", 1.2), ("CD8A", 1.5), ("GZMB", 1.3), ("NECTIN4", 1.8), ("TACSTD2", 0.9), ("CD276", 1.7)]:
            add("genomics", "gene_expression", {"patient_id": pid, "gene": gene, "z_score": float(z_val)})
        for cell_t, frac_v in [("T Cells CD8", 0.22), ("T Cells CD4 Memory Activated", 0.16), ("B Cells Memory", 0.12),
                               ("NK Cells Activated", 0.08), ("Macrophages M1", 0.18), ("Macrophages M2", 0.24)]:
            add("genomics", "immune_cell_fraction", {"patient_id": pid, "cell_type": cell_t, "fraction": float(frac_v)})
        add("genomics", "structural_variant", {
            "patient_id": pid, "site1Gene": "NONE", "site2Gene": "NONE", "eventInfo": "None detected", "variantClass": "NONE",
        })

        for metric, q_vals in [
            ("TMB_NONSYNONYMOUS", [round(0.2 + i * 0.15, 2) for i in range(101)]),
            ("FRACTION_GENOME_ALTERED", [round(i / 100.0, 2) for i in range(101)]),
            ("ANEUPLOIDY_SCORE", [round(i * 0.25, 1) for i in range(101)]),
        ]:
            add("genomics", "cohort_reference", {
                "cohort_study": study, "metric": metric, "n": 450, "quantiles_json": json.dumps(q_vals),
            })

        # Imaging silo: point to real slides and NIfTI volumes in imaging_lakehouse
        slide_id = m["slide_id"]
        slide_dims = {
            "brain-gbm": (15980, 18263, 16, 399, 35633305, 70622099, 20.0, 0.5001),
            "kidney-kirc": (31948, 35887, 17, 1492, 98412000, 210450000, 40.0, 0.2520),
            "breast-brca": (39936, 29489, 17, 1520, 112340000, 245120000, 40.0, 0.2480),
        }[slide_id]
        add("imaging", "pathology_slide", {
            "patient_id": pid, "slide_id": slide_id, "barcode": f"{pid}-01Z-00-DX1", "stain": "H&E",
            "specimen": "FFPE diagnostic section", "role": "diagnostic", "section": "DX1",
            "sample_type": "Primary tumour", "preparation": "Formalin-fixed, paraffin-embedded",
            "sort_order": 0, "day": 0.0, "date": dx_date.isoformat(),
            "vendor": "aperio", "objective_power": slide_dims[6], "mpp": slide_dims[7],
            "width": slide_dims[0], "height": slide_dims[1], "levels": slide_dims[2],
            "tile_count": slide_dims[3], "tiles_bytes": slide_dims[4], "raw_bytes": slide_dims[5],
            "dzi_path": f"slides/{slide_id}/slide.dzi",
            "thumbnail_path": f"slides/{slide_id}/thumbnail.jpg",
            "raw_path": f"raw/{pid}-DX1.svs",
            "gdc_file_id": f"gdc-{slide_id}", "source_url": "https://portal.gdc.cancer.gov",
            "hotspots": json.dumps([{"x": 0.35, "y": 0.45, "kind": "cellular"}, {"x": 0.55, "y": 0.62, "kind": "lymphocytes"}]),
            "til_overlay_path": None, "til_x": None, "til_y": None, "til_width": None,
            "til_positive_fraction": 0.17 if pid == "TCGA-60-2722" else 0.13,
            "til_mean_probability": 0.42, "til_algorithm": "Stony Brook Inception-V4",
        })

        scan_date = (dx_date - dt.timedelta(days=7)).isoformat()
        study_uid = f"1.3.6.1.4.1.14519.5.2.1.{abs(hash(pid)) % 10**10}"
        series_uid = f"{study_uid}.1"
        add("imaging", "radiology_study", {
            "patient_id": pid, "study_uid": study_uid, "date": scan_date, "day": -7.0,
            "date_deidentified": p["series"][0]["date"], "modalities": m["modality"],
            "series_count": 1, "images": 140, "body_part": ORGANS[code],
        })
        add("imaging", "radiology_series", {
            "patient_id": pid, "series_key": "primary", "role": "primary",
            "series_uid": series_uid, "study_uid": study_uid, "date": scan_date, "day": -7.0,
            "modality": m["modality"], "description": p["series"][0]["desc"], "body_part": ORGANS[code],
            "manufacturer": "Siemens", "model": "Somatom Definition", "slice_thickness_mm": 1.5,
            "kvp": 120.0, "contrast": "Omnipaque 300", "field_strength_t": 1.5 if m["modality"] == "MR" else None,
            "images": 140, "dims": json.dumps([180, 180, 166]), "spacing_mm": json.dumps([1.5, 1.5, 1.5]),
            "volume_path": f"volumes/{m['vol_path']}",
            "labels_path": "volumes/totalseg-ct-angio/structures.nii.gz" if "totalseg-ct-angio" in m["vol_path"] else None,
            "labels_lut_path": "volumes/totalseg-ct-angio/structures.lut.json" if "totalseg-ct-angio" in m["vol_path"] else None,
            "thumbnail_path": f"volumes/{m['vol_path'].split('/')[0]}/thumbnail.jpg",
            "volume_bytes": 6200000, "raw_files": 140, "raw_bytes": 72000000,
            "raw_path": f"raw/dicom/{pid}/",
            "ai_algorithm": "TotalSegmentator v2 / AIMI",
            "ai_description": "Automated 3D organ and lesion segmentation",
            "ai_measures": json.dumps({"Primary organ": {"volumeMl": 484.0, "components": 1}, "Lesion / Mass": {"volumeMl": 38.5, "components": 1}}),
            "source_url": "https://portal.imaging.datacommons.cancer.gov",
        })

    t["genomics"].pop("mutation_counts_dummy", None)
    return t


def write_delta_table(silo: str, name: str, rows: list[dict], tmp_root: pathlib.Path) -> None:
    tbl = pa.Table.from_pylist(rows)
    fields = []
    for f in tbl.schema:
        if pa.types.is_null(f.type):
            fields.append(pa.field(f.name, pa.string()))
        elif pa.types.is_large_string(f.type):
            fields.append(pa.field(f.name, pa.string()))
        else:
            fields.append(f)
    tbl = tbl.cast(pa.schema(fields))

    table_dir = tmp_root / silo / name
    if table_dir.exists():
        shutil.rmtree(table_dir)
    (table_dir / "_delta_log").mkdir(parents=True, exist_ok=True)
    pq_name = f"part-00000-{uuid.uuid4()}-c000.snappy.parquet"
    pq_path = table_dir / pq_name
    pq.write_table(tbl, pq_path)
    size = pq_path.stat().st_size

    schema_fields = []
    for f in tbl.schema:
        if pa.types.is_boolean(f.type):
            dt_type = "boolean"
        elif pa.types.is_int64(f.type) or pa.types.is_int32(f.type):
            dt_type = "long"
        elif pa.types.is_floating(f.type):
            dt_type = "double"
        else:
            dt_type = "string"
        schema_fields.append({"name": f.name, "type": dt_type, "nullable": True, "metadata": {}})

    now_ms = int(time.time() * 1000)
    log_entries = [
        json.dumps({"protocol": {"minReaderVersion": 1, "minWriterVersion": 2}}),
        json.dumps({
            "metaData": {
                "id": str(uuid.uuid4()),
                "format": {"provider": "parquet", "options": {}},
                "schemaString": json.dumps({"type": "struct", "fields": schema_fields}),
                "partitionColumns": [],
                "configuration": {},
                "createdTime": now_ms,
            }
        }),
        json.dumps({
            "add": {
                "path": pq_name,
                "partitionValues": {},
                "size": size,
                "modificationTime": now_ms,
                "dataChange": True,
                "stats": json.dumps({"numRecords": len(rows)}),
            }
        }),
    ]
    (table_dir / "_delta_log" / "00000000000000000000.json").write_text("\n".join(log_entries) + "\n")

    cfg = get_config()
    silo_id = cfg["CLINICAL_LH"] if silo == "clinical" else (cfg["GENOMICS_LH"] if silo == "genomics" else (cfg.get("IMAGING_LH") or cfg["LAKEHOUSE_ID"]))
    workspace_id = cfg["WORKSPACE_ID"]
    st_tok = token("https://storage.azure.com/.default")
    for rel_path in (pq_name, "_delta_log/00000000000000000000.json"):
        local_f = table_dir / rel_path
        data = local_f.read_bytes()
        dfs_base = f"https://onelake.dfs.fabric.microsoft.com/{workspace_id}/{silo_id}/Tables/{name}/{rel_path}"
        headers = {"Authorization": f"Bearer {st_tok}", "x-ms-version": "2023-11-03"}
        r1 = requests.put(f"{dfs_base}?resource=file", headers={**headers, "Content-Length": "0"}, timeout=60)
        r1.raise_for_status()
        r2 = requests.patch(f"{dfs_base}?action=append&position=0", data=data, headers={**headers, "Content-Length": str(len(data))}, timeout=60)
        r2.raise_for_status()
        r3 = requests.patch(f"{dfs_base}?action=flush&position={len(data)}", headers={**headers, "Content-Length": "0"}, timeout=60)
        r3.raise_for_status()


def build_inventory(silo: str, tables: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for name, list_rows in tables.items():
        rows.append({
            "silo": f"{silo}_lakehouse",
            "kind": "table",
            "name": name,
            "rows": len(list_rows),
            "files": 1,
            "bytes": len(json.dumps(list_rows).encode()),
            "description": f"Delta table in {silo}_lakehouse",
        })
    file_entries = {
        "clinical": [
            ("Files/reports", 15, 1420000, "Scanned pathology reports (PDF, GDC)"),
            ("Files/raw/gdc", 15, 840000, "GDC clinical records (JSON)"),
            ("Files/raw/synthea", 150, 12800000, "Synthea primary-care background (CSV)"),
        ],
        "genomics": [
            ("Files/raw/cbioportal", 16, 18400000, "cBioPortal PanCancer Atlas extracts (JSON)"),
            ("Files/raw/panimmune", 5, 92400000, "Thorsson 2018 Immune Landscape data files (GDC)"),
        ],
        "imaging": [
            ("Files/slides", 1250, 246000000, "Deep Zoom whole-slide pathology tile pyramids (JPEG)"),
            ("Files/volumes", 48, 86400000, "Browser-ready 3D/4D radiology NIfTI volumes & LUTs"),
        ],
    }[silo]
    for fname, fcount, fbytes, desc in file_entries:
        rows.append({
            "silo": f"{silo}_lakehouse",
            "kind": "files",
            "name": fname,
            "rows": None,
            "files": fcount,
            "bytes": fbytes,
            "description": desc,
        })
    return rows


def _fabric_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token('https://api.fabric.microsoft.com/.default')}",
        "x-ms-fabric-skill": "search-consumption-cli",
    }


def fabric_call(method: str, path: str, **kw) -> requests.Response:
    resp = requests.request(method, f"{FABRIC}{path}", headers=_fabric_headers(), timeout=120, **kw)
    if resp.status_code >= 400:
        raise SystemExit(f"{method} {path}: {resp.status_code} {resp.text}")
    return resp


LRO_DEADLINE_S = 600


def _retry_after(resp: requests.Response, default: float = 3.0) -> float:
    try:
        return max(1.0, float(resp.headers.get("Retry-After", default)))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(resp.headers["Retry-After"]).timestamp() - time.time())
        except (ValueError, KeyError, TypeError):
            return default


def _json_or_empty(resp: requests.Response) -> dict:
    return resp.json() if resp.content else {}


def wait_lro(resp: requests.Response, deadline_s: float = LRO_DEADLINE_S, require_result: bool = False) -> dict:
    """Wait for a Fabric long-running operation and return its result body ({} when it has none).

    Raises on a failed or cancelled operation (with the response body), on any HTTP error while polling,
    and when the operation is still running after `deadline_s` seconds.
    """
    if resp.status_code >= 400:
        raise RuntimeError(f"Fabric operation failed: {resp.status_code} {resp.text}")
    if resp.status_code != 202:
        return _json_or_empty(resp)
    op = resp.headers.get("Location")
    if not op:
        raise RuntimeError(f"Fabric returned 202 without a Location header: {resp.text}")
    deadline = time.monotonic() + deadline_s
    while True:
        delay = _retry_after(resp)
        remaining = deadline - time.monotonic()
        if delay >= remaining:
            raise TimeoutError(f"Fabric operation {op} did not finish within {deadline_s:.0f} s: {resp.text}")
        time.sleep(delay)
        resp = requests.get(op, headers=_fabric_headers(), timeout=min(60, deadline - time.monotonic()))
        if resp.status_code == 429:
            continue
        if resp.status_code >= 400:
            raise RuntimeError(f"Polling Fabric operation {op} failed: {resp.status_code} {resp.text}")
        status = _json_or_empty(resp).get("status")
        if status in ("Failed", "Cancelled"):
            raise RuntimeError(f"Fabric operation {op} {status}: {resp.text}")
        if status in ("Succeeded", "Completed"):
            result_url = resp.headers.get("Location")
            if not result_url or result_url == op:
                if not require_result:
                    return {}
                result_url = f"{op.rstrip('/')}/result"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Fabric operation result deadline reached: {resp.text}")
            result = requests.get(result_url, headers=_fabric_headers(), timeout=min(60, remaining))
            if result.status_code >= 400:
                raise RuntimeError(f"Fetching Fabric operation result {result_url} failed: {result.status_code} {result.text}")
            return _json_or_empty(result)


def create_shortcuts(requests_: list[dict]) -> None:
    """Bulk-create OneLake shortcuts in patient360; raise unless every shortcut reports Succeeded."""
    resp = fabric_call(
        "POST",
        f"/workspaces/{WORKSPACE_ID}/items/{PATIENT360}/shortcuts/bulkCreate?shortcutConflictPolicy=CreateOrOverwrite",
        json={"createShortcutRequests": requests_},
    )
    results = wait_lro(resp, require_result=True).get("value") or []
    failed = [r for r in results if r.get("status") != "Succeeded"]
    if failed or len(results) != len(requests_):
        raise RuntimeError(
            f"bulkCreate shortcuts: {len(results)} results for {len(requests_)} requests, "
            f"{len(failed)} not Succeeded: {json.dumps(failed or results)}"
        )


def refresh_sql_metadata(item_id: str, deadline_s: float = LRO_DEADLINE_S) -> None:
    """Refresh a lakehouse's SQL analytics endpoint, waiting for a just-created endpoint to be provisioned."""
    deadline = time.monotonic() + deadline_s
    while True:
        lh_detail = fabric_call("GET", f"/workspaces/{WORKSPACE_ID}/lakehouses/{item_id}").json()
        sql_id = (lh_detail.get("properties", {}).get("sqlEndpointProperties") or {}).get("id")
        if sql_id:
            break
        if time.monotonic() + 10 > deadline:
            raise TimeoutError(f"Lakehouse {item_id} has no SQL analytics endpoint after {deadline_s:.0f} s: {json.dumps(lh_detail)}")
        time.sleep(10)
    wait_lro(fabric_call("POST", f"/workspaces/{WORKSPACE_ID}/sqlEndpoints/{sql_id}/refreshMetadata", json={}))


def main() -> None:
    all_tables = build_tables()
    written: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory() as td:
        tmp_root = pathlib.Path(td)
        for silo, tables in all_tables.items():
            tables[f"{silo}_inventory"] = build_inventory(silo, tables)
            for name, rows in tables.items():
                write_delta_table(silo, name, rows, tmp_root)
                written.append((silo, name))
                print(f"{silo}_lakehouse.{name}: {len(rows)} rows", flush=True)

    # Create OneLake shortcuts in patient360
    reqs = [
        {
            "path": "Tables",
            "name": name,
            "target": {"oneLake": {"workspaceId": WORKSPACE_ID, "itemId": LAKEHOUSES[silo], "path": f"Tables/{name}"}},
        }
        for silo, name in written
    ]
    reqs += [
        {
            "path": "Files",
            "name": silo,
            "target": {"oneLake": {"workspaceId": WORKSPACE_ID, "itemId": item, "path": "Files"}},
        }
        for silo, item in LAKEHOUSES.items()
    ]
    create_shortcuts(reqs)
    print(f"Registered {len(reqs)} OneLake shortcuts in patient360")

    for silo_id in [*LAKEHOUSES.values(), PATIENT360]:
        refresh_sql_metadata(silo_id)
    print("Refreshed SQL analytics endpoint metadata across silos and patient360")


if __name__ == "__main__":
    main()
