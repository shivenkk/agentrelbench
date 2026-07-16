# M1 Audit Evidence — EnterpriseOps-Gym Reproducibility

Empirical follow-up to `docs/eog-technical-map.md` section "What is UNKNOWN (must
be covered by the M1 Docker audit)". All 5 tests below were run against live
MCP Docker containers (csm on port 8001, itsm on port 8006) using the clone's
own vendored HTTP helpers (`benchmark/mcp_client.py`, endpoint conventions from
`benchmark/verifier.py`). Rerunnable scripts live in `m1_audit/`; every script
writes its own evidence JSON to `m1_audit/evidence/` and prints a verdict.
Clone commit: `de22905d21a080b83bf4a54258afe4250ee2dd55` (unchanged; no tracked
files in `external/EnterpriseOps-Gym` were modified — only a `.venv/` was
created inside it).

## Setup

**Docker.** `docker info` initially failed ("Cannot connect to the Docker
daemon"). Ran `open -a Docker`; a re-check of `docker info` a few seconds later
succeeded — well within the 180s budget, no BLOCKED state reached.

**Images.** README's pull template (`shivakrishnareddyma225/enterpriseops-gym-mcp-<domain>:latest`)
matched exactly; no name adaptation needed.

| Domain | Image | RepoDigest |
|---|---|---|
| csm | `shivakrishnareddyma225/enterpriseops-gym-mcp-csm:latest` | `sha256:eaa456ac9aa85728426e7d3813a0bbca0949d6a8695be30e26f03894e6e6b189` |
| itsm | `shivakrishnareddyma225/enterpriseops-gym-mcp-itsm:latest` | `sha256:a234ae3fb7cee196ba25e6b9957969dea829919b6e8271dddae128f065aaf39f` |

**Container port mystery solved.** The README's domain/port table (lines
128–141) has an unexplained row `| <container_port> | N/A | 8005 |`.
`docker inspect ... --format '{{json .Config.Cmd}}'` on both images shows
`["python","-m","uvicorn","main:app","--host","0.0.0.0","--port","8005"]` —
**every domain image listens on internal port 8005 regardless of domain**;
only the host-side mapping differs. Containers started as:

```
docker run -d --name eog-csm  -p 8001:8005 shivakrishnareddyma225/enterpriseops-gym-mcp-csm:latest
docker run -d --name eog-itsm -p 8006:8005 shivakrishnareddyma225/enterpriseops-gym-mcp-itsm:latest
```

Both ports (8001, 8006) were free before starting (`lsof` empty). Both
containers reported `health: starting` → `healthy` within ~12s. **Flakiness
note:** both images are `linux/amd64`; this host is `linux/arm64/v8`
(Apple Silicon), so Docker prints a platform-mismatch warning and runs them
under emulation. Functionally this caused no failures and timing stayed fast
(see Test 4), but it's worth knowing for anyone reproducing this on Apple
Silicon — expect a one-line harmless warning on every `docker run`.

