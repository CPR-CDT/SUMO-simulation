# Red team 1 — blind, read-only, fresh agent (2026-11-23)

Scope: README, params.csv, avsim/*, tests, scenarios. No DECISIONS, runs or ledger. Prompt: playbook `scorer-redteam.md`, adapted to artefact hunting.

**Verdict: progress-demo prototype PASS; paper FAIL. Single most important fix: restore common random numbers.**

Faults, most serious first, each with confidence and status:

1. **CRN break** (high). One shared RNG drew routine holds, stuck draws, service times and conveyance, so after onset every later draw shifted. **Fixed:** per-entity streams.
2. **Censoring bias in ambulance response** (high). Late calls were scored short; ratio and blocked time came from arrived calls only. **Fixed:** calls scored only to 4200 s; ratio still uses arrived calls only, and the censored count is reported.
3. **Blockage capped by teleport (300 s); no ambulance escape** (opposite-lane overtaking off, no rerouting); README was wrong about overtaking (high). **Measured, not removed:** N_teleoff arms; README corrected.
4. **amb_lost handler was dead code** (medium). **Fixed:** an inserted-then-missing ambulance frees its unit.
5. **Every halted AV needs an operator after restore** (high), so recovery rests on assumed `operators` and `service_mean`. **Sensitivity arm:** N_autoresume_A1; C4 sweeps operators.
6. **Background delay misses the insertion backlog** (medium). **Partly fixed:** pending insertions recorded in the time series and summary.
7. **A3 in-lane pickups not counted as blocking** (high). **Fixed:** dwell records.
8. **Assist waits still queued at the end were dropped** (high). **Fixed:** kept as censored waits.
9. **A5 saturates by choice of rate** (ρ ≈ 1.67) (high). **Added:** A5_low (ρ ≈ 0.56).
10. **State-machine strands and kerb leaks** (medium). **Partly fixed:** kerb released when a taxi leaves the network. Strands are still possible and are counted as anomalies.
11. **Response mixes unit queueing and travel; "freeflow" is a route estimate at dispatch; "blocked" includes red lights** (high). **Fixed:** split metrics and renames (`amb_slow_mean_s`).
12. **P1's benefit is built in through kerb bookkeeping** (high). **Open:** stated as a limitation; N_allkerb_A1_P1 bounds it.
13. **Hygiene:** warmup unused, params mismatch, missing params rows. **Fixed:** documented and rows added.

Null and limiting runs it asked for, and their status:
- noise floor: added (N_noise, SUMO seed only);
- all-kerb A1: added;
- teleport off: added;
- longer scoring tail: done through calls_end_s;
- auto-resume: added;
- A5 below capacity: added;
- 150-AV vs 0-AV baseline: available from N_0av_base vs baseline;
- response split: done.
