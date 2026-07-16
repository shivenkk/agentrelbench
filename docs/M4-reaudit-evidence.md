# M4 Full-Toolset Determinism Re-Audit — Evidence

Hard gate before the k=8 pilot (`docs/task-design-m4.md` §3b item 4: "The
full-toolset determinism re-audit is a hard gate: if even one tool in the
finalized tasks' reachable surface (union of `selected_tools`) shows
nondeterminism, resolve it or quarantine that tool's tasks before the k=8
pilot."). The original M1 audit (`docs/M1-audit-evidence.md`) proved
reproducibility over one hand-picked 10-call csm sequence (6 distinct tools)
and a 6-call itsm sequence (5 distinct tools). This re-audit computes the
**actual** reachable surface — the union of `selected_tools` across all 20
finalized task.json files — and exercises every one of it.

Method, containers, and vendored-client machinery are unchanged from M1 and
are only summarized here; see `docs/M1-audit-evidence.md` for full detail.
All new scripts live in `m4_reaudit/`, reuse `m1_audit/gym_client.py` and
`m1_audit/db_diff.py` verbatim (imported, not modified), and are run with
`external/EnterpriseOps-Gym/.venv/bin/python`. No tracked files in
`external/`, no task files, and no labeler/estimator code were touched.

---

## 0. Scope — computed, not assumed

**Script:** `m4_reaudit/compute_tool_union.py`
**Command:** `.venv/bin/python m4_reaudit/compute_tool_union.py`

Read every `tasks/{csm,itsm}/*/task.json` (12 csm + 8 itsm = 20, confirmed by
`find`), unioned `selected_tools`, and cross-checked that every task within a
domain references the identical `seed_database_file` (they do — and it's the
exact same file `m1_audit/gym_client.py`'s `CSM_SEED`/`ITSM_SEED` constants
already point at, so M1's seed files are still the right ones to re-run
against). Output: `data/eog/tool-union-{csm,itsm}.json`.

| Domain | Tasks | Union size | Mutating | Read-only | Untagged (gap in tool-tags-*.json) |
|---|---|---|---|---|---|
| csm | 12 | 40 | 16 | 24 | 0 |
| itsm | 8 | 26 | 8 | 18 | 0 |

csm tasks: account-onboarding-chain, case-close-with-note,
case-reassign-scoped, case-triage-basic, contract-price-correction,
contract-renewal-enlist, entitlement-update-dead-contract,
installed-product-serial, knowledge-publish-and-link, notification-cleanup,
product-price-sync, sla-relink.

itsm tasks: change-request-cab-gate, ci-cost-correction,
incident-sla-cleanup, incident-triage-basic, notification-outward,
parent-child-restructure, problem-change-mapping, template-driven-incidents.

**csm mutating union (16):** `add_new_entitlement, create_new_account,
delete_case_slas, delete_notifications, enlist_new_contract,
link_case_knowledge, link_new_case_sla, register_new_interaction,
set_case_assignment_group, update_case, update_case_sla_details,
update_contract, update_entitlement, update_installed_product_details,
update_knowledge, update_product`.

Of these, only 3 (`update_case`, `update_case_sla_details`,
`link_new_case_sla`) were exercised by M1's original csm sequence — **13 of
16 mutating tools were never touched by M1** and had zero direct
determinism evidence before this audit. Notably, `create_new_case`,
`assign_case_to_user`, and `send_notification` (all in M1's sequence) are
**not** in the current portfolio's mutating union at all — no finalized csm
task selects them.

**itsm mutating union (8):** `add_child_incident, delete_incident_slas,
map_change_request, remove_child_incident, send_notification, update_change,
update_configuration_item, update_incident`. M1's original itsm sequence
covered only `update_incident`, `update_configuration_item`, and
`send_notification` — **5 of 8 were never touched by M1** (`add_child_incident`,
`delete_incident_slas`, `map_change_request`, `remove_child_incident`,
`update_change`). `create_incident`, exercised heavily by M1, is not in this
portfolio's union (no finalized itsm task selects it) — it's re-used below in
Test C purely as a create-ID-stability probe, per the task brief, not for
union coverage.

Partition source: `data/eog/tool-tags-{csm,itsm}.json` (`read` vs.
`reversible-write` / `compensable` / `irreversible`, "mutating" = anything
not tagged `read`). Spot-checked several tag/description pairs for sanity
(e.g. `register_new_interaction`: tagged irreversible/"create with no delete
twin", description confirms it creates an `interaction` row with no
corresponding delete tool in either domain's inventory; `map_change_request`:
tagged compensable/"delete twin exists", and `delete_change_request_mappings`
does exist in the full itsm inventory, just isn't in this portfolio's union).
Zero untagged tools in either domain — the tag registries already cover the
full union.

---

## 1. Setup

Docker containers `eog-csm` (8001→8005) and `eog-itsm` (8006→8005) were
already running healthy from M1 (same images, same digests — see
`docs/M1-audit-evidence.md` §Setup). csm still requires `x-user-email:
thomas.green@servicenow.com` context on every `tools/call`; itsm still
requires none (both reconfirmed empirically below, no change from M1).
`sql-runner` still returns rows in `result['data']` (`gym_client.sql_runner`
+ `db_diff.rows_from_sql_result` handle this) and still silently injects
`LIMIT 100` without an explicit `LIMIT` (`db_diff.py`'s `BIG_LIMIT =
1_000_000` convention, reused unmodified, guards against this everywhere).

**Seed entity reconnaissance** (`m4_reaudit/probe_seed_entities.py`, evidence
in `m4_reaudit/evidence/seed_probe_{csm,itsm}.json`): seeded one throwaway DB
per domain, ran read-only `SELECT`s to discover valid, real entity IDs for
every tool argument used below (accounts, products, contracts, entitlements,
cases, case_slas, knowledge, notifications, user groups for csm; incidents,
changes, configuration items, incident_slas, child_incident pairs,
change_request_mappings, users for itsm), then deleted the throwaway DB.
Table DDL (`sqlite_master.sql`) was inspected for every table touched, to
respect uniqueness/foreign-key/check constraints when picking arguments (e.g.
`account.name` is `UNIQUE`; `child_incident` has `UNIQUE(parent_incident,
child_incident)` + `CHECK(parent_incident <> child_incident)`;
`change_request_mapping` has `UNIQUE(org_id, change_id, incident_id)`, and
`map_change_request`'s own description confirms `org_id` is auto-derived
from request headers, not a caller argument — confirmed all chosen itsm
entities (`INC_001/002/003/005/008`, `CHG_001/002`) share `org_id=ORG_001`).

---

## 2. Test A — Mutating determinism

Per domain: one fixed sequence exercising **every** mutating tool in the
union at least once, with valid hardcoded arguments for pre-existing seed
entities (from the probe above) and dynamically-captured arguments for
entities created mid-sequence. Run identically on 3 independently-seeded
databases (same seed file as every task.json), sequentially (seed → run →
dump), never in parallel. Full-dump all tables from all 3 replicas, diff
position-by-position (`db_diff.positional_diff_multi`, natural DB row order
— valid here because identical seed + identical call order means physical
row order matches even where volatile column values don't).

### csm — `m4_reaudit/test_a_mutating_determinism_csm.py`

16-call sequence, one call per mutating tool, chained so some creates depend
on earlier creates in the *same* sequence (new account → new contract on
that account → new entitlement on that contract) — a stricter determinism
test than independent creates, since it checks that dependent-row ID
assignment stays stable too:

| # | Tool | Target | Result / captured ID |
|---|---|---|---|
| 1 | `create_new_account` | new | `account_id` |
| 2 | `enlist_new_contract` | new account from #1 | `contract_id` |
| 3 | `add_new_entitlement` | new account+contract from #1/#2 | `entitlement_id` |
| 4 | `update_contract` | existing `contract_id=1` | `contract_price`→99999 |
| 5 | `update_entitlement` | existing `entitlement_id=1` | `support_level`→enterprise |
| 6 | `update_installed_product_details` | existing `installed_product_id=3` | `status`→repair |
| 7 | `update_product` | existing `product_id=1` | `product_price`→999 |
| 8 | `update_knowledge` | existing `knowledge_id=1` | `state`→draft |
| 9 | `update_case` | existing `case_id=1` | state/priority/escalation |
| 10 | `set_case_assignment_group` | existing `case_id=1` | group 4→7 |
| 11 | `link_new_case_sla` | new, on `case_id=1` | `case_sla_id` |
| 12 | `update_case_sla_details` | existing `case_sla_id=2464` | stage→completed |
| 13 | `delete_case_slas` | **exactly** the row from #11 (narrow filter) | row removed |
| 14 | `link_case_knowledge` | `case_id=1` + `knowledge_id=1` | `case_kb_id` |
| 15 | `register_new_interaction` | new, `case_id=1` | `interaction_id` |
| 16 | `delete_notifications` | existing `notification_id=724` (narrow filter) | row removed |

Coverage: **16/16 mutating tools exercised** (`coverage_complete: true`).

New-row primary key identity across R1/R2/R3 — **all identical**:

```
new_account:     {R1: 53,   R2: 53,   R3: 53}
new_contract:    {R1: 154,  R2: 154,  R3: 154}
new_entitlement: {R1: 432,  R2: 432,  R3: 432}
new_case_sla:    {R1: 2465, R2: 2465, R3: 2465}
new_case_kb:     {R1: 528,  R2: 528,  R3: 528}
new_interaction: {R1: 1233, R2: 1233, R3: 1233}
```

Note `new_account=53` for all 3 replicas here — matches Test C's isolated
2-replica check below exactly, a useful 5-way cross-corroboration (Test A's
3 + Test C's 2, all fresh seeds, all landed on account_id=53).

Full dump: 18 tables, 10,637 rows per replica. `row_count_mismatch: {}`,
`tables_not_common_to_all: []`. 12 `table.column` pairs varied across
replicas — **all 12 classified `wall-clock timestamp`, zero
non-timestamp variance** (`non_timestamp_varying_columns: {}`):
`account.sys_created_on/sys_updated_on`, `contract.sys_created_on/sys_updated_on`,
`customer_case.sys_updated_on`, `entitlement.sys_created_on/sys_updated_on`,
`installed_product.sys_updated_on`, `interaction.started_at`,
`interaction.sys_created_on`, `knowledge.sys_updated_on`, `product.sys_updated_on`.
After stripping those 12 columns, the 3 replicas' canonical hashes are
identical (`identical_modulo_volatile_columns: true`).

**Verdict: PASS modulo volatile columns** (identical-modulo-known-plus-newly-confirmed
volatile columns; see §6 for the registry update). Evidence:
`m4_reaudit/evidence/test_a_csm.json` (full call logs for all 3 replicas,
full diff report). Wall time: 3.92s.

### itsm — `m4_reaudit/test_a_mutating_determinism_itsm.py`

8-call sequence, one call per mutating tool (confirmed still no
`x-user-email`/context requirement on itsm `tools/call`, matching M1):

| # | Tool | Target | Notes |
|---|---|---|---|
| 1 | `update_incident` | existing `INC_002` | status→on_hold, priority→critical |
| 2 | `update_change` | existing `CHG_001` | status→implement |
| 3 | `update_configuration_item` | existing `CI_001` | cost→1250.75, status→maintenance |
| 4 | `add_child_incident` | new pair `(INC_003, INC_008)` | verified not already linked; `child_incident_mapping_id` captured |
| 5 | `remove_child_incident` | **exactly** the mapping from #4 | row removed |
| 6 | `map_change_request` | `CHG_002` + `INC_005` (both org `ORG_001`) | `change_request_mapping_id` captured |
| 7 | `send_notification` | `INC_001` → `carlos.rodriguez@techcorp.com` (non-self) | `notification_id` captured |
| 8 | `delete_incident_slas` | existing `incident_sla_id=TSLA_001` (narrow filter) | row removed |

Coverage: **8/8 mutating tools exercised** (`coverage_complete: true`).

New-row primary keys across R1/R2/R3 — **all identical**:
`new_child_mapping: CINC_008` (all 3), `new_change_request_mapping: CRM_006`
(all 3), `new_notification: NOTIF_008` (all 3).

Full dump: 24 tables, 242 rows per replica. `row_count_mismatch: {}`,
`tables_not_common_to_all: []`. 7 `table.column` pairs varied — **all 7
`wall-clock timestamp`, zero non-timestamp variance**:
`change.updated_on`, `change_request_mapping.created_at/updated_at`,
`configuration_item.updated_on`, `incident.updated_at`,
`notification.created_on/updated_on`.

**Verdict: PASS modulo volatile columns.** Evidence:
`m4_reaudit/evidence/test_a_itsm.json`. Wall time: 3.03s.

---

## 3. Test B — Read purity

Per domain: fresh seed, full dump, call **every** read-only tool in the union
once with valid args, full dump again. Zero-tolerance comparison — unlike
Test A, no volatile-column allowance: a read tool must not write *anything*,
not even bump a timestamp.

### csm — `m4_reaudit/test_b_read_purity_csm.py`

All 24 read-only tools called once (`count_case_by_state`,
`count_case_for_assignment_group`, `count_contract_by_status`,
`count_installed_product_by_status`, `count_notifications_by_case`,
`count_notifications_by_status`, `find_account`, `find_case_knowledge_linkages`,
`find_case_slas`, `find_contracts`, `find_entitlements`,
`find_installed_product_by_serial`, `find_interactions`, `find_notifications`,
`find_product`, `find_product_by_id`, `find_products`, `find_sla_definitions`,
`find_user_group`, `get_accounts`, `get_cases_assigned_to`,
`retrieve_installed_products`, `retrieve_knowledge`, `search_cases`).

```
before: 3ff48380a29ee9f06ad59906d99919ef83df918ee8a5b7623ecf3acf22964fc9
after:  3ff48380a29ee9f06ad59906d99919ef83df918ee8a5b7623ecf3acf22964fc9
overall_match: True
```

That hash is byte-identical to M1's original Test 2 seed-repeatability hash
(`docs/M1-audit-evidence.md`) — independent confirmation the seed itself is
still untouched *and* that these 24 reads wrote nothing.

**Verdict: PASS, byte-identical (zero tolerance).** Evidence:
`m4_reaudit/evidence/test_b_csm.json`.

### itsm — `m4_reaudit/test_b_read_purity_itsm.py`

All 18 read-only tools called once (`find_change_by_number`,
`find_change_request_mappings_for_incident`,
`find_configuration_item_by_serial_number`, `find_configuration_items`,
`find_incident_by_id`, `find_incident_by_number`, `find_incident_slas`,
`find_notifications_sent_for_incident`, `find_parent_incident`,
`find_stage_wise_breached_incident_sla_counts`, `get_incident_template_by_name`,
`get_incident_templates`, `get_user`, `get_user_using_name`,
`list_change_request_mappings`, `list_changes`, `list_child_incidents`,
`list_incidents`).

```
before: a8b8d19002790f2404f610420227052e7906556d93f1f3ea5cf956b02d77bc59
after:  a8b8d19002790f2404f610420227052e7906556d93f1f3ea5cf956b02d77bc59
overall_match: True
```

**Verdict: PASS, byte-identical (zero tolerance).** Evidence:
`m4_reaudit/evidence/test_b_itsm.json`.

---

## 4. Test C — Create-ID stability

### csm — `m4_reaudit/test_c_create_id_stability_csm.py`

On two independently freshly-seeded DBs, `create_new_account(name="M4
CreateID Stability Check Account", account_type="customer", active=true)`.
Basis for the expected value: `SELECT MAX(account_id) FROM account` on a
throwaway probe seed returned 52 (52 existing accounts), so a deterministic
AUTOINCREMENT should hand back 53.

```
R1: account_id=53
R2: account_id=53
```

**account-onboarding-chain** (one of the 12 finalized csm tasks) depends on
this exact value. **Verdict: PASS — stable, matches expected 53.** (Also
corroborated by Test A's own `create_new_account` call landing on 53 across
all 3 of *its* replicas — 5 fresh-seed creates total, all = 53.) Evidence:
`m4_reaudit/evidence/test_c_csm.json`.

### itsm — `m4_reaudit/test_c_create_id_stability_itsm.py`

On two independently freshly-seeded DBs, `create_incident(caller_id=
"USER_005", short_description="M4 CreateID Stability Check",
category="software", priority="high")`. Basis: `SELECT COUNT(*) FROM
incident` on a throwaway probe seed returned 23 (highest `INC_023`), so a
fresh create should yield `INC_024` — also exactly what M1's own
`test3_replay_reproducibility_itsm.py` found on this identical seed file,
a useful cross-time corroboration that nothing has drifted since M1.

```
R1: incident_id=INC_024
R2: incident_id=INC_024
```

**Verdict: PASS — stable, matches expected INC_024.** Evidence:
`m4_reaudit/evidence/test_c_itsm.json`.

---

## 5. Test D — itsm `send_notification` self-recipient quirk (characterized, not fixed)

`tasks/itsm/notification-outward/RATIONALE.md` (written during task design,
before this audit) already documented: *"send_notification returns success
but creates no row when the recipient is USER_001 (the default acting user,
marcus.thompson) — a self-notification guard keyed on that one user."* This
test (`m4_reaudit/test_d_notification_quirk_itsm.py`) re-derives that finding
from scratch with live evidence on two fresh seeds, and **corrects one part
of the existing characterization**: it is not silent at the server.

Five probes per replica (R1, R2 — fully consistent across both):

| Step | Call | Context header | Result |
|---|---|---|---|
| A | `send_notification(INC_001, marcus.thompson@techcorp.com)` | none | tool call **fails** (HTTP-level), no row written |
| B | `send_notification(INC_001, carlos.rodriguez@techcorp.com)` | none | succeeds, row written (control) |
| C | `send_notification(INC_002, marcus.thompson@techcorp.com)` | none | fails, no row (rules out INC_001-specific coincidence) |
| D | `send_notification(INC_002, carlos.rodriguez@techcorp.com)` | `x-user-email: carlos.rodriguez@techcorp.com` | succeeds, row written |
| E | `send_notification(INC_002, benjamin.chen@techcorp.com)` | `x-user-email: marcus.thompson@techcorp.com` | succeeds, row written (control) |

**What actually happens at the MCP server:** steps A/C return an explicit
HTTP-level validation error, not a 200-OK "success" envelope:

```json
{"detail": {"details": [{"code": "CANNOT_SEND_TO_SELF",
  "context": {"current_user_email": "marcus.thompson@techcorp.com",
              "provided_value": "marcus.thompson@techcorp.com"},
  "field": "email", "message": "Cannot send notification to yourself"}],
  "error": true, "error_code": "VALIDATION_ERROR", ...}}
```

This is a genuine, well-labeled validation error (`CANNOT_SEND_TO_SELF`),
identical and reproducible across both fresh seeds. Step D — an explicit
`x-user-email` header asserting `carlos.rodriguez@techcorp.com` as "acting
user", sent to that same address — did **not** trigger the guard. That rules
out a generic "recipient == asserted request identity" mechanism: the
`current_user_email` the server compares against is **hardcoded to
marcus.thompson@techcorp.com / USER_001 specifically**, regardless of any
header (itsm's `tools/call` still takes no required auth context at all, per
M1 and reconfirmed here — but this one validation path has its own fixed
notion of "self").

**Where the "silence" actually comes from.** Read (not modified) from the
vendored harness:
- `external/EnterpriseOps-Gym/benchmark/mcp_client.py` (`_send_request`,
  ~lines 209–227): a non-200 HTTP response (this validation error rides
  FastAPI's `{"detail": {...}}` envelope on what is evidently a 4xx, not a
  200-OK MCP result with `isError: true` content) is converted to
  `{"success": False, "error": "MCP request failed: <status> - <body>"}` —
  note **no `"result"` key at all** on this path.
- `external/EnterpriseOps-Gym/orchestrators/react.py:105` and
  `orchestrators/planner_react.py:277` (identical pattern in both): the
  agent-visible `ToolMessage` is built as
  `ToolMessage(content=json.dumps(tool_result.get("result", {})), ...)`.
  Since the failure-path dict has no `"result"` key, `.get("result", {})`
  silently falls back to `{}` — **the LLM sees the literal string `"{}"`**,
  with the `CANNOT_SEND_TO_SELF` code, message, and context never
  surfaced. `tool_result.get("success")` is logged server-side
  (react.py:89 / planner_react.py:261) but never included in the message
  content the model actually reads.

So: **not silent at the database/MCP-server layer** (explicit, well-formed
validation error, same on both fresh seeds) — **silent at the harness's
tool-result-to-LLM-message layer**, which discards the error before the
model ever sees it. Net effect for an acting agent matches
notification-outward's design assumption (an empty-looking tool result, no
row written), but the mechanism is one layer removed from where
RATIONALE.md placed it. Not fixed here per instructions (`external/` is
vendored/tracked and out of scope) — documented for whoever maintains that
task or the harness wrapper.

**Verdict: quirk confirmed, mechanism now precisely characterized and
reproducible across 2 independent fresh seeds.** Evidence:
`m4_reaudit/evidence/test_d_itsm.json`.

---

## 6. Volatile-column registry updates

**Script:** `m4_reaudit/merge_volatile_registry.py` — reconciled Test A's
empirically-observed `table.column` variance against
`data/eog/volatile-columns-{csm,itsm}.json`, which mixed real M1-empirical
entries with placeholder entries from an earlier systematic DDL scan (marked
`"empirical confirmation due in M4 full-toolset re-audit"`). Applied surgically
(insertion order and existing 1-space indent preserved — verified via `git
diff` that only the touched entries changed, no reformatting).

| Domain | Brand-new (never listed before) | Placeholder → confirmed-empirical | Already-empirical (untouched) |
|---|---|---|---|
| csm | **`interaction.started_at`** (1) | `account.sys_created_on`, `account.sys_updated_on`, `contract.sys_created_on`, `entitlement.sys_created_on`, `entitlement.sys_updated_on`, `installed_product.sys_updated_on`, `interaction.sys_created_on`, `knowledge.sys_updated_on`, `product.sys_updated_on` (9) | `contract.sys_updated_on`, `customer_case.sys_updated_on` (2) |
| itsm | none (0) | `change.updated_on`, `change_request_mapping.created_at`, `change_request_mapping.updated_at` (3) | `configuration_item.updated_on`, `incident.updated_at`, `notification.created_on`, `notification.updated_on` (4) |

**`interaction.started_at` is the one genuinely new finding**: csm's
`register_new_interaction` was never exercised by M1 (it's not in the
current portfolio's union either way it matters — it *is* now, and wasn't
part of M1's 6-tool sequence). Its `started_at` argument is optional and, when
omitted (as in Test A's call), the server silently defaults it to
wall-clock-at-creation-time — the same behavior class as every `sys_*_on`
timestamp already in the registry, just on a business-named column instead
of a `sys_*` one. All 12 other upgraded/reconfirmed columns behave exactly
like the rest of the registry (`behavior: "wall-clock timestamp"`) — no
surprises, just paid-down "pending confirmation" debt. All updated entries
carry a `provenance` field citing this audit's script and date; nothing else
in either file was touched (verified via `git diff --stat`: 185 / 64 lines
changed, all within the intended entries plus one new `m4_reaudit` top-level
summary block per file).

---

## 7. Rerunnable scripts (`m4_reaudit/`)

| Script | Purpose |
|---|---|
| `compute_tool_union.py` | Union of `selected_tools` across all 20 task.json → `data/eog/tool-union-{csm,itsm}.json` |
| `probe_seed_entities.py` | Read-only reconnaissance on a throwaway seed per domain → `evidence/seed_probe_{csm,itsm}.json` |
| `test_a_mutating_determinism_csm.py` | Test A, csm (3 replicas, 16/16 mutating tools) |
| `test_a_mutating_determinism_itsm.py` | Test A, itsm (3 replicas, 8/8 mutating tools) |
| `test_b_read_purity_csm.py` | Test B, csm (24/24 read-only tools, zero-tolerance) |
| `test_b_read_purity_itsm.py` | Test B, itsm (18/18 read-only tools, zero-tolerance) |
| `test_c_create_id_stability_csm.py` | Test C, csm (`create_new_account` → 53 ×2) |
| `test_c_create_id_stability_itsm.py` | Test C, itsm (`create_incident` → INC_024 ×2) |
| `test_d_notification_quirk_itsm.py` | Test D, itsm self-recipient quirk (5 probes ×2 replicas) |
| `merge_volatile_registry.py` | Reconciles Test A findings into `data/eog/volatile-columns-*.json` |

All import `m1_audit/gym_client.py` and `m1_audit/db_diff.py` directly
(unmodified) rather than duplicating their seed/dump/diff/hash machinery.
Every script writes its own evidence JSON to `m4_reaudit/evidence/` and
prints a verdict, matching the M1 convention. Run order for a full
re-audit: `compute_tool_union.py` → `probe_seed_entities.py` (optional,
informational) → `test_a_*` → `test_b_*` → `test_c_*` → `test_d_*` →
`merge_volatile_registry.py`. All executions in this audit ran
sequentially (no parallel seeding during any diff); the 7 determinism test
runs (Test A × 2 domains, B × 2, C × 2, D × 1) summed to 13.32s of
live-container wall time (per-script `wall_time_s` in each evidence JSON).

---

## 8. Summary of findings (synthesis into a gate decision is upstream)

- **Coverage:** 100% of the finalized portfolio's reachable tool surface was
  exercised under this audit — 16/16 csm mutating, 24/24 csm read-only,
  8/8 itsm mutating, 18/18 itsm read-only.
- **Genuine nondeterminism found:** none, in either domain, across any test.
  Every `non_timestamp_varying_columns` set was empty; every captured
  new-row primary key (9 fields across csm+itsm Test A — 6 csm + 3 itsm —
  plus the 2 dedicated Test C checks, 11 total) was identical across all
  replicas.
- **Read purity:** both domains byte-identical before/after their full
  read-only tool set — zero tolerance, zero findings.
- **New volatile columns:** 1 genuinely new (`interaction.started_at`,
  csm), 12 presumed→confirmed upgrades (9 csm + 3 itsm), applied to
  `data/eog/volatile-columns-{csm,itsm}.json` with full evidence.
- **Quirk characterized:** itsm `send_notification` self-recipient guard is
  a real, explicit, hardcoded-to-USER_001 HTTP-level validation error at the
  server (not silent there); the silence an agent actually experiences is
  introduced by the vendored harness's own error-swallowing pattern in
  `orchestrators/react.py`/`planner_react.py` (both identical), which is
  reproducible and consistent across independent seeds. Not fixed
  (out of scope), but now precisely documented with a corrected mechanism
  versus the pre-existing RATIONALE.md description.
- **Nothing found here indicates a task should be quarantined** on
  determinism grounds — the finding above is a documentation correction to
  notification-outward's rationale, not a new risk to that task's design
  (the design already worked around the *behavioral* effect correctly, it
  just attributed the mechanism to the wrong layer).
