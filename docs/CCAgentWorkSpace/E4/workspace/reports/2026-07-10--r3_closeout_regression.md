# E4 Regression — R3 修復包收口 wave(WP-A.4 rerun 代碼落地 + E1 五項收口)· 2026-07-10

樹態:HEAD `2a6f1df5d` + 收口 dirty(counterfactual_rerun.py[新]/test_cost_gate_counterfactual_rerun.py[新]/evidence_stats.py/test_cost_gate_evidence_methodology.py[+40 純增]/SCRIPT_INDEX/cron/prereg 索引 docs)+兄弟 auth dirty(login.html 等,未觸)。依 PM 修復包報告 §四 lane 定義/§三 四元組對照;charter=`scratchpad/r3_fix_charter.md`。本 wave 不 commit 不 push。

## Test 結果(全 lane ×2 逐字一致,Mac py3.10 pytest9.0.3 從 srv root)

| Lane | passed | failed | skipped | error | 報告§三對照 | delta 判定 |
|---|---|---|---|---|---|---|
| `pytest tests/` ×2 | 814 | 5 | 2 | 0 | 812/5/2/0 | +2=GUI batch-1 spec-drift guard 已 commit(`fcb931ee2`),==E4 memory 最新 BASELINE 814;5F 名單逐字同 pre-existing(stock_etf_ipc_handler×2/ipc_tests/stable_boundary_docs/blocked_symbols_freeze)|
| `pytest helper_scripts/research/tests/` ×2 | 1591 | 1 | 4 | 0 | 1579/1/4/0(rerun 落地後) | +12=rerun 套件 9→20(+11,E2 P2×3 收口測試)+1 mutation-biting 測試;REMOVED=0(methodology diff 純 +40 insertion,rerun 套件=全新 untracked 檔);1F=pre-existing `test_cli_missing_optional_sealed_evidence_fails_closed_to_packet` 牆鐘 time-bomb |
| `pytest helper_scripts/canary/ --continue-on-collection-errors` ×2 | 533 | 0 | 0 | 1 CE | 533/0/0/1CE | 零 delta;CE=pre-existing Mac py3.10 缺 tomllib(`test_check_cost_gate_double_deduct.py`),Linux py3.12 不受影響(前輪親證) |
| Rust cargo | 豁免 | — | — | — | — | dirty 樹 0 .rs 親證(`git status` grep);Linux lib 口徑 4404 不變 |
| GUI node --check | 豁免 | — | — | — | — | 本 wave 0 GUI 檔;dirty login.html=兄弟 auth session 改動非本 scope |

聚焦子集:`test_cost_gate_counterfactual_rerun.py`=20/0、`test_cost_gate_evidence_methodology.py`=37/0(含新 mutation 測試 `test_f1_t_test_n_is_effective_entry_count_not_raw_row_count`)。

## Gate 雙向(涉 eligibility/n_eff gate 邏輯)
- fail-closed 側:n_eff 29/days 4/top-day >50/censored >30 全擋;t 檢定 n 換 raw outcome_count 即紅(mutation bite,E2 open P2 收口)。
- 正常路徑側:n_eff 30/days 5/top-day 50.0/censored 30.0 恰達門檻仍通過(`test_eligibility_e1..e4` 四個 boundary 測試雙側斷言)。

## Mock 審查
- `test_cost_gate_counterfactual_rerun.py`:0 mock/patch/monkeypatch(純函數真跑)✓
- methodology 新測試:0 mock 新增行 ✓
- 補充驗證:`bash -n cost_gate_learning_lane_cron.sh` OK;`outcome_review.py` git-clean 且 sha `e0c1b767…`==E1 mutation 還原核對值 ✓

## 跑兩遍結果
三 lane 各 ×2 逐字一致(counts+失敗名單);flaky=N。

## Findings(全量)
1. INFO/HIGH:裸 `pytest helper_scripts/canary/`(Mac py3.10)在 collection 即 Interrupted(0 測試執行),四元組 533/0/0/1CE 須 `--continue-on-collection-errors` 或 `--ignore` 才可得——PM 報告 §四 命令用 --ignore,語義等價;pre-existing hygiene 票已在 §六-8。
2. INFO/HIGH:tests/ 814 vs 報告 §三 812、research 1591 vs 1579——皆 passed 只增歸因閉合(見上表),非回歸。
3. INFO/MEDIUM:本收口輪 E1 五檔 diff 的獨立 E2 review 未見落檔於 E2 workspace/reports(E2 memory 載 WP-A.4 rerun 代碼對抗審=ISSUES P2×3+NIT×7 無 P0/P1,inline 不落檔;P2×3 已由本輪測試收口親證)。是否需補正式 E2 落檔屬 PM 裁決,不阻回歸。

## 結論
**PASS**(zero regression;刪測=0;E2 ISSUES 之 P2×3+open P2[t(n_eff) mutation bite]全部有對應收口測試且親跑綠)。退 E1:無。

E4 REGRESSION DONE: PASS · report path: docs/CCAgentWorkSpace/E4/workspace/reports/2026-07-10--r3_closeout_regression.md
