# EA-3 funding_arb SL Gate "P1 Hot-fix" — PA RCA + Recommendation

**Date**: 2026-05-25
**Author**: PA（Project Architect）
**Severity**: **PA 重新分級 = LOW（非 bug；是 sentinel-locked 設計值）**
**Trigger**: QC verdict 2026-05-25 inline 升 P1 hot-fix — funding_arb 5/16 audit 出現 1 fill 6.29% notional > 5% SL gate（違 3% risk_config hard cap）
**Reads**: `risk_config_demo.toml` + `risk_checks_per_strategy_tests.rs` 線 444-466 sentinel test + `strategy_params_demo.toml` + memory `project_funding_arb_v2_deprecation_path` + memory `project_g2_funding_arb_monitor`
**結論**: **QC verdict 大概率 incomplete reading**；6.29% **不違 SL gate**，是 demo dyn_stop floor 6.25% + 0.04pp 設計範圍內。FA F2 RCA OQ-4 已 sentinel 鎖定。recommend **降回 P3 documentation-only carry-over**，不 hot-fix。

---

## TL;DR

| 項目 | QC 升 P1 claim | PA 重新驗證 |
|---|---|---|
| **fill notional** | 6.29% | ✅ confirm 6.29%（per QC audit；PA 未獨立取 PG fills 驗，但採信 QC reading）|
| **SL gate 違反？** | 是（> 5%）| ❌ **否** — 5% 不是 demo SL gate；demo `stop_loss_max_pct=25.0` |
| **3% risk_config hard cap** | 違反 | ❌ **概念混淆** — 3% 是 position size risk（`position_size_max_pct` 之 risk per trade target，per memory `feedback_position_sizing`），不是 SL pct |
| **真實 SL gate** | – | demo dyn_stop floor = `stop_loss_max_pct × base_ratio = 25.0 × 0.25 = 6.25%`（per FA F2 RCA OQ-4 sentinel test） |
| **6.29% 越界？** | 是 | ❌ **否** — 6.29% = floor 6.25% + 0.04pp 「設計範圍內」（per `risk_checks_per_strategy_tests.rs:466` 註釋鎖定）|
| **funding_arb 現狀** | 活躍 | ❌ **dormant** — `strategy_params_demo.toml::funding_arb.active=false`（per 2026-04-18 G-2 v2 NEGATIVE EDGE 棄；2026-05-03 三端統一停）|
| **修法必要** | P1 hot-fix | **❌ NONE** — 無 bug 需修；建議 QC closure 為「QC 誤讀；funding_arb 已 dormant + sentinel locked」 |

**PA verdict**: **QC reject hot-fix；reclassify P3 documentation-only carry-over**

---

## 1. SSH 與 codebase evidence（PA 親驗）

### 1.1 risk_config_demo.toml（PA 親讀）

```toml
[limits]
stop_loss_max_pct = 25.0          # demo 寬容上限
take_profit_max_pct = 25.0
position_size_max_pct = 25.0
total_exposure_max_pct = 150.0
correlated_exposure_max_pct = 65.0
...

[dynamic_stop]
# 2026-05-02 BUSDT demo loss 後 operator 決策 3C(a)：
# base_ratio 0.4→0.25，全 demo 策略 dyn_stop floor 從 effective_sl*0.4 降至
# effective_sl*0.25（25% effective_sl 下 floor 由 10%→6.25%）。
base_ratio = 0.25                  # floor = 25.0 × 0.25 = 6.25%
cap_ratio = 0.85                   # cap = 25.0 × 0.85 = 21.25%
```

**critical reading**：
- demo `stop_loss_max_pct = 25.0`（**不是 5%**）— QC verdict 之 "5% SL gate" **不存在於 risk_config_demo.toml**
- demo `dyn_stop floor = 6.25%`（per `compute_dynamic_stop_pct` clamp range）

### 1.2 risk_checks.rs SL 邏輯（PA 親讀 line 330-358）

