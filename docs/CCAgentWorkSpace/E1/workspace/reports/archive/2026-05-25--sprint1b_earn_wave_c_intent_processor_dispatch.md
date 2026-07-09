---
report: Sprint 1B Earn Wave C — IntentProcessor Earn branch dispatch IMPL
date: 2026-05-25
author: E1 (Backend Developer, Rust)
phase: Sprint 1B Earn Wave C — IMPL DONE 待 E2 review
status: cargo build --release PASS 26.32s + cargo test --release --workspace +10 new PASS (4135 → 4145) / 1 pre-existing FAIL (W2-IMPL-5 stalled)
parent dispatch: PM Wave C dispatch (operator prompt 2026-05-24)
runtime: Mac development (cargo check + cargo build --release + cargo test --release --workspace --no-fail-fast)
production engine: 未碰
---

# §0. TL;DR

Sprint 1B Earn Wave C 接線 IntentProcessor Earn dispatch branch。新增 `earn_router.rs` (703 LOC) 含 `EarnRouter::dispatch_earn_intent()` async entry，9 個 fail-closed gate（E-0..E-9）+ EarnLeaseGuard RAII；改 IntentProcessor mod.rs (+2 field + 兩 setter + `process_earn_intent` async method 經 cross-file impl block extension at earn_router.rs)；改 router.rs (`process_with_features` + `process_gates_only_with_features` 入口加 Gate 0 `is_earn()` short-circuit reject)。+4 dispatch test + 6 earn_router internal unit test 全 PASS。0 carry-over `OPENCLAW_ALLOW_MAINNET` /  hard-coded path / panic / unwrap。

# §1. 修改清單

| 檔案 | 動作 | LOC |
|---|---|---|
| `rust/openclaw_engine/src/intent_processor/earn_router.rs` | **新建** — EarnRouter dispatch + EarnLeaseGuard + cross-file IntentProcessor impl block + 6 unit test | +703 |
| `rust/openclaw_engine/src/intent_processor/mod.rs` | `mod earn_router;` + 2 field (bybit_earn_client / earn_movement_writer) + 2 ctor 更新 + setter & method comment marker | +21 / -75 (net -54) |
| `rust/openclaw_engine/src/intent_processor/router.rs` | `process_with_features` + `process_gates_only_with_features` 入口 Gate 0 `is_earn()` short-circuit reject（不破現有 trade-path） | +27 |
| `rust/openclaw_engine/src/intent_processor/tests_sprint1b_earn.rs` | +4 dispatch test（2 sync trade-path guard + 2 async process_earn_intent fail-closed） | +241 |

**淨變動**：4 file，+992 / -75 = +917 LOC（含新 file 703 LOC）。

# §2. 設計核心

## 2.1 為什麼 sync `process()` + async `process_earn_intent()` 兩入口

`process_with_features` 是 sync `&self` trading hot-path（既有 caller 鏈：tick_pipeline → strategies → IntentProcessor）；Bybit Earn API 是 async（reqwest::Client）。三選一：
- (a) **採用**：sync entry short-circuit reject + 新 async entry `process_earn_intent` — surgical，0 破現有 trade-path caller
- (b) `process_with_features` 改 async — 破所有 caller signature
- (c) `block_on()` 在 sync 內 — 反 pattern，破 tokio scheduler 假設

選 (a) + Gate 0 短路：caller 誤把 Earn intent 送 trade-path 立即 reject + 提示走 `process_earn_intent`；反之亦然（earn_router 內 Gate E-2 redundant check 拒絕非 Earn variant）。

## 2.2 5-gate inheritance 對齊

| Gate | 對映 ADR-0030 / earn_governance | IMPL 位置 |
|---|---|---|
| E-0 capability wiring | client/writer 未注入 = capability OFF | earn_router.rs:217-235 |
| E-1 earn_payload Some | earn_governance §3.2 7 field | :238-246 |
| E-2 intent_type is_earn (defence) | invariant guard | :250-254 |
| E-3 governance auth | 5-gate Gate a | :257-259 |
| E-4 lease acquire | LeaseScope::EarnStake/EarnRedeem 60s TTL | :262-285 |
| E-5 amount parse | f64 finite > 0 | :289-307 |
| E-6 INSERT placeholder | earn_governance §2.5 兩階段 | :320-340 |
| E-7 Bybit place-order | subscribe/redeem flexible | :344-368 |
| E-8 UPDATE outcome 'matched' | Bybit ack OK | :371-410 |
| E-9 write_failure 'mismatch' | earn_governance §5.1 + release Failed | :413-475 |

