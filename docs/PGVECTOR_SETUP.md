## PostgreSQL + pgvector Setup Guide

Complete guide for running ACE Enterprise with PostgreSQL and pgvector semantic search.

## Overview

This setup replaces JSON file storage with PostgreSQL and enables semantic pattern search using pgvector. This allows:

- **Fast similarity search** using vector indexing (IVFFlat)
- **Scalable storage** for large playbook databases
- **ACID transactions** for reliable updates
- **Multi-user access** for team collaboration
- **Semantic search** across extracted patterns

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Gherkin Extraction                                         │
│  ├─ Analyze code + tests                                    │
│  ├─ Extract scenarios                                       │
│  └─ Convert to knowledge patterns                           │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  PostgreSQL Repository                                      │
│  ├─ Store patterns as bullets                               │
│  ├─ Generate embeddings (sentence-transformers)             │
│  └─ Index with pgvector                                     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Semantic Search                                            │
│  ├─ Query by meaning (not keywords)                         │
│  ├─ Cosine similarity (pgvector <=> operator)               │
│  ├─ Filter by section/tags                                  │
│  └─ Cross-playbook domain search                            │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -e .

# Or manually:
pip install sqlalchemy psycopg2-binary pgvector sentence-transformers
```

### 2. Start PostgreSQL

Choose your preferred method: **Docker** or **Nix**

#### Option A: Docker (Containerized)

```bash
# Start PostgreSQL with pgvector
docker compose up -d postgres

# Or use docker-compose (older versions)
docker-compose up -d postgres

# Verify it's running
docker compose ps postgres
```

**Pros:** Isolated, doesn't affect system, easy cleanup
**Cons:** Requires Docker installed

#### Option B: Nix (Declarative)

```bash
# Enter Nix development environment
nix-shell

# Or with flakes (more modern):
nix develop

# Start PostgreSQL
start-postgres

# Check status
postgres-status
```

**Pros:** Reproducible, no Docker needed, declarative configuration
**Cons:** Requires Nix installed

**Nix Commands Available:**
- `start-postgres` - Start PostgreSQL server
- `stop-postgres` - Stop PostgreSQL server
- `restart-postgres` - Restart PostgreSQL server
- `postgres-status` - Check status and version
- `postgres-psql` - Connect to PostgreSQL shell

**Nix Setup Details:**
- PostgreSQL 16 with pgvector extension
- Data stored in `./.nix-postgres/data` (gitignored)
- Socket in `./.nix-postgres/sockets`
- Database: `ace_enterprise`
- User: `ace_user` / Password: `ace_password`
- Port: `5432`

#### Option C: Native PostgreSQL

If you have PostgreSQL already installed:

```bash
# Ensure pgvector extension is available
# On Ubuntu/Debian:
sudo apt install postgresql-16-pgvector

# On macOS with Homebrew:
brew install pgvector

# Create database
createdb ace_enterprise

# Enable extension
psql ace_enterprise -c "CREATE EXTENSION vector;"

# Set DATABASE_URL environment variable
export DATABASE_URL="postgresql://user:password@localhost:5432/ace_enterprise"
```

### 3. Run Database Migration

```bash
# Create tables and enable pgvector
python migrations/run_migration.py
```

Expected output:
```
INFO - Connecting to PostgreSQL...
INFO - Host: localhost:5432
INFO - Database: ace_enterprise
INFO - ✓ Connected to PostgreSQL
INFO - Found 1 migration(s)
INFO - Running migration: 001_enable_pgvector.sql
INFO - ✓ Migration 001_enable_pgvector.sql completed successfully
INFO -
✅ All migrations completed successfully!
```

### 4. Test the Setup

```bash
# Test PostgreSQL + pgvector integration
python demo_pgvector_test.py
```

Expected output:
```
================================================================================
PGVECTOR SETUP TEST
================================================================================

1. Testing database connection...
   ✓ Connected to PostgreSQL

2. Testing pgvector extension...
   ✓ pgvector enabled (version: 0.5.1)

3. Creating test playbook...
   ✓ Playbook created: test_pgvector

4. Testing embedding generation...
   ✓ Generated 384-dimensional embedding

