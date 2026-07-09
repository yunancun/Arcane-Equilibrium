# E1 — LG-2 T4 RiskConfig [pricing] section + hot-reload

Date: 2026-05-11
Owner: E1
Wave: Sprint N+1 Wave 2.2 LG-2 T4
Status: IMPL DONE — 待 E2 審查 / E4 regression

PA tech plan SoT: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §2.4 表 T4

---

## 1. 任務摘要

LG-2 T4 = 將 24h pricing freshness gate 配置（max_age_warn / max_age_fail /
cold_default_acceptable_modes）從 LG-3 RFC 散落硬編碼（healthcheck `[45]`
86400s + RFC 文檔 60min warn）統一為 RiskConfig 一級欄位，經 ArcSwap 熱重載。

範圍嚴格 T4：
- `openclaw_types::risk::PricingConfig` 新 struct + validate + 8 unit test
- `openclaw_engine::config::risk_config::RiskConfig::pricing: Option<PricingConfig>`
- 3 個 `risk_config*.toml` 加 `[pricing]` section（per env 不同 default）
- RiskConfig::validate() 整合 PricingConfig invariant check
- 8 個 RiskConfig 層整合測試 + 1 個實 TOML smoke test

不做：
- ❌ LG-2 T1 (contract tests) / T2 (startup assertion) / T3 (FeeSource enum)
- ❌ `pipeline_config.rs` apply_risk_snapshot RMW 邏輯改動（PricingConfig
  為 passive read-only field，無 tick hot-path 消費者）
- ❌ 不發 commit / 不部署

---

## 2. 必要 push back（PA plan 與代碼真實狀態 drift）

### Push back 1：「4 個 TOML」應為「3 個 TOML」

PA plan §2.4 表 T4 寫 `risk_config*.toml × 4 加 [pricing] section（paper /
demo / live_demo / live）`，但代碼真實狀態：

```bash
$ ls settings/risk_control_rules/risk_config*.toml
risk_config.toml          # legacy fallback（per startup/mod.rs:196-203）
risk_config_paper.toml    # paper engine
risk_config_demo.toml     # demo engine
risk_config_live.toml     # live engine（含 LiveDemo + Mainnet）
```

**沒有 `risk_config_live_demo.toml`**。Runtime 中 LiveDemo pipeline 走
`risk_config_live.toml`（per `startup/mod.rs:208-210`：`OPENCLAW_RISK_CONFIG_LIVE`
env var 覆蓋；LiveDemo 與 Mainnet 共用 live TOML，靠 `authorization.json` +
`OPENCLAW_ALLOW_MAINNET` env 區分）。

採取行動：以**代碼真實狀態為準**，3 個 TOML 加 [pricing] section：
- `risk_config_paper.toml`
- `risk_config_demo.toml`
- `risk_config_live.toml`

`risk_config.toml`（legacy fallback）**不加** [pricing] — 它只在 paper TOML
缺失時 fallback 使用（startup/mod.rs:196-203），實際 deploy 從不主動載入。
Smoke test 證實 legacy TOML 走 `Option<PricingConfig>` None fallback OK。

### Push back 2：PricingConfig 應放 `openclaw_types`（已採納）

PA plan §2.4 寫 `rust/openclaw_types/src/risk.rs 加 PricingConfig struct`，
這對齊 LG-2 後續 task 跨 crate 共用此型別的需求（T1 contract test 在
`openclaw_engine` / T2 startup assertion 在 `bybit_rest_client.rs` /
T3 FeeSource enum healthcheck 跨 Rust+Python）。我同意此 plan。

注意 `RiskConfig` 主 struct 仍在 `openclaw_engine::config::risk_config`
（per `openclaw_types/src/risk.rs:6-12` ARCH-RC1 1C-1 Batch 6 註：composite
RiskConfig 已從 openclaw_types 刪除）。故 `RiskConfig.pricing` 欄位走
`Option<openclaw_types::PricingConfig>`，型別於 types crate 定義，欄位於
engine crate 持有 — 跨 crate 引用模式與 `H0GateConfig` 一致。

---

## 3. 修改清單

### 3.1 Rust source（5 檔）

