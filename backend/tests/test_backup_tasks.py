"""Off-platform backup scripts: Full Text PDFs and the database, to S3 (#65 leftovers)."""

from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from asr_backend import backup_tasks

BUCKET = "asr-test-backups"
PREFIX = "asr-backups"


class _FakeS3Client:
    """An in-memory stand-in for boto3's S3 client, just the calls backup_tasks makes."""

    def __init__(self):
        # (bucket, key) -> {"Body": bytes, "Metadata": dict}
        self.objects: dict[tuple[str, str], dict] = {}

    def head_object(self, *, Bucket, Key):
        try:
            obj = self.objects[(Bucket, Key)]
        except KeyError:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
            ) from None
        return {"Metadata": obj["Metadata"]}

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        body = Path(filename).read_bytes()
        self.objects[(bucket, key)] = {
            "Body": body,
            "Metadata": (ExtraArgs or {}).get("Metadata", {}),
        }

    def put_object(self, *, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = {"Body": Body, "Metadata": {}}


@pytest.fixture
def client():
    return _FakeS3Client()


# --- backup_full_texts -------------------------------------------------------------------


def test_uploads_every_pdf(tmp_path, client):
    (tmp_path / "one.pdf").write_bytes(b"first pdf")
    (tmp_path / "two.pdf").write_bytes(b"second pdf")
    (tmp_path / "not-a-pdf.txt").write_bytes(b"ignored")

    report = backup_tasks.backup_full_texts(tmp_path, bucket=BUCKET, prefix=PREFIX, client=client)

    assert sorted(report.uploaded) == ["one.pdf", "two.pdf"]
    assert report.skipped == []
    assert report.failed == []
    assert client.objects[(BUCKET, f"{PREFIX}/full_texts/one.pdf")]["Body"] == b"first pdf"


def test_skips_a_file_already_backed_up_unchanged(tmp_path, client):
    (tmp_path / "one.pdf").write_bytes(b"same bytes")
    backup_tasks.backup_full_texts(tmp_path, bucket=BUCKET, prefix=PREFIX, client=client)

    report = backup_tasks.backup_full_texts(tmp_path, bucket=BUCKET, prefix=PREFIX, client=client)

    assert report.uploaded == []
    assert report.skipped == ["one.pdf"]


def test_re_uploads_a_file_replaced_in_place(tmp_path, client):
    """A Reviewer re-attaching a PDF overwrites the same filename; the backup must notice."""
    path = tmp_path / "one.pdf"
    path.write_bytes(b"old content")
    backup_tasks.backup_full_texts(tmp_path, bucket=BUCKET, prefix=PREFIX, client=client)

    path.write_bytes(b"new content, replaced")
    report = backup_tasks.backup_full_texts(tmp_path, bucket=BUCKET, prefix=PREFIX, client=client)

    assert report.uploaded == ["one.pdf"]
    assert report.skipped == []
    assert client.objects[(BUCKET, f"{PREFIX}/full_texts/one.pdf")]["Body"] == b"new content, replaced"


def test_missing_storage_directory_is_not_an_error(tmp_path, client):
    report = backup_tasks.backup_full_texts(
        tmp_path / "does-not-exist", bucket=BUCKET, prefix=PREFIX, client=client
    )

    assert report.uploaded == report.skipped == report.failed == []


def test_a_head_object_failure_that_is_not_missing_is_reported_not_raised(tmp_path, client):
    """One file's unexpected S3 error shouldn't abort the rest of the backup run."""
    (tmp_path / "one.pdf").write_bytes(b"content")

    def _broken_head_object(*, Bucket, Key):
        raise ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject")

    client.head_object = _broken_head_object

    report = backup_tasks.backup_full_texts(tmp_path, bucket=BUCKET, prefix=PREFIX, client=client)

    assert report.uploaded == []
    assert [name for name, _error in report.failed] == ["one.pdf"]


# --- backup_database ----------------------------------------------------------------------


def test_backup_database_uploads_pg_dumps_stdout(monkeypatch, client):
    captured_args = {}

    class _FakeResult:
        returncode = 0
        stdout = b"binary pg_dump archive bytes"
        stderr = b""

    def _fake_run(args, capture_output, check):
        captured_args["args"] = args
        return _FakeResult()

    monkeypatch.setattr(backup_tasks.subprocess, "run", _fake_run)

    report = backup_tasks.backup_database(
        "postgresql+psycopg://db.invalid/db",
        bucket=BUCKET,
        prefix=PREFIX,
        client=client,
    )

    assert report.bucket == BUCKET
    assert report.size_bytes == len(b"binary pg_dump archive bytes")
    assert report.key.startswith(f"{PREFIX}/database/asr-db-")
    assert report.key.endswith(".dump")
    assert client.objects[(BUCKET, report.key)]["Body"] == b"binary pg_dump archive bytes"
    # pg_dump doesn't understand the +psycopg driver suffix; it must be stripped.
    assert captured_args["args"][0] == "pg_dump"
    assert captured_args["args"][1] == "postgresql://db.invalid/db"


def test_backup_database_passes_through_a_url_without_the_psycopg_suffix(monkeypatch, client):
    """DATABASE_URL is already plain postgresql:// in some environments (not the +psycopg form
    settings.py stores); pg_dump should get it unchanged, not mangled looking for a prefix
    that isn't there."""
    captured_args = {}

    class _FakeResult:
        returncode = 0
        stdout = b"archive"
        stderr = b""

    def _fake_run(args, capture_output, check):
        captured_args["args"] = args
        return _FakeResult()

    monkeypatch.setattr(backup_tasks.subprocess, "run", _fake_run)

    backup_tasks.backup_database(
        "postgresql://db.invalid/db", bucket=BUCKET, prefix=PREFIX, client=client
    )

    assert captured_args["args"][1] == "postgresql://db.invalid/db"


def test_backup_database_raises_on_a_pg_dump_failure(monkeypatch, client):
    class _FakeResult:
        returncode = 1
        stdout = b""
        stderr = b"pg_dump: error: connection failed"

    monkeypatch.setattr(backup_tasks.subprocess, "run", lambda *a, **k: _FakeResult())

    with pytest.raises(backup_tasks.OperatorError, match="connection failed"):
        backup_tasks.backup_database(
            "postgresql+psycopg://db.invalid/db", bucket=BUCKET, prefix=PREFIX, client=client
        )


def test_backup_database_raises_a_clear_error_when_pg_dump_is_missing(monkeypatch, client):
    def _raise_not_found(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(backup_tasks.subprocess, "run", _raise_not_found)

    with pytest.raises(backup_tasks.OperatorError, match="pg_dump"):
        backup_tasks.backup_database(
            "postgresql+psycopg://db.invalid/db", bucket=BUCKET, prefix=PREFIX, client=client
        )


# --- command lines -------------------------------------------------------------------------


def test_backup_full_texts_main_fails_clearly_without_a_bucket_configured(monkeypatch):
    monkeypatch.setattr(backup_tasks.settings, "backup_s3_bucket", None)

    assert backup_tasks.backup_full_texts_main([]) == 1


def test_backup_database_main_fails_clearly_without_a_bucket_configured(monkeypatch):
    monkeypatch.setattr(backup_tasks.settings, "backup_s3_bucket", None)

    assert backup_tasks.backup_database_main([]) == 1
