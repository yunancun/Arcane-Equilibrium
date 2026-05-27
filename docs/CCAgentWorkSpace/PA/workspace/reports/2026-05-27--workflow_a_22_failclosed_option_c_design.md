# Workflow A — 22 條 fail-closed 1e-3 Invariant Option (c) AMD-09-03 附錄 PA Design

**日期**：2026-05-27
**Owner**：PA
**Scope**：僅 PA design 層（不寫 TW/FA/QC/R4 patch 本體；不改 AMD-09-03 字面）
**狀態**：DESIGN — 待 PM dispatch / TW patch
**Trigger**：PM CONDITIONAL APPROVED Option (c)（drift audit §11.3 A 條 + §13 P1 行）；TODO.md §3 Workflow A + §8.1 7.5-11.5 hr 估算。

## 來源 cross-ref

- AMD-2026-05-09-03 §1.2 行 52（22 條 invariant 字面來源）+ §1.2 行 63（`Π_{i=1..22} P(passi) ≈ 1e-3` 數學論證）
- drift audit `2026-05-25--v1_to_v58_full_consolidation_drift.md` §3.1 行 145 + §4.2 #15 行 262 + §11.3 A 行 424 + §13 P1 行 492
- execution-plan v5.8 §11.5 行 873-905（5-Gate Auto Path Inheritance Hard Invariant — patch 風格參考）
- AMD-09-03 §6.3 行 332-345（16 原則合規矩陣 — patch 風格參考）

---

## §1 22 條 Invariant 完整列表（I1-I22）

**來源**：AMD-09-03 §1.2 行 52 一字未改抽取，按原文順序編號 I1-I22。每條保留原文字面以便後續 TW patch 對齊。

| ID | Invariant（AMD-09-03 行 52 字面）| 類別 |
|---|---|---|
| I1 | cost_gate | gate 預設姿態 |
| I2 | Decision Lease shadow | lease 授權路徑 |
| I3 | executor shadow_mode | 5-agent 鏈授權 |
| I4 | Cognitive Modulator default conservative | agent 行為調製 |
| I5 | SM-04 ladder | 風控 escalation |
| I6 | Guardian veto | per-intent 風控 |
| I7 | Layer2 manual-only | AI escalation |
| I8 | lambda:True 移除 | runtime callable 收緊 |
| I9 | `shadow_mode_provider` IPC fail | IPC fail-closed |
| I10 | `_read_shadow_mode` exception fallback | Python exception path |
| I11 | OPENCLAW_LEASE_ROUTER 單向 | router 方向收緊 |
| I12 | `risk_envelope` 默認收縮 | 風控 envelope |
| I13 | strategy active=false default for new strategies | 策略註冊 |
| I14 | promotion gate min_observations=200 | promotion 樣本門 |
| I15 | DSR/PBO 卡 None evidence | 統計 evidence gate |
| I16 | Kelly tier hardcoded | sizing 預設 |
| I17 | `[40]` realized edge tolerance | healthcheck edge |
| I18 | `[33]` maker fill-rate target | healthcheck maker |
| I19 | `[55]` chain coverage | healthcheck lineage |
| I20 | `[42b]` LOW_SAMPLE | healthcheck sample |
| I21 | `[51]` opportunity_positive_n=0 | healthcheck opportunity |
| I22 | `funding_arb` ADR-0018 退役 default | 策略 retired default |

**驗證**：22 條全部來自 AMD-09-03 §1.2 行 52 字面；FA 與 QC pre-verify 必須對照原文確認 0 創造 / 0 漏抽 / 0 順序重排。

**已知失真風險**：drift audit §11.3 A 條 PM verdict 註「22 條真實 ≥ 50 條」— 即 AMD-09-03 行 52 列舉只是 4-agent consensus 當時的 representative 子集。本附錄遵守 PM Option (c) 決議：**僅就行 52 字面 22 條 land invariant**，「真實 ≥ 50 條」屬未來升 ADR 候選範圍（drift §11.3 A 條備註「Option (c) 保留升 ADR future option」）。

---

## §2 每條 Invariant 的 fail-closed 1e-3 容差語意

**核心語意**：`Π_{i=1..22} P(pass_i) ≈ 1e-3` 是**整體下單路徑**的條件機率乘積，**不是**每條單獨的 1e-3 容差。1e-3 是 demo 環境 stationary fixed point 的數學表徵，**不可一刀切套用每條**。

