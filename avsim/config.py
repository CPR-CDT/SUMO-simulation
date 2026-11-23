"""Scenario configuration: defaults + YAML overrides.

Every numeric default here has a row in params.csv (value, source, grade, bias direction).
Change a default here only together with its params.csv row.
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

DEFAULTS: dict = {
    "name": "baseline",
    "seed": 1,
    "net": "data/net/west_london.net.xml",
    "sim": {
        "end_s": 5400,            # 90 min simulated
        "warmup_s": 900,          # documentation only: the analysis window starts at 1800 s, after warm-up
        "sumo_seed_offset": 0,    # noise-floor arm: changes only SUMO's internal RNG
        "step_s": 1.0,
        "time_to_teleport_s": 300,  # SUMO default; teleports are counted and reported
        "meandata_period_s": 300,
    },
    "background": {
        "period_s": 1.0,          # ≈3,600 veh/h: stationary network, mean speed ≈22 km/h; to calibrate vs DfT counts
        "fringe_factor": 5,
    },
    "fleet": {
        "n_taxis": 150,
        "n_stands": 20,
        "requests_per_h": 300,
        "pickup_dwell_s": 30,
        "no_show_wait_s": 300,    # how long an AV waits for a rider who never appears
        "dropoff_dwell_s": 30,
        "max_pickup_km": 3.0,
        "dispatch_every_s": 5,
        "kerb_space_m": 7.0,      # one kerb space per 7 m of kerbside
        "kerb_fraction": 0.3,     # share of kerbside usable for stopping (rest: junctions, bus stops, yellow lines, parked cars)
        "stand_kerb_spaces": 12,
        "heartbeat_timeout_s": 5,
        "base_assist_per_veh_h": 0.5,   # routine remote-assist events per moving AV-hour
        "stuck_wait_s": 90,             # waiting longer than this in traffic may trigger an assist request
        "p_stuck_assist": 0.2,
        "auto_resume_on_restore": False,  # True = no operator needed once the link is back (sensitivity)
        "harbour_max_km": 1.5,
        "pullover_max_m": 150,
    },
    "assist": {
        "operators": 6,
        "service_mean_s": 180,
        "service_cv": 0.6,
        "fake_service_mean_s": 60,
    },
    "ems": {
        "incidents_per_h": 6.0,   # illustrative; real Cat-1 rate in area is lower
        "probes_per_h": 30.0,     # measurement-only blue-light trips (do not use real units)
        "call_to_dispatch_s": 30,
        "on_scene_s": 1200,
        "p_convey": 0.6,
        "handover_s": 900,
        "amb_speed_factor": 1.2,
        "lc_opposite": 0,         # ambulance opposite-lane overtaking off (see DECISIONS.md)
        "bluelight": False,       # SUMO 1.28 bluelight device segfaults intermittently (DECISIONS.md)
        "red_light_pass": True,   # approximation instead: may cross red lights at <= red_speed_ms
        "red_speed_ms": 5.56,     # 20 km/h
        "cat1_p90_target_s": 900,
        "cat1_mean_target_s": 420,
    },
    "analysis": {"start_s": 1800, "end_s": 5400,    # same window for every arm, attack or not
                 "calls_end_s": 4200},               # calls scored only up to here: >=20 min to arrive before sim end
    "policy": "P0",               # P0 stop-in-lane | P1 pull-over | P2 safe-harbour
    "attacks": [],
    "econ": {"value_of_time_gbp_per_h": 15.0},
    "replay": {"record": False, "every_s": 5},
}


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(path: str | Path | None = None, **overrides) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path) as f:
            cfg = deep_merge(cfg, yaml.safe_load(f) or {})
    cfg = deep_merge(cfg, overrides)
    return cfg
