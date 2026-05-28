# Alpha Tournament Activation Protocol Spec

**Date**: 2026-05-28
**Author**: PA (sub-agent dispatch from PM main session)
**Status**: SPEC-FINAL / IMPL-DEFERRED（runner code 不在本 spec 範圍）
**Trigger**: TODO v77 `P2-ALPHA-TOURNAMENT-ACTIVATION-SPEC`（per Sprint 2 Q2 lock = N=5 / M=15）
**Operator directive**: 保留 Tournament framing 給 future use，但 Sprint 2 內部不啟動 tournament 排名運作。

---

## 0. Read This First

本 spec 是 Alpha Tournament SSOT (`docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`) 的 **activation layer**。它定義 tournament 何時激活、何時凍結、激活後排名/晉級/淘汰的 slot 預留，以及與 Sprint 2 hybrid 方案 C 的銜接。

**本 spec 不取代 SSOT**：排名 metric 公式、出口 lane（`reject` / `draft_only` / `observe_more` / `stage0_ready`）、5-gate evidence 仍以 SSOT §4-§6 為準。

讀順序（任何 PA / QC / MIT / E1 / E2 / E4 / QA agent 啟動 tournament 激活時）：

1. `CLAUDE.md` §二 / §四 — root principles + live hard boundaries。
2. `TODO.md` — current Sprint 2 / Sprint 3+ 狀態 + 策略池當前 settled n。
3. SSOT `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md` — 排名 / 出口 lane / 5-gate。
4. **本 spec** — activation 觸發 / 退出 / re-entry / 評估時點。
5. AMD-2026-05-26-01（funding_arb deprecation）— 池大小計算口徑。

衝突優先序：

`CLAUDE hard boundary > Accepted ADR/AMD > SSOT § scoring + gates > 本 spec activation layer > older execution plan prose`。

---

## 1. 目的 + 與 SSOT 關係

### 1.1 目的

Alpha Tournament SSOT 已定義「**如何**評分、什麼可進 Stage 0、出口 lane 怎麼分」，但沒定義「tournament 排名運作**何時**才有意義啟動」。本 spec 補這個缺口：

- 給「池太小、樣本太薄」的早期狀態一個**明確凍結機制**，避免 N=2 / N=3 候選硬排名造成 false signal。
- 給「策略池長大、每策略樣本累積」的成熟狀態一個**明確激活機制**，避免 future operator / future agent 看 SSOT 不知何時啟用 tournament 排名。
- 保 Tournament framing 給 future use，**Sprint 2 不啟動 tournament 排名運作**（per Sprint 2 Q2 lock）。

### 1.2 與 SSOT 的關係（層級分工）

| 層 | 文件 | 內容 |
|---|---|---|
| Scoring layer | SSOT §4 | scorecard fields / `risk_adjusted_net_edge` 公式（rank tie-breaker） |
| Gate layer | SSOT §5 | 5-gate（data / fee / sample / replay / governance / portfolio） |
| Output lane layer | SSOT §6 | `reject` / `draft_only` / `observe_more` / `stage0_ready` |
| **Activation layer**（本 spec） | 本 spec §2-§8 | 何時啟動 tournament 排名 / 何時凍結 / re-entry / 評估時點 |
| Stage ladder | SSOT §7 + AMD-2026-05-15-01 | 不被本 spec 改變 |

**本 spec 是 activation gate，不是 scoring engine。** 即使 activation 未觸發，每個 candidate 仍按 SSOT 走 scorecard + 5-gate + output lane（DRAFT / observe_more / stage0_ready 等），只是不進入「跨策略排名/晉級/淘汰」運作。

---

## 2. Activation 觸發條件

Tournament 排名運作的激活是**AND 條件**：