**正確的 fail-closed 容差語意分組**（PA 從 AMD-09-03 全文 + drift audit 抽取）：

### §2.1 Group A — 對比基準=「per-invariant 通過率 P_i」（個別容差不適用 1e-3）

I1-I16 屬 Group A。語意為：

- **量**：每條 invariant 單獨被 demo runtime trace 通過的條件機率 `P_i ∈ [0.5, 0.9]`
- **對比基準**：AMD-09-03 §1.2 行 63 範圍「每條路徑單獨 P 約 0.5-0.9」
- **fail-closed 觸發**：`P_i < 0.5` 持續 ≥ 24h（單條過嚴）OR `P_i = 1.0` 持續 ≥ 7d（單條完全 bypass — 違反 fail-closed 哲學本身）
- **>1e-3 即視為違反？**：**否**。1e-3 不在 Group A 個別容差語意。Group A 的容差是 `[0.5, 0.9]` window。

### §2.2 Group B — 對比基準=「整體 22-product P_total」（1e-3 容差適用）

唯一適用 1e-3 容差的是**整體乘積**：

- **量**：`P_total = Π_{i=1..22} P(pass_i)`
- **對比基準**：AMD-09-03 §1.2 行 63「22 條乘積在 1e-3 量級」
- **fail-closed 觸發**：`|log10(P_total) - log10(1e-3)| > 1`（即 P_total 跌出 `[1e-4, 1e-2]` window）持續 ≥ 24h
- **>1e-3 即視為違反**：**部分對**。`P_total > 1e-2`（鬆 1 數量級以上）= 死循環解套訊號需逐條稽核哪個 invariant 被放寬；`P_total < 1e-4`（緊 1 數量級以上）= demo 進一步癱瘓必觸發 SM-04 alert

### §2.3 Group C — Healthcheck 帶 ID 條目（I17-I21）

I17-I21 為 healthcheck 編號（`[40]/[33]/[55]/[42b]/[51]`），容差語意由各 healthcheck spec 自帶（**不繼承 1e-3**）：

- I17 `[40]` realized edge tolerance — 容差由 §5.8 [40] 規格定（avg_net_bps + Wilson lower）
- I18 `[33]` maker fill-rate target — 容差由 ADR-0039 maker_fill_rate_30d 定
- I19 `[55]` chain coverage — 容差 = `chain_with_lease ratio ≥ 0.7`（AMD-09-03 §2.2 Stage 3 引用）
- I20 `[42b]` LOW_SAMPLE — 容差 = `settled eligible ratio < 0.95`（AMD-09-03 §2.2 Stage 1 rollback 引用）
- I21 `[51]` opportunity_positive_n=0 — 容差 = `n=0` 即觸 fail-closed（已是 binary）

**1e-3 不適用 Group C**。附錄須明示「healthcheck 容差遵循各自 spec，不繼承本附錄 1e-3」。

### §2.4 Group D — 退役/移除（I8, I22）

I8 (lambda:True 移除) + I22 (funding_arb ADR-0018 退役) 是 **disable / removal 類**，**沒有「通過率」可量**：

- I8 — 容差語意 = grep 證明 codebase 中無 `lambda: True` 殘留（codebase 靜態 invariant，非 runtime）
- I22 — 容差語意 = strategy roster 中 `funding_arb.active=false` 持續（per AMD-2026-05-26-01）

**1e-3 完全不適用 Group D**。附錄須明示「removal/retirement invariant 用 codebase 靜態檢查或 config flag，不適用條件機率」。

### §2.5 PA design verdict — 容差套用範圍

| Group | 條目 | 1e-3 適用 | 容差方式 |
|---|---|---|---|
| A | I1-I7, I9-I16 | ❌ | `P_i ∈ [0.5, 0.9]` per-invariant |
| B | 整體乘積 P_total | ✅ | `log10(P_total) ∈ [-4, -2]` |
| C | I17-I21 healthcheck | ❌ | 各 healthcheck spec 自帶 |
| D | I8, I22 removal | ❌ | 靜態檢查 / config flag |

**附錄字面必明示**：1e-3 是 §2.2 Group B 整體乘積的對比基準，**不是**對每條 invariant 的容差統一套用。違反此澄清就把 4-agent 數學論證錯誤泛化（PM 拒絕升 ADR 的核心理由之一）。

---

## §3 AMD-09-03 附錄結構（建議插入 §X + 字面 patch block）

### §3.1 插入位置

