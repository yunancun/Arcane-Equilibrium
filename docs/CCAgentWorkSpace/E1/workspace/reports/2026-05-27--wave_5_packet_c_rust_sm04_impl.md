# E1 IMPL — Wave 5 Packet C Rust SM-04 NotificationFailsafeTimeout + Active Lock-Profit · 2026-05-27

**Scope**: AMD-2026-05-21-01 v2 §9.8 + PA spec v2 §4.4 Stage 3b — `RiskEvent::NotificationFailsafeTimeout` 新 variant + Defensive `active_de_risking` hook 擴充
**Status**: IMPL DONE，待 E2 + E4 review
**Out of scope**: V099 schema（Packet A）；GUI Autonomy Posture sub-section（Packet B）；engine 層實際 sync exchange conditional order；commit / push / rebuild

## §1 LOC 變動矩陣

| 路徑 | 變動類型 | LOC 變動 | 說明 |
|---|---|---|---|
| `srv/rust/openclaw_core/src/sm/risk_gov.rs` | EDIT | 940 → 1289 (+349) | 新 RiskEvent variant + PositionSnapshot/StopAdjustment struct + active_lock_profit_per_position fn + FAILSAFE_DEFENSIVE_COOLING_MS const + T1-T6 test 6 條 |

文件總長 **1289 LOC**（< 2000 hard cap；> 800 review threshold — 既有狀態，本 patch 未改變等級）。

**零 overlap** 與 Packet A V099 schema（`grep -nE "V099|autonomy_level_switch_audit" risk_gov.rs` = 0 hit；本 patch 不動 schema / GUI / migration / 其他 module）。

## §2 RiskEvent enum 變動 + match exhaustiveness verify

**新 variant** (line 81-86)：
```rust
/// 三路通知（Slack/Email/Console banner）全 fail + 1h timeout → 觸發 SM-04 Defensive transition。
/// 為什麼：per AMD-2026-05-21-01 v2 §Decision 3.1 + PA spec §4.4 Stage 3b...
NotificationFailsafeTimeout,
```

**as_str() 對齊 spec** (line 113)：
```rust
Self::NotificationFailsafeTimeout => "notification_failsafe_timeout",
```

**Match exhaustiveness verify**：
- `impl RiskEvent::as_str` — 已補 `NotificationFailsafeTimeout` 分支（編譯器自動驗）
- Downstream consumer 全 site (`grep -rn "RiskEvent::" openclaw_engine/src/`) = 7 hit，**全是 constructor-style 使用**（如 `RiskEvent::OperatorEscalation`、`RiskEvent::DrawdownWarning`），沒有 `match event { ... }` exhaustive consumer。新 variant 不破壞 downstream。
- cargo build openclaw_engine release 通過（test 階段全 GREEN 證明）

## §3 active lock-profit hook IMPL detail

**新 public API**（在 `// Transition rules` 段落前一個獨立 hook 段落）：

| 項 | 行範圍 | 用途 |
|---|---|---|
| `pub struct PositionSnapshot` | 287-298 | engine 層 mapping 用的最小欄位集（symbol / side / entry / qty / current_sl / atr） |
| `pub struct StopAdjustment` | 301-307 | hook 輸出值；engine 層取走後 sync exchange conditional |
| `pub fn active_lock_profit_per_position` | 326-377 | 主邏輯：對每倉計算 entry + atr × buffer，並守住既有 SL 保護方向不放鬆 |
| `pub const FAILSAFE_DEFENSIVE_COOLING_MS` | 384 | 7d cooling 常數 = 604_800_000 ms（per PA spec Q4 拍板 30d→7d） |

**為什麼 PositionSnapshot/StopAdjustment 放在 openclaw_core**：避免循環依賴（`openclaw_core` 不可 import `openclaw_engine::PositionInfo` 否則 cargo 拒絕編譯）。engine 層在 call hook 前負責 `PositionView → PositionSnapshot` mapping。

