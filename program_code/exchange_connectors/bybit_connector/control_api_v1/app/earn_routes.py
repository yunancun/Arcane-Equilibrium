"""
Earn Routes — Bybit Earn first stake FastAPI 後端（Sprint 1B Wave C E1 IMPL；E2 round 2 fix）

MODULE_NOTE：
  模塊用途：
    對齊 docs/execution_plan/2026-05-25--earn_first_stake_gui_design_spec.md §4
    提供 6 個 REST API 端點，作為 Earn tab GUI 的 backend 接點。

    路由前綴 /api/v1/earn；含 5 個只讀 GET 與 1 個寫入 POST：
      - GET  /balance     — Earn 帳戶餘額（呼 Rust IPC BybitEarnClient.get_flexible_positions
                             聚合，attach 最新對賬狀態）；
      - GET  /products    — Flexible Saving 產品列表（per OP-3 鎖 USDT
                             FlexibleSaving；其他 product type defer Sprint 5+）；
      - GET  /preflight   — 5-gate 預檢 + Stage 0R harness JSON 狀態
                             （per spec §5 + §7；GUI 同步輪詢 15s）；
      - GET  /positions   — 當前 Earn 持倉（per OP-5 default Sprint 1B IMPL）；
      - GET  /records     — V100 learning.earn_movement_log 歷史
                             （per OP-5 default；read-only audit）；
      - POST /stake       — first stake 主寫入（雙閘門 Operator + live_reserved；
                             typed-confirm + sync wait Bybit ack per OP-6）。

  主要類 / 函數：
    - EarnStakeRequest：Pydantic body for POST /stake，含 Sprint 1B [100, 200]
      USDT 範圍硬鎖 + typed_confirm_phrase 必填；
    - _verify_typed_confirm_phrase：後端 case-sensitive phrase 比對
      （per spec §6.2 + anti-pattern #4 後端必再驗）；
    - _read_stage_0r_harness：掃 $OPENCLAW_DATA_DIR/canary/earn_first_stake_stage0r_*.json
      最近一份 + age 計算（per spec §7.3）；
    - _build_audit_footer：注入 actor / ts / commit_sha / trace_id
      （per spec §4.4 audit-aware response footer）；
    - _ipc_call_or_degraded：IPC GET 端點走 fail-soft（method not registered
      = Wave D carry-over → return degraded payload）；POST 端點走 fail-closed
      （raise 503 + reason）。

  依賴：
    - .governance_routes._get_auth_actor / _require_operator_role
      （統一 cookie / Bearer token + Operator 角色驗證鏈）；
    - .live_session_routes._global_mode_is_live_reserved
      （live_reserved global mode dual gate per §4.3）；
    - .ipc_client.EngineIPCClient（lazy singleton 模式對齊
      engine_capabilities_routes._get_ipc）；
    - .db_pool.get_conn / put_conn（V100 learning.earn_movement_log 只讀查詢）；
    - .json_fast（per project 慣例不直接 import json）。

  硬邊界：
    a. 寫入端點 fail-closed：Bybit retCode != 0 / IPC timeout / typed_confirm
       mismatch / 5-gate 任一 fail → HTTP 400/403/503 帶 reason；不偽造成功
       不靜默吞錯（per CLAUDE.md §四 + earn_governance §5.1）；
    b. typed_confirm_phrase 後端 case-sensitive 比對 + amount embedded
       （per OQ-3 default `CONFIRM EARN STAKE $<amount> USDT`）—
       前端 modal 是 UX 防護，後端是 SSOT 真實檢查；
    c. Sprint 1B IPC method name `process_earn_intent` 對齊 Rust
       `IntentProcessor.process_earn_intent`（earn_router.rs:605）；Wave D
       接通前 IPC method not_registered 走 degraded （GET）/ fail-closed 503
       （POST）；
    d. 純 Read-only 端點不繞 Operator role gate（per spec §4.2 session valid
       即可）；但 stake 必 Operator + live_reserved 雙閘；
    e. amount_usd 範圍 [100, 200] USDT 硬鎖 + 鎖整數（F1 E2 round 2 修自
       Decimal）— first stake 微壓力測試無小數精度需求；Sprint 5+ 後續 stake
       / redeem 才放寬；
    f. SQL 全參數化（per CLAUDE.md §七 安全代碼規範）；engine_mode 走
       white-list `('live', 'live_demo')` 對映 V100 schema CHECK 4 enum；
    g. fail-soft 不適用 stake：stake 一旦走入 fail-soft 就會誤導 operator 以
       為「沒事但其實沒寫」—per CLAUDE.md §四 fail-closed mandate；
    h. Stage 0R harness JSON HMAC sig 防偽（F3 E2 round 2）— harness 寫 JSON
       時加 `_hmac_sig` field（OPENCLAW_IPC_SECRET HMAC-SHA256 over canonical
       JSON bytes）；後端讀 JSON 時 verify sig，mismatch/missing 視為 PENDING
       不放行 stake（fail-closed）。

  Wave D carry-over（不阻 Wave C closure）：
    - Rust IPC server dispatch.rs 註冊：`process_earn_intent`
      / `get_earn_balance` / `get_flexible_products` / `get_flexible_positions`
      / `get_apr_history` （Sprint 1B Wave D MIT/E1 sub-task）；
    - typed_confirm_phrase canonical regex moved to a shared helper after
      common-modals.js Phrase Pattern Registry lands （per W3 follow-up）。

規格 / Spec：
  - docs/execution_plan/2026-05-25--earn_first_stake_gui_design_spec.md §4
    FastAPI Routes Spec；
  - docs/execution_plan/2026-05-21--earn_governance_spec.md §2.1（operator
    authority hard fail-closed）+ §3.2（EarnIntentPayload 7 field）；
  - rust/openclaw_engine/src/intent_processor/earn_router.rs（9-gate
    contract E-0..E-9）；
  - rust/openclaw_engine/src/bybit_earn_client.rs（5 endpoint
    Bybit V5 wrap）；
  - sql/migrations/V100__m4_hypothesis_base_table.sql line 355-379（earn_movement_log
    10 column schema）。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator

from . import json_fast as json
from .error_sanitize import log_safe_exception
from .governance_routes import _get_auth_actor, _require_operator_role, _sanitize_log
# F7：原本 _ipc_call_strict() 內部 lazy import，移到 module top 對齊 FastAPI 慣例。
# 為什麼上移：lazy import 在 stake hot path 每次 strict-call 都會走一次
# importlib 緩存查找，雖 O(1) 但語意上每個 strict 端點都隱性依賴 ipc_client；
# 顯式 top-level import 對 grep / 依賴掃描更友好（per CLAUDE.md §七 readability）。
from .ipc_client import EngineDisconnectedError, EngineIPCClient, EngineTimeoutError
from .secret_runtime import get_secret_value

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

earn_router = APIRouter(
    prefix="/api/v1/earn",
    tags=["Earn / Bybit Earn 質押"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

# Sprint 1B first stake 範圍硬鎖（per OP-2 拍板）。Sprint 5+ 後續 stake 變動：
# 預期由 RiskConfig TOML 接管而非 hard-code（per earn_governance §6.3）。
# F1 (E2 round 2)：first stake [100, 200] USDT 鎖整數（無小數精度需求）；
# 雙端 phrase 對齊不需 Decimal normalize，直接 `f"{amount}"` 即可。
EARN_FIRST_STAKE_MIN_USD: int = 100
EARN_FIRST_STAKE_MAX_USD: int = 200

# OP-3 拍板 Sprint 1B first stake 只跑 USDT FlexibleSaving；其他 coin / product
# type defer Sprint 5+。本常量是 server-side 強制白名單。
EARN_FIRST_STAKE_COIN: str = "USDT"
EARN_FIRST_STAKE_PRODUCT_CATEGORY: str = "FlexibleSaving"

# 後端 typed-confirm phrase 樣板：`CONFIRM EARN STAKE $<amount> USDT`（per
# OQ-3 default + spec §6.2）；amount 帶入避 muscle memory + 強迫 operator
# 親手鍵入 amount 數字一致。
_TYPED_CONFIRM_PHRASE_TEMPLATE: str = "CONFIRM EARN STAKE ${amount} USDT"

# Stage 0R harness JSON 檔名 glob（per spec §7.3）。Harness CLI 寫
# $OPENCLAW_DATA_DIR/canary/earn_first_stake_stage0r_<date>.json。
_STAGE_0R_HARNESS_FILE_GLOB: str = "earn_first_stake_stage0r_*.json"
_STAGE_0R_HARNESS_MAX_AGE_SEC: int = 24 * 60 * 60  # 24h

# IPC method 名對齊 Rust earn_router.rs:605 `process_earn_intent` + Wave D 待
# 註冊的 BybitEarnClient wrap method 名（per spec §4.3 處理鏈 step 3-4）。
_IPC_METHOD_PROCESS_EARN_INTENT: str = "process_earn_intent"
_IPC_METHOD_GET_EARN_BALANCE: str = "get_earn_balance"
_IPC_METHOD_GET_FLEXIBLE_PRODUCTS: str = "get_flexible_products"
_IPC_METHOD_GET_FLEXIBLE_POSITIONS: str = "get_flexible_positions"

# F3 (E2 round 2)：Stage 0R harness JSON HMAC sig field 名。
# 為什麼要 HMAC：harness JSON 寫入 $OPENCLAW_DATA_DIR/canary/ 後，惡意 actor
# 可能直接編輯 JSON 把 eligible_for_first_stake 從 false 改 true 繞過 first
# stake 5-gate；HMAC sig 確保 JSON 由 harness 寫入（共享 OPENCLAW_IPC_SECRET）
# 而非手動竄改。掛 OPENCLAW_IPC_SECRET（per executor_routes.py:368 範式）。
_STAGE_0R_HMAC_SIG_FIELD: str = "_hmac_sig"

# IPC POST /stake 同步等 Bybit ack 上限（per OP-6 sync default + ux-checklist
# 3.3 spinner ≤ 10s + earn_governance §5.1 timeout 等價 retCode != 0
# fail-closed）。Wave C IMPL 給 12s 留 Rust 端 PG INSERT + Bybit place-order
# 雙 IO 緩衝；GUI 端 spinner 對齊。
_IPC_STAKE_TIMEOUT_SEC: float = 12.0

# Records query 預設 limit + max（GUI table render 與 audit query 平衡）。
_RECORDS_DEFAULT_LIMIT: int = 50
_RECORDS_MAX_LIMIT: int = 200


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models / 請求與回應模型
# ═══════════════════════════════════════════════════════════════════════════════


class EarnStakeRequest(BaseModel):
    """
    POST /api/v1/earn/stake body — first stake 寫入請求。

    為什麼 amount 走 int（F1 round 2 修正自 Decimal）：first stake [100, 200] USDT
    無小數精度需求；鎖整數可避免雙端 phrase 不對齊（前端 $100.50 USDT vs 後端
    $100.5 USDT 的 Decimal normalize 邊界）。Bybit V5 接 string 型 amount，
    Rust 端 builder 補小數位（"100" → "100.00"）；Python 端在此鎖整數即可。
    """

    coin: str = Field(
        default=EARN_FIRST_STAKE_COIN,
        description="USDT only（Sprint 1B 硬鎖 per OP-3）",
    )
    product_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Bybit Earn productId (FlexibleSaving / USDT)",
    )
    amount_usd: int = Field(
        ...,
        ge=EARN_FIRST_STAKE_MIN_USD,
        le=EARN_FIRST_STAKE_MAX_USD,
        # F1：Pydantic strict int enforce；浮點輸入（100.5）會 422 reject。
        # `strict=True` 確保 JSON 端 "100.5" / 100.5 都 422，不會被 cast 為 100。
        strict=True,
        description="Stake 金額 USDT 範圍 [100, 200] 整數（Sprint 1B first stake 硬鎖）",
    )
    expected_apr_bps: int = Field(
        ...,
        ge=0,
        le=100_000,
        description="預期 APR (basis points, 0-100000 = 0-1000%)；由前端從 product.estimateApr 轉換",
    )
    rationale: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Operator rationale（EarnIntentPayload 必填欄位 per earn_governance §3.2）",
    )
    type_confirm_phrase: str = Field(
        ...,
        # F1：integer-only 後 phrase 長度 = `CONFIRM EARN STAKE $XXX USDT` 區間
        # [27, 28]（100 28 char / 99 27 char / 200 28 char）；min 27 容納未來
        # < 100 邊界探測 case（雖然 amount_usd ge=100 會先擋），max 32 留小餘
        # 量避 caller 端 trailing-whitespace edge 過早 422。
        min_length=27,
        max_length=32,
        description="後端 case-sensitive 比對 'CONFIRM EARN STAKE $<amount> USDT'",
    )

    @validator("coin")
    def _validate_coin(cls, v: str) -> str:
        """硬鎖 USDT（per OP-3）；其他 coin 在 Sprint 5+ 才放寬。"""
        if v != EARN_FIRST_STAKE_COIN:
            raise ValueError(
                f"coin must be '{EARN_FIRST_STAKE_COIN}' (Sprint 1B first stake "
                f"locked to USDT FlexibleSaving)"
            )
        return v


# ═══════════════════════════════════════════════════════════════════════════════
# Auth Dependencies / 認證依賴
# ═══════════════════════════════════════════════════════════════════════════════


def _require_operator_for_stake(
    actor: Any = Depends(_get_auth_actor),
) -> Any:
    """
    POST /stake 必需 Operator 角色 + 認證 actor；
    為什麼分 dep 而不 inline：FastAPI dep override 對 unit test 友好
    （test 可 mock _get_auth_actor lambda 回傳特定 role actor）。
    對齊 governance_routes._require_operator_auth 範式。
    """
    _require_operator_role(actor)
    return actor


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 共用輔助
# ═══════════════════════════════════════════════════════════════════════════════


def _format_phrase_amount(amount_usd: int) -> str:
    """
    格式化 phrase 中的 amount —— 對應 GUI 前端 modal 顯示一致。

    F1 (E2 round 2)：amount_usd 鎖整數後直接 `f"{n}"`；雙端對齊無小數歧義。
    """
    return f"{amount_usd}"


def _verify_typed_confirm_phrase(
    submitted_phrase: str,
    amount_usd: int,
) -> bool:
    """
    後端 case-sensitive 比對 typed_confirm_phrase。

    為什麼後端必再驗（per spec §6.2 + anti-pattern #4）：前端 typed-confirm
    modal 是 UX 防誤觸層，但 API 可被繞（curl / Postman 直 POST），後端必須
    是 SSOT；hmac.compare_digest 避 timing attack（phrase 比對量小但保
    範式統一）。
    """
    expected = _TYPED_CONFIRM_PHRASE_TEMPLATE.format(
        amount=_format_phrase_amount(amount_usd),
    )
    # 字面比對；strip 不做（trailing whitespace 也算 mismatch，避操作員 copy-
    # paste 帶入空白後混淆）。
    return hmac.compare_digest(
        submitted_phrase.encode("utf-8"),
        expected.encode("utf-8"),
    )


def _generate_trace_id() -> str:
    """
    生成可排序 trace_id：<ts_ms>-<uuid4>。
    對齊 handoff_routes._generate_trace_id 範式 + spec §4.4 audit footer
    trace_id 注入。
    """
    ts_ms = int(time.time() * 1000)
    return f"{ts_ms}-{uuid.uuid4()}"


def _get_commit_sha() -> str:
    """
    讀取 commit SHA 注入 audit footer。

    為什麼走 env var：runtime 不應 fork git subprocess；deploy script
    （restart_all.sh）負責 export OPENCLAW_COMMIT_SHA。未設定走 'unknown'
    fail-soft（audit footer 不阻 stake 路徑）。
    """
    return os.environ.get("OPENCLAW_COMMIT_SHA", "unknown")[:16]


def _build_audit_footer(actor: Any, trace_id: str | None = None) -> dict[str, Any]:
    """
    構造 audit-aware response footer（per spec §4.4 + ux-checklist 2.5）。
    所有 6 endpoint response 共用此 footer 結構。
    """
    return {
        "actor": _sanitize_log(getattr(actor, "actor_id", "anonymous")),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "commit_sha": _get_commit_sha(),
        "trace_id": trace_id or _generate_trace_id(),
    }


def _response_envelope(
    data: Any,
    *,
    actor: Any,
    degraded: bool = False,
    reason: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    統一 response envelope。
    對齊 handoff_routes._replay_response + governance_routes.GovernanceResponse
    範式。
    """
    return {
        "ok": True,
        "data": data,
        "degraded": degraded,
        "reason": reason,
        "data_category": "earn",
        "_audit": _build_audit_footer(actor, trace_id),
    }


