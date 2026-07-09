# E2 PR Adversarial Review — Phase 1b Calibration Sweep Harness

- Branch: `feature/phase-1b-calibration-sweep-harness`
- Commit: `93069c29 feat(calibration): Phase 1b sweep harness IMPL — 81 cells × Python replay (v48 P0 Step 2)`
- Date: 2026-05-18 (Mac local + ssh trade-core empirical verify)
- Reviewer: E2
- Timebox: light review per `feedback_pnl_priority_over_governance.md` — 2h budget；4-agent heavy SKIPPED

---

## §0 Verdict

**APPROVE-CONDITIONAL → pass to E4**

- 0 MUST-FIX（不 block merge）
- 3 SHOULD-FIX（建議 E1 在 merge 前或 PA cell-selection 階段處理，但若 PA 接受可推遲）
- 4 NTH（P2/P3 follow-up，不影響 sweep 跑與 cell 選擇）
- pytest 63/63 PASS 在 0.03s（mock-free fixture，真實 exercise simulation engine）
- 跨平台 grep 0 hardcoded path
- SQL 全 %s parameterized；無 except:pass；無 f-string log
- governance / 9 safety invariants 不適用（純 read-only research tool；無 Rust 觸動、無 TOML、無 V### migration、無 live auth path）
- 多 session race check 5/5 PASS

---

## §1 Caveat 1-7 Adversarial Verdict

### Caveat 1: PG schema mismatch — VERIFIED, ACCEPTABLE substitute

SSH `trade-core` 實證 (1 hr 內):
- `market.market_tickers`: 14 column 含 `ts/symbol/last_price/best_bid/best_ask/spread_bps/...`，1h 內 76159 row / 40 symbols / MAX(ts)=2026-05-18 14:20:41+02（live data）
- `market.symbol_universe_snapshots`: `tick_size numeric` 存在，DISTINCT ON symbol+ts DESC 邏輯合理
- XRPUSDT 5min 190 samples (~38/min) — E1 claim 67/min 是樂觀但同 order of magnitude，coverage 充足

`market.orderbook_50` / `market.trades` / `market.instruments` 不存在 → E1 用 `market_tickers` 替代是 **better than spec §3.1 fallback rule**：
- spec fallback = `market.trades` aggregated minute mid（分鐘聚合，coarse）
- E1 actual = `market.market_tickers` BBO snapshot（亞秒級精度，含 spread_bps）

**結論**: spec drift 但屬升級而非降級。需 PA 在 §4 selection 報告中標明「實際 data source 是 market_tickers 非 orderbook_50/trades」以保留審計鏈。

### Caveat 2: Trade tape simplified (BBO cross fill) — VERIFIED, MEDIUM CAVEAT

Code (`phase_1b_sweep_replay.py:273-287`):
```python
if position_is_long:
    if sample.best_bid >= (limit_price - FILL_PRICE_TOLERANCE):
        simulated_fill = True
else:
    if sample.best_ask <= (limit_price + FILL_PRICE_TOLERANCE):
        simulated_fill = True
```

E1 自承（comment line 154-156）「保守模型 — 真實 fill 需 trade actually print，BBO cross 是 necessary 但非 sufficient」。

**對抗 probe**:
- minute aggregation 不適用此處（用 BBO snapshot 不是 minute agg）— **E1 caveat 1 替代後此風險已大幅減低**
- BBO snapshot freshness: SSH 確認 1h 76k rows / 40 symbols ≈ 31 sample/symbol/min ≈ 2s 一次 snapshot — 對 fill detection 足夠細粒度
- 但 **systematic optimistic 風險仍在**: BBO 越過 limit_price 不等於 maker order 被 fill（queue position 後排可能 BBO 過了還沒輪到我們）— spec §2.3.5 標 future enhancement

**結論**: ACCEPT with caveat. acceptance gate 數字會 systematically optimistic（fill rate 上界）— PA 在 cell selection 報告必須顯著標 caveat。SHOULD-FIX#3 建議 sweep_report.py 在 metadata 加 `caveat="fill_detection_uses_bbo_cross_proxy_not_trade_tape"` field 自動傳遞。

