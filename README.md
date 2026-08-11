# AgentRelBench

**A reliability instrument for action-taking LLM agents: ground-truth, severity-priced damage measured across repeated runs.**

When an agent has write access, a wrong action is not a bad sample to regenerate. It is a state
change someone has to detect, price, and unwind. AgentRelBench computes damage from database state
diffs (severity-priced, deterministic, no LLM anywhere in the measurement path), measures it across
repeated runs (pass^k and safe^k), and answers a question that decides whether pre-deployment audits
mean anything: **is an agent's damage risk a stable property of a task, or a per-run coin flip?**

In our data it is a coin flip. Damage is universal across the nine models and six families we
measured, stochastic within every damage-producing cell, and never concentrated in an always-fail
task. Zero always-fail cells across 48 held-out damage events. A single clean run misses a
damage-producing (model, task) pair 0.80 of the time.

Several agent benchmarks do run each task more than once. The distinction here is what repetition is
*for*: they repeat to stabilize a point estimate, so run-to-run variance is a nuisance parameter to
average away. We treat that variance as the result, and report the per-cell damage distribution.

## Supported substrate: EnterpriseOps-Gym

**Read this before installing.** The measurement core is genuinely substrate-independent:
`src/agentrelbench/estimators.py` is 338 lines with no reference to any gym. But state export and
the harness patching are coupled to
[EnterpriseOps-Gym](https://github.com/ServiceNow/EnterpriseOps-Gym) (ServiceNow AI Research + Mila,
Apache-2.0), and **EnterpriseOps-Gym is the only supported substrate.**

If you came here to point this at your own database, you would need to write an adapter first, on the
order of 500 lines. That is planned work, not shipped work. What this package supports today is:
bring your own model, run it against the published task suite in the published environment.

The use case it serves well is the one it was built for. The one it does not serve is a drop-in
reliability harness for arbitrary environments.

## Install

```
pip install agentrelbench
```

Three commands are installed:

| Command | What it does |
|---|---|
| `arb-run` | Runs a task suite k times per task, archiving per-run DB state exports plus a batch manifest |
| `arb-label` | Labels archived runs into verdicts (state-diff damage labeler) |
| `arb-validate` | Proves a task's oracle and counterexample scripts produce their declared verdicts |

Running the instrument end to end additionally needs the EnterpriseOps-Gym containers and provider
credentials. Reproducing the paper's analysis does not (see below).

## Reproduce the paper's numbers

One command, no credentials and no containers. This runs **from a clone of the repository**, not from
the pip package: the released run data lives in the repo and is deliberately not shipped inside the
wheel or sdist.

```
git clone <repo> && cd agentrelbench && scripts/reproduce.sh
```

It builds a fresh venv, checks every released verdicts file against its manifest sha256 and row
count, runs the estimator and audit test suites, regenerates all four figures and the Appendix E
tables under assertions, and re-derives every headline number from the released run data. It exits
nonzero on any drift. Proven in a `python:3.12-slim` container; transcript in
`docs/cleanroom-transcript.txt`.

Scope: this reproduces the *analysis*, from released verdicts through estimators to figures and
numbers. It does not re-run the agents. The campaign numbers are records of runs that already
happened, and by this paper's own finding those runs are stochastic, so re-running would not
reproduce them and must not be used to "regenerate" them.

## What ships

```
tasks/              20 base tasks (csm, itsm), each with task.json, damage.json,
                    oracle.script.json, counterexamples/
tasks-escalated/    13 distractor variants (plus10 arm)
data/seed-dbs/      the 2 seed databases the task suite runs against (1.3 MB)
runs/               12 released verdicts files plus a provenance manifest for each
src/agentrelbench/  instrument: k-run wrapper, state export, damage labeler, estimators
scripts/            figures, Appendix E tables, number audit, reproduce, manifests
docs/               specs, campaign and frontier results, appendices
```

Every released verdicts file has a `.manifest.json` sidecar recording model id, provider, sampling
parameters, per-task k, run window, harness and substrate commits, MCP image digests, source
batches, and sha256. Three of the twelve are marked `provenance: partial` and list exactly which
fields were never recorded; see the Limitations section of the paper.

Pinned substrate digests:

```
enterpriseops-gym-mcp-csm@sha256:eaa456ac9aa85728426e7d3813a0bbca0949d6a8695be30e26f03894e6e6b189
enterpriseops-gym-mcp-itsm@sha256:a234ae3fb7cee196ba25e6b9957969dea829919b6e8271dddae128f065aaf39f
```

## Tests

```
pytest
```

150 tests. All pass with the EnterpriseOps-Gym csm container up on `:8001`; one acceptance test
needs it, since that test stubs only the LLM.

## How it drives EnterpriseOps-Gym without modifying the clone

`arb-run` runs in its own lightweight environment (httpx plus stdlib) and never imports
EnterpriseOps-Gym. Per task it execs `agentrelbench.inner_runner` under the clone's own venv Python,
with `PYTHONPATH` extended to this package's `src/`, so that process can import
`agentrelbench.eog_patch` without agentrelbench being installed into the clone. The patch wraps
EnterpriseOps-Gym's per-run database create and delete call sites with dump-then-continue, so each
run's post-seed and pre-cleanup state is captured through `/api/sql-runner`. No tracked file under
the clone is ever modified.

Seed database paths in `task.json` are repo-relative and resolved to absolute at config-staging time,
before the harness changes directory into the clone. Nothing needs to be configured for this.
