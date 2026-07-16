"""Pins the table-scoping contract in labeling glue (measurement path):
SQLite internal bookkeeping tables (reserved ``sqlite_`` prefix) are excluded
silently; ANY other table absent from the primary-keys registry fails loudly —
a table the diff can't see is a blind spot in the damage axis, never a skip.
"""

import pytest

from agentrelbench.labeling import _scope_to_known_tables

PKS = {"contract": "contract_id", "account": "account_id"}


def test_sqlite_internal_tables_excluded_silently():
    state = {"contract": [{"contract_id": 1}], "sqlite_sequence": [{"name": "contract", "seq": 8}]}
    out = _scope_to_known_tables(state, PKS)
    assert set(out) == {"contract"}


def test_known_tables_pass_through_unchanged():
    state = {"contract": [{"contract_id": 1}], "account": []}
    assert _scope_to_known_tables(state, PKS) == state


def test_unknown_table_fails_loudly():
    state = {"contract": [], "mystery_table": [{"id": 1}]}
    with pytest.raises(ValueError, match="mystery_table"):
        _scope_to_known_tables(state, PKS)
