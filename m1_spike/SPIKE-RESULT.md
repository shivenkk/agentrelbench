# M1 Spike Result — Task-Injection End-to-End

Proves check (c): a custom task JSON + custom seed DB reference runs through
EOG's unmodified `evaluate.py`, `--num_runs 2` producing independently-seeded
`run_N/` artifacts, driven entirely by the offline `scripted_responder.py`.

## What was run (exact commands)

1. **Schema source** — read a real shipped task verbatim:
   `external/EnterpriseOps-Gym/data/revised/csm/task_20251209_132736_542_99ba2325_6705caf4.json`
   (also cross-checked against `benchmark/models.py`'s `BenchmarkConfig` /
   `GymServerConfig` / `VerifierConfig` dataclasses directly in the clone).

2. **Entity-ID discovery + dry run** (throwaway, not part of the deliverable) —
   seeded the csm DB from
   `scratch/gym_dbs/Domain Wise DBs and Task-DB Mappings/csm/dbs/db_1762232091750_3ev7dns6b.sql`
   via `gym_client.seed()`, confirmed `account_id=1`, `contact_id=123`,
   `product_id=128`, `installed_product_id=3`, `user_group.group_id=4`,
   `user.user_id` 1/3/6 all exist (`POST /api/sql-runner`, explicit `LIMIT`
   avoided the silent `LIMIT 100`), then executed the exact 3-call sequence
   live to confirm the resulting `case_id` and final row before writing it
   into the task/script files.

