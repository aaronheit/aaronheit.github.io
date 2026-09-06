#!/usr/bin/env python3
"""
MN SCIENCE MCA-IV DASHBOARD — PHASE 1 TRANSFORM
Reads the MDE Assessment File (Science, Public) and emits tidy CSVs for Tableau.
"""
import pandas as pd, numpy as np
from scipy.stats import norm
import os, sys

SRC = "/mnt/user-data/uploads/MCAALTMCA_Science_Public_Oct2025.xlsx"
OUT = "/home/claude/out"
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------
# Cut scores from MDE "Science Performance Level Cut Scores" (Sept 2025)
# ---------------------------------------------------------------
CUTS = pd.DataFrame([
    ("5",  "Beginning",    501,  539, 1), ("5",  "Intermediate", 540,  549, 2),
    ("5",  "Meets",        550,  560, 3), ("5",  "Advanced",     561,  599, 4),
    ("8",  "Beginning",    801,  839, 1), ("8",  "Intermediate", 840,  849, 2),
    ("8",  "Meets",        850,  858, 3), ("8",  "Advanced",     859,  899, 4),
    ("HS", "Beginning",   1001, 1039, 1), ("HS", "Intermediate",1040, 1049, 2),
    ("HS", "Meets",       1050, 1066, 3), ("HS", "Advanced",    1067, 1099, 4),
], columns=["grade", "performance_level", "score_min", "score_max", "level_order"])

MEETS_CUT   = {"5": 550,  "8": 850,  "HS": 1050}
SCALE_MIN   = {"5": 501,  "8": 801,  "HS": 1001}
SCALE_MAX   = {"5": 599,  "8": 899,  "HS": 1099}

RENAME = {
    "Data Year":"data_year","County Number":"county_number","County Name":"county_name",
    "District Number":"district_number","District Type":"district_type","District Name":"district_name",
    "School Number":"school_number","School Name":"school_name","ECSU Number":"ecsu_number",
    "Economic Development Region":"econ_dev_region","School Classification":"school_classification",
    "Test Name":"test_name","Grade":"grade","Subject":"subject",
    "Group Category":"group_category","Student Group":"student_group",
    "Total Tested":"total_tested","Filter All":"filter_all",
    "Count Valid Scores MCA":"count_valid_mca","Filter MCA":"filter_mca",
    "Count Valid Scores ALTMCA":"count_valid_altmca","Filter ALTMCA":"filter_altmca",
    "Count Level B":"count_beginning","Count Level I":"count_intermediate",
    "Count Level M":"count_meets","Count Level A":"count_advanced",
    "Percent Proficient":"pct_proficient","Percent Level B":"pct_beginning",
    "Percent Level I":"pct_intermediate","Percent Level M":"pct_meets",
    "Percent Level A":"pct_advanced",
    "MCA Average Score":"mca_mean","MCA Standard Deviation":"mca_sd",
    "ALTMCA Average Score":"altmca_mean","ALTMCA Standard Deviation":"altmca_sd",
    "Count Absent":"n_absent","Count Invalid - Student Behavior":"n_invalid_behavior",
    "Count Invalid - Device":"n_invalid_device","Count Invalid - Other":"n_invalid_other",
    "Count Medical Exempt":"n_medical_exempt","Count Not Attempted":"n_not_attempted",
    "Count Not Complete":"n_not_complete","Count Not Enrolled":"n_not_enrolled",
    "Count Refused - Parent":"n_refused_parent","Count Refused - Student":"n_refused_student",
    "Count Wrong Grade":"n_wrong_grade",
    "Count Valid Scores MCA with Accommodations":"n_accommodations",
    "Count Extenuating Circumstances Attempted":"n_ext_attempted",
    "Count Extenuating Circumstances Not Attempted":"n_ext_not_attempted",
}

NUMERIC = ["total_tested","count_valid_mca","count_valid_altmca","count_beginning",
    "count_intermediate","count_meets","count_advanced","pct_proficient","pct_beginning",
    "pct_intermediate","pct_meets","pct_advanced","mca_mean","mca_sd","altmca_mean",
    "altmca_sd","n_absent","n_invalid_behavior","n_invalid_device","n_invalid_other",
    "n_medical_exempt","n_not_attempted","n_not_complete","n_not_enrolled",
    "n_refused_parent","n_refused_student","n_wrong_grade","n_accommodations",
    "n_ext_attempted","n_ext_not_attempted"]

print("=" * 70); print("MN SCIENCE MCA-IV — TABLEAU TRANSFORM"); print("=" * 70)

frames = []
for sheet, level in [("State","State"), ("District","District"), ("School","School")]:
    d = pd.read_excel(SRC, sheet_name=sheet, dtype=str)
    d = d.rename(columns=RENAME)
    d = d[d["data_year"].astype(str).str.match(r"^\d{2}-\d{2}$", na=False)]
    d["summary_level"] = level
    print(f"  {sheet:<9} raw rows: {len(d):>7,}")
    frames.append(d)

