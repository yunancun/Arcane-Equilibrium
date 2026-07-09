# FA pre-verify — Workflow A 22 fail-closed 1e-3 Invariant Option (c)

**Owner**: FA · **Date**: 2026-05-27 · **Scope**: PA design report read-only verify
**Status**: **CONDITIONAL APPROVE** — TW + QC 並行 dispatch READY post C1-C6 wording

**Base**:
- PA design `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--workflow_a_22_failclosed_option_c_design.md` (323 lines)
- Source 1: AMD-09-03 `docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` §1.2 行 52 + 行 63
- Source 2: drift audit `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md` §3.1 行 145 + §11.3 A 行 424

> **Note**: This report was reconstructed from sub-agent inline return (2026-05-27 PM session) due to sub-agent harness `Do NOT Write report` constraint. Content matches sub-agent return verbatim.

---

## §1 22 Invariant 字面對齊 verdict（PA §1 表 vs AMD-09-03 行 52 原文）

AMD-09-03 行 52 整段為一個 continuous prose run, 22 條以 ` / ` 分隔, 抽取後與 PA design §1 表逐條對照:

| ID | PA design 字面 | AMD-09-03 行 52 原文相對應 token | Verdict |
|---|---|---|---|
| I1 | cost_gate | "cost_gate" | ✅ |
| I2 | Decision Lease shadow | "Decision Lease shadow" | ✅ |
| I3 | executor shadow_mode | "executor shadow_mode" | ✅ |
| I4 | Cognitive Modulator default conservative | "Cognitive Modulator default conservative" | ✅ |
| I5 | SM-04 ladder | "SM-04 ladder" | ✅ |
| I6 | Guardian veto | "Guardian veto" | ✅ |
| I7 | Layer2 manual-only | "Layer2 manual-only" | ✅ |
| I8 | lambda:True 移除 | "lambda:True 移除" | ✅ |
| I9 | `shadow_mode_provider` IPC fail | "`shadow_mode_provider` IPC fail" | ✅ |
| I10 | `_read_shadow_mode` exception fallback | "`_read_shadow_mode` exception fallback" | ✅ |
| I11 | OPENCLAW_LEASE_ROUTER 單向 | "OPENCLAW_LEASE_ROUTER 單向" | ✅ |
| I12 | `risk_envelope` 默認收縮 | "`risk_envelope` 默認收縮" | ✅ |
| I13 | strategy active=false default for new strategies | 同 | ✅ |
| I14 | promotion gate min_observations=200 | 同 | ✅ |
| I15 | DSR/PBO 卡 None evidence | 同 | ✅ |
| I16 | Kelly tier hardcoded | 同 | ✅ |
| I17 | `[40]` realized edge tolerance | 同 | ✅ |
| I18 | `[33]` maker fill-rate target | 同 | ✅ |
| I19 | `[55]` chain coverage | 同 | ✅ |
| I20 | `[42b]` LOW_SAMPLE | 同 | ✅ |
| I21 | `[51]` opportunity_positive_n=0 | 同 | ✅ |
| I22 | `funding_arb` ADR-0018 退役 default | 同 | ✅ |

**字面對齊率**: 22/22 = 100%
**順序**: PA 編號 I1-I22 與 AMD-09-03 行 52 由左至右 enumeration 完全一致。
**創造**: 0 條。**漏抽**: 0 條。**重排**: 0 條。

**FA-1 PASS**.

注意: AMD-09-03 行 63 字面為「每條路徑單獨 P 約 0.5-0.9，22 條乘積在 1e-3 量級」— PA §2.1 引用「P_i ∈ [0.5, 0.9]」與行 63 字字相符；§2.2 「乘積在 1e-3 量級」亦 verbatim。**1e-3 數學論證字面引用 FA-3 PASS**.

---

## §2 PA 4-Group 分組合理性 verdict

| Group | PA 分配 | FA verdict | 理由 |
|---|---|---|---|
| A 個別容差 [0.5, 0.9] | I1-I7, I9-I16 (15 條) | ✅ APPROVE | AMD-09-03 行 63「每條路徑單獨 P 約 0.5-0.9」原文直接支援；個別容差語意對齊行 52 中 runtime-觀察 invariant 性質 |
| B log10 乘積 [1e-4, 1e-2] | 整體 P_total | ✅ APPROVE | 行 63「22 條乘積在 1e-3 量級」原文支援；±1 數量級 window 合理 (允 stochastic noise) |
| C 沿用既有 healthcheck spec | I17-I21 ([40][33][55][42b][51]) | ✅ APPROVE 且 critical 避 dual-source | I17-I21 5 條均為帶 ID healthcheck，已存 spec；附錄不重定義是治理一致性最佳實踐 |
| D 靜態 grep + config flag | I8 (lambda:True), I22 (funding_arb) | ✅ APPROVE | I8 是 codebase 靜態 removal；I22 已於 AMD-2026-05-26-01 (D) 處置 funding_arb V2 Retired，per-strategy config flag 治理 |