3. **Authored artifacts:**
   - `m1_spike/tasks/task.json` — custom csm task (gym `sn-csm-server`,
     absolute `seed_database_file` path, `context: {"x-user-email":
     "thomas.green@servicenow.com"}`, `selected_tools:
     ["create_new_case","update_case","assign_case_to_user"]`, 2 verifiers).
   - `m1_spike/script.json` — 4 turns: 3 `tool_calls` (one tool per turn, to
     stay aligned with the responder's `n_tool_msgs`-indexed turn selection)
     + 1 final `content` turn.

4. **Responder sanity check:**
   ```
   python3 scripted_responder.py --script script.json --port 8099
   curl -s -X POST http://127.0.0.1:8099/v1/chat/completions -H "Content-Type: application/json" -d '...'
   ```
   Verified all 4 turns (0/2/3/4 prior tool messages) return well-formed
   OpenAI-style responses with correct `tool_calls`/`finish_reason`.

5. **Harness run** (from the clone's uv venv, absolute paths throughout):
   ```
   cd external/EnterpriseOps-Gym
   .venv/bin/python evaluate.py \
     --configs_folder /Users/shiven/Documents/Projects/agentrelbench/m1_spike/tasks \
     --llm_config /Users/shiven/Documents/Projects/agentrelbench/m1_spike/llm_stub.json \
     --output_folder /Users/shiven/Documents/Projects/agentrelbench/m1_spike/results \
     --orchestrator react --concurrency 1 --num_runs 2
   ```
   No `--domain`/`--mode` needed — those only apply to the `--hf_dataset` path;
   `--configs_folder` is the direct local-JSON path per `evaluate.py`'s argparse.
   Exit code 0.

6. **Cleanup:** killed the responder process; containers (`eog-csm`, `eog-itsm`)
   left running; confirmed `git status --short` in the clone is empty (no
   tracked files touched).

## Fix required (deviation)

`evaluate.py` failed immediately with `ModuleNotFoundError: No module named
'nest_asyncio'`. Root cause: the clone's `uv.lock` pins a package literally
named **`nest-asyncio2`** (module `nest_asyncio2`), but
`utils/task_queue_worker.py` imports the standard **`nest_asyncio`** (no "2")
— an upstream lockfile/import-name mismatch, not something introduced by this
spike (`git status` was clean before this run). Fixed by installing the real,
well-known PyPI package into the existing venv only:
```
uv pip install --python external/EnterpriseOps-Gym/.venv/bin/python nest_asyncio
```
This does not touch `pyproject.toml`/`uv.lock` (both tracked, untouched —
verified via `git status`) or any clone source file; it only adds the missing
module to the already-synced `.venv`.

## Pass criteria

**Both runs execute; `run_1/` and `run_2/` each contain `results_*.json`.** ✅
```
m1_spike/results/run_1/results_task.json  (15326 bytes)
m1_spike/results/run_2/results_task.json  (15326 bytes)
```
Log: `Processing 1 config files with concurrency 1 into folder: .../run_1` →
`RUN 1 COMPLETED` / `Overall Success: True` → `BENCHMARK COMPLETED`, then the
same for `run_2`. Tool discovery log confirms scoping worked as configured:
`[TOOL_SOURCE] ✅ Discovered 89 tools from gym 'sn-csm-server'` →
`[TOOL_FILTER] ✅ Filtered from 89 to 3 tools`.

**`tool_results` records the scripted calls with arguments + server results.** ✅
From `run_1/results_task.json` → `runs[0].tool_results` (identical in `run_2`):
```json
{
  "tool_name": "create_new_case",
  "arguments": {"account_id": 1, "contact_id": 123, "channel": "email", "priority": "high",
                "state": "new", "assignment_group_id": 4, "assigned_to": 3,
                "escalation": false, "product_id": 128, "installed_product_id": 3, ...},
  "result": {"success": true, "result": {"content": [{"text":
     "{\"case_id\": 1233, \"number\": \"CS-0001233\", ... \"state\": \"new\", ...}"}],
     "isError": false}},
  "gym_server": "sn-csm-server"
}
```
...followed by `update_case` (`case_id:1233` → `state: in_progress, priority:
critical, escalation:1`) and `assign_case_to_user` (`{"assignment_status":
"success", "assigned_to": 6, ...}`), each with full arguments and full server
response captured.

**Verifier `actual` values captured; run 1 vs run 2 used different `database_id`s.** ✅
`verification_results` (identical shape/values in both runs):
```json
{
  "case_reflects_create_update_assign": {"passed": true, "expected": 1, "actual": 1,
     "comparison_type": "equals", "query": "SELECT COUNT(*) AS count FROM customer_case WHERE case_id = 1233 AND state = 'in_progress' AND ... ;"},
  "customer_case_row_count_after_create": {"passed": true, "expected": 1233, "actual": 1233,
     "comparison_type": "equals", "query": "SELECT COUNT(*) AS count FROM customer_case;"}
}
```
`verification_summary`: `{"total": 2, "passed": 2, "failed": 0, "pass_rate": 1.0}` in both runs.
Different `database_id`s per run, from the harness's own log lines (`benchmark.mcp_client`):
```
run_1: ✅ Database created from file: db_1784202780001_tyj3ty8mw   (deleted after run_1 finished)
run_2: ✅ Database created from file: db_1784202780576_gf22qnj12   (deleted after run_2 finished)
```

## Surprises / notes

- **Langchain flow was clean** — zero retries, zero `Attempt N failed`, zero
  tracebacks. Only one cosmetic `UserWarning: Parameters {'extra_body'}
  should be specified explicitly...` per run from `langchain_openai` (a
  framework-level notice about how `model_kwargs` is threaded through,
  unrelated to our task/responder — harmless).
- **Determinism reconfirmed independently of the M1 audit:** the *same*
  `case_id` (1233) and byte-identical tool arguments/results/verifier `actual`
  values appeared in both runs despite different underlying `database_id`s —
  consistent with the audit's Test 2/3 findings for this exact seed file.
- **Numeric coincidence, not a bug:** verifier 2's `expected_value: 1233` (the
  post-create row count) numerically equals `case_id: 1233`. This is a
  coincidence of this seed file's history (1232 pre-existing rows, +1 new
  case = 1233, and the autoincrement PK also happens to land on 1233) —
  flagging so it isn't misread as the two verifiers checking the same thing.
- **One seed per outer run** (not two) — despite `executor.py` logging a
  separate "DATABASE SETUP — Creating master databases" banner before
  `initialize()`, only one `POST /api/seed-database` call (one "Database
  created from file" log line) occurred per outer run in practice, each
  cleanly deleted in the `finally` block after that run's verifiers ran.
- **Environment gap, not this spike's doing:** the `nest-asyncio`/`nest-asyncio2`
  mismatch (see Fix above) was present in the clone's synced venv before this
  run started; worth flagging upstream if EnterpriseOps-Gym is adopted further.

## Checklist

- ✅ Both runs executed; `run_1/results_task.json` and `run_2/results_task.json` present.
- ✅ `tool_results` records all 3 scripted calls with full arguments + server results.
- ✅ Verifier `actual` values captured (1 and 1233); run_1/run_2 used different `database_id`s (`db_1784202780001_tyj3ty8mw` vs `db_1784202780576_gf22qnj12`, from logs).
- ✅ Responder → langchain flow was clean: 0 retries, 0 tracebacks, only 1 benign `UserWarning`/run.
- Deviation: had to `uv pip install nest_asyncio` into the clone's `.venv` (upstream lockfile pinned `nest-asyncio2` instead) — no tracked file touched, `git status` clean.
- Responder process killed; `eog-csm`/`eog-itsm` containers left running per instructions.
