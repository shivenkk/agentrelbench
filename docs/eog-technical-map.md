# EnterpriseOps-Gym — Technical Map for AgentRelBench

Read-only analysis of the clone at `external/EnterpriseOps-Gym`.
Commit `de22905d21a080b83bf4a54258afe4250ee2dd55` (2026-06-03, "Merge PR #16 release/data_fixes"). License Apache-2.0 (`LICENSE`).
DBs unzipped (read-only) to `scratch/gym_dbs/Domain Wise DBs and Task-DB Mappings/`.

**Verdict up front:** Check (b) — reset determinism — *plausibly passes at the harness level* (every run re-seeds a fresh DB from a static SQL file; runs are independent; per-run outputs are separate). All residual nondeterminism lives inside the opaque MCP Docker containers and must be confirmed by the M1 empirical audit. Check (c) — damage layer + custom tasks — *passes*: custom tasks are just local JSON files (`--configs_folder`), custom DBs are just a `seed_database_file` path, verifiers are declarative SQL over an HTTP endpoint we can reuse. The only structural constraint is that tools are fixed per domain container.

---

## A. Reset & seeding mechanics (check b)

### The exact seed path (per run, via HTTP POST)
1. `evaluate.py:main()` loads task JSON configs and, for each, calls `execute_sample()` (`evaluate.py:189`), which builds a `BenchmarkExecutor` and calls `executor.execute_benchmark()` (`evaluate.py:213-223`).
2. `BenchmarkExecutor.execute_benchmark()` (`benchmark/executor.py:482`) loops `for run_number in range(1, self.config.number_of_runs + 1)` (`executor.py:510`) calling `execute_single_run(run_number)`.
3. **`execute_single_run()` re-seeds the DB every run** (`executor.py:309-349`):
   ```python
   for gym_conf in self.gym_configs:
       db_id = create_database_from_file(gym_conf["mcp_server_url"], gym_conf["seed_database_file"])  # 323
       ...
       client.database_id = db_id  # 349  -> subsequent tool calls hit the fresh DB
   ```
4. `create_database_from_file()` (`benchmark/mcp_client.py:19-58`) reads the SQL file from disk and **POSTs it to `{gym_url}/api/seed-database`** with body `{database_id, name, description, sql_content}` (`mcp_client.py:43-54`). The `database_id` is generated fresh each call: `db_{int(time.time()*1000)}_{9 random chars}` (`mcp_client.py:23-24`).
5. Tool calls carry the DB via the `x-database-id` HTTP header (`mcp_client.py:184-185`); verifier SQL carries it too (`verifier.py:220`). So routing to the correct per-run DB instance is header-based.
6. After all runs, `execute_benchmark()`'s `finally` block deletes every auto-created DB via `DELETE {gym_url}/api/delete-database` (`executor.py:553-563`, `mcp_client.py:65-104`).

**So the seed is: per run (not per task, not once), via an HTTP call to the server's `/api/seed-database` endpoint, with the full SQL file contents in the request body.** Each run gets a brand-new isolated database id. This is strong for clean run-to-run attribution: runs do not share DB state.

### `--num_runs > 1`: two independent-trial mechanisms, both re-seed
- **Outer (`--num_runs`, CLI)** — `evaluate.py:317-329`:
  ```python
  for idx in range(int(args.num_runs)):
      output_folder = os.path.join(args.output_folder, f"run_{idx+1}")   # separate folder per run
      ...
      await worker.process(config_files)   # re-run ALL tasks
  ```
  Each outer run is a full independent pass over all tasks, written to a **separate `run_1/`, `run_2/`, … subfolder**. Output file per task: `run_N/results_{taskname}.json` (`evaluate.py:235-238`). This is the cleanest k-run mechanism for our harness. (Default `--num_runs = 3`, `evaluate.py:260`.)
- **Inner (`number_of_runs`, task JSON)** — the `execute_benchmark` loop (`executor.py:510`); all inner runs land in one file's `runs[]` array with aggregate `statistics`.

**Both re-seed a fresh DB per run** (step 3 runs inside `execute_single_run`, which the inner loop calls each iteration). Runs are therefore independent trials. Per-run outputs are stored separately at the outer level (`run_N/` folders) and together at the inner level (`runs[]`).