**4-Group 分組合理性 FA-2 PASS**.

**Group A 細項提醒** (MINOR, non-blocker): 建議 PA 在 §9 附錄 wording 明示「Group A 中 I13-I16 採『config flag set 持續性 = 1.0』binary 視為 P_i = 1.0 並豁免 7d threshold」。

---

## §3 5 風險 verdict + mitigation

### R1 — 22 條真實 ≥ 50 條樣本偏差

**Source verify**: drift audit §11.3 A 行 424 確有「22 條真實 ≥ 50 條」PM 註。但**未找到** drift audit 列出具體 ≥ 50 條 candidate list 或 28 條 additional candidates（grep `≥ 50 條` 只在 §11.3 行 424 出現 1 次）。

**FA verdict**: ⚠️ **PM 註目前是 unsubstantiated claim**.

**Mitigation suggestion**:
1. PA §3.2 §9.6 「升 ADR 觸發條件 = 22→≥30」FA APPROVE 保留；
2. **新增要求**: AMD-09-03 §9 附錄字面**必須引用** drift audit §11.3 A 行 424 PM 註原文；
3. **新增要求**: PM 在 dispatch 時把「produce 28 條 additional candidate list」列為 future ADR 升級的 P3 backlog.

### R2 — 1e-3 容差語意一刀切誤讀

**FA verdict**: ✅ **APPROVE PA mitigation**. PA §2.5 表 + §3.2 §9.4 明示已完整。AMD-09-03 行 63 字面確實是「22 條乘積在 1e-3 量級」非每條 1e-3。

**強化要求** (CONDITIONAL): TW patch §9.4 wording 必須包含字面 **「1e-3 是 Group B 整體乘積，**不是**每條 invariant 的容差」**（粗體 + 「不是」是必須的反向澄清）。Recommend TW patch §9 開頭即放 Big Box Warning。

### R3 — Group C healthcheck dual-source-of-truth

**FA verdict**: ✅ **APPROVE PA mitigation**. PA §2.3 + §3.2 §9.3 明示「Group C 繼承既有 healthcheck spec，本附錄不重定義」。

**強化要求** (CONDITIONAL): TW patch §9 附錄要列**5 個 healthcheck spec source path**（[40] 在 §5.8 spec、[33] 在 ADR-0039、[55] 在 §AMD-09-03 §2.2 Stage 3、[42b] 在 §AMD-09-03 §2.2 Stage 1、[51] 在 spec source 待確認）。

### R4 — Group D I22 funding_arb 與 ADR-0046 PROPOSED 衝突

**FA verdict**: ✅ **APPROVE PA mitigation 但補強**. I22「funding_arb ADR-0018 退役 default」現已被 AMD-2026-05-26-01 升格為 **roster-level retirement**（strategy roster 5→4）。

**強化要求** (CONDITIONAL):
1. TW patch §9 I22 wording 必須 **cross-ref AMD-2026-05-26-01** + ADR-0018 + ADR-0046 PROPOSED 三個治理 anchor；
2. PA §4.4 R4-6 cross-ref target 補一條：R4-7 = AMD-2026-05-26-01 I22 lineage cross-ref；

### R5 — 7.5-11.5 hr 5 並行假設不成立

**FA verdict**: ✅ **APPROVE PA mitigation (FA 前置)**. 本 FA report 本身即此 mitigation 的 execution.

**強化要求**: 因 FA pre-verify APPROVE 後可即刻派 **TW + QC 並行**（QC math 不依賴 TW wording），實際 chain 可壓縮為 `FA done → (TW patch ∥ QC math + healthcheck [81] SQL prototype) → CC + R4 → operator sign-off`，總工時 lower bound 6.5h / upper bound 10h，在 TODO §3 行 84 「7.5-11.5 hr」內。

---

## §4 與 9 Safety Invariants Live Dashboard (TODO §5) 重疊盤點

