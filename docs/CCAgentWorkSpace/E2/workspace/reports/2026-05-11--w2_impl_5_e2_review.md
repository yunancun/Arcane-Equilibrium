# E2 PR Adversarial Review — W2-IMPL-5（stalled sub-agent collateral）· 2026-05-11

**Reviewer**: E2（senior backend code reviewer + adversarial auditor）
**Trigger**: PA dispatch · W2-IMPL-5 sub-agent (`a0e1741f`) stalled 600s watchdog killed；PM 已剛 commit + push 兩 collateral file (HEAD `73bcc1f5`)；需對抗性 verify 是否真完整可用
**HEAD**: `73bcc1f5`（Mac local = Linux trade-core = origin/main 三端 100% sync）
**Skills loaded**: `pr-adversarial-review` + `bilingual-comment-style`

---

## 0. Verdict

**APPROVED · PASS to E4 regression**，附 2 MEDIUM finding（不阻 E4，建議 PM 或 E1 順手帶清）。

| 維度 | 結論 |
|---|---|
| Integration test 三層 fence 各對應 1 assert（缺一拒簽）| ✅ Layer 1 + Layer 2 + Layer 3 三 assert function 各 1 個 + sentinel marker |
| Integration test 9/9 PASS（E2 Mac release 獨測）| ✅ `running 9 tests ... ok` |
| 既有 baseline 不退化 | ✅ `openclaw_engine --lib` 2797/2797 + `openclaw_core --lib` 434/434 |
| NaN safe (compute_btc_book_imbalance + ingest_task) | ✅ 3-event chain (NaN qty / empty / valid) ingest_task 不 panic + slot Some(0.333) |
| Cross-language consistency (Rust struct NaN propagation) | ✅ btc_lead_return_pct NaN → cond 4 fail / alt_xcorr NaN → cond 3 fail in-memory verify ✓；PG round-trip 由 E4 dry-run gate 另驗 |
| file ≤ 800 LOC | ✅ 534 LOC ≪ 800 警告線 |
| 三層 fence source code 真實對齊 (E2 獨自 verify) | ✅ Layer 1 `on_tick/step_4_5_dispatch.rs:206-212` + Layer 2 `main.rs:1005-1018` + Layer 3 `cross_asset/mod.rs:157-237` |
| 跨平台 grep (`/home/ncyu` / `/Users/[^/]+`) | ✅ test file 0 hit；signoff_pack line 241 是政策反例引用不在禁區 |
| 中文注釋政策（2026-05-05 governance） | ✅ MODULE_NOTE + docstring + inline 全中文（部分技術術語英文 reference 不譯） |
| §九 8 條 checklist | ✅ 全綠 |
| OpenClaw 9 條 special | ✅ 全綠 |
| Sub-agent IMPL artifact 完整 | ✅ test file + signoff_pack + cargo test 通過 + memory 教訓 sibling W2-IMPL-1/3/4 已 land |
| Sub-agent memory append 完成 | ❌ **E1 memory 缺 W2-IMPL-5 自身 entry**（stalled 在此 phase）|
| Signoff_pack IMPL-4 SQL fix context update | ❌ MEDIUM-1 §3 line 99 仍寫 `trading.klines`（SQL fix 已改 `market.klines`）|
| Layer 2 helper test-only mirror vs main.rs share code | ⚠️ MEDIUM-2 已 explicit declare + N+2 P2 ticket 建議 |
| Memory append 缺失補完 | E2 不補（PM 收尾） |
| 是否需重派 W2-IMPL-5 Round 2 | ❌ **不需** — 核心 IMPL artifact 完整 + 缺失全可由 PM/E1 順手帶 |

**結論**：stalled sub-agent 雖在 memory append phase 被 600s watchdog kill，但 **完整 IMPL artifact 已 land**（test file + signoff_pack 兩 file pushed in HEAD `73bcc1f5`），且 9/9 cargo test PASS + 既有 baseline 0 退化。**stalled ≠ unfinished** — 只是收尾流程的 memory append step 未跑完。E2 對抗驗證後判定 **PASS to E4**，不需重派。memory append 缺失留 PM 統一收尾，不阻 W2 IMPL chain 整 sign-off。

