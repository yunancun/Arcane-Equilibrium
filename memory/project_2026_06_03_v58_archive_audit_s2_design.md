---
name: project_2026_06_03_v58_archive_audit_s2_design
description: 2026-06-03 接手——V5.8 意圖保存+歸檔完整性審計(3 塊代碼/DB/run-artifact 實證 PASS)+AEG-S2 設計+funding-tilt 協議+P5 soak total 空轉發現
metadata: 
  node_type: memory
  type: project
  originSessionId: 35987fef-75ca-4b1a-827d-0e1f65bedf84
---

2026-06-03 接手 TODO（v111，三端同步），operator 要求：對照 V5.8 確保意圖未失 + 被歸檔的部分必須是「真實讀過代碼/runtime 得出的 verified-as-passing」非文檔誤導。

**審計結論（兩軸全過，可不重做）**：
- **軸 1 意圖保存**：v110→v111 精簡（300→167 行）未失 V5.8 意圖。逐條對照 v58 memory + 87 行 preservation audit + v110 全文：autonomy 凍結(M1-M13→指針)/alpha 主攻/成本牆兩逃逸路/R-2b HINT(已兌現)/V### BLOCKER/Sprint2 從屬 AEG 全保存。健康證據：v111 §7 誠實列 4 個逾期項待 triage，沒把未驗當 done 埋掉。2 minor note：成本牆**推理**只在 memory+QC verdict 非 TODO body（pointer 可追）；M4 no-writeback 隨凍結壓縮。
- **軸 2 歸檔完整性**：派 3 獨立對抗 agent ground 在實際代碼/DB/git，**不採信文檔字面**，全 PASS：(a) E2 驗 `CODE-SIMPLIFY-P0-P4` 8/8 commit——3 個 byte-identical 宣稱(P1/P2a/P4)逐行 diff 證偽失敗=真純抽取、P2b CRITICAL fix 真在 HEAD、P3 mainnet guard 真 fail-closed、8 commit 零觸 Rust 熱路徑。(b) MIT 驗 V125(6 表/3 hypertable)+daily-kline(精確 14505)+funding/OI(精確 46539/348153,0 fake-zero,strict-parse code-level fail-closed,**writer 根本不算 cap→不可能重蹈 funding_short_v2 樣本窗 max 硬傷**),三層(commit+runtime+data)真一致。(c) QC 驗 trend NO-GO DEFENSIBLE 非假陰性(backfill 把 56d→730d 樣本不足出口堵死,effective_n=237 過 floor,harness 對真 momentum 有 bite)。**我撈原始 run JSON 對賬 verdict 逐位吻合**(k40 HAC=2.7155/k90=−2.60/n_eff=2.087/stopped_at=edge gate 非 cost gate)→ 文檔未誤導。這是少見「審計過度歸因」教訓的**反例**(三層真一致)。

**P5 soak total 空轉發現（最重要，防未來誤判）**：P5-SM step-i soak 宣稱 RUNNING/0 divergence，但親驗發現：gate 是 `divergences==0 AND total>=N`(`governance_divergence.py:33`),**只 grep WARN=0 不充分**。WARN 簽名是 `SM_DIVERGENCE`(不是 "divergence")。comparator(`record_divergence`)只在 Python `GovernanceHub.acquire/release/get`(hub.py:933/1053/1179)內觸發,該 hub 主 caller=`executor_agent.py:554`(**shadow 默認**)非 Rust 權威熱路徑(那 408k/24h lease_transitions 是 Rust event_consumer 寫)→ **若 Python shadow-hub 無 organic 流量,total≈0,「0 divergence」是 silent no-op 偽 pass**。收口前須讀 `total`:auth'd POST `/api/v1/governance/health-check`→`lease_ipc_divergence.total`(API 綁 tailnet IP `100.91.109.86:8000` 非 localhost,curl localhost=HTTP 000)。flag 真 ON(worker env `OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1` 親驗)。

**推進 operator 選的 3 方向(設計完成,committed 7bc2f9ee)**：
- **AEG-S2 證據自動化**(MIT 設計 `…/MIT/…/2026-06-03--aeg_s2_evidence_automation_design.md`):3 組件 regime runner(a)∥breadth ladder(b)→robustness matrix(c)。**BLOCKING:regime labels 不可重用 V002 `market.regime_snapshots`**(intraday/無版本 vs AEG daily-anchor/版本化衝突)→新建 `research.aeg_regime_labels` **V127**(建檔前重確 Linux `_sqlx_migrations` head,2026-06-01 reflection 仍 V115 但 V125/126 檔在 repo=apply state 須重 reflect)。(b)/(c) artifact-only(S2 無新表)。**critical-path=FND-2 PIT universe builder IMPL(契約完成未 scope,PM 須先 scope)**;(a) 可在 V127 批准後即開。
- **funding-tilt 診斷協議**(QC `…/QC/…/2026-06-03--funding_tilt_carry_diagnostic_protocol.md`):成本牆逃逸路②(trend NO-GO 後唯一未測象限)。cross-sectional funding-tilt long-short + time-series funding-extreme,K=8,對標 trend 5 重嚴謹。**QC 誠實預判清牆 ~20-25%,最可能失敗=carry 量級不足(median |F|≈IR floor→NO-GO-C)**。**next=MIT 先跑 cheap DATA TASK #0+#1(canonical run 覆蓋+funding median 量級),~1 天可能就 NO-GO-C 省下全 harness**。
- **收尾**:commit 3 sibling memory(E5/MIT/QA)復原 0-dirty;klines.git_sha 全 NULL(apply 漏傳 --git-sha,cosmetic,若進 promotion lane 建議補)。

**交叉印證**:MIT+QC 各自獨立都指出 `data_loader.py:300` Phase-1 `compute_rule_based_regime` 的 full-sample vol-tercile cross-section leak(minor,productionized `aeg_regime_v0.1.0` runner 不可繼承)。

承 [[project_2026_06_02_aeg_trend_listing_infra_deployed]]（infra 部署）+ [[project_2026_05_31_v58_alpha_pivot]]（成本牆 2 逃逸路）+ [[project_2026_06_01_rust_python_boundary_simplification_audit]]（P5-SM Option2）；funding-tilt 紅線見 [[project_2026_05_31_funding_short_structural_doa]]（cap SSOT + regime-dormant）；soak 發現呼應 [[feedback_evidence_discipline_under_degraded_tools]]（silent no-op 偽 pass）。
