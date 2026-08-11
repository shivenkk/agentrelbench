-- Database Seed Data for: anmol-itsm-db-v1
-- Database ID: db_1765301900121_3mwjj54xy
-- MCP Server: sn-itsm-internal
-- Created: 2025-12-09 17:38:22.118563+00:00
-- Description: No description provided
-- NOTE: This is seed data fallback (export-sql API was unavailable)

-- ============================================
-- SEED DATA (SQL Statements)
-- ============================================


-- ITSM Sample Data - 100% Schema Compliant with RBAC and Tenant Scoping
-- Two Organizations: TechCorp (ORG_001) and Acme Corp (ORG_002)
-- ===========================================

-- Organizations (organization)
INSERT INTO organization (org_id, name, active, created_at, updated_at) VALUES
('ORG_001', 'TechCorp', 1, datetime('2024-01-01 08:00:00'), datetime('2024-01-01 08:00:00')),
('ORG_002', 'Acme Corp', 1, datetime('2024-01-01 08:00:00'), datetime('2024-01-01 08:00:00'));

-- Roles (role) - shared across organizations
INSERT INTO role (role_id, name) VALUES
('ROLE_001', 'admin'),
('ROLE_002', 'manager'),
('ROLE_003', 'agent'),
('ROLE_004', 'reporter');

        -- Permissions (permission) - Simplified model: CRUD and READ only
        -- 18 resources × 2 actions = 36 permissions total
INSERT INTO permission (perm_id, resource, action) VALUES
-- Users permissions
('PERM_001', 'users', 'read'),
('PERM_002', 'users', 'crud'),
-- Groups permissions
('PERM_003', 'groups', 'read'),
('PERM_004', 'groups', 'crud'),
-- Services permissions
('PERM_005', 'services', 'read'),
('PERM_006', 'services', 'crud'),
-- Service Offerings permissions
('PERM_007', 'service_offerings', 'read'),
('PERM_008', 'service_offerings', 'crud'),
-- Configuration Items permissions
('PERM_009', 'configuration_items', 'read'),
('PERM_010', 'configuration_items', 'crud'),
-- Incident Templates permissions
('PERM_011', 'incident_templates', 'read'),
('PERM_012', 'incident_templates', 'crud'),
-- Problems permissions
('PERM_013', 'problems', 'read'),
('PERM_014', 'problems', 'crud'),
-- Changes permissions
('PERM_015', 'changes', 'read'),
('PERM_016', 'changes', 'crud'),
-- Notifications permissions
('PERM_017', 'notifications', 'read'),
('PERM_018', 'notifications', 'crud'),
-- Notification Analysis permissions
('PERM_019', 'notification_analysis', 'read'),
('PERM_020', 'notification_analysis', 'crud'),
-- SLA Definitions permissions
('PERM_021', 'sla_definitions', 'read'),
('PERM_022', 'sla_definitions', 'crud'),
-- SLA Metrics permissions
('PERM_023', 'sla_metrics', 'read'),
('PERM_024', 'sla_metrics', 'crud'),
-- Incidents permissions
('PERM_025', 'incidents', 'read'),
('PERM_026', 'incidents', 'crud'),
-- Knowledge permissions
('PERM_027', 'knowledge', 'read'),
('PERM_028', 'knowledge', 'crud'),
-- Locations permissions
('PERM_029', 'locations', 'read'),
('PERM_030', 'locations', 'crud'),
-- Change Mappings permissions
('PERM_031', 'change_mappings', 'read'),
('PERM_032', 'change_mappings', 'crud'),
-- Incident Affected CIs permissions
('PERM_033', 'incident_affected_cis', 'read'),
('PERM_034', 'incident_affected_cis', 'crud'),
-- Incident SLAs permissions
('PERM_035', 'incident_slas', 'read'),
('PERM_036', 'incident_slas', 'crud');

-- Role-Permission mappings (role_permission)
-- Admin: all CRUD permissions (15 resources)
INSERT INTO role_permission (role_id, perm_id) VALUES
('ROLE_001', 'PERM_002'), ('ROLE_001', 'PERM_004'), ('ROLE_001', 'PERM_006'), ('ROLE_001', 'PERM_008'),
('ROLE_001', 'PERM_010'), ('ROLE_001', 'PERM_012'), ('ROLE_001', 'PERM_014'), ('ROLE_001', 'PERM_016'),
('ROLE_001', 'PERM_018'), ('ROLE_001', 'PERM_020'), ('ROLE_001', 'PERM_022'), ('ROLE_001', 'PERM_024'),
('ROLE_001', 'PERM_026'), ('ROLE_001', 'PERM_028'), ('ROLE_001', 'PERM_030'), ('ROLE_001', 'PERM_032'),
('ROLE_001', 'PERM_034'), ('ROLE_001', 'PERM_036');

-- Manager: all CRUD permissions (15 resources)
INSERT INTO role_permission (role_id, perm_id) VALUES
('ROLE_002', 'PERM_002'), ('ROLE_002', 'PERM_004'), ('ROLE_002', 'PERM_006'), ('ROLE_002', 'PERM_008'),
('ROLE_002', 'PERM_010'), ('ROLE_002', 'PERM_012'), ('ROLE_002', 'PERM_014'), ('ROLE_002', 'PERM_016'),
('ROLE_002', 'PERM_018'), ('ROLE_002', 'PERM_020'), ('ROLE_002', 'PERM_022'), ('ROLE_002', 'PERM_024'),
('ROLE_002', 'PERM_026'), ('ROLE_002', 'PERM_028'), ('ROLE_002', 'PERM_030'), ('ROLE_002', 'PERM_032'),
('ROLE_002', 'PERM_034'), ('ROLE_002', 'PERM_036');

-- Agent: mixed permissions
-- CRUD: configuration_items, problems, changes, incidents, knowledge, locations
-- READ: users, groups, services, service_offerings, incident_templates, notifications, notification_analysis, sla_definitions, sla_metrics, change_mappings, incident_affected_cis, incident_slas
INSERT INTO role_permission (role_id, perm_id) VALUES
('ROLE_003', 'PERM_001'), ('ROLE_003', 'PERM_003'), ('ROLE_003', 'PERM_005'), ('ROLE_003', 'PERM_007'),
('ROLE_003', 'PERM_010'), ('ROLE_003', 'PERM_011'), ('ROLE_003', 'PERM_014'), ('ROLE_003', 'PERM_016'),
('ROLE_003', 'PERM_017'), ('ROLE_003', 'PERM_019'), ('ROLE_003', 'PERM_021'), ('ROLE_003', 'PERM_023'),
('ROLE_003', 'PERM_026'), ('ROLE_003', 'PERM_028'), ('ROLE_003', 'PERM_030'), ('ROLE_003', 'PERM_031'),
('ROLE_003', 'PERM_033'), ('ROLE_003', 'PERM_035');

-- Reporter: all READ permissions (15 resources)
INSERT INTO role_permission (role_id, perm_id) VALUES
('ROLE_004', 'PERM_001'), ('ROLE_004', 'PERM_003'), ('ROLE_004', 'PERM_005'), ('ROLE_004', 'PERM_007'),
('ROLE_004', 'PERM_009'), ('ROLE_004', 'PERM_011'), ('ROLE_004', 'PERM_013'), ('ROLE_004', 'PERM_015'),
('ROLE_004', 'PERM_017'), ('ROLE_004', 'PERM_019'), ('ROLE_004', 'PERM_021'), ('ROLE_004', 'PERM_023'),
('ROLE_004', 'PERM_025'), ('ROLE_004', 'PERM_027'), ('ROLE_004', 'PERM_029'), ('ROLE_004', 'PERM_031'),
('ROLE_004', 'PERM_033'), ('ROLE_004', 'PERM_035');

