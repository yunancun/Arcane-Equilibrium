# W-AUDIT-8a C1-LIQ-WRITER — [67] Healthcheck Amend Report

**Date**: 2026-05-18
**Author**: E1
**Branch**: `feature/w-audit-8a-c1-liq-writer-impl`
**Base**: `7ab6c22d` → Amend `d8938a78`
**Task**: E1 IMPL [67] healthcheck for PA decomposition §6.3 acceptance #3 closure
(E2 + MIT cross-finding: original IMPL missed mandated healthcheck delivery).

## 任務摘要

PA §6.3 acceptance #3 強制要求：

> "New healthcheck [67]+ covers topic freshness + row volume + parse errors + symbol coverage"

原 C1-LIQ-WRITER IMPL（commit 7ab6c22d）落 Rust provider + IPC slot + AlphaSurface
wire-up 但**未交付** [67] healthcheck script。PM 決定 same-PR amend，派 E1
background 補上 healthcheck（Python + tests）。

## 修改清單

### 新檔
| 檔案 | LOC | 描述 |
|---|---|---|
| `helper_scripts/canary/healthchecks/67_liquidation_pulse_freshness.py` | 354 | Standalone CLI healthcheck for `market.liquidations`；4-維度（freshness / row volume / cohort coverage / parse guard）；reuses `_common.py`；hardcoded 25-sym COHORT_SYMBOLS aligned with `rust/openclaw_engine/src/main.rs` DEFAULT_COHORT |
| `helper_scripts/canary/healthchecks/tests/test_67_pulse_freshness.py` | 320 | pytest 16 tests；reuses `conftest.fake_cursor_factory`；covers all-green / per-dim 3-ladder / severity_max integration / SQL param shape / cohort sanity |

### 修改
| 檔案 | 變更 |
|---|---|
| `helper_scripts/SCRIPT_INDEX.md` | 新增 `[67]` 條目 + tests count 44→60 |

### Commit
- `d8938a78` on `feature/w-audit-8a-c1-liq-writer-impl` (pushed to origin)

## 關鍵設計選擇

### 1. 單一 [67] vs 拆 [67]+[68]
PA 寫「1-2 個 script」，選單一 [67] 整合 4 維。

**理由**：V095 `chk_market_liquidations_side_v095` CHECK constraint 已在 INSERT
階段 fail-closed bad parse（side ∉ {'Buy', 'Sell'} 寫入失敗），DB 內存在的 row
= 全部 parse PASS。`parse_errors` 真正可監測的 proxy = side enum coverage +
qty/price finite ratio，這與 row context 不可分離；強拆 [68] 會變成「query DB
然後驗證 V095 constraint 自身」= meaningless tautology。

整合做法：parse_guard 成為 [67] 的第四維度，與 freshness/volume/coverage 共享
SQL probe + verdict 合併。

### 2. Cohort 25-sym hardcoded
與 `rust/openclaw_engine/src/main.rs` DEFAULT_COHORT 對齊：

```python
COHORT_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", ..., "INJUSDT",  # 25 sym
)
```

POLUSDT 取代 MATICUSDT（per Bybit V5 status=Closed since 2024-09-06）。
W1 IMPL 階段 dynamic cohort deferred to W-AUDIT-8c phase（per
`panel_aggregator/funding_curve.rs` 同 pattern）。

### 3. Per-hour rate ladder
window-secs 可變（CLI `--window-secs`），volume ladder normalize 成 per-hour rate
（default 30 row/hr PASS）；24h vs 8h 共用閾值。

```python
hours = window_secs / 3600.0
pass_lower_total = pass_lower_per_hour * hours
warn_lower_total = pass_lower_total * 0.5  # 折半 WARN
```

### 4. Cohort coverage 用 SQL-filter 後 distinct
Non-cohort symbol（BSBUSDT/HYPEUSDT 等）也會被 Bybit 推到 `market.liquidations`
但 `LiquidationPulseAggregator` silent ignored；coverage 分子用 cohort ∩ observed，
不用 raw distinct（避免 non-cohort overflow 給虛高分子）。

```sql
SELECT DISTINCT symbol
FROM market.liquidations
WHERE ts > NOW() - (%s::int * INTERVAL '1 second')
  AND symbol = ANY(%s::text[])   -- cohort filter
```

## Verdict 規則

四維度各自 verdict，整體取 severity_max；任一 FAIL → overall FAIL。

| 維度 | PASS | WARN | FAIL |
|---|---|---|---|
| Freshness | ≤ 60s | 60-300s | > 300s |
| Row volume | ≥ pass_lower × hours | warn_lower ≤ n < pass_lower | < warn_lower (折半) |
| Symbol coverage | ≥ 80% | 50-80% | < 50% |
| Parse guard | Buy & Sell ≥ 1, non_finite=0 | — | side absent OR non_finite > 0 |

`severity_max` 嚴重度: PASS=0 < INSUFFICIENT_SAMPLE=1 < WARN=2 < FAIL=3。

## Linux PG empirical（2026-05-18 24h window）

