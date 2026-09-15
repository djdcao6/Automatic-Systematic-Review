import uuid

from conftest import TestSessionLocal

from asr_backend import crud, models, schemas


def create_project(authed_client, name: str = "My Review") -> str:
    response = authed_client.post("/review-projects", json={"name": name, "merge_mode": "combine"})
    return response.json()["id"]


def test_get_review_project_not_found(authed_client):
    response = authed_client.get("/review-projects/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_new_review_project_has_no_criteria(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.get(f"/review-projects/{project_id}")

    assert response.status_code == 200
    assert response.json()["criteria"] is None


def test_save_criteria_with_all_pico_fields_blank(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.put(
        f"/review-projects/{project_id}/criteria",
        json={
            "exclusion_rules": ["Non-English", "Case reports"],
            "notes": "Focus on adult populations only.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["population"] is None
    assert body["intervention"] is None
    assert body["comparison"] is None
    assert body["outcome"] is None
    assert body["exclusion_rules"] == ["Non-English", "Case reports"]
    assert body["notes"] == "Focus on adult populations only."


def test_save_and_retrieve_full_criteria(authed_client):
    project_id = create_project(authed_client)

    authed_client.put(
        f"/review-projects/{project_id}/criteria",
        json={
            "population": "Adults with type 2 diabetes",
            "intervention": "Metformin",
            "comparison": "Placebo",
            "outcome": "HbA1c reduction",
            "exclusion_rules": ["Animal studies"],
            "notes": "Exclude conference abstracts.",
        },
    )

    response = authed_client.get(f"/review-projects/{project_id}")

    assert response.status_code == 200
    criteria = response.json()["criteria"]
    assert criteria["population"] == "Adults with type 2 diabetes"
    assert criteria["intervention"] == "Metformin"
    assert criteria["comparison"] == "Placebo"
    assert criteria["outcome"] == "HbA1c reduction"
    assert criteria["exclusion_rules"] == ["Animal studies"]
    assert criteria["notes"] == "Exclude conference abstracts."


def test_saving_criteria_again_replaces_previous_values(authed_client):
    project_id = create_project(authed_client)

    authed_client.put(
        f"/review-projects/{project_id}/criteria",
        json={"population": "First draft"},
    )
    response = authed_client.put(
        f"/review-projects/{project_id}/criteria",
        json={"population": "Revised"},
    )

    assert response.status_code == 200
    assert response.json()["population"] == "Revised"


def test_upsert_criteria_is_safe_when_two_sessions_race(authed_client):
    project_id = uuid.UUID(create_project(authed_client))

    session_a = TestSessionLocal()
    session_b = TestSessionLocal()
    try:
        project_a = session_a.get(models.ReviewProject, project_id)
        project_b = session_b.get(models.ReviewProject, project_id)
        # Both sessions load the project before either writes criteria for it —
        # this is the race: both see no existing Criteria row.
        assert project_a.criteria is None
        assert project_b.criteria is None

        crud.upsert_criteria(session_a, project_a, schemas.CriteriaUpdate(population="First"))
        result = crud.upsert_criteria(
            session_b, project_b, schemas.CriteriaUpdate(population="Second")
        )

        assert result.population == "Second"
    finally:
        session_a.close()
        session_b.close()


def test_save_criteria_for_missing_review_project(authed_client):
    response = authed_client.put(
        "/review-projects/00000000-0000-0000-0000-000000000000/criteria",
        json={"population": "Adults"},
    )

    assert response.status_code == 404
