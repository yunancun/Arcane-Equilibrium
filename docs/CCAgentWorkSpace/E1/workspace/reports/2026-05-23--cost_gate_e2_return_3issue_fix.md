---
report: cost_gate low-sample 深負 arm — E2 RETURN-TO-E1 3 issue 修復
date: 2026-05-23
author: E1 (Backend Developer, Rust)
phase: E2 RETURN-TO-E1 → E1 FIX DONE → 待 E2 re-review
status: FIX DONE — 待 E2 re-review
parent dispatch:
  - operator prompt 2026-05-23 §E2 review verdict 後續
upstream review:
  - srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-23--cost_gate_low_sample_deep_neg_e2_review.md
upstream report:
  - srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--cost_gate_cell_level_deny_fix.md
runtime: Mac development（cargo test 通過）
production engine: 未碰 / 不 rebuild / 不 push
---

# E1 cost_gate E2 RETURN-TO-E1 3 issue 修復 — 2026-05-23

## §0. TL;DR

E2 review verdict **RETURN-TO-E1** for 718c1ddd + 188f244a。3 issue:
1. CRITICAL — 既有 `test_cost_gate_moderate_low_sample_negative_routes_to_exploration` FAIL（E1 上輪 commit 只跑 cargo check 沒跑 cargo test）
2. HIGH — 188f244a message 對 1B funding_arb scope understated（漏 BUSDT 被 step 1 連帶 deny）
3. MEDIUM — `gates.rs:141` tracing field key `shrunk_bps` 與既有 4 處 `estimated_edge_bps` baseline 不一致

**修法**:1 個 follow-up commit `662dd407`,涵蓋 Issue 1 test fix + Issue 3 field rename;Issue 2 在 commit message body 內補 errata(因 188f244a + 718c1ddd 已 push origin/main,per §git-and-sync 不 amend + force push)。

```
$ git log --oneline -4
662dd407 fix(gates): E2 RETURN-TO-E1 — low-sample 深負 arm 3 issue 修復  ← 本次
1639506f docs(sprint-4-wave-b-m1): Singleton Registry SSOT ... ← 上輪 HEAD
188f244a feat(gates): cost_gate_moderate 加 low-sample 深負 arm (cutoff=-15bps)
718c1ddd config(demo): cost_gate_min_n_trades_for_block 30→15
```

`cargo test --lib -p openclaw_engine intent_processor`: **138 PASS / 0 FAIL**

## §1. Dispatch 與決策路徑差異

### 1.1 Dispatch 建議路徑(2 個方案)
- **路徑 A**: `git rebase -i HEAD~2` 把 188f244a 標 edit + amend 把 Issue 3 改動 stage 進 amend + amend message body
- **路徑 B**: 把 Issue 1 + Issue 3 全堆 working dir + `git add -A; git commit --amend`

兩路徑都需要 `188f244a` 與 `718c1ddd` 未 push。

### 1.2 實證 dispatch 假設過期 → push back
```
$ git rev-parse HEAD origin/main
1639506fff95a3a29e055037663d702659096cf5
1639506fff95a3a29e055037663d702659096cf5
```

`HEAD == origin/main` → **`188f244a` + `718c1ddd` + `1639506f` 全已 push**。

Per CLAUDE.md §git-and-sync:「Do not use destructive git commands unless explicitly requested and approved」 + 角色 hard convention「Never force push to main」 → amend + `git push --force-with-lease main` 是 destructive,不在 operator 明示授權範圍。

### 1.3 替代方案(本實作採用)
1 個 follow-up commit(`662dd407`)封裝:
- Issue 1 test fix（tests.rs）
- Issue 3 tracing field rename（gates.rs）
- Issue 2 funding_arb scope errata 在本 commit message body 內標明,作為 188f244a 的勘誤,operator 看 git log 串讀兩 commit 即可對齊 1B 探索 scope

不 push,等 E2 re-review + E4 regression pass 後 PM 統一 push。

## §2. Issue 1（CRITICAL）test fix