5-gate Gate b `OPENCLAW_ALLOW_MAINNET=1` 由 BybitRestClient 構造時把關（Earn 走 Demo/LiveDemo 端點時不觸 Gate b；client 已是有效 instance）。

## 2.3 EarnLeaseGuard RAII 範式

對齊 router.rs::RouterLeaseGuard 範式：
- 成功 `consume_ok()` → release Consumed
- Bybit / writer fail `consume_failed()` → release Failed
- earn_payload absent / writer placeholder fail → guard 未 consume，Drop 自動 release Cancelled

確保 acquire 成功的 lease **永必** release（避 leak）。

## 2.4 governance_approval_id carry-over (Wave D/E)

EarnIntentPayload.approval_id 是 String UUID（per packet §3.2），但 EarnMovementWriter 接 i64 (PA-DRIFT-6 soft ref BIGINT)。本 IMPL 占位寫 `0`，文檔化於 earn_router.rs:316-322 + report §6 carry-over，留 Wave D/E 補「先 INSERT governance_audit_log RETURNING id」chain。

# §3. 驗證結果

| Verify | Command | Result |
|---|---|---|
| cargo check lib | `cargo check -p openclaw_engine --lib` | **PASS 6.58s** (0 new warning) |
| Release build | `cargo build --release -p openclaw_engine` | **PASS 26.32s** (engine bin 重建 0 error) |
| 新 earn_router unit test | `cargo test --release -p openclaw_engine --lib intent_processor::earn_router` | **6/6 PASS** |
| 新 dispatch test | `cargo test --release -p openclaw_engine --lib intent_processor::tests::earn_router_fail_closed / intent_processor_dispatches_earn / trade_intent_unaffected` | **4/4 PASS** |
| **全工作區** | `cargo test --release --workspace --no-fail-fast` | **4145 PASS / 1 FAIL pre-existing / 5 ignored** (round 2 baseline 4135 → 4145 = +10 new) |

1 pre-existing FAIL = `layer_2_fence_archive_policy_diagnostic_only` (tests/btc_lead_lag_panel_fence_integration.rs:300)：W2-IMPL-5 stalled sub-agent collateral，**與本 IMPL 0 耦合** (0 動 panel_aggregator / 0 動 main.rs / 0 動 env-var 解析)。

# §4. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 max_retries / live_execution_allowed / execution_authority / system_mode / production engine / V### SQL ✓ |
| **§七 Code And Docs Rules** | 新代碼注釋全中文；無 emoji；earn_router.rs 含 MODULE_NOTE + 主要類函數 + 依賴 + 硬邊界 + 不變量 + 規格參照 ✓ |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 review；不自行 commit；不派下游 sub-agent ✓ |
| **§九 Code Structure Guardrails** | earn_router.rs 703 LOC < 800 ✓；mod.rs 1968 LOC < 2000 ✓ (cross-file impl 釋放 75 LOC); router.rs 1220 LOC (pre-existing > 800，本 IMPL 僅 +27 不破) |
| **§跨平台兼容性** | grep `/home/ncyu` `/Users/[^/]` 0 命中 ✓ |
| **§安全代碼規範** | 0 panic / 0 unwrap / 0 expect 在 hot path；EarnDispatchError thiserror 7 variant；BybitApiError 4 分支映射 ret_code ✓ |
| **bilingual-comment-style** | 新代碼注釋全中文；觸及既有 bilingual block 不主動清；安全 / fail-closed 路徑全帶中文 rationale ✓ |
| **5-gate inheritance** | E-0..E-9 全 fail-closed，每 gate 帶中文 spec 引用 ✓ |

# §5. Self-check 反模式

