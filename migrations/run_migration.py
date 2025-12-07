"""
Database Migration Runner

Runs SQL migrations to set up PostgreSQL with pgvector.
"""

import sys
from pathlib import Path
import logging

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_migration(migration_file: Path, conn):
    """Run a SQL migration file."""
    logger.info(f"Running migration: {migration_file.name}")

    with open(migration_file, 'r') as f:
        sql = f.read()

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        conn.commit()
        logger.info(f"✓ Migration {migration_file.name} completed successfully")
    except Exception as e:
        conn.rollback()
        logger.error(f"✗ Migration {migration_file.name} failed: {e}")
        raise
    finally:
        cursor.close()


def main():
    """Run all pending migrations."""

    # Database connection parameters (from docker-compose.yml)
    db_params = {
        'host': 'localhost',
        'port': 5432,
        'database': 'ace_enterprise',
        'user': 'ace_user',
        'password': 'ace_password'
    }

    logger.info("Connecting to PostgreSQL...")
    logger.info(f"Host: {db_params['host']}:{db_params['port']}")
    logger.info(f"Database: {db_params['database']}")

    conn = None
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(**db_params)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        logger.info("✓ Connected to PostgreSQL")

        # Get migration files
        migrations_dir = Path(__file__).parent
        migration_files = sorted(migrations_dir.glob('*.sql'))

        if not migration_files:
            logger.warning("No migration files found")
            return

        logger.info(f"Found {len(migration_files)} migration(s)")

        # Run each migration
        for migration_file in migration_files:
            run_migration(migration_file, conn)

        logger.info("\n✅ All migrations completed successfully!")
        logger.info("\nNext steps:")
        logger.info("1. Test setup: python demo_pgvector_test.py")
        logger.info("2. Extract patterns: python demo_gherkin_extraction_pgvector.py")

    except psycopg2.Error as e:
        logger.error(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed")


if __name__ == "__main__":
    main()
