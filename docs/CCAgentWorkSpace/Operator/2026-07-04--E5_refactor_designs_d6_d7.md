# E5 — D6+D7 重構設計三件套（sizing 語義統一 / 熱檔拆分 / learning-lane 公共 lib）

日期：2026-07-04 ｜ 角色：E5（Optimization Engineer，只設計不動業務碼）
基準：Mac repo `2be58c191`（= Linux checkout 同 SHA；三個 D7a 目標檔在髒樹中此刻均 clean，行號錨點有效）
授權來源：operator 裁決 D6+D7 全授權（PA validated fix plan `2026-07-03--cold_audit_validated_fix_plan.md` §需 operator 決策清單 D6/D7；P2-10/P2-12）
紀律聲明：本文 fact（帶 file:line 實測）/ inference（標「推斷」）/ assumption（標「假設」）分列；全部 finding 全量列出含 LOW/INFO。

---

## 1. D6 — sizing 語義統一設計（P2-12）

### 1.1 位點盤點（FACT，全量）

**現況本質**：同一個 `[limits]` 區塊內兩種量綱共存——`per_trade_risk_pct = 0.1`（fraction，=10%）與 `position_size_max_pct = 15.0`（percent，=15%）並排（`settings/risk_control_rules/risk_config.toml:9,27`）。名字全部叫 `_pct`，語義靠讀 consumer 代碼才能分辨。

**A. fraction（0–1）家族**：

| 欄位 | 定義/校驗錨點 | 三環境值 | 消費錨點（數學形式） |
|---|---|---|---|
| `limits.per_trade_risk_pct` | `rust/openclaw_engine/src/config/risk_config.rs:436-437`；bounds `[0.001,0.20]` :71-72、validate :693-696（錯誤訊息自注「(0.1–20%)」） | live 0.05 / demo 0.1 / paper 0.20 | `ml/kelly_sizer.rs:259,274`（`balance * risk_pct / price`）；`tick_pipeline/on_tick/step_4_5_dispatch.rs:174`（`equity * pct`）；`bounded_probe_active_order.rs:197`；`intent_processor/mod.rs:487`（DEFAULT 0.03）,895-899（clamp setter）,926-928；`tick_pipeline/pipeline_config.rs:76,83` |
| `limits.flash_dip_buy_max_notional_pct_equity` | `intent_processor/mod.rs:779-803`；`strategies/flash_dip_buy/params.rs:50-51`（注釋「<=3%」=0.03） | ~0.03 | `equity * pct` 直乘 |
| `dynamic_sizing.step_pct / min_pct / max_pct` | `risk_config_demo.toml:268` 區塊（0.005/0.01/0.05，注釋自證「±0.5% step, 1%..5% clamp」）；`dynamic_risk_sizer.rs:61,385` | demo enabled；paper :211；live :220 | sizer 內直接當 fraction 步進 |
| `kelly.reference_atr_pct` | `ml/kelly_sizer.rs:129`（default 0.02） | — | fraction |
| IPC `SizerStatus.current_pct / base_pct` | `dynamic_risk_sizer.rs:162-163` | — | fraction 出線 |

**B. percent（0–100）家族**：
`position_size_max_pct`（15/25/50）、`total_exposure_max_pct`（100）、`correlated_exposure_max_pct`（60）、`session_drawdown_max_pct`、`daily_loss_max_pct`、`stop_loss_max_pct`、`take_profit_max_pct`、trailing_*、`drawdown_*_pct` 梯度、`daily_loss_*_pct`、`liquidation_buffer_pct`、`extreme_drop_pct`/`moderate_drop_pct`（`risk_config.toml:6-14,52-78,135,169-170`）；per-strategy `position_size_max_pct`（`config/risk_config_per_strategy.rs:181-192`，跨欄位校驗以 percent 比大小）。
消費數學：`risk_checks.rs:171-173`（`position_value / balance * 100.0` vs limit）；`step_4_5_dispatch.rs:176` 與 `bounded_probe_active_order.rs:212`（`/ 100.0`，後者帶 `>0 && <=100` guard :202-204）。

**C. 邊界轉換位點（現況 ad hoc ×7，各自為政）**：

