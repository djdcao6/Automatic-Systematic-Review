"""Operator tasks, run by hand for the closed pilot (#62).

There is no email sending and no delete route, so the operator resets a password or
removes a project or an account on request, and the pilot terms say so. The scripts in
backend/scripts are thin wrappers around the `*_main` functions here, so the tests
exercise the same code the operator runs.

Deleting an account
-------------------
* Projects the account OWNS are deleted whole: rows, and the PDFs under
  `full_text_storage_path`. A Co-Reviewer in such a project loses it, and their work in it.
* Projects where the account is the CO-REVIEWER are kept. The account is detached the way
  an Owner's "remove Co-Reviewer" does it (#29): the Owner sees the project as waiting for
  a replacement and can invite one. The Owner's flow diagram, Conflicts and CSV export are
  not changed by someone leaving.
* If anything of the account's is left in other people's projects (its Screening
  Decisions, its side of a Conflict, the former-Co-Reviewer mark), the account row is
  ANONYMIZED instead of deleted: the email becomes unusable and the password is replaced
  with one nobody knows. The person's identity goes; their decisions, including any
  free-text reasons, stay with the Owner's review.
* Otherwise the account row is deleted.
"""

import argparse
import secrets
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from asr_backend import crud, models
from asr_backend.auth import hash_password
from asr_backend.db import SessionLocal
from asr_backend.settings import settings

# `.invalid` is reserved and never delivers, and sign-up refuses it, so no one can register
# an address like this and take over an anonymized account's name.
ANONYMIZED_EMAIL_DOMAIN = "deleted.invalid"
NEW_PASSWORD_BYTES = 12


class OperatorError(Exception):
    """A request the operator can fix and retry: unknown email, unknown project id."""


@dataclass
class ProjectReport:
    id: uuid.UUID
    name: str
    owner_email: str
    co_reviewer_email: str | None
    citations: int
    screening_decisions: int
    conflicts: int
    # PDFs under the storage path that are (or would be) deleted.
    pdf_files: list[Path] = field(default_factory=list)
    # PDFs the database lists but that are not on disk.
    pdfs_missing: list[str] = field(default_factory=list)
    # PDFs the database lists at a path outside the storage path: never touched.
    pdfs_outside_storage: list[str] = field(default_factory=list)
    # PDFs that could not be deleted after the rows were gone.
    pdfs_failed: list[str] = field(default_factory=list)


@dataclass
class DetachedProject:
    id: uuid.UUID
    name: str
    owner_email: str
    screening_decisions_kept: int


@dataclass
class AccountReport:
    email: str
    owned: list[ProjectReport] = field(default_factory=list)
    detached: list[DetachedProject] = field(default_factory=list)
    # "deleted" or "anonymized".
    outcome: str = "deleted"
    # What still points at the account in other people's projects, when it is anonymized.
    kept_screening_decisions: int = 0
    kept_conflicts: int = 0
    kept_projects: int = 0
    # Stripe is not touched; the operator cancels the subscription there.
    stripe_subscription_id: str | None = None


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _count(db: Session, statement) -> int:
    return db.scalar(statement) or 0


def _get_reviewer(db: Session, email: str) -> models.Reviewer:
    reviewer = crud.get_reviewer_by_email(db, _normalize_email(email))
    if reviewer is None:
        raise OperatorError(f"No account with the email {email}.")
    return reviewer


def _email_of(db: Session, reviewer_id: uuid.UUID | None) -> str | None:
    if reviewer_id is None:
        return None
    reviewer = db.get(models.Reviewer, reviewer_id)
    return reviewer.email if reviewer else None


def reset_password(db: Session, email: str) -> str:
    """Sets a new random password and returns it; it is not kept anywhere else."""
    reviewer = _get_reviewer(db, email)
    password = secrets.token_urlsafe(NEW_PASSWORD_BYTES)
    reviewer.hashed_password = hash_password(password)
    db.commit()
    return password


def _remove_project(db: Session, project: models.ReviewProject, root: Path) -> ProjectReport:
    """Deletes a project's rows in the open transaction and reports what went, PDFs included.

    The rows go through the relationship cascades, so a table added under a project later is
    covered without touching this. The files are only listed here: they are deleted after
    the commit, so a failed commit never leaves rows pointing at PDFs that are gone.
    """
    citation_ids = select(models.Citation.id).where(
        models.Citation.review_project_id == project.id
    )
    report = ProjectReport(
        id=project.id,
        name=project.name,
        owner_email=_email_of(db, project.owner_reviewer_id) or "unknown",
        co_reviewer_email=_email_of(db, project.co_reviewer_id),
        citations=_count(
            db,
            select(func.count())
            .select_from(models.Citation)
            .where(models.Citation.review_project_id == project.id),
        ),
        screening_decisions=_count(
            db,
            select(func.count())
            .select_from(models.ScreeningDecision)
            .where(models.ScreeningDecision.citation_id.in_(citation_ids)),
        ),
        conflicts=_count(
            db,
            select(func.count())
            .select_from(models.Conflict)
            .where(models.Conflict.review_project_id == project.id),
        ),
    )

    resolved_root = root.resolve()
    for file_path in db.scalars(
        select(models.FullText.file_path).where(models.FullText.citation_id.in_(citation_ids))
    ):
        path = Path(file_path).resolve()
        if not path.is_relative_to(resolved_root):
            report.pdfs_outside_storage.append(file_path)
        elif not path.is_file():
            report.pdfs_missing.append(file_path)
        else:
            report.pdf_files.append(path)

    # The one link no relationship covers: a Citation merged into another (ADR 0005).
    db.execute(
        update(models.Citation)
        .where(models.Citation.review_project_id == project.id)
        .values(merged_into_citation_id=None)
    )
    db.delete(project)
    db.flush()
    return report