5. Adding test bullets with embeddings...
   ✓ Added 3 bullets with embeddings

6. Testing pgvector similarity search...
   ✓ Found 3 similar bullets

   Query: "How does OAuth authentication work?"
   Results:
     [0.876] OAuth uses authorization code flow for third-party ac...
     [0.654] JWT tokens provide stateless authentication...
     [0.543] RBAC controls user permissions based on roles...

7. Repository statistics...
   Total playbooks: 1
   Total bullets: 3
   Bullets with embeddings: 3
   Embedding coverage: 100.0%

================================================================================
✅ PGVECTOR SETUP TEST PASSED
================================================================================
```

### 5. Extract and Store Patterns

```bash
# Extract Gherkin from code and store in PostgreSQL
python demo_gherkin_extraction_pgvector.py
```

This will:
1. Analyze existing code and tests
2. Extract Gherkin scenarios
3. Convert scenarios to knowledge patterns
4. Store patterns with semantic embeddings
5. Demonstrate semantic search

### 6. Explore Semantic Search

```bash
# Try advanced semantic search features
python demo_semantic_pattern_search.py
```

This demonstrates:
- Cross-domain pattern search
- Multiple distance metrics (cosine, L2, inner product)
- Section-specific filtering
- Multi-playbook domain search
- Pattern recommendations

## Database Schema

### Playbooks Table

```sql
CREATE TABLE playbooks (
    id SERIAL PRIMARY KEY,
    playbook_id VARCHAR(100) UNIQUE NOT NULL,
    version VARCHAR(20) NOT NULL,
    domain VARCHAR(100) NOT NULL,
    base_model VARCHAR(100) NOT NULL,
    total_tokens INTEGER DEFAULT 0,
    total_bullets INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Bullets Table (with pgvector)

```sql
CREATE TABLE bullets (
    id SERIAL PRIMARY KEY,
    bullet_id VARCHAR(50) UNIQUE NOT NULL,
    playbook_id INTEGER REFERENCES playbooks(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    section VARCHAR(100) NOT NULL,
    tags JSONB DEFAULT '[]'::jsonb,
    helpful_count INTEGER DEFAULT 0,
    harmful_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    embedding vector(384)  -- pgvector: 384 dimensions
);
```

### Vector Indexes

```sql
-- Cosine similarity (primary for semantic search)
CREATE INDEX idx_bullets_embedding_cosine ON bullets
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- L2 distance (Euclidean)
CREATE INDEX idx_bullets_embedding_l2 ON bullets
    USING ivfflat (embedding vector_l2_ops)
    WITH (lists = 100);

-- Inner product
CREATE INDEX idx_bullets_embedding_ip ON bullets
    USING ivfflat (embedding vector_ip_ops)
    WITH (lists = 100);
```

## API Usage

### Repository Operations

```python
from storage.repository import PlaybookRepository
from utils.embedding import get_embedding_service

# Initialize
repo = PlaybookRepository()
embedder = get_embedding_service()

# Create playbook
playbook = repo.create_playbook(
    playbook_id="my_playbook",
    version="1.0.0",
    domain="authentication",
    base_model="gpt-4"
)

# Add bullet (embedding generated automatically)
bullet = repo.add_bullet(
    playbook_id="my_playbook",
    bullet_id="pattern_001",
    content="OAuth uses authorization code flow",
    section="authentication/oauth",
    tags=["oauth", "security"]
)

# Bulk add bullets
bullets = [
    {
        "bullet_id": "pattern_002",
        "content": "JWT tokens provide stateless auth",
        "section": "authentication/jwt",
        "tags": ["jwt", "security"]
    },
    # ... more bullets
]
repo.bulk_add_bullets("my_playbook", bullets)
```

### Semantic Search

```python
# Search by meaning
query = "How to authenticate with OAuth?"
query_emb = embedder.embed_text(query)

results = repo.similarity_search(
    query_embedding=query_emb,
    playbook_id="my_playbook",
    top_k=10,
    similarity_threshold=0.5,
    distance_metric="cosine"
)

# Results: List[(BulletModel, similarity_score)]
for bullet, similarity in results:
    print(f"[{similarity:.3f}] {bullet.content}")
```

### Multi-Playbook Search

```python
# Search across all playbooks in a domain
results = repo.similarity_search_multi_playbook(
    query_embedding=query_emb,
    domain="authentication",
    top_k=10,
    similarity_threshold=0.5
)

# Results: List[(BulletModel, similarity_score, playbook_id)]
for bullet, similarity, playbook_id in results:
    print(f"[{similarity:.3f}] [{playbook_id}] {bullet.content}")
```

## Performance Tuning

### Vector Index Tuning

The IVFFlat index uses inverted lists to speed up searches:

```sql
-- Default: lists = 100 (good for < 100K rows)
-- Recommendation: sqrt(row_count) for larger datasets

-- For 1M rows:
CREATE INDEX idx_bullets_embedding_cosine ON bullets
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 1000);
```

### Search Performance

```python
# Faster: Use lower similarity threshold
results = repo.similarity_search(
    query_embedding=query_emb,
    similarity_threshold=0.7,  # Higher threshold = fewer results
    top_k=5  # Limit results
)

# Faster: Filter by section
results = repo.similarity_search(
    query_embedding=query_emb,
    section="authentication/oauth",  # Reduces search space
    top_k=10
)
```

### Connection Pooling

```python
# Repository uses connection pooling by default
repo = PlaybookRepository()

# Configure pool size (if needed)
from sqlalchemy import create_engine

engine = create_engine(
    database_url,
    pool_size=10,  # Max connections
    max_overflow=20,  # Extra connections
    pool_pre_ping=True  # Verify connections
)
```

## Troubleshooting

### PostgreSQL Not Starting

```bash
# Check logs
docker compose logs postgres

# Common issues:
# 1. Port 5432 already in use
docker compose down
lsof -i :5432
kill <PID>

# 2. Permission issues with volumes
docker compose down -v
docker compose up -d postgres
```

### pgvector Extension Not Found

```bash
# Verify image includes pgvector
docker compose exec postgres psql -U ace_user -d ace_enterprise -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"

# If empty, re-run migration
python migrations/run_migration.py
```

### Connection Errors

```python
# Check connection string in .env or config/settings.py
DATABASE_URL=postgresql+psycopg2://ace_user:ace_password@localhost:5432/ace_enterprise

# Test connection
python -c "from storage.repository import PlaybookRepository; repo = PlaybookRepository(); print('✓ Connected')"
```

### Slow Searches

```bash
# Check index usage
docker compose exec postgres psql -U ace_user -d ace_enterprise -c "
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE tablename = 'bullets';
"

# Rebuild indexes if needed
docker compose exec postgres psql -U ace_user -d ace_enterprise -c "
REINDEX INDEX idx_bullets_embedding_cosine;
"
```

## Migration from JSON Storage

If you have existing playbooks in JSON format:

```bash
# Create migration script (TODO)
python migrations/migrate_json_to_pg.py
```

This will:
1. Read JSON playbooks from `data/playbooks/`
2. Create playbook records in PostgreSQL
3. Store bullets with embeddings
4. Preserve all metadata

## Next Steps

1. **Extract more patterns**: Run Gherkin extraction on your codebases
2. **Build pattern library**: Accumulate patterns across projects
3. **Enable recommendations**: Use semantic search for code suggestions
4. **Cross-language migration**: Use patterns for Go generation
5. **Monitor performance**: Track search latency and accuracy

## Resources

- **pgvector**: https://github.com/pgvector/pgvector
- **sentence-transformers**: https://www.sbert.net/
- **SQLAlchemy**: https://docs.sqlalchemy.org/
- **PostgreSQL JSONB**: https://www.postgresql.org/docs/current/datatype-json.html

## Architecture Benefits

✅ **Semantic Search**: Find patterns by meaning, not keywords
✅ **Scalability**: Handle millions of patterns efficiently
✅ **ACID Transactions**: Reliable concurrent updates
✅ **Rich Queries**: Combine semantic + keyword + metadata filters
✅ **Cross-Project**: Share knowledge across teams
✅ **Versioning**: Track pattern evolution over time
✅ **Analytics**: Query pattern usage and effectiveness
