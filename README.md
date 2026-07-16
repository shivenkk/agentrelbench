# AgentRelBench

**A reliability instrument for action-taking LLM agents: ground-truth, severity-priced damage × repeated runs.**

Existing agent benchmarks measure either consistency of *success* across runs (pass^k) or end-state *harm* in a single run — never both. AgentRelBench joins the halves: it computes damage from database state diffs (severity-priced, deterministic, no LLM judges), measures it across repeated runs (pass^k × safe^k), and asks the question no one has answered: **is an agent's damage risk a stable property of tasks (auditable once) or a per-run coin flip (invisible to any finite audit)?**

Built as an environment-agnostic layer, demonstrated on [EnterpriseOps-Gym](https://github.com/ServiceNow/EnterpriseOps-Gym) (ServiceNow AI Research + Mila).

## Status

Phase 1 — M0/M1: substrate evaluation of EnterpriseOps-Gym (license ✓ Apache-2.0; determinism audit and extensibility spike in progress).

## Documents

- [Problem statement, hypothesis & decision log](docs/problem-and-hypothesis.md)
- [Project brief](AgentRelBench_Project_Brief.md)
- [k-run wrapper spec](docs/krun-wrapper-spec.md)

## arb-run: k-run wrapper (M3)

Package at `src/agentrelbench/` (src layout), installable from the repo root
into its own venv:

```
uv venv --python 3.12 .venv
uv pip install -e ".[dev]" --python .venv/bin/python
```

Run the benchmark k times per task, archiving per-run DB state exports and a
batch manifest (domain/server is inferred per task from its own
`gym_servers_config` -- no `--domain` flag needed):

```
.venv/bin/arb-run --tasks <dir-of-task-json> --llm-config <llm_config.json> --k 8 --out runs/
```

Output layout:

```
runs/<batch_id>/<task_id>/run_<n>/{results_*.json, post_seed_state.json.gz, final_state.json.gz}
runs/<batch_id>/manifest.json
```

**How it drives EOG without touching the clone.** `arb-run` itself runs in
agentrelbench's own lightweight venv (httpx + stdlib only) and never imports
EnterpriseOps-Gym. Per task, it execs `agentrelbench.inner_runner` under the
*clone's own*, already-synced venv Python
(`external/EnterpriseOps-Gym/.venv/bin/python`, which has
langchain/ray/etc. plus `nest_asyncio`), with `PYTHONPATH` extended to this
package's `src/` so that process can `import agentrelbench.eog_patch`
without agentrelbench ever being installed into the clone's venv. That patch
(`src/agentrelbench/eog_patch.py`) wraps
`benchmark.executor.{create_database_from_file,delete_database}` --
EnterpriseOps-Gym's per-run database create/delete call sites -- with
dump-then-continue, so every run's post-seed and pre-cleanup state is
captured via `/api/sql-runner` (`src/agentrelbench/state_export.py`, shared
with the future damage labeler). No tracked file under
`external/EnterpriseOps-Gym` is ever modified.

Tests (offline; the acceptance test still needs the csm container up on
`:8001`, since only the LLM is stubbed):

```
.venv/bin/pytest tests/ -v
```
