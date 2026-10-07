"""Verify compressed image integrity and refusal to load a corrupted transfer."""
import gzip
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("transport", ROOT / "scripts/remote-deploy.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


class ImageTransportTests(unittest.TestCase):
    def test_export_is_complete_and_digest_matches_transferred_bytes(self):
        payload = b"image tar payload" * 1000
        process = SimpleNamespace(stdout=io.BytesIO(payload), wait=lambda: 0)
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(transport.subprocess, "run") as run, patch.object(transport.subprocess, "Popen", return_value=process):
                archive, digest = transport.export_image("release:sha", Path(temp), "user", "test-token")
            self.assertEqual(gzip.decompress(archive.read_bytes()), payload)
            self.assertEqual(digest, hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(run.call_args_list[0].kwargs["input"], "test-token\n")

    def test_failed_export_is_not_accepted(self):
        process = SimpleNamespace(stdout=io.BytesIO(b"partial"), wait=lambda: 1)
        with tempfile.TemporaryDirectory() as temp, patch.object(transport.subprocess, "run"), patch.object(transport.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "export failed"):
                transport.export_image("release:sha", Path(temp), "user", "test-token")

    def test_corrupted_transfer_never_loads_image_or_starts_deployment(self):
        self.exercise_transfer(corrupted=True)

    def test_valid_transfer_loads_before_deployment_and_cleans_up(self):
        self.exercise_transfer(corrupted=False)

    def exercise_transfer(self, corrupted):
        env = {"SERVER_HOST": "101.34.213.125", "SERVER_USER": "ubuntu", "SERVER_PORT": "22",
            "SERVER_PROJECT_PATH": "/home/ubuntu/playnow-miniapp", "SERVER_SSH_KEY": "test-key",
            "SERVER_KNOWN_HOSTS": "test-host", "GHCR_TOKEN": "test-token", "GHCR_USER": "user",
            "DEPLOY_SHA": "a" * 40, "DEPLOY_RUN_ID": "123-1", "DEPLOY_BOOTSTRAP": "true"}
        calls = []

        def fake_run(argv, **kwargs):
            if argv[0] == "ssh":
                remote = shlex.split(argv[-1]); calls.append(remote)
                self.assertNotIn("test-token", kwargs.get("input") or "")
                if remote[0] == "sha256sum" and corrupted:
                    raise subprocess.CalledProcessError(1, argv)
            return subprocess.CompletedProcess(argv, 0)

        def fake_export(reference, directory, username, token):
            archive = directory / "image.tar.gz"; archive.write_bytes(b"payload")
            return archive, "b" * 64

        with patch.dict(os.environ, env, clear=True), patch.object(transport, "export_image", side_effect=fake_export), patch.object(transport.subprocess, "run", side_effect=fake_run):
            if corrupted:
                with self.assertRaises(subprocess.CalledProcessError): transport.main()
            else:
                transport.main()
        load = [i for i, c in enumerate(calls) if "load" in c]
        deploy = [i for i, c in enumerate(calls) if "--image-loaded" in c]
        check = next(i for i, c in enumerate(calls) if c[0] == "sha256sum")
        if corrupted:
            self.assertFalse(load); self.assertFalse(deploy)
        else:
            self.assertLess(check, load[0]); self.assertLess(load[0], deploy[0])
            self.assertIn("--bootstrap", calls[deploy[0]])
        self.assertEqual(calls[-1], ["rm", "-f", "/tmp/playnow-release-123-1.tar.gz", "/tmp/playnow-image-123-1.tar.gz"])


if __name__ == "__main__":
    unittest.main()
