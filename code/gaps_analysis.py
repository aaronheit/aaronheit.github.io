"""
The Gap Depends on the Line
Statewide Science MCA-IV achievement gaps, spring 2025, measured three ways:
  1. Percentage-point gaps at each of MDE's three published cut scores
     (computed directly from the published performance-level shares).
  2. A standardized mean gap (pooled-SD effect size), which does not depend on any cut.
  3. A normal-model curve showing the gap at every possible cut, validated against (1).
Source: MDE Assessment Files, All Standards-Based (MCA/MTAS/ALTMCA), Science, Public, 2025, State sheet.
"""
import json, math, sys
import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "MCAALTMCA_Science_Public_Oct2025.xlsx"
OUT = sys.argv[2] if len(sys.argv) > 2 else "gaps_data.json"

SCALE = {"5":  {"label": "Grade 5",     "min": 501,  "max": 599,  "cuts": {"I": 540,  "M": 550,  "A": 561}},
         "8":  {"label": "Grade 8",     "min": 801,  "max": 899,  "cuts": {"I": 840,  "M": 850,  "A": 859}},
         "HS": {"label": "High school", "min": 1001, "max": 1099, "cuts": {"I": 1040, "M": 1050, "A": 1067}}}

GROUPS = {
    "el":       ("English learners",                  "English learners"),
    "not_el":   ("Not English learners",              "Not English learners"),
    "hl":       ("Students experiencing homelessness","Experiencing homelessness"),
    "not_hl":   ("Students not experiencing homelessness","Not experiencing homelessness"),
    "frpm":     ("Students eligible for free/reduced-price meals","Eligible for free or reduced-price meals"),
    "not_frpm": ("Students not eligible for free/reduced-price meals","Not eligible"),
    "sped":     ("Students receiving special education services","Receiving special education"),
    "not_sped": ("Students not receiving special education services","Not receiving special education"),
    "black":    ("Black or African American students","Black students"),
    "hisp":     ("Hispanic or Latino students","Hispanic or Latino students"),
    "amind":    ("American Indian Students","American Indian students"),
    "asian":    ("Asian students","Asian students"),
    "multi":    ("Students with two or more races","Students of two or more races"),
    "white":    ("White students","White students"),
    "female":   ("Female students","Female students"),
    "male":     ("Male students","Male students"),
}

PAIRS = [  # (id, focal, reference, label)
    ("el",     "el",    "not_el",   "English learners and non-English learners"),
    ("hl",     "hl",    "not_hl",   "Students experiencing homelessness and those who are not"),
    ("black",  "black", "white",    "Black and White students"),
    ("hisp",   "hisp",  "white",    "Hispanic or Latino and White students"),
    ("frpm",   "frpm",  "not_frpm", "Students eligible and not eligible for free or reduced-price meals"),
    ("amind",  "amind", "white",    "American Indian and White students"),
    ("sped",   "sped",  "not_sped", "Students receiving and not receiving special education"),
    ("asian",  "asian", "white",    "Asian and White students"),
    ("multi",  "multi", "white",    "Students of two or more races and White students"),
    ("gender", "female","male",     "Female and male students"),
]

def phi(z):  # standard normal CDF
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))

def share_at_or_above(mean, sd, cut):  # continuity-corrected for integer scale scores
    return 1 - phi((cut - 0.5 - mean) / sd)

df = pd.read_excel(SRC, sheet_name="State", dtype=str)
df = df[df["Data Year"] == "24-25"]
num = ["Count Valid Scores MCA", "Count Valid Scores ALTMCA", "MCA Average Score", "MCA Standard Deviation",
       "Percent Level B", "Percent Level I", "Percent Level M", "Percent Level A", "Percent Proficient"]
for c in num: df[c] = pd.to_numeric(df[c], errors="coerce")

out = {"grades": {}, "pairs": [{"id": p, "focal": f, "ref": r, "label": l} for p, f, r, l in PAIRS],
       "source": "MDE Assessment Files, Science, Public, 2025 (State)"}
abs_err = []

for g, meta in SCALE.items():
    gd = df[df["Grade"] == g]
    groups = {}
    for key, (mde_name, short) in GROUPS.items():
        row = gd[gd["Student Group"] == mde_name]
        if row.empty: continue
        r = row.iloc[0]
        ge = {"I": r["Percent Level I"] + r["Percent Level M"] + r["Percent Level A"],
              "M": r["Percent Level M"] + r["Percent Level A"],
              "A": r["Percent Level A"]}
        alt = r["Count Valid Scores ALTMCA"]; mca = r["Count Valid Scores MCA"]
        groups[key] = {"name": short, "mean": round(r["MCA Average Score"], 2), "sd": round(r["MCA Standard Deviation"], 2),
                       "n": int(mca), "alt_share": round(alt / (alt + mca), 4) if (alt + mca) else 0,
                       "ge": {k: round(v, 4) for k, v in ge.items()}}
        for k, c in meta["cuts"].items():
            abs_err.append(abs(share_at_or_above(r["MCA Average Score"], r["MCA Standard Deviation"], c) - ge[k]))

    stats = []
    for pid, f, ref, _ in PAIRS:
        a, b = groups[f], groups[ref]
        pooled = math.sqrt(((a["n"] - 1) * a["sd"] ** 2 + (b["n"] - 1) * b["sd"] ** 2) / (a["n"] + b["n"] - 2))
        d = (b["mean"] - a["mean"]) / pooled
        gaps = {k: round((b["ge"][k] - a["ge"][k]) * 100, 1) for k in "IMA"}
        curve = [(c, (share_at_or_above(b["mean"], b["sd"], c) - share_at_or_above(a["mean"], a["sd"], c)) * 100)
                 for c in range(meta["min"], meta["max"] + 1)]
        peak = max(curve, key=lambda t: abs(t[1]))
        stats.append({"pair": pid, "d": round(d, 2), "gaps": gaps, "peak_cut": peak[0], "peak_gap": round(peak[1], 1)})
    order_d = sorted(stats, key=lambda s: -abs(s["d"]))
    order_p = sorted(stats, key=lambda s: -abs(s["gaps"]["M"]))
    for s in stats:
        s["rank_d"] = order_d.index(s) + 1
        s["rank_prof"] = order_p.index(s) + 1
    out["grades"][g] = {**meta, "groups": groups, "stats": stats}

out["model_mae_points"] = round(sum(abs_err) / len(abs_err) * 100, 2)
out["model_max_err_points"] = round(max(abs_err) * 100, 2)
json.dump(out, open(OUT, "w"), separators=(",", ":"))
print(f"wrote {OUT}  ({len(json.dumps(out)):,} bytes)")
print(f"normal model vs published shares at all three cuts: mean abs error {out['model_mae_points']} pts, max {out['model_max_err_points']} pts")
for g in out["grades"]:
    print(f"\n=== {out['grades'][g]['label']} ===   pair: gap@I  gap@M  gap@A  | d  | rank by prof -> rank by d")
    for s in out["grades"][g]["stats"]:
        print(f"  {s['pair']:<7} {s['gaps']['I']:>6} {s['gaps']['M']:>6} {s['gaps']['A']:>6}  | {s['d']:>5} | {s['rank_prof']:>2} -> {s['rank_d']:>2}   peak {s['peak_gap']} @ {s['peak_cut']}")
