# P1-BB-REVERSION-REGIME-OBSERVABILITY — 技術設計（PA, 2026-06-11）

**Executive summary（5 行）**
1. 推薦方案：在 dispatch 層 `persist_intent`（`on_tick_helpers.rs:406`）的 details JSON 加 `hurst_label` + `hurst_value` 兩鍵，值由 `step_4_5_dispatch.rs` 既有 `indicators: Option<&IndicatorSnapshot>` 參數（:148）直接搬運——**不動 OrderIntent、不動策略碼、不動 IPC、零 migration**。
2. 全策略統一加（非 bb_reversion-only）：persist_intent 是共用函數，按策略分支反而更多代碼；統一加 = 嚴格更簡 + bb_breakout/ma_crossover 同價取得同證據面。
3. 代碼現實與 brief 有 4 處重大出入：`HurstHysteresis` 不存在（真名 `HysteresisDetector` 且 runtime `[hurst] enabled=false` dormant，gate 實際消費 openclaw_core **瞬時** label，閾值 0.60/0.40 非 0.55/0.45）；`regime_snapshots` 0 rows 根因 = enum variant + writer 在但 **0 producer**；`AlphaSurface.regime`（RegimeTag）是無關軸；`openclaw_types::OrderIntent` 是 agent-spine 同名異物。
4. 熱路徑紀律：新代碼只在 intent 發射分支執行（per-intent 非 per-tick），0 鎖 / 0 IO / 0 重算，label 是同 tick 同 snapshot 已算好值的引用搬運；persist 結構本身 fail-soft（`try_send` 非阻塞 + `let _ =`），observability 結構性不可能擋交易。
5. E1 = 1 任務（2 檔互鎖不可並行拆，~25 行碼 + ~100 行測試，0.5-1 session）；鏈 PA→E1→E2→E4（E4 含 hot-path 性能斷言 + Linux rebuild + 部署後 SQL 驗收）。

---

## 0. 任務與裁決範圍

QA 2026-06-02 提出、06-10 複查維持：bb_reversion `mean_reverting` hard gate（2026-06-01 `324001c3` Track B fix）無正面證據面——無法確認「gate fire 時 regime 判定是什麼」，B 複查永遠 INCONCLUSIVE，且 `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`（2026-06-27）的 `bb_reversion@mean_reverting` 樣本判讀依賴它。QA 建議：fire 時把 Hurst label 持久化進 `trading.intents.details`。

本報告 = 設計 + E1 拆分，不含實作。

---

## 1. 代碼現實盤點（全部親 grep / 親讀，file:line ground）

### 1.1 Hurst / regime 計算在哪（與 brief 線索的出入）

| brief 線索 | 代碼現實 |
|---|---|
| `HurstHysteresis` | **不存在**（rust 全域 grep 0 hits）。真名 `HysteresisDetector`（`rust/openclaw_engine/src/regime/hurst.rs:136`），由 `apply_hurst_regime_label_for`（`tick_pipeline/pipeline_helpers.rs:885`）每 tick 在 `compute_indicators` 後接線。 |
| 滯回 label 是 gate 輸入 | **僅當 `[hurst] enabled=true`**。三環境 TOML 全部 `enabled = false`（`settings/risk_control_rules/risk_config_demo.toml:403-404`，paper/live 同）→ 滯回路徑 **dormant**，`apply_hurst_regime_label_for` 開頭 bypass。 |
| gate 實際消費什麼 | openclaw_core `compute_indicators` 的**瞬時** label：`indicators/mod.rs:143-149` 呼 `hurst(close, 10, 50, 0.60, 0.40)` → `IndicatorSnapshot.hurst: Option<HurstResult>`（`mod.rs:184`）。`HurstResult { hurst: f64, regime: String }`（`volatility.rs:119-122`）。**瞬時閾值 0.60/0.40**（`DEFAULT_HURST_TRENDING/MEAN_REVERTING_THRESHOLD`，volatility.rs:128/131），非 HurstConfig 的 0.55/0.45（後者只在滯回啟用時生效）。 |
| `AlphaSurface.regime` | 無關軸：`openclaw_core/src/alpha_surface.rs:602` `pub regime: RegimeTag`（Tier 4 信息流，default Unknown）。bb_reversion gate 讀 `ctx.indicators.hurst`（`bb_reversion/mod.rs:421` `let ind = ctx.indicators`），不讀 surface.regime。 |

