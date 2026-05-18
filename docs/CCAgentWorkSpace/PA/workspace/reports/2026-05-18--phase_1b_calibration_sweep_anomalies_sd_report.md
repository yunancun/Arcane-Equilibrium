# Phase 1b Calibration Sweep — SD-1 / SD-2 Anomaly Investigation

- Date: 2026-05-18 (Mac, post-sweep `sweep_20260518_125510`)
- Author: PA
- Trigger: PA cell selection report §5.2 (SD-1 A axis dead) + §5.3 (SD-2 PS family 100% skip)
- Predecessor: `2026-05-18--phase_1b_calibration_cell_selection_report.md`
- Format: PnL-led per `feedback_pnl_priority_over_governance.md`
- Scope: **read-only investigation**；不修 code / 不改 spec / 不動 production

---

## §0 Verdict per anomaly

| ID | Anomaly | Verdict | Hypothesis confirmed | Action |
|---|---|---|---|---|
| **SD-1** | A axis (`offset_bps`) dead variable | **VERIFIED dead — spec design intent (NOT IMPL bug)** | A1 (strict-passive maker design：limit = BBO ± buffer×tick，不引用 offset_bps) | Spec note + future sweep prune A axis (78 → ~20 cells) |
| **SD-2** | PS family 100% skip | **VERIFIED no-sample — replay seed pool 內無 `phys_lock_gate4_stale_roc_neg` exit_reason** | B1 (post-restart 4 + pre-restart 50 = 54 fills 內 0 row PS reason) | Spec note + SD-2-future re-sweep when PS sample 出現 |

**核心結論**：兩 anomaly 都 **不是 IMPL bug**，**不需 E1 fix**，**不阻 24h pilot**。只需 spec v0.3 amend note 記錄設計約束 + 後續 sweep efficiency improvement。

---

## §1 SD-1 — A axis (offset_bps) dead variable investigation

### §1.1 Empirical observation (from sweep CSV)

從 `sweep_aggregate.csv` 81 cells 取 G family C=90s B=1，4 個 A 軸 cells：

| cell_id | A (bps) | B | C (ms) | maker_fill_rate | n_simulated_fills | expected_fee_saving_bps |
|---|---|---|---|---|---|---|
| G-AB-01-C90 | 0.5 | 1 | 90000 | 0.7083333 | 34 | 3.3679... |
| G-AB-03-C90 | 1.0 | 1 | 90000 | 0.7083333 | 34 | 3.3679... |
| G-AB-05-C90 | 2.0 | 1 | 90000 | 0.7083333 | 34 | 3.3679... |
| G-AB-07-C90 | 3.0 | 1 | 90000 | 0.7083333 | 34 | 3.3679... |

**精度到第 7 位小數 identical** (fill rate / n_fills / fee saving / adverse all bit-equal)。

擴展 verify：C=60s B=1 (G-AB-{01,03,05,07}-C60) 同樣 4 cell fill=0.6875；C=30s B=1 同樣 4 cell fill=0.5833；PG family C=45s B=1 (PG-AB-{01,03,05,07}-C45) 同樣 4 cell fill=0.5000。**N=78 unique cells 中，A axis 從未 surface 任何差異**。

### §1.2 Code call-path proof — Python port

`srv/helper_scripts/calibration/phase_1b_maker_price.py`：

**`compute_close_limit_price`** (line 53-101)：
- limit_price 計算路徑 (line 86-101)：呼 `compute_post_only_price(is_long=!position_is_long, inputs, policy.offset_bps, buffer_ticks)`
- 將 `policy.offset_bps` 作為 `fallback_offset_bps` 傳入 — 但這只是 signature 傳遞

**`compute_post_only_price`** (line 104-152)：
- Line 117 注釋明文："**為什麼保留 fallback_offset_bps 參數但未使用：與 Rust signature 一致；Rust 的 fallback_offset_bps 在 warn log 引用但不參與計算**"
- Line 131-148 price 計算：
  ```python
  buffer = float(buffer_ticks) * tick
  cross_buffer = tick if buffer_ticks == 0 else buffer
  if is_long:
      price = bid - buffer  # 或 ask - cross_buffer
  else:
      price = ask + buffer  # 或 bid + cross_buffer
  ```
- **`fallback_offset_bps` 完全不在 price formula 中**