| 檔 | 改動類型 | LOC delta |
|---|---|---|
| `rust/openclaw_types/Cargo.toml` | 新 `[dev-dependencies] toml`（單元測試 round-trip 用） | +5 / -0 |
| `rust/openclaw_types/src/risk.rs` | 新 `PricingConfig` struct + default + validate + 8 單元測試；MODULE_NOTE 更新 | +211 / -10 |
| `rust/openclaw_types/src/lib.rs` | `pub use risk::PricingConfig` re-export | +3 / -1 |
| `rust/openclaw_engine/src/config/risk_config.rs` | `RiskConfig.pricing: Option<PricingConfig>` 新欄位 + validate 整合 | +27 / -0 |
| `rust/openclaw_engine/src/config/risk_config_tests.rs` | 7 個 RiskConfig 層整合測試 + 1 個實 TOML smoke 測試 | +218 / -0 |

### 3.2 TOML config（3 檔）

| 檔 | 改動 | [pricing] default |
|---|---|---|
| `settings/risk_control_rules/risk_config_paper.toml` | 加 `[pricing]` section | warn=1440min (24h) / fail=10080min (7d) / modes=[paper, demo, live_demo] |
| `settings/risk_control_rules/risk_config_demo.toml` | 加 `[pricing]` section | warn=60min (1h) / fail=1440min (24h) / modes=[paper, demo, live_demo] |
| `settings/risk_control_rules/risk_config_live.toml` | 加 `[pricing]` section | warn=30min / fail=720min (12h) / modes=[demo, live_demo] |

理由：
- **paper 寬鬆**：paper pipeline 預設 dormant（OPENCLAW_ENABLE_PAPER=1 才啟動），
  不接 Bybit fee endpoint，數值僅作 schema parity（per memory
  `feedback_env_config_independence`：禁衛生合併，每環境獨立）
- **demo 中庸**：demo 是 learning / edge 累積主通道（per memory
  `project_edge_data_isolation`），hourly fee refresh fail 一次即 WARN，24h
  hard-fail 對齊 LG-3 RFC §2.3
- **live 嚴格**：Live（LiveDemo + Mainnet）走真實/模擬真實流量，per memory
  `feedback_demo_loose_live_strict_policy` 永遠 fail-closed strict；12h fail
  比 demo 24h 收緊；whitelist **移除 "paper"**（live 配置無 paper 路徑）
  且**永不可含 "live"**（LG-3 RFC §2.3 mainnet hard-block 不變式，
  PricingConfig::validate() 強制）

---

## 4. PricingConfig struct 設計

```rust
// rust/openclaw_types/src/risk.rs
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
pub struct PricingConfig {
    /// 超過此分鐘 → healthcheck `[45]` WARN（default 60）。
    #[serde(default = "default_pricing_warn_minutes")]
    pub max_age_warn_minutes: u64,
    /// 超過此分鐘 → healthcheck `[45]` FAIL（default 1440 = 24h）。
    #[serde(default = "default_pricing_fail_minutes")]
    pub max_age_fail_minutes: u64,
    /// 接受 seed_default / cold_default 的 engine_mode 白名單。
    /// 字串需與 `trading.fills.engine_mode` 完全一致。
    #[serde(default = "default_pricing_cold_modes")]
    pub cold_default_acceptable_modes: Vec<String>,
}

impl Default for PricingConfig {
    fn default() -> Self {
        Self {
            max_age_warn_minutes: 60,      // LG-3 RFC §Refresh Cadence
            max_age_fail_minutes: 1440,    // 24h = RFC mainnet hard-block 等同門檻
            cold_default_acceptable_modes: vec![
                "paper".into(), "demo".into(), "live_demo".into(),
            ],
        }
    }
}

impl PricingConfig {
    pub fn validate(&self) -> Result<(), String> {
        if self.max_age_fail_minutes == 0 {
            return Err("risk.pricing.max_age_fail_minutes must be > 0".into());
        }
        if self.max_age_warn_minutes >= self.max_age_fail_minutes {
            return Err(format!(
                "risk.pricing.max_age_warn_minutes ({}) must be < max_age_fail_minutes ({})",
                self.max_age_warn_minutes, self.max_age_fail_minutes
            ));
        }
        if self.cold_default_acceptable_modes.is_empty() {
            return Err("risk.pricing.cold_default_acceptable_modes must not be empty".into());
        }
        // LG-3 RFC §2.3 fail-closed：live 不可進入白名單，否則 mainnet 退化。
        if self.cold_default_acceptable_modes.iter().any(|m| m == "live") {
            return Err(
                "risk.pricing.cold_default_acceptable_modes must NOT contain 'live' \
                 (LG-3 RFC §2.3 mainnet fail-closed invariant)".into(),
            );
        }
        Ok(())
    }
}
```