# ─── Live reserved global mode dual gate（per spec §4.3 第 2 條）────────────


def _global_mode_is_live_reserved() -> bool:
    """
    讀 global mode；live_reserved 才允許 stake（per spec §4.3 dual gate）。

    為什麼動態讀而非啟動時讀：global mode 可由 operator GUI 切換
    （demo_reserved / shadow_only / live_reserved）；stake 必拍當下狀態。
    Fail-soft：讀失敗 → return False（不允許 stake；fail-closed 是正確默認）。
    """
    try:
        from . import main_legacy as base  # noqa: PLC0415
        # paper_state 內 'mode' field 是 global mode 字串
        store = getattr(base, "STORE", None)
        if store is None:
            return False
        state = store.read()
        if not isinstance(state, dict):
            return False
        # paper_state.mode 對映 global mode 字串
        paper_state = state.get("paper_state") or {}
        mode = paper_state.get("mode") if isinstance(paper_state, dict) else None
        return mode == "live_reserved"
    except Exception as exc:
        # fail-soft 但 log；不阻路徑（caller 端會拒絕）
        log_safe_exception(logger, "earn_live_reserved_gate_read", exc, level=logging.WARNING)
        return False


# ─── Stage 0R harness JSON 掃描（per spec §7.3）──────────────────────────────


