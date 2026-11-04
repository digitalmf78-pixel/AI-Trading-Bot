# Valuation fields in NSE V8 reports

The fundamental cache and reports now carry these provider-snapshot fields when available: valuation price, trailing and forward P/E, price/book, enterprise value/EBITDA, price/sales, price/free-cash-flow, PEG, market capitalization, enterprise value, and dividend yield.

Each row also records the provider quote date/time, requested EOD date, retrieval timestamp, source URL, currency, field coverage, and whether the numbers are a current provider snapshot. A valuation is marked current for that EOD only when the provider supplies a quote timestamp on the requested date. The current Yahoo Finance snapshot is secondary-source data; it is not an official filing and must not be treated as historical point-in-time valuation data in a backtest.

`ValuationAssessmentStatus=PROVIDER_SNAPSHOT_AVAILABLE_NOT_CLASSIFIED` means ratios were retrieved. It does not mean the stock is cheap or expensive. The scanner does not guess a universal P/E cutoff; valuation should be compared with the relevant sector, the company's own history, debt, cash flow, and the financial period used.

If the provider does not return a ratio, the field stays blank and the report lists it in `ValuationFieldsMissing`. Ratios at or below zero are listed in `ValuationNonMeaningfulFields` because, for example, negative P/E can indicate negative earnings rather than a bargain. The scan refreshes the valuation snapshot for the current EOD date even when the slower fundamental cache is otherwise complete.