不變量：
- `max_age_fail_minutes > 0`
- `max_age_warn_minutes < max_age_fail_minutes`（warn 嚴格小於 fail）
- `cold_default_acceptable_modes` 非空
- `cold_default_acceptable_modes` 不含 `"live"`（LG-3 RFC §2.3 強約束）

---

## 5. RiskConfig 整合

```rust
// rust/openclaw_engine/src/config/risk_config.rs
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RiskConfig {
    // ... 既有欄位 ...
    #[serde(default)]
    pub cost_edge: CostEdgeConfig,
    /// LG-2 T4 (2026-05-11): 24h pricing freshness gate 配置。
    #[serde(default)]
    pub pricing: Option<openclaw_types::PricingConfig>,
}

impl RiskConfig {
    pub fn validate(&self) -> Result<(), String> {
        // ... 既有 validate 步驟 ...
        self.cost_edge.validate()?;
        // LG-2 T4：PricingConfig 啟用時走完整 invariant 檢查
        if let Some(ref pricing) = self.pricing {
            pricing.validate().map_err(|e| format!("risk.pricing: {e}"))?;
        }
        // ... 其餘 validate 步驟 ...
    }
}
```

**為何用 `Option<PricingConfig>` 而非 `PricingConfig` direct**：

向後相容 — 舊 TOML 無 `[pricing]` section 時 deserialize 後是 `None`，下游
消費者（後續 LG2-T1 contract test / LG2-T2 startup assertion / LG2-T3
healthcheck cross-check）會 fallback 到 `PricingConfig::default()`，對齊
LG-3 RFC §Refresh Cadence 硬編碼語意。

如果改為 `PricingConfig direct` + `#[serde(default)]`，serde 會直接 deserialize
default value，但喪失「config 是否顯式設定」的訊號（下游無法區分「TOML 沒有
section」vs「TOML 顯式設了 default 值」）。`Option` 保留此訊號，方便後續
healthcheck `[45]` 跨 source-of-truth 對賬。

---

## 6. ArcSwap hot-reload 整合

**重要結論：不需動 pipeline_config.rs**。

`apply_risk_snapshot()`（pipeline_config.rs:64-174）的 RMW 設計是針對「下游
擁有派生 copy 的 sub-struct（如 H0GateConfig）」，需要把 RiskConfig 對應欄位
拉齊到下游 owned copy。**PricingConfig 在 LG2-T4 階段沒有任何下游 owned
consumer**：
- LG2-T1 contract tests：訪問 `cfg.pricing` 走 RiskConfig snapshot path（同源
  ArcSwap 路徑），無 owned copy
- LG2-T2 startup assertion：在 `build_exchange_pipeline` 啟動前讀，不在 hot-path
- LG2-T3 FeeSource healthcheck cross-check：Python 走 `query_fee_source` IPC，
  Rust 端讀 ConfigStore::load 即時值

因此 PricingConfig 走 RiskConfig snapshot 既有 ArcSwap 路徑即可，無需新增
RMW 邏輯。**Hot-reload 自動可達**：
- TOML 改 `[pricing]` → `RiskConfigManager::reload_from_disk()` 觸發 →
  `ConfigStore.swap()` 寫新 snapshot → tick 頂部 `sync_risk_config_if_changed`
  發現 version bump → `apply_risk_snapshot(new_snapshot)` 拉新 snapshot 給
  下游派生 copy → pricing 欄位透過 `cfg.pricing` 訪問即得新值

IPC `patch_risk_config` 路徑：deep-merge JSON 既有支援 `Option<>` 欄位 patch
（per ARCH-RC1 deep-merge contract），新加欄位無需特殊處理。

證明：2828 既有 lib test PASS — 不變 hot-reload / RMW 行為。

---

## 7. Unit test 結果

### 7.1 openclaw_types::risk::tests::test_pricing*（8/8 PASS）

```
running 8 tests
test risk::tests::test_pricing_config_default_matches_rfc ... ok
test risk::tests::test_pricing_config_validate_zero_fail_rejected ... ok
test risk::tests::test_pricing_config_validate_warn_ge_fail_rejected ... ok
test risk::tests::test_pricing_config_validate_empty_modes_rejected ... ok
test risk::tests::test_pricing_config_validate_live_in_whitelist_rejected ... ok
test risk::tests::test_pricing_config_toml_round_trip ... ok
test risk::tests::test_pricing_config_partial_toml_uses_defaults ... ok
test risk::tests::test_pricing_config_json_round_trip ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 27 filtered out
```