itsm's startup log usefully self-reports `📦 MCP Tools Module Loaded: 93 ITSM
API tools` — an independent cross-check that matched Test 1's live count
exactly.

**Python env.** `uv sync --extra openai` inside `external/EnterpriseOps-Gym`
completed cleanly (Python 3.12.4 venv at `external/EnterpriseOps-Gym/.venv`).
All `m1_audit/` scripts are run with that interpreter and import
`benchmark.mcp_client` directly from the clone (`sys.path` insert), per the
"reuse them" instruction.

**Seed files used** (arbitrary, representative picks from `scratch/gym_dbs/`):
- csm: `csm/dbs/db_1762232091750_3ev7dns6b.sql` (18 tables, 10,633 rows)
- itsm: `itsm/dbs/db_1765301900121_3mwjj54xy.sql` (24 tables, smaller — used for the "lighter" itsm replay test)

**Shared library code** (`m1_audit/gym_client.py`, `m1_audit/db_diff.py`):
- `gym_client.seed()` wraps the clone's own `create_database_from_file()` (POST `/api/seed-database`).
- `gym_client.sql_runner()` mirrors the exact request shape used by `benchmark/verifier.py:_execute_sql_query` (POST `/api/sql-runner`, `{query, database_id}` + `x-database-id` header) — there's no standalone sql-runner helper in `mcp_client.py` itself to import, only the endpoint convention to reuse.
- `gym_client.new_client()` wraps `MCPClient` (`initialize` handshake → `tools/list` / `tools/call`).
- `db_diff.py` provides table enumeration, PK discovery (regex over `CREATE TABLE` text from `sqlite_master.sql`, since `PRAGMA` is blocked — see Test 4), canonical hashing, and two diff strategies: a sorted/canonical hash (for yes/no identity) and a **positional** (natural DB row-order) diff, which is what actually pinpoints *which* `table.column` varies without a volatile column scrambling row alignment the way a full-row sort would.

---

## Test 1 — Tool Inventory

**Script:** `m1_audit/test1_tool_inventory.py`
**Command:** `.venv/bin/python m1_audit/test1_tool_inventory.py`

Dumped `tools/list` from both live servers (no seed needed — tool schemas are
static per domain image). Wrote full `{name, description, inputSchema}` for
every tool to `data/eog/tool-inventory-csm.json` / `-itsm.json`.

First-pass read-only vs state-changing split (by name-prefix heuristic,
falling back to description-keyword scan; full per-tool classification in
`m1_audit/evidence/test1_classification.json`):

| Domain | Total tools | Read-only | State-changing | Unclear |
|---|---|---|---|---|
| csm | 89 | 49 | 40 | 0 |
| itsm | 93 | 51 | 42 | 0 |

itsm's 93 matches the container's own startup log line
(`📦 MCP Tools Module Loaded: 93 ITSM API tools`) exactly — independent
confirmation the dump is complete.

State-changing tools (csm, 40): `assign_case_to_user, set_case_assignment_group,
add_new_user, update_user_details, add_new_user_group, update_user_group,
add_new_group_member, remove_group_membership, create_new_account,
update_account_details, create_contact, update_contact, add_location,
update_location, add_new_product, update_product, delete_products,
register_new_installed_product, update_installed_product_details,
enlist_new_contract, update_contract, add_new_entitlement, update_entitlement,
add_new_sla_definition, update_sla_definition, create_new_case, update_case,
link_new_case_sla, update_case_sla_details, delete_case_slas,
register_new_interaction, update_interaction, create_knowledge, update_knowledge,
link_case_knowledge, updated_linked_case_knowledge,
delete_case_knowledge_linkages, send_notification, update_notification,
delete_notifications`.

State-changing tools (itsm, 42, selected): `add_new_user, update_user_details,
add_new_user_group, update_user_group, add_new_group_member,
remove_group_membership, add_location, update_location,
create_new_incident_template, update_incident_template,
register_configuration_item, update_configuration_item, add_new_service,
update_service, create_change, update_change, create_problem, update_problem,
create_incident, update_incident, add_child_incident(s), update_child_incident,
remove_child_incident, register_new_service_offering, update_service_offering,
create_knowledge_article, update_knowledge_article, link_knowledge_to_incident,
remove_knowledge_link_to_incident, add_new_sla_definition, update_sla_definition,
send_notification, update_notification, delete_notifications,
map_change_request, delete_change_request_mappings,
link_affected_ci_to_incident, remove_affected_ci_from_incident,
link_new_incident_sla, update_incident_sla_details, delete_incident_slas`
(full list in the JSON).

**Note on heuristic quality:** the naive first pass mis-bucketed aggregate
read tools (`count_*`, `avg_*`, `total_sum_*`, `*_count`) and `register_*`
create-tools until the prefix/suffix list was extended (see script history —
initial run had 16+5 "unclear"; final run has 0). This is a **name/description
heuristic as explicitly scoped ("first-pass")**, not a verified-by-execution
classification; a handful of borderline tools (e.g., anything that both reads
and conditionally writes) would need manual/LLM review for a production
classifier.

**Verdict: PASS** (both inventories dumped completely, cross-validated by itsm's own log).

---

## Test 2 — Seed Repeatability (csm)

**Script:** `m1_audit/test2_seed_repeatability.py`
**Command:** `.venv/bin/python m1_audit/test2_seed_repeatability.py`

Loaded the identical csm seed SQL file twice (`POST /api/seed-database` ×2,
independently generated `database_id`s), enumerated tables via
`SELECT name FROM sqlite_master WHERE type='table'` (worked directly — no
fallback to `information_schema` needed; **engine is SQLite**, confirmed
further by itsm's own log line `Initializing seed database at
./mcp_databases/seed_store.db`), dumped every table from both with an
explicit large `LIMIT`, canonicalized (sorted tables, rows sorted by full-row
JSON, no columns excluded), and SHA-256 hashed.

Key raw output:
```
table list identical across the two seeds: True (18 tables)
total rows: db1=10633 db2=10633
OVERALL canonical hash match: True
  db1 overall hash: 3ff48380a29ee9f06ad59906d99919ef83df918ee8a5b7623ecf3acf22964fc9
  db2 overall hash: 3ff48380a29ee9f06ad59906d99919ef83df918ee8a5b7623ecf3acf22964fc9
  no per-table hash mismatches