AMD-09-03 當前章節：§1 修訂背景 / §2 修訂內容 / §3 不適用範圍 / §4 配套機制 / §5 IMPL ownership / §6 decision rationale / §7 後續動作 / §8 sign-off。

**建議插入點**：**新 §9 「Fail-Closed 1e-3 Invariant 矩陣附錄」**，放在 §8 sign-off 之後（避免擾動既有 §1-§8 已 sign-off 結構）。

附錄與既有章節關係：
- §1.2 行 52 / 行 63（22 條 + 1e-3 數學論證）由 §9 補完容差語意；§1.2 字面**不改**
- §6.3 16 原則合規矩陣是 patch block 風格參考（保留同類 table 格式）
- §11.5 v5.8 5-Gate Auto Path Inheritance Hard Invariant table 是更近期 patch block 風格參考

### §3.2 附錄章節骨架（給 TW 拍板 wording）

```
## 9. Fail-Closed 1e-3 Invariant 矩陣附錄（2026-05-27 補；per drift audit §11.3 A）

### 9.1 附錄來源 + 治理理由
- drift audit §11.3 A 條 PM Option (c) CONDITIONAL APPROVED
- AMD-25-21-01 v2 §Decision 2.2 evidence gate 不滿足升 ADR 條件
- 22 條真實 ≥ 50 條（PM 註），本附錄只 land §1.2 行 52 列舉的 22 條；其餘留 future ADR 升級 option

### 9.2 22 條 invariant 矩陣（PA design §1 表照搬）
[I1-I22 完整表格 — TW 字面對齊 AMD-09-03 §1.2 行 52]

### 9.3 容差語意分組（PA design §2 表照搬）
- Group A (I1-I7, I9-I16) per-invariant P_i ∈ [0.5, 0.9]
- Group B 整體乘積 log10(P_total) ∈ [-4, -2]
- Group C (I17-I21) healthcheck spec 自帶
- Group D (I8, I22) 靜態 / config flag

### 9.4 fail-closed 1e-3 適用範圍明示
**重要澄清**：1e-3 是 §1.2 行 63 整體乘積的對比基準，不是每條容差統一套用。

### 9.5 與既有不變式的關係
- §3.1 DOC-08 §12 9 條安全不變量 — 不變
- §3.2 SM-04 5 ladder — 不變
- §3.3 Live boundary 5-gate — 不變
- §3.4 §二 16 原則硬不變式 — 不變
- §9 本附錄補的是「fail-closed 哲學的細粒度量化容差」，不替代 §3 既有 4 類

### 9.6 升 ADR 觸發條件（future option 保留）
本附錄保留升 ADR 條件：
- 22 條擴張到 ≥ 30 條（drift audit §11.3 A PM 註）
- runtime 偵測 P_total 連續 14d 跌出 [1e-4, 1e-2]
- 任一 Group D 條目恢復 active（如 funding_arb 重啟）→ 升 ADR 重新評估

### 9.7 healthcheck 接線
新 healthcheck `[81] failclosed_invariant_matrix_aggregate`（避 [78]/[80] collision per drift audit §11 canary rename 教訓）：
- 每 24h 對 Group B P_total 觀測
- 對 Group A 每條 P_i 觀測
- Group C 沿用既有 healthcheck（[40][33][55][42b][51]）
- Group D 用靜態 grep + config flag 檢查
- FAIL 條件按 §2.5 分組規則
```

### §3.3 字面 patch block 模板（TW 拍板 wording 時參考；不寫 patch 本體）

格式參考 v5.8 §11.5 + AMD-09-03 §6.3。**不**在此處寫死 wording — TW 拍板時須對齊：

1. AMD-09-03 §1.2 行 52 原文逐字（22 條 invariant 字面不改）
2. §1.2 行 63 1e-3 量級數學論證字面不改
3. §3 不適用範圍 4 類 cross-ref 明示
4. drift audit §11.3 A PM Option (c) 治理理由引用
5. healthcheck `[81]` cron 接線（避 [78][80] collision）

---

## §4 Cascade Downstream Patch Points

### §4.1 TW Patch Points（TW workflow 任務）

