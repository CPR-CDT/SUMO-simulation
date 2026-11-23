"""Exogenous inputs, pre-drawn from independent random streams (common random numbers).

The same seed gives identical background traffic, taxi requests and EMS incidents in every
attack/policy arm, so arm-vs-baseline differences are paired, not seed noise.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

import numpy as np

from .config import ROOT
from .world import World

VTYPES_XML = """<additional>
  <vType id="robotaxi" vClass="passenger" color="0,170,255" length="5.0" accel="2.0" decel="4.0" sigma="0.0"/>
  <vType id="ambulance" vClass="emergency" guiShape="emergency" color="255,40,40" length="6.5" maxSpeed="40"
         speedFactor="{amb_sf}" speedDev="0" accel="2.6" decel="4.5" sigma="0.0" lcOpposite="{amb_opp}">
    {bluelight}
  </vType>
</additional>
"""


def sumo_home() -> str:
    import sumo
    return sumo.SUMO_HOME


def background_routes(cfg: dict) -> str:
    """Background traffic routes for this seed (cached)."""
    bg = cfg["background"]
    cache = ROOT / "data" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"bg_s{cfg['seed']}_p{bg['period_s']}_f{bg['fringe_factor']}_e{cfg['sim']['end_s']}.rou.xml"
    if not out.exists():
        tool = os.path.join(sumo_home(), "tools", "randomTrips.py")
        tmp_trips = out.with_suffix(".trips.xml")
        subprocess.run([sys.executable, tool, "-n", str(ROOT / cfg["net"]), "-o", str(tmp_trips), "-r", str(out),
                        "-b", "0", "-e", str(cfg["sim"]["end_s"]), "-p", str(bg["period_s"]),
                        "--fringe-factor", str(bg["fringe_factor"]), "--vehicle-class", "passenger",
                        "--validate", "--seed", str(cfg["seed"]), "--prefix", "bg"],
                       check=True, capture_output=True)
    return str(out)


def vtypes_file(cfg: dict, run_dir) -> str:
    p = run_dir / "vtypes.add.xml"
    e = cfg["ems"]
    bl = '<param key="has.bluelight.device" value="true"/>' if e.get("bluelight", True) else ""
    p.write_text(VTYPES_XML.format(amb_sf=e["amb_speed_factor"], amb_opp=e.get("lc_opposite", 1), bluelight=bl))
    return str(p)


@dataclass
class Request:
    rid: str
    t: float
    origin: str
    dest: str
    fake: bool = False


@dataclass
class Incident:
    iid: str
    t: float
    edge: str
    u_convey: float = 0.0   # pre-drawn so the convey decision is identical in every arm


def taxi_requests(cfg: dict, w: World) -> list[Request]:
    rng = np.random.default_rng([cfg["seed"], 101])
    rate = cfg["fleet"]["requests_per_h"] / 3600
    t, out, i = 0.0, [], 0
    while True:
        t += rng.exponential(1 / rate)
        if t >= cfg["sim"]["end_s"]:
            break
        o, d = rng.choice(len(w.stop_edges), 2, replace=False)
        out.append(Request(f"q{i}", t, w.stop_edges[o], w.stop_edges[d]))
        i += 1
    return out


def ems_incidents(cfg: dict, w: World) -> list[Incident]:
    rng = np.random.default_rng([cfg["seed"], 202])
    rate = cfg["ems"]["incidents_per_h"] / 3600
    cands = [e for e in w.stop_edges if (e, "emergency") in w.lane_for]
    weights = np.array([w.edge_len[e] for e in cands])
    weights /= weights.sum()
    rng_c = np.random.default_rng([cfg["seed"], 203])
    t, out, i = 0.0, [], 0
    while True:
        t += rng.exponential(1 / rate)
        if t >= cfg["sim"]["end_s"]:
            break
        out.append(Incident(f"inc{i}", t, cands[rng.choice(len(cands), p=weights)], float(rng_c.random())))
        i += 1
    return out
