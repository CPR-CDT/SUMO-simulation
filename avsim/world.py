"""Static world: road network, stop-able edges, kerb capacity, stands, EMS sites.

Read once per run from the SUMO network (sumolib); nothing here talks to a running simulation.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field

import numpy as np
import sumolib

from .config import ROOT

# OSM highway types whose kerbside can plausibly take a stopping vehicle.
STOPPABLE_TYPES = ("primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service")


@dataclass
class Site:
    kind: str
    name: str
    x: float
    y: float
    edge: str
    pos: float
    units: int = 0


@dataclass
class World:
    net: sumolib.net.Net
    stop_edges: list[str]                     # edges where a passenger car may stop (pickups, incidents)
    edge_len: dict[str, float]
    edge_xy: dict[str, tuple[float, float]]   # midpoint
    edge_type: dict[str, str]
    lane_for: dict[tuple[str, str], int]      # (edge, vclass) -> kerbside lane index allowing that class
    kerb_cap: dict[str, int]
    stands: list[str]
    stations: list[Site] = field(default_factory=list)
    hospitals: list[Site] = field(default_factory=list)

    def xy(self, edge: str) -> tuple[float, float]:
        return self.edge_xy[edge]

    def edges_within(self, x: float, y: float, r: float) -> list[str]:
        return [e for e in self.stop_edges if math.dist(self.edge_xy[e], (x, y)) <= r]

    def nearest_stop_edge(self, x: float, y: float, candidates: list[str] | None = None) -> str:
        cands = candidates or self.stop_edges
        pts = np.array([self.edge_xy[e] for e in cands])
        return cands[int(np.argmin(((pts - (x, y)) ** 2).sum(1)))]


def _edge_type(e) -> str:
    t = e.getType() or ""
    return t.split(".")[-1] if t else "unknown"


def _largest_scc(net) -> set[str]:
    import networkx as nx
    g = nx.DiGraph()
    for e in net.getEdges():
        if e.getFunction() == "internal" or not e.allows("passenger"):
            continue
        for succ in e.getOutgoing():
            if succ.allows("passenger"):
                g.add_edge(e.getID(), succ.getID())
    return max(nx.strongly_connected_components(g), key=len)


def build(cfg: dict) -> World:
    net = sumolib.net.readNet(str(ROOT / cfg["net"]))
    fl = cfg["fleet"]
    stop_edges, edge_len, edge_xy, edge_type, lane_for, kerb_cap = [], {}, {}, {}, {}, {}
    for e in net.getEdges():
        if e.getFunction() == "internal":
            continue
        eid = e.getID()
        shape = e.getShape()
        mid = shape[len(shape) // 2]
        edge_len[eid] = e.getLength()
        edge_xy[eid] = (float(mid[0]), float(mid[1]))
        edge_type[eid] = _edge_type(e)
        for vc in ("passenger", "emergency"):
            for ln in e.getLanes():  # lane 0 is the kerbside lane in SUMO, also in left-hand networks
                if ln.allows(vc):
                    lane_for[(eid, vc)] = ln.getIndex()
                    break
        if (eid, "passenger") in lane_for and e.getLength() >= 30 and edge_type[eid] in STOPPABLE_TYPES:
            stop_edges.append(eid)
            kerb_cap[eid] = int(e.getLength() / fl["kerb_space_m"] * fl["kerb_fraction"])
    # keep only edges in the largest strongly connected component (reachable to *and* from everywhere)
    scc = _largest_scc(net)
    stop_edges = [e for e in stop_edges if e in scc]
    w = World(net, stop_edges, edge_len, edge_xy, edge_type, lane_for, kerb_cap, [])

    # Taxi stands / safe harbours: k-means-style spread over stoppable edges (deterministic).
    rng = np.random.default_rng(12345)
    pts = np.array([edge_xy[e] for e in stop_edges])
    centres = pts[rng.choice(len(pts), fl["n_stands"], replace=False)]
    for _ in range(15):
        lab = ((pts[:, None, :] - centres[None]) ** 2).sum(2).argmin(1)
        centres = np.array([pts[lab == k].mean(0) if (lab == k).any() else centres[k] for k in range(len(centres))])
    long_edges = [e for e in stop_edges if edge_len[e] >= 60]
    w.stands = sorted({w.nearest_stop_edge(cx, cy, long_edges) for cx, cy in centres})
    for s in w.stands:
        w.kerb_cap[s] = max(w.kerb_cap[s], fl["stand_kerb_spaces"])

    with open(ROOT / "data" / "ems_sites.csv") as f:
        for row in csv.DictReader(f):
            x, y = net.convertLonLat2XY(float(row["lon"]), float(row["lat"]))
            cands = [p for p in net.getNeighboringEdges(x, y, 200) if (p[0].getID(), "emergency") in lane_for
                     and p[0].getLength() >= 20 and p[0].getFunction() != "internal"]
            cands.sort(key=lambda p: p[1])
            e = cands[0][0]
            site = Site(row["kind"], row["name"], x, y, e.getID(), e.getLength() / 2, int(row["units"] or 0))
            (w.stations if row["kind"] == "station" else w.hospitals).append(site)
    return w
