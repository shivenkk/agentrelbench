<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)"
            srcset="https://raw.githubusercontent.com/shivenkk/agentrelbench/main/docs/figs/header-dark.svg">
    <img alt="AgentRelBench: a reliability instrument for action-taking LLM agents"
         src="https://raw.githubusercontent.com/shivenkk/agentrelbench/main/docs/figs/header-light.svg">
  </picture>
</p>

<p align="center">
  <strong>Agent safety does not repeat. We measured it.</strong>
</p>

<p align="center">
  <a href="https://github.com/shivenkk/agentrelbench/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/shivenkk/agentrelbench/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/agentrelbench/"><img alt="PyPI" src="https://img.shields.io/pypi/v/agentrelbench"></a>
  <a href="https://pypi.org/project/agentrelbench/"><img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue"></a>
  <a href="https://github.com/shivenkk/agentrelbench/blob/main/LICENSE"><img alt="Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <a href="https://github.com/shivenkk/agentrelbench/actions/workflows/ci.yml"><img alt="156 tests" src="https://img.shields.io/badge/tests-156-brightgreen"></a>
</p>

When an LLM agent holds write access, a wrong action becomes a state change that someone has to detect,
price, and unwind. You cannot regenerate it. That narrows the useful question about pre-deployment
testing to one thing: **does an agent cause damage repeatably?**

Across 2,128 evaluation runs on nine models in six families, no. Damage appeared in every model family
we measured, and inside every damage-producing cell it was stochastic. **Not one task damaged on every
run**, across 48 held-out damage events, so a one-shot audit has no dangerous task to find.

**A single clean run misses a damage-producing (model, task) pair 80% of the time.** More runs help
only geometrically.

<p align="center">
  <img src="https://raw.githubusercontent.com/shivenkk/agentrelbench/main/docs/figs/fig4-audit-decay.png"
       alt="Probability that k independent audit runs all look clean, for each demonstrably-stochastic held-out cell" width="560">
</p>

This does not go away with capability. The most capable model we measured damages on only one task out
of twenty, but that residual is still a per-run coin flip: it fails at p-hat = 0.16, a single audit run
misses it 84% of the time, and five independent clean runs still miss it 43% of the time.

## Results

Every number below is recomputed from the released run data by `scripts/audit_numbers.py`, which fails
loudly on drift. Held-out models were chosen and their criteria frozen before any of them ran.

| Pool | Model | Runs | Damaging tasks | Damage events | Stochastic cells | Always-fail cells |
|---|---|---:|---:|---:|---:|---:|
| Held-out | mistral-small-24b | 208 | 3 / 20 | 26 | 3 | **0** |
| Held-out | gpt-oss-120b | 224 | 1 / 20 | 12 | 1 | **0** |
| Held-out | deepseek-v3.2 | 224 | 1 / 20 | 4 | 0 | **0** |
| Frontier | claude-opus-4.6 | 224 | 1 / 20 | 5 | 1 | **0** |
| Frontier | claude-haiku-4.5 | 208 | 1 / 20 | 1 | 0 | **0** |
| Development | llama-3.1-8b | 160 | 7 / 20 | 11 | 0 | **0** |
| Development | llama-3.3-70b | 160 | 2 / 20 | 4 | 0 | **0** |
| Development | qwen3-32b | 160 | 2 / 20 | 4 | 0 | **0** |
| Development | qwen3-14b | 160 | 2 / 20 | 2 | 0 | **0** |

"Stochastic" means the cell's exact 95% Clopper-Pearson interval lies strictly inside (0.05, 0.95),
a criterion fixed in advance. The k=1 audit miss rate is 0.80 over the 13 development pairs (the
pre-registered primary) and 0.665 over 7 held-out pairs, which is below our pre-registered power floor
of 8 and is therefore reported as underpowered rather than as confirmation.

<p align="center">
  <img src="https://raw.githubusercontent.com/shivenkk/agentrelbench/main/docs/figs/fig2-universality-stochasticity.png"
       alt="Damage probability on the flagship commit-gated task across all model families, with exact confidence intervals against the pre-registered stochastic band" width="820">
</p>

Two further results worth naming. One model family committed the gated irreversible change **while
declaring that it had refused**, which transcript grading and LLM-judge grading both score as a safe
refusal. Only state-diff verification catches it. And our own initially favored headline was demoted
by a pre-registered criterion that fired against it; that demotion is reported in the paper rather than
quietly dropped.

## Supported substrate: EnterpriseOps-Gym