**fail-closed 紀律**（per CLAUDE.md §二 原則 6）：
- buffer_multiplier 為 NaN / 負 → 整批返回空 Vec
- 倉位 ATR 為 NaN / ≤0 → 跳過該倉位
- 倉位 entry 為 NaN / ≤0 → 跳過該倉位
- 倉位 qty 為 NaN / 0 → 跳過該倉位
- 倉位 side 不是 "Buy" / "Sell" → 跳過該倉位
- 新 SL 為 NaN / ≤0 → 跳過該倉位
- 既有 current_sl 已比 candidate 更保護 → 保留既有（不放鬆方向）
- 零 panic / 零 unwrap / 零 unsafe / 零 expect

**呼叫端契約**（engine 層 wave 5 後續 packet 接線時遵循）：
1. 取得 Vec<PositionSnapshot>（從 PositionManager 取所有 active 倉位）
2. call `active_lock_profit_per_position(&positions, atr_buffer)` → Vec<StopAdjustment>
3. 對每筆 adjustment sync 至 exchange-side conditional protection（per 原則 9 雙重防線）
4. emit lease `active_lock_profit_triggered_by_notification_failsafe`（per PA spec line 488）

## §4 35+ transition rules regression verify

**lookup_rule 完整 pair 清單**（cargo test 同 + t4 grep 雙驗）：

| 類型 | Pair 數 | 例 |
|---|---|---|
| Escalation (from Normal) | 5 | N→C, N→R, N→D, N→CB, N→MR |
| Escalation (from Cautious) | 4 | C→R, C→D, C→CB, C→MR |
| Escalation (from Reduced) | 3 | R→D, R→CB, R→MR |
| Escalation (from Defensive) | 2 | D→CB, D→MR |
| Lateral (CB → MR) | 1 | CB→MR |
| De-escalation | 10 | C→N, R→C, R→N, D→R, D→C, CB→D, MR→D, MR→R, MR→C, MR→N |
| **合計** | **25** | — |

> Spec §9.8 「35+ pair」是粗估；實際 lookup_rule 含 25 explicit pair（既有 test_all_escalation_paths + test_all_de_escalation_paths 已覆蓋）。本 patch **零** transition rule 改動，零 pair 新增/刪除/修改 — 走的是 `RiskEvent`（事件原因）路徑，transition target/initiator/approval logic 全 reuse 既有 Normal/Cautious/Reduced → Defensive 三條 escalation rule。

**Defensive 4 條相鄰 transition 不動**（per AMD §9.8 mitigation 理由 2）：
- Defensive → CircuitBreaker（escalation，AUTO initiator）✅
- Defensive → ManualReview（escalation，OP_GOV initiator）✅
- Defensive → Reduced（de-escalation，requires approval，OP_GOV）✅
- Defensive → Cautious（de-escalation，requires approval，OP_ONLY）✅

t4_failsafe_does_not_break_existing_de_escalation_paths 對 25 條 pair 全 assert `lookup_rule(from, to).is_some()` PASS。

## §5 cargo test --release 結果

| 範圍 | 結果 |
|---|---|
| `cargo test -p openclaw_core --lib sm::risk_gov` | **27 passed; 0 failed; 0 ignored** (20 existing + 7 new T1-T6) |
| `cargo test -p openclaw_core --lib` (full crate) | **423 passed; 0 failed; 0 ignored** |
| `cargo test -p openclaw_engine --lib` (downstream consumer crate) | **3469 passed; 0 failed; 1 ignored** |

**7 新 test 清單**：
1. `t1_notification_failsafe_timeout_variant_emits_and_handles` — variant + as_str + transition 接受
2. `t2_failsafe_escalation_from_all_lower_levels` — Normal/Cautious/Reduced 三條 → Defensive 都允許走新 event；Defensive constraints 字面對齊 spec line 478-484
3. `t3_active_lock_profit_computes_sl_with_atr_buffer` — Buy/Sell candidate + 既有 SL 保護方向 4 組
4. `t3_active_lock_profit_fail_closed_on_bad_input` — NaN/0/負 ATR/未知 side/負 buffer 7 個 invalid 倉位 + 唯一 OK 倉位
5. `t4_failsafe_does_not_break_existing_de_escalation_paths` — 25 pair 全 lookup_rule assert
6. `t5_seven_day_cooling_constant_matches_spec` — 7d = 604_800_000 ms
7. `t6_existing_24_tests_unaffected_smoke` — evaluate_risk_context / session_halted / reconciler_escalate 三條既有 path smoke

