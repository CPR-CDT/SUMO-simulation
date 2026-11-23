"""Batch: scenarios x seeds, in parallel worker processes (one SUMO per process).

python batch.py --seeds 1 2 3 --jobs 6 scenarios/baseline.yaml scenarios/A1_P0.yaml ...
Writes runs/<name>_s<seed>/summary.json and appends to runs/batch_<tag>.csv.
"""
import argparse
import csv
import json
import multiprocessing as mp
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def one(job):
    scen, seed = job
    # separate interpreter per run: libsumo holds one simulation per process
    p = subprocess.run([sys.executable, str(ROOT / "run.py"), scen, "--seed", str(seed)],
                       capture_output=True, text=True, cwd=ROOT)
    if p.returncode != 0:
        return {"scenario": scen, "seed": seed, "error": f"exit {p.returncode}: {p.stderr[-300:]}"}
    s = json.loads(p.stdout[p.stdout.index("{"):])
    s["scenario"] = scen
    return s


def flat(s):
    out = {}
    for k, v in s.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                out[f"{k}.{k2}"] = v2
        elif isinstance(v, list):
            out[k] = "+".join(map(str, v))
        else:
            out[k] = v
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios", nargs="+")
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--tag", default="v1")
    a = ap.parse_args()
    jobs = [(s, k) for k in a.seeds for s in a.scenarios]
    rows = []
    with mp.Pool(a.jobs) as pool:
        for s in pool.imap_unordered(one, jobs):
            rows.append(flat(s))
            print(s.get("name", s["scenario"]), s.get("seed"), "ERROR " + s["error"] if "error" in s else
                  f"resp_mean={s.get('resp_mean_s', float('nan')):.0f}s lane_block={s.get('lane_block_min', 0):.0f}min",
                  flush=True)
    keys = sorted({k for r in rows for k in r})
    out = ROOT / "runs" / f"batch_{a.tag}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(rows)
    print("wrote", out)
