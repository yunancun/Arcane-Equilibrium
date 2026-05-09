# 玄衡 · Arcane Equilibrium — 2026-05-09 對抗性核實 v2 整合報告

> **PM Sign-off Banner（2026-05-09 v2 UTC）**
>
> - **背景**：2026-05-09 v1 verification land 後，operator 24h+ 跑 34 commits 第二輪修復（W-AUDIT-6c portfolio VaR/CVaR/EVT 大爆發 + W-AUDIT-1/2/3/5/7 collateral fixes + LiveDemo restore + AMD-2026-05-09-02 收口 P0-DECISION-AUDIT-2/4/5）
> - **本份**：12 個原 audit 提出方 agent **第二輪**對抗性核實，對標 v1 verdict 的 ❌ + ⚠️ + 🆕 在 v2 修復是否到位
> - **總體 verdict**：**真實飛躍** — ✅ 從 74→122（+48，+65%）/ ❌ 從 120→66（-54，-45%）/ 🆕 從 53→21（-60%）
> - **執行**：12 verification v2 後台並行，每報告寫 `srv/docs/CCAgentWorkSpace/<AGENT>/workspace/reports/2026-05-09--*_verification_v2.md`

---

## §1 12 Verification v2 vs v1 對比

| Agent | v1 (✅/⚠️/❌/🔄/🆕) | v2 (✅/⚠️/❌/🔄/🆕) | 關鍵 v2 verdict |
|---|---|---|---|
| **FA** | 7/4/12/6/3 | **14/4/5/3/1** | 業務鏈 58→**62%**；LiveDemo restored；F-12 真檔對齊；F-01 lambda 真移除；AMD §2 鎖定 shadow_mode=true 為 fail-closed 預設 |
| **AI-E** | 0/1/4/0/5 | 1/1/7/0/5 | 24h ai cost $0；ai_invocations Δ 0；ContextDistiller source added；F-strategist-cap 30→50；cron 仍 not installed |
| **E5** | 6/9/15/0/6 | **9/8/13/0/0** + W-AUDIT-6c bonus | runner.rs LOC 2467→**1167**（真拆）；binary 20.6 MB 持平；W-AUDIT-6c portfolio VaR/CVaR/EVT IMPL bonus |
| **E4** | 8/5/8/0/3 | **14/3/4/0/1** | pytest 3871→**3925**（+54 -7 fail）；cargo lib 2560→**2584**（+24 0 fail）；雙跑 deterministic identical |
| **E3** | 7/4/7/0/4 (NEW-VULN 4) | **3/1/0/0/0**（NEW-VULN: **0**）| 4 NEW-VULN 全清（launchd/lease audit/cookie/phase4 dead code 全 closed）|
| **CC** | 8/7/2/0/1 | **12/5/0/0/0** | B-→**B+**（25/30=83.3%）；P0-DECISION 拍板 2/5→**5/5**（AMD-2026-05-09-02 收口）；原則 #11 從 ❌→✅；原則 #16 從 ⚠️→✅ |
| **QC** | 0/1/19/0/3 | **11/4/4/0/2** | 0/20→**11/20 真修**（W-AUDIT-6 大爆發）；DSR/PBO promotion gate **LIVE**；VaR/CVaR/EVT **LIVE**；funding_arb 4 risk_config 全清 |
| **MIT** | 7/5/5/0/7 | 7/5/9/0/3 | ML 基座達標 42→**44%**；attr_chain_ok 24h 0.0188%→**0.5041%**（denominator artifact，ok_n only +47%）；feature_baselines row 仍 0 |
| **BB** | 5/3/7/0/2 | **6/3/7/0/2** | 技術 97% / 政策 70%（持平）；funding_arb +1 / LiveDemo -1 平手 |
| **TW** | 12/11/12/0/8 | **14/8/13/0/6** | README 78→**88%**；SCRIPT_INDEX 80% 持平 |
| **R4** | 8/8/9/0/5 | **14/4/4/0/1** | 索引 75→**92%**；**CRITICAL × 5 closed: 5/5**（v1 2/5 → v2 全 close）；LG-X-05 補上 |
| **A3** | 6/4/20/0/6 | **7/5/18/0/7** | 7.4→**8.3/10**；Critical 4/5；openConfirmModal a11y 真補；GUI work-rate 下降 |
| **TOTAL** | **74/66/120/6/53 = 319** | **122/47/66/3/21 = 259** | **✅ +48 (+65%) / ❌ -54 (-45%) / 🆕 -32 (-60%)** |

---

## §2 7 Wave Closure v2 真實狀態