| # | 位置 | 行為 |
|---|---|---|
| C1 | `control_api_v1/app/risk_routes.py:308-312` | fraction ×100 → GUI percent（注釋自證） |
| C2 | `risk_routes.py:934-945` | **同邏輯第二份複製**（同檔重複） |
| C3 | `app/risk_view_client.py:126-136` | GUI percent /100 → Rust fraction，單欄位特判（注釋警告 0.5→50% 事故形態） |
| C4 | `app/static/risk-tab.js:812` | **啟發式**：`p1_risk_pct < 1 ? ×100 : 原值` |
| C5 | `risk-tab.js:511`（fmtPctOrUnknown） | **啟發式**：`abs(n) <= 1 ? ×100 : n` |
| C6 | `risk-tab.js:931-934` | 雙名 fallback：`current_pct`（fraction）否則 `current_risk_pct/100`（percent）——後者**全 repo 零 producer**（grep 實測），死分支 |
| C7 | `app/paper_trading_routes.py:212-227` | 防禦性單位 sanity（`per_trade_risk_pct_not_rust_fraction` if >1；`position_size_max_pct_above_100`） |
| C8 | `program_code/ml_training/mlde_demo_applier.py:425,477` | clamp 下界按欄位名硬編碼（per_trade_risk_pct=0.0001/0.001，其他=1.0）——單位知識隱式散佈進 ML applier |

**D. 危險點（FACT+推斷）**：
- C4/C5 啟發式在「真 percent 值 ≤1」時必然誤判：per_trade 設 0.5%（route 送 0.5）→ C4 判 `<1` → ×100 → GUI 顯示 50%。C3 注釋證明團隊已知此坑但只修了寫入向，顯示向（C4/C5）仍是猜的。**severity HIGH / confidence HIGH（顯示層，非下單路徑；下單權威在 Rust，故非資金風險，是 operator 誤讀風險）**。
- `_pct` 命名對 fraction 欄位是系統性誤導（`flash_dip_buy_max_notional_pct_equity`=0.03、`per_trade_risk_pct`=0.1）；每個新 agent/工程師第一次都要重新考古。memory `feedback_position_sizing` 自身就把 0.05-0.20 fraction 記成「0.05-0.20%」——**單位混雜已實際污染治理記憶一次**。

### 1.2 設計：canonical 表示 + 邊界轉換函數

**Canonical 決策（E5 自選，理由註明）**：canonical = **各欄位現行單位不變 + 單位登記表顯式化**。不做全域改 fraction/改 percent 的數值遷移——那會觸碰三環境 TOML 生效值表示（`feedback_risk_changes_scoped` + 本任務鐵則「不改任何生效數值」),且 serde 欄位改名會破 `applier_riskconfig.rs:136-166` allowlist、mlde patch 路徑、GUI patch 鍵名等 IPC 契約面。統一的是「**單位知識的存放位置**」：從散佈在 8+ 個 consumer 的隱式知識，收斂為兩側各一張顯式表 + 唯一轉換函數。

**D6-1 Rust：`config/pct_units.rs`（新檔，~120 行）**
```rust
pub enum PctUnit { Fraction, Percent }
/// 每個 *_pct* 欄位一行，顯式註冊；漏註冊 = test fail
pub static UNIT_TABLE: &[(&str, PctUnit)] = &[
    ("limits.per_trade_risk_pct", PctUnit::Fraction),
    ("limits.position_size_max_pct", PctUnit::Percent),
    ("limits.flash_dip_buy_max_notional_pct_equity", PctUnit::Fraction),
    ("dynamic_sizing.step_pct", PctUnit::Fraction), /* … 全表 */
];
#[inline] pub fn percent_to_fraction(p: f64) -> f64 { p / 100.0 }
#[inline] pub fn fraction_to_percent(f: f64) -> f64 { f * 100.0 }
```
- `step_4_5_dispatch.rs:176`、`bounded_probe_active_order.rs:212`、`risk_checks.rs:171` 的 `/100.0`、`*100.0` 改走此二函數（同一浮點運算，bit-identical；15.0/100.0 與字面 0.15 IEEE 同值）。
- 註冊完備性測試：serde 序列化 `RiskConfig::default()` → 遞歸走所有含 `pct` 的 key path → 斷言每條在 UNIT_TABLE（防未來新欄位漏登記）。

**D6-2 Python：`control_api_v1/app/pct_units.py`（新檔，~60 行）**
- `UNIT_TABLE`（與 Rust 同表雙寫）+ `to_gui_percent(rust_key, v)` / `to_rust_value(rust_key, gui_percent)`。
- C1/C2（risk_routes 兩份重複 ×100）與 C3（risk_view_client /100）全部改調此模組；C2 的複製順手消除。
- 雙寫防漂移：contract test 把 Rust 側 UNIT_TABLE dump 成 JSON fixture（build script 或手動 golden 檔），pytest 斷言兩表逐條相等。

