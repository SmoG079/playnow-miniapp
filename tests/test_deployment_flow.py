"""Exercise release failure boundaries without connecting to Docker or production."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deployment", ROOT / "scripts/deploy-production.py")
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)


class DeploymentFlowTests(unittest.TestCase):
    def exercise(self, *, bootstrap=False, initialized=True, fail=None, schema_changed=False):
        with tempfile.TemporaryDirectory() as temp:
            project = (Path(temp) / "project").resolve();project.mkdir()
            release = project / ".releases/new";release.mkdir(parents=True)
            (release / ".registry").mkdir()
            (release / "compose.production.yml").write_text("services: {}")
            (project / "backend/uploads").mkdir(parents=True)
            (project / "backend/celerybeat").mkdir()
            (project / "backend/.env").write_text("DEBUG=false")
            (project / ".env.production.next").write_text("API_IMAGE=old\nKEEP='literal$dollar'\n")
            (project / ".env.production").write_text("API_IMAGE=old\nKEEP='literal$dollar'\n")
            redis_data = Path(temp) / "redis";redis_data.mkdir()
            old = project / ".releases/old";old.mkdir()
            (old / "compose.production.yml").write_text("services: {}")
            (old / ".env.candidate").write_text("API_IMAGE=old")
            ready = project / ".deployment-ready.json"
            if initialized: ready.write_text(json.dumps({"sha": "b" * 40, "release": str(old)}))
            calls = [];schema_calls = 0

            def fake_run(argv, **kwargs):
                nonlocal schema_calls
                calls.append(argv)
                out = ""
                error = False
                if argv[0] == "curl": out = '{"status":"ok"}'
                if "config" in argv and "--format" in argv:
                    out = json.dumps({"services": {"redis": {"environment": {"REDIS_PASSWORD": "test"}}, "mysql": {"environment": {"MYSQL_DATABASE": "club_db"}}}})
                if argv[:2] == ["docker", "inspect"]:
                    if "club-redis" in argv:
                        out = json.dumps([{"Mounts": [{"Destination": "/data", "Source": str(redis_data)}]}])
                    else:
                        out = json.dumps([{"Name": "/" + name, "State": {"Running": True}, "Mounts": [{"Destination": "/app/celerybeat"}]} for name in deployment.APP_CONTAINERS])
                if "-c" in argv and "get_table_names" in argv[-1]:
                    compile(argv[-1], "<schema-fingerprint>", "exec")
                    schema_calls += 1
                    out = json.dumps({"schema": "new" if schema_changed and schema_calls > 1 else "old"})
                if fail == "preflight" and "--check-image" in argv: error = True
                if fail == "migration" and ("scripts/adopt_legacy_database.py" in argv or ("alembic" in argv and "upgrade" in argv)): error = True
                if fail == "start-app" and "up" in argv and "api" in argv and str(old / "compose.production.yml") not in argv: error = True
                return subprocess.CompletedProcess(argv, 1 if error else 0, stdout=out, stderr="simulated failure" if error else "")

            args = ["deploy-production.py", "--release", str(release), "--sha", "a" * 40, "--docker-config", str(release / ".registry")]
            if bootstrap: args.append("--bootstrap")
            fake_process = SimpleNamespace(stdout=io.BytesIO(b"-- Dump completed on fixture\n"), wait=lambda: 0)
            old_mask = os.umask(0o077)
            caught = None
            try:
                with patch.object(deployment, "PROJECT", project), patch.object(deployment, "BACKUP_ROOT", Path(temp) / "backups"), patch.object(deployment.os, "geteuid", return_value=0), patch.object(deployment, "load_helper", return_value=SimpleNamespace(sync_container_files=lambda *args: None)), patch.object(deployment.subprocess, "run", side_effect=fake_run), patch.object(deployment.subprocess, "Popen", return_value=fake_process), patch.object(sys, "argv", args), redirect_stdout(io.StringIO()):
                    try: deployment.main()
                    except RuntimeError as error: caught = str(error)
            finally:
                os.umask(old_mask)
            state = json.loads(ready.read_text()) if ready.exists() else None
            return calls, caught, state

    def test_first_release_requires_explicit_bootstrap(self):
        calls, error, state = self.exercise(initialized=False)
        self.assertIn("First deployment requires manual bootstrap", error)
        self.assertFalse(calls)
        self.assertIsNone(state)

    def test_failed_preflight_never_stops_services(self):
        calls, error, state = self.exercise(fail="preflight")
        self.assertIn("preflight failed", error)
        self.assertFalse(any(c[:2] == ["docker", "stop"] for c in calls))
        self.assertEqual(state["sha"], "b" * 40)

    def test_bootstrap_success_records_verified_release(self):
        calls, error, state = self.exercise(bootstrap=True, initialized=False, schema_changed=True)
        self.assertIsNone(error)
        self.assertEqual(state["sha"], "a" * 40)
        self.assertTrue(state["schema_changed"])
        self.assertTrue(any("up" in c and "mysql" in c and "redis" in c for c in calls))

    def test_daily_release_does_not_restart_infrastructure(self):
        calls, error, state = self.exercise()
        self.assertIsNone(error)
        self.assertFalse(any("up" in c and ("mysql" in c or "redis" in c) for c in calls))
        self.assertEqual(state["sha"], "a" * 40)

    def test_migration_failure_does_not_start_app_or_stamp_release(self):
        calls, error, state = self.exercise(fail="migration")
        self.assertIn("migration failed", error)
        self.assertFalse(any("up" in c or c[:2] == ["docker", "start"] for c in calls))
        self.assertEqual(state["sha"], "b" * 40)

    def test_unchanged_schema_restores_previous_app_on_start_failure(self):
        calls, error, state = self.exercise(fail="start-app")
        self.assertIn("start-app failed", error)
        self.assertTrue(any("up" in c and any(str(x).endswith("/old/compose.production.yml") for x in c) for c in calls))
        self.assertEqual(state["sha"], "b" * 40)

    def test_changed_schema_stays_stopped_on_start_failure(self):
        calls, error, state = self.exercise(fail="start-app", schema_changed=True)
        self.assertIn("start-app failed", error)
        self.assertFalse(any("up" in c and any(str(x).endswith("/old/compose.production.yml") for x in c) for c in calls))
        self.assertEqual(state["sha"], "b" * 40)

    def test_image_replacement_preserves_other_settings_and_rejects_injection(self):
        content = deployment.replace_image("API_IMAGE='old'\nKEEP='literal$dollar'\n", "ghcr.io/smog079/playnow-miniapp-api:" + "a" * 40)
        self.assertIn("KEEP='literal$dollar'", content)
        self.assertEqual(content.count("API_IMAGE="), 1)
        with self.assertRaises(RuntimeError): deployment.replace_image("", "bad;echo injected")


if __name__ == "__main__":
    unittest.main()
