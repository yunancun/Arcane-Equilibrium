# E2 PR Adversarial Review — P2-SIM-QUEUE-AWARE-ADJUSTMENT v55

- Branch / HEAD: `232c3aff` (origin/main 0 ahead，feature 未推)
- Date: 2026-05-20
- Reviewer: E2
- 範圍: queue-aware bias model + historical regression CLI（Mac local + 既有 ssh
  trade-core empirical 跑過 14d 樣本）

---

## §0 Verdict

**APPROVE-CONDITIONAL → pass to E4**

- 0 MUST-FIX（不 block merge）
- 2 SHOULD-FIX（建議 E1 在 E4 前或下次 sweep 處理；不阻 E4 regression）
- 4 NTH（P2/P3 follow-up，不影響 v55 regression interpretation）
- pytest **89/89 PASS 在 0.04s**（既有 63 + queue_adjustment 22 + integration 4，
  mock-free fixture）
- bias_before +61.11pp → bias_after -1.17pp，|bias| reduction 59.95pp，verdict
  PASS（target ≤ 5pp）— 但 statistical caveat 見 §1.4
- 8 條 reviewer checklist 全 PASS
- OpenClaw 9 條特殊條目全 PASS（純 read-only Python research tool 不適用大多數）
- §3.11 ML invariant grep PASS：0 命中 linucb / scorer / quantile / mlde / dl3
- Multi-session race check 5/5 PASS
- 範圍鎖定：0 改 V094 schema / Rust runtime / strategy logic / TOML

---

## §1 對抗 review — 8 個維度逐項

### §1.1 task #1 — Bias model 數學正確性

**PASS**

公式逐項驗（`apply_queue_adjustment` line 125-189）:

```
fill_p_adjusted = fill_p_proxy
                × (1 - base_rejection_rate)
                × (1 - queue_weight × queue_factor)
```

對抗 probe：
1. **乘性 vs 加性合理性**：乘性 model 自然保證 fill_p_proxy=0 → fill_p_adjusted=0
   （"no cross → no fill" necessary condition 不破），加性會在 proxy=0 時需額外
   clamp 防負概率。E1 在 §3.2 line 145-149 完整 justify。**通過**。
2. **單調性 / 飽和性**：`queue_factor = my_qty / (my_qty + depth_5)` 線性飽和
   bounded [0, 1] 單調，my_qty=depth_5 時 0.5，極端 saturate。對應 test
   `test_queue_factor_zero_when_my_qty_far_smaller / half / approaches_one`
   全 PASS。**通過**。
3. **邊界 case**：
   - fill_p_proxy=0：line 158 早 return 0.0 ✓（test_apply_queue_adjustment_zero_proxy_returns_zero）
   - queue_w=0：base_factor 仍套用（test_apply_queue_adjustment_with_base_rejection_no_queue_data 0.5×1=0.5）✓
   - base_rejection=0：default DEFAULT_BASE_REJECTION_RATE=0.0 對應 base_factor=1.0 ✓
   - queue_factor=None：line 171 queue_adjustment 維持 1.0，只套 base ✓
   - queue_factor > 1（浮點 drift）：line 175-176 clamp [0,1] ✓
   - queue_w > 1：line 182-183 clamp [0,1] ✓
   - base_rejection > 1：line 167-168 clamp [0,1]，極端 base=1.5 → 0 ✓
4. **物理 model 對齊**：與 Roll 1984 / Glosten-Milgrom single-parameter linear
   approximation 一致；queue 與 non-queue fail mode 物理上獨立 → 乘性合成
   correct（兩維 hazard 獨立可乘）。

證據：22 unit tests 對 queue_factor / apply_queue_adjustment / select_same_side_depth
boundary case 完整覆蓋，全 PASS。

### §1.2 task #2 — `base_rejection=0.70` 是否 hardcode

**PASS（critical 驗證點）**

`grep -rn "base_rejection\|0.70" helper_scripts/calibration/phase_1b_queue_adjustment.py`
結果：

- Line 60: `DEFAULT_BASE_REJECTION_RATE = 0.0`（**default 是 0.0 不是 0.70**）
- `0.70` 在 source code 0 出現

