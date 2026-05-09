#!/usr/bin/env python3
"""Unit tests for passive_wait_healthcheck `[56]` live_pipeline_active."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_live_pipeline import (  # noqa: E402
    check_56_live_pipeline_active,
)


class TestLivePipelineHealthcheck(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.secrets = self.root / "secrets"
        self.data = self.root / "runtime"
        self.live = self.secrets / "live"
        self.live.mkdir(parents=True)
        self.data.mkdir(parents=True)
        os.environ["OPENCLAW_SECRETS_DIR"] = str(self.secrets)
        os.environ["OPENCLAW_DATA_DIR"] = str(self.data)
        os.environ.pop("OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED", None)
        os.environ.pop("OPENCLAW_LIVE_PIPELINE_STALE_SECONDS", None)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        self.tmp.cleanup()

    def _write_live_slot(self, endpoint: str = "demo") -> None:
        (self.live / "api_key").write_text("key", encoding="utf-8")
        (self.live / "api_secret").write_text("secret", encoding="utf-8")
        (self.live / "bybit_endpoint").write_text(endpoint, encoding="utf-8")

    def _write_auth(self) -> None:
        (self.live / "authorization.json").write_text("{}", encoding="utf-8")

    def _write_snapshot(self, *, age_seconds: float) -> None:
        path = self.data / "pipeline_snapshot_live.json"
        path.write_text("{}", encoding="utf-8")
        ts = time.time() - age_seconds
        os.utime(path, (ts, ts))

    def test_unconfigured_live_slot_pass_skips_by_default(self) -> None:
        status, msg = check_56_live_pipeline_active()

        self.assertEqual(status, "PASS")
        self.assertIn("not configured", msg)
        self.assertIn("api_key=False", msg)

    def test_required_unconfigured_live_slot_fails(self) -> None:
        os.environ["OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED"] = "1"

        status, msg = check_56_live_pipeline_active()

        self.assertEqual(status, "FAIL")
        self.assertIn("health required", msg)
        self.assertIn("api_secret=False", msg)

    def test_explicitly_disabled_returns_pass_even_when_configured(self) -> None:
        self._write_live_slot()
        os.environ["OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED"] = "0"

        status, msg = check_56_live_pipeline_active()

        self.assertEqual(status, "PASS")
        self.assertIn("disabled", msg)

    def test_configured_live_demo_missing_authorization_fails(self) -> None:
        self._write_live_slot(endpoint="demo")

        status, msg = check_56_live_pipeline_active()

        self.assertEqual(status, "FAIL")
        self.assertIn("endpoint=live_demo", msg)
        self.assertIn("authorization_json_missing", msg)

    def test_configured_auth_present_but_missing_snapshot_fails(self) -> None:
        self._write_live_slot(endpoint="demo")
        self._write_auth()

        status, msg = check_56_live_pipeline_active()

        self.assertEqual(status, "FAIL")
        self.assertIn("auth=present", msg)
        self.assertIn("snapshot missing", msg)

    def test_configured_auth_present_but_stale_snapshot_fails(self) -> None:
        self._write_live_slot(endpoint="demo")
        self._write_auth()
        self._write_snapshot(age_seconds=600)

        status, msg = check_56_live_pipeline_active()

        self.assertEqual(status, "FAIL")
        self.assertIn("snapshot stale", msg)
        self.assertIn("threshold=180s", msg)

    def test_configured_auth_present_fresh_snapshot_passes(self) -> None:
        self._write_live_slot(endpoint="demo")
        self._write_auth()
        self._write_snapshot(age_seconds=5)

        status, msg = check_56_live_pipeline_active()

        self.assertEqual(status, "PASS")
        self.assertIn("live pipeline active", msg)
        self.assertIn("endpoint=live_demo", msg)


if __name__ == "__main__":
    unittest.main()
