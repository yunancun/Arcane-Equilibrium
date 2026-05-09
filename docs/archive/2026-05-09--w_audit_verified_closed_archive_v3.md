# 2026-05-09 v3 W-AUDIT-1..7 已 verified-closed + PA Redesign 整合內容歸檔

**歸檔目的**：v3 對抗性核實後真 closed 的 finding + PA fix plan v2 DUAL-TRACK 結構 + 5 commits 真實 cover 細節從 active TODO 移出。

**未歸檔（仍 active）**：
- v3 ❌ 84 條（含 W-AUDIT-4 V079 未 apply + cron 未 install + label_close_tag NULL 98.9%）
- v3 ⚠️ 39 條
- v3 🆕 39 條
- 16 新 wave（Track W 7 + Track A 9）

---

## §1 5 Commits 真實 cover 細節

| Commit | 對應 P0-V2-NEW | 真實 cover | runtime apply |
|---|---|---|---|
| `ad14db07` | P0-V2-NEW-1 Donchian leak-bias | ✅ IndicatorEngine 已用 donchian_prior；bb_breakout 自動拿 leak-free | ❌ engine 仍跑 5/8 binary |
| `c2ab7b1a` | P0-V2-NEW-2 strategist cap | ⚠️ source 真寫但**選 freedom-not-gate 路徑**；無 supervised gate；無 ADR | ❌ source/test only |
| `48227607` | P0-V2-NEW-3 DSR/PBO evidence | ✅ source/test：promotion_evidence producer 完整 wire；trial_sharpes 持久化 | ❌ V079 完全未 apply（_sqlx_migrations max=78）|
| `c081029d` | QC NEW-1 selection bias | ✅ 17+4 cells frozen + counterfactual.py 真跑；治標非治本 | ⚠️ JSON freeze + audit 真跑；無 dynamic_unblock_check |
| `da2aba11` | F-08 cron scope | ⚠️ source 修 scope mismatch；audit jobs 真實 IMPL；但 cron **未 install** | ❌ crontab installation pending |

**結構性觀察**：5/5 commits 全 source/test only；延續 v2「打 source 不打 deploy」模式。

---

## §2 v3 真 closed Finding（v2 ❌ → v3 ✅）

### CC v3 升級

| 維度 | v2 → v3 |
|---|---|
| 16 根原則 | 12/4/0 → **13/3/0**（#10 ✅✅✅ / #15 ✅✅）|
| 9 安全不變量 | 8/1/0 → 8/1/0（不變）|
| 5 硬邊界 | 5/0/0 → 5/0/0（不變）|
| compliance score | B+ (25/30) → **A- (27/30 = 90.0%)** |

### E4 v3 升級

| 引擎 | v2 → v3 |
|---|---|
| pytest control_api_v1 | 3925/3 → **3961/3**（+36 PASS）|
| cargo lib | 2584/0 → **2586/0**（+2 PASS）|
| 雙跑 deterministic | identical |

### E3 v3

NEW-VULN: 0 → 0 持平
3 governance promotion endpoints 全 require_operator + require_scope ✅
V079 4 fail-closed CHECK constraints（NaN/Inf rejection + engine_mode whitelist）✅
558 LOC `promotion_evidence.py` 100% parameterized SQL ✅

### lease_transitions BYPASS 24h（V078 唯一真活躍）

24h 7955 → 11133 = **+40% growth**（仍 ~33-46/min steady）

---

## §3 12 Verification 跨 agent PA Redesign Verdict

| Agent | PA verdict | 條件 |
|---|---|---|
| FA | AGREE | 5 root cause 中 3 完全 verified / 1 spec-IMPL gap / 1 互補非衝突 |
| AI-E | PARTIAL AGREE | strategist skill LLM-driven 但 0 invocation |
| E5 | PARTIAL | strategist LOC 錯 56x；sprint 樂觀 2x |
| E4 | (未直接 verdict) | 5/5 sibling test 真實到位 |
| E3 | ACCEPT WITH 7 HARD-PRECON | 0 hard-gate broken |
| CC | ACCEPT-WITH-CONDITIONS（5 條 must）| B+→A- 升級 |
| QC | PARTIAL AGREE | 5 alpha 中 2 高可行 + 1 demo 不可行 + 2 半衰期 mismatch |
| MIT | PARTIAL AGREE | real root cause label_close_tag NULL 1-day fix 比 PA R-3 4-6 sprint 短 |
| BB | CONDITIONAL APPROVE（Alpha Surface MEDIUM）| 3 spec error 必修（L25/liquidation/basis）|
| TW | 應升 ADR + AMD + Spec doc | PA workspace-only 不夠 |
| R4 | 必建 ADR-0021 + ARCH-04 + CONTEXT 5 詞條 + AMD-2026-05-09-03/04 | 雙登記 CRITICAL |
| A3 | GUI HIGH 影響 | 建議新 2 tab（Alpha Sources + Hypothesis Lab）|

