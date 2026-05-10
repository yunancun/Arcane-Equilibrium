# W1 IMPL sub-task 1 — Rust panel_aggregator broadcast core + V085 funding_curve writer wire-up

**Author**: E1 (sub-agent)
**Date**: 2026-05-11
**Sprint / Wave**: Sprint N+1 W1 W-AUDIT-8a Phase B Tier 2 collector
**Spec source**: `srv/docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md` v1.1 (BB WS-first revision)
**Dispatch reference**: v3.7 §3.1 W1-IMPL-α first chunk (~150-200 LOC core + tests)
**Branch**: `main`
**Commit**: `0b76a4db` (LOCAL ONLY — push sandbox-denied per task spec, awaiting PM unified push after E2 + A3 + E4)

---

## §1 任務摘要

完成 Sprint N+1 W1 W-AUDIT-8a Phase B Tier 2 panel collector 的 first chunk
（per dispatch v3.7 §3.1 W1-IMPL-α 範圍）：把 `funding_curve` aggregator 從 stub typedef 升級為**真實 wire panel writer + broadcast core skeleton + 9 unit test**。

**範圍嚴格限定**：
- ✅ B-1 部分：`FundingCurveAggregator` core + V085 `panel.funding_rates_panel` writer
- ✅ Broadcast core skeleton: `PanelAggregator` 框架 + cancel token + funding_curve_mut() accessor
- ✅ slot typedef declare: `FundingCurvePanelSlot` 在 PA D+0 anchor (`slots.rs:170`) 下
- ✅ Unit tests: 9 PASS (cohort filter / overwrite latest / flush / pool unavailable / cohort dedupe / SQL grep guard / panel_aggregator skeleton 3)

**Defer to next sub-task**（per dispatch §「Defer to next W1 sub-task」）：
- ❌ B-2 oi_delta_panel aggregator → E1-β sub-task 2
- ❌ WS subscription wire-up + reconnect → E1-γ sub-task 3
- ❌ main.rs mpsc → broadcast migration → E1-γ sub-task 3
- ❌ continuous aggregate / 5m/15m/1h chunks → E1-γ sub-task 3
- ❌ engine main loop integration / step_4_5_dispatch surface assignment → final E1-δ sub-task

---

## §2 修改清單

### 新檔（兩個）
| 檔 | LOC | 角色 |
|---|---|---|
| `srv/rust/openclaw_engine/src/panel_aggregator/funding_curve.rs` | 333 | FundingCurveAggregator + V085 writer + 6 unit tests |
| `srv/rust/openclaw_engine/src/panel_aggregator/mod.rs` | 221 | PanelAggregator skeleton + funding_curve sub-module re-export + 3 unit tests |

### 修改（一個）
| 檔 | LOC delta | 角色 |
|---|---|---|
| `srv/rust/openclaw_engine/src/ipc_server/slots.rs` | +17 | `FundingCurvePanelSlot` typedef declare 在 PA D+0 anchor 下 |

**Total**: 3 file changed, **+571 insertions** (W2 sibling sub-agent 並行新加 `panel_aggregator/btc_lead_lag.rs` + `database/btc_lead_lag_writer.rs` 不計入本 sub-task)

### 並行 sub-agent 觀察（multi-session）
- `lib.rs` 已被 W2 sub-agent 加 `pub mod panel_aggregator;` declare（line 51）— 我**未**動 lib.rs（co-existence 自然 work，因 W2 declare 包含 funding_curve 子模組）
- `panel_aggregator/btc_lead_lag.rs` (W2 寫) 和 `database/btc_lead_lag_writer.rs` (W2 寫) — 我**未**動，cargo test 全 PASS（25 panel_aggregator test = 9 mine + 16 W2）
- `database/mod.rs` ` M` (unstaged) — 並行 sub-agent 改動，不在我範圍

---

## §3 關鍵 diff

### 3.1 FundingCurveAggregator 核心（`funding_curve.rs:32-105`）

