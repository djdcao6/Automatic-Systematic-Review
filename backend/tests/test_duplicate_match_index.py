import random
import uuid

from sqlalchemy import event

from asr_backend import crud, duplicates, models, schemas
from asr_backend.citation_import import ParsedCitation

_TITLES = ["Statins in Primary Care", "Aspirin for Stroke", "", "Trial of X", "Trial of  X!"]
_DOIS = [None, None, "", "10.1/a", "10.1/b"]


def _citation(rng: random.Random) -> models.Citation:
    title = rng.choice(_TITLES)
    title = rng.choice([title, title.upper(), title.lower() + "."])
    return models.Citation(id=uuid.uuid4(), title=title, doi=rng.choice(_DOIS))


def _reference_match(citation, pool):
    """The original linear-scan semantics the index has to reproduce."""
    match = duplicates.find_match(citation, [c for c in pool if c.id != citation.id])
    return match.id if match is not None else None


def test_index_matches_the_linear_scan_for_every_doi_and_title_combination():
    rng = random.Random(7)
    pool = [_citation(rng) for _ in range(40)]
    index = duplicates.MatchIndex(pool)

    for _ in range(300):
        probe = _citation(rng)
        assert index.find_match(probe) == _reference_match(probe, pool)

    for member in pool[:5]:
        assert index.find_match(member) == _reference_match(member, pool)


def test_index_agrees_with_the_linear_scan_after_removals_and_additions():
    rng = random.Random(11)
    pool = [_citation(rng) for _ in range(40)]
    index = duplicates.MatchIndex(pool)

    for _ in range(15):
        removed = pool.pop(rng.randrange(len(pool)))
        index.remove(removed.id)
        added = _citation(rng)
        pool.append(added)
        index.add(added)
        for _ in range(20):
            probe = _citation(rng)
            assert index.find_match(probe) == _reference_match(probe, pool)


def test_index_returns_the_earliest_added_of_several_matches():
    first = models.Citation(id=uuid.uuid4(), title="Same Title", doi=None)
    second = models.Citation(id=uuid.uuid4(), title="same title", doi=None)
    index = duplicates.MatchIndex([first, second])

    probe = models.Citation(id=uuid.uuid4(), title="SAME TITLE", doi=None)

    assert index.find_match(probe) == first.id


def _rows_selected_during(engine, fn) -> int:
    rows = 0

    def count(_conn, cursor, statement, *_args):
        nonlocal rows
        if statement.lstrip().upper().startswith("SELECT") and cursor.rowcount > 0:
            rows += cursor.rowcount

    event.listen(engine, "after_cursor_execute", count)
    try:
        fn()
    finally:
        event.remove(engine, "after_cursor_execute", count)
    return rows


def test_import_does_not_reload_every_active_citation_for_each_row(db_session):
    """Guards the O(n^2) row-hydration cost found by scripts/profile_import.py.

    Reloading the whole active pool per row reads ~n^2/2 rows for n unique
    uploads; with the pool loaded once it stays a small constant per row.
    """
    reviewer = crud.create_reviewer(db_session, "importer@example.com", "not-a-real-hash")
    project = crud.create_review_project(
        db_session,
        reviewer.id,
        schemas.ReviewProjectCreate(name="Big", merge_mode="combine", review_mode="solo"),
    )
    n = 60
    parsed = [
        ParsedCitation(
            title=f"Unique study {i}", abstract=None, authors=[], year=None, source=[], doi=None
        )
        for i in range(n)
    ]

    rows = _rows_selected_during(
        db_session.get_bind(),
        lambda: duplicates.import_citations(db_session, project, parsed),
    )

    assert rows < 10 * n
