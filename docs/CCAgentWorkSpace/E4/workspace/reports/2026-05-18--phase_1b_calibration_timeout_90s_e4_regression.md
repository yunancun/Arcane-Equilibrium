# E4 Regression Report — Phase 1b Calibration grid timeout_ms 30s → 90s

- **Branch**: `feature/phase-1b-calibration-grid-timeout-90s`
- **HEAD**: `820f0532 feat(phase-1b): grid family close_maker timeout_ms 30s → 90s per calibration sweep`
- **Date**: 2026-05-18 (Mac + Linux trade-core)
- **Scope**: 11-LOC Rust constant change (timeout_ms 30s → 90s) post-calibration evidence; +3 LOC test assertion update; 2 Rust files
- **Upstream chain**: PA calibration cell selection (`2b65d3f1`) → E1 IMPL (`820f0532`) → E2 light review APPROVE-CONDITIONAL → 本 E4
- **Reference**: `phase_1b_calibration_cell_selection_report.md` Top-1 cell G-AB-01-C90 (fill 70.8% / saving +3.37 bps)

---

## §0 Verdict

**REGRESSION-PASS → pass to PM merge**

| 維度 | 結果 |
|---|---|
| Step 1 cargo workspace lib | engine 2992/0/1 · core 446/0/0 · types 35/0/0 ✅ |
| Step 2 maker_price determinism (3 runs) | 15/0/0 × 3 — non-flaky ✅ |
| Step 3 baseline regression | 2992/0/1 = E2 verify = `2026-05-18 phase_1b_runtime_activator` baseline ✅ |
| Step 4 sibling 5 fixture audit | 5/5 hardcoded `30_000.0` = BTCUSDT BBO mock price (USD), 0 timeout coupling ✅ |
| Step 5 tick_pipeline focused | 163/0/1 ignored — 0 regression ✅ |
| Step 5 strategies::common focused | 33/0/0 — 0 regression ✅ |
| Step 5b Linux release (scratch worktree × 2 runs) | 2992/0/1 × 2 (0.64s + 0.64s) — non-flaky, Mac↔Linux 1:1 ✅ |
| Step 6 Python calibration pytest | 63/63 PASS in 0.03s — 0 coupled regression ✅ |
| Step 7 Spec §7.1 compliance | spec line 488-493 列 default 30s / phys_lock 10s 但**未列 hard upper bound**；90s 屬 evidence-driven evolution，不違規但 spec doc 尚未同步（minor doc drift advisory）|
| Race check 5/5 | HEAD ≡ origin / 0 file conflict / 0 destructive op / unique path / 0 sibling source drift ✅ |
| Engine + Python cross-test | 0 import pollution / 0 cross-module side effect ✅ |
| Mock anti-pattern | 0 hit (per regression-testing-protocol §5) ✅ |

**0 BLOCKER · 0 MUST-FIX 新增 · 1 NTH (Phase 1b spec §7.1 doc sync update)**

---

## §1 Step 1 — cargo test --release --workspace --lib

```
$ cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release --workspace --lib
```

| Package | Result |
|---|---|
| `openclaw_core` | **446 passed; 0 failed; 0 ignored** in 0.01s |
| `openclaw_engine` | **2992 passed; 0 failed; 1 ignored** in 0.70s |
| `openclaw_types` | **35 passed; 0 failed; 0 ignored** in 0.00s |

### Baseline 對齊 + delta attribution

| Source | passed | 來源 |
|---|---|---|
| `2026-05-18 phase_1b_calibration_harness` E4 baseline | 2992 | E4 report `2026-05-18--phase_1b_calibration_harness_e4_regression.md` §5 |
| Phase 1b grid timeout 90s (本 PR) | +0 | unit test assertion 修改 (3 LOC), **未新增 test** |
| **Mac release 實測** | **2992** | §1 ✅ |
| **Linux release 實測** (scratch worktree) | **2992** | §5b ✅ |

**0 unexplained delta**. Predicted 2992 = Mac 實測 = Linux 實測 = E2 self-verify 四方 1:1 一致。

> Task brief 寫 "openclaw_core 35/0/0" — **實測 446/0/0**。35 是 `openclaw_types`。E4 以實測為準（per regression-testing-protocol「不信本 skill 內寫死數字」）。

---

## §2 Step 2 — Determinism (maker_price 3-run)

```
$ for i in 1 2 3; do cargo test --release -p openclaw_engine --lib strategies::common::maker_price 2>&1 | tail -2; done
```

