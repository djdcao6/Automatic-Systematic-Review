"""Operator scripts: password reset and deleting projects and accounts (#62)."""

import io
import subprocess
import sys
import uuid
from pathlib import Path

import pymupdf
import pytest
from conftest import TestSessionLocal, auth_headers_for
from sqlalchemy import func, select

from asr_backend import models, operator_tasks
from asr_backend.ai_suggestion import FullTextSuggestionResult, SuggestionResult, get_ai_suggester
from asr_backend.auth import verify_password
from asr_backend.db import Base
from asr_backend.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
CSV_SAMPLE = (
    "title,abstract,authors,year,source\n"
    "First study,An abstract,Author,2020,PubMed\n"
    "Second study,Another abstract,Author,2021,PubMed\n"
)
# Tables that belong to people, not to a project: a project going away leaves them.
PEOPLE_TABLES = {"reviewers", "subscriptions"}


class _FakeSuggester:
    def __init__(self):
        self.extraction_values: dict[str, str] = {}

    async def suggest_screening_decision(self, **kwargs) -> SuggestionResult:
        return SuggestionResult(decision="include", reason="Matches criteria.")

    async def suggest_full_text_decision(self, **kwargs) -> FullTextSuggestionResult:
        return FullTextSuggestionResult(
            decision="include",
            reason="Meets all criteria.",
            extraction_values=self.extraction_values,
        )


@pytest.fixture
def suggester():
    fake = _FakeSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_suggester, None)


def _make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def _accept_invitation(client, owner_headers, project_id: str, email: str) -> dict[str, str]:
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    access_token = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": email, "password": "correcthorse", "ai_consent": True},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def _populate(client, suggester, owner_email: str, name: str, co_email: str | None = None):
    """A project with something in every table that hangs off a project.

    Dual with a Co-Reviewer when `co_email` is given: the two disagree on the first Citation,
    so there is a Conflict too. Returns (project id, citation ids, owner headers, co headers).
    """
    owner = auth_headers_for(client, owner_email)
    project_id = client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "dual" if co_email else "solo"},
        headers=owner,
    ).json()["id"]
    co = _accept_invitation(client, owner, project_id, co_email) if co_email else None
    base = f"/review-projects/{project_id}"

    client.put(f"{base}/criteria", json={"population": "Adults"}, headers=owner)
    client.put(f"{base}/search-terms", json={"population_terms": ["adult"]}, headers=owner)
    client.post(
        f"{base}/citations", files={"file": ("c.csv", CSV_SAMPLE, "text/csv")}, headers=owner
    )
    citations = client.get(f"{base}/citations", headers=owner).json()
    first, second = (c["id"] for c in sorted(citations, key=lambda c: c["title"]))
    field_id = client.post(
        f"{base}/extraction-fields", json={"name": "Sample size", "description": None},
        headers=owner,
    ).json()["id"]
    suggester.extraction_values = {field_id: "120"}

    for citation_id in (first, second):
        client.post(f"{base}/citations/{citation_id}/suggestion", headers=owner)
    client.post(
        f"{base}/citations/{first}/decision", json={"decision": "include"}, headers=owner
    )
    if co:
        client.post(
            f"{base}/citations/{first}/decision",
            json={"decision": "exclude", "reason": "Wrong population"},
            headers=co,
        )
    client.post(
        f"{base}/citations/{first}/full-text",
        files={"file": ("p.pdf", io.BytesIO(_make_pdf(f"{name} first")), "application/pdf")},
        headers=owner,
    )
    client.post(
        f"{base}/citations/{second}/full-text",
        files={"file": ("p.pdf", io.BytesIO(_make_pdf(f"{name} second")), "application/pdf")},
        headers=owner,
    )
    client.post(f"{base}/citations/{first}/full-text-suggestion", headers=owner)
    client.post(
        f"{base}/citations/{first}/full-text-decision", json={"decision": "include"}, headers=owner
    )
    client.post(
        f"{base}/citations/{first}/extraction-fields/{field_id}/value",
        json={"value": "120"},
        headers=owner,
    )
    return project_id, (first, second), owner, co


