import csv
import io
import uuid

from asr_backend import crud, duplicates, schemas
from asr_backend.citation_import import ParsedCitation

CSV_HEADER = "title,abstract,authors,year,source,doi\n"


def create_project(authed_client, name: str = "My Review", merge_mode: str = "combine") -> str:
    response = authed_client.post(
        "/review-projects",
        json={"name": name, "merge_mode": merge_mode, "review_mode": "solo"},
    )
    return response.json()["id"]


def upload_csv(authed_client, project_id: str, content: str):
    return authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", content, "text/csv")},
    )


def list_citations(authed_client, project_id: str) -> list[dict]:
    return authed_client.get(f"/review-projects/{project_id}/citations").json()


def row(title: str, abstract: str = "", authors: str = "Author", year: str = "2020",
        source: str = "PubMed", doi: str = "") -> str:
    return f"{title},{abstract},{authors},{year},{source},{doi}\n"


def parse_export(response) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response.text)))


# --- Matching: within batch, DOI, and title fallback ---


def test_within_batch_duplicate_rows_merge_automatically(authed_client):
    project_id = create_project(authed_client)

    response = upload_csv(
        authed_client,
        project_id,
        CSV_HEADER
        + row("Dup Study", abstract="First row's abstract")
        + row("Dup Study", abstract="Second row's abstract"),
    )

    assert response.json()["created"] == 2
    citations = list_citations(authed_client, project_id)
    assert len(citations) == 1
    # The earlier-created (first) row survives; the second is archived into it.
    assert citations[0]["abstract"] == "First row's abstract"


def test_doi_match_merges_across_uploads_even_with_different_titles(authed_client):
    project_id = create_project(authed_client)

    upload_csv(authed_client, project_id, CSV_HEADER + row("First Title", doi="10.1/x"))
    upload_csv(authed_client, project_id, CSV_HEADER + row("Totally Different Title", doi="10.1/x"))

    citations = list_citations(authed_client, project_id)
    assert len(citations) == 1
    assert citations[0]["title"] == "First Title"


def test_title_fallback_match_merges_when_neither_side_has_doi(authed_client):
    project_id = create_project(authed_client)

    upload_csv(authed_client, project_id, CSV_HEADER + row("Same Study"))
    upload_csv(authed_client, project_id, CSV_HEADER + row("  SAME Study!!  "))

    citations = list_citations(authed_client, project_id)
    assert len(citations) == 1


def test_differing_dois_do_not_match_even_with_identical_titles(authed_client):
    project_id = create_project(authed_client)

    upload_csv(authed_client, project_id, CSV_HEADER + row("Same Study", doi="10.1/a"))
    upload_csv(authed_client, project_id, CSV_HEADER + row("Same Study", doi="10.1/b"))

    citations = list_citations(authed_client, project_id)
    assert len(citations) == 2


# --- Merge Mode: bibliographic field handling ---


def test_combine_mode_gap_fills_missing_fields_and_accumulates_source(authed_client):
    project_id = create_project(authed_client, merge_mode="combine")

    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER + row("Study", abstract="", year="", source="PubMed"),
    )
    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER + row("Study", abstract="An abstract", year="2021", source="Embase"),
    )

    citations = list_citations(authed_client, project_id)
    assert len(citations) == 1
    survivor = citations[0]
    assert survivor["abstract"] == "An abstract"
    assert survivor["year"] == 2021
    assert survivor["source"] == ["PubMed", "Embase"]


def test_keep_first_mode_leaves_survivor_bibliographic_fields_untouched(authed_client):
    project_id = create_project(authed_client, merge_mode="keep_first")

    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER + row("Study", abstract="", year="", source="PubMed"),
    )
    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER + row("Study", abstract="An abstract", year="2021", source="Embase"),
    )

    citations = list_citations(authed_client, project_id)
    assert len(citations) == 1
    survivor = citations[0]
    assert survivor["abstract"] is None
    assert survivor["year"] is None
    assert survivor["source"] == ["PubMed"]


# --- Archived Citations are excluded from list, count, and export ---


def test_archived_citations_excluded_from_list_count_and_export(authed_client):
    project_id = create_project(authed_client)

    upload_csv(authed_client, project_id, CSV_HEADER + row("Dup Study") + row("Dup Study"))

    citations = list_citations(authed_client, project_id)
    assert len(citations) == 1

    detail = authed_client.get(f"/review-projects/{project_id}").json()
    assert detail["citations_needing_decision"] == 1

    export_rows = parse_export(authed_client.get(f"/review-projects/{project_id}/export"))
    assert len(export_rows) == 1


# --- Reviewer-entered data: one-sided transfer and two-sided conflict ---
#
# Fresh upload rows never carry Reviewer-entered data on their own (it's only
# ever recorded via a separate call after a Citation already exists), so a
# genuine one-sided-transfer or conflicting-pair scenario can't be produced by
# replaying upload/decision calls alone: whichever Citation is discovered as
# a duplicate is discovered the moment it's created, before it could have any
# Reviewer-entered data of its own. These tests seed the "loser" side
# directly (bypassing the upload endpoint's own matching) to simulate a
# Citation that already carries Reviewer-entered data, then invoke the same
# matching/merge step the upload endpoint calls.


