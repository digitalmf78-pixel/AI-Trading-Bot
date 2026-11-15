"""Gemini-assisted, evidence-aware research for ECMS Volume Gainers.

This is an optional research layer. It does not alter the strict fundamental
shortlist, official XBRL verification, or trading decisions.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

INPUT_PATH = Path("outputs/ecms/volume_gainers_eod_research.csv")
NEWS_PATH = Path("outputs/ecms/volume_gainers_catalysts.csv")
OUTPUT_DIR = Path("outputs/ecms_gemini")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.8-flash"
MAX_SYMBOLS = 25
TIMEOUT = (15, 90)
OMIT_COLUMNS = {
    "MetricSourcesJSON", "MetricSourceURLsJSON", "MetricSourcePeriodsJSON",
    "MetricSourceCurrenciesJSON", "ProviderSourceDiagnosticsJSON",
    "FreeSourcesDiagnosticsJSON", "FreeSourcesAlternatesJSON",
}


def clean(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def row_payload(row: pd.Series) -> dict:
    return {
        str(key): clean(value)
        for key, value in row.items()
        if str(key) not in OMIT_COLUMNS and clean(value) is not None
    }


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Gemini response did not contain a JSON object")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Gemini response JSON root must be an object")
    return value


def research_prompt(stock: dict, news: list[dict]) -> str:
    return """You are an evidence-first Indian equity fundamental research analyst.
Analyze this NSE-listed company for a 2-4 week swing-trading research shortlist.
This is research, NOT a buy/sell recommendation.

STRICT RULES:
- Treat supplied financial metrics as data, not automatically as official facts.
- Distinguish official-verified, third-party/provider, and unavailable values.
- Use Google Search to check the latest company announcements, quarterly/annual
  results, exchange filings, credible business news, sector developments and
  material risks. Prefer NSE/BSE/company investor-relations sources.
- Focus on the latest 5 calendar days for news/announcements, and state dates.
- Never invent figures, dates, source URLs, management guidance or events.
- If sources conflict, explain the conflict. If evidence is unavailable, say so.
- High volume or RVOL is not a reason by itself to call a stock attractive.
- Consider whether the financial period is stale and whether valuation data
  is meaningful for this sector.
- Output ONLY one valid JSON object. No markdown fences or prose outside JSON.

Return this schema:
{
  "symbol": "NSE symbol",
  "company_name": "name",
  "research_classification": "STRONG|GOOD|AVERAGE|WEAK|INSUFFICIENT_DATA",
  "confidence": "HIGH|MEDIUM|LOW",
  "business_quality": "short assessment",
  "financial_strength": "short assessment with supplied figures and periods",
  "growth_and_profitability": "assessment",
  "debt_and_cashflow": "assessment",
  "valuation": "assessment or unavailable",
  "latest_results_and_announcements": "dated findings or unavailable",
  "last_5_days_news": "dated findings or unavailable",
  "sector_context": "assessment or unavailable",
  "positive_factors": ["..."],
  "negative_factors": ["..."],
  "red_flags": ["..."],
  "missing_or_unverified_data": ["..."],
  "evidence": [
    {"claim": "specific claim", "source_title": "title",
     "source_url": "https://...", "published_date": "YYYY-MM-DD or unknown"}
  ],
  "analyst_conclusion": "concise balanced conclusion",
  "not_a_trade_signal": true
}

A classification of STRONG requires multiple current, reliable sources and
credible financial strength. Use INSUFFICIENT_DATA rather than guessing.

STOCK DATA:
""" + json.dumps(stock, ensure_ascii=False, default=str) + """

