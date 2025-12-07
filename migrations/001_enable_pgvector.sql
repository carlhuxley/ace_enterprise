-- Migration 001: Enable pgvector and create ACE Enterprise schema
-- Date: 2025-12-06
-- Purpose: Full PostgreSQL setup with pgvector for semantic search

-- Enable pgvector extension
-- CREATE EXTENSION IF NOT EXISTS vector;

-- Create playbooks table
CREATE TABLE IF NOT EXISTS playbooks (
    id SERIAL PRIMARY KEY,
    playbook_id VARCHAR(100) UNIQUE NOT NULL,
    version VARCHAR(20) NOT NULL,
    domain VARCHAR(100) NOT NULL,
    base_model VARCHAR(100) NOT NULL,
    total_tokens INTEGER DEFAULT 0,
    total_bullets INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create bullets table with vector embeddings
CREATE TABLE IF NOT EXISTS bullets (
    id SERIAL PRIMARY KEY,
    bullet_id VARCHAR(50) UNIQUE NOT NULL,
    playbook_id INTEGER REFERENCES playbooks(id) ON DELETE CASCADE NOT NULL,
    content TEXT NOT NULL,
    section VARCHAR(100) NOT NULL,
    tags JSONB DEFAULT '[]'::jsonb,
    helpful_count INTEGER DEFAULT 0,
    harmful_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_used TIMESTAMP,
    embedding vector(384)  -- pgvector: 384 dimensions for sentence-transformers
);

-- Create indexes for fast querying
CREATE INDEX IF NOT EXISTS idx_playbooks_playbook_id ON playbooks(playbook_id);
CREATE INDEX IF NOT EXISTS idx_playbooks_domain ON playbooks(domain);
CREATE INDEX IF NOT EXISTS idx_playbooks_domain_version ON playbooks(domain, version);

CREATE INDEX IF NOT EXISTS idx_bullets_bullet_id ON bullets(bullet_id);
CREATE INDEX IF NOT EXISTS idx_bullets_playbook_id ON bullets(playbook_id);
CREATE INDEX IF NOT EXISTS idx_bullets_section ON bullets(section);
CREATE INDEX IF NOT EXISTS idx_bullets_playbook_section ON bullets(playbook_id, section);
CREATE INDEX IF NOT EXISTS idx_bullets_helpful_count ON bullets(helpful_count);

-- Create pgvector indexes for fast similarity search
-- IVFFlat: Inverted File with Flat quantizer (good for < 1M vectors)
-- lists = 100: Number of inverted lists (tune: sqrt(row_count) for datasets > 10K)
CREATE INDEX IF NOT EXISTS idx_bullets_embedding_cosine ON bullets
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_bullets_embedding_l2 ON bullets
    USING ivfflat (embedding vector_l2_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_bullets_embedding_ip ON bullets
    USING ivfflat (embedding vector_ip_ops)
    WITH (lists = 100);

-- Create checkpoints table
CREATE TABLE IF NOT EXISTS checkpoints (
    id SERIAL PRIMARY KEY,
    checkpoint_id VARCHAR(50) UNIQUE NOT NULL,
    playbook_id INTEGER REFERENCES playbooks(id) ON DELETE CASCADE NOT NULL,
    version VARCHAR(20) NOT NULL,
    snapshot JSONB NOT NULL,
    performance_metrics JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_playbook_id ON checkpoints(playbook_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON checkpoints(created_at);

-- Create experiment logs table
CREATE TABLE IF NOT EXISTS experiment_logs (
    id SERIAL PRIMARY KEY,
    experiment_id VARCHAR(50) UNIQUE NOT NULL,
    playbook_id INTEGER REFERENCES playbooks(id) ON DELETE SET NULL,
    task_input TEXT NOT NULL,
    task_output TEXT,
    playbook_snapshot JSONB,
    execution_time_ms INTEGER,
    success BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_experiment_logs_playbook_id ON experiment_logs(playbook_id);
CREATE INDEX IF NOT EXISTS idx_experiment_logs_created_at ON experiment_logs(created_at);

-- Add helpful comments
-- COMMENT ON EXTENSION vector IS 'pgvector extension for vector similarity search';
COMMENT ON TABLE playbooks IS 'ACE playbooks - versioned knowledge bases';
COMMENT ON TABLE bullets IS 'Knowledge bullets with vector embeddings';
COMMENT ON COLUMN bullets.embedding IS 'Sentence embedding (384 dims from all-MiniLM-L6-v2)';
COMMENT ON INDEX idx_bullets_embedding_cosine IS 'IVFFlat index for cosine similarity (primary for semantic search)';
COMMENT ON INDEX idx_bullets_embedding_l2 IS 'IVFFlat index for L2 distance';
COMMENT ON INDEX idx_bullets_embedding_ip IS 'IVFFlat index for inner product';

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for playbooks
CREATE TRIGGER update_playbooks_updated_at
    BEFORE UPDATE ON playbooks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Verify setup
DO $$
DECLARE
    vector_version TEXT;
BEGIN
    -- Check pgvector extension
    SELECT extversion INTO vector_version
    FROM pg_extension
    WHERE extname = 'vector';

    IF vector_version IS NULL THEN
        RAISE EXCEPTION 'pgvector extension not installed';
    END IF;

    RAISE NOTICE 'Migration 001 completed successfully';
    RAISE NOTICE 'pgvector version: %', vector_version;
    RAISE NOTICE 'Tables created: playbooks, bullets, checkpoints, experiment_logs';
    RAISE NOTICE 'Vector indexes created for cosine, L2, and inner product similarity';
END $$;