def _add_merge_and_duplicate(db, project_id: str, citation_ids, *, reverse: bool) -> None:
    """The two rows no relationship reaches from the project: a merged Citation, a duplicate pair.

    The merge is added in both directions across the tests, so whichever order the rows are
    deleted in, one of them meets a row that still points at the one being deleted.
    """
    first, second = (uuid.UUID(c) for c in citation_ids)
    survivor, loser = (second, first) if reverse else (first, second)
    db.get(models.Citation, loser).merged_into_citation_id = survivor
    db.add(
        models.PossibleDuplicate(
            review_project_id=uuid.UUID(project_id),
            survivor_citation_id=survivor,
            loser_citation_id=loser,
        )
    )
    db.commit()


def _row_counts(db) -> dict[str, int]:
    db.rollback()
    return {
        table.name: db.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
    }


def _stored_pdfs() -> set[str]:
    from asr_backend.settings import settings

    return {p.name for p in Path(settings.full_text_storage_path).glob("*.pdf")}


# --- reset_password ---------------------------------------------------------------------------


def test_reset_password_sets_a_new_one_that_works_and_the_old_one_fails(client, db_session):
    client.post(
        "/register",
        json={"email": "a@example.com", "password": "correcthorse", "ai_consent": True},
    )
    client.post(
        "/register",
        json={"email": "b@example.com", "password": "correcthorse", "ai_consent": True},
    )
    other_hash_before = db_session.scalar(
        select(models.Reviewer.hashed_password).where(models.Reviewer.email == "b@example.com")
    )

    new_password = operator_tasks.reset_password(db_session, "A@Example.com ")

    assert new_password != "correcthorse"
    old = client.post("/login", json={"email": "a@example.com", "password": "correcthorse"})
    new = client.post("/login", json={"email": "a@example.com", "password": new_password})
    assert old.status_code == 401
    assert new.status_code == 200
    db_session.expire_all()
    other_hash_after = db_session.scalar(
        select(models.Reviewer.hashed_password).where(models.Reviewer.email == "b@example.com")
    )
    assert other_hash_after == other_hash_before


def test_reset_password_gives_a_different_password_each_time(client, db_session):
    client.post(
        "/register",
        json={"email": "a@example.com", "password": "correcthorse", "ai_consent": True},
    )

    first = operator_tasks.reset_password(db_session, "a@example.com")
    second = operator_tasks.reset_password(db_session, "a@example.com")

    assert first != second
    assert len(first) >= 8


def test_reset_password_for_an_unknown_email_is_an_error(db_session):
    with pytest.raises(operator_tasks.OperatorError, match="No account"):
        operator_tasks.reset_password(db_session, "nobody@example.com")


def test_the_reset_password_command_prints_the_password_once(client, capsys):
    client.post(
        "/register",
        json={"email": "a@example.com", "password": "correcthorse", "ai_consent": True},
    )

    code = operator_tasks.reset_password_main(
        ["a@example.com"], session_factory=TestSessionLocal
    )

    out = capsys.readouterr().out
    assert code == 0
    password = out.split("a@example.com: ")[1].split()[0]
    assert client.post(
        "/login", json={"email": "a@example.com", "password": password}
    ).status_code == 200


def test_the_reset_password_command_reports_an_unknown_email(capsys):
    code = operator_tasks.reset_password_main(
        ["nobody@example.com"], session_factory=TestSessionLocal
    )

    assert code == 1
    assert "No account with the email nobody@example.com" in capsys.readouterr().err


# --- delete_project ---------------------------------------------------------------------------


@pytest.mark.parametrize("reverse_merge", [False, True])
def test_deleting_a_project_removes_every_row_under_it_and_its_pdfs_and_only_those(
    client, suggester, db_session, reverse_merge
):
    project_a, citations_a, *_ = _populate(client, suggester, "owner-a@example.com", "A", "co-a@example.com")
    _add_merge_and_duplicate(db_session, project_a, citations_a, reverse=reverse_merge)
    counts_a = _row_counts(db_session)
    pdfs_a = _stored_pdfs()
    project_b, *_ = _populate(client, suggester, "owner-b@example.com", "B", "co-b@example.com")
    counts_both = _row_counts(db_session)
    pdfs_b = _stored_pdfs() - pdfs_a
    # The test is only as good as what it puts in: every table a project owns has a row.
    project_tables = {
        "review_projects", "criteria", "search_terms", "citations", "extraction_fields",
        "possible_duplicates", "invitations", "conflicts", "ai_suggestions",
        "screening_decisions", "full_texts", "full_text_decisions", "full_text_suggestions",
        "full_text_suggestion_values", "extraction_values",
    }  # fmt: skip
    assert all(counts_a[table] > 0 for table in project_tables), counts_a
    assert len(pdfs_a) == 2 and len(pdfs_b) == 2

    report = operator_tasks.delete_project(db_session, uuid.UUID(project_a), dry_run=False)

    after = _row_counts(db_session)
    for table, count in after.items():
        if table not in PEOPLE_TABLES:
            assert count == counts_both[table] - counts_a[table], table
    assert after["reviewers"] == counts_both["reviewers"]
    assert _stored_pdfs() == pdfs_b
    assert db_session.get(models.ReviewProject, uuid.UUID(project_b)) is not None
    assert report.citations == 2
    assert report.conflicts == 1
    assert len(report.pdf_files) == 2


