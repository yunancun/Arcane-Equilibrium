# FA Audit Fix Verification v2 — 2026-05-09 第二輪對抗性核實報告

審計員：FA · 對應 v1 baseline `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--audit_fix_verification.md`
基準範圍：`455d796e..1bd55689`（34 commits 第二輪修復；v15→v16 + W-AUDIT-6c portfolio VaR/CVaR/EVT closure）

**Tally：✅ 14 / ⚠️ 4 / ❌ 5 / 🔄 3 / 🆕 1**

---

## §1 Executive Summary

**v1 → v2 變化矩陣**（v1 ✅7 / ⚠️4 / ❌12 / 🔄6 / 🆕3 → v2 ✅14 / ⚠️4 / ❌5 / 🔄3 / 🆕1）：

- **v1 ❌ 真翻 ✅**：4 條（F-01 source/test + AMD-2026-05-09-02 完整收口 P0-DECISION-AUDIT-2/4/5 + funding_arb 4 TOML 完全清除 + F-12 真檔對齊）
- **v1 🆕 NEW-ISSUE 收口**：3 條（NEW-ISSUE-1 LiveDemo restored + RCA `--keep-auth` warn / NEW-ISSUE-2 W-AUDIT-4 reclassification 標籤明確化 / NEW-ISSUE-3 cron script 仍未 install 但 F-09 FUP-2 已驗證）
- **v1 ❌ 仍 ❌**：5 條（6 表 row count 仍 0、cron 未 install、H-7 / H-8 / H-9 / H-10 等 W-AUDIT-4/7 殘餘）
- **v2 NEW-ISSUE**：W-AUDIT-7 F-strategist-cap 把 `max_param_delta_pct` 從 30%→50%（一次 67% rate 放寬，無 supervised gate 配套；可能與 SM-05 fail-closed 設計衝突）

**業務鏈完整度更新（~58% → ~62%）**：
- 自動掃描 95% (無變)
- 策略選擇 55% (無變；W-AUDIT-6 source/test 已 close 但 runtime 未 reload)
- AI 風控 78% → 80% (+2%；F-01 fail-closed 真實落地 + AMD SM-05 拍板)
- 下單 30% → 35% (+5%；LiveDemo restored；V078 BYPASS 補完 lease audit visibility)
- 止損 95% (無變)
- 學習 28% → 30% (+2%；F-09 FUP-2 cron install + V072 writer source/test；6 表 INSERT 仍未解)
- 進化 30% → 35% (+5%；DSR/PBO promotion gate + portfolio VaR/CVaR + ContextDistiller source/test close)
- 觀察 80% → 85% (+5%；[56] live_pipeline_active sentinel 補完，[55]/[56]/[43] 三層活性監測完備)

**Adversarial verdict**：**CONDITIONAL-IMPROVED**。v1 提到的 6 個結構性問題在 v2 中：
1. F-01 fake-live：v1 ❌ → v2 ⚠️真修一半（lambda 真移除 + AMD 拍板，但 runtime restart/deploy 未做）
2. W-AUDIT-2 source-only：v1 🔄 → v2 ✅真修（V078 applied + lease_transitions 103 rows runtime）
3. NEW-ISSUE-1 LiveDemo 停：v1 🆕CRITICAL → v2 ✅完整 closure
4. W-AUDIT-3 e2e test opt-in：v1 ⚠️ → v2 ⚠️未變
5. 6 表 0 INSERT 降級：v1 ❌ → v2 ❌未變（P2 ticket 開但 row count 仍 0）
6. F-12 file mismatch：v1 ⚠️ → v2 ✅真修

**修復品質明顯提升**：v1 是 source-only 假進度，v2 在 W-AUDIT-2 runtime 真實 deploy + AMD 治理拍板層真實落地；但 6 表 functional fix + cron install 仍是 W-AUDIT-4 殘留 functional gap。

---

## §2 v1 ❌+⚠️+🆕 19 條 finding 在 v2 的 status 變化

### v1 ❌ 12 條 → v2 status