```rust
pub struct FundingCurveAggregator {
    cohort: HashSet<String>,                    // 25-sym strict subset, O(1) lookup
    buffer: HashMap<String, (f64, i64)>,        // sym -> (rate_bps, next_funding_ms)
    db_pool: Arc<DbPool>,
}

impl FundingCurveAggregator {
    pub fn new(db_pool: Arc<DbPool>, cohort_symbols: Vec<String>) -> Self { ... }

    /// `rate_raw` = Bybit V5 tickers fundingRate raw (decimal, e.g. 0.0001 = 1bps)
    /// 本函數 ×10000 轉 bps 入 buffer
    /// non-cohort symbol → silent return（cohort filter, no log spam）
    pub fn on_funding_update(&mut self, symbol: &str, rate_raw: f64, next_funding_ms: i64) {
        if !self.cohort.contains(symbol) { return; }
        let funding_rate_bps = rate_raw * 10000.0;
        self.buffer.insert(symbol.to_string(), (funding_rate_bps, next_funding_ms));
    }

    pub async fn flush(&mut self, snapshot_ts_ms: i64) -> (usize, usize) {
        if self.buffer.is_empty() { return (0, 0); }
        // drain to snapshot — 防 INSERT 期間並發 update 污染本次 flush
        let rows: Vec<_> = self.buffer.drain().collect();
        // 逐 row INSERT 對應 V085 panel.funding_rates_panel
        // ...
    }
}
```

### 3.2 V085 INSERT writer（`funding_curve.rs:178-203`）

```rust
pub(crate) async fn insert_funding_snapshot(
    pool: &Arc<DbPool>,
    snapshot_ts_ms: i64,
    symbol: &str,
    funding_rate_bps: f64,
    next_funding_ms: i64,
) -> SingleInsertOutcome {
    let query = sqlx::query::<Postgres>(
        "INSERT INTO panel.funding_rates_panel \
         (snapshot_ts_ms, symbol, funding_rate_bps, next_funding_ms, source_tier) \
         VALUES ($1, $2, $3, $4, $5) \
         ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE SET \
            funding_rate_bps = EXCLUDED.funding_rate_bps, \
            next_funding_ms = EXCLUDED.next_funding_ms, \
            source_tier = EXCLUDED.source_tier",
    )
    .bind(snapshot_ts_ms)
    .bind(symbol)
    .bind(funding_rate_bps)
    .bind(next_funding_ms)
    .bind("bybit_v5_ws_tickers");
    exec_single_insert(pool, "panel.funding_rates_panel", query).await
}
```

### 3.3 PanelAggregator broadcast core skeleton（`mod.rs:67-133`）

```rust
pub struct PanelAggregator {
    funding_curve_aggregator: FundingCurveAggregator,
    #[allow(dead_code)] db_pool: Arc<DbPool>,
    #[allow(dead_code)] cancel: CancellationToken,
}

impl PanelAggregator {
    pub fn new(db_pool: Arc<DbPool>, cohort_symbols: Vec<String>, cancel: CancellationToken) -> Self {
        let funding_curve_aggregator = FundingCurveAggregator::new(db_pool.clone(), cohort_symbols);
        Self { funding_curve_aggregator, db_pool, cancel }
    }

    /// 供 sub-task 3 整合：dispatch broadcast Ticker variant on_funding_update
    pub fn funding_curve_mut(&mut self) -> &mut FundingCurveAggregator { ... }

    /// run_placeholder — sub-task 1 階段純骨架，等 cancel 即退出
    /// 預期最終 shape (per spec §2.3 line 169-191) 已寫在 doc comment 內
    pub async fn run_placeholder(self) {
        info!(target: "panel_aggregator", "PanelAggregator placeholder start ...");
        self.cancel.cancelled().await;
        info!(target: "panel_aggregator", "PanelAggregator placeholder cancelled, shutting down");
    }
}
```

### 3.4 FundingCurvePanelSlot typedef（`slots.rs:172-188`）

```rust
/// W-AUDIT-8a Phase B B-1: late-injected slot for FundingCurveSnapshot panel。
/// MODULE_NOTE：funding_curve panel aggregator 在 IPC server detach 後 spawn；
///   slot 用 Arc<RwLock<Option<FundingCurveSnapshot>>> 讓 main.rs late-inject。
///   None = uninitialized → dispatch step_4_5 取 None → surface.funding_curve = None →
///   declared FundingSkew tag 的策略 fail-closed 寫 evaluation_outcome='funding_panel_unavailable'。
pub type FundingCurvePanelSlot =
    Arc<RwLock<Option<openclaw_core::alpha_surface::FundingCurveSnapshot>>>;
```

---

## §4 治理對照

### 4.1 CLAUDE.md §二 16 條根原則合規（per W1 spec §7.2）
全 16 條 ✅ — funding_curve 寫 panel.* 學習平面（讀寫分離），cohort filter 是 25-sym strict subset（組合級風險），slot None → fail-closed（生存 > 利潤），ON CONFLICT DO UPDATE idempotent（交易可解釋）。

