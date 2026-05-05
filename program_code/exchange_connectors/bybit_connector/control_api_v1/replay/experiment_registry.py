"""REF-20 Sprint A R2 — replay.experiments registry helpers (Wave R2-T1).
REF-20 Sprint A R2 — replay.experiments 註冊表輔助（Wave R2-T1）。

MODULE_NOTE (EN):
    Sprint A R2-T1 (2026-05-04) extraction. Owns the
    ``POST /api/v1/replay/experiments/register`` business logic so that
    ``app/replay_routes.py`` can keep its thin route handler under the
    ``CLAUDE.md §九`` 1500 LOC hard cap. The route handler in
    ``replay_routes.py`` only does ``_require_replay_write(actor)`` then
    delegates here via ``asyncio.to_thread``.

    What this module does:
      - ``ReplayExperimentRegisterRequest`` Pydantic model with strict
        validators for V049 ``replay.experiments`` 22-column contract:
        symbol/strategy alphanumeric+_ guard, data_tier enum (S2/S3/S4),
        timeframe enum (V049 8-value allowlist), strategy_config_sha256
        and risk_config_sha256 as REQUIRED 64 hex char fields per Gap
        Closure Plan §5 mandate, manifest_jsonb 256 KB body cap, window
        end > start.
      - ``register_experiment(cur, actor, body) -> dict`` synchronous
        helper that runs inside the caller-owned PG transaction:
          1. Compute server-side ``experiment_id = uuid.uuid4()``.
          2. Compute ``manifest_hash = sha256(canonical_bytes)`` reusing
             the canonical-bytes contract from Sprint 1 F1 retrofit
             (sort_keys=True / separators=(',', ':') / ensure_ascii=False).
          3. If ``signature_hex`` provided → verify via
             ``manifest_signer.ManifestSigner`` from-bytes test path
             (production path lands in R2-T3 with secrets file).
          4. Acquire advisory lock keyed on ``(idempotency_key, actor)``
             then SELECT-then-INSERT for idempotency (V049 lacks the
             ``idempotency_key`` column so we cannot use the natural
             ``ON CONFLICT (idempotency_key, created_by) DO UPDATE``
             pattern; the advisory lock pattern is the prescribed
             fallback per R2-T1 spec note 7).
          5. INSERT V049 22-column contract: server-derived
             ``experiment_id`` + ``created_by=actor.actor_id`` +
             ``runtime_environment`` from env (CHECK enum 2-value) +
             ``timeframe`` from body (CHECK 8-value) + ``data_tier``
             from body (CHECK 5-value) + ``execution_confidence='none'``
             (Sprint A R3 default per plan §6.R6) + ``status='created'``
             + windows from body + ``manifest_jsonb`` + ``manifest_hash``
             + optional ``manifest_signature`` + ``signature_key_ref``.

    What this module does NOT do (R3+ scope):
      - simulated_fills_writer (R3 ``/finalize`` endpoint).
      - register_artifact_in_db post-spawn (R3 wire).
      - Production secrets file ``replay_signing_key`` lookup
        (R2-T3 in ``manifest_signer.py::load_signing_key_from_secrets_dir``).

MODULE_NOTE (中):
    Sprint A R2-T1（2026-05-04）抽出。擁有 ``POST /api/v1/replay/
    experiments/register`` 業務邏輯，讓 ``app/replay_routes.py`` 的薄
    route handler 守住 ``CLAUDE.md §九`` 1500 LOC 硬上限。replay_routes
    handler 只跑 ``_require_replay_write(actor)`` 然後透過
    ``asyncio.to_thread`` 委派至此。

    本 module 做的事：
      - ``ReplayExperimentRegisterRequest`` Pydantic model，嚴格 validator
        對齊 V049 ``replay.experiments`` 22 col 契約。
      - ``register_experiment(cur, actor, body) -> dict`` 同步 helper，
        在 caller 持有的 PG transaction 內執行。
      - V049 缺 ``idempotency_key`` 欄位 → 不能用 ``ON CONFLICT``；改用
        advisory lock + SELECT-then-INSERT pattern（R2-T1 spec note 7）。
      - ``signature_hex`` 若提供 → 驗 HMAC（重用 ``manifest_signer``）。

    本 module 不做（R3+ 範圍）：
      - simulated_fills_writer（R3 ``/finalize``）。
      - register_artifact_in_db post-spawn wire（R3）。
      - 生產 secrets file ``replay_signing_key`` lookup（R2-T3 在
        ``manifest_signer.py::load_signing_key_from_secrets_dir``）。

SPEC: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md §6.R2 / §5
V049 contract: sql/migrations/V049__replay_experiments.sql
Idempotency note: R2-T1 spec note 7 — V049 has no (idempotency_key, created_by)
                  unique index; advisory lock + SELECT-then-INSERT pattern used.
Canonical-bytes contract: replay/manifest_signer.py + replay/route_helpers.py
                          (Sprint 1 F1 retrofit invariant).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Optional, Tuple

from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# REF-20 Sprint A R2 round 2 fix H-1: in-memory idempotency cache.
# REF-20 Sprint A R2 round 2 fix H-1：記憶體 idempotency cache。
#
# Why module-level dict (not DB column / not manifest_jsonb pollution):
#   * Round 1 stamped ``_idempotency_key`` into ``manifest_jsonb`` so the
#     SELECT-then-INSERT pattern could find the row, but that broke the
#     ``sha256(manifest_jsonb) == manifest_hash`` invariant — the persisted
#     row was no longer self-consistent (E2 review H-1).
#   * V049 has no ``(idempotency_key, created_by)`` UNIQUE INDEX (R2-T1
#     spec note 7) so we can't use a natural SQL idempotency anchor.
#   * Add-a-V###-migration is forbidden by Sprint A R2 round 2 scope.
#
# Trade-off accepted (per E2 review H-1):
#   * Restart loses the cache. Operator re-issuing the same idempotency_key
#     after restart will get a NEW experiment_id (no replay-level dedup
#     across restart). V3 §5 30d idempotency TTL is a write-time guarantee
#     — after restart we lose that guarantee but treat it as the same
#     semantic class as restart-loses-pending-state.
#   * Race-safe within process: ``_REGISTER_IDEM_CACHE_THREAD_LOCK``
#     (threading.Lock) serializes lookups inside one uvicorn worker. The
#     register code path runs inside ``asyncio.to_thread`` so a thread-level
#     Lock is the correct primitive — not an asyncio Lock — and round 3
#     dropped a dead asyncio Lock module that had 0 callsite (E2 round 2
#     review M-DEAD-LOCK).
#   * Race-safe across xact: PG advisory xact lock (acquired in
#     ``_try_acquire_register_idempotency_lock``) serializes register
#     attempts of the same (actor, key) tuple at the DB layer; if both
#     pass the cache miss check + advisory lock → only one INSERT can win.
#   * Multi-worker fallback (uvicorn workers > 1): per-process module-level
#     dict means each worker has its own cache — cache hit % degrades but
#     race-safety is unbroken because the PG advisory xact lock + V049
#     single-row constraint are the real invariants. Two workers that both
#     miss cache + race the advisory lock → one INSERTs, the other SELECTs
#     the existing row + cache-fills locally → same experiment_id returned
#     to both clients.
#
# Why module-level dict 不用 DB column / 不污染 manifest_jsonb：
#   * Round 1 把 ``_idempotency_key`` 注入 ``manifest_jsonb`` 讓 SELECT-then-
#     INSERT 找得到 row，破了 ``sha256(manifest_jsonb) == manifest_hash``
#     不變式（E2 review H-1）。
#   * V049 無 ``(idempotency_key, created_by)`` UNIQUE INDEX 做天然 idempotency
#     anchor（R2-T1 spec note 7）。
#   * Sprint A R2 round 2 範圍禁加 V### migration。
#
# 取捨（E2 review H-1 accept）：
#   * 重啟丟 cache。同 idempotency_key 重啟後再送會拿到 *新* experiment_id；
#     失去 V3 §5 30d 跨重啟保證，視同 restart-loses-pending-state 同類。
#   * Process 內 race-safe：``_REGISTER_IDEM_CACHE_THREAD_LOCK``（threading.Lock）
#     序列化（caller 在 ``asyncio.to_thread`` 內，thread-level Lock 是正確原語）。
#     Round 3 刪掉了從未被呼叫的 asyncio Lock 模組（E2 round 2 review M-DEAD-LOCK）。
#   * 跨 xact race-safe：PG advisory xact lock 序列化同 (actor, key) tuple。
#   * Multi-worker fallback：每 worker 各自 cache，cache hit % 退化但 race-safety
#     不變（PG advisory lock + V049 single-row constraint 是真不變量）。
# ─────────────────────────────────────────────────────────────────────────
_REGISTER_IDEM_CACHE: dict[Tuple[str, str], dict[str, Any]] = {}
_REGISTER_IDEM_CACHE_THREAD_LOCK = threading.Lock()  # sync-safe inside to_thread


# ─── Constants / 常數 ─────────────────────────────────────────────────
# V049 CHECK enum allowlists (mirror sql/migrations/V049 lines 332-395).
# V049 CHECK enum 白名單（鏡像 sql/migrations/V049 第 332-395 行）。
V049_DATA_TIER_REGISTER_ALLOWED = ("S2", "S3", "S4")
V049_TIMEFRAME_ALLOWED = ("1m", "3m", "5m", "15m", "1h", "4h", "1d", "tick")
V049_RUNTIME_ENV_ALLOWED = ("linux_trade_core", "mac_dev_smoke_test_only")
V049_EXECUTION_CONFIDENCE_DEFAULT = "none"  # Sprint A R3 default per plan §6.R6
V049_STATUS_CREATED = "created"

# manifest_jsonb size cap (bytes). Aligned with Track C P0-5b artifact 256 KB
# read cap so a registered manifest can always be read back.
# manifest_jsonb 大小上限（bytes）。對齊 Track C P0-5b artifact 256 KB 讀
# 上限，讓註冊過的 manifest 永遠可讀回。
MANIFEST_JSONB_MAX_BYTES = 256 * 1024

# Advisory lock prefix for idempotency-key-scoped SELECT-then-INSERT pattern.
# Distinct from ADVISORY_LOCK_GLOBAL_KEY (run-cap) and
# ADVISORY_LOCK_PER_ACTOR_PREFIX (run-cap) in route_helpers.
# 給 idempotency-key SELECT-then-INSERT 的 advisory lock prefix。
# 與 route_helpers 的 run-cap lock 區隔。
ADVISORY_LOCK_REGISTER_IDEMPOTENCY_PREFIX = "replay_register_idem:"


# ─── Pydantic request model / Pydantic 請求模型 ────────────────────────


class ReplayExperimentRegisterRequest(BaseModel):
    """POST /experiments/register body — register a manifest in V049.
    POST /experiments/register body — 在 V049 註冊 manifest。

    Wave R2-T1 (2026-05-04): V049 contract requires server to derive
    ``experiment_id``, ``created_at``, ``created_by``, ``manifest_hash``,
    ``runtime_environment`` etc. The client only supplies the
    business-meaningful fields (symbol/strategy/window/configs/
    manifest_jsonb) plus optional ``idempotency_key`` +
    ``signature_hex`` + ``signature_key_ref``.

    Wave R2-T1（2026-05-04）：V049 契約規定 server 衍生
    ``experiment_id`` / ``created_at`` / ``created_by`` /
    ``manifest_hash`` / ``runtime_environment`` 等。client 只提供業務
    欄位 + 選填 idempotency / signature。

    SPEC § §5 mandate: ``strategy_config_sha256`` + ``risk_config_sha256``
    are REQUIRED. Without these the registered manifest cannot be replayed
    deterministically (cf. plan §5 row 4-6).
    """

    idempotency_key: Optional[str] = Field(
        default=None,
        max_length=128,
        description=(
            "Optional idempotency key; if (key, actor) collides with an "
            "existing replay.experiments row the prior row is returned "
            "instead of INSERT. Advisory lock pattern (V049 lacks the "
            "natural unique index column) — see R2-T1 spec note 7."
        ),
    )
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Trading pair symbol (e.g. BTCUSDT); alphanumeric+_.",
    )
    strategy: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Strategy name (e.g. grid_trading); alphanumeric+_.",
    )
    timeframe: str = Field(
        ...,
        min_length=1,
        max_length=8,
        description="Bar timeframe; V049 CHECK enum 8-value allowlist.",
    )
    data_tier: str = Field(
        ...,
        pattern="^(S2|S3|S4)$",
        description=(
            "Data tier per V3 §3 G1; register-time enum restricted to "
            "(S2, S3, S4) — Sprint A scope per plan §6.R2."
        ),
    )
    data_window_start: datetime = Field(
        ...,
        description="OOS label window start (UTC).",
    )
    data_window_end: datetime = Field(
        ...,
        description="OOS label window end (UTC); must be > start.",
    )
    strategy_config_sha256: str = Field(
        ...,
        pattern="^[0-9a-f]{64}$",
        description=(
            "REQUIRED per plan §5 mandate: 64-char lowercase hex SHA-256 "
            "of canonical strategy config snapshot at register time."
        ),
    )
    risk_config_sha256: str = Field(
        ...,
        pattern="^[0-9a-f]{64}$",
        description=(
            "REQUIRED per plan §5 mandate: 64-char lowercase hex SHA-256 "
            "of canonical risk_config snapshot at register time."
        ),
    )
    half_life_days: float = Field(
        ...,
        gt=0,
        le=365,
        description="V049 V041 stub field; signal half-life in days (0 < x ≤ 365).",
    )
    embargo_days: float = Field(
        default=0.0,
        ge=0,
        le=365,
        description="V049 V041 stub field; OOS embargo in days (≥0, ≤365).",
    )
    manifest_jsonb: dict[str, Any] = Field(
        ...,
        description=(
            "Full manifest payload per V3 §4.1; serialized canonically "
            "into ``manifest_hash``. 256 KB cap (raw JSON bytes)."
        ),
    )
    signature_hex: Optional[str] = Field(
        default=None,
        min_length=64,
        max_length=128,
        description=(
            "Optional pre-computed HMAC-SHA256 signature (hex). If "
            "provided, server verifies before INSERT. Production path "
            "loads signing key from $OPENCLAW_SECRETS_DIR/<env>/"
            "replay_signing_key (R2-T3 secrets-file path)."
        ),
    )
    signature_key_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description=(
            "Key reference (e.g. 'live/replay_signing_key:v3'); never "
            "secret value. Mirrors V049 ``signature_key_ref`` column."
        ),
    )
    # ── REF-20 Sprint B2 R5-T6 round 2 — config blob top-level fields ────
    # ── REF-20 Sprint B2 R5-T6 round 2 — 配置 blob 頂層欄位 ─────────────
    strategy_params: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "REF-20 Sprint B2 R5-T6 round 2: optional strategy parameter "
            "blob (e.g. {grid_levels: 20}). When supplied, server computes "
            "``strategy_config_sha256 = sha256(canonical_bytes(blob))`` and "
            "OVERRIDES the client-supplied ``strategy_config_sha256`` field "
            "so A4 acceptance fixture (PA design §5.1) can register two "
            "experiments with same strategy name + DIFFERENT params and "
            "observe distinct sha values in V049. Persisted into a copy of "
            "manifest_jsonb under reserved key ``_replay_strategy_params`` "
            "(post-validation injection bypasses the M-4 ``_*`` prefix "
            "rejector which only fires on client-supplied keys). The "
            "augmented manifest_jsonb's manifest_hash is recomputed so the "
            "DB self-consistency invariant ``sha256(persisted_jsonb) == "
            "manifest_hash`` continues to hold."
        ),
    )
    risk_overrides: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "REF-20 Sprint B2 R5-T6 round 2: optional risk override blob "
            "(e.g. {limits: {position_size_max_pct: 10.0}}). When supplied, "
            "server computes ``risk_config_sha256 = sha256(canonical_bytes("
            "blob))`` and OVERRIDES the client-supplied ``risk_config_sha256``. "
            "A5 acceptance fixture (PA design §5.2) registers same strategy "
            "with tight (2%) vs loose (10%) limits and observes distinct sha. "
            "Persisted into manifest_jsonb under reserved key "
            "``_replay_risk_overrides``."
        ),
    )

    @validator("symbol", "strategy")
    def _alphanumeric_underscore(cls, v: str) -> str:
        """Path-injection guard: alphanumeric + underscore only.
        防 path injection：只允許字母數字 + 底線。

        V049 ``replay.experiments`` does not use these as filesystem
        paths directly, but defense-in-depth against future audit
        emit / artifact directory naming that may interpolate them.
        V049 不直接拿 symbol/strategy 當檔路徑，但縱深防禦未來 audit
        emit / artifact dir 命名可能 interpolate 它們。
        """
        v = v.strip()
        if not v:
            raise ValueError("must be a non-empty string after strip")
        for ch in v:
            if not (ch.isalnum() or ch == "_"):
                raise ValueError(
                    "may only contain alphanumeric characters or underscore"
                )
        return v

    @validator("timeframe")
    def _timeframe_v049_allowlist(cls, v: str) -> str:
        """V049 CHECK chk_replay_experiments_timeframe 8-value allowlist.
        V049 CHECK 8 值白名單。
        """
        v = v.strip()
        if v not in V049_TIMEFRAME_ALLOWED:
            raise ValueError(
                f"timeframe must be one of {V049_TIMEFRAME_ALLOWED}; "
                f"got '{v}' (V049 CHECK chk_replay_experiments_timeframe)"
            )
        return v

    @validator("manifest_jsonb")
    def _no_reserved_prefix_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        """REF-20 Sprint A R2 round 2 fix M-4: reject keys with '_' prefix.
        REF-20 Sprint A R2 round 2 fix M-4：拒 '_' 前綴 key。

        Reserved for server-controlled metadata. Historically (R2 round 1)
        the server injected ``_idempotency_key`` into manifest_jsonb which
        broke the ``sha256(manifest_jsonb) == manifest_hash`` invariant
        (E2 review H-1). Round 2 moved that marker to an in-memory cache;
        this validator pre-emptively rejects any client-supplied ``_*``
        key so future server-side metadata reservations cannot collide.
        保留給 server 控制的 metadata。歷史上（R2 round 1）server 注入
        ``_idempotency_key`` 進 manifest_jsonb 破壞 ``sha256(manifest_jsonb)
        == manifest_hash`` 不變式（E2 review H-1）。Round 2 把該 marker
        改成記憶體 cache；此 validator 預先拒 client 提交的 ``_*`` key
        防未來 server-side metadata 預留衝突。

        Order matters: this validator runs BEFORE ``_size_cap`` so that
        an oversized payload containing a reserved prefix key surfaces
        the more security-relevant ValueError first.
        順序：本 validator 先於 ``_size_cap``，含禁用前綴又超大的 payload
        會先返回安全相關錯誤。
        """
        reserved = [k for k in v.keys() if isinstance(k, str) and k.startswith("_")]
        if reserved:
            raise ValueError(
                "manifest_jsonb keys with '_' prefix are reserved for "
                "server-controlled metadata; found: "
                + ", ".join(sorted(reserved))
            )
        return v

    @validator("manifest_jsonb")
    def _size_cap(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Canonical-form size cap (256 KB) on manifest_jsonb body.
        manifest_jsonb body 的 canonical-form 大小上限（256 KB）。

        Caps are computed on the SAME canonical bytes used for
        ``manifest_hash`` — Sprint 1 F1 retrofit invariant
        (sort_keys=True / separators=(',', ':') / ensure_ascii=False)
        — so any client whose manifest hashes successfully also fits
        within cap (no byte-count drift between hash and cap path).
        cap 計算與 ``manifest_hash`` 用的 canonical bytes 相同 — Sprint 1
        F1 retrofit invariant — 任何 hash 成功的 manifest 都在 cap 內。
        """
        try:
            canonical = json.dumps(
                v,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"manifest_jsonb is not JSON-serializable: {type(exc).__name__}"
            ) from exc
        if len(canonical) > MANIFEST_JSONB_MAX_BYTES:
            raise ValueError(
                f"manifest_jsonb canonical bytes "
                f"{len(canonical)} > {MANIFEST_JSONB_MAX_BYTES}-byte cap "
                f"(R2-T1 size limit)"
            )
        return v

    @validator("data_window_end")
    def _window_order(cls, v: datetime, values: dict[str, Any]) -> datetime:
        """V049 CHECK chk_replay_experiments_window_order: end > start.
        V049 CHECK：window 結束 > 開始。
        """
        start = values.get("data_window_start")
        if start is not None and v <= start:
            raise ValueError(
                "data_window_end must be strictly greater than "
                "data_window_start (V049 CHECK chk_replay_experiments_window_order)"
            )
        return v


