# Decision log
- **Money-based HOLD rule** (hold only if p x RTO cost > (1-p) x profit): answers Ops with Rs, protects margin. Alt: flat probability cut-off - rejected, ignores order value.
- **Marketing guard**: new ad-sourced customers get CONFIRM not HOLD; adds Rs300 acquisition value to what a cancel destroys. Alt: ignore - rejected, wastes ad spend.
- **Smoothed log-odds model, not sklearn/GBM**: ~2k rows, every driver must be explainable in plain English to ops. Smoothing (k=25) stops tiny segments (e.g. one pincode) from dominating.
- **Time-split backtest** (train < last month, score last month): random split would leak repeat customers.
- **LLM only in gray zone**: cost + latency; clear cases don't need it. Heuristic fallback so the repo runs with no API key.
- **Silence after 24h**: CONFIRM -> cancel (non-response is a strong RTO signal); NUDGE -> ship as COD (they were only moderate risk).
- **Prepaid discount** = 70% of expected saving, capped 7% of order, min Rs20. At p=30%: saving = (0.30-0.04) x Rs169.4 = Rs44 -> offer Rs30 (~4.6% of Rs649). Keeps 30% of the saving as buffer; acceptance rate (30%) is an ASSUMPTION to be measured.
- **Data cleaning** (spotted in the sample): duplicate order_ids, mixed-case status (delivered/Rto), IN_TRANSIT rows, Rs0 orders, missing pincodes, 9-digit phones, pincode not matching city, near-duplicate orders (KT15xxxx ids minutes apart). Near-duplicate detection NOT yet implemented.
- **Known limitation**: backtest Rs figures rely on config assumptions (confirm catches 60%, etc.), not measured outcomes. First live month should replace them.
