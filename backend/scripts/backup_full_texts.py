"""Uploads Full Text PDFs to the off-platform S3 backup bucket (#65 leftovers).

Run from backend/: uv run python scripts/backup_full_texts.py --help
See asr_backend.backup_tasks for what it does.
"""

from asr_backend.backup_tasks import backup_full_texts_main

if __name__ == "__main__":
    raise SystemExit(backup_full_texts_main())