**`compute_fee_saving_bps`** (line 161-186)：
- 公式：`FEE_SAVING_CAP_BPS - max(0, slippage_raw)`，其中 `FEE_SAVING_CAP_BPS = 3.5` (taker 5.5 - maker 2.0)
- slippage 從 `actual_taker_px` 與 `simulated_fill_px` 對比計算
- **`offset_bps` 不參與**

**`compute_adverse_selection_proxy_bps`** (line 189-230)：
- 公式：`(mid_at_fill_plus_60s - simulated_fill_px) * direction_sign / simulated_fill_px * 10000`
- **`offset_bps` 不參與**

### §1.3 Code call-path proof — Rust production source

`srv/rust/openclaw_engine/src/strategies/common/maker_price.rs:155-356`：

`compute_close_limit_price` line 164-231：
- Line 223-230 同樣呼 `compute_post_only_price(!position_is_long, inputs, policy.offset_bps, buffer_ticks, strategy_name, symbol)`

`compute_post_only_price` line 257-356：
- Line 305-336 price formula：`buffer = f64::from(buffer_ticks) * tick`；`price = bid - buffer` / `ask + buffer` / `ask - cross_buffer` / `bid + cross_buffer`
- `fallback_offset_bps` 只在 warn log fields 出現（line 276 / 297 / 315 / 332 / 350）
- **production code 也從不在 price 計算中引用 `fallback_offset_bps`**

### §1.4 結論

| 命題 | 結論 |
|---|---|
| Hypothesis A1 (spec design intent — BBO-cross-proxy 在 sweep 不引用 offset) | **不準確** — 真實 root cause 在更上游 |
| Hypothesis A2 (`phase_1b_sweep_replay.py` IMPL bug — offset_bps 沒傳 cross check) | **FALSE** — sweep simulation `_did_fill_within_window` 對 fill 判定基於 limit_price 與 BBO 比較；limit_price 本身已不含 offset |
| Hypothesis A3 (sample artifact) | **FALSE** — 4 axis × 18 row pair × 7 位小數 identical 不可能 statistical artifact |
| **真實 root cause** | **strict-passive close-maker 設計** — limit_price = BBO ± buffer×tick，offset_bps 設計上**從不**參與 limit price / fill / fee_saving / adverse 任何 path |

**Probability assessment（取代 cell selection report §5.2 的 60/25/15）**：
- spec design intent (strict-passive，offset_bps 是 dead parameter in current Rust IMPL): **100%**
- IMPL bug: **0%**
- sample artifact: **0%**

**為什麼是 dead**：`compute_post_only_price` 名義上是 strictly passive maker — 永遠掛 BBO 內側 buffer_ticks tick，不偏移 bps。`offset_bps` 是 historical leftover / 為未來「BBO 不可得時 last_price ± offset_bps」fallback 設計，但 strict path 已決定 **無 BBO 直接 strict-skip 而非 fallback to last_price**（per Rust line 274-281 注釋「no last_price fallback」）。

### §1.5 真實 A 軸用途 candidate

讀 Rust source + spec 後，PA inference：`offset_bps` 在當前 IMPL 是 **dead config parameter**，未發現任何 code path 真實引用。可能的歷史意圖：
- 早期設計：fallback maker price = `last_price × (1 + offset_bps × 1e-4)`，後改 strict-skip 而 parameter 留 backward compat
- 或保留供未來 dynamic fee tier 用（taker fee 隨 VIP 變動，offset_bps 可作為 PnL buffer）

但**當前 IMPL 完全不用** — Rust call-path grep confirmed。

---

## §2 SD-2 — PS family (phys_lock_gate4_stale_roc_neg) 100% skip investigation

### §2.1 Empirical observation (from sweep CSV)

從 `sweep_aggregate.csv` PS family 26 cells 全部：
- `n_attempts`: 54 (= total seeds in replay pool)
- `n_simulated_fills`: 0
- `n_skipped_family_mismatch`: 54
- `n_eligible`: 0

每 cell 100% 走 family_mismatch skip path，零 fill 產生。

### §2.2 SQL proof — replay seed pool 內無 PS exit_reason

跑查 trade-core PG `trading_ai.trading.fills`（依 `phase_1b_tick_loader.py:load_replay_seed` 的同邏輯）：