| 條件 | 閾值 | 說明 |
|---|---|---|
| **C1 池大小** | settled 策略池 ≥ **N=5** | 「settled 策略」=已通過 SSOT §5 sample gate（n ≥ 30）+ fee gate + replay gate 並進入 demo accumulation 階段的 candidate（含 baseline B0 內已被 SSOT § A0/A1/A2 引用的策略；但不含 `reject` / `draft_only` 狀態）。 |
| **C2 每策略樣本** | 每策略 n_settled ≥ **M=15** | 「n_settled」= 該策略在 demo + LiveDemo 累積的 settled fills 計數（per ADR-0025 track-based attribution；paper diagnostic 不計）。 |

**激活判定（pseudo-rule，runner code 不在本 spec）**：

```
tournament_activated := count(strategies where strategy.status == "settled" AND strategy.n_settled >= M) >= N
```

### 2.1 池大小計算口徑（重要）

- **計入池**：當前 active 在 demo / LiveDemo 累積 settled fills 的策略；含 SSOT §3 候選 A0 (C10 funding harvest) / A1 / A2 / A3 / A4 / A5 / B0 內 active baseline（grid / ma / bb_breakout / bb_reversion）。
- **不計入池**：
  - 已 retired 策略（per AMD-2026-05-26-01：funding_arb V2 Retired closed，不計）。
  - `reject` 狀態策略。
  - 純 `draft_only` 假說（M4 DRAFT writer 產出但未進入 IMPL）。
  - 純 paper diagnostic（per SSOT §4 `engine_mode` 規則）。

### 2.2 為何選 N=5 / M=15（rationale，不重議）

- **N=5**：Operator + PM 2026-05-28 grill-me 5 Q2 lock。直覺背書 = 跨策略排名要有「至少 5 個」才能跑出能拒絕 top-1 / top-2 的對照分布；< 5 排名只能反映「最不爛」非「真有 edge」。
- **M=15**：Operator + PM 2026-05-28 grill-me 5 Q2 lock。介於 SSOT §5 sample gate 的 30 events 門檻與「太緊根本不會激活」之間；M=15 是「跨策略可比」的下限，不是「該策略本身 edge significant」的 standalone gate（後者仍走 SSOT §5）。

**注意**：N / M 為 operator 拍板閾值，本 spec 不重新評估「是否該改 N=4 或 M=20」。Future revision 須走 AMD amendment（見 §11）。

---

## 3. 退出機制（Deactivation / Freeze）

### 3.1 自動凍結觸發

Tournament 一旦激活，若 settled 策略池 < **N-1 = 4**，自動凍結回 **Stage 0R direct path**（per Sprint 2 Q1 lock）。

| 觸發 | 行為 |
|---|---|
| 池從 ≥ N=5 跌至 = N-1 = 4 | 自動凍結 tournament 排名運作。每個 candidate 仍按 SSOT 走 scorecard + 5-gate + output lane；但不跑跨策略排名 / 晉級 / 淘汰。 |
| 凍結後池回升至 ≥ N=5 | 重新激活 tournament 排名運作（不需 manual re-trigger；每 Sprint 評估時自動 re-check，per §8）。 |

**為何選 hysteresis (激活 ≥ N / 凍結 < N-1)**：避免池在 N=5 邊界震盪（一策略 settled → 一策略 retire → 再 settled）造成 tournament 反覆 on/off 抖動。N-1=4 緩衝給池 1 個策略的「下行 grace」。

### 3.2 凍結期 fallback

凍結期間，所有 candidate 走 **Stage 0R direct path**：

- SSOT §4 scorecard 仍寫。
- SSOT §5 5-gate 仍跑。
- 出口 lane 仍按 SSOT §6（`reject` / `draft_only` / `observe_more` / `stage0_ready`）。
- 但**不**跑跨策略排名 / top-K 晉級 / 連續負 alpha 淘汰。
- `stage0_ready` 候選照 SSOT §7 進 Stage 0 dispatch（per AMD-2026-05-15-01 走 Stage 0R replay preflight），不需通過 tournament。

### 3.3 retired 策略口徑（per AMD-2026-05-26-01）

