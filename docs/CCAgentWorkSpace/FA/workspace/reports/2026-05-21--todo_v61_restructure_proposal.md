# TODO v61 重構建議 — FA 業務視角

**日期**：2026-05-21
**One-line summary**：v60 散在於三軸缺失（Wave/Sprint 排程軸 × 業務鏈端到端軸 × Strategy Stage progression 軸），v61 應在 §0 加 wave/sprint banner、§1 改 Sprint Roster（5 strategy × Stage gate matrix 進 reference table 不 inline）、§3 改 P0 + Sprint 4-10 active sprint endpoint、§4 P1 容納 24 H 級 v58-H + 3 missing module 處置、§10 references 新增 strategy×stage matrix 路徑與 v5.7/v5.8 整合 entry point；過時條目 §0.5/§-1 H+I 批 closure 全 archive，§5.1 W-AUDIT-4b 縮到 1 行 footnote。

## 1. 業務鏈完整度 check

| 業務鏈環節 | v60 狀態 | v61 期望 | 操作 |
|---|---|---|---|
| 自動掃描 | §3 stale signal `learning.edge_estimate_snapshots` 14d 0 rows | 併入 P0-EDGE-1 范圍（v60 已併） | keep §3 訊號 + cross-ref §4 P0 |
| 策略選擇（5 strategy） | 散在 §3 業務根因 + §-1 歸檔 + v5.7 §1 + v5.8 §1 | inline 1 表 strategy × Stage 當前位置；acceptance 走 reference | 新增 §1.3 strategy roster table（5 行）|
| AI 風險評估 | §4 P0-LG-3 spec ready / §3 LG-1/LG-2 PASS-WITH-CAVEAT | inline + §10 references | keep |
| 下單 / Decision Lease | §5.2 P1-LEASE-1 + v5.8 §2 M1 LAL | 串到 §4 P1 acceptance 6 條 + v5.8 sprint 1A-β prerequisite | merge：P1-LEASE-1 acceptance 引 v5.8 M1 §2 |
| 止損 | §4 OPS-1..4 + Stage 4 5-gate | 保留現有 §4 P0 + §2 LiveDemo 不變 | keep |
| 學習 | §5.2 P1-LG-5 / §3 stale snapshot + v5.8 M4/M5/M10/M11 | inline §4 P1 LG-5 maturity watch（已 14d）+ M4/M10/M11 在 §1.2 sprint progression | keep + cross-ref |
| 進化 | §0.6 Sprint 1A-β-ε five-phase（D+0 ~ D+10）| §1.1 Sprint Banner 主視角 | 大改：§0.6 拆 §1.1 sprint banner + §1.2 wave/sprint progression + §4 P1 部分 |

**端到端閉合度判定**：v60 業務鏈描述散在 5 處（§0/§0.6/§3/§5/§-1），v61 應 collapse 到 3 處（§0 摘要 / §1 sprint roster / §3 當前 wave 業務鏈狀態）。

## 2. v60 → v61 業務條目處置矩陣

| v60 條目 | 業務性質 | v61 處置 |
|---|---|---|
| §0 摘要（17 條 inline）| 含 active + done 混合 | **重寫**：壓 6 條核心（current sprint / current wave / P0 status / 24h next action / runtime / pending operator decision）|
| §0.5 v5.7 12 prefix DONE | DONE 業務 acceptance 已驗 | **ARCHIVE**：搬 archive；TODO 留 1 行 closure marker + link |
| §0.6 v5.8 16 CRITICAL + operator checklist + readiness | active operator action 業務鏈起點 | **拆**：§1 五子節（§1.1 banner / §1.2 progression / §1.3 strategy roster / §1.4 operator checklist / §1.5 readiness 12）|
| §1 路線變更區（empty） | 已被 v5.8 取代 | **REMOVE**：§1 改為 Sprint Roster |
| §2 架構邊界 + 硬不變式 | stable refs | **MOVE 部分**：核心硬邊界留 §2 ≤10 行；其餘 reference CLAUDE.md §四 |
| §3 當前活躍狀態 | Phase 2a / LG-1/LG-2 / stale signal | **keep + 縮**：6 行壓到「current runtime evidence」§3 |
| §4 P0 — True-Live Blockers | active acceptance 3 條 | **keep**：3 行 stable |
| §5.1 W-AUDIT-4b retained 5 項 | observe-only | **REMOVE 主表 → footnote**：移 §11 reference 1 行 |
| §5.2 P1 active queue 5 條 | active | **keep + ADD 3 missing module + 24 H 級 v58-H** |
| §6.1 H+I 批 closure | DONE | **ARCHIVE**：搬 archive；TODO 留 1 行 marker |
| §6.2 Deferred / Passive Wait 7 項 | passive | **keep**：4 行壓到 §5 P2/P3 backlog table |
| §7 Dormant + Passive Wait | 6 項 | **keep**：4 行 stable |
| §8 排程 | calendar gate | **keep + 重排**：以 sprint progression milestone 為主軸 |
| §9 跨 Wave 衝突仲裁 | 4 條 | **keep + ADD**：v5.8 sprint 1A-β-ε 對 P0 順序衝突 |
| §10 派工規則 + Handoff SOP | stable workflow | **MOVE references-only**：TODO 留 1 行 link |
| §11 References | references list | **keep + 擴**：加 strategy×stage matrix / v5.7+v5.8 business consolidation / 13-module roster |
| §-1 歷史 closure | historical narrative | **REMOVE → archive index 1 行** |

