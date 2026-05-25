"""
MODULE_NOTE
模塊用途：
    V109 learning.anomaly_events read-only query helper。Sprint 3 detector +
    cron + GUI audit forensic 用。對齊 V109 spec §5.3 SQL pattern + §8 cross-ref
    pattern；不寫入 (寫入走 Rust writer rust/openclaw_engine/src/database/
    anomaly_event_writer.rs)。

主要函數：
    - get_recent_anomalies(taxonomy, severity, hours=24)：query 24h 內 anomaly。
    - get_amplification_cap_count(symbol, taxonomy, engine_mode, since)：H-11
      cap 24h count helper (Python 端版本，對齊 Rust writer
      `amplification_loop_24h_count` 方法 SQL semantic)。

依賴：
    - psycopg2 (workspace dep，從 caller 端注入 connection)；
    - V109 schema 已 land (commit 16796d13)。

硬邊界：
    - Read-only；本 module 不寫 INSERT/UPDATE。
    - V109 23 column 對齊 Rust writer + V109 SQL。
    - engine_mode IN ('live','live_demo') training filter 由 caller 決定；本
      module SQL 不 hardcode (避免 paper 學習資料源被 over-filter)。

規格 / Spec:
    - V109 SQL: sql/migrations/V109__m8_anomaly_events_hypertable.sql
    - V109 spec v2 amend: docs/execution_plan/2026-05-25--v109_m8_anomaly_events_schema_spec_v2_amend.md
    - M8 design spec §5 H-11: docs/execution_plan/2026-05-21--m8_anomaly_detection_design_spec.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

if TYPE_CHECKING:
    import psycopg2.extensions


# V109 schema 4 CHECK constraint 對應 client-side enum reference
# (對齊 rust/openclaw_engine/src/database/anomaly_event_writer.rs 4 validator)。
VALID_EVENT_TAXONOMIES: tuple[str, ...] = (
    "regime_shift",
    "liquidation_cascade",
    "orderbook_imbalance",
    "funding_outlier",
    "volume_spike",
    "spread_widening",
    "price_dislocation",
    "ws_disconnect",
    "fee_anomaly",
)

VALID_SEVERITIES: tuple[str, ...] = ("INFO", "WARN", "CRITICAL", "HALT")

VALID_DETECTION_METHODS: tuple[str, ...] = (
    "atr_vol_funding_9cell",
    "rv_percentile",
    "block_bootstrap",
    "manual_operator",
)

VALID_ENGINE_MODES: tuple[str, ...] = (
    "paper",
    "demo",
    "live_demo",
    "live",
    "replay",
)

# ADR-0036 Decision 1 黑名單 (反向防護；對齊 Rust validate_detection_method)。
FORBIDDEN_DETECTION_SUBSTRINGS: tuple[str, ...] = (
    "hmm",
    "markov_switching",
    "markov-switching",
    "garch",
)


def get_recent_anomalies(
    conn: "psycopg2.extensions.connection",
    taxonomy: Optional[str] = None,
    severity: Optional[Iterable[str]] = None,
    engine_mode: Optional[Iterable[str]] = None,
    hours: int = 24,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """
    Query V109 learning.anomaly_events 內 past `hours` 小時 anomaly。

    為什麼參數 taxonomy / severity / engine_mode 全可選 :
        - taxonomy=None : 跨 9 taxonomy query (audit dashboard / GUI 用)。
        - severity=None : 跨 4 severity query (INFO+WARN+CRITICAL+HALT)。
        - engine_mode=None : caller 端決定是否 filter (training-only 必傳
          ('live','live_demo')；audit forensic 跨 mode)。

    參數說明：
        - conn: psycopg2 connection (caller 端注入；本函數不 own connection lifecycle)。
        - taxonomy: 9 enum 之一；None = 不 filter。client-side 驗 fail-fast。
        - severity: 4 enum 子集；None = 不 filter。
        - engine_mode: 5 enum 子集；None = 不 filter。
        - hours: lookback 視窗 (default 24h；對齊 H-11 24h rolling)。
        - limit: 最多回多少 row (避 GUI 超時；hot path 應加 paginated query)。

    回傳：list of dict (cursor.description-mapped)；空 list 即無 anomaly。

    為什麼回 list[dict] 而非 strong-typed row :
        - Sprint 2 Wave 1 階段 schema 可能微調；dict 比 dataclass 彈性。
        - Sprint 3 wire 接 detector 時可加 AnomalyEventRow dataclass。

    Spec : V109 spec §5.3 + §8.3 SQL pattern。
    """
    # 4 enum validator (對齊 Rust client-side check)。
    if taxonomy is not None and taxonomy not in VALID_EVENT_TAXONOMIES:
        raise ValueError(
            f"invalid taxonomy '{taxonomy}' "
            f"(must be one of {VALID_EVENT_TAXONOMIES})"
        )
    if severity is not None:
        invalid = [s for s in severity if s not in VALID_SEVERITIES]
        if invalid:
            raise ValueError(
                f"invalid severity values {invalid} "
                f"(must be subset of {VALID_SEVERITIES})"
            )
    if engine_mode is not None:
        invalid = [em for em in engine_mode if em not in VALID_ENGINE_MODES]
        if invalid:
            raise ValueError(
                f"invalid engine_mode values {invalid} "
                f"(must be subset of {VALID_ENGINE_MODES})"
            )
    if hours <= 0:
        raise ValueError(f"hours must be > 0, got {hours}")
    if limit <= 0:
        raise ValueError(f"limit must be > 0, got {limit}")

    sql_parts = [
        "SELECT id, observed_at, event_taxonomy, severity, detection_method,",
        "       atr_vol_state, funding_state, strategy_id, symbol,",
        "       metric_value, metric_baseline, metric_threshold,",
        "       amplification_loop_24h_count,",
        "       m3_health_observation_ref, m7_decay_signal_ref, m1_lal_demote_ref,",
        "       evidence_json, engine_mode, created_by, created_at,",
        "       updated_by, updated_at, source_version",
        "FROM learning.anomaly_events",
        "WHERE observed_at > now() - INTERVAL %(hours_iv)s",
    ]
    params: dict[str, Any] = {"hours_iv": f"{hours} hours"}

    if taxonomy is not None:
        sql_parts.append("  AND event_taxonomy = %(taxonomy)s")
        params["taxonomy"] = taxonomy
    if severity is not None:
        sev_tuple = tuple(severity)
        if sev_tuple:
            sql_parts.append("  AND severity = ANY(%(severity_arr)s)")
            params["severity_arr"] = list(sev_tuple)
    if engine_mode is not None:
        em_tuple = tuple(engine_mode)
        if em_tuple:
            sql_parts.append("  AND engine_mode = ANY(%(engine_mode_arr)s)")
            params["engine_mode_arr"] = list(em_tuple)

    sql_parts.append("ORDER BY observed_at DESC, id DESC")
    sql_parts.append("LIMIT %(lim)s")
    params["lim"] = limit

    sql = "\n".join(sql_parts)

    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols: Sequence[str] = [d.name for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return rows


def get_amplification_cap_count(
    conn: "psycopg2.extensions.connection",
    taxonomy: str,
    engine_mode: str,
    hours: int = 24,
) -> int:
    """
    H-11 amplification cap 24h count helper (Python 端版本)。

    對齊 Rust writer `AnomalyEventWriter::amplification_loop_24h_count` semantic +
    V109 spec §5.3 SQL pattern。**read-only**；caller decide 是否標
    evidence_json.cap_suppressed=true 不 emit M3 cascade。

    為什麼只計 CRITICAL/HALT 不含 INFO/WARN :
        - per H-11 + M3 §6.2「1 anomaly_type = 1 state change / 24h」針對的是
          trigger M3 cascade 的 severity (CRITICAL/HALT)；INFO/WARN 不 trigger M3
          state change (per M8 design spec §6.1)，不計入 cap。

    為什麼 engine_mode 必傳不可 None :
        - per V109 spec §5.3 line 277-278 + 5 paper / demo / live_demo / live /
          replay 5 個獨立計數空間；live 環境的 cap 不該被 paper 噪音污染。

    參數說明：
        - conn: psycopg2 connection。
        - taxonomy: 9 enum 之一；client-side 驗 fail-fast。
        - engine_mode: 5 enum 之一；client-side 驗 fail-fast。
        - hours: 視窗 (default 24h 對齊 H-11)。

    回傳：int count；caller decide ≥ 2 是否標 cap_suppressed。

    Spec : V109 spec §5.3 + M8 design spec §5.2 (Loop cap rule)。
    """
    if taxonomy not in VALID_EVENT_TAXONOMIES:
        raise ValueError(
            f"invalid taxonomy '{taxonomy}' "
            f"(must be one of {VALID_EVENT_TAXONOMIES})"
        )
    if engine_mode not in VALID_ENGINE_MODES:
        raise ValueError(
            f"invalid engine_mode '{engine_mode}' "
            f"(must be one of {VALID_ENGINE_MODES})"
        )
    if hours <= 0:
        raise ValueError(f"hours must be > 0, got {hours}")

    sql = """
    SELECT COUNT(*) AS cnt
    FROM learning.anomaly_events
    WHERE event_taxonomy = %(taxonomy)s
      AND observed_at > now() - INTERVAL %(hours_iv)s
      AND severity IN ('CRITICAL', 'HALT')
      AND engine_mode = %(engine_mode)s
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            {
                "taxonomy": taxonomy,
                "hours_iv": f"{hours} hours",
                "engine_mode": engine_mode,
            },
        )
        row = cur.fetchone()
    return int(row[0]) if row else 0


