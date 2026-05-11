# E4 Regression — P1 V083 ipc_close entry_context_id Fix + P2 demo TOML

**Date**: 2026-05-11 04:10 CEST
**Reviewer**: E4
**Trigger**: PM 任務 — V083 fix (commit `d4867676`) + P2 TOML (commit `27e86f89`) 回歸
**HEAD**: `27e86f89` (P2 TOML committed last; V083 fix in `d4867676` parent)
**Scope**: Rust producer-side fix (`commands.rs` +9 LOC + 4 unit test +86 LOC) + demo-only 2 TOML key tweak

---

## 0. Verdict

**E4 PASS · Deploy READY**

| 維度 | 結論 |
|---|---|
| Cargo lib regression (release) | ✅ 2789/0/0 跑兩遍 non-flaky；E1 自報 +4 test 覆寫 baseline 2785→2789 |
| 5 close path call site 真改 | ✅ 513/744/938/1121/1194 全 grep 確認替換為 helper 呼叫，0 hit `unwrap_or("")` 殘留 |
| Helper 隔離 (orphan_recovery_ctx string only in commands.rs + test file) | ✅ grep `-rn 'orphan_recovery_ctx' rust/openclaw_engine/src/` 0 跨檔擴散 |
| Linux PG dry-run V083 行為 | ✅ NULL→REJECT / synthetic→ACCEPT / 空字串→ACCEPT / entry-NULL→ACCEPT 4/4 預期 |
| trading_writer / batch_insert / emit_close_fill subset | ✅ 10/10/10/13 全 PASS,含 writer-side empty-entry-ctx fail-soft 不變式 |
| P2 TOML parseable + 真實 wire | ✅ tomllib parse OK + Rust ma_crossover/helpers.rs:256 + bb_reversion/mod.rs:586 真用 |
| SLA 影響 (helper in close path) | ✅ 定性 negligible (~50ns format! fallback；non-tick frequency) |
| Mock 安全 | ✅ E1 unit test 0 業務邏輯 mock (純 paper_state set/apply_fill + helper 真呼叫) |
| 跨語言一致性 | ⏸ N/A (本 fix 純字串解析,無浮點計算) |

---

## A. Cargo regression

### A.1 全 lib release run × 2

```
cargo test --release -p openclaw_engine --lib --manifest-path rust/Cargo.toml
```

**Run 1**:
```
test result: ok. 2789 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

**Run 2** (non-flaky):
```
test result: ok. 2789 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

**Baseline 對比**:

| Phase | passed | failed | ignored | source |
|---|---|---|---|---|
| W-C closure baseline (E4 2026-05-11 01:50) | 2776 | 0 | 0 | `2026-05-11--w_c_fix_e4_regression.md` |
| Sibling N+1 D+0 land (P2 stable_id helper / 其他 wave) | +9 | 0 | 0 | E1 IMPL DONE 報告 §5.2 baseline drift 說明 |
| V083 fix +4 unit test | +4 | 0 | 0 | resolve_close_entry_context_id.rs |
| **本次實測** | **2789** | **0** | **0** | E4 跑兩遍同綠 |
| Delta (vs E1 自報 2789) | 0 | 0 | 0 | ✅ E1 數字真實 |

### A.2 V083 fix 4 個新 unit test

```
test tick_pipeline::tests::resolve_close_entry_context_id::test_resolve_real_id_when_present ... ok
test tick_pipeline::tests::resolve_close_entry_context_id::test_resolve_synthetic_when_missing ... ok
test tick_pipeline::tests::resolve_close_entry_context_id::test_resolve_synthetic_when_empty_string ... ok
test tick_pipeline::tests::resolve_close_entry_context_id::test_synthetic_pattern_well_formed ... ok
```

| Test | Invariant | E4 認可 |
|---|---|---|
| test_resolve_real_id_when_present | paper_state 有真 id → 回真 id (happy path) | ✅ 邊界 + 正常 |
| test_resolve_synthetic_when_missing | paper_state 缺位 → 回 synthetic (engine restart 場景) | ✅ orphan recovery |
| test_resolve_synthetic_when_empty_string | paper_state 有倉但 entry_ctx 空 → 回 synthetic (orphan-adopted) | ✅ 邊界 |
| test_synthetic_pattern_well_formed | Prefix 嚴格 + 3-part split + ts_ms parseable u64 | ✅ cron-backfill 識別點不變式 lock |

