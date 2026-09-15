import uuid

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from asr_backend import models


class InvitationNotAcceptable(Exception):
    """The Invitation is unknown/settled, or its project already has a Co-Reviewer."""


def accept_invitation(
    db: Session, invitation: models.Invitation, reviewer_id: uuid.UUID
) -> models.ReviewProject:
    """Attaches `reviewer_id` to the Invitation's Review Project as Co-Reviewer.

    Two atomic, conditional UPDATEs guard against races: one so an
    already-accepted or revoked Invitation (or one accepted concurrently by a
    second request racing this one) can't be used twice, and one so a Review
    Project that already has a Co-Reviewer (attached by a concurrent accept of
    a different Invitation) doesn't get silently overwritten. Callers that
    create a Reviewer account as part of accepting (registration) should
    still check `invitation.review_project.co_reviewer_id` themselves first,
    since that account is created and committed before this function ever
    runs — see accept_invitation_by_registering in main.py.
    """
    if reviewer_id == invitation.review_project.owner_reviewer_id:
        raise InvitationNotAcceptable("The Owner cannot accept their own Invitation")

    invitation_result = db.execute(
        update(models.Invitation)
        .where(models.Invitation.id == invitation.id, models.Invitation.status == "pending")
        .values(status="accepted", accepted_at=func.now())
    )
    if invitation_result.rowcount == 0:
        db.rollback()
        raise InvitationNotAcceptable("Invitation is no longer valid")

    project_result = db.execute(
        update(models.ReviewProject)
        .where(
            models.ReviewProject.id == invitation.review_project_id,
            models.ReviewProject.co_reviewer_id.is_(None),
        )
        .values(co_reviewer_id=reviewer_id)
    )
    if project_result.rowcount == 0:
        db.rollback()
        raise InvitationNotAcceptable("Review Project already has a Co-Reviewer")

    db.commit()
    return db.get(models.ReviewProject, invitation.review_project_id)