## 3. v61 sections 業務優先順序建議

```
§0 摘要（≤ 6 條）
  - current sprint phase
  - current wave
  - active P0 status
  - next 24h operator action
  - runtime evidence
  - pending operator decision

§1 Sprint Roster + Wave Progression
  §1.1 Current Sprint Banner（Sprint 1A α/β/γ/δ/ε 五階段 + ETA + status emoji）
  §1.2 Sprint Progression Table（Sprint 1A → 10 列 ETA + 主要工作）
  §1.3 5 Strategy × Current Stage Roster（5 行）
  §1.4 Operator Action Checklist（D+0 ~ D+6 + Sprint 4 first Live ETA）
  §1.5 Sprint 1A-β Dispatch Readiness Checklist（12 條）

§2 架構邊界 + 硬不變式（≤ 10 行；cross-ref CLAUDE.md §二/§四）
§3 Runtime Evidence
§4 P0 Active（3 行）
§5 P1 / P2 / P3 — Engineering Queue + Backlog
  §5.1 active engineering（v60 §5.2 5 條 + 24 H 級 v58-H 群組）
  §5.2 3 missing module 處置（M14/M15/M16）
  §5.3 footnote: W-AUDIT-4b retained invariant 19
  §5.4 P2/P3 Deferred / Passive Wait（4 行）
§6 Dormant + Passive Wait（≤ 7 行；D-XX + earliest reactivate）
§7 排程 + Milestone（sprint progression milestone 主軸）
§8 跨 Wave 衝突仲裁（≤ 5 行）
§9 派工規則 + Handoff SOP（≤ 3 行 cross-ref）
§10 References（active only；≤ 25-30 paths）
§-1 移除（archive index 1 行）
```

## 4. business chain 缺口（如何在 v61 體現）

| 缺口 | v61 體現 |
|---|---|
| 5 strategy × Stage matrix 散布 | §1.3 strategy roster 5 行 + reference path |
| 13 module × 4 autonomy 維度 | §11 reference inline 1 行 + path |
| 3 missing module（M14/M15/M16）| §5.2 處置表 3 行 |
| 24 H 級 v58-H ticket | §5.1 分小群（M2/M3/M5/M8/M12/M13/M14-16/forgetfulness）|
| 資金路徑流圖 | §11 reference 1 行 |
| P0-EDGE-1 closure path | §1.2 Sprint 2 標 Alpha Tournament + §4 P0-EDGE-1 cross-ref |
| operator action checklist | §1.4 active checklist；歷史 D+0 archive |
| stale signal | §3 inline 1 行 + cross-ref §4 P0-EDGE-1 |

## 5. Reference 業務面 check list

§10 references 必含業務面 paths（≤ 25-30 條）：

```
業務 acceptance / consolidation：
  - v5.7 dispatch packet
  - v5.7 主檔 + v5.8 主檔
  - v5.7 FA business consolidation（5 strategy × Stage matrix §6 + 資金路徑 §7）
  - v5.8 FA executability audit（13-module business acceptance §0.6）
  - PM 最終 verdict（v5.8）
  - PA dispatch consolidation（v5.7 + v5.8）

Strategy acceptance：
  - C10/Unlock/Pairs/C13/Funding short → FA business consolidation §2.1-§2.5

Stage gate matrix：
  - Stage 0R/1/2/3/4 acceptance → FA business consolidation §3
  - Strategy × Stage matrix → §6

Governance：
  - 16 root principles → CLAUDE.md §二
  - 5-gate live → CLAUDE.md §四
  - Graduated Canary → AMD-2026-05-15-01
  - Bybit primary + Binance MD + DEX 不允 → ADR-0033
  - Cowork operator-assistant → ADR-0024
  - Earn governance → ADR-0030
  - M1 LAL → ADR-0034
  - Multi-venue gate → ADR-0040
  - AMD-2026-05-21-01-autonomy-vs-human-final-review

Runtime + Bybit：
  - Bybit API reference → docs/references/2026-04-04--bybit_api_reference.md
  - V103/V104 schema spec
  - V103/V104 PG dry-run
  - Earn governance spec

Archive：
  - 2026-05-19 v55 / 2026-05-20 v57.3 / 2026-05-21 v57.5 / 2026-05-21 v58 / 2026-05-21 v60 (new)
```

