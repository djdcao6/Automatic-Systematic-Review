import uuid

from conftest import auth_headers_for

from asr_backend import crud, duplicates, models, schemas
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


def list_possible_duplicates(authed_client, project_id: str) -> list[dict]:
    return authed_client.get(f"/review-projects/{project_id}/possible-duplicates").json()


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


def _make_conflicting_pair(authed_client, db_session, project_id: str):
    """Survivor (earlier-created, Include) vs. loser (later-created, Exclude)."""
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = list_citations(authed_client, project_id)[0]["id"]
    authed_client.post(
        f"/review-projects/{project_id}/citations/{survivor_id}/decision",
        json={"decision": "include", "reason": "Survivor reason"},
    )

    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    project = _get_project(db_session, project_id)
    crud.upsert_screening_decision(
        db_session,
        project,
        loser.id,
        project.owner_reviewer_id,
        schemas.ScreeningDecisionCreate(decision="exclude", reason="Loser reason"),
    )

    duplicates.process_upload_matches(db_session, project, [loser])
    return survivor_id, str(loser.id)


def _get_pending_id(authed_client, project_id: str) -> str:
    return list_possible_duplicates(authed_client, project_id)[0]["id"]


# --- Resolving ---


def test_resolving_applies_chosen_value_and_merges_everything_else(authed_client, db_session):
    project_id = create_project(authed_client, merge_mode="combine")
    survivor_id, loser_id = _make_conflicting_pair(authed_client, db_session, project_id)
    pd_id = _get_pending_id(authed_client, project_id)

    response = authed_client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={
            "choices": [
                {"field": "screening_decision", "extraction_field_id": None, "winner": "loser"}
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["id"] == survivor_id

    citations = list_citations(authed_client, project_id)
    assert len(citations) == 1
    assert citations[0]["id"] == survivor_id

    project = _get_project(db_session, project_id)
    survivor = crud.get_citation(db_session, project.id, uuid.UUID(survivor_id))
    assert survivor.owner_screening_decision.decision == "exclude"
    assert survivor.owner_screening_decision.reason == "Loser reason"
    assert survivor.archived is False

    loser = crud.get_citation(db_session, project.id, uuid.UUID(loser_id))
    assert loser.archived is True
    assert loser.merged_into_citation_id == uuid.UUID(survivor_id)

    assert list_possible_duplicates(authed_client, project_id) == []


def test_resolving_keeps_survivor_value_when_survivor_side_chosen(authed_client, db_session):
    project_id = create_project(authed_client)
    survivor_id, _ = _make_conflicting_pair(authed_client, db_session, project_id)
    pd_id = _get_pending_id(authed_client, project_id)

    authed_client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={
            "choices": [
                {"field": "screening_decision", "extraction_field_id": None, "winner": "survivor"}
            ]
        },
    )

    project = _get_project(db_session, project_id)
    survivor = crud.get_citation(db_session, project.id, uuid.UUID(survivor_id))
    assert survivor.owner_screening_decision.decision == "include"
    assert survivor.owner_screening_decision.reason == "Survivor reason"


def test_resolving_extraction_value_conflict_per_field(authed_client, db_session):
    project_id = create_project(authed_client)
    field = authed_client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": "Sample size", "description": None},
    ).json()

    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = list_citations(authed_client, project_id)[0]["id"]
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

    possible_duplicates = list_possible_duplicates(authed_client, project_id)
    assert len(possible_duplicates) == 1
    conflicts = possible_duplicates[0]["conflicting_fields"]
    assert conflicts == [
        {"field": "extraction_value", "extraction_field_id": field["id"], "extraction_field_name": "Sample size"}
    ]

    authed_client.post(
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


def test_resolving_with_mismatched_choices_is_rejected(authed_client, db_session):
    project_id = create_project(authed_client)
    _, _ = _make_conflicting_pair(authed_client, db_session, project_id)
    pd_id = _get_pending_id(authed_client, project_id)

    response = authed_client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={"choices": []},
    )
    assert response.status_code == 422

    # Still pending — a rejected resolve doesn't consume the hold.
    assert len(list_possible_duplicates(authed_client, project_id)) == 1


def test_resolving_an_already_settled_possible_duplicate_is_rejected(authed_client, db_session):
    project_id = create_project(authed_client)
    _, _ = _make_conflicting_pair(authed_client, db_session, project_id)
    pd_id = _get_pending_id(authed_client, project_id)

    authed_client.post(f"/review-projects/{project_id}/possible-duplicates/{pd_id}/dismiss")

    response = authed_client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={
            "choices": [
                {"field": "screening_decision", "extraction_field_id": None, "winner": "survivor"}
            ]
        },
    )
    assert response.status_code == 409


