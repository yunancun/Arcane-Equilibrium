# 2026-05-09 v2 W-AUDIT-1..7 已 verified-closed 內容歸檔（第二輪）

**歸檔目的**：把第二輪 v2 verification 真 closed 的 finding + 已生效的 W-AUDIT-6 大爆發細節從 active TODO 移出，避免主 TODO 膨脹。

**歸檔範圍**：
- v1 標 ❌ 在 v2 翻 ✅（48 條真修）
- W-AUDIT-6 大爆發 13+ commits 收口細節
- AMD-2026-05-09-02 收口 P0-DECISION-AUDIT-2/4/5 細節
- 6 P0-NEW-ISSUE/VULN 全清細節

**未歸檔（仍 active）**：
- v2 ❌ 66 條（含 W-AUDIT-4 reclassification、6 表 0 INSERT、bb_reversion verdict 等）
- v2 ⚠️ 47 條
- v2 🆕 21 條 NEW-ISSUE
- v2 🔄 3 條

---

## §1 W-AUDIT-1 docs sync v2 closure（CRITICAL 5/5 全 closed）

R4 v2 verdict 從 v1 「2/5 真 closed」翻 **5/5**。

### v1 ❌ → v2 ✅

| Sub-task | v2 Evidence |
|---|---|
| C1 docs/README 補 multi_agent_rework 14 文件 | line 183-196 列 14 條完整 |
| C2 docs/README 補 docs/agents/ 整章 | line 225-231 + CLAUDE.md §十一 對齊 |
| C3 docs/README 補 SCRIPT_INDEX | line 223 + SCRIPT_INDEX 自身列 ~20 條 |
| C4 SPECIFICATION_REGISTER LG-X 補 | line 58-66 LG-X-01..05 完整；LG-X-04 重編對應 LG-4 Supervised-Live；LG-X-05 對應 4 條 LG-5 RFC |
| C5 SM-03/EX-03/ARCH-02/03/AUDIT-13 補 | 全 ✅ Active |

### HIGH 5/6 + MEDIUM 3/5 + 全 v1 NEW × 5 closed
詳見 `srv/docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-09--index_verification_v2.md`

---

## §2 W-AUDIT-2 security IMPL — runtime verified

CC v2 verdict 從 v1 「source-only」翻 **runtime verified**。

| Sub-task | v2 Runtime Evidence |
|---|---|
| F-03 lease writer wired into all 3 active pipelines | Rust `governance_emit::build_bypass_transition_msg()` 真實 IMPL |
| V078 widening `chk_lease_transitions_to_state` | applied + BYPASS row 證明 facade lease bypass path 活躍 |
| Runtime spot-check | `learning.lease_transitions` rows=103；rebuild + rows=103 spot-check（runtime 證實）|
| Test | `governance_bypass_audit.rs` PASS（assert_eq! to_state="BYPASS" + event="non_production_bypass"）|
| Restart | `862e79b7` 部署 |

---

## §3 W-AUDIT-3 F-01 ExecutorAgent fake-live — partial close

### F-01 lambda:True 真實移除（CC + FA + E4 三方核實）

- `executor_agent.py:225`：`self._shadow_mode_provider: Optional[Callable[..., bool]] = shadow_mode_provider`
- grep `lambda:\s*True` in executor_agent.py = **0 命中**
- `_read_shadow_mode()` 顯式 fail-closed 分支（line 770-803）：provider None → `return True` + warning；provider 拋 exception → fail-closed
- pytest 30 passed
- AMD-2026-05-09-02 §2 拍板 shadow_mode=true 是 fail-closed 預設

### 仍 partial：F-15 e2e DB row coverage opt-in；engine restart 後 fail-closed metrics 未驗（W-AUDIT-3 不能標 DONE）

---

## §4 W-AUDIT-5 性能/結構 v2 closure

### F-12 runner.rs 真檔對齊（v1 ⚠️ → v2 ✅）

E5 verified：`replay/runner.rs` 2467→**1167** LOC；sibling `runner_tests.rs` 1299；test `tests/structure/test_replay_runner_split_static.py` LOC pin。Push Back #5 v1 真解決。

