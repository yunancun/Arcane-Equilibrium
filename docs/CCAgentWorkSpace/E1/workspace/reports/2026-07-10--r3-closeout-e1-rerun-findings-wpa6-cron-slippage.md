# E1 收口輪報告 — R3 修復包五項(E2 rerun findings / t(n_eff) mutation test / WP-A.6 / prereg 索引 / cron slippage)· 2026-07-10

STATUS: DONE

charter:`scratchpad/r3_fix_charter.md`;工作依據:PM 修復包最終報告 §三/§六(`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-10--r3_fix_package_report.md`)。多 session 髒樹,只動本輪五項相關檔;**未 commit / 未 push**(留最後統一步驟)。

---

## 一、任務摘要與逐項狀態

| 項 | 狀態 | 摘要 |
|---|---|---|
| (1) E2 rerun-code findings P2×3 | **NO-OP(前輩已完成,本輪核實)** | `counterfactual_rerun.py` 已含三項修復:①`build_cell_horizon_stats` 先算 cluster_result,`degenerate_reason=='zero_cluster_variance'` 併入 `data_integrity_suspect` 再進 eligibility/judge(:887-903);②凍結 SQL SELECT 投影改寫已記 `_base_deviation_log()` 第 5 條(:1205-1213),且抽成可測純函數;③`test_cost_gate_counterfactual_rerun.py` 已擴至 558 行 20 測:eligibility 邊界(n_eff 30/29、days 5/4、top-day 50.0/>50、censored 30.0/>30)、E5、replica 不一致、cluster V=0 退化輸入(cluster sums 相消、std>0)、select_family NEAR-only 排除、deviation_log SQL 條目、雙源合併/代表行/歸因拆分。本輪親跑 `pytest test_cost_gate_counterfactual_rerun.py` → **20 passed**。 |
| (2) t(n_eff) mutation-biting 測試 | DONE | 新測 `test_f1_t_test_n_is_effective_entry_count_not_raw_row_count`(`test_cost_gate_evidence_methodology.py`):30 distinct hourly entry(跨 6 UTC 日、帶擾動)×3 複本 → outcome_count=90 / n_eff=30;斷言 cell p 逐位= `one_sided_t_p_value(mean, std, 30)` 且 `p_raw(n=90) < p_eff/100` 分離保證。**mutation 親證**:臨時把 outcome_review.py:943-945 的 `effective_entry_count` 改回 `outcome_count` → 測試紅(expected 0.014915 vs raw-n ~7.6e-5);還原後 sha256 byte-identical(`e0c1b767…`,git diff 空)。 |
| (3) WP-A.6 checklist 前置 | DONE | 正本裁定=`docs/agents/profit-first-fast-demo-promotion-loop.md`(Demo order-capable runner 的 checklist 正本;TODO 多行 FROZEN 條目引用的「WP-A.6 checklist precondition」即此)。§2「不能缺」清單**首項**加 preregistered distinct-entry n_eff 檢定(機器可檢欄位 `sample_eligibility_ok`/`effective_entry_count`,正本指針 prereg §3;raw `outcome_count` 不是樣本量);§4 Final Window 加前置句:未通過(含 n_eff 不明)不得開窗,PM/E3 dispatch fail closed。 |
| (4) prereg 正本登記 | DONE | `docs/_indexes/document_index.md` 頂部新節「2026-07-10 反事實重跑預註冊(R3 修復包 WP-A.3)」(判準摘要+凍結錨+verdict sha+prereg v2 邊界);`docs/README.md` 目錄樹插入 `research/` 行(references/ 與 archive/ 之間,格式同構)。 |
| (5) cron REVIEW_ARGS 接 --slippage-artifact | DONE | `cost_gate_learning_lane_cron.sh` REVIEW_ARGS +1 flag 行(+3 行中文注釋):`--slippage-artifact "${OPENCLAW_COST_GATE_SLIPPAGE_QUANTILES_JSON:-$LANE_DIR/slippage_quantiles_latest.json}"`——默認即 `slippage_quantile_artifact.py::_default_artifact_path()` 產物路徑,env-overridable 符合本檔慣例。 |

## 二、修改清單(5 檔,62 行全 insertion)

| 檔 | diff |
|---|---|
| `helper_scripts/research/tests/test_cost_gate_evidence_methodology.py` | +40(新測試 1 個) |
| `helper_scripts/cron/cost_gate_learning_lane_cron.sh` | +4(REVIEW_ARGS 1 flag + 3 注釋) |
| `docs/agents/profit-first-fast-demo-promotion-loop.md` | +10(§2 首項 + §4 前置句) |
| `docs/_indexes/document_index.md` | +6(新節) |
| `docs/README.md` | +2(目錄樹 research/ 行) |