| Run | Result |
|---|---|
| Run 1 | `15 passed; 0 failed; 0 ignored; 0 measured` |
| Run 2 | `15 passed; 0 failed; 0 ignored; 0 measured` |
| Run 3 | `15 passed; 0 failed; 0 ignored; 0 measured` |

**3/3 identical** → maker_price module 在新 timeout 90s assertion 下完全 deterministic non-flaky ✅

---

## §3 Step 3 — Test count regression baseline

```
$ cargo test --release -p openclaw_engine --lib -- --list | tail -1
2993 tests, 0 benchmarks
```

= 2992 passed + 1 ignored. **0 test silently disabled**。

### Ignored test pre-existing attestation

```
$ cargo test --release -p openclaw_engine --lib -- --ignored | tail -10
failures:
    tick_pipeline::tests::h0_ctor_default::test_lg1_t3_known_gap_apply_risk_snapshot_does_not_wire_h0_shadow_mode
test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 2992 filtered out
```

唯一 ignored = `test_lg1_t3_known_gap_apply_risk_snapshot_does_not_wire_h0_shadow_mode`，標 `expected (post-fix): apply_risk_snapshot wires runtime.h0_shadow_mode into H0GateConfig.shadow_mode` — pre-existing known H0 gap test，與本 timeout PR 無因果。同 2026-05-18 phase_1b_calibration_harness E4 baseline 1 ignored 同身分 ✅

---

## §4 Step 4 — 5 sibling fixture audit (E2 SHOULD-FIX non-blocking)

E2 inline finding：「5 處 sibling fixture mock 用 hardcoded `30_000` 但屬 simulation input 不從 policy fn，functional correct，post-deploy 一併處理」。E4 逐位置查證：

```
$ grep -nE "30_000|30000" rust/openclaw_engine/src/strategies/common/maker_price.rs rust/openclaw_engine/src/tick_pipeline/tests/dual_rail_dispatch.rs
```

| File:Line | Context | Type | Functional impact |
|---|---|---|---|
| `maker_price.rs:92` | `timeout_ms: 90_000,` (comment refs 30_000) | **policy fn (本 PR 改點)** | N/A — comment audit trail |
| `maker_price.rs:416` | `inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1)` test BBO | **BTCUSDT mock 中位價** `$30,000 USD` | **0** — 不涉 timeout |
| `maker_price.rs:428` | 同上 (sell test) | 同上 | **0** |
| `maker_price.rs:440` | 同上 (buffer_zero test) | 同上 | **0** |
| `maker_price.rs:453` | `inputs_no_bbo(30_000.0, Some(0.1))` test | `last_price` BTCUSDT mock | **0** |
| `maker_price.rs:465` | `last_price: 30_000.0,` (MakerPriceInputs literal) | 同上 | **0** |
| `maker_price.rs:479` | 同上 | 同上 | **0** |
| `maker_price.rs:494` | 同上 | 同上 | **0** |
| `maker_price.rs:501` | `assert!((price - 30_000.9).abs() < 1e-9)` | passive 賣價 (= ask 30_001 - tick 0.1) | **0** — 計算 expected price，非 timeout |
| `maker_price.rs:508` | `inputs_with_bbo(30_000.0, 30_002.0, 30_001.0, 0.1)` crossed-book test | BTCUSDT 中位價 mock | **0** |
| `maker_price.rs:528` | 同 (happy_path_never_crosses_book) | 同上 | **0** |
| `maker_price.rs:610` | `inputs_with_bbo(30_000.0, 29_999.0, 30_001.0, 0.1)` (本 PR 改 612 assertion 用此 fixture) | BTCUSDT mock 中位價 | **0** |
| `maker_price.rs:612` | comment 內 `30_000` (本 PR 改點 audit trail) | comment | N/A |
| `dual_rail_dispatch.rs:476` | comment 內 `30_000` (本 PR 改點 audit trail) | comment | N/A |

### Signature 確認

`fn inputs_with_bbo(last: f64, bid: f64, ask: f64, tick: f64) -> MakerPriceInputs` (maker_price.rs:390)
`fn inputs_no_bbo(last: f64, tick: Option<f64>) -> MakerPriceInputs` (maker_price.rs:401)

**全 13 處 `30_000.0` (含本 PR 改點 audit comment) 0 個是 timeout 數值**。全是：
1. `30_000.0` = $30,000 BTCUSDT mock price (BBO simulation 中位)
2. `30_000.9` = expected passive sell price (calculation result)

