# Nix development environment for ACE Enterprise
# Provides PostgreSQL 16 with pgvector extension
#
# Usage:
#   nix-shell                    # Enter development environment
#   nix-shell --run start-postgres  # Start PostgreSQL in background
#   nix-shell --run stop-postgres   # Stop PostgreSQL

{ pkgs ? import <nixpkgs> {} }:

let
  # Database configuration
  dbName = "ace_enterprise";
  dbUser = "ace_user";
  dbPassword = "ace_password";
  pgPort = "5432";

in pkgs.mkShell {
  name = "ace-enterprise-dev";

  buildInputs = with pkgs; [
    # PostgreSQL with pgvector extension
    (postgresql_16.withPackages (ps: [ ps.pgvector ]))

    # Python with packages
    python312
    python312Packages.pip
    python312Packages.virtualenv

    # Python dependencies for ACE Enterprise
    python312Packages.psycopg2
    python312Packages.sqlalchemy
    python312Packages.pydantic
    python312Packages.pyyaml
    python312Packages.httpx
    python312Packages.pytest
    python312Packages.pytest-asyncio

    # Development tools
    git
  ];

  shellHook = ''
    echo "🚀 ACE Enterprise Development Environment"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Set PostgreSQL paths (absolute)
    export PGDATA="$PWD/.nix-postgres/data"
    export PGHOST="$PWD/.nix-postgres/sockets"
    export PGPORT="${pgPort}"

    # Set up Python user packages directory
    export PYTHONUSERBASE="$PWD/.nix-python-packages"
    export PATH="$PYTHONUSERBASE/bin:$PATH"
    mkdir -p "$PYTHONUSERBASE"

    # Install Python packages if needed
    if [ ! -f "$PYTHONUSERBASE/.installed" ]; then
      echo "📦 Installing Python packages (first time only)..."
      pip install --user --quiet pgvector sentence-transformers python-dotenv pydantic-settings 2>/dev/null || true
      touch "$PYTHONUSERBASE/.installed"
      echo "✓ Python packages installed to $PYTHONUSERBASE"
    fi

    # Create postgres directories if they don't exist
    mkdir -p "$PGDATA" "$PGHOST"

    # Set DATABASE_URL
    export DATABASE_URL="postgresql://${dbUser}:${dbPassword}@localhost:${pgPort}/${dbName}"

    # Initialize PostgreSQL if not already done
    if [ ! -d "$PGDATA/base" ]; then
      echo "📦 Initializing PostgreSQL database..."

      # Clean up and recreate data directory (initdb needs a fresh directory)
      if [ -d "$PGDATA" ]; then
        rm -rf "$PGDATA"
      fi
      mkdir -p "$PGDATA"

      # Create password file OUTSIDE data directory (initdb needs empty dir)
      PWFILE="/tmp/.nix-pg-init-$$"
      echo "${dbPassword}" > "$PWFILE"
      chmod 600 "$PWFILE"

      # Initialize database (use C locale - always available in Nix)
      if initdb --encoding=UTF8 --locale=C --auth=md5 --pwfile="$PWFILE"; then
        echo "✓ Database cluster initialized"
        rm "$PWFILE"
      else
        echo "✗ Failed to initialize database"
        rm -f "$PWFILE"
        return 1
      fi

      # Configure PostgreSQL
      cat >> "$PGDATA/postgresql.conf" <<EOF
unix_socket_directories = '$PGHOST'
port = $PGPORT
listen_addresses = 'localhost'
max_connections = 100
shared_buffers = 128MB
EOF

      # Configure authentication
      cat >> "$PGDATA/pg_hba.conf" <<EOF
# Allow local connections with password
local   all   all   md5
host    all   all   127.0.0.1/32   md5
host    all   all   ::1/128        md5
EOF

      echo "✓ PostgreSQL initialized"
    fi

    # Helper functions
    start-postgres() {
      if pg_isready >/dev/null 2>&1; then
        echo "✓ PostgreSQL is already running"
      else
        echo "🚀 Starting PostgreSQL..."
        pg_ctl -l "$PGDATA/postgresql.log" start
        sleep 2

        # Create database and user if first run
        if ! psql -U $USER -lqt | cut -d \| -f 1 | grep -qw ${dbName}; then
          echo "📦 Creating database and user..."
          createdb ${dbName}
          psql -d ${dbName} -c "CREATE USER ${dbUser} WITH PASSWORD '${dbPassword}';"
          psql -d ${dbName} -c "GRANT ALL PRIVILEGES ON DATABASE ${dbName} TO ${dbUser};"
          psql -d ${dbName} -c "CREATE EXTENSION IF NOT EXISTS vector;"
          echo "✓ Database setup complete"
        fi

        echo "✓ PostgreSQL started on port $PGPORT"
        echo "  Connection: postgresql://${dbUser}:${dbPassword}@localhost:$PGPORT/${dbName}"
      fi
    }

    stop-postgres() {
      if pg_isready >/dev/null 2>&1; then
        echo "🛑 Stopping PostgreSQL..."
        pg_ctl stop
        echo "✓ PostgreSQL stopped"
      else
        echo "PostgreSQL is not running"
      fi
    }

    restart-postgres() {
      stop-postgres
      sleep 1
      start-postgres
    }

    postgres-status() {
      if pg_isready >/dev/null 2>&1; then
        echo "✓ PostgreSQL is running on port $PGPORT"
        psql -U $USER -d ${dbName} -c "SELECT version();"
        psql -U $USER -d ${dbName} -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
      else
        echo "✗ PostgreSQL is not running"
      fi
    }

    postgres-psql() {
      psql -U ${dbUser} -d ${dbName}
    }

    # Export helper functions
    export -f start-postgres
    export -f stop-postgres
    export -f restart-postgres
    export -f postgres-status
    export -f postgres-psql

    echo ""
    echo "📚 Available commands:"
    echo "  start-postgres     - Start PostgreSQL server"
    echo "  stop-postgres      - Stop PostgreSQL server"
    echo "  restart-postgres   - Restart PostgreSQL server"
    echo "  postgres-status    - Check PostgreSQL status"
    echo "  postgres-psql      - Connect to PostgreSQL shell"
    echo ""
    echo "🔗 Database URL: $DATABASE_URL"
    echo ""
    echo "To get started:"
    echo "  1. start-postgres"
    echo "  2. python migrations/run_migration.py"
    echo "  3. python demo_pgvector_test.py"
    echo ""
  '';

  # Prevent impure environment variables
  NIX_ENFORCE_PURITY = 0;
}