df = pd.concat(frames, ignore_index=True, sort=False)
for c in NUMERIC:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

print(f"\n  combined: {len(df):,} rows")

# Grade '0' is an all-grades roll-up. Drop it: it double-counts.
before = len(df)
df = df[df["grade"].isin(["5", "8", "HS"])].copy()
print(f"  dropped grade '0' roll-up: {before - len(df):,} rows -> {len(df):,} remain")

# ---------------------------------------------------------------
# Derived: cut-score geometry
# ---------------------------------------------------------------
df["meets_cut"]  = df["grade"].map(MEETS_CUT)
df["scale_min"]  = df["grade"].map(SCALE_MIN)
df["scale_max"]  = df["grade"].map(SCALE_MAX)

df["points_to_cut"] = df["meets_cut"] - df["mca_mean"]        # >0 = mean below cut
df["z_to_cut"] = np.where(df["mca_sd"] > 0,
                          df["points_to_cut"] / df["mca_sd"], np.nan)
df["est_pct_above_cut"] = np.where(df["z_to_cut"].notna(),
                                   1 - norm.cdf(df["z_to_cut"]), np.nan)
df["model_residual"] = df["pct_proficient"] - df["est_pct_above_cut"]
df["mean_above_cut"] = np.where(df["mca_mean"].notna(),
                                df["mca_mean"] >= df["meets_cut"], np.nan)

# Position of the mean within the 0-100 normalized scale, for band plotting
df["mean_pct_of_scale"] = ((df["mca_mean"] - df["scale_min"]) /
                           (df["scale_max"] - df["scale_min"]))

# "One band away" — students in Intermediate are within 10 pts of Meets
df["pct_near_cut"] = df["pct_intermediate"]
df["count_near_cut"] = df["count_intermediate"]
df["pct_proficient_or_near"] = df["pct_proficient"] + df["pct_intermediate"]

# ---------------------------------------------------------------
# Derived: participation (constructed — NOT MDE's official rate)
# ---------------------------------------------------------------
refuse = ["n_refused_parent", "n_refused_student"]
miss   = ["n_absent", "n_not_attempted", "n_medical_exempt"]
inval  = ["n_invalid_behavior", "n_invalid_device", "n_invalid_other",
          "n_not_complete", "n_ext_attempted", "n_ext_not_attempted"]

df["n_refused_total"]  = df[refuse].sum(axis=1, min_count=1)
df["n_missing_total"]  = df[miss].sum(axis=1, min_count=1)
df["n_invalid_total"]  = df[inval].sum(axis=1, min_count=1)
df["n_nonparticipant"] = df[["n_refused_total","n_missing_total","n_invalid_total"]].sum(axis=1, min_count=1)
df["denom_participation"] = df["total_tested"].fillna(0) + df["n_nonparticipant"].fillna(0)

dp = df["denom_participation"].replace(0, np.nan)
df["pct_participation"]    = df["total_tested"]     / dp
df["pct_refused_parent"]   = df["n_refused_parent"] / dp
df["pct_refused_student"]  = df["n_refused_student"]/ dp
df["pct_refused_total"]    = df["n_refused_total"]  / dp
df["pct_nonparticipant"]   = df["n_nonparticipant"] / dp
df["below_95_participation"] = np.where(df["pct_participation"].notna(),
                                        df["pct_participation"] < 0.95, np.nan)
df["pct_accommodations"] = np.where(df["count_valid_mca"] > 0,
                                    df["n_accommodations"] / df["count_valid_mca"], np.nan)

# ---------------------------------------------------------------
# Flags
# ---------------------------------------------------------------
df["is_suppressed"] = (df["filter_all"].astype(str).str.upper() == "Y")
df["is_anoka_hennepin"] = (df["district_number"].astype(str).str.strip() == "11") & \
                          (df["district_type"].astype(str).str.strip() == "1")
df["district_focus"] = np.where(df["is_anoka_hennepin"], "Anoka-Hennepin", "Other Minnesota")
df["grade_label"] = df["grade"].map({"5":"Grade 5","8":"Grade 8","HS":"High School"})
df["grade_order"] = df["grade"].map({"5":1,"8":2,"HS":3})

# ---------------------------------------------------------------
# Statewide percentile ranks (school level only, within grade x group)
# ---------------------------------------------------------------
sch = df["summary_level"] == "School"
for src, dest in [("mca_mean","pctile_mean"), ("pct_proficient","pctile_proficient"),
                  ("pct_near_cut","pctile_near_cut")]:
    df.loc[sch, dest] = (df.loc[sch]
        .groupby(["grade","student_group"])[src]
        .rank(pct=True, na_option="keep"))

df.loc[sch, "state_rank_mean"] = (df.loc[sch]
    .groupby(["grade","student_group"])["mca_mean"]
    .rank(ascending=False, method="min", na_option="keep"))
df.loc[sch, "state_n_schools"] = (df.loc[sch]
    .groupby(["grade","student_group"])["mca_mean"]
    .transform(lambda s: s.notna().sum()))

