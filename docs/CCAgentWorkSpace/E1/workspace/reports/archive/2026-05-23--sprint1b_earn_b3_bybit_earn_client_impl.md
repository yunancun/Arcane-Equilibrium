---
report: E1 Sprint 1B Earn Wave B B3 — bybit_earn_client.rs Flexible-only IMPL
date: 2026-05-23
author: E1
phase: Sprint 1B Pending 3.2 Earn first stake — Wave B B3 IMPL DONE / 待 E2 + E4 sign-off
status: IMPL-DONE-AWAITING-E2-E4-PM
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md §2 + §4
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint1b_earn_b2_lease_scope_variant_impl.md (B2 並行 IMPL)
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint1b_earn_b5_reconciliation_cron_impl.md (B5 並行 IMPL)
not in scope:
  - 不 IMPL `IntentType::EarnStake` / `IntentType::EarnRedeem` enum 接線（B1 並行 E1a 範圍）
  - 不 IMPL `EarnMovementWriter` V100 writer（B4 並行 E1d 範圍）
  - 不 IMPL Daily reconciliation cron 主邏輯（B5 並行 E1e 範圍，已 land per B5 report）
  - 不 IMPL IntentProcessor Earn 分支接線（B6 後續 wave）
  - 不接 real Bybit endpoint（OP-1 API key 重發前不可；mock-only per dispatch packet 拍板）
  - 不 commit；待 E2 review → E4 → PM 統一
---

# E1 Sprint 1B Earn Wave B B3 — bybit_earn_client.rs Flexible-only IMPL

## §1 任務摘要

Per PA dispatch packet `2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md` §2（Bybit Earn endpoint client）+ §4（bybit_rest_client.rs RateLimitGroup patch），同 OP-3 拍板「Flexible Saving only / fixed staking defer Sprint 5+」+ OP-1 拍板「API key 重發前不接 real Bybit endpoint」，B3 IMPL 範圍鎖定 **5 個 flexible-only endpoint Rust client + RateLimitGroup 對映 patch + mock unit test**。

5 個 endpoint 對應 dispatch packet §1.2.1：
- E-1 GET `/v5/earn/product` (Flexible Saving 產品列表)
- E-2 POST `/v5/earn/place-order` orderType=Stake (subscribe / first stake 主寫)
- E-3 POST `/v5/earn/place-order` orderType=Redeem (margin headroom 強制 redeem)
- E-4 GET `/v5/earn/position` (Daily reconciliation cron + post-stake verify)
- E-5 GET `/v5/earn/apr-history` (ML drift detection；Sprint 2+ 用)

關鍵 IMPL 設計：共用既有 `BybitRestClient` 走 signed `get_checked` / `post_checked`（HMAC-SHA256 + rate limit + retCode 4xx/5xx 觀測自動繼承），不重複 HTTP / 簽名 / 觀測邏輯；對齊 `bybit_rest_client.rs` 1376 LOC 範式 + PA-DRIFT-4 round 1 H-3 fix 教訓。

---

## §2 修改清單

### 2.1 新檔

| 路徑 | LOC | 摘要 |
|---|---|---|
| `srv/rust/openclaw_engine/src/bybit_earn_client.rs` | 601 | Bybit V5 Earn API client — Flexible Saving only / 5 endpoint method + 5 response struct + 1 request struct + 10 mock unit test |

### 2.2 修改檔

| 路徑 | 行範圍 | 改動類型 | 摘要 |
|---|---|---|---|
| `srv/rust/openclaw_engine/src/lib.rs` | line 14-17 | mod 註冊 + 註釋 | `pub mod bybit_earn_client;` + 3 行 module purpose comment |
| `srv/rust/openclaw_engine/src/bybit_rest_client.rs` | line 240-260 | RateLimitGroup::from_path 擴 `/v5/earn/` → Asset | 對齊 BB C4 verdict + tiagosiebler SDK 註釋「5 req/s」rate limit |
| `srv/rust/openclaw_engine/src/bybit_rest_client_tests.rs` | line ~286-309 | test 補 5 `/v5/earn/` 路徑 assertion | 防 path drift；對齊 OP-3 flexible-only 拍板實際接的 5 endpoint |