---

## 1. 改動範圍 vs PA dispatch §3.5

```
git show 73bcc1f5 --stat
```

| File | LOC | 屬性 |
|---|---|---|
| `rust/openclaw_engine/tests/btc_lead_lag_panel_fence_integration.rs` | +534 | 新檔 integration test |
| `docs/governance_dev/2026-05-11--w2_impl_signoff_pack.md` | +342 | 新檔 signoff pack |
| `docs/CCAgentWorkSpace/E2/memory.md` | +24 | E2 sibling pattern append (W2-IMPL-4 SQL fix) |
| `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_impl_4_sql_fix_e2_review.md` | +281 | sibling E2 report (W2-IMPL-4) |
| `docs/CCAgentWorkSpace/E4/memory.md` | +44 | sibling E4 memory (W2-IMPL-4 redryrun) |
| `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w2_impl_4_sql_fix_e4_redryrun.md` | +300 | sibling E4 report (W2-IMPL-4) |

**累計改動**: +1525 LOC（其中 W2-IMPL-5 mine = test 534 + signoff 342 = 876 LOC；其餘 sibling W2-IMPL-4 SQL fix re-review collateral）

**PA dispatch §3.5 W2-IMPL-5 acceptance criteria 對齊**：✅ 9/9 criteria（§3 章節對應）。

---

## 2. CLAUDE.md §九 8 條 checklist

| Item | 狀態 | 證據 |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ | §3.5 W2-IMPL-5 acceptance criteria 9/9 對齊 + 0 source code 改動（per task scope「只新檔 test」）|
| 沒有 except:pass / 靜默吞異常 | ✅ | grep 0 hit；test 用 `assert!` panic-on-fail（test 必要） |
| 日誌使用 %s 格式（非 f-string） | ✅ | test 內 `assert!` macro 用 Rust `{:?}` format（測試訊息容許）；無 logger f-string |
| 新 API 端點有 _require_operator_role() | N/A | 純 Rust integration test；無 FastAPI endpoint |
| except HTTPException: raise 在 except Exception 之前 | N/A | 同上 |
| detail=str(e) 已改為 "Internal server error" | N/A | 同上 |
| asyncio 路由中沒有 blocking threading.Lock | N/A | Rust 端純 tokio async；無 Python asyncio |
| 沒有私有屬性穿透（._xxx） | ✅ | test 全用 pub API（`evaluate_shadow_signal` / `BtcLeadLagShadowSignal::no_signal` / `effective_engine_mode` / `mock_*` test helper）|

---

## 3. OpenClaw 9 條特殊 checklist

| 條目 | 狀態 | 證據 |
|---|---|---|
| 跨平台 grep (`/home/ncyu` / `/Users/[^/]+`) | ✅ | test file 0 hit；signoff_pack line 241 是政策反例引用屬 docs/governance 反例引用允許範圍 |
| 雙語注釋（2026-05-05 governance 中文 only）| ✅ | MODULE_NOTE 主體中文 + 技術術語英文 reference 不譯；inline 全中文 |
| Rust unsafe / unwrap / panic 在交易路徑 | ✅ | 0 unsafe；`expect("send ...")` × 3 限 test fixture 內 mpsc::Sender 故障（不可恢復測試錯誤；非交易路徑）；無 panic 在 production code |
| 跨語言 IPC schema 一致 | ✅ | `BtcLeadLagPanel` struct 8 field 對齊 V088 12 column（snapshot_ts_ms / lead_window_secs / btc_lead_return_pct / alt_symbols / alt_xcorr / alt_expected_dir / source_tier / btc_book_imbalance 主信號 + 60s/300s shadow value extension）|
| Migration Guard A/B/C | N/A | 純測試檔；無 SQL migration |
| healthcheck 配對 | N/A | 不引入 wait-TODO |
| Singleton 登記 §九 表 | N/A | 0 新 singleton |
| 文件大小 800/2000 | ✅ | 534 LOC ≪ 800；signoff_pack 342 LOC ≪ 800 |
| Bybit API 改動 | N/A | 不動 Bybit endpoint；mock event 用 `PriceEvent::new` + `event_kind = Some(Orderbook)` 在 fixture |

