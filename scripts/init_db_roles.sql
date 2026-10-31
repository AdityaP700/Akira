\set ON_ERROR_STOP on

-- ==============================================================================
-- Least-Privilege PostgreSQL Roles Setup for Akira
-- ==============================================================================
-- Security rationale:
-- 1. Separation of DDL and DML: The application runtime role (app_rw) does NOT own
--    any tables or sequences. If an SQL injection vulnerability or runtime compromise
--    occurs, an attacker cannot DROP tables, ALTER schema, or alter DB-level permissions.
-- 2. Append-Only Enforced at Database Privilege Layer:
--    - Tables `ledger_entries`, `expense_shares`, and `provider_events` are STRICTLY
--      granted SELECT and INSERT only. No UPDATE or DELETE privilege is granted to app_rw.
--    - Table `notifications` is granted SELECT and INSERT, and UPDATE on (read_at) only.
--    - Table `user_pii` is granted SELECT, INSERT, UPDATE (no DELETE without owner).
--    - Tables `users`, `groups`, `group_members`, `expenses`, `settlements`, `idempotency_keys`
--      are granted SELECT, INSERT, UPDATE.
-- 3. Migration and schema administration are reserved strictly for `app_owner`.
--
-- ==============================================================================
-- Execution Instructions (Neon / Hosted Postgres / Local):
-- ==============================================================================
-- Connect with administrative privileges (e.g. 'neondb_owner' on Neon, or 'postgres' locally)
-- and pass your chosen passwords as psql variables:
--
--   psql "$ADMIN_DATABASE_URL" \
--     -v app_owner_password="<your_chosen_owner_password>" \
--     -v app_rw_password="<your_chosen_rw_password>" \
--     -f scripts/init_db_roles.sql
--
-- Note: Neither real nor dev passwords are stored in this script.
--
-- ==============================================================================

-- Create roles if they do not exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_owner') THEN
        CREATE ROLE app_owner WITH LOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_rw') THEN
        CREATE ROLE app_rw WITH LOGIN;
    END IF;
END $$;

-- Set user-chosen passwords from psql variables
ALTER ROLE app_owner WITH LOGIN PASSWORD :'app_owner_password';
ALTER ROLE app_rw WITH LOGIN PASSWORD :'app_rw_password';

-- Grant connection on the current connected database (e.g. 'akira' or Neon database)
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO app_owner, app_rw', current_database());
END $$;

-- Migration runner schema ownership
GRANT ALL ON SCHEMA public TO app_owner;
ALTER SCHEMA public OWNER TO app_owner;

-- Ensure future tables created by app_owner grant permissions to app_rw
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_rw;

-- Tables: General Read/Write tables
GRANT SELECT, INSERT, UPDATE ON TABLE users TO app_rw;
GRANT SELECT, INSERT, UPDATE ON TABLE user_pii TO app_rw;
GRANT SELECT, INSERT, UPDATE ON TABLE groups TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE group_members TO app_rw;
GRANT SELECT, INSERT, UPDATE ON TABLE expenses TO app_rw;
GRANT SELECT, INSERT, UPDATE ON TABLE settlements TO app_rw;
GRANT SELECT, INSERT, UPDATE ON TABLE idempotency_keys TO app_rw;

-- Tables: Append-only tables (STRICTLY NO UPDATE, NO DELETE for runtime app)
GRANT SELECT, INSERT ON TABLE ledger_entries TO app_rw;
GRANT SELECT, INSERT ON TABLE expense_shares TO app_rw;
GRANT SELECT, INSERT ON TABLE provider_events TO app_rw;

-- Table: Notifications (SELECT, INSERT, UPDATE on read_at only)
GRANT SELECT, INSERT ON TABLE notifications TO app_rw;
GRANT UPDATE (read_at) ON TABLE notifications TO app_rw;

-- Sequences usage for autoincrement primary keys
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_rw;