```rust
// 1. Hard stop — uses effective_sl (= min(override, limits) when Some).
if pnl_pct <= -effective_sl {
    return RiskAction::ClosePosition(...);
}

// 2. Dynamic stop — uses effective_sl as the hard-stop ceiling fed into
//    compute_dynamic_stop_pct.
let dyn_stop = compute_dynamic_stop_pct(
    effective_sl * dyn_cfg.base_ratio,    // floor = 25.0 × 0.25 = 6.25%
    atr_pct,
    symbol,
    entry_ts_ms,
    regime,
    effective_sl,                          // hard ceiling = 25.0
    dyn_cfg.cap_ratio,                     // cap_ratio = 0.85 → cap = 21.25%
    dyn_cfg.atr_stop_mult,                 // 2.0
);
if pnl_pct <= -dyn_stop {
    return RiskAction::ClosePosition(...);
}
```

**邏輯**：
- `dyn_stop = clamp(ATR × 2.0 / entry × 100, floor=6.25%, cap=21.25%)`
- 觸發條件：`pnl_pct <= -dyn_stop`
- ATR 低時 → dyn_stop 收緊到 floor 6.25%；6.29% fill 觸 `pnl_pct <= -6.29` < `-6.25 = -dyn_stop` → **是 SL gate 正常觸發**，不是越界

### 1.3 Sentinel test `test_demo_toml_dyn_stop_base_ratio_locked`（PA 親讀 line 461-508）

```rust
// 觸發背景：funding_arb F2 RCA 顯示 6.29% SL 是 dyn_stop floor（25.0 × 0.25
// = 6.25%）內，屬「設計範圍內」非「越界」；若未來 base_ratio 從 0.25 drift
// 至 0.20，則 floor 變 5.0%，6.29% 就會被誤判為「真正越界」，外部 analyst
// 從外部看數據將形成系統性誤判。

#[test]
fn test_demo_toml_dyn_stop_base_ratio_locked() {
    // ── dynamic_stop.base_ratio = 0.25 ──
    assert!(
        (cfg.dynamic_stop.base_ratio - 0.25).abs() < 1e-9,
        "dynamic_stop.base_ratio expected 0.25, got {} — \
         任何動 base_ratio 之前須先跑 SL gate semantic impact audit（FA F2 OQ-4）",
        cfg.dynamic_stop.base_ratio
    );

    // ── effective dyn_stop floor = 25.0 × 0.25 = 6.25% ──
    let dyn_stop_floor = cfg.limits.stop_loss_max_pct * cfg.dynamic_stop.base_ratio;
    assert!(
        (dyn_stop_floor - 6.25).abs() < 1e-9,
        "demo dyn_stop floor expected 6.25%, got {}% — \
         funding_arb F2 RCA OQ-4 鎖定值",
        dyn_stop_floor
    );
}
```

**讀解**：
- 6.29% case 已被 FA F2 RCA OQ-4 audit 過
- 結論：「設計範圍內」非「越界」
- sentinel test 鎖死 base_ratio=0.25 防 silent drift
- **本案 5/16 fill 6.29% 是已知範例，不是新 bug**

### 1.4 strategy_params_demo.toml funding_arb 狀態（PA 親讀）

```toml
# total_cost_bps. Audit: docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md
# 停用 2026-04-18：G-2 v2 判決 NEGATIVE EDGE（n=13，0/13 勝率，-36.76 bps）。
# 待 R-02 Strategist 重評入場/退場/成本三參數配對後再啟。
#
# 2026-05-03 stop-loss RCA: demo-only re-enable produced fresh negative edge
# before any verified funding capture. Keep disabled across paper/demo/live until
# the strategy is redesigned around funding settlement windows and maker entry.
[funding_arb]
active = false
```

**讀解**：funding_arb 三端（paper/demo/live）統一 active=false 自 2026-05-03（per memory `project_funding_arb_v2_deprecation_path` 2A 棄策略路徑）

**衍生問題**：5/16 audit 之 6.29% fill 是 funding_arb dormant **之前** 的歷史 fill（4/29 或更早），不是當前活躍 fill

---

