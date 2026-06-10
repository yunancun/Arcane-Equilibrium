# AC-S2-A-3 候選證據檢查 — 2026-06-10(提前 ~06-11 排程一天)

> **PM 代落盤註記**:本報告由 FA agent 產出,該 session 無寫檔工具,內容由 PM 逐字代存(2026-06-10)。FA 自述證據侷限:無 Bash/SSH,「0 fills」未做當日 PG 新鮮 count,依 config `active=false`+05-29 FACT+06-04/06-10 多報告收斂(confidence MED-HIGH)。

## Executive Summary

1. **結論 = (b) 無候選滿足 AC-S2-A-3**,且證據鏈停在 step 0:兩個指定候選(funding_short_v2 / liquidation_cascade_fade)demo `active=false`、從未進 demo canary、0 fills——不是「差幾 bps」,是「累積根本沒開始」。
2. 前置鏈(green Stage 0R → operator 核准進 demo canary)一項都沒發生;A1 regime-dormant(30% APR 入場閘 56d 0 觸發)、A2 唯一一次 Stage 0R run = observe_more(n_eff=7、avg_net −2.45bps)後 thesis 已被 06-03 down-beta 研究 NO-GO。
3. AC-S2-A-3 **未被 AEG 取代但已被降格為必要非充分**:即使未來達標,亦僅觸發 Stage 0R replay preflight 派工,晉升一律過 ADR-0047 五要素矩陣 + AEG-S2 閾值(PSR/DSR≥0.95、PBO<0.5、OOS Sharpe>0)。
4. 建議:該排程項由日期觸發改**事件觸發**(4 條件),backstop 併入 2026-06-27 bb 30d clock 檢查點;不建議純 re-date,因 ~06-11 的日期前提(05-29 即啟動累積)已塌。
5. 今日**不應派 Stage 0R replay preflight**。

## §1 AC-S2-A-3 定義原文(三處一致,無後續修訂)

- **Sprint 2 dispatch packet** `docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md` §2.3:「AC-S2-A-3 | ≥ 1 個 candidate 達 demo 7d avg_net > 5bps + Wilson CI lower > 0 | Sprint 3+ verdict(Sprint 2 內未必 ready)」
- **Entry checklist** `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--sprint2_alpha_tournament_entry_checklist.md` Reject gate 5:「AC-S2-A-3 ≥1 candidate 達 demo 7d avg_net > 5bps + Wilson CI > 0 + **n≥30**;通過判據: funding_short_v2 OR liquidation_cascade_fade 達 demo 7d threshold;軟化 = 出 `draft_only`」
- **Preflight readiness 報告** `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--sprint2_stage0r_preflight_readiness.md` §3.3:「AC-S2-A-3 evidence 最早 ~2026-06-11(D+14 demo 累積),**但前置 = candidate 經 Stage 0R green + operator approve 進 demo canary;若 Stage 0R RED 或 operator 未 approve,evidence 不啟動 → ETA 順延**」——本排程項 ~06-11 日期即源於此條件式 ETA。

## §2 逐條判定(條件 vs 當前證據)

