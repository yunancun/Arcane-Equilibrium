# E1 報告 — R3 WP-A E2 RETURN 修復輪 1:n_eff 門檻 30 + 成本公式對齊預註冊 §6

日期:2026-07-10 · 執行者:E1(修復輪 1)· charter:`scratchpad/r3_fix_charter.md` WP-A · 狀態:IMPLEMENTATION DONE,待 E2 複審

## 任務摘要

逐條修 E2 兩條 P1 blocking findings(承 2026-07-10 首輪報告
`2026-07-10--r3-wpa-outcome-review-f1-dedup-cost-dual-track.md`):

1. **P1-1(n_eff 門檻未對齊預註冊)**:`min_effective_entries_per_side_cell`
   默認 5 → **30**,對齊同 tree 已落檔的 QC 預註冊
   `docs/research/2026-07-10--counterfactual_rerun_preregistration.md` §3 E1
   (n_eff≥30;§0.3 映射 charter WP-A.1→§2/§3)。生產 cron 不帶 flag 時
   n_eff∈[5,30) 的 cell 不再可能成 `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE`。
2. **P1-2(主判成本公式違預註冊 §6)**:主判滑點 q50 → **mean_abs**
   (E[|slip|],§6.1 凍結公式);尾部敏感性欄改 **CVaR90**(§6.2,cvar90 缺失
   fallback q90 並記 `tail_metric="q90_fallback"`);`slippage_quantile_artifact.py`
   SQL + payload 擴 `mean_abs` / `mean_signed`(§6.1 透明對照)/ `cvar90` 欄。

## 修改清單

| 檔案 | 變更 |
|---|---|
| `helper_scripts/research/cost_gate_learning_lane/outcome_review.py` | 門檻默認 30(dataclass + argparse);`_load_expected_slippage` 投影 mean_abs+尾部(新 `_project_tail_slippage`);`_expected_cost_bps_for_row` 回傳主判+尾部兩軌;`_effective_entries` 攜 `net_tail`/`tail_cost_bps`;cell 新欄 `mean_net_tail`/`net_tail_positive_pct`/`avg_tail_cost_bps`/`tail_metric`(§6.2 命名逐字對齊);`cost_basis_main` 改名 `expected_slippage_mean_abs_v1`;packet `expected_cost_artifact` 塊 `global_q50_bps`→`global_mean_abs_bps`+`global_tail_bps`+`global_tail_metric` |
| `helper_scripts/research/cost_gate_learning_lane/sealed_horizon_learning_evidence.py` | `min_review_effective_entries_per_side_cell` 默認 5→30(dataclass + argparse) |
| `helper_scripts/research/cost_gate_learning_lane/slippage_quantile_artifact.py` | SQL 擴 avg(s)/avg(s_signed)/CVaR90 相關子查詢(ROLLUP 兩層皆算);payload 擴三欄;`ARTIFACT_SCHEMA_VERSION` v1→v2(純增欄,q75 消費端 `cost_model.load_slippage_quantiles` 不驗版不受影響) |
| `helper_scripts/research/tests/test_cost_gate_evidence_methodology.py` | floor 測試改 n_eff=29 邊界直測默認 30;meeting-floor 測試擴到 n_eff=30(默認 cfg 走通候選+BH);BH 撤下測試顯式 n_eff=6 保 revocation 路徑本體;成本軌測試組共用 `_COST_TRACK_CFG`(n_eff=5,顯式放寬,測成本語義非 floor);artifact fixture 改 mean_abs/cvar90 形;新增 2 測:cvar90 缺欄 fallback q90、v1 舊 artifact 缺 mean_abs 整軌 fail-closed |
| `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` | 兩個 live-build 5-entry fixture 擴到 30 distinct entry(avg 維持 11.5、wrongful_block_score/cushion 斷言值不變,sample_factor=30/30=1) |
| `helper_scripts/research/tests/test_cost_gate_cost_backfill_and_quantiles.py` | ROLLUP 投影測試補三欄斷言 + 缺欄行 → None 斷言 + schema v2 斷言 |

## 關鍵設計(小決策與理由)

