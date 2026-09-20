import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from asr_backend import crud, models
from asr_backend.db import get_db
from asr_backend.schemas import MAX_PASSWORD_BYTES
from asr_backend.settings import settings

_ALGORITHM = "HS256"
_ACCESS_TOKEN_TTL = timedelta(days=30)

# auto_error=False so a missing Authorization header reaches
# get_current_reviewer and gets the same 401 as an invalid/expired token,
# rather than HTTPBearer's default 403.
_bearer_scheme = HTTPBearer(auto_error=False)


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    encoded = password.encode("utf-8")
    # bcrypt raises on more than 72 bytes. Registration rejects such passwords, so
    # no account has one: report it as a wrong password, like any other.
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))


# Verified on login when the email is unknown, so that path takes about as
# long as a real wrong-password check instead of returning early.
DUMMY_PASSWORD_HASH = hash_password("no-such-reviewer-placeholder")


def create_access_token(reviewer_id: uuid.UUID) -> str:
    payload = {
        "sub": str(reviewer_id),
        "exp": datetime.now(UTC) + _ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError from exc
    subject = payload.get("sub")
    if subject is None:
        raise InvalidTokenError
    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise InvalidTokenError from exc


def get_current_reviewer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> models.Reviewer:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        reviewer_id = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    reviewer = crud.get_reviewer(db, reviewer_id)
    if reviewer is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return reviewer