wall time: 1.51s
```

**Verdict: PASS — byte-for-byte identical.** No column differed at all (csm's
seed data contains no `CURRENT_TIMESTAMP` literals, unlike hr per the
technical map, so there was nothing to expect to vary here). Evidence:
`m1_audit/evidence/test2_seed_repeatability.json`.

---

## Test 3 — Replay Reproducibility (the key test)

### csm

**Script:** `m1_audit/test3_replay_reproducibility_csm.py`

Chose 6 distinct state-changing tools from Test 1's inventory: `create_new_case,
update_case, assign_case_to_user, link_new_case_sla, send_notification,
update_case_sla_details`. Valid seed entity IDs were discovered by querying a
throwaway seeded DB first (`account_id=1`, `contact_id=123`, `product_id=128`,
`installed_product_id=3`, `assignment_group_id=4`, agent `user_id`s 3/5/6/9,
`sla_def_id` 1/2 — all confirmed present via `SELECT`). Composed a fixed
10-call sequence (2 cases created, each updated, assigned, SLA-linked; one
notification; one SLA-detail update), hardcoding all seed-entity references.
IDs for entities *created* during the sequence (case_a, case_b, the two
case_sla links, the notification) are necessarily captured dynamically from
each replica's own tool response — that dynamic capture is the mechanism that
lets us test whether those IDs come out identical.

**Surprising early finding:** csm's `tools/call` requires an `x-user-email`
context header that must resolve to a real user in the seed (`Error:
x-user-email header is required for user identification`, then `Error: User
not found for given email` for a made-up address). Used a real seeded agent's
email (`thomas.green@servicenow.com`, `user_id=1`) throughout.

Ran the identical sequence against 3 independently-seeded `database_id`s (R1,
R2, R3), then dumped and positionally diffed all 18 tables across all three.

Key raw output:
```
New-row primary key identity across replays:
  case_a: {'R1': 1233, 'R2': 1233, 'R3': 1233} -> identical=True
  case_b: {'R1': 1234, 'R2': 1234, 'R3': 1234} -> identical=True
  sla_link_a: {'R1': 2465, 'R2': 2465, 'R3': 2465} -> identical=True
  sla_link_b: {'R1': 2466, 'R2': 2466, 'R3': 2466} -> identical=True
  notification_a: {'R1': 734, 'R2': 734, 'R3': 734} -> identical=True

row_count_mismatch: {}
tables_not_common_to_all: []
Varying table.column keys (4):
  case_sla.start_time: behavior=wall-clock timestamp, diff_count=2
  customer_case.sys_created_on: behavior=wall-clock timestamp, diff_count=2
  customer_case.sys_updated_on: behavior=wall-clock timestamp, diff_count=2
  notification.sys_created_on: behavior=wall-clock timestamp, diff_count=1