| AC-S2-A-3 條件 | 當前狀態 | 判定 | 證據 |
|---|---|---|---|
| 候選在 demo 活躍累積 | A1/A2 均 `active = false`(註解明寫「Stage 0R replay preflight PASS + operator IPC active=true 才啟」) | FAIL(step 0) | `settings/strategy_params_demo.toml:213-214, 233-234` |
| n≥30 demo fills | 0 fills(05-29 FACT 30d=0;其後無任何活化事件;06-04 PM 審計再證 active=false) | FAIL | readiness 報告 §3.1 gate 5;`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-04--external_framework_revolutx_real_code_audit.md:85` |
| 7d avg_net > 5bps | 無 demo 數據可算;A2 唯一 offline 量測 avg_net = **−2.45bps**(n_eff=7,sample_insufficient) | FAIL | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-30--a2_lcs_fade_stage0r_assessment.md` |
| Wilson CI lower > 0 | 同上,無樣本 | FAIL | 同上 |
| (隱含前置)green Stage 0R preflight | 任一候選皆無 green artifact;A2=observe_more(非綠);A1 probe #1 93% `missing_basis_asof` 撲空;runner 本身未在 runtime env 端到端跑過、auth fix 仍在未併分支(`P1-A1A2-STAGE0R-RUNNER-IMPL` E2→E4→PM owed) | FAIL | QC 05-30 報告 §2;`docs/audits/2026-05-31--funding_short_v2_structural_infeasibility.md:61`;TODO v123 §5 |

**最接近的候選離標準多遠**:(i) A2 在唯一可量測軸上點估 −2.45bps vs +5bps = 差 7.45bps 且方向為負、n_eff=7 vs n≥30,且該數字是 offline replay 非 demo fills——按 AC 的證據定義實為 0%;thesis 已於 06-03 被 down-beta masquerade 家族 NO-GO,demo TOML 維持 inactive。(ii) A1 不可量測:當前 regime 其 30% APR 入場閘 56d 觸發 0 次(窗內 max +10.95% APR),即使活化也是 0 signal;06-10 L2 P3b 設計已把它列為 DEAD MODE 教訓 seed。(iii) 同門檻的 textbook lane(AC-S2-A-1/P0-EDGE-1(i)):0/4 達標維持,06-01 RCA「已實現 edge 普遍負」,7d 內 bb_breakout 僅 4 fire、bb_reversion 僅 12 intents,n≪30。(iv) 新 AEG lane:listing fade 等 operator-timed Gate-B 24h 真捕捉;AEG-S3 真 `candidate_regime_metrics` rows = 0;residual producer flag-on 但單配置 demo 一律誠實 defer(`pbo_not_applicable_single_candidate`),PART 4 Stage0R orchestrator triple-OFF inert——均無法在現狀產生 AC-S2-A-3 證據。

## §3 AEG 閘門關係(服從性判定)

AC-S2-A-3 **從屬而非被取代**:TODO §3「Sprint 2 / Stage 0R legacy alpha | 從屬於 AEG | AEG gate 之外不晉升」。ADR-0047 要求每個 verdict 附 regime/breadth/freshness/survivorship/execution-realism 矩陣 + 統計閘;AEG-S2 robustness matrix 已硬化閾值(PSR/DSR≥0.95、PBO<0.5、IS/OOS Sharpe>0,`7494126a`)。AC-S2-A-3 的 7d/5bps/Wilson 弱於上述全部 → 假設性達標也只構成「值得派 Stage 0R replay preflight + 進 AEG 矩陣」的觸發,不是晉升證據。故不採 (c) 全面歸檔:排程項的「檢查點」功能仍有效,只是觸發機制錯了(日期 → 應為事件)。

## §4 背景陳述交叉核驗(差異全列,裁決交 PM)

| 背景陳述 | 核驗 | 備註 |
|---|---|---|
| 6 結構性候選全 NO-GO | **部分準確** | trend NO-GO(`a99ef886`)、funding-tilt NO-GO-C(no-reopen)、cascade-fade NO-GO+inactive、A1 regime-dormant = 屬實。**oi_delta:TODO §1 = 「排後」非正式 NO-GO**,與 MIT 06-09 報告憑記憶列其入 5 down-beta NO-GO 衝突,按權威序信 TODO;同報告把 listing 列 NO-GO,亦與 TODO「listing fade=主路」衝突(歷史回測負面 vs 前向捕捉主路兩回事)。**A3** BTC/ETH pairs = DRAFT/defer 從未 IMPL,非 NO-GO。對本判定零實質影響。 |
| residual flag-on 誠實 defer / PART 4 triple-OFF / AEG-S2 缺真 rows / bb_reversion 06-27 鐘 | **全部屬實** | TODO v123 §5/§6 直接核到。 |

## §5 證據鏈完整度(FA 評分)

Stage 0R runner 可信化 ~40%(代碼在 main、offline 跑過,runtime 未證+fix 分支未併)→ green verdict 0% → operator demo-canary 核准 0% → demo 累積(AC-S2-A-2)0% → AC-S2-A-3 verdict 0%。**Legacy lane 整體 ≈ 10%**;唯一活的替代供給線是 AEG lane(基建 ~90% 就緒,候選 rows 0%)。
