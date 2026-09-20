"""Size limits for file uploads (#55).

Two layers: a middleware rejects an oversized body before it is parsed or spooled
to disk, and the upload handlers re-check the exact file size, record count and
page count once the file is in hand.
"""

import re
from collections.abc import Callable

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MEGABYTE = 1024 * 1024

# A route pattern and a getter returning (body limit in bytes, 413 message).
Rule = tuple[re.Pattern[str], Callable[[], tuple[int, str]]]

MAX_CITATION_FILE_BYTES = 10 * MEGABYTE
MAX_CITATION_RECORDS = 20_000
MAX_PDF_BYTES = 50 * MEGABYTE
MAX_PDF_PAGES = 200

# Multipart boundaries and part headers wrap the file, so the body limit sits a
# little above the file limit. The handler enforces the exact file limit.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


def citation_file_too_large_message() -> str:
    return (
        f"File is larger than the {MAX_CITATION_FILE_BYTES // MEGABYTE} MB limit. "
        "Split it into smaller files and upload them one at a time."
    )


def pdf_too_large_message() -> str:
    return f"PDF is larger than the {MAX_PDF_BYTES // MEGABYTE} MB limit."


class UploadSizeLimitMiddleware:
    """Rejects an upload body over its route's limit with a 413.

    Checks Content-Length up front, and counts bytes as they stream in so a
    chunked request with no Content-Length is cut off at the limit too. The
    counting raises an HTTPException from `receive`, which FastAPI's body
    parsing lets through and Starlette turns into the 413 response.
    """

    def __init__(self, app: ASGIApp, rules: list[Rule]):
        self.app = app
        self.rules = rules

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        rule = next((get for pattern, get in self.rules if pattern.fullmatch(scope["path"])), None)
        if rule is None:
            await self.app(scope, receive, send)
            return
        limit, message = rule()

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await JSONResponse({"detail": message}, status_code=413)(scope, receive, send)
            return

        received = 0

        async def counting_receive():
            nonlocal received
            event = await receive()
            if event["type"] == "http.request":
                received += len(event.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=message)
            return event

        await self.app(scope, counting_receive, send)


def default_rules() -> list[Rule]:
    """Read the limits at request time so tests can lower them."""
    return [
        (
            re.compile(r"/review-projects/[^/]+/citations"),
            lambda: (
                MAX_CITATION_FILE_BYTES + MULTIPART_OVERHEAD_BYTES,
                citation_file_too_large_message(),
            ),
        ),
        (
            re.compile(r"/review-projects/[^/]+/citations/[^/]+/full-text"),
            lambda: (MAX_PDF_BYTES + MULTIPART_OVERHEAD_BYTES, pdf_too_large_message()),
        ),
    ]