**設計含義**：持久化 `ind.hurst.{regime, hurst}` 即捕捉 gate 真正消費的值（無論滯回開關），語義自動跟隨；無須區分兩條路（同一個槽位，滯回啟用時被 `pipeline_helpers.rs:945` 覆寫）。

### 1.2 gate 判定點 vs intent 創建點：label 是否在手

`bb_reversion/mod.rs` 同一個 `on_tick` 函數體內：

- **gate 判定**（:562-588）：`require_mean_reverting_regime`（default true，params.rs:155）→ `match &ind.hurst`：`Some(h)` 且 `from_legacy_str(&h.regime)==AntiPersistent` 才放行；`None` → fail-closed skip。
- **intent 創建**（:658-669）：`make_entry_intent_with_qty` → `OrderIntent::new_trade`（`intent_processor/mod.rs:265`）。OrderIntent **無 regime 欄位**。

label 在 gate 點在手（`ind.hurst`），但 OrderIntent 不攜帶 → 問題變成「details JSON 構造點能否拿到同一份 snapshot」。

### 1.3 intent → `trading.intents` 序列化路徑（唯一 details 構造點）

```
策略 on_tick(ctx, surface) → Vec<StrategyAction::Open(OrderIntent)>
  └─ step_4_5_dispatch.rs（on_tick_step_4_5_dispatch, :144；簽名含
     indicators: Option<&IndicatorSnapshot> :148；ctx 構造 :287 直接引用同一參數）
       ├─ pre-risk reject 路徑 → record_pre_risk_rejection(:92) → persist_intent(:112)
       ├─ exchange 成功路徑 → persist_intent(:748)
       └─ paper 成功路徑 → persist_intent(:1054)
            └─ on_tick_helpers.rs persist_intent(:406)
                 構造 details = json!({strategy, confidence, submitted_qty,
                 is_sentinel, is_long, limit_price, time_in_force, post_only,
                 maker_timeout_ms, signal_id, context_id, scanner{...含
                 market_regime=scanner 軸}, scanner_gate}) (:481-495)
                 → TradingMsg::Intent{details: Some(json)} (:498-515)
                 → trading_writer.rs flush_intents(:295) INSERT 第 12 欄
                   details (:314, INTENT_COLS=12 "includes details JSONB" :212)
                 → ON CONFLICT (intent_id, ts) DO NOTHING (:348)
```

**關鍵可達性結論**：dispatch 函數參數 `indicators` 與策略 gate 讀的 `ctx.indicators` 是**同一份引用**（:287），三個 persist_intent call sites 全在該函數體內 → label **無須穿層傳遞、無須動 OrderIntent**，在 call site 用 `indicators.and_then(|i| i.hurst.as_ref())` 即得 gate 同 tick 消費的精確值。

**第二條 intent 寫入路（必須知道但不改）**：`commands.rs:407` IPC external_intent（手動 / GUI 單），details 帶 `"source":"command"`（:399），無 indicators 在 scope、無 regime 決策 → **不加鍵**。既有 Python 讀方已用此鍵過濾（`opportunity_tracker.py:181` `COALESCE(i.details->>'source','') <> 'command'`）→ 驗收 SQL 沿用同口徑。

**Close 不寫 intents**：`StrategyAction::Close`（dispatch:1441）走 deferred-close 執行，grep 證 persist_intent 僅上述 3 sites → bb_reversion 的 intents rows = entry（含 pre-risk rejected qty=0 rows，它們也已通過策略內 regime gate）。

### 1.4 `market.regime_snapshots` 0 rows 根因（順帶確證 QA 發現）