**Test design 評論**：
- 4 test cover helper 邏輯 + cron backfill 整合契約 — **覆蓋良好**
- Mock 0 (純 paper_state apply_fill + set_entry_context_id 真實呼叫) — 不掩蓋業務邏輯
- **缺口（accept,不 BLOCKER）**：5 close path 各自 ts_ms 來源（513=parameter / 744=event.ts_ms / 938=line 911 ts_ms / 1121=line 1041 ts_ms / 1194=line 1041 ts_ms）沒有 integration test 直接驗證；但 E1 報告 §3.2 已 documented 對應 line 號，且 emit_close_fill 13 test 透過完整 pipeline 間接覆蓋（含 `test_emit_close_fill_threads_entry_context_id` / `test_emit_close_fill_accepts_empty_entry_context_id`）。

### A.3 跨檔案隔離驗證

```bash
grep -rn 'orphan_recovery_ctx' /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/
```

| File | 出現次數 | 用途 |
|---|---|---|
| `tick_pipeline/commands.rs` | 6 (5 注釋 + 1 format!) | helper + call site 注釋 + format string 本體 |
| `tick_pipeline/tests/resolve_close_entry_context_id.rs` | 5 (assertion 字面 + 注釋) | unit test 預期值 |

**0 跨檔擴散**。Helper 是 `pub(super)`（緊範圍 visibility，sibling tests/ 模組可訪問，crate 外不暴露）。✅ 隔離乾淨。

### A.4 5 個 close path call site 真實替換

```bash
grep -nE 'resolve_close_entry_context_id\(' rust/openclaw_engine/src/tick_pipeline/commands.rs
```

```
513:        let existing_entry_ctx = self.resolve_close_entry_context_id(symbol, ts_ms);
744:            let entry_ctx = self.resolve_close_entry_context_id(symbol, event.ts_ms);
938:                    let entry_ctx = self.resolve_close_entry_context_id(&symbol, ts_ms);
1040:    pub(super) fn resolve_close_entry_context_id(&self, symbol: &str, ts_ms: u64) -> String {
1121:                let entry_ctx = self.resolve_close_entry_context_id(symbol, ts_ms);
1194:            let entry_ctx = self.resolve_close_entry_context_id(symbol, ts_ms);
```

5 close path call site (513/744/938/1121/1194) + 1 helper definition (1040) = **與 PA spec / E1 報告完全對齊**。

`get_entry_context_id` 殘留檢查：
```bash
grep -nE 'get_entry_context_id\(.*\)' commands.rs
167:            .get_entry_context_id(symbol)        # ← submit_external_order, push back
1041:        match self.paper_state.get_entry_context_id(symbol) {  # ← helper internal
```

**line 167 push back 確認**：E1 報告 §6.1 已標 — `submit_external_order` 同 pattern latent bug，user prompt 表未列。E4 無權擴大 scope（E4 限制不修代碼），同意 E1 push back PA/PM 後續決定。**不阻 V083 fix deploy**（不在本次 fix 範圍）。

### A.5 相關 subset 測試 (writer / batch_insert / emit_close_fill)

```
trading_writer:        10/0  全 PASS · 含 test_entry_fill_empty_entry_ctx_not_violation
batch_insert:          10/0  全 PASS
emit_close_fill:       13/0  全 PASS · 含 test_emit_close_fill_threads_entry_context_id +
                                         test_emit_close_fill_accepts_empty_entry_context_id
tick_pipeline (full):  170/0  全 PASS (per E1 自報；本次未獨立重跑,已含於 2789)
```

**writer-side 不變式核驗**：`test_emit_close_fill_accepts_empty_entry_context_id` 仍 PASS = writer-side 仍允許 empty entry_ctx 進入 batch（fail-soft by-design）。V083 producer fix 是「不送空字串給 writer」，writer 容忍性是兩條獨立防線；fix 後兩條防線並存,**沒互相破壞**。

---

## B. Linux PG dry-run (V083 行為驗證)

### B.1 4 條 dry-run 結果

執行：`ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -v ON_ERROR_STOP=0"` + 4 BEGIN/ROLLBACK pairs

