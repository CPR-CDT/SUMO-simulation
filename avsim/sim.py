"""Co-simulation runner: SUMO (physical layer) <-> fleet management system, remote-assist centre,
coordinator-free contingency policy, and EMS dispatch, coupled every simulated second through TraCI/libsumo.

Integration points (each is a two-way coupling, see README "Integration"):
  link loss (cyber)          -> halts of AVs on the road (physical)          [policy P0/P1/P2 decides where]
  halted AVs (physical)      -> lane blockage -> congestion -> ambulance delay (EMS)
  congestion (physical)      -> 'stuck' AVs ask for remote assist (cyber queue) -> longer holds (physical)
  assist queue (cyber)       -> recovery time of every halted AV (physical)
  ghost bookings (cyber)     -> AVs converge and dwell at kerb or in lane (physical)
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import config as C
from .attacks import Attacks
from .demand import background_routes, ems_incidents, ems_probes, taxi_requests, vtypes_file
from .world import World, build

if os.environ.get("AVSIM_TRACI") == "1":
    import traci as T  # slower, but allows sumo-gui
else:
    import libsumo as T

BIG = 1e7
MOVING_STATES = ("TO_STAND", "TO_PICKUP", "TO_DROPOFF", "TO_HARBOUR")


@dataclass
class Taxi:
    vid: str
    state: str = "PARKED_IDLE"
    req: object = None
    target: tuple | None = None          # (edge, kind) of the stop it is heading to / sitting at
    kerb_edge: str | None = None         # kerb space currently reserved
    dwell_until: float = 0.0
    link: bool = True
    link_lost_t: float | None = None
    halt: dict | None = None             # open halt record
    resume_state: str | None = None
    in_queue: bool = False
    stuck_flagged: bool = False
    idx: int = 0
    moving_s: float = 0.0                # moving, connected seconds (clock for routine assist events)
    next_hold_at: float = 0.0
    n_hold: int = 0
    n_stuck: int = 0
    n_assist: int = 0
    dwell_rec: dict | None = None        # open record of a pickup/drop-off dwell that stands in a lane


@dataclass
class Amb:
    aid: str
    station: object
    state: str = "TO_SCENE"
    inc: object = None
    t_state: float = 0.0
    record: dict = field(default_factory=dict)
    inserted: bool = False
    last_edge: str | None = None
    n_reinsert: int = 0


class Run:
    def __init__(self, cfg: dict, out_dir: Path):
        self.cfg = cfg
        self.out = out_dir
        self.out.mkdir(parents=True, exist_ok=True)
        self.w: World = build(cfg)
        self.att = Attacks(cfg["attacks"], self.w, cfg["seed"])
        self.seed = cfg["seed"]
        fl = cfg["fleet"]
        reqs = taxi_requests(cfg, self.w) + self.att.ghost_requests()
        reqs.sort(key=lambda r: r.t)
        self.req_feed = deque(reqs)
        self.pending: list = []
        self.req_log: dict[str, dict] = {}
        self.inc_feed = deque(ems_incidents(cfg, self.w))
        self.inc_queue: list = []
        self.probe_feed = deque(ems_probes(cfg, self.w))
        self.probes: dict[str, dict] = {}       # live probe id -> record
        self.probe_log: list[dict] = []
        self.fake_assist = deque(sorted(self.att.fake_assist_times()))
        self.n_fake = 0
        self.kerb_used: Counter = Counter()
        self.taxis: dict[str, Taxi] = {}
        self.ambs: dict[str, Amb] = {}
        self.free_units = {s.name: s.units for s in self.w.stations}
        self.halts: list[dict] = []
        self.incidents: list[dict] = []
        self.ts: list[dict] = []
        self.anomalies: Counter = Counter()
        self.teleports: Counter = Counter()
        # assist centre
        self.queue: deque = deque()           # (t_req, kind, vid)
        self.ops_busy: list[tuple[float, str, str | None]] = []  # (t_done, kind, vid)
        self.assist_waits: list[dict] = []
        self.replay: list = []
        self.t = 0.0

    def _gen(self, tag: int, idx: int, k: int):
        """Common random numbers: draw k of entity idx for purpose tag is the same in every arm."""
        return np.random.default_rng([self.seed, tag, idx, k])

    def _service_time(self, mean: float, tag: int, idx: int, k: int) -> float:
        a = self.cfg["assist"]
        sig = math.sqrt(math.log(1 + a["service_cv"] ** 2))
        return float(self._gen(tag, idx, k).lognormal(math.log(mean) - sig * sig / 2, sig))

    def _next_hold_gap(self, tx) -> float:
        rate = self.cfg["fleet"]["base_assist_per_veh_h"]
        return float(self._gen(701, tx.idx, tx.n_hold).exponential(3600 / rate)) if rate > 0 else float("inf")

    # ------------------------------------------------------------------ SUMO plumbing
    def start(self):
        c = self.cfg
        edgedata = self.out / "edgedata.add.xml"
        edgedata.write_text(
            f'<additional><edgeData id="bg" period="{c["sim"]["meandata_period_s"]}" file="edgedata.xml" '
            f'vTypes="bg_passenger" excludeEmpty="true"/></additional>')
        import shutil, sys
        sumo_bin = shutil.which("sumo") or str(Path(sys.executable).parent / "sumo")
        cmd = [sumo_bin, "-n", str(C.ROOT / c["net"]), "-r", background_routes(c),
               "-a", f"{vtypes_file(c, self.out)},{edgedata}",
               "--seed", str(c["seed"] + c["sim"].get("sumo_seed_offset", 0)), "--step-length", str(c["sim"]["step_s"]),
               "--time-to-teleport", str(c["sim"]["time_to_teleport_s"]),
               "--no-step-log", "true", "--no-warnings", "true",
               "--statistic-output", str(self.out / "stats.xml"),
               "--lanechange.duration", "2", "--default.action-step-length", "1",
               "--collision.action", c["sim"].get("collision_action", "warn")]
        T.start(cmd)
        for i in range(self.cfg["fleet"]["n_taxis"]):
            stand = self.w.stands[i % len(self.w.stands)]
            vid = f"taxi{i}"
            T.route.add(f"r_{vid}", [stand])
            pos = min(10 + 7 * (i // len(self.w.stands)), self.w.edge_len[stand] - 2)
            T.vehicle.add(vid, f"r_{vid}", typeID="robotaxi", depart="0", departPos=str(pos), departSpeed="0")
            self.taxis[vid] = Taxi(vid, idx=i)
            self.taxis[vid].next_hold_at = self._next_hold_gap(self.taxis[vid])
            self._place_stop(self.taxis[vid], stand, pos + 1, "kerb", force=True)

    def _lane(self, edge: str, vc: str = "passenger") -> int:
        return self.w.lane_for.get((edge, vc), 0)

    def _place_stop(self, tx: Taxi, edge: str, pos: float, kind: str, force: bool = False) -> bool:
        """Reserve kerb if kind == 'kerb' (falls back to an in-lane stop when the kerb is full)."""
        if kind == "kerb" and not force and self.kerb_used[edge] >= self.w.kerb_cap.get(edge, 0):
            kind = "lane"
        lane = self._lane(edge)
        pos = max(1.0, min(pos, self.w.edge_len[edge] - 1.0))
        try:
            T.vehicle.setStop(tx.vid, edge, pos, lane, BIG, 1 if kind == "kerb" else 0)
        except T.TraCIException:
            self.anomalies["setStop_failed"] += 1
            return False
        if kind == "kerb":
            self.kerb_used[edge] += 1
            tx.kerb_edge = edge
        tx.target = (edge, kind)
        return True

    def _release_kerb(self, tx: Taxi):
        if tx.kerb_edge:
            self.kerb_used[tx.kerb_edge] -= 1
            tx.kerb_edge = None

    def _clear_stops(self, vid: str):
        try:
            n = len(T.vehicle.getStops(vid, 0))
            stopped = T.vehicle.isStopped(vid)
            for i in reversed(range(1 if stopped else 0, n)):
                T.vehicle.replaceStop(vid, i, "")
        except T.TraCIException:
            self.anomalies["clear_stops_failed"] += 1

    def _go(self, tx: Taxi, edge: str, kind: str = "kerb") -> bool:
        """Send a taxi to a stop on `edge`, ending its current stop if any."""
        vid = tx.vid
        self._close_dwell(tx)
        pos = self.w.edge_len[edge] * 0.6
        if T.vehicle.getRoadID(vid) == edge and T.vehicle.getLanePosition(vid) > pos - 20:
            # stop would be behind us: caller picks another target
            self.anomalies["target_behind"] += 1
            return False
        was_stopped = T.vehicle.isStopped(vid)
        try:
            T.simulation.findRoute(T.vehicle.getRoadID(vid) if not T.vehicle.getRoadID(vid).startswith(":")
                                   else T.vehicle.getRoute(vid)[T.vehicle.getRouteIndex(vid)], edge, "robotaxi")
        except T.TraCIException:
            self.anomalies["no_route"] += 1
            return False
        self._clear_stops(vid)
        try:
            T.vehicle.changeTarget(vid, edge)
        except T.TraCIException:
            self.anomalies["no_route"] += 1
            return False
        self._release_kerb(tx)
        if not self._place_stop(tx, edge, pos, kind):
            return False
        if was_stopped:
            try:
                T.vehicle.resume(vid)
            except T.TraCIException:
                self.anomalies["resume_failed"] += 1
        return True

    def _halt_here(self, tx: Taxi, kind: str) -> str:
        """Bring a moving taxi to a stop ahead (in lane, or at the kerb if kind == 'kerb' and space exists)."""
        vid = tx.vid
        if T.vehicle.isStopped(vid):
            # already sitting at a stop (pickup/dropoff/stand): it stays where it is
            return tx.target[1] if tx.target else "lane"
        self._clear_stops(vid)
        v = T.vehicle.getSpeed(vid)
        need = v * v / (2 * 3.0) + 3.0  # comfortable braking at 3 m/s^2
        if kind == "kerb":
            need += 30.0  # room to move across to the kerbside lane
        route, ri = T.vehicle.getRoute(vid), T.vehicle.getRouteIndex(vid)
        road = T.vehicle.getRoadID(vid)
        cand, left = [], need
        if not road.startswith(":") and road in self.w.edge_len:
            lp = T.vehicle.getLanePosition(vid)
            cand.append((road, lp + need))
            left = need - (self.w.edge_len[road] - lp)
        for e in route[ri + 1: ri + 4]:
            if e in self.w.edge_len:
                cand.append((e, max(2.0, left)))
                left -= self.w.edge_len[e]
        for e, p in cand:
            if e not in self.w.edge_len or p > self.w.edge_len[e] - 1:
                continue
            k = kind if (kind == "kerb" and e in self.w.kerb_cap) else "lane"
            lane = self._lane(e) if k == "kerb" else (T.vehicle.getLaneIndex(vid) if e == road else self._lane(e))
            if k == "kerb" and self.kerb_used[e] >= self.w.kerb_cap[e]:
                k, lane = "lane", (T.vehicle.getLaneIndex(vid) if e == road else self._lane(e))
            try:
                T.vehicle.setStop(vid, e, p, lane, BIG, 1 if k == "kerb" else 0)
            except T.TraCIException:
                continue
            self._release_kerb(tx)
            if k == "kerb":
                self.kerb_used[e] += 1
                tx.kerb_edge = e
            tx.target = (e, k)
            return k
        T.vehicle.setSpeed(vid, 0.0)  # last resort: emergency stop where it is
        self.anomalies["halt_setspeed_fallback"] += 1
        tx.target = (road, "lane")
        return "lane"

    # ------------------------------------------------------------------ fleet: halts and recovery
    def _open_halt(self, tx: Taxi, cause: str, kind: str):
        tx.resume_state = tx.state
        tx.state = "HALTED"
        tx.halt = {"vid": tx.vid, "cause": cause, "kind": kind, "start": self.t, "end": None,
                   "with_passenger": tx.resume_state in ("TO_DROPOFF", "AT_DROPOFF"),
                   "edge": tx.target[0] if tx.target else None}

    def _close_dwell(self, tx: Taxi):
        if tx.dwell_rec:
            tx.dwell_rec["end"] = self.t
            self.halts.append(tx.dwell_rec)
            tx.dwell_rec = None

    def _close_halt(self, tx: Taxi):
        if tx.halt:
            tx.halt["end"] = self.t
            self.halts.append(tx.halt)
            tx.halt = None

    def _on_link_lost(self, tx: Taxi):
        pol = self.cfg["policy"]
        if tx.state in ("HALTED", "HOLD_ASSIST"):
            return
        if tx.state == "PARKED_IDLE":
            return  # parked at a stand: simply not dispatchable while offline
        if pol == "P2":
            near = self._nearest_free_stand(tx)
            if near:
                tx.resume_state = tx.state
                self._go(tx, near, "kerb")
                tx.state = "TO_HARBOUR"
                tx.halt = {"vid": tx.vid, "cause": "link", "kind": "harbour", "start": self.t, "end": None,
                           "with_passenger": tx.resume_state in ("TO_DROPOFF", "AT_DROPOFF"), "edge": near}
                return
            pol = "P1"
        kind = self._halt_here(tx, "kerb" if pol == "P1" else "lane")
        self._open_halt(tx, "link", kind)

    def _nearest_free_stand(self, tx: Taxi) -> str | None:
        x, y = T.vehicle.getPosition(tx.vid)
        best, bd = None, self.cfg["fleet"]["harbour_max_km"] * 1000
        for s in self.w.stands:
            d = math.dist((x, y), self.w.xy(s))
            if d < bd and self.kerb_used[s] < self.w.kerb_cap[s]:
                best, bd = s, d
        return best

    def _recover(self, tx: Taxi):
        """Operator has cleared the vehicle: close the halt and continue its plan."""
        tx.in_queue = False
        self._close_halt(tx)
        try:
            T.vehicle.setSpeed(tx.vid, -1)
        except T.TraCIException:
            pass
        prev = tx.resume_state
        tx.resume_state = None
        if prev in ("TO_DROPOFF", "AT_DROPOFF") and tx.req is not None:
            tx.state = "TO_DROPOFF" if self._go(tx, tx.req.dest, "kerb") else self._to_stand(tx)
        elif prev in ("TO_PICKUP", "AT_PICKUP") and tx.req is not None and self._req_alive(tx.req):
            tx.state = "TO_PICKUP" if self._go(tx, tx.req.origin, "kerb") else self._to_stand(tx)
        else:
            if tx.req is not None:
                self._req_drop(tx.req, "cancelled_after_halt")
            tx.req = None
            self._to_stand(tx)

    def _to_stand(self, tx: Taxi) -> str:
        x, y = T.vehicle.getPosition(tx.vid)
        cur = T.vehicle.getRoadID(tx.vid)
        order = sorted(self.w.stands, key=lambda s: math.dist((x, y), self.w.xy(s)))
        for s in order[:4]:
            if s != cur and self._go(tx, s, "kerb"):
                tx.state = "TO_STAND"
                return tx.state
        self.anomalies["no_stand_reachable"] += 1
        tx.state = "TO_STAND"
        return tx.state

    # ------------------------------------------------------------------ requests / dispatch
    def _req_alive(self, r) -> bool:
        return self.t - r.t < 1200  # rider cancels after 20 min without pickup (assumption)

    def _req_drop(self, r, status: str):
        self.req_log[r.rid]["status"] = status
        self.req_log[r.rid]["end_t"] = self.t

    def _dispatch(self):
        if not self.att.dispatch_ok(self.t):
            return
        still = []
        idle = [tx for tx in self.taxis.values() if tx.state in ("PARKED_IDLE", "TO_STAND") and tx.link
                and tx.vid in self.live]
        pos = {tx.vid: T.vehicle.getPosition(tx.vid) for tx in idle}
        for r in self.pending:
            if not self._req_alive(r):
                self._req_drop(r, "timeout")
                continue
            ox, oy = self.w.xy(r.origin)
            best, bd = None, self.cfg["fleet"]["max_pickup_km"] * 1000
            for tx in idle:
                d = math.dist(pos[tx.vid], (ox, oy))
                if d < bd:
                    best, bd = tx, d
            if best and self._go(best, r.origin, "kerb"):
                best.state, best.req = "TO_PICKUP", r
                idle.remove(best)
                self.req_log[r.rid].update(status="assigned", assigned_t=self.t, taxi=best.vid)
            else:
                still.append(r)
        self.pending = still

    # ------------------------------------------------------------------ assist centre
    def _assist_step(self):
        a = self.cfg["assist"]
        done = [b for b in self.ops_busy if b[0] <= self.t]
        self.ops_busy = [b for b in self.ops_busy if b[0] > self.t]
        for _, kind, vid in done:
            if kind != "fake":
                tx = self.taxis[vid]
                if tx.link and tx.vid in self.live:
                    self._recover(tx)
                else:
                    tx.in_queue = False  # lost link again before help arrived; it will re-request
        while self.fake_assist and self.fake_assist[0] <= self.t:
            self.n_fake += 1
            self.queue.append((self.fake_assist.popleft(), "fake", f"fake{self.n_fake}"))
        if not self.att.assist_ok(self.t):
            return
        while self.queue and len(self.ops_busy) < a["operators"]:
            t_req, kind, vid = self.queue.popleft()
            if kind == "fake":
                dur = self._service_time(a["fake_service_mean_s"], 704, 0, int(vid[4:]))
            else:
                tx = self.taxis[vid]
                dur = self._service_time(a["service_mean_s"], 703, tx.idx, tx.n_assist)
                tx.n_assist += 1
            self.ops_busy.append((self.t + dur, kind, vid))
            self.assist_waits.append({"t_req": t_req, "t_start": self.t, "wait": self.t - t_req, "kind": kind,
                                      "vid": vid})

    def _request_assist(self, tx: Taxi, kind: str):
        if not tx.in_queue:
            tx.in_queue = True
            self.queue.append((self.t, kind, tx.vid))

    # ------------------------------------------------------------------ per-step fleet update
    def _fleet_step(self):
        fl = self.cfg["fleet"]
        dt = self.cfg["sim"]["step_s"]
        check_stuck = int(self.t) % 10 == 0
        for tx in self.taxis.values():
            vid = tx.vid
            if vid not in self.live:
                continue
            x, y = T.vehicle.getPosition(vid)
            ok = self.att.link_ok(self.t, x, y)
            # heartbeat: the vehicle reacts only after the link has been down for the timeout
            if not ok:
                tx.link_lost_t = tx.link_lost_t if tx.link_lost_t is not None else self.t
                if tx.link and self.t - tx.link_lost_t >= fl["heartbeat_timeout_s"]:
                    tx.link = False
                    self._on_link_lost(tx)
            else:
                tx.link_lost_t = None
                if not tx.link:
                    tx.link = True
            st = tx.state
            stopped = T.vehicle.isStopped(vid)
            # link restored: halted vehicles ask the assist centre to clear them
            if (st == "HALTED" and tx.link and tx.halt and tx.halt["cause"] == "link"
                    and fl.get("auto_resume_on_restore", False)):
                self._recover(tx)   # sensitivity arm: no operator needed once the link is back
                continue
            if st in ("HALTED", "HOLD_ASSIST") and tx.link and tx.halt and not tx.in_queue:
                self._request_assist(tx, "recovery" if tx.halt["cause"] == "link" else "hold")
                continue
            if st == "TO_HARBOUR" and stopped:
                tx.state = "HALTED"
                continue
            if st in ("HALTED", "HOLD_ASSIST"):
                continue
            # arrivals at stops
            if st in ("TO_PICKUP", "TO_DROPOFF", "TO_STAND") and stopped and tx.target \
                    and T.vehicle.getRoadID(vid) == tx.target[0]:
                if st in ("TO_PICKUP", "TO_DROPOFF") and tx.target[1] == "lane":
                    tx.dwell_rec = {"vid": vid, "cause": "dwell_fake" if tx.req.fake else "dwell", "kind": "lane",
                                    "start": self.t, "end": None, "with_passenger": st == "TO_DROPOFF",
                                    "edge": tx.target[0]}
                if st == "TO_PICKUP":
                    r = tx.req
                    tx.state = "AT_PICKUP"
                    tx.dwell_until = self.t + (1e9 if r.fake else fl["pickup_dwell_s"])
                    self.req_log[r.rid]["arrive_pickup_t"] = self.t
                    self.req_log[r.rid]["pickup_kind"] = tx.target[1]
                elif st == "TO_DROPOFF":
                    tx.state = "AT_DROPOFF"
                    tx.dwell_until = self.t + fl["dropoff_dwell_s"]
                elif st == "TO_STAND":
                    tx.state = "PARKED_IDLE"
                    if tx.target[1] == "lane":  # stand kerb was full: look for another one
                        self._to_stand(tx)
                continue
            if st == "AT_PICKUP":
                r = tx.req
                if r.fake and self.t - self.req_log[r.rid]["arrive_pickup_t"] >= fl.get("no_show_wait_s", 300):
                    self._req_drop(r, "no_show")
                    tx.req = None
                    self._to_stand(tx)
                elif not r.fake and self.t >= tx.dwell_until:
                    self.req_log[r.rid]["pickup_t"] = self.t
                    tx.state = "TO_DROPOFF" if self._go(tx, r.dest, "kerb") else "AT_PICKUP"
                continue
            if st == "AT_DROPOFF" and self.t >= tx.dwell_until:
                self.req_log[tx.req.rid].update(status="completed", end_t=self.t)
                tx.req = None
                self._to_stand(tx)
                continue
            # routine and congestion-triggered remote-assist holds (moving, connected vehicles)
            if st in MOVING_STATES and st != "TO_HARBOUR" and tx.link and not stopped:
                tx.moving_s += dt
                hit = False
                if tx.moving_s >= tx.next_hold_at:
                    hit = True
                    tx.n_hold += 1
                    tx.next_hold_at = tx.moving_s + self._next_hold_gap(tx)
                if check_stuck:
                    wt = T.vehicle.getWaitingTime(vid)
                    if wt > fl["stuck_wait_s"] and not tx.stuck_flagged:
                        tx.stuck_flagged = True
                        u = self._gen(702, tx.idx, tx.n_stuck).random()
                        tx.n_stuck += 1
                        hit = hit or u < fl["p_stuck_assist"]
                    elif wt == 0:
                        tx.stuck_flagged = False
                if hit:
                    kind = self._halt_here(tx, "lane")
                    self._open_halt(tx, "assist_hold", kind)
                    tx.state = "HOLD_ASSIST"
                    self._request_assist(tx, "hold")

    # ------------------------------------------------------------------ EMS
    def _ems_step(self):
        e = self.cfg["ems"]
        while self.inc_feed and self.inc_feed[0].t + e["call_to_dispatch_s"] <= self.t:
            self.inc_queue.append(self.inc_feed.popleft())
        still = []
        for inc in self.inc_queue:
            ix, iy = self.w.xy(inc.edge)
            free = [s for s in self.w.stations if self.free_units[s.name] > 0]
            if not free:
                still.append(inc)
                continue
            st = min(free, key=lambda s: math.dist((s.x, s.y), (ix, iy)))
            if self._launch_amb(st, inc):
                self.free_units[st.name] -= 1
            else:
                still.append(inc)
        self.inc_queue = still
        for a in list(self.ambs.values()):
            try:
                self._amb_update(a)
            except T.TraCIException:
                # ambulance removed by SUMO (e.g. teleport/collision): count it, free the unit
                self.anomalies["amb_lost"] += 1
                self.ambs.pop(a.aid, None)
                self.free_units[a.station.name] += 1

    def _launch_amb(self, st, inc) -> bool:
        aid = f"amb_{inc.iid}"
        try:
            ff = T.simulation.findRoute(st.edge, inc.edge, "ambulance")
            T.route.add(f"r_{aid}", list(ff.edges))
            T.vehicle.add(aid, f"r_{aid}", typeID="ambulance", depart="now", departPos=str(st.pos),
                          departSpeed="0", departLane="best")
            T.vehicle.setStop(aid, inc.edge, self.w.edge_len[inc.edge] / 2, self._lane(inc.edge, "emergency"), BIG, 0)
        except T.TraCIException:
            self.anomalies["amb_launch_failed"] += 1
            return False
        a = Amb(aid, st, "TO_SCENE", inc, self.t)
        a.record = {"iid": inc.iid, "t_call": inc.t, "t_dispatch": self.t, "station": st.name,
                    "edge": inc.edge, "route_m": ff.length, "route_est_s": ff.travelTime, "t_arrive": None,
                    "blocked_s": 0.0}
        self.ambs[aid] = a
        return True

    def _amb_update(self, a: Amb):
        e = self.cfg["ems"]
        if a.aid not in self.live:
            if a.inserted and a.state == "TO_SCENE" and a.last_edge and a.n_reinsert < 3:
                # SUMO teleported the ambulance past its stop and removed it at route end. Put it back where it was
                # last seen so the call is answered late, not never (the teleport still skips part of the jam).
                if self._reinsert_amb(a):
                    return
            if a.inserted:  # removed by SUMO (route end after a teleport, collision): free the unit
                self.anomalies["amb_lost"] += 1
                self.ambs.pop(a.aid, None)
                self.free_units[a.station.name] += 1
            return
        if not a.inserted:
            a.inserted = True
            a.record["t_insert"] = self.t
        road = T.vehicle.getRoadID(a.aid)
        if road and not road.startswith(":"):
            a.last_edge = road
        stopped = T.vehicle.isStopped(a.aid)
        if a.state == "TO_SCENE":
            if T.vehicle.getSpeed(a.aid) < 1.0 and not stopped:
                a.record["blocked_s"] += self.cfg["sim"]["step_s"]
            if stopped and T.vehicle.getRoadID(a.aid) == a.inc.edge:
                a.record["t_arrive"] = self.t
                a.record["response_s"] = self.t - a.inc.t
                self.incidents.append(a.record)
                a.state, a.t_state = "ON_SCENE", self.t
        elif a.state == "ON_SCENE" and self.t - a.t_state >= e["on_scene_s"]:
            convey = a.inc.u_convey < e["p_convey"]
            if convey:
                ix, iy = self.w.xy(a.inc.edge)
                h = min(self.w.hospitals, key=lambda s: math.dist((s.x, s.y), (ix, iy)))
                self._amb_go(a, h.edge, h.pos)
                a.state = "TO_HOSP"
            else:
                self._amb_go(a, a.station.edge, a.station.pos)
                a.state = "RETURN"
            a.t_state = self.t
        elif a.state == "TO_HOSP" and stopped and T.vehicle.getRoadID(a.aid) != a.inc.edge:
            a.state, a.t_state = "HANDOVER", self.t
        elif a.state == "HANDOVER" and self.t - a.t_state >= e["handover_s"]:
            self._amb_go(a, a.station.edge, a.station.pos)
            a.state, a.t_state = "RETURN", self.t
        elif a.state == "RETURN" and stopped and T.vehicle.getRoadID(a.aid) == a.station.edge:
            T.vehicle.remove(a.aid)
            self.free_units[a.station.name] += 1
            a.state = "DONE"
            del self.ambs[a.aid]

    def _reinsert_amb(self, a: Amb) -> bool:
        old = a.aid
        new = f"{old.split('#')[0]}#r{a.n_reinsert + 1}"
        try:
            rt = T.simulation.findRoute(a.last_edge, a.inc.edge, "ambulance")
            if not rt.edges:
                return False
            T.route.add(f"r_{new}", list(rt.edges))
            T.vehicle.add(new, f"r_{new}", typeID="ambulance", depart="now", departSpeed="0", departLane="best")
            T.vehicle.setStop(new, a.inc.edge, self.w.edge_len[a.inc.edge] / 2, self._lane(a.inc.edge, "emergency"),
                              BIG, 0)
        except T.TraCIException:
            self.anomalies["amb_reinsert_failed"] += 1
            return False
        a.n_reinsert += 1
        a.record["n_reinsert"] = a.n_reinsert
        a.inserted = False
        self.ambs.pop(old, None)
        a.aid = new
        self.ambs[new] = a
        self.anomalies["amb_reinserted"] += 1
        return True

    def _probe_step(self):
        e = self.cfg["ems"]
        while self.probe_feed and self.probe_feed[0].t + e["call_to_dispatch_s"] <= self.t:
            p = self.probe_feed.popleft()
            ix, iy = self.w.xy(p.edge)
            st = min(self.w.stations, key=lambda s: math.dist((s.x, s.y), (ix, iy)))
            try:
                rt = T.simulation.findRoute(st.edge, p.edge, "ambulance")
                if not rt.edges or len(rt.edges) < 2:
                    continue
                T.route.add(f"r_{p.iid}", list(rt.edges))
                T.vehicle.add(p.iid, f"r_{p.iid}", typeID="ambulance", depart="now", departPos=str(st.pos),
                              departSpeed="0", departLane="best", arrivalPos="max")
            except T.TraCIException:
                self.anomalies["probe_launch_failed"] += 1
                continue
            self.probes[p.iid] = {"pid": p.iid, "t_call": p.t, "t_dispatch": self.t, "route_m": rt.length,
                                  "route_est_s": rt.travelTime, "teleported": False, "slow_s": 0.0}

    def _amb_go(self, a: Amb, edge: str, pos: float):
        try:
            self._clear_stops(a.aid)
            T.vehicle.changeTarget(a.aid, edge)
            T.vehicle.setStop(a.aid, edge, max(1.0, min(pos, self.w.edge_len[edge] - 1)),
                              self._lane(edge, "emergency"), BIG, 0)
            T.vehicle.resume(a.aid)
        except T.TraCIException:
            self.anomalies["amb_go_failed"] += 1

    # ------------------------------------------------------------------ main loop
    def run(self) -> dict:
        wall0 = time.time()
        self.start()
        c = self.cfg
        end = c["sim"]["end_s"]
        rep_every = c["replay"]["every_s"] if c["replay"]["record"] else None
        while self.t < end:
            T.simulationStep()
            self.t = T.simulation.getTime()
            self.live = set(T.vehicle.getIDList())
            for vid in T.simulation.getStartingTeleportIDList():
                if vid in self.probes:
                    self.probes[vid]["teleported"] = True
                self.teleports["taxi" if vid.startswith("taxi") else "amb" if vid.startswith("amb") else "bg"] += 1
            for vid in T.simulation.getArrivedIDList():
                if vid in self.probes:
                    rec = self.probes.pop(vid)
                    rec["t_arrive"] = self.t
                    rec["travel_s"] = self.t - rec["t_dispatch"]
                    self.probe_log.append(rec)
                if vid.startswith("taxi"):
                    self.anomalies["taxi_left_network"] += 1
                    self._release_kerb(self.taxis[vid])
            while self.req_feed and self.req_feed[0].t <= self.t:
                r = self.req_feed.popleft()
                self.req_log[r.rid] = {"rid": r.rid, "t": r.t, "fake": r.fake, "status": "pending",
                                       "origin": r.origin}
                if self.att.dispatch_ok(self.t):
                    self.pending.append(r)
                else:
                    self._req_drop(r, "app_down")
            self._fleet_step()
            if int(self.t) % c["fleet"]["dispatch_every_s"] == 0:
                self._dispatch()
            self._assist_step()
            self._ems_step()
            self._probe_step()
            if int(self.t) % 30 == 0:
                self._sample_ts()
            if rep_every and int(self.t) % rep_every == 0:
                self._sample_replay()
        for tx in self.taxis.values():   # close halts still open at the end (censored)
            if tx.halt:
                tx.halt["censored"] = True
                self._close_halt(tx)
            self._close_dwell(tx)
        for rec in self.probes.values():     # probes still driving at the end: censored
            rec.update(t_arrive=None, travel_s=self.t - rec["t_dispatch"], censored=True)
            self.probe_log.append(rec)
        for t_req, kind, vid in self.queue:   # requests never served: wait censored at the end
            self.assist_waits.append({"t_req": t_req, "t_start": None, "wait": self.t - t_req, "kind": kind,
                                      "vid": vid, "censored": True})
        T.close()
        return self._write(time.time() - wall0)

    def _sample_ts(self):
        states = Counter(tx.state for tx in self.taxis.values())
        lane_halted = sum(1 for tx in self.taxis.values() if tx.halt and tx.halt["kind"] == "lane")
        # fresh ID list: vehicles removed earlier in this step (ambulances back at station) are no longer known
        speeds = [v for v in (T.vehicle.getSpeed(v) for v in T.vehicle.getIDList()) if v >= 0]
        self.ts.append({"t": self.t, "n_veh": len(self.live), "mean_speed": float(np.mean(speeds)) if speeds else 0,
                        "lane_halted": lane_halted, "halted_total": states["HALTED"] + states["HOLD_ASSIST"],
                        "assist_queue": len([q for q in self.queue if q[1] != "fake"]),
                        "assist_queue_fake": len([q for q in self.queue if q[1] == "fake"]),
                        "pending_requests": len(self.pending), "amb_active": len(self.ambs),
                        "inc_waiting_unit": len(self.inc_queue),
                        "pending_insert": len(T.simulation.getPendingVehicles()),
                        **{f"st_{k}": v for k, v in states.items()}})

    def _sample_replay(self):
        frame = {"t": self.t, "taxi": [], "amb": [], "bg": []}
        for tx in self.taxis.values():
            if tx.vid in self.live:
                x, y = T.vehicle.getPosition(tx.vid)
                frame["taxi"].append([round(x), round(y), tx.state[:3] + ("L" if tx.halt and tx.halt["kind"] == "lane" else "")])
        now_live = set(T.vehicle.getIDList())
        for aid in self.ambs:
            if aid in now_live:
                x, y = T.vehicle.getPosition(aid)
                frame["amb"].append([round(x), round(y)])
        for vid in list(self.live)[::4]:
            if vid.startswith("bg"):
                x, y = T.vehicle.getPosition(vid)
                frame["bg"].append([round(x), round(y)])
        self.replay.append(frame)

    def _write(self, wall: float) -> dict:
        from .metrics import summarise
        with open(self.out / "config.json", "w") as f:
            json.dump(self.cfg, f, indent=1)
        for name, rows in [("incidents", self.incidents), ("halts", self.halts), ("ts", self.ts),
                           ("requests", list(self.req_log.values())), ("assist", self.assist_waits), ("probes", self.probe_log)]:
            if rows:
                keys = sorted({k for r in rows for k in r})
                with open(self.out / f"{name}.csv", "w", newline="") as f:
                    wr = csv.DictWriter(f, keys)
                    wr.writeheader()
                    wr.writerows(rows)
        if self.replay:
            with open(self.out / "replay.json", "w") as f:
                json.dump({"frames": self.replay, "stations": [asdict(s) for s in self.w.stations],
                           "hospitals": [asdict(s) for s in self.w.hospitals],
                           "attacks": self.att.specs}, f)
        s = summarise(self, wall)
        with open(self.out / "summary.json", "w") as f:
            json.dump(s, f, indent=1)
        return s


def run(cfg: dict, out_dir: str | Path | None = None) -> dict:
    out = Path(out_dir) if out_dir else C.ROOT / "runs" / f"{cfg['name']}_s{cfg['seed']}"
    return Run(cfg, out).run()