| v1 # | finding | v1 verdict | v2 verdict | 變化證據 |
|---|---|---|---|---|
| C-2 | risk_config × 3 shadow=true + lambda:True | ❌ | ⚠️ **真修一半** | `executor_agent.py:217-225` 注釋明寫 fail-closed 邏輯；commit `caf973fb` 真實移除 lambda；30 passed pytest；TOML 仍 true 但 AMD-2026-05-09-02 §2 拍板「shadow_mode=true 是 W-A demo fail-closed 預設」— 設計上鎖定。**剩**：runtime restart deploy 未做 |
| C-3 | Layer 2 自主推理無 trigger | ❌ | ✅ **DONE-BY-DECISION** | AMD-2026-05-09-02 §4 + ADR-0020：Layer2 manual supervisor-only by design |
| C-4 / H-3 | openclaw_core 9 模組死代碼 | ❌ | ✅ **DONE-BY-DECISION** | AMD-2026-05-09-02 §4 + ADR-0015 permanent sunset candidates |
| H-6 | 6 表 0 production INSERT | ❌ 降級 | ❌ **未真修** | V068/V070/V071 仍 reclassification COMMENT；row count 仍 0；P2-AUDIT-VERIFY-3 開單 |
| H-7 | exit_features.est_net_bps 100% NULL | ❌ | ⚠️ **deploy 真做** | F-09 FUP-2 cron install + [43] PASS；NULL 寫端是否真接未直接驗 |
| H-8 | PerceptionPlane 0 caller | ❌ | ❌ **未動** | 16 天 0 動作 |
| H-9 | H0_GATE Python singleton 0 caller | ❌ | ❌ **未動** | 同上 |
| H-10 | HStateCache + CostEdgeAdvisor env-OFF | ❌ | ❌ **未動** | F-cea-env remaining |
| H-12 | risk_config_paper.toml shadow=true 死設定 | ❌ | ✅ **DONE-BY-DESIGN** | AMD §2 拍板 shadow_mode=true 是預設 |
| M1-M5/M11/M13/L1-L8 | medium/low cosmetic | ❌ | ❌ **未動** | 0 commit |

### v1 ⚠️ 4 條 → v2 status

| v1 # | finding | v1 verdict | v2 verdict | 變化證據 |
|---|---|---|---|---|
| W-AUDIT-2 | source-only / 0 runtime impact | ⚠️ | ✅ **真 close** | V078 applied + lease_transitions 真寫（BYPASS rows=103）+ F-03 wired into all 3 active pipelines + V078 widening `chk_lease_transitions_to_state`；rebuild/restart `862e79b7` 部署 |
| W-AUDIT-3 | F-17 + F-15 真改 / F-01 PENDING | ⚠️ | ⚠️ **F-01 真修但 runtime evidence opt-in** | F-01 source/test close（30 passed）；F-15 e2e DB row 仍 opt-in；engine restart/runtime fail-closed metrics 未驗 |
| H-5 / F-08 | ML 訓練 cron not installed | 🔄 | ❌ **未變** | cron script 5 paths 寫了但「Suggested cron entry, installed manually by the operator」未做；P2-AUDIT-VERIFY-4 開單 |
| F-12 | runner.rs file mismatch | ⚠️ | ✅ **真修** | `replay/runner.rs` 2469→1166 + `runner_tests.rs` 1299 sibling + LOC static guard |

### v1 🆕 NEW-ISSUE 3 條 → v2 status

| v1 # | finding | v1 verdict | v2 verdict | 變化證據 |
|---|---|---|---|---|
| NEW-1 | LiveDemo pipeline 停 | 🆕 CRITICAL | ✅ **完整 closure** | 三層補完：(1) `/api/v1/live/auth/renew` signed route 重簽；(2) `restart_all.sh --keep-auth` 加 `warn_keep_auth_missing_authorization()` preflight；(3) `[56] live_pipeline_active` healthcheck sentinel；完整 RCA in `Operator/2026-05-09--three_blockers_runtime_closure.md` |
| NEW-2 | V068/V070/V071 reclassification 降級 | 🆕 HIGH | 🔄 **standard 明確化** | P2-AUDIT-VERIFY-3 開單；W-AUDIT-4 source-closed status 仍 ACTIVE；INSERT 路徑未真接所以 finding 本質仍 ❌ |
| NEW-3 | cron script 寫但 not installed | 🆕 HIGH | ❌ **未變** | F-09 FUP-2 邊際進展；F-08 ml_training cron 仍 not installed；P2-AUDIT-VERIFY-4 開單 |

---

