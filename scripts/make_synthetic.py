"""TEST-ONLY synthetic data with the same schema (so the repo runs without the real CSV)."""
import numpy as np, pandas as pd
r = np.random.default_rng(1); n = 2000
cities = {"Delhi": "11", "Mumbai": "40", "Patna": "80", "Darbhanga": "84", "Bengaluru": "56", "Pune": "41"}
risk = {"Delhi": .3, "Mumbai": .27, "Patna": .5, "Darbhanga": .6, "Bengaluru": .25, "Pune": .22}
c = r.choice(list(cities), n); prior = r.choice([0, 0, 0, 1, 3], n); prto = np.where(prior > 1, r.choice([0, 1, 2], n), 0)
junk = r.random(n) < .05
p = np.array([risk[x] for x in c]) + 0.15 * (prto > 0) + 0.3 * junk
df = pd.DataFrame({"order_id": [f"KT{100000+i}" for i in range(n)],
    "order_datetime": pd.to_datetime("2026-04-01") + pd.to_timedelta(r.integers(0, 183 * 24 * 60, n), unit="m"),
    "customer_name": np.where(junk, "xyz xyz", "Priya Sharma"), "phone": r.integers(6e9, 9.9e9, n).astype(str),
    "address": np.where(junk, "xyz", "Flat 12, Green Park Apartments, MG Road"), "city": c,
    "state": "X", "pincode": [cities[x] + str(r.integers(1000, 9999)) for x in c], "order_value": r.choice([299, 449, 649, 998, 1497, 2999], n),
    "items": "Hair Oil 100ml", "num_items": 1, "customer_prior_orders": prior, "customer_prior_rto": prto,
    "utm_source": r.choice(["meta_ads", "google_ads", "direct"], n), "courier": r.choice(["Delhivery", "BlueDart"], n),
    "payment_method": "COD", "final_status": np.where(r.random(n) < np.clip(p, 0, .95), "RTO", "DELIVERED")})
df.sort_values("order_datetime").to_csv("data/orders_synthetic.csv", index=False)
