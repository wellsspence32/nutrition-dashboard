#!/usr/bin/env python3
"""
Cronometer Nutrition & Fitness Dashboard Builder
Run locally:  python build_dashboard.py
GitHub Actions runs this automatically on schedule.
"""

import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Config — edit these as needed
# ---------------------------------------------------------------------------
ROOT     = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_DIR  = ROOT / "docs"
OUT_FILE = OUT_DIR / "index.html"

TARGETS = {
    "calories": 2000,
    "protein":  150,
    "carbs":    200,
    "fat":      66.7,
}

HYDROSTATIC = [
    {"date": "2021-09-08", "weight": 148.2, "lean_lb": 125.9, "fat_lb": 22.3, "bf_pct": 15.1, "rmr": 1756},
    {"date": "2022-09-07", "weight": 144.4, "lean_lb": 126.0, "fat_lb": 18.4, "bf_pct": 12.8, "rmr": 1757},
    {"date": "2023-08-28", "weight": 146.6, "lean_lb": 129.0, "fat_lb": 17.6, "bf_pct": 12.0, "rmr": 1787},
    {"date": "2024-10-16", "weight": 150.8, "lean_lb": 131.9, "fat_lb": 18.9, "bf_pct": 12.5, "rmr": 1816},
]

# Remove General Walking sessions under 20 min (dog walks)
EXERCISE_FILTERS = [
    ("General Walking", 20),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def find_csv(pattern):
    matches = sorted(DATA_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        print(f"ERROR: No file matching {pattern!r} in {DATA_DIR}/")
        sys.exit(1)
    return matches[0]

def rolling_30d(df, cols):
    return df.set_index("Date")[cols].rolling("30D", min_periods=7).mean().reset_index()

def safe(v):
    return round(float(v), 1) if v is not None and not (isinstance(v, float) and np.isnan(v)) else None

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_nutrition():
    path = find_csv("*daily*summary*.csv")
    print(f"  Nutrition: {path.name}")
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df[df["Energy (kcal)"] > 500].sort_values("Date").reset_index(drop=True)
    roll = rolling_30d(df, ["Energy (kcal)", "Protein (g)", "Carbs (g)", "Fat (g)"])
    out = []
    for i, row in df.iterrows():
        r = roll.iloc[i]
        out.append({
            "date":         row["Date"].strftime("%Y-%m-%d"),
            "calories":     round(float(row["Energy (kcal)"]), 1),
            "protein":      round(float(row["Protein (g)"]), 1),
            "carbs":        round(float(row["Carbs (g)"]), 1),
            "fat":          round(float(row["Fat (g)"]), 1),
            "calories_avg": safe(r["Energy (kcal)"]),
            "protein_avg":  safe(r["Protein (g)"]),
            "carbs_avg":    safe(r["Carbs (g)"]),
            "fat_avg":      safe(r["Fat (g)"]),
        })
    print(f"    {len(out)} days  ({out[0]['date']} to {out[-1]['date']})")
    return out

def load_exercise():
    path = find_csv("*exercise*.csv")
    print(f"  Exercise:  {path.name}")
    df = pd.read_csv(path)
    df["Day"] = pd.to_datetime(df["Day"])
    before = len(df)
    for name, min_min in EXERCISE_FILTERS:
        df = df[~((df["Exercise"] == name) & (df["Minutes"] < min_min))]
    print(f"    Filtered out {before - len(df)} short sessions")
    daily = df.groupby("Day").agg(
        minutes=("Minutes", "sum"),
        calories_burned=("Calories Burned", "sum"),
        sessions=("Exercise", "count"),
    ).reset_index()
    daily["calories_burned"] = daily["calories_burned"].abs().round(1)
    daily["minutes"] = daily["minutes"].round(1)
    daily = daily.rename(columns={"Day": "Date"}).set_index("Date").sort_index()
    roll = daily[["minutes", "calories_burned"]].rolling("30D", min_periods=5).mean()
    out = []
    for date, row in daily.iterrows():
        r = roll.loc[date]
        out.append({
            "date":            date.strftime("%Y-%m-%d"),
            "minutes":         row["minutes"],
            "calories_burned": row["calories_burned"],
            "sessions":        int(row["sessions"]),
            "minutes_avg":     safe(r["minutes"]),
        })
    print(f"    {len(out)} exercise days")
    return out

def load_weight():
    path = find_csv("*biometric*.csv")
    print(f"  Biometrics: {path.name}")
    df = pd.read_csv(path)
    df["Day"] = pd.to_datetime(df["Day"])
    weight = df[df["Metric"] == "Weight"].sort_values("Day")
    out = [{"date": r["Day"].strftime("%Y-%m-%d"), "weight": r["Amount"]} for _, r in weight.iterrows()]
    print(f"    {len(out)} weight entries")
    return out

# ---------------------------------------------------------------------------
# Build + write
# ---------------------------------------------------------------------------
def build():
    print("\nLoading data...")
    nutrition = load_nutrition()
    exercise  = load_exercise()
    weight    = load_weight()

    nutr_df = pd.DataFrame(nutrition)
    nutr_df["date"] = pd.to_datetime(nutr_df["date"])
    last90  = nutr_df[nutr_df["date"] >= nutr_df["date"].max() - pd.Timedelta(days=90)]

    bundle = {
        "nutrition":   nutrition,
        "exercise":    exercise,
        "weight":      weight,
        "hydrostatic": HYDROSTATIC,
        "targets":     TARGETS,
        "summary": {
            "last90_cal_avg":     round(float(last90["calories"].mean()), 0),
            "last90_protein_avg": round(float(last90["protein"].mean()), 1),
            "last90_carbs_avg":   round(float(last90["carbs"].mean()), 1),
            "last90_fat_avg":     round(float(last90["fat"].mean()), 1),
            "data_start":         nutrition[0]["date"],
            "data_end":           nutrition[-1]["date"],
            "total_days":         len(nutrition),
        },
        "generated": datetime.now().strftime("%Y-%m-%d"),
    }

    OUT_DIR.mkdir(exist_ok=True)
    html = TEMPLATE.replace("__DATA__", json.dumps(bundle, separators=(",", ":")))
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"\n  Dashboard written to {OUT_FILE}  ({OUT_FILE.stat().st_size // 1024} KB)")
    s = bundle["summary"]
    print(f"  Last 90 days: {s['last90_cal_avg']:.0f} kcal / {s['last90_protein_avg']}g P / {s['last90_carbs_avg']}g C / {s['last90_fat_avg']}g F")

# ---------------------------------------------------------------------------
# HTML template (data injected at __DATA__)
# ---------------------------------------------------------------------------
TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wells — Nutrition & Fitness Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0d0f0e;--surface:#161a18;--border:#2a3330;--text:#e8ede9;--muted:#7a9080;--accent:#4ade80;--accent2:#facc15;--accent3:#f87171;--accent4:#60a5fa;--font-display:'Syne',sans-serif;--font-mono:'DM Mono',monospace}
body{background:var(--bg);color:var(--text);font-family:var(--font-mono);min-height:100vh}
.header{padding:2.5rem 2rem 1.5rem;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:1rem}
.header-left h1{font-family:var(--font-display);font-size:2rem;font-weight:800;letter-spacing:-0.02em}
.subtitle{font-size:0.75rem;color:var(--muted);margin-top:0.25rem;letter-spacing:0.08em;text-transform:uppercase}
.updated{font-size:0.7rem;color:var(--muted)}
.range-bar{padding:1rem 2rem;border-bottom:1px solid var(--border);display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap}
.range-label{font-size:0.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-right:0.5rem}
.range-btn{padding:0.35rem 0.9rem;border:1px solid var(--border);background:transparent;color:var(--muted);font-family:var(--font-mono);font-size:0.72rem;cursor:pointer;border-radius:3px;transition:all 0.15s}
.range-btn:hover{border-color:var(--accent);color:var(--accent)}
.range-btn.active{border-color:var(--accent);color:var(--accent);background:rgba(74,222,128,0.08)}
.insight-bar{padding:1rem 2rem;border-bottom:1px solid var(--border);background:var(--surface);display:flex;gap:2rem;align-items:center;flex-wrap:wrap}
.insight-item{display:flex;flex-direction:column;gap:0.1rem}
.insight-label{font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em}
.insight-val{font-family:var(--font-display);font-size:1.4rem;font-weight:700}
.insight-sub{font-size:0.65rem}
.green{color:var(--accent)}.yellow{color:var(--accent2)}.red{color:var(--accent3)}.blue{color:var(--accent4)}
.sep{width:1px;height:2.5rem;background:var(--border)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border)}
.full{grid-column:1/-1}
.card{background:var(--bg);padding:1.5rem}
.card-label{font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.75rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem}
.leg{display:inline-flex;align-items:center;gap:0.3rem;font-size:0.65rem;color:var(--muted)}
.leg::before{content:'';width:8px;height:2px;border-radius:1px;display:inline-block}
.lg::before{background:var(--accent)}.ly::before{background:var(--accent2)}.lb::before{background:var(--accent4)}.lr::before{background:var(--accent3)}
canvas{width:100%!important}
.comp-table{width:100%;border-collapse:collapse;margin-top:0.5rem}
.comp-table th{font-size:0.6rem;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted);text-align:left;padding:0.4rem 0.5rem;border-bottom:1px solid var(--border)}
.comp-table td{font-size:0.8rem;padding:0.5rem;border-bottom:1px solid var(--border)}
.comp-table tr:last-child td{border-bottom:none}
.hi{color:var(--accent);font-weight:500}.dim{color:var(--muted);font-size:0.7rem}
.footer{padding:1rem 2rem;border-top:1px solid var(--border);font-size:0.65rem;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:0.5rem}
@media(max-width:700px){.grid{grid-template-columns:1fr}.full{grid-column:1}.header{flex-direction:column;align-items:flex-start}}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <h1>Wells / Nutrition + Fitness</h1>
    <div class="subtitle" id="hdr-sub"></div>
  </div>
  <div class="updated" id="updated"></div>
