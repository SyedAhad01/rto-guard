# AI usage log
Tools: Claude (design, code, README drafts).
TODO before submitting - add 2-3 real examples from your own run. Candidates that actually happened while building:
1. Shell `mkdir -p {a,b}` brace expansion failed silently (created a literal folder) -> caught when `cat > rto/engine.py` errored; fixed with explicit dirs.
2. First synthetic backtest showed HOLD losing money -> reminder that backtest on fake data proves nothing; thresholds must be tuned on the real CSV, not on synthetic output.
3. (add yours: any wrong number or claim the AI made that you checked against the data)