TODO.md §5 行 125-137 9 safety invariants (I1-I9) source = **DOC-08 §12** + **CLAUDE.md §四 Hard Boundaries**。本附錄 22 invariant source = **AMD-09-03 §1.2 行 52 4-agent consensus**.

| 條目 | DOC-08 §12 I1-I9 | AMD-09-03 I1-I22 | 是否重疊 |
|---|---|---|---|
| 5-gate live boundary | I1 | (無直接對應；I2 Decision Lease shadow 部分 cover) | **NO 重疊** — 不同 abstraction level |
| ML/Dream/Executor 不繞 Lease | I7 | I2 Decision Lease shadow + I3 executor shadow_mode + I7 Layer2 manual-only | **PARTIAL 重疊** |
| 其他 7 條 | (各自) | 無直接對應 | NO |

**重疊評估**: DOC-08 §12 I7 與 AMD-09-03 I2 + I3 + I7 是**同層 invariant 不同切面**。DOC-08 是 enforcement gate；AMD-09-03 22 條是 sub-component fail-closed defaults。**沒有 enforcement 衝突**.

**FA-5 verdict**: ✅ 9 dashboard invariant 與 22 附錄 invariant 屬不同 abstraction level，無重複 enforcement，可並存。

**強化要求** (CONDITIONAL): TW patch §9.5 必補「9.5.5 DOC-08 §12 9 條 vs §9 附錄 22 條 abstraction level 對應表」。

---

## §5 Final Verdict

**CONDITIONAL APPROVE**.

- 字面對齊率 22/22 = 100% (FA-1 全 PASS)
- 4-Group 分組: ALL APPROVE (FA-2 全 PASS)
- 1e-3 語意非一刀切澄清: APPROVE (FA-3 全 PASS)
- 升 ADR 觸發條件: APPROVE (FA-4 全 PASS)
- 與 DOC-08 §12 不衝突: APPROVE (FA-5 全 PASS)

### Conditional 條件清單（TW patch wording 必須 land 才升 FULL APPROVE）

1. **C1 (from R2)**: TW patch §9.4 必含字面「1e-3 是 Group B 整體乘積，**不是**每條 invariant 的容差」反向澄清（粗體 +「不是」）
2. **C2 (from R1)**: TW patch §9.1 必引用 drift audit §11.3 A 行 424 PM 註「22 條真實 ≥ 50 條」原文，並在 §9.6 列「produce 28 條 additional candidate list」為 future ADR P3 backlog
3. **C3 (from R3)**: TW patch §9.3 必列 5 個 healthcheck spec source path ([40]/[33]/[55]/[42b]/[51])
4. **C4 (from R4)**: TW patch §9 I22 wording cross-ref AMD-2026-05-26-01 + ADR-0018 + ADR-0046 PROPOSED 三個 anchor；PA §4.4 R4 補一條 R4-7
5. **C5 (from §4)**: TW patch §9.5 補一條「9.5.5 DOC-08 §12 9 條 vs §9 附錄 22 條 abstraction level 對應表」
6. **C6 (minor from §2)**: TW patch §9.2 Group A 內備註「I13-I16 採 config flag set 持續性 = 1.0 binary 視為 P_i = 1.0，豁免 7d auto fail-closed threshold」

### 派 TW + QC 並行 readiness

**YES 可即刻派**. C1-C6 條件全部屬 TW patch wording 範疇，TW 接到本 FA report + PA design 即可動工；QC math verify 不依賴 TW wording，可並行。

預期 chain:
- TW patch 寫作 (~3h, 含 C1-C6 wording) ∥ QC math + [81] SQL prototype (~2-3h)
- CC + R4 (~1.5h)
- operator sign-off
- **總工時 lower bound 6.5h / upper bound 10h**

### Hard Boundary 體檢

PA design + AMD-09-03 §9 附錄計劃**不觸碰**任何硬邊界（純 documentation governance + healthcheck wire-up `[81]`）。**無 BLOCKER**.

### 16 根原則

22/22 invariant 與 16 根原則 #3 (AI→Lease→複核→執行)、#4 (策略不繞 Guardian/risk)、#6 (Uncertainty defaults conservative)、#7 (學習不直接 rewrite Live) 強化關係正向。**Approve 16/16**.

---

**Maintenance contract**: 本報告為 FA pre-verify 草稿副本（主會話於 2026-05-27 從 FA sub-agent inline return 重建）；正式 audit trail 走本檔；未來 G3 sign-off 時 verify C3 5 source path resolve 狀態。