# ─── Helpers / 輔助函式 ────────────────────────────────────────────────


def compute_manifest_canonical_bytes(manifest_jsonb: dict[str, Any]) -> bytes:
    """Canonicalize manifest_jsonb to bytes per the cross-language contract.
    依跨語言契約把 manifest_jsonb 規範化為 bytes。

    Three settings are load-bearing (Sprint 1 F1 retrofit invariant):
      * ``sort_keys=True``        — alphabetical keys ↔ Rust BTreeMap default.
      * ``separators=(',', ':')`` — compact ↔ Rust serde_json compact default.
      * ``ensure_ascii=False``    — raw UTF-8 ↔ Rust serde_json never escapes.

    三項設定缺一不可（Sprint 1 F1 retrofit 不變量）。

    Mirrors: ``replay/manifest_signer.py::sign`` (which expects caller-
    canonicalized bytes) + ``replay/route_helpers.py::write_manifest_fixture``
    (disk-fixture write). Both Python paths and the Rust
    ``replay/manifest_signer.rs::canonical_body_for_signing`` path consume
    the same shape — keeping all three writers using identical kwargs is
    the cheapest invariant.
    鏡像 ``replay/manifest_signer.py::sign`` + ``write_manifest_fixture``；
    Rust ``replay/manifest_signer.rs::canonical_body_for_signing`` 接同
    shape；三條 writer 統一 kwargs 是最便宜的不變量。
    """
    return json.dumps(
        manifest_jsonb,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def compute_manifest_hash(manifest_jsonb: dict[str, Any]) -> str:
    """Compute SHA-256 hex over canonical manifest_jsonb bytes.
    對 canonical manifest_jsonb bytes 計算 SHA-256 hex。

    Returns 64 lowercase hex char (`hashlib.sha256().hexdigest()`).
    回傳 64 小寫 hex 字（``hashlib.sha256().hexdigest()``）。
    """
    return hashlib.sha256(compute_manifest_canonical_bytes(manifest_jsonb)).hexdigest()


# ─── Sprint B2 R5-T6 — config-sha lookup / 配置 sha 查詢 ───────────────


def lookup_replay_config_sha256(
    cur: Any, experiment_id: str
) -> Tuple[Optional[str], Optional[str]]:
    """Read back ``(strategy_config_sha256, risk_config_sha256)`` from V049.
    從 V049 取回 ``(strategy_config_sha256, risk_config_sha256)``。

    REF-20 Sprint B2 R5-T6 (per dispatch §11.1).

    Sprint A R2 register handler INSERTs both columns (V049 22-col contract
    lines 775+802 in this file). R5-T6 adds the read-back helper so that:
      1. R5-T4 CLI can SELECT the canonical sha hashes when constructing
         the in-memory `StrategyParamsConfig` / `RiskConfig` (Sprint C R6
         will widen to actual config blob retrieval — R5-T6 lands the read
         path so R6 only needs to add a JSONB blob column reader).
      2. Audit chain reconstruction tools can verify that a registered
         experiment's manifest still has matching strategy/risk config sha
         pre-replay (defense against post-register config swap).

    Sprint A R2 register handler 已 INSERT 兩 column（V049 22-col 契約本檔
    line 775+802）。R5-T6 加 read-back helper 使：
      1. R5-T4 CLI 在構造 in-memory `StrategyParamsConfig` / `RiskConfig` 時
         可 SELECT canonical sha；Sprint C R6 將擴為實際 config blob 取回 —
         R5-T6 僅落 read path，R6 只需加 JSONB blob column reader。
      2. 審計鏈重建工具可驗已註冊 experiment 的 manifest 仍有匹配 strategy/
         risk config sha（防 post-register config swap）。

    Args:
        cur: psycopg2-style cursor inside caller's transaction.
        experiment_id: V049 row's experiment_id (uuid text or uuid object).

    Returns / 回傳:
        Tuple ``(strategy_sha, risk_sha)``; ``(None, None)`` if experiment
        not found. Both fields are NOT NULL in V049 — once a row exists,
        both sha values are guaranteed populated by the R2 register handler.
        Tuple ``(strategy_sha, risk_sha)``；experiment 找不到時回 ``(None, None)``。
        V049 兩 column 皆 NOT NULL — row 一旦存在，R2 register handler 保
        兩 sha 必填。

    SAFETY / 不變量：
        - parameterised SQL（無字串拼接）。
        - 僅 SELECT，無 mutation；caller 不需 commit。
        - V049 column 名永久（PA design §6.1 + §5 cross-language contract）。
    """
    cur.execute(
        """
        SELECT strategy_config_sha256, risk_config_sha256
          FROM replay.experiments
         WHERE experiment_id = %s::uuid
         LIMIT 1;
        """,
        (str(experiment_id),),
    )
    row = cur.fetchone()
    if row is None:
        return None, None
    strategy_sha = row[0]
    risk_sha = row[1]
    # Defense-in-depth: V049 NOT NULL constraint guarantees both fields, but
    # if a future schema migration relaxes this, treat empty/NULL as missing
    # so callers can fail loud on partial state.
    # 縱深防禦：V049 NOT NULL 保證雙欄；若未來 migration 放寬，視 NULL/空
    # 為 missing 使 caller fail loud。
    if not strategy_sha or not risk_sha:
        logger.warning(
            "lookup_replay_config_sha256: experiment_id=%s has partial sha "
            "(strategy=%r risk=%r) — V049 NOT NULL invariant violated?",
            experiment_id, strategy_sha, risk_sha,
        )
        return strategy_sha or None, risk_sha or None
    return str(strategy_sha), str(risk_sha)


# ─── Sprint B2 R5-T6 round 2 — config blob lookup / 配置 blob 讀取 ─────


def lookup_replay_config_blob(
    cur: Any, experiment_id: str
) -> dict[str, Optional[dict[str, Any]]]:
    """Read back ``(strategy_params, risk_overrides)`` blobs from V049.
    從 V049 取回 ``(strategy_params, risk_overrides)`` blobs。

    REF-20 Sprint B2 R5-T6 round 2 (per dispatch §Fix 1.5).

    Sprint B2 R5-T6 round 2 register handler injects optional blobs into
    ``replay.experiments.manifest_jsonb`` under reserved keys
    ``_replay_strategy_params`` / ``_replay_risk_overrides``. This helper
    extracts them so:
      1. R5-T7 acceptance fixture builders can SELECT round-tripped blobs
         to assert that A4/A5 parameter delta produced distinct sha values
         AND that the persisted blobs match what was registered.
      2. ``replay/route_helpers.py::build_default_manifest_payload`` (later
         Sprint B work) can copy blobs from V049 into the disk manifest
         fixture so the Rust replay_runner's R5-T4 round 2 manifest schema
         (``ReplayManifest.strategy_params`` / ``risk_overrides``) sees them.

    Sprint B2 R5-T6 round 2 register handler 將選用 blob 注入
    ``replay.experiments.manifest_jsonb`` 的保留 key
    （``_replay_strategy_params`` / ``_replay_risk_overrides``）。Helper 取回：
      1. R5-T7 acceptance fixture 可 SELECT round-trip 的 blob 驗 A4/A5 參數
         delta 確實產生不同 sha + 持久化 blob 與 register 時一致。
      2. ``build_default_manifest_payload`` 後續 Sprint 可從 V049 copy blob 進
         disk manifest fixture，使 Rust runner R5-T4 round 2 manifest schema
         （``ReplayManifest.strategy_params`` / ``risk_overrides``）看得到。

    Args:
        cur: psycopg2-style cursor inside caller's transaction.
        experiment_id: V049 row's experiment_id (uuid text or uuid object).

    Returns / 回傳:
        Dict ``{"strategy_params": Optional[dict], "risk_overrides":
        Optional[dict]}``. Both keys present in returned dict; per-key value
        is ``None`` when (a) experiment not found, (b) manifest_jsonb has no
        such reserved key, or (c) reserved key value is not a dict (defense:
        won't surface non-dict polluted values to caller).
        回傳兩 key 永遠出現；值為 ``None`` 時代表（a）找不到 experiment、
        （b）manifest_jsonb 無此保留 key、（c）保留 key 值非 dict（防禦性
        不把污染值往外送）。

    SAFETY / 不變量：
        - parameterised SQL（無字串拼接）。
        - 僅 SELECT，無 mutation；caller 不需 commit。
        - psycopg2 ``jsonb`` 自動解碼為 Python dict（不需 ``json.loads``）；
          若回傳是 str（極舊 driver fallback），手動 ``json.loads`` 防禦。
    """
    cur.execute(
        """
        SELECT manifest_jsonb
          FROM replay.experiments
         WHERE experiment_id = %s::uuid
         LIMIT 1;
        """,
        (str(experiment_id),),
    )
    row = cur.fetchone()
    none_pair: dict[str, Optional[dict[str, Any]]] = {
        "strategy_params": None,
        "risk_overrides": None,
    }
    if row is None:
        return none_pair
    raw = row[0]
    if raw is None:
        return none_pair
    # psycopg2 returns jsonb as Python dict by default; older drivers may
    # surface a JSON-encoded str. Decode-or-passthrough defensively.
    # psycopg2 預設 jsonb→dict；舊版 driver 可能給字串，必要時 decode。
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(
                "lookup_replay_config_blob: experiment_id=%s manifest_jsonb "
                "bytes not utf-8 decodable",
                experiment_id,
            )
            return none_pair
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning(
                "lookup_replay_config_blob: experiment_id=%s manifest_jsonb "
                "str payload not JSON parseable",
                experiment_id,
            )
            return none_pair
    if not isinstance(raw, dict):
        logger.warning(
            "lookup_replay_config_blob: experiment_id=%s manifest_jsonb "
            "is not dict (got %s)",
            experiment_id, type(raw).__name__,
        )
        return none_pair
    # Defensive: only return when value is dict; tolerate missing keys.
    # 防禦：只回 dict 值；無 key 視為未注入。
    strat = raw.get("_replay_strategy_params")
    risk = raw.get("_replay_risk_overrides")
    return {
        "strategy_params": strat if isinstance(strat, dict) else None,
        "risk_overrides": risk if isinstance(risk, dict) else None,
    }


def _resolve_runtime_environment() -> str:
    """Determine V049 runtime_environment value from env (CHECK 2-value enum).
    從 env 解析 V049 runtime_environment（CHECK 2 值 enum）。

    Default ``linux_trade_core`` for prod/CI. Operator can override via
    ``OPENCLAW_REPLAY_RUNTIME_ENV`` env (matches replay_routes.py /run
    handler INSERT pattern at line 396 + 402).
    預設 ``linux_trade_core``；operator 可由 ``OPENCLAW_REPLAY_RUNTIME_ENV``
    env 覆寫（與 replay_routes.py /run handler INSERT pattern 一致）。
    """
    raw = os.environ.get("OPENCLAW_REPLAY_RUNTIME_ENV", "").strip()
    if raw in V049_RUNTIME_ENV_ALLOWED:
        return raw
    return "linux_trade_core"


def _try_acquire_register_idempotency_lock(
    cur: Any, actor_id: str, idempotency_key: str
) -> bool:
    """Try to acquire xact-scoped advisory lock for register idempotency.
    為 register idempotency 嘗試取 xact-scoped advisory lock。

    Pattern note: V049 has no UNIQUE INDEX on
    (idempotency_key, created_by) — so the natural ON CONFLICT
    clause is unavailable (R2-T1 spec note 7). We use advisory lock
    keyed on ``register_idem:<actor_id>:<idempotency_key>`` to serialize
    register attempts of the same key+actor; inside the lock we
    SELECT-then-INSERT instead of relying on UNIQUE INDEX.
    pattern 註：V049 無 (idempotency_key, created_by) UNIQUE INDEX → 不能
    用 ON CONFLICT；此處用 advisory lock 鎖 actor+key 串行化 register。

    Returns / 回傳:
        True if lock acquired (caller proceeds with SELECT-then-INSERT);
        False if another concurrent register holds the lock — caller
        should immediately retry SELECT (the holder's INSERT will have
        committed by the time we wake up since lock is xact-scoped).
    """
    lock_key = (
        f"{ADVISORY_LOCK_REGISTER_IDEMPOTENCY_PREFIX}{actor_id}:{idempotency_key}"
    )
    cur.execute(
        "SELECT pg_try_advisory_xact_lock(hashtext(%s));",
        (lock_key,),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def _cache_lookup_idempotency(
    actor_id: str, idempotency_key: str
) -> Optional[dict[str, Any]]:
    """Look up cached register result for (actor_id, idempotency_key).
    依 (actor_id, idempotency_key) 查 cache 內的 register 結果。

    REF-20 Sprint A R2 round 2 fix H-1: replaces the JSONB ``->>``
    SELECT path which depended on a server-injected ``_idempotency_key``
    inside ``manifest_jsonb`` (broke the sha256(manifest_jsonb) ==
    manifest_hash invariant per E2 review H-1).
    REF-20 Sprint A R2 round 2 fix H-1：取代依賴 ``manifest_jsonb`` 內
    server 注入 ``_idempotency_key`` 的 JSONB SELECT 路徑（破不變式）。

    Returns / 回傳:
        Cached entry dict ``{"experiment_id", "manifest_hash",
        "status", "created_at"}`` if found; ``None`` else.

    Thread-safe via ``_REGISTER_IDEM_CACHE_THREAD_LOCK`` (caller already
    runs inside ``asyncio.to_thread`` so a thread-level Lock is the
    correct primitive — async tasks call this through to_thread).
    執行緒安全由 ``_REGISTER_IDEM_CACHE_THREAD_LOCK`` 保證（caller 在
    ``asyncio.to_thread`` 內，用 thread-level Lock 是正確原語）。
    """
    cache_key = (actor_id, idempotency_key)
    with _REGISTER_IDEM_CACHE_THREAD_LOCK:
        entry = _REGISTER_IDEM_CACHE.get(cache_key)
        if entry is None:
            return None
        # Return shallow copy so caller mutations don't leak into cache.
        # 回淺拷貝防 caller mutation 滲入 cache。
        return dict(entry)


def _cache_set_idempotency(
    actor_id: str, idempotency_key: str, entry: dict[str, Any]
) -> None:
    """Store register result for (actor_id, idempotency_key) in cache.
    把 register 結果存入 (actor_id, idempotency_key) cache。
    """
    cache_key = (actor_id, idempotency_key)
    with _REGISTER_IDEM_CACHE_THREAD_LOCK:
        _REGISTER_IDEM_CACHE[cache_key] = dict(entry)


def _cache_clear_for_test() -> None:
    """Clear in-memory idempotency cache (TEST-ONLY hermetic helper).
    清空 in-memory idempotency cache（**僅測試用**）。
    """
    with _REGISTER_IDEM_CACHE_THREAD_LOCK:
        _REGISTER_IDEM_CACHE.clear()


def _verify_signature_or_raise(
    *,
    manifest_canonical: bytes,
    manifest_hash_hex: str,
    signature_hex: str,
    signature_key_ref: Optional[str],
    manifest_signer_module: Any,
) -> None:
    """Verify HMAC signature against the canonical manifest bytes.
    對 canonical manifest bytes 驗 HMAC 簽名。

    R2-T1 scope: dev/test path uses ``OPENCLAW_REPLAY_VERIFY_TEST_KEY``
    env — same env as ``post_manifest_verify`` route. The R2-T3 retrofit
    (manifest verify production path) replaces with secrets-file load.
    For now the register endpoint mirrors the same fallback logic to
    keep R2-T1 scope tight (no scope creep into R2-T3 territory).
    R2-T1 範圍：dev/test 用 ``OPENCLAW_REPLAY_VERIFY_TEST_KEY`` env —
    與 ``post_manifest_verify`` route 同 env。R2-T3 retrofit 換 secrets
    file。本 R2-T1 沿用同 fallback 守住範圍。

    Raises / 觸發例外:
        ValueError with caller-readable reason on verify failure.
    """
    test_key_hex = os.environ.get("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "").strip()
    if not test_key_hex:
        raise ValueError(
            "register_signature_verify_unavailable: "
            "OPENCLAW_REPLAY_VERIFY_TEST_KEY not set (dev/test path); "
            "production secrets-file path lands in R2-T3"
        )
    try:
        key_bytes = bytes.fromhex(test_key_hex)
    except ValueError as exc:
        raise ValueError(
            f"register_signature_verify_bad_test_key: hex decode failed: {exc}"
        ) from exc

    fingerprint = signature_key_ref or "register_test_fp"
    archive = manifest_signer_module.InMemoryKeyArchive()
    # InMemoryKeyArchive.insert(fingerprint, status) — KeyArchive ABC only
    # tracks status by fingerprint; the raw key bytes live with the signer
    # instance via ``from_bytes_for_test`` (mirrors Rust archive trait).
    # InMemoryKeyArchive.insert 只記 (fingerprint, status)；raw key bytes
    # 由 signer 自身透過 ``from_bytes_for_test`` 持有（鏡像 Rust trait）。
    archive.insert(fingerprint, manifest_signer_module.KeyStatus.ACTIVE)
    signer = manifest_signer_module.ManifestSigner.from_bytes_for_test(
        key_bytes, fingerprint,
    )
    # ManifestSigner.verify raises ValueError(SignatureFailMode.X.value) on
    # any mismatch (signature / hash / key missing / key expired).
    signer.verify(
        manifest_canonical,
        manifest_hash_hex,
        signature_hex,
        fingerprint,
        archive,
    )


# ─── Public helper: register_experiment / 公開 API：register_experiment ─


def register_experiment(
    cur: Any,
    actor: Any,
    body: ReplayExperimentRegisterRequest,
    *,
    manifest_signer_module: Any = None,
) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
    """Register a manifest in V049 ``replay.experiments``.
    在 V049 ``replay.experiments`` 註冊 manifest。

    Wave R2-T1 (2026-05-04). Caller is the replay_routes ``/experiments/
    register`` route handler running inside ``asyncio.to_thread`` over a
    PG transaction owned by the caller (txn lifecycle outside this
    function — caller commits/rollbacks).

    R2-T1 流程（caller 持 PG transaction）：
      1. 計 ``experiment_id = uuid.uuid4()``。
      2. 計 ``manifest_canonical_bytes`` + ``manifest_hash``。
      3. 若 ``signature_hex`` 提供 → verify（fail → ValueError）。
      4. ``idempotency_key`` 提供 → in-memory cache lookup（H-1）+ hash
         mismatch detection（H-2）+ PG advisory lock（cross-xact race
         保險）。
      5. INSERT V049 22-col 契約。Round 2 fix M-3：linux_trade_core
         缺 ``OPENCLAW_ENGINE_BINARY_SHA`` env → 503 fail-closed。

    Args:
        cur: PG cursor (caller-owned xact, statement_timeout already SET).
        actor: ``base.AuthenticatedActor`` — uses ``actor.actor_id``.
        body: validated ``ReplayExperimentRegisterRequest``.
        manifest_signer_module: ``replay.manifest_signer`` module
            (caller injects so test can swap; default None disables
            signature verify and forces caller to pass module to verify).

    Returns / 回傳:
        ``(result_dict, None)`` on success — dict has ``experiment_id``,
        ``manifest_hash``, ``status``, ``created_at``, ``idempotency_hit``;
        ``(None, err_str)`` on failure — err is one of:
        - ``"register_signature_verify_unavailable"``
        - ``"register_signature_verify_bad_test_key:..."``
        - ``"manifest_hash_mismatch"`` / ``"signature_mismatch"`` /
          ``"key_missing"`` / ``"key_expired"`` (from
          ``ManifestSigner.verify`` ValueError args[0]).
        - ``"idempotency_replay_attack"`` (R2 round 2 H-2): same
          idempotency_key + same actor + DIFFERENT manifest_hash.
        - ``"engine_binary_sha_not_provisioned"`` (R2 round 2 M-3):
          linux_trade_core runtime + no ``OPENCLAW_ENGINE_BINARY_SHA``.
    """
    actor_id = str(actor.actor_id)

    # Step 1: derive experiment_id.
    # 步驟 1：衍生 experiment_id。
    experiment_id = uuid.uuid4()

    # ── REF-20 Sprint B2 R5-T6 round 2 — config blob server-side wiring ──
    # ── REF-20 Sprint B2 R5-T6 round 2 — 配置 blob 伺服端接線 ─────────
    #
    # When ``strategy_params`` / ``risk_overrides`` are supplied at register
    # time (PA design §5.1 + §5.2 acceptance fixture pattern), server:
    #   (a) computes the canonical sha256 of each blob using the SAME
    #       canonical-bytes contract as ``manifest_hash`` (Sprint 1 F1
    #       retrofit invariant: sort_keys+separators+ensure_ascii=False)
    #       and OVERRIDES the client-supplied
    #       ``strategy_config_sha256`` / ``risk_config_sha256``
    #       (the client-supplied value becomes a placeholder in this path).
    #   (b) injects the raw JSON blobs into a COPY of ``manifest_jsonb``
    #       under reserved keys ``_replay_strategy_params`` /
    #       ``_replay_risk_overrides`` so the Rust replay_runner can read
    #       them out of the disk fixture (R5-T4 Round 2 manifest schema).
    #   (c) recomputes ``manifest_hash`` from the AUGMENTED manifest_jsonb
    #       so the DB self-consistency invariant ``sha256(persisted_jsonb)
    #       == manifest_hash`` continues to hold (E2 review H-1).
    #
    # When neither blob is supplied (legacy path / R5-T6 round 1 callers),
    # the existing behaviour is preserved exactly: client-supplied sha
    # values + unmodified manifest_jsonb + xlang signature invariant intact.
    # The 13/13 cross-language fixture set has neither blob field present so
    # canonical_bytes is unchanged → 13/13 PASS.
    #
    # SAFETY / 不變量：
    #   - 注入路徑只在 server 端執行（M-4 client-prefix rejector 已過）。
    #   - manifest_canonical 與 manifest_hash 的 byte-equality 由
    #     compute_manifest_canonical_bytes 保證（與 Rust serde_json compact
    #     對齊）；augmented body 的 hash 重新計算，invariant 保持。
    #   - 若 client 同時提供 ``signature_hex``：簽名是針對 ORIGINAL body
    #     計算的，server 注入後 hash 會變 → signature 將驗證失敗。Round 2
    #     範圍不支援 signed-with-blob 同時使用；測試路徑不簽名（R5-T7
    #     fixture 路徑同步走 unsigned path）。Sprint C R6 fee calibration
    #     會處理 signed+blob 的雙路徑契約。
    # 當 ``strategy_params`` / ``risk_overrides`` 兩者均不提供（legacy /
    # R5-T6 round 1 caller）時，行為與 round 1 完全一致：用 client 提供的
    # sha + 不動 manifest_jsonb + 跨語言 signature invariant 不破。
    # 13/13 跨語言 fixture 兩 blob 欄位皆不在 → canonical_bytes 不變 → 不退。
    manifest_to_persist: dict[str, Any] = body.manifest_jsonb
    effective_strategy_sha = body.strategy_config_sha256
    effective_risk_sha = body.risk_config_sha256

    if body.strategy_params is not None or body.risk_overrides is not None:
        # Shallow copy so caller's body.manifest_jsonb is not mutated.
        # 淺拷貝避免動到 caller 的 body.manifest_jsonb。
        manifest_to_persist = dict(body.manifest_jsonb)
        if body.strategy_params is not None:
            strategy_canonical = compute_manifest_canonical_bytes(
                body.strategy_params
            )
            effective_strategy_sha = hashlib.sha256(
                strategy_canonical
            ).hexdigest()
            manifest_to_persist["_replay_strategy_params"] = body.strategy_params
        if body.risk_overrides is not None:
            risk_canonical = compute_manifest_canonical_bytes(
                body.risk_overrides
            )
            effective_risk_sha = hashlib.sha256(risk_canonical).hexdigest()
            manifest_to_persist["_replay_risk_overrides"] = body.risk_overrides

    # Step 2: canonical bytes + manifest hash (over the AUGMENTED body if
    # blobs were injected; legacy path: unmodified body).
    # 步驟 2：canonical bytes + manifest hash（注入後的 augmented body 或原 body）。
    manifest_canonical = compute_manifest_canonical_bytes(manifest_to_persist)
    manifest_hash_hex = hashlib.sha256(manifest_canonical).hexdigest()

    # Step 3: signature verify (only if client supplied).
    # 步驟 3：signature 驗（client 有提供才驗）。
    if body.signature_hex is not None:
        if manifest_signer_module is None:
            return None, "register_signature_verify_module_missing"
        try:
            _verify_signature_or_raise(
                manifest_canonical=manifest_canonical,
                manifest_hash_hex=manifest_hash_hex,
                signature_hex=body.signature_hex,
                signature_key_ref=body.signature_key_ref,
                manifest_signer_module=manifest_signer_module,
            )
        except ValueError as exc:
            return None, str(exc)

    # Step 4: idempotency cache lookup (H-1) + hash-mismatch guard (H-2).
    # 步驟 4：idempotency cache 查找（H-1）+ hash 不符守門（H-2）。
    #
    # R2 round 2 fix H-1: replaces SELECT WHERE manifest_jsonb->>'_idempotency_key'
    # with in-memory cache (the JSONB injection broke sha256 invariant).
    # R2 round 2 fix H-2: cache hit but DIFFERENT manifest_hash → 409
    # ``idempotency_replay_attack``（攻擊者用同 key 改 body 想 silently 拿
    # existing experiment）。
    if body.idempotency_key:
        cached = _cache_lookup_idempotency(actor_id, body.idempotency_key)
        if cached is not None:
            cached_hash = cached.get("manifest_hash")
            if cached_hash is not None and cached_hash != manifest_hash_hex:
                # H-2: same idempotency_key + same actor + DIFFERENT manifest →
                # treat as replay attack; return 409 (caller maps via
                # ``map_register_error_to_http``).
                # H-2：同 key+actor 但 manifest 不同 → 視為 replay attack。
                logger.warning(
                    "register_experiment: idempotency_replay_attack "
                    "(actor=%s key=%s cached_hash=%s new_hash=%s)",
                    actor_id, body.idempotency_key,
                    cached_hash, manifest_hash_hex,
                )
                return None, "idempotency_replay_attack"
            # Cache hit + matching hash → return cached experiment_id.
            # cache hit + hash 對 → 直接回 cached 結果。
            return (
                {
                    "experiment_id": cached["experiment_id"],
                    "manifest_hash": cached.get("manifest_hash"),
                    "status": cached.get("status", V049_STATUS_CREATED),
                    "created_at": cached.get("created_at"),
                    "idempotency_hit": True,
                },
                None,
            )
        # Cache miss → acquire PG advisory xact lock for cross-process
        # serialization, then proceed to INSERT. Lock auto-releases on
        # commit/rollback. Cross-process duplicate in cache-miss + race is
        # acknowledged trade-off (per H-1 module-level comment).
        # cache miss → 取 PG advisory xact lock 跨 process 序列化，然後 INSERT。
        # cache miss + race 跨 process 可能 INSERT 重複 row 是 H-1 取捨。
        lock_acquired = _try_acquire_register_idempotency_lock(
            cur, actor_id, body.idempotency_key,
        )
        if not lock_acquired:
            logger.warning(
                "register_experiment: advisory lock contended (actor=%s key=%s); "
                "proceeding with INSERT under best-effort serialization",
                actor_id, body.idempotency_key,
            )

    # Step 5: V049 22-col contract INSERT.
    # 步驟 5：V049 22-col 契約 INSERT。
    runtime_environment = _resolve_runtime_environment()
    git_sha = os.environ.get("OPENCLAW_GIT_SHA", "").strip() or None
    engine_binary_sha = (
        os.environ.get("OPENCLAW_ENGINE_BINARY_SHA", "").strip() or None
    )
    # R2 round 2 fix M-3: linux_trade_core REQUIRES OPENCLAW_ENGINE_BINARY_SHA
    # env. Round 1 silently fell back to ``"register_pending_engine_sha"``
    # sentinel which polluted DB rows for supply-chain audit. Round 2 fails
    # closed with 503 instead so operator must export the real sha before
    # production deploys can register manifests.
    # R2 round 2 fix M-3：linux_trade_core 必有 OPENCLAW_ENGINE_BINARY_SHA env。
    # Round 1 用 sentinel 過 CHECK 但污染 supply-chain audit；Round 2 改
    # 503 fail-closed，operator 必先 export 真 sha 才能註冊。
    if runtime_environment == "linux_trade_core" and not engine_binary_sha:
        return None, "engine_binary_sha_not_provisioned"

    # R2 round 2 fix H-1: do NOT inject ``_idempotency_key`` into manifest_jsonb.
    # The persisted manifest_jsonb must be byte-equal to the (possibly
    # blob-augmented per Sprint B2 R5-T6 round 2) input so the
    # ``sha256(persisted_jsonb) == manifest_hash`` invariant continues to hold.
    # The augmentation (``_replay_strategy_params`` / ``_replay_risk_overrides``)
    # is performed BEFORE manifest_canonical/manifest_hash computation above
    # (see Sprint B2 R5-T6 round 2 block) so this INSERT writes a matching
    # pair: persisted manifest_jsonb bytes ↔ manifest_hash invariant intact.
    # R2 round 2 fix H-1：不注入 ``_idempotency_key`` 進 manifest_jsonb；持
    # 久化的 manifest_jsonb 必與（可能由 Sprint B2 R5-T6 round 2 注入 blob）
    # input byte-equal 以維持 ``sha256(persisted_jsonb) == manifest_hash``
    # 不變式。注入發生在前面 manifest_canonical/manifest_hash 計算之前，
    # 故 INSERT 寫入時 persisted body bytes 與 hash 仍是同對。

    cur.execute(
        """
        INSERT INTO replay.experiments (
            experiment_id, parent_experiment_id, created_at, created_by,
            runtime_environment, git_sha, engine_binary_sha,
            strategy_config_sha256, risk_config_sha256,
            timeframe, data_tier, execution_confidence,
            calibration_train_window_start, calibration_train_window_end,
            oos_label_window_start, oos_label_window_end,
            candidate_window_start, candidate_window_end,
            oos_embargo_seconds, total_candidates_K,
            manifest_jsonb, manifest_hash, manifest_signature,
            signature_key_ref, expires_at, status, output_policy_jsonb,
            half_life_days, embargo_days
        ) VALUES (
            %s::uuid, NULL, NOW(), %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            NULL, NULL,
            %s, %s,
            NULL, NULL,
            NULL, NULL,
            %s::jsonb, %s, %s,
            %s, NULL, %s, NULL,
            %s, %s
        )
        RETURNING experiment_id::text, created_at;
        """,
        (
            str(experiment_id), actor_id,
            runtime_environment, git_sha, engine_binary_sha,
            # REF-20 Sprint B2 R5-T6 round 2: prefer server-computed sha
            # when ``strategy_params`` / ``risk_overrides`` were supplied;
            # else fall back to client-supplied (legacy path).
            # 優先使用 server 算的 sha；無 blob 時退回 client 提供值。
            effective_strategy_sha, effective_risk_sha,
            body.timeframe, body.data_tier, V049_EXECUTION_CONFIDENCE_DEFAULT,
            body.data_window_start, body.data_window_end,
            json.dumps(manifest_to_persist, sort_keys=True, ensure_ascii=False),
            bytes.fromhex(manifest_hash_hex),
            bytes.fromhex(body.signature_hex) if body.signature_hex else None,
            body.signature_key_ref,
            V049_STATUS_CREATED,
            body.half_life_days, body.embargo_days,
        ),
    )
    inserted = cur.fetchone()
    if inserted is None:
        return None, "register_insert_no_row_returned"
    inserted_id, inserted_created_at = inserted

    created_at_iso = (
        inserted_created_at.isoformat()
        if hasattr(inserted_created_at, "isoformat")
        else str(inserted_created_at)
    )

    # Populate cache for idempotent future requests (H-1 invariant: cache
    # holds the manifest_hash so H-2 mismatch detection works on retry).
    # 填 cache 供未來 idempotent 請求（H-1：cache 含 manifest_hash 供 H-2 檢測）。
    if body.idempotency_key:
        _cache_set_idempotency(
            actor_id,
            body.idempotency_key,
            {
                "experiment_id": inserted_id,
                "manifest_hash": manifest_hash_hex,
                "status": V049_STATUS_CREATED,
                "created_at": created_at_iso,
            },
        )

    return (
        {
            "experiment_id": inserted_id,
            "manifest_hash": manifest_hash_hex,
            "status": V049_STATUS_CREATED,
            "created_at": created_at_iso,
            "idempotency_hit": False,
        },
        None,
    )


# ─── PG transaction wrapper / PG transaction 包裝 ────────────────────


def run_register_in_pg_xact(
    get_pg_conn_fn: Any,
    actor: Any,
    body: ReplayExperimentRegisterRequest,
    *,
    statement_timeout_ms: int = 2_000,
    manifest_signer_module: Any = None,
) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
    """Run register_experiment inside a PG transaction (commit on success).
    在 PG transaction 內跑 register_experiment（成功 commit）。

    REF-20 Sprint A R2-T1 (2026-05-04). Caller is the replay_routes
    ``post_experiment_register`` handler via ``asyncio.to_thread``.
    Owns xact lifecycle (commit on err is None, rollback otherwise);
    the registry helper itself is txn-agnostic so unit tests can drive
    it with a mock cursor without going through this wrapper.
    REF-20 Sprint A R2-T1：caller 透過 ``asyncio.to_thread`` 跑；本
    helper 持 xact 生命周期；register_experiment 本身 txn-agnostic 便
    於 mock cursor 測。

    Args:
        get_pg_conn_fn: Caller-provided context-manager factory
            (typically ``app.db_pool.get_pg_conn``).
        actor: ``base.AuthenticatedActor`` (uses ``actor.actor_id``).
        body: validated ``ReplayExperimentRegisterRequest``.
        statement_timeout_ms: Per-stmt timeout (default 2000 = 2s).
        manifest_signer_module: ``replay.manifest_signer`` module for
            optional signature verify.

    Returns / 回傳:
        (result_dict, None) on success; (None, err_str) on failure.
        err_str ∈ {"pg_unavailable", "pg_error:<ExcName>",
        register_experiment err codes}.
    """
    with get_pg_conn_fn() as conn:
        if conn is None:
            return None, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))
            result, err = register_experiment(
                cur, actor, body, manifest_signer_module=manifest_signer_module,
            )
            if err is not None:
                conn.rollback()
                return None, err
            conn.commit()
            return result, None
        except Exception as exc:  # noqa: BLE001 — fail-closed PG envelope
            logger.warning("run_register_in_pg_xact: %s", exc)
            try:
                conn.rollback()
            except Exception:
                pass
            return None, f"pg_error:{type(exc).__name__}"


# ─── Error → HTTP mapping helper / 錯誤碼到 HTTP 對映 ─────────────────


def map_register_error_to_http(err: Optional[str]) -> Optional[Tuple[int, dict[str, Any]]]:
    """Map register_experiment error string → (status_code, detail dict).
    把 register_experiment 錯誤碼對到 (status_code, detail dict)。

    Returns / 回傳:
        ``None`` if ``err is None`` (success — no HTTP exception).
        ``(status, detail)`` otherwise; caller raises ``HTTPException``.
    """
    if err is None:
        return None
    if err == "pg_unavailable":
        return 503, {
            "reason_codes": ["replay_pg_unavailable"],
            "message": "PG unavailable; cannot register manifest",
        }
    if err.startswith("register_signature_verify_unavailable"):
        return 400, {
            "reason_codes": ["replay_register_signature_verify_unavailable"],
            "message": err,
        }
    if err in ("manifest_hash_mismatch", "signature_mismatch",
               "key_missing", "key_expired"):
        return 400, {
            "reason_codes": [f"replay_register_{err}"],
            "message": f"signature verify failed: {err}",
        }
    if err.startswith("register_signature_verify_bad_test_key"):
        return 400, {
            "reason_codes": ["replay_register_bad_test_key"],
            "message": err,
        }
    # R2 round 2 fix H-2: idempotency replay attack → 409 Conflict.
    # R2 round 2 fix H-2：idempotency replay attack → 409 Conflict。
    if err == "idempotency_replay_attack":
        return 409, {
            "reason_codes": ["replay_register_idempotency_replay_attack"],
            "message": (
                "idempotency_key reused with a different manifest_hash; "
                "either pick a new idempotency_key or resubmit the original "
                "manifest unchanged"
            ),
        }
    # R2 round 2 fix M-3: linux_trade_core requires OPENCLAW_ENGINE_BINARY_SHA.
    # R2 round 2 fix M-3：linux_trade_core 必有 OPENCLAW_ENGINE_BINARY_SHA。
    if err == "engine_binary_sha_not_provisioned":
        return 503, {
            "reason_codes": ["replay_engine_binary_sha_not_provisioned"],
            "message": (
                "linux_trade_core runtime requires OPENCLAW_ENGINE_BINARY_SHA "
                "env to be exported (supply-chain audit invariant); operator "
                "must restart engine after binary build"
            ),
        }
    return 503, {
        "reason_codes": ["replay_register_failed"],
        "message": f"register failed: {err}",
    }


__all__ = [
    "ReplayExperimentRegisterRequest",
    "register_experiment",
    "run_register_in_pg_xact",
    "compute_manifest_canonical_bytes",
    "compute_manifest_hash",
    "lookup_replay_config_sha256",  # R5-T6 read-back helper
    "lookup_replay_config_blob",  # R5-T6 round 2 read-back blob helper
    "map_register_error_to_http",
    "_cache_clear_for_test",  # R2 round 2 H-1 — TEST-ONLY hermetic helper
    "MANIFEST_JSONB_MAX_BYTES",
    "V049_DATA_TIER_REGISTER_ALLOWED",
    "V049_TIMEFRAME_ALLOWED",
    "ADVISORY_LOCK_REGISTER_IDEMPOTENCY_PREFIX",
]
