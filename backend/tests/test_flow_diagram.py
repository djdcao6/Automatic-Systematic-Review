import io
import uuid

import pymupdf
from conftest import auth_headers_for

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


def get_flow_diagram(authed_client, project_id: str) -> dict:
    response = authed_client.get(f"/review-projects/{project_id}/flow-diagram")
    assert response.status_code == 200
    return response.json()


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


def _make_pdf(text: str = "Sample paper text") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def record_screening_decision(authed_client, project_id: str, citation_id: str, decision: str, reason: str | None = None) -> None:
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": decision, "reason": reason},
    )


def attach_full_text(authed_client, project_id: str, citation_id: str) -> None:
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": ("paper.pdf", io.BytesIO(_make_pdf()), "application/pdf")},
    )


def record_full_text_decision(
    authed_client, project_id: str, citation_id: str, decision: str, reason: str | None = None
) -> None:
    response = authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": decision, "reason": reason},
    )
    assert response.status_code == 200


def set_exclusion_rules(authed_client, project_id: str, exclusion_rules: list[str]) -> None:
    authed_client.put(
        f"/review-projects/{project_id}/criteria",
        json={
            "population": None,
            "intervention": None,
            "comparison": None,
            "outcome": None,
            "exclusion_rules": exclusion_rules,
            "notes": None,
        },
    )


def test_identification_counts_are_per_source_and_precede_deduplication(authed_client):
    project_id = create_project(authed_client)
    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER
        + row("Study A", source="PubMed", doi="10.1/a")
        + row("Study B", source="Embase", doi="10.1/b"),
    )

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["identification_counts"] == {"PubMed": 1, "Embase": 1}


def test_duplicate_merged_away_from_one_source_still_counts_under_its_own_source(authed_client):
    project_id = create_project(authed_client)
    # Same DOI -> automatic merge, no conflicting reviewer data.
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", source="PubMed", doi="10.1/x"))
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", source="Embase", doi="10.1/x"))
    # The merge actually happened -- confirm before asserting on the funnel.
    assert len(list_citations(authed_client, project_id)) == 1

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["identification_counts"] == {"PubMed": 1, "Embase": 1}
    assert diagram["duplicates_removed"] == 1


def test_duplicates_removed_excludes_pending_possible_duplicates(authed_client, db_session):
    project_id = create_project(authed_client)
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

    possible_duplicates = authed_client.get(
        f"/review-projects/{project_id}/possible-duplicates"
    ).json()
    assert len(possible_duplicates) == 1

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["duplicates_removed"] == 0


def test_duplicates_removed_excludes_dismissed_possible_duplicates(authed_client, db_session):
    project_id = create_project(authed_client)
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
    possible_duplicate_id = authed_client.get(
        f"/review-projects/{project_id}/possible-duplicates"
    ).json()[0]["id"]
    authed_client.post(
        f"/review-projects/{project_id}/possible-duplicates/{possible_duplicate_id}/dismiss"
    )

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["duplicates_removed"] == 0


def test_screened_excluded_and_pending_counts_reflect_only_decided_citations(authed_client):
    project_id = create_project(authed_client)
    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER
        + row("Included Study")
        + row("Excluded Study")
        + row("Maybe Study")
        + row("Undecided Study"),
    )
    citations = {c["title"]: c["id"] for c in list_citations(authed_client, project_id)}
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citations['Included Study']}/decision",
        json={"decision": "include"},
    )
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citations['Excluded Study']}/decision",
        json={"decision": "exclude", "reason": "Wrong population"},
    )
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citations['Maybe Study']}/decision",
        json={"decision": "maybe"},
    )

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["screened"] == 3
    assert diagram["excluded"] == 1
    assert diagram["pending"] == 1


def test_archived_duplicate_citation_is_not_counted_in_screened_excluded_or_pending(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study", doi="10.1/x"))
    assert len(list_citations(authed_client, project_id)) == 1

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["screened"] == 0
    assert diagram["excluded"] == 0
    assert diagram["pending"] == 1


def _create_dual_project(client, headers, name: str = "Dual Review") -> str:
    return client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": "dual"},
        headers=headers,
    ).json()["id"]