| # | File / Section | 動作 | 依賴 |
|---|---|---|---|
| TW-1 | `docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` | 插入新 §9 附錄章節（§3.2 骨架）+ 標題 metadata 加「2026-05-27 §9 附錄補 per drift audit §11.3 A」 | drift audit §11.3 A |
| TW-2 | `docs/governance_dev/SPECIFICATION_REGISTER.md` AMD section | AMD-09-03 entry 加 `(2026-05-27 §9 invariant matrix appendix)` 註 | TW-1 |
| TW-3 | `srv/CLAUDE.md` Hard Boundaries 段 | 不改字面，但 §九 routing 加 1 行「fail-closed 1e-3 invariant matrix 細粒度規範見 AMD-09-03 §9」 | TW-1 |
| TW-4 | `docs/decisions/DOC-01_..._V2.md` §5.6（失敗默認收縮）| 加 cross-ref「實作見 AMD-09-03 §9 22-invariant matrix」 | TW-1 |
| TW-5 | `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md` §11.3 A 條 | 狀態從「PM CONDITIONAL APPROVED」更新為「LAND 2026-05-27 per AMD-09-03 §9」 | TW-1 |

### §4.2 FA Verify Hooks（FA workflow 任務）

| # | Verify Hook | 動作 |
|---|---|---|
| FA-1 | I1-I22 字面對齊 | grep AMD-09-03 §1.2 行 52 vs PA design §1 表 → 22/22 字字相符；任何 1 條 drift = 退回 PA 補 |
| FA-2 | §2 分組合理性 | 對 Group A/B/C/D 每條判定獨立驗：Group A 是否 `P_i ∈ [0.5, 0.9]` 證據在 runtime 可量？Group B P_total 計算公式可否在 SQL 落地？ |
| FA-3 | 1e-3 適用範圍澄清 | FA 簽 §2.5 表 — 是否同意「1e-3 不一刀切」 |
| FA-4 | 升 ADR 觸發條件 | FA 對 §3.2 §9.6 三條觸發條件評估是否窮舉合理（漏條 → push back） |
| FA-5 | §3.1 DOC-08 §12 9 條不衝突 | FA 簽 §9 附錄不弱化既有 4 類不變式 |

**FA pre-verify 建議**：在 TW patch 寫之前，**先派 FA pre-verify I1-I22 字面對齊 + §2 分組是否合理**。原因見 §5 風險 R1。

### §4.3 QC Math Verify Hooks（QC workflow 任務）

| # | Verify Hook | 動作 |
|---|---|---|
| QC-1 | `Π_{i=1..22} P(pass_i) ≈ 1e-3` 數學重推 | 採 `P_i ∈ [0.5, 0.9]` 範圍，`Π = 0.5^22 ≈ 2.4e-7`（下界）vs `0.9^22 ≈ 0.098`（上界），1e-3 落在區間內 → 數學自洽 |
| QC-2 | Group A `[0.5, 0.9]` 範圍是否真有 runtime evidence | QC 從 demo runtime 7d 抽 trace 估每條 invariant 實測 P_i；落在範圍內 → APPROVE；任一 P_i 落外 → push back 重評範圍 |
| QC-3 | Group B P_total 觀測公式 SQL 化 | QC 寫 `[81] failclosed_invariant_matrix_aggregate` 的 SQL prototype；驗證 24h window 真能算出 P_total |
| QC-4 | 1e-3 容差 ±1 量級 `[1e-4, 1e-2]` 寬度合理性 | QC 驗 ±1 量級是否 4-agent consensus 數學論證可接受；過嚴/過鬆 push back |
| QC-5 | drift audit §11.3 A PM 註「22 條真實 ≥ 50 條」是否 quant | QC 對 ≥ 50 條的論據評估；如有具體 28 條 candidate 列表，QC 簽是否進 future ADR 觸發條件 |

### §4.4 R4 Cross-ref Target List（R4 workflow 任務）

R4 對附錄 §9 land 後執行 cross-ref audit，target：