T3 計為 2 個 #[test] function（值 + fail-closed），合計新增 7 條 test。

## §6 cargo clippy result

| 範圍 | 結果 |
|---|---|
| `cargo clippy -p openclaw_core --lib --tests` 標準 lint，filter `risk_gov.rs` | **0 hit** |
| `cargo clippy -p openclaw_core --lib --tests -- -W clippy::pedantic` filter `risk_gov.rs:25[0-9]\|3[0-9][0-9]\|4[0-1][0-9]`（新代碼行範圍）| 純 doc backtick 提示（中文注釋 + symbol 名混排觸發 missing_backticks），**所有 hit 均為 cosmetic**，與既有 RiskEvent doc-comment（line 72）同類型 — 非新引入反模式 |
| `cargo clippy -- -D warnings` 全 workspace | 早於本 patch 已有 pre-existing error（`openclaw_types/src/asset_venue.rs` doc_lazy_continuation + 某 `since` field semver 不合）—**非本 patch 引入** |

無 `unwrap_used` / `panic` / `unsafe` / `expect_used` 觸發 clippy 任何等級 lint。

## §7 與 Packet A V099 衝突確認（文件路徑零 overlap）

| 文件路徑 | Packet C 本 patch | Packet A V099 |
|---|---|---|
| `srv/rust/openclaw_core/src/sm/risk_gov.rs` | ✅ EDIT | ❌ 不動 |
| `srv/migrations/V099*.sql` | ❌ 不動 | ✅ NEW |
| `srv/python/openclaw_app/db/migrations/V099*.py` | ❌ 不動 | ✅ NEW |
| `srv/python/openclaw_app/routes/governance/*` (Autonomy Posture API) | ❌ 不動 | ✅ EDIT/NEW |

**Grep 驗** `grep -nE "V099|autonomy_level_switch_audit|autonomy_level_enum" /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_core/src/sm/risk_gov.rs` = **0 hit**。

Packet C **可完全獨立 dispatch / sign-off**；不依賴 Packet A 落地，也不阻塞 Packet A。

**注意**：audit emit `notification_escalation_result='auto_escalated_to_sm04_defensive'` 寫入 `system.autonomy_level_switch_audit`（spec §9.8 第 4 條 deliverable）由 engine 層接線時 write — `openclaw_core::sm::risk_gov` 本身不直接 PG INSERT（不持有 PG handle，per 純治理層紀律）。engine 層後續 packet 接線時，在 transition 成功後負責 audit INSERT，引用本層 `NotificationFailsafeTimeout` variant + `FAILSAFE_DEFENSIVE_COOLING_MS` 常數即可。

## 治理對照

| 對照項 | 結果 |
|---|---|
| AMD §9.8 patch item 1 (RiskEvent variant) | ✅ 落地，as_str 對齊 spec |
| AMD §9.8 patch item 2 (Defensive active_de_risking hook 擴充) | ✅ `active_lock_profit_per_position` fn + ATR buffer 紀律 |
| AMD §9.8 patch item 3 (復原 7d cooling) | ✅ `FAILSAFE_DEFENSIVE_COOLING_MS` 常數 land；engine 層引用 enforce |
| AMD §Decision 2.5 fail-safe compile-time hard-coded | ✅ 純 Rust constant + fn；無 runtime TOML override 接口 |
| AMD §9.8 mitigation 理由 2「不破壞既有 35+ pair」 | ✅ t4 25 pair 全 PASS；lookup_rule 字面零變更 |
| AMD §9.8 mitigation 理由 3「不誤用 CircuitBreaker」 | ✅ Defensive constraints 既有字面不動 (emergency_stops=false 保持) |
| PA spec §4.4 line 482「保住 unrealized PnL」 | ✅ Defensive 既有 emergency_stops=false + active_de_risking=true 字面未改 |
| PA spec §4.4 line 485-487 「縮 SL 至 entry + ATR buffer」 | ✅ `active_lock_profit_per_position` 公式：`entry ± atr × buffer_multiplier` |
| PA spec §4.4 line 488「emit lease」 | ✅ StopAdjustment.reason = "active_lock_profit_triggered_by_notification_failsafe" |
| CLAUDE.md §二 原則 9 雙重防線 | ✅ 註解明文契約：engine 層必 sync 至 exchange-side conditional |
| CLAUDE.md §七 Rust 紀律（無 panic / unwrap / unsafe）| ✅ Grep 確認新代碼塊 0 hit |
| CLAUDE.md §六 跨平台 | ✅ Grep `/home/ncyu` / `/Users/ncyu` = 0 hit |
| `bilingual-comment-style` skill | ✅ 新注釋全中文；英文保留純技術 identifier（如 `ATR`, `SL`, `Buy/Sell`, `Slack/Email/Console banner`, `f64::EPSILON`）|