**Retry layering (relevant to variance attribution):**
- Whole-sample retry: `execute_sample` retries up to 5× if *any* run errored, with linear backoff `asyncio.sleep(i+1)` (`evaluate.py:222-233`). Only *errored* runs trigger retry; a run that completes with wrong/damaging actions is **not** retried, so damage is preserved.
- Per-LLM-call retry: `invoke_with_tools` wraps the model in `.with_retry(retry_if_exception_type=(Exception,), stop_after_attempt=3)` (`benchmark/llm_client.py:319-328`). Planner LLMs also retry 3× (`executor.py:153-156`, `planner_react.py:166-169`).

### `reset_database_between_runs` is a dead flag
`reset_database_between_runs: bool = True` is defined in `benchmark/models.py:82` and appears in every task JSON, but a repo-wide grep finds **no other reference** — it is never consumed. The DB is *always* re-seeded per run regardless. Good for determinism, but note the flag is inert (setting it `False` would not create shared/persistent state).

### Nondeterminism / wall-clock / randomness audit (grep results, each judged)
| Hit | Location | Relevance |
|---|---|---|
| `random.choice(load_llm_configs(...))` | `evaluate.py:198`, `:209` | **Real, controllable.** Picks one LLM endpoint from the pool ("load balancer"). If the pool has >1 entry, endpoint varies run-to-run. **Mitigation: use a single-element LLM config.** |
| `int(time.time()*1000)` + `random.choices` | `mcp_client.py:23-24` | DB *identifier* only. No effect on DB state or verifier outcomes. |
| `datetime.now().strftime(...)` (db_name) | `mcp_client.py:41` | Cosmetic DB display name. Irrelevant. |
| `datetime.now(timezone.utc)` | `executor.py:315,366-367` | `execution_time_ms` latency measurement. Written to output; inherently varies but does not affect DB state or verifier pass/fail. |
| `datetime.now().strftime(...)` | `ray_experiment_queue.py:114` | Output folder timestamp naming (Ray path only). Irrelevant to state. |
| temperature | config default **0.6** (`evaluate.py:174`), `LLMConfig`/`BenchmarkConfig` default 0.0 (`models.py:80,93`), examples use 1.0 | Model sampling variance. This is the *subject* of our p̂ measurement, not a bug. |
No `.seed()`, `torch.manual_seed`, `np.random`, or `uuid` anywhere in the harness.

### Volatile columns in the SQL snapshots
The snapshots are **data-only INSERT dumps** (see section C) — schema lives in the container, so column DEFAULTs/triggers are *not visible here*. From the dump text itself:
- **`hr` uses `CURRENT_TIMESTAMP` 180×** inside its INSERT values (first snapshot) — hr seed timestamps are wall-clock at seed time, i.e. **hr has seed-time nondeterminism** in its `created_at`/`updated_at`-type columns.
- Autoincrement/serial markers are rare in the dumps: `csm`=1, `itsm`=2, `email`=2, others 0.
- No `CREATE TRIGGER` in any snapshot; no `CURRENT_TIMESTAMP` outside hr.
- The ServiceNow-style domains (csm/itsm/hr) carry timestamp columns (`sys_created_on`, `sys_updated_on`, `closed_on`, `created_at`, `updated_at`) that server tools will stamp with wall-clock on write (the csm policy prompt explicitly says "Capture timestamps (sys_updated_on...)", task JSON line 20). **These vary run-to-run and must be excluded from our state-diff damage labeler.** Verifiers in the shipped tasks check IDs/states/enums, not timestamps, so verifier outcomes are timestamp-insensitive.

### What is UNKNOWN (must be covered by the M1 Docker audit)
The MCP server images (`shivakrishnareddyma225/enterpriseops-gym-mcp-<domain>`, README:124) are opaque. M1 must empirically test:
1. **Reset semantics of `/api/seed-database`**: does it drop+recreate+repopulate cleanly per `database_id`, with no residue/append? Two identical seeds must yield identical state.
2. **Isolation under concurrency**: harness runs with `--concurrency` up to 10 (`evaluate.py:256`) against a *shared* server, isolating by `x-database-id`. Confirm no cross-task DB bleed.
3. **Server-side write nondeterminism**: run an *identical* fixed tool-call sequence twice on a fresh seed and diff the DB (excluding known timestamp columns). Confirm identical rows/ids — i.e., no unseeded UUIDs, no wall-clock leaking into logical columns, deterministic autoincrement.
4. **In-container schema**: triggers / `ON UPDATE CURRENT_TIMESTAMP` / defaults not visible in the data-only dumps.
5. **`/api/sql-runner` capabilities**: confirm it accepts arbitrary read (`SELECT`) queries and returns rows (our damage labeler depends on this).

