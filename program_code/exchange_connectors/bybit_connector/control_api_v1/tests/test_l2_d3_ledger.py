"""
L2 Advisory Mesh — D3 Provenance & Audit Phase 1 測試。

覆蓋（驗意圖，非僅行為）：
  - l2_secret_redactor（v4）：keyword-gated + 結構臂遮罩 / 冪等 / 版本 / JSONB 遞迴 /
    良性散文無誤遮（負向）/ store-original-by-span（偵測 normalized、存入原文）/
    naked-context-free 高熵殘留（xfail-strict，operator 2026-06-08 拍板 A）/
    v4 CRITICAL fast-path gate fix（gate-set==strip-set，brute-force 全 Cf route slow-path）/
    v4 keyword 補全（hmac/signing/auth/裸 secret/private_key，free-text + JSONB-key 兩形）/
    v4 size cap（256KB 截斷 + marker + 冪等 + worst-case bound，DoS guard）。
  - L2CallLedgerWriter.record_l2_call：消毒在 INSERT 之前（寫入路徑無窗口）、
    sha256 算在已消毒文本上、合成密鑰永不 verbatim 落庫、redactor_version 入庫、
    str(e) 永不 verbatim（classified error_code）、INSERT-only（無 UPDATE/DELETE）。
  - Layer2CostTracker.record_session：session 自由文本欄（final_summary /
    recommendation.reasoning / insights）落 durable state 前過 redactor（§D.1.1）。
  - record_consequential_mark / record_gate_seam：INSERT-only、details 消毒。
  - DB 不可用 fail-soft（ok=False，NEVER raise）。
  - 接線可達性：layer2_engine._record_l2_call_to_ledger 真呼叫 writer 並綁
    session.l2_reply_id（證明 writer reachable 非死碼）。

Mac-tested（mocked PG）。Linux PG 雙 apply 冪等 dry-run + E3 對抗驗 owed。
"""

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import l2_secret_redactor as R
from app import l2_call_ledger_writer as W
from app import l2_memory_recall_context as MRC


# ═══════════════════════════════════════════════════════════════════════════════
# l2_secret_redactor
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedactor:
    def test_api_key_redacted(self):
        r = R.redact("api_key=AKIAIOSFODNN7EXAMPLE1234 trailing")
        assert "AKIAIOSFODNN7EXAMPLE1234" not in r.text
        assert "[REDACTED:api_key]" in r.text
        assert "api_key" in r.kinds_hit

    def test_bearer_redacted(self):
        r = R.redact("Authorization: Bearer abc123XYZ.tok_val")
        assert "abc123XYZ.tok_val" not in r.text
        assert "[REDACTED:bearer]" in r.text

    def test_dsn_credential_redacted_scheme_kept(self):
        # 結構臂遮整段 user:pass credential（user 名亦可識別 → over-redaction，
        # §B.2 寧可多遮），但保留 scheme 結構脈絡（forensic-useful）。
        r = R.redact("postgresql://trading_admin:supersecret@db/trading_ai")
        assert "supersecret" not in r.text
        assert "trading_admin" not in r.text  # 整段 credential 被遮（v2 較 v1 更嚴）
        assert "postgresql://" in r.text       # scheme 脈絡仍在
        assert "@db/trading_ai" in r.text      # host/db 脈絡仍在
        assert "[REDACTED:db_dsn]" in r.text

    def test_hmac_sign_redacted(self):
        r = R.redact("X-BAPI-SIGN=9f8e7d6c5b4a3f2e1d0c header")
        assert "9f8e7d6c5b4a3f2e1d0c" not in r.text
        assert "[REDACTED:bearer]" in r.text

    def test_auth_json_signature_redacted(self):
        r = R.redact('signature="MEUCIQDxyzBASE64BLOB12345" approved')
        assert "MEUCIQDxyzBASE64BLOB12345" not in r.text
        assert "[REDACTED:auth_json]" in r.text

    def test_secret_slot_redacted(self):
        r = R.redact("secret_slot=slotmat6789abc ref")
        assert "slotmat6789abc" not in r.text
        assert "[REDACTED:secret_slot]" in r.text

    def test_private_url_redacted(self):
        r = R.redact("connect to trade-core and 10.0.0.5 and node.local")
        assert "trade-core" not in r.text
        assert "10.0.0.5" not in r.text
        assert r.kinds_hit.count  # 命中 private_url
        assert "[REDACTED:private_url]" in r.text

    def test_benign_prose_not_redacted(self):
        # 負向：正常散文不得被誤遮（防 false-positive 破壞脈絡）。
        text = "BTC funding rate is 0.01% and net edge estimate is 5bps after fees"
        r = R.redact(text)
        assert r.text == text
        assert r.kinds_hit == []

    def test_idempotent(self):
        # 對已消毒文本再跑 = no-op（D.1.1 :361）。
        once = R.redact("api_key=ZZZZZZZZZZZZZZZZ1234 and postgres://u:pw@h/db").text
        twice = R.redact(once).text
        assert once == twice

    def test_version_present(self):
        assert R.redact("x").redactor_version == R.REDACTOR_VERSION
        assert R.REDACTOR_VERSION.startswith("l2_redactor.")

    def test_jsonb_recursive(self):
        obj = {
            "sys": "use api_key=ZZZZZZZZZZZZZZZZ1234",
            "nested": {"dsn": "postgres://u:secretpw@h/db"},
            "arr": [1, "Bearer tok12345678", {"k": "X-BAPI-SIGN=deadbeefcafe1234"}],
        }
        out = R.redact_jsonb(obj)
        flat = str(out)
        assert "secretpw" not in flat
        assert "ZZZZZZZZZZZZZZZZ1234" not in flat
        assert "tok12345678" not in flat
        assert "deadbeefcafe1234" not in flat
        # key 不被遮（schema-controlled）。
        assert "nested" in out and "arr" in out

    def test_none_and_empty(self):
        assert R.redact(None).text == ""
        assert R.redact("").text == ""
        assert R.is_clean(None) is True
        assert R.is_clean("plain text") is True
        assert R.is_clean("api_key=ABCDEFGHIJKLMNOP1234") is False

    def test_redactor_version_is_v4(self):
        # bump 證據：v3→v4（CRITICAL fast-path gate fix + keyword 補全 + size cap）。
        assert R.REDACTOR_VERSION == "l2_redactor.v4"