### 7.2 openclaw_engine::config::risk_config::tests::test_pricing*（7/7 PASS）

```
running 7 tests
test config::risk_config::tests::test_pricing_config_default_riskconfig_omits_pricing ... ok
test config::risk_config::tests::test_pricing_config_legacy_toml_without_section_parses ... ok
test config::risk_config::tests::test_pricing_config_new_toml_section_parses ... ok
test config::risk_config::tests::test_pricing_config_invalid_section_rejected_at_validate ... ok
test config::risk_config::tests::test_pricing_config_live_in_whitelist_rejected_at_validate ... ok
test config::risk_config::tests::test_pricing_config_round_trip_via_riskconfig ... ok
test config::risk_config::tests::test_pricing_config_three_env_toml_strings_parse ... ok

test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured; 2822 filtered out
```

### 7.3 真實 TOML smoke（1/1 PASS）

```
running 1 test
test config::risk_config::tests::test_lg2_t4_real_toml_files_parse_and_validate ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 2828 filtered out
```

驗證內容：
- `risk_config.toml`（legacy fallback）— 解析 PASS，validate PASS，pricing=None
- `risk_config_paper.toml` — 解析 PASS，validate PASS，pricing=Some(warn=1440, fail=10080, modes=[paper, demo, live_demo])
- `risk_config_demo.toml` — 解析 PASS，validate PASS，pricing=Some(warn=60, fail=1440, modes=[paper, demo, live_demo])
- `risk_config_live.toml` — 解析 PASS，validate PASS，pricing=Some(warn=30, fail=720, modes=[demo, live_demo])

### 7.4 整體 lib regression

```
openclaw_types : test result: ok. 35 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
openclaw_engine: test result: ok. 2828 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out
```

**0 regression**。1 ignored 是既有 ignored test，不是我新增。

### 7.5 cargo build --release

```
cargo build --release -p openclaw_types -p openclaw_engine
    Finished `release` profile [optimized] target(s) in 24.85s
```

綠（18 warnings 為 pre-existing dead-code warning，與 LG-2 T4 無關）。

---

## 8. 治理對照

### 8.1 16 原則

| # | 原則 | LG-2 T4 對齊 |
|---|---|---|
| 4 | 策略不繞風控 | ✅ PricingConfig 走 RiskConfig 一級路徑，與既有風控 config 同源 |
| 5 | 生存 > 利潤 | ✅ Mainnet 必拒 `seed_default` 經 validate() 強制（不含 "live" 不變式） |
| 6 | 失敗默認收縮 | ✅ Option None fallback → PricingConfig::default()（per LG-3 RFC §2.3 mainnet hard-block） |
| 8 | 可解釋 | ✅ healthcheck `[45]` 後續 T3 cross-check 可讀此 config 解釋判決 |

### 8.2 硬邊界（§四）

- ✅ 不破 `max_retries=0`
- ✅ 不碰 `live_execution_allowed` / `execution_authority` / `system_mode`
- ✅ 不繞 GovernanceHub + Decision Lease

### 8.3 跨平台兼容（§七 ★★）

- ✅ 路徑不硬編碼：`test_lg2_t4_real_toml_files_parse_and_validate` 用
  `env!("CARGO_MANIFEST_DIR").parent().parent()` 跨平台動態解析，無
  `/home/ncyu` / `/Users/ncyu` 硬編碼
- ✅ 3 個 risk_config TOML 對等加 [pricing] section，不破三環境 config 獨立
  原則（per memory `feedback_env_config_independence`）

### 8.4 注釋規範（2026-05-05 governance change：默認中文）

- ✅ MODULE_NOTE 中文 / inline 中文 / docstring 中文
- ✅ openclaw_types/risk.rs MODULE_NOTE 既有為中英對照 — 走 2026-05-05 之後
  rule：「修改既有中英對照塊時移除英文只保留中文」我已在動到的 block 端把
  舊 EN/中對照清理為中文（per CLAUDE.md §七 注釋規範）

### 8.5 文件大小（§九）

| 檔 | 修改後行數 | 限制 | 狀態 |
|---|---|---|---|
| `rust/openclaw_types/src/risk.rs` | 348 | 800 警告 / 2000 硬限 | ✅ 遠低於警告線 |
| `rust/openclaw_engine/src/config/risk_config.rs` | 1216 | 2000 硬限 | ✅ |
| `rust/openclaw_engine/src/config/risk_config_tests.rs` | 1796 | 2000 硬限 | ✅ 接近限度，後續 LG2-T1 contract test 加新檔不再加此檔 |

