"""Sets a new random password for an account and prints it once.

Run from backend/: uv run python scripts/reset_password.py --help
See asr_backend.operator_tasks for what it does.
"""

from asr_backend.operator_tasks import reset_password_main

if __name__ == "__main__":
    raise SystemExit(reset_password_main())