### W-AUDIT-5b orjson / deepcopy / ai_budget RwLock / event_consumer split

E5 v2 verified all source/test landed。

---

## §5 W-AUDIT-6 大爆發 — source/test queue closed（QC 11/20 真修）

### 11 個 v1 ❌ → v2 ✅

| # | Finding | Commit | Evidence |
|---|---|---|---|
| 1 | DSR/PBO/CPCV advisory only | `716eb3d6` | promotion_pipeline.py 內 selection_bias fail-closed gate；SelectionBiasPromotionGate composite |
| 2 | per_trade_risk_pct 雙 SSOT | `d65bf617` | kelly_sizer.rs:138 從 RiskConfig.limits.per_trade_risk_pct；4 TOML 統一=0.1 |
| 6 | bb_breakout cooldown 600k vs 300k | `00224d9e` | params.rs:23=300_000；mod.rs:200/201=DEFAULT_COOLDOWN_MS |
| 7 | Kelly tier 8/6/4 hardcoded | `45f1139f` | kelly_sizer.rs young/mature/established_fraction 全 RiskConfig.kelly + validate + tests |
| 8 | fast_track 15%/5%+3σ hardcoded | `8df29e9e` | FastTrackConfig + serde_default + validate；4 TOML [fast_track] section |
| 10 | ma_crossover R:R 結構不對稱 | `51dd5d60` | 4 TOML [per_strategy.ma_crossover] SL=2.5/TP=8.0/TP enforced=true/trail_act=0.6/trail_dist=0.4；R:R 3.2:1 |
| 11 | 無 production VaR/CVaR/EVT | `cc6476dd` | portfolio_var.py 266 行（VaR + CVaR + EVT GPD + 3 stress）；wired into _check_demo_gates `tail_risk:no_evidence` fail-closed |
| 12 | 無 block bootstrap | `cc6476dd` 同 chain | quantile_bootstrap.py Politis-White n^(1/3) + stationary_bootstrap_resample；TailRiskBootstrapResult |

### funding_arb 4 risk_config 全清
`af4942b6 risk: retire funding arb from risk config`：grep `funding_arb` in risk_config*.toml = **0 命中**；strategy_params 三 TOML 仍保留 `[funding_arb]` block (active=false) 為「歷史工件」per ADR-0018 + AMD-2026-05-09-02 §3。

### W-AUDIT-6c portfolio tail risk gate
- portfolio_var.py + cvar.py + LUNA/FTX/COVID 三場景 + PortfolioTailRiskGate fail-closed
- 測試：13+39+153 全 PASS
- E5 bonus 標 W-AUDIT-6c 真實 IMPL

---

## §6 W-AUDIT-7 GUI a11y + LiveDemo restored

### openConfirmModal a11y 真補（A3 NEW-1 closed）
commit `441ff9b5`：common.js:1633 加 `role="dialog" aria-modal="true" aria-labelledby` + tabindex + Esc/Tab focus trap + previousActive.focus 還原 + setTimeout 初始焦點。**A 級實作**，影響 ~10 caller (paper-stop-all/delete-strategy/live-close-position/dust-clear/live-close-anyway)。

### LiveDemo pipeline restored 三層 closure
1. `/api/v1/live/auth/renew` signed route 重簽
2. `restart_all.sh --keep-auth` 加 `warn_keep_auth_missing_authorization()` preflight
3. `[56] live_pipeline_active` healthcheck sentinel
4. RCA：01:11 UTC `manual` sentinel boot 消費 auth.json，後續 --keep-auth 保留已缺失

---

## §7 P0-DECISION-AUDIT 5/5 拍板（AMD-2026-05-09-02 收口）

`docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`（86 行 / 5 章節）+ SPECIFICATION_REGISTER line 18 登記：

| ID | Decision |
|---|---|
| 1 | （v1 已 closed）|
| 2 | Option A：W-A demo fail-closed posture，shadow_mode=true 為標準狀態，shadow_mode=false 須 P0-EDGE-1 + supervised promotion gates |
| 3 | （v1 已 closed）|
| 4 | Option ii：grid 限 ORDIUSDT / ma_crossover 修正 / bb_breakout 1m reject + 5m redesign / funding_arb retire / bb_reversion 配 MA confirmation |
| 5 | Option i + ii：9 個 legacy openclaw_core 模組 sunset / Layer2 manual+supervisor-only by design |