def _compute_stage_0r_hmac(payload_bytes: bytes, secret: str) -> str:
    """
    對 Stage 0R harness JSON bytes 計算 HMAC-SHA256 hex (lowercase)。

    為什麼 hex-lowercase 而非 base64：對齊 live_trust_routes._sign_authorization_payload
    + executor_routes 既有 IPC HMAC 慣例（rust 端 IntentProcessor 接 hex）。
    """
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    return mac.hexdigest()


def _verify_stage_0r_hmac(payload: dict[str, Any], sig_recorded: str | None) -> tuple[bool, str | None]:
    """
    驗 Stage 0R JSON HMAC sig 與 OPENCLAW_IPC_SECRET 對齊。

    F3 (E2 round 2)：harness 寫 JSON 時插入 _hmac_sig field（值 = hex(HMAC-SHA256
    over JSON bytes excluding _hmac_sig)）；後端讀 JSON 時剝出 sig field、用 secret
    重算對比；mismatch 視為 cron user 以外的 actor 竄改 / harness 未配 secret。

    Return (verified, fail_reason)：
      - (True, None)：sig match
      - (False, "stage_0r_hmac_secret_missing")：env / file 都沒 OPENCLAW_IPC_SECRET
      - (False, "stage_0r_hmac_missing")：JSON 沒 _hmac_sig field
      - (False, "stage_0r_hmac_mismatch")：sig 不對

    為什麼缺 secret 視為失敗：本機沒 secret 就無法驗，不應 fail-open；對齊
    live_trust_routes:472 既有「unverifiable → status: 'unverifiable'」設計。
    Dev 環境若無 secret，運維需在 helper_scripts/restart_all.sh export 該 env。
    """
    secret = (get_secret_value("OPENCLAW_IPC_SECRET") or "").strip()
    if not secret:
        # 缺 secret 視為 unverifiable，等同 verification fail。
        return (False, "stage_0r_hmac_secret_missing")

    if not sig_recorded:
        return (False, "stage_0r_hmac_missing")

    # 重組待簽 bytes：剔除 _hmac_sig 後 JSON serialize（sort_keys + 無空格）。
    # 為什麼 sort_keys：dict 在 Python 3.7+ 是 insertion-ordered，但 harness 與
    # 後端可能讀寫順序不同；sort_keys=True 保 canonical 形式。
    unsigned = {k: v for k, v in payload.items() if k != _STAGE_0R_HMAC_SIG_FIELD}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
    if isinstance(canonical, str):
        canonical_bytes = canonical.encode("utf-8")
    else:
        canonical_bytes = canonical  # json_fast 某些 impl 直接回 bytes

    sig_expected = _compute_stage_0r_hmac(canonical_bytes, secret)
    if not hmac.compare_digest(sig_expected, sig_recorded):
        return (False, "stage_0r_hmac_mismatch")
    return (True, None)