### 4.2 DOC-08 §12 9 條安全不變量（per spec §7.3）
本 wave **不動** lease / authorization / audit / reconciler / mainnet env / Bybit retCode / fail-closed semantic / live_reserved 任何路徑 → 全 9 條無關 ✅

### 4.3 硬邊界 5 項（per spec §7.4）
本 wave **不動** `live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `decision_lease_emitted` / `authorization.json` → 全 5 項無關 ✅

### 4.4 跨平台兼容性（CLAUDE.md §七 ★★）
- ✅ 路徑無硬編碼（aggregator 不讀路徑；DbPool 由 caller 注入）
- ✅ LocalLLMClient 抽象不涉（純資料管線）
- ✅ 服務可遷移（Linux / Mac dev 一致行為，PG empty url → fail-soft pool=None）
- ✅ 依賴乾淨（用既有 sqlx + tokio + tracing + tokio-util workspace deps，無新增）

### 4.5 注釋規範（CLAUDE.md §七 2026-05-05 governance：默認中文）
- ✅ MODULE_NOTE 中文（funding_curve.rs 頭部 + mod.rs 頭部）
- ✅ struct / fn doc 中文（每個 public API 有 docstring）
- ✅ inline 不變式 + SAFETY 注釋中文
- ✅ 禁英文 only block，禁中文 only 在無技術詞處（serde / tokio / sqlx 等技術詞保 English）

### 4.6 SQL migration / Guard 規範（CLAUDE.md §七）
- ✅ V085 SQL D+0 已 land（`srv/sql/migrations/V085__panel_funding_curve.sql`），含 Guard A/B/C
- ✅ 本 IMPL 不改 SQL，aggregator INSERT 對齊 V085 schema
- ✅ test_insert_sql_locks_v085_columns grep guard 防 sub-task drift

### 4.7 雙 sub-agent / 強制工作鏈（CLAUDE.md §八）
- ✅ Sub-agent IMPL DONE 不直接 commit + push（只 local commit，不 push）
- ✅ Stage / commit `--only` 隔絕 sibling staging area（multi-session race 守則 + `feedback_git_commit_only_for_metadoc.md`）
- ✅ 等 E2 + A3 並行 + E4 regression PASS 後 PM 統一 push
- ✅ 雙 sub-agent 文件互不重疊（W1 panel_aggregator/{mod.rs,funding_curve.rs} + slots.rs 部分；W2 panel_aggregator/btc_lead_lag.rs + database/btc_lead_lag_writer.rs）

---

## §5 Test 結果

### 5.1 panel_aggregator 模組（cargo test panel_aggregator）
```
test result: ok. 25 passed; 0 failed; 0 ignored; 0 measured; 2710 filtered out; finished in 0.03s
```

**9 個我新加 test**（mod.rs 3 + funding_curve.rs 6）：
1. `funding_curve::tests::test_cohort_symbol_funding_update_buffers` — cohort sym update → buffer 入（rate × 10000 對齊）
2. `funding_curve::tests::test_non_cohort_symbol_ignored` — non-cohort sym → silent ignored
3. `funding_curve::tests::test_same_symbol_overwrite_keeps_latest` — 同 sym 多次 update → buffer overwrite latest
4. `funding_curve::tests::test_flush_empty_buffer_returns_zero` — empty buffer flush → no-op (0,0)
5. `funding_curve::tests::test_flush_pool_unavailable_buffer_drained` — pool 不可用 → fail count + buffer drained
6. `funding_curve::tests::test_cohort_size_initialization` — cohort dedupe + 大小驗
7. `funding_curve::tests::test_insert_sql_locks_v085_columns` — grep guard for V085 schema 5 column + ON CONFLICT
8. `panel_aggregator::tests::test_panel_aggregator_constructs_with_cohort` — PanelAggregator 構造 + cohort 大小
9. `panel_aggregator::tests::test_funding_curve_mut_accessor_dispatch` — mut accessor dispatch 進 buffer 通暢
10. `panel_aggregator::tests::test_run_placeholder_responds_to_cancel` — cancel token 響應 < 200ms

**16 個 W2 sibling test**（panel_aggregator::btc_lead_lag::*）— 共存 OK，0 衝突。

### 5.2 全 lib regression（cargo test --lib）
```
test result: ok. 2735 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.58s
```
**0 regression**。新加 9 test 計入；W2 16 test 計入；共 +25 vs baseline 2710。

### 5.3 Cargo build release（cargo build --release）
```
warning: `openclaw_engine` (lib) generated 19 warnings
warning: `openclaw_engine` (bin "openclaw-engine") generated 2 warnings
    Finished `release` profile [optimized] target(s) in 23.35s
