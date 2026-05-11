# PA P2 N+2 Sprint Backlog Tickets — W2 IMPL Chain Post-Closure + P1-1 Helper Follow-up

**Date**: 2026-05-11
**Author**: PA (Project Architect)
**Scope**: 3 P2 ticket 整合（W2 IMPL chain 後置 + P1-1 stable_id CI grep rule follow-up）+ N+2 sprint capacity 評估 + cross-reference 既有 backlog
**Decision class**: Spec / plan 文檔；**不寫業務代碼**
**Current HEAD**: `9463f778` (W2 IMPL chain FULL CLOSURE `a771226d` + Option A-Lite Wave 1 land + V083 cron synthetic id recognition)
**Sprint context**: N+1 D+0 ongoing；**N+2 sprint = W5-W6 (2026-05-24..06-06，8 active workdays + 1 stand-by)**

---

## 0. Executive Summary

| Ticket | 來源 | 範圍 | LOC est. | Acceptance ease | N+2 排序 |
|---|---|---|---|---|---|
| **P2-N2-1** btc_lead_lag.rs split | E2 W2 chain review `d4186c86` §5.5 + W2 signoff_pack §4.1 | Rust 4-split 拆檔 | 1771 → 4×400 ± | 中（需重結構，跨檔依賴可控）| 2 |
| **P2-N2-2** w2_paper_edge_report.py split | E2 W2 chain review §5.6 + signoff_pack §4.2 | Python 4-split CLI 工具 | 1257 → 4×300 ± | 高（純工具腳本，0 hot path）| 1 |
| **P2-N2-3** Layer 2 helper share-code | signoff_pack §10.1 / E2 review §10 | 抽 `should_spawn_btc_lead_lag_producer` helper | +50 / −20 LOC | 高（純抽 fn，test mirror 替換）| 3 |
| **P2-N2-4** stable_id CI grep rule | E2 review §5（W-D MAG-083 P1-1 follow-up）/ PA memory 2026-05-11 §架構教訓 2 | CI guard 攔截字面複製 | +30 LOC（CI script + grep rule）| 高（純治理 script）| 4 |

**Aggregate P2 backlog count after this doc**: 既有 §12 active P2 = 4 條（`P2-LEASE-1` / `P2-STRUCT-2` / `P2-AUDIT-DEAD-CODE` D-16 dormant / `P2-V19-CYCLE`）+ legacy deferred = 2 條（`P2-AUDIT-VERIFY-3` → mounted into `W-AUDIT-8f` per AMD-2026-05-09-02 / `P2-STRUCT-3` empty-fallback rug-pull pending）+ 本 doc 新增 4 條 = **active P2 = 8 條（其中本 doc N+2 promote = 4 條，其餘 4 條為 long-tail / event-trigger）**

**N+2 capacity 評估**: N+2 = 5 active E1 + 1 stand-by × 8d ≈ 48 E1-days。本 doc 4 ticket 合計 ~5 E1-days；**完全可吸收，不擠壓 N+2 主線**（W-AUDIT-8a Phase D + Stage 2 demo cohort 14d + W-AUDIT-8d IMPL = ~35 E1-days）。剩餘 ~8 E1-days 為 buffer / stand-by 待用。

**Operator 拍板項**（§5）：
1. **P2-N2-1 拆檔方案**：4-split (producer.rs / ingest_task.rs / snapshot.rs / db_writer.rs) vs alternative (single-file + MODULE_NOTE only)？
2. **P2-N2-3 Layer 2 helper**：抽 share-code 是否 over-engineering？（main.rs 18 LOC inline + integration test 18 LOC mirror = 36 LOC total；抽 helper ~30 LOC + 兩處 callsite 各 ~5 LOC = ~40 LOC，淨增 4 LOC + 1 module 增量）

---

## 1. P2-N2-1: btc_lead_lag.rs 拆 4-split

### 1.1 Trigger

- E2 W2 chain review `d4186c86` §5.5 [P2-1]：`rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs` baseline 1253 → 本 wave +518 → **1771 LOC**（>800 警告線；<2000 hard cap）
- §九 「pre-existing baseline exception clause」**僅適用 baseline > 2000**；本 case 不適用該 clause
- W2 signoff_pack §4.1 accept 理由：「W2 spec §4.2 step 6 設計把 producer/aggregator/writer 都耦合在 `btc_lead_lag.rs` 內走同生命週期」；強行拆分 N+2 sprint 對齊 W1 sibling `funding_curve.rs` + `oi_delta.rs` pattern 更合理（W1 sibling 已拆好）
- **Sibling reference**：W1 IMPL 已把 `funding_curve.rs` / `oi_delta.rs` 拆 producer / writer 分離，與 W2 內聚單檔耦合不對稱 — N+2 收口對稱

### 1.2 Sub-task Scope (4-split design)