`grep` regression CLI 的 0.70 出現位置：
- `phase_1b_queue_bias_regression.py:319`: `base_rejections: tuple = (..., 0.70, ...)`
  — 這是 **2D sweep grid 的列舉值之一**，不是 default
- CLI `--base-rejection` argparse default = `DEFAULT_BASE_REJECTION_RATE` = 0.0

E1 honest finding 100% 對齊：
> 正確路徑 = CLI 顯式 inject；source DEFAULT 維持 0.0

`apply_queue_adjustment(fill_p_proxy=1.0, queue_factor=None)` 在 default 設定下
回 1.0（無 base 維度調整），符合 a priori 不假設 fail mode 的設計意圖。

**通過**。

### §1.3 task #3 — v55 治理 invariant

**PASS**

驗 §3.11 ML training pipeline non-input invariant（最敏感條目）：

```bash
grep -rn "queue_adjusted\|queue_factor\|base_rejection_rate" \
    rust/openclaw_engine/src \
    program_code/.../ml_training \
    rust/openclaw_engine/src/strategist \
    rust/openclaw_engine/src/learning \
    rust/openclaw_engine/src/ml_training
```
→ **0 命中**。

驗 sim harness vs runtime 隔離：

```bash
grep -rn "queue_adjusted\|same_side_depth\|base_rejection" \
    rust/openclaw_engine/src
```
→ **0 命中**。

驗下游 sweep_report / CLI：
- `phase_1b_sweep_report.py` 沒讀 `queue_adjusted_fill_rate` / `queue_factor` / `same_side_depth_5` 新欄位
- `phase_1b_sweep_cli.py:139-144` 呼 `simulate_all_cells` **沒**傳 `orderbook_windows`
  → 走 default 路徑 `None` → 純 backward-compat，舊 81-cell sweep 不會無故跑 queue adjust

V094 close_maker_* 欄位使用驗：
- `close_maker_attempt` 用作 WHERE filter（regression CLI line 113 / tick_loader line 163）
- `close_maker_fallback_reason` carrier
- `liquidity_role` ground truth（maker vs taker count）
- **不餵任何 ML feature／training data**（§3.11 invariant FULL PASS）

**通過**。sweep proxy 修正與 runtime fill rate 推論明確隔離。

### §1.4 task #4 — Historical regression empirical 結果

**PASS with statistical CAVEAT**（E1 已 honest disclose）

1. **PG read-only 風險**：
   - 5 個 SQL 查詢全 SELECT only（grep cur.execute 全為 SELECT，0 INSERT/UPDATE/DELETE）
   - `_get_conn()` 用既有 phase_1b_tick_loader 同模式，DSN 從 env var
   - JSON artifact 顯示 `actual_maker=5, actual_taker=13, n_attempts=18` 與
     `liquidity_role` ground truth 對齊
   - **無破壞 production data 風險** ✓

2. **重現性**：
   - JSON artifact `p2_sim_queue_aware_regression_v55.json` 內含：
     - `ANCHOR_CELL` 完整 schema（line 2-12）
     - `lookback_days: 14`（line 13）
     - `queue_weight: 0.1, base_rejection_rate: 0.7`（line 23-24）
     - 45 個 sweep cell 完整 (queue_w, base) × adjusted_rate × bias_pp（line 95-366）
     - 5 個 sample fill diagnostic（line 33-89）
   - 任意 Linux PG host 跑 `python3 phase_1b_queue_bias_regression.py
     --queue-weight 0.1 --base-rejection 0.7 --sweep-params --json-out X.json`
     可重現（PG sample stability 假設）✓

3. **Wilson CI 對 n=18 bias_after**：
   - actual_fill_rate = 5/18 = 0.2778
   - Wilson 95% CI = [0.1250, 0.5087]（寬度 38.4pp，E2 手算驗）
   - adjusted_rate = 0.2661 **完全落在 actual CI 內**
   - → bias_after -1.17pp 在 statistical sense 「indistinguishable from zero」
   - **但這也代表「indistinguishable from +25pp / -15pp」**：n=18 CI 太寬無法
     精細判別任何 base_rejection 值是否「真實」