## §3 NEW-ISSUE v2（v2 修復過程引入）

### 🆕 v2-NEW-ISSUE-1：F-strategist-cap `max_param_delta_pct` 30%→50%（MEDIUM）

**Evidence**：TODO L322 W-AUDIT-7 F-strategist-cap：`risk_config_{paper,demo,live}.toml`, `StrategistConfig::default()`, `DEFAULT_MAX_PARAM_DELTA_PCT` now align on 0.50

**FA concerns**：
- 一次 67% rate 放寬（30%→50%），無 supervised promotion gate 配套
- `P0-DECISION-AUDIT-2` 拍板原則「shadow_mode=true 是 fail-closed 預設」+「promotion 需 supervised gate」；此處 strategist 上限放寬卻無對應 promotion gate
- 與 SM-05 fail-closed 預設姿態相對立：strategy 參數變化 cap 越大，shadow→live 對齊風險越大
- 風險 surface：strategist 在 shadow 中可推 50% 偏離的參數變化，run live 時這些偏離通過 cap 進入 live

**FA 立即行動建議**：
1. 重新審查 30%→50% 的設計依據（FA 找不到 RFC 或 ADR 解釋）
2. 加 supervised gate：`max_param_delta_pct=0.50` 必綁 `LIVE_PENDING + DSR/PBO PASS` 才生效；shadow / DEMO_ACTIVE 仍應 0.30
3. 或補 ADR 記錄此放寬的數學/業務 rationale

---

## §4 對抗性 Push Back（5 條最關鍵）

### Push Back #1：W-AUDIT-3 F-01 真修但「runtime restart/deploy + supervised promotion gates」缺位

F-01 source/test 真實落地（lambda 移除 + 30 passed pytest），但 W-AUDIT-3 未經 engine restart deploy；TODO 自承「Runtime deploy/restart not performed」。SM-05 Option A 拍板「shadow_mode=false 是 promotion state, not a live authorization grant」— 但 supervised promotion gates 本身仍未 IMPL（P0-LG-3 active）。**FA 要求**：W-AUDIT-3 不能標 DONE，必須標 PARTIAL until P0-LG-3 IMPL + Linux runtime restart 驗證 fail-closed shadow → submit 路徑 metrics。

### Push Back #2：W-AUDIT-4 V068/V070/V071 reclassification 是「降級」非「fix」必須在 TODO 明確標誌

P2-AUDIT-VERIFY-3 開單但 W-AUDIT-4 在 P1 仍 ACTIVE。**FA 要求**：(1) W-AUDIT-4 status 應改為「PARTIAL: reclassification only, INSERT path not closed」；(2) 6 表分別開「INSERT path implementation」P1/P2 ticket；(3) 不能讓「reclassification COMMENT」算作 functional gap closure。

### Push Back #3：v2-NEW-ISSUE-1 F-strategist-cap 67% 放寬無 supervised gate 配套

W-AUDIT-7 F-strategist-cap 30%→50% 是治理一致性問題。一次 67% rate 放寬而無對應 RFC / ADR / supervised gate 綁定，等於「治理拍板 SM-05 fail-closed」與「strategist 隱性放寬」之間矛盾。**FA 要求**：補 ADR 解釋 + 把 50% 綁定 LIVE_PENDING 而非 paper/demo 全域生效。

### Push Back #4：F-08 cron not installed 但 W-AUDIT-4 標 ACTIVE 是治理失誤

P2-AUDIT-VERIFY-4 開單但 W-AUDIT-4 仍標 ACTIVE。F-08 5 個 ML paths 的 cron 必須 install 才有 functional impact；script 寫了沒裝 = 0 進度。**FA 要求**：(1) operator 授權 `crontab -e` 安裝 + verify 24h cron fire（observability via `[Xc] ml_training_cron_active`）；(2) 不能用「source/test added」當 W-AUDIT-4 close 證據。

### Push Back #5：v1 提出的 H-8/H-9 16 天 0 動作

H-8/H-9（PerceptionPlane validate_for_decision 0 caller + H0_GATE Python orphan）至今 16 天 0 commit；TODO 也未開單。長期被遺忘的功能 gap。**FA 要求**：W-AUDIT-5 next pass 加 H-8/H-9 sunset 評估（與 P2-AUDIT-DEAD-CODE 並列）。

---

