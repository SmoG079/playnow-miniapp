#!/usr/bin/env python3
"""Run with sudo on the audited server; stage configuration without restarting."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

DEFAULT_PROJECT = "/home/ubuntu/playnow-miniapp"


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True)


def environment(container):
    return dict(v.split("=", 1) for v in container["Config"]["Env"] if "=" in v)


def digest(container, repository, allow_local=False):
    image = json.loads(docker("image", "inspect", container["Image"]))[0]
    matches = [d for d in image.get("RepoDigests", []) if d.startswith(repository + "@sha256:")]
    if not matches:
        if allow_local:
            print("API has no registry digest; staged reference uses its local image ID and must be replaced before release")
            return image["Id"]
        raise RuntimeError(f"No immutable digest for {repository}; resolve it before staging")
    return matches[0]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sync_container_files(container, source, destination):
    """Copy only absent files, refusing conflicts and symbolic links."""
    with tempfile.TemporaryDirectory(prefix="playnow-persist-") as temp:
        snapshot = Path(temp) / "snapshot"
        snapshot.mkdir()
        subprocess.run(["docker", "cp", f"{container}:{source}/.", str(snapshot)], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        entries = list(snapshot.rglob("*"))
        for path in entries:
            target = destination / path.relative_to(snapshot)
            if path.is_symlink() or target.is_symlink():
                raise RuntimeError("Symlink found in persistent files; manual review required")
            if path.is_file() and target.exists() and (not target.is_file() or file_hash(path) != file_hash(target)):
                raise RuntimeError("Persistent file conflict; existing host file was not overwritten")
        copied = 0
        for path in entries:
            target = destination / path.relative_to(snapshot)
            if path.is_dir():
                target.mkdir(mode=0o755, parents=True, exist_ok=True)
            elif path.is_file() and not target.exists():
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                with target.open("xb") as out, path.open("rb") as inp:
                    shutil.copyfileobj(inp, out)
                target.chmod(0o644)
                copied += 1
        files = [p for p in entries if p.is_file()]
        if any(file_hash(p) != file_hash(destination / p.relative_to(snapshot)) for p in files):
            raise RuntimeError("Persistent file verification failed")
        return {"verified_files": len(files), "copied_files": copied}


def values_from_running_services(containers):
    by_name = {c["Name"].lstrip("/"): c for c in containers}
    api, mysql, redis = (by_name[n] for n in ("club-api", "club-mysql", "club-redis"))
    appenv, dbenv = environment(api), environment(mysql)
    dburl, redisurl = urlsplit(appenv["DATABASE_URL"]), urlsplit(appenv["REDIS_URL"])
    from urllib.parse import unquote
    if dburl.hostname != "mysql" or dburl.path != "/" + dbenv["MYSQL_DATABASE"]:
        raise RuntimeError("Database destination differs from the audited internal service")
    if unquote(dburl.username or "") != dbenv["MYSQL_USER"] or unquote(dburl.password or "") != dbenv["MYSQL_PASSWORD"]:
        raise RuntimeError("Application credentials differ from the existing MySQL configuration")
    command = redis["Config"]["Cmd"]
    password = command[command.index("--requirepass") + 1]
    if redisurl.hostname != "redis" or unquote(redisurl.password or "") != password:
        raise RuntimeError("Redis destination or password differs from the running service")
    def volume(container, target):
        matches = [m["Name"] for m in container["Mounts"] if m["Destination"] == target and m["Type"] == "volume"]
        if len(matches) != 1:
            raise RuntimeError("Expected exactly one existing data volume")
        return matches[0]
    networks = set(api["NetworkSettings"]["Networks"]) & set(mysql["NetworkSettings"]["Networks"]) & set(redis["NetworkSettings"]["Networks"])
    if networks != {"playnow-miniapp_default"}:
        raise RuntimeError("Unexpected network topology")
    return {
        "API_IMAGE": digest(api, "ghcr.io/smog079/playnow-miniapp-api", allow_local=True),
        "MYSQL_IMAGE": digest(mysql, "mysql"),
        "REDIS_IMAGE": digest(redis, "redis"),
        "APP_ENV_FILE": "./backend/.env",
        "PUBLIC_BASE_URL": "https://www.tennisplaynow.site:8443",
        "LOG_LEVEL": "INFO", "DATABASE_URL": appenv["DATABASE_URL"], "REDIS_URL": appenv["REDIS_URL"],
        "MYSQL_DATABASE": dbenv["MYSQL_DATABASE"], "MYSQL_USER": dbenv["MYSQL_USER"],
        "MYSQL_PASSWORD": dbenv["MYSQL_PASSWORD"], "MYSQL_ROOT_PASSWORD": dbenv["MYSQL_ROOT_PASSWORD"],
        "REDIS_PASSWORD": password, "MYSQL_DATA_VOLUME": volume(mysql, "/var/lib/mysql"),
        "REDIS_DATA_VOLUME": volume(redis, "/data"), "APP_NETWORK": "playnow-miniapp_default",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--prepare", action="store_true", help="Create protected pending environment and persistent directories")
    parser.add_argument("--sync-files", action="store_true", help="Refresh uploads; run once more after stopping new writes")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("Run with sudo so no credentials are printed or copied through the client")
    project = Path(args.project).resolve()
    if str(project) != DEFAULT_PROJECT or not (project / "backend/.env").is_file():
        raise RuntimeError("This script is restricted to the audited deployment directory")
    containers = json.loads(docker("inspect", "club-api", "club-mysql", "club-redis"))
    values = values_from_running_services(containers)
    print("Existing credentials, immutable image digests and data volumes verified")
    if not args.prepare and not args.sync_files:
        print("Read-only check complete; no files changed")
        return
    if args.prepare:
        env_path = project / ".env.production.next"
        if any("\n" in value or "\r" in value for value in values.values()):
            raise RuntimeError("Multiline infrastructure variable requires manual review")
        content = "".join(key + "='" + value.replace("'", "\\'") + "'\n" for key, value in values.items())
        if env_path.exists() and env_path.read_text() != content:
            raise RuntimeError("Pending environment already differs; review it before replacing")
        old_mask = os.umask(0o077)
        try:
            if not env_path.exists():
                with env_path.open("x") as file:
                    file.write(content)
            env_path.chmod(0o600)
        finally:
            os.umask(old_mask)
        for rel in ["uploads", "logs/api", "logs/celery-worker", "logs/celery-beat", "certs", "pay-certs", "celerybeat"]:
            path = project / "backend" / rel
            path.mkdir(parents=True, exist_ok=True, mode=0o700 if rel in ("certs", "pay-certs", "celerybeat") else 0o755)
        print("Pending environment written with mode 600; persistent directories prepared")
    result = sync_container_files("club-api", "/app/uploads", project / "backend/uploads")
    print("UPLOAD_COPY", json.dumps(result))
    print("No containers were restarted. Refresh files after stopping new uploads before switching.")


if __name__ == "__main__":
    main()