# ═══════════════════════════════════════════════════════════════════════════════
# l2_secret_redactor — 對抗向量（HIGH）：keyword-gated + 結構臂仍 redacted；
# naked-context-free 高熵向量為「已知殘留」標 xfail-strict（operator 2026-06-08 拍板 A：
# 回 keyword-gated + 結構臂，接受 naked-context-free 殘留——blanket bare 高熵臂越過
# PA LOCKED §B.2 且實測誤遮 29% 合法 forensic 內容，毀 ledger 可重建性 = D3 目的）。
# 殘留最佳解在 P3 source-side（產生端不把裸密鑰寫進 prompt/summary），非 redactor。
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedactorAdversarialE3:
    # ── 結構臂（keyword-free，可分辨低誤遮，符 PA §B.2 結構臂精神，保留）──

    def test_jwt_blob_redacted(self):
        # JWT 有可分辨結構（eyJ….….…），低誤遮 → 結構臂保留。
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N"
        r = R.redact(f"bearer-less token {jwt} here")
        assert jwt not in r.text
        assert "[REDACTED:jwt]" in r.text
        assert "jwt" in r.kinds_hit

    def test_zero_width_in_keyword_redacted(self):
        # 零寬字元插進 keyword 中段規避 keyworded arm → NFKC+strip（僅供偵測）後仍命中；
        # store-original：遮在 original，零寬字元在未遮區仍保留（byte 不破壞）。
        zw = "api​_key=SUPERSECRETVALUE1234"
        r = R.redact(zw)
        assert "SUPERSECRETVALUE1234" not in r.text
        assert "[REDACTED:api_key]" in r.text

    def test_url_encoded_dsn_redacted(self):
        # url-encode DSN 規避 scheme:// pattern → URL-decode-once（僅供偵測）後現形；
        # store-original：cred 區域映回 original 被遮，scheme/host 的 %XX 原樣保留。
        enc = "postgres%3A%2F%2Fuser%3Apw%40host%2Fdb"
        r = R.redact(enc)
        assert "user%3Apw" not in r.text  # cred 區域（user:pw 的 url-encoded）已遮
        assert "[REDACTED:db_dsn]" in r.text

    def test_short_keyworded_under_16_redacted(self):
        # api_key= 值 <16：keyworded 命中即遮不設 16 下限（§B.2.d）。
        r = R.redact("api_key=shortkey12")  # value 10 char < 16
        assert "shortkey12" not in r.text
        assert "[REDACTED:api_key]" in r.text

    # ── 私有 IP（結構臂，可分辨拓撲，保留）──

    def test_private_ip_10_8_redacted(self):
        r = R.redact("bind to 10.0.0.5 internal")
        assert "10.0.0.5" not in r.text
        assert "[REDACTED:private_ip]" in r.text

    def test_private_ip_172_16_redacted(self):
        r = R.redact("connect 172.16.0.9 and 172.31.255.1")
        assert "172.16.0.9" not in r.text
        assert "172.31.255.1" not in r.text
        assert "[REDACTED:private_ip]" in r.text

    def test_private_ip_192_168_and_testnet_redacted(self):
        r = R.redact("host 192.168.5.5 and 192.0.2.44")
        assert "192.168.5.5" not in r.text
        assert "192.0.2.44" not in r.text

    def test_private_ipv6_redacted(self):
        r = R.redact("iface fe80::1ff:fe23:4567:890a and fc00::1")
        assert "fe80::1ff:fe23:4567:890a" not in r.text
        assert "[REDACTED:private_ip]" in r.text

    def test_public_ip_not_redacted(self):
        # 負向：公網 IP 不是私有拓撲，不得誤遮（8.8.8.8）。
        r = R.redact("dns server 8.8.8.8 reachable")
        assert "8.8.8.8" in r.text

    # ── JSON header-echo dict 形（key-name 臂，可分辨 key 名，保留）──

    def test_json_header_echo_dict_redacted(self):
        # header dict 的敏感 key（Authorization / x-bapi-api-key）→ 不論 value
        # 結構一律遮（value 可能無 keyword/結構，唯靠 key 名判定）。
        obj = {
            "Authorization": "sometokenvalue",   # 無 keyword、低熵 → 靠 key 名遮
            "x-bapi-api-key": "KEYMAT1234",
            "nested": {"password": "pw99"},
            "benign": "keep this prose",
        }
        out = R.redact_jsonb(obj)
        flat = str(out)
        assert "sometokenvalue" not in flat
        assert "KEYMAT1234" not in flat
        assert "pw99" not in flat
        # benign 非敏感 key 不被遮。
        assert "keep this prose" in flat

    # ── 已知殘留（operator A）：naked-context-free 高熵串 ───────────────────────
    # bare alnum token / bare 64-hex / bare base64 blob，無 adjacent keyword 且無
    # JWT/DSN/IP 結構。資訊論上無法與合法高熵識別碼（git-SHA / sha256 / config-flag /
    # model-id）區分而不大量誤遮（前一輪 blanket 高熵臂實測誤遮 29% 合法 forensic）。
    # 標 xfail-strict 防 silent regress（若改回會遮，strict 報 XPASS 強制 review）。
    # 具名 critical 資產帶其慣常 keyword/結構時皆被抓（見上）；殘留最佳解在 P3
    # source-side。

    @pytest.mark.xfail(
        reason="已知殘留（operator 2026-06-08 拍板 A）：naked-context-free bare alnum "
        "token，無 keyword/結構，資訊論上無法區分合法高熵識別碼而不大量誤遮；"
        "最佳解在 P3 source-side。",
        strict=True,
    )
    def test_bare_24char_high_entropy_residual(self):
        tok = "aB3xY9kLmN2pQ7rS4tU8vW1z"  # 24 char bare、無 keyword/結構
        assert len(tok) == 24
        r = R.redact(f"key material {tok} end")
        assert "[REDACTED" in r.text  # 預期失敗（殘留，不再被 blanket 高熵臂遮）

    @pytest.mark.xfail(
        reason="已知殘留（operator A）：naked-context-free bare alnum token（35 char）"
        "無 keyword/結構；最佳解在 P3 source-side。",
        strict=True,
    )
    def test_bare_35char_residual(self):
        tok = "AKIAJQ4PXK9ZB7M2WD1RTYU8GHN6FOSLCEV"  # 35 char bare（無 api_key= keyword）
        r = R.redact(tok)
        assert "[REDACTED" in r.text  # 預期失敗（殘留）

    @pytest.mark.xfail(
        reason="已知殘留（operator A）：bare 64-hex（無 keyword/結構）資訊論上不可分於"
        "合法 sha256/git-SHA forensic 識別碼；最佳解在 P3 source-side。",
        strict=True,
    )
    def test_bare_64hex_residual(self):
        import random
        random.seed(2026)
        hexhmac = "".join(random.choice("0123456789abcdef") for _ in range(64))
        r = R.redact(hexhmac)
        assert "[REDACTED" in r.text  # 預期失敗（殘留，不可分於合法 sha256）

    @pytest.mark.xfail(
        reason="已知殘留（operator A）：bare base64 blob（無 keyword/結構）不可分於"
        "合法 base64 config/payload；最佳解在 P3 source-side。",
        strict=True,
    )
    def test_bare_base64_blob_residual(self):
        blob = "TWFueSBoYW5kcyBtYWtlIGxpZ2h0IHdvcmsgYW5kIG1vcmU="  # bare base64
        r = R.redact(blob)
        assert "[REDACTED" in r.text  # 預期失敗（殘留）

    def test_legit_high_entropy_identifier_not_redacted(self):
        # operator A 的正向價值證明：合法高熵 forensic 識別碼（git-SHA / sha256 /
        # config-flag / model-id）不再被誤遮，store-original byte-identical 保留——
        # 這正是回 keyword-gated 的目的（ledger 可重建 = D3 目的本身）。
        src = (
            "commit a59f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f "
            "model claude-opus-4-8-20260115 flag OPENCLAW_RESIDUAL_ALPHA_PRODUCER"
        )
        r = R.redact(src)
        assert r.text == src           # byte-identical，未誤遮
        assert r.kinds_hit == []

    # ── ReDoS：無 catastrophic backtracking（線性） ──

    def test_no_catastrophic_backtracking(self):
        import time
        # 單字元類 200K bait（pattern arm 的 worst case）。
        bait = "A" * 200000 + "!"
        t0 = time.perf_counter()
        R.redact(bait)
        dt = (time.perf_counter() - t0) * 1000
        # 線性 → 應遠低於指數爆炸（給寬鬆上限證非 catastrophic；非嚴格 perf gate）。
        assert dt < 2000, f"possible ReDoS: {dt:.0f}ms on 200K single-class bait"