E1 honest finding §6.1 已明確 disclose：
> empirical 校 14d n=18 樣本 Wilson 95% CI [15%, 50%] 對應 0.50-0.85 base 區間，
> 太寬；當前實作正確路徑 = CLI 顯式 inject；source DEFAULT 維持 0.0；後續累積至
> n≥50 後再考慮 promote 為 source constant + spec amend

→ **E1 已自證 statistical limitation；不算盲區**。task verdict（|bias_after| ≤ 5pp）
僅在 14d sample 下成立，不可外推為 "queue model bias-free"。

### §1.5 task #5 — Test coverage

**PASS**

抽查 7 個 test 非空殼（含 NEW 22 unit + 4 integration）:

| test | 真實 invoke | edge case 覆蓋 |
|---|---|---|
| `test_queue_factor_zero_when_my_qty_far_smaller` | `compute_queue_factor(1, 10000)` → 9.999e-5 | 小 qty / 大 depth ✓ |
| `test_queue_factor_half_when_my_qty_equals_depth` | (100, 100) → 0.5 | 等量 ✓ |
| `test_queue_factor_approaches_one_when_my_qty_dominates` | (10000, 1) → ~0.9999 | 大 qty / 小 depth ✓ |
| `test_queue_factor_none_when_depth_zero/negative/none/nan` × 4 | fail-closed | 邊界 ✓ |
| `test_apply_queue_adjustment_zero_proxy_returns_zero` | (0, 0.5) → 0 | "no cross → no fill" 不變 ✓ |
| `test_apply_queue_adjustment_clamps_weight/factor_to_valid_range` × 2 | 浮點 drift | 邊界 ✓ |
| `test_apply_queue_adjustment_caps_proxy_at_one` | 1.0001 → 1.0 | 浮點 drift ✓ |
| `test_apply_queue_adjustment_base_rejection_clamped` | base=1.5/=-0.5 | 邊界 ✓ |
| `test_end_to_end_typical_close_buy_with_realistic_depth` | ARBUSDT 500 vs 10k → factor 0.0476 | realistic 14d 比例 ✓ |
| `test_queue_adjusted_probability_when_fill_and_depth_available` | qty=100 vs depth=100 → factor=0.5 → 0.80 | integration ✓ |
| `test_queue_adjusted_probability_passthrough_when_no_orderbook` | orderbook=None → 1.0 | backward-compat ✓ |
| `test_queue_adjusted_probability_zero_when_no_fill` | no cross + has depth → 0.0 | "no cross → no fill" 不變 ✓ |
| `test_simulate_cell_aggregates_queue_adjusted_rate` | 2 seeds (fill+no fill) → (0.8 + 0) / 2 = 0.40 | aggregate ✓ |

既有 63 test（maker_price / sweep_cells / sweep_replay / sweep_report）GREEN — 因
新 dataclass field 全有 default value，舊 test 不需改 = false positive 風險 0。

**Gap**:
- 無 `compute_queue_factor` 對 nan/inf 在 my_qty 的測試（`math.isfinite(my_qty)` 邏輯在 line 107 有 guard）
- 無 `apply_queue_adjustment` 對 `fill_probability_proxy=NaN` 的測試（line 155-156 已有
  `math.isfinite` guard）— 缺 explicit test 但邏輯路徑已驗

**評估**: 22 unit 對 pure-function 覆蓋面充足；4 integration 覆蓋 simulate_cell
aggregate。整體 coverage 充足，不阻 E4。

### §1.6 task #6 — 範圍鎖定

**PASS**

驗：

1. **V094 schema 0 觸**：
   - `git diff sql/migrations/` → 0 file 改動
   - 範圍只在 helper_scripts/calibration/

2. **Rust runtime 0 觸**：
   - `grep queue_adjusted|queue_factor|same_side_depth|base_rejection` rust/openclaw_engine/src → 0 命中
   - `git diff rust/` → 只 `tests/stress_integration.rs`（與本任務無關，是隔壁 worktree 殘留 M file）

3. **strategy logic 0 觸**：
   - 純 Python helper / read-only PG / 純 simulation
   - 無 TOML / RiskConfig / live order path 觸碰

