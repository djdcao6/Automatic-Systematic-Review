"""Removes a project: its rows and its PDFs. Needs --yes to do it.

Run from backend/: uv run python scripts/delete_project.py --help
See asr_backend.operator_tasks for what it does.
"""

from asr_backend.operator_tasks import delete_project_main

if __name__ == "__main__":
    raise SystemExit(delete_project_main())
