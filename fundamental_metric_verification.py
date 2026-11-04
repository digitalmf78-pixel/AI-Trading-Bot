"""Fail-closed audit of cached fundamental metrics against official NSE XBRL evidence.

This module is read-only with respect to the fundamental cache.  It never
changes a metric, infers a calculation basis, or upgrades a value merely because
an NSE filing URL/publication date exists.  A metric is marked
OFFICIAL_XBRL_VERIFIED only when a separately recorded evidence row points to a
local XML file whose SHA-256, XBRL context, entity, period, unit, namespace,
contextRef and numeric fact all match the cached value.

The first implementation intentionally supports DIRECT_FACT_MATCH only.
Derived ratios/growth metrics require a future component-level reconciliation
engine and remain pending rather than being guessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('.')
METRICS_PATH = Path('data/inputs/fundamental_metrics.csv')
FILINGS_PATH = Path('outputs/v8_official_financial_results_filings.csv')
EVIDENCE_PATH = Path('data/inputs/fundamental_metric_verification_evidence.csv')
OUTPUT_DIR = Path('outputs')
DETAILS_PATH = OUTPUT_DIR / 'v8_fundamental_metric_verification.csv'
SUMMARY_PATH = OUTPUT_DIR / 'v8_fundamental_metric_verification_summary.csv'
FILING_SUMMARY_PATH = OUTPUT_DIR / 'v8_fundamental_filing_metadata_summary.csv'

# Metrics used by the shortlist plus persisted TTM totals.  Status/text fields
# are deliberately excluded.
DIRECT_FACT_ALLOWED_METRICS = {'OperatingCashFlowINR'}  # annual statement fact only; all ratios/growth/FCF/TTM are derived
DIRECT_FACT_TAGS = {'OperatingCashFlowINR': {'CashFlowsFromUsedInOperatingActivities'}}
NUMERIC_METRICS = [
    'RevenueGrowthPct', 'ProfitGrowthPct', 'ROEPercent', 'ROCEPercent',
    'DebtToEquity', 'InterestCoverage', 'OperatingCashFlowINR',
    'FreeCashFlowINR', 'RevenueTTMINR', 'PreviousRevenueTTMINR',
    'NetProfitTTMINR', 'PreviousNetProfitTTMINR', 'EBITTTMINR',
    'InterestExpenseTTMINR',
]
EVIDENCE_COLUMNS = [
    'TckrSymb', 'MetricName', 'ProviderMetricValue', 'OfficialMetricValue',
    'Tolerance', 'FinancialPeriodEnd', 'PublicationDate',
    'MetricCalculationBasis', 'OfficialFilingURL', 'XbrlFactTag',
    'XbrlContextRef', 'EntityIdentifier', 'EntityIdentifierScheme',
    'UnitMeasure', 'TaxonomyNamespace', 'PeriodStart', 'PeriodEnd',
    'DimensionsJSON', 'EvidenceFilePath', 'EvidenceSHA256',
    'VerificationMethod', 'EvidenceDetailsJSON',
]


def _clean(value: Any) -> str:
    if value is None or value is pd.NA:
        return ''
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _number(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _local(tag: str) -> str:
    return str(tag).rsplit('}', 1)[-1]


def _namespace(tag: str) -> str:
    return tag[1:].split('}', 1)[0] if tag.startswith('{') else ''


def _normal_dimensions(context: ET.Element) -> str:
    dims = []
    for node in context.iter():
        local = _local(node.tag).lower()
        if local in {'explicitmember', 'typedmember'}:
            dims.append({
                'kind': local,
                'dimension': node.attrib.get('dimension', ''),
                'value': ''.join(node.itertext()).strip(),
            })
    return json.dumps(sorted(dims, key=lambda x: (x['dimension'], x['kind'], x['value'])), separators=(',', ':'))


def _parse_xbrl(path: Path) -> tuple[dict[str, dict], dict[str, str], list[ET.Element]]:
    root = ET.parse(path).getroot()
    contexts: dict[str, dict] = {}
    units: dict[str, str] = {}
    for node in root.iter():
        local = _local(node.tag).lower()
        if local == 'context':
            cid = node.attrib.get('id', '')
            identifier = next((x for x in node.iter() if _local(x.tag).lower() == 'identifier'), None)
            start = next((x for x in node.iter() if _local(x.tag).lower() == 'startdate'), None)
            end = next((x for x in node.iter() if _local(x.tag).lower() == 'enddate'), None)
            instant = next((x for x in node.iter() if _local(x.tag).lower() == 'instant'), None)
            contexts[cid] = {
                'EntityIdentifier': (identifier.text or '').strip() if identifier is not None else '',
                'EntityIdentifierScheme': identifier.attrib.get('scheme', '') if identifier is not None else '',
                'PeriodStart': (start.text or '').strip() if start is not None else '',
                'PeriodEnd': (end.text or '').strip() if end is not None else ((instant.text or '').strip() if instant is not None else ''),
                'DimensionsJSON': _normal_dimensions(node),
            }
        elif local == 'unit':
            uid = node.attrib.get('id', '')
            measures = [(x.text or '').strip() for x in node.iter() if _local(x.tag).lower() == 'measure']
            units[uid] = '*'.join(measures)
    facts = [node for node in root.iter() if node.attrib.get('contextRef')]
    return contexts, units, facts


def _filing_metadata_status(metric: pd.Series, filings: pd.DataFrame) -> tuple[str, str]:
    symbol = _clean(metric.get('TckrSymb')).upper()
    period = _clean(metric.get('FinancialPeriodEnd'))[:10]
    url = _clean(metric.get('OfficialFilingURL'))
    pub = _clean(metric.get('PublicationDate'))[:10]
    if not url:
        reason = 'OfficialFilingURL is empty'
        register_keys = {'TckrSymb', 'FinancialPeriodEnd', 'OfficialFilingURL'}
        if not filings.empty and register_keys.issubset(filings.columns):
            same_symbol = filings[
                filings['TckrSymb'].astype(str).str.upper().eq(symbol)
            ]
            same_period = same_symbol[
                same_symbol['FinancialPeriodEnd'].astype(str).str[:10].eq(period)
            ]
            if len(same_period):
                candidate_urls = ';'.join(
                    same_period['OfficialFilingURL'].astype(str).drop_duplicates().head(5).tolist()
                )
                reason += (
                    f'; exact symbol/period candidate rows={len(same_period)}'
                    f'; candidate URLs={candidate_urls}'
                )
            elif len(same_symbol):
                periods = ';'.join(
                    same_symbol['FinancialPeriodEnd'].astype(str).str[:10].drop_duplicates().head(5).tolist()
                )
                reason += (
                    f'; no exact symbol/period filing in register'
                    f'; other registered periods={periods}'
                )
            else:
                reason += '; symbol not present in official filing register'
        return 'FILING_URL_MISSING', reason
    if filings.empty:
        return 'FILING_REGISTER_UNAVAILABLE', 'Official filing register is missing or empty'
    required = {'TckrSymb', 'FinancialPeriodEnd', 'PublicationDate', 'PublicationDateStatus', 'OfficialFilingURL'}
    if not required.issubset(filings.columns):
        return 'FILING_REGISTER_SCHEMA_INVALID', 'Required official filing register columns are missing'
    subset = filings[
        filings['TckrSymb'].astype(str).str.upper().eq(symbol)
        & filings['FinancialPeriodEnd'].astype(str).str[:10].eq(period)
        & filings['OfficialFilingURL'].astype(str).eq(url)
    ]
    if len(subset) != 1:
        same_period = filings[
            filings['TckrSymb'].astype(str).str.upper().eq(symbol)
            & filings['FinancialPeriodEnd'].astype(str).str[:10].eq(period)
        ]
        candidates = ';'.join(same_period['OfficialFilingURL'].astype(str).drop_duplicates().head(5).tolist())
        reason = f'Expected exactly one symbol/period/URL filing row; found {len(subset)}'
        if len(subset) == 0 and len(same_period):
            reason += f'; same-symbol-period candidate rows={len(same_period)}; candidate URLs={candidates}'
        return ('FILING_REGISTER_DUPLICATE_EXACT_MATCH' if len(subset) > 1 else 'FILING_NOT_FOUND_EXACT_MATCH', reason)
    f = subset.iloc[0]
    if _clean(f.get('PublicationDate'))[:10] != pub:
        return 'FILING_PUBLICATION_DATE_MISMATCH', 'Cache publication date differs from exact official filing row'
    if _clean(f.get('PublicationDateStatus')).upper() != 'VERIFIED':
        return 'FILING_PUBLICATION_DATE_NOT_VERIFIED', 'Official filing register does not mark publication date VERIFIED'
    if not url.startswith('https://nsearchives.nseindia.com/corporate/xbrl/'):
        return 'FILING_URL_NOT_OFFICIAL_XBRL_HOST', 'Filing URL is not on the NSE archives XBRL host/path'
    return 'OFFICIAL_FILING_METADATA_MATCHED', 'Exact symbol, period, URL and publication date matched; this does not verify metric values'


def _match_evidence(metric: pd.Series, metric_name: str, evidence: pd.DataFrame,
                    repo_root: Path) -> tuple[str, str, dict]:
    symbol = _clean(metric.get('TckrSymb')).upper()
    period = _clean(metric.get('FinancialPeriodEnd'))[:10]
    pub = _clean(metric.get('PublicationDate'))[:10]
    basis = _clean(metric.get('MetricCalculationBasis')).upper()
    url = _clean(metric.get('OfficialFilingURL'))
    if metric_name not in DIRECT_FACT_ALLOWED_METRICS or basis != 'ANNUAL_ALIGNED_STATEMENTS':
        return 'DERIVED_RECONCILIATION_REQUIRED', 'Only annual OperatingCashFlowINR is eligible for direct-fact verification; this metric/basis requires component-level reconciliation', {}
    if evidence.empty:
        return 'PROVIDER_ONLY', 'No metric-level XBRL evidence row exists', {}
    needed = set(EVIDENCE_COLUMNS)
    if not needed.issubset(evidence.columns):
        return 'EVIDENCE_LEDGER_SCHEMA_INVALID', 'Evidence ledger is missing required columns', {}
    candidates = evidence[
        evidence['TckrSymb'].astype(str).str.upper().eq(symbol)
        & evidence['MetricName'].astype(str).eq(metric_name)
        & evidence['FinancialPeriodEnd'].astype(str).str[:10].eq(period)
        & evidence['PublicationDate'].astype(str).str[:10].eq(pub)
        & evidence['MetricCalculationBasis'].astype(str).str.upper().eq(basis)
        & evidence['OfficialFilingURL'].astype(str).eq(url)
    ]
    if len(candidates) == 0:
        return 'PROVIDER_ONLY', 'No exact symbol/metric/period/basis/filing evidence match', {}
    if len(candidates) != 1:
        return 'EVIDENCE_DUPLICATE_MATCH', f'Expected one exact evidence row; found {len(candidates)}', {}
    ev = candidates.iloc[0].to_dict()
    if _clean(ev.get('VerificationMethod')).upper() != 'DIRECT_FACT_MATCH':
        return 'DERIVED_RECONCILIATION_REQUIRED', 'Only DIRECT_FACT_MATCH is supported; derived metrics need component-level reconciliation', ev
    details = _clean(ev.get('EvidenceDetailsJSON'))
    try:
        parsed_details = json.loads(details)
    except (TypeError, ValueError):
        return 'EVIDENCE_DETAILS_INVALID', 'EvidenceDetailsJSON must be valid JSON', ev
    if not isinstance(parsed_details, dict) or not parsed_details:
        return 'EVIDENCE_DETAILS_INVALID', 'EvidenceDetailsJSON must be a non-empty object', ev

    required_text = ['XbrlFactTag', 'XbrlContextRef', 'EntityIdentifier', 'EntityIdentifierScheme',
                     'UnitMeasure', 'TaxonomyNamespace', 'PeriodStart', 'PeriodEnd', 'EvidenceFilePath', 'EvidenceSHA256']
    missing = [k for k in required_text if not _clean(ev.get(k))]
    if missing:
        return 'EVIDENCE_FIELDS_MISSING', 'Missing: ' + ','.join(missing), ev
    if _clean(ev.get('DimensionsJSON')) == '':
        return 'EVIDENCE_FIELDS_MISSING', 'DimensionsJSON must explicitly be [] or a dimension list', ev

    evidence_path = (repo_root / _clean(ev['EvidenceFilePath'])).resolve()
    try:
        evidence_path.relative_to(repo_root.resolve())
    except ValueError:
        return 'EVIDENCE_PATH_OUTSIDE_REPOSITORY', 'Evidence file path must remain inside repository', ev
    if not evidence_path.is_file():
        return 'EVIDENCE_FILE_MISSING', f'XBRL evidence file not found: {ev["EvidenceFilePath"]}', ev
    digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    if digest.lower() != _clean(ev['EvidenceSHA256']).lower():
        return 'EVIDENCE_SHA256_MISMATCH', 'XBRL evidence file SHA-256 differs from evidence ledger', ev

    try:
        contexts, units, facts = _parse_xbrl(evidence_path)
    except (ET.ParseError, OSError) as exc:
        return 'XBRL_XML_INVALID', f'{type(exc).__name__}: {exc}', ev
    context_ref = _clean(ev['XbrlContextRef'])
    context = contexts.get(context_ref)
    if context is None:
        return 'XBRL_CONTEXT_NOT_FOUND', 'XbrlContextRef does not exist in evidence XML', ev
    context_checks = {
        'EntityIdentifier': _clean(ev['EntityIdentifier']),
        'EntityIdentifierScheme': _clean(ev['EntityIdentifierScheme']),
        'PeriodStart': _clean(ev.get('PeriodStart')),
        'PeriodEnd': _clean(ev['PeriodEnd']),
    }
    for key, expected in context_checks.items():
        if expected and context.get(key, '') != expected:
            return 'XBRL_CONTEXT_MISMATCH', f'{key} differs between ledger and XML context', ev
    try:
        expected_dims = json.loads(_clean(ev['DimensionsJSON']))
        actual_dims = json.loads(context['DimensionsJSON'])
    except ValueError:
        return 'EVIDENCE_DIMENSIONS_INVALID', 'DimensionsJSON must be valid JSON', ev
    if expected_dims != actual_dims:
        return 'XBRL_DIMENSIONS_MISMATCH', 'Dimension members differ between ledger and XML context', ev

    tag = _clean(ev['XbrlFactTag'])
    if tag not in DIRECT_FACT_TAGS.get(metric_name, set()):
        return 'XBRL_FACT_TAG_NOT_APPROVED_FOR_METRIC', f'{tag} is not an approved direct fact tag for {metric_name}', ev
    matching = [f for f in facts if _local(f.tag) == tag and f.attrib.get('contextRef') == context_ref]
    if len(matching) != 1:
        return 'XBRL_FACT_NOT_UNIQUE', f'Expected exactly one {tag} fact in context {context_ref}; found {len(matching)}', ev
    fact = matching[0]
    unit_ref = fact.attrib.get('unitRef', '')
    actual_unit = units.get(unit_ref, '')
    if actual_unit != _clean(ev['UnitMeasure']):
        return 'XBRL_UNIT_MISMATCH', 'Fact unit differs from evidence ledger', ev
    if not (actual_unit == 'INR' or actual_unit.endswith(':INR')):
        return 'XBRL_UNIT_NOT_CURRENCY_INR', f'OperatingCashFlowINR requires INR unit, got {actual_unit}', ev
    if _namespace(fact.tag) != _clean(ev['TaxonomyNamespace']):
        return 'XBRL_TAXONOMY_MISMATCH', 'Fact namespace differs from evidence ledger', ev
    try:
        fact_value = float((fact.text or '').strip())
        scale = int(fact.attrib.get('scale', '0') or 0)
        fact_value *= 10 ** scale
        if fact.attrib.get('sign') == '-':
            fact_value *= -1
    except (TypeError, ValueError, OverflowError):
        return 'XBRL_FACT_VALUE_INVALID', 'XBRL fact value/scale/sign is invalid', ev
    provider_value = _number(metric.get(metric_name))
    recorded_provider = _number(ev.get('ProviderMetricValue'))
    official_value = _number(ev.get('OfficialMetricValue'))
    tolerance = _number(ev.get('Tolerance'))
    tolerance = tolerance if tolerance is not None and tolerance >= 0 else 0.0
    if provider_value is None or recorded_provider is None or official_value is None:
        return 'EVIDENCE_VALUE_INVALID', 'Provider or official metric value is not numeric', ev
    if abs(provider_value - recorded_provider) > tolerance:
        return 'CACHE_VALUE_CHANGED_SINCE_EVIDENCE', 'Cached metric value differs from the evidence ledger', ev
    if abs(fact_value - official_value) > tolerance:
        return 'XBRL_FACT_VALUE_DIFFERS_FROM_LEDGER', 'XML fact value differs from OfficialMetricValue in ledger', ev
    if abs(provider_value - fact_value) > tolerance:
        return 'PROVIDER_VALUE_MISMATCH', 'Cached provider value does not match the official XBRL fact', ev
    return 'OFFICIAL_XBRL_VERIFIED', 'Exact direct fact, context, entity, period, dimensions, unit, taxonomy and SHA-256 matched', ev


def build_metric_verification(metrics: pd.DataFrame, filings: pd.DataFrame | None = None,
                              evidence: pd.DataFrame | None = None,
                              repo_root: str | Path = '.') -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    filings = filings if filings is not None else pd.DataFrame()
    evidence = evidence if evidence is not None else pd.DataFrame(columns=EVIDENCE_COLUMNS)
    root = Path(repo_root).resolve()
    rows = []
    for _, metric in metrics.iterrows():
        symbol = _clean(metric.get('TckrSymb')).upper()
        filing_status, filing_reason = _filing_metadata_status(metric, filings)
        for metric_name in NUMERIC_METRICS:
            value = _number(metric.get(metric_name))
            if value is None:
                continue
            if filing_status != 'OFFICIAL_FILING_METADATA_MATCHED':
                verification_status, verification_reason, ev = (
                    'FILING_METADATA_NOT_CONFIRMED',
                    'Exact official filing metadata must match before metric-level XBRL verification',
                    {},
                )
            else:
                verification_status, verification_reason, ev = _match_evidence(metric, metric_name, evidence, root)
            rows.append({
                'TckrSymb': symbol,
                'MetricName': metric_name,
                'CachedMetricValue': value,
                'MetricSource': _clean(metric.get('Source')),
                'FinancialPeriodEnd': _clean(metric.get('FinancialPeriodEnd'))[:10],
                'PublicationDate': _clean(metric.get('PublicationDate'))[:10],
                'PublicationDateStatus': _clean(metric.get('PublicationDateStatus')),
                'MetricCalculationBasis': _clean(metric.get('MetricCalculationBasis')),
                'MetricPeriodAlignmentStatus': _clean(metric.get('MetricPeriodAlignmentStatus')),
                'OfficialFilingURL': _clean(metric.get('OfficialFilingURL')),
                'FilingMetadataStatus': filing_status,
                'FilingMetadataReason': filing_reason,
                'MetricValueVerificationStatus': verification_status,
                'MetricValueVerificationReason': verification_reason,
                'EvidenceFilePath': _clean(ev.get('EvidenceFilePath')),
                'EvidenceSHA256': _clean(ev.get('EvidenceSHA256')),
                'XbrlFactTag': _clean(ev.get('XbrlFactTag')),
                'XbrlContextRef': _clean(ev.get('XbrlContextRef')),
            })
    detail = pd.DataFrame(rows)
    if detail.empty:
        summary = pd.DataFrame(columns=['MetricValueVerificationStatus', 'MetricCount', 'DistinctSymbols'])
        filing_summary = pd.DataFrame(columns=['FilingMetadataStatus', 'MetricRows', 'DistinctSymbols'])
    else:
        summary = (detail.groupby('MetricValueVerificationStatus', dropna=False)
                   .agg(MetricCount=('MetricName', 'size'), DistinctSymbols=('TckrSymb', 'nunique'))
                   .reset_index())
        filing_summary = (detail.drop_duplicates('TckrSymb').groupby('FilingMetadataStatus', dropna=False)
                          .agg(MetricRows=('MetricName', 'size'), DistinctSymbols=('TckrSymb', 'nunique'))
                          .reset_index())
    return detail, summary, filing_summary


def run_audit(metrics_path: str | Path = METRICS_PATH,
              filings_path: str | Path = FILINGS_PATH,
              evidence_path: str | Path = EVIDENCE_PATH,
              output_dir: str | Path = OUTPUT_DIR,
              repo_root: str | Path = '.') -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metrics_path, filings_path, evidence_path = Path(metrics_path), Path(filings_path), Path(evidence_path)
    if not metrics_path.exists():
        raise FileNotFoundError(f'Fundamental cache not found: {metrics_path}')
    metrics = pd.read_csv(metrics_path)
    filings = pd.read_csv(filings_path) if filings_path.exists() else pd.DataFrame()
    if evidence_path.exists():
        evidence = pd.read_csv(evidence_path, keep_default_na=False)
    else:
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=EVIDENCE_COLUMNS).to_csv(evidence_path, index=False)
        evidence = pd.DataFrame(columns=EVIDENCE_COLUMNS)
    detail, summary, filing_summary = build_metric_verification(metrics, filings, evidence, repo_root=repo_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output_dir / DETAILS_PATH.name, index=False)
    summary.to_csv(output_dir / SUMMARY_PATH.name, index=False)
    filing_summary.to_csv(output_dir / FILING_SUMMARY_PATH.name, index=False)
    return detail, summary, filing_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metrics', default=str(METRICS_PATH))
    parser.add_argument('--filings', default=str(FILINGS_PATH))
    parser.add_argument('--evidence', default=str(EVIDENCE_PATH))
    parser.add_argument('--output-dir', default=str(OUTPUT_DIR))
    args = parser.parse_args()
    detail, summary, filing_summary = run_audit(args.metrics, args.filings, args.evidence, args.output_dir)
    print(f'FUNDAMENTAL_METRIC_ROWS={len(detail)}')
    if not summary.empty:
        print(summary.to_string(index=False))
    print('FILING_METADATA_SUMMARY')
    if not filing_summary.empty:
        print(filing_summary.to_string(index=False))
    print('CACHE_MUTATION=NONE')
    print('VERIFIED_STATUS_REQUIRES_HASHED_OFFICIAL_XML_DIRECT_FACT_MATCH')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


