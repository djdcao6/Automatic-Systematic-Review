import asyncio
import io
import itertools
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pymupdf
import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Delete

from asr_backend import crud, full_text_suggestion, models
from asr_backend.ai_suggestion import (
    FullTextSuggestionResult,
    SuggestionGenerationError,
    SuggestionResult,
    get_ai_suggester,
)
from asr_backend.main import app
from asr_backend.settings import settings


def create_project(authed_client, name: str = "My Review") -> str:
    payload = {"name": name, "merge_mode": "combine", "review_mode": "solo"}
    return authed_client.post("/review-projects", json=payload).json()["id"]


def create_citation(authed_client, project_id: str, title: str = "Study A") -> str:
    authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={
            "file": (
                "citations.csv",
                f"title,abstract,authors,year,source\n{title},An abstract,Jane Doe,2020,PubMed\n",
                "text/csv",
            )
        },
    )
    citations = authed_client.get(f"/review-projects/{project_id}/citations").json()
    return next(c["id"] for c in citations if c["title"] == title)


def create_extraction_field(authed_client, project_id: str, name: str = "Sample size") -> dict:
    return authed_client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": name, "description": None},
    ).json()


def make_pdf(text: str = "Sample paper text") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def upload_full_text(authed_client, project_id: str, citation_id: str, content: bytes, filename="paper.pdf"):
    return authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )


def get_detail(authed_client, project_id: str, citation_id: str) -> dict:
    return authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()


def generate_suggestion(authed_client, project_id: str, citation_id: str):
    return authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-suggestion"
    )


class _FakeSuggester:
    def __init__(
        self,
        decision="include",
        reason="Meets all criteria.",
        extraction_values=None,
        error=None,
        truncated=False,
    ):
        self.decision = decision
        self.reason = reason
        self.extraction_values = extraction_values or {}
        self.error = error
        self.truncated = truncated
        self.screening_calls = 0
        self.full_text_calls = 0

    async def suggest_screening_decision(self, **kwargs) -> SuggestionResult:
        self.screening_calls += 1
        return SuggestionResult(decision="include", reason="Matches criteria.")

    async def suggest_full_text_decision(self, **kwargs):
        from asr_backend.ai_suggestion import FullTextSuggestionResult

        self.full_text_calls += 1
        if self.error:
            raise self.error
        return FullTextSuggestionResult(
            decision=self.decision,
            reason=self.reason,
            extraction_values=self.extraction_values,
            truncated=self.truncated,
        )


class _BarrierSuggester(_FakeSuggester):
    """Holds every caller inside the model call until `parties` of them have arrived.

    Each caller gets its own answer ("Answer 1", "Answer 2"), so a test can tell
    whose answer ended up stored.
    """

    def __init__(self, parties: int):
        super().__init__()
        self._barrier = threading.Barrier(parties, timeout=10)
        self._answers = itertools.count(1)

    async def suggest_full_text_decision(self, **kwargs):
        await asyncio.to_thread(self._barrier.wait)
        self.full_text_calls += 1
        return FullTextSuggestionResult(
            decision="include", reason=f"Answer {next(self._answers)}", extraction_values={}
        )


class _GatedSuggester(_FakeSuggester):
    """Parks its caller inside the model call until the test lets it finish."""

    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self._answers = itertools.count(1)

    async def suggest_full_text_decision(self, **kwargs):
        self.entered.set()
        await asyncio.to_thread(self.release.wait)
        self.full_text_calls += 1
        return FullTextSuggestionResult(
            decision="include", reason=f"Answer {next(self._answers)}", extraction_values={}
        )


@pytest.fixture
def override_suggester():
    fake = _FakeSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_suggester, None)


def test_opening_a_citation_with_a_full_text_does_not_wait_on_the_model(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())

    detail = get_detail(authed_client, project_id, citation_id)

    assert detail["full_text_suggestion"] is None
    assert detail["full_text_suggestion_unavailable_reason"] is None
    assert detail["full_text_suggestion_needs_generation"] is True
    assert override_suggester.full_text_calls == 0


