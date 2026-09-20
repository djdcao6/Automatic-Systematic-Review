import asyncio
from types import SimpleNamespace

import pytest
from conftest import auth_headers_for

from asr_backend import models
from asr_backend.main import app
from asr_backend.search_terms import (
    NoPicoFieldPopulatedError,
    SearchTermsGenerationError,
    SearchTermsGenerator,
    SearchTermsResult,
    compute_combined_query,
    get_search_terms_generator,
)

# ---------------------------------------------------------------------------
# SearchTermsGenerator (Anthropic call boundary), mirrors test_ai_suggestion.py
# ---------------------------------------------------------------------------


def _tool_response(**terms) -> SimpleNamespace:
    block = SimpleNamespace(type="tool_use", name="propose_search_terms", input=terms)
    return SimpleNamespace(content=[block])


class _FakeMessages:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.messages = _FakeMessages(response=response, error=error)


def test_generate_raises_when_no_pico_field_populated():
    suggester = SearchTermsGenerator(client=_FakeClient(), model="claude-haiku-4-5")

    with pytest.raises(NoPicoFieldPopulatedError):
        asyncio.run(suggester.generate())


def test_generate_does_not_call_the_api_when_no_pico_field_populated():
    client = _FakeClient(response=_tool_response(
        population_terms=[], intervention_terms=[], comparison_terms=[], outcome_terms=[]
    ))
    suggester = SearchTermsGenerator(client=client, model="claude-haiku-4-5")

    with pytest.raises(NoPicoFieldPopulatedError):
        asyncio.run(suggester.generate())

    assert client.messages.last_kwargs is None


def test_generate_returns_parsed_term_lists():
    client = _FakeClient(
        response=_tool_response(
            population_terms=["adults", "grown-ups"],
            intervention_terms=["metformin"],
            comparison_terms=[],
            outcome_terms=["HbA1c"],
        )
    )
    suggester = SearchTermsGenerator(client=client, model="claude-haiku-4-5")

    result = asyncio.run(
        suggester.generate(
            population="Adults with type 2 diabetes",
            intervention="Metformin",
            outcome="HbA1c reduction",
        )
    )

    assert result == SearchTermsResult(
        population_terms=["adults", "grown-ups"],
        intervention_terms=["metformin"],
        comparison_terms=[],
        outcome_terms=["HbA1c"],
    )


def test_generate_accepts_a_single_populated_pico_field():
    client = _FakeClient(
        response=_tool_response(
            population_terms=[],
            intervention_terms=[],
            comparison_terms=["sham procedure"],
            outcome_terms=[],
        )
    )
    suggester = SearchTermsGenerator(client=client, model="claude-haiku-4-5")

    result = asyncio.run(suggester.generate(comparison="Placebo"))

    assert result.comparison_terms == ["sham procedure"]
    assert "Comparison: Placebo" in client.messages.last_kwargs["messages"][0]["content"]
    assert "Population" not in client.messages.last_kwargs["messages"][0]["content"]


def test_generate_forces_the_tool_call():
    client = _FakeClient(
        response=_tool_response(
            population_terms=[], intervention_terms=[], comparison_terms=[], outcome_terms=[]
        )
    )
    suggester = SearchTermsGenerator(client=client, model="claude-haiku-4-5")

    asyncio.run(suggester.generate(population="Adults"))

    assert client.messages.last_kwargs["tool_choice"] == {
        "type": "tool",
        "name": "propose_search_terms",
    }


def test_generate_raises_on_api_error():
    suggester = SearchTermsGenerator(
        client=_FakeClient(error=RuntimeError("boom")), model="claude-haiku-4-5"
    )

    with pytest.raises(SearchTermsGenerationError):
        asyncio.run(suggester.generate(population="Adults"))


def test_generate_raises_when_no_tool_call_returned():
    suggester = SearchTermsGenerator(
        client=_FakeClient(response=SimpleNamespace(content=[])), model="claude-haiku-4-5"
    )

    with pytest.raises(SearchTermsGenerationError):
        asyncio.run(suggester.generate(population="Adults"))


# ---------------------------------------------------------------------------
# compute_combined_query (pure function)
# ---------------------------------------------------------------------------


