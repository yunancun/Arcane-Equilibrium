#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：WATCHDOG-ALERT-WIRE（2026-06-05）engine-down 非靜默告警單元測試 +
  共用告警 config loader（app/alert_config.py）的 file-primary / env-fallback /
  malformed-safe / SSRF 守衛測試。
主要類/函數：
  - TestAlertConfigLoader：load_alert_config file-primary、env-fallback、壞檔安全、
    save round-trip、mask_secret。
  - TestSSRFGuard：validate_webhook_url 阻擋 metadata / loopback / RFC1918 /
    link-local，允許 public https，拒 http。
  - TestWatchdogEmit：emit_engine_down_alert_if_new 去重（≤1/key）、recovery 清 marker、
    未配置 = no-op 不拋、告警掛起不拖住主循環。
依賴：engine_watchdog.py、app/alert_config.py（path-insert）、unittest.mock、tempfile。
硬邊界：全在 tmpdir；不寫 prod /tmp/openclaw；monkeypatch urllib，絕不發真 HTTP。
"""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# app 的 alert_config 是純標準庫，可直接 path-insert import（不拉 FastAPI / app 套件）。
_APP_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..",
        "program_code", "exchange_connectors", "bybit_connector",
        "control_api_v1", "app",
    )
)
sys.path.insert(0, _APP_DIR)

import alert_config  # noqa: E402
import engine_watchdog  # noqa: E402
from engine_watchdog import (  # noqa: E402
    emit_engine_down_alert_if_new,
    clear_engine_down_alert_marker,
    _send_alert_best_effort,
    _load_alert_creds,
    load_state,
    save_state,
)


def _write_config(data_dir, telegram=None, webhook=None):
    """直接寫一份 alert_config.json（繞過 save，用於測 loader 讀取）。"""
    import json
    cfg = {
        "version": 1,
        "telegram": telegram or {"enabled": False, "bot_token": "", "chat_id": ""},
        "webhook": webhook or {"enabled": False, "urls": [], "secret": ""},
        "updated_at": int(time.time()),
    }
    with open(Path(data_dir) / "alert_config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f)


class _CleanEnv:
    """測試輔助：清掉四個告警 env 變量，確保 env-fallback 測試不被宿主環境污染。"""

    _KEYS = (
        "OPENCLAW_TELEGRAM_BOT_TOKEN", "OPENCLAW_TELEGRAM_CHAT_ID",
        "OPENCLAW_WEBHOOK_URLS", "OPENCLAW_WEBHOOK_SECRET",
    )

    def __enter__(self):
        self._saved = {k: os.environ.pop(k, None) for k in self._KEYS}
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ═══════════════════════════════════════════════════════════════════════════════
# Loader：file-primary / env-fallback / malformed-safe / save round-trip / mask
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlertConfigLoader(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_file_primary_telegram(self):
        """檔內憑證優先：即使 env 也設了，仍以檔為準。"""
        _write_config(self.dir, telegram={
            "enabled": True, "bot_token": "FILE_TOKEN", "chat_id": "FILE_CHAT",
        })
        with _CleanEnv():
            os.environ["OPENCLAW_TELEGRAM_BOT_TOKEN"] = "ENV_TOKEN"
            os.environ["OPENCLAW_TELEGRAM_CHAT_ID"] = "ENV_CHAT"
            cfg = alert_config.load_alert_config(self.dir)
        self.assertTrue(cfg["telegram"]["enabled"])
        self.assertEqual(cfg["telegram"]["bot_token"], "FILE_TOKEN")
        self.assertEqual(cfg["telegram"]["chat_id"], "FILE_CHAT")

    def test_env_fallback_when_file_absent(self):
        """無檔時回退 env（back-compat）。"""
        with _CleanEnv():
            os.environ["OPENCLAW_TELEGRAM_BOT_TOKEN"] = "ENV_TOKEN"
            os.environ["OPENCLAW_TELEGRAM_CHAT_ID"] = "ENV_CHAT"
            os.environ["OPENCLAW_WEBHOOK_URLS"] = "https://a.example.com,https://b.example.com"
            cfg = alert_config.load_alert_config(self.dir)
        self.assertTrue(cfg["telegram"]["enabled"])
        self.assertEqual(cfg["telegram"]["bot_token"], "ENV_TOKEN")
        self.assertTrue(cfg["webhook"]["enabled"])
        self.assertEqual(cfg["webhook"]["urls"], ["https://a.example.com", "https://b.example.com"])

    def test_malformed_file_returns_safe_disabled(self):
        """壞檔（非 JSON）→ 安全 disabled 空殼，永不拋。"""
        with open(Path(self.dir) / "alert_config.json", "w", encoding="utf-8") as f:
            f.write("{ this is not valid json ]]]")
        with _CleanEnv():
            cfg = alert_config.load_alert_config(self.dir)
        self.assertFalse(cfg["telegram"]["enabled"])
        self.assertFalse(cfg["webhook"]["enabled"])
        self.assertEqual(cfg["webhook"]["urls"], [])

    def test_malformed_wrong_types_coerced(self):
        """欄位型別錯（urls 是 dict、token 是 int）→ 收斂成安全預設，不拋。"""
        import json
        with open(Path(self.dir) / "alert_config.json", "w", encoding="utf-8") as f:
            json.dump({
                "telegram": {"enabled": True, "bot_token": 12345, "chat_id": None},
                "webhook": {"enabled": True, "urls": {"bad": 1}, "secret": []},
            }, f)
        with _CleanEnv():
            cfg = alert_config.load_alert_config(self.dir)
        self.assertEqual(cfg["telegram"]["bot_token"], "")
        self.assertEqual(cfg["telegram"]["chat_id"], "")
        self.assertEqual(cfg["webhook"]["urls"], [])
        self.assertEqual(cfg["webhook"]["secret"], "")

    def test_save_then_load_round_trip(self):
        """save → load round-trip；檔權限 0600。"""
        with _CleanEnv():
            alert_config.save_alert_config(self.dir, {
                "version": 1,
                "telegram": {"enabled": True, "bot_token": "TKN", "chat_id": "CHT"},
                "webhook": {"enabled": False, "urls": [], "secret": ""},
            })
            cfg = alert_config.load_alert_config(self.dir)
        self.assertEqual(cfg["telegram"]["bot_token"], "TKN")
        self.assertGreater(cfg["updated_at"], 0)
        # 權限 0600（僅 owner 讀寫）。
        import stat as _stat
        st_mode = os.stat(Path(self.dir) / "alert_config.json").st_mode
        self.assertEqual(_stat.S_IMODE(st_mode), 0o600)
        # E3 LOW-1 (2026-06-05)：明確斷言 group/other 一個讀 bit 都沒有。
        # 為什麼單列：save 先 chmod(tmp,0600) 再 os.replace（rename 沿用來源 inode
        # 權限），確保最終憑證檔一落地即無 0644 窗；此斷言守的就是「never group/other-readable」。
        self.assertEqual(_stat.S_IMODE(st_mode) & (_stat.S_IRGRP | _stat.S_IROTH), 0)

    def test_mask_secret(self):
        self.assertEqual(alert_config.mask_secret(""), "")
        self.assertEqual(alert_config.mask_secret("abc"), "••••")
        self.assertEqual(alert_config.mask_secret("abcdef1234"), "••••1234")


# ═══════════════════════════════════════════════════════════════════════════════
# SSRF 守衛
# ═══════════════════════════════════════════════════════════════════════════════


class TestSSRFGuard(unittest.TestCase):

    def test_blocks_cloud_metadata(self):
        ok, reason = alert_config.validate_webhook_url("https://169.254.169.254/latest/meta-data")
        self.assertFalse(ok)
        self.assertEqual(reason, "blocked_internal_address")

    def test_blocks_loopback(self):
        self.assertFalse(alert_config.validate_webhook_url("https://127.0.0.1/x")[0])
        self.assertFalse(alert_config.validate_webhook_url("https://127.5.5.5/x")[0])

    def test_blocks_rfc1918(self):
        self.assertFalse(alert_config.validate_webhook_url("https://10.0.0.1/x")[0])
        self.assertFalse(alert_config.validate_webhook_url("https://172.16.0.1/x")[0])
        self.assertFalse(alert_config.validate_webhook_url("https://192.168.1.1/x")[0])

    def test_blocks_link_local_and_unspecified(self):
        self.assertFalse(alert_config.validate_webhook_url("https://169.254.1.1/x")[0])
        self.assertFalse(alert_config.validate_webhook_url("https://0.0.0.0/x")[0])

    def test_rejects_non_https(self):
        ok, reason = alert_config.validate_webhook_url("http://8.8.8.8/x")
        self.assertFalse(ok)
        self.assertEqual(reason, "scheme_not_https")

    def test_rejects_control_chars(self):
        self.assertFalse(alert_config.validate_webhook_url("https://8.8.8.8/x\ny")[0])

    def test_allows_public_https(self):
        # 8.8.8.8 是 IP 字面量，不需 DNS；公網位址應放行。
        ok, reason = alert_config.validate_webhook_url("https://8.8.8.8/hook")
        self.assertTrue(ok, msg=f"reason={reason}")


# ═══════════════════════════════════════════════════════════════════════════════
# Watchdog emit：去重 / recovery 清 marker / 未配置 no-op / 告警掛起不拖主循環
# ═══════════════════════════════════════════════════════════════════════════════


def _count_canary(data_dir, event_name):
    """數 canary_events.jsonl 中指定 event 出現次數。"""
    import json
    path = Path(data_dir) / "canary_events.jsonl"
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(line).get("event") == event_name:
                n += 1
        except json.JSONDecodeError:
            continue
    return n


class TestWatchdogEmit(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        # 配一個 webhook 通道（用 mock urlopen，不發真 HTTP）。
        _write_config(self.dir, webhook={
            "enabled": True, "urls": ["https://hook.example.com/x"], "secret": "S3CR3T",
        })

    def tearDown(self):
        self._tmp.cleanup()

    def test_emit_dedup_one_per_key(self):
        """同一 key 重複 emit → 只發一次（去重），canary 計數 == 1。"""
        with mock.patch("engine_watchdog.urllib.request.urlopen"):
            now = time.time()
            r1 = emit_engine_down_alert_if_new(self.dir, "circuit_broken", "S", "B", now)
            r2 = emit_engine_down_alert_if_new(self.dir, "circuit_broken", "S", "B", now + 5)
            r3 = emit_engine_down_alert_if_new(self.dir, "circuit_broken", "S", "B", now + 10)
        self.assertTrue(r1)
        self.assertFalse(r2)
        self.assertFalse(r3)
        self.assertEqual(_count_canary(self.dir, "ENGINE_DOWN_ALERT_SENT"), 1)
        # marker 已持久化。
        st = load_state(self.dir)
        self.assertEqual(st["last_engine_down_alert_key"], "circuit_broken")
        self.assertIn("engine_down_since_ts", st)

    def test_recovery_clears_marker_allows_re_emit(self):
        """recovery 清 marker → 之後同 key 可再發一次（不被永久去重吞掉）。"""
        with mock.patch("engine_watchdog.urllib.request.urlopen"):
            now = time.time()
            self.assertTrue(emit_engine_down_alert_if_new(self.dir, "circuit_broken", "S", "B", now))
            clear_engine_down_alert_marker(self.dir)
            # 清後 marker 不存在。
            st = load_state(self.dir)
            self.assertIsNone(st.get("last_engine_down_alert_key"))
            self.assertNotIn("engine_down_since_ts", st)
            # 同 key 可再發。
            self.assertTrue(emit_engine_down_alert_if_new(self.dir, "circuit_broken", "S", "B", now + 100))
        self.assertEqual(_count_canary(self.dir, "ENGINE_DOWN_ALERT_SENT"), 2)

    def test_different_keys_each_emit(self):
        """不同 key（prolonged-down 每窗口換 key）→ 各發一次。"""
        with mock.patch("engine_watchdog.urllib.request.urlopen"):
            now = time.time()
            emit_engine_down_alert_if_new(self.dir, "circuit_broken", "S", "B", now)
            emit_engine_down_alert_if_new(self.dir, "circuit_broken_reping_4", "S", "B", now + 14400)
            emit_engine_down_alert_if_new(self.dir, "circuit_broken_reping_8", "S", "B", now + 28800)
        self.assertEqual(_count_canary(self.dir, "ENGINE_DOWN_ALERT_SENT"), 3)

    def test_unconfigured_is_noop_and_does_not_raise(self):
        """無任一通道配置 → _send_alert_best_effort no-op，不拋；一次性 warn。"""
        empty = tempfile.TemporaryDirectory()
        try:
            engine_watchdog._alert_unconfigured_warned = False
            with _CleanEnv():
                # 不應拋例外。
                _send_alert_best_effort("S", "B", "CRITICAL", empty.name)
            self.assertTrue(engine_watchdog._alert_unconfigured_warned)
        finally:
            empty.cleanup()
            engine_watchdog._alert_unconfigured_warned = False

    def test_hanging_send_does_not_stall(self):
        """告警 urlopen 掛起（sleep > timeout）→ emit 仍迅速返回（fire-and-forget daemon thread）。

        為什麼這條最關鍵：load-bearing 失敗隔離 —— 掛起的端點絕不可拖住 watchdog。
        """
        def _slow_urlopen(*a, **k):
            time.sleep(30)  # 遠超 5s timeout；若非 daemon thread，emit 會卡 30s。

        with mock.patch("engine_watchdog.urllib.request.urlopen", side_effect=_slow_urlopen):
            start = time.monotonic()
            emit_engine_down_alert_if_new(self.dir, "circuit_broken", "S", "B", time.time())
            elapsed = time.monotonic() - start
        # emit 不等送出完成 → 應遠小於 30s（給寬鬆上限 5s）。
        self.assertLess(elapsed, 5.0)

    def test_raising_send_does_not_propagate(self):
        """urlopen 拋例外 → 被 catch-all 吞掉，emit 正常返回 True 並寫 canary。"""
        with mock.patch("engine_watchdog.urllib.request.urlopen", side_effect=OSError("boom")):
            r = emit_engine_down_alert_if_new(self.dir, "circuit_broken", "S", "B", time.time())
        self.assertTrue(r)
        self.assertEqual(_count_canary(self.dir, "ENGINE_DOWN_ALERT_SENT"), 1)

    def test_creds_loader_file_primary(self):
        """watchdog 內聯 loader file-primary：讀到檔內 webhook。"""
        with _CleanEnv():
            creds = _load_alert_creds(self.dir)
        self.assertTrue(creds["webhook"]["enabled"])
        self.assertEqual(creds["webhook"]["urls"], ["https://hook.example.com/x"])
        self.assertEqual(creds["webhook"]["secret"], "S3CR3T")

    def test_creds_loader_env_fallback(self):
        """watchdog 內聯 loader env-fallback：無檔時回退 env。"""
        empty = tempfile.TemporaryDirectory()
        try:
            with _CleanEnv():
                os.environ["OPENCLAW_TELEGRAM_BOT_TOKEN"] = "T"
                os.environ["OPENCLAW_TELEGRAM_CHAT_ID"] = "C"
                creds = _load_alert_creds(empty.name)
            self.assertTrue(creds["telegram"]["enabled"])
            self.assertEqual(creds["telegram"]["bot_token"], "T")
        finally:
            empty.cleanup()

    def test_no_secret_leak_in_canary(self):
        """canary 事件不得含 token / secret（只 log alert_key / channel 名）。"""
        with mock.patch("engine_watchdog.urllib.request.urlopen"):
            emit_engine_down_alert_if_new(self.dir, "circuit_broken", "S", "B", time.time())
        raw = (Path(self.dir) / "canary_events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("S3CR3T", raw)
        self.assertNotIn("hook.example.com", raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
