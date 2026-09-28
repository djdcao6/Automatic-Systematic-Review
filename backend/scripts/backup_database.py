"""Dumps the database and uploads it to the off-platform S3 backup bucket (#65 leftovers).

Run from backend/: uv run python scripts/backup_database.py --help
See asr_backend.backup_tasks for what it does.
"""

from asr_backend.backup_tasks import backup_database_main

if __name__ == "__main__":
    raise SystemExit(backup_database_main())
