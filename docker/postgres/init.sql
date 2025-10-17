-- Initialize ACE Enterprise Database

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create enum types
DO $$ BEGIN
    CREATE TYPE adaptation_mode AS ENUM ('offline', 'online', 'hybrid');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE task_outcome AS ENUM ('success', 'failure', 'timeout', 'error');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE checkpoint_trigger AS ENUM ('scheduled', 'performance_peak', 'manual', 'pre_deployment', 'pre_risky_update');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ace_enterprise TO ace_user;

-- Set timezone
SET timezone = 'UTC';

-- Create indexes for common queries (will be managed by Alembic migrations)
-- This is just for initial setup

COMMENT ON DATABASE ace_enterprise IS 'ACE Enterprise - Agentic Context Engineering Production System';
