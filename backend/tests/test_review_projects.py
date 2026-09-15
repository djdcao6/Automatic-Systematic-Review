import uuid

from conftest import auth_headers_for

from asr_backend import crud
from asr_backend.settings import settings


def test_create_review_project(authed_client):
    response = authed_client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My Review"
    assert body["criteria_locked"] is False
    assert body["merge_mode"] == "combine"
    assert body["review_mode"] == "solo"
    assert "id" in body
    assert "created_at" in body


def test_create_review_project_with_keep_first_merge_mode(authed_client):
    response = authed_client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "keep_first", "review_mode": "solo"},
    )

    assert response.status_code == 201
    assert response.json()["merge_mode"] == "keep_first"


def test_create_review_project_requires_merge_mode(authed_client):
    response = authed_client.post(
        "/review-projects", json={"name": "My Review", "review_mode": "solo"}
    )

    assert response.status_code == 422


def test_create_review_project_rejects_invalid_merge_mode(authed_client):
    response = authed_client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "not_a_mode", "review_mode": "solo"},
    )

    assert response.status_code == 422


def test_create_review_project_with_dual_review_mode(authed_client):
    response = authed_client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "dual"},
    )

    assert response.status_code == 201
    assert response.json()["review_mode"] == "dual"


def test_create_review_project_requires_review_mode(authed_client):
    response = authed_client.post(
        "/review-projects", json={"name": "My Review", "merge_mode": "combine"}
    )

    assert response.status_code == 422


def test_create_review_project_rejects_invalid_review_mode(authed_client):
    response = authed_client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "not_a_mode"},
    )

    assert response.status_code == 422


def test_create_review_project_rejects_blank_name(authed_client):
    response = authed_client.post(
        "/review-projects",
        json={"name": "   ", "merge_mode": "combine", "review_mode": "solo"},
    )

    assert response.status_code == 422


def test_create_review_project_strips_surrounding_whitespace(authed_client):
    response = authed_client.post(
        "/review-projects",
        json={"name": "  My Review  ", "merge_mode": "combine", "review_mode": "solo"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "My Review"


def test_review_project_detail_includes_merge_mode(authed_client):
    project_id = authed_client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "keep_first", "review_mode": "solo"},
    ).json()["id"]

    response = authed_client.get(f"/review-projects/{project_id}")

    assert response.status_code == 200
    assert response.json()["merge_mode"] == "keep_first"


def test_review_project_detail_includes_review_mode(authed_client):
    project_id = authed_client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "dual"},
    ).json()["id"]

    response = authed_client.get(f"/review-projects/{project_id}")

    assert response.status_code == 200
    assert response.json()["review_mode"] == "dual"


def test_review_project_merge_mode_is_immutable(authed_client):
    project_id = authed_client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
    ).json()["id"]

    # Immutability is enforced by omission: no update route exists for a
    # Review Project at all, so this can only 404 (unmatched path) or
    # 405 (path matched by another method).
    response = authed_client.put(
        f"/review-projects/{project_id}", json={"merge_mode": "keep_first"}
    )

    assert response.status_code in (404, 405)
    assert (
        authed_client.get(f"/review-projects/{project_id}").json()["merge_mode"]
        == "combine"
    )


def test_review_project_review_mode_is_immutable(authed_client):
    project_id = authed_client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
    ).json()["id"]

    # Same as merge_mode: no update route exists for a Review Project at all,
    # so this can only 404 (unmatched path) or 405 (path matched by another
    # method).
    response = authed_client.put(
        f"/review-projects/{project_id}", json={"review_mode": "dual"}
    )

    assert response.status_code in (404, 405)
    assert (
        authed_client.get(f"/review-projects/{project_id}").json()["review_mode"]
        == "solo"
    )


def test_list_review_projects(authed_client):
    authed_client.post(
        "/review-projects",
        json={"name": "First", "merge_mode": "combine", "review_mode": "solo"},
    )
    authed_client.post(
        "/review-projects",
        json={"name": "Second", "merge_mode": "keep_first", "review_mode": "dual"},
    )

    response = authed_client.get("/review-projects")

    assert response.status_code == 200
    names = [project["name"] for project in response.json()]
    assert names == ["First", "Second"]


def test_list_review_projects_empty(authed_client):
    response = authed_client.get("/review-projects")

    assert response.status_code == 200
    assert response.json() == []


def test_allows_cross_origin_requests_from_frontend(authed_client):
    response = authed_client.get(
        "/review-projects", headers={"Origin": settings.frontend_origin}
    )

    assert response.headers["access-control-allow-origin"] == settings.frontend_origin


# --- Authorization: scoping to the owning Reviewer (#24) ---


def test_create_review_project_requires_authentication(client):
    response = client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
    )

    assert response.status_code == 401


def test_create_review_project_rejects_invalid_token(client):
    response = client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


def test_list_review_projects_requires_authentication(client):
    response = client.get("/review-projects")

    assert response.status_code == 401


def test_create_review_project_records_owner(client, db_session):
    headers = auth_headers_for(client, "owner@example.com")
    reviewer_id = client.get("/me", headers=headers).json()["id"]

    project_id = client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
        headers=headers,
    ).json()["id"]

    project = crud.get_review_project(db_session, uuid.UUID(project_id))
    assert str(project.owner_reviewer_id) == reviewer_id


def test_list_review_projects_only_returns_own_projects(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    other_headers = auth_headers_for(client, "someone-else@example.com")

    client.post(
        "/review-projects",
        json={"name": "Owner's Review", "merge_mode": "combine", "review_mode": "solo"},
        headers=owner_headers,
    )
    client.post(
        "/review-projects",
        json={"name": "Other's Review", "merge_mode": "combine", "review_mode": "solo"},
        headers=other_headers,
    )

    owner_projects = client.get("/review-projects", headers=owner_headers).json()
    other_projects = client.get("/review-projects", headers=other_headers).json()

    assert [p["name"] for p in owner_projects] == ["Owner's Review"]
    assert [p["name"] for p in other_projects] == ["Other's Review"]


def test_get_review_project_rejects_non_owner(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    other_headers = auth_headers_for(client, "someone-else@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "Owner's Review", "merge_mode": "combine", "review_mode": "solo"},
        headers=owner_headers,
    ).json()["id"]

    response = client.get(f"/review-projects/{project_id}", headers=other_headers)

    assert response.status_code == 403


def test_get_review_project_requires_authentication(client):
    owner_headers = auth_headers_for(client, "owner@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "Owner's Review", "merge_mode": "combine", "review_mode": "solo"},
        headers=owner_headers,
    ).json()["id"]

    response = client.get(f"/review-projects/{project_id}")

    assert response.status_code == 401


def test_get_review_project_for_missing_project_returns_404(client):
    headers = auth_headers_for(client, "owner@example.com")

    response = client.get(
        "/review-projects/00000000-0000-0000-0000-000000000000", headers=headers
    )

    assert response.status_code == 404