---

## B. Task format & custom-task injection (check c)

### Loader code (two sources, one code path)
`evaluate.py:main()` (`evaluate.py:243-329`) accepts either:
- `--configs_folder <local dir>` → `config_files = glob.glob(os.path.join(configs_folder, "*.json"))` (`evaluate.py:311-316`). **Local task files, directly.**
- `--hf_dataset <repo> --domain <d> --mode <m>` → downloads with `hf_load_dataset(args.hf_dataset, mode, split=domain)` (`evaluate.py:295`) and **materializes each row to a JSON file in a temp dir** (`evaluate.py:296-310`), then treats that temp dir as `configs_folder`. During materialization, HF-only fields `task_id`/`domain` are dropped and JSON-string fields `gym_servers_config`/`verifiers` are `json.loads`'d (`evaluate.py:286,301-304`).

So the HF path is a thin convenience that produces the *same* local JSON format. **Custom task = drop a JSON file in a folder and pass `--configs_folder`.** No HF dependency required. (`benchmark_utils.load_config` / `evaluate.load_config` parse the JSON; `skip_sample` resumes by checking for an existing `results_*.json`, `benchmark_utils.py:51-57`.)

### One full task record (verbatim from repo)
`data/revised/csm/task_20251209_132736_542_99ba2325_6705caf4.json` — abridged (system_prompt is a ~4 KB policy string):
```json
{
  "mcp_endpoint": "/mcp",
  "number_of_runs": 1,
  "reset_database_between_runs": true,
  "gym_servers_config": [
    {
      "mcp_server_name": "sn-csm-server",
      "mcp_server_url": "http://localhost:8001",
      "seed_database_file": "Domain Wise DBs and Task-DB Mappings/csm/dbs/db_1765219280033_d7pqrz32b.sql",
      "context": { "x-user-email": "jose.roberson@servicenow.com" },
      "user_info": { "user_id": 32, "name": "Jose Roberson", "email": "jose.roberson@servicenow.com" }
    }
  ],
  "system_prompt": "CSM Agent Policy ... (long policy text) ...",
  "user_prompt": "The Wilson and Sons customer reached out ... recreate the case, escalate, assign to Case Assignment_2 / agent Cory Vargas, confirm entitlement active, attach SLAs ...",
  "selected_tools": ["find_user_group","update_case","find_user","find_entitlements","find_contacts",
                     "link_new_case_sla","find_sla_definitions","search_cases","check_user_membership",
                     "find_product","find_account","create_new_case"],
  "restricted_tools": [],
  "verifiers": [ /* see below */ ]
}
```
Task-JSON key union across the 13 local tasks: `gym_servers_config, mcp_endpoint, number_of_runs, reset_database_between_runs, restricted_tools, selected_tools, system_prompt, user_prompt, verifiers` (`models.BenchmarkConfig`, `models.py:53-82`). `GymServerConfig` fields: `mcp_server_name, mcp_server_url, mcp_endpoint="/mcp", seed_database_file, auth_config, context, database_id(runtime)` (`models.py:40-50`).

### One SQL verifier (verbatim)
From the same task (`verifiers[0]`):
```json
{
  "verifier_type": "database_state",
  "name": "Verify case creation",
  "gym_name": "sn-csm-server",
  "validation_config": {
    "query": "SELECT COUNT(*) AS count FROM customer_case WHERE case_id = 1233 AND state = 'in_progress' AND assignment_group_id = 24 AND assigned_to = 427 AND channel = 'email' AND priority = 'critical' AND escalation_reason = 'customer_request' AND escalation = 1;",
    "expected_value": 1,
    "comparison_type": "equals"
  }
}
```
Verifier types (`models.VerifierType`, `models.py:6-9`): `database_state`, `response_check`, `tool_execution`. `comparison_type` supports `equals / greater_than / less_than / contains` (`verifier.py:374-400`). Across the 13 local tasks: **102 verifiers, all `database_state`, all `equals`, 0 `response_check`** (1 verifier expects `0`, i.e. a negative/no-change check).