# ═══════════════════════════════════════════════════════════════════════════════
# l2_secret_redactor — v4 CRITICAL fast-path gate fix（Finding 1，re-E2）：fast-path
# 的 gate-set 必須 == strip-set（_is_control_or_format）by construction。前一版用手列
# codepoint regex 當 gate，漏 ~135 個會被 strip 但 regex 未涵蓋且 NFKC-stable 的 Cf
# 字元（U+180E / U+061C / U+2066-2069 / U+E00xx tag 區等）→ 用這些字元切斷 keyword 的
# secret 走 fast-path 在 raw 文本（不 strip）偵測 → 漏遮逐字入庫洩漏。
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedactorFastPathGateCriticalV4:
    # 前一版 regex 漏的具名 Cf 字元（皆 strip-set 成員、NFKC-stable）。
    _LEAKED_CF = [
        ("U+180E", "᠎"),   # MONGOLIAN VOWEL SEPARATOR
        ("U+061C", "؜"),   # ARABIC LETTER MARK
        ("U+2066", "⁦"),   # LEFT-TO-RIGHT ISOLATE
        ("U+2067", "⁧"),   # RIGHT-TO-LEFT ISOLATE
        ("U+2068", "⁨"),   # FIRST STRONG ISOLATE
        ("U+2069", "⁩"),   # POP DIRECTIONAL ISOLATE
        ("U+E0041", "\U000e0041"),  # TAG LATIN CAPITAL LETTER A（tag 區 Cf）
    ]

    @pytest.mark.parametrize("name,ch", _LEAKED_CF)
    def test_keyword_split_by_leaked_cf_char_fully_redacted(self, name, ch):
        # CRITICAL 回歸：keyword 被前一版 gate 漏的 Cf 字元切斷的 secret → 必完整遮、
        # 原文無 verbatim 殘留（前一版這些走 fast-path 在 raw 偵測 keyword 仍被切斷 →
        # 漏遮逐字入庫）。
        secret = "SUPERSECRETVALUE1234"
        raw = "api" + ch + "_key=" + secret + " trailing context"
        r = R.redact(raw)
        assert secret not in r.text, f"{name}: secret leaked verbatim (gate drift not fixed)"
        assert "[REDACTED:api_key]" in r.text, f"{name}: secret not redacted"

    def test_brute_force_strip_set_all_route_to_slow_path(self):
        # brute-force 斷言（防未來再 drift）：所有 _is_control_or_format 會 strip 的字元
        # （整 Unicode 空間）全部 route 到 slow-path（_needs_offset_map(sample) 為 True）。
        # 若 gate 與 strip 謂詞分離（如改回手列 regex）此測立刻 RED。
        misses = []
        strip_count = 0
        for cp in range(0x110000):
            ch = chr(cp)
            if R._is_control_or_format(ch):
                strip_count += 1
                # 含此 strip-set 字元的文本必須走 slow-path（不論其他條件）。
                if not R._needs_offset_map("x" + ch + "y"):
                    misses.append(hex(cp))
        assert strip_count > 100, "sanity: strip-set 應涵蓋上百個控制/格式字元"
        assert misses == [], (
            f"{len(misses)} strip-set char(s) leak to fast-path (gate-set != strip-set): "
            f"{misses[:20]}"
        )

    def test_zero_secret_with_leaked_cf_byte_identical(self):
        # 良性文本含前一版漏的 Cf 字元、無 secret：走 slow-path、存入 byte-identical
        # （store-original 不變量不被 gate fix 影響）。
        src = "benign⁦text᠎with⁩isolates and no secret"
        r = R.redact(src)
        assert r.text == src
        assert r.text.encode("utf-8") == src.encode("utf-8")
        assert r.kinds_hit == []


