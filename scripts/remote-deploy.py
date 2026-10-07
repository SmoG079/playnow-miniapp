#!/usr/bin/env python3
"""GitHub runner transport: verified host key, protected credentials, no raw shell inputs."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile


def main():
    required = ["SERVER_HOST", "SERVER_USER", "SERVER_PORT", "SERVER_PROJECT_PATH", "SERVER_SSH_KEY",
        "SERVER_KNOWN_HOSTS", "GHCR_TOKEN", "GHCR_USER", "DEPLOY_SHA", "DEPLOY_RUN_ID"]
    values = {key: os.environ[key] for key in required}
    if values["SERVER_HOST"] != "101.34.213.125" or values["SERVER_USER"] != "ubuntu" or values["SERVER_PROJECT_PATH"] != "/home/ubuntu/playnow-miniapp":
        raise RuntimeError("Secrets do not match the audited production target")
    if not re.fullmatch(r"[0-9a-f]{40}", values["DEPLOY_SHA"]) or not re.fullmatch(r"[0-9]+-[0-9]+", values["DEPLOY_RUN_ID"]):
        raise RuntimeError("Invalid release identity")
    port = int(values["SERVER_PORT"])
    if not 0 < port < 65536:
        raise RuntimeError("Invalid SSH port")
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="playnow-deploy-") as temp:
        directory = Path(temp)
        key = directory / "key";known = directory / "known_hosts"
        key.write_text(values["SERVER_SSH_KEY"].replace("\\n", "\n").strip() + "\n");key.chmod(0o600)
        known.write_text(values["SERVER_KNOWN_HOSTS"].strip() + "\n");known.chmod(0o600)
        archive = directory / "release.tar.gz"
        files = ["compose.production.yml", "scripts/deploy-production.py", "scripts/prepare-production.py", "scripts/validate-production.py"]
        with tarfile.open(archive, "w:gz") as tar:
            for file in files: tar.add(root / file, arcname=file)
        destination = values["SERVER_USER"] + "@" + values["SERVER_HOST"]
        options = ["-i", str(key), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(known)]
        remote = values["SERVER_PROJECT_PATH"] + "/.releases/" + values["DEPLOY_SHA"] + "-" + values["DEPLOY_RUN_ID"]
        uploaded = "/tmp/playnow-release-" + values["DEPLOY_RUN_ID"] + ".tar.gz"
        def ssh(args, input=None):
            subprocess.run(["ssh", *options, "-p", str(port), destination, shlex.join(args)], input=input, text=True, check=True)
        try:
            ssh(["sudo", "-n", "install", "-d", "-m", "700", remote, remote + "/.registry"])
            subprocess.run(["scp", *options, "-P", str(port), str(archive), destination + ":" + uploaded], check=True)
            ssh(["sudo", "-n", "tar", "-xzf", uploaded, "-C", remote])
            ssh(["sudo", "-n", "docker", "--config", remote + "/.registry", "login", "ghcr.io", "--username", values["GHCR_USER"], "--password-stdin"], values["GHCR_TOKEN"] + "\n")
            args = ["sudo", "-n", "python3", remote + "/scripts/deploy-production.py", "--release", remote,
                "--sha", values["DEPLOY_SHA"], "--docker-config", remote + "/.registry"]
            if os.environ.get("DEPLOY_BOOTSTRAP") == "true": args.append("--bootstrap")
            ssh(args)
        finally:
            ssh(["sudo", "-n", "rm", "-rf", remote + "/.registry"])
            ssh(["rm", "-f", uploaded])


if __name__ == "__main__":
    main()