### Task ↔ DB mapping
There are **no separate mapping files** — the folder "Domain Wise DBs and Task-DB Mappings" contains only `<domain>/dbs/*.sql`. The mapping is embedded in each task's `gym_servers_config[].seed_database_file`, a **path relative to the process CWD** (resolved by `create_database_from_file`, which just `open()`s it, `mcp_client.py:35`). The example points at `Domain Wise DBs and Task-DB Mappings/csm/dbs/db_1765219280033_d7pqrz32b.sql` — so the unzipped `gym_dbs` tree must sit at CWD. Snapshot counts per domain: calendar 11, csm 18, hr 4, teams 12, drive 5, itsm 9, email 3, hybrid 14.

### What it takes to run a CUSTOM task with a CUSTOM DB
Fully supported without touching the clone:
1. Write a custom SQL snapshot (or edit an existing one) → put it anywhere reachable from CWD.
2. Write a task JSON: point `gym_servers_config[].seed_database_file` at your SQL, set `system_prompt`/`user_prompt`, and author `verifiers` (declarative SQL + expected value).
3. `python evaluate.py --configs_folder <your_dir> --llm_config <cfg> --output_folder <out> --num_runs k`.
**Constraint:** the *tools* come from the domain's Docker image; you cannot add custom tools without rebuilding the image, so custom tasks reuse an existing domain's toolset (+ `selected_tools`/`restricted_tools` to subset it). The DB, prompts, and verifiers are fully custom.

---

## C. Verifier execution & run artifacts

### How verifiers execute
`VerifierEngine` (`benchmark/verifier.py:15`) runs after the agent, against the **live server DB for that run**. `_execute_sql_query` (`verifier.py:195-255`) POSTs to **`{base_url}/api/sql-runner`** with `{query, database_id}` and the `x-database-id` header + context headers (`verifier.py:210-221`). So verifiers query the *same* seeded database instance the agent just mutated, over HTTP (not a local dump, not the MCP tool interface — the dedicated sql-runner API). `_execute_database_state_verifier` (`verifier.py:81-128`) pulls `query`/`expected_value`, runs it, extracts the scalar (`_extract_value_from_sql_result`, `verifier.py:291`), and compares (`_compare_values`, `verifier.py:374`). `response_check` additionally runs an LLM comparison (`verifier.py:129-165`); `tool_execution` checks whether expected tools were called (`verifier.py:166-194`).

### Run artifacts on disk
Per task per outer run: `<output_folder>/run_N/results_{taskname}.json` (`evaluate.py:235-240`). Structure (`executor.py:526-545`):
```
{
  "benchmark_config": { model, number_of_runs, user_prompt,
                        gym_servers:[{name,url,seed_database_file,uses_cloning}], total_tools_available },
  "runs": [ <one per inner run> ],
  "statistics": { ... }
}
```
Each entry in `runs[]` (`executor.py:380-400`, populated by the orchestrator `react.py:119-125`):
```
{ run_number, started_at, execution_time_ms,
  model_response,
  conversation_flow: [ system_message | user_message |
                       ai_message{content, usage_metadata, response_metadata, tool_calls:[{name,args}]} |
                       tool_result{tool_name, result, gym_server} ],
  tools_used: [names],
  tool_results: [ {tool_name, arguments, result, gym_server} ],   # every call with full args + result
  verification_results: { <verifier_name>: {passed, actual, expected, query, ...} },
  verification_summary: {total, passed, failed, pass_rate},
  overall_success }
```
`tool_results` gives **every tool call with its arguments and the server's response** — exactly the action trace our damage labeler needs. Token usage is captured per AI step (`react.py:49-63`; `planner_react.py:221-235`; `decomposing_planner.py:64-86`). Agent loop cap: `max_iterations = 50` (`orchestrators/base.py:23`). A failed run instead stores `{run_number, error, overall_success:false}` (`executor.py:514-522`).