**D6-3 GUI：去啟發式（risk-tab.js）**
- C4（:812）：刪啟發式，直讀 route 的 percent 契約值（route 已保證 percent，:872-873 注釋自證）。
- C5（:511）：`fmtPctOrUnknown` 拆為 `fmtPctFromFraction(v)`（×100 顯示）與 `fmtPctDisplay(v)`（原值即 percent）兩個顯式函數；枚舉全部 caller（:529 等）逐一按欄位單位選用。
- C6（:931-934）：刪 `current_risk_pct` 死 fallback（零 producer，FACT）。
- 驗收 `node --check` + A3 目測 demo/live 面板。

**D6-4 四方一致性測試（TOML↔Rust↔Python↔GUI）**
1. **TOML↔Rust**（Rust test 或 pytest 讀 TOML）：三環境 TOML 逐檔載入 → fraction 欄位值 ∈(0,1]、percent 欄位值 ∈(0,100]；`per_trade_risk_pct` ∈[0.001,0.20] 與 `risk_config.rs:71-72` 常量同源斷言。**此測試同時是「生效數值零變更」的守衛**：D6 全部 commit 前後三環境 TOML `git diff` 必須為空。
2. **Rust↔Python**：golden vector（0.1→10.0、0.05→5.0、0.005→0.5、0.20→20.0）過 `to_gui_percent`/`to_rust_value` 往返 == 原值（bit-exact，`==` 不用 approx）。
3. **Python↔GUI**：route response 契約測試——`/api/.../risk` 回應中 `p1_risk_pct` 斷言等於 TOML fraction ×100；GUI 端無單測 harness（假設：repo 無 JS test runner，實測只有 node --check SOP）→ 消滅 C4/C5 啟發式後 GUI 成為「盲渲染」，一致性由 route 契約測試覆蓋即閉環。
4. **dynamic_sizing band**：斷言 `min_pct ≤ base(per_trade_risk_pct) ≤ max_pct` 三環境成立（現值 demo：0.01≤0.1？**注意：demo per_trade=0.1 > max_pct=0.05，band 錨點在 band 外**——這是既有現實，測試先以「記錄現狀」模式落地（snapshot assert），是否收斂交 operator/QC，**不在 D6 改值**）。⚠ 此點升 finding F-D6-1（見 §4）。
5. C8（mlde clamp）：把欄位單位判斷改引 `pct_units.UNIT_TABLE`，clamp 值不變。

**不做的事（鐵則）**：不改任何 TOML 值；不改欄位名（改名列 D6-5 defer 項，需 PA 另批：serde alias + IPC 鍵名遷移是另一個 sprint 的量）；不動 live 任何 gate。

**預估工作量**：Rust ~150 行新增 +6 行改動；Python ~80 行新增、~40 行改動；JS ~30 行改動；測試 ~250 行。E1 一人 0.5-1 天 + E2 審 0.5 天。

### 1.3 D6 衝突面（Phase B 排序約束）

| 衝突檔 | 誰會動 | 排序 |
|---|---|---|
| `step_4_5_dispatch.rs`（:174-176） | P1-1 over-gate 統一設計（bounded_probe 邊在本檔）、P1-11 1m gate、D7a 拆分 | D6 Rust 側排 **P1-1、P1-11 之後，D7a 之前**（拆分後行號全變，轉換函數改動先落免二次定位） |
| `bounded_probe_active_order.rs`（:197-212） | P1-1 可能重寫 admission 邊 | 同上，P1-1 後 |
| `risk_routes.py` / `risk_view_client.py` | P2-6 fake-success 掃描（read-only，E3/A3） | 無寫衝突，可並行 |
| `risk-tab.js` | P1-9 是 tab-live.js/console.html，不相交 | 可並行 |
| 三環境 TOML | D5 cost_edge arm 會寫 demo/live TOML | D6 不寫 TOML，零衝突 |

---

## 2. D7a — 熱檔拆分方案（P2-10 熱檔批）