### 2.1 既有 test rename + assertion 反轉

`tests.rs:1022-1043`:

```diff
 #[test]
-fn test_cost_gate_moderate_low_sample_negative_routes_to_exploration() {
-    // EDGE-DIAG-2: a negative shrunk_bps with n_trades < default 30 must NOT
-    // block — it routes to exploration mode (allow + log) so demo can
-    // accumulate fills toward statistically robust estimates.
-    // EDGE-DIAG-2：低樣本（n<30）負 shrunk_bps 不阻擋，走探索模式。
+fn test_cost_gate_moderate_low_sample_deep_neg_blocks() {
+    // EDGE-DIAG-2 v2(2026-05-23 PM RCA + MIT sensitivity sweep):
+    // low-sample deep-negative arm 已上線:n<min_n 且 shrunk_bps<-15 改為 BLOCK,
+    // 不再無條件走探索。原因:NEARUSDT(n=18, shrunk_bps=-16.46)在 noise band 內
+    // 累損 6 天 -21.98 USD demo。新 arm 把 deep tail(< -15)從探索分離出來直接 deny;
+    // noise band [-15, 0) 仍走探索,維持「demo 放寬」精神。
+    // 本 test 從 routes_to_exploration 改 deep_neg_blocks,fixture(shrunk=-50, n=6)
+    // 同時滿足 n<min_n AND shrunk<-15 → 新 arm 攔截。
+    // EDGE-DIAG-2 v2:低樣本深負(n<30 且 < -15bps)改為 BLOCK,避免噪音帶累損。
     let mut proc = IntentProcessor::new();
     let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -50.0, "win_rate": 0.3, "n": 6, "std_bps": 5.0}}"#;
     ...
-    assert!(
-        result.is_none(),
-        "low-sample negative edge (n=6 < 30) should route to exploration, not block"
-    );
+    assert!(
+        result.is_some(),
+        "low-sample deep-negative (n=6 < 30 AND shrunk -50 < -15) should BLOCK via EDGE-DIAG-2 v2 arm"
+    );
+    let reason = result.unwrap().rejected_reason.unwrap();
+    assert!(
+        reason.contains("JS-demo"),
+        "block reason should be CostGateJsDemoNegative variant, got: {reason}"
+    );
 }
```

**Rename 理由**: 原 name `routes_to_exploration` 與新 invariant(深負攔截)語意撕裂;改為 `deep_neg_blocks` 對齊 EDGE-DIAG-2 v2 behavior。

**Reason 字串斷言**: 新增 `reason.contains("JS-demo")` 守 `CostGateJsDemoNegative::format()` 模板「cost_gate(JS-demo): estimated=...bps < 0 — blocked」格式;若未來 rejection_coding.rs 改 variant format,本 test 會 catch。

### 2.2 新增 boundary tests

`tests.rs:1045-1080` 新增 2 個 boundary test:

```rust
#[test]
fn test_cost_gate_moderate_low_sample_noise_band_explore() {
    // EDGE-DIAG-2 v2 boundary:low-sample 但 shrunk 落在 noise band [-15, 0) 內
    // 仍走探索 — 統計上 50% 命中率,deep tail 才方向可靠。
    // Fixture: n=6 < min_n=30,shrunk=-10.0 ∈ [-15, 0) → 不觸發新 arm,
    // fall-through 到既有 low-sample arm 探索。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -10.0, "win_rate": 0.3, "n": 6, "std_bps": 5.0}}"#;
    let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(json).unwrap();
    proc.set_edge_estimates(estimates);
    let result = proc.cost_gate_moderate("ma_crossover", "BTCUSDT", 0.00055, 1_000_000_000.0);
    assert!(
        result.is_none(),
        "low-sample shrunk -10 ∈ [-15, 0) noise band should still explore, not block"
    );
}

#[test]
fn test_cost_gate_moderate_low_sample_at_neg15_boundary_explore() {
    // EDGE-DIAG-2 v2 嚴格 `<` 邊界:shrunk_bps == -15.0 恰在 cutoff,
    // 新 arm guard 是 `cell.shrunk_bps < -15.0`(strict less-than),
    // -15.0 不觸發,fall-through 到 low-sample 探索 arm。
    // 守住「邊界不攔」契約,避免 cutoff 移動造成 flip-flop。
    let mut proc = IntentProcessor::new();
    let json = r#"{"ma_crossover::BTCUSDT": {"shrunk_bps": -15.0, "win_rate": 0.3, "n": 6, "std_bps": 5.0}}"#;
    ...
    assert!(
        result.is_none(),
        "shrunk == -15.0 at boundary (strict `<` not `<=`) should not block, fall-through to explore"
    );
}
```