# ═══════════════════════════════════════════════════════════════════════════════
# l2_secret_redactor — v4 LOW-1 keyword-set 補全（re-E3）：HMAC / signing / auth 簽章
# 金鑰類 + 裸 secret + private_key，使設計 §B.5「every named critical asset still
# caught」屬實 + 對齊 secret-leak-detection skill Pattern-A。每 keyword 驗 free-text
# kw=value 與 JSONB-key 兩形。
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedactorKeywordCompletenessV4:
    # (keyword, 預期 kind) — kind 由 _KW_DISPATCH 分支決定。
    _NEW_KEYWORDS = [
        ("auth_signing_key", "auth_json"),
        ("hmac_key", "bearer"),
        ("hmac", "bearer"),
        ("signing_key", "auth_json"),
        ("signing_secret", "auth_json"),
        ("auth_key", "auth_json"),
        ("secret", "api_key"),
        ("private_key", "api_key"),
    ]

    @pytest.mark.parametrize("kw,expected_kind", _NEW_KEYWORDS)
    def test_new_keyword_freetext_redacted(self, kw, expected_kind):
        secret = "SECRETMATERIAL1234567"
        r = R.redact(f"config {kw}={secret} trailing")
        assert secret not in r.text, f"{kw}=value not redacted"
        assert "[REDACTED:" in r.text
        assert expected_kind in r.kinds_hit, f"{kw} 應命中 kind={expected_kind}，實 {r.kinds_hit}"

    @pytest.mark.parametrize("kw,_kind", _NEW_KEYWORDS)
    def test_new_keyword_jsonb_key_redacted(self, kw, _kind):
        # JSONB-key 臂：敏感 key 不論 value 結構一律遮 value（_SENSITIVE_KEY_RE 補同步）。
        out = R.redact_jsonb({kw: "barevalue12345"})
        assert "barevalue12345" not in str(out), f"JSONB key {kw!r} value not redacted"
        assert out[kw] == "[REDACTED:api_key]"

    def test_naked_secret_keyword_colon_form(self):
        # 裸 secret 以 ': ' 分隔形（header-style）亦遮（catch-all，§B.5 named asset）。
        r = R.redact("secret: ABCDEFGH12345678")
        assert "ABCDEFGH12345678" not in r.text
        assert "[REDACTED:api_key]" in r.text


# ═══════════════════════════════════════════════════════════════════════════════
# l2_secret_redactor — v4 LOW-2 size cap（re-E3，DoS guard）：偵測前對輸入文本截斷於
# 256KB（高位）+ logged truncation marker。bound store-original per-char 迴圈在
# degenerate 全-evasion 輸入下的 super-linear 成本 + bound 儲存。256KB 遠大於現實 L2
# response，不影響 full-forensic 目標。
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedactorSizeCapV4:
    def test_oversized_input_truncated_with_marker(self):
        big = "A" * (300 * 1024)  # 307200 > 256KB cap
        r = R.redact(big)
        # 輸出 ≈ 256KB + marker（不再是 300KB）。
        assert len(r.text) <= R._MAX_REDACT_INPUT_CHARS + 64
        assert "[TRUNCATED:" in r.text
        # 丟棄字元數正確（300KB - 256KB）。
        dropped = (300 * 1024) - R._MAX_REDACT_INPUT_CHARS
        assert f"[TRUNCATED:{dropped} chars]" in r.text

    def test_under_cap_input_not_truncated(self):
        # 剛好在 cap 下：不截、無 marker（不影響現實響應）。
        src = "B" * (R._MAX_REDACT_INPUT_CHARS - 100)
        r = R.redact(src)
        assert "[TRUNCATED:" not in r.text
        assert r.text == src

    def test_truncation_idempotent(self):
        # 已截斷文本再跑 redact() 為 no-op（不二次截斷 / 不丟 marker / 不換 n）。
        once = R.redact("C" * (400 * 1024)).text
        twice = R.redact(once).text
        assert once == twice

    def test_secret_within_retained_region_still_redacted(self):
        # cap 前段（retained 區）的 secret 仍被遮（cap 不旁路消毒，只 bound 尾端）。
        src = ("x" * 1000) + " api_key=KEEPSECRET123456 " + ("y" * (300 * 1024))
        r = R.redact(src)
        assert "KEEPSECRET123456" not in r.text
        assert "[REDACTED:api_key]" in r.text
        assert "[TRUNCATED:" in r.text

    def test_cap_bounds_worst_case_all_evasion(self):
        # ReDoS bound：degenerate 全-evasion（每 char 強制 slow-path per-char 迴圈）
        # 在 cap 後 worst-case 時間有界（800K/2M 皆 clamp 到 256K）；pre-cap 此為
        # super-linear（~n^1.7，800K 9.4s）。給寬鬆上限證 bound（非嚴格 perf gate）。
        import time
        sh = "­"  # soft-hyphen：control/format → slow-path、NFKC strip 每 char
        for n in (800 * 1024, 2 * 1024 * 1024):
            t0 = time.perf_counter()
            R.redact(sh * n)
            dt = (time.perf_counter() - t0) * 1000
            assert dt < 1000, f"cap failed to bound all-evasion {n}: {dt:.0f}ms"

    def test_marker_not_itself_redacted(self):
        # truncation marker 無 keyword/結構，不被誤遮（forensic 可讀）。
        r = R.redact("D" * (300 * 1024))
        assert "[TRUNCATED:" in r.text
        # marker 區段不含 [REDACTED:（marker 自身未被當 secret）。
        marker_idx = r.text.index("[TRUNCATED:")
        assert "[REDACTED:" not in r.text[marker_idx:]