- funding_arb V2 已 Retired closed，**不計池大小**。
- 任何 future ADR/AMD 把策略升格 Retired，同口徑不計池。
- 暫時 `dormant` 但未 retired（如 bb_breakout 30 天 catch-up 期）= 仍計池（settled 樣本累積中）。

---

## 4. 排名 metric slot 預留

**本 spec 不指定排名公式**。SSOT §4 已列 `risk_adjusted_net_edge = net_bps_per_trade * expected_trades_per_month - expected_drawdown_penalty - implementation_tax` 為**rank tie-breaker** 候選；本 spec 預留以下 metric slot 給 activation 觸發後選定：

| Candidate metric | 適用情境 | 風險 |
|---|---|---|
| `risk_adjusted_net_edge`（SSOT §4） | 預設 tie-breaker | 公式參數 `expected_trades_per_month` / `expected_drawdown_penalty` / `implementation_tax` 在 N=5/M=15 時可能仍不穩定 |
| PSR (Probabilistic Sharpe Ratio) | 樣本足且非常態分布 | 需 n ≥ ~60 / strategy 才 robust；M=15 可能不夠 |
| DSR (Deflated Sharpe Ratio) | 跨多策略比較時 control 多重檢驗 | 需 strategy 池總嘗試次數的先驗 |
| Sharpe ratio | 簡單可比 | 對厚尾 / 小樣本 mis-leading |
| `cost_edge_ratio`（per CLAUDE root principle #13） | AI cost-aware ranking | M4/M7/M11 cost tracking 須先完整 |

**啟用時機**：activation 觸發後（C1+C2 同時滿足），由 PA + QC 拍板選 1-2 個 primary metric + 1 個 tie-breaker。`[future-iteration: 公式待 PA + QC 啟動時定]`

**禁止**：activation 未觸發前不可寫 ranking runner code（per CLAUDE.md operating-style #2 + feedback_no_dead_params）。

---

## 5. 晉級規則 slot 預留

**本 spec 不指定 K**。Activation 觸發後候選晉級規則 slot：

| 規則 slot | 預備 candidate | 啟用時機 |
|---|---|---|
| top-K 晉級至 Stage 0R replay preflight | K ∈ {1, 2, 3}；候選按 §4 primary metric 排序 | activation 觸發 + N≥5 時由 PA + QC 拍 K 值 |
| 晉級後行為 | 走 SSOT §7 Stage 0R direct path / Stage 0R replay preflight（per AMD-2026-05-15-01） | 同上 |
| 晉級 cool-down | 每策略晉級後須 ≥ ?? Sprint 不被再次評估晉級 | 待 activation 後資料定 |

`[future-iteration: K 值 + cool-down 等 activation 觸發後 PA + QC 拍板]`

**重要 invariant**（不可違反）：

- 晉級 ≠ Stage 1 alpha-bearing promotion（per CLAUDE §四 hard boundary：promotion 須 Demo + green Stage 0R replay preflight）。
- 晉級 ≠ trading authority（仍須走 Decision Lease + Guardian + 5-gate）。
- 晉級僅為「**進入 Stage 0R replay preflight 排隊優先順序**」的 evidence input。

---

## 6. 淘汰規則 slot 預留

**本 spec 不指定 X**。Activation 觸發後策略淘汰規則 slot：

| 規則 slot | 預備 candidate | 啟用時機 |
|---|---|---|
| 連續 X 期負 alpha → 淘汰 | X ∈ {2, 3, 4}；「期」單位 = Sprint 或 D+N 評估 cron | activation 觸發 + N≥5 時由 PA + QC 拍 X 值 + 期單位 |
| 淘汰行為 | 候選進 SSOT §6 `reject` 出口 + 不立即 ADR retire；走 §7 re-entry path 重評 | 同上 |
| 淘汰 grace window | 連續 X-1 期負 alpha = warning（observe_more 升格），第 X 期才 reject | 待 activation 後資料定 |