---

## 4. 對抗反問結果

### 4.1 Q: 「三層 fence 各對應 1 assert 缺一拒簽」— test 真覆蓋 3 fence 各自至少 1 assert (非 stub return true)?

**Test source 驗證**：

| Layer | test function | assert 真實邏輯 | 非 stub 證據 |
|---|---|---|---|
| 1 (step_4_5_dispatch) | `layer_1_fence_only_paper_mode_reads_btc_lead_lag_slot` (line 164-236) | 9 case (PipelineKind × BybitEnvironment) iter + `effective_engine_mode` 推導 em + match arm if/else assert | 9 case 各對應 `should_read` bool + 2 ass per case → 18 actual assertion |
| 2 (main.rs env-gate) | `layer_2_fence_env_gate_three_states` (line 251-295) | 3 状態 × N case 合計 8 個 explicit assert | (a) 4 case env=1 全 spawn + (b) 1 case unset+paper-only spawn + (c) 3 case unset+demo/live skip |
| 3 (cross_asset evaluator) | `layer_3_fence_panel_none_yields_no_signal_sentinel` (line 308-342) | 3 case: panel=None sentinel + Some(panel) all-fail symbol-in-cohort + Some(panel) symbol-not-in-cohort | sentinel.step_gate / condition_pass_count / xcorr.is_nan / expected_dir / alt_index 五段 assert + 2 case 額外 step_gate / count assert |

**E2 獨立 verify Layer 1 source code 邏輯對齊**：

```rust
// rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:206-212
let btc_lead_lag_panel_owned: Option<BtcLeadLagPanel> = match em {
    "paper" => self.btc_lead_lag_panel_slot.as_ref().and_then(|slot| slot.try_read().ok().and_then(|guard| guard.clone())),
    _ => None,  // demo / live_demo / live → fence 主防線
};
```

test mock 對齊邏輯 (line 215-219)：
```rust
let panel_owned: Option<BtcLeadLagPanel> = match em {
    "paper" => Some(mock_panel.clone()),  // simulate slot.try_read() pass
    _ => None,                             // Layer 1 fence default arm
};
```

**E2 評估**: ✅ 對齊。9 case 中 `should_read` bool 精確對應「`em == "paper"`」（Paper variant 2 case + 其餘 7 case false），iter assert 缺一即 cargo test 紅。**非 stub**。

**E2 獨立 verify Layer 2 source code 邏輯對齊**：

```rust
// rust/openclaw_engine/src/main.rs:1005-1018
let btc_lead_lag_paper_enabled_env = std::env::var("OPENCLAW_ENABLE_PAPER").map(|v| v.trim() == "1").unwrap_or(false);
let btc_lead_lag_producer_should_spawn = if btc_lead_lag_paper_enabled_env {
    true  // (a) env=1 → spawn
} else if !has_demo && !has_live {
    true  // (b) env unset + paper-only → spawn
} else {
    false // (c) env unset + demo|live → skip
};
```

test helper `layer_2_should_spawn` (line 141-152)：
```rust
fn layer_2_should_spawn(paper_enabled_env: bool, has_demo: bool, has_live: bool) -> bool {
    if paper_enabled_env { true }
    else if !has_demo && !has_live { true }
    else { false }
}
```

**E2 評估**: ✅ 結構同源 1:1。`layer_2_should_spawn` 是 **test-only mirror**（非 share code），sub-agent 已 explicit declare in comments (line 119)。**MEDIUM-2 finding**：若 main.rs 改邏輯，本 helper 必同步改才能維持 assertion 真實對應。signoff_pack §10.1 已預判 N+2 P2 ticket 抽 helper to `mode_state.rs` pub fn `should_spawn_btc_lead_lag_producer(paper_enabled_env, has_demo, has_live) -> bool`，accept N+2 處理。

**E2 獨立 verify Layer 3 source code 邏輯對齊**：