# ═══════════════════════════════════════════════════════════════════════════════
# l2_secret_redactor — store-original-by-span（§B.5 不變量）：偵測在 normalized
# 文本，但存入 = 原文僅 secret span 被遮。零-secret 輸入存入須 byte-identical
# （NFKC/url-decode/strip 只用於偵測，不得改寫存入文本）。防 ledger 可重建性破壞。
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedactorStoreOriginalBySpan:
    def test_cjk_fullwidth_punct_byte_identical(self):
        # 中文全形標點 ，：（） 經 NFKC 會被偵測層正規化成半形，但存入必須是原文
        # （全形標點 byte-identical）——否則 ledger 文本 != as-sent，毀重建。
        src = "策略分析，net edge：5bps（低波動 regime）測試"
        r = R.redact(src)
        assert r.text == src
        assert r.text.encode("utf-8") == src.encode("utf-8")
        assert r.kinds_hit == []

    def test_legit_url_encoded_percent_byte_identical(self):
        # 合法 %2F / %20（非 secret）：偵測層 url-decode-once 但存入 byte-identical。
        src = "path component a%2Fb and a space%20here are legitimate"
        r = R.redact(src)
        assert r.text == src
        assert r.text.encode("utf-8") == src.encode("utf-8")
        assert r.kinds_hit == []

    def test_zero_width_benign_byte_identical(self):
        # 零寬字元在良性文本（無 secret）：偵測層 strip 但存入保留零寬（byte 不變）。
        src = "be​nign zero‍width text with no secret"
        r = R.redact(src)
        assert r.text == src
        assert r.text.encode("utf-8") == src.encode("utf-8")
        assert r.kinds_hit == []

    def test_secret_span_redacted_rest_byte_identical(self):
        # 混合：一個真 secret + 周邊全形/CJK 無關內容。只 secret span 被遮，
        # 其餘（含 CJK 全形）byte-identical 保留。
        src = "日誌：api_key=KEY1234567890ABCD 然後 中文散文 結束"
        r = R.redact(src)
        assert "KEY1234567890ABCD" not in r.text
        assert "[REDACTED:api_key]" in r.text
        # secret 之外的原文 byte-identical（前綴 + 後綴）。
        assert r.text.startswith("日誌：api_key=")
        assert r.text.endswith(" 然後 中文散文 結束")

    def test_sha256_consistency_on_original_redacted(self):
        # sha256 對「原文-遮-span」一致：redactor.text 是 hash 基底（writer 不變）。
        src = "prompt 中文 api_key=SECRETKEY12345678 end 全形（）"
        red = R.redact(src).text
        # 同輸入二次 redact 同輸出（hash 穩定）。
        assert R.redact(src).text == red
        h = hashlib.sha256(red.encode("utf-8")).hexdigest()
        assert h == hashlib.sha256(R.redact(src).text.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# L2CallLedgerWriter — mock PG conn helper
# ═══════════════════════════════════════════════════════════════════════════════


def _mock_conn_provider():
    """回 (provider_callable, cur, conn)。provider() 回一個 ctx-manager yield conn。"""
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cur
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=conn)
    cm.__exit__ = MagicMock(return_value=False)
    return (lambda: cm), cur, conn


def _insert_params(cur):
    """從 mock cursor 取首次 execute 的 (sql, params)。"""
    assert cur.execute.called, "no INSERT issued"
    sql, params = cur.execute.call_args[0]
    return sql, params


# Bybit-shaped 合成密鑰（測試專用，非真鑰）。
FAKE_API_KEY = "BYBITKEYABCDEFGH12345678"
FAKE_BEARER = "Bearer faketok_ABCDEFG12345"
FAKE_DSN = "postgresql://trading_admin:fakepassw0rd@trade-core:5432/trading_ai"