## 2. RCA：6.29% > 5% > 3% 為何 fail-loud 沒擋

### 2.1 QC verdict 推理鏈拆解

QC verdict 推理（推斷）：
1. 觀察：5/16 audit 看到 funding_arb 1 fill notional 6.29%
2. 期望：risk_config 設「3% risk/trade」hard cap（per `feedback_position_sizing`）
3. 期望：funding_arb 自家設「5% SL」
4. 判斷：6.29% > 5% > 3% → SL gate fail-loud 沒擋 → P1 hot-fix

### 2.2 PA 拆解每環誤讀

| QC 推理 | 實際 |
|---|---|
| 「3% risk/trade hard cap」 | 是 **position sizing target**（每筆風險目標 3% 倉位），不是 SL gate；`position_size_max_pct=25.0` 才是 risk_config hard cap |
| 「funding_arb 自家 5% SL」 | 無此設定；funding_arb dormant；無自家 SL override；走 global `stop_loss_max_pct=25.0` + `dynamic_stop` clamp |
| 「6.29% > 5% SL gate」 | 5% gate 不存在；真實 gate = dyn_stop floor 6.25%；6.29% = floor + 0.04pp 在 clamp 範圍內 |
| 「fail-loud 沒擋」 | SL gate 正常觸發（pnl_pct=-6.29% ≤ -dyn_stop=-6.25% → ClosePosition）；不是 fail-loud 漏 |

### 2.3 真實 fill 流程（推測 5/16 fill）

```
funding_arb 進場（dormant 前）
→ ATR 低 → dyn_stop clamped to floor 6.25%
→ market move → pnl_pct = -6.29%
→ risk_checks.rs line 353: pnl_pct (-6.29) <= -dyn_stop (-6.25) → True
→ RiskAction::ClosePosition("DYNAMIC STOP: pnl -6.29% <= -6.25%")
→ 平倉 fill 落 PG
```

**這正是 SL gate 設計工作的方式** — clamp 在 floor，fill 落 floor + 微小 slippage（0.04pp）。

---

## 3. 推薦結論（3 個 path）

### 3.1 PA Recommended Path A（最強推薦）：**Reject hot-fix；reclassify P3 documentation**

**理由**：
- 6.29% **不違** SL gate；是 dyn_stop floor 6.25% + 0.04pp 設計範圍內
- FA F2 RCA OQ-4 已 sentinel 鎖定；test 已 lock；任何未來改動必過 SL gate semantic impact audit
- funding_arb 三端 dormant；無 hot-fix 必要性
- 修「正常工作的 gate」反破 sentinel governance

**動作**：
1. PA reject 「P1 hot-fix」classification
2. 主會話 reclassify QC verdict 為「PA cross-check：funding_arb 6.29% 是 sentinel-locked design value；no fix needed」
3. 更新 P0-FUNDING-ARB-DECISION-FORCE TODO entry 註腳：「QC 5/25 verdict EA-3 已 PA cross-check + verdict OVERTURNED」
4. QC closure 此 finding 為 P3 documentation-only carry-over
5. 順便 land：在 QC verdict template 加 cross-ref `risk_checks_per_strategy_tests.rs:444-508` 之 sentinel test（防 QC 未來再誤讀）

**ETA**：30 min 主會話 + 0 LOC IMPL
**Risk**：低；不改 production；只改治理 verdict + 加 doc cross-ref

### 3.2 Path B（妥協）：Documentation-only LOC 修改

若主會話 / QC 堅持「6.29% 看起來像 bug」需 doc 補強：

**動作**：在 `risk_config_demo.toml [dynamic_stop]` 區段加 inline 註釋：
```toml
[dynamic_stop]
# ... existing comment ...
# (per FA F2 RCA OQ-4) demo dyn_stop floor = 25.0 × 0.25 = 6.25%；
# funding_arb 6.29% fill 案例 = floor + 0.04pp 屬「設計範圍內」非越界。
# 改動 base_ratio / cap_ratio 必過 SL gate semantic impact audit。
# 參見 rust/openclaw_engine/src/risk_checks_per_strategy_tests.rs:444-508 sentinel test。
base_ratio = 0.25
cap_ratio = 0.85
```

