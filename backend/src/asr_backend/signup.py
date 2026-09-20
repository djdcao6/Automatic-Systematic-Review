"""Who may sign up during the closed pilot (#60).

SIGNUP_ALLOWLIST is a comma-separated list of emails, matched case-insensitively.
Empty means nobody can register. A lone `*` means anyone can, for local
development and the tests; it is not for the pilot.
"""

from asr_backend import models
from asr_backend.settings import settings

OPEN_SIGNUP = "*"


def _entries() -> set[str]:
    return {
        entry.strip().lower() for entry in settings.signup_allowlist.split(",") if entry.strip()
    }


def is_allowlisted(email: str) -> bool:
    entries = _entries()
    return OPEN_SIGNUP in entries or email.strip().lower() in entries


def can_create_review_projects(reviewer: models.Reviewer) -> bool:
    """False for an invitation-only account whose email is not on the allowlist.

    Checked live rather than stored, so adding the email to the allowlist lifts
    the restriction at once, with no change to the account.
    """
    return not reviewer.invited_only or is_allowlisted(reviewer.email)