## 6. 5 strategy × Stage gate matrix 是否進 TODO 還是只 reference

**結論**：**只進 §1.3 5 行 roster + reference**；詳 matrix 不 inline。

理由：
1. 完整 matrix 含 5 strategy × 5 stage × 4 acceptance = 100+ cells，inline 超 200 行
2. FA business consolidation §6 已含完整 matrix
3. 業務看板需求是「快速看出每策略現在位置」，5 行 roster 已足

**§1.3 5 行 roster format**：

| Strategy | Current Stage | Next Stage | Sprint ETA | Notes |
|---|---|---|---|---|
| C10 funding harvest | 4 LIVE | – | – | demo spot leg paper-only Phase 1 |
| Unlock SHORT | 0 (DRAFT) | 0R Replay Preflight | Sprint 3 W15-18 | Tokenomist signal dep |
| Pairs trading | 0 (DRAFT) | 0 (Alpha Tournament) | Sprint 2 W12-15 | BTC/ETH cointegration |
| C13 defined-risk | 0 (DRAFT) | 0 (Alpha Tournament) | Sprint 2-6 | Bybit options demo 待驗 |
| Funding short-only | 0 (DRAFT) | 0 (Alpha Tournament) | Sprint 2-6 | high-threshold > 30% annualized |

## 7. 13 module × 4 autonomy 維度矩陣 處置建議

**結論**：**§5.1 P1 容納 13 module IMPL 進度（不展 matrix）+ §11 reference inline 1 行**

**§5.1 13 module IMPL 進度小群（按 Sprint phase 排）**：
- Sprint 1A-β/γ DESIGN：M1 LAL / M2 / M3 / M4 / M6 / M7 / M8 / M9 / M10 / M11
- Sprint 1A-δ interface stub：M5 / M12 / M13
- Y1 partial IMPL：M3 partial (Sprint 1B) / M11 nightly (Sprint 3) / M1 Tier 1 (Sprint 4) / M9 read-only (Sprint 4)
- Y1 末 ~ Y2 IMPL：M4 stage 2 (Sprint 8) / M7 auto-demote (Sprint 8) / M1 Tier 2 (Y2 Q2) / M6 Auto (Y2)
- Y2-Y3 IMPL：M2 enable (Y2) / M8 active trigger (Y2) / M10 Tier C-E (Y2-Y3) / M12 cross-venue (Y2-Y3) / M13 Y3+ / M5 Y3+

## 8. operator action checklist + 提醒節點（業務面）

**§1.4 inline 6 行 active operator action**；歷史完成（D1-D5 已批）archive 1 行 marker。

| 日期 | Action | 提醒 trigger | 卡進度後果 |
|---|---|---|---|
| **D+1 (2026-05-22)** | OpenClaw API key 發行日（5 min Bybit Web UI 查 last edited）| PM ping AM | 阻 Sprint 1B Earn first stake |
| **D+1-D+2** | Phase 2a 14d verdict 三選一（calibration r2 / accept 35% / Phase 2b LiveDemo）| clock 觸發 | 阻 P0-EDGE-1 → Sprint 4 first Live |
| **D+2-D+3** | review AMD-2026-05-21-01 草案（protected vs opt-in scope）| CC + PM ping | 阻 CR-3 + 7 auto-apply module |
| **D+3** | 提供 P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 closure ETA | PM ping | 阻 Sprint 4 first Live |
| **D+4** | batch review 4 ADR draft（0034 LAL / 0036 / 0037 / 0038）| TW + PM ping | 阻 CR-2/5/7 + V### spec |
| **D+5** | batch sign-off 12 ADR + 1 AMD + Console tab + Tokenomist | PM ping | 阻 Sprint 1A-β 派發 |

**業務面提醒節點原則**：每個 operator action 必標「卡進度後果」（business chain 鏈接影響）。

## 9. 對 PM 整合的 top 3 必收建議

1. **§1 改 Sprint Roster 作為主視角**：v60 業務鏈散在 5 處（§0/§0.5/§0.6/§-1/§5），v61 §1 五子節集中
2. **§5 P1 必容納 3 missing module（M14/M15/M16）+ 24 H 級 v58-H 群組**：business chain 缺口完整可見
3. **§10 references 必補「strategy × Stage matrix」+「資金路徑」+「13-module business acceptance」三條 path**

**v61 預期行數**：v60 400 → v61 200-250 行（壓 40-50%）