def test_a_dry_run_says_what_would_go_and_changes_nothing(client, suggester, db_session):
    project_id, *_ = _populate(client, suggester, "owner@example.com", "A", "co@example.com")
    before = _row_counts(db_session)
    pdfs = _stored_pdfs()

    report = operator_tasks.delete_project(db_session, uuid.UUID(project_id), dry_run=True)

    assert report.citations == 2
    assert report.co_reviewer_email == "co@example.com"
    assert _row_counts(db_session) == before
    assert _stored_pdfs() == pdfs


def test_the_delete_project_command_needs_yes_and_says_what_it_would_do(
    client, suggester, db_session, capsys
):
    project_id, *_ = _populate(client, suggester, "owner@example.com", "My Review")
    before = _row_counts(db_session)

    code = operator_tasks.delete_project_main([project_id], session_factory=TestSessionLocal)

    out = capsys.readouterr().out
    assert code == 1
    assert 'Would remove project "My Review"' in out
    assert "--yes" in out
    assert _row_counts(db_session) == before

    code = operator_tasks.delete_project_main(
        [project_id, "--yes"], session_factory=TestSessionLocal
    )

    out = capsys.readouterr().out
    assert code == 0
    assert 'Removed project "My Review"' in out
    assert "2 PDF files deleted" in out
    assert _row_counts(db_session)["review_projects"] == 0
    assert _stored_pdfs() == set()


def test_deleting_an_unknown_project_is_an_error_and_a_bad_id_is_refused(capsys):
    code = operator_tasks.delete_project_main(
        [str(uuid.uuid4()), "--yes"], session_factory=TestSessionLocal
    )

    assert code == 1
    assert "No project with the id" in capsys.readouterr().err
    with pytest.raises(SystemExit) as refused:
        operator_tasks.delete_project_main(["not-an-id", "--yes"], session_factory=TestSessionLocal)
    assert refused.value.code == 2


def test_a_pdf_outside_the_storage_path_is_reported_and_left_alone(
    client, suggester, db_session, tmp_path
):
    project_id, citations, *_ = _populate(client, suggester, "owner@example.com", "A")
    elsewhere = tmp_path / "not-ours.pdf"
    elsewhere.write_bytes(b"%PDF-1.4 keep me")
    full_text = db_session.scalar(
        select(models.FullText).where(models.FullText.citation_id == uuid.UUID(citations[0]))
    )
    full_text.file_path = str(elsewhere)
    db_session.commit()

    report = operator_tasks.delete_project(db_session, uuid.UUID(project_id), dry_run=False)

    assert elsewhere.exists()
    assert report.pdfs_outside_storage == [str(elsewhere)]
    assert len(report.pdf_files) == 1
    assert db_session.get(models.ReviewProject, uuid.UUID(project_id)) is None


def test_a_listed_pdf_that_is_not_on_disk_does_not_stop_the_delete(client, suggester, db_session):
    project_id, *_ = _populate(client, suggester, "owner@example.com", "A")
    for path in Path(operator_tasks.settings.full_text_storage_path).glob("*.pdf"):
        path.unlink()

    report = operator_tasks.delete_project(db_session, uuid.UUID(project_id), dry_run=False)

    assert len(report.pdfs_missing) == 2
    assert db_session.get(models.ReviewProject, uuid.UUID(project_id)) is None


def test_a_pdf_that_cannot_be_deleted_is_reported_after_the_rows_are_gone(
    client, suggester, db_session, monkeypatch
):
    project_id, *_ = _populate(client, suggester, "owner@example.com", "A")

    def refuse(self, *args, **kwargs):
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "unlink", refuse)

    report = operator_tasks.delete_project(db_session, uuid.UUID(project_id), dry_run=False)

    assert len(report.pdfs_failed) == 2
    assert db_session.get(models.ReviewProject, uuid.UUID(project_id)) is None


