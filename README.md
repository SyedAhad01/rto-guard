# RTO Guard - COD order decision engine

Setup (<5 min):
```
pip install -r requirements.txt
cp /path/to/orders_sample.csv data/orders_sample.csv
python run.py                 # backtest last month -> out/dashboard.html, out/findings.txt, out/backtest.csv
python run.py --llm           # also use Claude for address checks (export ANTHROPIC_API_KEY first)
python -m rto.whatsapp        # interactive WhatsApp chat simulator
```
No real CSV yet? `python scripts/make_synthetic.py && python run.py --csv data/orders_synthetic.csv` (test data only; numbers mean nothing).

**Change thresholds without code:** edit `config.yaml` (risk cut-offs, discount rules, marketing guard) and re-run.

## Where the LLM is (and isn't) used
| Task | Tool | Why |
|---|---|---|
| RTO probability, thresholds, Rs maths, discount | plain code | deterministic, auditable, free |
| Is this address deliverable? (Hinglish, "ph krke aana") | LLM, only for orders in the gray zone | regex can't judge meaning; skipping clear ship/hold cases keeps cost near zero |
| Fake names (asdf, test) | regex | simple list works |
| WhatsApp reply yes/no | keywords (Hinglish list) | LLM only worth adding for the "random reply" bucket |

## Decision rules (all in rto/engine.py)
p(RTO) -> SHIP / NUDGE / CONFIRM / HOLD by thresholds. HOLD only if expected RTO loss > profit at stake (incl. Rs300 value for new customers). New ad-acquired customers are confirmed, never auto-cancelled, unless name+address are both junk.
Model is trained on months before the scored month (no leakage).
