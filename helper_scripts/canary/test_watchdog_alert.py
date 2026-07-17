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
  - TestAlertSink（WATCHDOG-ALERT-SINK 2026-06-11）：本地耐久 sink 寫入 / 欄位 /
    body 截斷 / >5MB 輪轉 / sink I/O 失敗吞沒且不阻斷發送 / 不改變原函數對外語義。
  - TestAlertRedactor（E3 MED-1 修復輪 2026-06-11）：含毒 subject/body 的 DSN/
    X-BAPI/keyword=value/長 hex/長 base64 遮蔽 + 原語義不變 + 冪等 + sink 與遠送
    雙路皆過 redactor。
  - TestSinkObservability（W-2）：sink 失敗回 False + warning；unconfigured INFO 行據實。
  - TestNoRedirectOpener（E3 LOW）：alert_sink.urlopen_no_redirect 拒 30x（loopback
    自架 server，零外發）。
依賴：engine_watchdog.py、alert_sink.py、app/alert_config.py（path-insert）、
  unittest.mock、tempfile。
硬邊界：全在 tmpdir；不寫 prod /tmp/openclaw；monkeypatch urllib，絕不發真外部 HTTP
  （redirect 測試僅 127.0.0.1 測試自架 server）。
"""

import http.server
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
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
import alert_sink  # noqa: E402
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


# ═══════════════════════════════════════════════════════════════════════════════
# WATCHDOG-ALERT-SINK（2026-06-11）：本地耐久 sink —— 無 creds 也必達
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlertSink(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()
        engine_watchdog._alert_unconfigured_warned = False

    def _sink_path(self):
        return Path(self.dir) / "alerts" / "alerts.jsonl"

    def _read_sink_records(self):
        import json
        path = self._sink_path()
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_sink_written_when_unconfigured(self):
        """creds 全缺 → 不再完全沉默：sink 必達且欄位齊全，channels_attempted=[]。"""
        with _CleanEnv():
            _send_alert_best_effort("SUBJ", "BODY", "CRITICAL", self.dir)
        records = self._read_sink_records()
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["subject"], "SUBJ")
        self.assertEqual(rec["body"], "BODY")
        self.assertEqual(rec["severity"], "CRITICAL")
        self.assertEqual(rec["channels_attempted"], [])
        self.assertIsNone(rec["channels_ok"])
        # ts_utc 為 ISO-8601 UTC 字串（YYYY-MM-DDTHH:MM:SSZ）。
        self.assertRegex(rec["ts_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_sink_written_before_remote_send(self):
        """通道已配置且 urlopen 掛起 → 函數返回時 sink 已落地（寫在嘗試之前），
        channels_attempted 記錄 webhook。"""
        _write_config(self.dir, webhook={
            "enabled": True, "urls": ["https://hook.example.com/x"], "secret": "S",
        })

        def _slow_urlopen(*a, **k):
            time.sleep(30)

        with _CleanEnv(), mock.patch(
            "engine_watchdog.urllib.request.urlopen", side_effect=_slow_urlopen,
        ):
            start = time.monotonic()
            _send_alert_best_effort("S2", "B2", "WARN", self.dir)
            elapsed = time.monotonic() - start
        # fire-and-forget 語義不變（不等待送出）。
        self.assertLess(elapsed, 5.0)
        records = self._read_sink_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["channels_attempted"], ["webhook"])

    def test_sink_body_truncated_2000(self):
        """body > 2000 字 → sink 內截斷到 2000（防單條撐爆）。"""
        with _CleanEnv():
            _send_alert_best_effort("S", "x" * 5000, "WARN", self.dir)
        records = self._read_sink_records()
        self.assertEqual(len(records[0]["body"]), 2000)

    def test_sink_rotation_over_5mb(self):
        """既有 alerts.jsonl > 5MB → append 前 rename 成 .1（保一代），新檔只含本次記錄。"""
        sink_dir = Path(self.dir) / "alerts"
        sink_dir.mkdir(parents=True)
        big = sink_dir / "alerts.jsonl"
        with open(big, "w", encoding="utf-8") as f:
            f.write("{\"old\": true}\n" * 400_000)  # ~5.6MB > 5MB 閾值
        self.assertGreater(big.stat().st_size, 5 * 1024 * 1024)
        with _CleanEnv():
            _send_alert_best_effort("ROT", "B", "INFO", self.dir)
        rotated = sink_dir / "alerts.jsonl.1"
        self.assertTrue(rotated.exists())
        self.assertGreater(rotated.stat().st_size, 5 * 1024 * 1024)
        records = self._read_sink_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["subject"], "ROT")

    def test_sink_io_failure_swallowed_and_send_still_attempted(self):
        """sink 路徑被檔案占用（mkdir 失敗）→ 異常吞沒不拋，遠端發送照常進行。"""
        # 製造 I/O 故障：<data_dir>/alerts 是普通檔案 → mkdir(parents) 必失敗。
        (Path(self.dir) / "alerts").write_text("not a dir", encoding="utf-8")
        _write_config(self.dir, webhook={
            "enabled": True, "urls": ["https://hook.example.com/x"], "secret": "S",
        })
        import threading as _threading
        sent = _threading.Event()

        def _mark_sent(*a, **k):
            sent.set()
            raise OSError("stop here")  # 既有 catch-all 吞掉

        with _CleanEnv(), mock.patch(
            "engine_watchdog.urllib.request.urlopen", side_effect=_mark_sent,
        ):
            # 不應拋例外（sink 失敗被吞）。
            _send_alert_best_effort("S", "B", "CRITICAL", self.dir)
            self.assertTrue(sent.wait(timeout=5.0), "remote send not attempted")

    def test_sink_does_not_change_unconfigured_warn_once(self):
        """原一次性 unconfigured warning 語義不變：仍只 warn 一次；回傳恆 None。"""
        engine_watchdog._alert_unconfigured_warned = False
        with _CleanEnv():
            r1 = _send_alert_best_effort("S", "B", "WARN", self.dir)
            self.assertTrue(engine_watchdog._alert_unconfigured_warned)
            r2 = _send_alert_best_effort("S", "B", "WARN", self.dir)
        self.assertIsNone(r1)
        self.assertIsNone(r2)
        # 兩次呼叫 → sink 兩條（每次必達，與一次性 warn 無關）。
        self.assertEqual(len(self._read_sink_records()), 2)


# ═══════════════════════════════════════════════════════════════════════════════
# E3 MED-1（修復輪 2026-06-12）：redactor —— sink 落盤與遠送雙路皆過脫敏
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlertRedactor(unittest.TestCase):
    """毒樣本逐規則驗證 + 冪等 + sink/遠送雙路；運維語義（host/錯誤類別）必須保留。"""

    # 每行對應一條 redaction 規則（DSN userinfo / X-BAPI / keyword=value / 裸長 hex / 長 base64）。
    POISON_SUBJECT = (
        "engine down: postgres" + "://trading_admin:SuperSecretPw9@127.0.0.1:5432/trading_ai unreachable"
    )
    POISON_BODY = (
        "restart stderr tail: FATAL postgres" + "://user1:Hunter2Pass@10.0.0.8/db refused\\n"
        "X-BAPI-API-KEY: 9KdQpXvTestKeyValue\n"
        "api_key=AbCdEf123456 secret: topsecretvalue token: tok_abc123\n"
        "hmac=ffeeddccbbaa99887766554433221100ffeeddccbbaa9988\n"
        "digest 0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "blob A1b2C3d4A1b2C3d4A1b2C3d4A1b2C3d4A1b2C3d4A1b2C3d4 tail"
    )
    SECRETS = (
        "SuperSecretPw9", "Hunter2Pass", "9KdQpXvTestKeyValue", "AbCdEf123456",
        "topsecretvalue", "tok_abc123",
        "ffeeddccbbaa99887766554433221100ffeeddccbbaa9988",
        "0123456789abcdef0123456789abcdef0123456789abcdef",
        "A1b2C3d4A1b2C3d4A1b2C3d4A1b2C3d4A1b2C3d4A1b2C3d4",
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        engine_watchdog._alert_unconfigured_warned = False

    def tearDown(self):
        self._tmp.cleanup()
        engine_watchdog._alert_unconfigured_warned = False

    def _read_sink_records(self):
        path = Path(self.dir) / "alerts" / "alerts.jsonl"
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def test_each_rule_masks_its_class_and_keeps_ops_semantics(self):
        out = alert_sink.redact_alert_text(self.POISON_SUBJECT + "\n" + self.POISON_BODY)
        for secret in self.SECRETS:
            self.assertNotIn(secret, out)
        # 運維語義保留：host/db 可讀（只遮 userinfo）、錯誤類別字樣在。
        self.assertIn("postgres://***@127.0.0.1:5432/trading_ai", out)
        self.assertIn("engine down", out)
        self.assertIn("restart stderr tail", out)

    def test_redaction_idempotent(self):
        once = alert_sink.redact_alert_text(self.POISON_BODY)
        self.assertEqual(once, alert_sink.redact_alert_text(once))

    def test_redaction_failure_fails_closed_not_open(self):
        """redactor 內部炸 → 回安全佔位，絕不回原文（寧丟內容不漏 secret）。

        註：re.Pattern.sub 是 C 層唯讀屬性不可 patch，改以替換規則表注入故障。
        """
        class _Boom:
            def sub(self, repl, text):
                raise RuntimeError("boom")

        with mock.patch.object(alert_sink, "_REDACTION_RULES", ((_Boom(), "x"),)):
            out = alert_sink.redact_alert_text(self.POISON_BODY)
        self.assertNotIn("Hunter2Pass", out)
        self.assertIn("REDACTION-FAILED", out)

    def test_sink_and_remote_send_both_redacted(self):
        """E3 MED-1 主斷言：毒 body 同時配置 webhook —— 落盤紀錄與遠送 payload 都無 secret。"""
        _write_config(self.dir, webhook={
            "enabled": True, "urls": ["https://hook.example.com/x"], "secret": "S",
        })
        captured, done = [], threading.Event()

        def _capture(req, timeout=None):
            captured.append(req)
            done.set()
            return mock.MagicMock()  # context-manager 兼容替身。

        with _CleanEnv(), mock.patch(
            "engine_watchdog.urllib.request.urlopen", side_effect=_capture,
        ):
            _send_alert_best_effort(self.POISON_SUBJECT, self.POISON_BODY, "CRITICAL", self.dir)
            self.assertTrue(done.wait(timeout=5.0), "remote send not attempted")
        rec = self._read_sink_records()[0]
        remote_payload = captured[0].data.decode("utf-8")
        for secret in self.SECRETS:
            self.assertNotIn(secret, rec["subject"])
            self.assertNotIn(secret, rec["body"])
            self.assertNotIn(secret, remote_payload)

    def test_unconfigured_info_log_subject_redacted(self):
        """INFO 行 log subject（W-2 措辭）也必須是脫敏後文本。"""
        with _CleanEnv(), self.assertLogs("engine_watchdog", level="INFO") as cap:
            _send_alert_best_effort(self.POISON_SUBJECT, "B", "WARN", self.dir)
        joined = "\n".join(cap.output)
        self.assertNotIn("SuperSecretPw9", joined)
        self.assertIn("alert recorded to local sink only", joined)

    def test_creds_load_fail_path_sink_also_redacted(self):
        """憑證讀取炸的分支（channels_attempted=[]）同樣過 redactor。"""
        with _CleanEnv(), mock.patch(
            "engine_watchdog._load_alert_creds", side_effect=OSError("creds boom"),
        ):
            _send_alert_best_effort(self.POISON_SUBJECT, self.POISON_BODY, "CRITICAL", self.dir)
        rec = self._read_sink_records()[0]
        self.assertEqual(rec["channels_attempted"], [])
        for secret in self.SECRETS:
            self.assertNotIn(secret, rec["subject"])
            self.assertNotIn(secret, rec["body"])


# ═══════════════════════════════════════════════════════════════════════════════
# W-2（修復輪 2026-06-12）：sink 失敗觀測面據實
# ═══════════════════════════════════════════════════════════════════════════════


class TestSinkObservability(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        engine_watchdog._alert_unconfigured_warned = False

    def tearDown(self):
        self._tmp.cleanup()
        engine_watchdog._alert_unconfigured_warned = False

    def test_append_alert_sink_returns_true_on_success(self):
        self.assertIs(alert_sink.append_alert_sink(self.dir, "S", "B", "INFO", []), True)

    def test_append_alert_sink_returns_false_and_warns_on_io_failure(self):
        """W-2：失敗回 False + logger.warning（debug 級＝默認不可見＝觀測面沉默）。"""
        (Path(self.dir) / "alerts").write_text("file blocks dir", encoding="utf-8")
        with self.assertLogs("alert_sink", level="WARNING") as cap:
            out = alert_sink.append_alert_sink(self.dir, "S", "B", "INFO", [])
        self.assertIs(out, False)
        self.assertIn("alert sink append failed", "\n".join(cap.output))

    def test_unconfigured_sink_ok_says_recorded(self):
        with _CleanEnv(), self.assertLogs(level="INFO") as cap:
            _send_alert_best_effort("S", "B", "WARN", self.dir)
        joined = "\n".join(cap.output)
        self.assertIn("alert recorded to local sink only", joined)
        self.assertNotIn("alert LOST", joined)

    def test_unconfigured_sink_failed_says_lost_never_recorded(self):
        """sink 壞 + 無通道 = 告警真丟失：必須 WARNING「alert LOST」，不得謊稱 recorded。"""
        (Path(self.dir) / "alerts").write_text("file blocks dir", encoding="utf-8")
        with _CleanEnv(), self.assertLogs(level="INFO") as cap:
            _send_alert_best_effort("S", "B", "WARN", self.dir)
        joined = "\n".join(cap.output)
        self.assertIn("alert LOST: sink write failed and no channels configured", joined)
        self.assertNotIn("alert recorded to local sink", joined)
        # LOST 行必須是 WARNING 級（INFO 會被運維 grep WARNING 漏掉）。
        self.assertTrue(any(
            line.startswith("WARNING:engine_watchdog:alert LOST") for line in cap.output
        ))


# ═══════════════════════════════════════════════════════════════════════════════
# E3 LOW（修復輪 2026-06-12）：禁 redirect opener（loopback 自架 server，零外發）
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoRedirectOpener(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.hits: list = []

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server 介面名
                TestNoRedirectOpener.hits.append(self.path)
                if self.path.startswith("/redir-long"):
                    # 超長 Location（外部可控）：驗 error message 截斷不灌爆 log。
                    self.send_response(302)
                    self.send_header(
                        "Location",
                        f"http://127.0.0.1:{self.server.server_address[1]}/target?pad=" + "x" * 2000,
                    )
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                elif self.path.startswith("/redir"):
                    self.send_response(302)
                    self.send_header(
                        "Location", f"http://127.0.0.1:{self.server.server_address[1]}/target",
                    )
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    body = b"ok"
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            def log_message(self, *args):  # 靜默 http.server 的 stderr 噪音。
                pass

        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_200_passes_through_as_context_manager(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/ok")
        with alert_sink.urlopen_no_redirect(req, timeout=5.0) as resp:
            self.assertEqual(resp.read(), b"ok")

    def test_302_refused_and_target_never_fetched(self):
        type(self).hits.clear()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/redir")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            alert_sink.urlopen_no_redirect(req, timeout=5.0)
        self.assertEqual(ctx.exception.code, 302)
        self.assertIn("redirect refused", str(ctx.exception))
        # 唯一命中 = /redir；/target 從未被請求 = 真沒跟跳（即使同 host 也拒）。
        self.assertEqual(type(self).hits, ["/redir"])

    def test_refused_error_message_bounded_for_cron_log(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/redir-long")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            alert_sink.urlopen_no_redirect(req, timeout=5.0)
        # Location 2000+ 字 → message 截斷 200（exc log 進 cron log 防爆）。
        self.assertLess(len(str(ctx.exception)), 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
