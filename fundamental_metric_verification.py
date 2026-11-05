"""Fail-closed audit of cached fundamental metrics against official NSE XBRL evidence.

This module is read-only with respect to the fundamental cache.  It never
changes a metric, infers a calculation basis, or upgrades a value merely because
an NSE filing URL/publication date exists.  A metric is marked
OFFICIAL_XBRL_VERIFIED only when a separately recorded evidence row points to a
local XML file whose SHA-256, XBRL context, entity, period, unit, namespace,
contextRef and numeric fact all match the cached value.

Direct cash flow evidence and annual revenue/profit growth are verified against
official NSE XBRL. Derived growth is calculated from same-basis, consecutive
annual filings with statement cross-foot checks. Other derived ratios remain
pending rather than being guessed.
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
# The five-filing statement cross-foot audit consistently selected this NSE
# concept over the similarly named competing concept.  Operating cash flow is
# still accepted only when the filing itself reconciles CFO + CFI + CFF to the
# reported net cash change (see _verify_cashflow_crossfoot below).
DIRECT_FACT_TAGS: dict[str, set[str]] = {
    'OperatingCashFlowINR': {'CashFlowsFromUsedInOperatingActivities'},
}
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


def _fact_value(fact: ET.Element) -> float | None:
    """Return an XBRL numeric fact after applying scale and sign attributes."""
    try:
        value = float((fact.text or '').strip())
        value *= 10 ** int(fact.attrib.get('scale', '0') or 0)
        if fact.attrib.get('sign') == '-':
            value *= -1
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _verify_cashflow_crossfoot(facts: list[ET.Element], context_ref: str,
                               unit_ref: str, unit_measure: str,
                               taxonomy_namespace: str) -> tuple[bool, str]:
    """Require a same-context, same-unit operating/investing/financing cross-foot."""
    component_tags = {
        'operating': 'CashFlowsFromUsedInOperatingActivities',
        'investing': 'CashFlowsFromUsedInInvestingActivities',
        'financing': 'CashFlowsFromUsedInFinancingActivities',
        'net_change': 'IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges',
    }
    values: dict[str, float] = {}
    for component, tag in component_tags.items():
        matched = [fact for fact in facts
                   if _local(fact.tag) == tag
                   and _namespace(fact.tag) == taxonomy_namespace
                   and fact.attrib.get('contextRef') == context_ref]
        if len(matched) != 1:
            return False, f'{component} fact {tag} is not unique in the selected annual context'
        fact = matched[0]
        if fact.attrib.get('unitRef', '') != unit_ref:
            return False, f'{component} cash-flow fact does not use the selected INR unit'
        value = _fact_value(fact)
        if value is None:
            return False, f'{component} cash-flow fact is not a valid numeric XBRL value'
        values[component] = value
    components = values['operating'] + values['investing'] + values['financing']
    reported = values['net_change']
    tolerance = max(1.0, max(abs(components), abs(reported)) * 1e-9)
    if unit_measure not in {'INR', 'INR:INR'} and not unit_measure.endswith(':INR'):
        return False, f'cash-flow cross-foot requires INR, got {unit_measure}'
    if abs(components - reported) > tolerance:
        return False, ('Operating + investing + financing cash flow does not reconcile to '
                       'the filing net cash change before FX')
    return True, 'Same-context operating, investing and financing facts reconcile to net cash change before FX'


def _generated_ocf_evidence(metrics: pd.DataFrame, filings: pd.DataFrame,
                            manual_evidence: pd.DataFrame, repo_root: Path,
                            symbols: set[str] | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build ephemeral direct-fact evidence for requested symbols from official NSE XML.

    The hand-maintained evidence ledger is never changed.  XML is cached by URL
    hash, re-hashed on every run, and every generated fact has to pass the same
    exact filing/context/unit/value and cash-flow cross-foot checks as manual
    evidence. Per-symbol download or mapping failures remain diagnostic rows.
    """
    generated: list[dict[str, str]] = []
    diagnostics: list[dict[str, str]] = []
    if symbols is None:
        return pd.DataFrame(columns=EVIDENCE_COLUMNS), pd.DataFrame()
    requested = {str(s).strip().upper() for s in symbols if str(s).strip()}
    if not requested or filings.empty:
        return pd.DataFrame(columns=EVIDENCE_COLUMNS), pd.DataFrame()
    from nse_xbrl_fetch import fetch_official_xbrl_xml

    target_metrics = metrics[
        metrics['TckrSymb'].astype(str).str.upper().isin(requested)
        & metrics['OperatingCashFlowINR'].notna()
    ] if {'TckrSymb', 'OperatingCashFlowINR'}.issubset(metrics.columns) else metrics.iloc[0:0]
    seen: set[tuple[str, str, str]] = set()
    for _, metric in target_metrics.iterrows():
        symbol = _clean(metric.get('TckrSymb')).upper()
        period = _clean(metric.get('FinancialPeriodEnd'))[:10]
        pub = _clean(metric.get('PublicationDate'))[:10]
        basis = _clean(metric.get('MetricCalculationBasis')).upper()
        url = _clean(metric.get('OfficialFilingURL'))
        key = (symbol, period, url)
        if key in seen:
            continue
        seen.add(key)
        manual_match = False
        manual_keys = {'TckrSymb', 'MetricName', 'FinancialPeriodEnd', 'OfficialFilingURL'}
        if not manual_evidence.empty and manual_keys.issubset(manual_evidence.columns):
            manual_match = bool((manual_evidence['TckrSymb'].astype(str).str.upper().eq(symbol)
                                 & manual_evidence['MetricName'].astype(str).eq('OperatingCashFlowINR')
                                 & manual_evidence['FinancialPeriodEnd'].astype(str).str[:10].eq(period)
                                 & manual_evidence['OfficialFilingURL'].astype(str).eq(url)).any())
        if manual_match:
            continue
        filing_status, filing_reason = _filing_metadata_status(metric, filings)
        if filing_status != 'OFFICIAL_FILING_METADATA_MATCHED':
            diagnostics.append({'TckrSymb': symbol, 'FinancialPeriodEnd': period,
                                'Status': filing_status, 'Reason': filing_reason})
            continue
        if basis != 'ANNUAL_ALIGNED_STATEMENTS':
            diagnostics.append({'TckrSymb': symbol, 'FinancialPeriodEnd': period,
                                'Status': 'ANNUAL_BASIS_REQUIRED', 'Reason': 'Provider metric is not annual aligned'})
            continue
        if not period.endswith('-03-31'):
            diagnostics.append({'TckrSymb': symbol, 'FinancialPeriodEnd': period,
                                'Status': 'ANNUAL_PERIOD_UNSUPPORTED', 'Reason': 'Only March year-end contexts are currently mapped'})
            continue
        start = f'{int(period[:4]) - 1}-04-01'
        cache_name = hashlib.sha256(url.encode('utf-8')).hexdigest()[:16] + '.xml'
        cache_path = repo_root / 'data' / 'cache' / 'xbrl_samples' / cache_name
        try:
            if not cache_path.is_file():
                fetch_official_xbrl_xml(url, cache_path)
            digest = hashlib.sha256(cache_path.read_bytes()).hexdigest()
            contexts, units, facts = _parse_xbrl(cache_path)
        except Exception as exc:
            diagnostics.append({'TckrSymb': symbol, 'FinancialPeriodEnd': period,
                                'Status': 'OFFICIAL_XBRL_FETCH_OR_PARSE_FAILED',
                                'Reason': f'{type(exc).__name__}: {exc}'})
            continue

        candidates = []
        for context_ref, context in contexts.items():
            if (context.get('PeriodStart') != start or context.get('PeriodEnd') != period
                    or context.get('DimensionsJSON') != '[]' or not context.get('EntityIdentifier')):
                continue
            for tag in DIRECT_FACT_TAGS.get('OperatingCashFlowINR', set()):
                matching = [fact for fact in facts if _local(fact.tag) == tag
                            and fact.attrib.get('contextRef') == context_ref]
                for fact in matching:
                    unit_ref = fact.attrib.get('unitRef', '')
                    unit_measure = units.get(unit_ref, '')
                    namespace = _namespace(fact.tag)
                    fact_value = _fact_value(fact)
                    if fact_value is None or not (unit_measure == 'INR' or unit_measure.endswith(':INR')):
                        continue
                    crossfoot_ok, reason = _verify_cashflow_crossfoot(
                        facts, context_ref, unit_ref, unit_measure, namespace)
                    if crossfoot_ok:
                        candidates.append((context_ref, context, fact, unit_ref, unit_measure,
                                           namespace, fact_value))
                    else:
                        diagnostics.append({'TckrSymb': symbol, 'FinancialPeriodEnd': period,
                                            'Status': 'XBRL_CASHFLOW_CROSSFOOT_FAILED', 'Reason': reason})
        if len(candidates) != 1:
            diagnostics.append({'TckrSymb': symbol, 'FinancialPeriodEnd': period,
                                'Status': 'XBRL_ANNUAL_CONTEXT_AMBIGUOUS' if len(candidates) > 1 else 'XBRL_ANNUAL_CONTEXT_UNRESOLVED',
                                'Reason': f'Expected one unsegmented annual CFO fact with reconciled statement; found {len(candidates)}'})
            continue
        context_ref, context, fact, _, unit_measure, namespace, official_value = candidates[0]
        generated.append({
            'TckrSymb': symbol, 'MetricName': 'OperatingCashFlowINR',
            'ProviderMetricValue': _clean(metric.get('OperatingCashFlowINR')),
            'OfficialMetricValue': str(official_value), 'Tolerance': '0',
            'FinancialPeriodEnd': period, 'PublicationDate': pub,
            'MetricCalculationBasis': basis, 'OfficialFilingURL': url,
            'XbrlFactTag': _local(fact.tag), 'XbrlContextRef': context_ref,
            'EntityIdentifier': context['EntityIdentifier'],
            'EntityIdentifierScheme': context['EntityIdentifierScheme'],
            'UnitMeasure': unit_measure, 'TaxonomyNamespace': namespace,
            'PeriodStart': context['PeriodStart'], 'PeriodEnd': context['PeriodEnd'],
            'DimensionsJSON': context['DimensionsJSON'],
            'EvidenceFilePath': str(cache_path.relative_to(repo_root)), 'EvidenceSHA256': digest,
            'VerificationMethod': 'DIRECT_FACT_MATCH',
            'EvidenceDetailsJSON': json.dumps({'generated': True, 'cashflowCrossfoot': 'PASS'}, separators=(',', ':')),
        })
    return pd.DataFrame(generated, columns=EVIDENCE_COLUMNS), pd.DataFrame(diagnostics)