`counterfactual_rerun.py` / `test_cost_gate_counterfactual_rerun.py` / `evidence_stats.py` 本輪**零改動**(前輩產物原樣;仍為 untracked/modified 待 E2→E4 鏈)。

## 三、關鍵驗證(可重跑)

```bash
cd /Users/ncyu/Projects/TradeBot/srv
# (1) rerun findings 修復核實
python3 -m pytest helper_scripts/research/tests/test_cost_gate_counterfactual_rerun.py -q   # 20 passed
# (2) mutation bite(手動):outcome_review.py:943-945 effective_entry_count→outcome_count 後跑下行必紅
python3 -m pytest helper_scripts/research/tests/test_cost_gate_evidence_methodology.py -q   # 37 passed
shasum -a 256 helper_scripts/research/cost_gate_learning_lane/outcome_review.py             # e0c1b767…(還原核對)
# (5) cron 語法 + CLI 雙向 smoke(scratchpad 內執行,缺檔→conservative_v1 / 在檔→expected_slippage_mean_abs_v1,exit 皆 0)
bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh
# 回歸
python3 -m pytest helper_scripts/research/tests/ -q   # 1591 passed / 1 failed / 4 skipped
python3 -m pytest tests/ -q                            # 814 passed / 5 failed / 2 skipped
```

唯一 research fail = pre-existing `test_cli_missing_optional_sealed_evidence_fails_closed_to_packet` 牆鐘 time-bomb(PM 報告 §三已列 baseline);root 5 fail 名單逐字同 E4 baseline(stock_etf_ipc×2 / ipc_tests / stable_boundary_docs / blocked_symbols_freeze),皆與本輪無關。

## 四、治理對照

- 硬邊界零觸碰:無 .rs / 無 runtime / 無 PG 寫 / Cost Gate 零代碼改動;cron 新 flag fail-closed(artifact 缺失/過期/缺 mean_abs → outcome_review 自行回退 conservative_v1 主判,已 CLI 親證)。
- 跨平台:新增行無硬編碼機器路徑($LANE_DIR ← OPENCLAW_DATA_DIR)。
- 注釋:新增全中文,英文留技術詞。
- 續作棒紀律:任務(1)判定 NO-OP 依據=修復代碼注釋+測試 docstring 與 E2 findings 逐條對應(untracked 檔無 git log);禁止重做,未重寫任何前輩產物。

## 五、小決策(自行選擇+理由)

1. **WP-A.6 正本位置**=`profit-first-fast-demo-promotion-loop.md` §2+§4:它是 Demo order-capable 進入條件與 final window 的唯一 checklist 正本,TODO FROZEN 行的 unfreeze 條件即引用「WP-A.6 checklist precondition」;未動 `profit-first-autonomy-loop.md`(其 §2 是授權 envelope 契約,非 evidence checklist),維持單一正本。
2. **cron flag 帶 env-override**:符合本檔全部 artifact 路徑的既有慣例;默認值=producer 默認輸出路徑,零配置即生效。
3. **mutation 測試效應量取中等**(mean≈0.3/std≈0.72):強效應會使 n_eff 與 raw-n 兩個 p 同時 underflow 到 0,測試失去牙。

## 六、不確定之處

- 任務(1)的前輩產物本輪僅做「與 findings 逐條對應+測試全綠」核實,未逐行重審其統計正確性——該深度屬 E2 複審職權。
- Linux runtime 上 `slippage_quantiles_latest.json` 是否已有 producer 排程屬活化面(cron 目前無 producer 行);無檔時新 flag 行為=現狀(conservative 主判),無風險。

## 七、Operator / 主會話下一步

1. 派 E2 審本輪 5 檔 diff(+前輩 rerun-code 三檔複審,同批)→ E4 回歸 → 統一 commit。
2. push + Linux 同步後,cron 下一輪自動帶 `--slippage-artifact`;若要主判真用實測 E[cost],需在 Linux 排 `slippage_quantile_artifact.py` 產出(獨立活化決策)。
3. TODO FROZEN 行的「WP-A.6 checklist precondition (not yet landed)」措辭在 commit 後可由 PM 更新為 landed(TODO 編輯屬 PM,本輪未動 TODO.md)。

E1 IMPLEMENTATION DONE: 待 E2 審查(report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--r3-closeout-e1-rerun-findings-wpa6-cron-slippage.md)
