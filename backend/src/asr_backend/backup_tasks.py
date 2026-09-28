"""Off-platform backups for the pilot (remaining #65 leftovers).

Render's disk has no documented way to copy Full Text PDFs out (its SSH access supports
no scp, rsync or sftp), and a weekly database export was still a manual dashboard click.
Both operator scripts here push a copy to an S3 bucket you control instead, run by hand
on whatever cadence you choose (weekly is the roadmap's suggestion, not enforced here).
The scripts in backend/scripts are thin wrappers around the `*_main` functions here, so
the tests exercise the same code the operator runs. See README.md for setup.

Full Text PDFs are matched by an MD5 stored as S3 object metadata, not by comparing
timestamps or assuming the key is new: a Full Text's file can be replaced in place (same
filename, new bytes) when a Reviewer re-attaches a PDF, and only checking whether the key
already exists would silently keep serving a stale backup after a legitimate replacement.

The database backup shells out to `pg_dump` in the custom (`-Fc`) format, which is
compressed and restorable with `pg_restore` against an empty database. `pg_dump` isn't a
Python library; it must already be on PATH (matching the server's major version).
"""

import argparse
import hashlib
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from asr_backend.settings import settings

MD5_METADATA_KEY = "content-md5"
_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}
_HASH_CHUNK_BYTES = 1024 * 1024


class OperatorError(Exception):
    """A request the operator can fix and retry: missing config, missing pg_dump, etc."""


@dataclass
class FullTextBackupReport:
    bucket: str
    prefix: str
    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # already backed up, unchanged
    failed: list[tuple[str, str]] = field(default_factory=list)  # (filename, error)


@dataclass
class DatabaseBackupReport:
    bucket: str
    key: str
    size_bytes: int


def s3_client():
    if not settings.backup_s3_bucket:
        raise OperatorError(
            "BACKUP_S3_BUCKET is not set. Create an S3 bucket for backups and set "
            "BACKUP_S3_BUCKET (and, if the bucket isn't in your AWS default region, "
            "BACKUP_S3_REGION)."
        )
    try:
        return boto3.client("s3", region_name=settings.backup_s3_region)
    except (BotoCoreError, ClientError) as exc:
        raise OperatorError(f"Could not create an S3 client: {exc}") from exc


def _local_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remote_md5(client, bucket: str, key: str) -> str | None:
    """The object's stored MD5, or None if it doesn't exist yet."""
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in _NOT_FOUND_CODES:
            return None
        raise
    return head.get("Metadata", {}).get(MD5_METADATA_KEY)


def backup_full_texts(
    root: Path, *, bucket: str, prefix: str, client
) -> FullTextBackupReport:
    """Uploads every `*.pdf` under `root`, skipping ones already backed up unchanged."""
    report = FullTextBackupReport(bucket=bucket, prefix=prefix)
    if not root.is_dir():
        return report

    for path in sorted(root.glob("*.pdf")):
        key = f"{prefix}/full_texts/{path.name}"
        try:
            local_md5 = _local_md5(path)
            remote_md5 = _remote_md5(client, bucket, key)
            if remote_md5 == local_md5:
                report.skipped.append(path.name)
                continue
            client.upload_file(
                str(path), bucket, key, ExtraArgs={"Metadata": {MD5_METADATA_KEY: local_md5}}
            )
            report.uploaded.append(path.name)
        except (ClientError, BotoCoreError, OSError) as exc:
            report.failed.append((path.name, str(exc)))
    return report


def _plain_postgres_url(url: str) -> str:
    """pg_dump doesn't know the `+psycopg` driver suffix SQLAlchemy uses (see settings.py)."""
    prefix = "postgresql+psycopg://"
    if url.startswith(prefix):
        return "postgresql://" + url[len(prefix) :]
    return url


def backup_database(
    database_url: str, *, bucket: str, prefix: str, client, pg_dump_path: str = "pg_dump"
) -> DatabaseBackupReport:
    """Runs `pg_dump -Fc` and uploads the archive as one S3 object."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    key = f"{prefix}/database/asr-db-{timestamp}.dump"

    try:
        result = subprocess.run(
            [pg_dump_path, _plain_postgres_url(database_url), "-Fc"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise OperatorError(
            f"'{pg_dump_path}' was not found on PATH. Install the PostgreSQL client tools "
            "(matching the server's major version) so pg_dump is available."
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise OperatorError(f"pg_dump failed (exit {result.returncode}): {stderr}")

    body = result.stdout
    try:
        client.put_object(Bucket=bucket, Key=key, Body=body)
    except (ClientError, BotoCoreError) as exc:
        raise OperatorError(f"Upload to S3 failed: {exc}") from exc
    return DatabaseBackupReport(bucket=bucket, key=key, size_bytes=len(body))


# --- command lines ---------------------------------------------------------------------------


def _describe_full_text_backup(report: FullTextBackupReport) -> list[str]:
    lines = [
        f"Backed up Full Text PDFs to s3://{report.bucket}/{report.prefix}/full_texts/:",
        f"  {len(report.uploaded)} uploaded, {len(report.skipped)} unchanged (skipped)",
    ]
    for name in report.uploaded:
        lines.append(f"    uploaded: {name}")
    for name, error in report.failed:
        lines.append(f"    FAILED: {name}: {error}")
    return lines


def _describe_database_backup(report: DatabaseBackupReport) -> list[str]:
    size_mb = report.size_bytes / (1024 * 1024)
    return [f"Backed up the database to s3://{report.bucket}/{report.key} ({size_mb:.1f} MB)"]


def backup_full_texts_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backup_full_texts.py",
        description="Upload every Full Text PDF under FULL_TEXT_STORAGE_PATH to the "
        "off-platform S3 backup bucket (BACKUP_S3_BUCKET). Only new or changed files "
        "are actually uploaded.",
    )
    parser.parse_args(argv)
    try:
        client = s3_client()
        report = backup_full_texts(
            Path(settings.full_text_storage_path),
            bucket=settings.backup_s3_bucket,
            prefix=settings.backup_s3_prefix,
            client=client,
        )
    except OperatorError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    for line in _describe_full_text_backup(report):
        print(line)
    return 1 if report.failed else 0


def backup_database_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backup_database.py",
        description="Run pg_dump against DATABASE_URL and upload the archive to the "
        "off-platform S3 backup bucket (BACKUP_S3_BUCKET).",
    )
    parser.add_argument(
        "--pg-dump-path",
        default="pg_dump",
        help="path to the pg_dump binary, if it isn't on PATH under its usual name",
    )
    args = parser.parse_args(argv)
    try:
        client = s3_client()
        report = backup_database(
            settings.database_url,
            bucket=settings.backup_s3_bucket,
            prefix=settings.backup_s3_prefix,
            client=client,
            pg_dump_path=args.pg_dump_path,
        )
    except OperatorError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    for line in _describe_database_backup(report):
        print(line)
    return 0
