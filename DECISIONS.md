# Decision and assumption log

Newest first. Each entry: date (UTC), decision, reason, who. Rules live in files (playbook Rule 0).

- **2026-11-23** — Build the integration core (fleet software, attacks, policies) and also the network, EMS and metrics cards in one session rather than with parallel builder agents. Reason: these components share one TraCI loop and state; splitting them before the interfaces had settled would have cost more than it saved. Fresh agents are kept for the checks (red team, QA). (Claude, as integrator)
- **2026-11-23** — libsumo (in-process) instead of socket TraCI, for about a 5–10× speed-up; `AVSIM_TRACI=1` switches back for sumo-gui/debugging.
- **2026-11-23** — Network: OSM bbox 51.465..51.512 N, −0.245..−0.170 E (Hammersmith & Fulham + west Kensington & Chelsea, ~6.4 × 5.8 km). Built with `--lefthand` (UK traffic) and `--opposites.guess` (allows overtaking through the opposite lane, which ambulances do around stopped vehicles). Stops are limited to the largest strongly connected component.
- **2026-11-23** — Overpass was overloaded, so EMS sites came from Nominatim by name. These are two stations and two A&E hospitals; Hammersmith Hospital and St Mary's are outside the box.
- **2026-11-23** — Common random numbers: background traffic, taxi requests and EMS incidents are drawn from fixed seed streams, so arms are paired with the baseline.
- **2026-11-23** — Parked idle AVs that lose the link are simply undispatchable (no halt, no assist request). Only vehicles on the road halt.
- **2026-11-23** — Collisions: `--collision.action warn` (the default teleport would silently remove vehicles, including ambulances). Collisions are counted in summary.json and are a known fidelity issue.
- **2026-11-23** — Policies P0–P2 change only what happens on link loss. A3 and A5 are therefore run under P0 only.
