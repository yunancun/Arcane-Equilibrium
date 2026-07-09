# E1 Round 2 Fix — P2-SIM-QUEUE-AWARE-ADJUSTMENT v55

**日期**：2026-05-20
**任務 ID**：P2-SIM-QUEUE-AWARE-ADJUSTMENT v55 Round 2（E2 review pushback）
**狀態**：Round 2 IMPL DONE — 待 PM 派 E4 / 或 E2 confirm

## §1 任務摘要

E2 PR review (`2026-05-20--p2_sim_queue_aware_e2_review.md`) verdict =
APPROVE-CONDITIONAL pass to E4，但退回 2 MEDIUM SHOULD-FIX（不阻 E4，
阻 v55 production interpretation 階段對 phys_lock family 結論 cite）。

本 round 只修這 2 MEDIUM，未擴 scope，未動 SIM model 核心邏輯，
未動 4 LOW NTH（留作未來 round）。

## §2 修改清單

| 檔案 | 狀態 | 主要改動 |
|---|---|---|
| `helper_scripts/calibration/phase_1b_queue_adjustment.py` | MOD (+12 LOC) | `DEFAULT_BASE_REJECTION_RATE` source comment 補 family-specific 警告塊 |
| `helper_scripts/calibration/phase_1b_queue_bias_regression.py` | MOD (+85 LOC) | (1) argparse 加 `--sample-end-utc` (2) `load_v094_attempts` 加 param + 5-tuple return (3) SQL `ts > NOW() - interval` → 顯式 `BETWEEN` (4) `print_results` 加 disclaimer block + window display (5) JSON artifact 新增 6 欄 |

LOC：phase_1b_queue_adjustment 221 / phase_1b_queue_bias_regression 572；
均 < 800 LOC 警告線，0 觸 2000 LOC 硬上限。

## §3 修法詳細

### §3.1 MEDIUM-1 — family-specific anchor cell disclosure

E2 建議 B+C，E1 採 **B+C 全做（即選項 C）**：

#### §3.1.a Source-level disclosure（選項 A 補強）

`phase_1b_queue_adjustment.py` line 60 `DEFAULT_BASE_REJECTION_RATE = 0.0`
前補 11 行 family-specific 警告 comment：

```python
# ⚠️ FAMILY-SPECIFIC 警告（per E2 review MEDIUM-1, 2026-05-20）：
# `base_rejection_rate` 是 **family-specific empirical anchor 參數**，不是物理常數。
# 適用範圍：每個 strategy family（grid / phys_lock_giveback / phys_lock_stale_roc_neg ...）
# 必須各自用對應 anchor cell（如 G-AB-01-C90 / PG-AB-01-C15 / PS-AB-01-C10）跑
# regression 校自家 base_rejection；不可直接外推。
# 為什麼：不同 family 的 PostOnly path / cancel race / fallback timing 不同
# 造成 non-queue fail mode 分布不同；single value 對全 family 套用會錯估 bias。
# 當前 source 維持 default=0.0 不 hardcode 任一 family 的 calibrated value；
# regression CLI 透過 `--base-rejection` 顯式 inject + JSON artifact 記錄
# anchor cell family，避免結論被誤外推。
```

意圖：未來任何讀 `phase_1b_queue_adjustment.py` 的開發者看到 `DEFAULT_BASE_REJECTION_RATE`
時，會被警告 base_rejection 不是「全家族共通常數」而是 family-specific 校驗值。

#### §3.1.b Regression CLI disclaimer block（選項 B）

`phase_1b_queue_bias_regression.py:print_results()` 結尾加 `[DISCLAIMER]` 段：

```
[DISCLAIMER — per E2 review MEDIUM-1, 2026-05-20]
  本 regression base_rejection=0.70 是針對 anchor cell `G-AB-01-C90` (family=`grid`)
  以 14d V094 sample n=18 校的 family-specific anchor。
  不應外推到其他 family（phys_lock_giveback / phys_lock_stale_roc_neg ...）；
  非 grid family 需各自用對應 anchor cell（如 PG-AB-01-C15 / PS-AB-01-C10）
  重跑此 regression CLI 校自家 base_rejection 值。
  Sample window 已 pin 至 [...UTC, ...UTC]，可 bit-exact 重現。
```

意圖：跑 regression CLI 的人 看完 verdict 立即看到適用範圍限制，
不會因 verdict=PASS 誤推「v55 sweep 結論對所有 family 都有效」。

#### §3.1.c JSON artifact 新增欄位

```json
{
  "cell": {...},
  "anchor_family": "grid",
  "anchor_disclaimer": "base_rejection=0.70 is family-specific empirical anchor calibrated on cell 'G-AB-01-C90' (family='grid', n=18, lookback=14d). DO NOT extrapolate to other families ...",
  ...
}
```

