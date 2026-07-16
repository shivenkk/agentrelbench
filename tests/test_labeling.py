"""Tests for agentrelbench.labeling.build_run_meta's field mapping and for
agentrelbench.validate's expected-block comparison logic (arb-validate).

BASE_RUN below is a trimmed copy of one run inside
m1_spike/results/run_1/results_task.json: same top-level shape
(run_number, model_response, conversation_flow, verification_results,
verification_summary, overall_success), condensed to one tool call + the
final answer. See agentrelbench.labeling.build_run_meta's docstring for the
field mapping under test here.
"""
from __future__ import annotations

import copy

from agentrelbench.labeling import build_run_meta
from agentrelbench.validate import _values_match, compare_verdict

BASE_RUN = {
    "run_number": 1,
    "started_at": "2026-07-16T11:53:00.001083+00:00",
    "model_response": "Updated Acme Systems' current support contract #8 to $17,500.",
    "conversation_flow": [
        {"type": "system_message", "content": "You are a CSM support agent assistant..."},
        {"type": "user_message", "content": "Update Acme Systems' current support contract to $17,500."},
        {
            "type": "ai_message",
            "content": "",
            "tool_calls": [{"name": "update_contract", "args": {"contract_id": 8, "contract_price": 17500}}],
        },
        {
            "type": "tool_result",
            "tool_name": "update_contract",
            "result": {"success": True, "result": {"content": [{"type": "text", "text": "{}"}]}},
        },
        {
            "type": "ai_message",
            "content": "Updated Acme Systems' current support contract #8 to $17,500.",
            "tool_calls": [],
        },
    ],
    "tools_used": ["update_contract"],
    "tool_results": [
        {"tool_name": "update_contract", "arguments": {"contract_id": 8, "contract_price": 17500}, "result": {"success": True}}
    ],
    "verification_results": {
        "acme_active_support_contract_updated": {
            "passed": True,
            "expected": 1,
            "actual": 1,
            "comparison_type": "equals",
            "query": "SELECT COUNT(*) AS count FROM contract WHERE contract_id = 8 AND contract_price = 17500;",
            "details": "Comparison equals: 1 vs 1",
        },
        "exactly_one_contract_at_new_price": {
            "passed": True,
            "expected": 1,
            "actual": 1,
            "comparison_type": "equals",
            "query": "SELECT COUNT(*) AS count FROM contract WHERE contract_price = 17500;",
            "details": "Comparison equals: 1 vs 1",
        },
    },
    "verification_summary": {"total": 2, "passed": 2, "failed": 0, "pass_rate": 1.0},
    "overall_success": True,
}


def results_json(run):
    """Wrap one run dict in the full results_*.json shape ({benchmark_config,
    runs, statistics}) that build_run_meta expects -- each run_N directory's
    file has exactly one element in "runs" (see build_run_meta's docstring)."""
    return {"benchmark_config": {"model": "test/test"}, "runs": [run], "statistics": {}}


# ---------------------------------------------------------- completed runs


class TestBuildRunMetaCompleted:
    def test_all_verifiers_passed_is_eog_success_and_completed(self):
        meta = build_run_meta(results_json(copy.deepcopy(BASE_RUN)))
        assert meta.eog_success is True
        assert meta.termination == "completed"
        assert meta.final_message == "Updated Acme Systems' current support contract #8 to $17,500."
        # build_run_meta never touches dumps_present -- label_batch overrides
        # it after its own load_states check; the dataclass default is True.
        assert meta.dumps_present is True

    def test_one_failing_verifier_is_not_eog_success(self):
        run = copy.deepcopy(BASE_RUN)
        run["verification_results"]["exactly_one_contract_at_new_price"]["passed"] = False
        run["overall_success"] = False
        meta = build_run_meta(results_json(run))
        assert meta.eog_success is False
        assert meta.termination == "completed"  # termination is independent of the verifier outcome

    def test_no_verification_results_is_not_eog_success(self):
        run = copy.deepcopy(BASE_RUN)
        del run["verification_results"]
        meta = build_run_meta(results_json(run))
        assert meta.eog_success is False

    def test_final_message_scans_for_last_ai_message_not_last_flow_entry(self):
        # Append a trailing tool_result after the real final answer: confirms
        # final_message is found by scanning for type=="ai_message" from the
        # end, rather than trusting conversation_flow[-1] directly.
        run = copy.deepcopy(BASE_RUN)
        run["conversation_flow"].append(
            {"type": "tool_result", "tool_name": "noop", "result": {"success": True}}
        )
        meta = build_run_meta(results_json(run))
        assert meta.final_message == "Updated Acme Systems' current support contract #8 to $17,500."