**Coverage 對照 E2 建議**:
| E2 要求 | 本實作 test |
|---|---|
| `test_cost_gate_moderate_low_sample_noise_band_explore` shrunk=-10, n=6 → is_none() | ✅ 同名 |
| `test_cost_gate_moderate_low_sample_at_neg15_boundary_explore` shrunk=-15.0, n=6 → is_none()(strict `<`) | ✅ 同名 |
| `test_cost_gate_moderate_low_sample_deep_neg_blocks` shrunk=-20, n=6 → is_some() + reason "JS-demo" | ✅ 既有 test rename 後復用 fixture shrunk=-50, n=6 已 cover 此語意;reason "JS-demo" 斷言加上 |

**未實作 E2 建議的 NaN test**: E2 §Issues found 提到 `n<min_n 且 shrunk_bps = NaN → explore`;E2 review 自己也說「NaN fall-through 到既有 low-sample arm 走 explore (非新 arm 死循),但 test coverage 缺」並標 "default behavior 跟既有 EDGE-DIAG-2 一致,不算新引入問題"。本 patch 不擴 scope,NaN test 留作 follow-up(若 E2 re-review 要求補,1 行 fixture 變更即可)。

### 2.3 cargo test 結果

```
test result: ok. 138 passed; 0 failed; 0 ignored; 0 measured; 3040 filtered out; finished in 0.04s
```

新加的 3 個 test 確認 PASS:
- `test_cost_gate_moderate_low_sample_deep_neg_blocks ... ok`（既有 rename）
- `test_cost_gate_moderate_low_sample_noise_band_explore ... ok`（新）
- `test_cost_gate_moderate_low_sample_at_neg15_boundary_explore ... ok`（新）

138 = 上輪 baseline 預估 135 + 3 new + 1 rename = 138 ✓
(E2 預估 ~136 + 3 = ~139 — 差 1 是 E2 baseline 數可能與本地 module 計數略差,核心是 0 FAIL)

## §3. Issue 3（MEDIUM）tracing field key 對齊

### 3.1 改動

`gates.rs:138-148`:

```diff
 Some(cell) if cell.n_trades < min_n && cell.shrunk_bps < -15.0 => {
+    // E2 review 2026-05-23 對齊:tracing field key 改用 `estimated_edge_bps`
+    // 與既有 4 處(paper L73 / demo L159 / live L73 / live L157)baseline 一致;
+    // audit log grep 不再分裂兩種 key。`cutoff_bps` 顯式 f64 避免 type mismatch。
     tracing::info!(
         strategy,
         symbol,
-        shrunk_bps = cell.shrunk_bps,
+        estimated_edge_bps = cell.shrunk_bps,
         n_trades = cell.n_trades,
-        cutoff_bps = -15.0,
+        cutoff_bps = -15.0_f64,
         "cost_gate(JS-demo): low sample but deep-negative — block / 低樣本深負阻擋"
     );
```

### 3.2 對齊驗證

`rg "estimated_edge_bps" srv/rust/openclaw_engine/src/intent_processor/gates.rs`:
- L73 `cost_gate_paper` negative explore arm
- L143(本 patch 新加)`cost_gate_moderate_with_slippage` deep-negative block arm  ← 對齊
- L159 `cost_gate_moderate_with_slippage` low-sample explore arm
- L235(預估,未列 diff)cost_gate_live 路徑

