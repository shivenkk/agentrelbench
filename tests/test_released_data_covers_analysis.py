"""Every run file the analysis reads must be in the released set.

This invariant was broken and the break survived every local test: the llama-70b
arm-C batch was read by make_appendix_e.py but never tracked, and locally the
untracked file is just sitting there. Only the clean-room run failed. That is the
gap this test closes, so the next omission fails in a second instead of after a
container build.

Existence is the assertion, not git-tracked-ness: the clean room has no git, and
"the file is there when the analysis runs" is the property that actually matters.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

import pytest  # noqa: E402
from make_appendix_e import ARM_C  # noqa: E402
from make_data_manifests import RELEASED  # noqa: E402
from make_figures import DEV_BREADTH, DEV_CAB_BATCHES, MERGED  # noqa: E402


def released_paths():
    return {(REPO / "runs" / rel).resolve() for rel in RELEASED}


def verdicts_of(rel):
    """Accept either a batch directory or a direct file reference."""
    path = REPO / rel
    return (path if path.suffix == ".jsonl" else path / "verdicts.jsonl").resolve()


@pytest.mark.parametrize("rel", sorted(ARM_C.values()))
def test_arm_c_batches_are_released(rel):
    assert verdicts_of(rel) in released_paths(), (
        f"{rel} is read by make_appendix_e.ARM_C but is not in "
        f"make_data_manifests.RELEASED, so it will be missing from a fresh checkout"
    )


@pytest.mark.parametrize("rel", sorted(DEV_BREADTH.values()))
def test_dev_breadth_batches_are_released(rel):
    assert verdicts_of(rel) in released_paths()


@pytest.mark.parametrize("rel", sorted(str(p) for p in MERGED.values()))
def test_merged_pool_files_are_released(rel):
    assert Path(rel).resolve() in released_paths()


def test_dev_cab_batches_are_released():
    for entry in DEV_CAB_BATCHES:
        rel = entry[1]
        assert verdicts_of(rel) in released_paths(), f"{rel} not released"


def test_every_released_file_exists_and_is_non_empty():
    for rel in RELEASED:
        path = REPO / "runs" / rel
        assert path.exists(), f"released file missing from this checkout: {rel}"
        assert path.stat().st_size > 0, f"released file is empty: {rel}"


def test_released_set_is_the_twelve_files_the_docs_promise():
    """README ("all 12 released verdicts files", "12 released verdicts files")
    and the paper's reproducibility statement both quote this count."""
    assert len(RELEASED) == 12, (
        f"RELEASED now has {len(RELEASED)} files, but README and the paper's "
        f"reproducibility statement say 12; update both or restore the set"
    )


def test_every_released_file_has_a_manifest():
    for rel in RELEASED:
        manifest = (REPO / "runs" / rel).with_suffix(".manifest.json")
        assert manifest.exists(), (
            f"{rel} has no provenance sidecar; run scripts/make_data_manifests.py"
        )


# Section 4 states one decoding configuration for the whole study. A single
# off-config batch would falsify that sentence silently, so it is asserted here
# rather than left to a reader diffing JSON.
SAMPLING = {"temperature": 0.6, "max_tokens": 4096}


def test_every_llm_config_sets_the_same_sampling_parameters():
    """Temperature must be set EXPLICITLY: the substrate's LLMConfig dataclass
    defaults temperature to 0.0, so an omitted key would silently run greedy."""
    configs = sorted((REPO / "conf-local").glob("*.json"))
    assert configs, "no LLM configs found; conf-local is where they live"
    for path in configs:
        cfg = json.loads(path.read_text())
        for key, expected in SAMPLING.items():
            assert cfg.get(key) == expected, (
                f"{path.name} sets {key}={cfg.get(key)!r}, not {expected!r}; "
                f"Section 4's single-configuration claim no longer holds"
            )


def test_every_manifest_records_the_same_sampling_parameters():
    manifests = sorted((REPO / "runs").rglob("*manifest*.json"))
    assert manifests, "no manifests found"
    for path in manifests:
        recorded = json.loads(path.read_text()).get("sampling_params")
        assert recorded == SAMPLING, (
            f"{path.relative_to(REPO)} records {recorded!r}, not {SAMPLING!r}; "
            f"Section 4's single-configuration claim no longer holds"
        )
