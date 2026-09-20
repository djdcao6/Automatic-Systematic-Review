"""Removes an account and the projects it owns. Needs --yes to do it.

Run from backend/: uv run python scripts/delete_account.py --help
See asr_backend.operator_tasks for what it does.
"""

from asr_backend.operator_tasks import delete_account_main

if __name__ == "__main__":
    raise SystemExit(delete_account_main())