def test_generating_a_full_text_suggestion_keeps_it_for_later_views(authed_client, override_suggester):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())

    response = generate_suggestion(authed_client, project_id, citation_id)

    assert response.status_code == 200
    assert response.json() == {
        "suggestion": {
            "decision": "include",
            "reason": "Meets all criteria.",
            "extraction_values": [],
            "truncated": False,
        },
        "suggestion_unavailable_reason": None,
    }
    detail = get_detail(authed_client, project_id, citation_id)
    assert detail["full_text_suggestion"]["decision"] == "include"
    assert detail["full_text_suggestion"]["reason"] == "Meets all criteria."
    assert detail["full_text_suggestion_needs_generation"] is False
    assert override_suggester.full_text_calls == 1


def test_a_suggestion_from_truncated_text_is_marked_truncated_for_later_views(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())
    override_suggester.truncated = True

    outcome = generate_suggestion(authed_client, project_id, citation_id).json()

    assert outcome["suggestion"]["truncated"] is True
    detail = get_detail(authed_client, project_id, citation_id)
    assert detail["full_text_suggestion"]["truncated"] is True


def test_full_text_suggestion_includes_active_extraction_field_values(authed_client, override_suggester):
    project_id = create_project(authed_client)
    field = create_extraction_field(authed_client, project_id, name="Sample size")
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())
    override_suggester.extraction_values = {field["id"]: "120 participants"}

    outcome = generate_suggestion(authed_client, project_id, citation_id).json()

    values = outcome["suggestion"]["extraction_values"]
    assert values == [
        {
            "extraction_field_id": field["id"],
            "name": "Sample size",
            "value": "120 participants",
        }
    ]


def test_full_text_suggestion_keeps_each_value_with_its_own_field(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    field_a = create_extraction_field(authed_client, project_id, name="Duration")
    field_b = create_extraction_field(authed_client, project_id, name="Follow-up")
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())
    override_suggester.extraction_values = {
        field_a["id"]: "6 months",
        field_b["id"]: "12 months",
    }

    outcome = generate_suggestion(authed_client, project_id, citation_id).json()

    values = {v["extraction_field_id"]: v["value"] for v in outcome["suggestion"]["extraction_values"]}
    assert values == {field_a["id"]: "6 months", field_b["id"]: "12 months"}


def test_a_second_request_returns_the_same_suggestion_without_asking_the_model_again(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())

    first = generate_suggestion(authed_client, project_id, citation_id).json()
    override_suggester.reason = "A different answer."
    second = generate_suggestion(authed_client, project_id, citation_id).json()

    assert second == first
    assert override_suggester.full_text_calls == 1


def test_full_text_suggestion_unavailable_without_a_full_text(authed_client, override_suggester):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    detail = get_detail(authed_client, project_id, citation_id)

    assert detail["full_text_suggestion"] is None
    assert detail["full_text_suggestion_unavailable_reason"] == "no_full_text"
    assert detail["full_text_suggestion_needs_generation"] is False
    assert override_suggester.full_text_calls == 0


def test_full_text_suggestion_unavailable_when_parse_failed(authed_client, override_suggester):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    # An all-image PDF page has no extractable text layer, so parsing fails.
    doc = pymupdf.open()
    doc.new_page()
    upload_full_text(authed_client, project_id, citation_id, doc.tobytes())

    detail = get_detail(authed_client, project_id, citation_id)

    assert detail["full_text"]["parse_status"] == "parse_failed"
    assert detail["full_text_suggestion"] is None
    assert detail["full_text_suggestion_unavailable_reason"] == "parse_failed"
    assert detail["full_text_suggestion_needs_generation"] is False
    assert override_suggester.full_text_calls == 0


def test_two_simultaneous_first_requests_share_one_model_generation(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())
    suggester = _GatedSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: suggester
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(generate_suggestion, authed_client, project_id, citation_id)
            assert suggester.entered.wait(timeout=10)
            second = pool.submit(generate_suggestion, authed_client, project_id, citation_id)
            suggester.release.set()
            futures = [first, second]
            responses = [future.result() for future in futures]
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)

    assert [response.status_code for response in responses] == [200, 200]
    assert suggester.full_text_calls == 1
    first, second = (response.json()["suggestion"] for response in responses)
    assert first == second
    assert get_detail(authed_client, project_id, citation_id)["full_text_suggestion"] == first