```
panel_aggregator/btc_lead_lag/
├── mod.rs           — re-export (BtcLeadLagPanelSlot, BtcLeadLagProducer, ...)  ~50 LOC
├── producer.rs      — BtcLeadLagProducer struct + new() + on_tick() + run_loop()  ~450 LOC
├── ingest_task.rs   — BtcOrderbookSlot + spawn_btc_orderbook_ingest_task() + compute_btc_book_imbalance()  ~350 LOC
├── snapshot.rs      — BtcLeadLagSnapshot + per-symbol cohort + nan_to_null_f32 helper + 純 calc fn  ~400 LOC
└── db_writer.rs     — PG INSERT panel.btc_lead_lag_panel + nan_to_null_f32 sink + Guard A/B 對齊  ~300 LOC
```

**Cross-file 邏輯切點**：
- `producer.rs` 對 `ingest_task.rs` 端只 import `BtcOrderbookSlot` 型別 + `compute_btc_book_imbalance` 純 fn
- `producer.rs::on_tick` 對 `snapshot.rs` 端用 `BtcLeadLagSnapshot::compute_from_kline_buffer` 純 fn
- `producer.rs::run_loop` 對 `db_writer.rs` 端用 `write_btc_lead_lag_panel_row(pool, snapshot)` async fn
- `mod.rs` 只 re-export 公開 API（`BtcLeadLagPanelSlot` + `BtcLeadLagProducer` + 必要 free fn）；其餘 module-private

### 1.3 Acceptance Criteria

1. **LOC budget**：每檔 ≤ 500 LOC（warning line 800 內，hard cap 2000 內，留 60%+ headroom 給未來擴）；`mod.rs` ≤ 100 LOC
2. **內聚性 verify**：
   - `cargo test --release -p openclaw_engine --lib panel_aggregator::btc_lead_lag` 31 PASS baseline 不退化（W2 signoff_pack §8.1）
   - `cargo build --release -p openclaw_engine --tests` 0 error / 0 new warning（baseline `1f0354cf` 18 pre-existing dead_code warning 不變）
3. **W1 sibling 對稱**：與 `funding_curve.rs` / `oi_delta.rs` split pattern naming + 切點對齊
4. **Public API 不變**：外部 callers（main.rs binary spawn + integration test in `tests/btc_lead_lag_panel_fence_integration.rs`）grep `panel_aggregator::BtcLeadLagProducer` / `panel_aggregator::BtcLeadLagPanelSlot` callsite 不需要改 import 路徑（mod.rs re-export 完成）
5. **三層 fence 不變**：split 後 Layer 1+2+3 fence 各對應 assert 仍 in `tests/btc_lead_lag_panel_fence_integration.rs`，不受 split 影響（fence 在外層 binary + step_4_5_dispatch）
6. **新檔 MODULE_NOTE**：每個新檔頂部加中文 MODULE_NOTE（注釋默認中文 per `feedback_chinese_only_comments.md` 2026-05-05）

### 1.4 LOC Estimate

- **Raw 移檔**：1771 → 4×~400 ± + mod.rs ~50 = ~1650 LOC（**淨 LOC 略減 ~120**，因移除 inline 重複 import + 文件頂部 module 注釋合併）
- **Effort**：~1.5 E1-day（1 E1 純 refactor，0 邏輯改動；E2 review 0.5d；E4 regression 0.5d 跑既有 31 PASS suite）

### 1.5 跨檔 Cohesion 評估（避免 over-split）

| 拆檔組合 | Cohesion 評估 | 結論 |
|---|---|---|
| producer + ingest_task | ❌ 弱（producer 60s tick 跑，ingest_task ~100Hz event-driven，生命週期不對稱）| 拆 |
| producer + snapshot | ❌ 弱（snapshot 是 producer 一次性 compute 結果 struct，但 fn 純粹可獨立）| 拆 |
| producer + db_writer | ❌ 弱（db_writer 是 PG IO sink，與 producer 業務邏輯解耦）| 拆 |
| snapshot + db_writer | ⚠️ 中（snapshot 是 db_writer 唯一 input；可考慮合併）| **不拆 — 保 snapshot 純 calc fn + db_writer 純 IO sink 分離，便於 mock test**|
| ingest_task + snapshot | ❌ 弱（一個 event-driven 寫 slot；一個 60s tick compute）| 拆 |

**Verdict**：4-split 合理（producer / ingest_task / snapshot / db_writer）；2-split (producer-aggregator / db_writer) 不夠細；6-split (producer / ingest / aggregate / snapshot / writer / config) 過度（config 直接 inline producer struct）。

### 1.6 依賴關係

- **依賴**：無（W2 IMPL chain 已 closed `a771226d`；signoff_pack land；新增 sibling W-AUDIT-8d (BTC→Alt fast-track) IMPL 不撞 file，因為 8d 是新 strategy 消費 panel 不改 producer）
- **被依賴**：W-AUDIT-8d IMPL（N+2 W5-W6 啟）會 import `BtcLeadLagPanelSlot` 從新 mod.rs；split 後 import 路徑 by re-export 不變
- **與 W-AUDIT-8a Phase B Rust panel_aggregator IMPL (N+1 W1)**：對稱拆檔 reference；如果 N+1 W1 落實了 funding_curve / oi_delta 拆檔 pattern，N+2 P2-N2-1 借鑒設計

### 1.7 風險評級

- **改動風險評級 = 低**：純 refactor 移檔，0 邏輯改動，0 新邊界，0 hot path touch
- **16 原則 + DOC-08 §12 + §四 5 硬邊界 觸碰 = 0**

