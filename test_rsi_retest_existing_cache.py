from pathlib import Path
import pandas as pd
from rsi_retest_existing_cache import add_indicators, add_signals, delivery_gate, run_trade_simulation


def test_ema50_requires_50_closes_and_rsi_available_after_warmup():
    dates = pd.bdate_range('2026-01-01', periods=60)
    close = [100 + i * 0.2 + (i % 4) for i in range(60)]
    df = pd.DataFrame({'Date': dates, 'Symbol': 'ABC', 'Open': close, 'High': [x+2 for x in close], 'Low': [x-2 for x in close], 'Close': close})
    out = add_indicators(df)
    assert out['EMA50'].iloc[:49].isna().all()
    assert pd.notna(out['EMA50'].iloc[49])
    assert pd.notna(out['RSI14'].iloc[-1])


def test_delivery_gate_requires_exact_five_dates_and_each_day_at_least_60():
    dates = pd.bdate_range('2026-01-01', periods=6)
    prices = pd.DataFrame({'Date': dates, 'Symbol': 'ABC'})
    delivery = pd.DataFrame({'Date': list(dates[1:6]), 'Symbol': 'ABC', 'DeliveryPct': [60.0, 61.0, 60.0, 75.0, 60.0]})
    out = delivery_gate(prices, delivery)
    assert out.iloc[4]['Delivery5Status'] == 'WAIT_FOR_DATA'  # only four prior sessions have report rows
    assert out.iloc[5]['Delivery5Pass'] is True or bool(out.iloc[5]['Delivery5Pass'])
    delivery.loc[delivery['Date'].eq(dates[3]), 'DeliveryPct'] = 59.99
    out2 = delivery_gate(prices, delivery)
    assert out2.iloc[5]['Delivery5Status'] == 'REJECT'


def test_trade_simulation_uses_next_open_and_conservative_stop_first():
    dates = pd.bdate_range('2026-01-01', periods=25)
    df = pd.DataFrame({'Date': dates, 'Symbol': 'ABC', 'Open': [100]*25, 'High': [101]*25, 'Low': [99]*25, 'Close': [100]*25, 'SIG': [False]*25})
    df.loc[0, 'SIG'] = True
    df.loc[1, 'High'] = 110
    df.loc[1, 'Low'] = 98
    # signal-day stop is 99; entry 100; target 102. Both touched on entry day => stop first.
    trades = run_trade_simulation(df, 'SIG', max_hold=20)
    assert len(trades) == 1
    assert trades.iloc[0]['ExitReason'] == 'STOP_LOSS'
    assert trades.iloc[0]['RMultiple'] == -1


def test_signals_are_false_below_ema50():
    dates = pd.bdate_range('2026-01-01', periods=70)
    close = [100 + i * 0.1 + (i % 3) for i in range(70)]
    df = pd.DataFrame({'Date': dates, 'Symbol': 'ABC', 'Open': close, 'High': [x+1 for x in close], 'Low': [x-1 for x in close], 'Close': close})
    out = add_signals(add_indicators(df))
    assert not (out.loc[~out['AboveEMA50'], ['RSI30_RECOVERY','RSI40_RETEST','RSI50_RETEST']].any().any())
