"""Render one or more replay runs side by side as an MP4 and a GIF (for the README).

python scripts/make_video.py out_basename runs/A2_P0_s1 [runs/A2_P2_s1 ...] [--every 6] [--from 1500] [--to 4500]

Needs runs recorded with --replay. Frames are 5 s apart; --every 6 keeps one frame per 30 s of sim time.
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter, PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle
import sumolib

ROOT = Path(__file__).resolve().parents[1]
BG, ROAD, MAJOR, FG, MUTED = "#0f1419", "#262e37", "#45505c", "#e6e6e6", "#8a96a3"
C_MOVE, C_KERB, C_LANE, C_AMB, C_OTHER = "#3fa9f5", "#ffb000", "#ff4fd8", "#ff3030", "#7d8590"
POLICY = {"P0": "stop in lane", "P1": "pull over", "P2": "safe harbour"}
ATTACK = {"A1": "zonal link loss", "A2": "fleet backend outage", "A3": "ghost bookings", "A5": "assist flood"}

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("runs", nargs="+")
ap.add_argument("--every", type=int, default=6)
ap.add_argument("--from", dest="t0", type=float, default=1500)
ap.add_argument("--to", dest="t1", type=float, default=4500)
ap.add_argument("--fps", type=int, default=8)
ap.add_argument("--width", type=float, default=5.2, help="inches per panel")
a = ap.parse_args()

runs = []
for r in a.runs:
    r = Path(r)
    cfg = json.load(open(r / "config.json"))
    rep = json.load(open(r / "replay.json"))
    fr = [f for f in rep["frames"] if a.t0 <= f["t"] <= a.t1][:: a.every]
    runs.append((cfg, rep, fr))
n_frames = min(len(x[2]) for x in runs)

net = sumolib.net.readNet(str(ROOT / runs[0][0]["net"]))
minor, major = [], []
for e in net.getEdges():
    if e.getFunction() == "internal":
        continue
    m = (e.getType() or "").split(".")[-1] in ("primary", "trunk", "secondary", "motorway")
    (major if m else minor).append(e.getShape())
(x0, y0), (x1, y1) = net.getBBoxXY()
aspect = (y1 - y0) / (x1 - x0)

k = len(runs)
fig, axes = plt.subplots(1, k, figsize=(a.width * k, a.width * aspect + 0.9), facecolor=BG, squeeze=False)
axes = axes[0]
fig.subplots_adjust(left=0.01, right=0.99, top=0.86, bottom=0.08 if k > 1 else 0.13, wspace=0.03)
arts = []
for ax, (cfg, rep, fr) in zip(axes, runs):
    ax.set_facecolor(BG); ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.axis("off")
    ax.add_collection(LineCollection(minor, colors=ROAD, linewidths=0.4))
    ax.add_collection(LineCollection(major, colors=MAJOR, linewidths=0.9))
    for s in rep["stations"]:
        ax.text(s["x"], s["y"], "+", color=FG, ha="center", va="center", fontsize=11, weight="bold")
    for h in rep["hospitals"]:
        ax.text(h["x"], h["y"], "H", color=FG, ha="center", va="center", fontsize=9, weight="bold")
    rings = []
    for at in rep["attacks"]:
        if "x" in at:
            c = Circle((at["x"], at["y"]), at["radius_m"], fill=False, ls="--", lw=1.4, ec="#5a4a58")
            ax.add_patch(c); rings.append((c, at))
    atk = ", ".join(f'{t["type"]} {ATTACK.get(t["type"], "")}' for t in rep["attacks"]) or "no attack"
    ax.set_title(f'{atk}\npolicy {cfg["policy"]}: {POLICY.get(cfg["policy"], "")}', color=FG, fontsize=10, loc="left")
    bg = ax.scatter([], [], s=2.5, c=C_OTHER, lw=0)
    tx = ax.scatter([], [], s=6, lw=0)
    am = ax.scatter([], [], s=28, c=C_AMB, lw=0.6, edgecolors=BG)
    lab = ax.text(0.01, 0.01, "", transform=ax.transAxes, color=FG, fontsize=9, va="bottom",
                  bbox=dict(fc=BG, ec="none", alpha=0.8, pad=3))
    arts.append((rep, fr, bg, tx, am, lab, rings))
clock = fig.text(0.01, 0.955, "", color=FG, fontsize=12, weight="bold")
handles = [plt.Line2D([], [], ls="", marker="o", ms=5, mfc=c, mec=c, label=l) for c, l in
           [(C_MOVE, "AV moving / idle"), (C_KERB, "AV halted at kerb / harbour"), (C_LANE, "AV halted in lane"),
            (C_AMB, "ambulance"), (C_OTHER, "other traffic (1 in 4)")]]
leg = fig.legend(handles=handles, loc="lower center", ncol=5 if k > 1 else 2, frameon=False, fontsize=8.5, labelcolor=FG,
                 bbox_to_anchor=(0.5, 0.0))


def in_lane(s):
    # state code = first 3 letters of the taxi state + "L" if halted in a traffic lane ("HAL" alone = kerb/harbour)
    return len(s) == 4 and s[3] == "L"


def colour(s):
    if in_lane(s):
        return C_LANE
    if s.startswith("HAL") or s.startswith("HOL"):
        return C_KERB
    return C_MOVE


def update(i):
    t = None
    for rep, fr, bg, tx, am, lab, rings in arts:
        f = fr[i]; t = f["t"]
        bg.set_offsets([p[:2] for p in f["bg"]] or [[x0 - 1e4, y0]])
        tx.set_offsets([p[:2] for p in f["taxi"]] or [[x0 - 1e4, y0]])
        tx.set_color([colour(p[2]) for p in f["taxi"]] or [C_MOVE])
        tx.set_sizes([16 if in_lane(p[2]) else 6 for p in f["taxi"]] or [6])
        am.set_offsets([p[:2] for p in f["amb"]] or [[x0 - 1e4, y0]])
        active = [at["type"] for at in rep["attacks"] if at["start_s"] <= t < at["end_s"]]
        for c, at in rings:
            c.set_edgecolor(C_LANE if at["start_s"] <= t < at["end_s"] else "#5a4a58")
        lane = sum(in_lane(p[2]) for p in f["taxi"])
        lab.set_text(f'attack: {"ACTIVE" if active else "off"}   AVs halted in lane: {lane}   ambulances out: {len(f["amb"])}')
        lab.set_color(C_LANE if active else FG)
    win = [(at["start_s"], at["end_s"]) for r in arts for at in r[0]["attacks"]]
    clock.set_text(f"t = {int(t // 60)} min" + (f"   (attack window {int(min(w[0] for w in win) // 60)}-"
                   f"{int(max(w[1] for w in win) // 60)} min)" if win else ""))
    return []


out = Path(a.out)
out.parent.mkdir(parents=True, exist_ok=True)
for writer, ext, dpi in [(FFMpegWriter(fps=a.fps, bitrate=2500), ".mp4", 130), (PillowWriter(fps=a.fps), ".gif", 75)]:
    path = out.with_suffix(ext)
    with writer.saving(fig, str(path), dpi=dpi):
        for i in range(n_frames):
            update(i)
            writer.grab_frame(facecolor=BG)
    print("wrote", path, round(path.stat().st_size / 1e6, 1), "MB", n_frames, "frames")
