# Counterfactual Replay Audit — v2 `ExitConfig` (base / slope / floor) Calibration Spec
# 反事實回放審計 — v2 `ExitConfig`（base / slope / floor）三參數校準規範

**Spec 寫入時間 / Written**：2026-04-22
**最早可執行時間 / Earliest execution**：2026-04-29（v2 runtime ≥ 7d from 2026-04-22 20:55 CEST `--rebuild`）
**執行位置 / Execution host**：Linux `trade-core`（Mac 無法 — 需 PG 直連 + 大量 1-min bar replay）
**觸發 TODO**：TRACK-P Phase 2 軌道 1「counterfactual replay audit」未打勾項
**狀態 / Status**：SPEC ONLY · NOT CODE · NOT COMMITTED BY THIS SESSION

---

## 0. Quickstart（給未來 operator / sub-agent 的 TL;DR）

1. **§11 schema prerequisite**：`\d trading.fills` + `\d trading.klines_1m` + fee/order_type NULL 率 + klines freshness — 任一 block → 不得進 Step 2。
2. 確認 `trading.fills WHERE engine_mode='demo' AND ts_ms >= 1776884100000 AND exit_reason LIKE 'risk_close:phys_lock_gate4_%'` ≥ **100 rows**（§8 Step 1）；不夠延後到 2026-05-06。
3. 擴展 `program_code/audit/counterfactual_exit_audit.py`：加 `--mode {single-v1, grid-v2}` flag + `ExitConfigV2` dataclass + `simulate_phys_lock_v2()`（§2 擴展點 / §8 Step 3）— **不改原 v1 `PhysLockConfig` 與 `simulate_phys_lock()`**。
4. **v1 fee regression check**（§3.5）：先用新 per-fill fee source 重跑 v1，對帳 `2026-04-19` 歷史基準 ±10%，不 pass 不得進 v2 grid。
5. 跑 v2 grid-v2 掃描（§3，110 tuple + Wilcoxon + 10% hold-out seed=42），寫 `/tmp/openclaw/counterfactual_v2_grid_search_<YYYYMMDD>.{json,md}`。
6. 按 §7.0 **四條 gate（A hard guards + B significance + C effect size + D hold-out）** 判決；**兩條設計意圖必驗**：(i) 追求最高單筆 close 盈利（right_tail + total PnL 不得稀釋） (ii) 防微利即套離場（lock_count 與持倉時長分布不得極端飄移）。
7. Promote（四條全過）：改 `exit_features/v2.rs::ExitConfig::Default` seed → `cargo test -p openclaw_engine --lib` → `ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"` → §8 Step 6 跑 `v2_swap_24h_observation.sh` 觀察 24h。

---

## 1. 背景 / Context

### 1.1 為何需要 / Why

2026-04-22 20:55 CEST `--rebuild` 部署 `TRACK-P-V2-SWAP-1`（commit `306993e`），engine PID **158918** 起 Priority 6（`risk_checks::check_position_on_tick`）由 v1 線性 `physical_micro_profit_lock` + `PhysLockConfig`（固定 `giveback_atr_norm_threshold=0.7`）切為 v2 非線性 `exit_features::physical_micro_profit_lock_v2` + `ExitConfig`：

```text
threshold(peak_atr_norm) = max(giveback_base − giveback_slope × peak_atr_norm, giveback_floor)
```

v2 種子值 **從未經過實證校準**（直接照 designer doc §三 落預設）：

| Parameter        | Default seed | Source                                    |
|------------------|--------------|-------------------------------------------|
| `giveback_base`  | `1.0`        | designer doc seed                         |
| `giveback_slope` | `0.15`       | designer doc seed                         |
| `giveback_floor` | `0.3`        | designer doc seed                         |

v2 runtime 24h 觀察不足以決定三參數是否最優 — 需要 7 天 demo fills + 逐倉位 tick/1-min bar replay 才能 grid search 出資料驅動的 tuple。

### 1.2 前置條件 / Preconditions

- v2 runtime **已連續存活 ≥ 7d**（2026-04-22 20:55 起，最早 2026-04-29 20:55 CEST）
- **無中途 `--rebuild` 改 `exit_features/v2.rs`**（允許機械 refactor / log 字串變更 / 其他模組動；禁動 `ExitConfig` / `physical_micro_profit_lock_v2` / `non_linear_giveback_fn` 邏輯）
- `trading.fills` demo `exit_reason LIKE 'risk_close:phys_lock_gate4_%'` 累積 **≥ 100 rows**（否則 grid search 易過擬合，延後）
- `trading.klines_1m`（或等價 `market.klines` 視現況 schema）freshness ≤ 24h；陳舊 → fallback fills-only 報告（delta 不可算，audit 不是空跑但失效）

### 1.3 非目標 / Out of scope — 這份 audit **不做** 下列事

- **不** 調整 v1 `PhysLockConfig` — v1 pure fn 已於 `306993e` 退役，沒有任何 runtime 走 v1
- **不** 改 Gate 1 (`min_net_floor_bps=5.0`) / Gate 2 (`min_hold_secs=30`) / Gate 3 (`min_peak_atr_norm=0.5`) 閾值；這三個 gate 是 design §三 硬語意，**只校準 Gate 4a 三參數**
- **不** 改 Gate 4b (`stale_peak_ms=60_000`) — 是時間語意 gate，與非線性 giveback 正交
- **不** 跨 engine_mode 混 — 本輪 audit 僅跑 `engine_mode='demo'`（per memory `feedback_demo_over_paper_for_edge.md`）；live/live_demo 資料體量還不夠
- **不** 綁 ConfigStore 熱重載 — 目前 `ExitConfig` 走 `RiskConfig.exit` + ArcSwap，`--rebuild` 即生效，不需 hot-reload 改動
- **不** 動下游 `parse_exit_tag` / `strip_phys_lock_prefix` — reason string ABI（`phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`）凍結不動

