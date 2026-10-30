-- Least-privilege PostgreSQL roles configuration for Akira
--
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

-- Create roles if not existing
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_owner') THEN
        CREATE ROLE app_owner WITH LOGIN PASSWORD 'app_owner_dev_pass';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_rw') THEN
        CREATE ROLE app_rw WITH LOGIN PASSWORD 'app_rw_dev_pass';
    END IF;
END $$;

-- Grant database connection
GRANT CONNECT ON DATABASE akira TO app_owner;
GRANT CONNECT ON DATABASE akira TO app_rw;

-- Migration runner ownership
GRANT ALL ON SCHEMA public TO app_owner;
ALTER SCHEMA public OWNER TO app_owner;

-- Ensure future tables created by app_owner give default permissions to app_rw
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