| Test | INSERT 內容 | 預期 | 實際 | 結論 |
|---|---|---|---|---|
| (a) | close fill (`exit_reason='e4_dry_run_null'`) + `entry_context_id=NULL` | REJECT | `ERROR: new row for relation "_hyper_35_422_chunk" violates check constraint "chk_fills_close_has_entry_context_id_v083"` | ✅ V083 對 NULL fail-closed,fix 前 producer→writer NULL-coerce→撞此 |
| (b) | close fill + `entry_context_id='orphan_recovery_ctx:BTCUSDT:1700000000000'` | ACCEPT | `INSERT 0 1` | ✅ Fix 後 producer-side 通過 V083 |
| (c) | close fill + `entry_context_id=''` (空字串,跳過 writer NULL-coerce) | ACCEPT | `INSERT 0 1` | ✅ V083 不對空字串 reject — 證實「真兇是 writer NULL-coerce」 |
| (d) | entry fill (`exit_reason=NULL`) + `entry_context_id=NULL` | ACCEPT | `INSERT 0 1` | ✅ V083 對 entry path no-op (by-design,V083 SQL line 50-52) |

### B.2 V083 constraint 真實 schema

```
"chk_fills_close_has_entry_context_id_v083" CHECK (exit_reason IS NULL OR entry_context_id IS NOT NULL) NOT VALID
```

驗證點：
- `exit_reason IS NULL` → entry path 跳過 → entry NULL OK ✅ (Test d)
- `entry_context_id IS NOT NULL` → close path 必須有非 NULL entry_context_id ✅ (Test a/b)
- 空字串 `''` !== NULL,V083 不 reject 空字串 ✅ (Test c)
- `NOT VALID` → 不掃 historical row,只對新 INSERT 生效（不破歷史 38% 資料）

### B.3 Producer fix 完整邏輯閉環

```
[Before fix]
  producer commands.rs:1108 unwrap_or("")
    ↓ 寫空字串 entry_context_id
  writer trading_writer.rs:486-489 if entry_context_id.is_empty() { push_bind(None) }
    ↓ writer 把空字串 coerce 成 NULL
  PG INSERT (NULL,...) → V083 chk_..._v083 REJECT  ← bug

[After fix]
  producer commands.rs:1121 resolve_close_entry_context_id(symbol, ts_ms)
    ↓ paper_state 缺則回 well-formed "orphan_recovery_ctx:BTCUSDT:1700000000000"
  writer trading_writer.rs:486-489 push_bind(Some(...))
    ↓ writer 看到非空 → push Some
  PG INSERT (Some('orphan_recovery_ctx:...'),...) → V083 PASS  ← 修復
```

**Dry-run 確認**：fix 後 producer 送的 synthetic id 真實能透過 V083 check（Test b INSERT 0 1）。同時 P2 cron backfill 識別 prefix `orphan_recovery_ctx:%` 後可 UPDATE 為真 entry's context_id（cron 改造留 P2 follow-up）。

---

## C. P2 TOML config 驗證

### C.1 TOML syntax + key existence

```
$ /opt/homebrew/bin/python3.12 -c "import tomllib; d=tomllib.load(open('strategy_params_demo.toml','rb')); ..."

ma_crossover.min_trend_snr = 0.6
bb_reversion.min_persistence_ms = 120000

TOML parse: OK
top-level keys: ['bb_breakout', 'bb_reversion', 'funding_arb', 'grid_trading', 'ma_crossover']
ma_crossover keys: 12 (含 min_trend_snr)
bb_reversion keys: 6 (含 min_persistence_ms)
```

✅ 兩個改動目標 key 真實存在 + 整 TOML parseable + 5 strategy table 結構完整 (bb_breakout / bb_reversion / funding_arb / grid_trading / ma_crossover)。

### C.2 真實 wired 確認 (非 dead config)

**ma_crossover.min_trend_snr**:
```
strategies/strategy_params.rs:80    pub min_trend_snr: f64,                 (TOML loader struct)
strategies/ma_crossover/config.rs:55     self.min_trend_snr = params.min_trend_snr;  (TOML→Strategy)
strategies/ma_crossover/helpers.rs:256   snr >= self.min_trend_snr           (策略邏輯真用 — entry SNR gate)
```

**bb_reversion.min_persistence_ms**:
```
strategies/strategy_params.rs:225-226  pub min_persistence_ms: u64,           (TOML loader struct)
strategies/bb_reversion/mod.rs:213     self.min_persistence_ms = params.min_persistence_ms;  (TOML→Strategy)
strategies/bb_reversion/mod.rs:586     ... self.min_persistence_ms ...        (策略邏輯真用 — confluence persistence gate)
```

✅ 兩個 P2 參數**真實 wired**,從 TOML 通過 serde + Strategy::set_params 抵達策略 hot path。**非 dead config**（[no-dead-params](feedback_no_dead_params.md) 規則 PASS）。

### C.3 三環境隔離 (CLAUDE.md feedback_env_config_independence.md)