4. **`phase_1b_tick_loader.py` isolated dependency 描述**：
   - `import phase_1b_queue_adjustment.QueueDepthSample` 是循環依賴 risk？驗：
     `phase_1b_queue_adjustment.py` 只 `import math + dataclasses + typing` —
     **無**反向 import → 不循環 ✓
   - 新增 `OrderbookDepthWindow` + `load_orderbook_window` 是 new function，
     既有 `load_tick_window` / `load_replay_seed` / `load_tick_size_map` 簽名不變
   - `phase_1b_sweep_replay.py` 內 `load_all_orderbook_windows` 用局部 import
     `from phase_1b_tick_loader import load_orderbook_window`（line 567）規避
     module-level 循環

5. **git diff** stat：
   - 5 file phase_1b 範圍內（4 modified + 3 untracked + 1 already verified ahead）
   - 0 改 Rust / V094 SQL / TOML / authorization.json

### §1.7 task #7 — Adversarial probes（找 E1 missed issue）

#### §1.7a Family-specific bias 分群

**MEDIUM CAVEAT — SHOULD-FIX #1**

`ANCHOR_CELL = G-AB-01-C90`（family=grid）；regression CLI SQL line 113-117
`exit_reason = ANY(grid_close_*, bb_mean_revert, ma_reverse_cross, bw_squeeze,
pctb_revert)` 拉 **多家族 exit_reason**，但 `simulate_cell_against_fill` 內部會
`family_exit_mismatch` skip 非 grid family。

實際後果：n=18 全 grid family（regression 結果 `skip_breakdown.family_mismatch=0`
證實 PG sample 全是 grid_close_long/short）。對 grid family 結論 valid。**但**：
- 如果未來 bb_breakout / phys_lock_giveback / phys_lock_stale_roc_neg 各跑
  regression，需各自 anchor cell 重跑
- 當前 SQL 拉 6 exit_reason 過寬會浪費 PG round trip — minor inefficiency
- 結論不可外推至非 grid family

**SHOULD-FIX**: regression CLI doc 增加「結論限 grid family；其他 family 需用對應
anchor cell（PG-AB-01-C15 / PS-AB-01-C10）重跑」明確 disclose；OR SQL 改為只拉
anchor cell.family 對應 exit_reason 減少 query 浪費。

#### §1.7b `my_qty` source

**INFO — 不算 issue（V094 schema constraint）**

E1 使用 `seed.qty` = `trading.fills.qty` 作 `my_qty`。V094 schema 確認
（`sql/migrations/V094__fills_close_maker_audit.sql` line 12-13）：
> ADD close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE
> ADD close_maker_fallback_reason TEXT NULL

V094 **沒**新增 `placement_my_qty` hot column；其 spec line 9 明確說「lower-frequency
per-fill context 繼續放在 details JSONB payload」。

對 close-maker first attempt → cancel → taker fallback 路徑，placement_maker_qty
= fallback_taker_fill_qty（PostOnly cancel 後完整重提，qty 不變），所以 `seed.qty`
是 schema-available source 內最精確選擇。

**不是 placeholder**。E1 honest finding §6.3 已提到「placement 時刻精度」issue
但用「ob_snapshots 1m bucket 粒度差 vs sim ms-level」框架，沒明說 my_qty 用 fill
qty — minor doc gap，不致命。

#### §1.7c Queue depth source / timing alignment

**LOW CAVEAT — NTH#1**

`depth_at_or_before(seed.ts)` 取最近 1m bucket ≤ taker fallback ts。但 maker
placement 在 fill_ts - timeout_ms（60-90s）之前發生 → queue depth proxy 與
placement 時刻錯位最多 60-90s + bucket boundary（可能跨 1 個 bucket）。

對抗 probe：
- 14d sample queue_factor 全 < 0.02（per JSON artifact line 41/52/62/73/85）→ 此
  timing 偏差不影響當前結論
- 若未來 sample 出現 large-qty / small-depth 場景，timing 偏差可能 material

E1 §3.3 局限 #2「不模擬 order placement timing」已點出。**不阻 E4**。

#### §1.7d V002 market_tickers vs ob_snapshots streaming alignment

**INFO**

