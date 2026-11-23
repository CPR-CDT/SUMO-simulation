"""Study-area map: road network, EMS sites, taxi stands, attack zones. Writes docs/study_area.png."""
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from avsim import config, world
from avsim.attacks import NAMED_CENTRES

warnings.filterwarnings("ignore")
SURF, INK, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
C_STATION, C_HOSP, C_STAND, C_ZONE = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
cfg = config.load()
w = world.build(cfg)
net = w.net
fig, ax = plt.subplots(figsize=(10, 9.2), facecolor=SURF)
ax.set_facecolor(SURF)
for e in net.getEdges():
    if e.getFunction() == "internal":
        continue
    t = w.edge_type.get(e.getID(), "")
    major = t in ("trunk", "primary", "secondary")
    xs, ys = zip(*e.getShape())
    ax.plot(xs, ys, color="#8f9aa5" if major else "#d3d6d9", lw=1.1 if major else 0.4, zorder=1)
for s in w.stands:
    x, y = w.xy(s)
    ax.scatter(x, y, s=22, marker="s", color=C_STAND, zorder=3, edgecolor=SURF, lw=1)
for s in w.stations:
    ax.scatter(s.x, s.y, s=150, marker="P", color=C_STATION, zorder=4, edgecolor=SURF, lw=1.5)
    ax.annotate(s.name.split(" (")[0], (s.x, s.y), xytext=(8, 8), textcoords="offset points", color=INK, fontsize=9)
for h in w.hospitals:
    ax.scatter(h.x, h.y, s=150, marker="H", color=C_HOSP, zorder=4, edgecolor=SURF, lw=1.5)
    ax.annotate(h.name.split(" (")[0], (h.x, h.y), xytext=(8, -14), textcoords="offset points", color=INK, fontsize=9)
for name, r, lab in [("hammersmith_broadway", 800, "A1 zone (800 m)"), ("charing_cross_hosp", 300, "A3 zone (300 m)")]:
    lat, lon = NAMED_CENTRES[name]
    x, y = net.convertLonLat2XY(lon, lat)
    ax.add_patch(Circle((x, y), r, fill=False, ls="--", lw=1.6, color=C_ZONE, zorder=5))
    ax.annotate(lab, (x, y + r), xytext=(0, 6), textcoords="offset points", ha="center", color=INK, fontsize=9)
ax.set_aspect("equal")
ax.set_xticks([]); ax.set_yticks([])
for s in ax.spines.values():
    s.set_visible(False)
(x0, y0), (x1, y1) = net.getBBoxXY()
ax.plot([x0 + 200, x0 + 1200], [y0 + 200, y0 + 200], color=INK, lw=2)
ax.text(x0 + 700, y0 + 260, "1 km", ha="center", color=INK, fontsize=9)
handles = [plt.Line2D([], [], marker=m, ls="", color=c, markersize=9) for m, c in
           [("P", C_STATION), ("H", C_HOSP), ("s", C_STAND)]] + \
          [plt.Line2D([], [], color=C_ZONE, ls="--"), plt.Line2D([], [], color="#8f9aa5", lw=1.4)]
ax.legend(handles, ["Ambulance station", "A&E hospital", "Taxi stand / safe harbour", "Attack zones (default)",
                    "Trunk / primary / secondary road"], loc="upper right", frameon=True, facecolor=SURF,
          edgecolor="#e4e3df", fontsize=9, labelcolor=INK)
ax.set_title("Study area: Hammersmith & Fulham and west Kensington & Chelsea (OSM, 6.4 × 5.8 km)", loc="left",
             color=INK, fontsize=11)
fig.tight_layout()
fig.savefig("docs/study_area.png", dpi=150, facecolor=SURF)
print("wrote docs/study_area.png")