Identical modulo volatile columns (hash after stripping 4 volatile columns): True
wall time: 3.39s
```

**Deliverables:**
- (a) Verdict: **identical modulo 4 wall-clock timestamp columns** (not byte-identical, but everything else — including every ID, every enum/state, every FK — is exactly reproduced).
- (b) `data/eog/volatile-columns-csm.json`: the 4 `table.column` pairs above, each tagged `behavior: "wall-clock timestamp"`. No auto-increment or random-identifier volatility was observed anywhere.
- (c) New-row primary keys: **identical across all 3 replays** for every captured ID (case IDs, SLA-link IDs, notification ID).

**Verdict: PASS modulo volatile columns.** Full evidence (call logs, per-cell
diffs): `m1_audit/evidence/test3_replay_csm.json`.

### itsm (lighter — one seeding pair, 6 calls)

**Script:** `m1_audit/test3_replay_reproducibility_itsm.py`

5 distinct tools: `create_incident, update_incident,
register_configuration_item, update_configuration_item, send_notification`
(deliberately touching `configuration_item.cost`, itsm's dollar-relevant
column per the technical map). 2 independently-seeded replicas (R1, R2).

**Contrasting surprising finding:** itsm's `tools/call` did **not** require
any `x-user-email`/context header at all — `create_incident` succeeded
immediately with zero context. This is an **inconsistency between the two
domain servers** worth flagging to whoever builds the harness-facing wrapper:
csm enforces actor identity, itsm doesn't. `send_notification` on itsm *does*
separately validate its `email` argument against the seeded `users` table
(`USER_EMAIL_NOT_FOUND` if not present) — a different, argument-level check,
not a session-auth header.

Key raw output:
```
New-row primary key identity across replays:
  incident_a: {'R1': 'INC_024', 'R2': 'INC_024'} -> identical=True
  incident_b: {'R1': 'INC_025', 'R2': 'INC_025'} -> identical=True
  ci_a: {'R1': 'CI_005', 'R2': 'CI_005'} -> identical=True

row_count_mismatch: {}
Varying table.column keys (6):
  configuration_item.created_on / .updated_on: wall-clock timestamp
  incident.created_at / .updated_at: wall-clock timestamp
  notification.created_on / .updated_on: wall-clock timestamp