def _filing_reporting_basis(row: pd.Series) -> str:
    description = _clean(row.get('FilingDescription')).upper()
    if 'CONSOLIDATED' in description:
        return 'CONSOLIDATED'
    if 'STANDALONE' in description:
        return 'STANDALONE'
    return ''


def _annual_fact(contexts: dict[str, dict], units: dict[str, str], facts: list[ET.Element],
                 period_end: str, tag: str) -> tuple[dict | None, str]:
    start = f'{int(period_end[:4]) - 1}-04-01'
    found = []
    for context_ref, context in contexts.items():
        if (context.get('PeriodStart') != start or context.get('PeriodEnd') != period_end
                or context.get('DimensionsJSON') != '[]' or not context.get('EntityIdentifier')):
            continue
        matching = [fact for fact in facts if _local(fact.tag) == tag
                    and fact.attrib.get('contextRef') == context_ref]
        for fact in matching:
            unit_ref = fact.attrib.get('unitRef', '')
            unit_measure = units.get(unit_ref, '')
            value = _fact_value(fact)
            if value is not None and (unit_measure == 'INR' or unit_measure.endswith(':INR')):
                found.append({
                    'FactTag': tag, 'ContextRef': context_ref,
                    'EntityIdentifier': context['EntityIdentifier'],
                    'EntityIdentifierScheme': context['EntityIdentifierScheme'],
                    'UnitRef': unit_ref, 'UnitMeasure': unit_measure,
                    'TaxonomyNamespace': _namespace(fact.tag),
                    'PeriodStart': context['PeriodStart'], 'PeriodEnd': context['PeriodEnd'],
                    'DimensionsJSON': context['DimensionsJSON'], 'Value': value,
                })
    if len(found) != 1:
        return None, f'Expected exactly one unsegmented annual {tag} INR fact; found {len(found)}'
    return found[0], ''