---

## 2. 輸入資料 / Inputs

### 2.1 PostgreSQL 資料

**連線**：env var `PG_HOST/PG_PORT/PG_DB/PG_USER/PG_PASSWORD`（與 `counterfactual_exit_audit.py:_get_db_conn()` 一致），或 `~/.pgpass`。

**`trading.fills` 取樣**：
```sql
-- 7d demo phys-lock closes（v2 deploy 之後）
-- start_ms = 1776884100000 為 2026-04-22 20:55 UTC（v2-swap --rebuild 時點近似）
SELECT strategy_name, symbol, ts, price, qty, side, realized_pnl, context_id, entry_context_id
FROM trading.fills
WHERE engine_mode = 'demo'
  AND ts_ms >= :start_ms
  AND ts_ms <  :end_ms          -- :start_ms + 7 * 86400 * 1000
ORDER BY symbol, ts
```

**entry 配對**：既有 `pair_fills_to_positions()` 邏輯已處理（§1 bybit_sync shadow-path skip 亦沿用）。**不改 pairing 邏輯。**

### 2.2 Kline bars

**來源**：`trading.klines_1m`（若 repo 當前改名請以 schema 實況為準）。查法：
```sql
SELECT ts, open, high, low, close
FROM trading.klines_1m
WHERE engine_mode = 'demo'
  AND symbol     = :sym
  AND ts_ms BETWEEN :entry_ms AND :exit_ms
ORDER BY ts
```
chunk by symbol；若 position 跨 > 1d 建議 batch 200 position 一次拉。

**Kline staleness guard**：既有 `_KLINE_STALE_THRESHOLD_SECS = 24 * 3600` 直接沿用；v2 audit **不改** 陳舊守衛門檻；陳舊 → per-position `phys_reason="klines_stale_fallback"` 填入新 `AuditRecordV2.phys_reason` 即可。

### 2.3 現有工具 / Existing tooling — **Reuse, 不從零寫**

`program_code/audit/counterfactual_exit_audit.py` 於 2026-04-19 已跑過 v1 grid search（141/4 hits mean −39.4 bps · ma 52/10 hits mean −95.2 bps，詳 `docs/worklogs/2026-04-19-2--track_p_counterfactual_audit.md`）。**v2 擴展點**（spec 描述、**本次任務不寫 code**）：

#### 2.3.1 v1 結構盤點（為擴展定位）

| Symbol | Type | Location | v2 要動嗎 |
|---|---|---|---|
| `PhysLockConfig`（6 field: min_net_floor_bps / min_hold_secs / min_peak_atr_norm / giveback_atr_threshold / stale_peak_ms / atr_fallback_pct） | dataclass | L84-L94 | **不動**；新加 v2 sibling |
| `simulate_phys_lock(position, bars, cfg: PhysLockConfig)` | fn | L337-L425 | **不動**；新加 v2 sibling |
| `Position` / `KlineBar` / `PhysLockDecision` / `AuditRecord` | dataclass | L97-L149 | **不動**；v2 復用 Position/KlineBar，新加 `PhysLockDecisionV2`/`AuditRecordV2` sibling 或 optional `cfg_variant: str` field |
| `pair_fills_to_positions()` / `compute_peak()` / `compute_atr_pct()` / `_get_db_conn()` / `_is_exit_fill()` | helpers | 多處 | **全部 reuse 不動** |
| `audit_position()` | fn | L445+ | 新加 `audit_position_v2()` sibling 呼叫 `simulate_phys_lock_v2()` |
| `main()` CLI | entrypoint | 末段 | 加 `--mode {v1,v2}` flag，default v1 保回溯相容；grid search 另起新 CLI（§2.3.3） |

#### 2.3.2 v2 擴展點（Python 反射 Rust `exit_features/v2.rs` 語意）

```python
# NEW: 於 counterfactual_exit_audit.py 新增（不改 v1 PhysLockConfig）
@dataclass
class ExitConfigV2:
    # 鏡像 Rust ExitConfig.default() — seed 必須與 exit_features/v2.rs::default_*() 完全一致
    min_net_floor_bps: float = 5.0
    min_hold_secs: float = 30.0
    min_peak_atr_norm: float = 0.5
    stale_peak_ms: int = 60_000
    giveback_base: float = 1.0         # ← grid search axis
    giveback_slope: float = 0.15       # ← grid search axis
    giveback_floor: float = 0.3        # ← grid search axis
    atr_fallback_pct: float = 1.0      # 沿用 v1 fallback（Rust 側讓 Gate 3 Hold，Python 為可算 peak_atr_norm 必須填）

    def validate(self) -> None:
        # 鏡像 Rust ExitConfig::validate()
        if self.giveback_floor > self.giveback_base:
            raise ValueError("giveback_floor must be <= giveback_base")
        # （其他 validate 同 Rust：finite / 非負 / >0）

def non_linear_giveback_threshold(peak_atr_norm: float, cfg: ExitConfigV2) -> float:
    # 鏡像 Rust non_linear_giveback_fn
    norm = peak_atr_norm if (peak_atr_norm == peak_atr_norm and peak_atr_norm >= 0.0) else 0.0
    return max(cfg.giveback_base - cfg.giveback_slope * norm, cfg.giveback_floor)

def simulate_phys_lock_v2(position, bars, cfg: ExitConfigV2, *, fee_rate_bps: float = 10.0) -> PhysLockDecisionV2:
    # 與 v1 simulate_phys_lock 99% 相同；**唯一差異**：Gate 4a 用
    #   giveback_atr_norm >= non_linear_giveback_threshold(peak_atr_norm, cfg)
    # 而不是 `>= cfg.giveback_atr_threshold`
    # Gate 1/2/3/4b 全部照抄 v1 邏輯（含 prev_close ROC 計法）
    ...
```