class TestLedgerWriterSanitizeOnWritePath:
    def test_secrets_redacted_before_insert(self):
        provider, cur, conn = _mock_conn_provider()
        writer = W.L2CallLedgerWriter(conn_provider=provider)
        res = writer.record_l2_call(
            l2_reply_id="l2r:deadbeef0001",
            capability_id="l2.test",
            trigger="manual",
            created_at="2026-06-08T00:00:00Z",
            model="haiku",
            contract_ver="l2_contract.v1",
            schema_ver="l2_schema.v1",
            system_prompt=f"You are an agent. Connect {FAKE_DSN} with api_key={FAKE_API_KEY}.",
            input_context={"messages": [{"role": "user", "content": f"auth {FAKE_BEARER}"}]},
            raw_response=f"I used api_key={FAKE_API_KEY} and {FAKE_DSN}",
        )
        assert res["ok"] is True
        sql, params = _insert_params(cur)
        assert "INSERT INTO agent.l2_calls" in sql
        # 整個 params tuple 不得含任何合成密鑰 verbatim。
        blob = "\x00".join(str(p) for p in params)
        assert "fakepassw0rd" not in blob
        assert FAKE_API_KEY not in blob
        assert "faketok_ABCDEFG12345" not in blob
        # 但 [REDACTED:*] token 必在（forensic 留痕）。
        assert "[REDACTED:db_dsn]" in blob
        assert "[REDACTED:api_key]" in blob

    def test_sha256_over_sanitized_text(self):
        # 關鍵：prompt_sha256 必須 == sha256(已消毒 system_prompt)，不是原文。
        provider, cur, conn = _mock_conn_provider()
        writer = W.L2CallLedgerWriter(conn_provider=provider)
        raw_prompt = f"prompt with api_key={FAKE_API_KEY} secret"
        writer.record_l2_call(
            l2_reply_id="l2r:deadbeef0002",
            capability_id="l2.test",
            trigger="manual",
            created_at="2026-06-08T00:00:00Z",
            model="haiku",
            contract_ver="v1",
            schema_ver="v1",
            system_prompt=raw_prompt,
            input_context={},
            raw_response="ok",
        )
        sql, params = _insert_params(cur)
        # 用列名定位（避免 index 漂移脆弱）。
        cols = [c.strip() for c in sql.split("(", 1)[1].split(")", 1)[0].split(",")]
        idx_prompt = cols.index("system_prompt")
        idx_psha = cols.index("prompt_sha256")
        stored_prompt = params[idx_prompt]
        stored_psha = params[idx_psha]
        sanitized = R.redact(raw_prompt).text
        # 已消毒文本入庫（原密鑰不在）。
        assert FAKE_API_KEY not in stored_prompt
        # sha256 對已消毒文本，非原文。
        assert stored_psha == hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
        assert stored_psha != hashlib.sha256(raw_prompt.encode("utf-8")).hexdigest()

    def test_redactor_version_persisted(self):
        provider, cur, conn = _mock_conn_provider()
        writer = W.L2CallLedgerWriter(conn_provider=provider)
        writer.record_l2_call(
            l2_reply_id="l2r:deadbeef0003",
            capability_id="l2.test", trigger="manual",
            created_at="2026-06-08T00:00:00Z", model="haiku",
            contract_ver="v1", schema_ver="v1",
            system_prompt="p", input_context={}, raw_response="r",
        )
        sql, params = _insert_params(cur)
        cols = [c.strip() for c in sql.split("(", 1)[1].split(")", 1)[0].split(",")]
        assert params[cols.index("redactor_version")] == R.REDACTOR_VERSION

    def test_exception_classified_never_verbatim(self):
        # str(e) 攜帶 DSN → 絕不 verbatim；error_code 為 classified reason_code。
        provider, cur, conn = _mock_conn_provider()
        writer = W.L2CallLedgerWriter(conn_provider=provider)
        exc = RuntimeError(f"connect failed to {FAKE_DSN}")
        writer.record_l2_call(
            l2_reply_id="l2r:deadbeef0004",
            capability_id="l2.test", trigger="manual",
            created_at="2026-06-08T00:00:00Z", model="haiku",
            contract_ver="v1", schema_ver="v1",
            system_prompt="p", input_context={}, raw_response="r",
            error=exc, error_reason_code="db_error",
        )
        sql, params = _insert_params(cur)
        cols = [c.strip() for c in sql.split("(", 1)[1].split(")", 1)[0].split(",")]
        blob = "\x00".join(str(p) for p in params)
        # 原始 exception 文本（含 DSN）不得 verbatim 落庫。
        assert "fakepassw0rd" not in blob
        # error_code 為 classified（db_error），非 str(e)。
        assert params[cols.index("error_code")] == "db_error"

    def test_consequential_at_creation_set_once(self):
        provider, cur, conn = _mock_conn_provider()
        writer = W.L2CallLedgerWriter(conn_provider=provider)
        writer.record_l2_call(
            l2_reply_id="l2r:deadbeef0005",
            capability_id="l2.test", trigger="manual",
            created_at="2026-06-08T00:00:00Z", model="haiku",
            contract_ver="v1", schema_ver="v1",
            system_prompt="p", input_context={}, raw_response="r",
            consequential_at_creation=True,
        )
        sql, params = _insert_params(cur)
        cols = [c.strip() for c in sql.split("(", 1)[1].split(")", 1)[0].split(",")]
        assert params[cols.index("consequential_at_creation")] is True

    def test_insert_only_no_update_delete(self):
        # INSERT-only 不變式：writer 對 ledger 三方法只發 INSERT，零 UPDATE/DELETE。
        provider, cur, conn = _mock_conn_provider()
        writer = W.L2CallLedgerWriter(conn_provider=provider)
        writer.record_l2_call(
            l2_reply_id="l2r:deadbeef0006",
            capability_id="l2.test", trigger="manual",
            created_at="2026-06-08T00:00:00Z", model="haiku",
            contract_ver="v1", schema_ver="v1",
            system_prompt="p", input_context={}, raw_response="r",
        )
        for call in cur.execute.call_args_list:
            sql = call[0][0].upper()
            assert "UPDATE " not in sql
            assert "DELETE " not in sql
            assert "INSERT INTO" in sql

    def test_db_unavailable_fail_soft(self):
        # conn 為 None → ok=False，NEVER raise（不阻斷 session 收尾）。
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=None)
        cm.__exit__ = MagicMock(return_value=False)
        writer = W.L2CallLedgerWriter(conn_provider=lambda: cm)
        res = writer.record_l2_call(
            l2_reply_id="l2r:deadbeef0007",
            capability_id="l2.test", trigger="manual",
            created_at="2026-06-08T00:00:00Z", model="haiku",
            contract_ver="v1", schema_ver="v1",
            system_prompt="p", input_context={}, raw_response="r",
        )
        assert res["ok"] is False
        assert "db_unavailable" in res["errors"]