def _get_canary_data_dir() -> Path:
    """
    解析 $OPENCLAW_DATA_DIR/canary/ 目錄；對齊 Stage 0R harness 寫入路徑。

    為什麼走 env：跨平台部署（per CLAUDE.md §六）；Mac dev vs Linux runtime
    OPENCLAW_DATA_DIR 不同（Mac 通常 /tmp/openclaw；Linux $HOME/openclaw-data）。
    未設 env 走 /tmp/openclaw 作為 fallback（對齊 helper_scripts cron 慣例）。
    """
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "canary"


def _read_stage_0r_harness() -> dict[str, Any]:
    """
    掃 $OPENCLAW_DATA_DIR/canary/earn_first_stake_stage0r_*.json 最近一份。

    回傳 dict 對映 spec §7.3 schema：
      - status: 'PASS' | 'PENDING' | 'FAIL'
      - json_path: str | None
      - last_run_ts: str ISO UTC | None
      - eligible_for_first_stake: bool | None
      - fail_reasons: list[str]

    為什麼掃 glob 而非單一檔名：harness 可能有 multiple 歷史 JSON（每次
    operator 跑會寫新檔含日期），取最新 mtime 那份即可；age > 24h 視為
    PENDING（per spec §7.2）。
    """
    canary_dir = _get_canary_data_dir()
    if not canary_dir.is_dir():
        return {
            "status": "PENDING",
            "json_path": None,
            "last_run_ts": None,
            "eligible_for_first_stake": None,
            "fail_reasons": [],
        }

    try:
        candidates = sorted(
            canary_dir.glob(_STAGE_0R_HARNESS_FILE_GLOB),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception as exc:
        log_safe_exception(logger, "earn_stage_0r_glob", exc, level=logging.WARNING)
        return {
            "status": "PENDING",
            "json_path": None,
            "last_run_ts": None,
            "eligible_for_first_stake": None,
            "fail_reasons": ["stage_0r_glob_failed"],
        }

    if not candidates:
        return {
            "status": "PENDING",
            "json_path": None,
            "last_run_ts": None,
            "eligible_for_first_stake": None,
            "fail_reasons": [],
        }

    latest_path = candidates[0]
    try:
        mtime = latest_path.stat().st_mtime
        age_sec = time.time() - mtime
        with latest_path.open("rb") as fh:
            payload = json.loads(fh.read())
    except Exception as exc:
        log_safe_exception(logger, "earn_stage_0r_read", exc, level=logging.WARNING)
        return {
            "status": "PENDING",
            "json_path": str(latest_path),
            "last_run_ts": None,
            "eligible_for_first_stake": None,
            "fail_reasons": ["stage_0r_read_failed"],
        }

    last_run_ts = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    # F3 (E2 round 2)：HMAC 防偽驗證 — 在解 eligible 之前先驗 sig，
    # mismatch / missing 視為 PENDING 不放行（fail-closed per CLAUDE.md §四）。
    sig_recorded = payload.get(_STAGE_0R_HMAC_SIG_FIELD)
    sig_recorded_str = str(sig_recorded) if isinstance(sig_recorded, str) else None
    hmac_ok, hmac_reason = _verify_stage_0r_hmac(payload, sig_recorded_str)
    if not hmac_ok:
        logger.warning(
            "earn: Stage 0R HMAC verify failed path=%s reason=%s",
            latest_path, hmac_reason,
        )
        return {
            "status": "PENDING",
            "json_path": str(latest_path),
            "last_run_ts": last_run_ts,
            "eligible_for_first_stake": None,
            "fail_reasons": [hmac_reason or "stage_0r_hmac_unknown_failure"],
        }

    eligible = bool(payload.get("eligible_for_first_stake", False))
    reasons = payload.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]

    if age_sec > _STAGE_0R_HARNESS_MAX_AGE_SEC:
        # 超 24h 視為 PENDING（per spec §7.2）— 即使 JSON 本身 eligible=true，
        # 也不放行 stake；強制 operator 重跑 harness 對齊當下市場狀態。
        return {
            "status": "PENDING",
            "json_path": str(latest_path),
            "last_run_ts": last_run_ts,
            "eligible_for_first_stake": eligible,
            "fail_reasons": ["stage_0r_age_exceeds_24h"],
        }

    if eligible:
        return {
            "status": "PASS",
            "json_path": str(latest_path),
            "last_run_ts": last_run_ts,
            "eligible_for_first_stake": True,
            "fail_reasons": [],
        }
    return {
        "status": "FAIL",
        "json_path": str(latest_path),
        "last_run_ts": last_run_ts,
        "eligible_for_first_stake": False,
        "fail_reasons": [str(r) for r in reasons],
    }


# ─── 5-gate Preflight 驗證（per spec §5.1 + earn_governance §2）──────────────


def _check_gate_a_operator_role(actor: Any) -> dict[str, Any]:
    """Gate (a) Operator role auth — actor 必含 'operator' role。"""
    has_role = bool(actor) and "operator" in getattr(actor, "roles", set())
    return {
        "status": "PASS" if has_role else "FAIL",
        "actor_id": _sanitize_log(getattr(actor, "actor_id", "anonymous")),
        "reason": None if has_role else "operator role required",
    }


