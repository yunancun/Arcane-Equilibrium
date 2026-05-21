# 玄衡 · Arcane Equilibrium — 2026-05-09 對抗性核實 v3 整合報告

> **PM Sign-off Banner（2026-05-09 v3 UTC）**
>
> - **背景**：v2 verification land 後 operator 推 5 commits（`faf2d131..da2aba11`）+ PA 自寫 architectural redesign report（5 root cause / 5 cluster / 5 R-1..R-5 升級藍圖）
> - **本份**：13 個 agent 第三輪對抗性核實（12 verification + PA self-adversarial integration with work plan judgment）
> - **總體 verdict**：**架構 inflection point** — operator 已採納 PA R-1 升級為 W-AUDIT-8a SPEC PHASE + 新建 W-AUDIT-9 Graduated Canary Foundation；PA fix plan v2 給出 **DUAL-TRACK** 結構（Track W 7 wave + Track A 9 wave / ~360-420h / 6-12w）
> - **執行**：13 verification 後台並行，每報告寫 `srv/docs/CCAgentWorkSpace/<AGENT>/workspace/reports/2026-05-09--*_v3.md` + PA fix plan v2

---

## §1 13 Verification v3 vs v2 對比

| Agent | v2 (✅/⚠️/❌/🔄/🆕) | v3 (✅/⚠️/❌/🔄/🆕) | 關鍵 v3 verdict |
|---|---|---|---|
| **FA** | 14/4/5/3/1 | 4/5/6/3/1 | 業務鏈 62→**63%**；PA redesign **AGREE**；W-AUDIT-3/4/5/7 維持 partial；EX-06 §6.3「自动进入 live」spec drift 揭發 |
| **AI-E** | 1/1/7/0/5 | 5/2/0/0/5 | 24h ai cost $0；ai_invocations Δ 0；strategist skill 是 LLM-driven 但 0 invocation；PA **PARTIAL AGREE** |
| **E5** | 9/8/13/0/0 | 5/4/1/0/0 | PA **PARTIAL**；**strategist LOC PA 引「45000」實際 799 LOC（錯 56x）**；R-1+R-2+R-3 重構 ~9000 LOC / 真估 17-19 sprint vs PA 8-10（樂觀 2x）|
| **E4** | 14/3/4/0/1 | **5/1/0/0/0** | pytest 3925→**3961 (+36)** / cargo 2584→**2586 (+2)**；5/5 sibling test 真實到位；雙跑 deterministic identical |
| **E3** | 3/1/0/0/0 | 5/0/0/0/3 INFO+LOW | NEW-VULN: **0**；PA 安全 verdict **ACCEPT WITH 7 HARD-PRECON**；3 governance promotion endpoints 全 require_operator + require_scope |
| **CC** | 12/5/0/0/0 | **14/4/0/0/1** | B+→**A-（27/30 = 90.0%）**；PA redesign **ACCEPT-WITH-CONDITIONS**（5 條 must）；16 原則 13/3/0；9 不變量 8/1/0 |
| **QC** | 11/4/4/0/2 | 3/2/0/0/4 | PA **PARTIAL AGREE**；5 alpha source 中**只 2 高可行**（funding/OI）+ 1 demo 不可行（basis 同 funding_arb 限制）+ 2 半衰期 mismatch（orderflow/liquidation）|
| **MIT** | 7/5/9/0/3 | 1/3/11/0/2 | ML 基座 44% 持平；attr_chain_ok 24h **1.0857%**（real root cause = label_close_tag NULL 98.9%）；**V079 完全未 apply**（_sqlx_migrations max=78）|
| **BB** | 6/3/7/0/2 | 7/3/7/0/4 | 技術 97% / 政策 70% 持平；Alpha Surface Bundle **MEDIUM**；**Bybit V5 WS 沒「L25」levels（PA spec 寫錯）**；liquidation_pulse 4 weeks ago deleted |
| **TW** | 14/8/13/0/6 | 1/3/17/0/7 | README 88% / SCRIPT_INDEX 78%；5 commits 期間 doc sync 完全停滯；PA redesign 應升 **ADR + Amendment + Spec doc 三層登記** |
| **R4** | 14/4/4/0/1 | 8/4/6/0/3 | 索引 92→**64% 急速回退**（5 commits 期間 0/30+ 新文件登記）；PA redesign 應建 **ADR-0021 + ARCH-04 + 索引 + CONTEXT 5 詞條 + AMD-2026-05-09-03/04** |
| **A3** | 7/5/20/0/7 | 7/5/20/0/7 | 8.3→**8.0/10**；GUI work-rate 急降；PA redesign GUI 影響 **HIGH**；建議新 **2 tab**（Alpha Sources + Hypothesis Lab）→ 13-tab 升 15-tab |
| **PA**（self-adversarial） | — | DUAL-TRACK | **是否重 plan: DUAL-TRACK**；新 wave 數 **16**（Track W 7 + Track A 9）；增量工時 **~360-420h** / 6-12w |
| **TOTAL** | — | **65/39/84/3/39 = 230** | — |