E2 SHOULD-FIX **functional non-blocking** 結論成立 ✅。E2 用詞「5 處」實際 grep 顯示 BBO 模擬中位價總共 ~10 處，但全部為 BTCUSDT $30K price-domain 常量，無一個 timeout policy 耦合。不阻 deploy；可後續若有 PR touch sibling test 順手改成 `BTC_PRICE_MOCK` constant 提升可讀性（NTH P2）。

---

## §5 Step 5 — Cross-test sibling regression

### §5a Mac focused module tests

```
$ cargo test --release -p openclaw_engine --lib tick_pipeline::tests
test result: ok. 163 passed; 0 failed; 1 ignored; 0 measured; 2829 filtered out; finished in 0.05s

$ cargo test --release -p openclaw_engine --lib strategies::common
test result: ok. 33 passed; 0 failed; 0 ignored; 0 measured; 2960 filtered out; finished in 0.00s
```

✅ 兩 module（含本 PR 修改 maker_price + dual_rail_dispatch）full PASS。

### §5b Linux trade-core scratch worktree release lib (× 2 runs)

```
$ ssh trade-core "..."
W=/tmp/e4-p1b-90s-1779110434 (scratch isolated from runtime)
HEAD = 820f0532 (== Mac == origin/feature/phase-1b-calibration-grid-timeout-90s)

Run 1: test result: ok. 2992 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.64s
Run 2: test result: ok. 2992 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.64s
```

**Mac 2992/0/1 (0.68s/0.70s) ≡ Linux 2992/0/1 (0.64s/0.64s)** — 跨平台完全 1:1 + 雙跑非 flaky 雙重確認 ✅

Linux scratch worktree cleanup 完成。runtime engine 完全未觸動（cargo test 跑在 `/tmp/` scratch 不影響 `/home/ncyu/BybitOpenClaw/srv/` 主 repo）。

---

## §6 Step 6 — Python calibration pytest

```
$ python3 -m pytest helper_scripts/calibration/tests/ -q
63 passed in 0.03s
```

= Wave 1 baseline 63/63（per `2026-05-18 phase_1b_calibration_harness` E4 report §1）。**0 coupled regression** ✅

Python calibration harness 0 Rust touch / 0 timeout dependency → unchanged by design。

---

## §7 Step 7 — Spec §7.1 compliance (Phase 1b spec v1.3)

讀 `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` §7.1 (line 484-493):

```markdown
### 7.1 Timeout 設計

| 策略 / reason | timeout_ms | 理由 |
|---|---|---|
| 大部分策略級 | 30000 (30s) | entry maker avg 5-14s, max 50s；30s 涵蓋 p90 fill window |
| `phys_lock_gate4_stale_roc_neg` | 10000 (10s) | ROC<0 + stale 已偏弱，倉位 expose 久不利 |

**未來考量（Phase 1b+）**：ATR-aware timeout（vol 高短 timeout / vol 低長 timeout）— 不在 Phase 1b scope。
```

### 結論

- Spec **列 default 30s / phys_lock 10s 為當前實裝值，但未明定 hard upper bound** (≤120s)
- Task brief 寫「E2 verified ≤120s allowed range」— spec doc 本身沒寫此上限。可能是 E2 從 entry maker max 50s 推算的合理上限（90s < 120s 為 safety margin），或從另一個未列入 spec 的 source verified
- 90s 屬 **post-spec evidence-driven evolution**（calibration sweep G-AB-01-C90 fill 70.8% vs 30s 58.3% 12.5 ppt 改善），不違反 spec 任何明示約束
- **NTH advisory**: spec §7.1 應在後續 PR 同步加 row「grid family (post-calibration 2026-05-18) | 90000 (90s) | sweep G-AB-01-C90 evidence」or 補 "future considerations" note。不阻本 PR deploy

### Compliance verdict
✅ **不違反 spec §7.1 明示約束**。
⚠️ Spec doc 同步建議：合適時機（如 Phase 2a 24h 觀察後決定保留 90s 或調整）一併更新 spec §7.1 表格。

---

## §8 Multi-session race check 5/5