**整合 verdict**：**DUAL-TRACK 採納**，但 R-1 spec 必修 3 條 BB-side fact-check + 補 ADR/AMD/Spec doc 三層登記。

---

## §4 PA Fix Plan v2 DUAL-TRACK 詳情

### Track W — 收 v2 outstanding（7 wave / ~92h / 6-8 weeks）

| Wave | 內容 | ETA |
|---|---|---|
| W-AUDIT-3b | ExecutorAgent runtime smoke + fail-closed metrics | sprint 1 |
| W-AUDIT-4b | V079 DB apply + cron install + **label_close_tag writer fix（MIT v3 真實 root cause）** | sprint 1 |
| W-AUDIT-6c | portfolio tail risk gate runtime apply | sprint 2 |
| W-AUDIT-6d | 5 策略 verdict IMPL maintenance | sprint 2 |
| W-AUDIT-7c | API Key clear modal + Settings 拆 sub-tab + GUI a11y 補齊 | sprint 2-3 |
| W-AUDIT-1d | docs/README index sync + ADR-0021 草擬 | sprint 1 |
| W-AUDIT-5b | H-8 H-9 sunset + runner.rs split bin/server-side | sprint 3 |

### Track A — Alpha Source Architecture 升級（9 wave / ~270-330h / 6-12 weeks）

| Wave | 內容 | ETA |
|---|---|---|
| W-AUDIT-8a | Alpha Surface Foundation SPEC PHASE | **operator 已啟動**（CLAUDE.md §三 已加 row + spec doc）|
| W-AUDIT-9 | Graduated Canary Foundation（5-stage canary，supersedes AMD-02 §2 binary fail-closed）| **operator 已啟動**（AMD-2026-05-09-03 起）|
| W-AUDIT-8b | R-1 Alpha Surface IMPL（funding/oi 25 symbols throughput fix）| sprint 2-4 |
| W-AUDIT-8c | R-2 Strategist scope expansion（alpha-source orchestrator）| sprint 4-6 |
| W-AUDIT-8d | R-3 Hypothesis Pipeline first-class | sprint 6-8 |
| W-AUDIT-8e | R-4 Per-alpha-source supervised promotion | sprint 8-10 |
| W-AUDIT-8f | R-5 Spec-as-Code | sprint 10-12 |
| W-AUDIT-8g | Alpha Sources GUI tab（A3 建議）| sprint 4-6 |
| W-ARCH-3 | Spec drift 收口（EX-06 §6.3 自动进入 live + LG-X-02..05 supersedes 標記）| sprint 1 |

### 關鍵協調風險

W-AUDIT-9 T3 改 `executor_config_cache.py` + `_read_shadow_mode` stage-aware 與 Track W W-AUDIT-3b ExecutorAgent runtime smoke 衝突中-高 → **必須 W-AUDIT-3b 先 land**。

### Self-adversarial 6 push back 結果

| # | PA push back | self-adversarial | 結論 |
|---|---|---|---|
| 1 | Strategy Interface 偏差 | 4-agent consensus 部分推翻 | **降一檔**（TickContext 已含 5 cross-asset field）|
| 2 | Strategist scope 是調參器 | 站得住 | 保留 |
| 3 | Analyst L2-L5 dormant | 站得住，不需 reverse ADR-0020 | 保留 |
| 4 | ML 0.5% 學習平面死 | MIT 揭發 real root cause = label_close_tag NULL 1-day fix | **比 R-3 短** |
| 5 | 5-Agent 拆分骨架對 | 站得住 | 保留 |
| 6 | Alpha Surface 升級藍圖 | E5 LOC 校正 4-5 sprint | 保留方向 + 校正 estimate |

### 4-agent consensus 數學論證

**22 fail-closed defaults 累加 P(全 PASS) ≈ 1e-3 死循環** = P0-EDGE-1 雞蛋死循環是 demo 環境 stationary fixed point。

---

