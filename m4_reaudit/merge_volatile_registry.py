"""
M4 STEP FINAL, MERGE EMPIRICAL FINDINGS INTO data/eog/volatile-columns-*.json

Reads this audit's Test A evidence (m4_reaudit/evidence/test_a_{csm,itsm}.json
-- the only tests that produce multi-replica diffs; Test B was zero-diff by
construction and Test C/D don't full-dump-diff) and reconciles each
empirically-observed table.column against the existing registry
(data/eog/volatile-columns-{csm,itsm}.json), which currently mixes real
M1-empirical entries (have diff_count/examples) with placeholder entries added
by a systematic DDL scan (no diff_count -- just a
"schema-convention audit timestamp ... empirical confirmation due in M4"
provenance note).

For each table.column this run observed varying:
  - Not in the registry at all              -> ADD as a brand-new entry
                                                (this is what M4's gate cares
                                                about most).
  - In the registry only as a DDL-scan
    placeholder (no diff_count)             -> UPGRADE in place: replace the
                                                placeholder with the real
                                                empirical entry (diff_count,
                                                examples, behavior), keeping a
                                                provenance trail.
  - Already a real M1-empirical entry        -> leave untouched (already
                                                confirmed; reconfirming here
                                                would just be noise -- surgical
                                                changes only).

Nothing else in the registry files is touched (replicas/sequence_length/etc.
describe the ORIGINAL M1 test3 run specifically and are left as historical
record; a single new top-level "m4_reaudit" note records what changed here).

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/merge_volatile_registry.py
"""
import json

DATA_DIR = "/Users/shiven/Documents/Projects/agentrelbench/data/eog"
EVIDENCE_DIR = "/Users/shiven/Documents/Projects/agentrelbench/m4_reaudit/evidence"
TODAY = "2026-07-16"


def is_placeholder(entry: dict) -> bool:
    """DDL-scan placeholder entries have no diff_count/examples -- just a
    provenance note saying empirical confirmation is pending."""
    return "diff_count" not in entry


def merge_domain(domain: str, test_a_script: str):
    registry_path = f"{DATA_DIR}/volatile-columns-{domain}.json"
    evidence_path = f"{EVIDENCE_DIR}/test_a_{domain}.json"

    registry = json.load(open(registry_path))
    evidence = json.load(open(evidence_path))
    observed = evidence["varying_columns"]  # key "table.column" -> {table, column, diff_count, examples, behavior}

    brand_new, upgraded, already_confirmed = [], [], []

    for key, obs_entry in observed.items():
        existing = registry["volatile_columns"].get(key)
        new_entry = {
            "table": obs_entry["table"],
            "column": obs_entry["column"],
            "behavior": obs_entry["behavior"],
            "diff_count": obs_entry["diff_count"],
            "examples": obs_entry["examples"],
        }
        if existing is None:
            new_entry["provenance"] = (
                f"NEW -- discovered by M4 full-toolset re-audit ({test_a_script}, {TODAY}); "
                f"not present in the M1 audit or the systematic DDL scan (the tool(s) touching "
                f"this table were outside M1's original 6/5-tool replay sequence)."
            )
            registry["volatile_columns"][key] = new_entry
            brand_new.append(key)
        elif is_placeholder(existing):
            new_entry["provenance"] = (
                f"CONFIRMED by M4 full-toolset re-audit ({test_a_script}, {TODAY}) -- was a "
                f"systematic-DDL-scan placeholder ('empirical confirmation due in M4 full-toolset "
                f"re-audit'); now backed by a live 3-replica diff."
            )
            registry["volatile_columns"][key] = new_entry
            upgraded.append(key)
        else:
            already_confirmed.append(key)

    registry["m4_reaudit"] = {
        "date": TODAY,
        "script": test_a_script,
        "brand_new_columns_added": sorted(brand_new),
        "placeholder_columns_upgraded_to_empirical": sorted(upgraded),
        "already_empirical_columns_reconfirmed_untouched": sorted(already_confirmed),
        "evidence_doc": "docs/M4-reaudit-evidence.md",
    }

    with open(registry_path, "w") as f:
        # indent=1, sort_keys=False: matches the existing on-disk formatting of these registry
        # files exactly (confirmed via `git show HEAD:<path>` -- the files preserve INSERTION
        # order, not alphabetical; a later "systematic DDL scan" appended keys without
        # re-sorting). Updating existing dict keys in place preserves their position; only
        # genuinely new keys get appended at the end -- same convention the DDL scan used.
        # This keeps the diff surgical instead of reformatting/reordering the whole file.
        json.dump(registry, f, indent=1, sort_keys=False, default=str)

    print(f"=== {domain} ===")
    print(f"  brand-new columns added:        {sorted(brand_new)}")
    print(f"  placeholders upgraded:          {sorted(upgraded)}")
    print(f"  already-empirical (untouched):  {sorted(already_confirmed)}")
    print(f"  wrote -> {registry_path}\n")
    return {"brand_new": brand_new, "upgraded": upgraded, "already_confirmed": already_confirmed}


def main():
    results = {}
    results["csm"] = merge_domain("csm", "m4_reaudit/test_a_mutating_determinism_csm.py")
    results["itsm"] = merge_domain("itsm", "m4_reaudit/test_a_mutating_determinism_itsm.py")
    total_new = sum(len(r["brand_new"]) for r in results.values())
    print(f"TOTAL brand-new volatile columns discovered across both domains: {total_new}")


if __name__ == "__main__":
    main()
