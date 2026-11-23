"""Run one scenario.  python run.py scenarios/A1_P0.yaml --seed 1 [--replay]"""
import argparse
import json

from avsim import config
from avsim.sim import run

ap = argparse.ArgumentParser()
ap.add_argument("scenario", nargs="?")
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--replay", action="store_true")
ap.add_argument("--end", type=int)
a = ap.parse_args()
over = {"seed": a.seed}
if a.replay:
    over["replay"] = {"record": True}
if a.end:
    over["sim"] = {"end_s": a.end}
cfg = config.load(a.scenario, **over)
print(json.dumps(run(cfg), indent=1))