`[future-iteration: X 值 + 期單位 + 升格 warning 機制 等 activation 觸發後 PA + QC 拍板]`

**重要 invariant**：

- 淘汰 ≠ ADR retire（per AMD-2026-05-26-01 funding_arb 是「結構性 deprecation」非 tournament 淘汰）。
- ADR retire 走 ADR amendment / AMD path；tournament 淘汰走本 spec §7 re-entry path。
- 淘汰後仍可走 §7 re-entry，不需重新建立 ADR。

---

## 7. Re-entry Path

被 tournament 淘汰策略走 **Stage 0R replay preflight 重評**：

### 7.1 流程

1. 淘汰判定 → 候選狀態降為 `observe_more`（不是 `reject`）+ tournament `excluded` 標記。
2. 候選**不需要**重新走 N=5 / M=15 累積（per Sprint 2 Q2 lock 雙軌語意 = 已 settled 過的策略保留 settled 狀態）。
3. 候選走 Stage 0R replay preflight（per AMD-2026-05-15-01）→ 若 replay 顯示 edge 仍存在（fee-adjusted net > 0 + 樣本 ≥ SSOT §5 sample gate）→ 重新進池。
4. 重新進池後狀態：`settled, re-entered, last_excluded_at=YYYY-MM-DD`。
5. Tournament 排名計算重新納入該策略，但建議排名 metric 加 `re_entry_penalty` slot（避免 yo-yo 來回）。

### 7.2 限制

- 同一策略 90 天內最多 re-enter 2 次（避免無限震盪）；超過 → 走 ADR retire path 而非 tournament re-entry。
- Re-entry 後若連續 X-1 期負 alpha 又被淘汰 → 該策略**強制** ADR retire path（不再 re-entry）。

`[future-iteration: 90 天 / 2 次 / penalty 公式 等 activation 觸發後 PA + QC 拍板]`

---

## 8. 每 Sprint 觸發評估

本 spec **不寫 runner code**，但定義評估入口（governance ladder only）：

### 8.1 評估時機

| 入口 | 觸發 | 行為 |
|---|---|---|
| Sprint 啟動 | PM 每 Sprint 啟動 dispatch packet 時 | check C1 (池 ≥ N=5) + C2 (每策略 n_settled ≥ M=15)；若同時滿足且當前 frozen → 升格 activation；若任一 fail 且當前 active → 凍結 |
| 週期 cron | Future implementation：Linux runtime 每週 cron 一次 | 同 Sprint 啟動 check；發信號至 dashboard slot |
| Dashboard 入口 | Future implementation：Learning Cockpit 新 panel 顯示 `tournament_status: { activated, frozen, pool_size, per_strategy_n_settled[] }` | 純展示；不寫實作 |

### 8.2 評估行為（governance only，不寫 code）

每 Sprint 啟動時 PM 須在 dispatch packet 內列：

```
Tournament status check (per 本 spec §2 + §3):
- pool_size: <N_current> (threshold N=5)
- per_strategy_n_settled: { strategy_A: <n>, strategy_B: <n>, ... } (threshold M=15)
- activated: <true | false>
- frozen_reason: <if frozen, why>
- next_action: <if activated, K + X 待 PA+QC 拍板; if frozen, 維持 Stage 0R direct path>
```

`[future-iteration: cron + dashboard runner 實作待 activation 觸發後再開 ticket。]`

---

## 9. 對 Sprint 2 Hybrid 方案 C 的關係

Sprint 2 Q4 lock 為 hybrid 方案 C，三軌並行：

