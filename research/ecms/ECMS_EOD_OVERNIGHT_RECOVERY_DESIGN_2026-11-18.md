# ECMS EOD Overnight Recovery — Design Investigation (18-Nov-2026)

## Scope and safety
Research-only investigation. No production source, workflow, thresholds, cache, or NSE V8 files changed. This note extends the failure analysis for the EOD run that started at 01:28 IST on 18-Nov-2026.

## Evidence reviewed
- Main-branch scanner: strategies/ecms/volume_gainers.py (baseline 6144f5c9c197ffa1c301f2ac9b9a7f5450a21a7a).
- Workflow: .github/workflows/ecms-volume-gainers-shadow.yml.
- Tests: tests/test_ecms_volume_gainers.py.
- Scheduled triggers: 17:01 IST EOD (31 11 * * * UTC), 09:21 IST Morning (51 3 * * * UTC), 17:45 IST weekday EOD backup (15 12 * * 1-5 UTC).
- Failed run evidence: 17-Nov EOD event began 18-Nov at 01:28 IST; scheduler wrote SKIPPED / NOT_OFFICIAL_NSE_SESSION_SCAN_SLOT, expected 17:00 and actual 01:28. Workflow validation then failed because no current-run EOD marker existed.

## Confirmed failure chain
1. main() derives today from datetime.now(IST).date(), requires that date to be an NSE trading session, and obtains that date's EOD scan time.
2. For scheduled EOD, slot_ok is actual_minutes >= expected_minutes. At 01:28, it is false against 17:00. The run exits before the backup-cache recovery block.
3. If only the time guard were relaxed, run_eod() would still set scan_date to 18-Nov and _verified_nse_page_session_date() requires the NSE HTTP Date response header (converted to IST) to equal that scan date.
4. The HTTP Date header is a transport/response timestamp, not proof of the trading session represented by the Volume Gainers payload. The current code copies that timestamp-derived date into every row as NSEServerDateIST and treats it as page_session_date. This conflates capture date with market-data session date.
5. The cache fallback is not a recovery mechanism for a delayed missing run: it only returns success when a valid EOD cache for expected_latest_completed_session() already exists. In the failure case, that cache is precisely what is missing.

## Root cause
This is a session identity + delayed-schedule recovery design defect, not merely a clock comparison defect. A delayed event crossing IST midnight loses the original intended scan session when the code substitutes wall-clock today. In addition, HTTP response date is being used as a proxy for the payload's market session.

## Safe design requirements (do not implement by simply deleting the time guard)
- Keep Morning's narrow 15-minute slot check unchanged.
- Keep normal same-day EOD eligibility: scheduled EOD cannot execute before the official EOD slot.
- For a delayed EOD backup only, resolve one explicit target session from the official NSE trading calendar / latest completed-session source, not from current wall-clock date alone.
- Bound recovery to the intended overnight window and reject a run if a newer Morning session has already begun or if the target session cannot be resolved unambiguously.
- Separate at least three timestamps in data contracts: captured_at_ist (runtime/transport), market_session_date (actual NSE data session), and bhavcopy_date (latest completed bhavcopy session). Never infer market session solely from HTTP Date.
- Establish a trustworthy market-session field from NSE payload semantics (e.g. validated NSEUpdatedAt if its meaning is confirmed) or an independently verified official NSE session artifact. If no authoritative session evidence is available, fail closed with WAIT_FOR_DATA.
- Preserve current-run cache integrity: marker scan_date and row EODDate must both refer to the same resolved target session, and run ID / symbol count / snapshot status checks must remain intact.
- Do not let a delayed run overwrite a newer valid snapshot. Compare target session and existing marker before writing.
- Backup trigger should be a recovery-only path. If a valid target-session snapshot already exists, return a successful no-op; if absent, attempt exactly one target-session recovery.

## Required regression tests before any production change
1. Regular EOD at 17:01 IST on a trading day runs normally.
2. Regular EOD at 16:59 IST is skipped.
3. Backup at 17:45 IST on the same trading day runs if no valid target-session cache exists.
4. Backup at 01:28 IST next calendar day recovers the prior intended completed session only when official session evidence matches.
5. Delayed backup at 01:28 IST with no reliable market-session evidence fails closed; HTTP Date alone must not make it pass.
6. Backup after the next Morning scan has started cannot overwrite or masquerade as the previous session.
7. Weekend/holiday delay resolves the last official completed session safely or fails closed; it must not treat the calendar date as an NSE session.
8. Existing valid target-session cache causes backup no-op, including after midnight.
9. A stale cache from an older session is rejected.
10. Special-session EOD times (e.g. Muhurat) still use official calendar time and do not inherit the regular 17:00 assumption.
11. Run-marker date, row EODDate, scan date, and page evidence remain consistent under all above cases.

## Recommendation
First correct the data contract so payload market-session identity is independently evidenced. Then implement a dedicated, bounded delayed-backup resolver and tests in an isolated research branch. Only after the tests and a replay of the 17-Nov → 18-Nov failure pass should a separate production PR be proposed. No production change is authorized or made by this investigation.