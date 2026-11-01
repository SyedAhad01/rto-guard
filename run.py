"""python run.py [--csv data/orders_sample.csv] [--llm]
Trains on everything before the last full month, scores that month, writes out/backtest.csv, out/findings.txt, out/dashboard.html"""
import argparse, json, html, os
import pandas as pd
from rto.engine import load_cfg, clean, add_features, RiskModel, decide, rto_cost
os.makedirs("out", exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--csv", default="data/orders_sample.csv")
ap.add_argument("--llm", action="store_true", help="use Claude for address checks (needs ANTHROPIC_API_KEY)")
a = ap.parse_args()
cfg = load_cfg()
sep = "\t" if "\t" in open(a.csv, encoding="utf-8").readline() else ","
raw = pd.read_csv(a.csv, sep=sep, dtype={"phone": str, "pincode": str})
df, rep = clean(raw)
df, pin_map = add_features(df)

# ---- time split: no peeking at the month we score ----
last = df.order_datetime.max().to_period("M")
test = df[df.order_datetime.dt.to_period("M") == last].copy()
train = df[df.order_datetime.dt.to_period("M") < last]
model = RiskModel(k=cfg["model"]["smoothing"]).fit(train)
dec = pd.DataFrame([decide(r, model, cfg, a.llm) for _, r in test.iterrows()], index=test.index)
test = test.join(dec)

# ---- Rs impact (backtest uses the real outcome labels) ----
cost, c, bt = rto_cost(cfg), cfg["costs"], cfg["backtest_assumptions"]
test["margin"] = c["gross_margin"] * test.order_value
def impact(r):
    saved = lost = 0.0
    if r.action == "HOLD":
        saved, lost = (cost, 0) if r.rto else (0, r.margin)
    elif r.action == "CONFIRM":
        if r.rto: saved = bt["confirm_catches_rto"] * cost
        else: lost = bt["confirm_loses_genuine"] * r.margin
    elif r.action == "NUDGE":
        from rto.engine import prepaid_offer
        disc = prepaid_offer(r.p_rto, r.order_value, cfg)["discount"]
        if r.rto: saved = bt["nudge_accept_rate"] * (cost - disc)
        else: lost = bt["nudge_accept_rate"] * disc
    return pd.Series({"saved": saved, "lost": lost})
test = test.join(test.apply(impact, axis=1))
test["day"] = test.order_datetime.dt.date
test.drop(columns=["margin"]).to_csv("out/backtest.csv", index=False)

# ---- findings ----
def rate(g): return f"{g.rto.mean():.0%} (n={len(g)})"
L = [f"Data cleaning: {json.dumps(rep)}", f"Overall COD RTO rate: {rate(df)}",
     f"Cost of one RTO: Rs {cost:.1f}"]
for col in ["city", "prior_rto_band", "new_cust", "junk_name", "junk_addr", "no_pin", "pin_mismatch", "value_band", "utm_source", "courier", "hour_band"]:
    L.append(f"\nRTO by {col}:"); 
    for k, g in df.groupby(col): L.append(f"  {k}: {rate(g)}")
pm = df.groupby("value_band").rto.mean()
L.append(f"\nRTO Rs lost on all orders in data: Rs {df.rto.sum()*cost:,.0f}")
tm = test.groupby("action").agg(orders=("rto", "size"), actual_rto=("rto", "mean"), saved=("saved", "sum"), lost=("lost", "sum"))
L.append(f"\nBACKTEST on {last} (trained on earlier months):\n{tm.round(2).to_string()}")
L.append(f"Net impact Rs {test.saved.sum()-test.lost.sum():,.0f}  (saved {test.saved.sum():,.0f} - lost {test.lost.sum():,.0f}); baseline RTO loss that month Rs {test.rto.sum()*cost:,.0f}")
open("out/findings.txt", "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L[-8:]))

# ---- dashboard (yesterday = latest day in data) ----
y = test[test.day == test.day.max()]
cnt = y.action.value_counts().reindex(["SHIP", "CONFIRM", "NUDGE", "HOLD"]).fillna(0).astype(int)
names = {"SHIP": "Ship as-is", "CONFIRM": "Ship after confirmation", "NUDGE": "Nudge to prepaid", "HOLD": "Hold / cancel"}
rows = "".join(f"<tr><td>{html.escape(r.order_id)}</td><td>{r.action}</td><td>{r.p_rto:.0%}</td><td>{html.escape(r.reason)}</td></tr>"
               for r in y[y.action != "SHIP"].itertuples())
tiles = "".join(f"<div class=t><b>{cnt[k]}</b><span>{names[k]}</span></div>" for k in names)
s, l = y.saved.sum(), y.lost.sum()
open("out/dashboard.html", "w", encoding="utf-8").write(f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>RTO Guard - {y.day.max()}</title><style>:root{{--bg:#fff;--fg:#1a1a1a;--card:#f4f4f6}}@media(prefers-color-scheme:dark){{:root{{--bg:#16161a;--fg:#eee;--card:#25252b}}}}
body{{font:15px system-ui;background:var(--bg);color:var(--fg);max-width:900px;margin:24px auto;padding:0 16px}}.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.t{{background:var(--card);border-radius:10px;padding:14px}}.t b{{display:block;font-size:28px}}.t span{{opacity:.7}}table{{width:100%;border-collapse:collapse;margin-top:8px}}td,th{{text-align:left;padding:6px;border-bottom:1px solid #8883;font-size:13px}}</style>
<h2>COD orders on {y.day.max()}: {len(y)} orders</h2><div class=g>{tiles}</div>
<h3>Estimated impact (Rs)</h3><div class=g><div class=t><b>+{s:,.0f}</b><span>saved from avoided RTOs</span></div>
<div class=t><b>-{l:,.0f}</b><span>lost from cancelled/dropped genuine orders</span></div>
<div class=t><b>{s-l:+,.0f}</b><span>net impact</span></div></div>
<p style="opacity:.7;font-size:12px">Estimates use the backtest assumptions in config.yaml (confirm catches {bt['confirm_catches_rto']:.0%} of would-be RTOs, nudge accepted by {bt['nudge_accept_rate']:.0%}).</p>
<h3>Orders needing action</h3><table><tr><th>Order<th>Action<th>RTO risk<th>Why</tr>{rows}</table>""")
print("wrote out/dashboard.html")