</div>
<div class="range-bar">
  <span class="range-label">Range</span>
  <button class="range-btn" onclick="go(30,this)">30d</button>
  <button class="range-btn active" onclick="go(90,this)">90d</button>
  <button class="range-btn" onclick="go(180,this)">180d</button>
  <button class="range-btn" onclick="go(365,this)">1yr</button>
  <button class="range-btn" onclick="go(99999,this)">All time</button>
</div>
<div class="insight-bar">
  <div class="insight-item"><div class="insight-label">Calories avg</div><div class="insight-val" id="ic"></div><div class="insight-sub" id="ic2"></div></div>
  <div class="sep"></div>
  <div class="insight-item"><div class="insight-label">Protein avg</div><div class="insight-val" id="ip"></div><div class="insight-sub" id="ip2"></div></div>
  <div class="sep"></div>
  <div class="insight-item"><div class="insight-label">Carbs avg</div><div class="insight-val" id="ica"></div><div class="insight-sub" id="ica2"></div></div>
  <div class="sep"></div>
  <div class="insight-item"><div class="insight-label">Fat avg</div><div class="insight-val" id="if"></div><div class="insight-sub" id="if2"></div></div>
  <div class="sep"></div>
  <div class="insight-item"><div class="insight-label">Exercise days</div><div class="insight-val" id="ie"></div><div class="insight-sub" id="ie2"></div></div>
