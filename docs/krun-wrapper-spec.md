# k-Run Wrapper — Spec v0 (M3)

Runs (task, model, k) → k independent EOG runs with per-run state capture and a batch manifest. Never edits the pinned clone; all integration is import-time patching from our package.

## Behavior

1. Invoke EOG's `evaluate.py` flow with `--num_runs k` (native per-run re-seeding, verified in M1).
2. **Per run, capture two full-state exports** via `/api/sql-runner` (explicit large LIMIT + `rows < limit` assertion per table; per-domain headers — csm needs `x-user-email`):
   - `post_seed_state.json.gz` — immediately after seeding. Since seeding is deterministic, these must be identical across the k runs → **every batch doubles as a free determinism monitor**; the collector diffs them and fails loudly on drift.
   - `final_state.json.gz` — immediately **before** EOG's cleanup deletes the DB. Mechanism: patch the deletion call-site symbol (see technical map §A/§C, executor.py `finally` block ~553–563) with dump-then-delete. Patch applied by our entrypoint at import time.
3. **Manifest** per batch: our git SHA, EOG commit (`de22905d`), MCP image digests, task file hash, llm config (key redacted), sampling params, k, timestamps; per run: `database_id`, termination status, token usage, artifact paths.
4. Storage: `runs/<batch_id>/<task_id>/run_<n>/{results_*.json (EOG's, untouched), post_seed_state.json.gz, final_state.json.gz}` + `runs/<batch_id>/manifest.json`.
5. **Hard rule (locked 2026-07-16):** collection asserts both exports exist for every run; any missing dump → `INVALID_MISSING_DUMP`, nonzero exit, batch blocked. Never silently skipped.

## CLI

`arb-run --tasks <dir> --llm-config <json> --k 8 --out runs/` (domain inferred from task's `gym_servers_config`).

## Acceptance test (fully offline, no API keys)

Reuse `m1_spike/`: scripted responder + spike task, `--k 2` through the wrapper → assert run_1/run_2 both have EOG results + both exports; post-seed exports identical across runs; manifest complete; then corrupt-delete one final_state and assert the collector fails loudly with `INVALID_MISSING_DUMP`.

## Non-goals

No pass^k/safe^k estimators (Phase 2, orchestrator, test-first), no damage labeling (M2 labeler consumes these exports), no Ray orchestration (direct mode only for now).
