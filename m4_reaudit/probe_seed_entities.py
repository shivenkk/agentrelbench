"""
M4 STEP 0b, SEED ENTITY RECONNAISSANCE

Seeds ONE throwaway database per domain (from the exact seed files the
finalized 20-task portfolio references -- gc.CSM_SEED / gc.ITSM_SEED, confirmed
identical to every task.json's gym_servers_config.seed_database_file by
compute_tool_union.py), runs read-only SELECT probes via sql_runner to
discover valid entity IDs/names for constructing the Test A/B/C/D fixed
sequences with hardcoded, real arguments (per instructions: "query the seeded
DB first to pick valid entity IDs; read each tool's input schema"). Deletes
the throwaway DB when done -- this is reconnaissance, not one of the audited
replicas.

Rerun: external/EnterpriseOps-Gym/.venv/bin/python m4_reaudit/probe_seed_entities.py
"""
import json
import sys

sys.path.insert(0, "/Users/shiven/Documents/Projects/agentrelbench/m1_audit")
import gym_client as gc

EVIDENCE_DIR = "/Users/shiven/Documents/Projects/agentrelbench/m4_reaudit/evidence"


def q(base_url, db_id, sql):
    r = gc.sql_runner(base_url, sql, db_id)
    return gc.rows_from_sql_result(r)


def probe_csm():
    db = gc.seed(gc.CSM_URL, gc.CSM_SEED)
    print(f"csm probe db: {db}")
    out = {"db_id": db}
    out["account"] = q(gc.CSM_URL, db, "SELECT account_id, name, active, account_type FROM account ORDER BY account_id LIMIT 10;")
    out["product"] = q(gc.CSM_URL, db, "SELECT product_id, name, product_price, lifecycle_state, category FROM product ORDER BY product_id LIMIT 10;")
    out["installed_product"] = q(gc.CSM_URL, db, "SELECT installed_product_id, serial_number, account_id, product_id, location_id, status FROM installed_product ORDER BY installed_product_id LIMIT 10;")
    out["contract"] = q(gc.CSM_URL, db, "SELECT contract_id, account_id, contract_type, status, contract_price FROM contract ORDER BY contract_id LIMIT 10;")
    out["entitlement"] = q(gc.CSM_URL, db, "SELECT entitlement_id, account_id, contract_id, product_id, support_level, active FROM entitlement ORDER BY entitlement_id LIMIT 10;")
    out["customer_case"] = q(gc.CSM_URL, db, "SELECT case_id, account_id, contact_id, assignment_group_id, assigned_to, channel, priority, state, product_id, installed_product_id FROM customer_case ORDER BY case_id LIMIT 10;")
    out["case_sla"] = q(gc.CSM_URL, db, "SELECT case_sla_id, case_id, sla_def_id, stage, start_time, has_breached FROM case_sla ORDER BY case_sla_id DESC LIMIT 10;")
    out["sla_definition"] = q(gc.CSM_URL, db, "SELECT sla_def_id, name FROM sla_definition ORDER BY sla_def_id LIMIT 10;")
    out["knowledge"] = q(gc.CSM_URL, db, "SELECT knowledge_id, title, product_id, owner_id, state, visibility FROM knowledge ORDER BY knowledge_id LIMIT 10;")
    out["case_knowledge"] = q(gc.CSM_URL, db, "SELECT case_kb_id, case_id, knowledge_id, used_as FROM case_knowledge ORDER BY case_kb_id DESC LIMIT 10;")
    out["notification"] = q(gc.CSM_URL, db, "SELECT notification_id, case_id, email, type, status FROM notification ORDER BY notification_id DESC LIMIT 10;")
    out["user_group"] = q(gc.CSM_URL, db, "SELECT group_id, name FROM user_group ORDER BY group_id LIMIT 10;")
    out["user"] = q(gc.CSM_URL, db, "SELECT user_id, first_name, last_name, email, role FROM user ORDER BY user_id LIMIT 15;")
    out["contact"] = q(gc.CSM_URL, db, "SELECT contact_id, account_id FROM contact ORDER BY contact_id LIMIT 10;")
    gc.delete_db(gc.CSM_URL, db)
    return out


def probe_itsm():
    db = gc.seed(gc.ITSM_URL, gc.ITSM_SEED)
    print(f"itsm probe db: {db}")
    out = {"db_id": db}
    out["users"] = q(gc.ITSM_URL, db, "SELECT user_id, first_name, last_name, email FROM users ORDER BY user_id LIMIT 15;")
    out["incident"] = q(gc.ITSM_URL, db, "SELECT incident_id, number, caller_id, assigned_to, assignment_group, category, priority, status, service, configuration_item FROM incident ORDER BY incident_id LIMIT 10;")
    out["change"] = q(gc.ITSM_URL, db, "SELECT change_id, number, status, category, assigned_to, assignment_group, cab_required FROM change ORDER BY change_id LIMIT 10;")
    out["configuration_item"] = q(gc.ITSM_URL, db, "SELECT configuration_item_id, serial_number, owner_id, location_id, cost, status FROM configuration_item ORDER BY configuration_item_id LIMIT 10;")
    out["incident_sla"] = q(gc.ITSM_URL, db, "SELECT incident_sla_id, incident_id, sla_def_id, stage, has_breached FROM incident_sla ORDER BY incident_sla_id DESC LIMIT 10;")
    out["child_incident"] = q(gc.ITSM_URL, db, "SELECT child_incident_mapping_id, parent_incident, child_incident FROM child_incident ORDER BY child_incident_mapping_id LIMIT 20;")
    out["problem"] = q(gc.ITSM_URL, db, "SELECT problem_id, number FROM problem ORDER BY problem_id LIMIT 10;")
    out["change_request_mapping"] = q(gc.ITSM_URL, db, "SELECT change_request_mapping_id, change_id, incident_id, problem_id FROM change_request_mapping ORDER BY change_request_mapping_id LIMIT 20;")
    out["incident_template"] = q(gc.ITSM_URL, db, "SELECT incident_template_id, name FROM incident_template ORDER BY incident_template_id LIMIT 10;")
    out["notification"] = q(gc.ITSM_URL, db, "SELECT notification_id, incident_id, email, type, status FROM notification ORDER BY notification_id DESC LIMIT 10;")
    out["sla_definition"] = q(gc.ITSM_URL, db, "SELECT sla_def_id, name FROM sla_definition ORDER BY sla_def_id LIMIT 10;")
    gc.delete_db(gc.ITSM_URL, db)
    return out


def main():
    csm = probe_csm()
    itsm = probe_itsm()
    with open(f"{EVIDENCE_DIR}/seed_probe_csm.json", "w") as f:
        json.dump(csm, f, indent=2, sort_keys=True, default=str)
    with open(f"{EVIDENCE_DIR}/seed_probe_itsm.json", "w") as f:
        json.dump(itsm, f, indent=2, sort_keys=True, default=str)
    print("wrote seed_probe_csm.json, seed_probe_itsm.json")


if __name__ == "__main__":
    main()
