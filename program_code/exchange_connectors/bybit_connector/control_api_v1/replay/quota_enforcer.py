"""REF-20 P2a-S5 ReplayQuotaEnforcer — manifest TTL / per-actor cap / global run cap / storage cap.
REF-20 P2a-S5 ReplayQuotaEnforcer — manifest TTL / per-actor 上限 / global run 上限 / storage 上限。

MODULE_NOTE (EN):
    Wave 3 R20-P2a-S5 (workplan §4) lands the **enforcement** half of V3 §5
    "Manifest, Quota, Retention". The enforcer is a pure Python class that
    wraps a `psycopg2`-style cursor (DB-API 2.0) and applies four hard caps
    + one TTL marker before any new manifest / run / artifact materialises:

      | Limit                    | Cap   | Enforce method                                     |
      |--------------------------|-------|----------------------------------------------------|
      | per-actor active manifest| 20    | `enforce_manifest_create(actor_id)`                |
      | per-actor active run     | 1     | `enforce_run_start(actor_id)` part 1               |
      | global active run (P2/P3)| 1     | `enforce_run_start(actor_id)` part 2               |
      | env-specific storage cap | 1024 MB default (env var override) | `enforce_artifact_storage(env)` |
      | manifest TTL             | 30d   | `mark_manifest_expired(manifest_id)`               |

    All four enforcement methods raise `ReplayQuotaExceededError` (one shared
    custom exception, with `quota_kind` discriminator) on violation. They
    return a `QuotaCheckResult` on pass so the caller (P2a-S3 routes) can
    surface remaining slots in the API response.

    `ReplayQuotaEnforcer` does **NOT**:
      - couple to GovernanceHub / Decision Lease / live hot path (V3 §6.2 +
        V3 §12 #14 red-line: replay subsystem must not couple to live);
      - perform actual artifact filesystem prune (delegated to
        `helper_scripts/cron/replay_artifact_prune.py` per V3 §5 + workplan
        S5 row);
      - generate manifests / sign manifests (P2a-S2 manifest_signer owns);
      - INSERT/UPDATE manifests (P2a-S3 routes own);
      - perform DDL (V### migration territory, owned by P2b runner SQL
        fixture per V3 §6 + REF-20_RESERVATION.md note).

    Schema-absent graceful: when `replay.experiments` /
    `replay.report_artifacts` tables are not yet present (V3 §6 says these
    land via P2b runner SQL fixture in Wave 3/4), every enforcement method
    treats absence as "0 active resources" and admits the new request. This
    intentional permissiveness mirrors the cron pattern in
    `helper_scripts/cron/replay_artifact_prune.py` and lets the enforcer be
    wired into routes before the runner ships fixture SQL — flipping to
    real enforcement once tables materialise without code changes.

MODULE_NOTE (中):
    Wave 3 R20-P2a-S5（workplan §4）落地 V3 §5 「Manifest, Quota, Retention」
    的**執行**那一半。Enforcer 是純 Python class，包一個 `psycopg2` 風格
    cursor（DB-API 2.0），在新 manifest / run / artifact 物化前套用 4 條硬
    上限 + 1 條 TTL marker：

      | 限制                        | 上限  | 強制方法                                       |
      |---------------------------|-----|---------------------------------------------|
      | per-actor active manifest | 20  | `enforce_manifest_create(actor_id)`        |
      | per-actor active run      | 1   | `enforce_run_start(actor_id)` 第一段        |
      | global active run（P2/P3） | 1   | `enforce_run_start(actor_id)` 第二段        |
      | env 專屬 storage cap        | 1024 MB（env var 可調）              | `enforce_artifact_storage(env)`             |
      | manifest TTL              | 30d | `mark_manifest_expired(manifest_id)`       |

    4 條 enforce 方法都在違反時 raise `ReplayQuotaExceededError`（單一共用
    custom exception，`quota_kind` 欄區分），通過則 return `QuotaCheckResult`
    讓 caller（P2a-S3 routes）在 API response 暴露剩餘 slot 數。

    `ReplayQuotaEnforcer` **不**做：
      - 耦合 GovernanceHub / Decision Lease / live hot path（V3 §6.2 + V3
        §12 #14 紅線：replay subsystem 嚴禁耦合 live）；
      - 實際 artifact filesystem prune（交 `helper_scripts/cron/
        replay_artifact_prune.py` per V3 §5 + workplan S5 row）；
      - 生成 manifest / 簽 manifest（P2a-S2 manifest_signer 擁有）；
      - INSERT/UPDATE manifests（P2a-S3 routes 擁有）；
      - DDL（V### migration 範圍，per V3 §6 + REF-20_RESERVATION.md 說明，
        由 P2b runner SQL fixture 擁有）。

    Schema absent graceful：當 `replay.experiments` / `replay.report_artifacts`
    表尚未存在（V3 §6 說由 P2b runner SQL fixture 在 Wave 3/4 land），
    每個 enforce 方法把「表缺」視為「0 active resources」並放行新請求。
    這個設計性放寬與 `helper_scripts/cron/replay_artifact_prune.py` 的 cron
    pattern 一致，讓 enforcer 可在 runner 出貨 fixture SQL 前先接到 routes —
    表 land 後 0 行代碼變更即啟用真正執行。

SPEC: REF-20 V3 §5 (Manifest, Quota, Retention) + §3 G9 (90d/180d/key separation)
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4
          Wave 3 R20-P2a-S5
V3 §12 acceptance #4: replay_manifest_quota_guard
V3 §12 acceptance #14: replay_no_live_mutation (this module 0 trading.* / 0 live)

Cross-language note / 跨語言註：本 module 為 Python 端 enforcer；Rust 端
    enforcement 由 `bin/replay_runner` Wave 3-4 land 時的 cfg gate 強制
    （見 V3 §6.2 acceptance checks），雙端 enforce 同 cap 但獨立實作。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional


# ─── Logging setup / 日誌設定 ────────────────────────────────────────
# Logger name mirrors `manifest_signer` package convention — module-level
# logger lazily resolved by Python logging.
# Logger 命名對齊 `manifest_signer` package convention — module-level
# logger 由 Python logging 延遲解析。
log = logging.getLogger("replay.quota_enforcer")


# ─── Config constants / 配置常量 ─────────────────────────────────────
# V3 §5 spec invariants — DO NOT change without amendment.
# V3 §5 規範不變量 — 未經 amendment 不得修改。

# manifest TTL: 30 days default (V3 §5 row "manifest TTL").
# manifest TTL：30 天預設（V3 §5 「manifest TTL」row）。
MANIFEST_TTL_DAYS = 30

# Per-actor active manifest cap (V3 §5 "per-actor active manifests = 20").
# 單一 actor 同時 active manifest 上限（V3 §5 「per-actor active manifests = 20」）。
PER_ACTOR_ACTIVE_MANIFEST_CAP = 20

# Per-actor active run cap (V3 §5 "per-actor active runs = 1").
# 單一 actor 同時 active run 上限（V3 §5 「per-actor active runs = 1」）。
PER_ACTOR_ACTIVE_RUN_CAP = 1

# Global active run cap (V3 §5 "global active runs = 1 in P2/P3").
# 全局同時 active run 上限（V3 §5 「global active runs = 1 in P2/P3」）。
GLOBAL_ACTIVE_RUN_CAP = 1

# Default env-specific storage cap (1 GiB / env). V3 §5 says
# "implementation defines env-specific cap before P2a merge"; we expose env
# var `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB` for operator override per
# env (paper/demo/live) without code changes.
# 預設 env 專屬 storage cap（每 env 1 GiB）。V3 §5 說「implementation
# defines env-specific cap before P2a merge」；本實作透過 env var
# `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB` 讓 operator 為每個 env
# （paper/demo/live）獨立調整，無需改碼。
DEFAULT_ARTIFACT_STORAGE_CAP_MB = 1024


# ─── Custom exception / 自定異常 ─────────────────────────────────────
class ReplayQuotaExceededError(Exception):
    """Raised when a quota check fails. Single shared exception with
    `quota_kind` discriminator so caller routes can format human-readable
    error responses without inspecting the exception class hierarchy.

    當 quota 檢查失敗時 raise。共用單一 exception 加 `quota_kind` 欄
    discriminator，caller route 可不 inspect class 階層直接組裝
    human-readable 錯誤回應。

    `quota_kind` values:
      - `'manifest_per_actor'` → per-actor active manifest cap exceeded
      - `'run_per_actor'` → per-actor active run cap exceeded
      - `'run_global'` → global active run cap exceeded
      - `'storage_env'` → env-specific artifact storage cap exceeded

    `quota_kind` 取值對應四條 cap，方便 caller 區分回 4xx/5xx 行為。
    """

    def __init__(
        self,
        quota_kind: str,
        actor_or_env: str,
        current: int | float,
        cap: int | float,
        detail: str = "",
    ) -> None:
        self.quota_kind = quota_kind
        self.actor_or_env = actor_or_env
        self.current = current
        self.cap = cap
        self.detail = detail
        message = (
            f"replay quota exceeded ({quota_kind}): "
            f"{actor_or_env} current={current} cap={cap}"
        )
        if detail:
            message = f"{message}; {detail}"
        super().__init__(message)


# ─── Result type / 結果型別 ──────────────────────────────────────────
@dataclass(frozen=True)
class QuotaCheckResult:
    """Returned by `enforce_*` methods on PASS — exposes remaining slot
    count so caller can surface it in API response (operator UX).

    `enforce_*` 方法通過時回的結果 — 暴露剩餘 slot 數讓 caller route
    放進 API response（operator UX）。

    Fields / 欄位：
      - `quota_kind`: same enum string as exception
      - `current`: current usage at check time
      - `cap`: hard cap from spec
      - `remaining`: cap - current（永不 negative；caller 不需自算）
      - `schema_present`: True when DB tables exist; False when graceful
        fallback path was taken (caller can log degraded mode telemetry)

      - `quota_kind`：與 exception 同一個 enum 字串
      - `current`：檢查當下用量
      - `cap`：spec 上限
      - `remaining`：cap - current（永遠非負；caller 不需自算）
      - `schema_present`：True 表 DB 表存在；False 表走 graceful fallback
        路徑（caller 可上 degraded mode telemetry）
    """

    quota_kind: str
    current: int | float
    cap: int | float
    remaining: int | float
    schema_present: bool


# ─── Storage cap resolution / Storage cap 解析 ───────────────────────
def _resolve_storage_cap_mb() -> int:
    """Resolve env-specific artifact storage cap (MB) from env var.
    從 env var 解析 env 專屬 artifact storage cap (MB)。

    Priority / 優先級:
      1. `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB` env var (parsed as int)
      2. `DEFAULT_ARTIFACT_STORAGE_CAP_MB` (1024)

    Invalid values (non-numeric / ≤0) fall back to default + log warning;
    this prevents typo-induced silent cap of 0 (which would block all
    artifacts).

    無效值（非數字 / ≤0）退回預設並 log warning；防 typo 導致 cap=0
    silent block 所有 artifact。
    """
    raw = os.environ.get("OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB", "")
    if not raw:
        return DEFAULT_ARTIFACT_STORAGE_CAP_MB
    try:
        parsed = int(raw)
    except ValueError:
        log.warning(
            "OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB=%r not int; "
            "falling back to default %d",
            raw,
            DEFAULT_ARTIFACT_STORAGE_CAP_MB,
        )
        return DEFAULT_ARTIFACT_STORAGE_CAP_MB
    if parsed <= 0:
        log.warning(
            "OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB=%d ≤ 0 invalid; "
            "falling back to default %d",
            parsed,
            DEFAULT_ARTIFACT_STORAGE_CAP_MB,
        )
        return DEFAULT_ARTIFACT_STORAGE_CAP_MB
    return parsed


# ─── Schema presence probe (graceful fallback) ─────────────────────────
def _table_exists(cur: Any, schema: str, table: str) -> bool:
    """Return True iff `schema.table` exists in current DB.
    若 `schema.table` 在當前 DB 存在則回 True。

    Mirrors `replay_key_archive_cleanup._v042_present` pattern —
    information_schema probe is read-only + portable across psycopg2
    versions. Any unexpected exception fails closed (returns False) so the
    enforcer treats schema-absent identically to "tables missing →
    graceful permit".

    對齊 `replay_key_archive_cleanup._v042_present` 模式 —
    information_schema probe 唯讀且跨 psycopg2 版本可移植。任何例外
    fail-closed（回 False），enforcer 把 schema-absent 等同「表缺 → graceful
    放行」。
    """
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s LIMIT 1;",
            (schema, table),
        )
        return cur.fetchone() is not None
    except Exception as exc:  # noqa: BLE001 — fail-closed schema probe
        log.warning(
            "schema probe failed for %s.%s: %s; treating as absent",
            schema,
            table,
            exc,
        )
        return False


# ─── Enforcer class / 強制器主類 ─────────────────────────────────────
class ReplayQuotaEnforcer:
    """Pure-Python quota enforcer wrapping a DB-API 2.0 cursor.
    純 Python quota enforcer，包一個 DB-API 2.0 cursor。

    Caller responsibility / Caller 責任:
      - Hand a live cursor (psycopg2 / mock); enforcer does NOT manage
        connection lifecycle.
      - Wrap calls in caller's own transaction; enforcer does NOT commit
        or rollback (it is a read-only check + 1 UPDATE in
        `mark_manifest_expired`).
      - Catch `ReplayQuotaExceededError` and convert to HTTP 429 / 409
        per route convention (P2a-S3 owns the route mapping).

      - 傳一個 live cursor（psycopg2 / mock）；enforcer 不管 connection
        生命週期。
      - 把呼叫包進 caller 自己的 transaction；enforcer 不 commit / rollback
        （唯讀檢查 + `mark_manifest_expired` 一個 UPDATE）。
      - Catch `ReplayQuotaExceededError` 後依 route convention 轉
        HTTP 429 / 409（P2a-S3 擁有 route mapping）。

    Thread safety / 執行緒安全:
      Stateless beyond the cursor reference; reuse across requests is safe
      iff each request hands its own cursor. The shared instance pattern
      (one enforcer at app boot, cursor injected per call) is preferred.

      除了 cursor reference 外無狀態；每個請求用自己的 cursor 即可跨請求
      共用。建議 app 啟動建一個 enforcer instance，每呼叫注入 cursor。
    """

    def __init__(self) -> None:
        # Resolve storage cap once at construction so subsequent
        # `enforce_artifact_storage` calls do not re-parse env var
        # (operator changing env var requires app restart, which is the
        # intended deploy posture).
        # 在 ctor 時解析一次 storage cap，後續 `enforce_artifact_storage`
        # 不重 parse env var（operator 改 env var 需重啟 app — 這是預期
        # 部署姿態）。
        self._storage_cap_mb = _resolve_storage_cap_mb()
        log.info(
            "ReplayQuotaEnforcer ctor: storage_cap=%d MB "
            "(per_actor_manifest=%d, per_actor_run=%d, global_run=%d, "
            "manifest_ttl=%dd)",
            self._storage_cap_mb,
            PER_ACTOR_ACTIVE_MANIFEST_CAP,
            PER_ACTOR_ACTIVE_RUN_CAP,
            GLOBAL_ACTIVE_RUN_CAP,
            MANIFEST_TTL_DAYS,
        )

    # ─── Public API: enforcement / 公開 API：強制 ─────────────────────

    def enforce_manifest_create(
        self, cur: Any, actor_id: str
    ) -> QuotaCheckResult:
        """Reject if actor already has 20 active manifests.
        若 actor 已有 20 個 active manifest 則拒絕。

        V3 §5: per-actor active manifests = 20.
        V3 §5：per-actor active manifests = 20。

        "Active" definition / 「Active」定義:
            `expires_at IS NULL OR expires_at > NOW()`. A manifest with
            `expires_at <= NOW()` is considered TTL-expired and does NOT
            count toward the cap. The `mark_manifest_expired` writer (this
            class) flips manifests to expired by stamping `expires_at`.

            `expires_at IS NULL OR expires_at > NOW()`。`expires_at <= NOW()`
            的 manifest 視為 TTL-expired，不計入 cap。`mark_manifest_expired`
            寫手（本 class）透過 stamp `expires_at` 來翻轉 manifest 為 expired。

        Schema absent graceful / 表缺 graceful:
            `replay.experiments` 不在 → 視為 0 active manifest，放行。

        Args / 參數:
            cur: psycopg2-style cursor inside caller's transaction.
            actor_id: replay actor identifier (string per V3 §11 routes).

        Returns / 回傳:
            `QuotaCheckResult` on PASS.

        Raises / 例外:
            `ReplayQuotaExceededError(quota_kind='manifest_per_actor', ...)`
            when count >= 20.
        """
        if not _table_exists(cur, "replay", "experiments"):
            log.info(
                "enforce_manifest_create: replay.experiments absent; "
                "graceful permit (actor=%s)",
                actor_id,
            )
            return QuotaCheckResult(
                quota_kind="manifest_per_actor",
                current=0,
                cap=PER_ACTOR_ACTIVE_MANIFEST_CAP,
                remaining=PER_ACTOR_ACTIVE_MANIFEST_CAP,
                schema_present=False,
            )

        count = self._count_active_manifests_for_actor(cur, actor_id)
        if count >= PER_ACTOR_ACTIVE_MANIFEST_CAP:
            raise ReplayQuotaExceededError(
                quota_kind="manifest_per_actor",
                actor_or_env=actor_id,
                current=count,
                cap=PER_ACTOR_ACTIVE_MANIFEST_CAP,
                detail=(
                    "expire / cancel one or wait for TTL "
                    "(default 30d per V3 §5)"
                ),
            )
        return QuotaCheckResult(
            quota_kind="manifest_per_actor",
            current=count,
            cap=PER_ACTOR_ACTIVE_MANIFEST_CAP,
            remaining=PER_ACTOR_ACTIVE_MANIFEST_CAP - count,
            schema_present=True,
        )

    def enforce_run_start(
        self, cur: Any, actor_id: str
    ) -> QuotaCheckResult:
        """Reject if actor already has 1 active run, OR if global active
        runs ≥ 1. Both checks are evaluated; the per-actor check raises
        first if violated.

        若 actor 已有 1 active run，或全局 active runs ≥ 1 則拒絕。
        兩個檢查都會執行；per-actor 違反時優先 raise。

        V3 §5: per-actor active runs = 1; global active runs = 1 in P2/P3.
        V3 §5：per-actor active runs = 1；global active runs = 1 in P2/P3。

        "Active run" definition / 「Active run」定義:
            `status IN ('created', 'running')`. Once flipped to
            `completed` / `failed` / `cancelled` the run no longer counts.
            (Schema column `status` from V3 §4.1 `replay.experiments`.)

            `status IN ('created', 'running')`。一旦翻 `completed` /
            `failed` / `cancelled`，此 run 不再計入。
            （schema column `status` 來自 V3 §4.1 `replay.experiments`。）

        Returns the result for the **per-actor** quota; the global check is
        a separate condition raised before this return when violated. The
        caller can re-call to inspect global remaining if needed (or trust
        that PASS implies both per-actor < 1 AND global < 1).

        Returns / 回傳:
            `QuotaCheckResult(quota_kind='run_per_actor', ...)` 表 PASS。

        Raises / 例外:
            `ReplayQuotaExceededError(quota_kind='run_per_actor', ...)`
                若 actor 已有 active run；
            `ReplayQuotaExceededError(quota_kind='run_global', ...)`
                若全局已有 active run（per-actor PASS 後第二段 raise）。
        """
        if not _table_exists(cur, "replay", "experiments"):
            log.info(
                "enforce_run_start: replay.experiments absent; "
                "graceful permit (actor=%s)",
                actor_id,
            )
            return QuotaCheckResult(
                quota_kind="run_per_actor",
                current=0,
                cap=PER_ACTOR_ACTIVE_RUN_CAP,
                remaining=PER_ACTOR_ACTIVE_RUN_CAP,
                schema_present=False,
            )

        # 1) Per-actor cap / 1) 單 actor 上限。
        per_actor_count = self._count_active_runs_for_actor(cur, actor_id)
        if per_actor_count >= PER_ACTOR_ACTIVE_RUN_CAP:
            raise ReplayQuotaExceededError(
                quota_kind="run_per_actor",
                actor_or_env=actor_id,
                current=per_actor_count,
                cap=PER_ACTOR_ACTIVE_RUN_CAP,
                detail=(
                    "wait for current run to complete / fail / cancel "
                    "(per-actor active run = 1 per V3 §5)"
                ),
            )

        # 2) Global cap / 2) 全局上限。
        global_count = self._count_active_runs_global(cur)
        if global_count >= GLOBAL_ACTIVE_RUN_CAP:
            raise ReplayQuotaExceededError(
                quota_kind="run_global",
                actor_or_env="<global>",
                current=global_count,
                cap=GLOBAL_ACTIVE_RUN_CAP,
                detail=(
                    "another actor already has an active run "
                    "(global active run = 1 in P2/P3 per V3 §5)"
                ),
            )

        return QuotaCheckResult(
            quota_kind="run_per_actor",
            current=per_actor_count,
            cap=PER_ACTOR_ACTIVE_RUN_CAP,
            remaining=PER_ACTOR_ACTIVE_RUN_CAP - per_actor_count,
            schema_present=True,
        )

    def enforce_artifact_storage(
        self, cur: Any, env: str
    ) -> QuotaCheckResult:
        """Reject if env-summed live artifact bytes ≥ env storage cap.
        若 env 加總的 live artifact bytes ≥ env storage cap 則拒絕。

        V3 §5: artifact storage cap = implementation defines env-specific cap.
        Implementation choice: single env var `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB`
        applied uniformly to every env (paper/demo/live); operator can
        override per-cluster. Env separation is enforced at the **query
        scope** (sum bytes WHERE env = ?) — caller passes the env, this
        method does not parse env from elsewhere.

        V3 §5：artifact storage cap = implementation defines env-specific cap。
        實作選擇：用單一 env var `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB`
        套用到每個 env（paper/demo/live）；operator 可 per-cluster 覆寫。
        Env 分離由 **query scope** 強制（sum bytes WHERE env = ?）— caller
        傳 env，本方法不從別處解析。

        "Live artifact" definition / 「Live artifact」定義:
            `expires_at IS NULL OR expires_at > NOW()` 且 owning experiment
            non-cancelled. Pruned (post-`expires_at`) artifacts do not count.

        Schema column / Schema 欄:
            `replay.report_artifacts.bytes` (assumed integer). Schema absent
            → graceful permit (0 bytes used).

        Returns `QuotaCheckResult` with `current` / `cap` / `remaining` in
        MB units (matching the env var unit so operator math works).

        回 `QuotaCheckResult`，`current` / `cap` / `remaining` 以 MB 為單位
        （對齊 env var 單位讓 operator 算數一致）。
        """
        if not _table_exists(cur, "replay", "report_artifacts"):
            log.info(
                "enforce_artifact_storage: replay.report_artifacts absent; "
                "graceful permit (env=%s, cap=%d MB)",
                env,
                self._storage_cap_mb,
            )
            return QuotaCheckResult(
                quota_kind="storage_env",
                current=0,
                cap=self._storage_cap_mb,
                remaining=self._storage_cap_mb,
                schema_present=False,
            )

        used_mb = self._sum_live_artifact_bytes_mb(cur, env)
        if used_mb >= self._storage_cap_mb:
            raise ReplayQuotaExceededError(
                quota_kind="storage_env",
                actor_or_env=env,
                current=used_mb,
                cap=self._storage_cap_mb,
                detail=(
                    "wait for prune cron (replay_artifact_prune.py runs "
                    "every 6h) or raise OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB"
                ),
            )
        return QuotaCheckResult(
            quota_kind="storage_env",
            current=used_mb,
            cap=self._storage_cap_mb,
            remaining=self._storage_cap_mb - used_mb,
            schema_present=True,
        )

    def mark_manifest_expired(
        self, cur: Any, manifest_id: str
    ) -> bool:
        """Stamp manifest's `expires_at <= NOW()` so it stops counting.
        對 manifest stamp `expires_at <= NOW()`，讓它停止計入 active 計數。

        Used by routes when caller explicitly cancels / deletes a manifest
        before TTL natural expiry, freeing a per-actor slot immediately.

        當 caller 在 TTL 自然過期前明示 cancel / delete manifest 時呼叫，
        立即釋放一個 per-actor slot。

        Idempotent / 冪等:
            UPDATE WHERE manifest_id = ? AND (expires_at IS NULL OR
            expires_at > NOW()). Re-marking already-expired manifest is a
            no-op (RETURNING empty).

            UPDATE WHERE manifest_id = ? AND (expires_at IS NULL OR
            expires_at > NOW())。對已 expired manifest 重 mark 是 no-op
            （RETURNING 空）。

        Schema absent graceful / Schema 缺 graceful:
            `replay.experiments` not present → log + return False (no-op).

            `replay.experiments` 缺 → log + return False（no-op）。

        Returns / 回傳:
            True iff a row was actually flipped (manifest existed +
            previously not expired). False if schema absent or row missing
            or already expired.

            True 表真翻轉了 row（manifest 存在 + 之前未 expired）；False 表
            schema 缺 / row 缺 / 已 expired。
        """
        if not _table_exists(cur, "replay", "experiments"):
            log.info(
                "mark_manifest_expired: replay.experiments absent; "
                "no-op (manifest_id=%s)",
                manifest_id,
            )
            return False

        # Idempotent UPDATE with RETURNING — only flips rows that are
        # currently active (not yet TTL-expired), avoiding repeated audit
        # noise on retry. NULL expires_at also matches because the schema
        # may have inserted with NULL pending mark; treat NULL as "active
        # forever, never auto-expired".
        # Idempotent UPDATE with RETURNING — 只翻轉當前 active（尚未 TTL
        # expired）的 row，避免 retry 時重複 audit noise。NULL expires_at
        # 也視為「forever active 從未自動過期」並符合此 WHERE 條件。
        cur.execute(
            """
            UPDATE replay.experiments
               SET expires_at = NOW()
             WHERE experiment_id = %s
               AND (expires_at IS NULL OR expires_at > NOW())
            RETURNING experiment_id;
            """,
            (manifest_id,),
        )
        row = cur.fetchone()
        if row is None:
            log.info(
                "mark_manifest_expired: no row to flip "
                "(manifest_id=%s; either absent or already expired)",
                manifest_id,
            )
            return False
        log.info("mark_manifest_expired: flipped manifest_id=%s", manifest_id)
        return True

    # ─── Internal SQL helpers / 內部 SQL helper ──────────────────────

    def _count_active_manifests_for_actor(
        self, cur: Any, actor_id: str
    ) -> int:
        """Count active (non-TTL-expired) manifests created by actor.
        計算 actor 創建的 active（未 TTL expired）manifest 數量。
        """
        cur.execute(
            """
            SELECT COUNT(*) FROM replay.experiments
             WHERE created_by = %s
               AND (expires_at IS NULL OR expires_at > NOW())
               AND COALESCE(status, 'created') NOT IN ('cancelled');
            """,
            (actor_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _count_active_runs_for_actor(self, cur: Any, actor_id: str) -> int:
        """Count active (status IN created/running) runs for one actor.
        計算 actor 的 active（status IN created/running）run 數量。
        """
        cur.execute(
            """
            SELECT COUNT(*) FROM replay.experiments
             WHERE created_by = %s
               AND status IN ('created', 'running');
            """,
            (actor_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _count_active_runs_global(self, cur: Any) -> int:
        """Count global active (status IN created/running) runs.
        計算全局 active（status IN created/running）run 數量。
        """
        cur.execute(
            """
            SELECT COUNT(*) FROM replay.experiments
             WHERE status IN ('created', 'running');
            """
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _sum_live_artifact_bytes_mb(self, cur: Any, env: str) -> int:
        """Sum live artifact bytes for env; return MB (rounded down int).
        加總 env 的 live artifact bytes；回 MB（int 向下取整）。

        Joins to `replay.experiments` to apply env scope (column
        `runtime_environment` per V3 §4.1) — V3 §4.1 says
        `runtime_environment` ∈ {`linux_trade_core`,
        `mac_dev_smoke_test_only`}. Caller's `env` semantically maps to
        `runtime_environment`; we accept the caller's string verbatim and
        let SQL match (avoids hardcoding the enum here in case future
        envs added).

        透過 join `replay.experiments` 套用 env scope（V3 §4.1 column
        `runtime_environment`）。Caller 的 `env` 對應 `runtime_environment`；
        本方法 verbatim 接 caller 字串給 SQL 比對（避免硬編 enum，未來新
        env 不需改碼）。
        """
        cur.execute(
            """
            SELECT COALESCE(SUM(ra.bytes), 0)
              FROM replay.report_artifacts ra
              JOIN replay.experiments ex
                ON ra.experiment_id = ex.experiment_id
             WHERE ex.runtime_environment = %s
               AND (ra.expires_at IS NULL OR ra.expires_at > NOW());
            """,
            (env,),
        )
        row = cur.fetchone()
        bytes_used = int(row[0]) if row and row[0] is not None else 0
        # Bytes → MB: divide by 1024*1024, integer floor.
        # bytes → MB：除以 1024*1024，向下取整。
        return bytes_used // (1024 * 1024)

    # ─── Read-only accessors / 唯讀存取器 ───────────────────────────

    @property
    def storage_cap_mb(self) -> int:
        """Resolved env-specific storage cap (MB).
        已解析的 env 專屬 storage cap (MB)。
        """
        return self._storage_cap_mb


# ─── Module export / 模組匯出 ────────────────────────────────────────
__all__ = [
    "DEFAULT_ARTIFACT_STORAGE_CAP_MB",
    "GLOBAL_ACTIVE_RUN_CAP",
    "MANIFEST_TTL_DAYS",
    "PER_ACTOR_ACTIVE_MANIFEST_CAP",
    "PER_ACTOR_ACTIVE_RUN_CAP",
    "QuotaCheckResult",
    "ReplayQuotaEnforcer",
    "ReplayQuotaExceededError",
]