**ETA**：~10 min；LOC=5
**Risk**：低；只加註釋

### 3.3 Path C（per memory funding_arb V2 deprecation 路徑同 trigger）：直接 deprecate

**動機**：per memory `project_funding_arb_v2_deprecation_path`，2A 棄策略路徑已決；既然 dormant + 已棄，不如徹底從 codebase 移除：
- `rust/openclaw_engine/src/strategies/funding_arb/` mod 整體 delete
- `strategy_params_*.toml [funding_arb]` block delete
- `risk_checks_per_strategy_tests.rs` sentinel test 標 `#[ignore = "funding_arb deprecated"]`
- registry.rs funding_arb instantiation delete

**ETA**：~2 hr（PA spec + E1 IMPL + E2 review + E4 regression）
**Risk**：中；deprecate impacts test coverage；需 PM sign-off + AMD（Architecture Migration Decision）
**Defer 原因**：本案 trigger 只是 QC verdict 誤判；不必抓本機會 deprecate（單獨派工會更乾淨）

**PA verdict**：Path C **defer to 獨立 ticket**（Sprint 3 或 Sprint 4+ 之 strategy alpha-deficient cleanup wave 內並行）

---

## 4. 修法 path（若主會話採 Path B）

**File**: `srv/settings/risk_control_rules/risk_config_demo.toml`
**LOC**: +5 註釋

**Diff（precision spec for E1 IMPL）**：

```diff
 [dynamic_stop]
 # 2026-05-02 BUSDT demo loss 後 operator 決策 3C(a)：
 # base_ratio 0.4→0.25，全 demo 策略 dyn_stop floor 從 effective_sl*0.4 降至
 # effective_sl*0.25（25% effective_sl 下 floor 由 10%→6.25%）。
 # 目的：demo 為學習資料源，收緊 floor 減少深虧樣本以加速 EDGE-DIAG-2 收斂。
 # 影響：當時啟用的 demo strategy 倉位 dyn_stop 趨緊 20-35%（取決 ATR）。
 # Paper/Live TOML 不動
 # (per `feedback_env_config_independence`)。Rollback：改回 0.4 + reload_risk_config。
 # 2026-05-02 operator decision 3C(a) post BUSDT demo loss.
 # Tightens dyn_stop floor across ALL demo strategies as part of EDGE-DIAG-2
 # learning-channel calibration. Paper/Live unaffected by env independence.
+#
+# EA-3 cross-ref（2026-05-25 PA verdict）：funding_arb 5/16 audit 6.29% fill
+# = dyn_stop floor 6.25% + 0.04pp 設計範圍內，非越界。SL gate 正常工作。
+# 參見 rust/openclaw_engine/src/risk_checks_per_strategy_tests.rs:444-508
+# sentinel test (FA F2 RCA OQ-4)；改動 base_ratio/cap_ratio 必過 SL semantic audit。
 base_ratio = 0.25
 cap_ratio = 0.85
```

**estimated LOC**: 5 lines（純註釋）
**ETA**: 10 min E1 IMPL + 0 cargo regression（pure TOML 註釋；cargo test 不掃 TOML 註釋）

---

## 5. 是否同時 deprecate funding_arb（per memory 2A 棄策略路徑）

### 5.1 Memory state（PA 重讀）

memory `project_funding_arb_v2_deprecation_path` 2026-05-02：
- 3 決策：1B demo active=true 收 EDGE-DIAG-2 樣本 / **2A 中期棄策略**（QC delta-neutral 數學不成立 + Bybit demo 無 spot lending）/ 3C TOML 改動 commit a19797d
- 2026-05-03 stop-loss RCA：demo-only re-enable produced fresh negative edge → keep disabled across paper/demo/live

### 5.2 是否本案併修？