-- Locations (location) - tenant-scoped
INSERT INTO location (location_id, name, plot_no, street, city, state, country, active, org_id, created_on, updated_on) VALUES
('LOC_001', 'TechCorp NYC Headquarters', '100', 'Broadway', 'New York', 'NY', 'USA', 1, 'ORG_001', datetime('2024-01-01 08:00:00'), datetime('2024-01-01 08:00:00')),
('LOC_002', 'London Development Center', '25', 'Canary Wharf', 'London', 'England', 'UK', 1, 'ORG_001', datetime('2024-01-01 09:00:00'), datetime('2024-01-01 09:00:00')),
('LOC_003', 'Acme Corp HQ', '500', 'Market Street', 'San Francisco', 'CA', 'USA', 1, 'ORG_002', datetime('2024-01-01 10:00:00'), datetime('2024-01-01 10:00:00'));

-- Users - ORG_001 (TechCorp): USER_001-006
INSERT INTO users (user_id, user_name, first_name, last_name, email, phone, role, active, static_token, org_id, location_id, created_on, updated_on) VALUES
('USER_001', 'marcus.thompson', 'Marcus', 'Thompson', 'marcus.thompson@techcorp.com', '+1-415-555-0101', 'admin', 1, 'admin_token_marcus_2024_secure', 'ORG_001', 'LOC_001', datetime('2024-01-15 09:00:00'), datetime('2024-01-15 09:00:00')),
('USER_002', 'priya.sharma', 'Priya', 'Sharma', 'priya.sharma@techcorp.com', '+1-415-555-0102', 'manager', 1, 'manager_token_priya_2024_secure', 'ORG_001', 'LOC_001', datetime('2024-01-16 10:00:00'), datetime('2024-01-16 10:00:00')),
('USER_003', 'carlos.rodriguez', 'Carlos', 'Rodriguez', 'carlos.rodriguez@techcorp.com', '+1-415-555-0103', 'agent', 1, 'agent_token_carlos_2024_secure', 'ORG_001', 'LOC_001', datetime('2024-01-17 11:00:00'), datetime('2024-01-17 11:00:00')),
('USER_004', 'aisha.williams', 'Aisha', 'Williams', 'aisha.williams@techcorp.com', '+1-415-555-0104', 'agent', 1, 'agent_token_aisha_2024_secure', 'ORG_001', 'LOC_001', datetime('2024-01-18 12:00:00'), datetime('2024-01-18 12:00:00')),
('USER_005', 'benjamin.chen', 'Benjamin', 'Chen', 'benjamin.chen@techcorp.com', '+1-415-555-0105', 'reporter', 1, 'reporter_token_benjamin_2024_secure', 'ORG_001', 'LOC_002', datetime('2024-01-19 13:00:00'), datetime('2024-01-19 13:00:00')),
('USER_006', 'elena.petrov', 'Elena', 'Petrov', 'elena.petrov@techcorp.com', '+1-415-555-0106', 'agent', 1, 'agent_token_elena_2024_secure', 'ORG_001', 'LOC_002', datetime('2024-01-20 14:00:00'), datetime('2024-01-20 14:00:00'));

-- Users - ORG_002 (Acme Corp): USER_007-010
INSERT INTO users (user_id, user_name, first_name, last_name, email, phone, role, active, static_token, org_id, location_id, created_on, updated_on) VALUES
('USER_007', 'raj.patel', 'Raj', 'Patel', 'raj.patel@acme.com', '+1-415-555-0107', 'admin', 1, 'admin_token_raj_2024_secure', 'ORG_002', 'LOC_003', datetime('2024-01-21 15:00:00'), datetime('2024-01-21 15:00:00')),
('USER_008', 'sophie.mueller', 'Sophie', 'Mueller', 'sophie.mueller@acme.com', '+1-415-555-0108', 'manager', 1, 'manager_token_sophie_2024_secure', 'ORG_002', 'LOC_003', datetime('2024-01-22 16:00:00'), datetime('2024-01-22 16:00:00')),
('USER_009', 'kenji.tanaka', 'Kenji', 'Tanaka', 'kenji.tanaka@acme.com', '+1-415-555-0109', 'agent', 1, 'agent_token_kenji_2024_secure', 'ORG_002', 'LOC_003', datetime('2024-01-23 17:00:00'), datetime('2024-01-23 17:00:00')),
('USER_010', 'isabella.rossi', 'Isabella', 'Rossi', 'isabella.rossi@acme.com', '+1-415-555-0110', 'reporter', 1, 'reporter_token_isabella_2024_secure', 'ORG_002', 'LOC_003', datetime('2024-01-24 18:00:00'), datetime('2024-01-24 18:00:00'));

-- User Groups - ORG_001 (TechCorp)
INSERT INTO user_group (group_id, name, type, active, email, description, manager_id, org_id, created_on, updated_on) VALUES
('GROUP_001', 'Level 1 Support Team', 'IT Support', 1, 'support-l1@techcorp.com', 'First level support team handling initial user requests', 'USER_002', 'ORG_001', datetime('2024-01-10 08:00:00'), datetime('2024-01-10 08:00:00')),
('GROUP_002', 'Service Desk Operations', 'Service Desk', 1, 'servicedesk@techcorp.com', 'Service desk operations team managing IT requests', 'USER_002', 'ORG_001', datetime('2024-01-10 08:30:00'), datetime('2024-01-10 08:30:00'));

-- User Groups - ORG_002 (Acme Corp)
INSERT INTO user_group (group_id, name, type, active, email, description, manager_id, org_id, created_on, updated_on) VALUES
('GROUP_003', 'IT Support Team', 'IT Support', 1, 'itsupport@acme.com', 'IT support team for Acme Corp', 'USER_008', 'ORG_002', datetime('2024-01-10 09:00:00'), datetime('2024-01-10 09:00:00')),
('GROUP_004', 'Infrastructure Team', 'Infrastructure Problem Team', 1, 'infrastructure@acme.com', 'Infrastructure and problem resolution team', 'USER_008', 'ORG_002', datetime('2024-01-10 09:30:00'), datetime('2024-01-10 09:30:00'));

-- User Group Members - ORG_001
INSERT INTO user_group_member (member_id, group_id, user_id, org_id, created_on, updated_on) VALUES
('MEMBER_001', 'GROUP_001', 'USER_003', 'ORG_001', datetime('2024-01-15 10:00:00'), datetime('2024-01-15 10:00:00')),
('MEMBER_002', 'GROUP_001', 'USER_004', 'ORG_001', datetime('2024-01-15 10:30:00'), datetime('2024-01-15 10:30:00')),
('MEMBER_003', 'GROUP_002', 'USER_006', 'ORG_001', datetime('2024-01-16 11:00:00'), datetime('2024-01-16 11:00:00'));

-- User Group Members - ORG_002
INSERT INTO user_group_member (member_id, group_id, user_id, org_id, created_on, updated_on) VALUES
('MEMBER_004', 'GROUP_003', 'USER_009', 'ORG_002', datetime('2024-01-17 12:00:00'), datetime('2024-01-17 12:00:00')),
('MEMBER_005', 'GROUP_004', 'USER_008', 'ORG_002', datetime('2024-01-18 13:00:00'), datetime('2024-01-18 13:00:00'));