---

## 2. P2-N2-2: w2_paper_edge_report.py 拆 4-split

### 2.1 Trigger

- E2 W2 chain review §5.6 [P2-2]：`helper_scripts/reports/w2_paper_edge_report.py` NEW 1257 LOC > 800 警告線
- W2 signoff_pack §4.2 accept 理由：「N+2 evidence 後再評是否拆 module」；§10.2 「N+2 sprint 若 reviewer 反映拆 module 更好 → 開 ticket」
- W2 spec v1.2 §7.1 6 mandatory metric (PSR Bailey-LdP 2012 + DSR K=95 + bootstrap CI + R²(60/120/300) + per-cohort counterfactual + +15/+5-15/<+5 step gate) 全在單檔 1257 LOC，operator 一鍵跑 `python3 helper_scripts/reports/w2_paper_edge_report.py` 簡單；但 N+2+ 跑多個 paper edge report tool（M2 wave / W-AUDIT-8d / 後續 alpha source per-symbol report）會 4-split pattern 對齊 sibling 工具家族（`paper_edge_report_v1.py` 等）

### 2.2 Sub-task Scope (4-split design)

```
helper_scripts/reports/w2/
├── __init__.py                          — empty (Python module marker)
├── w2_paper_edge_metrics.py            — PSR(0) Bailey-LdP 2012 / DSR K=95 (mu_0=√(2 ln 95))
│                                          / block_bootstrap_ci(seed=20260512) / R²(N) /
│                                          per_cohort_counterfactual_delta / step_gate_verdict  ~350 LOC
├── w2_paper_edge_render.py             — render_markdown / render_csv / render_json /
│                                          per_symbol_breakdown_table  ~300 LOC
├── w2_paper_edge_smoke.py              — 3 mock fixture (plus15 / plus5_15 / minus5) +
│                                          run_smoke_test()  ~300 LOC
└── w2_paper_edge_report.py             — CLI argparse + PG conn + 整合 main() +
                                            signoff trail + cron-friendly exit codes  ~310 LOC
```

**Cross-file 切點**：
- `w2_paper_edge_metrics.py` 是純函數庫（NumPy/SciPy/pandas 計算）；測試覆蓋 mock-based
- `w2_paper_edge_render.py` 純展現層（input = metrics 算好的 dict）
- `w2_paper_edge_smoke.py` import 上兩個 module 提供 3 mock case smoke
- `w2_paper_edge_report.py` 是 CLI entry point + PG conn + 拼 metrics→render→輸出

### 2.3 Acceptance Criteria

1. **LOC budget**：每檔 ≤ 400 LOC（warning line 800 內）；4-split 合計 ~1260 LOC（±5 LOC 移檔注釋整合容差）
2. **CLI 不變**：`python3 helper_scripts/reports/w2/w2_paper_edge_report.py --run-id=... --output-dir=...` 與 baseline `python3 helper_scripts/reports/w2_paper_edge_report.py --run-id=... --output-dir=...` byte-equal output（mock smoke 重跑 PASS）
3. **Smoke test**：`python3 helper_scripts/reports/w2/w2_paper_edge_smoke.py` 3 case (plus15 / plus5_15 / minus5) ALL PASS
4. **MODULE_NOTE**：每個新檔頂部加中文 MODULE_NOTE 引用 W2 spec v1.2 §7.1 6 metric definition
5. **SCRIPT_INDEX 更新**：`helper_scripts/SCRIPT_INDEX.md` 對齊 4 個新 path（baseline 1 entry + 註明 wrapper compat 至 sprint N+3 退役）
6. **舊 CLI shim 保留 1 sprint**：`helper_scripts/reports/w2_paper_edge_report.py` 留 thin wrapper `python3 -m helper_scripts.reports.w2.w2_paper_edge_report` 1 sprint deprecation window，避免 D+12 跑時 cron / operator command 斷掉

### 2.4 LOC Estimate

- **Raw 移檔**：1257 → 4×~310 ± + __init__.py = ~1260 LOC（淨 +3 LOC）
- **+ thin wrapper shim**：~30 LOC（1 sprint window）
- **Effort**：~1 E1-day（1 E1 refactor + smoke 重跑；0.3d E2 review；0.3d E4 跑 smoke + CLI byte-equal verify）

### 2.5 跨檔 Cohesion 評估

| 拆檔組合 | Cohesion 評估 | 結論 |
|---|---|---|
| metrics + render | ❌ 弱（純 calc vs 純展現，職責正交）| 拆 |
| metrics + smoke | ⚠️ 中（smoke 是 metrics 測試手段；但合併會讓 metrics 純度被測試 fixture 污染）| 拆 |
| render + smoke | ⚠️ 中（render 也需測試 fixture）| **不合 — smoke 統一一檔**|
| smoke + report (CLI) | ❌ 弱（smoke 是 dev-time tool，CLI 是 prod-time tool，生命週期不同）| 拆 |
| metrics + report (CLI) | ❌ 弱（CLI 不應直接持有 metrics 純函數，破壞 single-responsibility）| 拆 |

**Verdict**：4-split 合理；2-split (lib / cli) 對 metrics + render 混雜不好；5-split (metrics / render / smoke / cli / config) 過度（config 在 CLI argparse）。