class TestAgentLessonsRedaction:
    """spec #2：agent.lessons content 在 executemany INSERT 之前過 redactor，
    使 D.1.1「applies everywhere」對 lesson store 也成立。"""

    def test_lesson_content_redacted_before_executemany(self):
        from app import layer2_critic as LC
        from app.layer2_types import Layer2Session

        class _Insight:
            category = "risk"
            title = "leak"
            # LLM 蒸餾文本 drift 進 secret：DSN 密碼 + api_key。
            detail = f"observed {FAKE_DSN} and api_key={FAKE_API_KEY} in trace"

        session = Layer2Session(trigger="manual")
        cur = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value = cur
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=conn)
        cm.__exit__ = MagicMock(return_value=False)

        with patch.object(LC.db_pool, "get_pg_conn", return_value=cm):
            LC._persist_lessons_sync([_Insight()], session, "BTCUSDT")

        assert cur.executemany.called, "no executemany issued"
        sql, rows = cur.executemany.call_args[0]
        assert "INSERT INTO agent.lessons" in sql
        blob = "\x00".join(str(c) for row in rows for c in row)
        # 合成密鑰絕不 verbatim 落 agent.lessons。
        assert "fakepassw0rd" not in blob
        assert FAKE_API_KEY not in blob
        # 但 [REDACTED:*] token 必在（證明確實過了消毒非單純未命中）。
        assert "[REDACTED:" in blob

    def test_benign_lesson_content_unchanged(self):
        # 負向：良性 lesson 文本不被誤遮（保留可讀脈絡）。
        from app import layer2_critic as LC
        from app.layer2_types import Layer2Session

        class _Insight:
            category = "general"
            title = "edge note"
            detail = "grid_short net edge estimate is 5bps after fees in low-vol regime"

        session = Layer2Session(trigger="manual")
        cur = MagicMock()
        conn = MagicMock()
        conn.cursor.return_value = cur
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=conn)
        cm.__exit__ = MagicMock(return_value=False)

        with patch.object(LC.db_pool, "get_pg_conn", return_value=cm):
            LC._persist_lessons_sync([_Insight()], session, "BTCUSDT")

        sql, rows = cur.executemany.call_args[0]
        content_cell = rows[0][2]  # (symbol, category, content, ...)
        assert content_cell == "edge note: grid_short net edge estimate is 5bps after fees in low-vol regime"
        assert "[REDACTED" not in content_cell


class TestCostTrackerSessionRedaction:
    """Finding 3 / 設計 §D.1.1：Layer2CostTracker.record_session 把 session 的 LLM
    自由文本欄（final_summary / recommendation.reasoning / insights）在落 durable
    layer2_cost_state.json 之前過 secret redactor。"""

    def _make_tracker(self, tmp_path):
        from app.layer2_cost_tracker import Layer2CostTracker
        # 用 tmp state file 隔離（不碰真實 runtime/layer2_cost_state.json）。
        return Layer2CostTracker(state_file=str(tmp_path / "cost_state.json"))

    def test_session_freetext_redacted_before_persist(self, tmp_path):
        from app.layer2_types import Layer2Session, Recommendation, Insight

        tracker = self._make_tracker(tmp_path)
        session = Layer2Session(trigger="manual")
        # 注入密鑰到三個自由文本欄。
        session.final_summary = f"summary leaked {FAKE_DSN} and api_key={FAKE_API_KEY}"
        session.recommendation = Recommendation(
            action="hold", symbol="BTCUSDT", confidence=0.5, edge_bps=3.0,
            reasoning=f"because {FAKE_BEARER} was seen and api_key={FAKE_API_KEY}",
        )
        session.insights = [
            Insight(category="risk", title="leak note",
                    detail=f"observed dsn {FAKE_DSN} in trace"),
        ]

        tracker.record_session(session)

        # 讀回 durable state，斷言密鑰絕不 verbatim 落盤。
        sessions = tracker.get_sessions(limit=5)
        assert sessions, "no session persisted"
        blob = json.dumps(sessions, ensure_ascii=False)
        assert "fakepassw0rd" not in blob
        assert FAKE_API_KEY not in blob
        assert "faketok_ABCDEFG12345" not in blob
        # 但 [REDACTED:*] token 必在（證明確實過了消毒，非單純未命中）。
        assert "[REDACTED:" in blob
        # 結構/數值欄不受影響（forensic 盤面保留）。
        s0 = sessions[0]
        assert s0["recommendation"]["symbol"] == "BTCUSDT"
        assert s0["recommendation"]["action"] == "hold"

    def test_benign_session_freetext_unchanged(self, tmp_path):
        # 負向：良性自由文本不被誤遮（保留可讀脈絡）。
        from app.layer2_types import Layer2Session, Recommendation, Insight

        tracker = self._make_tracker(tmp_path)
        session = Layer2Session(trigger="manual")
        session.final_summary = "grid_short net edge 5bps after fees in low-vol regime"
        session.recommendation = Recommendation(
            action="buy", symbol="ETHUSDT", confidence=0.6, edge_bps=4.0,
            reasoning="funding tilt favorable and OI rising",
        )
        session.insights = [
            Insight(category="macro", title="rates", detail="funding rate is 0.01%"),
        ]

        tracker.record_session(session)
        s0 = tracker.get_sessions(limit=1)[0]
        assert s0["final_summary"] == "grid_short net edge 5bps after fees in low-vol regime"
        assert s0["recommendation"]["reasoning"] == "funding tilt favorable and OI rising"
        assert s0["insights"][0]["detail"] == "funding rate is 0.01%"
        assert "[REDACTED" not in json.dumps(s0, ensure_ascii=False)


