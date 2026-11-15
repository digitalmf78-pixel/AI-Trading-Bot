"""ECMS-only wrapper around no-key fundamentals sources.

The shared provider library's MoneyControl.get_ticker() can return the first
search result's sc_id alongside the full, multi-result search payload when its
exact stock_name lookup misses. This adapter selects one exact issuer hit and
returns that hit's own sc_id, preventing a different company's ID from being
used by the ECMS research workspace.
"""
from __future__ import annotations

import re
from typing import Any


def _identity_key(value: Any) -> str:
    value = re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())
    for suffix in ("private", "limited", "ltd"):
        value = value.replace(suffix, "")
    return value


def _select_exact_moneycontrol_hit(symbol: str, company_name: str | None, raw_hits: Any) -> dict | None:
    """Return exactly one result matching the NSE symbol or exact company name."""
    items = raw_hits if isinstance(raw_hits, list) else [raw_hits]
    expected_name = _identity_key(company_name)
    symbol_keys = ("ticker", "symbol", "nse_code", "nse_symbol", "nseCode", "symbol_code")
    name_keys = ("stock_name", "company_name", "company", "name", "security_name")
    matches = []
    for item in items:
        if not isinstance(item, dict):
            continue
        symbol_match = any(
            str(item.get(key, "")).strip().upper() == str(symbol).strip().upper()
            for key in symbol_keys
        )
        name_match = bool(expected_name) and any(
            _identity_key(item.get(key, "")) == expected_name for key in name_keys
        )
        if symbol_match or name_match:
            matches.append(item)
    # Ambiguous or absent identities are not safe enough to query fundamentals.
    if len(matches) != 1:
        return None
    hit = matches[0]
    if not str(hit.get("sc_id", "") or "").strip():
        return None
    return hit


def _strict_moneycontrol_factory(symbol: str, company_name: str | None):
    def factory():
        from Fundamentals import MoneyControl

        class ECMSMoneyControl:
            def __init__(self):
                self._client = MoneyControl()
                self.session = self._client.session

            def __getattr__(self, name):
                return getattr(self._client, name)

            def get_ticker(self, search_text: str):
                _library_selected_id, raw_hits = self._client.get_ticker(search_text)
                hit = _select_exact_moneycontrol_hit(symbol, company_name, raw_hits)
                if hit is None:
                    return "", raw_hits
                # Always use the ID from the exact matched result, never the
                # library's potentially unrelated first-result ID.
                return str(hit["sc_id"]), hit

        return ECMSMoneyControl()

    return factory


def fetch_ecms_free_fundamental_sources(
    symbol: str,
    *,
    company_name: str | None = None,
    missing_metrics=None,
    pause_seconds: float = 0.5,
) -> dict:
    """Fetch no-key data with ECMS-specific strict MoneyControl identity matching."""
    from free_fundamental_sources import fetch_free_fundamental_sources
    from nse_shareholding import fetch_nse_shareholding_metrics

    factories = {
        "moneycontrol": _strict_moneycontrol_factory(symbol, company_name),
        "nse_shareholding": fetch_nse_shareholding_metrics,
    }
    return fetch_free_fundamental_sources(
        symbol,
        company_name=company_name,
        missing_metrics=missing_metrics,
        pause_seconds=pause_seconds,
        source_factories=factories,
        capture_metric_source_urls=True,
    )