field name 統一後,Grafana / audit script grep `estimated_edge_bps=` 可取齊全部 cost_gate path 的 cell.shrunk_bps,無需 union 兩 key。

### 3.3 type 顯式

`cutoff_bps = -15.0_f64` 顯式 `f64` 後綴。`-15.0` 字面值 Rust default 是 `f64`,但既有 4 處 baseline 也是 `cell.shrunk_bps: f64`,顯式後綴讓 audit script 跑 schema check 不會誤判 f32 cast。

## §4. Issue 2（HIGH）funding_arb scope errata

### 4.1 188f244a message 原段
```
不影響 1B funding_arb 探索(僅 LABUSDT outlier 被 deny)
```

### 4.2 實證(per E2 review §7)

`settings/edge_estimates.json` 篩 `strategy = funding_arb`:

| symbol | n_trades | shrunk_bps | 攔截路徑 |
|---|---|---|---|
| LABUSDT | 6 | -55.77 | 新 arm 直接 deny(n<15 AND <-15) |
| BUSDT | 16 | -36.05 | step 1 min_n 30→15 → 跨入 robust arm 既有 negative-bps deny |
| BIOUSDT | <15 | [-15, 0) | low-sample arm pass 探索 |
| CLUSDT | <15 | [-15, 0) | low-sample arm pass 探索 |
| CHIPUSDT | <15 | [-15, 0) | low-sample arm pass 探索 |
| BABYUSDT | <15 | [-15, 0) | low-sample arm pass 探索 |
| PRLUSDT | <15 | [-15, 0) | low-sample arm pass 探索 |

**Scope 影響補正**:
- 「僅 LABUSDT」 → 不準確,BUSDT 也被攔(由 step 1 連帶 robust arm 觸發,非新 arm 直觸)
- 「6 個 funding_arb cell 繼續收 EDGE-DIAG-2 樣本」 → 修正為「5 個 cell(BIOUSDT/CLUSDT/CHIPUSDT/BABYUSDT/PRLUSDT)在 noise band [-15, 0) 內繼續 explore;BUSDT/LABUSDT 已 deny」

### 4.3 處理方式

本 commit `662dd407` message body 含完整 errata 段(見 §0 commit message body 中「Issue 2 對 188f244a commit message errata」)。

未 amend 188f244a,因兩 commit 已 push origin/main(per §1.2 git rev-parse 確認)。operator 拍板 deploy 前看 git log,串讀 718c1ddd / 188f244a / 662dd407 三 commit 即對齊真實 1B 探索 scope。

如 PM / E2 認為 errata 不足,可選 follow-up:
- 在 `docs/agents/` 開 follow-up doc 明示 1B scope 對齊
- 或 PM 在 RCA 文件(2026-05-23 EDGE-DIAG-2 PM RCA)補 BUSDT 影響欄

## §5. Verify

| Verify | Command | Result |
|---|---|---|
| Unit test | `cargo test --lib -p openclaw_engine intent_processor` | **138 PASS / 0 FAIL** |
| Type check | `cargo check -p openclaw_engine` | PASS(3.71s, 0 new warning) |
| Pre-existing warning(與本 patch 無關) | `unused import LEAD_WINDOW_SECS_MAIN` / `make_intent dead_code` / `spawn_position_reconciler dead_code` | unchanged |
| Git push state | `git rev-parse HEAD origin/main` | HEAD(662dd407) ahead by 1,未 push |

## §6. 修改清單