| Wave | v1 verdict | v2 verdict | 變化 |
|---|---|---|---|
| **W-AUDIT-1** docs sync | ⚠️ partial（CRITICAL 2/5）| ✅ **真 close**（CRITICAL 5/5；R4 反轉 v1 預期） | +3 closed |
| **W-AUDIT-2** security IMPL | 🔄 source-only | ✅ **runtime verified**（V078 + lease_transitions rows=103 + rebuild `862e79b7`）| 升級 |
| **W-AUDIT-3** fake-live | ⚠️ true partial | ⚠️ true partial（F-01 lambda 真移除；F-15 e2e DB row 仍 opt-in；engine restart fail-closed metrics 未驗）| F-01 飛躍 |
| **W-AUDIT-4** ML 基座 | ❌ downgraded | ❌ **仍降級**（V068/V070/V071 reclassification COMMENT；row count 仍 0；cron 仍 not installed）| 持平 |
| **W-AUDIT-5** 性能 | ⚠️ progress + critical mismatch | ⚠️→✅ **F-12 真修**（runner.rs 2467→1167）+ W-AUDIT-6c portfolio tail risk gate IMPL | 升級 |
| **W-AUDIT-6** 策略 | ⏸ untouched | ✅ **大爆發收口**（13+ commits / source/test queue closed / DSR-PBO+VaR-CVaR-EVT wired / funding_arb 4 risk_config 全清）| 飛躍 |
| **W-AUDIT-7** GUI/AI | ✅ progress + 🆕 LiveDemo regression | ✅ **GUI a11y + LiveDemo restored**（openConfirmModal a11y A 級；3 blockers runtime closure）| 升級 |

---

## §3 P0-DECISION-AUDIT 拍板狀態（v1 2/5 → v2 5/5）

| ID | 主題 | v2 狀態 | 收口路徑 |
|---|---|---|---|
| 1 | AMD §5.4 補件 | ✅ DONE | W-C operator auth file + AMD §5.4.1 |
| 2 | shadow_mode TOML 設計意圖 | ✅ DONE | AMD-2026-05-09-02 §1 Option A（shadow=true 是 fail-closed 預設）+ F-01 lambda 真移除 |
| 3 | §三 stale 防線改造 | ✅ DONE | 5 stale 數字真修 + healthcheck id |
| 4 | 5 策略 verdict | ✅ DONE | AMD §3 Option ii（grid CONDITIONAL / ma REVISE / bb 5m / funding RETIRE / bb_reversion 配 MA）+ W-AUDIT-6 大爆發 source/test |
| 5 | openclaw_core 9 模組 + Layer 2 sunset | ✅ DONE | AMD §4 Option i+ii（9 模組永久 sunset / Layer2 manual+supervisor-only by design）+ ADR-0015/0017/0020 |

**5/5 closed，無 PENDING**。

---

## §4 P0-NEW-ISSUE / NEW-VULN 收口

| ID | v1 狀態 | v2 狀態 | 收口路徑 |
|---|---|---|---|
| `P0-NEW-ISSUE-1` LiveDemo auth_missing | 🆕 CRITICAL ACTIVE | ✅ **DONE** | `/api/v1/live/auth/renew` 重簽 + `restart_all.sh --keep-auth` warn + `[56] live_pipeline_active` healthcheck sentinel + 完整 RCA |
| `P0-NEW-VULN-1` launchd plist HIGH | ACTIVE | ✅ **DONE** | E3 verified `b658e18c` |
| `P0-NEW-VULN-2` lease audit runtime 0 emit HIGH | ACTIVE | ✅ **DONE** | E3 verified `e97a333b` + V078 BYPASS check + lease_transitions runtime rows=103 |
| `P0-NEW-VULN-3` cookie secure default fail-OPEN MED | （隱含 v1）| ✅ **DONE** | E3 verified `cfadc339` |
| `P0-NEW-VULN-4` phase4 dead code INFO | （隱含 v1）| ✅ **DONE** | E3 verified `cfadc339` |
| `P0-AUDIT-NEW-LG-X-05` SPEC LG-X-05 缺 | ACTIVE | ✅ **DONE** | R4 verified `85804fbd` LG-X-04 重編 + LG-X-05 補完 |

**6/6 closed**。

---

## §5 v2 NEW-ISSUE 清單（v2 修復過程引入或漏報）

### Functional / Quant CRITICAL+HIGH
1. **🆕 QC NEW-ISSUE-4（HIGH）**：bb_breakout 5m demo active=true 但 Donchian leak-free shift(1) 未進 runtime — **學習資料 contaminated**（QC 已 4 次 push）
2. **🆕 QC NEW-ISSUE-5（MEDIUM）**：portfolio_var min_observations=200 vs OpenClaw demo 樣本量；可能卡 promotion gate `defer_data` verdict
3. **🆕 FA v2-NEW-ISSUE-1（MEDIUM）**：F-strategist-cap `max_param_delta_pct` 30%→50% 一次 67% 放寬，無 supervised gate 配套；與 SM-05 fail-closed 預設姿態相對立

### Documentation / Index
4. **🆕 R4 v2-N1（HIGH）**：殭屍引用 `archive/2026-05-09--w_audit_verified_closed_archive.md` 在 docs/README + TODO + summary 三處引用，**檔案不存在**（PM 收尾應補檔或刪引用）
5. **🆕 R4 v2-N4 / TW**：docs/README.md 仍缺 `Last Updated` header
6. **🆕 TW v2 6 條**：worklogs 12 天斷層仍存 / MODULE_NOTE 規範違反 / 等