**Sanity check**：擴展完成後，設 `giveback_base=0.7, slope=0.0, floor=0.7`（把非線性退化成 v1 線性 0.7）跑同一筆 fills，結果必須 **bit-exact** 等於 v1 `simulate_phys_lock`。這是擴展正確性的 smoke test。

#### 2.3.3 新 CLI（spec，不實作）

```text
python -m program_code.audit.counterfactual_v2_grid_search \
    --days 7 --engine-mode demo \
    --start-ts 2026-04-22T20:55:00Z \
    --out-json /tmp/openclaw/counterfactual_v2_grid_search_20260429.json \
    --out-md   /tmp/openclaw/counterfactual_v2_grid_search_20260429.md \
    --fee-rate-bps 10.0
```

或直接 extend 既有 `counterfactual_exit_audit.py` 加 `--grid-mode` flag + tuple iteration loop（選一；sub-agent 酌情）。

---

## 3. 校準 Grid / Grid search space

### 3.1 Cartesian product（原始 120 tuples）

| Axis            | Values                                    | Count |
|-----------------|-------------------------------------------|-------|
| `giveback_base` | `{0.7, 0.85, 1.0, 1.15, 1.3, 1.5}`        | 6     |
| `giveback_slope`| `{0.05, 0.10, 0.15, 0.20, 0.25}`          | 5     |
| `giveback_floor`| `{0.2, 0.3, 0.4, 0.5}`                    | 4     |

**範圍設計理由 / Why these ranges**：
- `base` 以 default 1.0 為中心 ±50%；下界 0.7 對應 v1 固定值 0.7（對照基準）；上界 1.5 覆蓋「shallow peak 也要 1.5 ATR 回吐才鎖」的保守端
- `slope` 下界 0.05 ≈「幾乎線性」、上界 0.25 對應「threshold 在 peak_atr_norm=3 時近乎觸 floor」
- `floor` 下界 0.2 對應「高 peak 時允許更大 giveback 才鎖」；上界 0.5 對應「保守快鎖」

### 3.2 Pruning rules

**硬剔除**：任何 `floor > base` 的 tuple（由 Rust `ExitConfig::validate()` 拒絕）— 實剩 ~110 tuple。
實測 pruning：`6 × 5 × 4 = 120`，其中 floor=0.4 排除 base ∈ {0.2}（無）、floor=0.5 排除 base=0.7/0.85 以下（無因 base ≥ 0.7）— 實際剔除僅 {base=0.7 × floor ∈ {0.4 最邊界 OK, 0.5 排除}}、{base=0.85 × floor=0.5 OK}、無嚴格 > 違反 ... 實務計算 = 120 tuple 基本全收；如 pruning 為 0 則保留 120 rows，不再強求 ~110。

### 3.3 其他固定參數（所有 tuple 共用）

```
min_net_floor_bps = 5.0
min_hold_secs     = 30.0
min_peak_atr_norm = 0.5
stale_peak_ms     = 60_000
atr_fallback_pct  = 1.0
```

### 3.4 Fee source — **不 hardcode，per-fill 實 fee**（2026-04-22 panel 修正）

舊版 spec 曾假設單一 `fee_rate_bps=10.0` scalar — 已作廢。原因：EDGE-P2-3 PostOnly（2026-04-21 20:44 部署）後 `grid_trading` / `ma_crossover` / `bb_breakout` 三策略於 demo 走 maker-entry path，runtime fee 由 `intent_processor::fee_rate_for_intent` 按 `order_type`（maker/taker）routing。固定 10 bps 會把 PostOnly 效果抹平，違反 counterfactual 對齊 runtime 的基本前提。

**Fee source 優先級**（`simulate_phys_lock_v2()` 新增參數 `fee_bps_per_fill: Optional[float] = None`）：

1. **優先（A）**：`trading.fills.fee_usdt` / `trading.fills.fee_rate` per-fill 實 fee（每筆 replay 帶自己的實 fee）— **需先跑 §11 schema prerequisite 確認欄位存在**
2. **Fallback（B）**：兩層 tier 按 `trading.fills.order_type` 分：`PostOnly/maker = 1 bps`、`taker = 5 bps`，round-trip 乘 2（入場 + 出場兩側）
3. **禁用（C）**：single scalar `fee_rate_bps` — 只在 `ExitConfigV2` unit test / mock fixture 允許

### 3.5 Fee sanity regression check（v1 回歸）

在跑 v2 grid 前，**必須先用新 fee source 重跑一次 v1 `simulate_phys_lock`**（既有 `PhysLockConfig` default），與 `docs/worklogs/2026-04-19-2--track_p_counterfactual_audit.md` 的歷史結果對帳：