```
metric: liquidation_pulse_freshness
check_id: [67]
window_secs: 86400
cohort_size: 25
n_rows: 6134
latest_age_secs: 14.52
buy_count: 5711
sell_count: 423
non_finite_count: 0
cohort_observed: 25
cohort_coverage_pct: 100.0
missing_cohort_symbols: []

dimensions:
  freshness:        PASS (latest_age=15s)
  row_volume:       PASS (n_rows=6134 >= pass_lower=720)
  symbol_coverage:  PASS (coverage=100.00% (25/25))
  parse_guard:      PASS (side enum complete (Buy=5711, Sell=423); all qty/price > 0)

verdict: PASS
```

**1h window self-validation**：coverage=28% (7/25) → FAIL — 正確 semantic（短窗
under-cover cohort；24h 是 C1 v2 proof doctrine 的標準 sample unit）。這證明
script 不會 false-PASS 短窗 sparse data。

## Test 驗證

```
Mac:
  $ python3 -m pytest helper_scripts/canary/healthchecks/tests/ -v
  16 new + 44 existing = 60 passed in 0.02s

Linux PG empirical:
  $ python3 67_liquidation_pulse_freshness.py --window-secs 86400 --text
  verdict: PASS
```

16 個 [67] 測試覆蓋：
- 全綠 path（all 4 dims PASS）
- Freshness 3-ladder（warn / fail / none-zero-rows insufficient）
- Volume 3-ladder（pass exact / warn middle / fail below warn）
- Coverage 3-ladder（warn / fail / cohort-only exclude non-cohort）
- Parse guard 3 fail paths（Buy absent / Sell absent / non-finite）
- severity_max integration（FAIL overrides WARN）
- SQL param shape（window_secs + cohort list）
- Cohort sanity（25 sym, POLUSDT subst MATICUSDT）

## 治理對照

| 項目 | 結果 |
|---|---|
| PA §6.3 acceptance #3 mandate「topic freshness + row volume + parse errors + symbol coverage」 | 4 維全覆蓋（parse_errors 整合入 parse_guard） |
| 預期 Linux PG empirical = PASS | **達成（24h 全綠）** |
| Mac + Linux pytest 全綠 | 60/60 PASS（無 regression） |
| SCRIPT_INDEX 更新 | 達成（[67] 條目 + tests count 44→60） |
| 不動 Rust / TOML / migrations | 達成（純 Python + Markdown） |
| Branch hygiene | 只 push c1-liq-writer branch，未動 main |
| Bilingual-comment-style chinese-first | 達成（新 module / function 中文 MODULE_NOTE + 中文注釋；技術詞英文保留） |
| 不擴大 PA 範圍 | 達成（acceptance #3 完整覆蓋，無額外 feature） |
| Isolated worktree 避 multi-session race | 達成（用 `/tmp/e1-c1-liq-writer-wt` 隔離） |

## 不確定之處 / 風險

### 1. WARN threshold tuning
本次選 freshness WARN=60s / FAIL=300s 是 PA prompt 建議；實際 baseline empirical
24h latest_age=14.52s（遠低於 60s），threshold 寬裕。若 future Bybit WS lag
增加，可能需要從 alert noise 反向調整 — 視 deploy 後 1-2 週實際分布決定。

### 2. Parse error proxy 局限
本 check 在 DB-side 監測「parser silent degradation」（Buy/Sell 半邊瞎 / qty/price
non-finite），但無法捕捉 row 不應該寫但被寫的情況（false positive parse）—
這需要 ws_client / market_writer 層的 telemetry，超出 healthcheck script 範圍。

### 3. 非 cohort symbol coverage 不被計入
24h Linux 觀察到 32 distinct symbols（BSBUSDT/HYPEUSDT/EDENUSDT 等非 cohort）；
coverage 只算 25-sym cohort，這些非 cohort 流量是 raw market data 被寫但
aggregator silent ignored — 正確行為，但 LR/dashboard 可能想看 raw distinct
作為「Bybit WS 推送廣度」指標。本 check 不包含 raw distinct，留 future 加新
script 或加 dimension（PA 未要求）。

### 4. 沒做（per mandate + 邊界）
- 沒動 Rust / TOML / migrations
- 沒派下游 sub-agent（單 agent + background）
- 沒做 E4 regression（branch ready for E4，但那是 E4 mandate）
- 沒清 sibling branch 殘留（ADR-0023 / B-REM-5 不是本 worktree 範圍）

## Operator 下一步

1. **E4 Linux regression** on `feature/w-audit-8a-c1-liq-writer-impl@d8938a78`
   - cargo workspace test（既有 7ab6c22d 已驗 2986/0/1 + openclaw_core 438/0；
     本 amend 純 Python + Markdown，cargo 不受影響）
   - Python pytest（60/60 PASS 已 Mac + Linux 雙跑驗）
2. **QA Audit** — 驗 acceptance #3 closure（4 維度都覆蓋；Linux PG empirical PASS）
3. **PM merge to main**（per E1 完成序列禁直接 commit main；branch 等審查鏈走完）

E1 IMPLEMENTATION DONE: 待 E4 regression + QA Audit + PM merge（report path:
`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8a_c1_liq_writer_healthcheck_67_amend.md`）
