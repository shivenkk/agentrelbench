# M1 Go/No-Go — EnterpriseOps-Gym as AgentRelBench's substrate

Date: 2026-07-16 · Substrate: EOG @ commit `de22905d`, MCP images digest-pinned · Status: **COMPLETE — all evidence in**

## Decision

**GO** — build the reliability instrument (damage labeler + k-run harness + custom task slice) on EnterpriseOps-Gym, scoped to **csm + itsm**. All three checks pass with direct evidence; the environment is more deterministic than required (only wall-clock timestamps vary; IDs and FKs byte-identical across independent replays), and the custom-task path works end-to-end through the unmodified harness. Fallback (bespoke mini-ERP, plan unchanged) triggers only per §5.

Sign-off: _Shiven — pending written confirmation (required before M2 starts)._

## 1. Check (a) — license permits a derivative benchmark: **PASS**

- `LICENSE` in the pinned clone is verbatim **Apache-2.0** (read directly, M0).
- MCP server images pulled and **digest-pinned** (audit wrap-up); attribution + NOTICE handling is standard Apache-2.0.

## 2. Check (b) — resets deterministic enough for clean variance attribution: **PASS**

Harness level (technical map, file:line-cited):
- Every run POSTs the full seed SQL to `/api/seed-database` and gets a fresh `database_id` — per-run independent re-seeding; `--num_runs k` yields separate `run_N/` artifact trees. (`reset_database_between_runs` is a dead flag; re-seeding is unconditional.)
- Harness-side nondeterminism enumerated and controllable: LLM-config pool `random.choice` (use a single config), latency timestamps (state-irrelevant).

Empirical (M1 audit, all tests rerunnable in `m1_audit/`):
- **Seed repeatability:** same seed loaded twice → full dumps **byte-identical**.
- **Replay reproducibility:** identical fixed tool-call sequences on 3 (csm) + 2 (itsm) independently seeded replicas → final states identical **except wall-clock timestamp columns only**; every PK, generated ID, enum, FK byte-identical. Volatile columns captured as data: `data/eog/volatile-columns-{csm,itsm}.json`.
- **Isolation:** per-call routing via `x-database-id`; interleaved writes across two DBs showed zero bleed — proven sharply by both DBs independently generating the *same* new PK.

Consequence for the instrument: run-to-run outcome variance on this substrate is attributable to the **model**, not the environment — the property the p̂ measurement requires.

## 3. Check (c) — damage layer + custom tasks addable cleanly: **PASS**

Confirmed at code + API level:
- Custom tasks are local JSON via `--configs_folder`; custom seed DB per task via `seed_database_file`; verifiers are declarative SQL+expected-value JSON. No clone edits needed.
- Full-state export for the damage labeler: `/api/sql-runner` accepts arbitrary SELECTs/JOINs; full csm dump = **0.304s** (18 tables, 10,633 rows) → per-run initial/final capture is negligible at k=8+.
- Model endpoint: `openrouter` provider takes any OpenAI-compatible base URL (Groq target) — code-confirmed; **live Groq smoke: PENDING-KEY** (no `GROQ_API_KEY` in env yet; blocking nothing in M2).

End-to-end proof (custom task JSON + custom verifiers + `--num_runs 2` through unmodified `evaluate.py`, driven by the offline scripted responder) — **spike PASS**, full writeup `m1_spike/SPIKE-RESULT.md`:
- Custom csm task (3 scripted state-changing calls: `create_new_case` → `update_case` → `assign_case_to_user`) executed in both runs; `run_1/` and `run_2/` artifacts complete.
- `tool_results` recorded every call with full arguments + server results; both custom verifiers evaluated with `actual` values captured.
- Runs used distinct `database_id`s (independent seeding confirmed in logs) yet produced identical case IDs and tool results — an independent reconfirmation of §2's determinism verdict.
- Responder→langchain flow clean: zero retries, zero tracebacks.
- Note (flagged in spike writeup): verifier 2's expected value `1233` coinciding with the created `case_id 1233` is a seed-history coincidence, not meaningful.

## 4. Facts that bind M2/M3 design (all encoded in `docs/damage-labeler-spec.md`)

1. `sql-runner` silently injects `LIMIT 100` on unbounded queries → every dump query carries an explicit large LIMIT + row-count assertion.
2. Final DB state is deleted in the executor's `finally` → our wrapper takes the pre-cleanup dump (monkey-patch in our package; shadow-verifier fallback documented).
3. csm requires a valid `x-user-email` header; itsm none → per-domain header config.
4. State diffs mask only the empirically derived timestamp columns; row matching is **PK-keyed** (justified by replay byte-identity).
5. Custom tools would require rebuilding their Docker images → M4 tasks reuse existing toolsets; abstention is expressed as declared refusal + no-state-change verification, not a new tool.
6. `hr` domain seeds carry `CURRENT_TIMESTAMP` (seed-time drift) → slice stays csm + itsm (which also carry the money columns for dollar-denominated tasks: `contract.contract_price`, `product.product_price`, `configuration_item.cost`).
7. EOG's `compute_score.py` does not actually exclude errored files (README claims otherwise) → we compute all statistics ourselves; errored runs are always damage-labeled.
8. Setup quirk: the clone's `uv.lock` pins `nest-asyncio2` while the source imports `nest_asyncio` (pre-existing upstream lockfile bug) → environment setup must `uv pip install nest_asyncio` into the venv after `uv sync` (spike hit and fixed this; only the untracked `.venv` touched).

## 5. Risks & fallback triggers

| Risk | Mitigation | Fallback trigger |
|---|---|---|
| Opaque MCP images change under `:latest` | digests pinned; recommend `docker save` archive of both images in M2 setup | image behavior diverges from audit and can't be re-pinned |
| Upstream breaking changes | clone pinned @ `de22905d`; no live dependency | — |
| Determinism differs on domains beyond csm/itsm | slice is csm+itsm only; rerun `m1_audit/` before any domain expansion | new domain needed AND fails audit |
| Groq/openrouter path fails live | code-level confirmed; smoke on key arrival | trivial (any OpenAI-compatible host works) |

## 6. Evidence index

- `docs/eog-technical-map.md` — file:line map (Opus agent, 2026-07-16)
- `docs/M1-audit-evidence.md` + `m1_audit/` — empirical audit, 5/5 PASS (Sonnet agent, 2026-07-16)
- `m1_spike/SPIKE-RESULT.md` + `m1_spike/` — task-injection spike, PASS (Sonnet agent, 2026-07-16)
- `data/eog/` — tool inventories, volatile-column lists (machine-readable)
