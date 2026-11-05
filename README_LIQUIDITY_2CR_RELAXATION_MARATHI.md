# NSE V8 — Liquidity levels

- Liquidity uses average NSE CM Bhavcopy traded value from the prior 20 complete sessions.
- Minimum eligible level is ₹1.5 crore/day, mildly relaxed from ₹2 crore.
- ₹1.5–2 crore = LOW; ₹2–5 crore = MEDIUM; ₹5 crore and above = STRONG.
- Missing sessions or traded-value fields remain WAIT_FOR_DATA; no estimated liquidity is used.
- All liquidity-passed stocks go to fundamental enrichment and appear in Telegram. Fundamental score 65+ is highlighted but is not a rejection gate.