1. **舊 v1 artifact 缺 mean_abs → 整軌拒用**(回退 conservative_v1),不以 q50 頂替:右偏 |slip| 下 q50 < mean,頂替 = anti-conservative,正是 E2 finding 本體。Linux 上既有 artifact 在新代碼下自動失效直到 cron 重產 v2 —— 失效方向 = 更保守,安全。
2. **尾部欄命名逐字取預註冊 §6.2**(`mean_net_tail`/`net_tail_positive_pct`),不自創;conservative_v1 保留為第三對照欄(§6.2「不得換皮重生」+ `candidacy_flipped_by_cost_model` 連續性)。
3. **gross 缺失 row 不入尾部樣本**(與主判軌「fallback 保守淨值」不同):conservative cost 可低於 CVaR90 尾部成本,替代會虛增 tail net(loss-budget 敘事 anti-conservative)。
4. **CVaR90 SQL 用相關子查詢對 ROLLUP 兩層取 `avg(s) FILTER s≥q90` 等價式**;q90 NULL 時自然回 NULL → 消費端 fallback。
5. **測試分層**:floor 本體用默認 cfg 直測(29/30 邊界);成本軌語義測試顯式放寬 n_eff=5(E2 suggestion 允許「顯式傳寬鬆 cfg」);policy live-build fixture 擴到 30(preflight/discovery 內部用默認 cfg,無注入點,擴 fixture 是唯一誠實解)。
6. **§6.1 fallback 鏈的範圍取捨**:預註冊 toml-tier 第三級 fallback 是 WP-A.4 重跑 CLI 的規格;本 lane review 在 global mean_abs 缺失時直接整軌回退 conservative_v1(其內部自帶 toml fallback),嚴格更保守,非偏離。

## 可重跑證據

```
python3 -m pytest helper_scripts/research/tests/ -q
# → 1 failed, 1563 passed, 4 skipped(failed = 首輪已記錄的 pre-existing
#   decision_packet 牆鐘 time-bomb,與本次改動無 import/行為交集)
python3 -m pytest helper_scripts/cron/tests/ -q      # → 242 passed
python3 -m pytest <4 個受影響測試檔> -q               # → 133 passed
```

CLI 冒煙(F1 真實形狀 2 distinct entry×50 行 + v2 artifact mean_abs=3.0/cvar90=20.0):
`cost_basis_main=expected_slippage_mean_abs_v1`;`thresholds.min_effective_entries_per_side_cell=30`;
n_eff=2 → `COLLECT_MORE`、candidate=False、t/BH=None;`avg_expected_cost_bps=17.0`
(=2×(5.5+3.0));`avg_tail_cost_bps=51.0`(=2×(5.5+20));`mean_net_tail=17.8`;
conservative 64.8 並列。

**PG 實查(Linux read-only,新 SQL 逐字 dry-run,window 90d)**:執行成功;
global 行 n=2529、`mean_abs=17.709` vs `q50=2.992`(**右偏證實,E2 推斷落錘**:
q50 主判低估單腿滑點 ~14.7bps ≈ 29bps round-trip)、`cvar90=125.212 ≥ q90=34.113`;
全部 symbol 行 cvar90≥q90 成立。

## 治理對照

- 不觸 max_retries / live_execution_allowed / execution_authority / system_mode;lane 純 artifact,PG SELECT-only,無 Bybit/order/runtime mutation。
- fail-closed 方向只收緊:n_eff floor 5→30;舊 artifact 整軌拒用回退保守;`order_authority=NOT_GRANTED`/`promotion_evidence=false` 不變。
- 無 SQL migration(fills 查詢為 SELECT-only 擴欄);無新 singleton;新注釋全中文;無硬編碼路徑。
- 檔面:outcome_review.py 1263 行(>800 需 E2 留意,<2000 硬頂)。

## 不確定之處 / 遺留

1. **artifact schema v1→v2**:純增欄;唯一版號常數在模組自身,全 repo 無等值檢查(grep 證實)。Linux 既有 v1 artifact 在新 review 下 expected 軌 OFF(保守回退)直到 cron 重產 —— 屬預期安全態,主 session 活化時重跑 `slippage_quantile_artifact` 即可。
2. **cron `REVIEW_ARGS` 仍未帶 `--slippage-artifact`**(首輪遺留,E2 未列 blocking):生產 review 主判維持 conservative_v1 直到活化決策;方向保守,不在本輪 scope。
3. pre-existing decision_packet time-bomb 測試紅照舊(建議 E4/PM ticket 化,首輪報告已記)。

## Operator 下一步

無需 operator 動作;等 E2 複審 → E4 回歸。Linux 活化清單(主 session):重產 v2 slippage artifact(單行:`cd ~/BybitOpenClaw/srv/helper_scripts/research && python3 -m cost_gate_learning_lane.slippage_quantile_artifact --print-json`)。