`MarketDataMsg::RegimeSnapshot` enum variant（`database/mod.rs:271`）+ writer `flush_regime_snapshots`（`market_writer.rs:615`）都在，但全引擎 **0 個 producer emit**（grep 排除 writer/enum 定義後 0 hits）→ 死管道。復活它 = 連續 per-tick 快照流（容量/保留策略需另議），是獨立工程；**intent-stamping（決策點採樣）是更小且足夠回答 QA 問題的路**，本設計不復活 regime_snapshots。

### 1.5 同名異物澄清（副作用排除）

`openclaw_types/src/intent.rs:70` 的 `OrderIntent` 是 agent-spine 5-Agent 通信類型（side: String + metadata HashMap），與 engine `intent_processor::OrderIntent`（:193）無關。本設計兩個都不碰 → **0 IPC schema 改動**。

---

## 2. 設計（最小爆炸半徑）

### 2.1 接口設計

**`on_tick_helpers.rs`**（2 處簽名 + 2 鍵）：

```rust
// persist_intent 簽名加一參數（11→12 參數；E1 確認 clippy too_many_arguments）
pub(crate) fn persist_intent(
    ...,                                    // 既有 11 參數不變
    hurst: Option<&openclaw_core::indicators::HurstResult>,  // NEW：引用搬運
)
// details json!(...) 內、"signal_id" 之前加：
"hurst_label": hurst.map(|h| h.regime.as_str()),  // "mean_reverting"|"trending"|"random_walk"|null
"hurst_value": hurst.map(|h| h.hurst),            // 原始 R/S 估計 [0,1]|null
```

`record_pre_risk_rejection`（dispatch:92，已有 `#[allow(clippy::too_many_arguments)]`）同樣加一個 `hurst` 參數透傳。

**`step_4_5_dispatch.rs`**（4 處 call site 各加一行實參）：

```rust
indicators.and_then(|i| i.hurst.as_ref())
```
（:546 caller→record_pre_risk_rejection、:748 exchange、:1054 paper；`Option<&IndicatorSnapshot>` 是 Copy 共享引用，無借用衝突。）

**commands.rs 明確不改**（改了= scope violation，E2 檢查點）。

### 2.2 命名裁決（domain 一致性）

- `hurst_label`：對齊 QA 建議 + `RegimeLabel` 類型詞；值域 = legacy 字串（gate 比較域、TODO `bb_reversion@mean_reverting` 記法一致、`HurstResult.regime` 原值原樣搬運不轉換）。
- `hurst_value`：原始 R/S 數值，讓 QA 可驗「label 與 0.40/0.60 閾值一致性」與邊界分佈。
- **不用裸 `regime` 鍵**：details.scanner 已有 `market_regime`（scanner 趨勢/震盪軸）、AEG 有 `main_regime`/`market_anchor_regime`（日線研究軸）、CONTEXT.md Tier D 詞彙明確警告 generic "regime" 命名——`hurst_` 前綴釘死軸別。
- **不採 QA 例子中的第三鍵 `regime_gate`**：dispatch 層拿不到策略內部 `require_mean_reverting_regime` flag，要拿必須動 OrderIntent（爆炸半徑↑）。且 label 分佈本身是**比自報 flag 更強的對抗證據**——gate-on 期間任何 `hurst_label != 'mean_reverting'` 的 bb_reversion entry row 直接證偽 gate（自報 flag 反而可能與 bug 同謀）。flag 歷史可由 TOML + params hot-reload audit 重建。
- **`hurst_stabilized` 欄 deferred**：當前三環境 `enabled=false` 全瞬時，無歧義；若未來 operator 翻 `[hurst] enabled=true`，同槽位語義變為滯回標籤——屆時加 bool 鍵是 cheap follow-up，現在預埋 = YAGNI。

### 2.3 Option A（OrderIntent-carried）為何被拒

