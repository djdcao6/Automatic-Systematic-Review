import uuid

from asr_backend import crud, duplicates, schemas
from asr_backend.citation_import import ParsedCitation

CSV_HEADER = "title,abstract,authors,year,source,doi\n"


def create_project(client, name: str = "My Review", merge_mode: str = "combine") -> str:
    response = client.post("/review-projects", json={"name": name, "merge_mode": merge_mode})
    return response.json()["id"]


def upload_csv(client, project_id: str, content: str):
    return client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", content, "text/csv")},
    )


def list_citations(client, project_id: str) -> list[dict]:
    return client.get(f"/review-projects/{project_id}/citations").json()


def list_possible_duplicates(client, project_id: str) -> list[dict]:
    return client.get(f"/review-projects/{project_id}/possible-duplicates").json()


def row(title: str, abstract: str = "", authors: str = "Author", year: str = "2020",
        source: str = "PubMed", doi: str = "") -> str:
    return f"{title},{abstract},{authors},{year},{source},{doi}\n"


def _get_project(db_session, project_id: str):
    return crud.get_review_project(db_session, uuid.UUID(project_id))


def _seed_unmatched_citation(db_session, project_id: str, title: str, doi: str | None = None):
    project = _get_project(db_session, project_id)
    [citation] = crud.create_citations(
        db_session,
        project.id,
        [ParsedCitation(title=title, abstract=None, authors=[], year=None, source=[], doi=doi)],
    )
    return citation


def _make_conflicting_pair(client, db_session, project_id: str):
    """Survivor (earlier-created, Include) vs. loser (later-created, Exclude)."""
    upload_csv(client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = list_citations(client, project_id)[0]["id"]
    client.post(
        f"/review-projects/{project_id}/citations/{survivor_id}/decision",
        json={"decision": "include", "reason": "Survivor reason"},
    )

    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    project = _get_project(db_session, project_id)
    crud.upsert_screening_decision(
        db_session,
        project,
        loser.id,
        schemas.ScreeningDecisionCreate(decision="exclude", reason="Loser reason"),
    )

    duplicates.process_upload_matches(db_session, project, [loser])
    return survivor_id, str(loser.id)


def _get_pending_id(client, project_id: str) -> str:
    return list_possible_duplicates(client, project_id)[0]["id"]


# --- Resolving ---


def test_resolving_applies_chosen_value_and_merges_everything_else(client, db_session):
    project_id = create_project(client, merge_mode="combine")
    survivor_id, loser_id = _make_conflicting_pair(client, db_session, project_id)
    pd_id = _get_pending_id(client, project_id)

    response = client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={
            "choices": [
                {"field": "screening_decision", "extraction_field_id": None, "winner": "loser"}
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["id"] == survivor_id

    citations = list_citations(client, project_id)
    assert len(citations) == 1
    assert citations[0]["id"] == survivor_id

    project = _get_project(db_session, project_id)
    survivor = crud.get_citation(db_session, project.id, uuid.UUID(survivor_id))
    assert survivor.screening_decision.decision == "exclude"
    assert survivor.screening_decision.reason == "Loser reason"
    assert survivor.archived is False

    loser = crud.get_citation(db_session, project.id, uuid.UUID(loser_id))
    assert loser.archived is True
    assert loser.merged_into_citation_id == uuid.UUID(survivor_id)

    assert list_possible_duplicates(client, project_id) == []


def test_resolving_keeps_survivor_value_when_survivor_side_chosen(client, db_session):
    project_id = create_project(client)
    survivor_id, _ = _make_conflicting_pair(client, db_session, project_id)
    pd_id = _get_pending_id(client, project_id)

    client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={
            "choices": [
                {"field": "screening_decision", "extraction_field_id": None, "winner": "survivor"}
            ]
        },
    )

    project = _get_project(db_session, project_id)
    survivor = crud.get_citation(db_session, project.id, uuid.UUID(survivor_id))
    assert survivor.screening_decision.decision == "include"
    assert survivor.screening_decision.reason == "Survivor reason"


def test_resolving_extraction_value_conflict_per_field(client, db_session):
    project_id = create_project(client)
    field = client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": "Sample size", "description": None},
    ).json()

    upload_csv(client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = list_citations(client, project_id)[0]["id"]
    project = _get_project(db_session, project_id)
    crud.upsert_extraction_value(
        db_session,
        uuid.UUID(survivor_id),
        uuid.UUID(field["id"]),
        schemas.ExtractionValueCreate(value="100 patients"),
    )

    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    crud.upsert_extraction_value(
        db_session, loser.id, uuid.UUID(field["id"]), schemas.ExtractionValueCreate(value="120 patients")
    )

    duplicates.process_upload_matches(db_session, project, [loser])

    possible_duplicates = list_possible_duplicates(client, project_id)
    assert len(possible_duplicates) == 1
    conflicts = possible_duplicates[0]["conflicting_fields"]
    assert conflicts == [
        {"field": "extraction_value", "extraction_field_id": field["id"], "extraction_field_name": "Sample size"}
    ]

    client.post(
        f"/review-projects/{project_id}/possible-duplicates/{possible_duplicates[0]['id']}/resolve",
        json={
            "choices": [
                {"field": "extraction_value", "extraction_field_id": field["id"], "winner": "loser"}
            ]
        },
    )

    values = crud.get_extraction_values(db_session, uuid.UUID(survivor_id))
    assert len(values) == 1
    assert values[0].value == "120 patients"


def test_resolving_with_mismatched_choices_is_rejected(client, db_session):
    project_id = create_project(client)
    _, _ = _make_conflicting_pair(client, db_session, project_id)
    pd_id = _get_pending_id(client, project_id)

    response = client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={"choices": []},
    )
    assert response.status_code == 422

    # Still pending — a rejected resolve doesn't consume the hold.
    assert len(list_possible_duplicates(client, project_id)) == 1


def test_resolving_an_already_settled_possible_duplicate_is_rejected(client, db_session):
    project_id = create_project(client)
    _, _ = _make_conflicting_pair(client, db_session, project_id)
    pd_id = _get_pending_id(client, project_id)

    client.post(f"/review-projects/{project_id}/possible-duplicates/{pd_id}/dismiss")

    response = client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={
            "choices": [
                {"field": "screening_decision", "extraction_field_id": None, "winner": "survivor"}
            ]
        },
    )
    assert response.status_code == 409


