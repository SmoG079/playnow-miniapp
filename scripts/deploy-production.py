#!/usr/bin/env python3
"""Serialize, back up, migrate and release the audited Tencent Cloud deployment."""
import argparse
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile
from urllib.parse import quote
import urllib.request

PROJECT = Path("/home/ubuntu/playnow-miniapp")
BACKUP_ROOT = Path("/var/backups/playnow")
APP_CONTAINERS = ["club-celery-beat", "club-api", "club-celery-worker"]


def replace_image(content, reference):
    if not re.fullmatch(r"ghcr\.io/smog079/playnow-miniapp-api:[0-9a-f]{40}", reference):
        raise RuntimeError("Release image must use the full commit SHA")
    lines = [line for line in content.splitlines() if not line.startswith("API_IMAGE=")]
    return "\n".join(lines) + "\nAPI_IMAGE='" + reference + "'\n"


def load_helper(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--docker-config", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise RuntimeError("Root and a full commit SHA are required")
    release = Path(args.release).resolve()
    if PROJECT / ".releases" not in release.parents:
        raise RuntimeError("Release must be staged in the audited project")
    registry = Path(args.docker_config).resolve()
    if registry != release / ".registry":
        raise RuntimeError("Registry credentials must use the protected release directory")
    os.umask(0o077)
    lock_file = (PROJECT / ".deployment.lock").open("a")
    with lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        ready = PROJECT / ".deployment-ready.json"
        if args.bootstrap and ready.exists():
            raise RuntimeError("Already adopted; bootstrap is only for the first release")
        if not args.bootstrap and not ready.exists():
            raise RuntimeError("First deployment requires manual bootstrap; no services were stopped")
        reference = "ghcr.io/smog079/playnow-miniapp-api:" + args.sha
        candidate = release / ".env.candidate"
        source_env = PROJECT / (".env.production.next" if args.bootstrap else ".env.production")
        candidate.write_text(replace_image(source_env.read_text(), reference))
        candidate.chmod(0o600)
        config = release / "compose.production.yml"
        compose = ["docker", "compose", "--project-directory", str(PROJECT), "--env-file", str(candidate), "-f", str(config)]

        def run(argv, phase, input=None):
            result = subprocess.run(argv, input=input, text=True, capture_output=True)
            (release / (phase + ".log")).write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f"{phase} failed; protected log: {release / (phase + '.log')}")
            return result.stdout

        run(["docker", "--config", str(registry), "pull", reference], "pull")
        run(["python3", str(release / "scripts/validate-production.py"), "--compose", str(config),
            "--env-file", str(candidate), "--check-image"], "preflight")
        if args.check_only:
            print("Release preflight passed; no services were stopped")
            return
        resolved = json.loads(run(compose + ["config", "--format", "json"], "resolved-config"))
        # The resolved config contains credentials: keep it on the server with mode 600.
        previous_inspect = json.loads(run(["docker", "inspect", *APP_CONTAINERS], "previous-containers"))
        if not all(c["State"]["Running"] for c in previous_inspect):
            raise RuntimeError("Existing app containers must be running before release")
        previous_state = json.loads(ready.read_text()) if ready.exists() else None
        stopped = False
        migration_started = False
        schema_unchanged = False
        backup = None

        schema_code = """import os,json
    from sqlalchemy import create_engine,inspect
    from sqlalchemy.engine import make_url
    e=create_engine(make_url(os.environ['DATABASE_URL']).set(drivername='mysql+pymysql'))
    i=inspect(e); data={}
    for t in sorted(i.get_table_names()):
        if t=='alembic_version': continue
        data[t]={'columns':i.get_columns(t),'indexes':i.get_indexes(t),'foreign_keys':i.get_foreign_keys(t)}
    print(json.dumps(data,default=str,sort_keys=True));e.dispose()
    """
        def schema_fingerprint(phase):
            data = run(compose + ["run", "--rm", "--no-deps", "-T", "api", "python", "-c", schema_code], phase)
            return hashlib.sha256(json.dumps(json.loads(data), sort_keys=True).encode()).hexdigest()

        try:
            print("Stopping Beat, API and Worker for a backed-up migration window", flush=True)
            # Mark before the first stop so partial stop failure also restores old containers.
            stopped = True
            for container in APP_CONTAINERS:
                run(["docker", "stop", "--time", "120", container], "stop-" + container)
            worker = json.loads(run(["docker", "inspect", "club-celery-worker"], "stopped-worker"))[0]
            if worker["State"].get("ExitCode", 0) != 0:
                raise RuntimeError("Worker did not shut down cleanly; migration was not started")
            prepare = load_helper(release / "scripts/prepare-production.py", "prepare_production")
            prepare.sync_container_files("club-api", "/app/uploads", PROJECT / "backend/uploads")
            beat_info = next(c for c in previous_inspect if c["Name"] == "/club-celery-beat")
            if not any(m["Destination"] == "/app/celerybeat" for m in beat_info["Mounts"]):
                for suffix in ("", ".db", ".dat", ".dir", ".bak"):
                    target = PROJECT / "backend/celerybeat" / ("celerybeat-schedule" + suffix)
                    result = subprocess.run(["docker", "cp", "club-celery-beat:/app/celerybeat-schedule" + suffix, str(target)], capture_output=True)
                    if result.returncode and not suffix:
                        raise RuntimeError("Could not preserve the stopped Beat schedule")
            password = resolved["services"]["redis"]["environment"]["REDIS_PASSWORD"]
            run(["docker", "exec", "-i", "club-redis", "sh"], "redis-save",
                "export REDISCLI_AUTH=" + shlex.quote(password) + "; redis-cli SAVE\n")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = BACKUP_ROOT / (timestamp + "-" + args.sha[:12])
            backup.mkdir(mode=0o700, parents=True)
            dbname = resolved["services"]["mysql"]["environment"]["MYSQL_DATABASE"]
            if dbname != "club_db":
                raise RuntimeError("Unexpected production database name")
            dump_command = ["docker", "exec", "club-mysql", "sh", "-c",
                'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysqldump -uroot --single-transaction --quick --routines --triggers --events --hex-blob --no-tablespaces --set-gtid-purged=OFF "$1"', "dump", dbname]
            with (backup / "dump.stderr").open("wb") as errors:
                process = subprocess.Popen(dump_command, stdout=subprocess.PIPE, stderr=errors)
                with gzip.open(backup / "club_db.sql.gz", "wb") as output:
                    shutil.copyfileobj(process.stdout, output)
                process.stdout.close()
                if process.wait():
                    raise RuntimeError("Database backup failed; migration has not started")
            completed = False
            with gzip.open(backup / "club_db.sql.gz", "rt") as file:
                for line in file:
                    completed |= line.startswith("-- Dump completed on")
            if not completed:
                raise RuntimeError("Database dump is incomplete")
            redis_info = json.loads(run(["docker", "inspect", "club-redis"], "redis-inspect"))[0]
            redis_path = next(m["Source"] for m in redis_info["Mounts"] if m["Destination"] == "/data")
            with tarfile.open(backup / "persistent-files-and-config.tar.gz", "w:gz") as archive:
                for path in [PROJECT / "backend/uploads", PROJECT / "backend/celerybeat", PROJECT / "backend/.env",
                    PROJECT / "docker-compose.yml", PROJECT / "docker-compose.prod.yml", PROJECT / "compose.production.yml",
                    PROJECT / ".env.production", candidate, Path(redis_path), Path("/etc/nginx")]:
                    if path.exists():
                        archive.add(path, arcname=str(path).lstrip("/"))
            (backup / "previous-containers.json").write_text(json.dumps(previous_inspect, indent=2))
            print(f"Backup verified: {backup}", flush=True)
            before = schema_fingerprint("schema-before")
            migration_started = True
            command = ["python", "scripts/adopt_legacy_database.py", "--apply"] if args.bootstrap else ["python", "-m", "alembic", "upgrade", "head"]
            run(compose + ["run", "--rm", "--no-deps", "-T", "api", *command], "migration")
            after = schema_fingerprint("schema-after")
            schema_unchanged = before == after
            if args.bootstrap:
                run(compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "180", "mysql", "redis"], "adopt-infrastructure")
            run(compose + ["up", "-d", "--no-build", "--no-deps", "--wait", "--wait-timeout", "180", "api", "celery_worker", "celery_beat"], "start-app")
            external = run(["curl", "--fail", "--silent", "--show-error", "--max-time", "15", "https://www.tennisplaynow.site:8443/health"], "external-health")
            if json.loads(external).get("status") != "ok":
                raise RuntimeError("External HTTPS response is not the expected API")
            uploads = sorted(p for p in (PROJECT / "backend/uploads").rglob("*") if p.is_file())
            if uploads:
                sample = uploads[0]
                url = "https://www.tennisplaynow.site:8443/uploads/" + quote(str(sample.relative_to(PROJECT / "backend/uploads")))
                with urllib.request.urlopen(url, timeout=15) as response:
                    if hashlib.sha256(response.read()).digest() != hashlib.sha256(sample.read_bytes()).digest():
                        raise RuntimeError("Public upload content differs from the persisted file")
            run(compose + ["exec", "-T", "api", "python", "scripts/check_health.py"], "dependency-health")
            run(compose + ["exec", "-T", "celery_worker", "celery", "-A", "app.tasks.worker", "inspect", "ping", "--timeout", "10"], "worker-health")
            shutil.copyfile(config, PROJECT / "compose.production.yml")
            shutil.copyfile(candidate, PROJECT / ".env.production")
            (PROJECT / ".env.production").chmod(0o600)
            state = {"sha": args.sha, "release": str(release), "backup": str(backup),
                "image": reference, "schema_changed": not schema_unchanged, "deployed_at": timestamp}
            temporary = ready.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, indent=2));temporary.replace(ready)
            print(f"Deployment verified: {args.sha}")
        except Exception:
            if stopped and not migration_started:
                run(["docker", "start", *APP_CONTAINERS], "restore-stopped-app")
                print("Migration did not start; original containers restored", flush=True)
            elif stopped and schema_unchanged and previous_state:
                old_release = Path(previous_state["release"])
                old_compose = ["docker", "compose", "--project-directory", str(PROJECT), "--env-file", str(old_release / ".env.candidate"), "-f", str(old_release / "compose.production.yml")]
                run(old_compose + ["up", "-d", "--no-build", "--no-deps", "--wait", "--wait-timeout", "180", "api", "celery_worker", "celery_beat"], "restore-previous-release")
                print("Schema unchanged; previous application release restored", flush=True)
            else:
                # Do not allow an unverified new app to continue serving after a failed migration/release.
                for name in APP_CONTAINERS:
                    subprocess.run(["docker", "stop", "--time", "120", name], capture_output=True)
                print(f"Release failed after migration started; app remains stopped for recovery. Backup: {backup}", flush=True)
            raise


if __name__ == "__main__":
    main()