| 軌 | 內容 | 進 activation 池？ |
|---|---|---|
| **主軌 A1+A2** | Funding short-only v2 + Liquidation cascade fade（SSOT §3 主要 Sprint 2 candidate） | **進池**（settled 累積中；A1+A2 IMPL ready after PA/MIT spec） |
| **對照軌 grid+ma** | 5 textbook 策略中 grid + ma 作為 baseline / control（per SSOT §3 B0） | **不進 activation 池**（SSOT §3 明確 B0 是 baseline/control，不算 candidate；對照軌存在是為了 evidence comparison，不是為了被 tournament 排名） |
| **catch-up 軌 bb_breakout + bb_reversion** | 30 天 grace 期累積（D+30 = 2026-06-27 評估，per TODO `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`） | **暫不計池**（n_settled < M=15 直接 fail C2）；D+30 評估時若 n_settled ≥ 15 → 進對照軌（同 grid+ma）；若 < 15 → ADR-0044 deprecation cascade |

### 9.1 Sprint 2 內部行為

- Tournament **不激活**（C1 fail：A1+A2 即使 IMPL 完，n_settled 短期內難達 15；池有 grid+ma 但不算 candidate）。
- 內部走 **Stage 0R direct path**（per Sprint 2 Q1 lock）。
- 候選 evidence 仍按 SSOT 走 scorecard + 5-gate；Stage 0R green = evidence accept；demo canary 另開 sprint。

### 9.2 對照軌不進 activation 池 rationale

SSOT §3 B0 明確：「5 textbook strategies are baseline/control only」。對照軌的功能是「給主軌 A1+A2 一個 baseline 比較」，不是「自己被排名 / 晉級 / 淘汰」。把對照軌算進 activation 池會：

- 把 N=5 閾值灌水（5 textbook 立刻達 N=5 卻不解決 P0-EDGE-1）。
- 違反 SSOT §3 B0 的「不做 textbook 拯救 engineering 投資」立場。

---

## 10. 未來 Sprint 激活預估時點

### 10.1 當前盤面（2026-05-28）

| 策略 | 7d n_settled（per TODO v77） | 進池狀態 |
|---|---|---|
| grid | ~30+（374 backfilled per memory，但對照軌不計） | 對照軌（不計 activation 池） |
| ma | ~25+（對照軌不計） | 對照軌（不計 activation 池） |
| bb_breakout | 1（demo 7d） | 暫不計（n_settled < M；30d catch-up 中） |
| bb_reversion | 3（demo 7d） | 暫不計（n_settled < M；30d catch-up 中） |
| funding_arb | retired（per AMD-2026-05-26-01） | **不計池** |
| A1 funding short-only v2 | 0（IMPL pending） | 待 IMPL + accumulation |
| A2 liquidation cascade fade | 0（IMPL pending） | 待 IMPL + accumulation |
| A3 BTC/ETH pairs | 0（stats DRAFT） | 待 IMPL + accumulation |
| A4 C13 defined-risk options | 0（data gate pending） | 待 data 驗 |
| A5 token unlock short | 0（Sprint 3+） | 待 external feed |

**當前激活池**：0 個策略滿足 C2（n_settled ≥ M=15）+ 1 個對照軌不計 = **C1 fail (0 < 5)**。

### 10.2 預估激活時點

> 注：此為粗略推估，非承諾；實際取決於 IMPL pace + demo 累積速度 + 策略 n_settled growth rate。

| 時點 | 假設 | 池組成預估 | 激活？ |
|---|---|---|---|
| **Sprint 2 完成（D+30，~2026-06-27）** | A1+A2 IMPL 完成 + demo 累積 30 天 + bb 30 天 catch-up 評估 | A1（n~10-20）+ A2（n~10-20）+ 可能 bb_breakout/bb_reversion 加入；2-4 個候選 | **不激活**（C1 fail：pool < N=5） |
| **Sprint 3 完成（~2026-07-25）** | A3 IMPL 完成 + A1/A2 累積 60 天 | A1（n~20-40）+ A2（n~20-40）+ A3（n~10-20）+ 可能 bb；3-5 個候選 | **邊界 / 可能激活**（C1 borderline；C2 部分策略可能仍 < 15） |
| **Sprint 4 完成（~2026-08-25）** | A4 data gate pass + IMPL，A1/A2/A3 累積 90 天 | A1+A2+A3+A4+bb（如 catch-up pass）= 4-5 candidates；每策略 n_settled 多數 ≥ 15 | **可能激活**（最早合理時點） |
| **Sprint 5 完成（~2026-09-25）** | A5 external feed 上線 + IMPL，所有前期累積 | 5+ candidates 各 n ≥ 15 | **激活高機率** |

