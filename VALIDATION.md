# Validation record

Only what has actually been run is listed. Updated 2026-11-23 for batch **v4** (code commit after the EMS probe and re-insertion changes).
- Main batch: 10 arms × 5 seeds, 0 failed runs.
- Check batch: 13 arms × 3 seeds, 0 failed runs.
- Full tables: `docs/results/results_v4.md` and `docs/results/checks_null4.md`. Raw rows: `docs/results/batch_*.csv`.

## Software checks

| Check | Result | Evidence |
|---|---|---|
| Metric unit tests | 9/9 pass | `pytest -q tests` |
| README quick start in a fresh clone | passes, after fixing a route-file bug the test exposed | commit "Fix: strip randomTrips header comment" |
| Same scenario and seed in two different processes | bit-identical (baseline seeds 1–3, run in two batches) | `batch_v4.csv` vs `batch_null4.csv` |
| Independence from Python hash seed | bit-identical for PYTHONHASHSEED 1, 2, 3 | baseline seed 2 |
| SUMO crashes | 0 in v4 (v2: 27/89 segfaults, traced to the bluelight device, now off) | DECISIONS.md |

## Null and limiting cases (v4 check batch, 3 seeds)

| Check | Expected | Result |
|---|---|---|
| A1 with duration 0 | = baseline | **exactly equal** (every metric, every seed) |
| A1 with radius 0 | = baseline | **exactly equal** |
| Baseline under P2 | = baseline | **exactly equal** |
| Baseline under P1 | = baseline | equal for seeds 1 and 3. Seed 2 diverged after t = 5093 s (background delay −0.6 veh-h, 1 trip). **A rerun of the same configuration matched the baseline exactly**, so this is a rare, non-reproducible divergence, not a policy effect. Bound: smaller than the noise floor. **Open issue.** |
| 0 AVs: A1 vs no attack | identical | **exactly equal** |
| N_noise (SUMO internal seed only) | paired noise floor | background delay +0.4 ± 38 veh-h; lane blocking +0.5 ± 14 AV-min; ambulance response +0.01 ± 0.43 min |
| A1 with unlimited operators | assist wait 0 | **0.00** min; lane blocking +577 AV-min (vs A1_P0 +1,433 on 5 seeds), so operator capacity drives most of the blockage |
| A1 with auto-resume (no operator needed) | less blockage | lane blocking +453 AV-min; assist wait ≈ 0 |
| A1_P1 with unlimited kerb | less blockage than A1_P1 | +501 AV-min (A1_P1: +702) |
| A5 below capacity (ρ ≈ 0.56) | ≈ no effect | every metric within the noise floor |
| Teleport off (baseline and A1_P0) | measure what teleports hide | **inconclusive**: without teleports the *baseline itself* gridlocks in some seeds (delay CI ± 1,068 veh-h). Teleports both remove real jams and hide AV blockage; their bias direction is mixed. |

## Not yet done

- Known-case face validity (Cruise, San Francisco 2023; Waymo, San Francisco, December 2025).
- Calibration of background demand against DfT counts.
- Global sensitivity analysis (Morris / Sobol).
- More seeds for EMS effects (most EMS confidence intervals are wide at n = 5).
- A second blind red team on the v4 code.