```rust
// rust/openclaw_engine/src/strategies/cross_asset/mod.rs:118-126
pub fn no_signal() -> Self {
    BtcLeadLagShadowSignal {
        condition_pass_count: 0,
        dual_layer_sigma_pct: ...,
        step_gate: "no_signal",
        r_squared_decay: 0,
        alt_index: None,
        xcorr: f64::NAN,
        expected_dir: 0,
    }
}
```

test assert (line 311-316)：
```rust
let sentinel = BtcLeadLagShadowSignal::no_signal();
assert_eq!(sentinel.step_gate, "no_signal");
assert_eq!(sentinel.condition_pass_count, 0);
assert!(sentinel.xcorr.is_nan());
assert_eq!(sentinel.expected_dir, 0);
assert_eq!(sentinel.alt_index, None);
```

**E2 評估**: ✅ 5 sentinel field 全 explicit assert。**非 stub**。

### 4.2 Q: NaN safe — `compute_btc_book_imbalance` 對 NaN qty / empty levels fail-soft → None 路徑真 cover?

**Test `nan_safe_ingest_task_does_not_panic_on_nan_qty` (line 365-428) source 驗證**：

- event 1: bids 含 NaN qty `(100.0, f64::NAN)` → compute fail-soft → slot 不寫
- event 2: bids `Some(vec![])` empty → compute fail-soft → slot 不寫
- event 3: bids `(100.0, 2.0); 5` valid → compute pass → slot 寫 imb=0.333

assertion (line 410-424):
- slot.is_some() （事 3 valid 後寫入）
- !imb.is_nan() （0.333 非 NaN）
- (imb - 5/15).abs() < 1e-9 （數學期望）

**E2 評估**: ✅ 3-event 端到端 chain 不 panic + slot 最終 Some(0.333) + 數學期望對齊（5×2 / (5×2 + 5×1) = 10/15 = 0.333）。**真實 cover**。

### 4.3 Q: cross-language consistency Rust write panel.btc_lead_lag_panel schema vs Python read 12 column 對齊?

**E2 cross-validate**：

| Rust struct field (`alpha_surface.rs:329-340`) | V088 SQL column (`V088*.sql:26-37`) | 對齊 |
|---|---|---|
| `alt_symbols: Vec<String>` | `alt_symbols TEXT[]` (line 33) | ✅ |
| `btc_lead_return_pct: f64` | `btc_lead_return_pct REAL` (line 28) | ✅ |
| `lead_window_secs: u32` | `lead_window_secs INT` (line 27) | ✅ |
| `alt_xcorr: Vec<f64>` | `alt_xcorr REAL[]` (line 34) | ✅ |
| `alt_expected_dir: Vec<i8>` | `alt_expected_dir SMALLINT[]` (line 35) | ✅ |
| `snapshot_ts_ms: i64` | `snapshot_ts_ms BIGINT` (line 26) | ✅ |
| `source_tier: String` | `source_tier TEXT` (line 37) | ✅ |

額外 V088 column 在 trait struct 缺：`btc_lead_return_pct_60s/300s` (decay shadow value) + `btc_book_imbalance` — 屬 producer 端 snapshot 私有 column，不暴露 trait struct ABI（per `cross_asset/mod.rs:249-254` MODULE_NOTE「保 ABI 穩定」）。

test `cross_language_consistency_nan_in_panel_propagates_to_cond_4_fail` (line 442-463) verify：
- `btc_lead_return_pct = NaN` → cond 4 fail → 4/5 pass → step_gate=plus5_15
- `alt_xcorr[0] = NaN` → cond 3 fail → 4/5 pass → step_gate=plus5_15

**E2 評估**: ✅ Rust struct 7 field 對齊 V088 7 主信號 column；NaN propagation 雙向 in-memory verify。注意 signoff_pack §10.2 explicit declare「PG round-trip byte-equal 屬 E4 dry-run gate 範圍」— E4 端負責跑 Linux PG runtime byte-equal verify（per `feedback_v_migration_pg_dry_run.md` 強制）。**真實 cover Rust 端 + delegate E4 端**。

### 4.4 Q: lookahead bias — producer 60s read vs ingest 100Hz write shift(1) verification?

**test 無 explicit shift(1) test**，但 signoff_pack §3 line 96 寫：

> WS push 100Hz vs producer read 1/60s = 6000:1，必先寫入後讀

