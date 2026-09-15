from sqlalchemy.orm import Session

from asr_backend import crud, models, schemas


def sync_conflict(
    db: Session, project: models.ReviewProject, citation: models.Citation
) -> None:
    """Keeps a Citation's Conflict in step with its two Screening Decisions, per #28.

    A no-op in Solo mode, before the Co-Reviewer has joined, or before either
    Reviewer has recorded their Screening Decision. Otherwise: creates a
    Conflict when both have decided and disagree, and clears one still
    *pending* if a later edit — a Screening Decision stays editable at any
    time — brings the two back into agreement, since a Conflict only exists
    while the two actually differ. A *resolved* Conflict is left alone either
    way: it's the Owner's settled call, not something a later Reviewer edit
    should reopen or erase.
    """
    if project.review_mode != "dual" or project.co_reviewer_id is None:
        return
    owner_decision = citation.screening_decision_for(project.owner_reviewer_id)
    co_reviewer_decision = citation.screening_decision_for(project.co_reviewer_id)
    if owner_decision is None or co_reviewer_decision is None:
        return
    existing = crud.get_conflict(db, citation.id)
    if owner_decision.decision == co_reviewer_decision.decision:
        if existing is not None and existing.status == "pending":
            crud.delete_conflict(db, existing)
        return
    if existing is not None:
        return
    crud.create_conflict(
        db, project.id, citation.id, project.owner_reviewer_id, project.co_reviewer_id
    )


def to_conflict_read(conflict: models.Conflict) -> schemas.ConflictRead:
    citation = conflict.citation
    # Reads the pairing off the Conflict itself, not the (possibly since
    # changed) ReviewProject, so a Co-Reviewer removed -- or removed and
    # replaced -- after this Conflict formed can't make it unreadable (#29).
    owner_decision = citation.screening_decision_for(conflict.owner_reviewer_id)
    co_reviewer_decision = citation.screening_decision_for(conflict.co_reviewer_id)
    assert owner_decision is not None
    assert co_reviewer_decision is not None
    return schemas.ConflictRead(
        id=conflict.id,
        citation=schemas.ConflictCitationRead.model_validate(citation),
        owner_decision=owner_decision,
        co_reviewer_decision=co_reviewer_decision,
        created_at=conflict.created_at,
    )