def _get_project(db_session, project_id: str):
    return crud.get_review_project(db_session, uuid.UUID(project_id))


def _seed_unmatched_citation(db_session, project_id: str, title: str, doi: str | None = None):
    project = _get_project(db_session, project_id)
    [citation] = crud.create_citations(
        db_session,
        project.id,
        [
            ParsedCitation(
                title=title, abstract=None, authors=[], year=None, source=[], doi=doi
            )
        ],
    )
    return citation


def test_one_sided_transfer_of_screening_decision(authed_client, db_session):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = list_citations(authed_client, project_id)[0]["id"]

    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    project = _get_project(db_session, project_id)
    crud.upsert_screening_decision(
        db_session,
        project,
        loser.id,
        project.owner_reviewer_id,
        schemas.ScreeningDecisionCreate(decision="exclude", reason="Not relevant"),
    )

    duplicates.process_upload_matches(db_session, project, [loser])

    survivor_decision = crud.get_screening_decision(
        db_session, uuid.UUID(survivor_id), project.owner_reviewer_id
    )
    assert survivor_decision is not None
    assert survivor_decision.decision == "exclude"
    assert survivor_decision.reason == "Not relevant"

    loser_decision = crud.get_screening_decision(db_session, loser.id, project.owner_reviewer_id)
    assert loser_decision is not None
    assert loser_decision.decision == "exclude"

    citation = crud.get_citation(db_session, project.id, loser.id)
    assert citation.archived is True
    assert citation.merged_into_citation_id == uuid.UUID(survivor_id)


def test_one_sided_transfer_of_full_text_decision(authed_client, db_session):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = uuid.UUID(list_citations(authed_client, project_id)[0]["id"])

    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    project = _get_project(db_session, project_id)
    crud.replace_full_text(
        db_session,
        loser.id,
        original_filename="paper.pdf",
        file_path="/tmp/paper.pdf",
        parsed_text="parsed text",
        parse_status="parsed",
    )
    crud.upsert_full_text_decision(
        db_session, loser.id, schemas.FullTextDecisionCreate(decision="include", reason="Meets criteria")
    )

    duplicates.process_upload_matches(db_session, project, [loser])

    survivor_full_text = crud.get_full_text(db_session, survivor_id)
    assert survivor_full_text is not None
    assert survivor_full_text.original_filename == "paper.pdf"

    survivor_decision = crud.get_full_text_decision(db_session, survivor_id)
    assert survivor_decision is not None
    assert survivor_decision.decision == "include"

    loser_decision = crud.get_full_text_decision(db_session, loser.id)
    assert loser_decision is not None
    assert loser_decision.decision == "include"


def test_one_sided_transfer_of_extraction_value(authed_client, db_session):
    project_id = create_project(authed_client)
    field = authed_client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": "Sample size", "description": None},
    ).json()
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = uuid.UUID(list_citations(authed_client, project_id)[0]["id"])

    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    project = _get_project(db_session, project_id)
    crud.upsert_extraction_value(
        db_session, loser.id, uuid.UUID(field["id"]), schemas.ExtractionValueCreate(value="120 patients")
    )

    duplicates.process_upload_matches(db_session, project, [loser])

    survivor_values = crud.get_extraction_values(db_session, survivor_id)
    assert len(survivor_values) == 1
    assert survivor_values[0].value == "120 patients"

    loser_values = crud.get_extraction_values(db_session, loser.id)
    assert len(loser_values) == 1
    assert loser_values[0].value == "120 patients"


def test_two_sided_conflicting_screening_decision_is_held_as_possible_duplicate(authed_client, db_session):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = list_citations(authed_client, project_id)[0]["id"]
    authed_client.post(
        f"/review-projects/{project_id}/citations/{survivor_id}/decision",
        json={"decision": "include"},
    )

    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    project = _get_project(db_session, project_id)
    crud.upsert_screening_decision(
        db_session,
        project,
        loser.id,
        project.owner_reviewer_id,
        schemas.ScreeningDecisionCreate(decision="exclude"),
    )

    duplicates.process_upload_matches(db_session, project, [loser])

    citations = list_citations(authed_client, project_id)
    assert len(citations) == 2

    survivor = crud.get_citation(db_session, project.id, uuid.UUID(survivor_id))
    assert survivor.owner_screening_decision.decision == "include"
    loser_after = crud.get_citation(db_session, project.id, loser.id)
    assert loser_after.archived is False
    assert loser_after.owner_screening_decision.decision == "exclude"

    possible_duplicates = authed_client.get(f"/review-projects/{project_id}/possible-duplicates").json()
    assert len(possible_duplicates) == 1
    pd = possible_duplicates[0]
    assert pd["survivor"]["id"] == survivor_id
    assert pd["loser"]["id"] == str(loser.id)
    assert pd["conflicting_fields"] == [
        {"field": "screening_decision", "extraction_field_id": None, "extraction_field_name": None}
    ]
