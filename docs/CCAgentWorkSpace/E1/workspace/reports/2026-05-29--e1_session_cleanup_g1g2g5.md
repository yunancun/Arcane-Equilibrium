# E1 IMPL — FA session gap audit G1/G2/G5 cosmetic cleanup · 2026-05-29

## 任務摘要

FA gap audit 三項 LOW 結構債 cleanup。全為 cosmetic/inert，**0 行為改變**。
worktree `../wt-gapfix` branch `fix/session-cleanup-g1g2g5`，未 commit（等 E2→E4→PM）。

## 修改清單

| 檔 | 改動 | 類型 |
|---|---|---|
| `rust/openclaw_engine/src/main.rs` | +6 行中文註釋（near-dead var 標 observability-only） | G2 純註釋 |
| `rust/openclaw_engine/src/notification_failsafe/providers/single_watcher.rs` | stale 註解對齊 registry §2.4（±3 行） | G5 純註釋 |
| `rust/openclaw_engine/src/event_consumer/handlers/risk.rs` | −217 行（C4 block 搬出） | G1 pure-move |
| `rust/openclaw_engine/src/event_consumer/handlers/notification_failsafe_escalate.rs` | 新檔 231 行（C4 block 搬入 + MODULE_NOTE） | G1 pure-move |
| `rust/openclaw_engine/src/event_consumer/handlers/mod.rs` | +mod 宣告 + re-export 改指（+5 −2） | G1 wire |

git diff stat：4 changed +12 −219；1 untracked 新檔。

## (1) G2 處置 — 保留 + 中文註釋（裁決 b）

`btc_lead_lag_paper_enabled_env = false`（main.rs ~L1110）D-hygiene 修
`should_spawn_btc_lead_lag_producer` 後不再 gate spawn，僅出現在兩條 spawn/skip
tracing log 的 `paper_enabled_env` field（L1142 / L1175 區）。

選保留非移除，理由：
1. 它與上方 `paper_env_requested`（原始 env 請求 + warn）成「請求 vs 生效」
   observability 對照 — 看 log 能確認 PAPER 確被忽略（自 2026-05-23 恆 false）。
2. 移除會破壞兩分支 log schema 結構，非最小改動（surgical 原則）。

inline 中文註釋明標：「僅供 observability 非決策；spawn 唯一權威是
`should_spawn_btc_lead_lag_producer`（D-hygiene 已修：只看 runtime binding）」，
防未來誤以為它 gate spawn。**未碰 spawn 決策邏輯**。

## (2) G5 註解改 — 對齊 singleton-registry §2.4

`single_watcher.rs` L77-78 原註解：「登記在 PA/E2 report + TODO follow-up
（無集中登記表）」— 已過期。`docs/architecture/singleton-registry.md §2.4`
（commit `a8ba146c`）已登記 `SHARED_WATCHER`(§2.4.1) + `FAILSAFE_FEED_SENDERS`(§2.4.2)。
改為：「已登記於 `docs/architecture/singleton-registry.md §2.4.2`（commit a8ba146c）。
`SHARED_WATCHER` 見同文件 §2.4.1」。純註解 0 code。

## (3) G1 裁決 — DO（clean pure-move）；risk.rs 822 → 605

裁決 = 做。三項 clean 驗證（do-if-clean-else-defer 判據）：

1. **caller 走 re-export，不走 `risk::`** — 決定性因素。外部 caller
   （`loop_handlers.rs` L726、`tests/c4_failsafe_wire_tests.rs` L57/L177）皆呼
   `handlers::handle_notification_failsafe_escalate`，經 `mod.rs` 的
   `pub(crate) use`。故只需把 `pub(crate) use risk::...` 改指
   `notification_failsafe_escalate::...`，**caller 零改**。