### Caveat 3: pre-Phase-1b taker baseline = 5.55 bps — VERIFIED

SSH 跑同樣 SQL:
```
engine_mode='demo' AND liquidity_role='taker' AND (close_maker_attempt IS NULL OR =FALSE)
AND ts > NOW() - INTERVAL '7 days' AND qty>0 AND price>0 AND fee NOT NULL
→ n=212 avg 5.552 bps
```

E1 claim n=213 / 5.55 bps — 差 1 row + 0.002 bps 是 time drift（review 時間晚於 E1 IMPL 時間）。**完全對齊**。

時間 range: `MIN=2026-05-11 14:33:56 / MAX=2026-05-18 08:15:09` — **含 pre-restart `2026-05-17 23:54:36` 之前數據**（pre-Phase-1b activator）。這 **符合 spec §4.1 acceptance gate 設計意圖**：用 pre-Phase-1b 的 taker baseline 來判 Phase 1b sweep cell 的 adverse selection。

`get_taker_baseline_fee_bps` fallback 寫死 5.5（line 343-345）— acceptable safety net；若 PG 完全無 taker fill 回 5.5（Bybit taker cap）保 gate 可工作。

**結論**: VERIFIED PASS.

### Caveat 4: Block 4 dedupe 未實作 — MEDIUM SHOULD-FIX

E1 留中文 comment 在 sweep_cells.py:154-155：「baseline D=50 既存於 Block 1-3 baseline 也存於 Block 4：標 is_baseline=True 但 cell_id 不同；report 階段需 dedupe by (family, A, B, C, D)」**但** sweep_report.py 沒實作 dedupe。

**對抗 probe**:
- 重疊 cells：
  - `G-AB-01-C30` (block 1) ≡ `G-D-D50` (block 4)：family=grid, A=0.5, B=1, C=30s, D=50
  - `PG-AB-01-C15` (block 2) ≡ `PG-D-D50` (block 4)：family=phys_giveback, A=0.5, B=1, C=15s, D=50
  - `PS-AB-01-C10` (block 3) ≡ `PS-D-D50` (block 4)：family=phys_stale_roc_neg, A=0.5, B=1, C=10s, D=50

- 對 simulation 影響：每個 cell 跑同樣 simulation（cell_id 不同 label 而已）→ 浪費 3 cell 的 compute
- 對 acceptance gate 影響：`aggregate_summary` 排序 top-2 by `fill_rate × fee_saving` → 若 baseline 配置 lucky 高分，top-2 可能選 2 個 same-config（label 不同）→ operator pilot 派 2 個重複 dispatch

**SHOULD-FIX**: PA cell selection 階段 OR sweep_report.aggregate_summary dedupe by (family, A, B, C, D) tuple，保留第一個 cell_id，丟掉 duplicate。若 PA 採前者，需明確記在 cell selection 報告中。

### Caveat 5: CLI orchestrator phase_1b_sweep_cli.py bonus — ACCEPT

188 LOC argparse + freshness print + per-cell verdict console output。
- 有 3 mutex options（--all-cells / --smoke-test / --cells）+ --skip-pre-restart override + --output-dir
- 順序 console summary 用於人工 inspect
- E1 commit message 列為「E2 review point #2 keep/drop」

**評估**: 合理 convenience。spec §2.5 只列 5 file，CLI 是 wrapper 對應 §5 Step 3 sweep execution；CLI 不引入額外複雜度（只 invoke 既有 module function），自身無業務邏輯。

**結論**: KEEP. NTH#1：CLI 加 `--dry-run` 顯示 cell 列表不跑 PG（人工 verify cell matrix），可推遲。

### Caveat 6: 浮點 epsilon 1e-6 — VERIFIED

對比 Rust source `rust/openclaw_engine/src/strategies/common/maker_price.rs:159-226`:
- Rust `compute_close_limit_price` 內部**不用** epsilon — 純 arithmetic + `is_finite() && > 0.0` filter
- Python port `compute_close_limit_price` 對齊（line 53-101）— **沒**加 epsilon ✓

