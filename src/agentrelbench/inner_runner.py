"""
Runs *inside* the EnterpriseOps-Gym clone's own venv, invoked as:

    <clone>/.venv/bin/python -m agentrelbench.inner_runner <job_spec.json>

with PYTHONPATH extended (by cli.py) to include this package's own `src/`
directory, so `agentrelbench` resolves via PYTHONPATH without ever being
pip-installed into the clone's venv (see README.md's "How arb-run runs EOG"
section for the full rationale).

This module is deliberately tiny: cli.py has already resolved which task,
what k, the output layout, and per-gym headers into a job spec; the only
thing left to do here is apply the agentrelbench.eog_patch and become
evaluate.py.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def main(argv: list = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m agentrelbench.inner_runner <job_spec.json>", file=sys.stderr)
        return 2

    job = json.loads(Path(argv[0]).read_text())

    clone_root = job["clone_root"]
    if clone_root not in sys.path:
        sys.path.insert(0, clone_root)

    from agentrelbench.eog_patch import apply_patch, set_run_context

    set_run_context(
        output_root=job["output_folder"],
        headers_by_gym_url=job["headers_by_gym_url"],
    )
    apply_patch()

    # Mirrors m1_spike's proven invocation convention (cd into the clone
    # before running evaluate.py); harmless for our own tasks' absolute
    # seed_database_file paths, and required for any task giving a
    # CWD-relative one (technical map §B).
    os.chdir(clone_root)

    # Provider pinning (added 2026-07-17, post provider-decomposition): when
    # ARB_PIN_PROVIDER is set, every OpenRouter request carries
    # provider={"order": [pin], "allow_fallbacks": false}, making the serving
    # stack a designed constant instead of per-request routing luck. EOG's
    # llm_client does `from langchain_openai import ChatOpenAI` inside the
    # constructor branch, which resolves the module attribute at call time --
    # so rebinding langchain_openai.ChatOpenAI here reaches it.
    pin = os.environ.get("ARB_PIN_PROVIDER")
    if pin:
        import langchain_openai

        _OrigChatOpenAI = langchain_openai.ChatOpenAI

        class _PinnedChatOpenAI(_OrigChatOpenAI):
            def __init__(self, **kwargs):
                mk = dict(kwargs.get("model_kwargs") or {})
                eb = dict(mk.get("extra_body") or {})
                eb["provider"] = {"order": [pin], "allow_fallbacks": False}
                mk["extra_body"] = eb
                kwargs["model_kwargs"] = mk
                super().__init__(**kwargs)

        langchain_openai.ChatOpenAI = _PinnedChatOpenAI
        print(f"[agentrelbench] provider pinned: {pin} (allow_fallbacks=false)")

    import evaluate  # the clone's top-level evaluate.py, now import-patchable

    # Force single-attempt semantics (added 2026-07-17 after two live failures).
    # EOG's evaluate.execute_sample retries the WHOLE sample (max_num_attempts=5,
    # fresh DB seed per attempt) whenever any run records an error. That is a
    # leaderboard convenience, and for us it is wrong twice over: (1) hidden
    # retries make a "run" a best-of-N sample, corrupting k-run iid semantics --
    # a failed attempt is DATA (labeled errored_*, feeds p-hat_upper); (2) the
    # extra per-attempt DB seeds break eog_patch's one-create-per-run
    # correlation, which then fails loudly (INVALID_MISSING_DUMP) -- the two
    # quarantined runs of 2026-07-16/17 were exactly this path firing.
    # Bare-name call sites resolve through module globals, so rebinding works
    # just like the create/delete patch.
    import inspect
    assert "max_num_attempts" in inspect.signature(evaluate.execute_sample).parameters, (
        "EOG drifted: evaluate.execute_sample no longer takes max_num_attempts; "
        "re-verify retry semantics before running"
    )
    _orig_execute_sample = evaluate.execute_sample

    async def _single_attempt_execute_sample(*args, **kwargs):
        kwargs["max_num_attempts"] = 1
        return await _orig_execute_sample(*args, **kwargs)

    evaluate.execute_sample = _single_attempt_execute_sample

    sys.argv = [
        "evaluate.py",
        "--configs_folder", job["configs_folder"],
        "--llm_config", job["llm_config_path"],
        "--output_folder", job["output_folder"],
        "--num_runs", str(job["k"]),
        "--concurrency", str(job.get("concurrency", 1)),
        "--orchestrator", job.get("orchestrator", "react"),
    ]
    asyncio.run(evaluate.main())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