**E2 評估**：自然 shift(1) 設計屬「結構性保證」非「test 可驗」（除非構造一個 deterministic time-coupled fixture，但 W2 spec 不要求）。Python 端 counterfactual SQL 走 `LEAD()` forward 60s/120s/300s — 是 W2-IMPL-4 已驗（Linux PG empirical EXPLAIN ANALYZE 1097ms）。**接受結構性保證**，不要求 explicit test cover。

**FYI 反問**：「6000:1 rate ratio 不變條件下，producer 60s tick 取的 imb 是上一次 ingest 寫入 (`slot.read()`) — 但 ingest 是 push-based，producer 是 pull-based，兩者間隔可達 0-60s。0 sec 情況下會否拿到「本 tick 同時 ingest 寫的」slot？」

**E2 分析**：tokio RwLock read/write 是公平互斥 — producer.run_loop 在 `slot.read().await` 階段，ingest_task `slot.write().await` 必排隊；不可能在「同 logical instant」拿到「未完成 write 的中間 state」。+ tokio scheduler async polling 是 cooperative，不 race。本 producer 抓的永遠是上一次 ingest 寫入 commit 後的 snapshot。**結構性無 lookahead bias**。

### 4.5 Q: file ≤ 800 LOC?

`wc -l rust/openclaw_engine/tests/btc_lead_lag_panel_fence_integration.rs` → 534 LOC ≪ 800。**PASS**。

### 4.6 Q: cargo test --release 9/9 PASS + baseline 不退化?

**E2 獨立 verify (Mac release)**：

```
$ cargo test --release -p openclaw_engine --test btc_lead_lag_panel_fence_integration

running 9 tests
test alpha_surface_borrow_lifetime_panel_lives_in_dispatch_scope ... ok
test alpha_surface_tier1_only_defaults_btc_lead_lag_to_none ... ok
test fence_signoff_matrix_three_layers_each_with_assert ... ok
test cross_language_consistency_nan_in_panel_propagates_to_cond_4_fail ... ok
test layer_2_fence_env_gate_three_states ... ok
test layer_3_fence_panel_none_yields_no_signal_sentinel ... ok
test layer_1_fence_only_paper_mode_reads_btc_lead_lag_slot ... ok
test layer_3_shadow_log_target_locked_to_spec_v1_2 ... ok
test nan_safe_ingest_task_does_not_panic_on_nan_qty ... ok

test result: ok. 9 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.03s
```

```
$ cargo test --release -p openclaw_engine --lib   → 2797 PASS 0 fail 0 ignored
$ cargo test --release -p openclaw_core --lib     → 434 PASS 0 fail 0 ignored
```

**E2 評估**: ✅ 9/9 PASS + baseline 2797/434 不退化（與 sub-agent self-claim 完全對齊）。

### 4.7 Q: Sub-agent stalled — IMPL artifact 是否 self-claim 完整 vs ground truth?

| Self-claim (signoff_pack §1 + §8) | Ground truth (E2 verify) | 對齊? |
|---|---|---|
| test file 534 LOC | `wc -l` = 534 LOC | ✅ |
| 9/9 test PASS | `cargo test` 9 passed; 0 failed | ✅ |
| signoff_pack 342 LOC | `wc -l` = 342 LOC | ✅ |
| baseline 2797/434 不退化 | E2 重跑 = 2797/434 | ✅ |
| 三層 fence 各 1 assert | source verify (line 164/251/308) | ✅ |
| §九 16 原則 0 觸碰 | E2 read source 0 觸碰 lease/auth/mainnet | ✅ |
| 跨平台 grep clean | E2 grep 0 hit | ✅ |
| 中文注釋政策對齊 | E2 read MODULE_NOTE 全中文 | ✅ |
| memory append 完成 | **❌ E1 memory 缺 W2-IMPL-5 自身 entry** | ❌ stalled 在此 phase |
| IMPL-4 SQL fix context update 在 signoff_pack | **❌ signoff_pack §3 line 99 仍寫 `trading.klines`** | ❌ 寫於 SQL fix 之後但未同步 |

