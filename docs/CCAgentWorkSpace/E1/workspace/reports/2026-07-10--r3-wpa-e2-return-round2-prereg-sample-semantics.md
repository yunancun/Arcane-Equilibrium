# R3 WP-A E2 RETURN 修復輪 2 — outcome_review 樣本語義對齊 QC 預註冊 §2/§3

**日期**:2026-07-10  **角色**:E1(修復輪 2)  **狀態**:IMPLEMENTATION DONE,待 E2 複審
**E2 finding**:P1 — v4 n_eff 統計語義與 QC 預註冊正本不一致,F1 近似複製通道仍開(合成攻擊實證:30 個同分鐘 distinct-ms 全同值 row → 偽候選 / p=0.0 / bh_fdr_pass=True)。
**判準正本**:`docs/research/2026-07-10--counterfactual_rerun_preregistration.md` §2/§3(§0.3 明確映射 charter WP-A.1)。

## 任務摘要

E2 最小修復集逐條落地(①②③ + regression 測試),並補齊 finding 敘述中點名的 §2.2/§2.3 語義(不平均、複本一致性):

| # | E2 要求 | 實作 |
|---|---|---|
| ① | 去重鍵分鐘量化(至少 (cell, horizon, entry_minute)) | `_entry_group_key` → `(entry_ts_ms // 60_000, horizon_minutes)`;缺 ts → unknown 桶不入樣本 |
| ② | eligibility 增 E2 distinct-days≥5 / E3 top-day≤50% | `_sample_eligibility_failure_reason`(E1 floor→E2 days→E3 share→entry 身分完整性);cfg 新欄 `min_distinct_entry_utc_days=5`、`max_top_entry_day_share_pct=50.0`(預註冊凍結值)+ CLI args |
| ③ | 非重疊窗 n_eff(選了強版,day 統計欄也一併輸出) | §2.6 greedy earliest-first;混 horizon cell 用「上一入選窗關閉」判準(比 per-horizon 各自 greedy 更保守);day 統計欄 `distinct_entry_utc_days`/`entry_day_counts`/`top_entry_utc_day`/`top_entry_day_share_pct` 全輸出 |
| 補 | §2.2 不平均 + §2.3 複本一致性 | 代表行 = attempt_id 字典序最小;複本 realized_net/gross 超 1e-9 容差或 None/值混雜 → cell `DATA_INTEGRITY_SUSPECT`,排除出檢定 family |
| 補 | §4 V=0 | 非重疊樣本 σ=0(n_eff≥2)→ 零變異數 dedup-escape 疑點,同判 `DATA_INTEGRITY_SUSPECT`,不給 p |
| 補 | §5.1 family 定義 | `_apply_bh_fdr` family 限 `bh_family_eligible`(eligibility 全過 + 非 suspect/legacy/observation-gap)cells |
| 測 | 「近似複製不得成候選」regression | 7 條新測試(見下) |

schema v4 → **v5**(v4 毫秒鍵 artifact 已證有近似複製通道,schema-gated 消費端 fail-closed 拒收)。

## 修改清單

- `helper_scripts/research/cost_gate_learning_lane/outcome_review.py`(1503 行):核心修復(上表)。連帶:`_wrongful_block_score` 增 `sample_eligibility_ok` 門(day-fail cell score=0,不得佔排序榜首);`would_pass_optimistic` / `conservative_tail_would_clear_thresholds` 鏡像同一 eligibility;新診斷 `DATA_INTEGRITY_SUSPECT`;packet 新增 `blocked_signal_distinct_entry_observation_count` / `..._window_overlap_excluded_entry_count` / `..._entry_ts_missing_row_count` / `data_integrity_suspect_side_cell_count`;`duplicate_outcome_row_count` 語義修正為「去重壓縮副本數」。
- `helper_scripts/research/cost_gate_learning_lane/sealed_horizon_learning_evidence.py`(819 行):E2/E3 pass-through(`min_review_distinct_entry_utc_days` / `max_review_top_entry_day_share_pct`,默認凍結值)× 2 處 review_cfg + argparse。
- `helper_scripts/research/tests/test_cost_gate_evidence_methodology.py`:新增 7 條 F1 regression(near-replication 同分鐘 distinct-ms 單日 / 單日 episode E2 攔 / top-day 60% E3 攔 / 非重疊窗折半 / 複本不一致 / 零變異數 / 缺 ts 阻立案);既有 fixture 改跨日分散 + 對稱擾動(全同值會撞 V=0 疑點——這本身是修復生效的證據)。
- `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`:候選 fixture 改 6 日 × 5 entry/1h;v4→v5 斷言 ×3;三處同日 3-entry fixture cfg 顯式放 day 欄(該組測 BH 撤下/分流語義,eligibility 本體由 methodology 組默認值直測)。
- `helper_scripts/research/tests/test_cost_gate_sealed_horizon_learning_evidence.py`:單 outcome fixture cfg 顯式放 day 欄。