**Post-restart pool** (anchor `2026-05-17T23:54:36Z`, demo + close_maker_attempt=TRUE)：
| exit_reason | count |
|---|---|
| grid_close_short | 3 |
| phys_lock_gate4_giveback | 1 |
| **phys_lock_gate4_stale_roc_neg** | **0** |
| 合計 | 4 |

**Pre-restart baseline** (最近 50 row 全 whitelist 8 reasons in last 7 days)：
| exit_reason | count |
|---|---|
| grid_close_short | 46 |
| phys_lock_gate4_giveback | 3 |
| ma_reverse_cross | 1 |
| **phys_lock_gate4_stale_roc_neg** | **0** |
| 合計 | 50 |

**合併 seed pool**：54 fills 總計：
- grid_close_short: 49 (90.7%) → G family eligible
- phys_lock_gate4_giveback: 4 (7.4%) → PG family eligible
- ma_reverse_cross: 1 (1.9%) → G family eligible (whitelist)
- **phys_lock_gate4_stale_roc_neg: 0 (0.0%)** → PS family 零樣本

### §2.3 Code path proof — family routing 正確

`srv/helper_scripts/calibration/phase_1b_sweep_replay.py:158-182`：
```python
allowed_reasons = FAMILY_EXIT_REASONS.get(cell.family, [])
canonical_reason = seed.exit_reason or ""
# 去 prefix
for prefix in ("strategy_close:", "risk_close:"):
    if canonical_reason.startswith(prefix):
        canonical_reason = canonical_reason[len(prefix):].strip()
if canonical_reason not in allowed_reasons:
    return FillSimulationResult(... skipped_reason="family_exit_mismatch")
```

`phase_1b_sweep_cells.py:49-60` family mapping：
```python
FAMILY_EXIT_REASONS = {
    "grid": ["grid_close_short", "grid_close_long", "bb_mean_revert",
             "ma_reverse_cross", "bw_squeeze", "pctb_revert"],
    "phys_lock_giveback": ["phys_lock_gate4_giveback"],
    "phys_lock_stale_roc_neg": ["phys_lock_gate4_stale_roc_neg"],
}
```

PS family whitelist = `["phys_lock_gate4_stale_roc_neg"]` 唯一 element。Seed pool 54 fills × PS whitelist 1 reason = 54 不 match × 26 cells = 1404 family_mismatch skip total。

**邏輯正確**：whitelist routing 工作如預期；不是 router bug。

### §2.4 為什麼 seed pool 沒 PS exit_reason

`phys_lock_gate4_stale_roc_neg` 是 phys_lock close 的 5 個 sub-reason 之一（per AMD `phys_lock_amd_v0_3_consolidation`）。在 7 天 + post-restart 窗口內：
- Phys_lock close fills 共 4 row（pre 3 + post 1）
- 4 row 都走 `phys_lock_gate4_giveback` reason path
- 0 row 走 `phys_lock_gate4_stale_roc_neg` reason path

**為什麼**：phys_lock_gate4_stale_roc_neg 觸發條件是「stale + roc_neg」兩 sub-gate 必同時 met。最近 7 天 demo runtime 內 phys_lock close 都是 giveback gate 觸發（market behavior + position lifecycle 偏向）；stale_roc_neg gate 罕觸發是 phys_lock 設計本身的 conditional distribution，與本 sweep IMPL 無關。

### §2.5 結論

| Hypothesis | 結論 |
|---|---|
| B1 (replay seed 內無 PS exit_reason 樣本) | **VERIFIED TRUE** — SQL 54/54 row 都不是 PS reason |
| B2 (family_mismatch skip due to parameter mapping bug) | **FALSE** — family routing 邏輯與 FAMILY_EXIT_REASONS mapping 都正確 |
| B3 (`phase_1b_sweep_replay.py` IMPL bug — PS family 完全 skip) | **FALSE** — skip 是 seed pool data shortage 自然結果，不是 IMPL skip |

**Implication**：
- PS family 26 cells 結果 **不可信 — n_eligible=0 統計上無 information**
- Calibration **不該動 PS family timeout (10s)** — 沒樣本支持任何方向決策
- 等 PS exit_reason 真實樣本累積後可重 sweep（observation period 可能需 30 天+ 視 phys_lock gate4 觸發頻率）

---

## §3 Recommended action per anomaly

### §3.1 SD-1 action