| 自檢項 | 結果 |
|---|---|
| (a) Earn intent 走 trade-path 不被靜默 dispatch | ✓ Gate 0 reject "earn_intent_routed_to_trade_path" + 對抗性 test 驗 |
| (b) Earn capability 未接 dep 不 silent no-op | ✓ Gate E-0 fail-closed reject "earn_dispatch_unwired" + test 驗 |
| (c) earn_payload absent 不嘗試 Bybit call | ✓ Gate E-1 在 Bybit call 前 fail-closed |
| (d) acquire 的 lease 不 leak | ✓ EarnLeaseGuard RAII Drop 自動 Cancelled + consume_ok / consume_failed 路徑 |
| (e) Bybit fail 必有 audit row | ✓ Gate E-9 write_failure mismatch row + Daily cron 對賬 |
| (f) writer placeholder fail 不做 Bybit call | ✓ Gate E-6 fail → return early，避免「Bybit 已 ack 但 audit 缺 row」 |
| (g) writer update fail（Bybit 已 ack）alert | ✓ Gate E-8 tracing::error + release Failed + return reject |
| (h) trade-path 不被 Gate 0 影響（regression guard） | ✓ test `intent_processor_trade_intent_unaffected_by_earn_branch` PASS |

# §6. 不確定之處 / Push back

**1 設計 carry-over (Wave D/E 必補)**：
- **governance_approval_id 占位 i64=0**：EarnIntentPayload.approval_id (String UUID) → EarnMovementWriter.governance_approval_id (i64 soft ref BIGINT)；本 IMPL 寫 sentinel 0。文檔化於 earn_router.rs:316-322。Wave D/E IMPL 應補：
  1. 先 INSERT `learning.governance_audit_log` 取 RETURNING id；
  2. 把 id 注入本 dispatch；
  3. earn_movement_log 行寫真實 soft ref。

**0 push back 設計決策**：
- 分 sync trade-path + async Earn entry 是 surgical 必須選擇（理由見 §2.1）；
- EarnLeaseGuard 對齊 RouterLeaseGuard 範式；
- Gate 順序 (E-0 capability → E-1 payload → E-2 intent_type → E-3 auth → E-4 lease → E-5 amount → E-6 placeholder → E-7 Bybit → E-8/E-9 outcome) 是 spec 順序 + fail-fast 原則。

**1 test 折衷**：`earn_router_fail_closed_when_earn_payload_missing` 在 mac dev unwired 環境下實際命中 Gate E-0 (capability OFF) 而非 E-1 (payload missing)；test 寬容驗兩者之一。真實 Gate E-1 直接命中需注入 dep (real Bybit + PG) — 違 mac dev local-only constraint。**留 Wave D/E integration test 補 (per §7 next step #4)**。

# §7. Operator 下一步 (carry-over to Wave C 後續)

1. **PM 派 E2 review**（focus: 5-gate inheritance 完整性 / EarnLeaseGuard Drop release 三路徑 / governance_approval_id carry-over 是否可接受 sentinel 0）；
2. **PM 派 E4 regression**（4145 PASS baseline 對齊 + Earn dispatch path Linux PG empirical test）；
3. **PA Wave D 接力**：補「先 INSERT governance_audit_log → process_earn_intent」chain（解 governance_approval_id sentinel 占位）；
4. **PA Wave D integration test**（mac mock 之外的真實 PG / Bybit demo end-to-end）；
5. **QA Stage 0R replay**（Earn dispatch path 不直接走 replay harness，但 5-gate fail-closed paths 應 covered by 既有 replay 範式）；
6. **OP-1 operator action**（per dispatch packet §1.2 OP-1 < 2026-04-09 路徑）：
   - Bybit Web 重發 API key 加 Earn scope；
   - 三端同步 OpenClaw secret slot；
   - restart engine + smoke 驗 `get_flexible_products("USDT")` 不返 retCode 10005 PermissionDenied；
7. **operator 親手 OP-1 後** first stake **不在本 task 範圍**；不可 deploy / restart engine。

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--sprint1b_earn_wave_c_intent_processor_dispatch.md`）**
