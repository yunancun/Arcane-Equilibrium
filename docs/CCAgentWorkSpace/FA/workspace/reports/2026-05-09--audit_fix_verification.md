# FA Audit Fix Verification — 2026-05-09 對抗性核實報告

審計員：FA · 對應 audit baseline `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-08--full_chain_functional_audit.md`
基準範圍：`72f05aa0..7fccad06` (28 commits)

**Tally：✅ 7 / ⚠️ 4 / ❌ 12 / 🔄 6 / 🆕 3**

---

## §1 Executive Summary

**修復覆蓋率**（按 FA 29 finding tally）：
- 真修：17 / 29 (~59%)
- 部分修 / source-only-未 deploy：7 / 29 (~24%)
- 假修 / 降級 / 未動：5 / 29 (~17%)
- NEW-ISSUE：3 條（修復過程引入）
- 5 條 P0-DECISION-AUDIT operator 仍 PENDING

**Adversarial verdict**：**CONDITIONAL-CRITICAL**。24h 28 commits 量大且大部份 source/test 真實落地，但 6 個結構性問題：

1. **F-01 ExecutorAgent shadow_mode** — 完全未動。`executor_agent.py:224` `lambda: True` 仍存；3 TOML 仍 `shadow_mode = true`；FA push back #2 operator 拍板未到（`P0-DECISION-AUDIT-2 PENDING-OPERATOR`）。fake-live 鏈仍是 0 真值。**最關鍵 finding 0% 修復**。
2. **F-11 dead schema 降級修法** — 原 audit 提 24 表 dead，PA fix plan 計畫 V068-V071「drop dead schema」，**真實落地的 V068/V070/V071 都改為「reclassification guard / metadata-only / COMMENT only / 0 destructive」**。表都還在，row count 沒變（0→0），形式上 closure 但 functional gap 沒解。
3. **🆕 NEW-ISSUE-1 engine restart 後 LiveDemo pipeline 停** — `.codex/WORKLOG.md:332` 記載：「live authorization file is missing, so the engine refused to spawn LiveDemo/live at boot and is running demo-only」。修復 W-AUDIT-7 + V077 deploy 觸發 restart，但 auth 文件未同步重建 → LiveDemo 從 5/8 audit 時的「真實 fills 流量」變成 0。引入新 functional regression。
4. **W-AUDIT-3 部分而 F-01 卡 operator** — TODO 自報 PARTIAL `da2dba25`，但下游 F-15 e2e test 要 `OPENCLAW_TEST_PG` opt-in 才驗 DB row（默認 early-return），實際 lease writer→DB row e2e 沒被自動驗。
5. **W-AUDIT-2 F-03 部分** — `spawn_lease_transition_pipeline` 確實接到 `main.rs:657`，但「source/test only; no rebuild/restart」— PA fix plan 自承 runtime 影響 0；engine restart 在 W-AUDIT-7 階段才發生（5/9 晚），且觸發 NEW-ISSUE-1。
6. **6 表 0 INSERT、5 ML 腳本 silent-unscheduled** — F-08 cron script 寫了但 TODO/WORKLOG 重複「cron not installed」；ML 訓練腳本仍未真實排程。

業務鏈完整度更新（從 ~58% → ~58%）：
- 自動掃描 95% (無變)
- 策略選擇 55% (無變)
- AI 風控 78% (無變)
- 下單 **35% → ~30%** (LiveDemo pipeline 因 NEW-ISSUE-1 暫停，only demo)
- 止損 95% (無變)
- 學習 28% (無變；6 表 0 INSERT 沒解 + cron 未裝)
- 進化 30% (無變)
- 觀察 80% (無變)

**修復 surface-level 多但 deep-impact 少。沒有任何單一 finding 真改變 fake-live 結構**。

---

## §2 Finding-by-Finding 核實表（29 finding）

### Critical 4 條