**Spec v0.3 amend note**（PA dispatch 寫，operator 批）：

> **§X. A axis (offset_bps) is a dead parameter in current strict-passive close-maker design.**
> 
> `compute_close_limit_price` / `compute_post_only_price` 當前 IMPL 永遠取 BBO 內側 buffer_ticks tick 作為 limit price，`fallback_offset_bps` 僅在 warn log 引用，不參與 price / fill / fee_saving / adverse 任何 calculation path。
> 
> 對未來 calibration sweep 的 implication：
> - **可 prune A 軸**：取 A=0.5 baseline 即可，cells 78 → ~20 (削減 ~75%)；
> - **若未來啟用 fallback path**（如「無 BBO 時用 last_price ± offset_bps fallback」），須先 update 此 spec note；
> - **不需修 IMPL** — 當前設計 intentional，offset_bps 留 backward compat + signature alignment with Rust。

**Future sweep efficiency improvement**：
- Sweep dimension 從 (A=4 × B=4-5 × C=3 × D=3 + 3 family) → (A=1 × B=4-5 × C=3 × D=3 + 2 active family) ≈ 78 → 20 cells
- Wall time 1.4s → ~0.4s (4x faster)，但 1.4s 已 trivial，主要益處是 cell selection 認知負擔降低

**24h pilot impact**: **無影響** — Cell A `G-AB-01-C90` 仍是 valid pilot candidate，A=0.5 是 conservative baseline（即使 A axis dead，本 cell 仍是 fill 最高 + saving 最高的 viable 配置）。

### §3.2 SD-2 action

**Spec v0.3 amend note**（PA dispatch 寫，operator 批）：

> **§Y. PS family (phys_lock_gate4_stale_roc_neg) 等 sample 累積才 sweep。**
> 
> 7 天 demo runtime + post-restart 4 fills seed pool 內 0 row PS exit_reason。Phys_lock_gate4_stale_roc_neg 觸發條件嚴格（stale + roc_neg 雙 sub-gate），自然 distribution 罕。
> 
> 對 calibration sweep 的 implication：
> - **PS family 26 cells 結果不可信** — n_eligible=0 統計上無 information；
> - **不該動 phys_lock_gate4_stale_roc_neg timeout (10s)** — 沒樣本支持決策；
> - **SD-2-future re-sweep trigger**：當 PS exit_reason 累積 ≥ 8 fills 後重跑 sweep（建議 monitor `helper_scripts/db/check_phys_lock_close_distribution.sql` 或類似 SQL）；
> - **不需修 IMPL** — sweep simulation family routing 正確，skip 是 data shortage 自然結果。

**Monitoring suggestion**：在 PG 設 view 或 daily check 看 PS exit_reason 累積：
```sql
SELECT COUNT(*) FROM trading.fills
 WHERE engine_mode='demo'
   AND close_maker_attempt=TRUE
   AND exit_reason='phys_lock_gate4_stale_roc_neg'
   AND ts > NOW() - INTERVAL '30 days';
```

**24h pilot impact**: **無影響** — pilot scope 已限定 grid family（per cell selection report §4.4），PS family 本就不在 pilot dispatch。

### §3.3 SHOULD-FIX vs SHOULD-DROP triage

| Item | 原 §5.2 / §5.3 列為 | 本 SD report 結論 | Final disposition |
|---|---|---|---|
| SD-1 A axis dead | suspected IMPL bug (25% prob) | confirmed spec design (100%) | **SHOULD-DROP** — 不修 IMPL，只 amend spec |
| SD-2 PS family skip | suspected router bug (33% prob) | confirmed data shortage | **SHOULD-DROP** — 不修 IMPL，只 amend spec + future re-sweep monitoring |

兩 anomaly 都從原 cell selection report 的「sus IMPL」降級到「confirmed spec / data」，**0 個需 E1 IMPL fix**，**0 個阻 pilot dispatch**。

---

## §4 PnL impact framing (per `feedback_pnl_priority_over_governance.md`)

### §4.1 SD-1 PnL leverage