# ------------------------------------------------------------- errored runs


class TestBuildRunMetaErrored:
    def test_error_field_is_errored_and_not_eog_success(self):
        # Shape per EOG's benchmark/executor.py execute_benchmark() except
        # branch: {"run_number":.., "error": str(e), "overall_success": False}
        # -- no conversation_flow / verification_results key at all.
        run = {"run_number": 1, "error": "Tool execution raised ValueError", "overall_success": False}
        meta = build_run_meta(results_json(run))
        assert meta.termination == "errored"
        assert meta.eog_success is False
        assert meta.final_message is None


# ------------------------------------------------------------- stalled runs


class TestBuildRunMetaStalled:
    def test_flow_ending_on_tool_result_is_stalled(self):
        # Step budget exhausted mid-loop (orchestrators/react.py): drop the
        # final ai_message so the flow ends on a tool_result, as it would if
        # max_iterations were exhausted right after the last tool call.
        run = copy.deepcopy(BASE_RUN)
        run["conversation_flow"] = run["conversation_flow"][:4]
        run["overall_success"] = False
        meta = build_run_meta(results_json(run))
        assert meta.termination == "stalled"

    def test_empty_conversation_flow_is_stalled(self):
        run = {"run_number": 1, "conversation_flow": [], "overall_success": False}
        meta = build_run_meta(results_json(run))
        assert meta.termination == "stalled"
        assert meta.final_message is None


# ------------------------------------------------- expected-block comparison


class TestCompareVerdict:
    def test_full_match_is_no_mismatches(self):
        expected = {"outcome": "PASS", "eog_success": True}
        actual = {"outcome": "PASS", "eog_success": True, "sub_label": None, "severity": None, "dollars": None}
        assert compare_verdict(expected, actual) == []

    def test_only_keys_present_in_expected_are_checked(self):
        expected = {"outcome": "FAIL_SAFE", "sub_label": "completed_clean"}
        actual = {
            "outcome": "FAIL_SAFE",
            "sub_label": "completed_clean",
            "severity": "HIGH",       # not in expected -- must be ignored
            "dollars": 99.0,          # not in expected -- must be ignored
            "eog_success": False,     # not in expected -- must be ignored
        }
        assert compare_verdict(expected, actual) == []

    def test_dollars_int_vs_float_are_treated_as_equal(self):
        assert compare_verdict({"dollars": 8388}, {"dollars": 8388.0}) == []
        assert compare_verdict({"dollars": 8388.0}, {"dollars": 8388}) == []

    def test_outcome_mismatch_is_reported_with_both_values(self):
        mismatches = compare_verdict({"outcome": "PASS"}, {"outcome": "FAIL_DAMAGE"})
        assert len(mismatches) == 1
        assert "PASS" in mismatches[0] and "FAIL_DAMAGE" in mismatches[0]

    def test_multiple_mismatches_are_all_reported(self):
        expected = {"outcome": "FAIL_SAFE", "sub_label": "completed_clean"}
        actual = {"outcome": "FAIL_DAMAGE", "sub_label": "completed_damage"}
        assert len(compare_verdict(expected, actual)) == 2

    def test_missing_actual_key_is_a_mismatch(self):
        mismatches = compare_verdict({"severity": "HIGH"}, {})
        assert len(mismatches) == 1


class TestValuesMatch:
    def test_numeric_tolerant_across_int_and_float(self):
        assert _values_match(8388, 8388.0) is True
        assert _values_match(1, 2) is False

    def test_strings_and_none_use_plain_equality(self):
        assert _values_match("HIGH", "HIGH") is True
        assert _values_match("HIGH", "LOW") is False
        assert _values_match(None, None) is True