| # | Cross-ref Target | 期望狀態 |
|---|---|---|
| R4-1 | v5.7 execution plan / v5.8 execution plan | §11.5 + §11 + §10 cross-ref 是否需引用 AMD-09-03 §9 |
| R4-2 | ADR-0042 (M3 health) | M3 HEALTH_DEGRADED/CRITICAL 是否引用 §9 fail-closed invariant |
| R4-3 | ADR-0043 (M6 reward) | M6 weight tuning 是否引用 §9 Group A I12 risk_envelope 收縮 |
| R4-4 | ADR-0044 (M7 decay) | M7 DECAY_ENFORCED 是否引用 §9 Group A I13 active=false default |
| R4-5 | ADR-0045 (M4 hypothesis) | M4 DRAFT writeback 是否引用 §9 Group A I7 Layer2 manual-only |
| R4-6 | ADR-0046 (basis funding_arb)（PROPOSED） | ADR-0046 land 時與 §9 I22 funding_arb retired 不衝突（**注意**：ADR-0046 file 尚未 land，drift §11.3 B `PROPOSED 2026-05-25`）|
| R4-7 | DOC-01 V2 §5.1-§5.16 | §5.6（失敗默認收縮）+ §5.4（策略不繞風控）cross-ref AMD-09-03 §9 |
| R4-8 | AMD-2026-05-21-01 v2 + AMD-2026-05-21-01 (Wave 5) | §9 不衝突 v2 Conservative/Standard autonomy level |
| R4-9 | TODO.md §3 Workflow A 行 84 | 狀態從 `D+0 可啟動` 更新為 `✅ LAND 2026-05-27`；§9 cross-ref §3 行 218 |
| R4-10 | `docs/CCAgentWorkSpace/PA/memory.md` | 追加本 design 條目（PA 完成序列強制） |

**R4 pass 兩輪**：Pass A drift detection（找漏引）→ Pass B post-fix verify（drift §11 Pass A/B 工序，funding_arb workflow F 範本）。

---

## §5 Risk + Open Question + Sign-off Gate

### §5.1 風險清單（5 大）

**R1 — 22 條 invariant 真實 ≥ 50 條的「樣本偏差」風險**
drift §11.3 A PM 註明「22 條真實 ≥ 50 條」，AMD-09-03 §1.2 行 52 列舉只是 4-agent consensus 當時抓到的 representative 子集。如附錄字面落 22 條，後續若發現遺漏的 invariant 不在 22 內，附錄就被批評為「治理 cherry-pick」。Mitigation = §3.2 §9.6 明確列「升 ADR 觸發條件 = 22→≥30」並保留 future option。

**R2 — 1e-3 容差語意一刀切套用 22 條的常見誤讀風險**
AMD-09-03 §1.2 行 63 數學論證是**乘積在 1e-3 量級**，不是每條 1e-3。E1/TW/QC sub-agent dispatch 時極容易誤把「22 條 fail-closed 1e-3」讀成「每條容差 1e-3」並設健康 check FAIL 條件。Mitigation = §2.5 表 + §3.2 §9.4 明示。

**R3 — Group C healthcheck spec 已存在，附錄重複定義風險**
I17-I21 已是 healthcheck `[40][33][55][42b][51]`，各自有 spec。附錄若重新規定容差會造成 dual-source-of-truth drift（v5.8 §6.7 已警告 dual-source 問題）。Mitigation = §2.3 + §3.2 §9.3 明示「繼承既有 healthcheck spec，本附錄不重定義」。

**R4 — Group D I22 funding_arb 與 ADR-0046 PROPOSED 衝突風險**
I22 列「funding_arb ADR-0018 退役 default」為 fail-closed invariant，但 ADR-0046 (PROPOSED 2026-05-25) 是 funding_arb basis observation/execution split 未來 redesign slot（drift §11.3 B 行 425）。若 ADR-0046 land 時恢復 funding_arb 部分 active，I22 字面失效。Mitigation = §3.2 §9.6 「Group D 任一條目恢復 active → 升 ADR 重新評估」+ R4-6 cross-ref 守住。

**R5 — TODO.md §3 行 84 工時估算 7.5-11.5 hr 假設 5-agent 並行成立**
TODO 標 7.5-11.5 hr「5 並行」，但本 PA design 揭示 FA pre-verify 應**前置**於 TW（§4.2 註）。若 FA push back §2 分組，TW 必返工 → 工時破 11.5 hr 上限。Mitigation = PM dispatch 時改為 PA→FA pre-verify (2h)→TW (3h)→QC+FA verify (3-4h)→R4 (1.5h-3h) 串行+局部並行 chain。

### §5.2 Open Question（需 PM / Operator 拍板）

**Q1**：附錄是否要把「真實 ≥ 50 條」的 28+ 條 candidate 也列入？
- 選 A：只 land 22 條（PM Option (c) 字面 — 推薦）；保留升 ADR future option
- 選 B：附錄擴張到 ≥ 30 條 — 違 Option (c) verdict，等同走升 ADR 路徑

