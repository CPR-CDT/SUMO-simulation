"""Outcome metrics. Pure functions over a finished run's records, so they can be unit-tested.

Survivorship rules (red-team item): incidents with no ambulance arrival by the end are kept, with a
censored response (end - call) and counted separately; halts still open at the end are censored at the end;
network delay comes from SUMO edgeData (includes vehicles still on the road), not from completed trips.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def ems_metrics(incidents: list[dict], all_calls: list[tuple[str, float]], w0: float, w1: float, end: float,
                p90_target: float, call_to_dispatch: float = 0.0) -> dict:
    """incidents: arrived records; all_calls: (iid, t_call) for every incident generated."""
    arrived = {r["iid"]: r for r in incidents}
    resp, censored, blocked, ratio, unit_wait, travel = [], 0, [], [], [], []
    for iid, tc in all_calls:
        if not (w0 <= tc < w1):
            continue
        r = arrived.get(iid)
        if r is None:
            resp.append(end - tc)
            censored += 1
        else:
            resp.append(r["response_s"])
            blocked.append(r["blocked_s"])
            tr = r["t_arrive"] - r["t_dispatch"]
            travel.append(tr)
            unit_wait.append(r["t_dispatch"] - r["t_call"] - call_to_dispatch)
            if r["route_est_s"] > 0:
                ratio.append(tr / r["route_est_s"])
    resp = np.array(resp, float)
    if len(resp) == 0:
        return {"n_calls": 0}
    return {"n_calls": int(len(resp)), "n_censored": censored,
            "resp_mean_s": float(resp.mean()), "resp_p90_s": float(np.percentile(resp, 90)),
            "resp_max_s": float(resp.max()), "frac_over_p90_target": float((resp > p90_target).mean()),
            "amb_slow_mean_s": float(np.mean(blocked)) if blocked else 0.0,   # time below 1 m/s incl. red lights
            "unit_wait_mean_s": float(np.mean(unit_wait)) if unit_wait else float("nan"),
            "travel_mean_s": float(np.mean(travel)) if travel else float("nan"),
            "travel_over_route_est_mean": float(np.mean(ratio)) if ratio else float("nan")}


def network_delay_veh_h(edgedata_path: Path, w0: float, w1: float) -> dict:
    """Sum of background vehicles' timeLoss over edges, for intervals overlapping the window (pro-rated)."""
    if not edgedata_path.exists():
        return {"bg_timeloss_veh_h": float("nan")}
    tl = ws = ss = 0.0
    for iv in ET.parse(edgedata_path).getroot().iter("interval"):
        b, e = float(iv.get("begin")), float(iv.get("end"))
        frac = overlap(b, e, w0, w1) / (e - b) if e > b else 0
        if frac <= 0:
            continue
        for ed in iv.iter("edge"):
            tl += frac * float(ed.get("timeLoss", 0))
            ws += frac * float(ed.get("waitingTime", 0))
            ss += frac * float(ed.get("sampledSeconds", 0))
    return {"bg_timeloss_veh_h": tl / 3600, "bg_waiting_veh_h": ws / 3600, "bg_sampled_veh_h": ss / 3600,
            "bg_timeloss_share": tl / ss if ss else float("nan")}


def halt_metrics(halts: list[dict], w0: float, w1: float) -> dict:
    out = {"lane_block_min": 0.0, "kerb_halt_min": 0.0, "harbour_halt_min": 0.0, "stranded_pax_min": 0.0,
           "lane_block_dwell_min": 0.0, "n_halts_link": 0, "n_halts_assist": 0, "n_lane_dwells": 0}
    for h in halts:
        d = overlap(h["start"], h["end"], w0, w1) / 60
        if d <= 0:
            continue
        out[f"{h['kind']}_block_min" if h["kind"] == "lane" else f"{h['kind']}_halt_min"] += d
        if h["cause"].startswith("dwell"):
            out["lane_block_dwell_min"] += d
            out["n_lane_dwells"] += 1
            continue
        if h.get("with_passenger"):
            out["stranded_pax_min"] += d
        out["n_halts_link" if h["cause"] == "link" else "n_halts_assist"] += 1
    return out


def request_metrics(reqs: list[dict], w0: float, w1: float) -> dict:
    real = [r for r in reqs if not r["fake"] and w0 <= r["t"] < w1]
    if not real:
        return {"n_requests": 0}
    st = [r["status"] for r in real]
    return {"n_requests": len(real), "completed": st.count("completed"),
            "unserved_frac": 1 - st.count("completed") / len(real),
            "app_down": st.count("app_down"), "timeout": st.count("timeout")}


def assist_metrics(waits: list[dict], w0: float, w1: float) -> dict:
    real = np.array([r["wait"] for r in waits if r["kind"] != "fake" and w0 <= r["t_req"] < w1], float)
    if len(real) == 0:
        return {"assist_n": 0}
    cens = sum(1 for r in waits if r["kind"] != "fake" and r.get("censored") and w0 <= r["t_req"] < w1)
    return {"assist_n": int(len(real)), "assist_n_censored": cens, "assist_wait_mean_s": float(real.mean()),
            "assist_wait_p90_s": float(np.percentile(real, 90)), "assist_wait_max_s": float(real.max())}


def summarise(run, wall_s: float) -> dict:
    c = run.cfg
    w0, w1 = c["analysis"]["start_s"], c["analysis"]["end_s"]
    end = c["sim"]["end_s"]
    calls = [(i.iid, i.t) for i in __import__("avsim.demand", fromlist=["x"]).ems_incidents(c, run.w)]
    s = {"name": c["name"], "seed": c["seed"], "policy": c["policy"],
         "attacks": [a["type"] for a in c["attacks"]], "wall_s": round(wall_s, 1),
         "window": [w0, w1]}
    s.update(ems_metrics(run.incidents, calls, w0, c["analysis"]["calls_end_s"], end, c["ems"]["cat1_p90_target_s"],
                         c["ems"]["call_to_dispatch_s"]))
    s.update(network_delay_veh_h(run.out / "edgedata.xml", w0, w1))
    s["bg_delay_cost_gbp"] = s.get("bg_timeloss_veh_h", 0) * c["econ"]["value_of_time_gbp_per_h"]
    s.update(halt_metrics(run.halts, w0, w1))
    s.update(request_metrics(list(run.req_log.values()), w0, w1))
    s.update(assist_metrics(run.assist_waits, w0, w1))
    s["max_lane_halted"] = max((r["lane_halted"] for r in run.ts), default=0)
    pend = [r["pending_insert"] for r in run.ts if w0 <= r["t"] < w1]
    s["pending_insert_mean"] = float(np.mean(pend)) if pend else 0.0
    s["pending_insert_max"] = max(pend, default=0)
    s["teleports"] = dict(run.teleports)
    try:
        st = ET.parse(run.out / "stats.xml").getroot()
        s["collisions"] = int(st.find("safety").get("collisions"))
    except Exception:
        s["collisions"] = None
    s["anomalies"] = dict(run.anomalies)
    return s