def test_a_suggestion_generated_from_a_replaced_pdf_is_not_kept(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf("First version"))
    suggester = _GatedSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: suggester
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            in_flight = pool.submit(generate_suggestion, authed_client, project_id, citation_id)
            assert suggester.entered.wait(timeout=10)
            upload_full_text(authed_client, project_id, citation_id, make_pdf("Second version"))
            suggester.release.set()
            stale = in_flight.result()
        detail = get_detail(authed_client, project_id, citation_id)
        fresh = generate_suggestion(authed_client, project_id, citation_id)
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)

    assert stale.status_code == 200
    assert stale.json() == {"suggestion": None, "suggestion_unavailable_reason": None}
    assert detail["full_text_suggestion"] is None
    assert detail["full_text_suggestion_needs_generation"] is True
    assert fresh.json()["suggestion"]["reason"] == "Answer 2"


def _wait_until_a_query_is_blocked_on_a_lock(engine, timeout: float = 10) -> None:
    """Returns once some database session is waiting for a lock another holds.

    Polls the database's own report of that state (a fresh connection each time,
    since pg_stat_activity is cached within a transaction) rather than guessing
    how long a thread needs to get there.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            blocked = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
        if blocked:
            return
        time.sleep(0.01)
    pytest.fail("No query became blocked on a lock")


class _PausedCommitSession(Session):
    """A session that stops just before committing, until the test lets it go."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.about_to_commit = threading.Event()
        self.proceed = threading.Event()

    def commit(self):
        self.about_to_commit.set()
        assert self.proceed.wait(timeout=10)
        super().commit()


def test_replacing_the_pdf_waits_for_a_suggestion_that_is_being_saved(authed_client, db_session):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf("First version"))
    citation_uuid = uuid.UUID(citation_id)
    stamp = crud.get_full_text(db_session, citation_uuid).updated_at
    engine = db_session.get_bind()
    saving = _PausedCommitSession(bind=engine)
    replacing = Session(bind=engine)
    events: list[str] = []
    replacement_started = threading.Event()
    replacement_finished = threading.Event()

    def save_suggestion():
        crud.create_full_text_suggestion(
            saving,
            citation_uuid,
            decision="include",
            reason="From the first version.",
            extraction_values={},
            active_fields=[],
            full_text_stamp=stamp,
            model="claude-test-model",
        )
        events.append("suggestion saved")

    def replace_pdf():
        replacement_started.set()
        crud.replace_full_text(
            replacing,
            citation_uuid,
            original_filename="paper.pdf",
            file_path="unused.pdf",
            parsed_text="Second version",
            parse_status="parsed",
        )
        events.append("pdf replaced")
        replacement_finished.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            saved = pool.submit(save_suggestion)
            assert saving.about_to_commit.wait(timeout=10)
            replaced = pool.submit(replace_pdf)
            assert replacement_started.wait(timeout=10)
            # Not just started: parked on the lock the save holds. Without this the
            # save can commit before the replacement has issued anything, and the
            # test would pass whatever order the replacement works in.
            _wait_until_a_query_is_blocked_on_a_lock(engine)
            assert not replacement_finished.is_set()
            saving.proceed.set()
            saved.result()
            replaced.result()
    finally:
        saving.close()
        replacing.close()

    assert events == ["suggestion saved", "pdf replaced"]
    # The replacement waited for the save, so it sees and removes what was saved.
    assert crud.get_full_text_suggestion(db_session, citation_uuid) is None


