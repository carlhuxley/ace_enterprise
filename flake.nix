{
  description = "ACE Enterprise - Institutional Knowledge Development Middleware";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Database configuration
        dbName = "ace_enterprise";
        dbUser = "ace_user";
        dbPassword = "ace_password";
        pgPort = "5432";

      in {
        devShells.default = pkgs.mkShell {
          name = "ace-enterprise-dev";

          buildInputs = with pkgs; [
            # PostgreSQL 16 with pgvector extension
            (postgresql_16.withPackages (ps: [ ps.pgvector ]))

            # Python 3.12 with common packages
            python312
            python312Packages.pip
            python312Packages.virtualenv
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
            echo "🚀 ACE Enterprise Development Environment (Nix Flakes)"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

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
              echo "✓ Python packages installed"
            fi

            # Create postgres directories
            mkdir -p "$PGDATA" "$PGHOST"

            # Set DATABASE_URL
            export DATABASE_URL="postgresql://${dbUser}:${dbPassword}@localhost:${pgPort}/${dbName}"

            # Initialize PostgreSQL if needed
            if [ ! -d "$PGDATA/base" ]; then
              echo "📦 Initializing PostgreSQL..."

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

              cat >> "$PGDATA/postgresql.conf" <<EOF
unix_socket_directories = '$PGHOST'
port = $PGPORT
listen_addresses = 'localhost'
max_connections = 100
shared_buffers = 128MB
EOF

              cat >> "$PGDATA/pg_hba.conf" <<EOF
local   all   all   md5
host    all   all   127.0.0.1/32   md5
host    all   all   ::1/128        md5
EOF
              echo "✓ PostgreSQL initialized"
            fi

            # Helper functions
            start-postgres() {
              if pg_isready >/dev/null 2>&1; then
                echo "✓ PostgreSQL already running"
              else
                echo "🚀 Starting PostgreSQL..."
                pg_ctl -l "$PGDATA/postgresql.log" start
                sleep 2

                if ! psql -U $USER -lqt | cut -d \| -f 1 | grep -qw ${dbName}; then
                  createdb ${dbName}
                  psql -d ${dbName} -c "CREATE USER ${dbUser} WITH PASSWORD '${dbPassword}';"
                  psql -d ${dbName} -c "GRANT ALL PRIVILEGES ON DATABASE ${dbName} TO ${dbUser};"
                  psql -d ${dbName} -c "CREATE EXTENSION IF NOT EXISTS vector;"
                fi
                echo "✓ PostgreSQL started on port $PGPORT"
              fi
            }

            stop-postgres() {
              if pg_isready >/dev/null 2>&1; then
                pg_ctl stop
                echo "✓ PostgreSQL stopped"
              fi
            }

            export -f start-postgres
            export -f stop-postgres

            echo ""
            echo "📚 Commands: start-postgres, stop-postgres"
            echo "🔗 Database: $DATABASE_URL"
            echo ""
          '';
        };

        # Default package (could build the application)
        packages.default = pkgs.python312Packages.buildPythonApplication {
          pname = "ace-enterprise";
          version = "0.1.0";
          src = ./.;

          propagatedBuildInputs = with pkgs.python312Packages; [
            pydantic
            pyyaml
            httpx
            sqlalchemy
            psycopg2
          ];

          meta = with pkgs.lib; {
            description = "Institutional Knowledge Development Middleware";
            license = licenses.asl20;
          };
        };
      }
    );
}