QC 修改範圍：demo TOML only。
- live + paper TOML 仍維持 Rust 默認 (ma_crossover 0.75 / bb_reversion 180_000ms)
- demo override 走 `min_trend_snr = 0.60` + `min_persistence_ms = 120000` 兩條獨立 TOML key
- 三環境風控/策略 config 故意分開,與 [feedback_env_config_independence.md] 對齊 ✅

---

## D. SLA 影響評估

### D.1 Helper 函數體分析

```rust
#[inline]
pub(super) fn resolve_close_entry_context_id(&self, symbol: &str, ts_ms: u64) -> String {
    match self.paper_state.get_entry_context_id(symbol) {
        Some(id) if !id.is_empty() => id.to_string(),
        _ => format!("orphan_recovery_ctx:{}:{}", symbol, ts_ms),
    }
}
```

**Cost 拆解**:

| 操作 | Cost (Mac M-series ballpark) | 路徑頻率 |
|---|---|---|
| `paper_state.get_entry_context_id()` HashMap lookup | ~10-30ns O(1) | 每次 close call |
| `.filter(\|p\| !p.entry_context_id.is_empty())` | ~1ns (1 bool check) | 每次 close call |
| `id.to_string()` (happy path) | ~30-50ns (alloc + memcpy ~20-byte) | 主流 (paper_state 有真 id) |
| `format!("orphan_recovery_ctx:{}:{}",...)` (fallback) | ~50-100ns (alloc + 2 format! arg push) | 邊界 (engine restart 後 / orphan-adopted) |

**單次呼叫總 cost**: happy path ~40-80ns / fallback path ~60-130ns

### D.2 Hot path 影響

5 close path call site **皆非 per-tick fan-out 主迴圈**：
- 513 (apply_confirmed_fill): 觸發於 fill confirmation event (~86 fill/24h baseline per memory)
- 744 (execute_position_close): 觸發於 position close 條件 (per fill / risk close)
- 938 (ipc_close_all): 觸發於 IPC `/close_all` event (operator / agent 命令)
- 1121 (ipc_close_symbol exchange): 觸發於 IPC `/close_symbol` event
- 1194 (ipc_close_symbol paper): 同上 (paper 分支)

**頻率上限估計**: ~100-200 calls/24h (含 strategy 自動 close + IPC 手動 close + risk close burst)

**SLA 預算**:
- H0 Gate < 1ms = 1,000,000ns
- Tick path < 0.3ms = 300,000ns
- IPC < 5ms = 5,000,000ns

**Helper 占比**: 130ns / 300,000ns = **0.043% Tick SLA** (per call,但實際不在 tick path)
**24h cumulative**: 130ns × 200 = 26,000ns = 0.026ms / 24h (totally negligible)

### D.3 結論 (定性)

**Helper 對 H0/Tick/IPC SLA 影響為 zero (negligible)**。理由：
1. Helper 在 close path （條件觸發） 不在 per-tick fan-out 主迴圈
2. 單次呼叫 cost ~50-100ns ,不到 SLA 預算 0.05%
3. format! 只在 fallback path 觸發 (orphan / restart 邊界,非常態)
4. happy path (paper_state 有真 id) 相對 fix 前 `unwrap_or("").to_string()` 的 cost delta 接近 0 (兩者皆 1 alloc)

**無需 micro-bench 證實**：cost 量級遠小於 measurement noise (typical bench p99 ~µs scale)。

---

## E. Mock 安全 + 跨語言一致性

### E.1 Mock 審查 (4 個 V083 unit test)

| Test | Mock | 業務邏輯 | 結論 |
|---|---|---|---|
| test_resolve_real_id_when_present | 0 mock | 真實 paper_state.apply_fill + set_entry_context_id + helper 真呼叫 | ✅ |
| test_resolve_synthetic_when_missing | 0 mock | 真實 paper_state (空狀態) + helper 真呼叫 | ✅ |
| test_resolve_synthetic_when_empty_string | 0 mock | 真實 paper_state.apply_fill + set_entry_context_id("") + helper 真呼叫 | ✅ |
| test_synthetic_pattern_well_formed | 0 mock | 真實 helper 真呼叫 + split + parse u64 | ✅ |

**0 業務邏輯 mock**。符合 mock 安全規則。

### E.2 跨語言一致性

**N/A**。本 fix 純字串解析（HashMap lookup + format!）,無浮點計算。1e-4 容差規則不適用。

---

## F. 跑兩遍 (non-flaky)

```
Run 1 (release):  2789 passed; 0 failed; 0 ignored; 0.56s
Run 2 (release):  2789 passed; 0 failed; 0 ignored; 0.56s
```

