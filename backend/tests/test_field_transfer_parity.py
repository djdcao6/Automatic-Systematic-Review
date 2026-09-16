import uuid

from asr_backend import crud, duplicates, schemas
from asr_backend.citation_import import ParsedCitation

# Duplicate merge and Possible Duplicate resolution both copy a loser Citation's
# Reviewer-entered field onto the survivor through the same shared _copy_field
# helper (see duplicates.py). These tests prove that sharing: for each field
# kind, the merge path (one-sided, auto-merged) and the resolution path
# (conflicting, Reviewer picks the loser) must land the survivor on the exact
# same value for the exact same loser input.

CSV_HEADER = "title,abstract,authors,year,source,doi\n"


def create_project(authed_client, name: str = "My Review") -> str:
    response = authed_client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "solo"},
    )
    return response.json()["id"]


def upload_csv(authed_client, project_id: str, content: str):
    return authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", content, "text/csv")},
    )


def list_citations(authed_client, project_id: str) -> list[dict]:
    return authed_client.get(f"/review-projects/{project_id}/citations").json()


def list_possible_duplicates(authed_client, project_id: str) -> list[dict]:
    return authed_client.get(f"/review-projects/{project_id}/possible-duplicates").json()


def row(title: str, doi: str = "") -> str:
    return f"{title},,Author,2020,PubMed,{doi}\n"


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


def _resolve(authed_client, project_id: str, field: str, extraction_field_id: str | None):
    pd_id = list_possible_duplicates(authed_client, project_id)[0]["id"]
    authed_client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={"choices": [{"field": field, "extraction_field_id": extraction_field_id, "winner": "loser"}]},
    )