先例 SOP（`c6f21fd57` event_consumer 拆分,FACT）：純機械搬移、搬移 block 逐位元組不變（Python byte-compare 驗證）、visibility 最小升級並逐項列數、mod/use/re-export 佈線、cargo test 通過數**嚴格相等**、tests/structure cap 集合更新、clippy 0 新警告。以下三案沿用全套驗收。

### 2.1 `rust/openclaw_engine/src/tick_pipeline/commands.rs`（2266 行）

**結構（FACT）**：18-56 檔內私有 `CloseOrderDispatchShape` + free fn `close_maker_audit_for_shape`；57 起單一 `impl TickPipeline` 到檔尾；**無 inline test mod**（僅 :77,:82 兩個 `#[cfg(test)]` test-helper 方法）。tick_pipeline/mod.rs:1420 `mod commands;`。
**拆分性質**：最乾淨的一檔——方法搬到 sibling 檔的新 `impl TickPipeline` 塊後，**所有 call site 零改**（方法綁在 type 上，與定義檔案無關），不需任何 re-export。

**5 檔方案（行號=2be58c191）**：

| 新檔 | 內容（行段） | 估行數 |
|---|---|---|
| `commands.rs`（保留） | use 頭 + CloseOrderDispatchShape 簇（18-56）+ maker-close accessors/test setters（57-170）+ `submit_external_order`（171-528）+ governor/risk-status/heartbeat accessors（529-640） | ~640 |
| `commands_fill_apply.rs` | `apply_confirmed_fill`（641-693）+ `apply_confirmed_fill_with_close_maker_audit`（694-969） | ~345 |
| `commands_close_dispatch.rs` | `execute_position_close`（970-1138）+ `close_position_after_exchange_dispatch`（1139-1162）+ `dispatch_close_maker_market_fallback`（1163-1300）+ `compute_close_reprice_limit`（1301-1332）+ `_for_pending`（1333-1360）+ `dispatch_close_maker_reprice`（1361-1476）+ `_for_pending`（1477-1508） | ~555 |
| `commands_close_lifecycle.rs` | `reconcile_pending_exchange_orders`（1509-1556）+ `converge_exchange_zero_close`（1557-1606）+ `ipc_close_all`（1607-1761）+ `resolve_close_entry_context_id`（1762-1772）+ `ipc_close_symbol`（1773-1974） | ~480 |
| `commands_status_snapshot.rs` | `grant_paper_auth`/`status`/`snapshot`/`set_system_mode`/`latest_prices`/`feed_replay_tick`/`check_and_clear_halt_expired`/`compute_halt_ttl_remaining_ms`（1975-2266） | ~305 |

全部 <800。`tick_pipeline/mod.rs` +4 行 `mod`。

**visibility 升級面（恰 3 項，比照先例逐項列）**：`close_order_dispatch_shape`（私有方法，:109）被移出檔的 :1016（→close_dispatch 同檔，免升）、:1649/:1850（→close_lifecycle 檔）呼叫；`CloseOrderDispatchShape` 與 `close_maker_audit_for_shape` 同理（:1023/:1657/:1858）。方案：三者隨簇搬進 `commands_close_dispatch.rs` 並升 `pub(super)`（tick_pipeline 內可見，其子孫 module 亦可見——與 on_tick 的既有 pub(super) 慣例同構）。CloseOrderDispatchShape 欄位若被跨檔直讀需同步升（搬移時逐欄位確認）。
**外部呼叫核對（FACT）**：`event_consumer/pending_sweep.rs:99,793` 與 `tick_pipeline/tests/dual_rail_dispatch.rs:705` 僅注釋/測試引用方法名，非跨模組符號依賴。

### 2.2 `tick_pipeline/on_tick/step_4_5_dispatch.rs`（2193 行）

**結構（FACT）**：1-57 docs/use；58-347 free helpers（~290 行，含 `pub(crate)` :58,:100 與 `#[cfg(test)] pub(crate)` :234,:255）；348-2185 `impl TickPipeline` 內**單一 1830 行方法** `on_tick_step_4_5_dispatch`（:363 起）；tests 已 `#[path]` 拆至 `step_4_5_dispatch_tests.rs`（1206 行，:2191-2193）。
**誠實聲明**:本檔無法用純機械手段降到 800——主 dispatch loop（~569-1827，~1260 行）是策略分派/intent 處理/回調強耦合熱路徑，硬切會造成參數爆炸與借用重構，風險>收益。目標設為「離 2000 硬限有安全邊際 + 可機械的部分全部拆走」。