</div>
<div class="grid">
  <div class="card full">
    <div class="card-label">Calories / day vs. target<span style="display:flex;gap:1rem"><span class="leg lg">daily</span><span class="leg ly">30-day avg</span><span class="leg lr">target 2000 kcal</span></span></div>
    <canvas id="cc" height="110"></canvas>
  </div>
  <div class="card">
    <div class="card-label">Protein (g)<span style="display:flex;gap:1rem"><span class="leg lg">30-day avg</span><span class="leg lr">target 150g</span></span></div>
    <canvas id="cp" height="120"></canvas>
  </div>
  <div class="card">
    <div class="card-label">Carbs (g)<span style="display:flex;gap:1rem"><span class="leg lb">30-day avg</span><span class="leg lr">target 200g</span></span></div>
    <canvas id="cca" height="120"></canvas>
  </div>
  <div class="card">
    <div class="card-label">Fat (g)<span style="display:flex;gap:1rem"><span class="leg ly">30-day avg</span><span class="leg lr">target 66.7g</span></span></div>
    <canvas id="cf" height="120"></canvas>
  </div>
  <div class="card">
    <div class="card-label">Exercise minutes / day<span style="display:flex;gap:1rem"><span class="leg lg">daily</span><span class="leg ly">30-day avg</span></span></div>
    <canvas id="ce" height="120"></canvas>
  </div>
  <div class="card">
    <div class="card-label">Weight (lbs)<span style="display:flex;gap:1rem"><span class="leg lg">scale</span><span class="leg ly">hydrostatic test</span></span></div>
    <canvas id="cw" height="120"></canvas>
  </div>
  <div class="card">
    <div class="card-label">Body composition — hydrostatic tests</div>
    <canvas id="cb" height="120"></canvas>
  </div>
  <div class="card">
    <div class="card-label">Body composition detail</div>
    <table class="comp-table">
      <thead><tr><th>Date</th><th>Weight</th><th>Lean (lb)</th><th>Fat (lb)</th><th>BF%</th><th>RMR</th></tr></thead>
      <tbody id="ctb"></tbody>
    </table>
  </div>
