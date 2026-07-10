# E1 報告 — R3 修復包 WP-A 第 1/2 點:outcome_review F1 去重 + 成本雙軌

日期:2026-07-10 · 執行者:E1 · charter:`scratchpad/r3_fix_charter.md` WP-A.1/2 · 狀態:IMPLEMENTATION DONE,待 E2 審查

## 任務摘要

修 `helper_scripts/research/cost_gate_learning_lane/outcome_review.py`:

1. **F1 去重(WP-A.1)**:per-(side_cell, entry_ts_ms) 去重 + distinct-entry effective-n(n_eff)進 eligibility;raw outcome_count 一律不得再進 eligibility / t 檢定 / BH-FDR。n_eff 門檻做成參數 `min_effective_entries_per_side_cell`(默認 **5**,暫定值,注釋標明待 QC 預註冊 WP-A.3 定案)。
2. **成本雙軌(WP-A.2)**:主判接 `slippage_quantile_artifact.py` 產物的實測 E[cost](q50,無 1.3 安全乘數,`FEE_FLOOR_BPS=11.0` 不破);conservative_v1(q75×1.3)降為敏感性欄並列輸出,不作主判。artifact 缺失/畸形/過期(>48h)→ 主判 fail-closed 回退 conservative_v1(與修復前行為一致,不因缺 artifact 放寬)。

同批補/改單元測試,含偽複製 fixture(同 entry_ts 多副本壓成 1 個有效觀測)。輸出 schema 向後兼容(只增欄不刪欄);schema_version v3→**v4**(語義變更信號,詳下)。

## 修改清單

| 檔案 | 變更 |
|---|---|
| `helper_scripts/research/cost_gate_learning_lane/outcome_review.py` | 主體改造(+528/-178 級):`_effective_entries`/`_entry_group_key` 去重、`_load_expected_slippage`/`_expected_cost_bps_for_row` 實測成本軌、config/CLI 新參數、schema v4 |
| `helper_scripts/research/cost_gate_learning_lane/sealed_horizon_learning_evidence.py` | 最小 pass-through:config 加 `min_review_effective_entries_per_side_cell`(默認 5)+ 兩處 `BlockedOutcomeReviewConfig` 構造 + CLI arg(+15 行) |
| `helper_scripts/research/tests/test_cost_gate_evidence_methodology.py` | 舊 fixture 補 entry_ts;新增 8 個測試(F1 去重 4 + 成本雙軌 4) |
| `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` | 7 個 live-build fixture 補 distinct entry_ts(候選類升到 5 entries);3 處 cfg 補 n_eff=3;2 處 schema 斷言 v3→v4 |
| `helper_scripts/research/tests/test_cost_gate_sealed_horizon_learning_evidence.py` | 單 outcome fixture 顯式 `min_review_effective_entries_per_side_cell=1` |

## 關鍵設計(小決策與理由,便於 E2 對抗)

1. **去重鍵與壓縮**:同 (side_cell, entry_ts_ms) 的 rows 壓成 1 個有效觀測,取組內均值(保守/樂觀/實測三軌淨值與 gross/cost 同步壓縮;跨 horizon 同 entry 也壓——charter 原文按 (side_cell, entry_ts) 去重,同 entry 不同 horizon 自相關 100% 不是獨立觀測)。
2. **entry_ts_ms 缺失 → 全收同一 unknown 桶**(fail-closed:無法證明 distinct 就不虛增 n_eff)。writer v2 起所有非 censored row 必有 entry_ts_ms,實際只影響 legacy row(其本已被 LEGACY_OPTIMISTIC gate 攔候選)。新增 `entry_ts_missing_row_count` 欄。
3. **`min_outcomes_per_side_cell` 語義自 v4 改量 n_eff**(統計可算性 floor,默認 3);`min_effective_entries_per_side_cell`(默認 5)是候選 eligibility 硬 floor。無重複數據時 raw==n_eff,舊行為不變;避免 dead param。
4. **欄位相容策略**:`outcome_count` 保持 raw 行數(觀測量/展示);統計欄(avg/std/pct/min/max/t/BH/wrongful_block_score/packet 加權平均)全部改 n_eff 樣本。新增 `effective_entry_count`/`duplicate_outcome_row_count`。`sample_margin_count` 改為 n_eff−min_eff。
5. **新 cell status `EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT`**(過線但 n_eff<門檻),診斷同名(不落 BLOCK_CONFIRMED 誤導「已證無 edge」),併入 packet `insufficient_sample_side_cell_count` → packet 落 continue_recording。
6. **實測 E[cost] 公式**:`2×(FEE_TAKER_BPS + slip_q50) + funding_drag_row`,slip 取 symbol q50(n≥20)否則 global q50;≥ FEE_FLOOR_BPS。q50/無乘數 = E 的穩健估計;尾部保守性由並列欄 `avg_net_bps_conservative`/`net_positive_pct_conservative`/`conservative_tail_would_clear_thresholds` 承載。`cost_model.load_slippage_quantiles` 只投影 q75,故本模組自讀 q50(不動 cost_model.py,守住檔面範圍)。
7. **schema v3→v4**:先 grep 全 repo——唯一 schema-gated 消費端 `false_negative_candidate_packet.py` import 常數比對(自動一致);升版讓 Linux 上修復前的 v3 存檔 artifact 被 fail-closed 拒收,不再餵 false-negative 鏈(呼應 charter WP-A.7 NEAR dispatch 凍結)。Rust 無鏡像(grep 0 hit)。其餘消費端(status/decision_packet/healthcheck/audit)不驗版,純 pass-through。
8. **headline sign-flip / BH family** 全改吃去重後主判軌淨值;`selection_universe`(K 登記)保留 raw horizons(登記面從寬)。

