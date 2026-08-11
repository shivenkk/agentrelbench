"""
Batch collector: walks a completed batch's run_N directories, enforces the
spec's hard rule (both state exports must exist for every run -- else
INVALID_MISSING_DUMP, nonzero exit, batch blocked -- never silently
skipped), verifies post-seed determinism across a task's runs (seeding is
deterministic, so every batch doubles as a free determinism monitor -- any
drift fails loudly rather than being logged and ignored), and assembles
runs/<batch_id>/manifest.json.

Kept independently callable (not just invoked from cli.py's happy path) so
callers -- including tests -- can re-run just the validation/manifest step
against an existing batch_dir without re-executing the (expensive) EOG runs.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agentrelbench.state_export import read_gzip_json

REDACTED = "***REDACTED***"
# Whole underscore/hyphen-separated words, not substrings: "llm_api_key" has a
# "key" word and is redacted; "max_tokens" has a "tokens" word (plural, not
# "token") and is correctly left alone. A naive substring check ("token" in
# "max_tokens") would wrongly redact sampling params -- caught in manual
# testing before this landed.
_SECRET_KEY_WORDS = {"key", "token", "secret", "password", "credential"}
_EOG_COMMIT_FALLBACK = "de22905d21a080b83bf4a54258afe4250ee2dd55"


class InvalidMissingDumpError(RuntimeError):
    """INVALID_MISSING_DUMP: a run is missing results_*.json and/or one of
    the two required state exports. Per spec this is a hard rule: nonzero
    exit, batch blocked, never silently skipped."""


class PostSeedDriftError(RuntimeError):
    """A task's post_seed_state exports differ across its runs. Seeding is
    supposed to be deterministic (docs/M1-audit-evidence.md Test 2), so this
    indicates a real reproducibility regression, not something to log and
    move past."""


def redact_llm_config(llm_config: dict[str, Any]) -> dict[str, Any]:
    """Replace any field whose *name* looks secret-bearing (a whole
    underscore/hyphen-separated word matching _SECRET_KEY_WORDS, e.g. the
    "key" in "llm_api_key") with a fixed redaction marker. Redacts by field
    name, not by guessing whether a given value "looks like" a real secret --
    a placeholder value should be redacted the same as a real one, so the
    manifest format doesn't leak which configs were real."""
    redacted = {}
    for key, value in llm_config.items():
        words = set(re.split(r"[_\-]", key.lower()))
        if (words & _SECRET_KEY_WORDS) and value not in (None, ""):
            redacted[key] = REDACTED
        else:
            redacted[key] = value
    return redacted