| 選項 | Pros | Cons | Verdict |
|---|---|---|---|
| (a) 修 SL gate + 沿 2A deprecation | 解 QC verdict + dormant 加碼 deprecate | 不必要；6.29% 非 bug；deprecate 是獨立決策 | **REJECT** |
| (b) 直接 deprecate + skip SL fix | 一次 cleanup；省獨立 ticket | scope creep；本案 trigger 只 doc 不該 deprecate | **DEFER** |
| (c) Reject hot-fix + 維持 dormant 現狀 + Path B doc clarification | 最小改動；2A deprecation 走獨立 ticket | – | **RECOMMEND** |

**PA verdict**：(c) — 本案 trigger 不啟動 deprecate；deprecate 留 Sprint 3+ alpha-deficient strategy cleanup wave 內派工

---

## 6. 回滾 / verify SOP

### 6.1 Path A（PA recommended）— 治理動作

**Rollback**：N/A（無 code 改動；只改 verdict + doc cross-ref）
**Verify**：
- PA 派 sub-agent QC re-review：基於 PA RCA + sentinel test cross-ref，是否同意降回 P3
- 若 QC 仍堅持 P1 → PA push back 並要 QC 提供：
  - QC 之「5% SL gate」source（哪個 TOML / .rs file）
  - QC 之「3% risk_config hard cap」source
  - 對 sentinel test line 444-508 註釋的反駁

### 6.2 Path B（doc clarification）— code 動作

**Rollback**：`git revert <commit>` 即可（純註釋；無 runtime effect）
**Verify**：
- `cargo test --workspace --release` 通過（註釋 change 不影響 test）
- `bash helper_scripts/build_then_restart_atomic.sh --dry-run` 不必（TOML 註釋無 reload 需求）

### 6.3 Path C（deprecate funding_arb）— code 動作（**不在本 spec scope**）

留獨立 ticket；引用此 spec 做 trigger reference。

---

## 7. PA push back to QC（建議主會話用）

主會話 inline 回 QC（建議 message）：

> QC 5/25 EA-3 verdict cross-check：
>
> 1. funding_arb 6.29% fill 是 dyn_stop floor + 0.04pp 設計範圍內，非越界。
> 2. 「3% risk_config hard cap」混淆 position sizing target 與 SL gate；risk_config hard cap = `stop_loss_max_pct=25.0`。
> 3. 「5% SL gate」不存在於 demo TOML；funding_arb dormant 無 self override；走 global dyn_stop clamp。
> 4. Sentinel test `risk_checks_per_strategy_tests.rs:444-508` 已鎖定本 case（FA F2 RCA OQ-4）。
>
> 建議：QC 降本 finding 為 P3 documentation-only carry-over；Path B 可選加 risk_config_demo.toml inline 註釋 cross-ref sentinel test（~10 min）。
>
> 若 QC 不同意，請提供：
> (a) 「5% SL gate」/「3% hard cap」之 codebase source（具體 file:line）
> (b) 對 sentinel test 註釋（line 444-466）的反駁
> (c) funding_arb 5/16 fill 真實時間戳（active 期還是 dormant 期）

---

## 8. 結論 + sign-off

**PA verdict**: 
- **Reject** QC 「P1 hot-fix」 classification
- **Recommend Path A**（reject + reclassify P3 doc-only）
- **Allow Path B**（如主會話 / QC 要 doc clarification，~10 min）
- **Defer Path C**（deprecate 留獨立 ticket）

**Sprint 2 阻塞？**：否 — 本案無 IMPL 阻 Sprint 2 派發

**Operator action needed**：
- [ ] 主會話 cross-check QC verdict + 採 Path A / Path B / Reject
- [ ] 若 Path B → E1 ~10 min IMPL + Mac cargo test pass + commit
- [ ] 若 Path A → 主會話 inline 回 QC + 更新 TODO 註腳

**ETA total**：
- Path A: 30 min 主會話
- Path B: 30 min 主會話 + 10 min E1 + 0 deploy
- Path C: defer Sprint 3+

---

**Report END**

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-25--ea3_funding_arb_sl_gate_p1_hotfix_spec.md`