```
**0 error**。Pre-existing warnings 19 + 2 = 21（含我加的 1 個 `FundingCurvePanelSlot is never used`，預期：sub-task 3 wire-up 才用）。

---

## §6 不確定之處 + Push back / Decision points

### 6.1 ✅ 並行 W2 + W1 sub-task 2 sub-agent 已 spontaneously land panel_aggregator dir 整合
觀察：實際開工時 `panel_aggregator/` dir 已被 W2 sub-agent 創建並 land `mod.rs`（references `pub mod btc_lead_lag;`）+ `btc_lead_lag.rs` + `lib.rs` declare `pub mod panel_aggregator`。我的 IMPL 走 co-existence 路：保留 W2 declare + 加我的 funding_curve namespace + extend mod.rs body 加 PanelAggregator skeleton。

我 commit `0b76a4db` land 後不久（IMPL DONE 階段），**W1 sub-task 2 (E1-β)** 並行 sub-agent 也 land oi_delta_aggregator + extend mod.rs 加 `pub mod oi_delta;` declare + `oi_delta_aggregator` field + `oi_delta_mut()` accessor + 1 個 PanelAggregator extension test (`test_oi_delta_mut_accessor_dispatch`)。

**最新 cargo test 35 PASS**（9 mine + 16 W2 + 9 W1-β + 1 panel_aggregator extension test 對應）：
- 我的 commit 保留 mod.rs original version（funding_curve only + W2 btc_lead_lag declare）
- W1-β sub-task 2 的 mod.rs extend 是 working tree 的後續變更，**不影響我的 commit**
- 三方 sub-agent IMPL 共存且 build / test 全 GREEN

但這暴露一個 PA dispatch 觀察：**dispatch 範圍在 W2 sub-agent 已 land mod.rs 後派 W1 IMPL**，導致 W1 sub-agent 必須讀 W2 既存內容並 co-exist。建議 PA 後續 dispatch 對 panel_aggregator namespace 內 sub-module 並行性增強：
- 預先 land mod.rs skeleton with `pub mod btc_lead_lag; pub mod funding_curve; pub mod oi_delta;` declare（W1 spec D+0 phase 加），這樣三 sub-task 並行時 mod.rs 永遠不撞 line collision
- 或 dispatch 時明文宣告：「W1 sub-task 1 owner 負責 mod.rs 整合，W2 sub-agent 必先 push self file 後 IMPL DONE，由 W1 sub-task 1 sub-agent 補 mod.rs 整合」

### 6.2 ✅ Push 被 sandbox 攔截（per task spec）
Sandbox 攔截 `git push`：「Pushing directly to main bypasses pull request review; user instructions said stage and let PM unified commit, not push」。完全符合 dispatch 上半段「Try git add + commit + push (Co-Authored-By Claude). 如 push 被 sandbox 攔截：stage + report；PM 統一 commit」+ CLAUDE.md §七 強制鏈 E1→E2→E4→QA→PM。

**狀態**：local commit `0b76a4db` 完成（3 file +571 LOC），未 push。等 PM 統一 push 序列。

### 6.3 ✅ PriceEvent 沒 next_funding_ms field — sub-task 3 範圍
觀察：W1 spec §1.1 明文「`next_funding_ms` 缺，W1 IMPL 必加」。本 sub-task 1 範圍刻意避開 PriceEvent 修改（dispatch 範圍 only `~150-200 LOC core + funding_curve writer`），改 caller-driven API（`on_funding_update(symbol, rate_raw, next_ts)`）讓 sub-task 3 wire-up 時加 PriceEvent.next_funding_ms field + parsers.rs `parse_ticker_item` extract `nextFundingTime` 後即可呼叫本 API。

**Sub-task 3 (E1-γ) IMPL 必須**：
1. `openclaw_types/src/price.rs`: 加 `pub next_funding_ms: Option<i64>` field
2. `ws_client/parsers.rs`: `parse_ticker_item` 加 `nextFundingTime` extract → `event.next_funding_ms`
3. main.rs broadcast::Receiver clone + select! drain Ticker variant + dispatch `panel_aggregator.funding_curve_mut().on_funding_update(...)`
4. 60s flush timer in select! tick → `panel_aggregator.funding_curve_mut().flush(now_ms() as i64).await`

### 6.4 ❓ Decision pending：PG dry-run V085 何時跑
**觀察**：`feedback_v_migration_pg_dry_run.md` 強制要求 V### migration IMPL DONE 前必跑 Linux PG dry-run（V055 5-round 教訓 + V089 trailing comma教訓 32 in memory）。但 V085 SQL 在 D+0 已 dry-run land 完成（per memory `2026-05-10--v085_087_088_dry_run_apply.md`），本 sub-task 不改 SQL；INSERT writer 對齊 V085 schema 由 `test_insert_sql_locks_v085_columns` grep guard + cargo test 驗。

**Decision needed**：
- Option A：PM 統一 commit 後重跑 V085 dry-run 確認 sqlx writer 真實 INSERT 不 RAISE
- Option B：信 D+0 dry-run + grep guard，Linux engine restart 第一個 60s flush 自然驗（sub-task 3 wire-up 後）
- **PA recommended approach**：Option B（D+0 已 dry-run + writer schema-locked + sub-task 3 整合後 1 個 flush 自然驗）

### 6.5 ❓ Multi-session race 觀察 — 本 sub-task 期間實際發生
過程觀察：我兩次 `git add` 後，sibling sub-agent staging 動作把我 staged 的 file 反 reset。最終用 `git commit --only <files>` + `-F <msg_file>` 的 atomic 模式才完成 commit。

**佐證 `feedback_git_commit_only_for_metadoc.md`**：multi-session 下 `git add + commit` 不安全。本案是 **rust source file** 不只是 meta-doc，但同樣命中 race；建議 governance 規則擴展：**任何並行 sub-agent IMPL 的 commit** 都應用 `git commit --only <file>` 模式（不只 meta-doc）。教訓追加到 memory.md 教訓 38（見 §8 後續更新）。

---

## §7 Operator 下一步

### 7.1 E2 review 入口（per dispatch §「E2 self-review + cargo test + Commit」）
- **路徑**：`docs/CCAgentWorkSpace/E2/workspace/reports/`
- **必檢 3 點**（per spec §6 line 530-532）：
  1. **Schema 對齊**: grep `funding_rate_bps`（NOT `funding_rate`）+ V085 schema 5 column；test_insert_sql_locks_v085_columns 已內建 grep guard
  2. **Cohort filter 完整性**: HashSet contains 是否真嚴守 strict subset（test_non_cohort_symbol_ignored 已驗）
  3. **Failure mode 對齊 spec §2.3 line 228-233**: PG fail / pool unavailable / cancel cleanup
- **應用工具**：`engineering:debug` Bug 排查 SOP（如 review 找到 issue）；`bilingual-comment-style` 雙語注釋 grep 驗證

### 7.2 A3 並行核驗（per `feedback_impl_done_adversarial_review.md`）
本 IMPL 涉及共用 helper（panel collector hot path）+ 寫操作（panel.funding_rates_panel PG INSERT），符合 A3 強制核驗 trigger。
- 重點驗 race condition：buffer drain → INSERT 過程中並發 on_funding_update 是否漏資料（本實作 drain 後立即釋放 buffer 給 update，drain 內 row 自包；但下次 flush 才寫；不變式：每個 update 至少進 1 個 snapshot）

### 7.3 E4 regression test（per CLAUDE.md §七 強制鏈 + cargo test --lib）
- **本 sub-task 已 verify**：cargo test --lib 2735 PASS 0 fail 0 ignored
- **E4 額外**：跑 `cargo test --release` + Linux 環境 cross-platform 驗 + 看是否有 platform-specific behaviour（理論上純 Rust + sqlx，無 platform diff）

### 7.4 PM 統一 commit + push（per CLAUDE.md §七 強制鏈）
- 我已 local commit `0b76a4db`（3 file +571 LOC），未 push
- 等 E2 + A3 + E4 全 PASS 後 PM `git push origin main` 觸發 cargo CI gate（如有）
- 不必 squash（保 3-file commit 完整 lineage 給後續 sub-task reference）

### 7.5 Sub-task 2 + 3 dispatch hint
**E1-β sub-task 2 (oi_delta_panel)** dispatch hint：
- File: `panel_aggregator/oi_delta.rs` (新) + V087 SQL writer + `OIDeltaPanelSlot` typedef in slots.rs (anchor line 178)
- Mirror funding_curve.rs structure: aggregator + buffer + flush + INSERT V087
- 1h sliding window deque per sym + cold-start REST backfill 75 req batch
- 預期 ~250-300 LOC + 6-8 unit tests

**E1-γ sub-task 3 (WS wire-up)** dispatch hint：
- File: `openclaw_types/src/price.rs` 加 `next_funding_ms: Option<i64>` + `ws_client/parsers.rs` extract `nextFundingTime`
- main.rs `event_tx` mpsc → tokio::sync::broadcast::channel(2048) migration（critical gating）
- main.rs spawn `panel_aggregator.run(broadcast_rx)` 真實 loop（替換 run_placeholder）
- step_4_5_dispatch.rs surface.funding_curve = self.funding_curve_slot.read().await.clone() assignment
- healthcheck `[57]` `check_57_funding_curve_panel_freshness()` (Python script)
- 預期 ~300-400 LOC（含 caller migration）+ E2 強制 verify mpsc → broadcast 全 caller 適配

---

## §8 Memory.md 更新 hint

追加教訓 38 到 `srv/docs/CCAgentWorkSpace/E1/memory.md`：

```
### 教訓 38：multi-session race 不只發生在 meta-doc，並行 sub-agent rust source 也命中