def test_screening_decision_transfers_identically_via_merge_and_resolution(authed_client, db_session):
    # Merge path: survivor has no Screening Decision, so the match merges automatically.
    merge_project_id = create_project(authed_client)
    upload_csv(authed_client, merge_project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    merge_survivor_id = list_citations(authed_client, merge_project_id)[0]["id"]
    merge_loser = _seed_unmatched_citation(db_session, merge_project_id, "Study", doi="10.1/x")
    merge_project = _get_project(db_session, merge_project_id)
    crud.upsert_screening_decision(
        db_session,
        merge_project,
        merge_loser.id,
        merge_project.owner_reviewer_id,
        schemas.ScreeningDecisionCreate(decision="exclude", reason="Loser reason"),
    )
    duplicates.process_upload_matches(db_session, merge_project, [merge_loser])
    merged_survivor = crud.get_citation(db_session, merge_project.id, uuid.UUID(merge_survivor_id))
    merge_result = (merged_survivor.owner_screening_decision.decision, merged_survivor.owner_screening_decision.reason)

    # Resolution path: survivor already has a conflicting Screening Decision, so the
    # match holds as a Possible Duplicate; the Reviewer picks the loser's value.
    resolve_project_id = create_project(authed_client)
    upload_csv(authed_client, resolve_project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    resolve_survivor_id = list_citations(authed_client, resolve_project_id)[0]["id"]
    resolve_project = _get_project(db_session, resolve_project_id)
    crud.upsert_screening_decision(
        db_session,
        resolve_project,
        uuid.UUID(resolve_survivor_id),
        resolve_project.owner_reviewer_id,
        schemas.ScreeningDecisionCreate(decision="include", reason="Survivor reason"),
    )
    resolve_loser = _seed_unmatched_citation(db_session, resolve_project_id, "Study", doi="10.1/x")
    crud.upsert_screening_decision(
        db_session,
        resolve_project,
        resolve_loser.id,
        resolve_project.owner_reviewer_id,
        schemas.ScreeningDecisionCreate(decision="exclude", reason="Loser reason"),
    )
    duplicates.process_upload_matches(db_session, resolve_project, [resolve_loser])
    _resolve(authed_client, resolve_project_id, "screening_decision", None)
    resolved_survivor = crud.get_citation(db_session, resolve_project.id, uuid.UUID(resolve_survivor_id))
    resolve_result = (
        resolved_survivor.owner_screening_decision.decision,
        resolved_survivor.owner_screening_decision.reason,
    )

    assert merge_result == ("exclude", "Loser reason") == resolve_result


def test_full_text_decision_transfers_identically_via_merge_and_resolution(authed_client, db_session):
    # Merge path: survivor has no Full-Text Decision, so the match merges automatically.
    merge_project_id = create_project(authed_client)
    upload_csv(authed_client, merge_project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    merge_survivor_id = list_citations(authed_client, merge_project_id)[0]["id"]
    merge_loser = _seed_unmatched_citation(db_session, merge_project_id, "Study", doi="10.1/x")
    merge_project = _get_project(db_session, merge_project_id)
    crud.upsert_full_text_decision(
        db_session, merge_loser.id, schemas.FullTextDecisionCreate(decision="include", reason="Meets criteria")
    )
    duplicates.process_upload_matches(db_session, merge_project, [merge_loser])
    merged_decision = crud.get_full_text_decision(db_session, uuid.UUID(merge_survivor_id))
    merge_result = (merged_decision.decision, merged_decision.reason)

    # Resolution path: survivor already has a conflicting Full-Text Decision, so the
    # match holds as a Possible Duplicate; the Reviewer picks the loser's value.
    resolve_project_id = create_project(authed_client)
    upload_csv(authed_client, resolve_project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    resolve_survivor_id = list_citations(authed_client, resolve_project_id)[0]["id"]
    crud.upsert_full_text_decision(
        db_session, uuid.UUID(resolve_survivor_id), schemas.FullTextDecisionCreate(decision="exclude", reason="Survivor call")
    )
    resolve_loser = _seed_unmatched_citation(db_session, resolve_project_id, "Study", doi="10.1/x")
    crud.upsert_full_text_decision(
        db_session, resolve_loser.id, schemas.FullTextDecisionCreate(decision="include", reason="Meets criteria")
    )
    resolve_project = _get_project(db_session, resolve_project_id)
    duplicates.process_upload_matches(db_session, resolve_project, [resolve_loser])
    _resolve(authed_client, resolve_project_id, "full_text_decision", None)
    resolved_decision = crud.get_full_text_decision(db_session, uuid.UUID(resolve_survivor_id))
    resolve_result = (resolved_decision.decision, resolved_decision.reason)

    assert merge_result == ("include", "Meets criteria") == resolve_result


def test_full_text_transfers_identically_via_merge_and_resolution(authed_client, db_session):
    # Merge path: survivor has no Full Text, so the match merges automatically.
    merge_project_id = create_project(authed_client)
    upload_csv(authed_client, merge_project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    merge_survivor_id = list_citations(authed_client, merge_project_id)[0]["id"]
    merge_loser = _seed_unmatched_citation(db_session, merge_project_id, "Study", doi="10.1/x")
    merge_project = _get_project(db_session, merge_project_id)
    crud.upsert_full_text(
        db_session,
        merge_loser.id,
        original_filename="loser.pdf",
        file_path="/tmp/loser.pdf",
        parsed_text="loser text",
        parse_status="parsed",
    )
    duplicates.process_upload_matches(db_session, merge_project, [merge_loser])
    merged_full_text = crud.get_full_text(db_session, uuid.UUID(merge_survivor_id))
    merge_result = merged_full_text.original_filename

    # Resolution path: survivor already has a Full Text (find_conflicts flags this
    # field as conflicting whenever both sides have one), so the match holds as a
    # Possible Duplicate; the Reviewer picks the loser's Full Text.
    resolve_project_id = create_project(authed_client)
    upload_csv(authed_client, resolve_project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    resolve_survivor_id = list_citations(authed_client, resolve_project_id)[0]["id"]
    crud.upsert_full_text(
        db_session,
        uuid.UUID(resolve_survivor_id),
        original_filename="survivor.pdf",
        file_path="/tmp/survivor.pdf",
        parsed_text="survivor text",
        parse_status="parsed",
    )
    resolve_loser = _seed_unmatched_citation(db_session, resolve_project_id, "Study", doi="10.1/x")
    crud.upsert_full_text(
        db_session,
        resolve_loser.id,
        original_filename="loser.pdf",
        file_path="/tmp/loser.pdf",
        parsed_text="loser text",
        parse_status="parsed",
    )
    resolve_project = _get_project(db_session, resolve_project_id)
    duplicates.process_upload_matches(db_session, resolve_project, [resolve_loser])
    _resolve(authed_client, resolve_project_id, "full_text", None)
    resolved_full_text = crud.get_full_text(db_session, uuid.UUID(resolve_survivor_id))
    resolve_result = resolved_full_text.original_filename

    assert merge_result == "loser.pdf" == resolve_result


def test_extraction_value_transfers_identically_via_merge_and_resolution(authed_client, db_session):
    # Merge path: survivor lacks this Extraction Field's value, so the match merges automatically.
    merge_project_id = create_project(authed_client)
    merge_field = authed_client.post(
        f"/review-projects/{merge_project_id}/extraction-fields",
        json={"name": "Sample size", "description": None},
    ).json()
    upload_csv(authed_client, merge_project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    merge_survivor_id = list_citations(authed_client, merge_project_id)[0]["id"]
    merge_loser = _seed_unmatched_citation(db_session, merge_project_id, "Study", doi="10.1/x")
    crud.upsert_extraction_value(
        db_session, merge_loser.id, uuid.UUID(merge_field["id"]), schemas.ExtractionValueCreate(value="120 patients")
    )
    merge_project = _get_project(db_session, merge_project_id)
    duplicates.process_upload_matches(db_session, merge_project, [merge_loser])
    merge_values = crud.get_extraction_values(db_session, uuid.UUID(merge_survivor_id))
    merge_result = merge_values[0].value

    # Resolution path: survivor already has a conflicting value for this field, so the
    # match holds as a Possible Duplicate; the Reviewer picks the loser's value.
    resolve_project_id = create_project(authed_client)
    resolve_field = authed_client.post(
        f"/review-projects/{resolve_project_id}/extraction-fields",
        json={"name": "Sample size", "description": None},
    ).json()
    upload_csv(authed_client, resolve_project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    resolve_survivor_id = list_citations(authed_client, resolve_project_id)[0]["id"]
    crud.upsert_extraction_value(
        db_session,
        uuid.UUID(resolve_survivor_id),
        uuid.UUID(resolve_field["id"]),
        schemas.ExtractionValueCreate(value="100 patients"),
    )
    resolve_loser = _seed_unmatched_citation(db_session, resolve_project_id, "Study", doi="10.1/x")
    crud.upsert_extraction_value(
        db_session, resolve_loser.id, uuid.UUID(resolve_field["id"]), schemas.ExtractionValueCreate(value="120 patients")
    )
    resolve_project = _get_project(db_session, resolve_project_id)
    duplicates.process_upload_matches(db_session, resolve_project, [resolve_loser])
    _resolve(authed_client, resolve_project_id, "extraction_value", resolve_field["id"])
    resolve_values = crud.get_extraction_values(db_session, uuid.UUID(resolve_survivor_id))
    resolve_result = resolve_values[0].value

    assert merge_result == "120 patients" == resolve_result