# ---------------------------------------------------------------
# Column order + write
# ---------------------------------------------------------------
ID = ["summary_level","data_year","county_name","district_number","district_type",
      "district_name","school_number","school_name","econ_dev_region",
      "school_classification","is_anoka_hennepin","district_focus"]
DIM = ["grade","grade_label","grade_order","subject","group_category","student_group"]
CNT = ["total_tested","count_valid_mca","count_valid_altmca","count_beginning",
       "count_intermediate","count_meets","count_advanced","count_near_cut"]
PCT = ["pct_proficient","pct_beginning","pct_intermediate","pct_meets","pct_advanced",
       "pct_near_cut","pct_proficient_or_near"]
SCR = ["mca_mean","mca_sd","meets_cut","scale_min","scale_max","points_to_cut",
       "z_to_cut","est_pct_above_cut","model_residual","mean_above_cut",
       "mean_pct_of_scale","altmca_mean","altmca_sd"]
PAR = ["n_refused_parent","n_refused_student","n_refused_total","n_absent",
       "n_not_attempted","n_medical_exempt","n_missing_total","n_invalid_behavior",
       "n_invalid_device","n_invalid_other","n_not_complete","n_ext_attempted",
       "n_ext_not_attempted","n_invalid_total","n_nonparticipant",
       "denom_participation","pct_participation","pct_refused_parent",
       "pct_refused_student","pct_refused_total","pct_nonparticipant",
       "below_95_participation","n_accommodations","pct_accommodations"]
RNK = ["pctile_mean","pctile_proficient","pctile_near_cut","state_rank_mean","state_n_schools"]
FLG = ["filter_all","filter_mca","filter_altmca","is_suppressed"]

cols = [c for c in ID+DIM+CNT+PCT+SCR+PAR+RNK+FLG if c in df.columns]
out = df[cols].copy()

main = f"{OUT}/mn_science_mca4_2025.csv"
out.to_csv(main, index=False)
CUTS.to_csv(f"{OUT}/mn_science_cutscores.csv", index=False)

# Slim school-only extract for the headline panels
slim = out[(out.summary_level=="School") & (out.student_group=="All students")]
slim.to_csv(f"{OUT}/mn_science_schools_allstudents.csv", index=False)

print("\n" + "=" * 70); print("OUTPUT"); print("=" * 70)
print(f"  mn_science_mca4_2025.csv          {len(out):>7,} rows x {len(cols)} cols")
print(f"  mn_science_schools_allstudents.csv{len(slim):>7,} rows")
print(f"  mn_science_cutscores.csv          {len(CUTS):>7,} rows")

# ---------------------------------------------------------------
# Verification
# ---------------------------------------------------------------
print("\n" + "=" * 70); print("VERIFICATION"); print("=" * 70)
g5 = slim[(slim.grade=="5") & slim.mca_mean.notna()]
print(f"\nGrade 5 schools statewide with a mean score: {len(g5):,}")
print(f"  mean score  min {g5.mca_mean.min():.1f} | p10 {g5.mca_mean.quantile(.1):.1f} "
      f"| median {g5.mca_mean.median():.1f} | p90 {g5.mca_mean.quantile(.9):.1f} "
      f"| max {g5.mca_mean.max():.1f}")
print(f"  schools with mean >= 550 cut: {int(g5.mean_above_cut.sum())} of {len(g5)}")
print(f"  median within-school SD: {g5.mca_sd.median():.2f}")
print(f"  median pct_near_cut (Intermediate): {g5.pct_near_cut.median():.1%}")

ah5 = g5[g5.is_anoka_hennepin]
print(f"\nAnoka-Hennepin grade 5: {len(ah5)} schools")
print(f"  mean range {ah5.mca_mean.min():.1f} - {ah5.mca_mean.max():.1f} "
      f"({ah5.mca_mean.max()-ah5.mca_mean.min():.1f} pts)")
print(f"  proficiency range {ah5.pct_proficient.min():.1%} - {ah5.pct_proficient.max():.1%}")
print(f"  median statewide percentile (mean score): {ah5.pctile_mean.median():.1%}")

print(f"\nModel check — corr(actual proficient, normal-model estimate): "
      f"{g5[['pct_proficient','est_pct_above_cut']].corr().iloc[0,1]:.3f}")
print(f"  median |residual|: {g5.model_residual.abs().median():.3f}")

print(f"\nParticipation, grade 5 statewide:")
print(f"  median participation rate: {g5.pct_participation.median():.1%}")
print(f"  schools below 95%: {int(g5.below_95_participation.sum())} of "
      f"{int(g5.below_95_participation.notna().sum())}")
print(f"  total parent refusals: {int(g5.n_refused_parent.sum()):,}")
print(f"  total student refusals: {int(g5.n_refused_student.sum()):,}")

print(f"\nSuppression: {int(slim.is_suppressed.sum())} of {len(slim)} school rows "
      f"({slim.is_suppressed.mean():.1%})")

print(f"\nGrade coverage (school level, All students):")
print(slim.groupby("grade_label").size().to_string())
print("\nDONE.")
