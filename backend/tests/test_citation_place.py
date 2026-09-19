"""A Citation's place in its Review Project's list, for the screening folio.

The detail endpoint reports where the Citation sits among the project's active
Citations and which ones are either side of it, so the screening page does not
have to download the whole list (abstracts included) to draw "412 of 1,860" and
its Previous/Next links.
"""

import uuid
from datetime import UTC, datetime

import pytest

from asr_backend import models
from asr_backend.ai_suggestion import SuggestionResult, get_ai_suggester
from asr_backend.main import app

CSV_HEADER = "title,abstract,authors,year,source\n"


def _row(title: str) -> str:
    return f"{title},An abstract,Author,2020,PubMed\n"


class _FakeSuggester:
    async def suggest_screening_decision(self, **kwargs) -> SuggestionResult:
        return SuggestionResult(decision="include", reason="Matches criteria.")


@pytest.fixture(autouse=True)
def _no_real_ai_calls():
    app.dependency_overrides[get_ai_suggester] = lambda: _FakeSuggester()
    yield
    app.dependency_overrides.pop(get_ai_suggester, None)


def _create_project(client, name: str = "My Review") -> str:
    return client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "solo"},
    ).json()["id"]


def _upload(client, project_id: str, *titles: str) -> None:
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", CSV_HEADER + "".join(_row(t) for t in titles), "text/csv")},
    )


def _listed_ids(client, project_id: str) -> list[str]:
    return [c["id"] for c in client.get(f"/review-projects/{project_id}/citations").json()]


def _detail(client, project_id: str, citation_id: str) -> dict:
    response = client.get(f"/review-projects/{project_id}/citations/{citation_id}")
    assert response.status_code == 200
    return response.json()


def test_reports_position_total_and_both_neighbours_for_a_middle_citation(authed_client):
    project_id = _create_project(authed_client)
    _upload(authed_client, project_id, "One", "Two", "Three")
    first, middle, last = _listed_ids(authed_client, project_id)

    detail = _detail(authed_client, project_id, middle)

    assert detail["position"] == 2
    assert detail["total"] == 3
    assert detail["previous_citation_id"] == first
    assert detail["next_citation_id"] == last


def test_the_first_citation_has_no_previous_and_the_last_has_no_next(authed_client):
    project_id = _create_project(authed_client)
    _upload(authed_client, project_id, "One", "Two", "Three")
    first, middle, last = _listed_ids(authed_client, project_id)

    first_detail = _detail(authed_client, project_id, first)
    last_detail = _detail(authed_client, project_id, last)

    assert (first_detail["position"], first_detail["previous_citation_id"]) == (1, None)
    assert first_detail["next_citation_id"] == middle
    assert (last_detail["position"], last_detail["next_citation_id"]) == (3, None)
    assert last_detail["previous_citation_id"] == middle


def test_a_lone_citation_has_a_place_but_no_neighbours(authed_client):
    project_id = _create_project(authed_client)
    _upload(authed_client, project_id, "Only")
    [only] = _listed_ids(authed_client, project_id)

    detail = _detail(authed_client, project_id, only)

    assert detail["position"] == 1
    assert detail["total"] == 1
    assert detail["previous_citation_id"] is None
    assert detail["next_citation_id"] is None


def test_positions_follow_the_order_of_the_citation_list(authed_client):
    project_id = _create_project(authed_client)
    _upload(authed_client, project_id, "One", "Two")
    _upload(authed_client, project_id, "Three", "Four")
    listed = _listed_ids(authed_client, project_id)

    positions = [_detail(authed_client, project_id, cid)["position"] for cid in listed]

    assert positions == [1, 2, 3, 4]


def test_citations_created_at_the_same_instant_keep_one_stable_order(authed_client, db_session):
    """A batch upload can stamp several rows with the same time; without a
    tie-break the list, and so every position and neighbour, is undefined."""
    project_id = _create_project(authed_client)
    _upload(authed_client, project_id, "One", "Two", "Three", "Four")
    db_session.query(models.Citation).update(
        {models.Citation.created_at: datetime(2026, 1, 1, tzinfo=UTC)}
    )
    db_session.commit()

    listed = _listed_ids(authed_client, project_id)
    details = [_detail(authed_client, project_id, cid) for cid in listed]

    assert listed == sorted(listed, key=uuid.UUID)
    assert [d["position"] for d in details] == [1, 2, 3, 4]
    assert [d["next_citation_id"] for d in details] == [*listed[1:], None]
    assert [d["previous_citation_id"] for d in details] == [None, *listed[:-1]]


def test_archived_citations_are_not_counted_or_linked(authed_client):
    project_id = _create_project(authed_client)
    _upload(authed_client, project_id, "Dup Study", "Dup Study", "Other Study")
    survivor, other = _listed_ids(authed_client, project_id)

    survivor_detail = _detail(authed_client, project_id, survivor)
    other_detail = _detail(authed_client, project_id, other)

    assert survivor_detail["total"] == 2
    assert survivor_detail["next_citation_id"] == other
    assert other_detail["position"] == 2
    assert other_detail["previous_citation_id"] == survivor


def test_an_archived_citation_has_no_position_and_no_neighbours(authed_client, db_session):
    project_id = _create_project(authed_client)
    _upload(authed_client, project_id, "Dup Study", "Dup Study", "Other Study")
    archived = db_session.query(models.Citation).filter_by(archived=True).one()

    detail = _detail(authed_client, project_id, str(archived.id))

    assert detail["position"] is None
    assert detail["total"] == 2
    assert detail["previous_citation_id"] is None
    assert detail["next_citation_id"] is None


def test_other_review_projects_citations_do_not_count(authed_client):
    project_id = _create_project(authed_client, "First Review")
    other_project_id = _create_project(authed_client, "Second Review")
    _upload(authed_client, project_id, "One", "Two")
    _upload(authed_client, other_project_id, "Three", "Four", "Five")
    [_, second] = _listed_ids(authed_client, project_id)

    detail = _detail(authed_client, project_id, second)

    assert detail["total"] == 2
    assert detail["position"] == 2
    assert detail["next_citation_id"] is None