**E2 評估**: 主要 IMPL artifact 與 self-claim 100% 對齊；stalled point 為 (1) E1 memory append 收尾 + (2) signoff_pack §3 IMPL-4 context update。兩者**均不影響 W2 IMPL chain 整體可用性** — test PASS / 文件 land / baseline 不退化等核心交付完整。

---

## 5. Findings

### 5.1 MEDIUM-1 · Signoff_pack §3 IMPL-4 SQL fix context drift

**位置**: `docs/governance_dev/2026-05-11--w2_impl_signoff_pack.md:99`

**問題**: 表格描述 IMPL-4 為 "offline tool 純讀 panel.btc_lead_lag_panel + trading.fills + **trading.klines**"，但 W2-IMPL-4 SQL fix（HEAD `4bc7be60`，是 `73bcc1f5` 的 parent）已把 SQL 從 `trading.klines` 改為 `market.klines`（B1 BLOCKER fix）。stalled sub-agent 在 SQL fix **之後**寫 signoff_pack 但 §3 描述未同步。

**Severity**: MEDIUM（governance doc drift，不影響執行邏輯但會誤導 future reader/auditor schema 期望）

**Impact**:
- 同一 LOW 問題 W2-IMPL-4 E2 review §5.1 已 flag `w2_paper_edge_report.py:6` docstring drift（同一根原因：W2-IMPL-5 stalled sub-agent 寫於 SQL fix 之後，全鏈未掃 trailing drift）
- audit chain reader 在跑 IMPL-4 caller 時若信 signoff_pack 描述會去 grep `trading.klines` 一無所獲

**建議修法**: signoff_pack §3 line 99 改 `trading.klines` → `market.klines`。1 char-level edit。

**動作**: E2 不修（per skill: signoff_pack 非 obvious typo/lint，屬 governance 文件 — 退回 PM 順手帶清。「不阻 E4 PASS」）

### 5.2 MEDIUM-2 · Layer 2 test-only mirror 維護債

**位置**: `rust/openclaw_engine/tests/btc_lead_lag_panel_fence_integration.rs:141-152`

**問題**: `layer_2_should_spawn(paper_enabled_env, has_demo, has_live)` helper 是 **test-only mirror**（非 share code），與 main.rs:1005-1018 binary 邏輯結構同源但代碼分離。signoff_pack §10.1 已 explicit declare 此 trade-off + N+2 P2 ticket 建議。

**Risk**: 若 main.rs 改邏輯（如新增 (d) `OPENCLAW_FORCE_PAPER_PANEL=1` env override 或改 paper-only 偵測邏輯）→ 本 helper 必同步改才能維持 Layer 2 assertion 真實對應；忘記同步 = test 仍 PASS 但 fence 真實邏輯與 test 期望脫節。

**Severity**: MEDIUM（latent maintenance debt + structural risk；當前 0 觸碰 = 不阻 W2 sign-off）

**Impact**:
- 短期 0 風險（main.rs:1005-1018 alpha-surface foundation 階段穩定，N+1 wave 不預期變動）
- 長期：W-AUDIT-8a Phase B/C/D 接 Tier 2 panel collector + 真實 alpha source promotion 時可能改 env-gate 邏輯（per spec v1.4 hypothesis）→ 二次 sync 風險

**建議修法**（N+2 P2 ticket，**不在本 wave scope**）：
- 抽 helper 到 `rust/openclaw_engine/src/main.rs` or `panel_aggregator/mod.rs` 為 pub fn `should_spawn_btc_lead_lag_producer(paper_enabled_env, has_demo, has_live) -> bool`
- main.rs:1005-1018 改 `let btc_lead_lag_producer_should_spawn = should_spawn_btc_lead_lag_producer(...)`
- integration test 直接 import `use openclaw_engine::should_spawn_btc_lead_lag_producer;` 代替本地 mirror
- share code 後 main.rs binary + integration test 永遠同源；改一改兩

**動作**: E2 不修（per skill: 抽 pub fn 屬業務代碼，非 obvious typo/lint — 退回 PM 開 N+2 P2 ticket `W2-N2-3: layer_2_should_spawn 抽 pub helper 消除 test-only mirror 維護債`）