### Is the full initial DB state recoverable?
**Initial state: yes** — it *is* the `seed_database_file` SQL snapshot (a complete data-only INSERT dump, in `gym_dbs.zip`). **Final state: not dumped** in the artifacts — only the specific `verification_results.actual` values are recorded. To diff full final state, our labeler must either (a) add `database_state` verifiers that SELECT the target rows/columns (captured in `verification_results`), or (b) query `/api/sql-runner` for target tables **before the `finally` cleanup deletes the DB** (`executor.py:553-563`) — reusing the exact mechanism `verifier._execute_sql_query` uses. Both are clean integration seams; (a) needs zero code change to the clone.

### compute_score.py aggregation — and the errored-file discrepancy
`compute_score.py` (`main`, `:53-90`) treats each **subfolder of `--results_folder` as a "mode"** and calls `process_mode` (`:15-50`). `process_mode` walks all `*.json`, reads `statistics.overall_success_rate` and `statistics.verifier_level_pass_rate` via `get_score` (`:12-13`), and averages them.

**Important:** the README claims "Files w/ Errors — agent errors; excluded from averages" (`README.md:273`), **but the shipped code does NOT exclude them.** `has_error` is computed (`compute_score.py:35`) and then scores are appended **unconditionally** (`:36-39`); errored files are only *counted* into `files_with_errors` (`:47`) and printed in red — the average (`:41-42`) includes their scores. There is no `if has_error: continue`. **Do not rely on `compute_score.py` for clean exclusion — compute p̂ ourselves from the per-run JSONs.** (Per-run stats: `overall_success_rate = successful_runs/total_runs`, `pass_at_1`, `verifier_level_pass_rate`, `mean_execution_time_ms`, `tool_usage`; `executor._calculate_statistics`, `:565-642`.)

---

## D. Model / endpoint configuration

- **Client code:** `benchmark/llm_client.py`. `LLMClient.__init__` (`:13-40`) → `_initialize_llm` (`:42-171`) branches on `provider`. Constructed in `executor.initialize` from `LLMConfig` (`executor.py:110-122`).
- **Arbitrary OpenAI-compatible base URL + key — CONFIRMED for Groq.** The `vllm` / `openrouter` branch (`llm_client.py:112-135`):
  ```python
  elif self.provider == "vllm" or self.provider == "openrouter":
      from langchain_openai import ChatOpenAI
      self.llm = ChatOpenAI(
          model=self.model,
          openai_api_key=self.api_key or "not-needed",
          openai_api_base=self.custom_api_endpoint,   # <- arbitrary base URL
          temperature=self.temperature, max_tokens=self.max_tokens,
          model_kwargs=model_kwargs)                    # top_p, reasoning_effort, extra_body.reasoning
  ```
  For Groq: set `{"llm_provider":"openrouter", "llm_model":"<groq model>", "llm_api_key":"<groq key>", "llm_api_endpoint":"https://api.groq.com/openai/v1"}`. A ready template exists at `conf.example/llm/openrouter.json` (provider `openrouter`, endpoint `https://openrouter.ai/api/v1`). Providers list (`README.md:149`): anthropic, aws_bedrock, openai, azureopenai, googlevertexai, google, vllm, openrouter, deepseek, qwq.
- **Sampling params:** `temperature`, `max_tokens`, `top_p`, `effort` (→ `reasoning_effort`), `reasoning` (→ `extra_body.reasoning`) all threaded from `LLMConfig` (`models.py:85-97`) through `executor.py:117-121` into the client. `LLMConfig` supports load-balanced pools (a JSON array; one is chosen by `random.choice`, `evaluate.py:198`).
- **Token usage logged:** yes, per AI step in `conversation_flow[].usage_metadata`/`response_metadata` (`react.py:49-63`, etc.).
- **Retry/backoff:** per LLM call `.with_retry(stop_after_attempt=3, retry_if_exception_type=(Exception,))` (`llm_client.py:319-328`); whole-sample 5× linear backoff (`evaluate.py:222-233`). No explicit rate-limit/backoff beyond LangChain's default.

---

## E. Tools & irreversibility (M2 slice + dollar tasks)

