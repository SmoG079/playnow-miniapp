#!/usr/bin/env python3
"""Validate resolved production configuration without printing credentials."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="/home/ubuntu/playnow-miniapp")
    parser.add_argument("--compose", default="compose.production.yml.next")
    parser.add_argument("--env-file", default=".env.production.next")
    parser.add_argument("--check-image", action="store_true", help="Require the new migration and health scripts in the release image")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("Run with sudo to read protected deployment settings")
    project = Path(args.project).resolve()
    result = subprocess.run(["docker", "compose", "--project-directory", str(project), "--env-file",
        str(project / args.env_file), "-f", str(project / args.compose), "config", "--format", "json"],
        text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("Compose configuration did not resolve; credentials were not printed")
    config = json.loads(result.stdout)
    services = config["services"]
    if set(services) != {"api", "mysql", "redis", "celery_worker", "celery_beat"}:
        raise RuntimeError("Expected only the five production services; no Nginx container")
    live = json.loads(subprocess.check_output(["docker", "inspect", "club-api", "club-mysql", "club-redis"], text=True))
    by_name = {c["Name"].lstrip("/"): c for c in live}
    for service, target, key in [("mysql", "/var/lib/mysql", "mysql_data"), ("redis", "/data", "redis_data")]:
        source = next(m["Name"] for m in by_name["club-" + service]["Mounts"] if m["Destination"] == target)
        volume = config["volumes"][key]
        if not volume.get("external") or volume["name"] != source:
            raise RuntimeError(f"{service} volume would change")
        if services[service].get("ports"):
            raise RuntimeError(f"{service} must not publish ports")
        current_image = json.loads(subprocess.check_output(["docker", "image", "inspect", services[service]["image"]], text=True))[0]["Id"]
        if current_image != by_name["club-" + service]["Image"]:
            raise RuntimeError(f"{service} image would change during adoption")
    network = config["networks"]["default"]
    if not network.get("external") or network["name"] != "playnow-miniapp_default":
        raise RuntimeError("Existing application network must be retained")
    api = services["api"]
    if any("build" in s for s in services.values()):
        raise RuntimeError("Production must use prebuilt images")
    ports = api.get("ports", [])
    if len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1" or str(ports[0]["published"]) != "8000":
        raise RuntimeError("API must bind only 127.0.0.1:8000")
    images = {services[s]["image"] for s in ("api", "celery_worker", "celery_beat")}
    if len(images) != 1:
        raise RuntimeError("API and Celery must use the same release image")
    oldenv = dict(v.split("=", 1) for v in by_name["club-api"]["Config"]["Env"] if "=" in v)
    platform_keys = {"PATH", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256", "PYTHON_PIP_VERSION", "PYTHON_SETUPTOOLS_VERSION", "PYTHON_GET_PIP_URL", "PYTHON_GET_PIP_SHA256"}
    changed_keys = {"PUBLIC_BASE_URL", "WX_PAY_CERT_DIR", "LOG_LEVEL", "DEBUG"}
    for service in ("api", "celery_worker", "celery_beat"):
        env = services[service]["environment"]
        jwt_secret = env.get("JWT_SECRET_KEY", "")
        if len(jwt_secret) < 32 or jwt_secret.startswith("generate-a-random-secret-key-here"):
            raise RuntimeError("Production JWT secret is missing or weak; no services were stopped")
        for key, value in oldenv.items():
            if key not in platform_keys | changed_keys and env.get(key) != value:
                raise RuntimeError(f"Existing application setting would change: {key}")
        if env["PUBLIC_BASE_URL"] != "https://www.tennisplaynow.site:8443" or env["DEBUG"] != "false":
            raise RuntimeError("Production public origin/debug setting is incorrect")
        for mount in services[service].get("volumes", []):
            # Compose 2.27 omits false values from the normalized JSON.
            if mount["type"] == "bind" and (mount.get("bind", {}).get("create_host_path", False) or not Path(mount["source"]).is_dir()):
                raise RuntimeError("A required bind directory is missing or would be silently created")
    upload = next(m for m in api["volumes"] if m["target"] == "/app/uploads")
    if upload["source"] != str(project / "backend/uploads"):
        raise RuntimeError("Unexpected upload directory")
    print("PASS: Compose resolves; existing volumes, network, credentials and infrastructure images retained")
    print("PASS: host Nginx preserved; API uses loopback; MySQL/Redis publish no ports; bind directories exist")
    if args.check_image:
        reference = api["image"]
        if not re.fullmatch(r"ghcr\.io/smog079/playnow-miniapp-api(?::[0-9a-f]{40}|@sha256:[0-9a-f]{64})", reference):
            raise RuntimeError("Release requires a registry image pinned by commit SHA or digest")
        image = json.loads(subprocess.check_output(["docker", "image", "inspect", reference], text=True))[0]
        revision = (image.get("Config", {}).get("Labels") or {}).get("org.opencontainers.image.revision")
        if not revision or (":" in reference and "@" not in reference and revision != reference.rsplit(":", 1)[1]):
            raise RuntimeError("Release image revision label does not match its commit SHA")
        required = ["scripts/check_health.py", "scripts/adopt_legacy_database.py", "alembic/versions/20261007_schema_alignment.py"]
        code = "from pathlib import Path; paths=" + repr(required) + "; assert all(Path('/app', p).is_file() for p in paths)"
        result = subprocess.run(["docker", "run", "--rm", "--network", "none", "--memory", "128m", reference,
            "python", "-c", code], capture_output=True)
        if result.returncode:
            raise RuntimeError("Release image lacks the new health/migration scripts")
        print("PASS: release image contains the new health/migration scripts")
    else:
        print("Release image is not yet verified; run again with --check-image after building the release")


if __name__ == "__main__":
    main()
