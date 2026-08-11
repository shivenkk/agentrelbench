# M1 task-injection spike

Proves check (c) end-to-end: a **custom task JSON** with a **custom seed DB reference** runs through EOG's unmodified `evaluate.py`, with `--num_runs 2` producing independently seeded `run_N/` artifacts, driven by `scripted_responder.py` (offline, deterministic, no API keys) so the spike isolates harness behavior from model behavior.

## Blocked on (from the reproducibility audit)

- Containers up (csm on :8001), audit leaves them running.
- `data/eog/tool-inventory-csm.json`, needed to fill real tool names/arguments in `task.json` and `script.json` (TODO markers).

## Run

1. Fill TODOs in `task.json` + `script.json` from the csm tool inventory (2–3 state-changing calls with valid seed-data IDs; verifier 1 checks a state change the script makes; verifier 2's SELECT captures a value so we see `actual` recording).
2. `python scripted_responder.py --script script.json --port 8099`
3. From the EOG clone venv:
   ```
   python evaluate.py \
     --configs_folder ../../m1_spike/tasks \
     --llm_config ../../m1_spike/llm_stub.json \
     --output_folder ../../m1_spike/results \
     --orchestrator react --concurrency 1 --num_runs 2
   ```
   (Exact args per docs/eog-technical-map.md §B; adjust if the loader needs `--domain`.)

## Pass criteria

- Both runs execute; `run_1/` and `run_2/` each contain `results_*.json`.
- `tool_results` records the scripted calls with arguments + server results.
- Verifier `actual` values captured; run 1 vs run 2 used different `database_id`s (independent seeding).