-- User-Role assignments - ORG_001
-- All roles are org-wide (no group_id column)
-- Future: Group-based permission differentiation can be handled via user_group_member table
INSERT INTO user_role (user_id, role_id, org_id) VALUES
-- Admins
('USER_001', 'ROLE_001', 'ORG_001'),
-- Managers
('USER_002', 'ROLE_002', 'ORG_001'),
-- Agents (org-wide roles)
('USER_003', 'ROLE_003', 'ORG_001'),
('USER_004', 'ROLE_003', 'ORG_001'),
('USER_006', 'ROLE_003', 'ORG_001'),
-- Reporters
('USER_005', 'ROLE_004', 'ORG_001');

-- User-Role assignments - ORG_002
-- All roles are org-wide (no group_id column)
INSERT INTO user_role (user_id, role_id, org_id) VALUES
-- Admins
('USER_007', 'ROLE_001', 'ORG_002'),
-- Managers
('USER_008', 'ROLE_002', 'ORG_002'),
-- Agents (org-wide roles)
('USER_009', 'ROLE_003', 'ORG_002'),
-- Reporters
('USER_010', 'ROLE_004', 'ORG_002');

-- Incident Templates - ORG_001
INSERT INTO incident_template (incident_template_id, name, caller_id, channel, short_description, category, impact, urgency, priority, configuration_item, service, service_offering, active, org_id, created_at, updated_at) VALUES
('TMPL_001', 'Password Reset Template', 'USER_001', 'email', 'Password reset required for user account', 'password-reset', 'low', 'low', 'moderate', NULL, NULL, NULL, 1, 'ORG_001', datetime('2024-01-05 09:00:00'), datetime('2024-01-05 09:00:00')),
('TMPL_002', 'Network Connectivity Issue', 'USER_002', 'phone', 'User experiencing network connectivity problems', 'hardware', 'low', 'low', 'high', NULL, NULL, NULL, 1, 'ORG_001', datetime('2024-01-05 10:00:00'), datetime('2024-01-05 10:00:00'));

-- Incident Templates - ORG_002
INSERT INTO incident_template (incident_template_id, name, caller_id, channel, short_description, category, impact, urgency, priority, configuration_item, service, service_offering, active, org_id, created_at, updated_at) VALUES
('TMPL_003', 'Software Installation Request', 'USER_007', 'self-service', 'Software installation required', 'software', 'low', 'low', 'moderate', NULL, NULL, NULL, 1, 'ORG_002', datetime('2024-01-05 11:00:00'), datetime('2024-01-05 11:00:00'));

-- Knowledge Articles (knowledge) - ORG_001
INSERT INTO knowledge (knowledge_id, kb_number, title, short_description, body, state, visibility, owner_id, org_id, created_on, updated_on) VALUES
('KB_001', 'KB0000001', 'Password Reset Procedure', 'Step-by-step guide for resetting user passwords', 'This article provides instructions for IT staff to reset user passwords through Active Directory. Steps: 1. Open AD Users and Computers. 2. Locate the user account. 3. Right-click and select Reset Password. 4. Enter new temporary password. 5. Check "User must change password at next logon". 6. Click OK and notify user.', 'published', 'internal', 'USER_002', 'ORG_001', datetime('2024-01-20 10:00:00'), datetime('2024-01-20 10:00:00')),
('KB_002', 'KB0000002', 'Email Client Configuration Guide', 'How to configure Outlook email client', 'Complete guide for configuring Microsoft Outlook email client. Includes server settings, port configurations, SSL settings, and troubleshooting common connection issues. Recommended for Level 1 support staff.', 'published', 'internal', 'USER_002', 'ORG_001', datetime('2024-01-22 11:00:00'), datetime('2024-01-22 11:00:00')),
('KB_003', 'KB0000003', 'Desktop Boot Failure Troubleshooting', 'Diagnostic steps for desktop boot issues', 'Comprehensive troubleshooting guide for desktop computers that fail to boot. Covers: power supply checks, RAM diagnostics, display connection verification, BIOS settings, and hardware component testing. Use this for Level 2 hardware support.', 'published', 'internal', 'USER_003', 'ORG_001', datetime('2024-01-25 14:00:00'), datetime('2024-01-25 14:00:00'));

-- Knowledge Articles (knowledge) - ORG_002
INSERT INTO knowledge (knowledge_id, kb_number, title, short_description, body, state, visibility, owner_id, org_id, created_on, updated_on) VALUES
('KB_004', 'KB0000001', 'Email Account Recovery Steps', 'Instructions for recovering locked email accounts', 'This knowledge article describes the process for recovering and unlocking user email accounts. Steps include: verifying user identity, checking account status in admin console, unlocking the account, resetting password if needed, and testing access. Estimated resolution time: 15 minutes.', 'published', 'internal', 'USER_008', 'ORG_002', datetime('2024-01-23 09:00:00'), datetime('2024-01-23 09:00:00')),
('KB_005', 'KB0000002', 'Corporate Email Access Guide', 'Common solutions for email access problems', 'Troubleshooting guide for common email access issues including: authentication failures, network connectivity problems, client configuration errors, and server connection issues. Includes both self-service and agent-assisted solutions.', 'published', 'internal', 'USER_008', 'ORG_002', datetime('2024-01-26 10:30:00'), datetime('2024-01-26 10:30:00'));

-- Configuration Items - ORG_001
INSERT INTO configuration_item (configuration_item_id, name, serial_number, owner_id, location_id, status, cost, org_id, created_on, updated_on) VALUES
('CI_001', 'Carlos Laptop', 'LAPTOP-NYC-001', 'USER_003', 'LOC_001', 'in_use', 1200.00, 'ORG_001', datetime('2024-01-10 10:00:00'), datetime('2024-01-10 10:00:00')),
('CI_002', 'Aisha Desktop', 'DESKTOP-NYC-145', 'USER_004', 'LOC_001', 'in_use', 800.00, 'ORG_001', datetime('2024-01-10 11:00:00'), datetime('2024-01-10 11:00:00'));

-- Configuration Items - ORG_002
INSERT INTO configuration_item (configuration_item_id, name, serial_number, owner_id, location_id, status, cost, org_id, created_on, updated_on) VALUES
('CI_003', 'Kenji Workstation', 'WS-SF-001', 'USER_009', 'LOC_003', 'in_use', 1500.00, 'ORG_002', datetime('2024-01-10 12:00:00'), datetime('2024-01-10 12:00:00')),
('CI_004', 'Acme Email Server', 'SERVER-SF-SRV01', 'USER_007', 'LOC_003', 'in_use', 6000.00, 'ORG_002', datetime('2024-01-10 13:00:00'), datetime('2024-01-10 13:00:00'));

-- Services - ORG_001
INSERT INTO service (service_id, name, owned_by, org_id, used_for, status, service_classification, business_criticality, description, created_on, updated_on) VALUES
('SVC_001', 'Email Service', 'USER_001', 'ORG_001', 'production', 'operational', 'technology-management', 'critical', 'Corporate email service for all employees', datetime('2024-01-08 09:00:00'), datetime('2024-01-08 09:00:00')),
('SVC_002', 'Customer Portal', 'USER_002', 'ORG_001', 'production', 'operational', 'business', 'critical', 'External customer-facing web portal', datetime('2024-01-08 10:00:00'), datetime('2024-01-08 10:00:00'));