E1 task brief 假設 `market.market_tickers.bid_size / ask_size` 可作 V002 size。
empirical 14d query 揭示 `market_tickers.bid_size` 僅 1.15% rows > 0（ingest
pipeline 沒填）→ IMPL 改用 `market.ob_snapshots.bid_depth_5 / ask_depth_5`。

`phase_1b_queue_adjustment.py` line 18-23 完整 disclose 此 reframe。

`ob_snapshots` 1m bucket 對齊 tick 時刻可能有 ±100ms drift — 不致命因為 1m 粒度
remixed 偏差遠大於 ms 偏差。**不阻 E4**。

#### §1.7e PG sample stability

**SHOULD-FIX #2**

regression JSON artifact 是 14d window，每次跑 `--lookback-days 14` 結果會隨
demo runtime 累積新 fill 而漂移。E1 IMPL `WHERE ts > NOW() - 14 days` 是
sliding window — 重現需 freeze sample（pin `ts BETWEEN X AND Y`）OR 接受結果
non-deterministic。

**SHOULD-FIX**: 加 `--sample-end-utc` CLI 參數，pin window end time；或
documentation 明確說「regression result depends on PG fill accumulation; for
exact reproduction, run within ~1 hour of original timestamp」。

### §1.8 task #8 — Commit-readiness + E4 派發

**PASS to E4**

E4 應跑：

1. **`pytest helper_scripts/calibration/tests/`** 89/89 PASS（E2 已驗）
2. **deterministic check**：
   - 用同 JSON artifact `--queue-weight 0.10 --base-rejection 0.70` 重跑（PG
     sample 可能漂移，但 sweep grid 對 fixed seed list 應 stable）
   - 對比新 JSON output 的 sample_results vs artifact line 33-89 ─ queue_factor /
     depth_5 / queue_adjusted_p 應 bit-exact
3. **既有 81-cell sweep regression**：
   - 跑 `phase_1b_sweep_cli.py --smoke-test` 確認舊 path（無 orderbook_windows）
     仍 PASS（per backward-compat 設計）
   - 兩次 smoke-test output diff = 0（deterministic check）
4. **無新 V### migration → 無 PG dry-run 需求**

---

## §2 8 條 reviewer checklist

| Item | 狀態 | 證據 |
|---|---|---|
| 1. 改動範圍與 PA 方案一致 | ✓ | 範圍限 helper_scripts/calibration/ 6 file；0 改 V094/Rust/TOML |
| 2. 沒有 except:pass 或靜默吞異常 | ✓ | grep 0 命中（`except:\s*pass`） |
| 3. 日誌使用 %s 格式（非 f-string） | ✓ | 0 logger 調用；f-string 全在 print/stdout |
| 4. 新 API 端點有 _require_operator_role() | N/A | 0 新 API endpoint |
| 5. except HTTPException: raise 在 except Exception 之前 | N/A | 0 HTTPException 用 |
| 6. detail=str(e) 已改為 "Internal server error" | N/A | 0 FastAPI 用 |
| 7. asyncio 路由中沒有 blocking threading.Lock | N/A | 0 asyncio/threading 用 |
| 8. 沒有私有屬性穿透（._xxx） | ✓ | grep 0 命中 |

---

## §3 OpenClaw 9 條特殊 checklist

| Item | 狀態 | 證據 |
|---|---|---|
| 3.1 跨平台合規 | ✓ | grep `/home/ncyu \| /Users/[^/]+` 0 命中 |
| 3.2 注釋規範 | ✓ | 6 file 全含 MODULE_NOTE + 中文 rationale；ob_snapshots reframe 完整 disclose |
| 3.3 Rust unsafe / unwrap | N/A | 0 Rust 改 |
| 3.4 跨語言 IPC | N/A | 0 IPC schema 改 |
| 3.5 Migration Guard A/B/C | N/A | 0 V### migration |
| 3.6 healthcheck 配對 | N/A | 0 新被動等待 TODO |
| 3.7 Singleton / monkey-patch | N/A | 0 新 singleton |
| 3.8 文件大小 800/2000 | ✓ | phase_1b_queue_bias_regression 452 LOC（最大）；其他 < 400 |
| 3.9 Bybit API | ✓ | 0 REST/WS endpoint call；只用 `"bybit_demo_ws"` data tag 字串 |
| **3.10 P0/P1 leak caller-path grep** | N/A | 0 P0/P1 finding |
| **3.11 ML training non-input invariant** | **✓** | grep 0 命中 linucb/scorer/quantile/mlde/dl3；close_maker_* 只用 filter/carrier/ground-truth，**不**進 training feature |