---

## §2 13 Verification 整合 4 大關鍵發現

### A. PA Redesign 跨 agent 共識 — **AGREE 但有條件**

| Agent | PA verdict |
|---|---|
| FA | AGREE |
| QC | PARTIAL AGREE（5 alpha 中 2 高可行）|
| MIT | PARTIAL AGREE（attribution real root 1-day fix 比 R-3 短）|
| E5 | PARTIAL（LOC 錯 56x；sprint 樂觀 2x）|
| E3 | ACCEPT WITH 7 HARD-PRECON |
| CC | ACCEPT-WITH-CONDITIONS（5 條 must）|
| AI-E | PARTIAL AGREE |
| BB | CONDITIONAL APPROVE（Alpha Surface MEDIUM）|
| TW | 應升 ADR + AMD + Spec doc 三層登記 |
| R4 | 必建 ADR-0021 + ARCH-04 + CONTEXT 5 詞條 |
| A3 | GUI HIGH 影響，需新 2 tab |
| **共識** | **DUAL-TRACK 採納，但 R-1 spec 必修 3 條（PA spec 不準）+ ADR/AMD/Spec doc 必補**

### B. **真實 attribution root cause v3 第一次定位**（MIT 重大發現）

- v1 v2 都認為是 wiring bug 或 V068 reclassification
- v3 MIT 直查：**attr_chain_ok 24h 1.0857%（76/7000）；real root cause = `label_close_tag` NULL 98.9%**
- **修法 1-day fix**（比 PA R-3 Hypothesis Pipeline 4-6 sprint **短得多**）
- 應立即升 P0 「label_close_tag writer fix」前置於 R-3

### C. 5 commits source-only 仍是 systemic 模式 — runtime apply 全 outstanding

- V079 migration **完全未 apply 到 PG**（_sqlx_migrations max=78；MIT 直查）
- ml_training_maintenance_cron.sh **未 install in crontab**（3 天 0 進展）
- engine 仍跑 5/8 binary（**不含 Donchian fix**；E5 揭發）
- W-AUDIT-2 V078 是 v2 **唯一真活躍 runtime 進步**（lease_transitions BYPASS 24h 7955→11133 +40%）

### D. PA spec 錯誤需修（3 條 BB-side fact-check）

- **L25 不存在**：Bybit V5 WS levels = 1/50/200/1000；PA spec「L25/L50」必改 L50/L200
- **liquidation_pulse 4 weeks ago deleted**：PA 沒提；R-1 IMPL 需 +1 sprint revert
- **basis 沒分 observation vs execution**：Demo 限 observation；execution 需 mainnet（同 funding_arb v2 retire 限制）

---

## §3 PA Fix Plan v2 — DUAL-TRACK 結構

**operator 已採納部分 PA R-1**（在 PA 寫 v2 plan 過程中已 push 動作）：
- 新建 **W-AUDIT-8a「Alpha Surface Foundation」SPEC PHASE**（CLAUDE.md §三 已加 row + `docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md`）
- 新建 **W-AUDIT-9「Graduated Canary Foundation」**（AMD-2026-05-09-03 起，supersedes AMD-02 §2 binary fail-closed default → 5-stage graduated canary）

### Track W — 收 v2 outstanding（~92h / 6-8 weeks）

| Wave | 內容 |
|---|---|
| W-AUDIT-3b | ExecutorAgent runtime smoke + fail-closed metrics |
| W-AUDIT-4b | V079 DB apply + cron install + label_close_tag writer fix（**MIT v3 真實 root cause**）|
| W-AUDIT-6c | portfolio tail risk gate runtime apply |
| W-AUDIT-6d | 5 策略 verdict IMPL maintenance |
| W-AUDIT-7c | API Key clear modal + Settings 拆 sub-tab + GUI a11y 補齊 |
| W-AUDIT-1d | docs/README index sync + ADR-0021 草擬 |
| W-AUDIT-5b | H-8 H-9 sunset + runner.rs split bin/server-side |

### Track A — Alpha Source Architecture 升級（~270-330h / 6-12 weeks）

| Wave | 內容 |
|---|---|
| W-AUDIT-8a | Alpha Surface Foundation SPEC PHASE（已啟動）|
| W-AUDIT-9 | Graduated Canary Foundation（已啟動，5-stage canary）|
| W-AUDIT-8b..8g | R-1 Alpha Surface IMPL + R-2 Strategist scope expansion + R-3 Hypothesis Pipeline + R-4 Per-alpha-source promotion + R-5 Spec-as-Code |
| W-ARCH-3 | Spec drift 收口（EX-06 §6.3 自动进入 live + LG-X-02..05 supersedes 標記）|

