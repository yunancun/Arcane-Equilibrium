# E1 Report: WP-02 Donchian Deprecate (Hygiene-Only)

Date: 2026-05-16
Task: P0-V2-NEW-1 Donchian leak-bias remediation — hygiene-only completion
Status: IMPL DONE hygiene, QC verify PASS, audit drift 第 3 次

## 1. Task Summary

12-agent audit Wave 1 中 QC + MIT 提及的 `donchian()` look-ahead bias 議題：原版 `IndicatorEngine::donchian()` window 計算包含 current bar，breach detector 用 `rolling(N).max()` 模式必然 mean-revert（feedback_indicator_lookahead_bias 反模式）。

**關鍵真相**（QC sub-agent 2026-05-16 verify）：

- 真正的 leak fix 早於 **2026-04-25 commit `75741eff`** 已 land，當時新增 `donchian_prior(N)` 函數使用 `shift(1).rolling(N).max()`，並把 `bb_breakout` 5m hard-gate 從 `donchian()` 改為 `donchian_prior()`
- 2026-04-25 起所有產線策略已用 leak-free 版本
- 2026-05-09 `ad14db07` commit 只是補測試 + Rust regression guard，**已是 hygiene-only**
- 但前後共有 **3 次** audit（W-AUDIT-1 / v2 / v3）誤把 `donchian()` 還在當 active leak risk 標出來

Wave 1 round 1 commit `6b8be386` 對 WP-02 的 hygiene 工作：

1. 給 `IndicatorEngine::donchian()` 加 `#[deprecated(since="...", note="leak: includes current bar; use donchian_prior() for entry signals")]` attribute
2. 強化 `tests/indicator_engine_donchian_leak.rs` regression test 覆蓋 prior vs current bar 兩條路徑

## 2. Changes

| File | Line(s) | Change |
|---|---|---|
| `rust/openclaw_engine/src/strategies/indicator_engine.rs` | 412-418 | `donchian()` 加 `#[deprecated]` + 中文注釋說明「entry signal 必用 `donchian_prior()`」 |
| `rust/openclaw_engine/tests/indicator_engine_donchian_leak.rs` | 1-87 | regression test 強化：3 場景（current bar new high / prior bar new high / both equal）驗證 `donchian()` vs `donchian_prior()` 差異 |

## 3. Key Diff

### donchian() deprecate（indicator_engine.rs）

```diff
+    /// Donchian channel envelope（包含 current bar）。
+    /// **leak-prone**：current bar 的 high/low 會出現在計算結果中，
+    /// 直接用於 entry signal 會 look-ahead bias（必然觸發 breach=current is N-bar max → mean-revert）。
+    /// entry signal 必使用 [`donchian_prior`]（shift(1) 後 rolling）。
+    /// 本函式僅保留供 study / backtest replay / mean-reversion exit logic 使用。
+    #[deprecated(
+      since = "2026-04-25",
+      note = "leak: includes current bar; use donchian_prior() for entry signals"
+    )]
     pub fn donchian(&self, period: usize) -> Option<DonchianChannel> {
       // existing implementation unchanged
     }
```

### regression test 強化

```diff
+    #[test]
+    fn donchian_vs_donchian_prior_three_scenarios() {
+        // 場景 1: current bar new high → donchian() shows breach, donchian_prior() doesn't
+        // 場景 2: prior bar new high → both show same breach
+        // 場景 3: both equal → no breach in either
+        // ... 87 lines of empirical comparison ...
+    }
```

## 4. Governance Check

| Rule | Status |
|---|---|
| `#[deprecated]` attribute 正確標 | PASS |
| 廢用 attribute 不破舊呼叫端（保留供 study）| PASS |
| `bb_breakout` 5m hard-gate 已用 `donchian_prior()` since `75741eff` | PASS（QC verify） |
| regression test cover 3 scenarios | PASS |
| Comment language = Chinese | PASS |
| File LOC under 800 warning | PASS（indicator_engine.rs 624 行） |

## 5. QC Verdict — Hygiene-Only PASS

QC sub-agent 2026-05-16 對 `donchian_prior` since `75741eff` 4-28 起 leak-free 做了 empirical verify：

- `git log --all -- "rust/openclaw_engine/src/strategies/indicator_engine.rs"` 看到 `75741eff` 2026-04-25 加入 `donchian_prior()` + 同 commit 改 bb_breakout 用 prior
- 2026-04-28 起 demo runtime 寫的 fills 對應 trade intent 全用 `donchian_prior` 路徑
- W-AUDIT-1 / v2 / v3 報告中提到 `donchian()` leak 已是 **stale finding**，audit drift 第 3 次

**verdict**：Wave 1 round 1 對 WP-02 的工作 100% hygiene，無 runtime behavior change；只補 dev-time guard（`#[deprecated]` warn）+ regression test。

## 6. Audit Drift 教訓 Carry-Over

Audit drift 第 3 次（W-AUDIT-1 / v2 / v3）reproduce 同一 stale finding，反映：

1. audit agent 對「leak-bias」反模式正確 trigger，但 trigger 後沒驗證 git history 確認是否已修
2. PA 收 audit 沒交叉檢查 source verify
3. TW 索引在 W-AUDIT-1 round closure 沒記錄 stale findings 區別

後續預防（W-AUDIT-1 closure 已記入）：每個 audit P0 finding 必先 git log 驗證是否 newly introduced 才接受派工。

## 7. Scope Not Touched

- bb_breakout 5m hard-gate（早於 4-25 改完，無需動）
- bb_reversion exit logic（`donchian()` 在 exit-side OK，因為 mean-revert exit 是 desired behavior）
- 其他 indicator family（RSI / ATR / BB / MACD / Stoch / Volume）leak audit（separate W-AUDIT ticket）
- WP-03 sigma fix（早於 2026-04-25 commit `67a82612` 已 land，audit drift 第 3 次同理）

## 8. Verification

- `cargo build --release -p openclaw_engine` → OK（warn: deprecated `donchian()` 1 處在 self-call，已加 `#[allow(deprecated)]`）
- `cargo test -p openclaw_engine indicator_engine_donchian_leak --release` → 3 PASS
- `cargo test -p openclaw_engine indicator_engine` → 13 PASS
- `grep -rn "fn donchian(" rust/openclaw_engine/src/` → 1 hit（indicator_engine.rs:418）✅
- `grep -rn "\.donchian(" rust/openclaw_engine/src/strategies/` → 0 hit on entry path（5m hard-gate 全用 donchian_prior）✅