FUP-8 註釋（on_tick_helpers.rs:420-424）原計劃「等 regime 接進 OrderIntent 再加」。實測推翻其必要性：dispatch 層已有同一份 snapshot（§1.3），OrderIntent-carried 的唯一增量收益是攜帶策略私有 gate flag（§2.2 已論證不需要）。成本側：OrderIntent 是 `#[derive(Serialize, Deserialize)]` 跨 canary/IPC-adjacent 結構 + 多個 struct literal 構造點 + `new_trade` 簽名改動波及 8 個策略 emit sites + tests，且 TODO 已有 `P1-INTENTYPE-FIELD-VISIBILITY-DEFER`（OrderIntent 改動先等 builder pattern 規格）。**Option B 爆炸半徑 = Option A 的 ~1/4，證據價值相同。**

### 2.4 bb_reversion-only vs 全策略統一：推薦全策略

| | bb_reversion-only | 全策略統一（推薦） |
|---|---|---|
| 代碼 | persist_intent 內加 `if intent.strategy=="bb_reversion"` 字串比較分支 | 無分支，兩鍵直加 |
| 證據面 | 只覆蓋本案 | bb_breakout（trending gate 假說）、ma_crossover（同樣消費 hurst，G7-03 3-of-4 策略已遷移 RegimeLabel）同價取得 |
| 行為風險 | 同（純 telemetry） | 同（純 telemetry） |
| null 噪音 | — | hurst 缺失策略/暖機期 = null 值（誠實，非 fabricate） |

QA 原文只要 bb_reversion，但統一加**嚴格更簡且零額外風險**——採統一。

### 2.5 熱路徑紀律（task 硬要求逐條）

1. **執行頻率**：persist_intent 僅在 intent 發射時呼叫（per-intent 非 per-tick；bb_reversion 7d=12 次、全策略量級也在「每 tick 0-1 個」）。非 intent tick **0 新指令**。
2. **0 鎖 / 0 IO / 0 重算**：`Option<&HurstResult>` 是已算好 snapshot 欄位的共享引用；新增成本 = `json!` 兩鍵（一個 ~15-byte 字串 clone + 一個 f64），相對既有 30+ 鍵 scanner 巨型 json 構造是 noise。
3. **NaN/panic 安全**：瞬時路徑 core 已 clamp [0,1]（volatility 註釋 + regime/hurst.rs:115-118 NaN 過濾）；防禦縱深 = serde_json `From<f64>` 把 non-finite 映 `Value::Null`（不 panic）。`json!` 巨集無 fallible 路徑。
4. **fail-soft 結構不變**：`let _ = try_send_trading_msg(...)`（:496）非阻塞，channel 滿丟訊息留 log；DB 不可用 → writer buffer 保留重試（trading_writer.rs:299-304）；**intent 的執行路徑不依賴 persist 結果** → label 缺失 / 序列化異常 / DB 故障在結構上不可能擋 intent。本設計不引入任何 early-return。

### 2.6 Migration 判定：**無需 migration，V138 不取**

- `details` JSONB 欄已存在且活躍：writer INSERT 第 12 欄（trading_writer.rs:212/314）+ Python 讀方在用 + QA 已對 938,832 rows 跑過 hurst key 查詢 = runtime 證據齊。jsonb 加鍵 0 schema 變更。
- **Index 不需**：驗收查詢以 `strategy_name + ts`（既有欄）過濾後才取 jsonb；bb_reversion ~12 intents/7d，全表掃描風險不存在。若未來跨策略 regime 分析變高頻查詢再議 V###（GIN on details），現在不取號。

### 2.7 向後兼容

- 舊 rows 無鍵 → `details->>'hurst_label'` 自然 NULL；唯一現役 Python details 消費點 `opportunity_tracker.py:181` 只讀 `source` 且 COALESCE 包裹——不受影響。
- 無任何 Rust 測試斷言 details 鍵集（grep `submitted_qty`/`is_sentinel` 0 test hits）→ 加鍵零測試破壞。
- 新 rows 鍵**永遠存在**（值可 null）→ `details ? 'hurst_label'` 兼作部署分界標記。

---

## 3. 驗收標準（B 複查翻正判準）

1. **部署後即時（D+1）**：bb_reversion 新 entry intents（排除 `source='command'`）100% 帶 `hurst_label` 鍵；gate-on 期間 100% `hurst_label='mean_reverting'` 且 `hurst_value < 0.40`（瞬時閾值）。**任何反例 = gate 違規證據**（這正是 B 複查要的可證偽性）。
2. **7-14d regime 分佈報告**（QA 用）：