-- Services - ORG_002
INSERT INTO service (service_id, name, owned_by, org_id, used_for, status, service_classification, business_criticality, description, created_on, updated_on) VALUES
('SVC_003', 'Acme Email Service', 'USER_007', 'ORG_002', 'production', 'operational', 'technology-management', 'critical', 'Corporate email service for Acme Corp', datetime('2024-01-08 11:00:00'), datetime('2024-01-08 11:00:00')),
('SVC_004', 'Development Environment', 'USER_008', 'ORG_002', 'development', 'operational', 'application', 'less-critical', 'Development and testing environment', datetime('2024-01-08 12:00:00'), datetime('2024-01-08 12:00:00'));

-- Service Offerings - ORG_001
INSERT INTO service_offering (service_offering_id, name, owned_by, business_service, used_for, status, service_classification, business_criticality, short_description, description, org_id, created_on, updated_on) VALUES
('SVCOFF_001', 'Outlook Email Access', 'USER_003', 'SVC_001', 'production', 'operational', 'technology-management', 'critical', 'Microsoft Outlook email client access', 'Provides access to corporate email through Microsoft Outlook client', 'ORG_001', datetime('2024-01-08 12:00:00'), datetime('2024-01-08 12:00:00')),
('SVCOFF_002', 'Web Portal Login', 'USER_004', 'SVC_002', 'production', 'operational', 'business', 'critical', 'Customer web portal authentication', 'Authentication and login service for customer portal', 'ORG_001', datetime('2024-01-08 13:00:00'), datetime('2024-01-08 13:00:00'));

-- Service Offerings - ORG_002
INSERT INTO service_offering (service_offering_id, name, owned_by, business_service, used_for, status, service_classification, business_criticality, short_description, description, org_id, created_on, updated_on) VALUES
('SVCOFF_003', 'Acme Email Access', 'USER_009', 'SVC_003', 'production', 'operational', 'technology-management', 'critical', 'Corporate email access', 'Provides access to corporate email', 'ORG_002', datetime('2024-01-08 14:00:00'), datetime('2024-01-08 14:00:00')),
('SVCOFF_004', 'Dev Server Access', 'USER_008', 'SVC_004', 'development', 'operational', 'application', 'less-critical', 'Development server environment access', 'Access to development and testing server environment', 'ORG_002', datetime('2024-01-08 15:00:00'), datetime('2024-01-08 15:00:00'));

-- SLA Definitions - ORG_001
INSERT INTO sla_definition (sla_def_id, name, metric, target_mins, pause_on_pending, applies_to_priority, active, schedule, org_id, created_on, updated_on) VALUES
('SLA_001', 'Critical Response SLA', 'response', 15, 1, 'critical', 1, NULL, 'ORG_001', datetime('2024-01-05 08:00:00'), datetime('2024-01-05 08:00:00')),
('SLA_002', 'High Priority Resolution SLA', 'resolution', 240, 1, 'high', 1, NULL, 'ORG_001', datetime('2024-01-05 09:00:00'), datetime('2024-01-05 09:00:00')),
('SLA_004', 'Moderate Priority Response SLA', 'response', 60, 1, 'moderate', 1, NULL, 'ORG_001', datetime('2024-01-05 10:00:00'), datetime('2024-01-05 10:00:00')),
('SLA_005', 'Low Priority Resolution SLA', 'resolution', 480, 1, 'low', 1, NULL, 'ORG_001', datetime('2024-01-05 11:00:00'), datetime('2024-01-05 11:00:00')),
('SLA_006', 'Low Priority Standard Response SLA', 'response', 120, 1, 'low', 1, NULL, 'ORG_001', datetime('2024-01-05 12:00:00'), datetime('2024-01-05 12:00:00'));

-- SLA Definitions - ORG_002
INSERT INTO sla_definition (sla_def_id, name, metric, target_mins, pause_on_pending, applies_to_priority, active, schedule, org_id, created_on, updated_on) VALUES
('SLA_003', 'Standard Response SLA', 'response', 120, 1, 'moderate', 1, NULL, 'ORG_002', datetime('2024-01-05 10:00:00'), datetime('2024-01-05 10:00:00')),
('SLA_007', 'Critical Priority Response SLA', 'response', 20, 1, 'critical', 1, NULL, 'ORG_002', datetime('2024-01-05 13:00:00'), datetime('2024-01-05 13:00:00')),
('SLA_008', 'High Priority Resolution SLA', 'resolution', 360, 1, 'high', 1, NULL, 'ORG_002', datetime('2024-01-05 14:00:00'), datetime('2024-01-05 14:00:00')),
('SLA_009', 'Low Priority Response SLA', 'response', 180, 1, 'low', 1, NULL, 'ORG_002', datetime('2024-01-05 15:00:00'), datetime('2024-01-05 15:00:00')),
('SLA_010', 'Database Resolution SLA', 'resolution', 600, 1, 'moderate', 1, NULL, 'ORG_002', datetime('2024-01-05 16:00:00'), datetime('2024-01-05 16:00:00'));