§5 Non-Goals 明文 8 條「不做什麼」邊界（A 級治理紀律）。

---

## §8 6 P0-NEW-ISSUE/VULN 全清

| ID | v2 Closure |
|---|---|
| `P0-NEW-ISSUE-1` LiveDemo auth_missing | 三層 closure（renew + warn + healthcheck）|
| `P0-NEW-VULN-1` launchd plist HIGH | `b658e18c` E3 verified |
| `P0-NEW-VULN-2` lease audit runtime 0 emit HIGH | `e97a333b` + V078 + rows=103 E3 verified |
| `P0-NEW-VULN-3` cookie secure default fail-OPEN MED | `cfadc339` E3 verified |
| `P0-NEW-VULN-4` phase4 dead code INFO | `cfadc339` E3 verified |
| `P0-AUDIT-NEW-LG-X-05` SPEC LG-X-05 缺 | `85804fbd` R4 verified |

---

## §9 16 根原則 + 9 安全不變量 v2 升級

### 16 根原則（v1 11/4/1 → v2 12/4/0）
- 原則 #11 Agent 最大自主：❌→✅（lambda:True 真移除 + AMD §1 Option A 明文「shadow_mode=false 是 promotion state」）
- 原則 #16 組合級風險：⚠️→✅（W-AUDIT-6c VaR/CVaR/EVT promotion gate fail-closed）
- 原則 #10 認知誠實：✅→✅✅（AMD §5 Non-Goals 8 條邊界 + W-AUDIT-1 sync 報告誠實標 partial）

### 9 不變量（v1 7/2/0 → v2 8/1/0）
- 不變量 #2 Lease 必在執行前 acquired：⚠️→✅（V078 + lease_transitions runtime rows=103 證實）

### 5 硬邊界保持 5/0/0 + 預防性硬邊界強化（keep-auth warn）

---

## §10 v1 NEW-ISSUE 收口

| v1 NEW | v2 收口 |
|---|---|
| NEW-ISSUE-1 LiveDemo 停 | ✅ 完整 closure（§6）|
| NEW-ISSUE-2 V068/V070/V071 reclassification 降級 | 🔄 standard 明確化 — P2-AUDIT-VERIFY-3 開單 |
| NEW-ISSUE-3 cron not installed | ❌ F-09 FUP-2 邊際進展（[43] PASS）；F-08 ml_training cron 仍 not installed |
| AI-E NEW × 5 | 部分 closed；ContextDistiller source added |
| E3 NEW-VULN × 4 | ✅ 全 closed |
| MIT NEW × 7 | 部分 closed；feature_baselines row 仍 0；Dream 仍 Foundation only |
| TW NEW × 8 | 部分 closed；docs/README 78→88% |
| R4 NEW × 5 | ✅ 全 closed（含 LG-X 編號 + MIT/BB 表 + archive 索引）|
| A3 NEW × 6 | NEW-1 a11y 真補；其他 5 仍 open |

---

## §11 與 PA fix plan §6 (88 finding) 對齊

| 維度 | 5/8 PA 識別 | 5/9 v1 verification | 5/9 v2 verification |
|---|---|---|---|
| ✅ Verified-FIXED | 88 預期 | 74（23%）| **122（47%）** |
| ⚠️ PARTIAL | -- | 66（21%）| 47（18%）|
| ❌ NOT-FIXED | -- | 120（38%）| 66（25%）|
| 🔄 REGRESSED | -- | 6（2%）| 3（1%）|
| 🆕 NEW-ISSUE | -- | 53（17%）| 21（8%）|
| **Total verification points** | 88 | 319 | **259** |

**結論**：v2 verification 後，74 → 122 真修（+48），❌ 120 → 66（-54）；剩餘 137 條（含 NEW）回流 active TODO 持續處理。

---

**歸檔者**：PM · 2026-05-09 v2 UTC · 對應 active TODO v17 patch