### 關鍵協調風險

W-AUDIT-9 T3 改 `executor_config_cache.py` + `_read_shadow_mode` stage-aware 與 Track W W-AUDIT-3b ExecutorAgent runtime smoke 衝突中-高，**必須 W-AUDIT-3b 先 land**。

### 4-agent consensus 數學論證（PA 引）

22 fail-closed defaults 累加 P(全 PASS) ≈ 1e-3 死循環 = P0-EDGE-1 雞蛋死循環是 demo 環境 stationary fixed point。

### 最早 supervised live

| 帶 | 機率 | 條件 |
|---|---:|---|
| 6/15 樂觀 | ~40% | W-AUDIT-9 IMPL land 後 P0-EDGE-1 evidence collection 路徑首次真實 active |
| 6/30 中位 | ~40% | Track A Stage 1+2 通過 + Track W 全收 |
| 7/15 悲觀 | ~20% | label_close_tag fix 延後 + R-1 spec 修錯 + W-AUDIT-9 卡 |

---

## §4 立即行動建議（PM 視角）

### P0（24-48h 內）

1. **MIT v3 揭發：label_close_tag NULL 98.9% writer fix**（1-day fix vs PA R-3 4-6 sprint，**最高 ROI**）
2. **V079 DB apply**（48227607 source 已落但 _sqlx_migrations max=78）
3. **operator 授權 `crontab -e` 安裝 ml_training_maintenance_cron**（3 天 0 進展）
4. **PA spec 修 3 條**（L25→L50 / liquidation revive / basis observation-only）
5. **建 ADR-0021 + ARCH-04 + CONTEXT 5 詞條 + AMD-2026-05-09-03/04**（R4/TW 共識）
6. **engine restart**（embed Donchian fix + W-AUDIT-9 graduated canary + 多 commits 落地）

### P1（本 sprint）

7. **W-AUDIT-3b 先 land**（avoid W-AUDIT-9 T3 衝突）
8. **risk_config_live.toml max_param_delta_pct 0.50→0.20**（QC NEW-V3-1 fail-closed 政策）
9. **donchian() legacy export 加 #[deprecated]**（QC NEW-V3-3）
10. **API Key clear modal**（A3 #10，48h+5commits 仍未動）
11. **governance-tab.js 兩個 confirm() 改 openConfirmModal**（A3 v2 漏報）
12. **W-AUDIT-8a SPEC PHASE 啟動**（已建 doc，需 R-1 spec 完整化）

### P2（本月）

13. v3 5 NEW-ISSUE 處理（cron install / 6 表 INSERT path / dynamic_block_threshold / GUI surface for freeze + promotion evidence / Alpha Sources tab）
14. R-2 + R-3 IMPL（Strategist scope expansion + Hypothesis Pipeline）

---

## §5 報告路徑指引

| Agent | v3 Path |
|---|---|
| FA | `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--audit_fix_verification_v3.md` |
| AI-E | `..ai_effectiveness_verification_v3.md` |
| E5 | `..optimization_verification_v3.md` |
| E4 | `..test_audit_verification_v3.md` |
| E3 | `..security_verification_v3.md` |
| CC | `..compliance_verification_v3.md` |
| QC | `..strategy_verification_v3.md` |
| MIT | `..db_ml_verification_v3.md` |
| BB | `..bybit_compatibility_verification_v3.md` |
| TW | `..doc_verification_v3.md` |
| R4 | `..index_verification_v3.md` |
| A3 | `..gui_ux_verification_v3.md` |
| **PA fix plan v2** | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_audit_pa_fix_plan_v2.md` |
| **v3 summary（本檔）** | `srv/2026-05-09--audit_fix_verification_v3_summary.md` |
| **v3 verified-closed archive** | `srv/docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md` |

---

**PM 整合結論**：v3 是**架構 inflection point** — 5 commits 真實 cover P0-V2-NEW-1/2/3 但 source-only；MIT 第一次定位 attribution real root cause（label_close_tag NULL 98.9%，1-day fix）；BB 揭發 PA spec 3 條錯誤（L25/liquidation/basis）；operator 已採納 PA R-1 啟動 W-AUDIT-8a + W-AUDIT-9。PA fix plan v2 給 **DUAL-TRACK**（Track W ~92h + Track A ~270-330h / 6-12w）。

**v2 → v3 變化**：
- 修復覆蓋率：v2 47% → v3 28%（**因 v3 揭發更多 outstanding，v2 高估**）
- ❌ 從 25% → 37%（v3 暴露真 outstanding）
- 🆕 從 8% → 17%（PA redesign 引入新對齊任務）

**距 supervised live**：6/15 樂觀(~40%) / 6/30 中位(~40%) / 7/15 悲觀(~20%)，基本同 v2。Track A W-AUDIT-9 IMPL land 後 P0-EDGE-1 evidence collection 路徑首次真實 active。