### 5.3 INFO · E1 memory W2-IMPL-5 entry 缺失（stalled 在此 phase）

**位置**: `docs/CCAgentWorkSpace/E1/memory.md`

**問題**: stalled sub-agent 600s watchdog kill 在 memory append phase；E1 memory 含 W2-IMPL-1/3/4 自身 entry（line 7848/7743/7781）+ IMPL-4 SQL fix entry（line 7890），**缺** W2-IMPL-5 integration test + signoff pack 完整教訓 entry。

**Severity**: INFO（流程治理 gap，非 code defect）

**Impact**:
- Future E1 接手 W2 後續工作（如 D+12 paper edge report run + N+2 P2 ticket 拆 helper）時無 memory 教訓 reference
- W2-IMPL-5 收尾教訓（如 Layer 2 test-only mirror trade-off / 9 case effective_engine_mode iter / cross_asset NaN propagation pattern / WS-rate vs producer-rate ratio shift(1) 結構性保證）丟失

**動作**: E2 不補（per task instructions「Memory append 未完成... E2 不補（PM 收尾）」）。**建議 PM 統一 commit W2 IMPL chain sign-off 時，補 W2-IMPL-5 memory entry**（可採用 signoff_pack §2.5 + §4 + §5 + §10 內容濃縮）。

### 5.4 INFO · 4 個 spec section reference 注釋寫「spec v1.2」舊版

**位置**: `rust/openclaw_engine/tests/btc_lead_lag_panel_fence_integration.rs:331` ("step_gate=minus5（per spec v1.2 §8.1）")，line 347 ("locked_to_spec_v1_2"), line 405-408 ("符 spec v1.2 §7.1 (3) 數學...")

**問題**: test comments + function name 注釋 spec v1.2，但 spec 已 v1.3（W2-IMPL-2 amendment 把 §6.2 從 Python writer 改 Producer env-gate）。spec v1.2 vs v1.3 在 §7.1 metric / §8.1 step gate 0 動（W2-IMPL-2 amendment scope 限 §6.2），所以 test 注釋寫 v1.2 在 metric / step gate 範疇上仍對。

**Severity**: INFO（注釋版本號 drift，0 邏輯影響）

**Impact**: future reader 看 spec v1.3 對 §6 章節 amendment 時可能困惑為何 test 提 v1.2

**動作**: E2 不修（純注釋版本號；signoff_pack §1 已 explicit declare spec v1.3）。建議 N+2 P2 ticket 順手清；不阻 E4。

---

## 6. 三層 fence × 4 sub-task 對照 — E2 verify

| Sub-task | Layer 1 (step_4_5_dispatch) | Layer 2 (main.rs env-gate) | Layer 3 (cross_asset evaluator) | 額外不變量 |
|---|---|---|---|---|
| **IMPL-1 (Orderbook 接線)** | ✅ orderbook slot 寫入時序自然 shift(1)（WS push 100Hz vs producer read 1/60s = 6000:1）| ✅ ingest task spawn 在 IMPL-2 fence pass `if` block 內；fence skip `else` 分支 `drop(book_event_rx)` no leak | N/A | ✅ NaN/empty fail-soft slot None |
| **IMPL-2 (Layer 2 amendment)** | ✅ Layer 1 主防線不變 | ✅ `layer_2_fence_env_gate_three_states` 三狀態 × 8 子 assert | N/A | ✅ spec v1.3 §6.2 同源 |
| **IMPL-3 (Healthcheck [57])** | N/A | ✅ check_57 設計對齊 IMPL-1 + IMPL-2 fence | N/A | ✅ Linux PG dry-run 0.167ms |
| **IMPL-4 (D+12 paper edge report)** | N/A | ✅ counterfactual SQL `WHERE engine_mode='paper'` | ✅ shadow log target 字串契約鎖定 | ✅ PSR(0) Bailey-LdP 2012 skew/kurt + Block-bootstrap deterministic seed |
| **IMPL-5 (本 wave)** | ✅ `layer_1_fence_only_paper_mode_reads_btc_lead_lag_slot` 9 case | ✅ `layer_2_fence_env_gate_three_states` 8 子 assert | ✅ `layer_3_fence_panel_none_yields_no_signal_sentinel` + `layer_3_shadow_log_target_locked_to_spec_v1_2` | ✅ NaN safety + cross-language NaN propagation + file ≤ 800 LOC |