# --- delete_account ---------------------------------------------------------------------------


def _reviewer(db, email: str) -> models.Reviewer | None:
    db.rollback()
    return db.scalar(select(models.Reviewer).where(models.Reviewer.email == email))


def test_an_account_with_nothing_left_in_anyone_elses_work_is_deleted_with_its_projects(
    client, suggester, db_session
):
    _populate(client, suggester, "owner@example.com", "Mine")
    _populate(client, suggester, "other@example.com", "Theirs")
    before = _row_counts(db_session)

    report = operator_tasks.delete_account(db_session, "Owner@Example.com", dry_run=False)

    assert report.outcome == "deleted"
    assert [project.name for project in report.owned] == ["Mine"]
    assert _reviewer(db_session, "owner@example.com") is None
    assert _reviewer(db_session, "other@example.com") is not None
    after = _row_counts(db_session)
    assert after["review_projects"] == 1
    assert after["reviewers"] == before["reviewers"] - 1
    assert client.post(
        "/login", json={"email": "owner@example.com", "password": "correcthorse"}
    ).status_code == 401
    assert len(_stored_pdfs()) == 2


def test_a_co_reviewer_is_detached_and_anonymized_and_their_decisions_stay_with_the_owner(
    client, suggester, db_session
):
    project_id, _, owner, _ = _populate(
        client, suggester, "owner@example.com", "Dual", "co@example.com"
    )
    co_id = _reviewer(db_session, "co@example.com").id
    before = _row_counts(db_session)

    report = operator_tasks.delete_account(db_session, "co@example.com", dry_run=False)

    assert report.outcome == "anonymized"
    assert report.owned == []
    assert [d.name for d in report.detached] == ["Dual"]
    assert report.detached[0].screening_decisions_kept == 1
    assert report.kept_screening_decisions == 1
    assert report.kept_conflicts == 1
    # The row is kept, made unusable, and the person's email is gone.
    account = db_session.get(models.Reviewer, co_id)
    db_session.refresh(account)
    assert account.email == f"deleted-{co_id}@deleted.invalid"
    assert _reviewer(db_session, "co@example.com") is None
    assert client.post(
        "/login", json={"email": "co@example.com", "password": "correcthorse"}
    ).status_code == 401
    # Sign-in refuses such an address outright, and the old password no longer fits the hash.
    assert not verify_password("correcthorse", account.hashed_password)
    # The Owner's review is intact, and waits for a replacement the way #29 does.
    after = _row_counts(db_session)
    for table in ("citations", "screening_decisions", "conflicts", "full_texts"):
        assert after[table] == before[table], table
    project = db_session.get(models.ReviewProject, uuid.UUID(project_id))
    db_session.refresh(project)
    assert project.co_reviewer_id is None
    assert project.former_co_reviewer_id == co_id
    detail = client.get(f"/review-projects/{project_id}", headers=owner)
    assert detail.status_code == 200


def test_a_token_from_before_the_account_was_removed_no_longer_opens_the_project(
    client, suggester, db_session
):
    project_id, (first, _), _, co = _populate(
        client, suggester, "owner@example.com", "Dual", "co@example.com"
    )
    url = f"/review-projects/{project_id}/citations/{first}"
    assert client.get(url, headers=co).status_code == 200

    operator_tasks.delete_account(db_session, "co@example.com", dry_run=False)

    assert client.get(url, headers=co).status_code in (403, 404)
    assert client.get(f"/review-projects/{project_id}", headers=co).status_code in (403, 404)


def test_removing_the_owner_takes_the_project_and_the_co_reviewers_work_in_it_but_not_their_account(
    client, suggester, db_session
):
    _populate(client, suggester, "owner@example.com", "Dual", "co@example.com")

    report = operator_tasks.delete_account(db_session, "owner@example.com", dry_run=False)

    assert report.outcome == "deleted"
    assert report.owned[0].co_reviewer_email == "co@example.com"
    assert _reviewer(db_session, "co@example.com") is not None
    counts = _row_counts(db_session)
    assert counts["screening_decisions"] == 0
    assert counts["conflicts"] == 0
    assert client.post(
        "/login", json={"email": "co@example.com", "password": "correcthorse"}
    ).status_code == 200


