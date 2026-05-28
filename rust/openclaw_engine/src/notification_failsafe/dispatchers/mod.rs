//! Wave 5 Packet C / C1 — 3-way notification dispatchers stub mod root.
//!
//! 為什麼此檔現為 stub：PM 在派 E1-PC1 之前 pre-stage 本子模塊宣告，避免 4 E1
//! 並行寫入 `notification_failsafe/mod.rs` 衝突。E1-PC1 將補：
//!   - `slack.rs`：Incoming Webhook URL 派發 + retry/timeout（per operator Q1.2 拍 Webhook）
//!   - `email.rs`：Gmail SMTP App Password 派發（per operator Q2.1 拍 Gmail）
//!   - `console_banner.rs`：本地 banner 寫入（per operator Q3.1 拍「直到 ack 不 auto-clear」）
//!   - `three_way.rs`：把三路綁成單一 `NotificationDispatcher` impl
//!   - tests/：mock + integration test
//!
//! Secret 全採 fail-closed 缺檔即 disable（同 `autonomy_totp.py` pattern）：
//!   - `~/BybitOpenClaw/secrets/vault/slack_webhook.json`
//!   - `~/BybitOpenClaw/secrets/vault/email_config.json`
//!
//! 不變量（per CLAUDE.md §二）：
//!   - 不真實寄送 in test（mock）
//!   - HTTP rate-limit 429 / 5xx 算 fail 不 retry-forever
//!   - per-dispatch timeout 硬限避免 hot path 卡住
//!
//! ref: docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md

pub mod console_banner;
pub mod email;
pub mod slack;
pub mod three_way;
