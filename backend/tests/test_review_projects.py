from asr_backend.settings import settings


def test_create_review_project(client):
    response = client.post(
        "/review-projects", json={"name": "My Review", "merge_mode": "combine"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My Review"
    assert body["criteria_locked"] is False
    assert body["merge_mode"] == "combine"
    assert "id" in body
    assert "created_at" in body


def test_create_review_project_with_keep_first_merge_mode(client):
    response = client.post(
        "/review-projects", json={"name": "My Review", "merge_mode": "keep_first"}
    )

    assert response.status_code == 201
    assert response.json()["merge_mode"] == "keep_first"


def test_create_review_project_requires_merge_mode(client):
    response = client.post("/review-projects", json={"name": "My Review"})

    assert response.status_code == 422


def test_create_review_project_rejects_invalid_merge_mode(client):
    response = client.post(
        "/review-projects", json={"name": "My Review", "merge_mode": "not_a_mode"}
    )

    assert response.status_code == 422


def test_create_review_project_rejects_blank_name(client):
    response = client.post(
        "/review-projects", json={"name": "   ", "merge_mode": "combine"}
    )

    assert response.status_code == 422


def test_create_review_project_strips_surrounding_whitespace(client):
    response = client.post(
        "/review-projects", json={"name": "  My Review  ", "merge_mode": "combine"}
    )

    assert response.status_code == 201
    assert response.json()["name"] == "My Review"


def test_review_project_detail_includes_merge_mode(client):
    project_id = client.post(
        "/review-projects", json={"name": "My Review", "merge_mode": "keep_first"}
    ).json()["id"]

    response = client.get(f"/review-projects/{project_id}")

    assert response.status_code == 200
    assert response.json()["merge_mode"] == "keep_first"


def test_review_project_merge_mode_is_immutable(client):
    project_id = client.post(
        "/review-projects", json={"name": "My Review", "merge_mode": "combine"}
    ).json()["id"]

    # Immutability is enforced by omission: no update route exists for a
    # Review Project at all, so this can only 404 (unmatched path) or
    # 405 (path matched by another method).
    response = client.put(
        f"/review-projects/{project_id}", json={"merge_mode": "keep_first"}
    )

    assert response.status_code in (404, 405)
    assert (
        client.get(f"/review-projects/{project_id}").json()["merge_mode"] == "combine"
    )


def test_list_review_projects(client):
    client.post("/review-projects", json={"name": "First", "merge_mode": "combine"})
    client.post(
        "/review-projects", json={"name": "Second", "merge_mode": "keep_first"}
    )

    response = client.get("/review-projects")

    assert response.status_code == 200
    names = [project["name"] for project in response.json()]
    assert names == ["First", "Second"]


def test_list_review_projects_empty(client):
    response = client.get("/review-projects")

    assert response.status_code == 200
    assert response.json() == []


def test_allows_cross_origin_requests_from_frontend(client):
    response = client.get(
        "/review-projects", headers={"Origin": settings.frontend_origin}
    )

    assert response.headers["access-control-allow-origin"] == settings.frontend_origin
