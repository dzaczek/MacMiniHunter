-- Create read-only user for Metabase dashboard
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tracker_readonly') THEN
        CREATE ROLE tracker_readonly WITH LOGIN PASSWORD 'readonly_password';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE mac_tracker TO tracker_readonly;

-- Grants will be applied after tables are created by Alembic
-- We use an event trigger approach or simply re-run grants after migration