```sql
SELECT details->>'hurst_label' AS label, count(*) AS n,
       round(min((details->>'hurst_value')::numeric), 4) AS h_min,
       round(max((details->>'hurst_value')::numeric), 4) AS h_max
FROM trading.intents
WHERE strategy_name = 'bb_reversion'
  AND ts >= '<deploy_ts>'
  AND COALESCE(details->>'source','') <> 'command'
GROUP BY 1;
-- 100%-presence 檢核：
SELECT count(*) FILTER (WHERE NOT details ? 'hurst_label') AS missing
FROM trading.intents
WHERE strategy_name='bb_reversion' AND ts >= '<deploy_ts>'
  AND COALESCE(details->>'source','') <> 'command';  -- 期望 0
```

3. **06-27 樣本鐘銜接**：落地越早帶標窗越長；若 ~06-13 前部署，06-27 有 ~14d 帶標 rows。**誠實聲明**：12 intents/7d 速率 → 14d ≈ 24 樣本，遠低於 catch-up clock 的 n<100 → 延長條款幾乎必然觸發。本設計解的是「樣本可判讀性」（每筆 fire 的 regime 可正面確認），不解「樣本量」——後者是 gate 通過率的市場事實，PM 排程時勿誤讀。
4. **B 複查翻正**：QA 以 (1)+(2) 把 INCONCLUSIVE → 正面 PASS（label 全 mean_reverting）或 FAIL（出現反例 → 升級調查）。

---

## 4. 副作用清單（PA checklist 逐條）

1. **其他模塊 import**：`persist_intent` 是 `pub(crate)`，grep 證僅 step_4_5_dispatch.rs 3 sites；`record_pre_risk_rejection` 私有單 caller。無第三方。
2. **mock 脆弱性**：0 個測試 mock persist_intent / 斷言 details 鍵集。
3. **asyncio/threading 邊界**：無——同步函數 + `try_send` 非阻塞，無 await 點新增。
4. **API response schema**：不動。intents 端點（若回吐 details）是 jsonb 透傳，加鍵 additive。
5. **Rust↔Python IPC schema**：不動（engine OrderIntent 不改、openclaw_types 不改、commands.rs 不改）。
6. **canary record**：OrderIntent 不變 → CanaryRecord schema 不變。
7. **LOC 治理（§九）**：on_tick_helpers.rs 792 → ~800+ **跨 review 注意線**（申報；本案 surgical 不拆檔，拆檔另案）；step_4_5_dispatch.rs 1813 → ~1820（hard cap 2000 內）。
8. **clippy**：persist_intent 11→12 參數，E1 須 clippy 通過（必要時 `#[allow(clippy::too_many_arguments)]`，與 :91 同檔先例一致）。

---

## 5. 風險評級 + 降級 / rollback 路徑

- **風險評級：中**。live intent 序列化路徑上的改動，但 (a) 純 telemetry 加鍵、(b) fail-soft 透傳結構不變、(c) 無交易效果 / 風控 / 授權邏輯觸碰。三硬邊界（live_execution_allowed / max_retries=0 / system_mode）0 接觸；H0/lease/GovernanceHub 0 接觸。
- **失敗行為（fail-soft 方向，task 硬要求）**：label 缺失 → 鍵=null，intent 照常 persist + 照常執行；NaN → null（serde 語義）；channel 滿 / DB 掛 → 既有 fail-soft（丟訊息留 log / buffer 重試），不阻塞 on_tick。**設計中無任何新增 early-return / panic / unwrap。**
- **Rollback**：單 commit revert + rebuild。無 schema 變更、無數據遷移、讀方雙向 null-safe（有鍵/無鍵都合法）→ 回滾零殘留。降級不需要 flag：此改動無行為面，「降級」=回滾本身。
- **部署**：Rust 改動需 `--rebuild` 生效（教訓：binary mtime ≠ engine 看到新值，verify 先查 boot kind）。TODO §6 已有 OPS-2 rebuild pending——**可同車一次重啟**（搭車與否屬 PM 調度決策）。