# --- Dismissing ---


def test_dismissing_leaves_both_citations_independent_and_active(client, db_session):
    project_id = create_project(client)
    survivor_id, loser_id = _make_conflicting_pair(client, db_session, project_id)
    pd_id = _get_pending_id(client, project_id)

    response = client.post(f"/review-projects/{project_id}/possible-duplicates/{pd_id}/dismiss")
    assert response.status_code == 204

    citations = list_citations(client, project_id)
    assert {c["id"] for c in citations} == {survivor_id, loser_id}

    project = _get_project(db_session, project_id)
    assert crud.get_citation(db_session, project.id, uuid.UUID(survivor_id)).archived is False
    assert crud.get_citation(db_session, project.id, uuid.UUID(loser_id)).archived is False

    assert list_possible_duplicates(client, project_id) == []


def test_dismissed_pair_survives_a_subsequent_upload_without_re_flagging(client, db_session):
    project_id = create_project(client)
    survivor_id, loser_id = _make_conflicting_pair(client, db_session, project_id)
    pd_id = _get_pending_id(client, project_id)
    client.post(f"/review-projects/{project_id}/possible-duplicates/{pd_id}/dismiss")

    upload_csv(client, project_id, CSV_HEADER + row("Unrelated Study"))

    citations = list_citations(client, project_id)
    assert {c["id"] for c in citations} == {survivor_id, loser_id, citations[2]["id"]}
    assert len(citations) == 3
    assert list_possible_duplicates(client, project_id) == []


# --- Exclusion from matching while unresolved ---


def test_third_upload_matching_a_held_citation_is_left_unmerged_against_it(client, db_session):
    project_id = create_project(client)
    survivor_id, loser_id = _make_conflicting_pair(client, db_session, project_id)
    # The pair is now an unresolved Possible Duplicate; both are on hold.

    upload_csv(client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))

    citations = list_citations(client, project_id)
    assert len(citations) == 3
    ids = {c["id"] for c in citations}
    assert survivor_id in ids
    assert loser_id in ids

    # No new Possible Duplicate was created for the third citation either.
    assert len(list_possible_duplicates(client, project_id)) == 1

    project = _get_project(db_session, project_id)
    third = next(c for c in citations if c["id"] not in (survivor_id, loser_id))
    third_citation = crud.get_citation(db_session, project.id, uuid.UUID(third["id"]))
    assert third_citation.archived is False
    assert third_citation.merged_into_citation_id is None