| Check | Command | Result | 評估 |
|---|---|---|---|
| 5a Fetch + 比對 branch HEAD | `git fetch origin && git log -1 origin/feature/phase-1b-calibration-grid-timeout-90s` | `820f0532` ≡ local HEAD ✓ | PASS |
| 5b Worktree clean (PR scope) | `git status` 4 modified `docs/CCAgentWorkSpace/{E2,MIT,PA,QA}/memory.md` + 12 untracked reports — **0 命中 `rust/` 或 `helper_scripts/calibration/`** | 0 source conflict ✓ | PASS |
| 5c 不識別 WIP 禁 revert | 0 操作 — sibling worktree dirty file 全部尊重 | N/A ✓ | PASS |
| 5d Report path unique | `2026-05-18--phase_1b_calibration_timeout_90s_e4_regression.md` 與 sibling E4 reports (`phase_1b_runtime_activator_full_regression` / `phase_1b_calibration_harness_e4_regression`) 不同檔名 | path unique ✓ | PASS |
| 5e Sibling push during review | `git log --since="30m ago" origin/main` 0 條 (stable) | 0 source drift ✓ | PASS |

**Race check 5/5 PASS** — 可安全交還 PM merge。

---

## §9 Mock / Anti-pattern audit

| Check | 結果 |
|---|---|
| 本 PR 0 新 test | 0 new test added (3 LOC 是修改既有 assertion，非新增 test) — 但 unit test 既有 15 個 maker_price test cover `timeout_ms` getter (`policy.timeout_ms == 90_000`) + dispatch test cover `req.maker_timeout_ms == Some(90_000)` |
| mockall 使用 | 0 (本 PR 純常量改 + assertion 更新) |
| 業務邏輯 100% 真跑 | ✅ `close_maker_price_policy("grid_close_long")` 真實調用 + assertion 對齊 |
| Deleted tests | 0（**沒刪測試使測試通過**） |
| Assertion value tampering | 0（assertion 從 30_000 → 90_000 同步 source change，per E2 self-verify + 本 E4 §1/§3 double-check）|
| Anti-pattern hit | **0** |

**Mock 審查 PASS**，per regression-testing-protocol §5 OK pattern。

---

## §10 Cross-language consistency / SLA

| 項 | 結果 |
|---|---|
| Cross-language Python↔Rust 一致性 | **N/A — Python `phase_1b_maker_price.py` 是 calibration replay port，使用 `CloseMakerPricePolicy(buffer_ticks=, offset_bps=, timeout_ms=)` 作為 input 參數而非 derive，不從 Rust `close_maker_price_policy()` 同步**。timeout 30s vs 90s 不會在 Python harness 觸發 cross-lang drift（calibration 是 explicit policy injection）|
| SLA hot path | **N/A** — 本 PR 0 hot path touch；`close_maker_price_policy()` 是 dispatch 階段 lookup（pending sweep 用 `maker_timeout_ms` field 做 time-based fallback gate），改 timeout 值不影響 H0 Gate / tick path / IPC latency |
| H0 Gate < 1ms / Tick path < 0.3ms / IPC < 5ms | 不適用本 PR scope |

---

## §11 PR scope verification

```
$ git diff 820f0532~..820f0532 --stat
 rust/openclaw_engine/src/strategies/common/maker_price.rs     | 11 +++++++++--
 rust/openclaw_engine/src/tick_pipeline/tests/dual_rail_dispatch.rs |  3 ++-
 2 files changed, 11 insertions(+), 3 deletions(-)
```

**Total: 2 Rust files / 14 LOC changes (11 insertions + 3 insertions = 14, not 11 per task brief)**。Task brief 算 11 net 估算可能漏看 dual_rail_dispatch 3 行；E4 以 `git diff --stat` 實測為準。

```
$ git diff --name-only origin/main..HEAD
rust/openclaw_engine/src/strategies/common/maker_price.rs
rust/openclaw_engine/src/tick_pipeline/tests/dual_rail_dispatch.rs
```

**0 over-touch**，與 task brief 列 file scope 完全一致 ✅。phys_lock family timeout 不變（spec §7.1 列 10s/15s）— 已在 commit message 明標 audit trail。

---

## §12 Verdict

### **REGRESSION-PASS → PM merge READY**

