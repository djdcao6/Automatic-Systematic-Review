"""Cross-cutting JWT gating and Reviewer-ownership checks (#24).

Endpoint-specific happy paths already live in each endpoint's own test file
(now exercised via the `authed_client` fixture). This file instead checks the
gate itself — no/invalid token (401) and a valid token for the wrong owner
(403) — across a representative sample of endpoints, so the check is proven
once at the seam (`get_review_project_or_404` in main.py) rather than
per-endpoint.
"""

import pytest
from conftest import auth_headers_for

CSV_SAMPLE = "title,abstract,authors,year,source\nStudy,An abstract,Author,2020,PubMed\n"


@pytest.fixture
def owner_headers(client):
    return auth_headers_for(client, "owner@example.com")


@pytest.fixture
def other_headers(client):
    return auth_headers_for(client, "someone-else@example.com")


@pytest.fixture
def project_id(client, owner_headers):
    return client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
        headers=owner_headers,
    ).json()["id"]


@pytest.fixture
def citation_id(client, owner_headers, project_id):
    client.post(
        f"/review-projects/{project_id}/citations",
        files={"file": ("citations.csv", CSV_SAMPLE, "text/csv")},
        headers=owner_headers,
    )
    citations = client.get(
        f"/review-projects/{project_id}/citations", headers=owner_headers
    ).json()
    return citations[0]["id"]


@pytest.fixture
def extraction_field_id(client, owner_headers, project_id):
    response = client.post(
        f"/review-projects/{project_id}/extraction-fields",
        json={"name": "Sample size", "description": None},
        headers=owner_headers,
    )
    return response.json()["id"]


def _representative_requests(project_id, citation_id, extraction_field_id):
    """(method, path, json_payload) for a representative slice of endpoints."""
    return [
        ("get", f"/review-projects/{project_id}", None),
        ("put", f"/review-projects/{project_id}/criteria", {"population": "Adults"}),
        ("get", f"/review-projects/{project_id}/citations", None),
        ("get", f"/review-projects/{project_id}/citations/{citation_id}", None),
        (
            "post",
            f"/review-projects/{project_id}/citations/{citation_id}/decision",
            {"decision": "include"},
        ),
        ("get", f"/review-projects/{project_id}/extraction-fields", None),
        (
            "post",
            (
                f"/review-projects/{project_id}/citations/{citation_id}"
                f"/extraction-fields/{extraction_field_id}/value"
            ),
            {"value": "120 patients"},
        ),
        ("get", f"/review-projects/{project_id}/possible-duplicates", None),
        ("get", f"/review-projects/{project_id}/flow-diagram", None),
        ("get", f"/review-projects/{project_id}/export", None),
    ]


def test_representative_endpoints_reject_missing_token(
    client, project_id, citation_id, extraction_field_id
):
    for method, path, payload in _representative_requests(
        project_id, citation_id, extraction_field_id
    ):
        response = client.request(method.upper(), path, json=payload)
        assert response.status_code == 401, f"{method.upper()} {path} -> {response.status_code}"


def test_representative_endpoints_reject_invalid_token(
    client, project_id, citation_id, extraction_field_id
):
    headers = {"Authorization": "Bearer not-a-real-token"}
    for method, path, payload in _representative_requests(
        project_id, citation_id, extraction_field_id
    ):
        response = client.request(method.upper(), path, json=payload, headers=headers)
        assert response.status_code == 401, f"{method.upper()} {path} -> {response.status_code}"


def test_representative_endpoints_reject_non_owner(
    client, other_headers, project_id, citation_id, extraction_field_id
):
    for method, path, payload in _representative_requests(
        project_id, citation_id, extraction_field_id
    ):
        response = client.request(method.upper(), path, json=payload, headers=other_headers)
        assert response.status_code == 403, f"{method.upper()} {path} -> {response.status_code}"


def test_representative_endpoints_allow_owner(
    client, owner_headers, project_id, citation_id, extraction_field_id
):
    for method, path, payload in _representative_requests(
        project_id, citation_id, extraction_field_id
    ):
        response = client.request(method.upper(), path, json=payload, headers=owner_headers)
        assert response.status_code < 400, f"{method.upper()} {path} -> {response.status_code}"


def test_co_reviewer_passes_the_representative_endpoints_gate(client, owner_headers):
    """A Co-Reviewer gets the same access as the Owner through the shared gate,
    per #26 — checked once here rather than per-endpoint like test_representative_endpoints_allow_owner.
    """
    dual_project_id = client.post(
        "/review-projects",
        json={"name": "Dual Review", "merge_mode": "combine", "review_mode": "dual"},
        headers=owner_headers,
    ).json()["id"]
    invitation_token = client.post(
        f"/review-projects/{dual_project_id}/invitations", headers=owner_headers
    ).json()["token"]
    co_reviewer_token = client.post(
        f"/invitations/{invitation_token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse"},
    ).json()["access_token"]
    co_reviewer_headers = {"Authorization": f"Bearer {co_reviewer_token}"}
    client.post(
        f"/review-projects/{dual_project_id}/citations",
        files={"file": ("citations.csv", CSV_SAMPLE, "text/csv")},
        headers=owner_headers,
    )
    citation_id = client.get(
        f"/review-projects/{dual_project_id}/citations", headers=owner_headers
    ).json()[0]["id"]
    extraction_field_id = client.post(
        f"/review-projects/{dual_project_id}/extraction-fields",
        json={"name": "Sample size", "description": None},
        headers=owner_headers,
    ).json()["id"]

    for method, path, payload in _representative_requests(
        dual_project_id, citation_id, extraction_field_id
    ):
        response = client.request(
            method.upper(), path, json=payload, headers=co_reviewer_headers
        )
        assert response.status_code < 400, f"{method.upper()} {path} -> {response.status_code}"


def test_co_reviewer_cannot_manage_invitations(client, owner_headers):
    dual_project_id = client.post(
        "/review-projects",
        json={"name": "Dual Review", "merge_mode": "combine", "review_mode": "dual"},
        headers=owner_headers,
    ).json()["id"]
    invitation_token = client.post(
        f"/review-projects/{dual_project_id}/invitations", headers=owner_headers
    ).json()["token"]
    co_reviewer_token = client.post(
        f"/invitations/{invitation_token}/accept-register",
        json={"email": "co-reviewer@example.com", "password": "correcthorse"},
    ).json()["access_token"]
    co_reviewer_headers = {"Authorization": f"Bearer {co_reviewer_token}"}

    response = client.post(
        f"/review-projects/{dual_project_id}/invitations", headers=co_reviewer_headers
    )

    assert response.status_code == 403


def test_dismiss_possible_duplicate_rejects_non_owner(client, other_headers, project_id):
    # Ownership is checked before the possible duplicate lookup (both hang off
    # the same get_review_project_or_404 dependency), so a non-owner is
    # rejected regardless of whether this id exists.
    fake_possible_duplicate_id = "00000000-0000-0000-0000-000000000000"

    response = client.post(
        f"/review-projects/{project_id}/possible-duplicates/{fake_possible_duplicate_id}/dismiss",
        headers=other_headers,
    )

    assert response.status_code == 403
