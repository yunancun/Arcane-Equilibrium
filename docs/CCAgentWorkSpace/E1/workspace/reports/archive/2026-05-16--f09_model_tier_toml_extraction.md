# E1 — P1 #5 F-09 model_tier TOML extraction（IMPL）

- **日期**：2026-05-16
- **角色**：E1
- **任務 ID**：WP-04 follow-up · F-09 MODEL-TIER-EXTRACTION
- **PA dispatch**：把 `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs:412` 硬碼 `"model_tier": "l1_9b"` 抽到 `[strategist]` TOML config + Rust serde struct + ArcSwap hot-reload contract
- **狀態**：IMPL DONE，待 E2 + E4 審查

---

## 1. 任務摘要

WP-04 識別 evaluate.rs build_payload 把 IPC `strategist_evaluate` 的 `model_tier` 硬寫 `"l1_9b"`；切 27B / L1.5 / L2 都要 rebuild Rust engine。AI-E 視角：27B 可用但 Rust 鎖死 9B 是浪費。PA 派 E1 對齊既有 `max_param_delta_pct` ArcSwap hot-reload pattern 把 tier 提取至 `RiskConfig.strategist.model_tier`，**不做** dynamic model routing（留 P2-F-09b ticket）。

範圍嚴格 scope-tight：static tier 提取，operator 透過 TOML 或 IPC `patch_risk_config` `<60s` 熱重載即可換 tier；hot path / routing 邏輯 0 改動。

---

## 2. 修改清單

| 檔 | LOC delta | 改動類型 |
|---|---|---|
| `rust/openclaw_engine/src/config/risk_config_advanced.rs` | +30 | `StrategistConfig` 加 `model_tier: String` field + serde default + Default impl + validate 加 `trim().is_empty()` 拒 |
| `rust/openclaw_engine/src/strategist_scheduler/mod.rs` | +18 | 加 `DEFAULT_STRATEGIST_MODEL_TIER` 常量 + `current_model_tier()` snapshot helper |
| `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs` | +22 / -3 | `evaluate_cycle` 加 snapshot 傳給 `build_strategist_eval_payload`；後者 signature 加 `model_tier: &str`；payload `"l1_9b"` 硬碼移除；test 加新 case + 既有 case 加 default 斷言 |
| `rust/openclaw_engine/src/config/risk_config_tests.rs` | +60 / -10 | 5 個既有 strategist test 改 `..Default::default()` spread；加新 test `_rejects_empty_or_whitespace_model_tier`；既有 `_defaults` / `_toml_roundtrip` / `_partial_fallback` 加 model_tier 斷言 |
| `settings/risk_control_rules/risk_config_paper.toml` | +9 | `[strategist]` section 加 `model_tier = "l1_9b"` + F-09 雙語 doc comment 區塊 |
| `settings/risk_control_rules/risk_config_demo.toml` | +9 | 同上 |
| `settings/risk_control_rules/risk_config_live.toml` | +10 | 同上 + live 環境 doc note |

共 **7 files**，0 file deletion，0 unrelated diff。

---

## 3. 關鍵 diff

### 3.1 `evaluate.rs`：硬碼移除 + caller 傳入

```rust
// Before:
//     "model_tier": "l1_9b",  // TODO(WP-04): 提取到 [strategist] TOML config

// After (build_strategist_eval_payload signature):
fn build_strategist_eval_payload(
    pair: &PairMetrics,
    current_json: &Value,
    ranges_value: Value,
    max_delta_pct: f64,
    model_tier: &str,  // ← F-09 NEW
) -> Value {
    serde_json::json!({
        ...
        // F-09 MODEL-TIER-EXTRACTION：原硬碼 "l1_9b" 已抽至
        // RiskConfig.strategist.model_tier；caller 從 ArcSwap snapshot 傳入。
        // TODO(P2-F-09b): dynamic model routing — caller 包裝層按 decision
        // complexity 動態選 tier。
        "model_tier": model_tier,
        ...
    })
}
```

### 3.2 `evaluate_cycle` caller 接 snapshot

```rust
let max_delta_pct = self.current_max_param_delta_pct();
// F-09 MODEL-TIER-EXTRACTION：從 RiskConfig.strategist 快照 model_tier，
// 取代 build_payload 內舊的 "l1_9b" 硬碼。
let model_tier = self.current_model_tier();
let params = build_strategist_eval_payload(
    pair,
    &current_json,
    ranges_value,
    max_delta_pct,
    &model_tier,
);
```

