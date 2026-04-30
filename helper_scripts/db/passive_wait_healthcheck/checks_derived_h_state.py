"""H-state gateway healthcheck [20].
H-state gateway 健康檢查 [20]。

Extracted from ``checks_derived.py`` by T6-FUP-WARN-ZONE-FILES-SPLIT.
由 T6-FUP-WARN-ZONE-FILES-SPLIT 自 ``checks_derived.py`` 抽出。
"""

from __future__ import annotations

import os
from pathlib import Path

def check_h_state_gateway_freshness() -> tuple[str, str]:
    """[20] G3-08 Phase 2 (2026-04-26): H-state gateway env-gate + IPC route + stub schema sentinel.

    MODULE_NOTE (EN): G3-08 completion-criteria sentinel. The H-state gateway
    is the Python → Rust observability bridge (mirror of G3-03
    ExecutorConfigCache pattern but flipped flow: Python = SSOT, Python
    pushes ``invalidate_h_state`` hints, Rust ``h_state_cache`` poller pulls
    full snapshot via ``query_h_state_full`` reverse IPC).

    History / 沿革：
      * Phase 1C (initial PA design plan §10.1) — plumbing-only: H1-H5 /
        5-Agent producers stay silent; expected ``version=0`` +
        ``h_states={}`` (canonical Phase 1 stub).
      * Phase 2 (commits ``9120948`` + ``f2ed286``, 2026-04-26) wired H1
        ThoughtGate + H3 ModelRouter producers; ``query_h_state_full``
        now returns ``version=1`` + ``h_states_keys=2`` (h1, h3).
        This sentinel was bumped by ``G3-08-PHASE-1C-FUP-CHECK20-SYNC``
        (Tier 6 Track 1) so PASS expectations track current Phase 2 wiring;
        a regression to Phase 1 shape (version=0, empty h_states) now
        surfaces as WARN/FAIL.

    Two-phase verdict (per PA §10.1 + Phase 2 update):

      A. **DEFAULT-OFF path (``OPENCLAW_H_STATE_GATEWAY != "1"``)**:
         PASS-skip with explicit dormant note. This is the canonical
         resting state — the gateway should NOT be enabled in production
         until Phase 4 lands the 5-Agent producers. PASS-skip is correct
         (silent-fail guard would alarm if env crept back to "1" before all
         producers are wired, but env=0 dormancy is by design).

      B. **DEFAULT-ON path (``OPENCLAW_H_STATE_GATEWAY == "1"``)**:
         Verify three invariants without making a live IPC roundtrip
         (which would couple this script to the auth secret + main process
         being up — too brittle for a 6h cron):
           1. Reverse IPC route ``query_h_state_full`` is registered in
              ``ai_service_dispatch.py`` (grep-based detection, byte-stable).
           2. ``h_state_invalidator.py`` and ``h_state_query_handler.py``
              modules import successfully (plumbing intact).
           3. ``build_h_state_full_response()`` returns the **Phase 2** stub
              shape: ``version=1`` + ``h_states`` contains both ``h1`` +
              ``h3`` keys (H1 ThoughtGate + H3 ModelRouter wired). Phase 3-4
              progressive deploy may add ``h2/h4/h5`` + ``agent_states`` —
              additive growth = PASS, regression to Phase 1 shape = WARN.
         Three-state output:
           - PASS: all 3 invariants hold (env=1 + route + modules + Phase 2
             stub with at least h1+h3 buckets).
           - WARN: invariant 3 fails (stub returned Phase 1 shape, missing
             expected h1/h3 buckets, or schema drift in unexpected direction).
           - FAIL: invariants 1 or 2 fail (route deregistered or modules
             unimportable — gateway is actually broken).

    Pure-function check: no live IPC, no DB cursor, no socket. We grep the
    dispatch source on disk and import the two Python modules. This matches
    the [16] strategist_cycle_fresh log-tail-parse philosophy: keep the
    healthcheck self-contained so cron/CI can run it without HMAC secrets.

    Cross-platform: pure ``Path.read_text()`` + ``importlib.import_module()``;
    no Linux-only API. Works identically on Mac dev and Linux prod.

    [20] G3-08 Phase 2（2026-04-26）：H 狀態橋接器 env-gate + IPC route +
    Phase 2 stub schema 哨兵。
    G3-08 完成標準哨兵。H 狀態橋接器是 Python → Rust 可觀察性橋
    （鏡射 G3-03 ExecutorConfigCache pattern，但資料流相反：Python=SSOT，
    Python 推 ``invalidate_h_state`` 提示，Rust ``h_state_cache`` poller
    透過 ``query_h_state_full`` reverse IPC 拉完整 snapshot）。

    沿革：
      * Phase 1C（PA design plan §10.1 初版）—— 純線路：H1-H5 / 5-Agent
        producer 靜默；expected ``version=0`` + ``h_states={}``。
      * Phase 2（commits ``9120948`` + ``f2ed286``，2026-04-26）接 H1
        ThoughtGate + H3 ModelRouter producer；``query_h_state_full`` 現
        回傳 ``version=1`` + ``h_states_keys=2``（h1, h3）。本 sentinel
        由 ``G3-08-PHASE-1C-FUP-CHECK20-SYNC``（Tier 6 Track 1）升級
        以對齊 Phase 2 實際線路；regression 回 Phase 1 shape（version=0、
        h_states 空）現會出 WARN/FAIL。

    兩段判決（PA §10.1 + Phase 2 update）：
      A. DEFAULT-OFF（``OPENCLAW_H_STATE_GATEWAY != "1"``）：PASS-skip 帶
         dormant 說明 —— 標準靜止狀態，正式環境 Phase 4 接完 5-Agent
         producer 之前 NOT 啟用。
      B. DEFAULT-ON（``OPENCLAW_H_STATE_GATEWAY == "1"``）：驗 3 個不變量
         （不做 live IPC roundtrip 避免 6h cron 與 auth secret/主程序耦合）：
           1. ``ai_service_dispatch.py`` 中 ``query_h_state_full`` route 已註冊
              （grep 偵測，byte-stable）
           2. ``h_state_invalidator.py`` 與 ``h_state_query_handler.py`` 模組
              可匯入（線路完好）
           3. ``build_h_state_full_response()`` 回傳 **Phase 2** stub shape：
              ``version=1`` + ``h_states`` 含 ``h1`` 與 ``h3`` 兩 key
              （H1 ThoughtGate + H3 ModelRouter 已接）。Phase 3-4 漸進部署
              可能加 ``h2/h4/h5`` + ``agent_states``，這類 additive 成長 = PASS；
              regression 回 Phase 1 shape = WARN。
         三態：3 個全 hold = PASS；invariant 3 fail = WARN；invariant 1 或 2
         fail = FAIL。

    純函式 check：無 live IPC、無 DB cursor、無 socket。grep 磁碟上的
    dispatch source + import 兩個 Python 模組。對齊 [16] strategist_cycle_fresh
    的 log-tail-parse 哲學 —— 讓 healthcheck 自足，cron/CI 不需 HMAC 即可跑。

    跨平台：純 ``Path.read_text()`` + ``importlib.import_module()``；
    無 Linux-only API。Mac dev 與 Linux prod 行為一致。
    """
    # Path A: env-gate disabled → PASS-skip (env=0 dormant by design).
    # 路徑 A：env 關閉 → PASS-skip（env=0 dormant by design）。
    env_val = os.environ.get("OPENCLAW_H_STATE_GATEWAY")
    if env_val != "1":
        env_repr = f"={env_val!r}" if env_val is not None else "=unset"
        return (
            "PASS",
            f"OPENCLAW_H_STATE_GATEWAY{env_repr} (≠'1') — env=0 dormant "
            "by design (per PA §10.1 completion criteria); skip",
        )

    # Path B: env-gate enabled → verify 3 invariants (Phase 2 expectations).
    # 路徑 B：env 開啟 → 驗 3 個不變量（Phase 2 預期）。

    # Invariant 1: ``query_h_state_full`` route registered in dispatch source.
    # We grep the source file rather than importing AIService to avoid
    # spawning the heavy control-api boot path inside a 6h cron.
    # 不變量 1：``query_h_state_full`` route 在 dispatch source 中已註冊。
    # grep 源檔而非 import AIService，避免 6h cron 觸發重型 control-api 啟動。
    base = os.environ.get("OPENCLAW_BASE_DIR") or os.environ.get(
        "OPENCLAW_SRV_ROOT"
    )
    if not base:
        # Production Linux fallback (mirrors check_observer_pipeline_alive).
        # 生產 Linux fallback（對齊 check_observer_pipeline_alive）。
        base = str(Path.home() / "BybitOpenClaw" / "srv")
    dispatch_path = (
        Path(base)
        / "program_code"
        / "exchange_connectors"
        / "bybit_connector"
        / "control_api_v1"
        / "app"
        / "ai_service_dispatch.py"
    )

    if not dispatch_path.exists():
        return (
            "FAIL",
            f"ai_service_dispatch.py missing at {dispatch_path} — "
            "Sub-task B did not deploy; gateway broken",
        )

    try:
        dispatch_src = dispatch_path.read_text(encoding="utf-8")
    except OSError as e:
        # Filesystem race or permission glitch — WARN to avoid masking the
        # real signal with a healthcheck-side IO error (mirrors [Xa]/[18]
        # fail-soft pattern).
        # 檔案系統競態或權限故障 —— WARN 避免 healthcheck-side IO 錯誤
        # 遮蔽真實信號（對齊 [Xa]/[18] fail-soft pattern）。
        return ("WARN", f"dispatch source read failed: {e}")

    if '"query_h_state_full"' not in dispatch_src:
        return (
            "FAIL",
            f"reverse IPC route 'query_h_state_full' missing from "
            f"{dispatch_path.name} — Sub-task B regressed?",
        )

    # Invariant 2: Python plumbing modules importable.
    # 不變量 2：Python 線路模組可匯入。
    import importlib

    h_modules = (
        "program_code.exchange_connectors.bybit_connector."
        "control_api_v1.app.h_state_invalidator",
        "program_code.exchange_connectors.bybit_connector."
        "control_api_v1.app.h_state_query_handler",
    )
    for mod_name in h_modules:
        try:
            importlib.import_module(mod_name)
        except ImportError as e:
            return (
                "FAIL",
                f"module import failed: {mod_name.rsplit('.', 1)[-1]}: {e}",
            )
        except Exception as e:  # noqa: BLE001 — surface unexpected raises
            # Non-ImportError raises during module import are unusual but
            # could indicate a circular import or syntax regression. Treat
            # as FAIL because Phase 1 plumbing must remain importable.
            # 非 ImportError 罕見 —— 可能循環匯入或語法 regression。
            # FAIL 因為 Phase 1 線路必須可匯入。
            return (
                "FAIL",
                f"module init failed: {mod_name.rsplit('.', 1)[-1]}: {e}",
            )

    # Invariant 3: Phase 1 stub returns canonical empty shape.
    # 不變量 3：Phase 1 stub 回傳標準空殼。
    try:
        from program_code.exchange_connectors.bybit_connector.control_api_v1.app.h_state_query_handler import (  # noqa: E501
            build_h_state_full_response,
        )

        resp = build_h_state_full_response()
    except Exception as e:  # noqa: BLE001 — surface schema regression
        return ("WARN", f"build_h_state_full_response() raised: {e}")

    # Phase 2 invariant: version=1 + h_states contains at least {h1, h3}
    # (H1 ThoughtGate + H3 ModelRouter wired by commits 9120948 + f2ed286,
    # 2026-04-26). Phase 3-4 progressive deploy may add h2/h4/h5 + agent_states
    # (additive growth = PASS). Regression to Phase 1 shape (version=0,
    # empty h_states) = WARN — surfaces a real backwards drift.
    # Phase 2 不變量：version=1 + h_states 至少含 {h1, h3}（H1 ThoughtGate +
    # H3 ModelRouter 已接，commits 9120948 + f2ed286，2026-04-26）。Phase 3-4
    # 漸進部署可能加 h2/h4/h5 + agent_states（additive 成長 = PASS）。
    # Regression 回 Phase 1 shape（version=0、h_states 空）= WARN 反映真實
    # 倒退漂移。
    if not isinstance(resp, dict):
        return ("WARN", f"stub returned non-dict: {type(resp).__name__}")
    version = resp.get("version")
    h_states = resp.get("h_states")
    agent_states = resp.get("agent_states")

    if not isinstance(h_states, dict) or not isinstance(agent_states, dict):
        return (
            "WARN",
            f"stub schema drift: h_states={type(h_states).__name__}, "
            f"agent_states={type(agent_states).__name__} (expected dict)",
        )

    # Phase 2 expectations: version == 1 and h_states ⊇ {h1, h3}.
    # Phase 2 預期：version == 1 且 h_states ⊇ {h1, h3}。
    expected_h_state_keys = {"h1", "h3"}
    actual_h_state_keys = set(h_states.keys())
    missing_h_state_keys = expected_h_state_keys - actual_h_state_keys

    if version != 1 or missing_h_state_keys:
        # Either version regressed to Phase 1 (version=0) or one of the
        # H1/H3 producers stopped emitting. WARN so operator notices and
        # can investigate the backwards drift before Wave 4 / Phase 3 lands.
        # version 倒退回 Phase 1（version=0）或 H1/H3 producer 之一停 emit。
        # WARN 提示 operator 注意，在 Wave 4 / Phase 3 落地前查 backwards drift。
        return (
            "WARN",
            f"stub regressed from Phase 2 shape (version={version}, "
            f"h_states_keys={sorted(actual_h_state_keys)}, expected ⊇ "
            f"{{'h1','h3'}}, missing={sorted(missing_h_state_keys)}, "
            f"agent_states_keys={len(agent_states)}) "
            "— H1/H3 producer regression? check Phase 2 wiring "
            "(commits 9120948 + f2ed286)",
        )

    extra_h_state_keys = actual_h_state_keys - expected_h_state_keys
    extra_note = (
        f", +Phase 3-4 keys={sorted(extra_h_state_keys)}"
        if extra_h_state_keys
        else ""
    )
    agent_note = (
        f", +Phase 4 agent_states_keys={len(agent_states)}"
        if agent_states
        else ""
    )
    return (
        "PASS",
        f"env=1 + route registered + modules importable + stub Phase 2 shape "
        f"(version=1, h_states⊇{{'h1','h3'}}{extra_note}{agent_note})",
    )
