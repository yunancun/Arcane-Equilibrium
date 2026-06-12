#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：watchdog 告警鏈的共用小模組（從 engine_watchdog.py 抽出——該檔 pre-existing
  已超 2000 行硬頂，本批新增的 sink/redactor 落此 sibling，主檔只留薄調用；E2-B MED-1）。
主要函數：
  - redact_alert_text：告警 subject/body 脫敏（E3 MED-1）。為什麼必須有：body 可內嵌
    `last_failure_reason`（= restart_all.sh stderr 尾段），引擎連 PG 失敗時 stderr 可含
    DSN（postgres://user:pass@host）；哨兵 body 則含外部公告文本。sink 落盤、INFO log
    與 Telegram/webhook 遠送共用同一脫敏入口，任一路徑都不得見原始 secret。
  - append_alert_sink：本地耐久告警 sink（append 一條 JSON 到 <data_dir>/alerts/
    alerts.jsonl）。遠端通道 creds 缺席或全掛時告警不得蒸發——本地 jsonl 是「無 creds
    也必達」的最後審計線。回傳 bool（W-2：寫入失敗時 caller 觀測面必須據實，不得謊稱
    recorded）。
  - urlopen_no_redirect：禁 redirect 的 urllib opener（E3 LOW）。外連面（Bybit 公告
    GET 等）跟跳 redirect = 出口可被 30x 引去任意 host；唯讀公開 API 不應 redirect，
    一律拒（30x 升 HTTPError，caller 走既有 fail-quiet 路徑）。
依賴：純標準庫（json/logging/os/re/time/urllib/pathlib）。
硬邊界：
  - append_alert_sink 永不拋：sink 是附加觀測面，任何 I/O 失敗（磁碟滿/權限/路徑被占）
    都不得影響 _send_alert_best_effort 的 best-effort 語義，更不得回拋進 watchdog
    恢復迴圈（失敗 → logger.warning + return False）。
  - redact_alert_text 冪等：已脫敏文本再過一次輸出不變（雙重調用安全）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger("alert_sink")

# ── sink 常數（自 engine_watchdog.py 移入，語義不變） ──

ALERT_SINK_DIRNAME = "alerts"
ALERT_SINK_FILE = "alerts.jsonl"
ALERT_SINK_MAX_BYTES = 5 * 1024 * 1024  # >5MB 輪轉一代（rename .1，保一代）
ALERT_SINK_BODY_MAX_CHARS = 2000  # body 截斷上限（防單條告警撐爆 sink）

# ── redactor（E3 MED-1） ──

_REDACT = "***"

# 規則序：先結構性形（URL userinfo / header / keyword=value）再裸長 token 形
# （hex/base64）。全部冪等：替換結果不再命中自身規則的新洩漏形。
_REDACTION_RULES: tuple[tuple[re.Pattern, str], ...] = (
    # ① URL userinfo（DSN 形）：postgres://user:pass@host → postgres://***@host。
    #    泛化到任意 scheme（mysql/redis/amqp 同為 DSN 形）；[^/\s@]+ 限定 userinfo 位
    #    （:// 與首個 / 之間的 @ 前段），不誤傷路徑中的 @；host/port/db 保留（語義可讀）。
    (re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/\s@]+@"), r"\1" + _REDACT + "@"),
    # ② Bybit 簽名面 header：X-BAPI-API-KEY / X-BAPI-SIGN / X-BAPI-TIMESTAMP… 值全遮。
    (re.compile(r"(X-BAPI-[A-Za-z0-9-]+\s*[=:]\s*)\S+", re.IGNORECASE), r"\1" + _REDACT),
    # ③ keyword=value：api_key/secret/token/signing_key/hmac(_key)/password 後接 =/: 的值。
    #    寬鬆寧多遮不漏遮（告警 body 是運維文本，誤遮一個詞代價遠小於漏一個 key）。
    (
        re.compile(
            r"((?:api[_-]?key|secret|token|signing[_-]?key|hmac(?:[_-]key)?|password|passwd)"
            r"\s*[=:]\s*)\S+",
            re.IGNORECASE,
        ),
        r"\1" + _REDACT,
    ),
    # ④ 長 hex run（≥32：sha256/hmac-hex/簽名長度帶；短 hex 如 blt UID 16 位不誤傷）。
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), _REDACT),
    # ⑤ 長 base64 樣式（標準字元集 ≥40 且至少含一個數字；字元集不含 '-'，
    #    故公告 url 的長 slug（hyphen 連接）不誤傷）。
    (re.compile(r"\b(?=[A-Za-z0-9+/]*\d)[A-Za-z0-9+/]{40,}={0,2}"), _REDACT),
)