| 歷史基準（fee_rate_bps=10 scalar） | 本輪重跑（per-fill fee） | 判定 |
|---|---|---|
| grid: 141 hits, mean **−39.4 bps** | grid: N hits, mean **X bps** | \|ΔX\| ≤ 4 bps（±10%）才信 fee source 正確 |
| ma: 52 hits, mean **−95.2 bps** | ma: N hits, mean **Y bps** | \|ΔY\| ≤ 9.5 bps（±10%）同上 |

**不 pass 不得進 v2 grid**。差異若 > 10% 代表：(1) fee source 欄位抓錯，(2) PostOnly 部署 revenue 實質改變 fee 分布（需先 operator 確認這是期望中的改變，而非 data bug）。

---

## 4. 評估指標 / Evaluation metrics

對每個 tuple（120 rows 中的一 row）計算以下 metric，輸出到 JSON + markdown summary：

| Metric                              | 定義 / Definition                                                           | 單位 |
|-------------------------------------|-----------------------------------------------------------------------------|------|
| `total_cf_pnl_usdt`                 | 所有 position 的 counterfactual close PnL 總和（簽名 USDT）                 | USDT |
| `mean_per_rt_bps`                   | 每 round-trip 平均 PnL                                                      | bps  |
| `median_per_rt_bps`                 | 每 round-trip PnL 中位數                                                    | bps  |
| `lock_count_4a`                     | Gate 4a giveback 觸發次數                                                   | int  |
| `lock_count_4b`                     | Gate 4b stale_roc_neg 觸發次數                                              | int  |
| `no_lock_count`                     | 走到 exit 都未觸發（fall-through real exit）                                | int  |
| `hold_secs_median`                  | cf exit − entry 的 holding time 中位數                                      | sec  |
| `hold_secs_p90`                     | 同上 90 百分位                                                              | sec  |
| `hold_secs_max`                     | 同上 max                                                                    | sec  |
| `right_tail_concentration`          | top-10% positions 的 cf PnL 總和 ÷ 全 position cf PnL 總和                  | 比例 |
| `delta_vs_real_bps_mean`            | (cf − real) × 10000 / real_abs 平均（與 v1 audit 一致 reporting）           | bps  |
| `cfg_variant`                       | `{"base": X, "slope": Y, "floor": Z}`                                       | dict |

**Right-tail concentration < 0.5** 是健康訊號（收益不集中在少數尾端）。**> 0.85** 代表 tuple 過度偏向長 hold 型少數大贏家 — flag 為 overfit 風險。

---

## 5. Ranking 與 pick 策略 / Ranking

**Primary sort key**：`total_cf_pnl_usdt` 降序（我們要 **絕對 PnL 最大化** 而非平均 — design §三 意圖「追求最高單筆 close 盈利」）。

**Tie-breaker**（差距 < 1% primary 視為 tie）：`mean_per_rt_bps` 降序。

**Second tie-breaker**：`no_lock_count` 降序（越多 fall-through 越接近 design 意圖「讓 position 跑完」）。

**Sanity guards（reject tuple，退回 default）**：
- `(lock_count_4a + lock_count_4b) < 10` → 觸發太少，over-fit 風險
- `hold_secs_median > 200 × 30` = 6000s（~100 min）→ 幾乎不鎖，退回意義失效
- `right_tail_concentration > 0.85` → 收益過度集中單一 outlier

**若 all tuples 觸 sanity guard** → 保留 default seed，audit 結論 = "inconclusive, hold default"。

---

## 6. 執行環境 / Execution env

| 項目 | 值 |
|---|---|
| Host | Linux `trade-core`（SSH via `ssh trade-core`）|
| Python | `~/.venv`（lightgbm / onnx / psycopg2 已裝）|
| Repo | `~/BybitOpenClaw/srv`（`git pull --ff-only origin main` 先同步）|
| DB creds | `~/.pgpass` or env `PG_*`（operator 配）|
| 資料範圍 | 起點 `2026-04-22T20:55:00Z` → +7d（最早 2026-04-29T20:55:00Z 後）|
| 輸出 | `/tmp/openclaw/counterfactual_v2_grid_search_<YYYYMMDD>.json` + `.md` summary |
| 運行時長估算 | 120 tuples × ~500 positions × ~1440 1-min bar replay ≈ **15–30 min**（single core；psycopg2 batch 拉 klines 主導 I/O）|
| 記憶體 | < 2 GB（positions + bars 全載入記憶體 OK）|
| 網路 | 無外部 — 只 PG localhost |

**Mac 不可執行理由**：psycopg2 連 PG 走 Linux localhost；`trading.klines_1m` 只在 Linux trade-core；資料量 > 1 GB 不宜透過 scp。Mac CC 作法為 `ssh trade-core "python -m program_code.audit.counterfactual_v2_grid_search ..."` 遠程觸發。

---

## 7. Go/No-Go 決策 / Promotion decision

**（2026-04-22 panel 修正 — 取代原「≥ 15% single threshold」四條 gate）**

核心原則：**設計意圖（§三 L108-111）有兩條，缺一不可驗**：
1. **「追求最高單筆 close 盈利」**（right-tail + total PnL 必須 ≥ default，不得因鎖得太早而喪失大贏家）
2. **「防微利即套離場」**（Gate 1 Hold + 4a non-linear threshold 讓淺 peak 不亂鎖；lock_count 與持倉時長分布不得偏離合理區間）