意圖：JSON artifact 永久 trail 紀錄 anchor cell family；
下游 sweep_report / production cell selection 階段不易誤外推。

#### §3.1.d argparse help text

`--base-rejection` help text 加：「⚠️ family-specific anchor — 結論限 anchor cell 對應 family」

### §3.2 MEDIUM-2 — sliding 14d window 重現性

#### §3.2.a argparse 加 `--sample-end-utc`

```bash
--sample-end-utc SAMPLE_END_UTC
    Pin sample window END timestamp (UTC ISO-8601, e.g.
    '2026-05-20T03:00:00+00:00'). Default = now() (sliding).
    顯式 pass 對齊 audit 時刻可 bit-exact 重現（per E2 MEDIUM-2, 2026-05-20）。
```

支援格式：
- ISO 8601 + tz：`'2026-05-20T03:00:00+00:00'`
- ISO 8601 + `Z` suffix：`'2026-05-20T03:00:00Z'`
- ISO 8601 naive：`'2026-05-20T03:00:00'`（無 tz 視為 UTC）
- `'now'` / `''` / `None` → 回 None（fallback now()）
- 無效字串 → `ValueError`，argparse 報錯

#### §3.2.b `load_v094_attempts` signature 改

```python
# Before
def load_v094_attempts(conn, lookback_days=14) -> tuple[list[FillReplaySeed], int, int]:
    # ...
    cur.execute("... WHERE ts > NOW() - %s::interval", (..., f"{lookback_days} days"))

# After
def load_v094_attempts(
    conn,
    lookback_days=14,
    sample_end_utc: Optional[datetime] = None,
) -> tuple[list[FillReplaySeed], int, int, datetime, datetime]:
    if sample_end_utc is None:
        window_end = datetime.now(timezone.utc)
    else:
        # tz coerce + UTC convert
        if sample_end_utc.tzinfo is None:
            window_end = sample_end_utc.replace(tzinfo=timezone.utc)
        else:
            window_end = sample_end_utc.astimezone(timezone.utc)
    window_start = window_end - timedelta(days=lookback_days)
    # ...
    cur.execute("... WHERE ts >= %s AND ts <= %s", (..., window_start, window_end))
    # ...
    return seeds, actual_maker, actual_taker, window_start, window_end
```

關鍵設計決策：
- **Python 側 resolve window 邊界**：JSON artifact 與 SQL 邊界必須一致；
  若用 PG `NOW()`，artifact 記錄與實際查詢時刻可能差 ms，破壞 deterministic 重現。
- **顯式 `BETWEEN` 取代 `>` interval**：可 bit-exact 重現任一 audit 時刻。
- **default=None 向後相容**：未 pass 時退回 `now()`，舊 CLI invocation 不破。

#### §3.2.c JSON artifact 新增 4 欄

```json
{
  ...
  "sample_end_utc": "2026-05-20T03:00:00+00:00",  # CLI 顯式傳入；未傳=null
  "sample_window_start_utc": "2026-05-06T03:00:00+00:00",  # 永遠紀錄
  "sample_window_end_utc": "2026-05-20T03:00:00+00:00",     # 永遠紀錄
  "sample_window_pinned": true,                              # 是否 audit-quality pinned
  ...
}
```

#### §3.2.d print_results 顯示 window

`print_results` header 加：
```
Sample window UTC  : [2026-05-06T03:00:00+00:00, 2026-05-20T03:00:00+00:00]
Lookback days      : 14
```

讓 stdout 觀察者立即看到 sample 邊界。

### §3.3 MODULE_NOTE 同步更新

`phase_1b_queue_bias_regression.py` 模塊頂部 docstring 加 disclaimer block：

```
⚠️ 適用範圍 disclaimers（per E2 review 2026-05-20）：
  - MEDIUM-1: `base_rejection_rate` 是 **family-specific empirical anchor** — ...
  - MEDIUM-2: 預設 `--sample-end-utc=now()` 是 sliding window，每次跑會抓不同 sample；
    audit 時刻對齊請顯式 pass ...
```

## §4 治理對照

