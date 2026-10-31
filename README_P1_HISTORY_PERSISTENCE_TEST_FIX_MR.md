# NSE V8 P1 History Persistence Workflow-Test Compatibility Fix

## Why this patch is needed

The GitHub Actions run `41173859764` checked out commit
`270a9d8eebe39081591f71c1ac4c4cc49df50991`.

The workflow already contains the safer history-inventory implementation:
- `mapfile` collects dated CSV snapshots.
- Each file is hashed and its Git tracking status is reported.
- Each snapshot is explicitly staged with `git add -f -- "$f"`.
- Staged files are listed before commit.

However, `test_fundamental_cache_persistence_workflow.py` still asserted the previous
single-line `find ... | xargs git add` implementation. That stale assertion caused
the regression test command to stop (`1 failed, 75 passed`) before the scanner and
the persistence step could run. Therefore this run does not prove history persistence.

## Patch contents

Replace only:
`test_fundamental_cache_persistence_workflow.py`

The revised test checks the current safer workflow behavior rather than requiring
one exact shell implementation.

## Validation

- `pytest -q test_fundamental_cache_persistence_workflow.py`: **6 passed**
- No trading filters, master specification, provider calculations, or workflow
  execution logic are changed by this patch.
- The workflow YAML itself is not modified.

## Next step

Commit/push the updated test file, then rerun GitHub Actions. Verify that:
1. The full regression test step completes.
2. NSE scan completes successfully.
3. `Persist fundamental cache and dated history in repository` executes.
4. Logs show `HISTORY_CSV_COUNT`, file hashes, tracking status, staged files,
   and the final committed file list.
