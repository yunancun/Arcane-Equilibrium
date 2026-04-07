-- ============================================================================
-- V014 — Engine events audit table (ARCH-RC1 1C-2-E)
-- V014 — 引擎事件審計表 (ARCH-RC1 1C-2-E)
-- ============================================================================
--
-- Single append-only audit log for engine lifecycle and ConfigStore patches.
-- Populated by Rust-side writers (1C-2-C IPC patch handlers, future Position
-- Reconciler, startup/shutdown hooks). One row per discrete event; bulk
-- patches that touch N sub-fields still write a single row whose payload
-- enumerates the changed field paths.
--
-- 引擎生命週期與 ConfigStore 補丁的單一 append-only 審計日誌。由 Rust 側
-- 寫入器填充（1C-2-C IPC patch handler、未來 Position Reconciler、
-- startup/shutdown hook）。每個離散事件一行；觸及 N 個子欄位的批次補丁
-- 仍寫一行，其 payload 列出變更的欄位路徑。
--
-- event_type values:
--   'startup'        — engine boot complete
--   'shutdown'       — engine clean exit
--   'config_patch'   — ConfigStore.replace() succeeded via IPC
--   'config_reject'  — patch failed validation (rolled back)
--   'reconcile'      — Position Reconciler reconciled exchange state (1C-4)
--   'crash'          — abnormal termination detected by watchdog
-- ============================================================================

CREATE TABLE IF NOT EXISTS observability.engine_events (
    id           BIGSERIAL PRIMARY KEY,
    ts_ms        BIGINT NOT NULL,
    event_type   TEXT NOT NULL,
    source       TEXT,
    config_name  TEXT,
    old_version  BIGINT,
    new_version  BIGINT,
    payload      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_engine_events_ts
    ON observability.engine_events (ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_engine_events_type_ts
    ON observability.engine_events (event_type, ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_engine_events_config
    ON observability.engine_events (config_name, new_version DESC)
    WHERE config_name IS NOT NULL;

COMMENT ON TABLE observability.engine_events IS
    'ARCH-RC1 1C-2-E: append-only engine lifecycle and ConfigStore patch audit log';