def test_combined_query_ors_terms_within_a_concept_and_ands_across_concepts():
    search_terms = models.SearchTerms(
        population_terms=["adults", "elderly"],
        intervention_terms=["metformin"],
        comparison_terms=[],
        outcome_terms=["HbA1c", "glycemic control"],
    )

    query = compute_combined_query(search_terms)

    assert query == "(adults OR elderly) AND (metformin) AND (HbA1c OR glycemic control)"


def test_combined_query_skips_concepts_with_no_terms():
    search_terms = models.SearchTerms(
        population_terms=["adults"],
        intervention_terms=[],
        comparison_terms=[],
        outcome_terms=[],
    )

    assert compute_combined_query(search_terms) == "(adults)"


def test_combined_query_is_empty_when_no_terms_stored():
    search_terms = models.SearchTerms(
        population_terms=[], intervention_terms=[], comparison_terms=[], outcome_terms=[]
    )

    assert compute_combined_query(search_terms) == ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class _FakeGenerator:
    def __init__(self, result=None, error=None):
        self.result = result or SearchTermsResult(
            population_terms=["adults"],
            intervention_terms=["metformin"],
            comparison_terms=["placebo"],
            outcome_terms=["HbA1c"],
        )
        self.error = error
        self.calls = 0
        self.last_kwargs = None

    async def generate(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        if self.error is not None:
            raise self.error
        if not any(kwargs.values()):
            raise NoPicoFieldPopulatedError(
                "At least one PICO field must be populated to generate Search Terms"
            )
        return self.result


@pytest.fixture
def override_generator():
    fake = _FakeGenerator()
    app.dependency_overrides[get_search_terms_generator] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_search_terms_generator, None)


def create_project(authed_client, name: str = "My Review", review_mode: str = "solo") -> str:
    response = authed_client.post(
        "/review-projects",
        json={"name": name, "merge_mode": "combine", "review_mode": review_mode},
    )
    return response.json()["id"]


def set_criteria(authed_client, project_id: str, **fields) -> None:
    authed_client.put(f"/review-projects/{project_id}/criteria", json=fields)


def test_generate_search_terms_persists_and_returns_combined_query(
    authed_client, override_generator
):
    project_id = create_project(authed_client)
    set_criteria(
        authed_client,
        project_id,
        population="Adults with type 2 diabetes",
        intervention="Metformin",
        comparison="Placebo",
        outcome="HbA1c reduction",
    )

    response = authed_client.post(f"/review-projects/{project_id}/search-terms")

    assert response.status_code == 201
    body = response.json()
    assert body["population_terms"] == ["adults"]
    assert body["intervention_terms"] == ["metformin"]
    assert body["comparison_terms"] == ["placebo"]
    assert body["outcome_terms"] == ["HbA1c"]
    assert body["combined_query"] == "(adults) AND (metformin) AND (placebo) AND (HbA1c)"
    assert override_generator.calls == 1


def test_generate_search_terms_passes_only_populated_pico_fields(
    authed_client, override_generator
):
    project_id = create_project(authed_client)
    set_criteria(authed_client, project_id, population="Adults", outcome="HbA1c reduction")

    authed_client.post(f"/review-projects/{project_id}/search-terms")

    assert override_generator.last_kwargs == {
        "population": "Adults",
        "intervention": None,
        "comparison": None,
        "outcome": "HbA1c reduction",
    }


def test_generate_search_terms_from_a_single_populated_pico_field(
    authed_client, override_generator
):
    project_id = create_project(authed_client)
    set_criteria(authed_client, project_id, comparison="Placebo")

    response = authed_client.post(f"/review-projects/{project_id}/search-terms")

    assert response.status_code == 201
    assert override_generator.last_kwargs == {
        "population": None,
        "intervention": None,
        "comparison": "Placebo",
        "outcome": None,
    }


def test_generate_search_terms_rejected_with_no_pico_fields_populated(
    authed_client, override_generator
):
    project_id = create_project(authed_client)

    response = authed_client.post(f"/review-projects/{project_id}/search-terms")

    assert response.status_code == 422
    assert override_generator.calls == 1


def test_generate_search_terms_rejected_when_criteria_never_saved(
    authed_client, override_generator
):
    project_id = create_project(authed_client)

    response = authed_client.post(f"/review-projects/{project_id}/search-terms")

    assert response.status_code == 422