| 維度 | 結果 |
|---|---|
| Rust workspace lib (Mac release) | 2992 + 446 + 35 = 3473 全 PASS / 0 failed / 1 ignored ✅ |
| openclaw_engine 雙跑 Mac | 2992/0/1 × 2 (0.68s + 0.70s) non-flaky ✅ |
| maker_price 3-跑 determinism | 15/0/0 × 3 identical ✅ |
| tick_pipeline focused | 163/0/1 (1 pre-existing ignored) ✅ |
| strategies::common focused | 33/0/0 ✅ |
| Linux trade-core scratch worktree × 2 | 2992/0/1 × 2 (0.64s + 0.64s) = Mac 1:1 non-flaky ✅ |
| Python calibration pytest | 63/63 in 0.03s — 0 coupling ✅ |
| Baseline delta attribution | 2992 = E2 self-verify = phase_1b_calibration_harness baseline ✅ |
| 5 sibling fixture audit | 0 timeout coupling — 全 BTCUSDT BBO mock price ✅ |
| Spec §7.1 compliance | 不違規（spec 未明定 upper bound）；NTH doc sync ⚠️ |
| Mock / anti-pattern | 0 hit ✅ |
| Race check 5/5 | 全 PASS ✅ |
| Engine runtime untouched | scratch worktree isolated ✅ |

### Recommendation to PM

1. **PM merge to main**: READY — `820f0532` 可直接 merge / cherry-pick / fast-forward
2. **Deploy**: PM 派 operator 在 Linux trade-core 跑 `bash helper_scripts/restart_all.sh --rebuild` 啟 90s timeout（Demo Phase 2a runtime 已具備 `use_maker_close=true` per `2026-05-18 phase_1b_runtime_activator` deploy chain）
3. **24h watch**: 部署後 24h 驗 close_maker fill rate 是否從 baseline ~58% → ~70% (per spec §8.1 healthcheck v1.1 Wilson CI lower ≥ 60% gate)
   - 注意 E2 caveat: simulation BBO-cross-proxy systematically optimistic，real fill rate 可能低於 70.8% sweep 預測
4. **不開新 P0/P1 ticket**：本 PR 純常量微調 / 0 schema / 0 migration / 0 secret / 0 runtime mutation logic change
5. **Spec doc sync NTH** (P2, 不阻本 deploy):
   - 在 Phase 2a 24h 觀察後決定保留 90s 或調整時，順手更新 `2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` §7.1 表格加 row 反映 calibration evidence-driven post-deploy 值
6. **E2 SHOULD-FIX (5 sibling fixture)**: 0 functional impact verified，可後續若 PR touch sibling test 順手把 `30_000.0` 提取為 `const BTC_BBO_MOCK_MID: f64 = 30_000.0;` 提升可讀性，但純風格非 blocker

### Lessons learned

- **11 LOC constant-change regression 模板**: 純常量 PR 不需 cross-language consistency 驗（無 Python dual），不需 SLA 壓測（無 hot path），不需 new test mock audit（無新 test），E4 重點 = (1) baseline 0 regression (2) assertion 對齊 source change (3) determinism 雙跑 (4) cross-platform Mac↔Linux 1:1 (5) sibling fixture audit verify E2 finding scope。約 20 min wall time，比 full Rust + Python E4 矩陣省 70%
- **Hardcoded `30_000` audit lesson**: 同數字在不同 domain (timeout_ms vs USD price) 是常見 simulation 陷阱。E4 必跑 signature lookup 確認 first-arg type (`fn inputs_with_bbo(last: f64, ...)` → BBO mock 非 timeout) 再判斷 functional coupling。否則容易誤把 BTCUSDT $30K price mock 報為 timeout drift
- **Task brief 數字以實測為準**：task brief 寫「11 LOC」實際 `git diff --stat` = 14 LOC（11+3）；寫「openclaw_core 35/0/0」實際 446/0/0（35 是 `openclaw_types`）。E4 必跑命令拿 baseline，不信 brief 內寫死數字（per regression-testing-protocol「不信本 skill 內寫死數字」廣義適用 task brief）
- **Spec doc 與 calibration evidence-driven evolution 時序**：calibration sweep 通常後於 spec 主文撰寫，spec §7.1 列當時設計值；evidence-driven 微調可能在 spec 沒明確列入 hard upper bound 的情況下落地。E4 compliance check = 「不違反 spec 明示約束」非「spec 必列此具體值」；後續 spec doc sync 是 NTH 而非 blocker
- **Linux scratch worktree isolation 不影響 runtime**: cargo test on `/tmp/e4-*` 完全與 `/home/ncyu/BybitOpenClaw/srv/` 主 repo + engine runtime 隔離。但需 cleanup（防 `/tmp/` 累積）。本次 cleanup 後 0 殘留 scratch

---

E4 REGRESSION DONE: PASS · report path: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-18--phase_1b_calibration_timeout_90s_e4_regression.md`
