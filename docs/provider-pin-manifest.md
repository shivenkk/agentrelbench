# Provider-pin manifest

Evidence that every held-out model ran under one pinned serving
configuration: a single OpenRouter provider per model, with
`allow_fallbacks=false`, for every run in the campaign.

Across the 9 campaign cells there are **60 pin
banners covering 656 runs**, one distinct provider per cell
(AtlasCloud, DeepInfra), and `allow_fallbacks=false` in every banner.

## What is being read, and why it is not simply published

The pin banner is printed once per pinned worker process, before that
process constructs any request; the process then executes every run of one
task. The banners live in the campaign driver logs (`runs/camp-*.log`),
which are untracked: `runs/` is gitignored because the logs are full agent
transcripts and publishing them would expose an oracle path for every task
to anyone searching the repository.

The released verdicts sidecars are not a substitute. Their provenance was
recovered from staged job specs after the fact, and each campaign sidecar
records `provider_pin: null`, because the pin was set in the runner's
environment rather than in the LLM config a sidecar could read back. These
logs are the only surviving record of it.

This manifest is therefore a derived artifact: counts and identifiers, no
transcript content.

## How it was produced

```
.venv/bin/python scripts/extract_provider_pins.py
```

The script re-derives every number below from the logs and exits non-zero
if any of them fails to hold, so this file cannot be edited into agreement
with a claim the logs do not support. Its output is a pure function of the
logs and carries no generation timestamp, so an unchanged set of logs
regenerates it byte for byte.

Three properties are asserted beyond the raw counts:

- **Coverage.** A banner proves a pin was installed in one process, not
  that the runs in the log used it. Every run block is required to sit
  downstream of a banner, with none preceding the first one.
- **No reroute.** OpenRouter names the endpoint it served in its error
  metadata. Any provider there other than the cell's pin fails the script.
- **Shape.** The expected provider, banner count and run count of each cell
  are frozen in the script, so it cannot quietly describe a different
  campaign than the paper does.

Coverage is also checked against the released data rather than only within
the logs. The runs the banners cover match each model's released verdicts
file exactly (mistral 208, oss 224, deepseek 224; 656 in total), so no
released held-out run falls outside this evidence.

## Per-cell evidence

| Cell | Model | Source log | Banners | Runs covered | Pinned provider | `allow_fallbacks` | Distinct providers |
| --- | --- | --- | ---: | ---: | --- | --- | ---: |
| mistral / breadth | `openrouter/mistralai/mistral-small-3.2-24b-instruct` | `camp-mistral-breadth.log` | 14 | 112 / 112 | DeepInfra | `false` | 1 |
| mistral / depth5 | `openrouter/mistralai/mistral-small-3.2-24b-instruct` | `camp-mistral-depth5.log` | 5 | 80 / 80 | DeepInfra | `false` | 1 |
| mistral / cab | `openrouter/mistralai/mistral-small-3.2-24b-instruct` | `camp-mistral-cab.log` | 1 | 16 / 16 | DeepInfra | `false` | 1 |
| oss / breadth | `openrouter/openai/gpt-oss-120b` | `camp-oss-breadth.log` | 14 | 112 / 112 | DeepInfra | `false` | 1 |
| oss / depth5 | `openrouter/openai/gpt-oss-120b` | `camp-oss-depth5.log` | 5 | 80 / 80 | DeepInfra | `false` | 1 |
| oss / cab | `openrouter/openai/gpt-oss-120b` | `camp-oss-cab.log` | 1 | 32 / 32 | DeepInfra | `false` | 1 |
| deepseek / breadth | `openrouter/deepseek/deepseek-v3.2` | `camp-deepseek-breadth.log` | 14 | 112 / 112 | AtlasCloud | `false` | 1 |
| deepseek / depth5 | `openrouter/deepseek/deepseek-v3.2` | `camp-deepseek-depth5.log` | 5 | 80 / 80 | AtlasCloud | `false` | 1 |
| deepseek / cab | `openrouter/deepseek/deepseek-v3.2` | `camp-deepseek-cab.log` | 1 | 32 / 32 | AtlasCloud | `false` | 1 |

All 9 cells served from `https://openrouter.ai/api/v1`. Banners count pinned
worker processes, one per task, so runs per banner is that task's k: 14
breadth tasks at k=8, 5 depth tasks at k=16, and the flagship CAB task in a
single process at k=32, except mistral where CAB is k=16.

## Source log digests

sha256 of each log as read. A reader who obtains a log from the authors
can check it against this list and re-run the extractor on it.

```
06f9ee0c67f8a2a3810c32eb4637f0ed8db15e02365cf05ceca84d820777995b  runs/camp-deepseek-breadth.log
708d8dde597bcee19bd5b4287b8ee32d77d4e70bad4622dd5d7388ce6aa8826f  runs/camp-deepseek-cab.log
7f7f9e90b773d9690c55726c30bf65f4b45b75165f3382a5a9fd419bb68d2d49  runs/camp-deepseek-depth5.log
f7123eb2ecf4dcda97a668ceffa22b1dbe33a320af881673166ddde7dbb65e4d  runs/camp-mistral-breadth.log
468ae6486a2f477476456bb3231b116c0cddfa573959f479ddf20e0dd81d322e  runs/camp-mistral-cab.log
64722e915d4ef8a1ce28e0a575cda9fb3b87e4868998b3ac496ceb6570ebd0d1  runs/camp-mistral-depth5.log
eefd5e75bd7dfe3c5b63868ae5bff1e92d9e62ef0dca0727a8acc6eb398b9886  runs/camp-oss-breadth.log
4807a6662eee742c17bef0ccd57604d09a370a7fbbfbd908a3da7d9868d87f4a  runs/camp-oss-cab.log
f5965d6b2e01d9d372e840c7610673aec16d3dddb29bf3d14960d022c02fb65d  runs/camp-oss-depth5.log
```

## Errored payloads: what a pinned endpoint does when it cannot serve

`camp-deepseek-depth5.log` contains 6 OpenRouter 400 payloads carrying a `provider_name`:

- **3 attributed to AtlasCloud**, the pinned provider: `Provider returned error` / `bad request`.
- **3 with `provider_name: None`**: context-length overflow. The pinned endpoint's limit is 163,840 tokens and the request was about 253,963-254,009 tokens, so OpenRouter rejected it before an endpoint was engaged, leaving nothing to attribute.

This is the pin working, not failing. Without it, a request the
pinned endpoint could not serve would have been rerouted to a
provider with a larger context window and the run would have
succeeded under a different serving stack, silently. Pinned, it
fails, and the failure is recorded as an errored run that feeds the
upper-bound estimator instead of contaminating the comparison.

No payload in any campaign log names a provider other than that
cell's pin, which is the observation that would have falsified the
claim.

## The mechanism, in the published source

`src/agentrelbench/inner_runner.py` lines 51-74. When
`ARB_PIN_PROVIDER` is set, the runner subclasses `ChatOpenAI` and rebinds
the module attribute, so every OpenRouter request the substrate makes
carries the provider block; the banner is printed only on that path.

- line 58: `pin = os.environ.get("ARB_PIN_PROVIDER")`
- line 68: `eb["provider"] = {"order": [pin], "allow_fallbacks": False}`
- line 74: `print(f"[agentrelbench] provider pinned: {pin} (allow_fallbacks=false)")`

The banners quoted in this manifest are the runtime output of that last
line, which is reached only after the rebinding above it has taken effect.