### 8.6 三環境風控 config 獨立

完全遵守 per memory `feedback_env_config_independence`：
- paper / demo / live 三個 TOML 加 [pricing] 用**不同 default**
- 各環境注釋明寫「per memory feedback_env_config_independence — 禁衛生合併」
- validate() 不強制 cross-env consistency（每環境獨立 invariant 即可）

---

## 9. 不確定之處

### 9.1 LG2-T1/T2/T3 後續使用 contract

我假設下游 task：
- T1 contract test 訪問 `cfg.pricing.as_ref().map(...).unwrap_or_else(PricingConfig::default)` pattern
- T2 startup assertion `if matches!(env, BybitEnvironment::Mainnet)` 才強制
  check pricing；LiveDemo + Demo 可走 seed_default
- T3 healthcheck `[45]` Python 走 `query_fee_source` IPC，新加 IPC handler
  讀 `cfg.pricing.as_ref().map(|p| p.max_age_fail_minutes).unwrap_or(1440)`
  pattern

如果 T1/T2/T3 預期 PricingConfig **總是有值**（無 Option），則我設計需改成
`pub pricing: PricingConfig` direct（serde default fallback）。**建議 PA
review 確認後決定**。如需 direct，我可加一個 follow-up PR 簡單修正。

### 9.2 risk_routes.py 並行改動

git status 顯示 `risk_routes.py` 有並行改動（**LG1-T4 sibling sub-agent 改的**，
非我）。若 LG1-T4 需要 `/api/v1/risk/h0_block_summary` route 也讀 PricingConfig
（如 startup assertion drift dashboard），可能需要 cross-task coordination。
**目前我沒動 risk_routes.py**，但 LG2-T3 後續會加 `query_fee_source` IPC，
那時可能進 risk_routes.py 加新 route — 與 LG1-T4 不衝突（不同 route name）。

### 9.3 PA plan 寫「4 個 TOML」

如 §2 push back，我以代碼真實狀態為準改 3 個。如 PA 實際意圖是「先創建
`risk_config_live_demo.toml`」分離 LiveDemo 與 Mainnet，那這是更大的 scope
（startup/mod.rs:208-210 + `OPENCLAW_RISK_CONFIG_LIVE` env 既有合約），
**不在 LG2-T4 範圍**。建議 PA push back 或開另一 task。

---

## 10. Operator 下一步

1. **E2 對抗性 code review**：
   - 重點：PricingConfig::validate() invariant 是否漏邊界 case
   - 重點：`Option<PricingConfig>` vs `PricingConfig direct` 設計是否最佳
   - 重點：三環境 default 數值是否符合 RFC §Refresh Cadence + LG-3 RFC §2.3
   - 重點：MODULE_NOTE 雙語 → 中文化是否徹底
   - 重點：3 個 TOML default 是否觸發既有測試 / fixture 預期破壞
2. **E4 regression run**：
   - 應全綠（本 IMPL 已 2828+35 PASS local）
   - 重點：integration / e2e（如有）
3. **PM coordination**：
   - 確認 PA push back 1（3 vs 4 TOML）— 採納 3 TOML 視為正式 LG2-T4 deliverable
   - LG2-T1（contract tests）+ LG2-T3（FeeSource enum）可立即派發
   - LG2-T2（startup assertion）需 LG2-T3 land 後再派
4. **Deploy 路徑**：
   - 不部署（per CLAUDE.md：等 E2 → E4 → QA → PM 統一 commit + push）
   - Deploy 時走標準 `bash helper_scripts/restart_all.sh --rebuild --keep-auth`
     即可（PyO3 + Rust binary rebuild）
   - TOML 改動可即時 hot-reload（無需 restart），engine 跑時操作員寫 TOML →
     `RiskConfigManager` 觸發 reload → ArcSwap swap → 下個 tick 生效

---

## 11. 完成序列

per E1 完成序列（CLAUDE.md profile.md）：

- ✅ 本報告存：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t4_riskconfig_pricing.md`
- ⏳ memory.md 追加（本 session 結束時做）
- ⏳ 等 E2 審查 → E4 regression → PM 統一 commit + push

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t4_riskconfig_pricing.md`）