def _finish(db: Session, dry_run: bool, reports: Sequence[ProjectReport]) -> None:
    """Commits and then deletes the PDFs, or rolls everything back on a dry run."""
    if dry_run:
        db.rollback()
        return
    db.commit()
    for report in reports:
        for path in report.pdf_files:
            try:
                path.unlink()
            except OSError:
                report.pdfs_failed.append(str(path))


def delete_project(db: Session, project_id: uuid.UUID, *, dry_run: bool) -> ProjectReport:
    project = crud.get_review_project(db, project_id)
    if project is None:
        raise OperatorError(f"No project with the id {project_id}.")
    report = _remove_project(db, project, Path(settings.full_text_storage_path))
    _finish(db, dry_run, [report])
    return report


def _references_left(db: Session, reviewer_id: uuid.UUID) -> tuple[int, int, int]:
    """(Screening Decisions, Conflicts, projects) in other people's work that name the account."""
    decisions = _count(
        db,
        select(func.count())
        .select_from(models.ScreeningDecision)
        .where(models.ScreeningDecision.reviewer_id == reviewer_id),
    )
    conflicts = _count(
        db,
        select(func.count())
        .select_from(models.Conflict)
        .where(
            (models.Conflict.owner_reviewer_id == reviewer_id)
            | (models.Conflict.co_reviewer_id == reviewer_id)
        ),
    )
    projects = _count(
        db,
        select(func.count())
        .select_from(models.ReviewProject)
        .where(
            (models.ReviewProject.co_reviewer_id == reviewer_id)
            | (models.ReviewProject.former_co_reviewer_id == reviewer_id)
        ),
    )
    return decisions, conflicts, projects


def delete_account(db: Session, email: str, *, dry_run: bool) -> AccountReport:
    reviewer = _get_reviewer(db, email)
    report = AccountReport(email=reviewer.email)
    root = Path(settings.full_text_storage_path)

    owned = db.scalars(
        select(models.ReviewProject)
        .where(models.ReviewProject.owner_reviewer_id == reviewer.id)
        .order_by(models.ReviewProject.created_at)
    ).all()
    for project in owned:
        report.owned.append(_remove_project(db, project, root))

    co_reviewing = db.scalars(
        select(models.ReviewProject)
        .where(models.ReviewProject.co_reviewer_id == reviewer.id)
        .order_by(models.ReviewProject.created_at)
    ).all()
    for project in co_reviewing:
        # What crud.remove_co_reviewer does (#29), inside this one transaction.
        project.former_co_reviewer_id = reviewer.id
        project.co_reviewer_id = None
        report.detached.append(
            DetachedProject(
                id=project.id,
                name=project.name,
                owner_email=_email_of(db, project.owner_reviewer_id) or "unknown",
                screening_decisions_kept=_count(
                    db,
                    select(func.count())
                    .select_from(models.ScreeningDecision)
                    .join(models.Citation)
                    .where(
                        models.Citation.review_project_id == project.id,
                        models.ScreeningDecision.reviewer_id == reviewer.id,
                    ),
                ),
            )
        )

    subscription = db.scalar(
        select(models.Subscription).where(models.Subscription.reviewer_id == reviewer.id)
    )
    if subscription is not None:
        report.stripe_subscription_id = subscription.stripe_subscription_id
        db.delete(subscription)
    db.flush()

    decisions, conflicts, projects = _references_left(db, reviewer.id)
    if decisions or conflicts or projects:
        report.outcome = "anonymized"
        report.kept_screening_decisions = decisions
        report.kept_conflicts = conflicts
        report.kept_projects = projects
        reviewer.email = f"deleted-{reviewer.id}@{ANONYMIZED_EMAIL_DOMAIN}"
        # A real hash of a password that is thrown away, so verifying against it works
        # and fails, like any wrong password.
        reviewer.hashed_password = hash_password(secrets.token_urlsafe(32))
    else:
        db.delete(reviewer)
    db.flush()

    _finish(db, dry_run, report.owned)
    return report


# --- command lines ---------------------------------------------------------------------------

