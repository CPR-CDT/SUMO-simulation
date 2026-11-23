# Validation record

Only what has actually been run is listed here. Updated 2026-11-23.

| Check | Result | Evidence |
|---|---|---|
| Metric unit tests | 8/8 pass | `pytest -q tests` |
| SUMO smoke test (30 min, 2,000 random trips) | runs at 337× real time; 6 teleports (3 jam, 3 yield) | `runs/smoke` (local) |
| Baseline stationarity, period 1.0 s | ≈ 740 vehicles and 6.2 m/s from 15 to 90 min | `runs/dbg_p1.0_s1/ts.csv` (local) |
| Baseline stationarity, period 0.6 / 0.8 s | **fails**: vehicle count rises; 290 teleports at 0.6 s | hence 1.0 s is the default |
| Ambulance opposite-lane overtaking | **SUMO segfault** at t≈4939 s; clean run with it off | DECISIONS.md |
| Null / limiting arms | *pending: batch null2* | — |
| Noise floor (N_noise) | *pending* | — |
| Known-case face validity | *not started* | — |
| Sensitivity analysis | *not started* | — |

Red team 1: see `ledger/reviews/redteam-1.md`.
