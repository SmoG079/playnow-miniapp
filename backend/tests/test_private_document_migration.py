import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location(
    "private_document_migration",
    Path(__file__).parents[1] / "scripts/migrate_private_documents.py",
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
settings = SimpleNamespace(
    PUBLIC_BASE_URL="https://app.example",
    OSS_BUCKET_NAME="example-123",
    COS_REGION="ap-shanghai",
)
source = "https://example-123.cos.ap-shanghai.myqcloud.com/doc/old.pdf"


def test_cli_can_start_without_pythonpath_override():
    result = subprocess.run(
        [sys.executable, str(Path(migration.__file__)), "--help"],
        cwd=Path(migration.__file__).parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--production" in result.stdout


def test_plan_preserves_metadata_and_requires_known_owner():
    row = {
        "id": 7,
        "created_by": "owner",
        "documents": [{"url": source, "name": "certificate"}],
    }
    plan = migration.build_plan([row], settings)
    assert plan[0]["previous"] == row["documents"]
    assert plan[0]["files"][0]["source_key"] == "doc/old.pdf"
    assert migration.target_filename("owner", source) != migration.target_filename(
        "other", source
    )
    with pytest.raises(ValueError, match="owner is unknown"):
        migration.build_plan([dict(row, created_by=None)], settings)


@pytest.mark.parametrize(
    "url",
    [
        "https://other.example/doc/a.pdf",
        source + "?versionId=1",
        "https://app.example/uploads/%2e%2e/secrets.pdf",
        "https://app.example/uploads/a%5cb.pdf",
    ],
)
def test_uncontrolled_or_ambiguous_source_is_rejected(url):
    with pytest.raises(ValueError):
        migration.source_key(url, settings)


def test_already_private_documents_are_unchanged():
    row = {
        "id": 7,
        "created_by": "owner",
        "documents": [{"url": "https://app.example/api/v1/media/doc/already.pdf"}],
    }
    assert migration.build_plan([row], settings) == []


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def mappings(self):
        return self

    def first(self):
        return self.value


class Connection:
    def __init__(self, docs):
        self.docs = docs
        self.writes = []

    def execute(self, statement, values):
        if str(statement).startswith("SELECT documents"):
            return Result(self.docs)
        if str(statement).startswith("SELECT user_id"):
            return Result(None)
        self.writes.append((str(statement), values))
        return Result(None)


def test_destination_checksum_failure_precedes_database_writes(tmp_path):
    row = {"id": 7, "created_by": "owner", "documents": [{"url": source}]}
    plan = migration.build_plan([row], settings)
    conn = Connection(row["documents"])
    with (
        patch.object(migration, "read_source", return_value=b"%PDF-original"),
        patch.object(migration.storage, "put_private_document", return_value="cos"),
        patch.object(
            migration.storage, "read_private_document", return_value=b"%PDF-corrupt"
        ),
    ):
        with pytest.raises(RuntimeError, match="checksum mismatch"):
            migration.apply_plan(conn, plan, tmp_path)
    assert conn.writes == []
    assert (tmp_path / plan[0]["files"][0]["filename"]).read_bytes() == b"%PDF-original"


def test_changed_references_refuse_copy_and_database_update(tmp_path):
    row = {"id": 7, "created_by": "owner", "documents": [{"url": source}]}
    plan = migration.build_plan([row], settings)
    conn = Connection([])
    with patch.object(migration, "read_source") as read:
        with pytest.raises(RuntimeError, match="changed since preflight"):
            migration.apply_plan(conn, plan, tmp_path)
        read.assert_not_called()
    assert conn.writes == []