### Where tool inventories live
Tool *schemas* are **not in the repo** — they are discovered at runtime from the running MCP server via `tools/list` (`executor._discover_and_merge_tools`, `executor.py:214`) and are baked into the Docker images. The only in-repo signal is each task's `selected_tools` / `restricted_tools` (e.g. the csm example lists `create_new_case`, `update_case`, `link_new_case_sla`, `find_*`, `search_cases`, `check_user_membership`). README: **512 tools across 8 domains** (`README.md:47`); "modes" `oracle / plus_5_tools / plus_10_tools / plus_15_tools` (`README.md:185`) add N distractor tools on top of the oracle set (the mode is the HF dataset config name, `evaluate.py:295`). Full tool inventories per domain must come from the M1 runtime `tools/list` dump.

### Money-like columns per domain (from the SQL snapshots)
Scanned one representative snapshot per domain (all snapshots within a domain share one table-set signature):

| Domain | Tables | Money/value columns (`table.column`) | Dollar-task fit |
|---|---|---|---|
| **csm** | 17 | **`contract.contract_price`, `product.product_price`** | **Strong** — real prices |
| **itsm** | 24 | **`configuration_item.cost`** | **Strong** — asset cost |
| teams | 47 | `attendance_records.total_attendance_in_seconds`, `meeting_attendance_reports.total_participant_count` | Weak (durations/counts) |
| drive | 28 | `uploads.total_size` | Weak (bytes) |
| email | 26 | `labels.messages_total`, `users.messages_total`, `*.threads_total` | Weak (counts) |
| calendar | 17 | — | No |
| hr | 26 | — (no salary/pay columns; hr = case mgmt, not payroll) | No |
| hybrid | 17 | — (drive-centric subset) | No |

### Domains with the most state-mutating tools
Inferred from `selected_tools` and schema semantics: the **ServiceNow-style domains (csm, itsm, hr)** are the most mutation-heavy — full record lifecycles with explicit state machines (case/incident/change create → update → resolve/close/cancel, assignment, escalation, SLA linkage, user (de)activation). `teams`/`drive`/`email`/`calendar` mutate too (messages, files, events) but their "money" columns are counters, not currency.

### Recommended vertical slice
**Primary: `csm`. Secondary: `itsm`.**
- **csm** — commit-heavy (create/update/close/cancel/escalate cases, link SLAs, membership changes), money-bearing (`contract.contract_price`, `product.product_price`), moderate table count (17), the most local example tasks already exist (12 in `data/revised/csm/`), and 18 seed snapshots. A dollar-denominated damage task is natural: e.g. wrongly cancel/close or mis-entitle a case tied to a contract, with damage = `contract.contract_price` read from the DB; or attach a wrong/expensive product (`product.product_price`).
- **itsm** — commit-heavy (incident/problem/change lifecycles), `configuration_item.cost` supports a "wrongly decommission/modify a high-cost CI" dollar task; 24 tables, 9 snapshots.
- **Avoid hr for money tasks** (no currency columns; also seed-time `CURRENT_TIMESTAMP` nondeterminism). Both csm and itsm are single-server domains (ports 8001 / 8006), simpler than `hybrid` (multi-server).

---

## F. Their refusal / infeasible-task mechanics

**There is no explicit refusal/abstain mechanic in the visible code or data.**
- Repo-wide grep for `infeasible|refus|abstain|reject|not_possible|unable|impossible` in `*.py`: **zero hits.**
- The 13 local task JSONs: **zero** infeasible/abstain text, **zero** `response_check` verifiers; all 102 verifiers are `database_state`+`equals`.
- No verifier type encodes "the agent should decline."

The only refusal-shaped behavior is **prompt-induced and verified implicitly by state**: system prompts instruct "if a user request violates policy, do not act on it … if you cannot proceed ahead provide the reason … before pausing" (csm policy, task line 20). A well-formed infeasible task would then use `database_state` verifiers whose `expected_value` matches the *unchanged* state (i.e. the agent passes by *not* mutating) — the single `expected_value:0` verifier locally is consistent with this. But it is a static, single-shot pass/fail with no "abstain" label.