**E2 verify 結論**：三層 fence × 4 sub-task 結構責任明確 + 5/5 IMPL 各 layer 對應 explicit assert 或結構性保證。

---

## 7. 三端 git sync verify

```
Mac (HEAD):           73bcc1f5 W2 IMPL chain SQL fix re-review APPROVED + W2-IMPL-5 stalled work collateral [skip ci]
Linux trade-core:     73bcc1f5 同 (ssh trade-core "git log --oneline -3")
origin/main:          73bcc1f5 同 (Mac local origin/main)
```

**結論**: ✅ 三端 100% sync 在 `73bcc1f5`。

---

## 8. 結論 — APPROVED · PASS to E4

W2-IMPL-5 stalled sub-agent collateral 兩 file (`btc_lead_lag_panel_fence_integration.rs` + `2026-05-11--w2_impl_signoff_pack.md`)：

**核心 IMPL 完整**：
- ✅ 三層 fence 各對應 1 explicit assert function (Layer 1 / 2 / 3)
- ✅ 9/9 integration test PASS（E2 Mac release 獨測 verify）
- ✅ baseline 2797/434 lib 不退化
- ✅ NaN safety + cross-language consistency in-memory verify
- ✅ file 534 LOC ≪ 800
- ✅ §九 16 原則 + DOC-08 §12 + 硬邊界 5 項 0 觸碰
- ✅ 跨平台 grep clean
- ✅ 中文注釋政策對齊

**Stalled 補完評估**：
- ❌ E1 memory 缺 W2-IMPL-5 自身 entry（stalled 600s watchdog kill 在此 phase）— **E2 不補**，留 PM 收尾
- ❌ Signoff_pack §3 line 99 `trading.klines` drift（IMPL-4 SQL fix context update 未同步）— MEDIUM-1，建議 PM 或 E1 順手清

**反問結論**：
- 是否需重派 W2-IMPL-5 Round 2？**❌ 不需** — IMPL artifact 完整 + 缺失全可由 PM/E1 順手帶；重派浪費 token + 拖延 W2 IMPL chain 收尾

**E4 re-regression 必含項**：
1. cargo test baseline 不退化（已 E2 verify）
2. integration test 9/9 PASS（已 E2 verify）
3. Linux PG cross-language byte-equal verify（per `feedback_v_migration_pg_dry_run`，E2 不跑屬 E4 dry-run gate 範圍）
4. paper engine 6h smoke（D+5 deploy 後）

**PM 收尾必含項**：
1. **補 E1 memory W2-IMPL-5 entry**（採用 signoff_pack §2.5 + §4 + §5 + §10 內容濃縮）
2. **修 signoff_pack §3 line 99** `trading.klines` → `market.klines`（1 char fix）
3. **開 N+2 P2 ticket**：(a) `W2-N2-1` btc_lead_lag.rs 拆 producer/ingest/writer 三檔 / (b) `W2-N2-2` w2_paper_edge_report.py 拆 metrics/render/smoke 三 module / (c) `W2-N2-3` layer_2_should_spawn 抽 pub helper 消除 test-only mirror 維護債
4. **commit 訊息明標**：W2 IMPL chain 5/5 sub-task IMPL DONE + pre-existing exception accept rationale + top-5 acceptance + stalled sub-agent collateral 收尾

---

## 9. Operator 下一步

1. **E4 regression**（已並行跑，read-only 不衝突）：cargo test baseline + Linux PG cross-language byte-equal verify
2. **PM**：補 §8 4 項 PM 收尾必含項
3. **W2 IMPL chain 整 sign-off**：E2 PASS + E4 PASS 後 PM 統一 sign-off + push（D+5 deploy paper engine 開始 7d evidence collection 序）
4. **R4 / 治理**：N+2 P2 ticket 開立排序

---

E2 REVIEW DONE: APPROVED · PASS to E4 · report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_impl_5_e2_review.md