## §5 v2 → v3 P0 條目轉換

### v2 P0 全 closed → archived

| ID | v2 狀態 | v3 verified |
|---|---|---|
| P0-DECISION-AUDIT-1..5 | 5/5 closed | ✅ 維持 closed（CC verified）|
| P0-NEW-ISSUE-1 LiveDemo | DONE | ✅ 維持 closed |
| P0-NEW-VULN-1..4 | DONE | ✅ 維持 closed（E3 verified）|
| P0-AUDIT-NEW-LG-X-05 | DONE | ✅ 維持 closed（R4 verified）|
| P0-V2-NEW-1 Donchian leak-bias | ACTIVE | ✅ **v3 真 closed**（ad14db07 IndicatorEngine 已用 donchian_prior）|
| P0-V2-NEW-2 strategist cap | ACTIVE | ⚠️ **PARTIAL**（c2ab7b1a 選 freedom-not-gate；FA 要求補 ADR-0021）|
| P0-V2-NEW-3 DSR/PBO evidence cron | ACTIVE | ⚠️ **PARTIAL**（48227607 source 真寫但 V079 未 apply / cron 未 install）|

---

## §6 v3 NEW-ISSUE 全集（39 條）

### v3 重點 NEW

1. **MIT v3 NEW**：label_close_tag NULL 98.9% real root cause（1-day fix）
2. **MIT v3 NEW**：V079 完全未 apply（_sqlx_migrations max=78）
3. **QC NEW-V3-1**：risk_config_live.toml max_param_delta_pct=0.50 違反 fail-closed 政策（應 0.20）
4. **QC NEW-V3-3**：donchian() legacy export 仍 public（應加 #[deprecated]）
5. **QC NEW-V3-4**：blocked_symbols freeze 17+4 cells 永久 dormant 缺 dynamic_unblock_check
6. **BB NEW-5**：PA spec L25 levels 不存在（Bybit V5 = 1/50/200/1000）
7. **BB NEW-6**：PA liquidation_pulse 已 4 weeks ago deleted
8. **BB NEW-7**：funding curve 25 symbols 7d 只 42 條 thin baseline
9. **BB NEW-8**：PA basis demo 限 observation 沒分
10. **A3 NEW-10/11**：governance-tab.js:1551/1600 兩個 confirm() critical-grade 寫操作 v2 漏報
11. **A3 NEW-12/13**：c081029d freeze + 48227607 promotion evidence GUI 0 surface
12. **R4 N1**：5 commits 期間 0/30+ 新文件登記（索引 92→64% 急速回退）
13. **R4 N2**：PA redesign 索引 0/5（必建 ADR-0021 + ARCH-04 + CONTEXT 5 詞條 + AMD-2026-05-09-03/04）
14. **TW v3 7 條**：含 SCRIPT_INDEX 0 hit / CHANGELOG 0 摘要 / Operator mirror 100% 字面重複（5/8 audit MC-7 anti-pattern 重現）
15. **CC v3 NEW**：PA redesign 範圍引入新對齊任務
16. **AI-E v3 5 NEW**：含 strategist skill 是 prompt hint 非 enforcement
17. **PA self-adv NEW**：22 fail-closed defaults P(全 PASS) ≈ 1e-3 死循環論證

---

## §7 與 PA fix plan v1 (88 finding) + v2 (16 wave) 對齊

| 維度 | v1 (5/8) | v2 (5/9) | v3 (5/9 晚) |
|---|---|---|---|
| ✅ Verified-FIXED | 74 | 122 | 65 |
| ⚠️ PARTIAL | 66 | 47 | 39 |
| ❌ NOT-FIXED | 120 | 66 | 84 |
| 🔄 REGRESSED | 6 | 3 | 3 |
| 🆕 NEW-ISSUE | 53 | 21 | 39 |
| **Total** | 319 | 259 | **230** |
| Wave 結構 | 7 wave (W-AUDIT-1..7) | 7 wave + 16 ticket | **DUAL-TRACK 16 wave**（Track W 7 + Track A 9）|

**v3 ❌ 84 vs v2 ❌ 66**：v3 暴露更多真 outstanding（V079 未 apply / cron 未 install / label_close_tag NULL / engine 仍跑舊 binary / GUI work-rate 急降 / 索引急速回退）。**v2 高估了 closure 程度**。

---

**歸檔者**：PM · 2026-05-09 v3 UTC · 對應 active TODO v18 patch