2. **4 helper + C4-specific imports 全僅此 block 用** — grep 確認：C4-specific
   imports（PgAuditEmitter / execute_failsafe_escalation / ExchangeStopSync /
   StopRequest / async_trait / PositionSnapshot / StopAdjustment / UnboundedSender 等）
   pre-618 非 import 0 hit；4 helper（PrebuiltSnapshots / InBandStopSync /
   NoopFailsafeAudit / compute_position_atr）全檔外 0 ref；risk.rs 無自有
   `#[cfg(test)]`。→ import 隨遷，無糾纏、無 visibility 牽連。
3. **搬完真 <800** — risk.rs 822（去 import 後 811）→ 搬出 C4 section 後 **605**。

搬移 = 機械性：C4 section（原 L618-822）+ C4-specific imports（原 L19-28）整塊
→ 新 `handlers/notification_failsafe_escalate.rs`（231 行，加 MODULE_NOTE）。
**0 邏輯改**（逐字搬，僅補模塊頭註）。

risk.rs 行數 before/after：**822 → 605**。

## (4) cargo 驗收

- `cargo test -p openclaw_engine --lib`：
  - baseline（G2+G5 已套、G1 前）：**3622 passed / 0 failed / 1 ignored**
  - G1 split 後：**3622 passed / 0 failed / 1 ignored** — **count 不變**（pure-move 確認）
- `cargo build -p openclaw_engine --release`：**Finished**（1m01s）
- clippy：**0 新 warning 引用我改的檔**。

pre-existing 噪音（非本 task、已存於未改 main tree）：
- release 3 warning：`btc_lead_lag/db_writer.rs:13` unused import、
  `single_watcher.rs:114` C4 dormant dead-fields（C4 wire 期 0 副作用設計殘留，
  非我改的 L77-78 註解）、`ma_crossover/helpers.rs:26` make_intent never used。
- `openclaw_core` clippy `since field must contain semver` error — 在未改的
  `srv/rust` main tree 重現確認 pre-existing，屬 openclaw_core crate clippy-strict
  問題，非本 task 範圍（不阻 release build）。

G1 split 驗證 grep：
- 搬移 fn 在新 module：`notification_failsafe_escalate.rs:133 pub(crate) async fn handle_notification_failsafe_escalate`
- re-route：`mod.rs:30 mod notification_failsafe_escalate;` + `mod.rs:39 pub(crate) use notification_failsafe_escalate::...`
- caller 正確 re-route（未動）：`loop_handlers.rs:726 handlers::handle_notification_failsafe_escalate(`

## 治理對照

- CLAUDE §九 800 行門檻：risk.rs 605 < 800 ✓。
- singleton 登記硬約束 5：G5 對齊 §2.4 已登記現況 ✓。
- 硬邊界：未碰 max_retries / live_execution_allowed / execution_authority /
  system_mode / spawn 決策邏輯（G2 明確不碰）✓。
- 注釋規範（chinese-first）：新增/改動註釋全中文，英文僅留技術 identifier ✓。
- cosmetic/inert：commit 後不單獨 redeploy，隨下次 LG-3 / incident-trigger
  rebuild 生效 ✓。

## 不確定之處

- 無實質不確定。G1 split 雖屬「結構移動」，但 caller 走 re-export + helper/import
  全 block-local，pure-move 風險極低；E4 regression 仍建議跑（結構移動驗 caller
  binding 在完整 build 下無漏接）。
- `single_watcher.rs:114` C4 dead-fields warning 是 C4 wire 期 dormant 設計殘留
  （非本 task），Sprint 3 incident-trigger 接上後自然消除；若 E2 認為值得提前清，
  屬另一 ticket（不在本 cosmetic cleanup 範圍，避免 scope 擴大）。

## Operator 下一步

1. chain → E2 審查（3 改動）→ E4 regression（僅 G1 split 屬結構移動需 E4 完整
   build 驗 caller binding）→ PM 統一 commit + push。
2. cosmetic/inert，**不單獨 redeploy**。

worktree 路徑：`/Users/ncyu/Projects/TradeBot/wt-gapfix`
（branch `fix/session-cleanup-g1g2g5`，未 commit）。

---
E1 IMPLEMENTATION DONE: 待 E2 審查（report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-29--e1_session_cleanup_g1g2g5.md`）