-- Incidents - ORG_001
INSERT INTO incident (incident_id, number, short_description, caller_id, service, service_offering, configuration_item, assigned_to, assignment_group, resolved_by, problem, change_request, caused_by_change, incident_template, parent_incident, org_id, channel, contact_type, status, category, description, worknotes, resolution_notes, close_notes, impact, urgency, priority, resolution_code, on_hold_reason, resolved, created_at, updated_at, service_display, service_offering_display, configuration_item_display, assigned_to_display, assignment_group_display, parent_incident_display, problem_display, change_request_display, incident_template_display) VALUES
('INC_001', 'INC0000001', 'Cannot access email account', 'USER_005', 'SVC_001', 'SVCOFF_001', 'CI_001', 'USER_003', 'GROUP_001', 'USER_003', NULL, NULL, NULL, 'TMPL_001', NULL, 'ORG_001', 'email', 'email', 'resolved', 'password-reset', 'User reports unable to log into Outlook email client', 'Password reset initiated via AD', 'Password successfully reset and user can access email', 'Issue resolved - user confirmed access restored', 'medium', 'medium', 'moderate', 'Solution Provided', NULL, datetime('2024-02-15 14:30:00'), datetime('2024-02-10 09:15:00'), datetime('2024-02-15 14:30:00'), 'Email Service', 'Outlook Email Access', 'Carlos Laptop', 'Carlos Rodriguez', 'Level 1 Support Team', NULL, NULL, NULL, NULL),
('INC_002', 'INC0000002', 'Desktop computer not booting', 'USER_005', 'SVC_002', 'SVCOFF_002', 'CI_002', 'USER_004', 'GROUP_002', NULL, NULL, NULL, NULL, 'TMPL_002', NULL, 'ORG_001', 'phone', 'phone', 'in_progress', 'hardware', 'Desktop workstation fails to power on, no display output', 'Hardware diagnostics in progress, checking power supply', NULL, NULL, 'high', 'high', 'high', NULL, NULL, NULL, datetime('2024-02-20 11:45:00'), datetime('2024-02-20 16:22:00'), 'Customer Portal', 'Web Portal Login', 'Aisha Desktop', 'Aisha Williams', 'Service Desk Operations', NULL, NULL, NULL, NULL),
('INC_003', 'INC0000003', 'Printer connectivity issue', 'USER_005', 'SVC_001', 'SVCOFF_001', 'CI_001', 'USER_003', 'GROUP_001', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'email', 'email', 'new', 'hardware', 'User unable to print documents from office printer', 'Checking printer configuration and network connectivity', NULL, NULL, 'low', 'medium', 'moderate', NULL, NULL, NULL, datetime('2024-02-19 10:00:00'), datetime('2024-02-19 10:00:00'), 'Email Service', 'Outlook Email Access', 'Carlos Laptop', 'Carlos Rodriguez', 'Level 1 Support Team', NULL, NULL, NULL, NULL),
('INC_004', 'INC0000004', 'Network connectivity issues', 'USER_003', 'SVC_001', 'SVCOFF_001', 'CI_001', 'USER_006', 'GROUP_001', NULL, NULL, NULL, NULL, 'TMPL_002', NULL, 'ORG_001', 'phone', 'phone', 'new', 'hardware', 'Intermittent network connection in NYC office', 'Initial troubleshooting performed', NULL, NULL, 'high', 'high', 'high', NULL, NULL, NULL, datetime('2024-02-18 09:30:00'), datetime('2024-02-18 09:30:00'), 'Email Service', 'Outlook Email Access', 'Carlos Laptop', 'Elena Petrov', 'Level 1 Support Team', NULL, NULL, NULL, NULL),
('INC_005', 'INC0000005', 'Software installation request', 'USER_004', 'SVC_002', 'SVCOFF_002', 'CI_002', 'USER_003', 'GROUP_002', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'self-service', 'portal', 'new', 'software', 'Request for Adobe Creative Suite installation', 'License verification in progress', NULL, NULL, 'low', 'low', 'low', NULL, NULL, NULL, datetime('2024-02-19 13:15:00'), datetime('2024-02-19 13:15:00'), 'Customer Portal', 'Web Portal Login', 'Aisha Desktop', 'Carlos Rodriguez', 'Service Desk Operations', NULL, NULL, NULL, NULL),
('INC_006', 'INC0000006', 'Critical system outage', 'USER_001', 'SVC_001', 'SVCOFF_001', NULL, 'USER_002', 'GROUP_002', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'phone', 'phone', 'in_progress', 'software', 'Complete email system outage affecting all users', 'Server restart attempted, investigating database corruption', NULL, NULL, 'high', 'high', 'critical', NULL, NULL, NULL, datetime('2024-02-21 08:05:00'), datetime('2024-02-21 08:45:00'), 'Email Service', 'Outlook Email Access', NULL, 'Priya Sharma', 'Service Desk Operations', NULL, NULL, NULL, NULL),
('INC_007', 'INC0000007', 'Account lockout issue', 'USER_003', 'SVC_001', 'SVCOFF_001', 'CI_001', 'USER_004', 'GROUP_001', 'USER_004', NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'email', 'email', 'resolved', 'password-reset', 'Multiple failed login attempts resulting in account lockout', 'Account unlocked, password reset', 'User provided with new credentials', 'Issue resolved', 'low', 'medium', 'moderate', 'Solution Provided', NULL, datetime('2024-02-22 10:35:00'), datetime('2024-02-22 09:10:00'), datetime('2024-02-22 10:35:00'), 'Email Service', 'Outlook Email Access', 'Carlos Laptop', 'Aisha Williams', 'Level 1 Support Team', NULL, NULL, NULL, NULL),
('INC_008', 'INC0000008', 'Feature enhancement request', 'USER_006', 'SVC_002', 'SVCOFF_002', NULL, 'USER_002', 'GROUP_002', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'email', 'email', 'in_progress', 'software', 'Request for additional reporting capabilities', 'Evaluating feasibility and implementation options', NULL, NULL, 'low', 'low', 'planning', NULL, NULL, NULL, datetime('2024-02-15 14:20:00'), datetime('2024-02-16 11:05:00'), 'Customer Portal', 'Web Portal Login', NULL, 'Priya Sharma', 'Service Desk Operations', NULL, NULL, NULL, NULL),
('INC_014', 'INC0000009', 'Monitor display flickering', 'USER_005', 'SVC_001', 'SVCOFF_001', 'CI_001', 'USER_003', 'GROUP_001', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'self-service', 'portal', 'new', 'hardware', 'Monitor screen flickers intermittently during use', 'Checking display cable connections and graphics driver', NULL, NULL, 'low', 'medium', 'moderate', NULL, NULL, NULL, datetime('2024-02-23 10:00:00'), datetime('2024-02-23 10:00:00'), 'Email Service', 'Outlook Email Access', 'Carlos Laptop', 'Carlos Rodriguez', 'Level 1 Support Team', NULL, NULL, NULL, NULL),
('INC_015', 'INC0000010', 'Application crash on startup', 'USER_001', 'SVC_002', 'SVCOFF_002', 'CI_002', 'USER_004', 'GROUP_002', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'phone', 'phone', 'in_progress', 'software', 'Customer portal application crashes immediately after launch', 'Reviewing application logs and error messages', NULL, NULL, 'high', 'high', 'high', NULL, NULL, NULL, datetime('2024-02-24 09:15:00'), datetime('2024-02-24 09:30:00'), 'Customer Portal', 'Web Portal Login', 'Aisha Desktop', 'Aisha Williams', 'Service Desk Operations', NULL, NULL, NULL, NULL),
('INC_016', 'INC0000011', 'WiFi connection drops frequently', 'USER_003', 'SVC_001', 'SVCOFF_001', 'CI_001', 'USER_006', 'GROUP_001', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'email', 'email', 'new', 'network', 'WiFi connection disconnects every few minutes', 'Testing wireless adapter and router signal strength', NULL, NULL, 'medium', 'medium', 'moderate', NULL, NULL, NULL, datetime('2024-02-25 11:20:00'), datetime('2024-02-25 11:20:00'), 'Email Service', 'Outlook Email Access', 'Carlos Laptop', 'Elena Petrov', 'Level 1 Support Team', NULL, NULL, NULL, NULL),
('INC_017', 'INC0000012', 'Keyboard keys not responding', 'USER_004', 'SVC_001', 'SVCOFF_001', 'CI_001', 'USER_003', 'GROUP_001', 'USER_003', NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'self-service', 'portal', 'resolved', 'hardware', 'Several keyboard keys stopped working', 'Keyboard replaced with new unit', 'New keyboard installed and tested successfully', 'Issue resolved', 'low', 'low', 'low', 'Solution Provided', NULL, datetime('2024-02-26 14:45:00'), datetime('2024-02-26 13:00:00'), datetime('2024-02-26 14:45:00'), 'Email Service', 'Outlook Email Access', 'Carlos Laptop', 'Carlos Rodriguez', 'Level 1 Support Team', NULL, NULL, NULL, NULL),
('INC_018', 'INC0000013', 'Slow database query performance', 'USER_002', 'SVC_002', 'SVCOFF_002', NULL, 'USER_002', 'GROUP_002', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_001', 'email', 'email', 'on_hold', 'database', 'Customer portal database queries taking too long', 'Waiting for DBA team to review query optimization', NULL, NULL, 'high', 'high', 'critical', NULL, 'Awaiting Problem', NULL, datetime('2024-02-27 08:30:00'), datetime('2024-02-27 09:00:00'), 'Customer Portal', 'Web Portal Login', NULL, 'Priya Sharma', 'Service Desk Operations', NULL, NULL, NULL, NULL);

-- Incidents - ORG_002
INSERT INTO incident (incident_id, number, short_description, caller_id, service, service_offering, configuration_item, assigned_to, assignment_group, resolved_by, problem, change_request, caused_by_change, incident_template, parent_incident, org_id, channel, contact_type, status, category, description, worknotes, resolution_notes, close_notes, impact, urgency, priority, resolution_code, on_hold_reason, resolved, created_at, updated_at, service_display, service_offering_display, configuration_item_display, assigned_to_display, assignment_group_display, parent_incident_display, problem_display, change_request_display, incident_template_display) VALUES
('INC_013', 'INC0000001', 'Unable to access email', 'USER_010', 'SVC_003', 'SVCOFF_003', 'CI_003', 'USER_009', 'GROUP_003', 'USER_009', NULL, NULL, NULL, 'TMPL_003', NULL, 'ORG_002', 'self-service', 'portal', 'closed', 'software', 'User cannot access corporate email', 'Email access restored after account reset', 'Account reset completed successfully', 'Issue resolved', 'low', 'low', 'low', 'Solution Provided', NULL, datetime('2024-02-18 16:00:00'), datetime('2024-02-18 10:30:00'), datetime('2024-02-18 16:00:00'), 'Acme Email Service', 'Acme Email Access', 'Kenji Workstation', 'Kenji Tanaka', 'IT Support Team', NULL, NULL, NULL, NULL),
('INC_009', 'INC0000002', 'Database performance issues', 'USER_008', 'SVC_004', 'SVCOFF_004', 'CI_004', 'USER_009', 'GROUP_004', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_002', 'email', 'email', 'in_progress', 'database', 'Slow query execution on development database', 'Performing query optimization and index analysis', NULL, NULL, 'medium', 'medium', 'moderate', NULL, NULL, NULL, datetime('2024-02-20 13:20:00'), datetime('2024-02-20 15:45:00'), 'Development Environment', 'Dev Server Access', 'Acme Email Server', 'Kenji Tanaka', 'Infrastructure Team', NULL, NULL, NULL, NULL),
('INC_010', 'INC0000003', 'Server maintenance request', 'USER_007', 'SVC_003', 'SVCOFF_003', 'CI_004', 'USER_008', 'GROUP_004', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_002', 'phone', 'phone', 'on_hold', 'hardware', 'Scheduled server maintenance for security patches', 'Maintenance scheduled for Friday night', NULL, NULL, 'medium', 'low', 'moderate', NULL, NULL, NULL, datetime('2024-02-21 09:30:00'), datetime('2024-02-21 10:15:00'), 'Acme Email Service', 'Acme Email Access', 'Acme Email Server', 'Sophie Mueller', 'Infrastructure Team', NULL, NULL, NULL, NULL),
('INC_011', 'INC0000004', 'VPN connection failure', 'USER_010', 'SVC_003', 'SVCOFF_003', 'CI_003', 'USER_009', 'GROUP_003', 'USER_009', NULL, NULL, NULL, NULL, NULL, 'ORG_002', 'self-service', 'portal', 'resolved', 'network', 'Cannot establish VPN connection from home office', 'VPN client reinstalled and configured', 'Connection working correctly after reconfiguration', 'Issue resolved', 'low', 'medium', 'moderate', 'Solution Provided', NULL, datetime('2024-02-22 12:00:00'), datetime('2024-02-22 09:25:00'), datetime('2024-02-22 12:00:00'), 'Acme Email Service', 'Acme Email Access', 'Kenji Workstation', 'Kenji Tanaka', 'IT Support Team', NULL, NULL, NULL, NULL),
('INC_012', 'INC0000005', 'Critical application crash', 'USER_008', 'SVC_004', 'SVCOFF_004', 'CI_004', 'USER_007', 'GROUP_004', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_002', 'phone', 'phone', 'in_progress', 'software', 'Production application repeatedly crashing with memory errors', 'Memory dump analysis in progress, temporary workaround deployed', NULL, NULL, 'high', 'high', 'critical', NULL, NULL, NULL, datetime('2024-02-19 14:50:00'), datetime('2024-02-19 14:55:00'), 'Development Environment', 'Dev Server Access', 'Acme Email Server', 'Raj Patel', 'Infrastructure Team', NULL, NULL, NULL, NULL),
('INC_019', 'INC0000006', 'Email attachment size limit issue', 'USER_010', 'SVC_003', 'SVCOFF_003', 'CI_003', 'USER_009', 'GROUP_003', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_002', 'self-service', 'portal', 'new', 'software', 'Unable to send email attachments larger than 10MB', 'Checking email server configuration and limits', NULL, NULL, 'low', 'low', 'low', NULL, NULL, NULL, datetime('2024-02-23 13:00:00'), datetime('2024-02-23 13:00:00'), 'Acme Email Service', 'Acme Email Access', 'Kenji Workstation', 'Kenji Tanaka', 'IT Support Team', NULL, NULL, NULL, NULL),
('INC_020', 'INC0000007', 'Development server access denied', 'USER_008', 'SVC_004', 'SVCOFF_004', 'CI_004', 'USER_009', 'GROUP_004', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_002', 'email', 'email', 'in_progress', 'software', 'Cannot access development server after recent changes', 'Reviewing access permissions and firewall rules', NULL, NULL, 'medium', 'medium', 'moderate', NULL, NULL, NULL, datetime('2024-02-24 10:30:00'), datetime('2024-02-24 11:00:00'), 'Development Environment', 'Dev Server Access', 'Acme Email Server', 'Kenji Tanaka', 'Infrastructure Team', NULL, NULL, NULL, NULL),
('INC_021', 'INC0000008', 'Backup job failure notification', 'USER_007', 'SVC_004', 'SVCOFF_004', 'CI_004', 'USER_008', 'GROUP_004', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_002', 'email', 'email', 'new', 'database', 'Automated backup job failed for development database', 'Investigating backup script and storage availability', NULL, NULL, 'medium', 'low', 'moderate', NULL, NULL, NULL, datetime('2024-02-25 08:00:00'), datetime('2024-02-25 08:00:00'), 'Development Environment', 'Dev Server Access', 'Acme Email Server', 'Sophie Mueller', 'Infrastructure Team', NULL, NULL, NULL, NULL),
('INC_022', 'INC0000009', 'Email sync issues on mobile device', 'USER_010', 'SVC_003', 'SVCOFF_003', 'CI_003', 'USER_009', 'GROUP_003', 'USER_009', NULL, NULL, NULL, NULL, NULL, 'ORG_002', 'phone', 'phone', 'resolved', 'software', 'Email not syncing properly on iPhone', 'Mobile device configuration updated', 'Email sync working correctly after reconfiguration', 'Issue resolved', 'low', 'medium', 'moderate', 'Solution Provided', NULL, datetime('2024-02-26 15:20:00'), datetime('2024-02-26 14:00:00'), datetime('2024-02-26 15:20:00'), 'Acme Email Service', 'Acme Email Access', 'Kenji Workstation', 'Kenji Tanaka', 'IT Support Team', NULL, NULL, NULL, NULL),
('INC_023', 'INC0000010', 'Server disk space warning', 'USER_008', 'SVC_004', 'SVCOFF_004', 'CI_004', 'USER_007', 'GROUP_004', NULL, NULL, NULL, NULL, NULL, NULL, 'ORG_002', 'email', 'email', 'on_hold', 'hardware', 'Development server disk space at 85% capacity', 'Planning disk cleanup and expansion', NULL, NULL, 'medium', 'low', 'moderate', NULL, 'Awaiting Change', NULL, datetime('2024-02-27 09:15:00'), datetime('2024-02-27 09:30:00'), 'Development Environment', 'Dev Server Access', 'Acme Email Server', 'Raj Patel', 'Infrastructure Team', NULL, NULL, NULL, NULL);

-- Problems - ORG_001
INSERT INTO problem (problem_id, number, problem_statement, service, service_offering, configuration_item, opened_by, status, category, short_description, impact, urgency, priority, assigned_to, assignment_group, worknotes, workaround, fix_notes, original_task, org_id, created_on, updated_on) VALUES
('PRB_001', 'PRB0000001', 'Multiple users experiencing periodic email service disruptions across different locations', 'SVC_001', 'SVCOFF_001', NULL, 'USER_002', 'root_cause', 'network', 'Intermittent email service outages', 'medium', 'medium', 'moderate', 'USER_002', 'GROUP_002', 'Network analysis shows packet loss during peak hours', 'Users advised to use webmail as temporary workaround', 'Investigating load balancer configuration', 'INC_001', 'ORG_001', datetime('2024-02-12 08:00:00'), datetime('2024-02-22 14:15:00'));

-- Problems - ORG_002
INSERT INTO problem (problem_id, number, problem_statement, service, service_offering, configuration_item, opened_by, status, category, short_description, impact, urgency, priority, assigned_to, assignment_group, worknotes, workaround, fix_notes, original_task, org_id, created_on, updated_on) VALUES
('PRB_002', 'PRB0000001', 'Email server performance degradation', 'SVC_003', 'SVCOFF_003', NULL, 'USER_007', 'fix_in_progress', 'software', 'Email server response times slower', 'medium', 'medium', 'moderate', 'USER_008', 'GROUP_004', 'Database query optimization in progress', 'Cache refresh suggested for immediate relief', 'Implementing database indexing improvements', 'INC_013', 'ORG_002', datetime('2024-02-16 13:20:00'), datetime('2024-02-21 10:45:00'));

-- Changes - ORG_001
INSERT INTO change (change_id, number, service, service_offering, configuration_item, requested_by, status, category, short_description, description, implementation_plan, testing_plan, cab_required, impact, priority, risk, assigned_to, assignment_group, close_code, close_notes, org_id, created_on, updated_on) VALUES
('CHG_001', 'CHG0000001', 'SVC_001', 'SVCOFF_001', NULL, 'USER_001', 'closed', 'system_software', 'Email server security patch', 'Apply critical security updates to email server infrastructure', 'Schedule maintenance window, apply patches, restart services', 'Verify email functionality, test user authentication', 1, 'medium', 'critical', 'high', 'USER_002', 'GROUP_002', 'successful', 'Patches applied successfully, all services operational', 'ORG_001', datetime('2024-02-05 09:00:00'), datetime('2024-02-08 18:00:00')),
('CHG_002', 'CHG0000002', 'SVC_002', 'SVCOFF_002', NULL, 'USER_002', 'implement', 'application_software', 'Customer portal upgrade', 'Upgrade customer portal to latest version for performance improvements', 'Deploy new version during maintenance window', 'Functional testing, performance benchmarking', 1, 'high', 'high', 'medium', 'USER_002', 'GROUP_002', NULL, NULL, 'ORG_001', datetime('2024-02-18 14:00:00'), datetime('2024-02-23 11:30:00'));

-- Changes - ORG_002
INSERT INTO change (change_id, number, service, service_offering, configuration_item, requested_by, status, category, short_description, description, implementation_plan, testing_plan, cab_required, impact, priority, risk, assigned_to, assignment_group, close_code, close_notes, org_id, created_on, updated_on) VALUES
('CHG_003', 'CHG0000001', 'SVC_003', 'SVCOFF_003', 'CI_004', 'USER_007', 'scheduled', 'hardware', 'Email server memory upgrade', 'Increase RAM on email server for better performance', 'Schedule downtime, install additional memory modules', 'System boot test, memory stress testing', 0, 'low', 'low', 'high', 'USER_008', 'GROUP_004', NULL, NULL, 'ORG_002', datetime('2024-02-25 16:00:00'), datetime('2024-02-25 16:00:00'));

-- Change Request Mappings
INSERT INTO change_request_mapping (change_request_mapping_id, change_id, incident_id, problem_id, org_id, created_at, updated_at) VALUES
-- ORG_001 mappings
('CRM_001', 'CHG_001', 'INC_001', NULL, 'ORG_001', datetime('2024-02-12 15:00:00'), datetime('2024-02-12 15:00:00')),
('CRM_002', 'CHG_002', 'INC_002', NULL, 'ORG_001', datetime('2024-02-18 16:30:00'), datetime('2024-02-18 16:30:00')),
('CRM_003', 'CHG_001', NULL, 'PRB_001', 'ORG_001', datetime('2024-02-13 10:00:00'), datetime('2024-02-13 10:00:00')),
-- ORG_002 mappings
('CRM_004', 'CHG_003', 'INC_013', NULL, 'ORG_002', datetime('2024-02-25 16:05:00'), datetime('2024-02-25 16:05:00')),
('CRM_005', 'CHG_003', NULL, 'PRB_002', 'ORG_002', datetime('2024-02-19 11:00:00'), datetime('2024-02-19 11:00:00'));

-- Incident SLAs
INSERT INTO incident_sla (incident_sla_id, incident_id, sla_def_id, stage, start_time, breach_time, has_breached, completed_time, org_id, created_on, updated_on) VALUES
-- ORG_001
('TSLA_001', 'INC_001', 'SLA_002', 'completed', datetime('2024-02-10 09:15:00'), datetime('2024-02-10 13:15:00'), 0, datetime('2024-02-10 10:45:00'), 'ORG_001', datetime('2024-02-10 09:15:00'), datetime('2024-02-10 10:45:00')),
('TSLA_002', 'INC_002', 'SLA_001', 'in_progress', datetime('2024-02-20 11:45:00'), datetime('2024-02-20 12:00:00'), 1, NULL, 'ORG_001', datetime('2024-02-20 11:45:00'), datetime('2024-02-20 16:22:00')),
('TSLA_004', 'INC_003', 'SLA_001', 'completed', datetime('2024-02-19 10:00:00'), datetime('2024-02-19 10:20:00'), 1, datetime('2024-02-19 10:25:00'), 'ORG_001', datetime('2024-02-19 10:00:00'), datetime('2024-02-19 10:25:00')),
('TSLA_005', 'INC_004', 'SLA_002', 'paused', datetime('2024-02-18 09:30:00'), datetime('2024-02-18 13:30:00'), 1, NULL, 'ORG_001', datetime('2024-02-18 09:30:00'), datetime('2024-02-18 13:30:00')),
('TSLA_006', 'INC_001', 'SLA_001', 'breached', datetime('2024-02-10 09:00:00'), datetime('2024-02-10 09:16:00'), 1, NULL, 'ORG_001', datetime('2024-02-10 09:00:00'), datetime('2024-02-10 09:16:00')),
-- ORG_002
('TSLA_003', 'INC_013', 'SLA_003', 'completed', datetime('2024-02-18 10:30:00'), datetime('2024-02-18 12:30:00'), 0, datetime('2024-02-18 11:15:00'), 'ORG_002', datetime('2024-02-18 10:30:00'), datetime('2024-02-18 11:15:00')),
('TSLA_007', 'INC_009', 'SLA_003', 'completed', datetime('2024-02-20 13:20:00'), datetime('2024-02-20 15:20:00'), 1, datetime('2024-02-20 15:30:00'), 'ORG_002', datetime('2024-02-20 13:20:00'), datetime('2024-02-20 15:30:00')),
('TSLA_008', 'INC_010', 'SLA_003', 'in_progress', datetime('2024-02-21 09:30:00'), datetime('2024-02-21 11:30:00'), 1, NULL, 'ORG_002', datetime('2024-02-21 09:30:00'), datetime('2024-02-21 11:30:00')),
('TSLA_009', 'INC_011', 'SLA_003', 'cancelled', datetime('2024-02-22 09:25:00'), datetime('2024-02-22 11:25:00'), 1, NULL, 'ORG_002', datetime('2024-02-22 09:25:00'), datetime('2024-02-22 11:25:00')),
('TSLA_010', 'INC_012', 'SLA_003', 'paused', datetime('2024-02-19 14:50:00'), NULL, 0, NULL, 'ORG_002', datetime('2024-02-19 14:50:00'), datetime('2024-02-19 14:50:00'));

-- Incident Affected CIs
INSERT INTO incident_affected_cis (incident_affected_cis_id, configuration_item, incident_id, org_id, created_on, updated_on) VALUES
-- ORG_001
('TASKCI_001', 'CI_001', 'INC_001', 'ORG_001', datetime('2024-02-10 09:20:00'), datetime('2024-02-10 09:20:00')),
('TASKCI_002', 'CI_002', 'INC_002', 'ORG_001', datetime('2024-02-20 11:50:00'), datetime('2024-02-20 11:50:00')),
-- ORG_002
('TASKCI_003', 'CI_003', 'INC_013', 'ORG_002', datetime('2024-02-18 10:35:00'), datetime('2024-02-18 10:35:00'));

-- Incident Knowledge Links (incident_knowledge) - ORG_001
INSERT INTO incident_knowledge (incident_kb_id, incident_id, knowledge_id, org_id, used_as, created_on, updated_on) VALUES
('IKB_001', 'INC_001', 'KB_001', 'ORG_001', 'resolution', datetime('2024-02-10 10:30:00'), datetime('2024-02-10 10:30:00')),
('IKB_002', 'INC_001', 'KB_002', 'ORG_001', 'suggested', datetime('2024-02-10 09:30:00'), datetime('2024-02-10 09:30:00')),
('IKB_003', 'INC_002', 'KB_003', 'ORG_001', 'applied', datetime('2024-02-20 13:00:00'), datetime('2024-02-20 13:00:00'));

-- Incident Knowledge Links (incident_knowledge) - ORG_002
INSERT INTO incident_knowledge (incident_kb_id, incident_id, knowledge_id, org_id, used_as, created_on, updated_on) VALUES
('IKB_004', 'INC_013', 'KB_004', 'ORG_002', 'resolution', datetime('2024-02-18 15:00:00'), datetime('2024-02-18 15:00:00')),
('IKB_005', 'INC_013', 'KB_005', 'ORG_002', 'suggested', datetime('2024-02-18 11:00:00'), datetime('2024-02-18 11:00:00'));

-- Notifications - ORG_001
INSERT INTO notification (notification_id, incident_id, org_id, email, subject, message, type, status, created_on, updated_on) VALUES
('NOTIF_001', 'INC_001', 'ORG_001', 'benjamin.chen@techcorp.com', 'Password Reset Complete', 'Your password has been reset successfully.', 'alert', 'delivered', datetime('2024-02-10 10:45:00'), datetime('2024-02-10 10:45:00')),
('NOTIF_002', 'INC_001', 'ORG_001', 'benjamin.chen@techcorp.com', 'Password Reset Confirmation', 'Please confirm receipt of your new password.', 'reminder', 'opened', datetime('2024-02-10 13:30:00'), datetime('2024-02-10 15:20:00')),
('NOTIF_003', 'INC_002', 'ORG_001', 'benjamin.chen@techcorp.com', 'Hardware Issue Update', 'Your desktop issue is currently being investigated by our technical team.', 'update', 'sent', datetime('2024-02-20 14:15:00'), datetime('2024-02-20 14:15:00')),
('NOTIF_004', 'INC_002', 'ORG_001', 'priya.sharma@techcorp.com', 'Critical Hardware Issue Alert', 'High priority hardware issue requires manager attention.', 'alert', 'delivered', datetime('2024-02-20 14:20:00'), datetime('2024-02-20 16:45:00'));

-- Notifications - ORG_002
INSERT INTO notification (notification_id, incident_id, org_id, email, subject, message, type, status, created_on, updated_on) VALUES
('NOTIF_005', 'INC_013', 'ORG_002', 'isabella.rossi@acme.com', 'Email Access Restored', 'Your email access has been successfully restored.', 'update', 'delivered', datetime('2024-02-18 15:30:00'), datetime('2024-02-18 16:45:00')),
('NOTIF_006', 'INC_013', 'ORG_002', 'isabella.rossi@acme.com', 'Email Issue Resolution', 'We have identified and fixed the root cause of your email access issue.', 'solution_proposal', 'sent', datetime('2024-02-18 16:00:00'), datetime('2024-02-18 16:00:00')),
('NOTIF_007', 'INC_013', 'ORG_002', 'sophie.mueller@acme.com', 'Customer Email Issue Resolution Report', 'Customer email issue has been resolved - details attached.', 'report', 'queued', datetime('2024-02-18 16:30:00'), datetime('2024-02-18 16:30:00'));

-- Child Incidents - ORG_001
-- INC_006 (Critical system outage) is parent to related email incidents
INSERT INTO child_incident (child_incident_mapping_id, parent_incident, child_incident, created_at, updated_at) VALUES
('CINC_001', 'INC_006', 'INC_001', datetime('2024-02-21 08:10:00'), datetime('2024-02-21 08:10:00')),
('CINC_002', 'INC_006', 'INC_004', datetime('2024-02-21 08:15:00'), datetime('2024-02-21 08:15:00')),
('CINC_003', 'INC_006', 'INC_007', datetime('2024-02-21 08:20:00'), datetime('2024-02-21 08:20:00'));

-- INC_002 (Desktop not booting) is parent to software installation request
INSERT INTO child_incident (child_incident_mapping_id, parent_incident, child_incident, created_at, updated_at) VALUES
('CINC_004', 'INC_002', 'INC_005', datetime('2024-02-20 12:00:00'), datetime('2024-02-20 12:00:00'));

-- Child Incidents - ORG_002
-- INC_012 (Critical application crash) is parent to related incidents
INSERT INTO child_incident (child_incident_mapping_id, parent_incident, child_incident, created_at, updated_at) VALUES
('CINC_005', 'INC_012', 'INC_009', datetime('2024-02-19 15:00:00'), datetime('2024-02-19 15:00:00')),
('CINC_006', 'INC_012', 'INC_010', datetime('2024-02-19 15:05:00'), datetime('2024-02-19 15:05:00'));

-- INC_013 (Unable to access email) is parent to VPN connection failure (related access issues)
INSERT INTO child_incident (child_incident_mapping_id, parent_incident, child_incident, created_at, updated_at) VALUES
('CINC_007', 'INC_013', 'INC_011', datetime('2024-02-18 11:00:00'), datetime('2024-02-18 11:00:00'));


-- ============================================
-- End of Seed Data
-- ============================================