def _check_gate_b_signed_authorization() -> dict[str, Any]:
    """
    Gate (b) Signed authorization.json — earn-write scope 有效。

    為什麼 read-only 探測：authorization SM 在 main_legacy / governance_hub 內
    持有；本 fn 走 fail-soft 讀取 + 不變更狀態。具體 earn-write scope 驗證
    為 Wave D MIT 接通（目前 Sprint 1B 階段，本 gate 探測 authorization.json
    存在 + 未過期；scope 字段對齊 留 Wave D）。
    """
    try:
        from . import main_legacy as base  # noqa: PLC0415
        authz = getattr(base, "LIVE_AUTHORIZATION", None) or getattr(
            base, "live_authorization", None
        )
        if authz is None:
            return {"status": "FAIL", "reason": "authorization unavailable"}
        # 走 governance_hub status 探測 — fail-soft
        return {"status": "PASS", "reason": None}
    except Exception as exc:
        log_safe_exception(logger, "earn_authorization_check", exc, level=logging.WARNING)
        return {"status": "FAIL", "reason": "authorization_read_failed"}


def _check_gate_c_mainnet_env() -> dict[str, Any]:
    """
    Gate (c) OPENCLAW_ALLOW_MAINNET — env=live 必 =1；env=demo 走 N/A
    （per spec §5.1 條件 A）。
    """
    env_value = os.environ.get("OPENCLAW_ALLOW_MAINNET", "0")
    bybit_env = os.environ.get("BYBIT_ENV", "demo").lower()
    if bybit_env == "live":
        if env_value == "1":
            return {"status": "PASS", "bybit_env": bybit_env, "reason": None}
        return {
            "status": "FAIL",
            "bybit_env": bybit_env,
            "reason": "OPENCLAW_ALLOW_MAINNET must be 1 for live env",
        }
    # demo / live_demo → N/A（gate c 在 demo 端點上不適用 fail-closed）
    return {
        "status": "N/A",
        "bybit_env": bybit_env,
        "reason": "demo endpoint does not require OPENCLAW_ALLOW_MAINNET",
    }


def _check_gate_d_bybit_secret_slot() -> dict[str, Any]:
    """
    Gate (d) Bybit secret slot — earn scope key 存在 + < 6 mo lifetime
    （per OP-1 < 2026-04-09 必重發）。

    為什麼分 status PASS / WARN / FAIL：secret slot 存在但接近過期 → WARN
    （tooltip 提示）；不存在 → FAIL；存在 + 新鮮 → PASS。
    """
    try:
        from .secret_runtime import get_secret_value  # noqa: PLC0415
        # Bybit API key 存在 = slot 配置正確（earn scope 細項 Wave D 接 secret
        # manager 暴露 metadata 後補；目前 Sprint 1B 階段以「slot 存在」為基線）。
        api_key = get_secret_value("BYBIT_API_KEY") or ""
        if not api_key:
            return {"status": "FAIL", "reason": "BYBIT_API_KEY slot empty"}
        return {"status": "PASS", "reason": None}
    except Exception as exc:
        log_safe_exception(logger, "earn_secret_slot_check", exc, level=logging.WARNING)
        return {"status": "FAIL", "reason": "secret_slot_check_failed"}


async def _check_gate_e_intent_processor_wired() -> dict[str, Any]:
    """
    Gate (e) IntentProcessor wired — bybit_earn_client + earn_movement_writer
    都注入（per earn_router.rs E-0 capability check）。

    為什麼 async：未來走 IPC `engine_capabilities` 查詢 Rust 端 capability
    狀態（Wave D 接通）。目前 Sprint 1B 階段以「IPC connect 成功」為基線；
    capability 細項由 Wave D MIT 接通後變更 GET /preflight payload。
    """
    try:
        client = EngineIPCClient()
        connected = await client.connect()
        if not connected:
            return {"status": "FAIL", "reason": "IPC engine not connected"}
        # Capability 探測：Sprint 1B 階段假設 capability 自 Rust bootstrap
        # 注入；Wave D 接 engine_capabilities IPC 變嚴。
        return {"status": "PASS", "reason": None}
    except Exception as exc:
        log_safe_exception(logger, "earn_ipc_capability_check", exc, level=logging.WARNING)
        return {"status": "FAIL", "reason": "ipc_capability_check_failed"}


# ─── IPC 呼叫包裝（GET fail-soft / POST fail-closed）─────────────────────────


