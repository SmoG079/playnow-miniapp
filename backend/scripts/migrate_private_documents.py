"""Back up and migrate referenced club certificates; never changes public ACLs.

Run after Alembic upgrade, with explicit DATABASE_URL and COS_PRIVATE_BUCKET_NAME.
Keep writers stopped throughout apply. Revoking old anonymous access is a separate
cloud-admin operation, performed only after authenticated downloads are verified.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
from urllib.parse import unquote, urlsplit

import sqlalchemy as sa
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import storage


def source_key(url, settings):
    parsed = urlsplit(url)
    public = urlsplit(settings.PUBLIC_BASE_URL)
    cos_host = f"{settings.OSS_BUCKET_NAME}.cos.{settings.COS_REGION}.myqcloud.com"
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("Certificate URL must be an unambiguous controlled source")
    if parsed.scheme == "https" and parsed.netloc == cos_host:
        backend, key = "cos", unquote(parsed.path.lstrip("/"))
    elif (parsed.scheme, parsed.netloc) == (
        public.scheme,
        public.netloc,
    ) and parsed.path.startswith("/uploads/"):
        backend, key = "local", unquote(parsed.path[len("/uploads/") :])
    else:
        raise ValueError("Certificate URL is outside controlled storage")
    if (
        not key
        or any(part in ("", ".", "..") for part in key.split("/"))
        or "\\" in key
    ):
        raise ValueError("Invalid certificate source path")
    return backend, key


def documents(value):
    value = json.loads(value) if isinstance(value, str) else value
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(d, dict) or not isinstance(d.get("url"), str) for d in value
    ):
        raise ValueError("Invalid certificate document list")
    return value


def target_filename(owner, url):
    ext = Path(urlsplit(url).path).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"):
        raise ValueError("Unsupported historical certificate format")
    return (
        uuid.uuid5(uuid.NAMESPACE_URL, f"playnow:certificate:{owner}:{url}").hex + ext
    )


def build_plan(rows, settings):
    plan = []
    for row in rows:
        previous = documents(row["documents"])
        changed = []
        for item in previous:
            parsed = urlsplit(item["url"])
            origin = urlsplit(settings.PUBLIC_BASE_URL)
            if (parsed.scheme, parsed.netloc) == (
                origin.scheme,
                origin.netloc,
            ) and parsed.path.startswith("/api/v1/media/doc/"):
                continue
            if not row["created_by"]:
                raise ValueError(f"clubs:{row['id']}: certificate owner is unknown")
            backend, key = source_key(item["url"], settings)
            changed.append(
                {
                    "source_url": item["url"],
                    "source_backend": backend,
                    "source_key": key,
                    "filename": target_filename(row["created_by"], item["url"]),
                }
            )
        if changed:
            plan.append(
                {
                    "club_id": row["id"],
                    "owner": row["created_by"],
                    "previous": previous,
                    "files": changed,
                }
            )
    return plan


def read_source(item):
    if item["source_backend"] == "local":
        return Path(storage._local_path(item["source_key"])).read_bytes()
    stream = (
        storage._get_client()
        .get_object(Bucket=storage.settings.OSS_BUCKET_NAME, Key=item["source_key"])[
            "Body"
        ]
        .get_raw_stream()
    )
    try:
        return stream.read()
    finally:
        stream.close()


def apply_plan(connection, plan, backup):
    for club in plan:
        current = connection.execute(
            sa.text("SELECT documents FROM clubs WHERE id=:id FOR UPDATE"),
            {"id": club["club_id"]},
        ).scalar_one()
        if documents(current) != club["previous"]:
            raise RuntimeError(
                f"clubs:{club['club_id']}: documents changed since preflight"
            )
        replacements = {}
        for item in club["files"]:
            filename = item["filename"]
            content = read_source(item)
            ext = Path(filename).suffix
            if ext == ".pdf" and not content.startswith(b"%PDF-"):
                raise RuntimeError(f"clubs:{club['club_id']}: invalid historical PDF")
            digest = hashlib.sha256(content).hexdigest()
            path = backup / filename
            if path.exists() and path.read_bytes() != content:
                raise RuntimeError("Backup content conflict")
            with path.open("wb") as output:
                output.write(content)
            path.chmod(0o600)
            backend = storage.put_private_document(filename, content, ext)
            if backend != "cos":
                raise RuntimeError("Migration requires private COS storage")
            if (
                hashlib.sha256(storage.read_private_document(filename)).hexdigest()
                != digest
            ):
                raise RuntimeError("Private destination checksum mismatch")
            existing = (
                connection.execute(
                    sa.text("SELECT user_id,backend FROM private_uploads WHERE id=:id"),
                    {"id": filename},
                )
                .mappings()
                .first()
            )
            if existing and (
                existing["user_id"] != club["owner"] or existing["backend"] != "cos"
            ):
                raise RuntimeError("Private upload ownership conflict")
            if not existing:
                connection.execute(
                    sa.text(
                        "INSERT INTO private_uploads (id,user_id,backend,content_type,created_at) VALUES (:id,:owner,'cos',:mime,:created)"
                    ),
                    {
                        "id": filename,
                        "owner": club["owner"],
                        "mime": storage.MIME[ext],
                        "created": datetime.now(timezone.utc).replace(tzinfo=None),
                    },
                )
            item["sha256"] = digest
            replacements[item["source_url"]] = (
                f"{storage.settings.PUBLIC_BASE_URL}/api/v1/media/doc/{filename}"
            )
        updated = [
            dict(item, url=replacements.get(item["url"], item["url"]))
            for item in club["previous"]
        ]
        connection.execute(
            sa.text("UPDATE clubs SET documents=:docs WHERE id=:id"),
            {"id": club["club_id"], "docs": json.dumps(updated)},
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("An explicit DATABASE_URL is required")
    url = make_url(os.environ["DATABASE_URL"])
    if url.database == "club_db" and not args.production:
        raise RuntimeError("Production requires --production")
    if args.apply and (
        not args.backup_dir
        or not storage.is_configured()
        or not storage.settings.COS_PRIVATE_BUCKET_NAME
        or storage.settings.COS_PRIVATE_BUCKET_NAME == storage.settings.OSS_BUCKET_NAME
    ):
        raise RuntimeError(
            "Apply requires backup directory and independent private COS bucket"
        )
    engine = sa.create_engine(
        url.set(drivername="mysql+pymysql"), poolclass=sa.pool.NullPool
    )
    try:
        with engine.begin() as conn:
            rows = (
                conn.execute(
                    sa.text("SELECT id,created_by,documents FROM clubs ORDER BY id")
                )
                .mappings()
                .all()
            )
            plan = build_plan(rows, storage.settings)
            print(
                json.dumps(
                    {
                        "mode": "apply" if args.apply else "preflight",
                        "clubs": len(plan),
                        "files": sum(len(c["files"]) for c in plan),
                    }
                )
            )
            if not args.apply:
                return
            backup = args.backup_dir.resolve()
            backup.mkdir(parents=True, exist_ok=True, mode=0o700)
            if backup.stat().st_mode & 0o077:
                raise RuntimeError("Backup directory must have mode 700")
            manifest = backup / "certificates.json"
            if manifest.exists():
                raise RuntimeError(
                    "Use a fresh backup directory; previous manifest is preserved"
                )
            manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
            manifest.chmod(0o600)
            apply_plan(conn, plan, backup)
            manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        print(
            "Certificate references committed; old public permissions were not changed"
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