# --- Dismissing ---


def test_dismissing_leaves_both_citations_independent_and_active(authed_client, db_session):
    project_id = create_project(authed_client)
    survivor_id, loser_id = _make_conflicting_pair(authed_client, db_session, project_id)
    pd_id = _get_pending_id(authed_client, project_id)

    response = authed_client.post(f"/review-projects/{project_id}/possible-duplicates/{pd_id}/dismiss")
    assert response.status_code == 204

    citations = list_citations(authed_client, project_id)
    assert {c["id"] for c in citations} == {survivor_id, loser_id}

    project = _get_project(db_session, project_id)
    assert crud.get_citation(db_session, project.id, uuid.UUID(survivor_id)).archived is False
    assert crud.get_citation(db_session, project.id, uuid.UUID(loser_id)).archived is False

    assert list_possible_duplicates(authed_client, project_id) == []


def test_dismissed_pair_survives_a_subsequent_upload_without_re_flagging(authed_client, db_session):
    project_id = create_project(authed_client)
    survivor_id, loser_id = _make_conflicting_pair(authed_client, db_session, project_id)
    pd_id = _get_pending_id(authed_client, project_id)
    authed_client.post(f"/review-projects/{project_id}/possible-duplicates/{pd_id}/dismiss")

    upload_csv(authed_client, project_id, CSV_HEADER + row("Unrelated Study"))

    citations = list_citations(authed_client, project_id)
    assert {c["id"] for c in citations} == {survivor_id, loser_id, citations[2]["id"]}
    assert len(citations) == 3
    assert list_possible_duplicates(authed_client, project_id) == []


# --- Exclusion from matching while unresolved ---


def test_third_upload_matching_a_held_citation_is_left_unmerged_against_it(authed_client, db_session):
    project_id = create_project(authed_client)
    survivor_id, loser_id = _make_conflicting_pair(authed_client, db_session, project_id)
    # The pair is now an unresolved Possible Duplicate; both are on hold.

    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))

    citations = list_citations(authed_client, project_id)
    assert len(citations) == 3
    ids = {c["id"] for c in citations}
    assert survivor_id in ids
    assert loser_id in ids

    # No new Possible Duplicate was created for the third citation either.
    assert len(list_possible_duplicates(authed_client, project_id)) == 1

    project = _get_project(db_session, project_id)
    third = next(c for c in citations if c["id"] not in (survivor_id, loser_id))
    third_citation = crud.get_citation(db_session, project.id, uuid.UUID(third["id"]))
    assert third_citation.archived is False
    assert third_citation.merged_into_citation_id is None


# --- Dual mode: per-citation blinding (#54, ADR 0006) ----------------------------------


def _dual_pending_pair(client, db_session):
    """A dual project whose Possible Duplicate pair the Owner has already screened
    (survivor include, loser exclude), and a Co-Reviewer who has decided nothing."""
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "Dual", "merge_mode": "combine", "review_mode": "dual"},
        headers=owner_headers,
    ).json()["id"]
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    co_reviewer_headers = {
        "Authorization": "Bearer "
        + client.post(
            f"/invitations/{token}/accept-register",
            json={"email": "co-reviewer@example.com", "password": "correcthorse", "ai_consent": True},
        ).json()["access_token"]
    }
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("c.csv", CSV_HEADER + row("Study", doi="10.1/x"), "text/csv")},
        headers=owner_headers,
    )
    survivor_id = client.get(
        f"/review-projects/{project_id}/citations", headers=owner_headers
    ).json()[0]["id"]
    client.post(
        f"/review-projects/{project_id}/citations/{survivor_id}/decision",
        json={"decision": "include", "reason": "Survivor reason"},
        headers=owner_headers,
    )
    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    project = _get_project(db_session, project_id)
    crud.upsert_screening_decision(
        db_session,
        project,
        loser.id,
        project.owner_reviewer_id,
        schemas.ScreeningDecisionCreate(decision="exclude", reason="Loser reason"),
    )
    duplicates.process_upload_matches(db_session, project, [loser])
    return project_id, survivor_id, str(loser.id), owner_headers, co_reviewer_headers


