//! MODULE_NOTE
//! 模塊用途：歷史回填子系統。目前僅含日線（timeframe='1d'）K 線回填。
//!   把 Bybit 歷史 OHLCV 嚴格解析後寫 market.klines + research.alpha_klines_provenance。
//! 主要子模塊：
//!   - daily_kline_backfill：分頁取數 + C-3 strict-parse（fake-zero/非有限/損壞 bar 不寫）。
//!   - writer：market.klines strict 寫入 + provenance append-only 帳本 + V125 preflight。
//! 依賴：market_data_client（既有 client，不重寫）、database::pool（sqlx）、openclaw_core::klines。
//! 硬邊界：純讀市場數據 + append-only provenance；不下單、不餵 intent、不碰 auth/lease/system_mode。
//!   timeframe='1d' 與 live 訂的 1m-1h 完全 disjoint（market.klines PK=(symbol,timeframe,ts)），
//!   ON CONFLICT DO NOTHING 永不與 live upsert 衝突。

pub mod daily_kline_backfill;
pub mod writer;