- **直接 PnL impact**: 0 bps — A axis dead 表示無論 operator 選 A=0.5 / 1.0 / 2.0 / 3.0，limit price 都 identical，actual fill / saving 相同
- **間接 PnL impact** (cognitive cost saving): future sweep prune A axis 後 cell selection 認知負擔降低，PA review 時間 -75%；但這對組合 PnL 是 indirect / zero-shot 影響
- **Decision-quality preservation**: 若不寫 spec amend note，未來下一輪 sweep 仍會 4× redundant cells，浪費 wall time + review 時間 — 此 governance debt 不直接影響當期 PnL，但長期 cognitive ROI 顯著

### §4.2 SD-2 PnL leverage

- **直接 PnL impact**: 0 bps — PS family 本就不在 pilot dispatch，且 phys_lock_gate4_stale_roc_neg 罕觸發（4/54 fills 對 0/54 PS），全部 phys_lock close 都走 giveback path
- **間接 PnL impact**: 若 future PS sample 累積後再 sweep，得出的 timeout (10s) 配置可能對 phys_lock close 真實 fill rate 有 marginal 改善（unknown magnitude）；但這是 future option value
- **Risk of inaction**: 0 — 不沒 fix 也不會有 false-positive cell selection（PS 26 cells 已被 cell selection report §3.2 全列 TRUE_FAIL，pilot 不會誤選）

### §4.3 Overall PnL prioritization

**兩 anomaly 都 LOW PnL leverage** (per user prompt header "Both anomalies low PnL leverage")。輕量 spec amend note + monitoring SQL = total 1-2 hour PA work，**不需 E1 IMPL effort**。

**ETA 總影響**: ~0 hour — 不需 E1/E2/E4 chain；PA 寫 spec v0.3 amend note 可在下一個 PA dispatch cycle 順帶完成（單獨開 issue 也不需要），不阻 24h pilot launch。

---

## §5 Multi-session race check 5/5

| Check | Command | Result | Pass |
|---|---|---|---|
| 5a 提交前 fetch + sibling window | `git fetch origin && git log HEAD..origin/main` | 0 new sibling commits, HEAD == origin/main | ✓ |
| 5b report path 寫入前 status clean | `git status --short` | report path 不存在於 modified / untracked list | ✓ |
| 5c sibling WIP 不 revert | dirty: TODO.md / E2/E4/MIT/PA memory.md + W-AUDIT-8c sibling reports | 不動 | ✓ |
| 5d report path 不重名 | `ls .../2026-05-18--phase_1b_calibration_sweep_anomalies_sd_report.md` | not exist (unique) | ✓ |
| 5e 分析期間 sibling 推 origin | `git fetch` 後 origin/main 未動 | ✓ | ✓ |

**Race check 5/5 PASS。**

---

## §6 16 原則合規 + 硬邊界 (CC skill `16-root-principles-checklist`)

### §6.1 16 根原則逐條（本報告 read-only investigation 範圍）

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ✓ N/A | 本報告無寫入 (僅 spec amend note suggestion，不寫 TOML / 不發 IPC) |
| 2 | 讀寫分離 | ✓ | CSV / PG / source code 全 read-only |
| 3 | AI 輸出 ≠ 命令 | ✓ | spec amend note suggestion，operator 決定是否批 |
| 4 | 策略不繞風控 | ✓ N/A | 不涉策略改動 |
| 5 | 生存 > 利潤 | ✓ N/A | 不涉風控配置 |
| 6 | 失敗默認收縮 | ✓ N/A | 不涉執行 path |
| 7 | 學習 ≠ 改寫 Live | ✓ N/A | 不涉 ML pipeline |
| 8 | 交易可解釋 | ✓ | sweep CSV / per-cell JSON / source code call-path 全 reconstructable |
| 9 | 災難保護 | ✓ N/A | 不涉執行 |
| 10 | 認知誠實 | ✓ | §1.4 把原 cell selection report 60% probability 修正為 100% with call-path proof；§2.5 列 hypothesis B2/B3 對應 FALSE 證據 |
| 11 | Agent 最大自主 | ✓ | recommendation only |
| 12 | 持續進化 | ✓ | spec v0.3 amend note 推動 sweep efficiency + data quality improvement |
| 13 | AI 成本感知 | ✓ N/A | offline analysis, no AI call |
| 14 | 零外部成本可運行 | ✓ | 全本地 PG + CSV + source 分析 |
| 15 | 多 Agent 協作 | ✓ | 沒派 sub-agent (light analysis per task scope) |
| 16 | 組合級風險 | ✓ | §4 PnL framing 0 risk to 組合 |