EXISTING ECMS NEWS / CATALYST DATA:
""" + json.dumps(news, ensure_ascii=False, default=str)


def call_gemini(session: requests.Session, api_key: str, model: str,
                prompt: str) -> tuple[dict, list[dict]]:
    response = session.post(
        API_URL.format(model=model),
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 5000,
            },
        },
        headers={"x-goog-api-key": api_key},
        timeout=TIMEOUT,
    )
    if response.status_code == 429:
        raise RuntimeError("GEMINI_RATE_LIMIT: free-tier quota/rate limit reached")
    response.raise_for_status()
    payload = response.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates: " + json.dumps(payload)[:800])
    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts = [part.get("text", "") for part in parts if part.get("text")]
    if not text_parts:
        raise RuntimeError("Gemini response contained no text")
    result = extract_json("\n".join(text_parts))
    grounding = candidates[0].get("groundingMetadata", {}).get("groundingChunks", [])
    sources = []
    for item in grounding:
        web = item.get("web", {}) if isinstance(item, dict) else {}
        if web.get("uri"):
            sources.append({"title": web.get("title", ""), "url": web["uri"]})
    result["gemini_grounding_sources"] = sources
    return result, sources


def main() -> int:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY secret is missing. Add it in GitHub repository "
            "Settings > Secrets and variables > Actions, then rerun with AI research enabled."
        )
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"ECMS EOD input not found: {INPUT_PATH}")
    stocks = pd.read_csv(INPUT_PATH, keep_default_na=False)
    if "TckrSymb" not in stocks.columns or stocks.empty:
        raise RuntimeError("ECMS EOD input has no valid TckrSymb rows")
    stocks["TckrSymb"] = stocks["TckrSymb"].astype(str).str.strip().str.upper()
    stocks = stocks.drop_duplicates("TckrSymb", keep="first").head(MAX_SYMBOLS)

    news = pd.read_csv(NEWS_PATH, keep_default_na=False) if NEWS_PATH.exists() else pd.DataFrame()
    if not news.empty and "TckrSymb" in news.columns:
        news["TckrSymb"] = news["TckrSymb"].astype(str).str.strip().str.upper()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "User-Agent": "ECMS-Gemini-Research-Pilot/1.0"})
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    records, errors = [], []
    for index, (_, row) in enumerate(stocks.iterrows(), start=1):
        symbol = str(row["TckrSymb"])
        related_news = []
        if not news.empty and "TckrSymb" in news.columns:
            related_news = [
                row_payload(item)
                for _, item in news[news["TckrSymb"] == symbol].head(12).iterrows()
            ]
        print(f"[{index}/{len(stocks)}] Gemini research: {symbol}", flush=True)
        try:
            result, sources = call_gemini(
                session, api_key, model,
                research_prompt(row_payload(row), related_news),
            )
            result["symbol"] = symbol
            result["research_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
            result["research_model"] = model
            result["research_status"] = "COMPLETED"
            records.append(result)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {str(exc)[:700]}"})
            records.append({
                "symbol": symbol,
                "research_classification": "INSUFFICIENT_DATA",
                "confidence": "LOW",
                "research_status": "FAILED",
                "analyst_conclusion": "AI research did not complete; do not infer a result.",
                "error": f"{type(exc).__name__}: {str(exc)[:700]}",
            })
            if "GEMINI_RATE_LIMIT" in str(exc):
                for _, pending_row in list(stocks.iterrows())[index:]:
                    records.append({
                        "symbol": str(pending_row["TckrSymb"]),
                        "research_classification": "INSUFFICIENT_DATA",
                        "confidence": "LOW",
                        "research_status": "NOT_ATTEMPTED_RATE_LIMIT",
                        "analyst_conclusion": "Not attempted because Gemini free-tier quota/rate limit was reached.",
                    })
                break
        # Stay comfortably below typical free-tier request rates.
        time.sleep(1.3)

    json_path = OUTPUT_DIR / "gemini_research.json"
    csv_path = OUTPUT_DIR / "gemini_research_summary.csv"
    status_path = OUTPUT_DIR / "gemini_research_status.json"
    json_path.write_text(json.dumps(records, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    summary_rows = []
    for item in records:
        summary_rows.append({
            "TckrSymb": item.get("symbol"),
            "AIResearchClassification": item.get("research_classification", "INSUFFICIENT_DATA"),
            "AIResearchConfidence": item.get("confidence", "LOW"),
            "AIResearchStatus": item.get("research_status", "FAILED"),
            "BusinessQuality": item.get("business_quality", ""),
            "FinancialStrength": item.get("financial_strength", ""),
            "LatestNews": item.get("last_5_days_news", ""),
            "RedFlags": " | ".join(item.get("red_flags", []) if isinstance(item.get("red_flags"), list) else []),
            "MissingData": " | ".join(item.get("missing_or_unverified_data", []) if isinstance(item.get("missing_or_unverified_data"), list) else []),
            "AnalystConclusion": item.get("analyst_conclusion", ""),
            "GroundingSources": " | ".join(
                source.get("url", "") for source in item.get("gemini_grounding_sources", [])
                if isinstance(source, dict)
            ),
        })
    pd.DataFrame(summary_rows).to_csv(csv_path, index=False)
    status = {
        "status": "PASS" if not errors else "PARTIAL" if len(errors) < len(stocks) else "FAILED",
        "input_stock_count": int(len(stocks)),
        "completed_count": int(sum(item.get("research_status") == "COMPLETED" for item in records)),
        "failed_count": len(errors),
        "model": model,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
        "note": "AI research is supplementary; it does not change ECMS strict shortlist or official XBRL verification.",
    }
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0 if not errors else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
