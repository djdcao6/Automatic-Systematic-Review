from asr_backend.settings import settings


def test_create_review_project(client):
    response = client.post("/review-projects", json={"name": "My Review"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "My Review"
    assert body["criteria_locked"] is False
    assert "id" in body
    assert "created_at" in body


def test_create_review_project_rejects_blank_name(client):
    response = client.post("/review-projects", json={"name": "   "})

    assert response.status_code == 422


def test_create_review_project_strips_surrounding_whitespace(client):
    response = client.post("/review-projects", json={"name": "  My Review  "})

    assert response.status_code == 201
    assert response.json()["name"] == "My Review"


def test_list_review_projects(client):
    client.post("/review-projects", json={"name": "First"})
    client.post("/review-projects", json={"name": "Second"})

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