**operator-actionable 結論**：

- **最早合理激活時點 = Sprint 4-5 之間**（~2026-08 至 ~2026-09）。
- Sprint 2 + Sprint 3 內部走 Stage 0R direct path，tournament 排名僅作 framing reserve。
- Activation 觸發前不寫 runner code（CLAUDE operating-style #2 + feedback_no_dead_params）；觸發後再開 PA ticket 拍板 §4-§7 slot 值。

---

## 11. Future Revision Path

本 spec 任何閾值變更（N=5 / M=15 / N-1=4 / 90 天 re-entry 限制）須走：

1. **AMD amendment**（governance-tier）；或
2. **新 ADR**（若為架構層變動，如 metric slot 啟用 / runner code 設計）。

不可在「執行中發現太緊就放寬」path patch（per CLAUDE.md operating-style #11 conflict surface + feedback_risk_changes_scoped）。

---

## 12. Acceptance Criteria

本 spec 完成判定：

1. spec land 至 `docs/execution_plan/specs/2026-05-28--alpha_tournament_activation_protocol.md`。
2. TODO v77 `P2-ALPHA-TOURNAMENT-ACTIVATION-SPEC` ticket 引用本 spec。
3. SSOT (`2026-05-26--alpha_tournament_ssot_spec.md`) §9 cross-document pointer 加本 spec link（PM 收尾時 land；本 spec 不改 SSOT）。
4. `docs/README.md` index 加本 spec（PM 收尾時 land）。
5. 沒有 code / runtime / DB / V### migration 改動（本 spec 純 governance ladder）。

---

## 13. Explicit Non-Goals

- **不寫** tournament runner code（無 Python class、無 Rust trait、無 cron job、無 dashboard frontend）。
- **不指定** 排名公式具體實作（§4 僅列 metric slot）。
- **不指定** K / X / cool-down / re-entry penalty 具體值（§5-§7 僅 slot）。
- **不改** SSOT §4-§6 scoring / gates / output lane。
- **不改** Stage ladder（per AMD-2026-05-15-01）。
- **不啟動** Sprint 2 tournament 排名運作（per Sprint 2 Q2 lock）。
- **不放寬** P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 / 5-gate boundary。

---

## 14. PA push-back 自評（對 N=5 / M=15 拍板早於有真實多策略 settled 樣本）

本節列 5 條最強反對 + 對應 mitigation。

### 14.1 反對 #1：N=5 / M=15 拍板無 empirical anchor

**反對**：當前盤面 0 個策略滿足 C2（per §10.1），N=5 / M=15 是「直覺猜測」，operator 拍板沒有真實多策略 settled 分布做 reference。若實際 demo 累積顯示 M=15 太緊（A1+A2 半年都打不到）或太鬆（30 天就達標但 edge 仍噪音），整個 activation 設計失去意義。

**mitigation**：
- 本 spec §11 明確 future revision path 走 AMD amendment，不假裝 N=5 / M=15 是永久 invariant。
- §10.2 預估激活時點 ~Sprint 4-5，給 6-9 月窗口可在「真實 settled 分布出來」後 amend。
- 即使閾值錯，Sprint 2-3 內部走 Stage 0R direct path（per §3.2），錯閾值不會傷 trading；只影響「何時開 PA ticket 拍 K/X」。

### 14.2 反對 #2：M=15 與 SSOT §5 sample gate (n ≥ 30) 不一致

