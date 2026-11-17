# NSE V8 Type A EMA44 Pullback Backtest

Status: research implementation; not production validation.

## Scope and sequence
- Reads only `data/bhavcopy/` and `data/cache/delivery/`; makes no network calls and writes no cache files.
- Applies candidate-specific Delivery A OR B eligibility using the existing 30-calendar-day / minimum-five-valid-report rule.
- Applies 20-prior-official-session average traded value >= INR 1.5 crore.
- RVOL is calculated for description and retained as the existing Type A condition (<=1.5), not as a separate universe rejection.
- Type A technical conditions mirror the EMA44-only implementation: mature EMA44, close above EMA44, 1%-15% correction from prior 20-session high, close within 3% of EMA44, RVOL <=1.5, at least 3 of latest 5 volumes below prior-20-session average, and bullish candle (close > open, close > prior close, CLV >0.50).
- Entry is next official NSE session open, with entry slippage applied. No same-day close execution assumption.
- Reports 5/10/20-session gross/net close returns, MFE and MAE. Default assumptions: 30 bps round-trip costs plus 10 bps entry and 10 bps exit slippage; override via `EMA44_BT_ROUND_TRIP_COST_BPS`, `EMA44_BT_ENTRY_SLIPPAGE_BPS`, `EMA44_BT_EXIT_SLIPPAGE_BPS`.

## Critical limitations
- Historical cache contains EQ series, not a point-in-time official Mainboard universe. Survivorship and historical board-classification bias remain.
- No point-in-time fundamentals are available; fundamentals are not backtested.
- This module does not simulate structural stops, actual overhead-resistance targets, 2R qualification, gaps through stops, position sizing, portfolio concurrency or drawdown. It deliberately leaves StopPrice, TargetPrice and RiskReward empty rather than inventing them. The existing V8 structural risk engine must be integrated for a complete execution backtest.
- Daily signals may repeat/overlap; these are signal observations, not independent executed trades.
- Current cache ends 2026-11-16, so recent signals have incomplete forward horizons and are excluded from the relevant horizon metrics.
- Cost/slippage values are research assumptions, not a broker-specific fee schedule; run sensitivity scenarios before drawing conclusions.

## Run
`python ema44_type_a_backtest.py`

Reports:
- `outputs/ema44_type_a_backtest/cache_coverage.csv`
- `outputs/ema44_type_a_backtest/cache_file_issues.csv`
- `outputs/ema44_type_a_backtest/signals.csv`
- `outputs/ema44_type_a_backtest/comparison.csv`
- `outputs/ema44_type_a_backtest/rejection_counts.csv`

No Master Specification, live scanner, cache, or ECMS workflow is changed by this research module.