def redact_alert_text(text) -> str:
    """告警文本脫敏：DSN userinfo / X-BAPI header / keyword=value / 長 hex / 長 base64。

    為什麼保守遮而非整段丟棄：告警的運維語義（host、錯誤類別、action 指引）必須保留，
    只遮 secret 本體；遮蔽後文本對 operator 仍可讀可定位。
    永不拋：脫敏自身失敗時回傳安全佔位（fail-closed——寧丟內容不漏 secret）。
    """
    try:
        out = str(text)
        for pattern, repl in _REDACTION_RULES:
            out = pattern.sub(repl, out)
        return out
    except Exception:  # noqa: BLE001 - redactor 故障不得拋進告警鏈；fail-closed 不回原文
        return "[REDACTION-FAILED: content withheld]"


# ── 本地耐久 sink ──


def append_alert_sink(
    data_dir: str, subject: str, body: str, severity: str, channels_attempted: list
) -> bool:
    """本地耐久告警 sink：append 一條 JSON 到 <data_dir>/alerts/alerts.jsonl。

    為什麼存在：遠端通道（Telegram/webhook）creds 缺席或全掛時，告警不得蒸發——
    本地 jsonl 是「無 creds 也必達」的最後審計線（operator 可事後 tail 查）。
    為什麼包死 try/except 永不拋：sink 是附加觀測面，任何 I/O 失敗都不得影響
    _send_alert_best_effort 原有 best-effort 語義，更不得回拋進 watchdog 恢復迴圈。
    W-2（E2 2026-06-11）：失敗回 False + logger.warning（告警可能真丟失，觀測面
    不得沉默在 debug 級）；caller 據回傳值決定 INFO 措辭。
    防禦縱深：subject/body 在此再過一次 redactor（冪等）——任何未來 caller 繞過
    上游脫敏點也不會把原始 secret 落盤。
    輪轉：append 前 size > ALERT_SINK_MAX_BYTES → os.replace 成 .1（保一代）。
    channels_ok 恆 null：發送是 fire-and-forget daemon thread，append 時點無法同步
    得知送達結果；欄位保留為 schema 前向兼容。

    Returns:
        True 已落盤；False 寫入失敗（已 warning，絕不拋）。
    """
    try:
        sink_dir = Path(data_dir) / ALERT_SINK_DIRNAME
        sink_dir.mkdir(parents=True, exist_ok=True)
        path = sink_dir / ALERT_SINK_FILE
        try:
            if path.stat().st_size > ALERT_SINK_MAX_BYTES:
                os.replace(path, path.with_suffix(".jsonl.1"))
        except OSError:
            pass  # 檔不存在或 stat 失敗 → 不輪轉，直接 append
        record = {
            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "subject": redact_alert_text(subject),
            "severity": str(severity),
            # 先脫敏再截斷：反序可能把 secret 截一半留尾段可見（半個 key 仍是洩漏）。
            "body": redact_alert_text(body)[:ALERT_SINK_BODY_MAX_CHARS],
            "channels_attempted": list(channels_attempted),
            "channels_ok": None,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return True
    except Exception as exc:  # noqa: BLE001 - sink 失敗絕不影響告警主路徑
        # W-2：升 warning——sink 失敗 + 無遠端通道時告警=真丟失，debug 級等於沉默。
        logger.warning("alert sink append failed (alert may be lost): %s", exc)
        return False


def redact_and_sink(
    data_dir: str, subject: str, body: str, severity: str, channels_attempted: list
) -> tuple:
    """脫敏 + 落 sink 的複合入口（engine_watchdog 薄調用點）。

    回 (redacted_subject, redacted_body, sink_ok)：caller 必須改用回傳的脫敏文本做
    遠端發送與 log——這是「sink 與遠送共用同一脫敏」的結構保證（E3 MED-1）。
    """
    subject = redact_alert_text(subject)
    body = redact_alert_text(body)
    sink_ok = append_alert_sink(data_dir, subject, body, severity, channels_attempted)
    return subject, body, sink_ok


# ── 禁 redirect 的 urllib opener（E3 LOW） ──


class _RedirectRefusedHandler(urllib.request.HTTPRedirectHandler):
    """把任何 30x redirect 升為 HTTPError。

    為什麼全拒而非僅跨 host：唯讀公開 API（Bybit 公告等）正常路徑不應 redirect；
    「同 host redirect 放行」需要解析比對 Location，多出的解析面只為一個不存在的
    正常場景——全拒更簡單且 fail-closed，誤拒由 caller 的 fail-quiet + meta-alert 可見。
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        # newurl 截斷 200：Location header 是外部可控文本（可達數十 KB），原樣入
        # error message 會經 caller 的 exc log 灌爆 cron log（截斷自查 2026-06-12）。
        raise urllib.error.HTTPError(
            req.full_url, code, f"redirect refused (-> {str(newurl)[:200]!r})", headers, fp,
        )


_NO_REDIRECT_OPENER = urllib.request.build_opener(_RedirectRefusedHandler())


def urlopen_no_redirect(req, timeout: float):
    """urlopen 等價物，但任何 30x 一律 raise HTTPError（不跟跳）。

    介面對齊 urllib.request.urlopen(req, timeout=…)（回應物支援 context manager），
    既有注入式測試替身（callable(req, timeout=…)）可無縫替換本函數。
    """
    return _NO_REDIRECT_OPENER.open(req, timeout=timeout)