並行 sub-agent IMPL 期間，sibling sub-agent staging 動作會反 reset 自己 git add
過的 file。本 W1 sub-task 1 IMPL 期間實測：兩次 git add 後 sibling 動 staging area，
我必須用 git commit --only <file> + -F <msg_file> atomic 模式才完成 commit。

教訓：feedback_git_commit_only_for_metadoc.md 規則擴展至所有並行 sub-agent IMPL，
不只 meta-doc。SOP：
1. git status 查看當前 untracked + modified（不接觸非自己範圍）
2. git add <my-files-explicit-paths>
3. git commit --only <my-files-explicit-paths> -F /tmp/<commit_msg>.txt
   (-m "..." inline 在 -- file path 後語法錯，git 把 message 當 file argument)
4. push 由 PM 統一 (sandbox 自然攔個別 sub-agent push)
```

追加教訓 39：

```
### 教訓 39：W1 spec §1.1 明標 PriceEvent 缺 next_funding_ms field，W1 IMPL 必加 — 
            但 sub-task 切分時可選 caller-driven API 避開 cross-file 修改

W1 spec 標 next_funding_ms 缺，但本 sub-task 1 (~150-200 LOC) 可選擇兩條 path：
A. 立即加 PriceEvent.next_funding_ms field + parsers.rs extract（cross-file ~50 LOC 改動）
B. funding_curve aggregator API 設成 caller-driven (on_funding_update(sym, rate, next_ts))，
   等 sub-task 3 wire-up 時一併加 PriceEvent field