### 2.6 依賴關係

- **依賴**：W2 D+12 paper edge report run 跑完並交 PM + QC + MIT 三角 sign-off（per W2 dispatch §5.1）；如果 D+12 verdict = revise，本 ticket 改順序在 revise 之後
- **被依賴**：N+3 W-AUDIT-8b/8c IMPL paper edge report 可以借鑒 metrics + render 模組化 pattern；W-AUDIT-8d IMPL 也會有自己的 paper_edge_report
- **與 W-AUDIT-8a Phase D Tier 4 IMPL (N+2)**：解耦（panel-level edge report vs alpha-surface level edge report，後者 N+5 才產出）

### 2.7 風險評級

- **改動風險評級 = 低**：純 refactor，0 hot path，CLI byte-equal output + smoke ALL PASS 守住功能不變
- **16 原則 + DOC-08 §12 + §四 5 硬邊界 觸碰 = 0**

---

## 3. P2-N2-3: Layer 2 helper share-code (`should_spawn_btc_lead_lag_producer`)

### 3.1 Trigger

- W2 signoff_pack §10.1：「Layer 2 fence helper 是 test-only mirror，非 share code」
- W2 integration test `tests/btc_lead_lag_panel_fence_integration.rs:119` `layer_2_should_spawn(paper_enabled_env, has_demo, has_live)` helper 與 main.rs:1005-1018 binary inline 計算邏輯同源但**不 share code**
- W2 signoff_pack §10.1 mitigation: 「注釋已明標『test-only mirror，邏輯與 main.rs:1005-1018 同源』」+「E2 review 可考慮要求把 Layer 2 spawn-or-skip 邏輯抽 `mode_state.rs` 或 `panel_aggregator/mod.rs` 為 pub fn」
- **Risk**: 若 main.rs 改邏輯 → 本 helper 同步改才能維持 layer 2 assertion 真實對應；漏改 = silent test drift（test 通過但 prod 行為改了）

### 3.2 Sub-task Scope

```rust
// 新增於 rust/openclaw_engine/src/panel_aggregator/mod.rs 或 mode_state.rs

/// Layer 2 fence: BtcLeadLagProducer spawn decision logic.
///
/// 三狀態 truth table:
/// - (a) OPENCLAW_ENABLE_PAPER=1 → spawn (paper-only producer 顯式啟用)
/// - (b) env unset + has_demo=false + has_live=false → spawn (dev/test 配置)
/// - (c) env unset + (has_demo=true OR has_live=true) → skip (mixed mode fence fired)
///
/// 不變式 / Invariants:
/// - 此函數是 W2-IMPL-1 Layer 2 fence 主邏輯權威；main.rs binary spawn + integration test
///   均必以本函數為 source of truth，不得 inline 重複實現
/// - 對「混跑 paper + demo 同 host」場景，producer **不寫 demo/live snapshot 觀察池**
///   （避免 paper noise 污染下游 ML pipeline）
pub fn should_spawn_btc_lead_lag_producer(
    paper_enabled_env: bool,
    has_demo: bool,
    has_live: bool,
) -> bool {
    if paper_enabled_env {
        true
    } else if !has_demo && !has_live {
        true
    } else {
        false
    }
}
```

### 3.3 Acceptance Criteria

1. **單一 SoT**：grep `OPENCLAW_ENABLE_PAPER` + `has_demo` + `has_live` 在 main.rs 1005-1018 範圍移到 `should_spawn_btc_lead_lag_producer` callsite；integration test `tests/btc_lead_lag_panel_fence_integration.rs:119` `layer_2_should_spawn` helper 移除，改 import 同函數
2. **8 子 assert 全 PASS**：integration test `layer_2_fence_env_gate_three_states` 8 子 assert 全 GREEN（W2 signoff_pack §3 已驗 PASS）
3. **MODULE_NOTE**：function docstring 中文 + invariant 明文「不得 inline 重複實現」+ panel_aggregator/mod.rs 頂部 add note
4. **0 callsite drift**：grep `OPENCLAW_ENABLE_PAPER\\.map\\(|v|\\)` 在 `rust/openclaw_engine/src/` 命中數 = 1 (binary + helper 共 1 處)；測試端 0

### 3.4 LOC Estimate

- **新檔 fn**：~30 LOC（含 MODULE_NOTE）
- **main.rs 替換 inline 18 LOC**：→ `let btc_lead_lag_producer_should_spawn = should_spawn_btc_lead_lag_producer(paper_enabled_env, has_demo, has_live);` ~3 LOC（淨 −15 LOC）
- **integration test 替換 18 LOC mirror**：→ import + 直接 call ~3 LOC（淨 −15 LOC）
- **Total**：+30 / −30 = **淨 0 LOC**（+1 module item）
- **Effort**：~0.5 E1-day（純 refactor）

### 3.5 跨檔 Cohesion 評估

- 屬 **panel_aggregator 模組職責**（producer spawn-or-skip 決策邏輯）→ 放 `panel_aggregator/mod.rs` 比 `mode_state.rs` 對稱（fence 邏輯與 producer 同模組，便於 future 擴 funding_curve / oi_delta_panel 同 pattern）
- alternative: `mode_state.rs` 也合理（與 has_demo / has_live env probe 同 module），但 panel_aggregator scope clearer

