"""Unit tests for the LIMIT-assertion logic in agentrelbench.state_export.

No network / containers required -- these exercise the pure assertion
function directly, per docs/M1-audit-evidence.md Test 4's finding that
/api/sql-runner silently applies LIMIT 100 to any query without its own
LIMIT clause (a returned row count == limit must therefore be treated as
truncation, not a coincidental exact match).
"""
import pytest

from agentrelbench.state_export import (
    DumpTruncatedError,
    assert_not_truncated,
    context_to_headers,
)


def test_assert_not_truncated_passes_when_below_limit():
    assert_not_truncated("customer_case", row_count=99, limit=100)  # must not raise


def test_assert_not_truncated_raises_when_equal_to_limit():
    # row_count == limit is indistinguishable from silent truncation.
    with pytest.raises(DumpTruncatedError, match="customer_case"):
        assert_not_truncated("customer_case", row_count=100, limit=100)


def test_assert_not_truncated_raises_when_above_limit():
    with pytest.raises(DumpTruncatedError):
        assert_not_truncated("case_sla", row_count=2464, limit=100)


def test_assert_not_truncated_zero_rows_is_fine():
    assert_not_truncated("empty_table", row_count=0, limit=1_000_000)  # must not raise


def test_context_to_headers_prefixes_bare_keys():
    assert context_to_headers({"user_email": "a@b.com"}) == {"x-user-email": "a@b.com"}


def test_context_to_headers_passes_through_x_prefixed_keys():
    assert context_to_headers({"x-user-email": "a@b.com"}) == {"x-user-email": "a@b.com"}


def test_context_to_headers_empty_or_none():
    assert context_to_headers({}) == {}
    assert context_to_headers(None) == {}


def test_context_to_headers_stringifies_values():
    assert context_to_headers({"user_id": 32}) == {"x-user-id": "32"}