**Stage 1（純機械，c6f21fd57 同級，先行）**：
- 58-347 free helpers → 新檔 `step_4_5_dispatch_support.rs`（~300 行含 use）。
- `pub(crate)` 項（`bounded_probe_soak_isolation_enabled_from_values`、`try_clone_panel_snapshot`、兩個 cfg(test) helper）走 `on_tick/mod.rs` 既有 `pub use` re-export 慣例（mod.rs:9-17 自文檔）保住外部路徑。
- 結果：2193 → ~1905。

**Stage 2（extract-method，非純機械，需 E2 sign-off）**——把方法尾部兩個借用邊界乾淨的階段抽為 `pub(super)` 私有方法至 sibling 檔：
- `step_4_5_deferred_closes(...)`（1986-2172，~187 行）：注釋自證「outside strategies_mut() borrow scope」（:1986），邊界最乾淨，**優先**。輸入=collected `pending_strategy_closes` 等 local；輸出=`close_confirmed_symbols`/`close_skipped_symbols`。
- `step_4_5_paper_sweep(...)`（1829-1985，~157 行）：paper resting-order sweep，同樣在主 loop borrow 結束後執行。
- 首段 context-capture（374-455）**列選項但不推薦**：與後續 borrow 交錯,參數面大回報低（推斷）。
- 結果：~1905 → ~1560。
- 剩餘 >800 部分：按 CLAUDE §九列 review-attention 檔監控，不在本批強拆（E5 判斷:年金化 token 稅低於強拆的一次性風險成本）。

**驗收（兩 stage 皆須）**：cargo test 通過數嚴格相等；搬移 block byte-compare（Stage 2 允許的唯一差異=函數簽名行與 local→參數改寫，逐行列入 commit message）；clippy 0 新警告；**Stage 2 追加**：Stage 0R replay parity（canary records bit-identical——tick 路徑重構的最強等價證據）+ hot_path bench 前後對照（方法呼叫預期被 inline，差異應 <1μs）。

### 2.3 `helper_scripts/research/cost_gate_learning_lane/status.py`（2238 行）

**外部 public surface（FACT，grep 實測）**：`summarize_cost_gate_learning_lane_{ledger,loop,historical_review,source,writer_config,writer_process}`、`build_cost_gate_learning_lane_activation_preflight`、`build_cost_gate_artifact_spine`、`ACTIVATION_PREFLIGHT_SCHEMA_VERSION`、`REQUIRED_SOURCE_RELATIVE_PATHS`、`main`。
Importers：`research/alpha_discovery_throughput/runtime_runner.py:19`（4500 行熱檔）、`db/audit/demo_learning_evidence_audit.py:41`（現役 cron lane）、`cron/demo_learning_stack_activation_packet.py:27`、**`cron/install_demo_learning_stack_crons.sh:121` 與 `install_cost_gate_learning_lane_cron.sh:160` 內嵌 python snippet**、tests ×3。install 腳本內嵌 import 無法原子同批改 → **facade 模式強制**：status.py 保留為 re-export 薄殼（比照 c6f21fd57 的 pub use 相容策略）。

**7 檔方案（行號=2be58c191）**：

| 新檔 | 內容（行段） | 估行數 | 衝突區 |
|---|---|---|---|
| `status_util.py` | 泛用 helpers（47-109 + 242-264：_write_json/_utc_now/_parse_dt/_age_seconds/_int/_float/_strip_env_value/_parse_env_bool/_read_json） | ~120 | 與 D7b lib 重疊：若 D7b Phase 1 先行，此檔大半變 import 轉發，可縮到 ~40 |
| `status_source.py` | REQUIRED_SOURCE_RELATIVE_PATHS（35-45）+ git/pin 簇（265-538：_run_git/_normalize_expected_head/**_expected_head_status**/_parse_git_status_line/**_source_reconcile_summary**/_summarize_git_checkout）+ summarize_source（1463-1506） | ~360 | ⚠ **P1-1/P1-4**（exact-head pin 死循環的判準函數就在這裡） |
| `status_ledger.py` | _latest_json_line/_file_mtime_age（539-597）+ summarize_ledger（598-815；:649 `read_text()` 全量重讀 = **P1-10 的 472MB 熱點本體**） | ~280 | ⚠ **P1-10/D9**（增量讀重寫必動此函數） |
| `status_loop.py` | summarize_loop（816-1416，600 行單函數）+ historical_review（1417-1462） | ~650 | — |
| `status_writer.py` | env/proc 偵測（110-241）+ writer config/process summary（1507-1681） | ~310 | — |
| `status_activation.py` | _plan_summary/_activation_decision/build_activation_preflight（1682-2109） | ~430 | P1-1 邊緣（activation gate 判準） |
| `status.py`（facade） | re-export 全 public surface + main/CLI（2110-2237） | ~180 | — |