def _check_growth_components(metric_name: str, current: dict, prior: dict,
                             contexts_by_file: list[tuple[dict, dict, list[ET.Element]]]) -> tuple[bool, str]:
    """Require official statement arithmetic to support each growth component."""
    for contexts, units, facts in contexts_by_file:
        primary = current if contexts is contexts_by_file[0][0] else prior
        context_ref = primary['ContextRef']
        namespace = primary['TaxonomyNamespace']
        unit_ref = primary['UnitRef']
        if metric_name == 'RevenueGrowthPct':
            tags = ('Income', 'OtherIncome')
            expected = primary['Value']
            calculation = None
        else:
            tags = ('ProfitLossForPeriodFromContinuingOperations',
                    'ProfitLossFromDiscontinuedOperationsAfterTax',
                    'ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod')
            expected = primary['Value']
            calculation = 0.0
        values = []
        for tag in tags:
            matches = [f for f in facts if _local(f.tag) == tag
                       and _namespace(f.tag) == namespace
                       and f.attrib.get('contextRef') == context_ref]
            if len(matches) != 1 or matches[0].attrib.get('unitRef', '') != unit_ref:
                return False, f'{metric_name} cross-foot component {tag} is not unique in the same annual INR context'
            value = _fact_value(matches[0])
            if value is None:
                return False, f'{metric_name} cross-foot component {tag} is not numeric'
            values.append(value)
        if metric_name == 'RevenueGrowthPct':
            revenue = [f for f in facts if _local(f.tag) == 'RevenueFromOperations'
                       and _namespace(f.tag) == namespace and f.attrib.get('contextRef') == context_ref]
            if len(revenue) != 1 or revenue[0].attrib.get('unitRef', '') != unit_ref:
                return False, 'RevenueFromOperations is not unique in the same annual INR context'
            revenue_value = _fact_value(revenue[0])
            if revenue_value is None:
                return False, 'RevenueFromOperations is not numeric'
            calculation = revenue_value + values[1]
            expected = values[0]
        else:
            calculation = sum(values)
        tolerance = max(1.0, max(abs(calculation), abs(expected)) * 1e-9)
        if abs(calculation - expected) > tolerance:
            return False, f'{metric_name} annual component statement does not cross-foot'
    return True, 'Annual revenue/profit component facts reconcile to the filing statement totals'