---

## §3 關鍵設計決策（diff highlights）

### 3.1 重要 Bybit V5 path 校正（vs PA dispatch packet）

PA dispatch packet §1.2.1 列「/v5/earn/flexible/*」路徑屬 **2025 舊 Bybit V5 spec**。tiagosiebler 2026 reference SDK（`rest-client-v5.ts` line 4117-4370）顯示 Bybit V5 **已 unified** 為：

| dispatch packet 列 | 真實 Bybit V5 (2026) | 差異 |
|---|---|---|
| `/v5/earn/flexible/product` GET | `/v5/earn/product` GET (param: category=FlexibleSaving) | 路徑統一不分 flexible/fixed |
| `/v5/earn/flexible/subscribe` POST | `/v5/earn/place-order` POST (orderType=Stake) | stake/redeem unified endpoint |
| `/v5/earn/flexible/redeem` POST | `/v5/earn/place-order` POST (orderType=Redeem) | 同上 |
| `/v5/earn/flexible/position` GET | `/v5/earn/position` GET | 路徑統一 |
| `/v5/earn/apr-history` GET | `/v5/earn/apr-history` GET | 對齊 |

本 IMPL 採真實 2026 path；MODULE_NOTE 明列對映表 + 端點對齊註釋（line 32-44）防 BB / E2 review 誤判「路徑改了」。

### 3.2 OP-3 拍板 Flexible-only 落地：常數固化

```rust
// 為什麼是常數而非 caller 傳值：Sprint 1B 範圍鎖定 FlexibleSaving；fixed staking
// (OnChain / FixedTerm) defer Sprint 5+。caller 不應有自由度走非 flexible path。
const CATEGORY_FLEXIBLE_SAVING: &str = "FlexibleSaving";
const ACCOUNT_TYPE_UNIFIED: &str = "UNIFIED";
```

5 endpoint method 全部 hardcoded `category=FlexibleSaving`；test `test_category_and_account_type_constants` 鎖定字面值防漂移。fixed staking 路徑要在 Sprint 5+ 開新 method 顯式分流。

### 3.3 stake/redeem 統一 endpoint 但分兩 method

Bybit V5 已 unified `/v5/earn/place-order` 帶 `orderType` discriminator，但本 IMPL 仍分 `subscribe_flexible()` / `redeem_flexible()` 兩 Rust method：

```rust
pub async fn subscribe_flexible(&self, coin, product_id, amount, order_link_id) -> ... {
    let body = PlaceOrderRequest { order_type: "Stake", ... };
    // ...
}

pub async fn redeem_flexible(&self, coin, product_id, amount, order_link_id) -> ... {
    let body = PlaceOrderRequest { order_type: "Redeem", ... };
    // ...
}
```

設計理由：上層 `IntentType::EarnStake` / `IntentType::EarnRedeem` 兩 enum variant 對映兩 Rust method 邊界清晰；caller 端不需自行傳 `"Stake"` / `"Redeem"` 字串污染 audit chain。`order_type` field 為 `&'static str` 在 build time 鎖死字面值。

### 3.4 共用 BybitRestClient `get_checked` / `post_checked` 不重複

```rust
pub struct BybitEarnClient {
    rest_client: Arc<BybitRestClient>,  // 共用既有 HMAC + rate limit + retCode 觀測
}

pub async fn get_flexible_products(&self, coin: &str) -> BybitResult<FlexibleProductListResult> {
    let params = [("category", CATEGORY_FLEXIBLE_SAVING), ("coin", coin)];
    let resp = self.rest_client.get_checked(PATH_EARN_PRODUCT, &params).await?;
    serde_json::from_value::<FlexibleProductListResult>(resp.result)
        .map_err(BybitApiError::JsonParse)
}
```

- 0 重複 HTTP / 簽名 / rate limit 邏輯（per `bybit_rest_client.rs` 1376 LOC 範式）
- retCode != 0 fail-closed 由 `get_checked` / `post_checked` 自動處理（per into_result() 走 `BybitApiError::Business`）— 對齊 9 不變量 #7
- 4xx / 5xx 計數自動 record（per PA-DRIFT-4 round 1 H-3 fix；計數下沉至 `get` / `post` 內部即覆蓋 raw caller 流量）
- 即使 `/v5/earn/product` 與 `/v5/earn/apr-history` 是公開 endpoint（無需 auth），本 IMPL 仍走 signed path **不繞觀測**

### 3.5 RateLimitGroup::from_path patch（5 行）

```rust
} else if path.starts_with("/v5/asset/")
    || path.starts_with("/v5/spot-margin")
    || path.starts_with("/v5/earn/")  // 新增
{
    Self::Asset
}
```

- 對齊 BB C4 verdict + tiagosiebler SDK 註釋「Rate limit: 5 req/s」
- Asset rate limit group 初始 remaining = 5（per `RateLimitState::default()` line 280；對齊 Bybit V5 Asset group 規範）
- test 補 5 `/v5/earn/` 路徑 assertion（product / place-order / order / position / apr-history）

### 3.6 Response struct `String` 載荷避免 rust_decimal 依賴

Bybit V5 spec 對 numeric field（amount / apr / pnl / timestamp）統一回字串避免浮點誤差。本 IMPL serde 設計：

```rust
pub struct FlexibleProduct {
    pub estimate_apr: String,    // "0.1023" (10.23%)
    pub min_stake_amount: String,
    pub max_stake_amount: String,
    pub precision: String,
    // ...
}
```

設計理由：
- `rust_decimal` 不在 `openclaw_engine` Cargo deps（verified `Cargo.toml` line 8-39）；不引入新依賴
- caller 端（下游 `EarnMovementWriter` B4 + reconciliation cron B5）負責 parse + precision validate
- `status` field 用 `String` 不做 enum，避免 Bybit 未來加新狀態（e.g. "Maintenance"）造成 panic-on-unknown（test `test_flexible_product_unknown_status_does_not_panic` 鎖定此語意）

### 3.7 idempotency key 強制 caller 傳

```rust
pub async fn subscribe_flexible(
    &self,
    coin: &str,
    product_id: &str,
    amount: &str,
    order_link_id: &str,  // <- caller 強制傳
) -> BybitResult<PlaceOrderResult>
```

設計理由：
- Bybit V5 `/v5/earn/place-order` 強制要求 `orderLinkId`（per SDK 註釋）
- caller 端應對映 `lease_id` 或 `authorization.json` UUID（per earn_governance §3.2 + W-AUDIT-9 LeaseScope 設計），確保 audit chain 可 reconstruct
- 本 client 端不驗 UUID 格式 / 不生成 default — 強制 audit 對映責任在 caller

### 3.8 PA dispatch packet 預估 vs 實際 LOC

| 項目 | PA 預估 | 實際 | 差異原因 |
|---|---|---|---|
| LOC | 400-500 | 601 | (1) 10 mock unit test 增 ~190 LOC (2) 完整 MODULE_NOTE + endpoint 對映表增 ~50 LOC (3) 每 method doc-comment 完整中文 rationale + safety invariant 增 ~50 LOC |
| Method 數 | 5（OP-3 flexible-only 縮 vs 12） | 5 | 對齊 |
| Response struct 數 | 5 | 5 + 3 list wrapper (`FlexibleProductListResult` / `FlexiblePositionListResult` / `AprHistoryResult`) | Bybit V5 response 走 `{list: [...]}` wrap pattern |

---

## §4 治理對照

| 維度 | 對齊狀態 | 證據 |
|---|---|---|
| `OPENCLAW_ALLOW_MAINNET` 5-gate | ✅ 不繞 | 共用 `BybitRestClient` 已含 LIVE-GUARD-1 三門（line 887-961）；本 client 0 新增 main-net bypass path |
| retCode != 0 fail-closed 不重試 | ✅ 強制 | 走 `get_checked` / `post_checked` 自動 propagate `BybitApiError::Business`；caller 端必須處理 Err 不繞 |
| Rate limit group 對齊 | ✅ Asset 5 req/s | `RateLimitGroup::from_path` patch + test 5 路徑 assertion |
| audit observability | ✅ 自動繼承 | 4xx / 5xx 觀測 + latency histogram 自動 record（per PA-DRIFT-4 round 1 H-3 fix） |
| 跨平台兼容 | ✅ PASS | 0 硬編碼 `/home/ncyu` / `/Users/ncyu`；secret slot 走既有 `read_secret_file()` HOME / OPENCLAW_SECRETS_DIR 機制 |
| 文件 LOC | ✅ PASS | 601 LOC < 800 行警告 + < 2000 行硬上限 |
| MODULE_NOTE | ✅ PASS | line 1-46 完整中文 4 section + endpoint 對映表 + 硬邊界 4 條 |
| 注釋規範 | ✅ 中文為主 | 0 emoji；每 method doc-comment 含「為什麼」rationale；technical term（field 名 / Bybit V5 path）保留英文 |
| 不擴大 PA 範圍 | ✅ PASS | 0 改動 4 既有策略 / IntentProcessor / EarnMovementWriter / IntentType enum（全 B1 / B4 / B5 並行 owner） |

---

## §5 驗證結果

### 5.1 cargo build --release

```
$ cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
$ cargo build --release 2>&1 | tail -5
warning: `openclaw_engine` (lib) generated 2 warnings (run `cargo fix --lib -p openclaw_engine` to apply 1 suggestion)
warning: `openclaw_engine` (bin "openclaw-engine") generated 1 warning
    Finished `release` profile [optimized] target(s) in 35.69s
```

- 0 error
- 2 warnings 為 pre-existing dead_code（`spawn_position_reconciler` in tasks.rs:795 / `LEAD_WINDOW_SECS_MAIN` in panel_aggregator/btc_lead_lag/db_writer.rs:13）— 不在 B3 引入

### 5.2 cargo test --release --lib bybit_earn_client

```
running 10 tests
test bybit_earn_client::tests::test_category_and_account_type_constants ... ok
test bybit_earn_client::tests::test_endpoint_path_constants ... ok
test bybit_earn_client::tests::test_empty_list_does_not_panic ... ok
test bybit_earn_client::tests::test_apr_history_round_trip ... ok
test bybit_earn_client::tests::test_flexible_position_full_fields ... ok
test bybit_earn_client::tests::test_flexible_product_serde_round_trip ... ok
test bybit_earn_client::tests::test_place_order_request_serialization ... ok
test bybit_earn_client::tests::test_flexible_position_optional_fields ... ok
test bybit_earn_client::tests::test_flexible_product_unknown_status_does_not_panic ... ok
test bybit_earn_client::tests::test_place_order_result_round_trip ... ok

test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured; 3320 filtered out; finished in 0.00s
```

**10/10 PASS**。Test 範圍覆蓋：
- 6 個 response serde round-trip（含 unknown status / empty list / optional field 缺失邊界）
- 1 個 request 序列化 camelCase 驗證（防 Bybit V5 簽名 field 漂移）
- 2 個 constants 字面值（防 path / category drift）
- **0 個接 real Bybit endpoint**（per OP-1 拍板）

### 5.3 cargo test --release --lib bybit_rest_client

```
test result: ok. 29 passed; 0 failed; 0 ignored; 0 measured; 3301 filtered out; finished in 0.20s
```

**29/29 PASS**（含新增 5 個 `/v5/earn/` RateLimitGroup assertion 在 `test_rate_limit_group_from_path`）。Patch 0 regression。

### 5.4 E1a 並行 PR observability

Build 第一輪曾遇 commands.rs / on_tick_helpers.rs `OrderIntent` literal missing `intent_type` / `earn_payload` field（line 195 / line 180）。stash B3 改動後驗證 lib build PASS — 證明這是 **E1a 並行 PR 已 land 但 caller 同步補在進行中**。二輪重 build（恢復 B3 改動）後 0 error，證明 E1a caller 補丁與 B3 IMPL 同步 land；**B3 IMPL 0 引入 caller 影響**。

---

## §6 不確定之處 / E2 重點

### 6.1 重點 #1 — Path 校正可能影響下游 spec

PA dispatch packet §1.2.1 + earn_governance §1.1 列「/v5/earn/flexible/*」舊路徑；本 IMPL 採真實 2026 path。下游：
- BB Wave C review 必須對齊本 IMPL 真實 path 不誤判
- earn_governance spec §1.1 line 列「12 endpoint」實際 unified 後可能少 1-2 個（fixed-related subscribe/redeem 統一到 `place-order`）
- 建議 PA 後續 wave 同步 spec 文檔 → real path / unified endpoint pattern

### 6.2 重點 #2 — String 載荷 amount/apr 下游 parse 責任邊界

本 IMPL 全用 String 載荷 numeric field 避免 rust_decimal 依賴；caller 端必須：
- 對 `FlexibleProduct.precision` 字串四捨五入 `amount` 字串再傳 `subscribe_flexible()`
- 對 `EarnPosition.totalPnl` / `claimableYield` parse 為 Decimal（B4 EarnMovementWriter 範圍）
- 對 `AprHistoryPoint.apr` parse 為 f64（B5 reconciliation cron + Sprint 2+ ML drift 範圍）

E2 review 應驗 caller 端（B4 / B5 IMPL）有沒漏這個 parse + precision validate。

### 6.3 重點 #3 — `order_link_id` 強制 caller 傳但 client 不驗 UUID

本 client 不驗 `order_link_id` 格式 / 不生成 default；caller 端責任：
- B6 IntentProcessor Earn 分支接線（後續 wave）必須在 5-gate Gate b 取 `authorization.json.id` UUID 或 `lease_id` 作為 `order_link_id`
- 若 caller 傳空字串 → Bybit V5 retCode 10001 InvalidParam → `BybitApiError::Business` fail-closed（不重試）
- 建議 E2 review 補一條「caller 必傳非空 order_link_id」test fixture 在 B6 IMPL 範圍

### 6.4 重點 #4 — RateLimitGroup::Asset 與既有 `/v5/asset/` 共享 5 req/s 槽位

`RateLimitState.group_remaining[Asset]` 是單一 AtomicI64；`/v5/earn/*` 5 endpoint + 既有 `/v5/asset/transfer/*` + `/v5/spot-margin*` 全共享同一 5 req/s 預算：
- Daily reconciliation cron（B5）走 `get_flexible_positions` + `get_unified_position`（B4 W-AUDIT-9 預留）會與既有 Asset endpoint 競爭
- earn_governance §11 RISK-3 已列「Bybit Earn rate limit 衝突」風險；B5 cron 預設 02:00 UTC 避 funding settlement 但仍可能撞 `/v5/asset/transfer/inter-transfer` 同槽
- E2 / BB review 應驗 B5 cron 是否需加 jitter（隨機 ±30 min）+ retry-after-backoff

### 6.5 重點 #5 — `category=FlexibleSaving` 鎖定字面值是否阻 future fixed staking

OP-3 拍板 flexible-only / fixed staking defer Sprint 5+；本 IMPL `CATEGORY_FLEXIBLE_SAVING` 是 `const &str` 全 5 method hardcoded。Sprint 5+ 開 fixed staking 路徑時必須：
- 新增 `BybitEarnFixedClient` 或同 client 加 `category: &str` 參數（破壞既有 5 method signature）
- 評估後決定：建議走「新 client」路徑保 flexible API 邊界清晰

E2 review 不必擋此 — defer Sprint 5+ 評估。

---

## §7 Operator 下一步

### 7.1 Wave B 同 PR 並行 IMPL 狀態

| Sub-task | Owner | 狀態 |
|---|---|---|
| B1 IntentType enum + OrderIntent extension | E1a | DONE per `intent_processor/mod.rs` line 73-247 grep verify |
| B2 LeaseScope EarnStake/EarnRedeem variant | E1b | DONE per `2026-05-23--sprint1b_earn_b2_lease_scope_variant_impl.md` |
| **B3 bybit_earn_client.rs Flexible-only** | **E1c (本報告)** | **DONE** |
| B4 EarnMovementWriter V100 writer | E1d | PENDING |
| B5 earn_reconciliation cron | E1e | DONE per `2026-05-23--sprint1b_earn_b5_reconciliation_cron_impl.md` |
| B6 IntentProcessor Earn 分支接線 | E1f | PENDING (depends on B4 + B3) |
| B7 GUI Earn governance tab | E1a-GUI | DEFER W+2 (per dispatch packet §7.3) |

### 7.2 E2 adversarial review dispatch ready

per `feedback_impl_done_adversarial_review` Sprint 1B Wave C 應派 E2 + BB + A3 三方並行核驗：

**E2 重點**（per §6）：
- 5 endpoint path 與 BB C4 verdict 對齊（path 校正影響）
- String 載荷下游 parse 責任邊界（caller 端責任清晰否）
- `order_link_id` 強制 caller 傳但 client 不驗格式
- RateLimitGroup::Asset 5 req/s 槽位共享風險（B5 cron 衝突）
- 5 endpoint 全走 signed `get_checked` / `post_checked` 不繞觀測（per PA-DRIFT-4 H-3 fix 對齊）

**BB 重點**：
- 5 endpoint path + scope + rate limit group 對齊 Bybit V5 2026 spec
- ToS / KYC / 地理 / mainnet boundary 不違反
- earn_governance §11 RISK-3 rate limit 衝突風險最終 verdict

**A3 重點**：
- 不擴大 PA dispatch packet 範圍 — 0 修改 既有策略 / IntentProcessor / EarnMovementWriter
- 注釋默認中文 + technical term 保留英文（per skill `bilingual-comment-style`）
- 0 hard-coded credentials / 0 bypass path / 0 emoji

### 7.3 E4 regression

- cargo test workspace 全 lib + integration
- B5 reconciliation cron + B2 LeaseScope variant + B3 earn_client 三方 0 regression
- E1a OrderIntent struct extension 對既有 4 strategy + IPC consumer 0 行為差驗證

### 7.4 PM 統一 commit

待 E2 + A3 + E4 + BB 全 ✅ APPROVE 後，PM 統一 commit Wave B 全部 sub-task land 至 srv main branch。

### 7.5 production deploy gap（OP-1 ≤ 2026-04-09 key 重發）

Wave E operator 親手 first stake 前必先（順序）：
1. Bybit Web → API management → 查既有 key「Last edited」≥ 2026-04-09 OR 重發 key 加 `Earn` permission（per dispatch packet §9.1 OP-1）
2. 三端同步：`secret_files/bybit/{slot}/api_key` + `api_secret` + `bybit_endpoint`（`live` 或 `demo` slot 對映 first stake 目標環境）
3. `bash helper_scripts/restart_all.sh --rebuild` 重建 engine binary
4. smoke 驗 `get_flexible_products("USDT")` 不返 retCode 10005 PermissionDenied / 10003 ApiKeyInvalid

---

**E1 IMPLEMENTATION DONE: 待 E2 審查**

Report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint1b_earn_b3_bybit_earn_client_impl.md`