def _screening_decisions(client, project_id, headers) -> tuple[dict | None, dict | None]:
    [possible_duplicate] = client.get(
        f"/review-projects/{project_id}/possible-duplicates", headers=headers
    ).json()
    return (
        possible_duplicate["survivor"]["screening_decision"],
        possible_duplicate["loser"]["screening_decision"],
    )


def test_a_reviewer_with_no_decision_on_either_citation_sees_no_screening_decision(
    client, db_session
):
    project_id, _, _, _, co_reviewer_headers = _dual_pending_pair(client, db_session)

    survivor, loser = _screening_decisions(client, project_id, co_reviewer_headers)

    assert survivor is None
    assert loser is None


def test_the_owner_who_has_decided_both_citations_sees_both_decisions(client, db_session):
    project_id, _, _, owner_headers, _ = _dual_pending_pair(client, db_session)

    survivor, loser = _screening_decisions(client, project_id, owner_headers)

    assert (survivor["decision"], loser["decision"]) == ("include", "exclude")


def test_blinding_in_possible_duplicates_is_per_citation(client, db_session):
    project_id, survivor_id, _, _, co_reviewer_headers = _dual_pending_pair(client, db_session)
    client.post(
        f"/review-projects/{project_id}/citations/{survivor_id}/decision",
        json={"decision": "include"},
        headers=co_reviewer_headers,
    )

    survivor, loser = _screening_decisions(client, project_id, co_reviewer_headers)

    assert survivor["decision"] == "include"
    assert loser is None


def test_a_reviewer_who_has_decided_a_citation_sees_the_owners_decision_on_it(
    client, db_session
):
    project_id, survivor_id, loser_id, _, co_reviewer_headers = _dual_pending_pair(
        client, db_session
    )
    for citation_id in (survivor_id, loser_id):
        client.post(
            f"/review-projects/{project_id}/citations/{citation_id}/decision",
            json={"decision": "maybe"},
            headers=co_reviewer_headers,
        )

    survivor, loser = _screening_decisions(client, project_id, co_reviewer_headers)

    assert (survivor["decision"], loser["decision"]) == ("include", "exclude")


def test_solo_possible_duplicates_still_show_the_screening_decisions(authed_client, db_session):
    project_id = create_project(authed_client)
    _make_conflicting_pair(authed_client, db_session, project_id)

    [possible_duplicate] = list_possible_duplicates(authed_client, project_id)

    assert possible_duplicate["survivor"]["screening_decision"]["decision"] == "include"
    assert possible_duplicate["loser"]["screening_decision"]["decision"] == "exclude"


# --- Copying a legacy Full-Text Exclude that has no reason (#66) -------------------------


def _add_full_text_decision(db_session, citation_id, decision: str, reason: str | None) -> None:
    db_session.add(
        models.FullTextDecision(
            citation_id=uuid.UUID(str(citation_id)), decision=decision, reason=reason
        )
    )
    db_session.commit()


def test_merging_copies_a_legacy_full_text_exclude_that_has_no_reason(authed_client, db_session):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = list_citations(authed_client, project_id)[0]["id"]
    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    _add_full_text_decision(db_session, loser.id, "exclude", None)

    duplicates.process_upload_matches(db_session, _get_project(db_session, project_id), [loser])

    survivor = crud.get_citation(
        db_session, _get_project(db_session, project_id).id, uuid.UUID(survivor_id)
    )
    assert survivor.full_text_decision.decision == "exclude"
    assert survivor.full_text_decision.reason is None


def test_resolving_can_pick_a_legacy_full_text_exclude_that_has_no_reason(
    authed_client, db_session
):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    survivor_id = list_citations(authed_client, project_id)[0]["id"]
    _add_full_text_decision(db_session, survivor_id, "include", None)
    loser = _seed_unmatched_citation(db_session, project_id, "Study", doi="10.1/x")
    _add_full_text_decision(db_session, loser.id, "exclude", None)
    duplicates.process_upload_matches(db_session, _get_project(db_session, project_id), [loser])
    pd_id = _get_pending_id(authed_client, project_id)

    response = authed_client.post(
        f"/review-projects/{project_id}/possible-duplicates/{pd_id}/resolve",
        json={
            "choices": [
                {"field": "full_text_decision", "extraction_field_id": None, "winner": "loser"}
            ]
        },
    )

    assert response.status_code == 200
    db_session.expire_all()
    survivor = crud.get_citation(
        db_session, _get_project(db_session, project_id).id, uuid.UUID(survivor_id)
    )
    assert survivor.full_text_decision.decision == "exclude"
    assert survivor.full_text_decision.reason is None
