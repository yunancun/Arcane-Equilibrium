//! MODULE_NOTE
//! 模塊用途：歷史回填子系統。含日線 K 線回填 + funding rate / open interest 歷史回填。
//!   把 Bybit 歷史資料嚴格解析後寫 market.klines / research.alpha_* 歷史表。
//! 主要子模塊：
//!   - daily_kline_backfill：日線（timeframe='1d'）分頁取數 + C-3 strict-parse（OHLC>0，
//!     fake-zero/非有限/損壞 bar 不寫）。
//!   - writer：market.klines strict 寫入 + alpha_klines_provenance append-only 帳本 + V125 preflight。
//!   - funding_oi_backfill：funding/OI 分頁取數 + ★ strict-parse VARIANT（讀原始 JSON，
//!     「欄位存在 AND finite」而非 >0 floor — 保留真 0.0/負 funding，只擋 missing/non-finite）。
//!   - funding_oi_writer：alpha_funding_rates_history / alpha_open_interest_history strict 寫入
//!     + alpha_history_ingest_runs/pages 帳本 + V125 preflight。
//! 依賴：market_data_client（既有 client + 新增 *_raw 原始回應方法）、database::pool（sqlx）、
//!   openclaw_core::klines、serde_json、sha2。
//! 硬邊界：純讀市場數據 + append-only provenance；不下單、不餵 intent、不碰 auth/lease/system_mode/cap。
//!   timeframe='1d' 與 live 訂的 1m-1h 完全 disjoint（market.klines PK=(symbol,timeframe,ts)），
//!   ON CONFLICT DO NOTHING 永不與 live upsert 衝突。

pub mod daily_kline_backfill;
pub mod funding_oi_backfill;
pub mod funding_oi_writer;
pub mod writer;