---

## §4 Multi-session race check 5/5

| Check | Command | Result | 評估 |
|---|---|---|---|
| 5a 提交前 fetch + sibling window | `git fetch --prune origin` + `git log --since="2h ago" origin/main` | origin/main HEAD = 232c3aff，2h 內無 new sibling commit | ✓ |
| 5b sub-agent IMPL DONE 前 status clean | `git status --porcelain helper_scripts/calibration/` | 3 modified + 3 untracked 全屬本任務；無外洩檔 | ✓ |
| 5c 看到 unknown WIP 禁 revert | 0 動既有 dirty file（其他 worktree memory.md / PM template / stress_integration.rs） | N/A | ✓ |
| 5d Sign-off report commit 前 path clean | `2026-05-20--p2_sim_queue_aware_e2_review.md` 不存在 | ✓ | ✓ |
| 5e review 期間 sibling 推 origin | `git log HEAD..origin/main` empty | ✓ | ✓ |

---

## §5 Findings

### CRITICAL (block merge): **0 個**

### HIGH (block E4): **0 個**

### MEDIUM (SHOULD-FIX，不阻 E4 regression，阻 v55 sweep production interpretation)

1. **family-specific anchor cell disclosure**（§1.7a）
   - 位置: `phase_1b_queue_bias_regression.py:104-117` regression CLI SQL
   - 修法：(a) doc 增加「結論限 grid family」明示；或 (b) SQL 改為只拉
     `FAMILY_EXIT_REASONS[cell.family]` 對應 exit_reason；或 (c) 為其他 family
     新增獨立 anchor cell 並跑各自 regression 補強整個 v55 結論
   - 嚴重性: MEDIUM — 對 anchor 是 grid 的當前結論不致命，但 v55 整體 deploy
     涵蓋 phys_lock 兩 family，需明確 caveat 各自 bias 未驗
   - 建議：E1 後續 round 或 PA cell selection 階段處理；不阻 E4 regression

2. **regression result reproducibility (sliding 14d window)**（§1.7e）
   - 位置: `phase_1b_queue_bias_regression.py:115` `ts > NOW() - %s::interval`
   - 修法：加 `--sample-end-utc` CLI 參數 + JSON artifact 內 record `sample_window_end_utc`
     方便重現；或 documentation 明確說 PG sample 漂移後結果會變
   - 嚴重性: MEDIUM — 影響 audit 可重現性；當前 14d window 跨 demo runtime
     fill 累積會慢慢漂移
   - 建議：E1 後續 round 處理

### LOW (E2 不直接修，留作 NTH P2/P3 follow-up)

1. queue depth timing alignment（placement vs fill_ts）— §1.7c
2. f-string DSN connection string（password URL 特殊字元 risk，但只在 Mac local
   + Tailscale read-only，非 BLOCKER）— 與既有 phase_1b_tick_loader 同模式
3. `--sweep-params` 2D sweep grid 用 hardcode tuple（line 318-319）— 可加 `--sweep-grid` argparse
4. `_qty_for_diagnostic` line 239 O(n) scan per sample — 可改 dict lookup（minor
   perf，n=18 不痛）

---

## §6 對 E1 自承 honest finding 評估

