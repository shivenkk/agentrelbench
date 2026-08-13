"""Tests for locating the EnterpriseOps-Gym clone that arb-run execs.

Written BEFORE the fix, and the installed package is the reproduction: arb-run
only ever ran EOG under REPO_ROOT/external/EnterpriseOps-Gym/.venv, and
REPO_ROOT is __file__-derived, so from a pip install it points into
site-packages where nothing was ever cloned -- with no flag or env var able to
say where the clone actually is. That takes arb-validate down too, since it
drives arb-run in-process.

Unlike the task suite and the registries, the clone cannot be fixed by shipping
it in the wheel: it is a separate repository with its own synced venv. So the
fix is a way to name it, plus an error that says how.
"""

import json
import os
import types
from pathlib import Path

import pytest

import agentrelbench
from agentrelbench.cli import _eog_clone_root, _run_one_task, main


@pytest.fixture
def installed_layout(tmp_path, monkeypatch):
    """A REPO_ROOT inside site-packages, as a wheel install produces, and no
    override set."""
    site_packages = tmp_path / "site-packages"
    monkeypatch.setattr("agentrelbench.cli.REPO_ROOT", site_packages)
    monkeypatch.delenv("ARB_EOG_CLONE", raising=False)
    return site_packages


class TestCloneLocation:
    def test_checkout_layout_is_the_default(self, installed_layout):
        assert _eog_clone_root() == installed_layout / "external" / "EnterpriseOps-Gym"

    def test_env_var_names_the_clone_from_an_installed_package(self, installed_layout, tmp_path, monkeypatch):
        clone = tmp_path / "EnterpriseOps-Gym"
        clone.mkdir()
        monkeypatch.setenv("ARB_EOG_CLONE", str(clone))
        assert _eog_clone_root() == clone

    def test_env_var_path_is_made_absolute(self, installed_layout, tmp_path, monkeypatch):
        """inner_runner chdirs into the clone and puts it on sys.path, so a
        relative override would stop naming the same directory."""
        clone = tmp_path / "EnterpriseOps-Gym"
        clone.mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ARB_EOG_CLONE", "EnterpriseOps-Gym")
        assert _eog_clone_root() == clone


class TestTheCloneCanImportOurPackage:
    """The clone's venv runs agentrelbench.inner_runner without agentrelbench
    ever being installed into it, purely off the PYTHONPATH arb-run hands it.
    Deriving that from REPO_ROOT (<repo>/src) leaves the clone importing from a
    directory that only exists in a checkout, which fails one line later than
    the clone lookup and just as fatally."""

    def test_pythonpath_names_our_package_directory_not_a_repo_layout(
        self, installed_layout, tmp_path, monkeypatch
    ):
        task_file = tmp_path / "case-triage-basic.json"
        task_file.write_text(json.dumps({
            "task_id": "t",
            "gym_servers_config": [{"mcp_server_url": "http://localhost:8001/mcp", "context": {}}],
        }))
        captured = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured["env"] = kwargs["env"]
            return types.SimpleNamespace(returncode=0)

        monkeypatch.setattr("agentrelbench.cli.subprocess.run", fake_run)
        clone = tmp_path / "EnterpriseOps-Gym"
        _run_one_task(task_file, "case-triage-basic", tmp_path / "llm.json", tmp_path / "batch", 1, clone)

        package_parent = Path(agentrelbench.__file__).resolve().parent.parent
        assert captured["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(package_parent)
        assert captured["argv"][0] == str(clone / ".venv" / "bin" / "python")


class TestFailsWithInstructions:
    def _run(self, tmp_path):
        return main(["--tasks", str(tmp_path / "tasks"),
                     "--llm-config", str(tmp_path / "llm_config.json"),
                     "--k", "1", "--out", str(tmp_path / "runs")])

    def test_installed_package_without_a_clone_says_how_to_point_at_one(
        self, installed_layout, tmp_path, capsys
    ):
        rc = self._run(tmp_path)
        err = capsys.readouterr().err
        assert rc == 1
        assert str(installed_layout / "external" / "EnterpriseOps-Gym") in err
        assert "ARB_EOG_CLONE" in err

    def test_override_naming_a_clone_with_no_synced_venv_is_reported(
        self, installed_layout, tmp_path, monkeypatch, capsys
    ):
        """Proves main() honors the override rather than only the helper: the
        path it complains about must be the one that was named."""
        clone = tmp_path / "EnterpriseOps-Gym"
        clone.mkdir()
        monkeypatch.setenv("ARB_EOG_CLONE", str(clone))
        rc = self._run(tmp_path)
        err = capsys.readouterr().err
        assert rc == 1
        assert str(clone / ".venv" / "bin" / "python") in err