## 可重跑證據

```
python3 -m pytest helper_scripts/research/tests/ -q
# → 1 failed, 1561 passed, 4 skipped(failed 為 pre-existing,見下)
python3 -m pytest helper_scripts/cron/tests/ helper_scripts/db/audit/ -q   # → 290 passed
```

CLI 冒煙(F1 真實形狀縮小版:2 distinct entry ×50 行 + 新鮮分位 artifact):

```
cd helper_scripts/research && python3 -m cost_gate_learning_lane.outcome_review \
  --ledger <f1_ledger.jsonl> --slippage-artifact <slippage_quantiles_latest.json> --print-json
# → schema v4;outcome_count=50, n_eff=2, dup=48;status=COLLECT_MORE;candidate=False;
#   t_p=None, bh=None, wrongful=0.0;cost_basis_main=expected_slippage_quantile_v1;
#   avg_net(main)=51.8(E[cost]=17.0=2×(5.5+3.0)) vs conservative 64.8 並列。
```

## 治理對照

- 不觸 max_retries/live_execution_allowed/execution_authority/system_mode;lane 純 artifact,無 PG 寫/Bybit/order/runtime mutation;fail-closed 只收緊不放寬(n_eff floor 新增;缺 artifact 回退保守)。
- 無 SQL migration;無新 singleton;新注釋全中文;無跨平台硬編碼路徑。
- 檔面:outcome_review.py 822→~1170 行(<2000 硬頂,>800 需 E2 留意)。

## 不確定之處 / 遺留

1. **n_eff 默認 5 為暫定**——QC 預註冊(WP-A.3)定案後若不同,只需改 `min_effective_entries_per_side_cell` 默認值(單點)。QC stage2 報告另有「NEAR cell 翻案需 n_eff≥30」為 dispatch 條件,非本 review eligibility 門檻,未混入。
2. **cron 未接 artifact**:`cost_gate_learning_lane_cron.sh` 的 REVIEW_ARGS 未帶 `--slippage-artifact`,runtime 定期 review 仍保守主判(fail-closed)。活化=一行 `--slippage-artifact "${LANE_DIR}/slippage_quantiles_latest.json"`,屬 Linux 活化步驟,留主 session/PM 決策(未擅自擴 cron 檔面)。
3. **pre-existing 測試紅**:`test_cost_gate_learning_lane_decision_packet.py::test_cli_missing_optional_sealed_evidence_fails_closed_to_packet`——fixture generated_at=2026-06-22 + `--max-artifact-age-hours 336`(14d),CLI 用牆鐘 now,2026-07-06 起必紅;decision_packet.py 與該測試均未被本次觸碰、無 import 依賴(已 grep 證實)。建議 E4/PM 另開 ticket 修 time-bomb(fixture 應注入 --now 或動態日期)。
4. **cluster-SE by day**(QC O3 提及)不在本任務兩點範圍,屬 WP-A.3 QC 預註冊後的重跑範疇。
5. policy 測試 `:1068` 留一處 v3 字串 fixture(模擬讀舊存檔的 pass-through 行為,status.py 本不驗版)——語義正確,未動。

## Operator / 主 session 下一步

1. E2 對抗審查本 diff(5 檔)→ E4 全鏈回歸。
2. QC 預註冊判準落 repo 後,以 CLI + `--slippage-artifact` 重跑 71,207 母集 + 33 GROSS_EDGE cells(WP-A.4)。
3. 決策 cron REVIEW_ARGS 是否接 artifact(單行,Linux 活化)。

E1 IMPLEMENTATION DONE: 待 E2 審查(report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--r3-wpa-outcome-review-f1-dedup-cost-dual-track.md)