`FILL_PRICE_TOLERANCE = 1e-6` 只用在 `simulate_cell_against_fill:273-287` BBO cross-limit-price 比較，這是 **simulation 層** Python f64 累積誤差容忍，不是 Rust 對齊問題。

**對抗 probe**: tick_size 最小是 USDT swap 0.0001 (1e-4) 或 BTCUSDT 0.5 之類 — 1e-6 比 tick_size 小 ≥2 order of magnitude，邊界 case 不會誤判（f64 加減誤差通常 1e-15 量級，1e-6 還算過於保守）。`simulated_fill_px = limit_price`（line 278, 285）符合「passive limit order 成交價是 limit price」semantic。

**結論**: VERIFIED PASS.

### Caveat 7: adverse_proxy fail-closed — MEDIUM SHOULD-FIX

`sweep_report.py:143-146`:
```python
adverse_ok = (
    adverse_selection_proxy_bps is not None
    AND adverse_selection_proxy_bps <= pre_phase_1b_taker_baseline_bps
)
```

`None` proxy 直接視為 adverse 失敗 → cell FAIL。

**對抗 probe**: 
- proxy=None 的原因：post-drift sample 缺（PG `market_tickers` 在 fill+60s 點無 sample）
- 這是 data quality issue，不是 cell quality issue
- spec §4.3 FAIL 定義是「all viable cells fail adverse proxy」，**不是「proxy missing → FAIL」**
- 後果：post-drift coverage gap 的 cell 被誤判 FAIL → 真實 viable cell 可能被剔除

**對抗反問**: PG `market_tickers` 對 25 whitelist symbol 有多大 post-drift gap?
- SSH 1h: 76k row / 40 symbol / ≈ 31 sample/symbol/min → fill_ts+60s 點有 sample 機率 > 99% in normal hour
- 但 demo endpoint 偶爾 thin / market closed window → 偶發 gap 不可忽略

**SHOULD-FIX**: 分三態 PASS / FAIL / INDETERMINATE，None proxy → INDETERMINATE（標警告但不阻 pilot；PA / operator 決定）。Alt: keep fail-closed but add explicit log + cell metadata 標 `adverse_status='data_missing'`。

---

## §2 File-by-File Findings

### `phase_1b_sweep_cells.py` (202 LOC) — Cell matrix
**1-line summary**: 81 cell cartesian generator，4 block deterministic + frozen dataclass，pytest 16 PASS。

Findings:
- **OK**: `_generate_block_ab_c` 共用 helper 減重複；family_prefix dict 對齊 spec §1.4
- **OK**: cell_id 唯一性 test_cell_ids_are_unique PASS
- **OK**: frozen dataclass 防 mutation
- **LOW**: Block 4 baseline cells 與 Block 1-3 baseline 同 config（caveat 4 already discussed）

### `phase_1b_tick_loader.py` (372 LOC) — PG loader
**1-line summary**: read-only PG SELECT only，schema 替代 spec §3.1 預設 table，含 freshness verify。

Findings:
- **OK**: 全部 SQL 用 %s parameterized（line 152/180/231/273/333）
- **OK**: `f"{lookback_days} days"` 是 int → str，安全
- **OK**: psycopg2 模式對齊 `counterfactual_exit_replay.py`
- **OK**: `load_tick_window` 一次 query 取全 window，3 段在 Python 切分，效能合理
- **OK**: `load_tick_size_map` 用 DISTINCT ON 取最新 tick_size，DB query plan 預期用 PK index
- **LOW**: DSN 用 f-string 拼接 env vars — password 含 URL 特殊字符（`%@/`）會破壞 DSN parsing。建議用 `psycopg2.connect(**kwargs)` keyword arg 模式。但 Mac local + Tailscale + read-only research tool，**不是 BLOCKER**。
- **LOW**: line 296-301 sample 分段 if/elif/if pattern — drift 是 standalone `if` 故意設計 overlap region [fill+60s, fill+90s]，符合 spec §3.2；可加 comment 解釋 overlap 設計

### `phase_1b_maker_price.py` (230 LOC) — Rust→Python port
**1-line summary**: `compute_close_limit_price` 1:1 port，含 fee_saving + adverse_proxy 計算。

