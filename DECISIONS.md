# Decision and assumption log

Newest first. Each entry: date (UTC), decision, reason, who. Rules live in files (playbook Rule 0).

- **2026-11-23** — First blind red team (report in `ledger/reviews/redteam-1.md`): **pass as a demo, fail as a paper**. Fixes applied:
  - per-entity common-random-number streams (routine holds on a moving-time clock, stuck draws, service times, conveyance pre-drawn per incident);
  - EMS calls scored only to 4200 s;
  - lost ambulances free their unit;
  - in-lane pickup/drop-off dwells counted as lane blocking (A3 was ~0 by construction);
  - assist requests still queued at the end are kept as censored waits;
  - insertion backlog recorded;
  - ambulance response split into unit wait and travel ("freeflow" renamed to `route_est`: findRoute at dispatch time).
  New check arms: N_noise (SUMO seed only), N_autoresume_A1, N_allkerb_A1_P1, N_teleoff_base / N_teleoff_A1_P0, A5_low (below capacity). Not yet addressed: P1's benefit rests on kerb bookkeeping (SUMO parking stops have no physical capacity); demand calibration; bus-lane kerb edge cases; teleport cap on blockage (measured by the teleoff arms, not removed). (Claude)
- **2026-11-23** — Background demand set to period 1.0 s (about 3,600 veh/h). At 0.6 s and 0.8 s the network supersaturated with no attack (the vehicle count kept rising and 290 teleports in 90 min at 0.6 s). At 1.0 s it holds steady at about 740 vehicles and 6.2 m/s from 15 to 90 min.
- **2026-11-23** — Ambulance opposite-lane overtaking turned off (`ems.lc_opposite: 0`). The baseline segfaulted in SUMO 1.28 at t≈4939 s with it on, and ran cleanly with it off. This overstates delay behind a halted AV on single-lane roads, and the bias is recorded in params.csv.
- **2026-11-23** — The first batch (v1) was stopped before analysis because it ran on the pre-fix code. No v1 numbers are used anywhere.

- **2026-11-23** — Build the integration core (fleet software, attacks, policies) and also the network, EMS and metrics cards in one session rather than with parallel builder agents. Reason: these components share one TraCI loop and state; splitting them before the interfaces had settled would have cost more than it saved. Fresh agents are kept for the checks (red team, QA). (Claude, as integrator)
- **2026-11-23** — libsumo (in-process) instead of socket TraCI, for about a 5–10× speed-up; `AVSIM_TRACI=1` switches back for sumo-gui/debugging.
- **2026-11-23** — Network: OSM bbox 51.465..51.512 N, −0.245..−0.170 E (Hammersmith & Fulham + west Kensington & Chelsea, ~6.4 × 5.8 km). Built with `--lefthand` (UK traffic) and `--opposites.guess` (allows overtaking through the opposite lane; ambulances' use of it was later disabled, see above). Stops are limited to the largest strongly connected component.
- **2026-11-23** — Overpass was overloaded, so EMS sites came from Nominatim by name. These are two stations and two A&E hospitals; Hammersmith Hospital and St Mary's are outside the box.
- **2026-11-23** — Common random numbers: background traffic, taxi requests and EMS incidents are drawn from fixed seed streams, so arms are paired with the baseline.
- **2026-11-23** — Parked idle AVs that lose the link are simply undispatchable (no halt, no assist request). Only vehicles on the road halt.
- **2026-11-23** — Collisions: `--collision.action warn` (the default teleport would silently remove vehicles, including ambulances). Collisions are counted in summary.json and are a known fidelity issue.
- **2026-11-23** — Policies P0–P2 change only what happens on link loss. A3 and A5 are therefore run under P0 only.