| E1 disclose | E2 verdict |
|---|---|
| §3.3 #1 不模擬真實 LOB ahead-volume | ✓ accept — 14d data 無 tick-level orderbook delta；用 top-5 depth_5 aggregate 是合理近似 |
| §3.3 #2 不模擬 order placement timing | ✓ accept — §1.7c CAVEAT 已分析 |
| §3.3 #3 不模擬 partial fill | ✓ accept — 14d V094 100% binary fill，partial 不常見 |
| §3.3 #4 base_rejection 是 empirical anchor 不是 derived | ✓ accept — §1.2 已驗 source 0 hardcode 0.70 |
| §6.1 14d n=18 Wilson CI 寬不應 hardcode 0.70 進 source | ✓ accept + 強化 — §1.4 Wilson CI 38.4pp 寬，bias_after -1.17pp 統計上 indistinguishable from 0；建議 n≥50 後再 evaluate promote |
| §6.2 queue model effective range < 0.5pp 不代表無用 | ✓ accept — pure-function model 數學正確，14d sample 巧合 vanishing 不否定 model design |
| §6.3 market_tickers.bid_size 1.15% 棄用 ob_snapshots 替代 | ✓ accept — empirical evidence 充分 |
| §6.4 ob_snapshots 1m bucket 跨 fill_ts 邊緣 | ✓ accept — 14d sample queue_factor vanishing 不受 1m 粒度影響 |

E1 honest disclosure quality **A-grade**。所有 limitation 明確 surface，無
optimistic claim。

---

## §7 結論 — Pass to E4 / RETURN

**Pass to E4** for deterministic regression check（per §1.8 task #8 list）。

E2 已自證：
- 純 Python research tool 0 Rust touch / 0 production code impact
- 8 條 + 9 條 + ML invariant + race check 全 PASS
- bias model 數學 correct / source 0 hardcode 0.70
- 89/89 test PASS reproducible（Mac local pytest 0.04s）
- E1 honest finding A-grade

E4 應驗：
1. `pytest helper_scripts/calibration/tests/` 89/89 PASS
2. `phase_1b_sweep_cli.py --smoke-test` × 2 deterministic check（無 queue path
   backward-compat）
3. `phase_1b_queue_bias_regression.py --queue-weight 0.10 --base-rejection 0.70
   --json-out X.json` 重跑，對比 JSON artifact `sample_results` line 33-89 bit-exact

PM 後續處理：
- 2 個 MEDIUM SHOULD-FIX 留作 E1 後續 round（不阻 E4 regression / 不阻 v55 sweep
  rerun，但阻 production cell selection interpretation 階段對 phys_lock family 結論
  cite）
- v55 sweep 用 `(queue_w=0.10, base=0.70)` 跑 81 cells 是 reasonable next step
  — 但需明確 disclose 「base_rejection=0.70 anchor 自 14d grid family n=18，外推至
  phys_lock 兩 family 需各自校 / 或保守用 base=0.0 + queue_w=0.40 default 退回 14d
  grid-only verdict 的 conservative 設定」

---

## §8 Adversarial probe 結論摘要

| 維度 | Verdict | 重要證據 |
|---|---|---|
| 1 bias model 數學 | PASS | 乘性合成 correct / 邊界 case 全 clamp / 22 unit test ✓ |
| 2 base_rejection=0.70 not hardcode | PASS | source default = 0.0；0.70 只在 regression CLI sweep grid tuple |
| 3 v55 governance invariant | PASS | 0 ML pipeline 命中 / 0 Rust runtime / sweep_report 不讀新欄位 |
| 4 PG empirical 結果 | PASS w/ CAVEAT | Wilson CI 38.4pp 寬 — bias_after -1.17pp 統計上 indistinguishable from 0；E1 已 disclose |
| 5 test coverage | PASS | 22 unit + 4 integration 全 PASS / 邊界 case 充足 / 既有 63 不受影響 |
| 6 範圍鎖定 | PASS | git diff stat 限 6 file calibration / 0 V094 / 0 Rust / 0 TOML |
| 7a family 分群 | MEDIUM SHOULD-FIX | 結論限 grid family；phys_lock 未驗 |
| 7b my_qty source | INFO | V094 schema 無 placement_my_qty；用 trading.fills.qty 是 best available |
| 7c queue depth timing | LOW | 14d queue_factor < 0.02 不受影響 |
| 7d ob_snapshots vs market_tickers | INFO | E1 empirical reframe 完整 disclose |
| 7e sliding 14d window 重現性 | MEDIUM SHOULD-FIX | 加 --sample-end-utc 或 doc disclose |
| 8 E4 派發 | PASS | 89/89 + smoke-test + regression bit-exact check |

---

E2 REVIEW DONE: APPROVE-CONDITIONAL · report path: docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-20--p2_sim_queue_aware_e2_review.md
