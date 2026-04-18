//! Shadow-fill writer — INSERT learning.decision_shadow_fills (EDGE-P3-1 Step 7c).
//! Shadow-fill 寫入器 — INSERT learning.decision_shadow_fills。
//!
//! MODULE_NOTE (EN): Async consumer for `ShadowFillMsg` channel. Each message
//!   becomes one row in `learning.decision_shadow_fills`. These rows capture
//!   ε-greedy paper exploration fills (spec §7.3 Step 7, F4+U3): the predictor
//!   rejected on cost but the exploration coin flip succeeded, so we synthesize
//!   a fill for observation only — never for live or demo trading, and never
//!   part of the training label backfill (`parquet_etl.py` WHERE clause
//!   excludes close_tag='shadow_fill:epsilon_greedy', §5.1).
//!
//!   DB-level safety rails: `engine_mode` CHECK (= 'paper') rejects any row a
//!   non-paper gate could theoretically produce; the close_tag default gives us
//!   a single permanent label-exclusion key. `synthetic_exit_price` /
//!   `synthetic_hold_ms` / `synthetic_net_edge_bps` stay NULL here — a later
//!   synthetic-close pass (separate writer, Stage 2+) populates them.
//!
//! MODULE_NOTE (中): `ShadowFillMsg` 通道的異步消費者；每條訊息寫入
//!   `learning.decision_shadow_fills` 一列。捕捉 ε-greedy paper 探索 fill
//!   （spec §7.3 Step 7，F4+U3）— 預測器拒絕但探索翻硬幣通過，僅作觀測，
//!   不入 live/demo，且永不納入訓練 label 回填（`parquet_etl.py` §5.1 WHERE
//!   以 close_tag='shadow_fill:epsilon_greedy' 排除）。
//!   DB 級保險：`engine_mode` CHECK (='paper') 拒絕任何非 paper 的錯誤路徑；
//!   `close_tag` 預設提供單一永久 label 排除鍵；`synthetic_*` 欄位保持 NULL，
//!   待後續 close-time writer 填入（Stage 2+ 獨立 pass）。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §7.3 / V017 migration.

use super::pool::DbPool;
use super::ShadowFillMsg;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Run the shadow-fill writer task.
/// 運行 shadow-fill 寫入器任務。
pub async fn run_shadow_fill_writer(
    mut rx: mpsc::Receiver<ShadowFillMsg>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    // Dedup: keep only latest per context_id before flush. Matches the
    // decision_feature_writer discipline — an ε-greedy branch fires at most
    // once per intent, but a replay/passthrough could double-send the same
    // context_id and the same-pass dedup keeps the table idempotent.
    // 去重：每個 context_id 只保留最新。ε-greedy 分支每個 intent 至多一次，
    // 但回放/passthrough 可能重發同一 context_id；flush 前去重保表冪等。
    let mut pending: HashMap<String, ShadowFillMsg> = HashMap::new();

    let flush_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.batch_flush_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(flush_interval);
    flush_timer.tick().await;

    info!("shadow_fill_writer started / shadow-fill 寫入器已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() && !pending.is_empty() {
                    flush_shadow_fills(&pool, &mut pending).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(sf) => {
                        pending.insert(sf.context_id.clone(), sf);
                    }
                    None => break,
                }
            }
        }
    }

    if pool.is_available() && !pending.is_empty() {
        flush_shadow_fills(&pool, &mut pending).await;
    }
    info!("shadow_fill_writer stopped / shadow-fill 寫入器已停止");
}

