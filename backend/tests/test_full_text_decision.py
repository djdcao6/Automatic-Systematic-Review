import io

import pymupdf


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


def make_pdf(text: str = "Sample paper text") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def attach_full_text(authed_client, project_id: str, citation_id: str) -> None:
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text",
        files={"file": ("paper.pdf", io.BytesIO(make_pdf()), "application/pdf")},
    )


def record_screening_decision(authed_client, project_id: str, citation_id: str, decision: str) -> None:
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": decision},
    )


def get_detail(authed_client, project_id: str, citation_id: str) -> dict:
    return authed_client.get(f"/review-projects/{project_id}/citations/{citation_id}").json()


def test_record_full_text_decision(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    attach_full_text(authed_client, project_id, citation_id)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": "include", "reason": "Meets all criteria after closer read"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "include"
    assert body["reason"] == "Meets all criteria after closer read"

    detail = get_detail(authed_client, project_id, citation_id)
    assert detail["full_text_decision"] == {
        "decision": "include",
        "reason": "Meets all criteria after closer read",
        "created_at": body["created_at"],
        "updated_at": body["updated_at"],
    }


def test_cannot_record_full_text_decision_without_a_full_text(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": "exclude", "reason": "Wrong population"},
    )

    assert response.status_code == 409
    detail = get_detail(authed_client, project_id, citation_id)
    assert detail["full_text_decision"] is None


def test_full_text_decision_is_editable(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    attach_full_text(authed_client, project_id, citation_id)

    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": "maybe", "reason": None},
    )
    response = authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": "exclude", "reason": "Wrong study design"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "exclude"
    assert body["reason"] == "Wrong study design"

    detail = get_detail(authed_client, project_id, citation_id)
    assert detail["full_text_decision"]["decision"] == "exclude"
    assert detail["full_text_decision"]["reason"] == "Wrong study design"


def test_exclusion_reason_is_drawn_from_criteria_exclusion_rules(authed_client):
    project_id = create_project(authed_client)
    authed_client.put(
        f"/review-projects/{project_id}/criteria",
        json={"exclusion_rules": ["Wrong population", "Non-English language"]},
    )
    citation_id = create_citation(authed_client, project_id)
    attach_full_text(authed_client, project_id, citation_id)

    exclusion_rules = authed_client.get(f"/review-projects/{project_id}").json()["criteria"][
        "exclusion_rules"
    ]
    chosen_reason = exclusion_rules[0]

    response = authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": "exclude", "reason": chosen_reason},
    )

    assert response.status_code == 200
    assert response.json()["reason"] == "Wrong population"


def test_recording_full_text_decision_does_not_modify_screening_decision(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    record_screening_decision(authed_client, project_id, citation_id, "maybe")
    before = get_detail(authed_client, project_id, citation_id)["screening_decision"]
    attach_full_text(authed_client, project_id, citation_id)

    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": "include", "reason": None},
    )

    after = get_detail(authed_client, project_id, citation_id)["screening_decision"]
    assert after == before
    assert after["decision"] == "maybe"


def test_maybe_screening_decision_is_resolved_once_full_text_decision_recorded(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    record_screening_decision(authed_client, project_id, citation_id, "maybe")

    assert get_detail(authed_client, project_id, citation_id)["screening_resolved"] is False

    attach_full_text(authed_client, project_id, citation_id)
    assert get_detail(authed_client, project_id, citation_id)["screening_resolved"] is False

    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": "exclude", "reason": "Wrong population"},
    )

    assert get_detail(authed_client, project_id, citation_id)["screening_resolved"] is True


def test_a_maybe_full_text_decision_does_not_resolve_a_maybe_screening_decision(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    record_screening_decision(authed_client, project_id, citation_id, "maybe")
    attach_full_text(authed_client, project_id, citation_id)

    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/full-text-decision",
        json={"decision": "maybe", "reason": None},
    )

    assert get_detail(authed_client, project_id, citation_id)["screening_resolved"] is False


def test_non_maybe_screening_decision_is_already_resolved(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    record_screening_decision(authed_client, project_id, citation_id, "include")

    assert get_detail(authed_client, project_id, citation_id)["screening_resolved"] is True


def test_unscreened_citation_is_not_resolved(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)

    assert get_detail(authed_client, project_id, citation_id)["screening_resolved"] is False


def test_citation_detail_has_no_full_text_decision_before_recording(authed_client):
    project_id = create_project(authed_client)
    citation_id = create_citation(authed_client, project_id)
    attach_full_text(authed_client, project_id, citation_id)

    detail = get_detail(authed_client, project_id, citation_id)

    assert detail["full_text_decision"] is None


def test_record_full_text_decision_for_missing_citation_returns_404(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.post(
        f"/review-projects/{project_id}/citations/00000000-0000-0000-0000-000000000000"
        "/full-text-decision",
        json={"decision": "include", "reason": None},
    )

    assert response.status_code == 404