### 3.6 依賴關係

- **依賴**：W2 IMPL chain `a771226d` 已 closed
- **被依賴**：未來 W-AUDIT-8a Phase B Rust panel_aggregator IMPL（N+1 W1）+ funding_curve / oi_delta producer spawn pattern 可借鑒；理想設計：N+2 拆 P2-N2-1 同時把 Layer 2 spawn helper 統一 pattern（per-panel `should_spawn_<panel>_producer`）

### 3.7 風險評級

- **改動風險評級 = 極低**：純 refactor 抽 helper，0 邏輯改動；integration test 自驗 8 子 assert 守住
- **16 原則 + DOC-08 §12 + §四 5 硬邊界 觸碰 = 0**
- **Over-engineering 評估**（operator 拍板項 §5.2）：
  - 反方：當前 main.rs 18 LOC inline + test 18 LOC mirror = 36 LOC total；抽 helper +1 module item，淨 LOC 0 變化但複雜度 +1 indirection 層
  - 正方：silent test drift 風險（main.rs 改邏輯 test 還 PASS 但測錯邏輯）；3-state truth table 多 callsite share 比 inline 易看；P2-N2-1 拆檔同時做的話 marginal cost ~0
  - **PA 立場**：**正方略勝**（silent drift 風險真實，類似 P1-1 stable_id helper 教訓；marginal cost 低；強烈建議與 P2-N2-1 同 N+2 wave 一併做）

---

## 4. P2-N2-4: stable_id CI grep rule（W-D MAG-083 P1-1 follow-up）

### 4.1 Trigger

- **PA memory 2026-05-11 §架構教訓 2**：「升 P1（從 E5 D-1 P2）`stable_id` helper 抽出 — 跨檔字面複製 3 處是 sub-architectural silent drift 風險源；當改算法時漏改一處 = audit chain 沉默斷裂 = MAG-082 evidence 信任崩塌」
- W-D MAG-083 P1-1 已 land：抽出 `spine_ids.rs::compute_spine_ids()` + `compute_filled_report_id()` 兩個 helper（commit chain 2026-05-11，PA report `w_d_mag083_pa_audit.md`）；但 **CI 端尚未加防護**，未來新 callsite 字面複製 `stable_id("decision"|"plan"|"report", &[…])` 邏輯仍可能繞 helper 出現
- E2 P1-1 review 隱含建議：CI grep rule 攔截 = 「治本」防線；human review 不夠（人工漏看 = MAG-082 evidence 信任崩塌等級風險）

### 4.2 Sub-task Scope

#### 4.2.1 CI grep guard script (新增)