**驗收**：搬移塊 byte-compare；`pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py test_alpha_discovery_throughput.py` + `cron/tests/` 全綠；`python3 -m cost_gate_learning_lane.status`（固定 fixture dir）CLI 輸出 canonical-JSON diff=0；外部 importer 清單逐條 import smoke。

### 2.4 D7a 統一排序約束

```
P0-1/D1(已完成) → P1-1 over-gate → P1-4 pin 派生 → P1-10/D9 ledger → P1-11 1m gate → D6(Rust側)
  → 之後才: commands.rs 拆分(衝突面最小,可先) → step_4_5_dispatch 拆分 → status.py 拆分(等 D7b Phase 1)
```
- commands.rs 唯一前置=P1-8 contract test（若 golden-vector fixture 引 commands.rs 行號則後拆；引方法名則無關——**推斷 P1-8 按方法名/wire format 錨定，衝突低**）。
- 三檔拆分均為獨立 commit、獨立可回滾（回滾成本=revert 單 commit，零語意風險）。

---

## 3. D7b — learning-lane 公共 lib 設計（P2-10 / F5）

### 3.1 重複塊盤點（FACT，87 檔 / 63,593 行，`2be58c191` 實測）

方法：同名 top-level `def` 跨檔計數 + 函數體 md5 判變異。**Top10（按可去重 LOC）**：

| # | 函數 | 份數 | 變異體 | dup LOC | 定性 |
|---|---|---|---|---|---|
| 1 | `_build_parser` | 74 | 每檔專屬 | ~1137 | **不遷**（CLI 骨架 by design；可選公共 add_common_args，ROI 低 defer） |
| 2 | `_artifact_summary` | 27 | 22 | ~744 | 半語意化，Phase 3 |
| 3 | `_authority_preserved` | 32 | **26 體 / 12 種簽名** | ~594 | **治理判準已實際 fork**（bool vs tuple[bool,list] vs 單 payload…4 檔有 danger_true_keys 17-18 鍵不等，28 檔各走各路）→ Phase 3 核心 |
| 4 | `_truthy` | 35 | 13 | ~585 | Phase 2 |
| 5 | `_read_json` | 74 | 15 | ~579 | Phase 2（error-tuple 派 vs raise 派） |
| 6 | `_parse_dt` | 43 | 5 | ~546 | Phase 2 |
| 7 | `_float` | 51 | 6 | ~396 | Phase 2 |
| 8 | `_write_json` | 58 | 7 | ~375 | Phase 2 |
| 9 | `_candidate_identity` | 21 | 12 | ~211 | Phase 3（identity 判準） |
| 10 | `_int` | 38 | 5 | ~191 | Phase 2 |

**byte-identical 全款（零風險批）**：`_utc_now` 81×1、`_list` 67×1、`_sha256` 20×1；近似：`_dict` 78×2、`_write_text` 50×2、`_str` 65×3。
**不可遷**：`render_markdown` 66 份 66 變異（每報告一版，by design）、`main` 80 份。
**合計**：top-21 helper dup ≈6,629 行；扣除不遷項 ≈**5,500 行可去重**（lane 總量的 ~8.6%）。
**既有基礎設施（FACT）**：lane 已是 package（`__init__.py` 存在），cron 以 `python3 -m cost_gate_learning_lane.X` + `PYTHONPATH=helper_scripts/research` 調用（`cron/cost_gate_learning_lane_cron.sh:713` 等 22 處模組調用實測）；已有共享模組 `contract.py`（16 行常量）、`proof_exclusion.py`（314 行）、`runtime_adapter.py`（838 行，自身也含一份 _utc_now.._str 重複）且 16 檔已 import contract → **跨檔 import 先例成立，遷移零基建成本**。

### 3.2 公共 lib API 草案

**`cost_gate_learning_lane/_lib.py`**（單一平面模組，理由：最低 import 稅 + 87 個 caller 一行 import；E5 自選，備選 `_lib/` 子包被否——多層 import 對 token 稅無益）：

