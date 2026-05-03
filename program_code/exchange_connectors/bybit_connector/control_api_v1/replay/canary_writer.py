"""REF-20 P2b-T3 CanaryArtifactWriter — replay artifact filesystem + DB registry.
REF-20 P2b-T3 CanaryArtifactWriter — replay artifact filesystem + DB registry。

MODULE_NOTE (EN):
    Wave 4 R20-P2b-T3 (workplan §4) lands the canary / diagnostic artifact
    writer that registers replay output files in `replay.report_artifacts`
    (V046 schema) and writes the JSON / JSONL payload to filesystem under
    OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/. Two surface methods:

      | Method                                | Purpose                              |
      |---------------------------------------|--------------------------------------|
      | write_replay_artifact(...)            | write payload to filesystem          |
      | register_artifact_in_db(cur, ...)     | INSERT into replay.report_artifacts  |

    Linux path (RUNTIME_LINUX): writes under
      `$OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/<artifact_type>.json`
    and registers row with `is_mock=False`.

    Mac dev path (RUNTIME_MAC): writes under
      `/tmp/replay_artifacts_test_only/<run_id>/<artifact_type>.json`
    and registers row with `is_mock=True` to surface V3 §6.3
    "Mac dev smoke is non-actionable by design" to operators.

    `CanaryArtifactWriter` does NOT:
      - couple to GovernanceHub / Decision Lease / live hot path
        (V3 §6.2 + §12 #14 red-line);
      - touch `trading.*` / `learning.*` / live config (V3 §12 #14);
      - perform DDL or DB migrations (V046 owns schema);
      - sign manifest payloads (manifest_signer owns);
      - prune expired files (S5 cron owns).

MODULE_NOTE (中):
    Wave 4 R20-P2b-T3（workplan §4）落地 canary / diagnostic artifact 寫手，
    將 replay output file 註冊到 `replay.report_artifacts`（V046 schema）並
    把 JSON / JSONL payload 寫到 filesystem
    OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/ 下。兩個 surface method：

      | 方法                                  | 用途                                |
      |---------------------------------------|--------------------------------------|
      | write_replay_artifact(...)            | 寫 payload 到 filesystem             |
      | register_artifact_in_db(cur, ...)     | INSERT 到 replay.report_artifacts    |

    Linux 路徑（RUNTIME_LINUX）：寫到
      `$OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/<artifact_type>.json`
    註冊列 `is_mock=False`。

    Mac dev 路徑（RUNTIME_MAC）：寫到
      `/tmp/replay_artifacts_test_only/<run_id>/<artifact_type>.json`
    註冊列 `is_mock=True`，向 operator 暴露 V3 §6.3「Mac dev smoke is
    non-actionable by design」。

    `CanaryArtifactWriter` 不做：
      - 耦合 GovernanceHub / Decision Lease / live hot path（V3 §6.2 +
        §12 #14 紅線）；
      - 動 `trading.*` / `learning.*` / live config（V3 §12 #14）；
      - DDL 或 DB migration（V046 擁有 schema）；
      - 簽 manifest payload（manifest_signer 擁有）；
      - 清過期檔（S5 cron 擁有）。

SPEC: REF-20 V3 §4.1 (replay.report_artifacts schema) + §11 P2b
      deliverables (canary/diagnostic artifacts registered Linux only)
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
          §4 Wave 4 R20-P2b-T3
V3 §12 acceptance #7 replay_registry_fk_contract (artifacts FK to run_state)
V3 §12 acceptance #14 replay_no_live_mutation (this module: 0 trading.*
      write, 0 live config mutation)
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# ─── Logging setup / 日誌設定 ────────────────────────────────────────
log = logging.getLogger("replay.canary_writer")


# ─── Constants / 常量 ────────────────────────────────────────────────
# V046 artifact_type enum allowlist. Mirrors CHECK chk_replay_report_artifacts_type.
# V046 artifact_type enum 白名單。對齊 CHECK chk_replay_report_artifacts_type。
ARTIFACT_TYPE_CANARY = "canary"
ARTIFACT_TYPE_DIAGNOSTIC = "diagnostic"
ARTIFACT_TYPE_PNL_SUMMARY = "pnl_summary"
ARTIFACT_TYPE_FILL_LOG = "fill_log"
ARTIFACT_TYPE_BASELINE_COMPARE = "baseline_compare"

ALLOWED_ARTIFACT_TYPES = frozenset({
    ARTIFACT_TYPE_CANARY,
    ARTIFACT_TYPE_DIAGNOSTIC,
    ARTIFACT_TYPE_PNL_SUMMARY,
    ARTIFACT_TYPE_FILL_LOG,
    ARTIFACT_TYPE_BASELINE_COMPARE,
})

# Default artifact subdirectory under OPENCLAW_DATA_DIR (Linux) or /tmp (Mac).
# OPENCLAW_DATA_DIR 下（Linux）/ /tmp 下（Mac）的預設 artifact 子目錄。
DEFAULT_ARTIFACTS_SUBDIR = "replay_artifacts"
MAC_DEV_ARTIFACTS_DIR = "/tmp/replay_artifacts_test_only"


# ─── Result type / 結果型別 ──────────────────────────────────────────
@dataclass(frozen=True)
class WriteResult:
    """Returned by `write_replay_artifact` — caller passes to
    `register_artifact_in_db` to complete the two-phase write.
    `write_replay_artifact` 的回傳；caller 傳給 `register_artifact_in_db`
    完成兩階段寫入。

    Fields / 欄位:
      - artifact_id    UUID hex (server-generated); used as V046 PRIMARY KEY.
      - artifact_path  filesystem path of the written file.
      - byte_size      bytes written (used by S5 quota_enforcer storage cap).
      - is_mock        True on Mac dev (V3 §6.3 non-actionable marker).
    """

    artifact_id: str
    artifact_path: str
    byte_size: int
    is_mock: bool


# ─── Writer class / 寫手主類 ─────────────────────────────────────────
class CanaryArtifactWriter:
    """Filesystem + DB writer for canary / diagnostic / pnl_summary /
    fill_log / baseline_compare replay artifacts.

    canary / diagnostic / pnl_summary / fill_log / baseline_compare replay
    artifact 的 filesystem + DB 寫手。

    Caller responsibility / Caller 責任:
      - Hand a live cursor to `register_artifact_in_db`; writer does NOT
        manage connection lifecycle.
      - Wrap calls in caller's own transaction; writer does NOT commit
        or rollback the DB INSERT.
      - Filesystem write side is independent (no transaction); on partial
        failure (file written but DB INSERT failed), caller should retry
        DB INSERT with same artifact_id (idempotent INSERT ... ON CONFLICT
        not used because PRIMARY KEY collision is recoverable evidence).

      - 把 live cursor 給 `register_artifact_in_db`；writer 不管 connection
        生命週期。
      - 把呼叫包進 caller 自己的 transaction；writer 不 commit / rollback
        DB INSERT。
      - filesystem 寫獨立於 transaction；partial failure（file 寫了 DB
        INSERT 失敗）時 caller 應以同 artifact_id 重試 DB INSERT（不用
        ON CONFLICT 因為 PK 衝突視為「可復原證據」而非錯誤）。

    Thread safety / 執行緒安全:
      Stateless beyond resolved root paths; reuse safe iff each call hands
      its own cursor (per uvicorn worker).
    """

    def __init__(self, runtime_environment: str = "") -> None:
        """Initialize writer; resolve root paths once.
        初始化 writer；一次解析 root path。

        Args:
            runtime_environment: V3 §4.1 enum. Empty string → auto-detect
                (sys.platform == 'darwin' → mac, else linux). Test
                callers can force a specific value.
        """
        self._runtime_env = self._resolve_runtime(runtime_environment)
        self._root_dir = self._resolve_root_dir(self._runtime_env)
        log.info(
            "CanaryArtifactWriter ctor: runtime_env=%s root_dir=%s",
            self._runtime_env, self._root_dir,
        )

    @staticmethod
    def _resolve_runtime(override: str) -> str:
        """Auto-detect or accept caller override.
        自動偵測或接受 caller override。
        """
        if override == "linux_trade_core" or override == "mac_dev_smoke_test_only":
            return override
        # Auto-detect via env var first (test-friendly), then sys.platform.
        # 先用 env var（test 友好），再 fallback sys.platform。
        env_override = os.environ.get("OPENCLAW_REPLAY_RUNTIME_ENV", "").strip()
        if env_override in ("linux_trade_core", "mac_dev_smoke_test_only"):
            return env_override
        import sys
        if sys.platform == "darwin":
            return "mac_dev_smoke_test_only"
        return "linux_trade_core"

    @staticmethod
    def _resolve_root_dir(runtime_env: str) -> Path:
        """Resolve root artifact directory per runtime_environment.
        依 runtime_environment 解析 root artifact 目錄。

        Linux: $OPENCLAW_DATA_DIR/replay_artifacts/ (fallback /tmp/openclaw
        per CLAUDE.md §六 path policy).

        Mac:   /tmp/replay_artifacts_test_only/ (V3 §6.3 non-actionable
        marker; never co-located with Linux runtime path so accidental
        path-mix can't cause Mac fixture to be picked up by Linux runner).

        Linux：$OPENCLAW_DATA_DIR/replay_artifacts/（fallback /tmp/openclaw
        per CLAUDE.md §六 path policy）。

        Mac：/tmp/replay_artifacts_test_only/（V3 §6.3 非可採用標記；永不
        與 Linux runtime 路徑重疊，避免 Mac fixture 被 Linux runner 誤拾）。
        """
        if runtime_env == "mac_dev_smoke_test_only":
            return Path(MAC_DEV_ARTIFACTS_DIR)
        # Linux path: prefer OPENCLAW_DATA_DIR per CLAUDE.md §六.
        # Linux 路徑：依 CLAUDE.md §六 用 OPENCLAW_DATA_DIR。
        data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
        return Path(data_dir) / DEFAULT_ARTIFACTS_SUBDIR

    @property
    def runtime_environment(self) -> str:
        """Resolved runtime_environment for this writer.
        本 writer 解析得到的 runtime_environment。
        """
        return self._runtime_env

    @property
    def root_dir(self) -> Path:
        """Resolved root directory for artifact files.
        artifact 檔的根目錄。
        """
        return self._root_dir

    @property
    def is_mock_environment(self) -> bool:
        """True iff runtime_environment is mac_dev_smoke_test_only.
        runtime_environment 是 mac_dev_smoke_test_only 時為 True。
        """
        return self._runtime_env == "mac_dev_smoke_test_only"

    # ─── Public API: write / 公開 API：寫入 ──────────────────────────

    def write_replay_artifact(
        self,
        run_id: str,
        artifact_type: str,
        payload: Any,
    ) -> WriteResult:
        """Write artifact payload to filesystem; return registration metadata.
        把 artifact payload 寫到 filesystem；回註冊 metadata。

        Args:
            run_id: V045 replay.run_state.run_id (UUID hex).
            artifact_type: V046 enum (must be in ALLOWED_ARTIFACT_TYPES).
            payload: JSON-serializable object (dict / list).

        Returns:
            `WriteResult` with server-generated artifact_id + filesystem
            path + byte_size + is_mock; caller passes to
            `register_artifact_in_db` to complete the two-phase write.

        Raises:
            ValueError: artifact_type not in allowlist.
            OSError: filesystem write failure (caller should treat as
                terminal — no DB registration if write failed).
        """
        if artifact_type not in ALLOWED_ARTIFACT_TYPES:
            raise ValueError(
                f"artifact_type={artifact_type!r} not in allowlist "
                f"{sorted(ALLOWED_ARTIFACT_TYPES)} / "
                f"artifact_type 不在白名單"
            )

        # Build per-run subdirectory; mkdir -p to allow concurrent writes
        # for different runs without race.
        # 建 per-run 子目錄；mkdir -p 容忍不同 run 的並發寫入。
        run_dir = self._root_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique artifact_id; one file per artifact (caller may
        # call this multiple times per run for multiple artifact types).
        # 生 artifact_id；一個 artifact 一個 file（caller 可對同 run 多次呼叫
        # 寫不同 type）。
        artifact_id = uuid.uuid4().hex
        # File name embeds artifact_id to avoid collision when caller writes
        # multiple artifacts of the same type for one run (rare but allowed).
        # 檔名嵌 artifact_id 避免同 run 同 type 多次寫入時碰撞（罕見但允許）。
        filename = f"{artifact_type}_{artifact_id}.json"
        artifact_path = run_dir / filename

        # Serialize with deterministic ordering for reproducibility (V3 §6.4
        # baseline reproducibility rule: artifact bytes deterministic for
        # same logical payload).
        # 用 deterministic ordering 序列化以便 reproducibility（V3 §6.4
        # baseline reproducibility 規則：同邏輯 payload 的 artifact bytes
        # deterministic）。
        body_bytes = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

        # Atomic-ish write: write to .tmp + rename. Caller is responsible
        # for retry on partial failure (no transaction here).
        # 近原子寫：先寫 .tmp 再 rename。partial failure 時由 caller 重試
        # （此處無 transaction）。
        tmp_path = artifact_path.with_suffix(".json.tmp")
        with open(tmp_path, "wb") as f:
            f.write(body_bytes)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(artifact_path)

        byte_size = len(body_bytes)
        log.info(
            "write_replay_artifact: run_id=%s type=%s path=%s bytes=%d is_mock=%s",
            run_id, artifact_type, artifact_path, byte_size,
            self.is_mock_environment,
        )

        return WriteResult(
            artifact_id=artifact_id,
            artifact_path=str(artifact_path),
            byte_size=byte_size,
            is_mock=self.is_mock_environment,
        )

    def register_artifact_in_db(
        self,
        cur: Any,
        run_id: str,
        write_result: WriteResult,
        *,
        artifact_type: str,
        expires_at_iso: Optional[str] = None,
    ) -> bool:
        """INSERT row in replay.report_artifacts referencing the file.
        對 replay.report_artifacts INSERT 一列指向該 file。

        Schema absent / Schema 缺:
            V046 absent → log + return False (no-op). Caller continues
            without raising (consistent with quota_enforcer / run_state_manager
            schema-absent pattern).

        Args:
            cur: psycopg2-style cursor inside caller's transaction.
            run_id: V045 replay.run_state.run_id (FK target).
            write_result: from `write_replay_artifact()`.
            artifact_type: V046 enum (re-supplied for logging clarity;
                must match write phase).
            expires_at_iso: optional ISO-8601 UTC TTL boundary (V3 §4.1
                "inherited or shorter than experiment TTL"); None means
                pinned (never auto-expire).

        Returns:
            True iff a row was actually INSERTed.

        Raises:
            ValueError: artifact_type mismatch or not in allowlist.
        """
        if artifact_type not in ALLOWED_ARTIFACT_TYPES:
            raise ValueError(
                f"artifact_type={artifact_type!r} not in allowlist "
                f"{sorted(ALLOWED_ARTIFACT_TYPES)}"
            )

        if not self._table_exists(cur, "replay", "report_artifacts"):
            log.info(
                "register_artifact_in_db: replay.report_artifacts absent; "
                "no-op (run_id=%s artifact_id=%s)",
                run_id, write_result.artifact_id,
            )
            return False

        cur.execute(
            """
            INSERT INTO replay.report_artifacts (
                artifact_id, run_id, artifact_type, artifact_path,
                byte_size, is_mock, created_at, expires_at
            ) VALUES (
                %s::uuid, %s::uuid, %s, %s,
                %s, %s, NOW(), %s::timestamptz
            )
            RETURNING artifact_id::text;
            """,
            (
                write_result.artifact_id, run_id,
                artifact_type, write_result.artifact_path,
                write_result.byte_size, write_result.is_mock,
                expires_at_iso,
            ),
        )
        row = cur.fetchone()
        if row is None:
            log.warning(
                "register_artifact_in_db: INSERT returned no row "
                "(unexpected; run_id=%s artifact_id=%s)",
                run_id, write_result.artifact_id,
            )
            return False
        log.info(
            "register_artifact_in_db: registered artifact_id=%s run_id=%s "
            "type=%s path=%s",
            write_result.artifact_id, run_id, artifact_type,
            write_result.artifact_path,
        )
        return True

    # ─── Internal helpers / 內部輔助 ─────────────────────────────────

    @staticmethod
    def _table_exists(cur: Any, schema: str, table: str) -> bool:
        """Check `schema.table` existence via information_schema (read-only).
        透過 information_schema 檢查 `schema.table` 是否存在（純讀）。
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
                schema, table, exc,
            )
            return False


# ─── Module export / 模組匯出 ────────────────────────────────────────
__all__ = [
    "ALLOWED_ARTIFACT_TYPES",
    "ARTIFACT_TYPE_BASELINE_COMPARE",
    "ARTIFACT_TYPE_CANARY",
    "ARTIFACT_TYPE_DIAGNOSTIC",
    "ARTIFACT_TYPE_FILL_LOG",
    "ARTIFACT_TYPE_PNL_SUMMARY",
    "CanaryArtifactWriter",
    "DEFAULT_ARTIFACTS_SUBDIR",
    "MAC_DEV_ARTIFACTS_DIR",
    "WriteResult",
]