Identical modulo volatile columns: True
wall time: 1.47s
```

itsm's formatted string IDs (`INC_024`, `CI_005` — a prefix + zero-padded
sequential counter, not a raw integer) were **just as deterministic** as csm's
plain integers.

**Verdict: PASS modulo volatile columns.** Outputs:
`data/eog/volatile-columns-itsm.json`, evidence
`m1_audit/evidence/test3_replay_itsm.json`.

---

## Test 4 — SQL-Runner Surface (csm)

**Script:** `m1_audit/test4_sql_runner_surface.py`

| Capability | Result |
|---|---|
| `sqlite_master` accessible | Yes (18 tables enumerated) |
| 2-table `LEFT JOIN` w/ aliases + `AS` | Works |
| 3-table `JOIN` + `GROUP BY` | Works |
| `PRAGMA` (non-`SELECT`) | **Rejected**, HTTP 400, `{"detail":"Only read-only SELECT queries are allowed"}` — confirms the endpoint enforces read-only |

**Important surprise, load-bearing for every other test:** the sql-runner
**silently injects `LIMIT 100`** onto any query without its own `LIMIT`
clause. Discovered by inspecting the response's echoed `query` field:
requesting `SELECT * FROM case_sla;` (2,464 true rows) returned only 100 rows,
and the server echoed back `"query": "SELECT * FROM case_sla LIMIT 100"`. An
**explicit** larger `LIMIT` (tested at `LIMIT 1000000`) correctly overrides
this and returns the true count (2,464/2,464 — not truncated). All dump code
in `m1_audit/db_diff.py` always appends an explicit large `LIMIT`; without
that, Tests 2/3/5 would have silently compared truncated 100-row samples
instead of full state, which could have hidden real nondeterminism sitting
past row 100 of any table.

Full-dump timing (all 18 csm tables, 10,633 rows, explicit big `LIMIT`
throughout): **0.304s wall time (~16.9 ms/table average)**. Per-run full-state
export is cheap.

**Verdict: PASS.** Evidence: `m1_audit/evidence/test4_sql_runner_surface.json`.

---

## Test 5 — Isolation (csm)

**Script:** `m1_audit/test5_isolation.py`

Seeded two independent `database_id`s (A, B) from the identical seed file.
Used a **single shared MCP session** (one `initialize` handshake, one
captured `mcp-session-id`) for the entire test, alternating
`create_new_case(A) → create_new_case(B) → update_case(A) → update_case(B) →
assign_case_to_user(A) → assign_case_to_user(B)`, passing `database_id`
explicitly per call rather than binding it at client construction. This
directly targets the open question: is routing per-call (HTTP header) or
server/session-global?

Because A and B are independently seeded from an identical file, the first
`create_new_case` against each landed on the **same** next-autoincrement
`case_id` (1233) in both — an unusually strong contamination probe, since a
routing bug would show up as *wrong content at a colliding PK*, not just a
missing row.

Key raw output:
```
case_a (created in db_a) = 1233; case_b (created in db_b) = 1233
customer_case row count before: A=1232 B=1232 -> after: A=1233 B=1233 (both exactly +1)
db_a_case_content_correct: True   (short_description/state/assigned_to all match A's calls only)
db_b_case_content_correct: True   (short_description/state/assigned_to all match B's calls only)
no_B_description_anywhere_in_A: True
no_A_description_anywhere_in_B: True
```

**Verdict: PASS — no cross-contamination.** Routing is confirmed **per-call
argument** (the `x-database-id` header set fresh on each `tools/call` request
via `MCPClient.call_tool(..., database_id=...)`), not server-global or
session-pinned — a single MCP session correctly served two independent
databases in strict alternation. Evidence:
`m1_audit/evidence/test5_isolation.json`.

---

## Wrap-up: containers left running for the next milestone

```
NAMES      IMAGE                                                       HOST PORT -> CONTAINER   STATUS
eog-csm    shivakrishnareddyma225/enterpriseops-gym-mcp-csm:latest    8001 -> 8005              healthy
eog-itsm   shivakrishnareddyma225/enterpriseops-gym-mcp-itsm:latest   8006 -> 8005              healthy
```

Stop / remove when no longer needed:
```
docker stop eog-csm eog-itsm
docker rm eog-csm eog-itsm
```

Restart later with the same image (already pulled, digests pinned above):
```
docker run -d --name eog-csm  -p 8001:8005 shivakrishnareddyma225/enterpriseops-gym-mcp-csm:latest
docker run -d --name eog-itsm -p 8006:8005 shivakrishnareddyma225/enterpriseops-gym-mcp-itsm:latest
```

## Candid summary of what was flaky or surprising

1. **The `LIMIT 100` default is the single biggest trap in this API** — completely silent unless you inspect the echoed `query` field. Any future harness code that calls `/api/sql-runner` without an explicit `LIMIT` will silently under-sample any table over 100 rows. This should be treated as a hard requirement for whatever damage-labeler / state-diff tooling gets built downstream.
2. **`PRAGMA` is blocked** ("Only read-only SELECT queries are allowed"), so schema introspection (PK discovery) had to go through `SELECT sql FROM sqlite_master` and regex over the `CREATE TABLE` text instead — works fine, just less direct than `PRAGMA table_info`.
3. **csm and itsm disagree on auth requirements**: csm hard-requires a valid `x-user-email` context header on every tool call (validated against the seed's `user` table); itsm requires none. Anyone building a uniform multi-domain wrapper needs to handle this per-domain, not assume one auth contract.
4. **Both docker images are `linux/amd64` on an `arm64` host** — harmless emulation warning on every `docker run`, no functional or performance issue observed (full-dump timing was still sub-second).
5. **The only nondeterminism found anywhere, in either domain, across 5 replay/seed/isolation replicas, was wall-clock timestamp columns** (`sys_created_on`/`sys_updated_on`/`start_time` in csm; `created_on`/`updated_on`/`created_at`/`updated_at` in itsm). Every primary key, every auto-generated formatted ID (`CS-0001233`, `INC_024`, `CI_005`), and every other logical column was byte-identical across all replicas tested. This directly confirms the technical map's prediction and narrows the M1-required "volatile column allowlist" to a short, purely-timestamp list per domain.