**反對**：SSOT §5 sample gate 要 n ≥ 30 才給「preliminary verdict」；本 spec C2 用 M=15。兩個 gate 同時存在製造「策略 n=20 過 activation C2 但 fail SSOT §5 sample gate」的 edge case。

**mitigation**：
- §1.2 已明確分層：activation gate 是「**跨策略可比**的下限」，不是「該策略 edge significant」的 standalone gate。
- §2.2 rationale 已寫：M=15 是「跨策略可比」門檻；SSOT §5 sample gate 仍各自獨立跑。
- 同時存在不矛盾：candidate 可能進 activation 池但仍是 `observe_more` 出口（per SSOT §6）；activation 池存在不等於 candidate stage0_ready。

### 14.3 反對 #3：N=5 把 5 textbook 控制組踢出計算反而讓 N=5 永遠不滿足

**反對**：§9 把 grid+ma+bb_breakout+bb_reversion 都歸對照軌不算池。實際上池要靠 A1+A2+A3+A4+A5 5 個新策略全部 IMPL + settled 才能滿足 C1。一個策略 IMPL 失敗或被 reject = N 永遠 = 4，tournament 永遠激活不了。

**mitigation**：
- §10.2 預估時點已誠實標 ~Sprint 4-5 為「最早合理」（含 A4/A5 風險）。
- §3.1 凍結是「自動回 Stage 0R direct path」非「破口」；激活失敗不傷 trading。
- 若 Sprint 4 時 A4/A5 仍 0 進度，operator 可走 §11 AMD path 改 N=4 或重定 textbook 算不算池；本 spec 不卡死。

### 14.4 反對 #4：activation 拍板過早 → 形成「目標管理」反模式

**反對**：明確 N=5 / M=15 等於告訴 operator + agent「衝 N=5 / M=15 達標 = 進步」，會誘導工程資源往「拼湊策略數量」傾斜，而非「衝 P0-EDGE-1 真實 alpha」。SSOT §3 已警告「Avoid spreading engineering across unproven strategies」，本 spec 把 N=5 寫成目標反向動機。

**mitigation**：
- §0 已明確「scoring + gate + output lane 仍以 SSOT 為準」，activation 不取代 5-gate。
- §13 Non-Goals 明確不放寬 5-gate；策略硬塞進池但 fee gate fail / sample gate fail 仍會被 SSOT §6 `reject`。
- §2.1 排除 `reject` / `draft_only` / paper diagnostic，無法「灌水」進池。
- 本 spec land 後 PM 在 Sprint dispatch packet 反 reminder：N=5 是激活 floor，不是優化目標（per §8.2 status check）。

### 14.5 反對 #5：本 spec 設計 30+ slot `[future-iteration]` 等於 dead spec

**反對**：§4 metric slot、§5 K slot、§6 X slot、§7 re-entry penalty、§8 cron 入口全部 `[future-iteration]`。CLAUDE.md feedback_no_dead_params 禁線指「dead code 不可」；30+ slot 等於「dead spec」+ 違反 operating-style #2 no speculative implementation。

**mitigation**：
- 本 spec 角色 = **governance ladder permanent doc**，不是 implementation spec。Slot 是「decision deferred until activated」的 governance signal，不是「未實作的 code stub」。
- §13 Non-Goals 明確「不寫 runner code」是 spec 設計意圖（per Operator directive + Sprint 2 Q2 lock）。
- 對比反模式：若現在拍 K=2 / X=3，跑 6 個月後資料顯示閾值錯，反而違反 SSOT §11 「Do not prioritize cosmetics over fee-adjusted edge」。Slot 預留 = 誠實的「資料不夠拍」聲明，符合 operating-style #1 think before coding。
- TODO `P2-ALPHA-TOURNAMENT-ACTIVATION-SPEC` ticket 明確「禁線：不寫 runner code」是 operator 直接 mandate；本 spec 遵守。

---

**END Alpha Tournament Activation Protocol Spec**