| # | 原 finding | Commit hash | Verdict | Evidence |
|---|---|---|---|---|
| C-1 | CLAUDE.md §三/§五/§四 lease retrofit drift（5 stale 數字）| `b91487f2` 之後 docs sync chain | ✅ **真修** | CLAUDE.md:67-99 runtime 已標 `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`；CLAUDE_CHANGELOG.md:6-25 W-AUDIT-1 條目；§三 改為「7 日重驗」防線；W-C authorization file `docs/governance_dev/2026-05-08--w_c_lease_router_authorized.md` 存在；AMD §5.4.1 amendment 確認 (`P0-DECISION-AUDIT-1 DONE`)。`[33]/[40]/[42b]` 數字也改為標時間戳。**但 PM 自承「runtime caveat: live authorization file is missing」(WORKLOG:332)** — §三 沒同步這個 NEW-ISSUE。 |
| C-2 | `risk_config_{demo,live,paper}.toml` shadow_mode=true × 3 + `lambda: True` fallback | 0 commit | ❌ **完全未修** | risk_config_demo.toml:246 + live.toml:231 + paper.toml:221 全仍 `shadow_mode = true`；executor_agent.py:224 仍 `(lambda: True)`。TODO L128/L176 自承「F-01 lambda:True removal + final SM-05 authority semantics still block on P0-DECISION-AUDIT-2 operator decision」。**FA push back #2 拍板 PENDING-OPERATOR**。最關鍵 fake-live finding 0% 修復。 |
| C-3 (≈H 1) | (擴) Layer 2 自主推理循環無 trigger | 0 commit | ❌ **未修** | layer2_routes.py:174 仍是唯一 trigger（手動 GUI）；P2-AUDIT-LAYER2-7c 排到「下個 cycle」；TODO `P0-DECISION-AUDIT-5 PENDING-OPERATOR`「Layer 2 GUI-only by design」未拍板。 |
| C-4 (≈H 2) | (擴) openclaw_core 9 模組死代碼 | 0 commit | ❌ **未修** | 14 天 + 24h = 15 天 0 動作；P0-DECISION-AUDIT-5 PENDING-OPERATOR；W-AUDIT-5 sub-tasks 未含 sunset。 |

### High 11 條

| # | 原 finding | Commit hash | Verdict | Evidence |
|---|---|---|---|---|
| H-3 | openclaw_core 9 模組 ~4468 行 Rust 死代碼 | 0 commit | ❌ 未修 | 同 C-4 |
| H-4 | Layer2 cron 無觸發 | 0 commit | ❌ 未修 | 同 C-3 |
| H-5 | 5 ML 訓練腳本 silent-unscheduled (thompson/optuna/cpcv/dl3/weekly_report) | helper_scripts/cron/ml_training_maintenance_cron.sh 新增 (mid-W-AUDIT-4) | 🔄 **半修** | cron script 寫了 5 paths：linucb_trainer / mlde_shadow_advisor / mlde_demo_applier / scorer_trainer / quantile_trainer (WORKLOG:240) — **但這 5 個是不同腳本**！原 finding 5 個是 thompson/optuna/cpcv/dl3/weekly_report，cron 寫的是另外 5 個。可能是 PA 重新評估後降版，但**原 5 個仍 silent-unscheduled**。WORKLOG 反覆「cron not installed」確認 runtime 0 影響。 |
| H-6 | 6 表 0 production INSERT (rl_transitions / promotion_pipeline / symbol_clusters / cpcv_results / ml_parameter_suggestions / bayesian_posteriors) | V068 (commit unclear, mid-W-AUDIT-4) | ❌ **降級假修** | V068 是「reclassification guard / metadata-only / 0 destructive」 — 只 COMMENT 表「retained because Phase4 routes reference this table」。**6 表 row count 沒任何變化（仍 0）**；INSERT 路徑 0 新增；PA fix plan §6 W-AUDIT-4 #3 計畫的「V068-V071 drop dead schema」未執行。**「reclassify retained」是把 finding 從 dead schema 重新標籤為 retained-but-empty，functional gap 沒解**。 |
| H-7 | learning.exit_features.est_net_bps 100% NULL writer 未 deploy | 0 commit | ❌ 未修 | sibling FUP-2 commit `34211ab4` 仍未 merge；TODO `P1-AUDIT-ML-4` 自承「F-09 FUP-2 deploy」remaining。 |
| H-8 | PerceptionPlane validate_for_decision 0 production caller | 0 commit | ❌ 未修 | 14+1 天 0 動作 |
| H-9 | H0_GATE Python singleton 0 production caller | 0 commit | ❌ 未修 | PA fix plan §5 C-3 對話：E3 解釋 Rust h0_gate active；**Python H0_GATE 是孤兒**仍未刪/接。 |
| H-10 | HStateCache + CostEdgeAdvisor env-OFF | 0 commit | ❌ 未修 | TODO `F-cea-env` 在 W-AUDIT-7 remaining；`OPENCLAW_COST_EDGE_ADVISOR=1` 仍未設。 |
| H-11 | CONTEXT.md 11 stale sentence | mid-W-AUDIT-1 docs sync | ✅ 真修 | TODO/WORKLOG 確認 CONTEXT glossary 已加 LG-X / REF-19 / REF-21 / Agent Spine 詞條 |
| H-12 | risk_config_paper.toml shadow_mode=true 死設定 | 0 commit | ❌ 未修 | paper.toml:221 仍 `shadow_mode = true`；同 C-2 |
| (新) F-12 runner.rs 2467 hard violation | mid-W-AUDIT-5a F-12 split | ✅ 真修 | WORKLOG:284-287 — replay_runner.rs 1599→626 LOC + sibling modules；`tests/structure/test_replay_runner_split_static.py` 加 LOC pin。但**注意原 finding 是 runner.rs 2467**，commit 改的是 `replay_runner.rs` 1599 → 626 — **是不同 file**！E5 原報告寫的「runner.rs 2467」可能指 `rust/openclaw_engine/src/replay/runner.rs`，commit 改的是 `bin/replay_runner.rs`。需 PM 對齊。 |

