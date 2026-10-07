#!/usr/bin/env python3
"""GitHub runner transport: verified host key, protected credentials, no raw shell inputs."""
import os
import gzip
import hashlib
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor


def export_image(reference, directory, username, token):
    """Pull on the runner and export without storing registry credentials on the host."""
    registry = directory / "registry"
    registry.mkdir(mode=0o700)
    docker = ["docker", "--config", str(registry)]
    subprocess.run(docker + ["login", "ghcr.io", "--username", username, "--password-stdin"],
        input=token + "\n", text=True, check=True)
    subprocess.run(docker + ["pull", reference], check=True)
    archive = directory / "image.tar.gz"
    process = subprocess.Popen(["docker", "save", reference], stdout=subprocess.PIPE)
    try:
        with gzip.open(archive, "wb", compresslevel=1) as output:
            shutil.copyfileobj(process.stdout, output)
    finally:
        process.stdout.close()
    if process.wait():
        raise RuntimeError("Runner image export failed")
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return archive, digest.hexdigest()


def transfer_image(archive, remote_parts, uploaded_image, ssh, scp):
    """Use bounded concurrent streams, then reassemble in the original order."""
    parts = []
    with archive.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            part = archive.parent / f"part-{len(parts):05d}"
            part.write_bytes(chunk)
            parts.append(part)
    if not parts:
        raise RuntimeError("Cannot transfer an empty image archive")
    ssh(["mkdir", "-m", "700", remote_parts])
    targets = [remote_parts + "/" + p.name for p in parts]
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(scp, part, target) for part, target in zip(parts, targets)]
        for future in futures:
            future.result()
    ssh(["sh", "-c", shlex.join(["cat", "--", *targets]) + " > " + shlex.quote(uploaded_image)])


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
        options = ["-i", str(key), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=12", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(known)]
        remote = values["SERVER_PROJECT_PATH"] + "/.releases/" + values["DEPLOY_SHA"] + "-" + values["DEPLOY_RUN_ID"]
        uploaded = "/tmp/playnow-release-" + values["DEPLOY_RUN_ID"] + ".tar.gz"
        uploaded_image = "/tmp/playnow-image-" + values["DEPLOY_RUN_ID"] + ".tar.gz"
        remote_parts = "/tmp/playnow-image-" + values["DEPLOY_RUN_ID"] + ".parts"
        def ssh(args, input=None):
            subprocess.run(["ssh", *options, "-p", str(port), destination, shlex.join(args)], input=input, text=True, check=True)
        def scp(source, target):
            subprocess.run(["scp", *options, "-P", str(port), str(source), destination + ":" + target], check=True, timeout=900)
        try:
            if os.environ.get("DEPLOY_BOOTSTRAP") != "true":
                try:
                    ssh(["sudo", "-n", "test", "-f", values["SERVER_PROJECT_PATH"] + "/.deployment-ready.json"])
                except subprocess.CalledProcessError as error:
                    raise RuntimeError("First deployment requires manual bootstrap; no image was transferred or services stopped") from error
            reference = "ghcr.io/smog079/playnow-miniapp-api:" + values["DEPLOY_SHA"]
            image, digest = export_image(reference, directory, values["GHCR_USER"], values["GHCR_TOKEN"])
            ssh(["sudo", "-n", "install", "-d", "-m", "700", remote, remote + "/.registry"])
            subprocess.run(["scp", *options, "-P", str(port), str(archive), destination + ":" + uploaded], check=True)
            ssh(["sudo", "-n", "tar", "-xzf", uploaded, "-C", remote])
            transfer_image(image, remote_parts, uploaded_image, ssh, scp)
            ssh(["sha256sum", "--check", "--status"], digest + "  " + uploaded_image + "\n")
            ssh(["sudo", "-n", "docker", "load", "--input", uploaded_image])
            args = ["sudo", "-n", "python3", remote + "/scripts/deploy-production.py", "--release", remote,
                "--sha", values["DEPLOY_SHA"], "--docker-config", remote + "/.registry", "--image-loaded"]
            if os.environ.get("DEPLOY_BOOTSTRAP") == "true": args.append("--bootstrap")
            ssh(args)
        finally:
            ssh(["sudo", "-n", "rm", "-rf", remote + "/.registry"])
            ssh(["rm", "-f", uploaded, uploaded_image])
            ssh(["rm", "-rf", "--", remote_parts])


if __name__ == "__main__":
    main()