Findings:
- **OK**: 與 Rust source `maker_price.rs:159-226 + 252-352` 1:1 對齊（const 50.0 / `is_finite() && > 0.0` filter / spread_bps comparison / `ceil(half_spread/tick)` widen / `u32::MAX = 2**32-1` overflow check）
- **OK**: 20 pytest 對應 Rust `mod tests` 行 377-662
- **OK**: `fallback_offset_bps` 保留 signature 對齊但 unused，符合 Rust strict-skip 設計
- **OK**: `compute_adverse_selection_proxy_bps` direction_sign 邏輯與 spec §2.3 對齊（sell close +1 / buy close -1）
- **NTH**: docstring 長 verbose 解釋 adverse direction_sign，可拆 helper function 改善可讀性

### `phase_1b_sweep_replay.py` (461 LOC) — Simulation engine
**1-line summary**: per cell × per fill simulation，BBO cross-limit fill detection，spec §2.3 algorithm 對齊。

Findings:
- **OK**: skip 分類完整（spread_guard / no_bbo / tick_size_missing / family_exit_mismatch / crossed_book）
- **OK**: position_is_long 反推邏輯正確（seed.side='Sell' → close long → position_is_long=True）
- **OK**: `strategy_close:` / `risk_close:` prefix canonicalization 對應 Rust 邏輯（line 162-164）
- **OK**: aggregate 統計分母 eligibility 計算合理（line 400-405）
- **MEDIUM (spec drift)**: `maker_fill_rate` 分母 spec §2.4 line 277 是 `n_attempts - n_skipped_spread_guard`（只扣 spread guard），IMPL 改為 `n_attempts - n_skip_total`。E1 自承「擴展」對齊 fillable 樣本但是 **spec drift 需 PA 確認**。建議 SHOULD-FIX：PA 在 cell selection 報告顯式 sign off「採用 expanded denom」並更新 spec v0.2，OR 改回 spec 原版分母。
- **LOW**: line 234-241 skip diagnostic 分類順序 — `crossed_book` 先判，但 `compute_close_limit_price` 內部已用 best_ask <= best_bid → None；line 236 `bbo_at_fill.spread_bps` 用 PG 預計算欄位 vs maker_price 內部重算，理論可不一致。實際**影響小**因為 diagnostic 只影響 skip_reason label 不影響 PASS/FAIL gate
- **LOW**: line 268-287 fill detection 線性掃描 replay_in_window，O(n) per cell × 81 cell × 4-54 seeds → 可忽略，efficient

### `phase_1b_sweep_report.py` (313 LOC) — Output + Wilson CI + gate
**1-line summary**: per-cell JSON + aggregate CSV + Wilson CI + PASS/CONDITIONAL/FAIL gate。

Findings:
- **OK**: Wilson CI 教科書公式對齊（line 99-104）；n=0 → (0,0) 邊界處理 OK
- **OK**: `fee_saving_ci` normal approx 對齊；n=1 → (saving, saving) 邊界 OK
- **OK**: `classify_cell` 邏輯對齊 spec §4.1/§4.2
- **OK**: `write_outputs` 創 3 種 file + optional per-fill audit JSONL
- **MEDIUM (Caveat 7)**: `adverse_ok` None proxy → FAIL（已上述討論）
- **MEDIUM (Caveat 4)**: aggregate_summary 沒 dedupe Block 4 baseline overlap（已上述討論）
- **LOW**: top-2 排序 by `fill_rate × fee_saving`，符合 spec §4.1 line 361；但 tiebreaker 沒定義 — n_simulated_fills 或 cell_id alphabetical？目前 Python sort stable，順序按 reports 列表順序。建議 NTH 加 explicit tiebreaker

### `phase_1b_sweep_cli.py` (188 LOC) — CLI
**1-line summary**: argparse 3-mode orchestrator + freshness print + console summary。

Findings:
- **OK**: 3 mutex group 互斥，good UX
- **OK**: smoke-test cells hardcode `G-AB-02-C30` + `PG-AB-02-C15` 合理快速驗證
- **NTH**: `--dry-run` 顯示 cell list 不跑 PG 可改善 cell matrix verify 流程
- **NTH**: console summary line 175-183 寬度未對齊（cell_id `:<20` 但長 cell_id 可能爆 alignment）