### Medium / Low 14 條

| # | 原 finding | Commit | Verdict |
|---|---|---|---|
| M1 | correlated_exposure_max_pct TOML 漂移 | 0 commit | ❌ 未修 |
| M2 | grafana_data_writer pipeline_bridge=None | 0 commit | ❌ 未修 |
| M3 | Python backtest stub | 0 commit | ❌ 未修 |
| M4 | evolution_engine._engine 來源不明 | 0 commit | ❌ 未修 |
| M5 | V999 migration 命名衝突 | 0 commit | ❌ 未修 |
| M11 | LiveAuthWatcher 5s poll 無 backoff | 0 commit | ❌ 未修 |
| M12 | V001-V022 Guard 覆蓋度未審 | V076 retrofit Guard A for V062/V063/V065 | 🔄 **半修** | V076 只覆蓋 3 個 (V062/V063/V065)，原 finding 是 V001-V022 (22 個)。覆蓋率 14%。 |
| M13 | _SCOUT_WORKER singleton 未登 §九 | 0 commit | ❌ 未修 |
| L1-L8 cosmetic | various | 0 commit | ❌ 未修 |

---

## §3 NEW-ISSUE 清單（修復過程引入的新問題）

### 🆕 NEW-ISSUE-1：LiveDemo pipeline 在 V077 deploy/restart 後停（CRITICAL）

**Evidence**：`.codex/WORKLOG.md:332`：「runtime caveat: live authorization file is missing, so the engine refused to spawn LiveDemo/live at boot and is running demo-only; no manual auth renewal/restoration was performed」

**Root cause**：W-AUDIT-7 GUI checkpoint 後 operator 授權 `restart_all.sh --rebuild --keep-auth` 重啟引擎；V077 columnstore CHECK 撞 Timescale 限制 → hotfix `49ceeb61` → engine-only restart with `--keep-auth`。但 `--keep-auth` 沒做到 — authorization file 不見了，導致 LiveDemo pipeline (HMAC-signed authorization.json 是 Rust 端 spawn pipeline 必經 gate) 在 boot 拒絕啟動。

