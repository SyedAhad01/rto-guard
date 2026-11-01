"""Decision engine. Maths for probabilities/money; LLM only for address judgement (gray zone only)."""
import re, math, os, json, yaml
import pandas as pd

def load_cfg(path="config.yaml"):
    return yaml.safe_load(open(path))

JUNK_NAME = re.compile(r"^(test( order)?|asdf|qwerty|abc|aaa|xyz( xyz)?|na|n/?a|[a-z])$", re.I)
JUNK_ADDR = {"xyz", ".", "home", "call me", "near station", "na"}
ADS = ("meta_ads", "google_ads", "influencer", "instagram_organic", "whatsapp_broadcast")

def rto_cost(cfg):
    c = cfg["costs"]
    return c["forward_shipping"] + c["return_shipping"] + c["packaging_handling"] + c["damage_rate"] * c["product_cost"]

def clean(df):
    """Fix data problems found in the sample. Returns (clean_df, report)."""
    rep = {"rows_in": len(df)}
    df = df.copy()
    df["final_status"] = df["final_status"].str.upper().str.strip()
    rep["exact_duplicate_rows"] = int(df.duplicated().sum())
    df = df.drop_duplicates()
    rep["duplicate_order_ids_kept_first"] = int(df.duplicated("order_id").sum())
    df = df.drop_duplicates("order_id", keep="first")
    rep["in_transit_dropped"] = int((df.final_status == "IN_TRANSIT").sum())
    df = df[df.final_status.isin(["RTO", "DELIVERED"])]
    rep["zero_value_dropped"] = int((df.order_value <= 0).sum())
    df = df[df.order_value > 0].copy()
    df["phone"] = df["phone"].astype(str).str.replace(r"\D", "", regex=True).str[-10:]
    df["pincode"] = df["pincode"].astype("string").str.strip()
    df["order_datetime"] = pd.to_datetime(df["order_datetime"])
    df["rto"] = (df.final_status == "RTO").astype(int)
    rep["rows_out"] = len(df)
    return df.reset_index(drop=True), rep

def add_features(df, pin_map=None):
    d = df.copy()
    d["junk_name"] = d.customer_name.fillna("").str.strip().apply(lambda s: bool(JUNK_NAME.match(s)) or s == "")
    a = d.address.fillna("").str.strip().str.lower()
    d["junk_addr"] = a.isin(JUNK_ADDR) | (a.str.len() < 12) | (a == d.city.fillna("").str.lower())
    d["bad_phone"] = d.phone.str.len() != 10
    d["no_pin"] = d.pincode.isna() | (d.pincode.fillna("").str.len() != 6)
    d["city"] = d.city.fillna("").replace("", "UNKNOWN")
    if pin_map is None:
        ok = d[~d.no_pin & (d.city != "UNKNOWN")]
        pin_map = ok.groupby("city").pincode.agg(lambda s: s.str[:2].mode().iat[0]).to_dict()
    d["pin_mismatch"] = [(not n) and (c in pin_map) and p[:2] != pin_map[c]
                         for c, p, n in zip(d.city, d.pincode.fillna(""), d.no_pin)]
    d["new_cust"] = d.customer_prior_orders == 0
    d["prior_rto_band"] = d.customer_prior_rto.clip(upper=2).astype(str)
    d["value_band"] = pd.cut(d.order_value, [0, 450, 800, 1500, 1e9], labels=["<450", "450-800", "800-1500", "1500+"]).astype(str)
    d["hour_band"] = pd.cut(d.order_datetime.dt.hour, [-1, 5, 11, 17, 23], labels=["night", "morning", "afternoon", "evening"]).astype(str)
    return d, pin_map

FEATS = ["city", "prior_rto_band", "new_cust", "value_band", "utm_source", "courier", "hour_band",
         "junk_name", "junk_addr", "bad_phone", "no_pin", "pin_mismatch"]
LABEL = {"city": "city history", "prior_rto_band": "past returns by this customer", "new_cust": "first-time customer",
         "value_band": "order value", "utm_source": "traffic source", "courier": "courier", "hour_band": "order time",
         "junk_name": "fake-looking name", "junk_addr": "junk/short address", "bad_phone": "invalid phone",
         "no_pin": "missing pincode", "pin_mismatch": "pincode doesn't match city"}

def logit(p): return math.log(p / (1 - p))
def sigmoid(x): return 1 / (1 + math.exp(-x))