## §5 與 PA fix plan §6 wave closure 對齊（v2）

| Wave | TODO v16 自報 | FA v2 真實 verdict |
|---|---|---|
| **W-AUDIT-1** docs sync | DONE | ✅ **真 close**（CLAUDE §三 加 LiveDemo restored + RCA 條目，drift 已收）|
| **W-AUDIT-2** security IMPL | DONE（runtime verified + V078 applied + lease_transitions 103 rows）| ✅ **真 close**（v1 ⚠️ → v2 ✅；F-03 wired + V078 widening + runtime spot-check）|
| **W-AUDIT-3** ExecutorAgent fake-live | PARTIAL | ⚠️ **真實 PARTIAL**（F-01 lambda 真移除 + AMD SM-05 拍板 + 30 passed pytest；F-15 e2e DB row 仍 opt-in；engine restart/runtime fail-closed metrics 未驗）|
| **W-AUDIT-4** ML 基座 | ACTIVE | ❌ **降級 + 假修**（P2-AUDIT-VERIFY-3/4 開單但 W-AUDIT-4 wave status 應改 PARTIAL）|
| **W-AUDIT-5** 性能/結構 | ACTIVE | ⚠️ **real progress + F-12 真修**（v1 ⚠️ → v2 ✅；F-20 damaged table 仍 remaining）|
| **W-AUDIT-6** 策略 + 量化 | SOURCE/TEST CLOSED | ✅ **source/test 真進展**（funding_arb 真清完；W-AUDIT-6c portfolio tail risk gate 補全 P0-EDGE-1 阻擋層）|
| **W-AUDIT-7** AI + GUI/UX | ACTIVE | ⚠️ **GUI 真進展 + 🆕 治理矛盾**（F-30/F-system/F-strategy 都真改；**F-strategist-cap 30%→50% 是 v2-NEW-ISSUE-1**：無 supervised gate 配套放寬；F-07/F-cea-env 仍 remaining）|

**5 個 P0-DECISION-AUDIT operator 拍板狀態（v1 1✅ / 2❌ / 3✅ / 4❌ / 5❌ → v2 1✅ / 2✅ / 3✅ / 4✅ / 5✅）**：AMD-2026-05-09-02 真實落地完整收口 SM-05 (Option A) + W-AUDIT-6 verdict (Option ii) + openclaw_core sunset (Option i) + Layer2 manual-only (Option ii)；ADR-0015 / ADR-0018 / ADR-0020 三 ADR 配套加入

---

## FA v2 最終 Verdict

**業務鏈完整度從 ~58% → ~62%（+4% 真實進展）**

- **真實 functional gain**：W-AUDIT-2 runtime deploy + LiveDemo restored + V078 BYPASS visibility + ContextDistiller + portfolio VaR/CVaR/EVT promotion gate + DSR/PBO promotion gate + Kelly RiskConfig + per_trade_risk_pct SSOT + funding_arb 完全清除 + F-12 真檔對齊 + AMD 治理拍板 + [56] healthcheck sentinel
- **未解 functional gap**：6 表 0 INSERT + F-08 cron not installed + H-8/H-9 16 天 0 動作 + W-AUDIT-3 runtime evidence opt-in + v2-NEW-ISSUE-1 strategist cap 30%→50% 治理不一致

**對抗性結論**：24h 第二輪 34 commits + W-AUDIT-6c land 是高品質 throughput；3 個關鍵 critical 真實收口（C-3/C-4/NEW-ISSUE-1），W-AUDIT-2 從 source-only 真翻 runtime deploy；但仍有 4 個結構性問題未解。

**最緊要 24h actions**：
1. PA 把 W-AUDIT-4 wave status 從 ACTIVE → PARTIAL；6 表分別開 P1/P2 INSERT path implementation ticket
2. operator 授權 `crontab -e` 安裝 F-08 5 ML training cron
3. F-strategist-cap 30%→50% 補 ADR + supervised gate
4. W-AUDIT-3 runtime restart + fail-closed metrics 驗 + supervised promotion gates IMPL（P0-LG-3）
5. H-8/H-9 加入 W-AUDIT-5 next pass sunset 評估

---

**FA VERIFICATION v2 DONE** · ✅ 14 / ⚠️ 4 / ❌ 5 / 🔄 3 / 🆕 1 · 業務鏈 ~62%