### 7.0 Four-condition gate（必須全中才能 Promote）

**Gate A — Hard sanity guards（既有 §5 reject rule 升級為必要條件）**：
- `lock_count_4a + lock_count_4b ∈ [0.8×, 1.5×]` × default_lock_count（驗「防微利即套」不過度觸發）
- `hold_secs_median ∈ [0.5×, 2×]` × default_hold_median（驗持倉時長未極端飄移）
- `right_tail_concentration ≥ 0.85 × default_right_tail`（驗「追求最高單筆 close 盈利」未被稀釋）

**Gate B — Statistical significance（multiple testing correction）**：
對 paired-fill counterfactual delta（best tuple 每 fill PnL − default tuple 每 fill PnL）跑 **Wilcoxon signed-rank test**，Bonferroni-corrected：
- `p < 0.05 / 110 ≈ 4.5e-4`（對 110 tuple 做 correction）
- 避免 120 tuple 掃描下 best tuple 為 lucky winner

**Gate C — Effect size**（兩條 OR，任一 trigger 即可）：
- `Winsorized (cap ±5000 bps) total_cf_pnl_usdt 改善 ≥ 8%`（從 15% 降，並用 P1-17 同 Winsorize 閾值去尾）
- `mean_per_rt_bps 改善 ≥ 5 bps`

**Gate D — Hold-out validation（防過擬合）**：
- Random 10% fills 預留 **不入 grid search**（隨機 seed 固定 `42` 保可重現）
- Best tuple 在 hold-out set 重算 `total_cf_pnl_usdt`，應顯示 **≥ 50% of in-sample improvement**
- 若 hold-out improvement < 50% of in-sample → treat as overfit → Hold

### 7.1 判決矩陣

| Gate 通過狀態 | Action |
|---|---|
| A+B+C+D 全過 | **Promote** — 按 §7.2 部署流程 |
| A 過但 B/C/D 任一不過 | **Hold** — 保持 default，寫 summary worklog，下輪（14d）重跑 |
| A 不過（lock_count / hold_time / right_tail 任一飄出） | **Reject audit** — 不動 config，flag 資料品質（klines stale? fills pairing gap? fee source 錯？）raise issue |

### 7.2 Promote 部署流程

**15% 門檻**（TBD by operator）— 本 spec 取 15%，operator 保留調整權；太低會把 noise 當 signal、太高會浪費校準機會。

1. 編輯 `rust/openclaw_engine/src/exit_features/v2.rs` 下列 3 fn 的 return 值：
   - `fn default_giveback_base() -> f64 { <new> }`
   - `fn default_giveback_slope() -> f64 { <new> }`
   - `fn default_giveback_floor() -> f64 { <new> }`
   - **不改** `ExitConfig` struct 本身 / `Default impl` 結構 / validate 邏輯
2. Rust test：`cd rust && cargo test -p openclaw_engine --lib`（預期 1835 passed / 0 failed — TRACK-P-V2-SWAP-1 基準）
3. 特別跑 `exit_features::v2::tests::test_exit_config_default_validates`（Test 17）確認新預設值仍通過 validate（對照 §三 doc seed spot-check 那幾行 assert 會要同步更新）
4. 寫 commit + worklog + `docs/CLAUDE_CHANGELOG.md` entry（TRACK-P-V2-CALIBRATE-1 或類似 tag）
5. `git push origin main`
6. `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only && bash helper_scripts/restart_all.sh --rebuild"`
7. 24h 觀察（§8 Step 5）

---

## 8. 驗證步驟 / Verification steps（shell one-liner 友善貼上）

> 依 memory `feedback_shell_paste_safety.md`：所有指令單行；heredoc / 多行 for 絕對禁止；遠端命令用 `ssh trade-core "..."` 包；引號注入按 `'\''` 模式。

### Step 1 — 確認 7d 資料量足夠

```bash
ssh trade-core 'psql -d trading_ai -tAc "SELECT COUNT(*) FROM trading.fills WHERE engine_mode='\''demo'\'' AND ts_ms >= 1776884100000 AND exit_reason LIKE '\''risk_close:phys_lock_gate4_%'\'';"'
```

**判讀**：`< 100` → 延 1 週再跑；`100-500` → 可跑但標註 low-n；`> 500` → confidence 高。

### Step 2 — 拉最新 repo + 確認 v2 未被改動

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && git log --oneline -1 -- rust/openclaw_engine/src/exit_features/v2.rs"
```

**判讀**：最近改動 commit 若 ≠ `306993e` 或 `aee96b9` 或 hotfix `d0f0c21`，打住 — 邏輯可能已被動，spec assumption 失效，先 RCA。

### Step 3 — 跑 counterfactual v2 grid search

**（2026-04-22 panel 決定：延伸既有 `counterfactual_exit_audit.py` 加 `--mode` flag，不新檔）**

CLI 固定：`python -m program_code.audit.counterfactual_exit_audit --mode grid-v2 ...`

`--mode` 取值：
- `single-v1`（既有 default 行為，向後相容）— 跑 v1 `PhysLockConfig` 單一 config
- `grid-v2`（新增）— 跑 v2 `ExitConfigV2` 110 tuple grid + Wilcoxon + hold-out

**E2 必查**：`argparse` sub-command 結構 + v1 single-mode 回歸測試不破（既有 `counterfactual_exit_audit.py::tests::test_phys_lock_rule_on_synthetic_fixture_locks_expected` 仍綠）。

**3a — v1 fee regression check（§3.5 前置）**：

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && source ~/.venv/bin/activate && python -m program_code.audit.counterfactual_exit_audit --mode single-v1 --days 7 --engine-mode demo --start-ts 2026-04-22T20:55:00Z --fee-source per-fill --out /tmp/openclaw/v1_fee_regression_$(date +%Y%m%d).json"
```

