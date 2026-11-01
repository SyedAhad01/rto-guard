# RTO Guard: COD order decision engine

Looks at every COD order before it ships and picks one of four actions: **ship as-is, ship after WhatsApp confirmation, nudge to prepaid, or hold/cancel**. Every decision comes with a plain-English reason.

## Run it (under 5 minutes)

```
git clone https://github.com/SyedAhad01/rto-guard.git
cd rto-guard
pip install -r requirements.txt
python run.py
```

This reads `data/orders_sample.csv` (tab- or comma-separated), trains on the earlier months, scores the last month, and writes:
- `out/dashboard.html`: the founder's morning screen (open it in a browser)
- `out/findings.txt`: data findings and the backtest table
- `out/backtest.csv`: every scored order with its action and reason

**WhatsApp chat simulator:**
```
python -m rto.whatsapp
```
If your terminal doesn't accept typing (Git Bash on Windows), pipe the replies instead:
```
printf 'confirm\nhaan\n' | python -m rto.whatsapp
printf 'confirm\nno\n' | python -m rto.whatsapp
printf 'confirm\nblah\nblah\n' | python -m rto.whatsapp
printf 'confirm\n/wait 24\n' | python -m rto.whatsapp
printf 'nudge\npay\n' | python -m rto.whatsapp
```

## Change the rules without touching code

Edit `config.yaml` (risk thresholds, discount rules, marketing guard, WhatsApp timings), save, and run `python run.py` again.

## Where the LLM is used, and where it isn't

| Task | Tool | Why |
|---|---|---|
| Return probability, thresholds, ₹ maths, discount | plain code | deterministic, free, easy to audit |
| Fake names (asdf, test, qwerty) | regex | a simple list does it |
| WhatsApp yes/no replies | keyword matching (English and Hinglish) | no LLM needed |
| Is this address deliverable? (Hinglish, vague landmarks) | LLM, only for borderline orders | meaning can't be judged by regex; skipping clear cases keeps cost near zero |

`python run.py --llm` turns the LLM check on (needs `pip install anthropic` and `ANTHROPIC_API_KEY`). Without a key it falls back to a simple rule. **The LLM path has not been tested against the live API.**

## Decision rules (rto/engine.py)

1. Each order gets a return-risk percentage from a smoothed log-odds model (city, past returns, order value, junk name/address, and so on).
2. Under 22% ship; 22–40% nudge to prepaid; 40–60% confirm on WhatsApp.
3. Hold only if expected return loss is bigger than the profit at stake (including ₹300 for a new customer), or if name and address are both fake.
4. First-time customers from ads are confirmed, never auto-cancelled, unless the order is junk.

## Backtest (September, trained on April–August)

| Action | Orders | Actually returned |
|---|---|---|
| Ship as-is | 94 | 9% |
| Nudge | 210 | 29% |
| Confirm | 19 | 63% |
| Hold | 6 | 83% |

Estimated net impact: +₹2,111 on 329 orders, after counting the ₹300 ad cost of every genuine new customer who is held or confirmed away. These ₹ figures use assumptions in `config.yaml` (confirmation stops 60% of would-be returns, 30% accept the prepaid offer), not measured results.

## Files

- `rto/engine.py`: cleaning, model, decision rules, prepaid discount maths
- `rto/whatsapp.py`: message flow and simulator
- `run.py`: backtest, findings, dashboard
- `config.yaml`: all thresholds
- `DECISIONS.md`: choices and alternatives
- `AI_USAGE_LOG.md`: AI tools used and where they went wrong
- `scripts/make_synthetic.py`: fake data for testing only

## Known limitations

Thresholds are tuned on one month (329 orders). Near-duplicate orders are not detected. Acceptance rates are assumed, not measured.