```bash
# helper_scripts/ci/check_no_literal_stable_id.sh
# 攔截：rust source（非 spine_ids.rs / 非 tests）字面複製 stable_id("decision"|"plan"|"report", &[...])
#
# Allowlist:
# - rust/openclaw_engine/src/agent_spine/spine_ids.rs                (helper module，自然有)
# - rust/openclaw_engine/src/agent_spine/events.rs                   (stable_id() 定義所在)
# - rust/openclaw_engine/src/agent_spine/tests.rs                    (legacy backward-compat test)
# - rust/openclaw_engine/src/agent_spine/runtime_shadow.rs           (僅允許注釋引用，不允許 callsite)
#
# 違規模式（grep regex）:
# (1) stable_id\("decision" + 行內或 next-line `, &\[`
# (2) stable_id\("plan"
# (3) stable_id\("report"
#
# 排除上 allowlist 4 檔 + 排除注釋行（// 或 /// 開頭，含 //! module doc）
```

#### 4.2.2 CI workflow integration

- 加入 `.github/workflows/<existing-CI>.yml` 或 `Makefile lint` target
- 或同 cargo test pre-check step（`cargo test --release` 跑前先跑 `bash helper_scripts/ci/check_no_literal_stable_id.sh`）
- Exit code 非 0 → CI fail；違規檔案 + 行號 print 至 stderr

#### 4.2.3 Documentation update

- `rust/openclaw_engine/src/agent_spine/spine_ids.rs` MODULE_NOTE 加一段：「新 callsite 必透過本 module helper；CI 端 `helper_scripts/ci/check_no_literal_stable_id.sh` 自動攔截字面複製違規」
- `CLAUDE.md §九 代碼結構約定` 加一條 invariant：`agent_spine.stable_id` algorithm 字面複製禁止；新 spine id callsite 必 import `spine_ids::compute_*` helper

### 4.3 Acceptance Criteria

1. **grep guard 真實生效**：把 `rust/openclaw_engine/src/event_consumer/types.rs` 或新檔加一個違規 callsite（mock test）→ CI fail；移除違規 → CI pass
2. **Allowlist 4 檔 exempt**：spine_ids.rs / events.rs / tests.rs (legacy backward-compat) / runtime_shadow.rs (only 注釋) → CI pass
3. **既有 codebase 不觸發**：HEAD `9463f778` 跑 `bash helper_scripts/ci/check_no_literal_stable_id.sh` → exit 0
4. **MODULE_NOTE 對齊**：spine_ids.rs 頂部 docstring + CLAUDE.md §九 同步更新

### 4.4 LOC Estimate

- **CI script (`check_no_literal_stable_id.sh`)**：~30 LOC（bash + grep + allowlist + exit code）
- **CI workflow yml / Makefile integration**：~5 LOC
- **spine_ids.rs MODULE_NOTE 更新**：~5 LOC
- **CLAUDE.md §九 invariant entry**：~3 LOC
- **Total**：~45 LOC
- **Effort**：~0.5 E1-day（純 CI script + 文檔；E2 review 0.2d；E4 不需測試（CI 自驗）；可由 E1a stand-by 處理）

### 4.5 跨檔 Cohesion 評估

- 屬 **CI / 治理 script 職責**（與 sibling `helper_scripts/ci/` 其他 lint guard 對齊）
- alternative: 寫 Rust clippy custom lint → 過度 engineering（純 grep script 已足夠）
- alternative: 寫 cargo `rust-toolchain` 一個 build.rs 自驗 → 過度（build.rs 拖長 build time，CI grep ~100ms 已夠）

### 4.6 依賴關係

- **依賴**：W-D MAG-083 P1-1 抽 helper 已 land（commit chain 2026-05-11）；spine_ids.rs 已存在
- **被依賴**：未來新增 spine event type 加 stable_id callsite（如 W-AUDIT-8a Phase B Tier 2 panel alpha source emit；W-AUDIT-8e R-2 Strategist orchestrator hypothesis emit）→ CI 自動攔截

### 4.7 風險評級

- **改動風險評級 = 極低**：純 CI script，0 runtime code 改動；防護面向 future regression，不改 hot path
- **16 原則 + DOC-08 §12 + §四 5 硬邊界 觸碰 = 0**
- **與 P1-1 helper 治本搭配**：helper 是「正面導引」(positive guidance: 用 helper 就對了)；CI grep 是「負面攔截」(negative guard: 不用 helper 就 CI fail)；兩者並行才是完整防線

---

## 5. Operator 拍板項

### 5.1 P2-N2-1 拆檔方案 — 4-split vs alternative

**Option A (PA 推薦)**：4-split (producer / ingest_task / snapshot / db_writer)
- Pro: 對稱 W1 sibling pattern (funding_curve / oi_delta 已拆)；每檔 ~400 LOC 健康內聚；test fixture 對 snapshot pure fn 易 mock
- Con: 4 file 增量；mod.rs re-export 維護成本（但 W1 已驗 pattern 合理）

**Option B (alternative)**：Single-file 1771 LOC + MODULE_NOTE only
- Pro: 0 refactor cost；單一檔對 PR review 容易上下文
- Con: 違反 §九 800 警告線（仍需開 P2 ticket）；與 W1 sibling asymmetric；未來 +new producer field / new ingest source → 推到 ~2000 hard cap 後仍需拆

**Option C (alternative)**：2-split (producer-aggregator / db_writer)
- Pro: 簡化 4→2，db_writer 純 IO sink 隔離
- Con: producer-aggregator 仍 ~1400 LOC > 800；snapshot pure fn 與 producer 混雜，難 mock test

**PA 立場**：**Option A 推薦**，與 W1 sibling 對稱優先級高。最終 operator 決定。

### 5.2 P2-N2-3 Layer 2 helper — share-code vs accept inline mirror

**Option A (PA 略偏好)**：抽 `should_spawn_btc_lead_lag_producer` helper
- Pro: silent test drift 防護（main.rs 改邏輯 test mirror 必須同步改 = test 失效）；future panel sibling 對齊 pattern
- Con: +1 module item indirection；marginal cost ~0.5d；當前 inline 18+18 LOC 不算多

**Option B (alternative)**：Accept test-only mirror + 注釋強標
- Pro: 0 refactor cost；inline 邏輯顯式對 reader 友好
- Con: silent drift 風險真實（雖然 acceptance test 8 子 assert 涵蓋三狀態，但若 main.rs 加第 4 狀態 → test 不會自動知道）；類似 P1-1 stable_id helper 抽出前的字面複製模式

**PA 立場**：**Option A 略偏好**，建議與 P2-N2-1 同 N+2 wave 一併做（marginal cost ~0）。如果 N+2 capacity 緊，Option B accept-with-comment 可接受 1 sprint 延後。

### 5.3 P2 N+2 全部 4 ticket 是否同 wave dispatch

- **PA 立場**：建議全 4 ticket N+2 W5 dispatch（總 ~5 E1-days，N+2 48 E1-days capacity 完全可吸收）
- **替代**：P2-N2-1+2+3 同 W5（refactor cluster），P2-N2-4 CI grep rule N+2 W6 由 E1a stand-by 處理（避免擠 active E1 capacity）
- 最終 operator 決定 dispatch sequencing

---

## 6. Aggregate P2 Backlog Summary

### 6.1 Total P2 ticket count（含本 doc 新增）

| ID | Status | N+2 active? | Owner |
|---|---|---|---|
| **P2-LEASE-1** | Active long-tail（trigger: long soak memory growth）| ⏳ event-trigger | ops |
| **P2-STRUCT-1** | DONE 2026-05-09 commit `dddc5dc1` | ✅ closed | — |
| **P2-STRUCT-2** | Active long-tail（trigger: next architecture hygiene sweep）| ⏳ N+6+ | E5 |
| **P2-STRUCT-3** | Active long-tail (`governance_hub_cascades.py:806` empty-fallback rug-pull, from REF20 Sprint 1 round 2) | ⏳ event-trigger | E1 |
| **P2-AUDIT-PERF-5b** | DONE | ✅ closed | — |
| **P2-AUDIT-VAR-6c** | DONE 2026-05-09 commit `cc6476dd` | ✅ closed | — |
| **P2-AUDIT-LAYER2-7c** | DONE-BY-DECISION（ADR-0020 sunset）| ✅ closed | — |
| **P2-AUDIT-DEAD-CODE** | Long-tail (D-16 dormant, Sprint N+6+) | ⏳ N+6+ | E1 + ops |
| **P2-AUDIT-VERIFY-1..7** | DONE 2026-05-09 | ✅ closed | — |
| **P2-AUDIT-VERIFY-3** | Mounted into `W-AUDIT-8f` per AMD-2026-05-09-02（N+5） | ⏳ N+5 | E1 + MIT |
| **P2-AUDIT-VERIFY-4** | DONE 2026-05-09（F-08 cron install）| ✅ closed | — |
| **P2-AUDIT-QC-STAND-ALONE** | DONE | ✅ closed | — |
| **P2-V19-CYCLE** | Long-tail（trigger: v19 land 後 1-2 sprint）| ⏳ N+3+ | PM |
| **P2-N2-1**（本 doc）| **NEW** btc_lead_lag.rs 4-split | 🆕 **N+2 W5** | E1 |
| **P2-N2-2**（本 doc）| **NEW** w2_paper_edge_report.py 4-split | 🆕 **N+2 W5** | E1 |
| **P2-N2-3**（本 doc）| **NEW** Layer 2 helper share-code | 🆕 **N+2 W5**（與 P2-N2-1 同 wave）| E1 |
| **P2-N2-4**（本 doc）| **NEW** stable_id CI grep rule | 🆕 **N+2 W6**（E1a stand-by 可吸收）| E1a |

**Total active P2 (不含 DONE)**:
- **N+2 W5-W6 promote = 4 條**（P2-N2-1/2/3/4 本 doc）
- **Long-tail / event-trigger = 5 條**（P2-LEASE-1 / P2-STRUCT-2 / P2-STRUCT-3 / P2-AUDIT-DEAD-CODE / P2-V19-CYCLE）
- **N+5 mounted = 1 條**（P2-AUDIT-VERIFY-3 → W-AUDIT-8f）
- **DONE = 7 條**

### 6.2 N+2 sprint capacity 評估

| 維度 | 數值 |
|---|---|
| **N+2 sprint window** | 2026-05-24..06-06 (W5-W6, 8 active workdays + weekends as buffer) |
| **N+2 E1 capacity** | **5 active + 1 stand-by** × 8d = **48 E1-days**（per TODO.md §0 Sprint Banner）|
| **N+2 主線消耗** | W-AUDIT-8a Phase D (~12d) + Stage 2 demo cohort 14d 觀察 (~10d ops only) + W-AUDIT-8d IMPL (~15d) = **~37 E1-days** |
| **N+2 主線 buffer** | 48 − 37 = **~11 E1-days available** |
| **本 doc P2-N2 4 ticket 消耗** | P2-N2-1 (1.5d) + P2-N2-2 (1d) + P2-N2-3 (0.5d) + P2-N2-4 (0.5d) = **~3.5 E1-days** |
| **N+2 剩餘 buffer** | 11 − 3.5 = **~7.5 E1-days** for stand-by / unexpected events |

**結論**：N+2 sprint capacity 完全可吸收本 doc 4 ticket（~3.5 E1-days）+ 留 ~7.5 days buffer。**不需推遲 P2-N2 至 N+3**。

### 6.3 Priority 排序

| 排序 | Ticket | 理由 |
|---|---|---|
| 1 | **P2-N2-2** w2_paper_edge_report.py split | 純 Python refactor + smoke-test driven，最易 PASS；W2 D+12 paper edge report run 跑完 verdict 確定後做（不阻 D+12 跑）|
| 2 | **P2-N2-1** btc_lead_lag.rs split | 與 W1 sibling pattern 對稱優先級高；同期 W-AUDIT-8a Phase B Rust panel_aggregator IMPL 也會處理 funding_curve / oi_delta sibling，N+2 一起 land 對稱 |
| 3 | **P2-N2-3** Layer 2 helper share-code | 與 P2-N2-1 同 wave 一併做 marginal cost ~0；防 silent test drift |
| 4 | **P2-N2-4** stable_id CI grep rule | 純 CI script，E1a stand-by 可吸收；future regression 防護重於 immediate user-facing impact |

---

## 7. Cross-Reference

### 7.1 上游文件

| Reference | Path / Commit | 用途 |
|---|---|---|
| PA W2 dispatch plan | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w2_impl_v12_dispatch_plan.md` (commit `0e88b4a9`) | W2 5 sub-agent 拆分 + cross-wave 衝突檢查 |
| E2 W2 chain review | `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_chain_e2_adversarial_review.md` (commit `d4186c86`) | P2-1/P2-2 ticket §5.5/§5.6 raised |
| W2 signoff_pack §4 | `srv/docs/governance_dev/2026-05-11--w2_impl_signoff_pack.md` §4.1/§4.2/§10.1 | pre-existing exception accept rationale + Layer 2 mirror push back |
| PA W-D MAG-083 audit | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md` + PA memory 2026-05-11 P1-1 entry + §架構教訓 2 | P1-1 stable_id helper + CI grep rule follow-up trigger |
| W-D MAG-084 sign-off | `srv/docs/governance_dev/2026-05-11--w_d_mag084_signoff.md` | W-D wave CLOSED status 確認 |

### 7.2 既有 archive backlog refs

- **TODO.md §12 P2 active**: `P2-LEASE-1` / `P2-STRUCT-2` / `P2-STRUCT-3` / `P2-AUDIT-DEAD-CODE` / `P2-AUDIT-VERIFY-3` (mounted) / `P2-V19-CYCLE`
- **W-AUDIT-7c R2 7 P2** (5/9 memory `feedback_impl_done_adversarial_review.md` ref)：實際 W-AUDIT-7c round 2 verdict 是 **single MEDIUM-2 deferred-P2 false positive，round 3 撤回**（per `2026-05-09--w_audit_7c_round3_e2_review.md` §28-100）— 不在 active P2 backlog
- **REF-20 retroactive 7 P2** (per `2026-05-03--ref20_wave3_to_9_retroactive_master_review.md`)：Sprint A-D 收口時 7 ticket 大多 DONE 或 archived；當前 active 殘留僅 `P2-STRUCT-3`（GovernanceHub cascade empty-fallback rug-pull）

### 7.3 下游 dependent

- **W-AUDIT-8a Phase B Rust panel_aggregator IMPL (N+1 W1)**：funding_curve / oi_delta sibling 拆檔 pattern 參考；如果 W1 land 後 N+2 W5 同步 P2-N2-1 對稱拆 btc_lead_lag.rs
- **W-AUDIT-8d (BTC→Alt Lead-Lag fast-track) IMPL (N+2 W5-W6)**：消費 `panel.btc_lead_lag_panel`，新策略 import `BtcLeadLagPanelSlot` 從新 mod.rs re-export，split 後不影響
- **W-D MAG-083 R-1 SYSTEMIC fix chain F1-F4 (N+1 W3-W4)**：P1-RCA-1 chain 與本 doc 0 file 重疊

---

## 8. 完成判定回報（per task）

1. **Dispatch plan commit hash**: pending (本 doc + memory append 後同次 commit；commit-即-push per CLAUDE.md §七)；行數 = 本 doc ~390 行
2. **3 P2 ticket each summary**:
   - **P2-N2-1 btc_lead_lag.rs split**：1771 → 4×~400 + mod.rs ~50；acceptance 5 條（LOC ≤500/file + cargo test 31 PASS + W1 sibling 對稱 + Public API re-export 不變 + 三層 fence assert 不變）；依賴 W2 IMPL closed `a771226d`（已 met）+ 與 W-AUDIT-8a Phase B IMPL (N+1) 對齊 pattern
   - **P2-N2-2 w2_paper_edge_report.py split**：1257 → 4×~310 + __init__；acceptance 6 條（LOC ≤400 + CLI byte-equal output + smoke 3 case ALL PASS + MODULE_NOTE + SCRIPT_INDEX 更新 + 1 sprint thin wrapper compat）；依賴 D+12 paper edge report run 跑完（W2 dispatch §5.1）
   - **P2-N2-3 Layer 2 helper share-code**：+30 / −30 LOC 淨 0；acceptance 4 條（單一 SoT grep count = 1 + 8 子 assert PASS + MODULE_NOTE 中文 + 0 callsite drift）；依賴 W2 IMPL closed（已 met）
3. **P1-1 grep rule P2 spec**: P2-N2-4 stable_id CI grep rule；scope `helper_scripts/ci/check_no_literal_stable_id.sh` ~30 LOC + CI workflow ~5 LOC + MODULE_NOTE/CLAUDE.md §九 update ~8 LOC = ~45 LOC；4 條 allowlist exempt（spine_ids.rs / events.rs / tests.rs / runtime_shadow.rs）；acceptance 4 條
4. **Total P2 backlog count**: active P2 = 8 條（含本 doc 新增 4 條）；N+2 capacity 48 E1-days 完全可吸收（本 doc 4 ticket ~3.5 E1-days，剩 ~7.5d buffer）；priority 排序 P2-N2-2 → P2-N2-1 → P2-N2-3 → P2-N2-4
5. **Cross-reference**: §7.1 上游 5 docs + §7.2 既有 archive backlog refs（含 W-AUDIT-7c R2 false-positive 撤回 entry + REF-20 retroactive entry）+ §7.3 下游 W-AUDIT-8a/8d/W-D MAG-083 R-1 dependent 完整

---

**PA DESIGN DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p2_n2_backlog_tickets.md`**