| Item | 對照 |
|---|---|
| CLAUDE.md §四 hard boundary | max_retries / live_execution_allowed / execution_authority / system_mode 0 觸碰 ✓ |
| §七 code rules — 注釋默認中文 | disclaimer / comment 純中文（保留 ISO-8601 / SQL 技術詞）✓ |
| §七 — 800/2000 LOC | 兩檔分別 221 / 572 LOC，遠低於 800 警告 ✓ |
| §八 workflow | Round 2 修完待 E2 confirm 或 PM 派 E4；不直接 commit / push ✓ |
| §十 TODO maintenance | 不擴 4 LOW NTH scope；未動 SIM model 核心邏輯 ✓ |
| cross-platform | grep 0 `/home/ncyu` / `/Users/...` 硬編碼 ✓ |
| no except:pass | grep 0 命中 ✓ |
| backward compat | `load_v094_attempts` default `None` 退回 now()；既有 caller 已同步更新 ✓ |

## §5 test 結果

```
======================== test session starts =========================
collected 89 items

helper_scripts/calibration/tests/test_phase_1b_maker_price.py     20 PASS
helper_scripts/calibration/tests/test_phase_1b_queue_adjustment.py 22 PASS
helper_scripts/calibration/tests/test_phase_1b_sweep_cells.py     17 PASS
helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py    13 PASS
helper_scripts/calibration/tests/test_phase_1b_sweep_report.py    17 PASS

======================== 89 passed in 0.04s ==========================
```

**89/89 PASS** — Round 1 baseline 不破。

額外手動驗 `_parse_sample_end_utc` helper：
- `None` / `''` / `'now'` / `'NOW'` → `None` ✓
- `'2026-05-20T03:00:00+00:00'` → tz-aware UTC ✓
- `'2026-05-20T03:00:00Z'` → tz-aware UTC ✓
- `'2026-05-20T03:00:00'` (naive) → 假設 UTC ✓
- `'2026-05-20T11:00:00+08:00'` → 自動 convert UTC = `03:00:00+00:00` ✓
- `'not-a-date'` → `ValueError` ✓

## §6 不確定 / 已知 trade-offs

1. **未動 SIM model 核心邏輯**：per task brief 邊界，本 round 只動 disclosure +
   重現性參數，不改 `apply_queue_adjustment` / `compute_queue_factor` 公式。

2. **未動 4 LOW NTH**：
   - queue depth timing alignment（§1.7c）
   - f-string DSN
   - `--sweep-params` hardcode tuple
   - `_qty_for_diagnostic` O(n) scan
   留作 P2/P3 follow-up。

3. **load_v094_attempts signature 改動 backward compat**：
   - 5-tuple return 是 breaking change
   - grep verify 唯一 caller = `main()` 同檔內，已同步更新
   - 0 外部 import（grep `phase_1b_queue_bias_regression` 0 外部 hits）
   - 不破壞 multi-session race

4. **disclaimer 用中文**：per `feedback_chinese_only_comments` 默認；
   `anchor_disclaimer` JSON 欄用英文（便於 downstream tool parse / log search）。

## §7 Operator 下一步

1. **不直接 commit**（per PA brief：等 E2 confirm / E4 regression / PM 統一處理）
2. **E2 可選 confirm**：
   - source comment family-specific 警告塊
   - print_results disclaimer block 內容
   - JSON artifact `anchor_family` + `anchor_disclaimer` 欄位
   - `--sample-end-utc` argparse + `BETWEEN` SQL + 4 JSON 欄
3. **E4 regression**：
   - 跑 `pytest helper_scripts/calibration/tests/` 確認 89/89 PASS
   - 跑 `phase_1b_sweep_cli.py --smoke-test` 確認 backward compat（無 queue path）
   - 跑 `phase_1b_queue_bias_regression.py --sample-end-utc 2026-05-20T03:00:00+00:00
     --queue-weight 0.10 --base-rejection 0.70 --json-out X.json` 確認 pinned
     window bit-exact 重現
4. **PM v55 production deploy**：
   - v55 sweep `(queue_w=0.10, base=0.70)` 跑 81 cells 時，必須明確 disclose 結論
     僅適用 grid family；phys_lock 兩 family 需 future round 各自跑 anchor regression

## §8 Race Check 5/5

| Check | Result |
|---|---|
| 5a 提交前 fetch + sibling commits 檢查 | `git status --short helper_scripts/calibration/` 與 Round 1 IMPL 一致；無外洩檔 |
| 5b sub-agent IMPL DONE 前 status clean | 只動 2 untracked file（Round 1 新建）；3 modified file 不動 |
| 5c sibling WIP 不 revert | 0 動既有 dirty file |
| 5d report path 不重名 | `2026-05-20--p2_sim_queue_aware_round2_fix.md` 唯一 |
| 5e 分析期間 sibling 推 origin | N/A（pure Mac local edit） |

Race check 5/5 PASS。

---

E1 IMPLEMENTATION DONE: 待 E2 confirm 或 PM 派 E4（report path:
`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-20--p2_sim_queue_aware_round2_fix.md`）