**Functional impact**：
- 從 5/8 audit 時的「demo + LiveDemo 兩管線真實 fills 流量」→ 現在 demo-only。
- 業務鏈下單從 35% → ~30%。
- **CLAUDE.md §三 / §五 沒記載** — 這個 runtime drift 5/9 已發生但 CLAUDE.md 沒同步。

**FA 立即行動建議**：(1) PM 補 §三 LiveDemo `auth_missing` 狀態；(2) 重生 authorization file via `_write_signed_live_authorization()` python route；(3) RCA `--keep-auth` 為何沒守住。

### 🆕 NEW-ISSUE-2：V068/V070/V071 dead schema fix 全降級為「reclassification guard」（HIGH）

**Evidence**：V068-V071 都是 `COMMENT ON TABLE ... 'W-AUDIT-4 V### reclassified: retained; ...';` 0 destructive；V069 限定 only `observability.scorer_predictions`。

**Root cause**：source audit 重新評估「6 表 0 INSERT」發現大多數表有 route/cron/Rust writer/Agent Spine 引用 → 從 drop 改為 retained。**這個重新評估本身合理**，但：
- 原 FA finding 「6 表 0 production INSERT」**未解** — row count 仍 0。
- 表名改 reclassified retained 不等於 functional gap closure。

**FA 立即行動建議**：澄清這是「降級修法」非「fix」；TODO 應重新分類為「F-11 reclassified pending real INSERT path」而非「DONE」。

### 🆕 NEW-ISSUE-3：cron script 寫了但「cron not installed」反覆（HIGH）

**Evidence**：WORKLOG:241/246/256/262 反覆「cron was not installed or run」；TODO L177「Cron not installed」明文。

**Root cause**：W-AUDIT-4 dispatch 是 source/test only checkpoint，operator 未授權 `crontab -e` 安裝。

**Functional impact**：學習 28% 未動；attribution_chain_ok 24h 0.013% 沒解。

---

## §4 對抗性 Push Back（5 條最關鍵）

### Push Back #1：F-01 是最關鍵 finding，但 24h 0% 修復

修復覆蓋率 ~59% 看似不錯，但**最關鍵的 F-01「shadow_mode TOML × 3 + lambda:True fallback」**（5 agent 共識 CRITICAL，全鏈 fake-live blocker）完全未動。理由是 PENDING `P0-DECISION-AUDIT-2`，但 operator 拍板已遲一天，且 PA push 推薦 (a) demo TOML W-A fail-close。**FA 要求 operator 24h 內拍板**。

### Push Back #2：H-6/H-7「dead schema」修法降級而 TODO 標 DONE 是治理失誤

PA fix plan §6 W-AUDIT-4 計畫「V068-V071 drop dead schema」，**真實落地 V068/V070/V071 都改為「metadata-only reclassification guard」**。TODO 不該標 W-AUDIT-4「ACTIVE / source-closed」而**沒區分**「source-only checkpoint」與「functional fix complete」。FA 要求 W-AUDIT-4 重新評估：是否真解了「6 表 0 INSERT」？答案是「沒」，所以 W-AUDIT-4 不應 close。

### Push Back #3：NEW-ISSUE-1 LiveDemo pipeline 停 — 是修復過程引入的功能回歸

這是**最嚴重的 functional regression**：本來 5/8 audit 時 LiveDemo 有真實 fills 流量，5/9 修復後反而退化。FA 要求：(1) 立即 §三 補 NEW-ISSUE-1 row；(2) 新增 healthcheck `[Xb] live_pipeline_active`；(3) RCA `--keep-auth` 為何失效。

### Push Back #4：W-AUDIT-2 source-only / 0 runtime impact 的「DONE」是樂觀標籤

PA fix plan + TODO 把 W-AUDIT-2 標 DONE 但**自承「Source/test only; no rebuild/restart」**。F-03 lease writer wire 接到 main.rs:657 是真實 source change，但**未經 engine restart 落地** — 真正 runtime 寫 lease_transitions 表還沒發生。W-AUDIT-2 應分兩階段：(2a) source close ✅；(2b) runtime deploy 待。

