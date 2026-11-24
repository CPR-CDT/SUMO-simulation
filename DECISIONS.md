# Decision and assumption log

Newest first. Each entry: date (UTC), decision, reason, who. Rules live in files (playbook Rule 0).

- **2026-11-24** — Demo videos added (`scripts/make_video.py`, `docs/demos/`). While checking the frames, found a **display bug in the replay viewer**: kerb/harbour halts (state code `HAL`) were drawn and counted as halted *in lane*, because the test was "code ends in L". Fixed in `make_replay.py` and `make_video.py`; the HTML replays were regenerated. Metrics were never affected (they use the halt record, not the replay code), but the "70 AVs halted in lane at minute 49" quoted for the A2_P0 replay was inflated: the correct figure is **66**. Also committed for traceability: the opposite-lane-free network and the `_dbg_crash_*` scenarios used in the segfault diagnosis (header comment stripped). (Claude)

- **2026-11-23** — **v4 is the current result set**: 89 runs, 0 failures. Results and checks are in `docs/results/`, with a summary in README §8.4.
  - All exact-identity null checks hold, except one non-reproducible late divergence (N_base_P1 seed 2, after t = 5093 s, 0.6 veh-h). Same-config reruns and three Python hash seeds were all bit-identical, so the cause is not found. Logged as an open issue, with a size below the noise floor.
  - Teleport-off arms are inconclusive: the baseline itself gridlocks without teleports in some seeds.
  - Figure panels chosen: background delay, lane blocking, ambulance response, probes stuck ≥ 5 min. (Claude)

- **2026-11-23** — v3 (no segfaults after the bluelight fix; 5 runs failed on a sampler bug, fixed and rerun individually) showed:
  - large, clear effects on AV lane blocking, background delay, stranded passengers, assist waits and unserved trips;
  - but the ambulance *response* increase came **only from censored calls**. Ambulances stuck ≥ 300 s were teleported by SUMO past their scene stop and removed at route end, so the call was never answered. Meanwhile *travel* among arrived calls fell (survivorship);
  - EMS sample: only ~5 scored calls per run.

  Decisions:
  1. An ambulance teleported away on its way to a scene is **re-inserted** where it was last seen and continues, so the call is answered late, not never (the teleport still skips part of the jam, so delay is understated).
  2. **Probe blue-light trips** at 30/h (measurement only, no real units used) for statistical power: travel / route-estimate ratio, share > 1.5×, share teleported (= stuck ≥ 5 min).

  v3 EMS numbers are not used; full rerun as v4. (Claude)

- **2026-11-23** — Batch v2 had 10/50 main and 17/39 check runs crash with SUMO segfaults, despite ambulance opposite-overtaking being off. Diagnosis on baseline seed 2 (crash at t≈3272 s inside a SUMO step, 7 s after our last command): opposite-lane-free network → still crashes; bluelight device off → clean, on both networks. Decision: **bluelight device off**, replaced by red-light pass (≤ 20 km/h). v2 discarded; full rerun as **v3**. Also: the logged collisions come from opposite-lane overtaking (0 collisions on the opposite-free net); the opposites net is kept so ordinary drivers can pass halted AVs. Route-cache race fixed (atomic write, net name in key). (Claude)
- **2026-11-23** — v2 null checks that completed before the crash fix all held **exactly**: N_dur0, N_r0, N_base_P1, N_base_P2 = baseline to every decimal; N_0av_A1 = N_0av_base. N_teleoff arms showed lane-blocking roughly 2× higher with teleport off, confirming red-team fault 3: teleports hide blockage. These checks are repeated in null3.

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