選 B 的理由：
- sub-task 1 範圍 first chunk 嚴格 ~150-200 LOC core，加 PriceEvent 屬擴大範圍
- aggregator API 不依賴 PriceEvent shape，更易 unit test
- sub-task 3 整合時 owner 對 broadcast pattern + parser 改動更熟，cross-file diff 集中
- E2 review 範圍小，core schema 對齊驗證集中

教訓：sub-task 切分時，cross-file dependency 偏向**讓有完整 wire-up 上下文的 sub-task 處理**，
不分散到 first chunk + second chunk + third chunk。本 sub-task 1 用 caller-driven API 
是 PA 切分意圖的對齊（dispatch §「Defer to next W1 sub-task」明列 WS subscription 留 sub-task 3）。
```

---

## §9 一句總結

**W1 IMPL sub-task 1 (E1-α first chunk) DONE：panel_aggregator broadcast core skeleton + funding_curve aggregator + V085 INSERT writer + 9 unit tests (cargo test panel_aggregator 25/25 PASS, full lib regression 2735/2735 PASS, cargo build --release 0 error)；本地 commit `0b76a4db` (3 file +571 LOC)，push 被 sandbox 攔截 per task spec，等 E2 + A3 + E4 sign-off 後 PM 統一 push；W1 spec v1.1 BB WS-first 設計對齊（caller-driven API 預留 sub-task 3 wire-up）；DOC-08 §12 + 16 原則 + 硬邊界 5 項全 0 觸碰；multi-session race 實測命中 sibling sub-agent staging 反 reset，用 git commit --only + -F atomic 模式破解（教訓 38）。**

---

**E1 IMPLEMENTATION DONE: 待 E2 審查 (report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w1_impl_alpha_panel_aggregator_v085_writer.md)**