def sampling_params(llm_config: dict[str, Any]) -> dict[str, Any]:
    """Extract just the sampling-relevant subset of an llm_config, per the
    spec's manifest field list ("llm config (key redacted), sampling
    params")."""
    keys = ("temperature", "max_tokens", "top_p", "effort", "reasoning")
    return {k: llm_config[k] for k in keys if k in llm_config}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha(repo_dir: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def _container_name_for_port(port: str) -> str | None:
    """Best-effort: find a running container publishing host port `port`."""
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return None
        for line in out.stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            name, ports = parts
            if f":{port}->" in ports:
                return name
    except Exception:
        pass
    return None


def _image_digest_for_container(container_name: str) -> str | None:
    """Best-effort: container name -> image ref -> RepoDigests[0]."""
    try:
        r1 = subprocess.run(
            ["docker", "inspect", "--format", "{{.Config.Image}}", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r1.returncode != 0:
            return None
        image_ref = r1.stdout.strip()
        r2 = subprocess.run(
            ["docker", "inspect", "--format", "{{json .RepoDigests}}", image_ref],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r2.returncode != 0:
            return None
        digests = json.loads(r2.stdout.strip())
        return digests[0] if digests else None
    except Exception:
        return None


def mcp_image_digest(gym_url: str) -> str | None:
    """Best-effort MCP image digest for whatever container is currently
    publishing `gym_url`'s port. Returns None (never raises) if docker is
    unavailable or no matching container is found -- this is traceability
    metadata, not something that should block a batch."""
    port = urlparse(gym_url).port
    if port is None:
        return None
    name = _container_name_for_port(str(port))
    if name is None:
        return None
    return _image_digest_for_container(name)


def discover_batch(batch_dir: Path) -> dict[str, list[Path]]:
    """Auto-discover {task_id: [run_N dirs, sorted by run number]} from a
    batch directory already written to disk -- needed so validation can be
    re-run against an existing batch_dir without re-supplying task metadata."""
    tasks: dict[str, list[Path]] = {}
    for task_dir in sorted(p for p in batch_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
        run_dirs = sorted(
            (p for p in task_dir.iterdir() if p.is_dir() and p.name.startswith("run_")),
            key=lambda p: int(p.name.split("_")[1]),
        )
        if run_dirs:
            tasks[task_dir.name] = run_dirs
    return tasks


def _run_token_usage(run_result: dict[str, Any]) -> int:
    return sum(
        (m.get("usage_metadata") or {}).get("total_tokens", 0)
        for m in run_result.get("conversation_flow", [])
        if m.get("type") == "ai_message"
    )


def _run_status(run_result: dict[str, Any]) -> str:
    if run_result.get("error"):
        return "error"
    return "success" if run_result.get("overall_success") else "verifier_failure"


def validate_and_collect_runs(batch_dir: Path, tasks: dict[str, list[Path]]) -> dict[str, dict[str, Any]]:
    """For every task's run dirs: assert results_*.json + both state exports
    exist (else INVALID_MISSING_DUMP), assert post_seed_state is identical
    across that task's runs (else PostSeedDriftError), and return
    manifest-ready per-task/per-run data.
    """
    collected: dict[str, dict[str, Any]] = {}
    for task_id, run_dirs in tasks.items():
        runs_manifest = []
        post_seed_dumps = []
        for run_dir in run_dirs:
            results_files = sorted(run_dir.glob("results_*.json"))
            post_seed_path = run_dir / "post_seed_state.json.gz"
            final_path = run_dir / "final_state.json.gz"

            missing = []
            if not results_files:
                missing.append("results_*.json")
            if not post_seed_path.exists():
                missing.append("post_seed_state.json.gz")
            if not final_path.exists():
                missing.append("final_state.json.gz")
            if missing:
                raise InvalidMissingDumpError(
                    f"INVALID_MISSING_DUMP: {task_id}/{run_dir.name} is missing {missing}"
                )

            results = json.loads(results_files[0].read_text())
            run_result = (results.get("runs") or [{}])[0]
            post_seed_dump = read_gzip_json(post_seed_path)
            post_seed_dumps.append((run_dir.name, post_seed_dump))

            runs_manifest.append(
                {
                    "run": run_dir.name,
                    "database_id": post_seed_dump.get("database_id"),
                    "status": _run_status(run_result),
                    "token_usage": _run_token_usage(run_result),
                    "artifacts": {
                        "results_json": str(results_files[0].relative_to(batch_dir)),
                        "post_seed_state": str(post_seed_path.relative_to(batch_dir)),
                        "final_state": str(final_path.relative_to(batch_dir)),
                    },
                }
            )

        if len(post_seed_dumps) > 1:
            base_name, base_dump = post_seed_dumps[0]
            for name, dump in post_seed_dumps[1:]:
                if dump.get("tables") != base_dump.get("tables"):
                    raise PostSeedDriftError(
                        f"post_seed_state drift for task {task_id!r}: {base_name} and "
                        f"{name} seeded different table state. Seeding is expected to "
                        f"be deterministic (docs/M1-audit-evidence.md Test 2) -- this "
                        f"indicates a real reproducibility regression."
                    )

        collected[task_id] = {"runs": runs_manifest}
    return collected


def assert_run_counts(tasks: dict[str, list[Path]], expected_k: int) -> None:
    """Silent-discard audit item #2: a task whose run-dir count != k means runs
    vanished upstream (e.g. a swallowed execute_sample exception) -- fail loudly
    rather than letting a short task shrink its n silently."""
    bad = {task_id: len(run_dirs) for task_id, run_dirs in tasks.items() if len(run_dirs) != expected_k}
    if bad:
        raise InvalidMissingDumpError(
            f"run-count violation (expected k={expected_k}): {bad} -- runs vanished upstream"
        )


def build_manifest(
    *,
    batch_dir: Path,
    batch_id: str,
    k: int,
    llm_config_path: Path,
    started_at: str,
    finished_at: str,
    our_repo_root: Path,
    eog_clone_root: Path,
    task_files: dict[str, Path],
) -> dict[str, Any]:
    """Validate the batch on disk (raises InvalidMissingDumpError /
    PostSeedDriftError -- see validate_and_collect_runs) and, only if that
    passes, assemble + write runs/<batch_id>/manifest.json. Safe to call more
    than once against the same batch_dir (e.g. to re-check after deliberately
    damaging an export -- see tests/test_acceptance.py); a failing re-check
    raises before touching the previously-written manifest.json.
    """
    tasks = discover_batch(batch_dir)
    assert_run_counts(tasks, expected_k=k)
    collected = validate_and_collect_runs(batch_dir, tasks)

    llm_config = json.loads(Path(llm_config_path).read_text())

    gym_urls = set()
    for _task_id, task_file in task_files.items():
        task_json = json.loads(Path(task_file).read_text())
        for gym in task_json.get("gym_servers_config") or []:
            gym_urls.add(gym["mcp_server_url"])

    manifest: dict[str, Any] = {
        "batch_id": batch_id,
        "k": k,
        "started_at": started_at,
        "finished_at": finished_at,
        "agentrelbench_git_sha": _git_sha(our_repo_root),
        "eog_commit": _git_sha(eog_clone_root) or _EOG_COMMIT_FALLBACK,
        "mcp_image_digests": {url: mcp_image_digest(url) for url in sorted(gym_urls)},
        "llm_config": redact_llm_config(llm_config),
        "sampling_params": sampling_params(llm_config),
        "tasks": {},
    }

    for task_id, task_file in task_files.items():
        if task_id not in collected:
            raise InvalidMissingDumpError(
                f"INVALID_MISSING_DUMP: task {task_id!r} has no run_N directories under {batch_dir}"
            )
        manifest["tasks"][task_id] = {
            "task_file": str(task_file),
            "task_file_sha256": _sha256_file(Path(task_file)),
            **collected[task_id],
        }

    manifest_path = batch_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
