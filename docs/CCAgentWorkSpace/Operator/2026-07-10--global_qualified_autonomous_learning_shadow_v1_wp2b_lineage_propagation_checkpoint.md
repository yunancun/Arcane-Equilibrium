# Operator Summary — GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP2-B Lineage Propagation

Date: 2026-07-10
State: `ACTIVE_WP2B_COLD_EVALUATION_BOARD_V2`
Checkpoint: `38ccd014c5ce974fbd395625b9597e12832395ee`
G2: `PARTIAL_SOURCE_ACCEPTED`

B2.2a 已完成 source acceptance，接受時 Mac 與 `origin/main` 對齊上述完整
SHA。合法的 prospective `candidate_event_context_v1` 現在可原樣走完
`event -> decision -> ledger -> blocked outcome`，並保留同一個 event hash。

保護條件是嚴格的七欄綁定：strategy、symbol、side、context ID、signal ID、
engine mode、timestamp 必須與 context 完全一致；不接受 alias、trim、大小寫或
型別轉換、時間 fallback、欄位補值。graft、缺欄、hash 錯誤或 summary 衝突都會
fail closed。

只有明確標記為 `explicit_source_rows` 的來源可攜帶 prospective context。
歷史 PG decision-feature、pipeline snapshot 與未標記 row 一律保持 contextless，
新 materialized row 明列 `UNQUALIFIED_CONTEXT_MISSING`，不會回填或偽造。
本階段也沒有生成 cold evaluation context 或 candidate-board projection；
`candidate_board.py`、`outcome_writer.py`、`price_observations.py` 的 production
code 都未改動。共用 fixture 已用 typed Rust contract 解析並驗 hash。

驗證結果：E1 `220 passed, 1 skipped`；E2 找到一個 P1 provenance bypass，修正後
P0/P1/P2 為 `0/0/0`；replacement E4 為 Python `303 passed, 1 skipped`、Rust
targeted `1 passed`；root Rust module `10/10`；QA `41/41` 並回傳
`PASS_SOURCE_CHECKPOINT_TO_PM`。

這不是 deploy、runtime active、資料新鮮、training、serving、promotion 或盈利
證明。本輪沒有 Linux、service、PG、Bybit、order、probe、Lease、Guardian、
RiskConfig、global Cost Gate 或任何 authority 動作。最後接受的 Linux/ALR
service pin 仍是 WP1 的 `7d1c247947f0fb6c139f8a0583c5e6ed6ae62c70`。

下一步是 B2.2b：明確附加驗證過的 cold evaluation context，並把
candidate-board schema / arbiter input 升為 v2；之後才做 restart-safe
event-driven primary handoff。Cron 只保留 reconciliation 用途。