def test_requesting_a_suggestion_without_a_full_text_does_not_ask_the_model(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    response = generate_suggestion(authed_client, project_id, citation_id)

    assert response.status_code == 200
    assert response.json() == {"suggestion": None, "suggestion_unavailable_reason": "no_full_text"}
    assert override_suggester.full_text_calls == 0


def test_requesting_a_suggestion_for_an_unparsable_full_text_does_not_ask_the_model(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    doc = pymupdf.open()
    doc.new_page()
    upload_full_text(authed_client, project_id, citation_id, doc.tobytes())

    response = generate_suggestion(authed_client, project_id, citation_id)

    assert response.status_code == 200
    assert response.json() == {"suggestion": None, "suggestion_unavailable_reason": "parse_failed"}
    assert override_suggester.full_text_calls == 0


def test_a_failed_generation_is_reported_and_the_next_request_tries_again(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())
    failing = _FakeSuggester(error=SuggestionGenerationError("boom"))
    app.dependency_overrides[get_ai_suggester] = lambda: failing
    try:
        first = generate_suggestion(authed_client, project_id, citation_id)
        detail = get_detail(authed_client, project_id, citation_id)
        generate_suggestion(authed_client, project_id, citation_id)
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)

    assert first.status_code == 200
    assert first.json() == {
        "suggestion": None,
        "suggestion_unavailable_reason": "generation_failed",
    }
    assert detail["full_text_suggestion"] is None
    assert detail["full_text_suggestion_needs_generation"] is True
    assert failing.full_text_calls == 2


class _HangingSuggester(_FakeSuggester):
    """Never answers, like a model call that has stopped responding."""

    async def suggest_full_text_decision(self, **kwargs):
        self.full_text_calls += 1
        await asyncio.sleep(3600)


def test_a_model_call_that_never_answers_is_reported_and_frees_the_next_request(
    authed_client, monkeypatch
):
    monkeypatch.setattr(full_text_suggestion, "GENERATION_TIMEOUT_SECONDS", 0.05)
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())
    hanging = _HangingSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: hanging
    try:
        first = generate_suggestion(authed_client, project_id, citation_id)
        second = generate_suggestion(authed_client, project_id, citation_id)
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)

    for response in (first, second):
        assert response.status_code == 200
        assert response.json() == {
            "suggestion": None,
            "suggestion_unavailable_reason": "generation_failed",
        }
    # The second request got the lock back and tried the model itself.
    assert hanging.full_text_calls == 2


def test_a_request_stops_waiting_for_a_generation_that_takes_too_long(
    authed_client, monkeypatch
):
    monkeypatch.setattr(full_text_suggestion, "GENERATION_WAIT_LIMIT_SECONDS", 0.3)
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())
    suggester = _GatedSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: suggester
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            leader = pool.submit(generate_suggestion, authed_client, project_id, citation_id)
            assert suggester.entered.wait(timeout=10)
            follower = generate_suggestion(authed_client, project_id, citation_id)
            suggester.release.set()
            leader_response = leader.result()
    finally:
        suggester.release.set()
        app.dependency_overrides.pop(get_ai_suggester, None)

    assert follower.status_code == 200
    assert follower.json() == {
        "suggestion": None,
        "suggestion_unavailable_reason": "generation_failed",
    }
    # Giving up did not disturb the request that was doing the work.
    assert leader_response.status_code == 200
    assert leader_response.json()["suggestion"]["reason"] == "Answer 1"
    assert suggester.full_text_calls == 1


def test_replacing_the_pdf_clears_the_suggestion_and_the_next_request_generates_a_new_one(
    authed_client, override_suggester
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf("First version"))
    generate_suggestion(authed_client, project_id, citation_id)
    assert override_suggester.full_text_calls == 1

    override_suggester.decision = "exclude"
    override_suggester.reason = "Wrong study design after re-read."
    upload_full_text(authed_client, project_id, citation_id, make_pdf("Second version"))
    detail = get_detail(authed_client, project_id, citation_id)
    outcome = generate_suggestion(authed_client, project_id, citation_id).json()

    assert detail["full_text_suggestion"] is None
    assert detail["full_text_suggestion_needs_generation"] is True
    assert override_suggester.full_text_calls == 2
    assert outcome["suggestion"]["decision"] == "exclude"
    assert outcome["suggestion"]["reason"] == "Wrong study design after re-read."