def test_an_account_that_owns_a_project_and_co_reviews_another_is_both_deleted_and_anonymized(
    client, suggester, db_session
):
    """The owned project goes; the account stays, made unusable, because of the other one."""
    _populate(client, suggester, "boss@example.com", "Boss's", "both@example.com")
    owner = auth_headers_for(client, "both@example.com")
    own_project = client.post(
        "/review-projects",
        json={"name": "Own", "merge_mode": "combine", "review_mode": "solo"},
        headers=owner,
    ).json()["id"]

    report = operator_tasks.delete_account(db_session, "both@example.com", dry_run=False)

    assert report.outcome == "anonymized"
    assert [p.name for p in report.owned] == ["Own"]
    assert [d.name for d in report.detached] == ["Boss's"]
    assert db_session.get(models.ReviewProject, uuid.UUID(own_project)) is None
    assert _row_counts(db_session)["review_projects"] == 1


def test_a_former_co_reviewer_mark_alone_keeps_the_account_as_anonymized(
    client, suggester, db_session
):
    project_id, _, owner, _ = _populate(
        client, suggester, "owner@example.com", "Dual", "co@example.com"
    )
    client.post(f"/review-projects/{project_id}/co-reviewer/remove", headers=owner)
    # Their decisions are the Owner's data too, and a project waits on their mark.
    report = operator_tasks.delete_account(db_session, "co@example.com", dry_run=False)

    assert report.outcome == "anonymized"
    assert report.kept_projects == 1


def test_a_dry_run_of_account_removal_changes_nothing_and_says_what_it_would_do(
    client, suggester, db_session
):
    _populate(client, suggester, "boss@example.com", "Boss's", "both@example.com")
    owner = auth_headers_for(client, "both@example.com")
    client.post(
        "/review-projects",
        json={"name": "Own", "merge_mode": "combine", "review_mode": "solo"},
        headers=owner,
    )
    before = _row_counts(db_session)
    pdfs = _stored_pdfs()

    report = operator_tasks.delete_account(db_session, "both@example.com", dry_run=True)

    assert report.outcome == "anonymized"
    assert [p.name for p in report.owned] == ["Own"]
    assert _row_counts(db_session) == before
    assert _stored_pdfs() == pdfs
    assert _reviewer(db_session, "both@example.com") is not None


def test_removing_an_account_drops_its_subscription_and_names_the_stripe_one(
    client, db_session
):
    client.post(
        "/register",
        json={"email": "payer@example.com", "password": "correcthorse", "ai_consent": True},
    )
    payer = _reviewer(db_session, "payer@example.com")
    db_session.add(
        models.Subscription(
            reviewer_id=payer.id,
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_456",
            status="active",
        )
    )
    db_session.commit()

    report = operator_tasks.delete_account(db_session, "payer@example.com", dry_run=False)

    assert report.stripe_subscription_id == "sub_456"
    assert _row_counts(db_session)["subscriptions"] == 0
    assert _reviewer(db_session, "payer@example.com") is None


def test_removing_an_unknown_account_is_an_error(db_session):
    with pytest.raises(operator_tasks.OperatorError, match="No account"):
        operator_tasks.delete_account(db_session, "nobody@example.com", dry_run=False)


def test_the_delete_account_command_needs_yes_and_says_what_it_would_do(
    client, suggester, db_session, capsys
):
    _populate(client, suggester, "boss@example.com", "Boss's", "both@example.com")
    before = _row_counts(db_session)

    code = operator_tasks.delete_account_main(
        ["both@example.com"], session_factory=TestSessionLocal
    )

    out = capsys.readouterr().out
    assert code == 1
    assert 'Would detach both@example.com as Co-Reviewer of "Boss\'s"' in out
    assert "Would anonymize the account both@example.com" in out
    assert "--yes" in out
    assert _row_counts(db_session) == before

    code = operator_tasks.delete_account_main(
        ["both@example.com", "--yes"], session_factory=TestSessionLocal
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "Anonymized the account both@example.com" in out
    assert _reviewer(db_session, "both@example.com") is None


def test_no_one_can_register_an_address_like_an_anonymized_one(client):
    response = client.post(
        "/register",
        json={
            "email": f"deleted-{uuid.uuid4()}@deleted.invalid",
            "password": "correcthorse",
            "ai_consent": True,
        },
    )

    assert response.status_code == 422


# --- the scripts themselves -------------------------------------------------------------------


@pytest.mark.parametrize("script", ["reset_password", "delete_project", "delete_account"])
def test_each_script_runs_from_the_backend_directory(script):
    result = subprocess.run(
        [sys.executable, f"scripts/{script}.py", "--help"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"{script}.py" in result.stdout