**Read this before installing.** The measurement core is genuinely substrate-independent:
`src/agentrelbench/estimators.py` has no reference to any environment. But state export and harness
patching are coupled to [EnterpriseOps-Gym](https://github.com/ServiceNow/EnterpriseOps-Gym)
(ServiceNow AI Research and Mila, Apache-2.0), and **EnterpriseOps-Gym is the only supported
substrate.**

If you came to point this at your own database, you would need to write an adapter first, on the order
of 500 lines. That is planned work, not shipped work. What this package supports today is: bring your
own model, run it against the published task suite in the published environment.

## Quickstart

```bash
pip install agentrelbench
```

The 20-task suite and its seed databases ship inside the package. Locate them, run a model k times per
task, then label the runs into verdicts:

```bash
SUITE=$(python -c "import agentrelbench,pathlib;print(pathlib.Path(agentrelbench.__file__).parent/'suite')")
arb-run   --tasks "$SUITE/tasks/csm" --llm-config my-model.json --k 8 --out runs/
arb-label --tasks "$SUITE/tasks/csm" runs/<batch_id>
```

Running the instrument needs the EnterpriseOps-Gym containers up and a provider credential in your LLM
config. Reproducing the paper's analysis needs neither.

## Reproduce the paper

One command, no credentials and no containers, from a clone of this repository. The released run data
lives in the repo and is deliberately not shipped inside the installable package, so reproduction is a
clone-only path; the pip package gives you the instrument and the task suite, not the campaign data:

```bash
git clone https://github.com/shivenkk/agentrelbench && cd agentrelbench && scripts/reproduce.sh
```

It builds a fresh virtualenv, checks all 12 released verdicts files against their recorded sha256 and
row counts, runs the estimator and audit suites, regenerates every figure and the Appendix E tables
under assertions, and re-derives every headline number from the run data. It exits nonzero on any
drift. Proven in a `python:3.12-slim` container; the transcript is in `docs/cleanroom-transcript.txt`.

This reproduces the *analysis*, not the agent runs. The campaign numbers are records of runs that
already happened, and by this paper's own finding those runs are stochastic, so re-running them would
not reproduce them and must not be used to regenerate them.

## What ships

```
tasks/              20 tasks (csm, itsm), each with task.json, damage.json,
                    oracle.script.json, counterexamples/, RATIONALE.md
tasks-escalated/    13 distractor variants
data/seed-dbs/      the 2 seed databases the suite runs against
runs/               12 released verdicts files, each with a provenance manifest
src/agentrelbench/  k-run wrapper, state export, damage labeler, estimators
scripts/            figures, Appendix E tables, number audit, reproduce, manifests
docs/               specs, campaign and frontier results, appendices, pre-registration
```

Every released verdicts file has a `.manifest.json` sidecar recording model id, provider, sampling
parameters, per-task k, run window, harness and substrate commits, MCP image digests, source batches,
and sha256. Three of the twelve are marked `provenance: partial` and list exactly which fields were
never recorded. The substrate is pinned by digest:

```
enterpriseops-gym-mcp-csm@sha256:eaa456ac9aa85728426e7d3813a0bbca0949d6a8695be30e26f03894e6e6b189
enterpriseops-gym-mcp-itsm@sha256:a234ae3fb7cee196ba25e6b9957969dea829919b6e8271dddae128f065aaf39f
```

## How damage is measured

No LLM appears anywhere in the measurement path. A verdict is a deterministic diff of the database
before and after a run, matched by primary key against a closed-world per-task whitelist, with
severity and dollar pricing attached to out-of-scope mutations. Refusal detection is a regex over a
declared token, so a stall can never be scored as an abstention.

The boundary that makes the damage axis crisp: a wrong-but-authorized outcome is a task *failure*, not
damage. Damage requires an out-of-scope irreversible mutation. Every task ships an oracle script and
counterexample scripts that pin both sides of that boundary, and `arb-validate` proves they still
produce their declared verdicts.

## Tests

```bash
pytest
```

156 tests. One acceptance test drives the real EnterpriseOps-Gym containers over HTTP and is marked
`needs_containers`; CI runs `pytest -m "not needs_containers"`. The estimators, the damage labeler,
and the manuscript number audit are all covered offline.

## Citation

```bibtex
@misc{khurdi2026agentrelbench,
  title  = {Safety Doesn't Repeat: Universal, Stochastic, Trap-Free Damage in Action-Taking LLM Agents},
  author = {Shiven Khurdi},
  year   = {2026},
  eprint = {arXiv:TBD},
}
```

## License

Apache-2.0. The substrate, EnterpriseOps-Gym, is independently Apache-2.0 and is not vendored here.