def test_full_text_suggestion_for_missing_citation_returns_404(authed_client, override_suggester):
    project_id = create_project(authed_client)

    response = authed_client.get(
        f"/review-projects/{project_id}/citations/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


def test_requesting_a_suggestion_for_a_missing_citation_returns_404(authed_client, override_suggester):
    project_id = create_project(authed_client)

    response = generate_suggestion(authed_client, project_id, "00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert override_suggester.full_text_calls == 0


def test_a_new_full_text_suggestion_stores_the_configured_model_and_keeps_it(
    authed_client, override_suggester, db_session, monkeypatch
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf())
    monkeypatch.setattr(settings, "anthropic_model", "claude-first-model")

    generate_suggestion(authed_client, project_id, citation_id)
    monkeypatch.setattr(settings, "anthropic_model", "claude-second-model")
    generate_suggestion(authed_client, project_id, citation_id)

    stored = (
        db_session.query(models.FullTextSuggestion)
        .filter_by(citation_id=uuid.UUID(citation_id))
        .one()
    )
    assert stored.model == "claude-first-model"
    assert override_suggester.full_text_calls == 1


def _replace_full_text(session, citation_id: str, filename: str = "second.pdf"):
    return crud.replace_full_text(
        session,
        uuid.UUID(citation_id),
        original_filename=filename,
        file_path="unused.pdf",
        parsed_text="Second version",
        parse_status="parsed",
    )


def _committed_pair(engine, citation_id: str) -> tuple[str | None, str | None]:
    """(Full Text filename, Suggestion reason) as a brand-new reader would see them."""
    reader = Session(bind=engine)
    try:
        full_text, suggestion = crud.get_full_text_with_suggestion(reader, uuid.UUID(citation_id))
        return (
            full_text.original_filename if full_text else None,
            suggestion.reason if suggestion else None,
        )
    finally:
        reader.close()


class _ObservedCommitSession(Session):
    """A session that reports what other readers can see right after each of its commits."""

    def __init__(self, *args, observe, **kwargs):
        super().__init__(*args, **kwargs)
        self._observe = observe
        self.observations: list = []

    def commit(self):
        super().commit()
        self.observations.append(self._observe())


class _FailingSuggestionDeleteSession(Session):
    """A session that fails deleting the Suggestion itself, after everything before it has run.

    By then the Full Text upsert and the delete of the Suggestion's values have both
    been executed in the open transaction, so what survives shows what was rolled back.
    """

    def execute(self, statement, *args, **kwargs):
        if isinstance(statement, Delete) and statement.table.name == "full_text_suggestions":
            raise RuntimeError("induced failure")
        return super().execute(statement, *args, **kwargs)


class _RecordingSuggester(_FakeSuggester):
    def __init__(self):
        super().__init__()
        self.seen_texts: list[str] = []

    async def suggest_full_text_decision(self, **kwargs):
        self.seen_texts.append(kwargs["full_text"])
        return await super().suggest_full_text_decision(**kwargs)


def test_a_suggestion_save_that_arrives_during_a_replacement_is_refused(
    authed_client, override_suggester, db_session
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf("First"), filename="first.pdf")
    citation_uuid = uuid.UUID(citation_id)
    old_stamp = crud.get_full_text(db_session, citation_uuid).updated_at
    engine = db_session.get_bind()
    replacing = _PausedCommitSession(bind=engine)
    saving = Session(bind=engine)

    def replace_pdf():
        _replace_full_text(replacing, citation_id)

    def save_suggestion():
        return crud.create_full_text_suggestion(
            saving,
            citation_uuid,
            decision="include",
            reason="From the first version.",
            extraction_values={},
            active_fields=[],
            full_text_stamp=old_stamp,
            model="claude-test-model",
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            replaced = pool.submit(replace_pdf)
            assert replacing.about_to_commit.wait(timeout=10)
            saved = pool.submit(save_suggestion)
            # The save is parked on the Full Text row the open replacement has locked.
            _wait_until_a_query_is_blocked_on_a_lock(engine)
            replacing.proceed.set()
            replaced.result()
            outcome = saved.result()
    finally:
        replacing.close()
        saving.close()

    assert outcome is None
    assert _committed_pair(engine, citation_id) == ("second.pdf", None)


def test_replacing_the_pdf_never_commits_new_metadata_beside_the_old_suggestion(
    authed_client, override_suggester, db_session
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf("First"), filename="first.pdf")
    generate_suggestion(authed_client, project_id, citation_id)
    engine = db_session.get_bind()
    replacing = _ObservedCommitSession(
        bind=engine, observe=lambda: _committed_pair(engine, citation_id)
    )

    try:
        _replace_full_text(replacing, citation_id)
    finally:
        replacing.close()

    coherent = {("first.pdf", "Meets all criteria."), ("second.pdf", None)}
    assert replacing.observations
    assert set(replacing.observations) <= coherent
    assert _committed_pair(engine, citation_id) == ("second.pdf", None)


def test_an_error_before_the_shared_commit_rolls_back_the_new_full_text_and_the_invalidation(
    authed_client, override_suggester, db_session
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    field = create_extraction_field(authed_client, project_id)
    override_suggester.extraction_values = {field["id"]: "120 patients"}
    upload_full_text(authed_client, project_id, citation_id, make_pdf("First"), filename="first.pdf")
    generate_suggestion(authed_client, project_id, citation_id)
    engine = db_session.get_bind()
    failing = _FailingSuggestionDeleteSession(bind=engine)

    try:
        with pytest.raises(RuntimeError, match="induced failure"):
            _replace_full_text(failing, citation_id)
    finally:
        failing.close()

    # Neither the new Full Text nor the already-executed delete of the values stuck.
    assert _committed_pair(engine, citation_id) == ("first.pdf", "Meets all criteria.")
    assert db_session.query(models.FullTextSuggestionValue).count() == 1


def test_a_detail_read_spanning_a_pdf_replacement_returns_one_coherent_snapshot(
    authed_client, override_suggester, db_session
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf("First"), filename="first.pdf")
    generate_suggestion(authed_client, project_id, citation_id)
    engine = db_session.get_bind()
    state = {"fired": False}

    def replace_after_the_first_read_of_either_table(conn, cursor, statement, *args):
        # Commits the replacement on its own connection right after the request
        # first reads Full Text or Suggestion data, i.e. between two separate
        # reads if the endpoint makes more than one.
        reads_the_pair = "full_texts" in statement or "full_text_suggestions" in statement
        if state["fired"] or not reads_the_pair or not statement.lstrip().upper().startswith("SELECT"):
            return
        state["fired"] = True
        replacing = Session(bind=engine)
        try:
            _replace_full_text(replacing, citation_id)
        finally:
            replacing.close()

    event.listen(engine, "after_cursor_execute", replace_after_the_first_read_of_either_table)
    try:
        detail = get_detail(authed_client, project_id, citation_id)
    finally:
        event.remove(engine, "after_cursor_execute", replace_after_the_first_read_of_either_table)

    assert state["fired"]
    suggestion = detail["full_text_suggestion"]
    pair = (
        detail["full_text"]["original_filename"],
        suggestion["reason"] if suggestion else None,
    )
    assert pair in {("first.pdf", "Meets all criteria."), ("second.pdf", None)}
    if suggestion is None:
        assert detail["full_text_suggestion_needs_generation"] is True
    # The replacement did commit, so the next read is the current snapshot.
    current = get_detail(authed_client, project_id, citation_id)
    assert current["full_text"]["original_filename"] == "second.pdf"
    assert current["full_text_suggestion"] is None


def test_replacing_the_pdf_removes_the_suggestion_and_its_suggested_values(
    authed_client, override_suggester, db_session
):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    field = create_extraction_field(authed_client, project_id)
    override_suggester.extraction_values = {field["id"]: "120 patients"}
    upload_full_text(authed_client, project_id, citation_id, make_pdf("First"))
    generate_suggestion(authed_client, project_id, citation_id)
    assert db_session.query(models.FullTextSuggestionValue).count() == 1

    response = upload_full_text(authed_client, project_id, citation_id, make_pdf("Second"))

    assert response.status_code == 201
    assert db_session.query(models.FullTextSuggestion).count() == 0
    assert db_session.query(models.FullTextSuggestionValue).count() == 0


def test_replacing_the_pdf_works_when_there_is_no_suggestion_to_clear(authed_client, db_session):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    upload_full_text(authed_client, project_id, citation_id, make_pdf("First"), filename="first.pdf")

    response = upload_full_text(
        authed_client, project_id, citation_id, make_pdf("Second"), filename="second.pdf"
    )

    assert response.status_code == 201
    assert response.json()["original_filename"] == "second.pdf"
    assert db_session.query(models.FullTextSuggestion).count() == 0


def test_the_next_suggestion_reads_the_replacement_pdfs_text(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    suggester = _RecordingSuggester()
    app.dependency_overrides[get_ai_suggester] = lambda: suggester
    try:
        upload_full_text(authed_client, project_id, citation_id, make_pdf("First version"))
        generate_suggestion(authed_client, project_id, citation_id)
        upload_full_text(authed_client, project_id, citation_id, make_pdf("Second version"))
        generate_suggestion(authed_client, project_id, citation_id)
    finally:
        app.dependency_overrides.pop(get_ai_suggester, None)

    assert len(suggester.seen_texts) == 2
    assert "First version" in suggester.seen_texts[0]
    assert "Second version" in suggester.seen_texts[1]
    assert "First version" not in suggester.seen_texts[1]