**完全一致** — 0 flaky。

---

## G. Unexpected / 待跟蹤

### G.1 line 167 submit_external_order latent bug (E1 push back 接受)

**Status**: E1 報告 §6.1 已標,user prompt 嚴格只列 5 close path,未動 line 167。
**E4 立場**: E4 限制不修代碼,接受 E1 push back。**不阻 V083 fix deploy**（不在本次範圍）。
**建議**: PA / PM 後續決定是否同 helper 化 line 167 (LOC ~5,理論上零風險,entry case 仍走 String::new() 分流)。

### G.2 PA spec 細節 disambiguation

**Status**: PA spec 第 26 行說「`unwrap_or("")` → 寫入空字串」,實際 V083 reject 是 NULL（writer-side line 486-489 把空字串 coerce 成 NULL）。
**E4 觀察**: PA spec 省略中間 writer NULL-coerce,但結論（producer 不送 well-formed id → V083 reject）正確。Dry-run §B.3 已給完整邏輯閉環。
**結論**: 不影響 fix 正確性。PA spec 細節可在後續更新時補完。

### G.3 P2 cron backfill 改造未隨此 fix 落地

**Status**: PA spec §6.2 / E1 報告 §7.4 標為 P2 follow-up — `edge_label_backfill.py` 加識別 `orphan_recovery_ctx:%` prefix → UPDATE 真 entry's context_id。
**E4 立場**: 不阻第一波止血。Synthetic id 已可被識別（test_synthetic_pattern_well_formed lock 不變式),P2 cron 後續實作可獨立進行。

### G.4 Sibling N+1 D+0 wave +9 test 已含於 2789

**Status**: E1 IMPL DONE 報告 §5.2 baseline drift 說明 — 2776 → 2789 = +4 mine + +9 sibling N+1 D+0 land。
**E4 認可**: 同次 cargo test 含全部 land code,2789 是當前 truthy baseline。

---

## H. 結論

### H.1 Test 表

| 引擎 | passed | failed | ignored | baseline | delta | non-flaky |
|---|---|---|---|---|---|---|
| Rust lib (release) | **2789** | **0** | **0** | 2776 (W-C closure 2026-05-11 01:50) | +13 (+4 V083 +9 sibling) | ✅ 跑兩遍同綠 |
| trading_writer subset | **10** | **0** | **0** | n/a | n/a | ✅ |
| batch_insert subset | **10** | **0** | **0** | n/a | n/a | ✅ |
| emit_close_fill subset | **13** | **0** | **0** | n/a | n/a | ✅ |
| Python pytest (本範圍 N/A) | n/a | n/a | n/a | 2555 | n/a | ⏸ 不適用 (純 Rust + TOML 改動) |

### H.2 新增測試 (V083 fix scope)

| File | New tests | Scope |
|---|---|---|
| `rust/openclaw_engine/src/tick_pipeline/tests/resolve_close_entry_context_id.rs` | +4 | 真 id / 缺位 synthetic / 空字串 synthetic / pattern well-formed (cron-backfill 識別點 invariant) |

### H.3 Linux PG dry-run

✅ 4/4 預期：
- (a) close+NULL → REJECT (V083 真有效)
- (b) close+synthetic → ACCEPT (fix 後 producer 通過)
- (c) close+空字串 → ACCEPT (writer NULL-coerce 是真兇)
- (d) entry+NULL → ACCEPT (entry path 不受影響)

### H.4 P2 TOML

✅ Parseable + 兩個 key 真實存在 + Rust strategy 邏輯真用 (helpers.rs:256 + bb_reversion/mod.rs:586) + 三環境隔離維持 (live/paper 用默認)

### H.5 SLA

✅ Helper cost ~50-100ns / call,~26ns × 200 calls/24h cumulative,**zero impact** H0 < 1ms / Tick < 0.3ms / IPC < 5ms。Close path 非 per-tick fan-out。

### H.6 Mock 安全

✅ 4 V083 unit test 0 業務邏輯 mock,純真實 paper_state + helper 真呼叫。

### H.7 退回 E1 修復清單

**無 BLOCKER**。Push back PA/PM:
- line 167 latent bug (E1 已標,不阻本 fix)
- P2 cron backfill 改造 (P2 follow-up,獨立 ticket)

派 PM commit 已完成（`d4867676` + `27e86f89` 已 land main）+ deploy。

---

**E4 REGRESSION DONE: PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--p1_v083_p2_freq_e4_regression.md`**