</div>
<div class="footer">
  <span id="ftr">Showing: 90 days</span>
  <span>Cronometer export · 30-day rolling windows · Targets: 2000 kcal / 150g P / 200g C / 66.7g F</span>
</div>
<script>
const D=__DATA__;
Chart.defaults.color='#7a9080';Chart.defaults.borderColor='#2a3330';Chart.defaults.font.family="'DM Mono',monospace";Chart.defaults.font.size=10;
const G='#4ade80',Y='#facc15',B='#60a5fa',R='#f87171',T=D.targets;
let CH={};
function fd(arr,k,days){if(days>=99999)return arr;const c=new Date(Date.now()-days*864e5);return arr.filter(x=>new Date(x[k])>=c);}
function av(arr){return arr.length?arr.reduce((a,b)=>a+b,0)/arr.length:0;}
function pc(p){return p>=95&&p<=110?'green':p>=85||p>110?'yellow':'red';}
function kill(id){if(CH[id]){CH[id].destroy();delete CH[id];}}
function line(id,labels,ds,yo={}){
  kill(id);
  CH[id]=new Chart(document.getElementById(id),{type:'line',data:{labels,datasets:ds},
  options:{responsive:true,animation:{duration:200},interaction:{mode:'index',intersect:false},
    plugins:{legend:{display:false},tooltip:{backgroundColor:'#1e2420',borderColor:'#2a3330',borderWidth:1,titleColor:'#e8ede9',bodyColor:'#7a9080',padding:8}},
    scales:{x:{ticks:{maxTicksLimit:8,maxRotation:0},grid:{color:'rgba(42,51,48,0.5)'}},y:{grid:{color:'rgba(42,51,48,0.5)'},...yo}}}});
}
function ins(nutr,ex){
  [[ic,ic2,av(nutr.map(d=>d.calories)),T.calories,'kcal'],
   [ip,ip2,av(nutr.map(d=>d.protein)),T.protein,'g'],
   [ica,ica2,av(nutr.map(d=>d.carbs)),T.carbs,'g','blue'],
   [iff,if2,av(nutr.map(d=>d.fat)),T.fat,'g']].forEach(([v,s,val,tgt,u,fc])=>{
    const p=val/tgt*100,cl=fc||pc(p);
    v.className='insight-val '+cl;v.textContent=val.toFixed(0)+u;
    s.className='insight-sub '+cl;s.textContent=p.toFixed(0)+'% of target';
  });
  const m=av(ex.map(d=>d.minutes));
  ie.className='insight-val yellow';ie.textContent=ex.length;
  ie2.className='insight-sub yellow';ie2.textContent=m.toFixed(0)+' min avg/session';
}
function render(days){
  const nutr=fd(D.nutrition,'date',days),ex=fd(D.exercise,'date',days),wt=fd(D.weight,'date',days);
  ftr.textContent='Showing: '+(days>=99999?'all time ('+D.summary.data_start+' – '+D.summary.data_end+')':'last '+days+' days');
  ins(nutr,ex);
  const NL=nutr.map(d=>d.date.slice(5));
  line('cc',NL,[
    {label:'Daily',data:nutr.map(d=>d.calories),borderColor:G,borderWidth:1,pointRadius:0,fill:false,tension:0.3},
    {label:'30d avg',data:nutr.map(d=>d.calories_avg),borderColor:Y,borderWidth:2,pointRadius:0,fill:false,tension:0.5},
    {label:'Target',data:nutr.map(()=>T.calories),borderColor:R,borderWidth:1.5,borderDash:[6,4],pointRadius:0,fill:false},
  ],{suggestedMin:1200,suggestedMax:3000});
  line('cp',NL,[
    {label:'30d avg',data:nutr.map(d=>d.protein_avg),borderColor:G,borderWidth:2,pointRadius:0,fill:false,tension:0.5},
    {label:'Target',data:nutr.map(()=>T.protein),borderColor:R,borderWidth:1.5,borderDash:[6,4],pointRadius:0,fill:false},
  ]);
  line('cca',NL,[
    {label:'30d avg',data:nutr.map(d=>d.carbs_avg),borderColor:B,borderWidth:2,pointRadius:0,fill:false,tension:0.5},
    {label:'Target',data:nutr.map(()=>T.carbs),borderColor:R,borderWidth:1.5,borderDash:[6,4],pointRadius:0,fill:false},
  ]);
  line('cf',NL,[
    {label:'30d avg',data:nutr.map(d=>d.fat_avg),borderColor:Y,borderWidth:2,pointRadius:0,fill:false,tension:0.5},
    {label:'Target',data:nutr.map(()=>T.fat),borderColor:R,borderWidth:1.5,borderDash:[6,4],pointRadius:0,fill:false},
  ]);
  const EL=ex.map(d=>d.date.slice(5));
  line('ce',EL,[
    {label:'Daily',data:ex.map(d=>d.minutes),borderColor:G,borderWidth:1,pointRadius:0,fill:false,tension:0.3},
    {label:'30d avg',data:ex.map(d=>d.minutes_avg),borderColor:Y,borderWidth:2,pointRadius:0,fill:false,tension:0.5},
  ]);
  {const cut=days>=99999?new Date('2000-01-01'):new Date(Date.now()-days*864e5);
  const hy=D.hydrostatic.filter(h=>new Date(h.date)>=cut);
  const all=[...new Set([...wt.map(d=>d.date),...hy.map(h=>h.date)])].sort().filter(d=>new Date(d)>=cut);
  const L=all.map(d=>d.slice(5));
  const wm=Object.fromEntries(wt.map(d=>[d.date.slice(5),d.weight]));
  const hm=Object.fromEntries(hy.map(h=>[h.date.slice(5),h.weight]));
  line('cw',L,[
    {label:'Scale',data:L.map(l=>wm[l]??null),borderColor:G,borderWidth:1.5,pointRadius:L.map(l=>wm[l]!=null?3:0),pointBackgroundColor:G,fill:false,tension:0.3,spanGaps:false},
    {label:'Hydrostatic',data:L.map(l=>hm[l]??null),borderColor:Y,borderWidth:0,pointRadius:L.map(l=>hm[l]!=null?7:0),pointBackgroundColor:Y,pointStyle:'star',fill:false,spanGaps:false},
  ],{suggestedMin:130,suggestedMax:165});}
  {const h=D.hydrostatic,L=h.map(d=>d.date.slice(0,4));
  kill('cb');
  CH['cb']=new Chart(document.getElementById('cb'),{type:'line',data:{labels:L,datasets:[
    {label:'Lean (lb)',data:h.map(d=>d.lean_lb),borderColor:G,borderWidth:2,pointRadius:5,pointBackgroundColor:G,fill:false,tension:0.4},
    {label:'Fat (lb)',data:h.map(d=>d.fat_lb),borderColor:R,borderWidth:2,pointRadius:5,pointBackgroundColor:R,fill:false,tension:0.4},
    {label:'BF%',data:h.map(d=>d.bf_pct),borderColor:Y,borderWidth:2,pointRadius:5,pointBackgroundColor:Y,fill:false,tension:0.4,yAxisID:'y2'},
  ]},options:{responsive:true,plugins:{legend:{display:false},tooltip:{backgroundColor:'#1e2420',borderColor:'#2a3330',borderWidth:1,titleColor:'#e8ede9',bodyColor:'#7a9080',padding:8}},
    scales:{x:{ticks:{maxRotation:0},grid:{color:'rgba(42,51,48,0.5)'}},y:{grid:{color:'rgba(42,51,48,0.5)'},suggestedMin:0,suggestedMax:160},
    y2:{position:'right',suggestedMin:0,suggestedMax:25,grid:{display:false},ticks:{callback:v=>v+'%',color:'#7a9080'}}}}});}
  {const tb=document.getElementById('ctb');tb.innerHTML='';
  D.hydrostatic.forEach((h,i)=>{
    const p=D.hydrostatic[i-1];
    const chg=(a,b,inv)=>{if(!p)return'<span class="dim">—</span>';const n=+(a-b).toFixed(1);if(!n)return'<span class="dim">—</span>';const ok=inv?n<0:n>0;return`<span style="color:${ok?'var(--accent)':'var(--accent3)'}">${n>0?'↑':'↓'}${Math.abs(n)}</span>`;};
    tb.innerHTML+=`<tr><td>${h.date}</td><td>${h.weight}lb</td><td class="hi">${h.lean_lb} <small>${chg(h.lean_lb,p?.lean_lb,false)}</small></td><td>${h.fat_lb} <small>${chg(h.fat_lb,p?.fat_lb,true)}</small></td><td>${h.bf_pct}% <small>${chg(h.bf_pct,p?.bf_pct,true)}</small></td><td class="dim">${h.rmr}</td></tr>`;
  });}
}
function go(days,btn){document.querySelectorAll('.range-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');render(days);}
const ic=document.getElementById('ic'),ic2=document.getElementById('ic2'),ip=document.getElementById('ip'),ip2=document.getElementById('ip2'),ica=document.getElementById('ica'),ica2=document.getElementById('ica2'),iff=document.getElementById('if'),if2=document.getElementById('if2'),ie=document.getElementById('ie'),ie2=document.getElementById('ie2'),ftr=document.getElementById('ftr');
document.getElementById('updated').textContent='Generated '+D.generated;
document.getElementById('hdr-sub').textContent='Cronometer · '+D.summary.data_start+' – '+D.summary.data_end+' · '+D.summary.total_days+' tracked days';
render(90);
</script>
</body>
</html>"""

if __name__ == "__main__":
    if not DATA_DIR.exists():
        print(f"ERROR: data/ folder not found. Create it and add your Cronometer CSVs.")
        sys.exit(1)
    build()