---

## 6. E1 派發計劃

**1 個 E1 任務**（兩檔簽名互鎖，不可並行拆；強拆=檔案重疊違反派發原則）：

| 項 | 內容 |
|---|---|
| 檔案 | `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`（persist_intent +1 參數 +2 json 鍵；record 簽名連動）、`rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`（record_pre_risk_rejection +1 參數透傳；4 個 call site 各 +1 行實參） |
| 禁區 | 不動 OrderIntent / commands.rs / 策略碼 / trading_writer.rs / openclaw_types；不引入鎖、IO、重算、early-return；鍵名鎖死 `hurst_label` / `hurst_value` |
| 測試要求 | (a) on_tick_helpers 既有測試模塊（:96 / :732）加 persist_intent 雙態測試：建 mpsc channel，`Some(HurstResult{0.33,"mean_reverting"})` → 收到的 TradingMsg details 斷言兩鍵值；`None` → 斷言兩鍵存在且為 null；(b) 既有鍵（strategy/confidence/submitted_qty/scanner）不變斷言（防 collateral）；(c) NaN 防禦測試：`HurstResult{f64::NAN, ...}` → hurst_value=null 不 panic |
| 估算 | 代碼 ~25 行 + 測試 ~100 行；0.5-1 session |
| 驗證 | `cargo test -p openclaw_engine`（lib + tick_pipeline tests）+ `cargo clippy` 0 new warnings |

**鏈**：PA（本報告）→ E1 → E2 → E4 → QA（部署後 §3 SQL）→ PM sign-off。

### E2 重點審查 3 點

1. **熱路徑斷言**：diff 內無任何 per-tick 路徑新代碼（全部在 intent-emission 分支 / persist 函數體內）；無大物件 clone（僅 `&HurstResult` 引用 + 字串鍵值）；非 intent tick 指令數零增。
2. **fail-soft 不變式**：逐路徑檢查 label 缺失 / NaN / None 不可能造成 panic、unwrap、early-return 或擋 intent persist / 執行；兩鍵用 `Option::map` 映 null 而非 unwrap。
3. **call-site 完備性與 scope 紀律**：4 個傳遞點全接齊（grep persist_intent 證無漏接第 5 點）；commands.rs **未被改**（改了即 scope violation）；OrderIntent / IPC 0 觸碰。

### E4 要求（live 序列化路徑 → 含 hot-path 性能斷言）

1. Mac `cargo test` 全綠 + Linux 全量 rebuild regression（lib + 43 targets 基線對照，0 新 fail）。
2. **Hot-path 性能斷言**：`stress_integration.rs`（既含 hurst/mean_reverting 覆蓋）base-vs-HEAD 對跑，tick 延遲統計（`tick_duration_us`）無回歸；code-path review 確認新代碼僅 intent fire 分支執行（與 E2 第 1 點雙簽）。
3. 部署驗證（rebuild 生效 + boot kind 確認後）：§3 驗收 SQL 首輪——首批 bb_reversion intent 帶鍵、label/value 與閾值一致。

---

## 7. 與既有概念的命名 / 治理對齊備忘

- `hurst_label` 值域沿用 legacy 字串（`HurstResult.regime` 原樣），與 Track B gate 比較域、TODO `bb_reversion@mean_reverting` 記法一致；軸別由 `hurst_` 前綴與 scanner `market_regime`、AEG `main_regime` 區隔（CONTEXT.md Tier D 詞彙警告 generic regime 命名）。
- 本設計與 16 根原則：強化原則 8（交易可重建可解釋——FUP-8 的 regime 缺口收口）；0 觸碰原則 1-7 寫入面（telemetry only）。
- 後續若 operator 翻 `[hurst] enabled=true`（滯回啟用），同鍵語義變為穩定 label——屆時補 `hurst_stabilized` bool（cheap follow-up，本設計記錄於此不預埋）。

---

**PA DESIGN DONE** · E1-READY · 0 migration · 0 blocker · 待 PM 派發