class RiskModel:
    """Smoothed log-odds model. Transparent: every driver can be read off."""
    def __init__(self, k=25, shrink=0.55): self.k, self.shrink = k, shrink
    def fit(self, d):
        self.base = d.rto.mean(); self.tab = {}
        for f in FEATS:
            g = d.groupby(f).rto.agg(["sum", "count"])
            rate = (g["sum"] + self.k * self.base) / (g["count"] + self.k)
            self.tab[f] = {str(i): logit(r) - logit(self.base) for i, r in rate.items()}
        return self
    def explain(self, row):
        parts = {f: self.shrink * self.tab[f].get(str(row[f]), 0.0) for f in FEATS}
        z = logit(self.base) + sum(parts.values())
        return sigmoid(z), parts, z

_cache = {}
def llm_address_check(addr, name, city, use_llm=False):
    """Judge address deliverability. LLM if enabled (reads Hinglish); else cheap heuristic."""
    key = (addr, city)
    if key in _cache: return _cache[key]
    res = None
    if use_llm and os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            m = anthropic.Anthropic().messages.create(
                model="claude-haiku-4-5", max_tokens=120,
                messages=[{"role": "user", "content": f"Indian delivery address (may be Hinglish). City: {city}. Address: {addr!r}. Name: {name!r}.\n"
                           'Reply JSON only: {"deliverable": true or false, "reason": "under 8 words"}'}])
            j = json.loads(m.content[0].text.strip().strip("`").replace("json", "", 1))
            res = {"deliverable": bool(j["deliverable"]), "reason": j["reason"]}
        except Exception:
            res = None
    if res is None:
        ok = bool(re.search(r"\d", addr)) or len(addr.split()) >= 4
        res = {"deliverable": ok, "reason": "has house/landmark detail" if ok else "too vague to find"}
    _cache[key] = res
    return res

def decide(row, model, cfg, use_llm=False):
    t, mk, c = cfg["thresholds"], cfg["marketing_guard"], cfg["costs"]
    p, parts, z = model.explain(row)
    reasons = []
    # LLM only where it can change the outcome: gray zone with a non-trivial address
    if t["ship_as_is_below"] * 0.6 < p < t["confirm_below"] and not row["junk_addr"]:
        a = llm_address_check(row["address"], row["customer_name"], row["city"], use_llm)
        if not a["deliverable"]:
            z += 0.7; p = sigmoid(z); reasons.append(f"address hard to deliver ({a['reason']})")
    for f, v in sorted(parts.items(), key=lambda kv: -kv[1])[:2]:
        if v > 0.25: reasons.append(f"{LABEL[f]} raises risk")
    cost = rto_cost(cfg)
    margin = c["gross_margin"] * row["order_value"]
    junk_pair = bool(row["junk_name"] and (row["junk_addr"] or row["bad_phone"]))
    paid_new = bool(row["new_cust"] and row["utm_source"] in ADS)
    value_at_stake = margin + (mk["new_customer_extra_value"] if row["new_cust"] else 0)
    hold_ok = p * cost > (1 - p) * value_at_stake
    if junk_pair:
        action = "HOLD"; reasons.insert(0, "name and address both look fake - likely test/prank order")
    elif p < t["ship_as_is_below"]:
        action = "SHIP"; reasons.insert(0, "low return risk")
    elif p < t["nudge_prepaid_below"]:
        action = "NUDGE"; reasons.insert(0, "moderate risk - a small prepaid discount costs less than a likely return")
    elif p < t["confirm_below"] or not hold_ok:
        action = "CONFIRM"; reasons.insert(0, "high risk - confirm on WhatsApp before shipping")
        if p >= t["confirm_below"]: reasons.append("order profit outweighs expected loss, so not cancelling")
    else:
        action = "HOLD"; reasons.insert(0, "very high risk and expected loss exceeds the profit")
    if action == "HOLD" and paid_new and mk["never_cancel_new_customers_from_ads"] and not junk_pair:
        action = "CONFIRM"; reasons.append("new customer we paid to acquire - confirm instead of cancel")
    return {"p_rto": round(p, 3), "action": action, "reason": "; ".join(reasons),
            "expected_loss_if_shipped": round(p * cost, 1)}

def prepaid_offer(p, order_value, cfg):
    d, c = cfg["prepaid_discount"], cfg["costs"]
    saving = (p - c["prepaid_rto_rate"]) * rto_cost(cfg)
    disc = max(d["min_rupees"], min(d["share_of_saving"] * saving, d["max_pct_of_order"] * order_value))
    return {"expected_saving": round(saving, 1), "discount": int(round(disc / 5) * 5)}