### Push Back #5：F-12 runner.rs split 改了不同 file — finding 與 commit mismatch

E5 原 finding 「runner.rs 2467 hard violation」指 governance 2000 cap 越過。WORKLOG:284 commit 改的是 `bin/replay_runner.rs` (1599 行) — **不是原 finding 的 runner.rs (2467 行)**。FA 要求 PA / E5 對齊：原 2467 LOC 的 runner.rs 在哪？是否真有 2000 cap violation 仍存？

---

## §5 與 PA fix plan §6 wave closure 對齊

| Wave | PA 計畫 status | TODO 自報 status | FA 真實 verdict |
|---|---|---|---|
| **W-AUDIT-1** docs sync | DONE | DONE | ✅ **真 close**，但 NEW-ISSUE-1 LiveDemo 停同日發生未同步入 §三 = 24h 後就又 stale |
| **W-AUDIT-2** security IMPL | DONE | DONE | 🔄 **source-only close**，runtime 未驗 — Wave 應分 2a source / 2b runtime 兩 phase |
| **W-AUDIT-3** ExecutorAgent fake-live | PARTIAL | PARTIAL | ⚠️ **真實 PARTIAL** — F-17 + F-15 真改，F-01 卡 PENDING-OPERATOR；F-15 e2e test DB row coverage 是 opt-in 默認 early-return |
| **W-AUDIT-4** ML 基座 + dead schema | ACTIVE | ACTIVE | ❌ **降級假修** — V068/V070/V071 reclassification guard；F-08 cron not installed；NEW-ISSUE-2/3。**最具誤導性的 wave**。 |
| **W-AUDIT-5** 性能/結構/CI | ACTIVE | ACTIVE | ✅ **真 progress（部分）** — F-21 strip / F-26 CI / F-27 字典 / F-test-h-state / F-12 replay_runner 都真實落地（但 Push Back #5 file mismatch）|
| **W-AUDIT-6** 策略 + 量化 | NEW | NEW | ⏸ **PENDING-OPERATOR** — 完全未啟 |
| **W-AUDIT-7** AI + GUI/UX | ACTIVE | ACTIVE | ✅ **真 progress（GUI）** — F-30 / F-system-mode-confirm / F-strategy-confirm 都真改。**但 NEW-ISSUE-1 是這個 wave engine restart 過程引入** |

**5 個 P0-DECISION-AUDIT operator 拍板狀態**：
- 1 ✅ DONE / 2 ❌ PENDING / 3 ✅ DONE / 4 ❌ PENDING / 5 ❌ PENDING

---

## FA 最終 Verdict

**業務鏈完整度從 ~58% → ~58%（無實質進展）**：source-level 多有改動但 functional gap（fake-live / 6 表 0 INSERT / 學習進化）一個沒解；NEW-ISSUE-1 反向 dragged LiveDemo 從 35% → 30%。

**對抗性結論**：24h 28 commits 是高 throughput 但**典型 source-only 假進度**：
1. 4 個 critical 中只有 C-1 真修；C-2/C-3/C-4 全 PENDING-OPERATOR 或 0 動作
2. W-AUDIT-2/4 標「DONE / ACTIVE」但運行時影響 0
3. NEW-ISSUE-1 是修復引入的 functional regression
4. NEW-ISSUE-2 「reclassification 降級修法」是 governance failure pattern

**最緊要 24h actions**：
1. operator 立即拍板 `P0-DECISION-AUDIT-2`（解 F-01 fake-live 死鎖）
2. PM 補 CLAUDE §三 NEW-ISSUE-1 LiveDemo pipeline `auth_missing` 狀態 + RCA `--keep-auth`
3. 重新分類 W-AUDIT-4 「ACTIVE」≠「DONE」；6 表 0 INSERT 必另開 functional fix wave
4. W-AUDIT-2 拆 2a source / 2b runtime；2b 必驗 lease_transitions row count > 0

---

**FA VERIFICATION DONE** · ✅ 7 / ⚠️ 4 / ❌ 12 / 🔄 6 / 🆕 3