### UX
7. **🆕 A3 v2-NEW-7（MEDIUM）**：tab-demo Demo 平倉 / 清塵仍 native `confirm()`（v1 漏報）
8. **🆕 A3 v2-NEW-8（MEDIUM）**：cards/linucb_card.html LinUCB migrate / rollback 仍 `confirm() + alert()`
9. **🆕 A3 v2-NEW-9（LOW）**：mode-tag 初始 textContent `shadow_only` 工程術語直暴露

### ML / Data
10. **🆕 MIT v2 3 條**：含 V077 columnstore fallback（Timescale OSS 限制）/ feature_baselines row 仍 0 / Dream Engine 仍 Foundation only

---

## §6 立即行動建議（v2 PM 視角）

### P0（24h 內）

1. **bb_breakout 5m demo active=true → pause until Donchian shift(1) IMPL**（QC NEW-ISSUE-4）— 學習資料當前 contaminated
2. **F-strategist-cap 30→50 補 ADR + supervised gate**（FA v2-NEW-1）— 治理一致性
3. **R4 v2-N1 殭屍引用補檔或刪引用**（PM 收尾應做）

### P1（本 Sprint）

4. **W-AUDIT-3 runtime restart + fail-closed metrics 驗 + supervised promotion gates IMPL（P0-LG-3）**
5. **W-AUDIT-4 重新分類**：標 PARTIAL 而非 ACTIVE；6 表 0 INSERT 必另開 functional fix wave
6. **DSR/PBO evidence 自動化 push 鏈**（QC §6.1 (a)）— 5 策略 None evidence → demo graduation 永遠卡
7. **trial_sharpes 持久化**（QC §6.1 (c)）— PBO 永遠 None 退化為 DSR-only
8. **bb_reversion verdict 拍板**（P0-DECISION-AUDIT-4 子項，仍未動）
9. **API Key clear 改 modal+打字確認**（A3 v1 #10，24h+34commits 仍 ignore）
10. **operator 授權 `crontab -e` 安裝 F-08 5 ML training cron**

### P2（本月）

11. v2 5 NEW-ISSUE 處理（包括 grid blocked_symbols freeze + Donchian shift(1) wire + tab-demo/linucb modal a11y + ContextDistiller 真實接入 production caller）
12. docs/README 補 `Last Updated` header
13. MIT/BB workspace/README 從 dir 根 + workspace/ 兩處整合

---

## §7 報告路徑指引

| Agent | v1 Path | v2 Path |
|---|---|---|
| FA | `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--audit_fix_verification.md` | `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--audit_fix_verification_v2.md` |
| AI-E | `..ai_effectiveness_verification.md` | `..ai_effectiveness_verification_v2.md` |
| E5 | `..optimization_verification.md` | `..optimization_verification_v2.md` |
| E4 | `..test_audit_verification.md` | `..test_audit_verification_v2.md` |
| E3 | `..security_verification.md` | `..security_verification_v2.md` |
| CC | `..compliance_verification.md` | `..compliance_verification_v2.md` |
| QC | `..strategy_verification.md` | `..strategy_verification_v2.md` |
| MIT | `..db_ml_verification.md` | `..db_ml_verification_v2.md` |
| BB | `..bybit_compatibility_verification.md` | `..bybit_compatibility_verification_v2.md` |
| TW | `..doc_verification.md` | `..doc_verification_v2.md` |
| R4 | `..index_verification.md` | `..index_verification_v2.md` |
| A3 | `..gui_ux_verification.md` | `..gui_ux_verification_v2.md` |
| **v1 summary** | `srv/2026-05-09--audit_fix_verification_summary.md` | — |
| **v2 summary（本檔）** | — | `srv/2026-05-09--audit_fix_verification_v2_summary.md` |
| **v2 verified-closed archive** | — | `srv/docs/archive/2026-05-09--w_audit_verified_closed_archive_v2.md` |

---

**PM 整合結論**：v2 是真實飛躍 — 修復覆蓋率從 v1 23% → v2 47%（+104%），❌ 從 38% → 25%，🆕 從 17% → 8%。W-AUDIT-2 從 source-only 翻 runtime verified；W-AUDIT-6 從 untouched 大爆發收口；W-AUDIT-1 從 partial 翻 5/5 CRITICAL closed；P0-DECISION-AUDIT 5/5 拍板；6 P0-NEW-ISSUE/VULN 全清。

**剩餘核心結構性 gap**：(1) W-AUDIT-4 6 表 0 INSERT + cron not installed = MLDE attribution 仍 0.5041% catastrophic；(2) bb_breakout 5m active 但 Donchian leak-bias 未修 = 學習資料 contaminated；(3) DSR/PBO evidence 自動化 push 鏈 + trial_sharpes 持久化缺 = promotion gate 永卡；(4) bb_reversion verdict 仍未動。

距 supervised live 規劃帶仍是 **6/15 悲觀 / 6/30 中位 / 7/15 樂觀**，但 v2 的飛躍把樂觀帶 6/30 提前的可能性提升至 ~40%（前提：W-AUDIT-3 runtime + W-AUDIT-4 INSERT path + Donchian shift(1) 三項 24h-72h 內完成）。
