#!/usr/bin/env bash
# Rebuild the SUMO network from the OSM extract (bbox 51.465..51.512 N, -0.245..-0.170 E).
# OSM fetched 2026-11-23 via Overpass with the query below; data (c) OpenStreetMap contributors, ODbL.
#   way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|*_link|living_street|service)$"](51.465,-0.245,51.512,-0.170)
set -euo pipefail
cd "$(dirname "$0")/.."
TYP=$(.venv/bin/python -c "import sumo,os;print(os.path.join(sumo.SUMO_HOME,'data','typemap','osmNetconvert.typ.xml'))")
.venv/bin/netconvert --osm-files data/osm/west_london.osm.xml --type-files "$TYP" \
  --lefthand --opposites.guess --geometry.remove --ramps.guess --junctions.join \
  --tls.guess-signals --tls.discard-simple --tls.join --tls.default-type actuated \
  --remove-edges.by-vclass pedestrian,bicycle --keep-edges.by-vclass passenger \
  --remove-edges.isolated --keep-edges.components 1 --output.street-names --output.original-names \
  --proj.utm --no-warnings -o data/net/west_london.net.xml
