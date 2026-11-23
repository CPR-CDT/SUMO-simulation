# av-cyber-sim — cyber disruption of a robotaxi fleet, West London

An integrated co-simulation for Group A's Integrator project. It covers:
- **traffic**: a SUMO microsimulation of Hammersmith & Fulham and west Kensington & Chelsea, built from OpenStreetMap;
- **the fleet management system**: dispatch, vehicle–cloud heartbeat, minimal-risk-condition (MRC) behaviour, the remote-assist centre and contingency policies;
- **EMS dispatch**: two real ambulance stations and two A&E hospitals;
- **an attack injector**.

The components are coupled every simulated second through libsumo (TraCI).

Status: **prototype**. See `STATUS.json` and `VALIDATION.md` for what has and hasn't been verified.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install eclipse-sumo libsumo traci sumolib numpy pandas matplotlib pyyaml networkx rtree pyproj pytest
.venv/bin/python -m pytest -q tests                          # metric tests
.venv/bin/python run.py scenarios/A1_P0.yaml --seed 1 --replay # one run (~2 min), writes runs/A1_P0_s1/
.venv/bin/python scripts/make_replay.py runs/A1_P0_s1          # animated replay.html
.venv/bin/python batch.py --seeds 1 2 3 4 5 --jobs 6 scenarios/baseline.yaml scenarios/A*.yaml
.venv/bin/python scripts/analyse.py runs/batch_v1.csv          # paired deltas vs baseline + figure
```

The network is rebuilt with `scripts/build_net.sh` (OSM extract in `data/osm/`).

## Integration: what couples cyber and physical

| From | Variable | To | Where in code |
|---|---|---|---|
| Attack (A1/A2) | per-vehicle link state + heartbeat timeout | MRC halt: in lane (P0), at kerb if space (P1), drive to safe harbour (P2) | `sim._fleet_step`, `_on_link_lost` |
| Halted AVs | stopped vehicle occupying a lane | Congestion, spillback, ambulance delay (SUMO car-following; ambulances may overtake through the opposite lane) | SUMO |
| Congestion | AV waiting time > `stuck_wait_s` | Remote-assist request + in-lane hold (positive feedback) | `_fleet_step` |
| Assist queue (operators, A5 fake load) | queue wait | Recovery time of every halted AV | `_assist_step` |
| Ghost bookings (A3) | fake requests in a zone | AVs converge and dwell (kerb, or in lane once the kerb is full) | `_dispatch`, `_place_stop` |
| Kerb capacity | finite spaces per edge | Whether a pull-over or pickup blocks a lane | `kerb_used`, `world.kerb_cap` |

## Null and limiting-case runs (the playbook's "lazy routes")

These are filled in from real runs in `VALIDATION.md`. Each one must hold:

| Run | Expected |
|---|---|
| attack duration 0 | identical to baseline (same seed) |
| baseline under P0 vs P1 vs P2 | identical (policy only acts on link loss) |
| A1 radius 0 | identical to baseline |
| A1 with 0 AVs | EMS metrics identical to the 0-AV baseline |
| infinite operators | assist wait = 0 |

## Files

| File | What it holds |
|---|---|
| `avsim/` | world (network), demand (common-random-number inputs), attacks, sim (co-simulation), metrics |
| `scenarios/*.yaml` | one arm each; `config.py` holds the defaults |
| `params.csv` | every parameter: value, grade (evidence / assumption / illustrative), source, **direction of bias** |
| `DECISIONS.md` | decision and assumption log |
| `ledger/cards/` | work items and their checks (playbook-style) |
| `STATUS.json`, `VALIDATION.md` | what is verified, and what is not |

Data: OpenStreetMap contributors (ODbL).