### `tests/test_*.py` × 4 (1009 LOC)
**1-line summary**: 63 unit + integration tests，mock-free fixture，0.03s run。

抽查 5 個 test 確認非空殼:
- `test_close_limit_price_long_close_sells_passively`: 真實 invoke `compute_close_limit_price` + assert 30002.0 (含 small-tick widening 邏輯)
- `test_simulate_fills_when_ask_drops_to_buy_limit`: 真實 invoke `simulate_cell_against_fill` + fixture window + assert simulated_fill=True + fee_saving=3.5
- `test_classify_fail_when_adverse_none`: 真實 invoke `classify_cell` adverse=None → FAIL（符合當前 fail-closed semantic）
- `test_wilson_ci_at_50_percent`: 真實 invoke `wilson_score_interval(5, 10)` + assert range 0.20 < low < 0.30
- `test_write_outputs_creates_files`: 真實 invoke `write_outputs` + tempfile + JSON content assert

**結論**: 真實覆蓋 + 防 regression 對應 Rust source `mod tests` 行 377-662 浮點 mismatch detection。

---

## §3 MUST-FIX / SHOULD-FIX / NTH

### MUST-FIX (block merge): **0 個**

無 critical issue 阻 merge。

### SHOULD-FIX (建議 merge 前處理 OR PA 顯式 sign off)

1. **Block 4 dedupe (Caveat 4)** — `sweep_report.py:aggregate_summary` 或 PA cell selection 階段加 dedupe by (family, A, B, C, D) tuple，避免 top-2 選 2 個 same-config 重複 cell
   - 位置: `phase_1b_sweep_report.py:232-258`
   - 修法: aggregate_summary 內加 `seen_keys = set(); pass_sorted_dedupe = [r for r in pass_sorted if r._key not in seen_keys and not seen_keys.add(r._key)]`
   - 嚴重性: MEDIUM
2. **maker_fill_rate 分母 spec drift** — IMPL 用 expanded denom 扣全部 skip，spec §2.4 只扣 spread_guard。PA 確認採用 expanded 並更新 spec v0.2 OR E1 改回 spec 原版
   - 位置: `phase_1b_sweep_replay.py:400-405`
   - 修法: PA 決定哪邊；若 keep IMPL → spec v0.2 patch 第 277 line
   - 嚴重性: MEDIUM
3. **adverse_proxy=None fail-closed** — 分 PASS/FAIL/INDETERMINATE 三態 OR PA 顯式 sign off「保守 fail-closed 是 deliberate」並標 cell metadata `adverse_status`
   - 位置: `phase_1b_sweep_report.py:143-146`
   - 修法: 加 `INDETERMINATE` enum + classify_cell 三態回傳 + report aggregate 區分 n_indeterminate
   - 嚴重性: MEDIUM

### NTH (P2/P3 follow-up)

1. CLI `--dry-run` 模式顯示 cell list 不跑 PG，方便 cell matrix verify
2. DSN 用 keyword args 模式取代 f-string 拼接（password URL-encoding 風險）
3. top-2 排序 explicit tiebreaker（n_simulated_fills DESC, cell_id ASC）
4. sweep_report metadata 加 `caveat="fill_detection_uses_bbo_cross_proxy_not_trade_tape"` field 自動傳遞給下游 PA cell selection

---

## §4 Test Coverage Adequacy

63 tests / 4 file 抽查 5 個確認非空殼:
- `test_close_limit_price_long_close_sells_passively` — 真實 invoke + small-tick widening assert
- `test_simulate_fills_when_ask_drops_to_buy_limit` — 真實 simulation engine 覆蓋
- `test_classify_fail_when_adverse_none` — fail-closed 行為 lock-in
- `test_wilson_ci_at_50_percent` — Wilson 公式正確性 lock-in
- `test_write_outputs_creates_files` — I/O 路徑 lock-in

**覆蓋面**:
- maker_price port: 20 tests 對應 Rust `mod tests` 行 377-662
- cell matrix: 16 tests 覆蓋 81 cell + 唯一性 + frozen + serializable
- replay engine: 9 tests 覆蓋 fill / skip / family mismatch / strategy_close prefix
- report: 18 tests 覆蓋 Wilson / fee_saving / classify / build_report / aggregate / write_outputs