def test_generate_search_terms_reports_generation_failure(authed_client):
    project_id = create_project(authed_client)
    set_criteria(authed_client, project_id, population="Adults")
    app.dependency_overrides[get_search_terms_generator] = lambda: _FakeGenerator(
        error=SearchTermsGenerationError("boom")
    )

    response = authed_client.post(f"/review-projects/{project_id}/search-terms")
    app.dependency_overrides.pop(get_search_terms_generator, None)

    assert response.status_code == 502


def test_get_search_terms_returns_persisted_terms_and_combined_query(
    authed_client, override_generator
):
    project_id = create_project(authed_client)
    set_criteria(authed_client, project_id, population="Adults")
    authed_client.post(f"/review-projects/{project_id}/search-terms")

    response = authed_client.get(f"/review-projects/{project_id}/search-terms")

    assert response.status_code == 200
    body = response.json()
    assert body["population_terms"] == ["adults"]
    assert body["combined_query"] == "(adults) AND (metformin) AND (placebo) AND (HbA1c)"


def test_get_search_terms_before_generation_returns_404(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.get(f"/review-projects/{project_id}/search-terms")

    assert response.status_code == 404


def test_regenerating_overwrites_previous_terms_with_no_history(
    authed_client, override_generator
):
    project_id = create_project(authed_client)
    set_criteria(authed_client, project_id, population="Adults")
    authed_client.post(f"/review-projects/{project_id}/search-terms")

    override_generator.result = SearchTermsResult(
        population_terms=["older adults"],
        intervention_terms=[],
        comparison_terms=[],
        outcome_terms=[],
    )
    response = authed_client.post(f"/review-projects/{project_id}/search-terms")

    assert response.status_code == 201
    assert response.json()["population_terms"] == ["older adults"]
    assert override_generator.calls == 2

    retrieved = authed_client.get(f"/review-projects/{project_id}/search-terms")
    assert retrieved.json()["population_terms"] == ["older adults"]


def test_edit_search_terms_recomputes_combined_query(authed_client, override_generator):
    project_id = create_project(authed_client)
    set_criteria(authed_client, project_id, population="Adults")
    authed_client.post(f"/review-projects/{project_id}/search-terms")

    response = authed_client.put(
        f"/review-projects/{project_id}/search-terms",
        json={
            "population_terms": ["adults", "grown-ups"],
            "intervention_terms": [],
            "comparison_terms": [],
            "outcome_terms": ["HbA1c"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["population_terms"] == ["adults", "grown-ups"]
    assert body["combined_query"] == "(adults OR grown-ups) AND (HbA1c)"


def test_edit_search_terms_replaces_all_concepts_omitted_ones_included(
    authed_client, override_generator
):
    """PUT replaces the whole record, mirroring CriteriaUpdate's full-replace
    convention (crud.upsert_criteria) — a payload that omits a concept clears
    it rather than preserving the previously stored terms for it.
    """
    project_id = create_project(authed_client)
    set_criteria(authed_client, project_id, population="Adults")
    authed_client.post(f"/review-projects/{project_id}/search-terms")

    response = authed_client.put(
        f"/review-projects/{project_id}/search-terms",
        json={"population_terms": ["adults"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["population_terms"] == ["adults"]
    assert body["intervention_terms"] == []
    assert body["comparison_terms"] == []
    assert body["outcome_terms"] == []


def test_edit_search_terms_persists_across_retrieval(authed_client, override_generator):
    project_id = create_project(authed_client)
    set_criteria(authed_client, project_id, population="Adults")
    authed_client.post(f"/review-projects/{project_id}/search-terms")

    authed_client.put(
        f"/review-projects/{project_id}/search-terms",
        json={
            "population_terms": ["adults"],
            "intervention_terms": ["aspirin"],
            "comparison_terms": [],
            "outcome_terms": [],
        },
    )
    response = authed_client.get(f"/review-projects/{project_id}/search-terms")

    assert response.json()["intervention_terms"] == ["aspirin"]


def test_edit_search_terms_without_prior_generation_creates_record(authed_client):
    project_id = create_project(authed_client)

    response = authed_client.put(
        f"/review-projects/{project_id}/search-terms",
        json={
            "population_terms": ["adults"],
            "intervention_terms": [],
            "comparison_terms": [],
            "outcome_terms": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["population_terms"] == ["adults"]


def _lock_criteria(authed_client, project_id: str) -> None:
    authed_client.post(
        f"/review-projects/{project_id}/citations",
        files={
            "file": (
                "citations.csv",
                "title,abstract,authors,year,source\nStudy,An abstract,Author,2020,PubMed\n",
                "text/csv",
            )
        },
    )
    citation_id = authed_client.get(
        f"/review-projects/{project_id}/citations"
    ).json()[0]["id"]
    authed_client.post(
        f"/review-projects/{project_id}/citations/{citation_id}/decision",
        json={"decision": "include"},
    )


def test_search_terms_endpoints_work_when_criteria_is_locked(authed_client, override_generator):
    project_id = create_project(authed_client)
    set_criteria(authed_client, project_id, population="Adults")
    _lock_criteria(authed_client, project_id)
    assert authed_client.get(f"/review-projects/{project_id}").json()["criteria_locked"] is True

    generate = authed_client.post(f"/review-projects/{project_id}/search-terms")
    get = authed_client.get(f"/review-projects/{project_id}/search-terms")
    edit = authed_client.put(
        f"/review-projects/{project_id}/search-terms",
        json={
            "population_terms": ["adults"],
            "intervention_terms": [],
            "comparison_terms": [],
            "outcome_terms": [],
        },
    )

    assert generate.status_code == 201
    assert get.status_code == 200
    assert edit.status_code == 200


def test_search_terms_endpoints_require_authorization(client):
    owner_headers = auth_headers_for(client, "owner-search-terms@example.com")
    other_headers = auth_headers_for(client, "other-search-terms@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "My Review", "merge_mode": "combine", "review_mode": "solo"},
        headers=owner_headers,
    ).json()["id"]
    client.put(
        f"/review-projects/{project_id}/criteria",
        json={"population": "Adults"},
        headers=owner_headers,
    )

    fake = _FakeGenerator()
    app.dependency_overrides[get_search_terms_generator] = lambda: fake
    try:
        requests = [
            ("post", f"/review-projects/{project_id}/search-terms", None),
            ("get", f"/review-projects/{project_id}/search-terms", None),
            (
                "put",
                f"/review-projects/{project_id}/search-terms",
                {
                    "population_terms": ["adults"],
                    "intervention_terms": [],
                    "comparison_terms": [],
                    "outcome_terms": [],
                },
            ),
        ]
        for method, path, payload in requests:
            no_token = client.request(method.upper(), path, json=payload)
            assert no_token.status_code == 401, f"{method.upper()} {path}"

            wrong_owner = client.request(
                method.upper(), path, json=payload, headers=other_headers
            )
            assert wrong_owner.status_code == 403, f"{method.upper()} {path}"

            allowed = client.request(
                method.upper(), path, json=payload, headers=owner_headers
            )
            assert allowed.status_code < 400, f"{method.upper()} {path}"
    finally:
        app.dependency_overrides.pop(get_search_terms_generator, None)


def test_co_reviewer_can_use_search_terms_endpoints(client):
    owner_headers = auth_headers_for(client, "co-review-owner@example.com")
    project_id = client.post(
        "/review-projects",
        json={"name": "Dual Review", "merge_mode": "combine", "review_mode": "dual"},
        headers=owner_headers,
    ).json()["id"]
    client.put(
        f"/review-projects/{project_id}/criteria",
        json={"population": "Adults"},
        headers=owner_headers,
    )
    invitation_token = client.post(
        f"/review-projects/{project_id}/invitations", headers=owner_headers
    ).json()["token"]
    co_reviewer_token = client.post(
        f"/invitations/{invitation_token}/accept-register",
        json={"email": "co-reviewer-search-terms@example.com", "password": "correcthorse", "ai_consent": True},
    ).json()["access_token"]
    co_reviewer_headers = {"Authorization": f"Bearer {co_reviewer_token}"}

    fake = _FakeGenerator()
    app.dependency_overrides[get_search_terms_generator] = lambda: fake
    try:
        response = client.post(
            f"/review-projects/{project_id}/search-terms", headers=co_reviewer_headers
        )
        assert response.status_code == 201
    finally:
        app.dependency_overrides.pop(get_search_terms_generator, None)