class TestMarksAndGateSeam:
    def test_consequential_mark_insert_only(self):
        provider, cur, conn = _mock_conn_provider()
        writer = W.L2CallLedgerWriter(conn_provider=provider)
        res = writer.record_consequential_mark(
            l2_reply_id="l2r:abc",
            reason="entered promote lane",
            lane="promote",
            marked_by="applier_x",
            details={"note": f"dsn {FAKE_DSN}"},
        )
        assert res["ok"] is True
        sql, params = _insert_params(cur)
        assert "INSERT INTO agent.l2_consequential_marks" in sql
        assert "UPDATE" not in sql.upper()
        # details 消毒（DSN 密碼不得 verbatim）。
        assert "fakepassw0rd" not in "\x00".join(str(p) for p in params)

    def test_gate_seam_insert_only_and_sanitized(self):
        provider, cur, conn = _mock_conn_provider()
        writer = W.L2CallLedgerWriter(conn_provider=provider)
        res = writer.record_gate_seam(
            l2_reply_id="l2r:abc",
            gate_id="dsr",
            verdict="pass",
            applier="dsr_gate",
            applied_as="proposal only",
            details={"meta": f"api_key={FAKE_API_KEY}"},
        )
        assert res["ok"] is True
        sql, params = _insert_params(cur)
        assert "INSERT INTO learning.l2_gate_seam_log" in sql
        assert "UPDATE" not in sql.upper()
        assert FAKE_API_KEY not in "\x00".join(str(p) for p in params)


# ═══════════════════════════════════════════════════════════════════════════════
# 接線可達性：engine 真呼叫 writer（證明非死碼）
# ═══════════════════════════════════════════════════════════════════════════════


class TestEngineWiring:
    def test_engine_records_first_call_and_binds_reply_id(self):
        from app.layer2_engine import Layer2Engine
        from app.layer2_types import Layer2Session
        from app import provider_client as pc

        engine = Layer2Engine(cost_tracker=MagicMock())
        session = Layer2Session(trigger="manual")
        assert session.l2_reply_id is None

        response = pc.L2Response(text="analysis result", input_tokens=10, output_tokens=5)
        captured = {}

        class _FakeWriter:
            def record_l2_call(self, **kwargs):
                captured.update(kwargs)
                return {"ok": True}

        with patch("app.layer2_engine._get_l2_ledger_writer", return_value=_FakeWriter()):
            engine._record_l2_call_to_ledger(
                session=session,
                system_prompt="SYS",
                messages=[{"role": "user", "content": "hi"}],
                response=response,
                eff_model="haiku",
                latency_ms=None,
            )

        # writer 被真呼叫，且帶上 session 攜帶的 prompt/response/context。
        assert captured["system_prompt"] == "SYS"
        assert captured["raw_response"] == "analysis result"
        assert captured["session_id"] == session.session_id
        assert captured["input_context"]["messages"] == [{"role": "user", "content": "hi"}]
        # ok=True → reply_id 綁到 session（供 persist_lessons 映射 context_id）。
        assert session.l2_reply_id is not None
        assert session.l2_reply_id.startswith("l2r:")
        assert captured["l2_reply_id"] == session.l2_reply_id

    def test_engine_ledger_includes_b3_memory_recall_shadow_metadata(self):
        from app.layer2_engine import Layer2Engine
        from app.layer2_types import Layer2Session
        from app import provider_client as pc

        engine = Layer2Engine(cost_tracker=MagicMock())
        session = Layer2Session(trigger="manual")
        response = pc.L2Response(text="analysis result", input_tokens=10, output_tokens=5)
        captured = {}
        recall = MRC.L2MemoryRecallContext(
            mode="shadow",
            attempted=True,
            record_ids=("mem:r1",),
            total_chars=12,
            degraded_level="fts",
        )

        class _FakeWriter:
            def record_l2_call(self, **kwargs):
                captured.update(kwargs)
                return {"ok": True}

        with patch("app.layer2_engine._get_l2_ledger_writer", return_value=_FakeWriter()):
            engine._record_l2_call_to_ledger(
                session=session,
                system_prompt="SYS",
                messages=[{"role": "user", "content": "hi"}],
                response=response,
                eff_model="haiku",
                latency_ms=None,
                memory_recall=recall,
            )

        assert captured["input_context"]["memory_recall_shadow"] == {
            "mode": "shadow",
            "record_ids": ["mem:r1"],
            "total_chars": 12,
            "degraded_level": "fts",
        }

    def test_engine_wiring_fail_soft_keeps_reply_id_none(self):
        from app.layer2_engine import Layer2Engine
        from app.layer2_types import Layer2Session
        from app import provider_client as pc

        engine = Layer2Engine(cost_tracker=MagicMock())
        session = Layer2Session(trigger="manual")
        response = pc.L2Response(text="r", input_tokens=1, output_tokens=1)

        class _BoomWriter:
            def record_l2_call(self, **kwargs):
                raise RuntimeError("db blew up")

        # writer 爆炸 → 不得 raise（fail-soft），session.l2_reply_id 維持 None。
        with patch("app.layer2_engine._get_l2_ledger_writer", return_value=_BoomWriter()):
            engine._record_l2_call_to_ledger(
                session=session, system_prompt="S", messages=[],
                response=response, eff_model="haiku", latency_ms=None,
            )
        assert session.l2_reply_id is None

    def test_db_unavailable_does_not_bind_reply_id(self):
        # writer 回 ok=False（DB 不可用）→ session.l2_reply_id 不綁（維持 None）。
        from app.layer2_engine import Layer2Engine
        from app.layer2_types import Layer2Session
        from app import provider_client as pc

        engine = Layer2Engine(cost_tracker=MagicMock())
        session = Layer2Session(trigger="manual")
        response = pc.L2Response(text="r", input_tokens=1, output_tokens=1)

        class _SkipWriter:
            def record_l2_call(self, **kwargs):
                return {"ok": False, "errors": ["db_unavailable"]}

        with patch("app.layer2_engine._get_l2_ledger_writer", return_value=_SkipWriter()):
            engine._record_l2_call_to_ledger(
                session=session, system_prompt="S", messages=[],
                response=response, eff_model="haiku", latency_ms=None,
            )
        assert session.l2_reply_id is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
