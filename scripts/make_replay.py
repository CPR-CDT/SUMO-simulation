"""Turn runs/<run>/replay.json into a self-contained animated HTML page.

python scripts/make_replay.py runs/A1_P0_s1 [out.html]
"""
import json
import sys
from pathlib import Path

import sumolib

ROOT = Path(__file__).resolve().parents[1]
run = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) > 2 else run / "replay.html"
cfg = json.load(open(run / "config.json"))
rep = json.load(open(run / "replay.json"))
net = sumolib.net.readNet(str(ROOT / cfg["net"]))
roads = []
for e in net.getEdges():
    if e.getFunction() == "internal":
        continue
    major = (e.getType() or "").split(".")[-1] in ("primary", "trunk", "secondary", "motorway")
    roads.append([1 if major else 0, [[round(x), round(y)] for x, y in e.getShape()]])
(x0, y0), (x1, y1) = net.getBBoxXY()
data = {"roads": roads, "bbox": [x0, y0, x1, y1], "frames": rep["frames"], "stations": rep["stations"],
        "hospitals": rep["hospitals"], "attacks": rep["attacks"], "name": cfg["name"], "policy": cfg["policy"]}

HTML = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AV attack replay</title>
<style>
:root{--bg:#0f1419;--fg:#e6e6e6;--muted:#8a96a3;--road:#2a333d;--major:#45505c}
body{margin:0;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif}
header{padding:10px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:16px;margin:0} .muted{color:var(--muted)}
canvas{display:block;width:100%;max-width:1100px;margin:0 auto;background:var(--bg)}
.ctl{display:flex;gap:8px;align-items:center} input[type=range]{width:260px}
.legend span{display:inline-flex;align-items:center;gap:4px;margin-right:12px}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
</style></head><body>
<header><h1 id="title"></h1><span class="muted" id="clock"></span>
<div class="ctl"><button id="play">Pause</button><input id="slider" type="range" min="0" value="0">
<select id="speed"><option value="1">1x</option><option value="3" selected>3x</option><option value="8">8x</option></select></div>
<div class="legend">
<span><i class="dot" style="background:#3fa9f5"></i>AV moving / idle</span>
<span><i class="dot" style="background:#ffb000"></i>AV halted at kerb / harbour</span>
<span><i class="dot" style="background:#ff4fd8"></i>AV halted in lane</span>
<span><i class="dot" style="background:#ff3030"></i>Ambulance</span>
<span><i class="dot" style="background:#7d8590"></i>Other traffic (1 in 4)</span>
<span>+ station, H hospital, dashed ring = attack zone</span></div></header>
<canvas id="c" width="1100" height="1000"></canvas>
<script>
const D=__DATA__;
const cv=document.getElementById('c'),g=cv.getContext('2d');
const [x0,y0,x1,y1]=D.bbox, W=cv.width, H=Math.round(W*(y1-y0)/(x1-x0)); cv.height=H;
const sx=x=>(x-x0)/(x1-x0)*W, sy=y=>H-(y-y0)/(y1-y0)*H, sr=r=>r/(x1-x0)*W;
document.getElementById('title').textContent=`${D.name} (policy ${D.policy})`;
const base=document.createElement('canvas');base.width=W;base.height=H;const b=base.getContext('2d');
for(const [m,pts] of D.roads){b.strokeStyle=m?'#45505c':'#262e37';b.lineWidth=m?1.6:0.7;b.beginPath();
 pts.forEach((p,i)=>i?b.lineTo(sx(p[0]),sy(p[1])):b.moveTo(sx(p[0]),sy(p[1])));b.stroke();}
const sl=document.getElementById('slider');sl.max=D.frames.length-1;let i=0,playing=true;
document.getElementById('play').onclick=e=>{playing=!playing;e.target.textContent=playing?'Pause':'Play'};
sl.oninput=()=>{i=+sl.value;draw()};
const lane=s=>s.length===4&&s[3]==='L';
function col(s){if(lane(s))return'#ff4fd8';if(s.startsWith('HAL')||s.startsWith('HOL'))return'#ffb000';return'#3fa9f5'}
function draw(){const f=D.frames[i];g.drawImage(base,0,0);
 for(const a of D.attacks){if(a.x===undefined)continue;const on=f.t>=a.start_s&&f.t<a.end_s;
  g.setLineDash([6,4]);g.strokeStyle=on?'#ff4fd8':'#5a4a58';g.lineWidth=2;g.beginPath();g.arc(sx(a.x),sy(a.y),sr(a.radius_m),0,7);g.stroke();g.setLineDash([]);}
 g.fillStyle='#7d8590';for(const [x,y] of f.bg)g.fillRect(sx(x)-1,sy(y)-1,2,2);
 for(const [x,y,s] of f.taxi){g.fillStyle=col(s);g.beginPath();g.arc(sx(x),sy(y),lane(s)?4:2.6,0,7);g.fill();}
 g.fillStyle='#ff3030';for(const [x,y] of f.amb){g.beginPath();g.arc(sx(x),sy(y),5,0,7);g.fill();}
 g.font='bold 13px system-ui';g.fillStyle='#fff';
 for(const s of D.stations)g.fillText('+',sx(s.x)-4,sy(s.y)+4);for(const h of D.hospitals)g.fillText('H',sx(h.x)-4,sy(h.y)+4);
 const act=D.attacks.filter(a=>f.t>=a.start_s&&f.t<a.end_s).map(a=>a.type).join(', ');
 const nLane=f.taxi.filter(t=>lane(t[2])).length;
 document.getElementById('clock').textContent=`t = ${Math.floor(f.t/60)} min · attack: ${act||'none'} · AVs halted in lane: ${nLane} · ambulances out: ${f.amb.length}`;
 sl.value=i;}
let last=0;function loop(ts){if(playing&&ts-last>200/ +document.getElementById('speed').value){last=ts;i=(i+1)%D.frames.length;draw();}requestAnimationFrame(loop)}
draw();requestAnimationFrame(loop);
</script></body></html>"""
out.write_text(HTML.replace("__DATA__", json.dumps(data, separators=(",", ":"))))
print("wrote", out, round(out.stat().st_size / 1e6, 1), "MB")
