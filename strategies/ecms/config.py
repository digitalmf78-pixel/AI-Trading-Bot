"""ECMS research configuration. No order execution is implemented here."""
from pathlib import Path

STRATEGY_NAME = "EOD Catalyst Momentum Scanner"
STRATEGY_CODE = "ECMS"
TIMEZONE = "Asia/Kolkata"

# Existing shared production/cache inputs. Consumers must treat these as read-only.
SHARED_READ_ONLY_PATHS = (
    "data/bhavcopy/",
    "data/cache/delivery/",
    "data/cache/sector_index_daily/",
    "data/cache/sector_constituents/",
    "data/cache/sector_quote_classifications/",
    "data/cache/universe/",
    "data/inputs/sector_map.csv",
    "data/inputs/sector_history.csv",
    "data/inputs/fundamental_metrics.csv",
    "data/cache/fundamental_history/",
    "data/cache/telegram_premarket_news_seen.csv",
    "data/cache/xbrl_samples/",
    "data/cache/xbrl_period_pairs/",
    "data/cache/shareholding_xbrl/",
    "outputs/v8_official_financial_results_filings.csv",
)

ECMS_OUTPUT_DIR = Path("outputs/ecms")
ECMS_STATE_DIR = Path("data/cache/ecms")
RVOL_LOOKBACK_SESSIONS = 20
EOD_RVOL_MIN = 1.5
CATALYST_LOOKBACK_CALENDAR_DAYS = 5
MORNING_SCAN_START = "09:15"
MORNING_CONFIRMATION_START = "09:25"
MORNING_CONFIRMATION_TARGET = "09:30"
SCORE_WEIGHTS = {
    "fundamental": 30,
    "catalyst": 30,
    "volume_price": 25,
    "sector_market": 15,
}
assert sum(SCORE_WEIGHTS.values()) == 100
FAIL_CLOSED_STATUSES = ("WAIT_FOR_DATA", "UNVERIFIED", "STALE_DATA")
AUTO_ORDER_EXECUTION = False