**Gap**:
- 無 `load_tick_window` / `load_replay_seed` / `load_tick_size_map` 的 unit test（PG-dependent，需 mock 或 integration test）— acceptable 因為 SQL 簡單 + smoke test 已 E2E 驗證
- 無 `compute_adverse_selection_proxy_bps` 完整 boundary case test（mid=None / fill_px=0 各 1 test 但少 edge cases 如 mid=NaN / fill_px=-1）

**結論**: 對 Mac-local research tool 充足。E4 deterministic check (same seed → same output) 可補 integration coverage。

---

## §5 Recommendation: pass to E4 / RETURN

**Pass to E4** for deterministic regression check（spec §6 / commit msg 列 next chain）。

E4 應確認:
1. 跑 `pytest helper_scripts/calibration/tests/` 全 PASS
2. 跑 CLI `--smoke-test` 兩次比對 output（deterministic check）
3. PA 對 3 個 SHOULD-FIX 決定方案（dedupe / denom drift / adverse fail-closed）— 此 3 個不阻 E4 regression，但阻 81 cell sweep production run interpretation

E2 已自證:
- Mac-local 純 Python research tool / 0 Rust touch / 0 production code impact
- spec §1-§5 主要邏輯 align（有 3 個 spec drift 上述標明）
- 16 root principles / 9 safety invariants 不適用（read-only research tool，無 trading side effect）

---

## §6 Multi-Session Race Check 5/5

| Check | Command | Result | 評估 |
|---|---|---|---|
| 5a 提交前 fetch + sibling window | `git fetch --prune origin` + `git log --since="2h ago" origin/main` | 2h 內僅 PA spec commit 75e29265（review 對象 parent） | ✓ |
| 5b sub-agent IMPL DONE 前 status clean | `git status --porcelain` | 4 unstaged 全屬其他 worktree report .md（PA/QA report + memory feedback），非本 review scope | ✓ |
| 5c 看到 unknown WIP 禁 revert | 無未識別 WIP | N/A | ✓ |
| 5d Sign-off report commit 前 path clean | report 將寫 `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--phase_1b_calibration_harness_e2_review.md`，無重名衝突 | ✓ |
| 5e PR review 期間 sibling 推 origin | review 期間無 sibling push（origin/main HEAD = 75e29265 不變） | ✓ |

**Race check 5/5 PASS**。

---

## §7 Adversarial Probe 結論摘要

| Caveat | Verdict | 重要證據 |
|---|---|---|
| 1 PG schema substitute | VERIFIED, ACCEPTABLE upgrade | SSH 確認 market_tickers 含 14 col + 1h 76k row + XRPUSDT 190 sample/5min |
| 2 BBO cross fill simplified | VERIFIED, MEDIUM CAVEAT | E1 自承 necessary 非 sufficient；spec §2.3.5 future enhancement 保留；report 須標 caveat |
| 3 5.55 bps taker baseline | VERIFIED | SSH 跑同樣 SQL → n=212 / 5.552 bps（差 1 row time drift） |
| 4 Block 4 dedupe 未實作 | CONFIRMED gap → SHOULD-FIX | sweep_cells comment 自承需 dedupe but sweep_report 沒做 |
| 5 CLI bonus 6th file | ACCEPT | 188 LOC argparse + 無業務邏輯，合理 convenience |
| 6 1e-6 epsilon | VERIFIED | port 內部不用 epsilon；只在 BBO fill 判定容忍 f64 累積誤差；tick_size ≥ 1e-5 安全 |
| 7 adverse fail-closed | MEDIUM SHOULD-FIX | None proxy 多半 data missing 非 cell quality；建議三態 |
| 額外 spec drift | maker_fill_rate denom 擴展 | spec §2.4 只扣 spread_guard / IMPL 扣全部 skip，技術上更合理但需 PA confirm |

---

E2 REVIEW DONE: APPROVE-CONDITIONAL · report path: docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--phase_1b_calibration_harness_e2_review.md