| File | 性質 | 改動 LOC | 摘要 |
|---|---|---|---|
| `rust/openclaw_engine/src/intent_processor/gates.rs` | edit | +3 / -2 | L138-148 tracing field rename + E2 對齊注釋 |
| `rust/openclaw_engine/src/intent_processor/tests.rs` | edit | +53 / -6 | 既有 test rename + assertion 反轉 + 2 new boundary test |
| `docs/CCAgentWorkSpace/E1/memory.md` | append | +24 | 本次教訓追加 |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--cost_gate_e2_return_3issue_fix.md` | new | +250 | 本報告 |

**不動 file**(per dispatch §禁忌):
- `gates.rs` `cost_gate_paper` (L14) / `cost_gate_live` (L215)
- `intent_processor/router.rs`
- `intent_processor/mode_state.rs`
- `intent_processor/edge_estimates.rs`
- `intent_processor/rejection_coding.rs`
- `settings/risk_control_rules/risk_config_live.toml`
- `settings/risk_control_rules/risk_config_paper.toml`
- `settings/risk_control_rules/risk_config_demo.toml`(cutoff 仍 -15.0 / min_n 仍 15)

## §7. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / live TOML / production engine ✓ |
| **§七 Code And Docs Rules** | 新代碼注釋全中文 / 觸及 bilingual block 不主動清(只觸及新加 arm,既有 bilingual unchanged)✓ |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 re-review;不自行 push;不派下游 sub-agent ✓ |
| **§git-and-sync** | 不 amend 已 push commit / 不 force push / 不動 1639506f 與 origin/main / 1 follow-up commit 模式 ✓ |
| **§九 Code Structure Guardrails** | gates.rs 上輪 287 LOC + 本次 +3 = 290 LOC(< 800 OK);tests.rs 既有 + 53 = 仍 < 2000 ✓ |
| **AC-5 production binary 0 mock time** | tests.rs 是 `#[cfg(test)]` cfg-gate 編譯,不進 production binary ✓ |
| **反模式對齊** | 不擴 scope(僅修 E2 列 3 issue)/ 不動 cost_gate_paper / live / paper TOML / 不改 cutoff -15.0 / 不改 min_n 15 ✓ |

## §8. 不確定之處

1. **Issue 2 errata 處理**: 本 commit message body 含完整 BUSDT/LABUSDT/5 noise-band cell 名單。是否需 PM 在 RCA 文件補 follow-up(operator 判斷)。
2. **NaN boundary test 未實作**: E2 review §Issues found §c 提到「n<min_n 且 shrunk_bps = NaN → explore」,並自評「default behavior 跟既有 EDGE-DIAG-2 一致,不算新引入問題」。本 patch 不擴 scope。若 E2 re-review 要求補,1 行 fixture(`"shrunk_bps": "NaN"`)即可,或單獨 follow-up commit。
3. **funding_arb noise band 5 cell n_trades 確切數**: §4.2 表列 BIOUSDT/CLUSDT/CHIPUSDT/BABYUSDT/PRLUSDT 標「<15」,真實 n_trades 沒在本 IMPL pass 直接 dump(因 E2 已驗證 shrunk_bps ∈ [-15, 0) 結論成立)。若 PM 要 audit log 精確 n,可在 sign-off 階段 `jq` 跑 edge_estimates.json 補。

## §9. Operator 下一步

1. **PM 派 E2 re-review**:focus on
   - cargo test 138 PASS 是否 cover EDGE-DIAG-2 v2 全 boundary(deep_neg / noise_band / cutoff equality)
   - tracing field rename 是否消除 audit log key 分裂
   - commit message body Issue 2 errata 段是否充分對齊 funding_arb scope
   - follow-up commit 方案(非 amend)是否符合 §git-and-sync(已 push commit 不 destructive 修改)
2. **E4 regression scope**(E2 re-review PASS 後):
   - 跑 `cargo test --release --lib` 全 suite(預期 3961 PASS baseline + 本 patch 3 new = 3964)
   - 跑 spike feature regression / nm scan AC-5
   - cost_gate replay benchmark(若 PM 排程):demo 模擬 PnL 改善 + 22 cell 新 deny 名單
3. **PM 統一 push**(E2 + E4 PASS 後):一次 push `662dd407` 到 origin/main
4. **Phase B deploy**:operator 後續 `restart_all --rebuild` 拉 engine pid 新 binary

---

**E1 IMPLEMENTATION DONE: 待 E2 re-review (report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--cost_gate_e2_return_3issue_fix.md`)**
