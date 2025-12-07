# Nix Setup for ACE Enterprise

Quick guide for using Nix to run PostgreSQL with pgvector.

## Prerequisites

Install Nix if you haven't already:
```bash
# Single-user installation
sh <(curl -L https://nixos.org/nix/install)

# Or multi-user (recommended for macOS):
sh <(curl -L https://nixos.org/nix/install) --daemon
```

## Quick Start

### Option 1: Using shell.nix (Classic Nix)

```bash
# Enter development environment (first time will install Python packages)
nix-shell

# The first time you enter the shell, it will:
# - Download/build Nix packages (PostgreSQL, Python, etc.)
# - Install Python packages (pgvector, sentence-transformers, etc.)
# This may take a few minutes on first run

# You'll see a welcome message with available commands
# Start PostgreSQL
start-postgres

# Run migrations
python migrations/run_migration.py

# Test the setup
python demo_pgvector_test.py
```

**Note:** The first `nix-shell` entry will install Python packages automatically. Subsequent entries will be instant.

### Option 2: Using flake.nix (Modern Nix Flakes)

```bash
# Enable flakes (if not already enabled)
mkdir -p ~/.config/nix
echo "experimental-features = nix-command flakes" >> ~/.config/nix/nix.conf

# Enter development environment
nix develop

# Start PostgreSQL
start-postgres

# Run migrations
python migrations/run_migration.py
```

## Available Commands

Once in the Nix shell, these commands are available:

| Command | Description |
|---------|-------------|
| `start-postgres` | Start PostgreSQL server with pgvector |
| `stop-postgres` | Stop PostgreSQL server |
| `restart-postgres` | Restart PostgreSQL server |
| `postgres-status` | Check PostgreSQL status and version |
| `postgres-psql` | Connect to PostgreSQL shell |

## Configuration

The Nix setup automatically:
- ✅ Installs PostgreSQL 16
- ✅ Enables pgvector extension
- ✅ Creates database: `ace_enterprise`
- ✅ Creates user: `ace_user` (password: `ace_password`)
- ✅ Stores data in `./.nix-postgres/data` (gitignored)
- ✅ Sets `DATABASE_URL` environment variable

## Database Details

- **Host:** localhost (Unix socket: `./.nix-postgres/sockets`)
- **Port:** 5432
- **Database:** ace_enterprise
- **User:** ace_user
- **Password:** ace_password
- **Connection URL:** `postgresql://ace_user:ace_password@localhost:5432/ace_enterprise`

## Workflow

```bash
# 1. Enter Nix environment
nix-shell  # or: nix develop

# 2. Start PostgreSQL
start-postgres

# 3. Run migrations (first time only)
python migrations/run_migration.py

# 4. Test setup
python demo_pgvector_test.py

# 5. Extract patterns and store in PostgreSQL
python demo_gherkin_extraction_pgvector.py

# 6. Try semantic search
python demo_semantic_pattern_search.py

# 7. When done, stop PostgreSQL
stop-postgres

# 8. Exit Nix shell
exit
```

## Troubleshooting

### PostgreSQL won't start

```bash
# Check if another instance is running
postgres-status

# Check logs
cat .nix-postgres/data/postgresql.log

# Clean slate (WARNING: deletes all data)
rm -rf .nix-postgres/
nix-shell  # Re-initialize
```

### Connection errors

```bash
# Verify DATABASE_URL is set
echo $DATABASE_URL

# Should output:
# postgresql://ace_user:ace_password@localhost:5432/ace_enterprise

# Test connection manually
postgres-psql
```

### pgvector extension not found

```bash
# Enter psql
postgres-psql

# Check if extension exists
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

# If empty, install it
CREATE EXTENSION vector;
```

## Differences from Docker Setup

| Feature | Docker | Nix |
|---------|--------|-----|
| Installation | Requires Docker | Requires Nix |
| Data Storage | Docker volume | `./.nix-postgres/` directory |
| Isolation | Container | Process |
| Resource Usage | Higher (VM overhead) | Lower (native) |
| Portability | Very portable | Portable (if Nix installed) |
| Setup Time | Slower (image pull) | Slower first time (build cache) |
| Reproducibility | High | Very High (pinned dependencies) |

## Advantages of Nix Setup

✅ **Reproducible**: Exact same environment on all machines
✅ **Declarative**: Configuration as code (`shell.nix`)
✅ **No Docker needed**: Lighter resource usage
✅ **Development friendly**: Helper commands built-in
✅ **Fast startup**: No container overhead
✅ **Pinned versions**: PostgreSQL 16 + pgvector guaranteed

## Python Virtual Environment

The Nix setup includes Python 3.12, but you may want a virtual environment:

```bash
# Inside nix-shell
python -m venv venv
source venv/bin/activate
pip install -e .
```

Or let Nix handle it:

```bash
# Already in the shell.nix configuration
# Just activate when entering
nix-shell --run "python -m venv venv && source venv/bin/activate"
```

## Cleanup

```bash
# Stop PostgreSQL
stop-postgres

# Remove Nix PostgreSQL data
rm -rf .nix-postgres/

# Remove Nix-installed Python packages
rm -rf .nix-python-packages/

# Remove Nix build cache (optional, aggressive - frees disk space)
nix-collect-garbage

# Deep clean (removes all unused Nix store items)
nix-collect-garbage -d
```

**Note:** The directories `.nix-postgres/` and `.nix-python-packages/` are gitignored, so they won't be committed to version control.

## Integration with CI/CD

You can use Nix in CI pipelines:

```yaml
# GitHub Actions example
- uses: cachix/install-nix-action@v22
  with:
    nix_path: nixpkgs=channel:nixos-unstable

- name: Run tests with Nix
  run: |
    nix-shell --run "start-postgres && python migrations/run_migration.py && pytest"
```

## Further Reading

- [Nix Manual](https://nixos.org/manual/nix/stable/)
- [Nix Pills](https://nixos.org/guides/nix-pills/) - Comprehensive Nix tutorial
- [NixOS Wiki - Development Environments](https://nixos.wiki/wiki/Development_environment_with_nix-shell)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