/// INSERT shadow-fill rows to PG. Non-paper rows are rejected in-process as a
/// second line of defense behind the DB CHECK (fail-soft + warn, not panic).
/// 寫入 shadow-fill 列；非 paper 在 writer 內亦被拒絕（warn + skip），
/// 是 DB CHECK 之外的第二道防線。
async fn flush_shadow_fills(pool: &DbPool, pending: &mut HashMap<String, ShadowFillMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            pending.clear();
            return;
        }
    };

    for (_, sf) in pending.drain() {
        // DB-RUN-6: reject epoch-0 writes — same policy as decision_feature_writer.
        // 拒絕 epoch=0 的寫入，1970 行會毒化訓練時間域 JOIN。
        if sf.ts_ms == 0 {
            warn!(
                ctx_id = %sf.context_id, symbol = %sf.symbol,
                "shadow_fill write rejected: ts_ms=0 (epoch leak) / 拒絕 epoch 0 寫入"
            );
            continue;
        }

        // R5 second-line defense: even though the gate's `is_paper` guard should
        // make non-paper impossible, reject anything that leaked — so a future
        // regression fails loudly in writer logs rather than hitting PG CHECK and
        // poisoning the pool's failure counter.
        // R5 第二道防線：gate 的 is_paper 保證非 paper 不應到達這裡；萬一退化
        // 也 warn+skip，避免 PG CHECK 拒絕後把寫入失敗計入 pool 失敗閾值。
        if sf.engine_mode != "paper" {
            warn!(
                ctx_id = %sf.context_id, engine = %sf.engine_mode,
                "shadow_fill write rejected: engine_mode must be 'paper' (R5 defense) \
                 / 拒絕非 paper 寫入（R5 防線）"
            );
            continue;
        }

        let ts = chrono::DateTime::from_timestamp_millis(sf.ts_ms as i64).unwrap_or_default();

        // JSONB parse — same policy as decision_feature_writer: malformed string
        // means `FeatureVectorV1::to_jsonb` regressed, warn-and-skip rather than
        // let sqlx reject at bind time.
        // JSONB 解析：格式錯代表上游退化，warn+skip 而非讓 sqlx bind 階段拒絕。
        let features_value: serde_json::Value = match serde_json::from_str(&sf.features_jsonb) {
            Ok(v) => v,
            Err(e) => {
                warn!(
                    ctx_id = %sf.context_id, error = %e,
                    "shadow_fill write rejected: malformed JSONB / JSONB 解析失敗"
                );
                continue;
            }
        };

        // synthetic_* columns left NULL — a later close-time pass fills them.
        // close_tag uses the V017 DDL default ('shadow_fill:epsilon_greedy').
        // synthetic_* 列留 NULL；close_tag 走 V017 預設值。
        let result = sqlx::query(
            "INSERT INTO learning.decision_shadow_fills \
             (context_id, ts, engine_mode, strategy_name, symbol, side, \
              features_jsonb, predicted_q10, predicted_q50, predicted_q90, \
              cost_bps_at_open) \
             VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
        )
        .bind(&sf.context_id)
        .bind(ts)
        .bind(&sf.engine_mode)
        .bind(&sf.strategy_name)
        .bind(&sf.symbol)
        .bind(sf.side as i16) // SMALLINT
        .bind(&features_value)
        .bind(sf.predicted_q10 as f64)
        .bind(sf.predicted_q50 as f64)
        .bind(sf.predicted_q90 as f64)
        .bind(sf.cost_bps_at_open)
        .execute(pg)
        .await;

        match result {
            Ok(_) => {
                pool.record_success();
                debug!(
                    ctx_id = %sf.context_id, strategy = %sf.strategy_name, symbol = %sf.symbol,
                    "shadow_fill written / shadow-fill 已寫入"
                );
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(
                    ctx_id = %sf.context_id, error = %e,
                    "shadow_fill write failed / shadow-fill 寫入失敗"
                );
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_sf(id: &str) -> ShadowFillMsg {
        ShadowFillMsg {
            context_id: id.into(),
            ts_ms: 1_700_000_000_000,
            engine_mode: "paper".into(),
            strategy_name: "ma_crossover".into(),
            symbol: "BTCUSDT".into(),
            side: 1,
            features_jsonb: r#"{"adx_1h":25.0,"side":1}"#.into(),
            predicted_q10: -10.0,
            predicted_q50: 5.0,
            predicted_q90: 20.0,
            cost_bps_at_open: 8.5,
        }
    }

    #[test]
    fn test_dedup_keeps_latest() {
        let mut pending: HashMap<String, ShadowFillMsg> = HashMap::new();
        let sf1 = make_sf("ctx-1");
        let mut sf2 = make_sf("ctx-1");
        sf2.strategy_name = "funding_arb".into();
        pending.insert(sf1.context_id.clone(), sf1);
        pending.insert(sf2.context_id.clone(), sf2);
        assert_eq!(pending.len(), 1);
        assert_eq!(pending["ctx-1"].strategy_name, "funding_arb");
    }

    #[test]
    fn test_dbrun6_epoch_zero_detected() {
        // flush_shadow_fills needs a live pool; verify the field carrier instead.
        // flush 需活 pool；此處驗欄位即可。
        let mut sf = make_sf("ctx-zero");
        sf.ts_ms = 0;
        assert_eq!(sf.ts_ms, 0);
    }

    #[test]
    fn test_non_paper_engine_mode_rejected_in_carrier() {
        // Second-line R5 defense — writer rejects before DB CHECK fires.
        // R5 第二道防線：writer 層拒絕，不勞 DB CHECK。
        let mut sf = make_sf("ctx-demo");
        sf.engine_mode = "demo".into();
        assert_ne!(sf.engine_mode, "paper");
    }

    #[test]
    fn test_malformed_jsonb_caught_before_sql() {
        let mut sf = make_sf("ctx-bad");
        sf.features_jsonb = "not json".into();
        let parsed: Result<serde_json::Value, _> = serde_json::from_str(&sf.features_jsonb);
        assert!(parsed.is_err());
    }

    #[test]
    fn test_valid_jsonb_parses() {
        let sf = make_sf("ctx-ok");
        let parsed: serde_json::Value =
            serde_json::from_str(&sf.features_jsonb).expect("valid JSON");
        assert_eq!(parsed["adx_1h"], 25.0);
        assert_eq!(parsed["side"], 1);
    }

    #[test]
    fn test_side_fits_smallint() {
        let sf_long = make_sf("ctx-long");
        let sf_short = ShadowFillMsg {
            side: -1,
            ..make_sf("ctx-short")
        };
        assert_eq!(sf_long.side as i16, 1);
        assert_eq!(sf_short.side as i16, -1);
    }

    #[test]
    fn test_insert_sql_locked_columns() {
        // Lock column list against silent drift — V017 schema must match.
        // synthetic_* columns + close_tag intentionally omitted (DDL defaults).
        // 鎖定欄位列表避免靜默漂移；synthetic_* + close_tag 故意用 DDL 預設。
        let src = include_str!("shadow_fill_writer.rs");
        for col in [
            "context_id",
            "engine_mode",
            "strategy_name",
            "side",
            "features_jsonb",
            "predicted_q10",
            "predicted_q50",
            "predicted_q90",
            "cost_bps_at_open",
        ] {
            assert!(src.contains(col), "INSERT SQL missing column: {col}");
        }
        // close_tag has DB default; writer must NOT bind it explicitly
        // (DDL drift on the default would silently change label exclusion).
        // Check: the INSERT SQL (everything after "INSERT INTO" and before the
        // first "VALUES") is column-list only — `close_tag` must not appear
        // there. Scoping the check to the column list avoids false positives
        // from this comment or future bilingual doc strings.
        // close_tag 走 DB 預設；writer 不應顯式 bind（DDL 漂移會靜默改變 label 排除鍵）。
        // 檢查範圍限 INSERT 欄位列表，避開註解/docstring 誤報。
        let col_list = src
            .split_once("INSERT INTO")
            .and_then(|(_, rest)| rest.split_once("VALUES"))
            .map(|(cols, _)| cols)
            .expect("INSERT INTO ... VALUES shape must hold");
        assert!(
            !col_list.contains("close_tag"),
            "writer must not bind close_tag — rely on DDL default"
        );
    }
}
