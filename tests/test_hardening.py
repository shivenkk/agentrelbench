"""Pins the four silent-discard hardening guards (docs/silent-discard-audit.md,
2026-07-17). Items #2/#3 are measurement-path; #1 is a static lint holding the
verified 0/76 gym-name-mismatch state true forever; #4 (tool-discovery guard)
lives in eog_patch and is exercised live, not unit-tested (requires the clone).
"""

import json
from pathlib import Path

import pytest

from agentrelbench.collector import InvalidMissingDumpError, assert_run_counts
from agentrelbench.labeler import InvalidRunError
from agentrelbench.labeling import build_run_meta

REPO = Path(__file__).resolve().parent.parent


class TestRunCountGuard:
    def test_short_task_fails_loudly(self):
        tasks = {"t1": [Path("run_1"), Path("run_2")], "t2": [Path("run_1")]}
        with pytest.raises(InvalidMissingDumpError, match="t2"):
            assert_run_counts(tasks, expected_k=2)

    def test_exact_counts_pass(self):
        assert_run_counts({"t1": [Path("run_1"), Path("run_2")]}, expected_k=2) is None


class TestEmptyResultsGuard:
    def test_empty_runs_array_raises(self):
        with pytest.raises(InvalidRunError) as ei:
            build_run_meta({"runs": []})
        assert ei.value.code == "INVALID_EMPTY_RESULTS"

    def test_absent_runs_key_raises(self):
        with pytest.raises(InvalidRunError):
            build_run_meta({"benchmark_config": {}})


class TestVerifierGymNameLint:
    def test_every_verifier_targets_a_configured_gym(self):
        # Audit item #1: EOG silently drops verifiers whose gym_name is not a
        # configured gym (executor.py:438-450), which could flip FAIL->PASS.
        # Static lint over every task in the repo keeps the verified 0-mismatch
        # state true for all future tasks and variants.
        task_files = sorted(REPO.glob("tasks/*/*/task.json")) + sorted(
            REPO.glob("tasks-escalated/*/*/task.json")
        )
        assert task_files, "no task files found — glob roots moved?"
        for tf in task_files:
            task = json.loads(tf.read_text())
            gyms = {g["mcp_server_name"] for g in task["gym_servers_config"]}
            for v in task["verifiers"]:
                gym_name = v.get("gym_name")
                assert not gym_name or gym_name in gyms, (
                    f"{tf}: verifier {v.get('name')!r} targets unknown gym {gym_name!r} "
                    f"(configured: {sorted(gyms)}) — EOG would silently drop it"
                )