SessionFactory = Callable[[], Session]


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def _describe_project(report: ProjectReport, *, dry_run: bool, indent: str = "") -> list[str]:
    removed = "Would remove" if dry_run else "Removed"
    lines = [
        f'{indent}{removed} project "{report.name}" ({report.id}), owned by {report.owner_email}:',
        (
            f"{indent}  {_plural(report.citations, 'citation')}, "
            f"{_plural(report.screening_decisions, 'screening decision')}, "
            f"{_plural(report.conflicts, 'conflict')}"
        ),
        (
            f"{indent}  {_plural(len(report.pdf_files), 'PDF file')} "
            f"{'to delete' if dry_run else 'deleted'}"
        ),
    ]
    if report.co_reviewer_email:
        lines.append(
            f"{indent}  its Co-Reviewer {report.co_reviewer_email} loses the project "
            "and their work in it"
        )
    if report.pdfs_missing:
        lines.append(
            f"{indent}  {_plural(len(report.pdfs_missing), 'listed PDF')} not found on disk"
        )
    for path in report.pdfs_outside_storage:
        lines.append(f"{indent}  NOT touched, outside the storage path: {path}")
    for path in report.pdfs_failed:
        lines.append(f"{indent}  COULD NOT delete (remove it by hand): {path}")
    return lines


def _describe_account(report: AccountReport, *, dry_run: bool) -> list[str]:
    lines: list[str] = []
    for project in report.owned:
        lines.extend(_describe_project(project, dry_run=dry_run))
    for detached in report.detached:
        lines.append(
            f'{"Would detach" if dry_run else "Detached"} {report.email} as Co-Reviewer of '
            f'"{detached.name}" ({detached.id}), owned by {detached.owner_email}: '
            f"{_plural(detached.screening_decisions_kept, 'screening decision')} kept, "
            "and the project now waits for a replacement Co-Reviewer"
        )
    if report.outcome == "anonymized":
        lines.append(
            f"{'Would anonymize' if dry_run else 'Anonymized'} the account {report.email}: "
            "its email and password are made unusable, and its "
            f"{_plural(report.kept_screening_decisions, 'screening decision')}, "
            f"{_plural(report.kept_conflicts, 'conflict')} and "
            f"{_plural(report.kept_projects, 'project')} stay in other people's reviews"
        )
    else:
        lines.append(f"{'Would delete' if dry_run else 'Deleted'} the account {report.email}")
    if report.stripe_subscription_id:
        lines.append(
            "Stripe was NOT changed: cancel subscription "
            f"{report.stripe_subscription_id} there by hand"
        )
    return lines


def _run(
    parser: argparse.ArgumentParser,
    argv: Sequence[str] | None,
    session_factory: SessionFactory,
    task: Callable[[Session, argparse.Namespace], list[str]],
    *,
    needs_yes: bool = False,
) -> int:
    """Runs a task, printing what it reports. Returns the exit code.

    A task that needs `--yes` is run as a dry run without it: it says what it would do,
    changes nothing and exits 1, so a script that forgets the flag cannot look successful.
    """
    args = parser.parse_args(argv)
    with session_factory() as db:
        try:
            lines = task(db, args)
        except OperatorError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
    for line in lines:
        print(line)
    if needs_yes and not args.yes:
        print("Nothing was changed. Run it again with --yes to do this.")
        return 1
    return 0


def _add_yes(parser: argparse.ArgumentParser, what: str) -> None:
    parser.add_argument(
        "--yes",
        action="store_true",
        help=f"actually {what}; without it, only says what would be removed",
    )


def reset_password_main(
    argv: Sequence[str] | None = None, *, session_factory: SessionFactory = SessionLocal
) -> int:
    parser = argparse.ArgumentParser(
        prog="reset_password.py",
        description="Set a new random password for an account and print it once. "
        "Someone already signed in stays signed in until their sign-in expires.",
    )
    parser.add_argument("email")

    def task(db: Session, args: argparse.Namespace) -> list[str]:
        password = reset_password(db, args.email)
        return [
            f"New password for {_normalize_email(args.email)}: {password}",
            "It is shown only now and is not stored anywhere else.",
        ]

    return _run(parser, argv, session_factory, task)


def delete_project_main(
    argv: Sequence[str] | None = None, *, session_factory: SessionFactory = SessionLocal
) -> int:
    parser = argparse.ArgumentParser(
        prog="delete_project.py",
        description="Remove a project: its rows and its PDFs under the full-text storage path.",
    )
    parser.add_argument("project_id", type=uuid.UUID)
    _add_yes(parser, "delete the project")

    def task(db: Session, args: argparse.Namespace) -> list[str]:
        report = delete_project(db, args.project_id, dry_run=not args.yes)
        return _describe_project(report, dry_run=not args.yes)

    return _run(parser, argv, session_factory, task, needs_yes=True)


def delete_account_main(
    argv: Sequence[str] | None = None, *, session_factory: SessionFactory = SessionLocal
) -> int:
    parser = argparse.ArgumentParser(
        prog="delete_account.py",
        description="Remove an account and the projects it owns. Projects where it is only the "
        "Co-Reviewer are kept for their Owner, and the account is anonymized instead of deleted "
        "if its decisions stay in them.",
    )
    parser.add_argument("email")
    _add_yes(parser, "delete the account")

    def task(db: Session, args: argparse.Namespace) -> list[str]:
        report = delete_account(db, args.email, dry_run=not args.yes)
        return _describe_account(report, dry_run=not args.yes)

    return _run(parser, argv, session_factory, task, needs_yes=True)