### 3.3 `StrategistConfig` schema 升級

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrategistConfig {
    #[serde(default = "default_strategist_max_param_delta_pct")]
    pub max_param_delta_pct: f64,

    /// F-09 MODEL-TIER-EXTRACTION (2026-05-16)：IPC `strategist_evaluate`
    /// payload 的 `model_tier` 字串；Python `_handle_strategist` 端轉 Ollama
    /// 模型 routing key（既有 default `"l1_9b"` 保 backward compat）。
    #[serde(default = "default_strategist_model_tier")]
    pub model_tier: String,
}

fn default_strategist_model_tier() -> String { "l1_9b".to_string() }

impl StrategistConfig {
    pub fn validate(&self) -> Result<(), String> {
        // ... 既有 max_param_delta_pct 三條校驗 ...
        if self.model_tier.trim().is_empty() {
            return Err(
                "risk.strategist.model_tier must be a non-empty, non-whitespace string \
                 (e.g. \"l1_9b\" / \"l1_27b\" / \"l1_5\"). Hardcoded fallback removed by F-09."
                    .to_string(),
            );
        }
        Ok(())
    }
}
```

### 3.4 Scheduler snapshot helper（mirror `current_max_param_delta_pct`）

```rust
/// F-09 MODEL-TIER-EXTRACTION：從 risk_store 取當前 strategist.model_tier 快照；
/// 缺 store 時走 DEFAULT_STRATEGIST_MODEL_TIER 後備。ArcSwap 無鎖讀取，hot-path 安全。
fn current_model_tier(&self) -> String {
    self.risk_store
        .as_ref()
        .map(|store| store.load().strategist.model_tier.clone())
        .unwrap_or_else(|| DEFAULT_STRATEGIST_MODEL_TIER.to_string())
}
```

### 3.5 TOML 三檔對稱補欄位

```toml
[strategist]
max_param_delta_pct = 0.50      # ±50% cap on per-cycle non-weight param delta
model_tier = "l1_9b"            # F-09 IPC strategist_evaluate Ollama tier；non-empty string
```

---

## 4. 治理對照

| 規範 | 對照 |
|---|---|
| CLAUDE.md §二 原則 11（Agent 自主權） | F-09 純內部 config extraction，硬邊界 0 改動 |
| CLAUDE.md §四 硬邊界 | `max_retries=0` / `live_execution_allowed` / `execution_authority` / `system_mode` 不碰；本 IMPL 是 Strategist Configurator IPC payload 字串，不影響 live order 路徑 |
| CLAUDE.md §七 跨平台 | 0 hardcoded `/home/ncyu` / `/Users/[^/]+` 路徑 |
| CLAUDE.md §七 注釋規範（2026-05-05 中文 only） | F-09 region 全中文 doc comment（既有英文段保留不主動清，per memory `feedback_chinese_only_comments.md`） |
| CLAUDE.md §七 SQL migration Guard A/B/C | 不涉 SQL migration |
| CLAUDE.md §七 被動等待 healthcheck | 不涉被動等待 TODO |
| CLAUDE.md §八 最小影響 | rustfmt drift 在 pre-existing 別人寫的 region 不順手修；F-09 改動嚴格在 4 個明確區域 |
| CLAUDE.md §九 singleton 登記 | `StrategistConfig` 已在 `RiskConfig` Arc<ArcSwap> 既有 singleton 下；無需新登記 |
| CLAUDE.md §九 文件大小 | 改後 `risk_config_advanced.rs` 1300+ / `evaluate.rs` 540+ / `mod.rs` 540+ — 全在 2000 hard cap 內 |
| Bilingual comment style skill | F-09 region 中文 doc 充分；保留既有英文段；MODULE_NOTE 區段未動 |
| `feedback_no_dead_params.md` | `model_tier` 是真實被 caller 讀取 + 真實出現在 IPC payload + Python `_handle_strategist` 真實使用的字串 routing key；非 dead param |

---

## 5. 驗證結果

| 驗證 | 結果 |
|---|---|
| `cargo check --target aarch64-apple-darwin --lib` | PASS（2 pre-existing warning，與 F-09 無關） |
| `cargo check --target aarch64-apple-darwin --release --lib` | **PASS** |
| `cargo test --lib --release strategist_scheduler::` | **36/0/0**（baseline 34 + 2 new） |
| `cargo test --lib --release config::risk_config` | **150/0/0**（含 6 strategist tests + 真實 TOML files parse/validate） |
| `cargo test --lib --release`（全套） | **2917/0/1**（baseline 2915 + 2 new；0 regression） |
| `cargo test --release --bin openclaw-engine` | **62/0/0** |
| `cargo fmt --check`（F-09 改動 4 region） | **0 diff**（pre-existing fmt drift 在其他 file 不在 F-09 scope） |
| `grep -E '(/home/ncyu|/Users/[^/]+)' <F-09 files>` | 0 命中 |
| `grep '"l1_9b"' evaluate.rs` 殘留 | 只剩 (a) 注釋指引 (b) test caller 傳值 — 0 production hardcoded payload write |
| `test_lg2_t4_real_toml_files_parse_and_validate`（真實 3 TOML 載入驗證） | PASS — paper/demo/live 三檔 `[strategist] model_tier = "l1_9b"` 正確 round-trip |

---

## 6. 不確定之處

1. **Python `_handle_strategist` 端的字串比對是否大小寫敏感？**
   `ai_service_dispatch.py:220` 用 `params.get("model_tier", "l1_9b")` 直接傳給下游 Ollama 配置；若 Python 端有 case-insensitive normalization，validate 不擋 `"L1_9B"` / `"l1_9B"` 等變體是 OK 的（Python 自帶處理）。若是嚴格 case-sensitive，operator 填錯大小寫會 silent fallback 到 Ollama default model — **建議 E4 在 Python 對端跑一次 dispatch test 確認**。
2. **`tune_cmd_snapshot` 在 evaluate.rs L373 + L393 已是現有 helper，本 IMPL 不動**。`current_model_tier()` 是讀 RiskConfig，**不**透過 PipelineCommand，所以與 demo/live channel 路徑無耦合 — pattern 與 `current_max_param_delta_pct` 完全對稱。
3. **`validate()` 不綁 enum**：選擇是「保留 future tier 名變動空間 + P2-F-09b dynamic routing」設計餘地，**代價是 typo 不被早期攔截**。若 E2 認為應綁 enum（e.g. `ModelTier::L1_9b / L1_27b / L1_5 / L2`），改動成本是再加一個 from_str 解析器 + tests — 可以後續 P1.5 補強。本 IMPL 保守選擇 = 寬鬆 validate。
4. **三 TOML 預設值同步**：paper/demo/live 都填 `"l1_9b"`。若 PA 後續想讓 demo 用 27B（探索）/ live 用 9B（保守），改 TOML 即可，不影響 IMPL。
5. **不改 Python 端**：本 IMPL 完全保留 Python `params.get("model_tier", "l1_9b")` 不動 — Rust 一律明確傳 tier 字串，但 Python 端 default 沒移除避免破其他 caller。F-09 完成後 Python default 是「dead code path」但保留保險絲。E2 可決定是否要在後續 ticket 清。
6. **dynamic routing 設計餘地**：caller layer 加包裝即可（依 `pair.deviation_score()` / `pair.fill_count` 等 decision complexity 動態選 tier），**不必動 `build_strategist_eval_payload` signature**。已在 TODO 注釋標識 P2-F-09b。

---

## 7. Operator 下一步

1. **派 E2 對抗性核驗**（per CLAUDE.md §八 強制鏈 E1→E2→E4→PM）：
   - 確認 `validate()` 不綁 enum 設計取捨是否需收緊
   - 確認 Python 端 `_handle_strategist` 字串等值比對是否需要對端 dispatch 測試
   - 確認 pre-existing rustfmt drift 不順手修是否符合「最小影響」原則
2. **派 E4 跑 regression**：
   - 必走：`cargo test --lib --release` 全套（已驗 2917/0/1）+ `cargo test --release --bin openclaw-engine`（已驗 62/0）
   - 補跑：Python `_handle_strategist` 端 IPC dispatch 真實 test（與 §6 #1 對接）
3. **PM 統一 commit + push**（per CLAUDE.md §七 commit-即-push）：本 IMPL 不直接 commit。
4. **P2-F-09b ticket 排程**：dynamic model routing — caller 層包裝按 decision complexity 動態選 tier。

---

## 8. 文件路徑（絕對）

- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategist_scheduler/evaluate.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/strategist_scheduler/mod.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/config/risk_config_advanced.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/config/risk_config_tests.rs`
- `/Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_paper.toml`
- `/Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_demo.toml`
- `/Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_live.toml`
- 本 sign-off：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--f09_model_tier_toml_extraction.md`

---

**E1 IMPLEMENTATION DONE**：待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--f09_model_tier_toml_extraction.md`）