```python
# coerce 族: _dict / _list / _str / _int / _float / _truthy / _round
# time 族:   _utc_now / _parse_dt / _age_seconds / _generated_at
# io 族:     _read_json_tuple (error-tuple 派) / _read_json_strict (raise 派)
#            _write_json / _write_text / _sha256 / _latest_json_line
# identity:  _candidate_identity / _candidate_key / _candidate_aligned
```
命名保留底線前綴原名（`from cost_gate_learning_lane._lib import _utc_now, _dict` 直接可用，migration diff 最小）。變異體不合併語意：行為分歧的以顯式雙函數（如 _read_json 兩派）或 kwargs 表達，**杜絕「合併時偷改語意」**。

**`contract.py` 擴充（治理判準正本）**：
```python
DANGER_TRUE_KEYS: frozenset[str]   # 32 個變體的鍵聯集,單一正本
def authority_preserved(*payloads, extra_danger_keys=(), extra_flag_fields=())
    -> tuple[bool, list[str]]      # 超集簽名,覆蓋 bool 與 tuple 兩派
def authority_preserved_bool(*payloads, **kw) -> bool   # 舊 bool 簽名薄殼
```
Canonical 語義=**聯集最嚴**（fail-closed:任一舊變體會 flag 的輸入,lib 必 flag）。**顯式聲明:對從較寬變體遷來的檔案這是行為變更（更嚴）**，方向符合 root principle 6（不確定默認保守），但必須逐檔對拍後才替換,且需 E2 sign-off。若某檔確有設計意圖需較寬判準,以 explicit kwarg 白名單表達,不留本地 fork。

### 3.3 遷移分期

| Phase | 範圍 | 驗等價方法 | 排序 |
|---|---|---|---|
| **0** | `_lib.py` + `contract.py` 擴充 + `tests/test_lane_lib_parity.py` 落地,不改任何現有檔 | 新增測試自證 | **可即刻**,零衝突 |
| **1** | byte-identical/準 identical 6 函數（_utc_now/_list/_sha256/_dict/_write_text/_str,~330 檔次）:刪本地 def + 加 import | 腳本化改寫;AST 級 diff 斷言「僅刪 def+增 import」;抽 3 個 cron 熱檔 CLI smoke 輸出 canonical-diff=0 | 冷檔子集（非 cron-22 且非 P1-1 觸碰檔）可與 P1-1 並行;熱檔批排 P1-1 後 |
| **2** | 低變異 IO/coerce 7 函數（_parse_dt/_float/_write_json/_int/_age_seconds/_truthy/_read_json） | 先產變異體語意分類表（每變異:行為差異+caller 依賴）;per-variant golden fixture 單測;逐檔按原變異選對應 lib 函數 | **全部排 P1-1 落地後**（authorization/admission/envelope 簇腳本是 P1-1 主戰場） |
| **3** | 治理判準（_authority_preserved 32 檔、_truthy_authority 12、_candidate_identity/_key、_artifact_summary） | 雙實現對拍:合成 payload 全排列 danger keys,舊 fn vs lib fn 逐檔 parity;更嚴方向差異逐條列給 E2;替換後刪本地 def | P1-1 後 + E2 sign-off;**與 P1-2/P2-7/P2-8 學習證據面批同窗最佳**（同一批 reviewer 上下文） |

**status.py 拆分（D7a）排 Phase 1 之後**：可少搬 ~150 行 util（§2.3 status_util.py 縮為薄殼）。
**runtime_adapter.py 自身**在 Phase 1 一併改 import（它是重複來源之一,非豁免區）。

### 3.4 D7b 衝突面

| 對手 | 相交面 | 處置 |
|---|---|---|
| **P1-1 over-gate 統一設計** | standing_demo_authorization*/bounded_probe_*/current_candidate_* 一大片 lane 腳本 | Phase 2/3 全排其後;Phase 1 排除其觸碰檔清單（派工時以 P1-1 PA spec 的檔案清單為準做差集） |
| **P1-10/D9 ledger rotation** | `runtime_adapter.read_jsonl_ledger` + status.py ledger 簇 | 該兩處 Phase 1/2 不碰,隨 D9 落地後再遷 |
| **P0-2 cron 對帳** | cron wrapper .sh（不在 lane 目錄） | 無寫衝突 |
| **P1-2 反事實成本模型** | `db/audit/cost_gate_reject_counterfactual.py`（lane 外） | 無寫衝突 |

