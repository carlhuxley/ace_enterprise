#!/usr/bin/env python3
"""Set up local audit database for development/testing.

Creates SQLite audit database and provides a local audit client
that writes directly to the database (bypassing HTTP for local dev).
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.audit.store import AuditStore


def setup_local_audit_db() -> str:
    """Create local SQLite audit database.

    Returns:
        Database URL for the local audit database
    """
    db_dir = project_root / ".local"
    db_dir.mkdir(exist_ok=True)

    db_path = db_dir / "audit.db"
    db_url = f"sqlite:///{db_path}"

    store = AuditStore(db_url)
    store.create_tables()

    stats = store.get_stats()
    print(f"Local audit DB: {db_path}")
    print(f"Total events: {stats['total_events']}")

    # Create .env.local if it doesn't exist
    env_file = project_root / ".env.local"
    env_content = f"""# Local development settings
AUDIT_DATABASE_URL={db_url}
AUDIT_DISABLED=false
"""

    if not env_file.exists():
        env_file.write_text(env_content)
        print(f"Created: {env_file}")
    else:
        print(f"Exists: {env_file}")

    return db_url


if __name__ == "__main__":
    setup_local_audit_db()