def _add_co_reviewer(client, owner_headers, project_id: str, email: str = "co-reviewer@example.com"):
    token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    access_token = client.post(
        f"/invitations/{token}/accept-register",
        json={"email": email, "password": "correcthorse"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def _upload_citation(client, headers, project_id: str) -> str:
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", CSV_HEADER + row("Study"), "text/csv")},
        headers=headers,
    )
    citations = client.get(f"/review-projects/{project_id}/citations", headers=headers).json()
    return citations[-1]["id"]


def _record_decision(client, project_id, citation_id, headers, decision, reason=None) -> None:
    client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": decision, "reason": reason},
        headers=headers,
    )


def test_dual_project_conflict_resolution_feeds_the_funnel(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    co_reviewer_headers = _add_co_reviewer(client, owner_headers, project_id)
    citation_id = _upload_citation(client, owner_headers, project_id)
    _record_decision(client, project_id, citation_id, owner_headers, "include")
    _record_decision(client, project_id, citation_id, co_reviewer_headers, "exclude")

    diagram = client.get(
        f"/review-projects/{project_id}/flow-diagram", headers=owner_headers
    ).json()
    # Neither raw decision counts until the Owner resolves the Conflict.
    assert diagram["screened"] == 0
    assert diagram["pending"] == 1

    conflict_id = client.get(
        f"/review-projects/{project_id}/conflicts", headers=owner_headers
    ).json()[0]["id"]
    client.post(
        f"/review-projects/{project_id}/conflicts/{conflict_id}/resolve",
        json={"decision": "exclude", "reason": "Owner's final call"},
        headers=owner_headers,
    )

    diagram = client.get(
        f"/review-projects/{project_id}/flow-diagram", headers=owner_headers
    ).json()
    assert diagram["screened"] == 1
    assert diagram["excluded"] == 1
    assert diagram["pending"] == 0


def test_flow_diagram_includes_criteria(authed_client):
    project_id = create_project(authed_client)
    authed_client.put(
        f"/review-projects/{project_id}/criteria",
        json={
            "population": "Adults with type 2 diabetes",
            "intervention": "Metformin",
            "comparison": "Placebo",
            "outcome": "HbA1c reduction",
            "exclusion_rules": ["Non-English", "Case reports"],
            "notes": "Focus on RCTs only",
        },
    )

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["criteria"]["population"] == "Adults with type 2 diabetes"
    assert diagram["criteria"]["exclusion_rules"] == ["Non-English", "Case reports"]


def test_flow_diagram_criteria_is_null_when_none_saved(authed_client):
    project_id = create_project(authed_client)

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["criteria"] is None


def test_flow_diagram_for_missing_review_project(authed_client):
    response = authed_client.get(
        "/review-projects/00000000-0000-0000-0000-000000000000/flow-diagram"
    )

    assert response.status_code == 404


def test_flow_diagram_rejects_non_owner_co_reviewer(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    other_headers = auth_headers_for(client, "someone-else@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
        headers=owner_headers,
    ).json()["id"]

    response = client.get(
        f"/review-projects/{project_id}/flow-diagram", headers=other_headers
    )

    assert response.status_code == 403


def test_flow_diagram_rejects_missing_token(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
        headers=owner_headers,
    ).json()["id"]

    response = client.get(f"/review-projects/{project_id}/flow-diagram")

    assert response.status_code == 401


def test_flow_diagram_allows_co_reviewer(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    co_reviewer_headers = _add_co_reviewer(client, owner_headers, project_id)

    response = client.get(
        f"/review-projects/{project_id}/flow-diagram", headers=co_reviewer_headers
    )

    assert response.status_code == 200


def test_full_text_excluded_counts_are_itemized_by_reason(authed_client):
    project_id = create_project(authed_client)
    set_exclusion_rules(authed_client, project_id, ["Wrong population", "Not RCT"])
    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER + row("Study A") + row("Study B") + row("Study C"),
    )
    citations = {c["title"]: c["id"] for c in list_citations(authed_client, project_id)}
    for citation_id in citations.values():
        record_screening_decision(authed_client, project_id, citation_id, "include")
        attach_full_text(authed_client, project_id, citation_id)
    record_full_text_decision(
        authed_client, project_id, citations["Study A"], "exclude", "Wrong population"
    )
    record_full_text_decision(
        authed_client, project_id, citations["Study B"], "exclude", "Wrong population"
    )
    record_full_text_decision(authed_client, project_id, citations["Study C"], "exclude", "Not RCT")

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["full_text_excluded_by_reason"] == {"Wrong population": 2, "Not RCT": 1}
    assert diagram["full_text_assessed"] == 3
    assert diagram["full_text_included"] == 0
    assert diagram["full_text_pending"] == 0


def test_full_text_funnel_scoped_to_include_and_maybe_screening_decisions(authed_client):
    project_id = create_project(authed_client)
    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER + row("Included Study") + row("Maybe Study") + row("Excluded Study"),
    )
    citations = {c["title"]: c["id"] for c in list_citations(authed_client, project_id)}
    record_screening_decision(authed_client, project_id, citations["Included Study"], "include")
    record_screening_decision(authed_client, project_id, citations["Maybe Study"], "maybe")
    record_screening_decision(
        authed_client, project_id, citations["Excluded Study"], "exclude", "Wrong population"
    )

    diagram = get_flow_diagram(authed_client, project_id)

    # Only the Include and Maybe Citations enter the full-text funnel, both
    # still pending since neither has a Full-Text Decision recorded yet --
    # the Excluded Citation never counts here at all.
    assert diagram["full_text_pending"] == 2
    assert diagram["full_text_assessed"] == 0
    assert diagram["full_text_included"] == 0
    assert diagram["full_text_excluded_by_reason"] == {}


def test_full_text_decision_on_excluded_screening_citation_is_excluded_from_every_count(
    authed_client,
):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study"))
    citation_id = list_citations(authed_client, project_id)[0]["id"]
    attach_full_text(authed_client, project_id, citation_id)
    record_screening_decision(
        authed_client, project_id, citation_id, "exclude", "Wrong population"
    )
    # A Full-Text Decision recorded despite the title/abstract Exclude.
    record_full_text_decision(authed_client, project_id, citation_id, "include")

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["full_text_assessed"] == 0
    assert diagram["full_text_included"] == 0
    assert diagram["full_text_excluded_by_reason"] == {}
    assert diagram["full_text_pending"] == 0


def test_full_text_included_counts_only_include_decisions(authed_client):
    project_id = create_project(authed_client)
    upload_csv(authed_client, project_id, CSV_HEADER + row("Study A") + row("Study B"))
    citations = {c["title"]: c["id"] for c in list_citations(authed_client, project_id)}
    for citation_id in citations.values():
        record_screening_decision(authed_client, project_id, citation_id, "include")
        attach_full_text(authed_client, project_id, citation_id)
    record_full_text_decision(authed_client, project_id, citations["Study A"], "include")
    record_full_text_decision(authed_client, project_id, citations["Study B"], "maybe")

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["full_text_included"] == 1
    assert diagram["full_text_assessed"] == 2
    assert diagram["full_text_excluded_by_reason"] == {}
    assert diagram["full_text_pending"] == 0


def test_full_text_pending_counts_include_maybe_citations_without_a_full_text_decision(
    authed_client,
):
    project_id = create_project(authed_client)
    upload_csv(
        authed_client,
        project_id,
        CSV_HEADER + row("Decided") + row("No Full Text Yet") + row("Maybe No Decision"),
    )
    citations = {c["title"]: c["id"] for c in list_citations(authed_client, project_id)}
    record_screening_decision(authed_client, project_id, citations["Decided"], "include")
    attach_full_text(authed_client, project_id, citations["Decided"])
    record_full_text_decision(authed_client, project_id, citations["Decided"], "include")
    record_screening_decision(authed_client, project_id, citations["No Full Text Yet"], "include")
    record_screening_decision(authed_client, project_id, citations["Maybe No Decision"], "maybe")

    diagram = get_flow_diagram(authed_client, project_id)

    assert diagram["full_text_assessed"] == 1
    assert diagram["full_text_included"] == 1
    assert diagram["full_text_pending"] == 2


def test_full_text_funnel_excludes_citation_with_a_pending_conflict(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = _create_dual_project(client, owner_headers)
    co_reviewer_headers = _add_co_reviewer(client, owner_headers, project_id)
    citation_id = _upload_citation(client, owner_headers, project_id)
    _record_decision(client, project_id, citation_id, owner_headers, "include")
    _record_decision(client, project_id, citation_id, co_reviewer_headers, "exclude")

    diagram = client.get(
        f"/review-projects/{project_id}/flow-diagram", headers=owner_headers
    ).json()

    assert diagram["full_text_pending"] == 0
    assert diagram["full_text_assessed"] == 0