**Q2**：healthcheck `[81] failclosed_invariant_matrix_aggregate` 編號是否要避 [78]/[80] collision？
- drift §11 教訓 = [67]→[80] rename 避 passive_wait collision；[78] feature_baseline cron stale 4.75d 仍 unresolved
- PA 推薦 [81]，由 E1 dispatch 時 SSH 驗 [78][79][80] 區段佔用後最終拍板

**Q3**：附錄 land 後 v5.7/v5.8 是否要 §10 cross-ref hook 同步補引？
- v5.8 §11.5 已存在 hard invariant table，新增 §10 cross-ref AMD-09-03 §9 是治理一致性需要
- 但 v5.7 dispatch-of-record 文本已 frozen（drift §6.6 內部不一致 caveat），是否在 v5.7 動 = PM 決

**Q4**：FA pre-verify 是否必要前置？
- PA 推薦 YES（per §5.1 R5）
- 但 TODO §3 行 84 列「5 並行」假設 FA 在 TW 之後，PM 需重排或接受工時 +2h

### §5.3 Sign-off Gate

| Gate | Owner | 進 IMPL 條件 |
|---|---|---|
| G1 — PA design APPROVED | PM | 本文件 PM read + Q1-Q4 拍板 |
| G2 — FA pre-verify APPROVED | FA | §4.2 FA-1..FA-5 全 PASS |
| G3 — TW patch wording APPROVED | PA + CC | §3.2 骨架 → TW 寫 wording → PA verify 對齊 + CC 16-原則合規 sign |
| G4 — QC math APPROVED | QC | §4.3 QC-1..QC-5 全 PASS |
| G5 — R4 Pass A drift detection | R4 | §4.4 R4-1..R4-10 全 PASS |
| G6 — R4 Pass B post-fix verify | R4 | drift §11 Pass A/B 工序 |
| G7 — Operator final sign-off | operator | G1-G6 完成 → operator commit |

---

## §6 PA E1 派發計劃（不寫 patch 本體；給 PM 拍板）

| Sub-task | Owner | 文件範圍 | 估時 | 依賴 |
|---|---|---|---|---|
| A-T1 FA pre-verify I1-I22 字面 + §2 分組 | FA | PA design §1 + §2 + AMD-09-03 §1.2 行 52 | 1.5-2h | 本 PA design |
| A-T2 TW patch §9 附錄 wording | TW | AMD-09-03 新 §9 + §3.2 骨架 | 2.5-3h | A-T1 PASS |
| A-T3 QC math + healthcheck `[81]` SQL prototype | QC | §4.3 QC-1..5 + `[81]` SQL | 2-3h | A-T1 PASS（與 A-T2 並行）|
| A-T4 CC 16-原則合規 + PA design alignment verify | CC + PA | §6.3 16-原則 patch alignment | 1h | A-T2 完 |
| A-T5 R4 Pass A drift detection | R4 | §4.4 R4-1..R4-10 | 1-1.5h | A-T2 + A-T3 完 |
| A-T6 R4 Pass B post-fix verify | R4 | 同 Pass A 模式 | 0.5-1h | A-T5 + fix 完 |

**並行**：A-T1（必先）→ A-T2 + A-T3 並行 → A-T4 + A-T5 並行 → A-T6
**總工時**：7.5-11.5h（與 TODO §3 行 84 估算對齊）
**E2 重點審查 3 點**：
1. 1e-3 容差語意「不一刀切」是否被 TW patch 字面 unambiguously 表達
2. Group C healthcheck spec 不被附錄重複定義（dual-source-of-truth 防漂）
3. healthcheck `[81]` cron 接線 SQL 是否在 Linux PG 經 dry-run 驗證（per `feedback_v_migration_pg_dry_run.md`）

---

## §7 不做事項（scope discipline）

- 不寫 TW patch 本體 wording — A-T2 owner
- 不寫 FA verify report — A-T1 owner
- 不寫 QC math proof / SQL — A-T3 owner
- 不寫 R4 audit report — A-T5/A-T6 owner
- 不修改 AMD-09-03 §1-§8 字面（既有 sign-off 結構保留）
- 不擴張 22 條 → ≥ 30 條（違 PM Option (c) verdict）

---

## §8 完成序列

- 本文件存 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--workflow_a_22_failclosed_option_c_design.md`
- 結論性 summary 同步進 main session output（≤ 250 字中文）
- PA memory 追加 (`docs/CCAgentWorkSpace/PA/memory.md`)：本日 design 條目

**PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--workflow_a_22_failclosed_option_c_design.md**