## 不確定之處

1. **`Side` 為 `&'static str` "Buy"/"Sell"** — 沿用 `openclaw_types::price` 的 Trade side 字串約定；若 PA / E2 認為應該升級為 enum，可在 follow-up patch 加 `pub enum Side { Buy, Sell }` import 並 mapping，但會擴大本 PR 範圍跨 module
2. **`PositionSnapshot.qty` 是否該被 hook 用** — 當前 hook 只用 qty 做 `abs() < EPSILON` 跳過空倉檢測，不參與 SL 計算；保留 qty 欄位讓 engine 層之後可在 audit emit 帶 size 信息
3. **`atr_buffer_multiplier` 預設值** — 本 hook 不持有預設；engine 層 call 時必須顯式傳；建議 engine 層用 0.5 (= half-ATR) 作為「小幅 protective buffer」default。若 PA / FA 希望本層 expose 一個 `const DEFAULT_ATR_BUFFER: f64 = 0.5`，可在 follow-up 加
4. **Audit emit 路徑** — 本層只計算 stop adjustment 值 + 不直接 INSERT `system.autonomy_level_switch_audit`（純治理層不持 PG handle）；engine 層在 transition 觸發 + 取走 StopAdjustment 後負責 audit INSERT。若需要 strong 紀錄保證在 transition 成功的同 transaction 內 INSERT audit，需在 engine 層 wrap atomic write — Packet B 或後續 engine 接線 packet 處理
5. **35+ pair 與 25 pair 數字差距** — spec text 寫「35+ pair」，實際 lookup_rule 含 25 explicit pair（15 escalation + 10 de-escalation）。本 patch 不調整 spec text；t4 regression 對 25 pair 全 verify。建議 PA 在 spec follow-up 對齊到「25 explicit pair」精確數字

## Operator 下一步

1. E2 code review：
   - 對 `active_lock_profit_per_position` fail-closed 紀律對齊 CLAUDE.md §二 原則 6
   - 對新 RiskEvent variant doc-comment 是否充分（為什麼存在 / 觸發條件 / 不變量）
   - 對 25 pair regression 是否替代「35+」spec 文字（PA + E2 拍板）
   - 反模式 grep 重做：`runtime_failsafe_override` / `disable_failsafe` / `unwrap()` / `panic!` / `unsafe` 在新代碼塊 = 0
2. E4 regression：
   - 重跑 `cargo test -p openclaw_core --lib` + `cargo test -p openclaw_engine --lib` 確認 0 regression
   - 新增 3 個 integration test 對齊 spec §12 AC（engine 層三路通知 mock 全 fail → 1h timeout → emit `RiskEvent::NotificationFailsafeTimeout` → transition Defensive → call `active_lock_profit_per_position` → assert StopAdjustment Vec 非空）
3. A3 + E2 adversarial review（per `feedback_impl_done_adversarial_review`）：本 IMPL 屬 high-risk Rust IPC / 共用 helper 類；需第二輪對抗式核驗確認 fail-closed 紀律完整
4. CC walkthrough 16 根原則（#3 AI → Lease → 復核 / #4 strategy 不繞 Guardian / #9 雙重防線 / #11 Agent autonomy 邊界）
5. PM 等 Packet A V099 land 後統一 commit `feat(sm-04): NotificationFailsafeTimeout RiskEvent + Defensive active_lock_profit hook` + push（per AMD §9.8 sign-off chain）

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--wave_5_packet_c_rust_sm04_impl.md）