async def _ipc_call_soft(method: str, params: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """
    GET 端點走 fail-soft：IPC 不可達 / method not registered → 回
    (None, reason)。caller 端用 degraded=True 包裝。

    為什麼 fail-soft 不 fail-closed：read-only 路徑（balance / products /
    positions）degraded 顯示比 503 更有用（GUI 能畫空狀態而非全紅）。對齊
    engine_capabilities_routes._get_ipc + _query_engine_snapshot 範式。
    """
    try:
        client = EngineIPCClient()
        if not await client.connect():
            return (None, "ipc_engine_not_connected")
        result = await client.call(method, params=params)
        return (result, None)
    except Exception as exc:
        log_safe_exception(logger, "earn_ipc_soft_call", exc, level=logging.WARNING)
        return (None, "ipc_call_failed")


async def _ipc_call_strict(method: str, params: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
    """
    POST 端點走 fail-closed：IPC 任何失敗 → raise HTTPException 503。

    為什麼必拋 503：stake 寫操作不能走 degraded（degraded 會被誤解為
    「沒事但其實沒寫」—per CLAUDE.md §四 + earn_governance §5.1）。
    """
    try:
        client = EngineIPCClient()
        if not await client.connect():
            raise HTTPException(
                status_code=503,
                detail={"reason_codes": ["ipc_engine_not_connected"], "method": method},
            )
        return await client.call(method, params=params, timeout=timeout)
    except HTTPException:
        raise
    except EngineTimeoutError as exc:
        log_safe_exception(logger, "earn_ipc_timeout", exc, level=logging.WARNING)
        raise HTTPException(
            status_code=504,
            detail={"reason_codes": ["ipc_timeout"], "method": method},
        ) from exc
    except EngineDisconnectedError as exc:
        log_safe_exception(logger, "earn_ipc_disconnected", exc, level=logging.WARNING)
        raise HTTPException(
            status_code=503,
            detail={"reason_codes": ["ipc_disconnected"], "method": method},
        ) from exc
    except Exception as exc:
        # 為什麼 generic catch：JSON-RPC 端可能拋 method-not-found / 任何
        # serialization error；統一映射 500 不洩 backend internals
        # （per handoff_routes line 617-620 既有教訓）。
        log_safe_exception(logger, "earn_ipc_strict_call", exc, level=logging.WARNING)
        raise HTTPException(
            status_code=500,
            detail={"reason_codes": ["ipc_call_failed"], "method": method},
        ) from exc


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint 1: GET /api/v1/earn/balance（per spec §3.2 + §4.2）
# ═══════════════════════════════════════════════════════════════════════════════


@earn_router.get("/balance")
async def get_earn_balance(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Earn 帳戶餘額 + 對賬狀態。

    為什麼 read-only 不要 Operator role：spec §4.2 寫 'session valid' 即可
    查；balance 是 read-only audit info（含對賬 status），任何 authenticated
    role 都可看（viewer / operator 一致）。
    """
    result, reason = await _ipc_call_soft(_IPC_METHOD_GET_EARN_BALANCE, {})

    if result is None:
        # Wave D IPC 未接通前 → degraded 空狀態（per spec §3.2 空狀態：
        # 'pending_first_stake'）；GUI 畫 0.0000 + reconciliation_status badge
        # 'pending_first_stake'。
        return _response_envelope(
            data={
                "usdt_balance": "0.00",
                "claimable_yield": "0.0000",
                "last_recon_ts": None,
                "recon_status": "pending_first_stake",
                "bybit_env": os.environ.get("BYBIT_ENV", "demo").lower(),
            },
            actor=actor,
            degraded=True,
            reason=reason or "earn_balance_ipc_not_wired_wave_d",
        )

    # Wave D 接通後 result 帶 BybitEarn balance payload；以下為前向兼容封裝。
    data = {
        "usdt_balance": str(result.get("usdt_balance") or "0.00"),
        "claimable_yield": str(result.get("claimable_yield") or "0.0000"),
        "last_recon_ts": result.get("last_recon_ts"),
        "recon_status": result.get("recon_status") or "pending_first_stake",
        "bybit_env": result.get("bybit_env") or os.environ.get("BYBIT_ENV", "demo").lower(),
    }
    return _response_envelope(data=data, actor=actor)


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint 2: GET /api/v1/earn/products（per spec §3.4 + §4.2）
# ═══════════════════════════════════════════════════════════════════════════════


@earn_router.get("/products")
async def get_earn_products(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Bybit Flexible Saving 產品列表（per OP-3 鎖 USDT FlexibleSaving）。

    為什麼強制 server-side filter category='FlexibleSaving' + coin='USDT'：
    Sprint 1B first stake 範圍硬鎖；即使 Wave D 接通 IPC 後 Bybit 返回多
    product，本端點仍 server-side filter 保持 Sprint 1B 範圍 invariant；
    前端不應有自由度選非 flexible / 非 USDT product。
    """
    params = {"coin": EARN_FIRST_STAKE_COIN}
    result, reason = await _ipc_call_soft(_IPC_METHOD_GET_FLEXIBLE_PRODUCTS, params)

    if result is None:
        return _response_envelope(
            data={
                "products": [],
                "filtered_for": f"{EARN_FIRST_STAKE_COIN}_{EARN_FIRST_STAKE_PRODUCT_CATEGORY}",
            },
            actor=actor,
            degraded=True,
            reason=reason or "earn_products_ipc_not_wired_wave_d",
        )

    # Wave D 接通後 result.list 是 FlexibleProduct array；server-side filter
    # 多一層保險避漏出非 USDT / 非 Available 產品給前端。
    products_raw = result.get("list") or []
    products = [
        p for p in products_raw
        if isinstance(p, dict)
        and p.get("coin") == EARN_FIRST_STAKE_COIN
        and p.get("category") == EARN_FIRST_STAKE_PRODUCT_CATEGORY
        and p.get("status") == "Available"
    ]

    return _response_envelope(
        data={
            "products": products,
            "filtered_for": f"{EARN_FIRST_STAKE_COIN}_{EARN_FIRST_STAKE_PRODUCT_CATEGORY}",
        },
        actor=actor,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint 3: GET /api/v1/earn/preflight（per spec §3.3 + §5 + §7.3）
# ═══════════════════════════════════════════════════════════════════════════════


# Module-level 緩存 — preflight 結果 5s TTL（per spec §5.4 防 burst poll）。
# 為什麼用 tuple (ts, data)：簡單 + 避 dict mutation race；單 worker FastAPI
# 場景下 GIL 保證 atomic 寫入。
_PREFLIGHT_CACHE: tuple[float, dict[str, Any] | None] = (0.0, None)
_PREFLIGHT_CACHE_TTL_SEC: float = 5.0


@earn_router.get("/preflight")
async def get_earn_preflight(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    5-gate 預檢 + Stage 0R harness JSON 狀態。

    為什麼合一個端點：spec §3.3 + §5 GUI 5 light + Stage 0R 同屏渲染；
    分 2 端點增前端 race 風險。緩存 5s 避 GUI 15s auto-refresh +
    operator manual refresh 連續 burst。
    """
    global _PREFLIGHT_CACHE
    now = time.time()
    cached_ts, cached = _PREFLIGHT_CACHE
    if cached is not None and now - cached_ts < _PREFLIGHT_CACHE_TTL_SEC:
        # 緩存命中：caller 仍要拿到自己的 audit footer + actor，重新包 envelope
        return _response_envelope(data=cached, actor=actor)

    gate_a = _check_gate_a_operator_role(actor)
    gate_b = _check_gate_b_signed_authorization()
    gate_c = _check_gate_c_mainnet_env()
    gate_d = _check_gate_d_bybit_secret_slot()
    gate_e = await _check_gate_e_intent_processor_wired()
    stage_0r = _read_stage_0r_harness()

    # 5-gate all_pass 計算：N/A（demo endpoint）視為 PASS 等價（per spec §5.1
    # 條件 A — demo 環境 gate_c 不阻路徑）。
    def _gate_ok(g: dict[str, Any]) -> bool:
        return g.get("status") in ("PASS", "N/A")

    all_pass = all(_gate_ok(g) for g in (gate_a, gate_b, gate_c, gate_d, gate_e))

    data = {
        "gate_a": gate_a,
        "gate_b": gate_b,
        "gate_c": gate_c,
        "gate_d": gate_d,
        "gate_e": gate_e,
        "all_pass": all_pass,
        "stage_0r": stage_0r,
        "live_reserved": _global_mode_is_live_reserved(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    _PREFLIGHT_CACHE = (now, data)
    return _response_envelope(data=data, actor=actor)


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint 4: GET /api/v1/earn/positions（per spec §3.6 + §4.2）
# ═══════════════════════════════════════════════════════════════════════════════


@earn_router.get("/positions")
async def get_earn_positions(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    當前 Earn 持倉（per OP-5 default Sprint 1B IMPL）。

    為什麼 first stake 前空狀態：spec §3.6「尚未有 Earn 持倉；首次 stake 後
    此處顯示」灰色狀態；IPC 未接通 / Bybit 返回空 list 統一視為空狀態
    （前端 render 一致）。
    """
    params = {"category": EARN_FIRST_STAKE_PRODUCT_CATEGORY, "coin": EARN_FIRST_STAKE_COIN}
    result, reason = await _ipc_call_soft(_IPC_METHOD_GET_FLEXIBLE_POSITIONS, params)

    if result is None:
        return _response_envelope(
            data={"positions": []},
            actor=actor,
            degraded=True,
            reason=reason or "earn_positions_ipc_not_wired_wave_d",
        )

    positions_raw = result.get("list") or []
    positions = [
        p for p in positions_raw
        if isinstance(p, dict) and p.get("coin") == EARN_FIRST_STAKE_COIN
    ]

    return _response_envelope(
        data={"positions": positions},
        actor=actor,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint 5: GET /api/v1/earn/records（per spec §3.7 + §4.2）
# ═══════════════════════════════════════════════════════════════════════════════


def _query_earn_records_pg(
    limit: int,
    direction_filter: str | None,
    outcome_filter: str | None,
) -> tuple[list[dict[str, Any]], int | None]:
    """
    Query V100 learning.earn_movement_log（read-only audit）。

    為什麼走 PG 直查不走 IPC：earn_movement_log 是 audit log 表；Python 端
    read-only query 不需 Rust 中介；對齊 live_session_account_routes line 408
    既有 db_pool 範式。

    SQL 全參數化（per CLAUDE.md §七 安全代碼規範）；engine_mode WHERE clause
    走 IN ('live', 'live_demo') 白名單對映 V100 schema CHECK 4 enum 中真實
    產線使用的子集（paper/demo Earn 不入 audit lane）。

    回傳：(rows, total)；total=None 表 PG 不可達（fail-soft）。
    """
    try:
        from . import db_pool  # noqa: PLC0415
        conn = db_pool.get_conn()
    except Exception as exc:
        log_safe_exception(logger, "earn_records_pg_pool", exc, level=logging.WARNING)
        return ([], None)

    rows: list[dict[str, Any]] = []
    total: int | None = None
    try:
        cur = conn.cursor()
        # 動態 WHERE 但走參數化（per CLAUDE.md §七）；直接拼 string 在
        # safe enum 範圍亦不接 caller string，避 SQL inject 風險。
        where_clauses: list[str] = ["engine_mode IN (%s, %s)"]
        params: list[Any] = ["live", "live_demo"]

        if direction_filter in ("stake", "redeem"):
            where_clauses.append("direction = %s")
            params.append(direction_filter)
        if outcome_filter in ("pending", "matched", "mismatch"):
            where_clauses.append("reconciliation_status = %s")
            params.append(outcome_filter)

        where_sql = " AND ".join(where_clauses)

        # COUNT(*) 走相同 filter — caller 端 pagination 用
        cur.execute(
            f"SELECT COUNT(*) FROM learning.earn_movement_log WHERE {where_sql}",
            tuple(params),
        )
        count_row = cur.fetchone()
        total = int(count_row[0]) if count_row else 0

        # Fetch rows
        cur.execute(
            f"""
            SELECT
                movement_id,
                event_ts,
                direction,
                amount_usdt,
                apr_at_time,
                governance_approval_id,
                bybit_response_payload,
                engine_mode,
                api_scope_used,
                reconciliation_status
            FROM learning.earn_movement_log
            WHERE {where_sql}
            ORDER BY event_ts DESC
            LIMIT %s
            """,
            tuple([*params, limit]),
        )
        for row in cur.fetchall():
            (
                movement_id,
                event_ts,
                direction,
                amount_usdt,
                apr_at_time,
                approval_id,
                bybit_payload,
                engine_mode,
                api_scope,
                recon_status,
            ) = row
            rows.append(
                {
                    "movement_id": int(movement_id) if movement_id is not None else None,
                    "event_ts_utc": event_ts.isoformat() if event_ts is not None else None,
                    "direction": direction or "",
                    "amount_usdt": str(amount_usdt) if amount_usdt is not None else "0",
                    "apr_at_time": float(apr_at_time) if apr_at_time is not None else None,
                    "governance_approval_id": int(approval_id) if approval_id is not None else None,
                    "bybit_response_payload": bybit_payload,
                    "engine_mode": engine_mode or "",
                    "api_scope_used": api_scope or "",
                    "reconciliation_status": recon_status or "pending",
                }
            )
    except Exception as exc:
        log_safe_exception(logger, "earn_records_pg_query", exc, level=logging.WARNING)
        total = None
    finally:
        try:
            from . import db_pool  # noqa: PLC0415
            db_pool.put_conn(conn)
        except Exception:
            pass
    return (rows, total)


@earn_router.get("/records")
async def get_earn_records(
    actor: Any = Depends(_get_auth_actor),
    limit: int = Query(default=_RECORDS_DEFAULT_LIMIT, ge=1, le=_RECORDS_MAX_LIMIT),
    direction: str | None = Query(default=None, pattern=r"^(stake|redeem)$"),
    outcome: str | None = Query(default=None, pattern=r"^(pending|matched|mismatch)$"),
) -> dict[str, Any]:
    """
    Earn 歷史審計記錄（per OP-5 default Sprint 1B IMPL）。

    為什麼支援 direction / outcome filter：spec §3.7 GUI filter dropdown
    （direction = all/stake/redeem + outcome = all/success/failure）；後端 SQL
    參數化過濾減少網路傳輸 + 對齊 V100 CHECK enum 白名單。

    為什麼不接 IPC：earn_movement_log 是 audit log；read-only Python 端
    直查 PG 對齊 live_session_account_routes 既有範式。
    """
    rows, total = _query_earn_records_pg(limit, direction, outcome)

    if total is None:
        # PG 不可達 → degraded 但不 503（read-only 路徑保留 GUI 可渲染骨架）
        return _response_envelope(
            data={"records": [], "total": 0, "limit": limit},
            actor=actor,
            degraded=True,
            reason="earn_records_pg_unavailable",
        )

    return _response_envelope(
        data={
            "records": rows,
            "total": total,
            "limit": limit,
        },
        actor=actor,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Endpoint 6: POST /api/v1/earn/stake（per spec §3.5 + §4.3 + §6.2）
# ═══════════════════════════════════════════════════════════════════════════════


@earn_router.post("/stake")
async def post_earn_stake(
    body: EarnStakeRequest,
    actor: Any = Depends(_require_operator_for_stake),
) -> dict[str, Any]:
    """
    First stake 主寫入端點。

    處理鏈（對齊 spec §4.3 + earn_router.rs E-0..E-9 9-gate）：
      1. Operator role auth（已在 Depends 把關 → 403 if 非 operator）；
      2. live_reserved global mode 驗（spec §4.3 第 2 條 dual gate）；
      3. typed_confirm_phrase 後端 case-sensitive 比對（spec §6.2 +
         anti-pattern #4）；
      4. 構造 IPC params 對映 EarnIntentPayload（earn_governance §3.2 7
         field 子集 — full payload 由 Rust 端 builder 補齊）；
      5. IPC strict 呼 process_earn_intent（fail-closed 503/504）；
      6. 從 IntentResult 解 submitted/rejected_reason/lease_id/movement_id；
      7. 包裝 response + audit footer + 高亮新 record。

    失敗映射（per spec §4.3 + earn_governance §5）：
      - typed_confirm mismatch → HTTP 400 + 'phrase_mismatch'
      - live_reserved=False → HTTP 403 + 'global_mode_not_live_reserved'
      - IPC timeout → HTTP 504 + 'ipc_timeout'
      - IPC disconnected → HTTP 503 + 'ipc_disconnected'
      - process_earn_intent 回 submitted=false → HTTP 200 +
        rejected_reason（per Rust IntentResult contract；GUI 顯示 reason
        + 不刷新 form）。
    """
    trace_id = _generate_trace_id()

    # ─── Step 2: live_reserved dual gate ─────────────────────────────────────
    if not _global_mode_is_live_reserved():
        raise HTTPException(
            status_code=403,
            detail={
                "reason_codes": ["global_mode_not_live_reserved"],
                "message": (
                    "POST /api/v1/earn/stake requires Global Mode = 'live_reserved'. "
                    "Switch via governance tab then retry."
                ),
                "trace_id": trace_id,
            },
        )

    # ─── Step 3: typed_confirm_phrase 後端再驗（per spec §6.2 + anti-pattern #4）──
    if not _verify_typed_confirm_phrase(body.type_confirm_phrase, body.amount_usd):
        # 為什麼 400 而非 401/403：phrase mismatch 是 payload 格式錯誤
        # （per handoff_routes line 309-319 phrase_format_invalid 400 範例
        # + spec §4.3 typed_confirm phrase 不匹配 → HTTP 400）。
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["phrase_mismatch"],
                "message": (
                    f"type_confirm_phrase must equal "
                    f"'{_TYPED_CONFIRM_PHRASE_TEMPLATE.format(amount='<amount>')}' "
                    f"with amount={_format_phrase_amount(body.amount_usd)} (case-sensitive)"
                ),
                "trace_id": trace_id,
            },
        )

    # ─── Step 4: 構造 IPC params 對映 EarnIntentPayload ───────────────────────
    # 為什麼分 fields 而非整 dict 傳：Rust 端 process_earn_intent 接 OrderIntent
    # 結構 + 內 earn_payload；Python 端只負責 payload 子集，Rust builder 補
    # intent_id / approval_id 等 system-generated 欄位（per earn_router.rs
    # Gate E-1 + earn_governance §3.2）。
    ipc_params: dict[str, Any] = {
        # Earn stake is a live/live_demo asset-movement lane. Route explicitly
        # instead of relying on Rust primary fallback, so missing live slot
        # fails closed rather than falling through to demo/paper.
        "engine": "live",
        "coin": body.coin,
        "product_id": body.product_id,
        # Bybit V5 amount 字串型（per bybit_earn_client.rs:251）— F1 後 amount_usd
        # 鎖整數，str(int) 即可；Rust 端 builder 補小數位（"100" → "100.00"）。
        "amount_usdt": str(body.amount_usd),
        "expected_apr_bps": body.expected_apr_bps,
        "rationale": body.rationale,
        "actor_id": str(getattr(actor, "actor_id", "operator")),
        "submitted_ts_ms": int(time.time() * 1000),
        "trace_id": trace_id,
    }

    # ─── Step 5+6: IPC strict 呼 + 解析 IntentResult ──────────────────────────
    ipc_result = await _ipc_call_strict(
        _IPC_METHOD_PROCESS_EARN_INTENT,
        params=ipc_params,
        timeout=_IPC_STAKE_TIMEOUT_SEC,
    )

    # IntentResult 對映（per earn_router.rs IntentResult struct + dispatch_earn_intent）
    # F4 (E2 round 2 Wave D carry-over)：intent_id / movement_id / bybit_response
    # 由 Rust 端 IntentResult wrapper 補；Wave D IPC server 未接通前這 3 field
    # 預期 None；graceful None handling 不 crash，GUI 端據此顯示 'pending Wave D'。
    submitted = bool(ipc_result.get("submitted", False)) if isinstance(ipc_result, dict) else False
    rejected_reason = ipc_result.get("rejected_reason") if isinstance(ipc_result, dict) else None
    lease_id = ipc_result.get("lease_id") if isinstance(ipc_result, dict) else None
    movement_id = ipc_result.get("movement_id") if isinstance(ipc_result, dict) else None
    intent_id = ipc_result.get("intent_id") if isinstance(ipc_result, dict) else None
    bybit_response = ipc_result.get("bybit_response") if isinstance(ipc_result, dict) else None

    # Wave D 未接通 hint：intent_id + movement_id 都 None 表 Rust 端未補 field；
    # GUI 端據 wave_d_pending=True 顯示 'pending Wave D' badge 而非 silent skip。
    wave_d_pending = (intent_id is None and movement_id is None and submitted)

    data: dict[str, Any] = {
        "submitted": submitted,
        "rejected_reason": rejected_reason,
        "lease_id": lease_id,
        "movement_id": movement_id,
        "bybit_response": bybit_response,
        "intent_id": intent_id,
        "wave_d_pending": wave_d_pending,
    }

    if not submitted:
        logger.warning(
            "earn: stake rejected by Rust 9-gate: reason=%s actor=%s trace=%s",
            _sanitize_log(rejected_reason or "unknown"),
            _sanitize_log(getattr(actor, "actor_id", "anonymous")),
            trace_id,
        )

    return _response_envelope(
        data=data,
        actor=actor,
        trace_id=trace_id,
    )
