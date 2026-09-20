import csv
import io
from dataclasses import dataclass, field

import rispy

from asr_backend import upload_limits


@dataclass
class ParsedCitation:
    title: str
    abstract: str | None
    authors: list[str]
    year: int | None
    source: list[str]
    doi: str | None


@dataclass
class ImportResult:
    citations: list[ParsedCitation] = field(default_factory=list)
    skipped: list[tuple[int, str]] = field(default_factory=list)


class UnsupportedFileType(Exception):
    pass


class TooManyRecords(Exception):
    def __init__(self, limit: int):
        super().__init__(
            f"File has more than {limit:,} records. "
            "Split it into smaller files and upload them one at a time."
        )


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    return stripped or None


def _clean_as_list(value: str | None) -> list[str]:
    cleaned = _clean(value)
    return [cleaned] if cleaned else []


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(char for char in value if char.isdigit())
    return int(digits[:4]) if len(digits) >= 4 else None


def parse_ris(content: str) -> ImportResult:
    result = ImportResult()
    entries = rispy.loads(content)
    if len(entries) > upload_limits.MAX_CITATION_RECORDS:
        raise TooManyRecords(upload_limits.MAX_CITATION_RECORDS)
    for index, entry in enumerate(entries, start=1):
        title = _clean(entry.get("title"))
        if title is None:
            result.skipped.append((index, "missing title"))
            continue
        result.citations.append(
            ParsedCitation(
                title=title,
                abstract=_clean(entry.get("abstract")),
                authors=list(entry.get("authors") or []),
                year=_parse_year(entry.get("year")),
                source=_clean_as_list(entry.get("name_of_database")),
                doi=_clean(entry.get("doi")),
            )
        )
    return result


def parse_csv(content: str) -> ImportResult:
    result = ImportResult()
    reader = csv.DictReader(io.StringIO(content))
    field_map = {(name or "").strip().lower(): name for name in reader.fieldnames or []}

    def get(row: dict[str, str | None], key: str) -> str | None:
        source_key = field_map.get(key)
        return row.get(source_key) if source_key else None

    for index, row in enumerate(reader, start=1):
        # Checked per row so a file of blank-titled rows can't pile up in `skipped`.
        if index > upload_limits.MAX_CITATION_RECORDS:
            raise TooManyRecords(upload_limits.MAX_CITATION_RECORDS)
        title = _clean(get(row, "title"))
        if title is None:
            result.skipped.append((index, "missing title"))
            continue
        authors_raw = get(row, "authors") or ""
        authors = [author.strip() for author in authors_raw.split(";") if author.strip()]
        result.citations.append(
            ParsedCitation(
                title=title,
                abstract=_clean(get(row, "abstract")),
                authors=authors,
                year=_parse_year(get(row, "year")),
                source=_clean_as_list(get(row, "source")),
                doi=_clean(get(row, "doi")),
            )
        )
    return result


def parse_upload(filename: str, content: str) -> ImportResult:
    lowered = filename.lower()
    if lowered.endswith(".ris"):
        return parse_ris(content)
    if lowered.endswith(".csv"):
        return parse_csv(content)
    raise UnsupportedFileType("File must be .ris or .csv")
