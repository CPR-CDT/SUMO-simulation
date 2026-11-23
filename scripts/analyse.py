"""Paired (same-seed) differences of every arm vs the baseline, with 95% CIs, plus a summary figure.

python scripts/analyse.py runs/batch_v1.csv
Writes runs/results_v1.md and runs/fig_v1.png.
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

src = Path(sys.argv[1])
tag = src.stem.replace("batch_", "")
df = pd.read_csv(src)
if "error" in df:
    bad = df[df["error"].notna()]
    if len(bad):
        print("RUNS WITH ERRORS:\n", bad[["scenario", "seed", "error"]])
    df = df[df["error"].isna()]

METRICS = [  # column, label, unit scale
    ("resp_mean_s", "Ambulance response, mean (min)", 1 / 60),
    ("resp_p90_s", "Ambulance response, P90 (min)", 1 / 60),
    ("travel_mean_s", "Ambulance travel time (min)", 1 / 60),
    ("unit_wait_mean_s", "Wait for a free unit (min)", 1 / 60),
    ("bg_timeloss_veh_h", "Background delay (veh-h)", 1),
    ("lane_block_min", "AV lane-blocking (AV-min)", 1),
    ("stranded_pax_min", "Stranded passengers (pax-min)", 1),
    ("assist_wait_mean_s", "Assist queue wait, mean (min)", 1 / 60),
    ("unserved_frac", "Unserved trip share", 1),
    ("probe_ratio_mean", "Probe ambulance travel / route estimate", 1),
    ("probe_share_teleported", "Probe ambulances stuck ≥5 min (share)", 1),
]
base = df[df["name"] == "baseline"].set_index("seed")
rows = []
for name, g in df[df["name"] != "baseline"].groupby("name"):
    g = g.set_index("seed")
    seeds = g.index.intersection(base.index)
    row = {"arm": name, "n_seeds": len(seeds)}
    for col, label, k in METRICS:
        if col not in g:
            continue
        d = (g.loc[seeds, col] - base.loc[seeds, col]).astype(float).dropna() * k
        m = d.mean()
        h = stats.t.ppf(0.975, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else np.nan
        row[col] = m
        row[col + "_ci"] = h
    rows.append(row)
res = pd.DataFrame(rows).set_index("arm").sort_index()

lines = [f"# Paired differences vs baseline ({tag})", "",
         "Mean of (arm − baseline) over common-random-number seeds, ± 95% t-interval half-width.", "",
         "| arm | n | " + " | ".join(l for _, l, _ in METRICS) + " |",
         "|---|---|" + "---|" * len(METRICS)]
for arm, r in res.iterrows():
    cells = [f"{r[c]:+.2f} ± {r[c + '_ci']:.2f}" if c in r and pd.notna(r[c]) else "–" for c, _, _ in METRICS]
    lines.append(f"| {arm} | {int(r['n_seeds'])} | " + " | ".join(cells) + " |")
bl = base[[c for c, _, _ in METRICS if c in base]].mean()
lines += ["", "Baseline absolute means: " + ", ".join(f"{l} = {bl[c] * k:.2f}" for c, l, k in METRICS if c in bl)]
lines += ["", "Teleports and collisions per arm (mean over seeds):", "",
          df.groupby("name")[[c for c in df.columns if c.startswith("teleports.") or c == "collisions"]]
          .mean().round(1).to_markdown()]
out_md = src.parent / f"results_{tag}.md"
out_md.write_text("\n".join(lines))
print("\n".join(lines))

# ---- figure: four panels, attack on x, policy as colour (reference palette slots 1-3, fixed order)
POL = {"P0": ("#2a78d6", "P0 stop in lane"), "P1": ("#eb6834", "P1 pull over"), "P2": ("#1baf7a", "P2 safe harbour")}
SURF, INK, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
panels = [METRICS[4], METRICS[5], METRICS[0], METRICS[10]]
attacks = ["A1", "A2", "A3", "A5"]
fig, axes = plt.subplots(2, 2, figsize=(11, 7), facecolor=SURF)
for ax, (col, label, _) in zip(axes.flat, panels):
    ax.set_facecolor(SURF)
    w = 0.26
    for ai, a in enumerate(attacks):
        for pi, p in enumerate(POL):
            arm = f"{a}_{p}" if a in ("A1", "A2") else (a if p == "P0" else None)
            if arm is None or arm not in res.index:
                continue
            x = ai + (pi - 1) * w if a in ("A1", "A2") else ai
            v, ci = res.loc[arm, col], res.loc[arm, col + "_ci"]
            ax.bar(x, v, w - 0.03, color=POL[p][0], zorder=2)
            if pd.notna(ci):
                ax.errorbar(x, v, yerr=ci, color=INK, lw=1, capsize=3, zorder=3)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xticks(range(len(attacks)))
    ax.set_xticklabels(["A1 zonal\nlink loss", "A2 fleet\noutage", "A3 ghost\nbookings", "A5 assist\nflood"],
                       color=MUTED, fontsize=9)
    ax.set_title("Δ " + label, loc="left", fontsize=10.5, color=INK)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color="#e4e3df", lw=0.6, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9c8c2")
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c, _ in POL.values()]
fig.legend(handles, [l for _, l in POL.values()], loc="upper center", bbox_to_anchor=(0.5, 0.955), ncol=3, frameon=False, fontsize=10,
           labelcolor=INK)
fig.suptitle("Change vs same-seed baseline (mean ± 95% CI, 5 paired seeds); A3/A5 run under P0 only", y=0.995, fontsize=11,
             color=MUTED)
fig.tight_layout(rect=(0, 0, 1, 0.91))
out_png = src.parent / f"fig_{tag}.png"
fig.savefig(out_png, dpi=160, facecolor=SURF)
print("wrote", out_md, out_png)