**Differentiation to state in writing:** EnterpriseOps-Gym (as shipped/public) has no first-class abstention category — "correct refusal" is at best an implicit no-state-change check baked into a specific task's SQL verifier, scored once. Our design measures **abstention/damage as a distributional reliability property**: p̂(damage) over *k* independent re-seeded runs of the *same* task, with a severity-priced damage label computed from DB state diffs — not a single deterministic verifier verdict. The private HF split *may* contain infeasible tasks, but we have no evidence of a dedicated mechanic beyond per-task SQL verifiers.

---

## G. Pinning, deps, tests, risks

- **Commit:** `de22905d21a080b83bf4a54258afe4250ee2dd55` (2026-06-03).
- **Python:** `requires-python >=3.11` (`pyproject.toml:5`).
- **Deps** (`pyproject.toml:6-46`): httpx, langchain, langchain-core, ray>=2.53, datasets>=4.5, huggingface_hub, pandas, numpy, pyarrow, tqdm, pydantic, python-dotenv, tabulate. Optional extras: `anthropic` (langchain-anthropic, langchain-aws, boto3), `openai` (langchain-openai, openai — needed for vllm/openrouter/Groq), `google`, `deepseek`, `qwq`. `[tool.uv] package=false`.
- **Tests:** **none.** No `test_*.py` / `conftest.py`; no pytest in deps.

### Top risks / blockers
1. **Opaque MCP containers (highest risk to check b).** All server-side write behavior is invisible in-repo. If a domain's tools stamp logical (non-timestamp) columns with wall-clock or fresh UUIDs, identical action sequences won't produce identical states. Evidence: snapshots are data-only, schema is in the image (`CREATE TABLE`=0 across all); hr seeds use `CURRENT_TIMESTAMP` 180×. **Mitigation/M1 test:** fixed-sequence replay + diff excluding timestamp columns.
2. **Final DB state is not persisted** (only verifier `actual` values). Evidence: `executor.py:526-545` result has no DB dump; DB deleted in `finally` (`:553-563`). **Mitigation:** add SELECT verifiers or query `/api/sql-runner` pre-cleanup — but this needs our own runner wrapper or per-task verifier authoring.
3. **`compute_score.py` does not exclude errored files** despite README:273. Evidence: `compute_score.py:35-39`. **Mitigation:** compute p̂ ourselves.
4. **LLM-config `random.choice`** (`evaluate.py:198,209`) injects endpoint variance if a pool is used. **Mitigation:** single-element config.
5. **`reset_database_between_runs` is inert** (`models.py:82`, unreferenced) — no way to opt into persistent state via config (fine for us; noted so we don't rely on it).
6. **Custom tools require rebuilding a Docker image** — our custom tasks must reuse an existing domain's toolset. Evidence: tools discovered via runtime `tools/list` (`executor.py:214`), not in repo.
7. **Docker/HF operational dependencies** (per-domain image pull, HF dataset for the full 1,150-task set). Local `--configs_folder` avoids HF; Docker is unavoidable to run tools.

### Closing assessment
Both checks can plausibly pass. **(c) is essentially confirmed now**: custom tasks are local JSON files consumed by `--configs_folder`, the schema is simple and fully exemplified in-repo, custom DBs are a `seed_database_file` path, and verifiers are declarative SQL executed over `/api/sql-runner` — a mechanism our damage labeler can reuse verbatim, and the initial state is the recoverable seed SQL. The damage layer slots in with either extra SQL verifiers (zero clone changes) or a small pre-cleanup query hook. **(b) passes at the harness level** — every run re-seeds a fresh, isolated database from a static SQL file, runs are independent, per-run artifacts are separate (`run_N/`), and harness nondeterminism is limited and controllable (single LLM config; verifier checks are timestamp-insensitive; damage diff must exclude timestamp columns). The decisive unknowns are all inside the MCP Docker images, so **M1 must empirically verify**: (i) `/api/seed-database` gives a clean, isolated, repeatable reset per `database_id`; (ii) an identical fixed tool-call sequence on a fresh seed yields byte-identical DB state modulo a known volatile-timestamp column allowlist; (iii) `/api/sql-runner` accepts arbitrary SELECTs for state capture; (iv) concurrent runs (`--concurrency`) don't leak state across `database_id`s; (v) the runtime `tools/list` dump for csm/itsm, to fix the mutating-tool set for our dollar-denominated damage tasks.