---

## 4. 全量 findings 表（E5 輸出格式）

| 等級 | 位置 | 當前問題 | 建議改法 | 預估收益 | 回滾成本 | confidence |
|---|---|---|---|---|---|---|
| HIGH | risk-tab.js:511,812 | 單位嗅探啟發式,percent≤1 時顯示 ×100 錯 | D6-3 去啟發式 | operator 誤讀風險歸零;顯示層 | 單 commit revert | HIGH |
| HIGH | cost_gate_learning_lane（87 檔） | _authority_preserved 32 份 26 變異=治理判準 silent fork **已發生** | D7b Phase 3 聯集最嚴正本 | 判準 drift 面歸一;~594 行 | Phase 3 逐檔可回滾 | HIGH |
| HIGH | 同上（全 lane） | ~5,500 行 helper 重複 | D7b Phase 0-2 | 每輪 lane 審計/重構省 ~45-60k tokens 讀量;年金化 | 逐 phase revert | HIGH |
| MED | risk_config.toml 等 | fraction/percent 同區塊混雜,`_pct` 名對 fraction 欄位誤導 | D6-1/2 UNIT_TABLE 顯式化（改名 defer D6-5） | 單位考古成本歸零;曾污染治理記憶一次 | 純新增,零回滾面 | HIGH |
| MED | commands.rs 2266 / step_4_5 2193 / status.py 2238 | 破 2000 硬限熱檔 ×3 | §2 拆分方案 | 讀改頻率×體量 token 稅;Read cap 邊緣 | 各單 commit revert | HIGH |
| MED | risk_routes.py:308-312 vs :934-945 | ×100 轉換邏輯同檔複製兩份 | D6-2 收斂 pct_units | 去重+單點維護 | 隨 D6 revert | HIGH |
| MED（F-D6-1,新發現） | risk_config_demo.toml:268 區 vs :34 | dynamic_sizing band [0.01,0.05] 不含 base per_trade_risk_pct=0.1——sizer 錨在 band 外,首次調整即被 clamp 到 0.05（等效砍半） | **需 QC/operator 裁決**,D6 只落 snapshot 測試記錄現狀,不改值 | 語意澄清;可能是有意保守亦可能是 P2-12 混雜的實害 | n/a（不改） | MED（值判讀 FACT;意圖未證） |
| LOW | risk-tab.js:931-934 | `current_risk_pct` fallback 零 producer=死分支 | D6-3 刪 | ~4 行+讀者困惑 | 隨 D6 revert | HIGH |
| LOW | mlde_demo_applier.py:425,477 | 單位知識以 magic clamp 隱式編碼 | D6-4(5) 引表 | 可讀性 | 隨 D6 revert | HIGH |
| INFO | paper_trading_routes.py:212-227 | 防禦性單位 sanity 是好模式,D6 後可引 UNIT_TABLE 消除硬編碼判準 | 隨 D6 順手 | 一致性 | — | HIGH |
| INFO | intent_processor/mod.rs:893「Set P1 risk cap percentage (e.g. 0.03 = 3%)」 | docstring 用 "percentage" 描述 fraction,注釋層繼續傳播混雜 | D6 批注釋統一（中文,標 fraction） | 文檔誠實 | — | HIGH |

**假陽性候選（列出不剔除）**：F-D6-1 可能是有意的「dynamic sizing 只許更保守」設計（sig gate 注釋顯示 UP 路徑本就偏保守）;但若有意,`pipeline_config.rs:76` re-anchor 語意與 band 外錨的交互應有注釋而無——判斷依據兩面列上,交 QC。

## 5. 給實現 wave 的排序總覽

1. **可即刻**：D7b Phase 0（lib+parity test,純新增）;D6-4 之 TOML 範圍守衛測試（純新增,亦是 D5/D6 的共同回歸網）。
2. **P1-1/P1-4/P1-10/P1-11 落地後**：D6 全量 → D7b Phase 1 熱檔批+Phase 2 → commands.rs 拆分（可更早,見 §2.4）→ step_4_5_dispatch Stage 1→2 → D7b Phase 3（與學習證據面批同窗）→ status.py 拆分（吃 D7b Phase 1 紅利）。
3. 每步獨立 commit、獨立回滾;拆分 commit 禁夾帶任何語意改動（發現即修復原則在拆分 commit 內**暫停**——bug 另開 commit,保 byte-compare 可驗）。