def _generated_growth_evidence(metrics: pd.DataFrame, filings: pd.DataFrame,
                               manual_evidence: pd.DataFrame, repo_root: Path,
                               symbols: set[str] | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Derive revenue/profit growth from two basis-matched official NSE annual filings."""
    generated: list[dict[str, str]] = []
    diagnostics: list[dict[str, str]] = []
    if symbols is None or filings.empty:
        return pd.DataFrame(columns=EVIDENCE_COLUMNS), pd.DataFrame()
    requested = {str(s).strip().upper() for s in symbols if str(s).strip()}
    target_metrics = metrics[metrics['TckrSymb'].astype(str).str.upper().isin(requested)].copy()
    growth_columns = [name for name in ('RevenueGrowthPct', 'ProfitGrowthPct') if name in target_metrics]
    if not growth_columns:
        return pd.DataFrame(columns=EVIDENCE_COLUMNS), pd.DataFrame()
    target_metrics = target_metrics[target_metrics[growth_columns].notna().any(axis=1)]
    from nse_xbrl_fetch import fetch_official_xbrl_xml

    xml_cache: dict[str, tuple[Path, str, dict[str, dict], dict[str, str], list[ET.Element]]] = {}

    def load_filing(url: str):
        if url not in xml_cache:
            cache_path = repo_root / 'data' / 'cache' / 'xbrl_samples' / (hashlib.sha256(url.encode('utf-8')).hexdigest()[:16] + '.xml')
            if not cache_path.is_file():
                fetch_official_xbrl_xml(url, cache_path)
            digest = hashlib.sha256(cache_path.read_bytes()).hexdigest()
            contexts, units, facts = _parse_xbrl(cache_path)
            xml_cache[url] = (cache_path, digest, contexts, units, facts)
        return xml_cache[url]

    for _, metric in target_metrics.iterrows():
        symbol = _clean(metric.get('TckrSymb')).upper()
        period = _clean(metric.get('FinancialPeriodEnd'))[:10]
        basis = _clean(metric.get('MetricCalculationBasis')).upper()
        current_url = _clean(metric.get('OfficialFilingURL'))
        current_pub = _clean(metric.get('PublicationDate'))[:10]
        if basis != 'ANNUAL_ALIGNED_STATEMENTS' or not period.endswith('-03-31'):
            continue
        current_status, current_reason = _filing_metadata_status(metric, filings)
        if current_status != 'OFFICIAL_FILING_METADATA_MATCHED':
            continue
        current_row = filings[
            filings['TckrSymb'].astype(str).str.upper().eq(symbol)
            & filings['FinancialPeriodEnd'].astype(str).str[:10].eq(period)
            & filings['OfficialFilingURL'].astype(str).eq(current_url)
        ].iloc[0]
        reporting_basis = _filing_reporting_basis(current_row)
        if not reporting_basis:
            diagnostics.append({'TckrSymb': symbol, 'MetricName': 'RevenueGrowthPct|ProfitGrowthPct',
                                'Status': 'XBRL_REPORTING_BASIS_UNRESOLVED', 'Reason': 'Current filing description does not identify standalone/consolidated basis'})
            continue
        previous_period = f'{int(period[:4]) - 1}-03-31'
        if not {'TckrSymb', 'FinancialPeriodEnd', 'PublicationDateStatus', 'OfficialFilingURL', 'FilingDescription'}.issubset(filings.columns):
            continue
        prior_rows = filings[
            filings['TckrSymb'].astype(str).str.upper().eq(symbol)
            & filings['FinancialPeriodEnd'].astype(str).str[:10].eq(previous_period)
            & filings['PublicationDateStatus'].astype(str).str.upper().eq('VERIFIED')
        ].copy()
        prior_rows = prior_rows[
            prior_rows['FilingDescription'].astype(str).str.upper().str.contains(reporting_basis)
            & prior_rows['FilingDescription'].astype(str).str.upper().str.contains('AUDITED')
        ]
        if prior_rows.empty:
            diagnostics.append({'TckrSymb': symbol, 'MetricName': 'RevenueGrowthPct|ProfitGrowthPct',
                                'Status': 'PRIOR_YEAR_AUDITED_FILING_NOT_FOUND', 'Reason': f'No verified {reporting_basis} audited filing for {previous_period}'})
            continue
        prior_rows = prior_rows.sort_values('PublicationDate', kind='stable')
        latest_prior = prior_rows[prior_rows['PublicationDate'].eq(prior_rows['PublicationDate'].max())]
        if latest_prior['OfficialFilingURL'].nunique() != 1:
            diagnostics.append({'TckrSymb': symbol, 'MetricName': 'RevenueGrowthPct|ProfitGrowthPct',
                                'Status': 'PRIOR_YEAR_FILING_AMBIGUOUS', 'Reason': 'Multiple latest audited URLs share the selected reporting basis'})
            continue
        prior_url = _clean(latest_prior.iloc[0]['OfficialFilingURL'])
        try:
            current_path, current_digest, current_contexts, current_units, current_facts = load_filing(current_url)
            prior_path, prior_digest, prior_contexts, prior_units, prior_facts = load_filing(prior_url)
        except Exception as exc:
            diagnostics.append({'TckrSymb': symbol, 'MetricName': 'RevenueGrowthPct|ProfitGrowthPct',
                                'Status': 'OFFICIAL_XBRL_FETCH_OR_PARSE_FAILED', 'Reason': f'{type(exc).__name__}: {exc}'})
            continue
        for metric_name, tag in (('RevenueGrowthPct', 'RevenueFromOperations'), ('ProfitGrowthPct', 'ProfitLossForPeriod')):
            if metric_name not in metric.index or _number(metric.get(metric_name)) is None:
                continue
            manual_match = False
            keys = {'TckrSymb', 'MetricName', 'FinancialPeriodEnd', 'OfficialFilingURL'}
            if not manual_evidence.empty and keys.issubset(manual_evidence.columns):
                manual_match = bool((manual_evidence['TckrSymb'].astype(str).str.upper().eq(symbol)
                                     & manual_evidence['MetricName'].astype(str).eq(metric_name)
                                     & manual_evidence['FinancialPeriodEnd'].astype(str).str[:10].eq(period)
                                     & manual_evidence['OfficialFilingURL'].astype(str).eq(current_url)).any())
            if manual_match:
                continue
            current_component, c_reason = _annual_fact(current_contexts, current_units, current_facts, period, tag)
            prior_component, p_reason = _annual_fact(prior_contexts, prior_units, prior_facts, previous_period, tag)
            if current_component is None or prior_component is None:
                diagnostics.append({'TckrSymb': symbol, 'MetricName': metric_name,
                                    'Status': 'XBRL_ANNUAL_COMPONENT_UNRESOLVED', 'Reason': c_reason or p_reason})
                continue
            if (current_component['EntityIdentifier'] != prior_component['EntityIdentifier']
                    or current_component['EntityIdentifierScheme'] != prior_component['EntityIdentifierScheme']):
                diagnostics.append({'TckrSymb': symbol, 'MetricName': metric_name,
                                    'Status': 'XBRL_ENTITY_MISMATCH', 'Reason': 'Current and prior year filings identify different entities'})
                continue
            crossfoot, crossfoot_reason = _check_growth_components(
                metric_name, current_component, prior_component,
                [(current_contexts, current_units, current_facts), (prior_contexts, prior_units, prior_facts)])
            if not crossfoot:
                diagnostics.append({'TckrSymb': symbol, 'MetricName': metric_name,
                                    'Status': 'XBRL_COMPONENT_CROSSFOOT_FAILED', 'Reason': crossfoot_reason})
                continue
            if prior_component['Value'] <= 0:
                diagnostics.append({'TckrSymb': symbol, 'MetricName': metric_name,
                                    'Status': 'XBRL_GROWTH_BASE_NOT_POSITIVE', 'Reason': 'Provider growth formula requires positive prior-year base'})
                continue
            official_growth = (current_component['Value'] - prior_component['Value']) / prior_component['Value'] * 100.0
            def component_record(component, path, digest):
                return {**component, 'EvidenceFilePath': str(path.relative_to(repo_root)), 'EvidenceSHA256': digest}
            details = {'formula': 'growth_percent', 'metric': metric_name,
                       'current': component_record(current_component, current_path, current_digest),
                       'prior': component_record(prior_component, prior_path, prior_digest),
                       'reportingBasis': reporting_basis, 'arithmeticCrossfoot': 'PASS'}
            generated.append({
                'TckrSymb': symbol, 'MetricName': metric_name,
                'ProviderMetricValue': _clean(metric.get(metric_name)),
                'OfficialMetricValue': str(official_growth), 'Tolerance': '0.01',
                'FinancialPeriodEnd': period, 'PublicationDate': current_pub,
                'MetricCalculationBasis': basis, 'OfficialFilingURL': current_url,
                'XbrlFactTag': tag, 'XbrlContextRef': current_component['ContextRef'],
                'EntityIdentifier': current_component['EntityIdentifier'],
                'EntityIdentifierScheme': current_component['EntityIdentifierScheme'],
                'UnitMeasure': current_component['UnitMeasure'],
                'TaxonomyNamespace': current_component['TaxonomyNamespace'],
                'PeriodStart': current_component['PeriodStart'], 'PeriodEnd': current_component['PeriodEnd'],
                'DimensionsJSON': current_component['DimensionsJSON'],
                'EvidenceFilePath': str(current_path.relative_to(repo_root)), 'EvidenceSHA256': current_digest,
                'VerificationMethod': 'DERIVED_COMPONENT_FACTS',
                'EvidenceDetailsJSON': json.dumps(details, separators=(',', ':')),
            })
    return pd.DataFrame(generated, columns=EVIDENCE_COLUMNS), pd.DataFrame(diagnostics)


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


def _verify_derived_growth_evidence(metric: pd.Series, metric_name: str,
                                   ev: dict, repo_root: Path) -> tuple[str, str, dict]:
    """Reopen both official filing snapshots and independently recompute growth."""
    try:
        details = json.loads(_clean(ev.get('EvidenceDetailsJSON')))
        if details.get('formula') != 'growth_percent' or details.get('metric') != metric_name:
            raise ValueError('Evidence formula/metric is not the approved growth calculation')
        current = details['current']
        prior = details['prior']
        expected_tag = ('RevenueFromOperations' if metric_name == 'RevenueGrowthPct'
                        else 'ProfitLossForPeriod')
        parsed = []
        for component in (current, prior):
            path = (repo_root / component['EvidenceFilePath']).resolve()
            path.relative_to(repo_root.resolve())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest.lower() != _clean(component['EvidenceSHA256']).lower():
                return 'EVIDENCE_SHA256_MISMATCH', 'Current/prior XBRL snapshot hash changed', ev
            contexts, units, facts = _parse_xbrl(path)
            context_ref = _clean(component['ContextRef'])
            context = contexts.get(context_ref)
            if context is None:
                return 'XBRL_CONTEXT_NOT_FOUND', 'Growth component context is absent from its XML filing', ev
            expected_end = _clean(metric.get('FinancialPeriodEnd'))[:10]
            if component is prior:
                expected_end = f'{int(expected_end[:4]) - 1}-03-31'
            if _clean(component.get('PeriodEnd')) != expected_end:
                return 'XBRL_PERIOD_MISMATCH', 'Current/prior component period does not match consecutive fiscal years', ev
            for key in ('EntityIdentifier', 'EntityIdentifierScheme', 'PeriodStart', 'PeriodEnd', 'DimensionsJSON'):
                if context.get(key, '') != _clean(component.get(key)):
                    return 'XBRL_CONTEXT_MISMATCH', f'{key} differs in current/prior filing context', ev
            fact_tag = _clean(component.get('FactTag'))
            if fact_tag != expected_tag:
                return 'XBRL_FACT_TAG_NOT_APPROVED_FOR_METRIC', f'{fact_tag} is not approved for {metric_name}', ev
            found = [fact for fact in facts if _local(fact.tag) == expected_tag
                     and _namespace(fact.tag) == _clean(component.get('TaxonomyNamespace'))
                     and fact.attrib.get('contextRef') == context_ref]
            if len(found) != 1:
                return 'XBRL_FACT_NOT_UNIQUE', f'Expected one {expected_tag} in annual context; found {len(found)}', ev
            fact = found[0]
            unit = units.get(fact.attrib.get('unitRef', ''), '')
            value = _fact_value(fact)
            if unit != _clean(component.get('UnitMeasure')) or not (unit == 'INR' or unit.endswith(':INR')):
                return 'XBRL_UNIT_MISMATCH', 'Growth components must use the same currency INR unit', ev
            if value is None or abs(value - float(component['Value'])) > 0.01:
                return 'XBRL_FACT_VALUE_DIFFERS_FROM_LEDGER', 'Official component value differs from evidence details', ev
            parsed.append((contexts, units, facts, component))
        if (parsed[0][3]['EntityIdentifier'] != parsed[1][3]['EntityIdentifier']
                or parsed[0][3]['EntityIdentifierScheme'] != parsed[1][3]['EntityIdentifierScheme']
                or parsed[0][3]['UnitMeasure'] != parsed[1][3]['UnitMeasure']):
            return 'XBRL_ENTITY_MISMATCH', 'Current and prior filings do not describe the same entity and unit', ev
        ok, reason = _check_growth_components(metric_name, parsed[0][3], parsed[1][3],
                                             [(parsed[0][0], parsed[0][1], parsed[0][2]),
                                              (parsed[1][0], parsed[1][1], parsed[1][2])])
        if not ok:
            return 'XBRL_COMPONENT_CROSSFOOT_FAILED', reason, ev
        prior_value = float(prior['Value'])
        if prior_value <= 0:
            return 'XBRL_GROWTH_BASE_NOT_POSITIVE', 'Prior-year base must be positive', ev
        official = (float(current['Value']) - prior_value) / prior_value * 100.0
        tolerance = _number(ev.get('Tolerance')) or 0.0
        provider = _number(metric.get(metric_name))
        recorded_provider = _number(ev.get('ProviderMetricValue'))
        recorded_official = _number(ev.get('OfficialMetricValue'))
        if None in (provider, recorded_provider, recorded_official):
            return 'EVIDENCE_VALUE_INVALID', 'Provider or derived growth value is not numeric', ev
        if abs(provider - recorded_provider) > tolerance:
            return 'CACHE_VALUE_CHANGED_SINCE_EVIDENCE', 'Cached growth differs from generated evidence', ev
        if abs(official - recorded_official) > tolerance:
            return 'XBRL_FACT_VALUE_DIFFERS_FROM_LEDGER', 'Recomputed growth differs from generated evidence', ev
        if abs(provider - official) > tolerance:
            return 'PROVIDER_VALUE_MISMATCH', 'Provider growth differs from official two-year calculation', ev
        return 'OFFICIAL_XBRL_VERIFIED', 'Growth independently recomputed from hash-verified, basis-matched annual filings with statement cross-foot checks', ev
    except (KeyError, TypeError, ValueError, OSError, ET.ParseError) as exc:
        return 'DERIVED_EVIDENCE_INVALID', f'{type(exc).__name__}: {exc}', ev


def _match_evidence(metric: pd.Series, metric_name: str, evidence: pd.DataFrame,
                    repo_root: Path) -> tuple[str, str, dict]:
    symbol = _clean(metric.get('TckrSymb')).upper()
    period = _clean(metric.get('FinancialPeriodEnd'))[:10]
    pub = _clean(metric.get('PublicationDate'))[:10]
    basis = _clean(metric.get('MetricCalculationBasis')).upper()
    url = _clean(metric.get('OfficialFilingURL'))
    if metric_name not in DIRECT_FACT_TAGS and metric_name not in {'RevenueGrowthPct', 'ProfitGrowthPct'}:
        if metric_name == 'OperatingCashFlowINR':
            return ('OFFICIAL_FACT_MAPPING_UNRESOLVED',
                    'Competing NSE operating-cash-flow tags have not been reconciled; no direct-fact mapping is approved', {})
        return 'DERIVED_RECONCILIATION_REQUIRED', 'No approved direct-fact mapping exists; derived metrics require component-level reconciliation', {}
    if basis != 'ANNUAL_ALIGNED_STATEMENTS':
        return 'DERIVED_RECONCILIATION_REQUIRED', 'Direct-fact verification requires an approved annual calculation basis; this metric/basis requires reconciliation', {}
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
    method = _clean(ev.get('VerificationMethod')).upper()
    if method == 'DERIVED_COMPONENT_FACTS' and metric_name in {'RevenueGrowthPct', 'ProfitGrowthPct'}:
        return _verify_derived_growth_evidence(metric, metric_name, ev, repo_root)
    if metric_name in {'RevenueGrowthPct', 'ProfitGrowthPct'}:
        return 'DERIVED_RECONCILIATION_REQUIRED', 'Growth cannot be verified from a single direct fact; two annual component filings are required', ev
    if method != 'DIRECT_FACT_MATCH':
        return 'DERIVED_RECONCILIATION_REQUIRED', 'Evidence method is not supported for this metric', ev
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
    fact_value = _fact_value(fact)
    if fact_value is None:
        return 'XBRL_FACT_VALUE_INVALID', 'XBRL fact value/scale/sign is invalid', ev
    if metric_name == 'OperatingCashFlowINR':
        crossfoot_ok, crossfoot_reason = _verify_cashflow_crossfoot(
            facts, context_ref, unit_ref, actual_unit, _namespace(fact.tag))
        if not crossfoot_ok:
            return 'XBRL_CASHFLOW_CROSSFOOT_FAILED', crossfoot_reason, ev
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
    reason = 'Exact direct fact, context, entity, period, dimensions, unit, taxonomy and SHA-256 matched'
    if metric_name == 'OperatingCashFlowINR':
        reason += '; cash-flow statement cross-foot reconciled'
    return 'OFFICIAL_XBRL_VERIFIED', reason, ev


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
              repo_root: str | Path = '.',
              symbols: set[str] | list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(repo_root).resolve()
    if symbols is None:
        recent_report = output_dir / 'v8_fundamental_report.csv'
        if recent_report.is_file():
            report = pd.read_csv(recent_report)
            if 'TckrSymb' in report.columns:
                symbols = set(report['TckrSymb'].dropna().astype(str).str.upper())
    generated_ocf, ocf_diagnostics = _generated_ocf_evidence(metrics, filings, evidence, repo_root, symbols)
    generated_growth, growth_diagnostics = _generated_growth_evidence(metrics, filings, evidence, repo_root, symbols)
    generated = pd.concat([generated_ocf, generated_growth], ignore_index=True)
    diagnostics = pd.concat([ocf_diagnostics, growth_diagnostics], ignore_index=True)
    combined_evidence = pd.concat([evidence, generated], ignore_index=True)
    detail, summary, filing_summary = build_metric_verification(metrics, filings, combined_evidence, repo_root=repo_root)
    detail.to_csv(output_dir / DETAILS_PATH.name, index=False)
    summary.to_csv(output_dir / SUMMARY_PATH.name, index=False)
    filing_summary.to_csv(output_dir / FILING_SUMMARY_PATH.name, index=False)
    generated.to_csv(output_dir / 'v8_fundamental_generated_evidence.csv', index=False)
    diagnostics.to_csv(output_dir / 'v8_fundamental_evidence_generation_diagnostics.csv', index=False)
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
    print('FUNDAMENTAL_METRIC_CACHE_AND_MANUAL_EVIDENCE_LEDGER_MUTATION=NONE')
    print('GENERATED_EVIDENCE=EPHEMERAL; OFFICIAL_XML_CACHE=data/cache/xbrl_samples')
    print('VERIFIED_STATUS_REQUIRES_HASHED_OFFICIAL_XML_DIRECT_FACT_MATCH')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())


