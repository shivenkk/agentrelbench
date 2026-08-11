"""Tests for seed-database path resolution at config-staging time.

Written BEFORE the implementation: this sits on the path that decides which
database a run is seeded against, so a bug here silently changes what every
measurement measures.

The problem being solved: inner_runner.py does os.chdir(clone_root) before EOG
reads the staged config, so a repo-relative seed_database_file in a committed
task.json would resolve against the EOG clone rather than this repo. Resolving
to an absolute path at staging time -- before that chdir -- makes the chdir
irrelevant, and needs no env var or setup step from whoever clones the repo.
"""

import json

import pytest

from agentrelbench.cli import REPO_ROOT, resolve_seed_paths


def config(seed, **extra):
    gym = {"mcp_server_url": "http://localhost:8001/mcp",
           "context": {"x-user-email": "thomas.green@servicenow.com"}}
    if seed is not None:
        gym["seed_database_file"] = seed
    return {"task_id": "t", "gym_servers_config": [gym], **extra}


@pytest.fixture
def seed_file(tmp_path, monkeypatch):
    """A real seed file inside a fake repo root, so existence checks can pass."""
    target = tmp_path / "data" / "seed-dbs" / "csm" / "db.sql"
    target.parent.mkdir(parents=True)
    target.write_text("-- seed\n")
    monkeypatch.setattr("agentrelbench.cli.REPO_ROOT", tmp_path)
    return target


class TestResolution:
    def test_relative_path_resolves_against_repo_root(self, seed_file, tmp_path):
        out = resolve_seed_paths(config("data/seed-dbs/csm/db.sql"))
        got = out["gym_servers_config"][0]["seed_database_file"]
        assert got == str(seed_file)

    def test_resolved_path_is_absolute(self, seed_file):
        out = resolve_seed_paths(config("data/seed-dbs/csm/db.sql"))
        from pathlib import Path
        assert Path(out["gym_servers_config"][0]["seed_database_file"]).is_absolute()

    def test_absolute_path_passes_through_unchanged(self, seed_file):
        """Un-migrated task.json files must keep working."""
        out = resolve_seed_paths(config(str(seed_file)))
        assert out["gym_servers_config"][0]["seed_database_file"] == str(seed_file)

    def test_resolution_is_independent_of_cwd(self, seed_file, tmp_path, monkeypatch):
        """The whole point: os.chdir must not be able to change the answer."""
        first = resolve_seed_paths(config("data/seed-dbs/csm/db.sql"))
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        second = resolve_seed_paths(config("data/seed-dbs/csm/db.sql"))
        assert first == second

    def test_every_gym_entry_is_resolved(self, seed_file, tmp_path):
        second = tmp_path / "data" / "seed-dbs" / "itsm" / "db.sql"
        second.parent.mkdir(parents=True)
        second.write_text("-- seed\n")
        cfg = config("data/seed-dbs/csm/db.sql")
        cfg["gym_servers_config"].append(
            {"mcp_server_url": "http://localhost:8006/mcp",
             "seed_database_file": "data/seed-dbs/itsm/db.sql"})
        out = resolve_seed_paths(cfg)
        assert [g["seed_database_file"] for g in out["gym_servers_config"]] == [
            str(seed_file), str(second)]


class TestFailsLoudly:
    def test_missing_seed_file_raises(self, seed_file):
        """A mis-seeded run is worse than a crashed one: it produces data."""
        with pytest.raises(FileNotFoundError, match="seed_database_file"):
            resolve_seed_paths(config("data/seed-dbs/csm/nope.sql"))

    def test_missing_absolute_seed_file_also_raises(self, seed_file, tmp_path):
        with pytest.raises(FileNotFoundError):
            resolve_seed_paths(config(str(tmp_path / "gone.sql")))


class TestEverythingElseIsPreserved:
    def test_other_fields_are_untouched(self, seed_file):
        cfg = config("data/seed-dbs/csm/db.sql", prompt="do the thing", k=8)
        out = resolve_seed_paths(cfg)
        assert out["prompt"] == "do the thing" and out["k"] == 8
        assert out["task_id"] == "t"

    def test_gym_context_headers_are_untouched(self, seed_file):
        out = resolve_seed_paths(config("data/seed-dbs/csm/db.sql"))
        assert out["gym_servers_config"][0]["context"] == {
            "x-user-email": "thomas.green@servicenow.com"}

    def test_input_is_not_mutated(self, seed_file):
        cfg = config("data/seed-dbs/csm/db.sql")
        resolve_seed_paths(cfg)
        assert cfg["gym_servers_config"][0]["seed_database_file"] == \
            "data/seed-dbs/csm/db.sql"

    def test_entry_without_seed_file_is_left_alone(self, seed_file):
        out = resolve_seed_paths(config(None))
        assert "seed_database_file" not in out["gym_servers_config"][0]

    def test_result_is_json_serializable(self, seed_file):
        json.dumps(resolve_seed_paths(config("data/seed-dbs/csm/db.sql")))


def test_real_repo_root_points_at_this_repo():
    """Guards the parents[2] arithmetic that makes resolution repo-anchored."""
    assert (REPO_ROOT / "src" / "agentrelbench" / "cli.py").exists()
    assert (REPO_ROOT / "pyproject.toml").exists()