def is_cap_suppressed(count: int) -> bool:
    """
    H-11 cap policy : count ≥ 2 → cap_suppressed=true (per V109 spec §5.3 line 280)。

    為什麼 helper 而非 caller 各自寫 :
        - 政策統一封裝；Sprint 3 detector + cron 用同一函式；
        - 未來改 cap threshold (e.g. cap=3 / 24h) 只改本函式不需 scan caller。
    """
    return count >= 2


def validate_detection_method_python(method: str) -> None:
    """
    ADR-0036 Decision 1 detection_method 黑名單反向防護 (Python 端對齊 Rust)。

    對齊 rust/openclaw_engine/src/database/anomaly_event_writer.rs
    `validate_detection_method` substring match 反向防護。

    本函式不傳 conn — 純 client-side 驗；caller 端可在組 row 前 fail-fast。

    Raises:
        ValueError: 命中黑名單 (HMM / Markov-switching / GARCH) 或不在 4 enum 內。
    """
    lower = method.lower()
    for forbidden in FORBIDDEN_DETECTION_SUBSTRINGS:
        if forbidden in lower:
            raise ValueError(
                f"invalid detection_method '{method}' — "
                f"ADR-0036 Decision 1 forbidden algorithm "
                f"(HMM / Markov-switching / GARCH 永久禁用)"
            )
    if method not in VALID_DETECTION_METHODS:
        raise ValueError(
            f"invalid detection_method '{method}' "
            f"(must be one of {VALID_DETECTION_METHODS})"
        )