## 關鍵自測證據(可重跑)

1. **E2 合成攻擊親跑**(scratchpad `attack_ledger.jsonl`,30 row、entry_ts_ms 各異 `base+i*997`、全同值 +25bps、單日):
   `python3 helper_scripts/research/cost_gate_learning_lane/outcome_review.py --ledger attack_ledger.jsonl --print-json`
   → `schema v5;cell status=COLLECT_MORE;distinct_entry_observation_count=1;n_eff=1;p=None;bh=None;candidate_count=0`(v4 為候選/p=0.0/BH pass)。
2. `pytest helper_scripts/research/tests/` → **1570 passed, 1 failed, 4 skipped**;唯一紅 = `test_cli_missing_optional_sealed_evidence_fails_closed_to_packet`(pre-existing 牆鐘 time-bomb,兩檔 `git status` 乾淨未觸,修復輪 1 報告已記錄)。
3. 消費端:`pytest helper_scripts/db/audit/test_demo_learning_evidence_audit.py helper_scripts/cron/tests/` → **252 passed**。
4. `git diff --check` PASS;無硬編碼機器路徑;無 SQL/runtime/order/Cost Gate 面。

## 治理對照

- Cost Gate 不降級(review-only artifact,order_authority=NOT_GRANTED / promotion_evidence=false 不變);fail-closed 全方向收緊(unknown ts 不入樣本、疑點 cell 不給 p、family 收窄)。
- 門檻值 = 預註冊凍結值為默認,測試放寬僅在顯式 cfg(與既有 `min_effective_entries_per_side_cell` 模式一致)。

## 不確定之處 / 偏差聲明(小決策)

1. **混 horizon cell 的 greedy**:prereg 以 (cell,horizon) 為 family 單位;lane cell 行 pooled-horizon 是既有結構,本輪未拆(拆 = artifact 按 cell×horizon 重 key,消費端連鎖改動,超最小修復集)。取保守解:pooled greedy 用「上一入選窗關閉」判準,跨 horizon 路徑重疊一併消除(n_eff ≤ per-horizon greedy 之和)。
2. **lane t 檢定仍 IID**(prereg §4 cluster-SE by day 未實作):不在 E2 最小修復集;非重疊化已消窗內自相關,日級相依由 E2/E3 day 門約束。§4 完整實作屬 WP-A.4 rerun 管線。若 QC 認定 lane-review 也須 cluster-SE,按 prereg §10 走分層裁決。
3. **V=0 疑點以 cell 級 IID σ 實作**(prereg §4 寫在 cluster V 上):判定方向相同且更早攔截,fail-closed 等價。
4. **缺 entry_ts row**:不入樣本 + 存在即阻立案(`entry_ts_missing_rows_block_candidacy`)——排除數據後立案 = 選擇性抽樣,故一併擋;比 v4(unknown 桶算 1 個 entry 入均值)更嚴。

## Operator / 下一步

- E2 複審本輪 delta;E4 回歸(pytest 全鏈)。
- WP-A.4 反事實 rerun 管線須按 prereg 完整實作(§4 cluster-SE、per-(cell,horizon) family)——本檔 lane review 修復不替代 rerun。
- 既有 Linux 存檔 v4 artifact 在下一次 cron review 重跑後自然被 v5 覆蓋;false_negative_candidate_packet 對 v4 fail-closed 拒收(設計內)。
