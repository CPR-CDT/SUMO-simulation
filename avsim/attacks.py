"""Attack injector. Each attack is a dict from the scenario YAML.

Common keys: type, start_s, duration_s. Zonal attacks add centre ([lat, lon] or a site name) and radius_m.

  A1  local V2C loss (cellular jamming / base-station DoS): AVs inside the zone lose the vehicle-cloud link.
  A2  fleet backend outage (ransomware on fleet ops): every AV loses the link; no dispatch; remote assist down.
  A3  ghost-booking swarm: fake trip requests at rate_per_h with origins inside the zone.
  A5  remote-assist flood: fake assist requests at rate_per_h join the operators' queue.

Sources and evidence grades for each attack: params.csv and ledger/cards/attacks-v1.json.
"""
from __future__ import annotations

import math

import numpy as np

from .demand import Request

NAMED_CENTRES = {  # lat, lon
    "hammersmith_broadway": (51.4925, -0.2235),
    "charing_cross_hosp": (51.48692, -0.21962),
    "chelsea_westminster_hosp": (51.48431, -0.18134),
    "fulham_broadway": (51.4802, -0.1955),
    "earls_court": (51.4914, -0.1937),
}


class Attacks:
    def __init__(self, specs: list[dict], world, seed: int):
        self.specs = []
        for a in specs:
            a = dict(a)
            a["end_s"] = a["start_s"] + a["duration_s"]
            if "centre" in a:
                c = a["centre"]
                lat, lon = NAMED_CENTRES[c] if isinstance(c, str) else c
                a["x"], a["y"] = world.net.convertLonLat2XY(lon, lat)
            self.specs.append(a)
        self.world = world
        self.seed = seed

    def _active(self, typ: str, t: float):
        return [a for a in self.specs if a["type"] == typ and a["start_s"] <= t < a["end_s"]]

    def link_ok(self, t: float, x: float, y: float) -> bool:
        if self._active("A2", t):
            return False
        return not any(math.dist((x, y), (a["x"], a["y"])) <= a["radius_m"] for a in self._active("A1", t))

    def dispatch_ok(self, t: float) -> bool:
        return not self._active("A2", t)

    def assist_ok(self, t: float) -> bool:
        return not self._active("A2", t)

    def any_active(self, t: float) -> bool:
        return any(a["start_s"] <= t < a["end_s"] for a in self.specs)

    def window(self):
        if not self.specs:
            return None
        return min(a["start_s"] for a in self.specs), max(a["end_s"] for a in self.specs)

    def ghost_requests(self) -> list[Request]:
        out = []
        for k, a in enumerate(self.specs):
            if a["type"] != "A3":
                continue
            rng = np.random.default_rng([self.seed, 303, k])
            zone = self.world.edges_within(a["x"], a["y"], a["radius_m"])
            t, i = a["start_s"], 0
            while True:
                t += rng.exponential(3600 / a["rate_per_h"])
                if t >= a["end_s"]:
                    break
                o = zone[rng.integers(len(zone))]
                d = self.world.stop_edges[rng.integers(len(self.world.stop_edges))]
                out.append(Request(f"g{k}_{i}", t, o, d, fake=True))
                i += 1
        return out

    def fake_assist_times(self) -> list[float]:
        out = []
        for k, a in enumerate(self.specs):
            if a["type"] != "A5":
                continue
            rng = np.random.default_rng([self.seed, 505, k])
            t = a["start_s"]
            while True:
                t += rng.exponential(3600 / a["rate_per_h"])
                if t >= a["end_s"]:
                    break
                out.append(t)
        return out