比對 `/tmp/openclaw/v1_fee_regression_*.json` 與 `docs/worklogs/2026-04-19-2--track_p_counterfactual_audit.md` 基準（grid −39.4 bps / ma −95.2 bps ±10%）。**不 pass 不得進 Step 3b**。

**3b — v2 grid-v2 主掃描**：

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && source ~/.venv/bin/activate && python -m program_code.audit.counterfactual_exit_audit --mode grid-v2 --days 7 --engine-mode demo --start-ts 2026-04-22T20:55:00Z --fee-source per-fill --holdout-pct 10 --holdout-seed 42 --out-json /tmp/openclaw/counterfactual_v2_grid_search_$(date +%Y%m%d).json --out-md /tmp/openclaw/counterfactual_v2_grid_search_$(date +%Y%m%d).md"
```

`--fee-source` 取值：
- `per-fill`（default，§3.4 A 層，最精確）
- `tier`（§3.4 B 層 fallback — PostOnly=1 bps / taker=5 bps 按 `order_type`）
- `scalar:<bps>`（§3.4 C 層 禁用，只供 unit test）

### JSON schema（output artifact 固化）

`counterfactual_v2_grid_search_*.json` 每 tuple 一 row：

```jsonc
{
  "base": 1.0, "slope": 0.15, "floor": 0.3,       // tuple identity
  "total_pnl_usdt": 12.34, "total_pnl_winsorized_usdt": 11.87,   // Gate C
  "mean_per_rt_bps": -8.2, "median_per_rt_bps": -3.1,            // Gate C alt
  "lock_count_4a": 42, "lock_count_4b": 8, "no_lock_count": 97,  // Gate A
  "hold_secs_p50": 180, "hold_secs_p90": 720, "hold_secs_max": 3600,  // Gate A
  "right_tail_concentration": 0.62,                                   // Gate A
  "wilcoxon_p_value": 0.0003,                                          // Gate B
  "holdout_in_sample_total_pnl_usdt": 11.12,                           // Gate D
  "holdout_out_sample_total_pnl_usdt": 6.78,                           // Gate D
  "holdout_ratio": 0.61,                                                // Gate D (≥ 0.5 要求)
  "passes_gate_a": true, "passes_gate_b": true,
  "passes_gate_c": true, "passes_gate_d": true,
  "overall_verdict": "Promote"  // or "Hold" | "Reject"
}
```

### Step 4 — Read summary

```bash
ssh trade-core "tail -n 200 /tmp/openclaw/counterfactual_v2_grid_search_$(date +%Y%m%d).md"
```

或 scp 回 Mac：`scp trade-core:/tmp/openclaw/counterfactual_v2_grid_search_$(date +%Y%m%d).md ~/Downloads/`。

### Step 5 — Go/No-Go

按 §7.0 四條 gate 判決：
- **Promote (A+B+C+D 全過)** → 按 §7.2 編 `exit_features/v2.rs` → commit → push → `ssh trade-core "... && bash helper_scripts/restart_all.sh --rebuild"`
- **Hold (A 過 B/C/D 任一不過)** → 寫 summary worklog `docs/worklogs/YYYY-MM-DD--counterfactual_v2_audit_result.md` 記錄判決理由 → commit → push；14d 後重跑
- **Reject (A 不過)** → 不動 config，raise issue 調查資料品質（klines stale / fills pairing / fee source）

### Step 6 — Post-calibration 24h 觀察（Promote 路徑才做）

```bash
ssh trade-core "nohup bash ~/BybitOpenClaw/srv/helper_scripts/v2_swap_24h_observation.sh > /tmp/openclaw/v2_swap_24h_observation_post_calib.log 2>&1 & disown"
```

24h 後 tail log 確認 (1) PID 穩定 (2) phys_lock_gate4_* fire 分布 (3) fills total PnL 方向與 audit prediction 一致 (± 20%)。

---

## 9. 風險與退路 / Risks & fallbacks

| 風險 | 偵測 | 退路 |
|---|---|---|
| 7d 資料不足（< 100 phys_lock fills） | Step 1 COUNT(*) | 延 7-14d；若系統整體交易頻率太低，發 issue 反思 strategy pacing |
| Grid 結果過擬合 demo，live_demo 表現不符 | Step 5 後對照 live_demo `exit_reason` 分布 | 同 tuple 跑 `--engine-mode live_demo` 對照；差異 > 30% 不 promote |
| v2 `ExitConfig` 三參數高度相關（base/slope/floor 同方向影響） | grid heat-map visual | Fallback 1D search：鎖 slope=0.15/floor=0.3，只掃 base ∈ 6 值（從 6 tuple 選最優，風險較低但信息量少）|
| Klines stale > 24h | `_KLINE_STALE_THRESHOLD_SECS` guard | 每 position 標 `klines_stale_fallback` 不 replay；若 > 30% position 陳舊 → RCA 掃描器 / kline writer 健康 |
| cf replay 的 1-min bar 粒度平滑掉 intra-bar spike | 既知 — `counterfactual_exit_audit.py` MODULE_NOTE 已明示為「改進下界」 | Accept — 本 audit 得出的是 lower bound，真實 runtime 會因 tick 粒度觸發更多 4a lock；promote 判斷保留 margin of safety |
| audit 結果與 v2 runtime 實際分布不一致（calibration artefact） | promote 後 24h fills `phys_lock_*` 分布對照 | rollback tuple；寫 RCA；下輪 audit 同步重評 fee rate / ATR 計法 |

---

## 10. 關聯 / References

- `CLAUDE.md` §三 2026-04-22 milestone（TRACK-P-V2-SWAP-1 + TICK-PIPELINE-MOD-SPLIT-1）
- `docs/CLAUDE_CHANGELOG.md` — TRACK-P-V2-SWAP-1 entry（commit `306993e` · 2026-04-22）
- `docs/worklogs/2026-04-19-2--track_p_counterfactual_audit.md` — v1 counterfactual 歷史（141/4 · 52/10 · mean bps 實測）
- `docs/worklogs/2026-04-18--dual_track_exit_design.md` + `2026-04-18-1--dual_track_exit_feasibility.md` — 設計起源
- `program_code/audit/counterfactual_exit_audit.py` — reuse 基礎（L84 PhysLockConfig · L337 simulate_phys_lock）
- `rust/openclaw_engine/src/exit_features/v2.rs` — `ExitConfig` 定義 + `non_linear_giveback_fn` + 25 單測（pure-fn fixture）
- Memory `project_track_p_runtime_live.md` — runtime 啟用狀態敘事
- Memory `feedback_demo_over_paper_for_edge.md` — demo fills 為 edge analysis 唯一合法源
- Memory `feedback_shell_paste_safety.md` — §8 shell 寫法約束
- Memory `feedback_env_config_independence.md` — 三環境 risk_config 獨立；**本 audit 只動 Rust Default seed（全環境共用 Default），不動 TOML 覆寫**

---

## 11. 前置 schema 驗證 / Schema prerequisite check（2026-04-22 panel 新增）

§3.4 per-fill fee source 依賴 `trading.fills` 欄位；§3.1 replay 依賴 `trading.fills` 與 `trading.klines_1m` join。**執行 §8 Step 1 之前必須跑本節 Step 0a–0d**，確認欄位存在且 NULL 率可接受。

### Step 0a — `trading.fills` schema

```bash
ssh trade-core 'psql -d trading_ai -c "\d trading.fills"'
```

**必須存在欄位**（預期清單，missing 任一 → block audit）：
- `ts_ms BIGINT NOT NULL`（replay 時序）
- `engine_mode TEXT NOT NULL`（filter demo）
- `symbol TEXT NOT NULL`
- `exit_reason TEXT`（filter `risk_close:phys_lock_%`）
- `entry_context_id TEXT`（pair positions）
- **`fee_usdt NUMERIC` OR `fee_rate NUMERIC`**（§3.4 A 層必要；兩者至少有一個）
- **`order_type TEXT`**（§3.4 B 層 fallback 必要；PostOnly/maker/taker 區分）
- `realized_pnl_usdt NUMERIC`（total PnL baseline）

### Step 0b — Fee 欄位 NULL 率

```bash
ssh trade-core 'psql -d trading_ai -tAc "SELECT COUNT(*) FILTER (WHERE fee_usdt IS NULL)::float / NULLIF(COUNT(*),0) AS fee_null_rate, COUNT(*) FILTER (WHERE order_type IS NULL)::float / NULLIF(COUNT(*),0) AS order_type_null_rate FROM trading.fills WHERE engine_mode='\''demo'\'' AND ts_ms >= 1776884100000;"'
```

**判讀**：
- `fee_null_rate > 0.05` → A 層不可用，退 B 層（tier by `order_type`）
- `order_type_null_rate > 0.05` → B 層也不可用，**block audit**（RCA fills writer 缺欄位接線）
- 兩者 ≤ 0.05 → A 層 per-fill fee 可用，進 §8 Step 1

### Step 0c — `trading.klines_1m` schema

```bash
ssh trade-core 'psql -d trading_ai -c "\d trading.klines_1m" | head -20'
```

**必須存在欄位**：`ts_ms` / `symbol` / `engine_mode` / `open` / `high` / `low` / `close`。

**判讀**：任一 missing → block audit（schema drift，開 RCA）。

### Step 0d — Klines freshness

```bash
ssh trade-core 'psql -d trading_ai -tAc "SELECT symbol, MAX(ts_ms) AS latest_ms, (EXTRACT(EPOCH FROM NOW())*1000 - MAX(ts_ms))/1000 AS stale_secs FROM trading.klines_1m WHERE engine_mode='\''demo'\'' GROUP BY symbol ORDER BY stale_secs DESC LIMIT 10;"'
```

**判讀**：任一 symbol `stale_secs > 86400`（24h）→ 該 symbol 所有 position 走 `klines_stale_fallback` 路徑；若 > 30% symbol 陳舊則 block audit。

### 觸發 block 時處置

- fee/order_type NULL rate 高：RCA `fills writer`（Rust `fill_engine.rs`）是否漏接欄位；修完後重跑 §8 Step 1
- klines schema drift：grep 最新 migration 與 §10 reference 版本對比，若有改動先同步 spec 再跑 audit
- klines staleness：檢查 `MARKET-KLINES-STALE-1`（`65acde6`）相關看板，確保三引擎 market_data_tx 並行 writer 在跑

---

## Appendix A — `ExitConfig` seed / Rust `exit_features/v2.rs` 對照卡

```rust
// rust/openclaw_engine/src/exit_features/v2.rs
fn default_min_net_floor_bps() -> f64 { 5.0 }        // Gate 1（不改）
fn default_min_hold_secs()     -> f64 { 30.0 }       // Gate 2（不改）
fn default_min_peak_atr_norm() -> f64 { 0.5 }        // Gate 3（不改）
fn default_stale_peak_ms()     -> i64 { 60_000 }     // Gate 4b（不改）
fn default_giveback_base()     -> f64 { 1.0 }        // Gate 4a ← grid search axis
fn default_giveback_slope()    -> f64 { 0.15 }       // Gate 4a ← grid search axis
fn default_giveback_floor()    -> f64 { 0.3 }        // Gate 4a ← grid search axis
```

**Promote 時 edit 範圍**：只動 **後 3 行 fn body 的 literal**。不動 struct / impl / validate / non_linear_giveback_fn。

---

## Appendix B — Non-linear giveback threshold 直觀表（default seed）

| `peak_atr_norm` | `threshold = max(1.0 − 0.15·x, 0.3)` |
|-----------------|--------------------------------------|
| 0.0             | 1.0                                  |
| 0.5             | 0.925                                |
| 1.0             | 0.85                                 |
| 2.0             | 0.7                                  |
| 3.0             | 0.55                                 |
| 4.0             | 0.4                                  |
| 4.67            | 0.3（floor kicks in）                |
| 10.0            | 0.3（clamped to floor）              |

- 與 v1 固定 0.7 對照：v1 相當於 v2 在 `peak_atr_norm=2.0` 的點值；v1 shallow peak（norm < 2）偏鬆 → v2 偏緊；v1 high peak（norm > 2）偏緊 → v2 偏鬆（這正是 design §三 意圖）。
- Grid search 的 `base` 移動整條曲線的截距、`slope` 移動斜率、`floor` 決定何時「拉平」— 三者交互作用，避免 1D search 漏掉 Pareto front。

---

## Appendix C — 並行 sub-audit：ma_crossover `trailing_distance_pct` sensitivity（2026-04-22 新增）

**動機**：P1-10 下一步 (2) ma_crossover SL/TP audit（`docs/worklogs/2026-04-22--p1_10_ma_crossover_sl_tp_audit.md`）發現 demo `trailing_distance_pct=3.5` 相對 ma_crossover 典型 move size（ATR ~1-1.5%）過寬，假設為 2026-04-20 R1 win rate 64%→37.8% 崩潰主因。該參數屬 `risk_checks.rs` trailing stop 邏輯，**與 `ExitConfig` v2 non-linear giveback 正交**。

**範圍隔離**：
- 主 audit（§1-§11）：`ExitConfig` 三參數 `base/slope/floor` grid search，**不動 trailing**
- Sub-audit（本 Appendix）：trailing_distance_pct 單參數 scan，**不動 ExitConfig**
- 兩者共用 7d demo replay 資料集（§2.1）但 simulate fn 分離：主用 `simulate_phys_lock_v2()`，sub 用新 `simulate_trailing_stop()` 呼 既有 `risk_checks::check_position_on_tick` 的 trailing 分支

**Axis**：`trailing_distance_pct ∈ {2.0, 2.5, 3.0, 3.5}`（4 值 · 含當前 demo=3.5 baseline + 對齊 live/paper 的 2.0 + 中間點）

**其他固定**（所有 4 值共用，取 demo TOML 現值）：
```
trailing_activation_pct = 0.8
trailing_min_rr         = 0.3
stop_loss_max_pct       = 25.0
base_ratio              = 0.4
cap_ratio               = 0.85
atr_stop_mult           = 2.0
```

**評估**：
- `ma_crossover_win_rate`（pnl > 0 ÷ total exits）— 主 signal，看是否從 37.8% 回升
- `mean_per_rt_usdt` · `median_per_rt_usdt` — 是否犧牲平均收益換取勝率
- `trailing_stop_trigger_count` vs `strategy_close:ma_reverse_cross` count — 比較兩條 exit path 的相對觸發率
- `asym_ratio`（|mean_loss| / mean_win）— 與 2026-04-20 R1 baseline 0.88 比較

**判決 gate**：類同主 audit §7.0 的 A/B/C/D 四條 — 但縮小 scope 至 ma_crossover · demo 單策略單 engine_mode，Bonferroni correction α=0.05/4=0.0125。

**執行時點**：與主 audit 同 session（2026-04-29+），可於主 audit 跑完 grid 後併行 sub-audit scan；~~不~~ 作為主 audit 的前置（互相獨立）。

**Non-goal**：
- 不調 `trailing_activation_pct`（單 axis 保純淨）
- 不跨策略（ma_crossover only）
- 不改 live/paper TOML（只驗 demo）

**資料驅動的前提**：主 audit 確認 v2 `ExitConfig` 三參數穩定後，再獨立驗 trailing scan — 避免兩者交互作用污染結論。若主 audit 結論先改了 `ExitConfig`，sub-audit 需 rebaseline 後重跑。

---

**EOF — spec 完成，未執行。實際 audit 最早 2026-04-29 進行。**