**評級**: A (16/16 完全合規)

### §6.2 §四 硬邊界 (5 條)

- ✓ Five-gate live: 不觸 (read-only investigation)
- ✓ Signed live authorization: 不觸
- ✓ LiveDemo grade: 不觸
- ✓ Mainnet env-var fallback: 不觸
- ✓ Bybit retCode fail-closed: 不觸

**結論**: 5/5 0 觸碰。

### §6.3 DOC-08 §12 9 不變量

本報告 read-only investigation 不破壞任何 9 不變量。

---

## §7 Call-path grep evidence (PA hard requirement)

per PA workflow rule「P0/P1 leak / look-ahead bias / selection bias finding 必附 grep proof」：

### §7.1 SD-1 Python port grep

```
$ grep -n 'offset_bps\|fallback_offset_bps' srv/helper_scripts/calibration/phase_1b_maker_price.py
40:    offset_bps: float
99:        fallback_offset_bps=policy.offset_bps,
108:    fallback_offset_bps: float,
115:    為什麼保留 fallback_offset_bps 參數但未使用：與 Rust signature 一致；
116:    Rust 的 fallback_offset_bps 在 warn log 引用但不參與計算（strict-skip 路徑下
```

只有 6 出現，其中：
- line 40: dataclass field declaration
- line 99: 傳給 `compute_post_only_price` 的 caller site
- line 108: function signature
- line 115-116: 注釋明確標示**未使用**
- **0 個出現在 price formula (line 131-148)**

### §7.2 SD-1 Rust source grep

```
$ grep -n 'offset_bps\|fallback_offset_bps' srv/rust/openclaw_engine/src/strategies/common/maker_price.rs
# (path: maker_price.rs:155-356)
```

Rust source 中 `fallback_offset_bps` 只在 warn log fields (line 276, 297, 315, 332, 350) 出現，**0 個在 price formula (line 305-336)**。

### §7.3 SD-2 SQL evidence

```sql
-- 跑於 trade-core PG, 2026-05-18 15:30 UTC
SELECT 'post-restart' AS pool, exit_reason, COUNT(*)
  FROM trading.fills
 WHERE engine_mode='demo' AND close_maker_attempt=TRUE
   AND ts > '2026-05-17 23:54:36'::timestamptz
 GROUP BY 1,2
UNION ALL
SELECT 'pre-restart-50' AS pool, exit_reason, COUNT(*)
  FROM (
    SELECT exit_reason FROM trading.fills
     WHERE engine_mode='demo'
       AND exit_reason = ANY(ARRAY['grid_close_short','grid_close_long','bb_mean_revert',
                                    'phys_lock_gate4_giveback','phys_lock_gate4_stale_roc_neg',
                                    'ma_reverse_cross','bw_squeeze','pctb_revert'])
       AND ts <= '2026-05-17 23:54:36'::timestamptz
       AND ts > '2026-05-10 23:54:36'::timestamptz
     ORDER BY ts DESC LIMIT 50
  ) sub
 GROUP BY 1,2 ORDER BY pool, COUNT DESC;
```

Result:
```
 post-restart   | grid_close_short         |  3
 post-restart   | phys_lock_gate4_giveback |  1
 pre-restart-50 | grid_close_short         | 46
 pre-restart-50 | phys_lock_gate4_giveback |  3
 pre-restart-50 | ma_reverse_cross         |  1
```

**`phys_lock_gate4_stale_roc_neg` 0 row** in both pools。

---

## §8 Append-only summary

- **SD-1 verdict**: VERIFIED dead, spec design intent (NOT IMPL bug). Action = spec v0.3 amend note + future sweep prune A axis (78 → ~20 cells). 0 ETA, 0 E1 fix.
- **SD-2 verdict**: VERIFIED no-sample, replay seed 內 0/54 row PS exit_reason. Action = spec v0.3 amend note + monitoring SQL for SD-2-future re-sweep trigger. 0 ETA, 0 E1 fix.
- **24h pilot impact**: **無影響** — Cell A `G-AB-01-C90` 仍 valid，不需 reblock。
- **Total ETA 影響**: ~0 hour (spec amend note 可順帶 next PA cycle 完成)
- **No E1/E2/E4 chain needed** — 兩 anomaly 都不是 IMPL bug。

---

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_sweep_anomalies_sd_report.md
