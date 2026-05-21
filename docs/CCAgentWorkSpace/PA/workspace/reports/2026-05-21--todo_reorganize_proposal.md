# PA Proposal — TODO 重排（read-only audit）

**日期**：2026-05-21
**Owner**：PA
**Trigger**：operator 反映 TODO 散亂，要求 PA+FA read-only audit + PM consolidate rewrite
**Status**：✅ PROPOSAL DONE — 待 PM consolidate FA G2 後 rewrite TODO

## §A 當前散亂問題清單（基於 v58 549 行實讀）

| # | 問題 | 證據（line range） | 嚴重度 |
|---|------|---------------------|--------|
| A-1 | 歷史段+空白 banner 占 §0 / §1 / §-0 / §-1 / §0.0 五大塊 ~100 行卻無 actionable | L1-122 | HIGH |
| A-2 | 「翻譯與歸檔說明」14 行 archive index 混在 §0 之後，非派工資訊 | L69-83 | HIGH |
| A-3 | §4.1 Wave Roster 12 列大表充滿已 closure 列 | L152-163 | MEDIUM |
| A-4 | §6 + §6.1 + §7 + §8 共 30 行純歷史 verdict + SOP（非派工）| L188-232 | HIGH |
| A-5 | §11.4 P0-MICRO-PROFIT 30 行 QC verdict + 守則 + reference | L299-328 | MEDIUM |
| A-6 | §11.5 EDGE-P2-3 Phase 1b 摘要 22 行（DEPLOY DONE；剩 verdict watch 一句即可）| L330-350 | MEDIUM |
| A-7 | §11.6 12-Agent Audit follow-up（4 條全 DONE 或 deferred；無 active）| L352-362 | MEDIUM |
| A-8 | §12.2 + §12.3 + §12.3a + §12.4 closure ledger 共 ~60 行 | L375-435 | HIGH |
| A-9 | §13 Push Back 治理記錄全 RESOLVED 2026-05-09 | L439-453 | MEDIUM |
| A-10 | §16 References 58 行 reference dump | L493-549 | HIGH |
| A-11 | 「待 operator 拍板（不主動推）」5 條夾在頭部說明區，與 §3 / §10 / §11.3 各有重複 | L27-32 | MEDIUM |
| A-12 | 重複 metadata（v58 closure trail / commit chain / 待 operator 拍板）三段各占 8-10 行說同個故事 | L7-32 | HIGH |

**散亂總診斷**：549 行裡，P0/P1 active actionable 實際只 14 條，佔比 < 5%；其餘 ~90% 為歷史 closure / passive wait / governance reference / archive index。

## §B 新 layout 建議（目標 ~280-320 行，從 549 縮 ~42%）

```
§0 摘要（5 行 max）
§1 路線變更區（保留空白，待 operator 重填）
§2 硬邊界 + 架構契約（10-12 行 max）
§3 當前活躍狀態（compact bullet ≤ 8 條）
§4 P0 active queue（表格 ≤ 4 列）
§5 P1 active queue（表格按優先級 sort ≤ 12 列）
§6 P2/P3 backlog（表格 ≤ 15 列）
§7 Dormant + Passive Wait（表格 ≤ 10 列）
§8 排程（表格 ≤ 6 列）
§9 跨 Wave 衝突仲裁（表格 ≤ 5 列）
§10 派工規則 + Handoff SOP（精簡 10 行）
§11 References（≤ 20 條）
§-1 歷史 closure 一段話留底（≤ 5 行）
```

**預估行數**：280-320 行。

## §C 可歸檔條目（明確 line range）

| Range | 內容 | 行數 |
|-------|------|------|
| L7-32 | v58 metadata 重複 | 26 |
| L46-50 | §-1 v56 P0 closure 段 | 5 |
| L52-83 | §0 v55 + 翻譯歸檔說明 | 32 |
| L99-105 | §1 Sprint Milestone Banner（空白）| 7 |
| L150-163 | §4.1 Wave Roster ✅ DONE 6 列 | 8 |
| L188-208 | §6 W-AUDIT 優先順序 + §6.1 A4-C tombstone | 21 |
| L211-217 | §7 W-AUDIT-6d Mid-Ground | 7 |
| L219-231 | §8 D-02 Layer 2 SOP（移 `docs/references/`）| 13 |
| L263-266 | §11.1 Sprint N+0 Active（空白）| 4 |
| L299-328 | §11.4 P0-MICRO-PROFIT QC verdict 全文 | 25 |
| L330-350 | §11.5 EDGE-P2-3 Phase 1b 摘要 | 19 |
| L352-362 | §11.6 12-Agent Audit follow-up | 11 |
| L375-377 | §12.2 P2 sweep 結算 | 3 |
| L401-435 | §12.4 27 條 ✅ DONE 詳情 | 28 |
| L439-453 | §13 Push Back / 4-agent audit cross-fact-check | 15 |
| L495-549 | §16 References 全文 | 38 |

**估算**：移歸檔 ~245 行，本檔淨削 ~190 行；最終 549 - 190 ≈ 360 行；如再合併 §4.1 6 列 → 310-330 行。

## §D 可立刻派的 actionable（owner 推薦）

| # | ID | Owner | 工時 | 判斷 |
|---|----|-----|-----|------|
| 1 | P3-AUDIT-SCRIPT-STALE-CONST | E1 | 30min | 立刻派 |
| 2 | P2-DYN-STOP-FLOOR-SENTINEL | E4 | 30min | 立刻派 |
| 3 | P2-LG1-DEMO-SLO-CARVEOUT | PA spec → E1 | 130 LOC + Grafana | 立刻派 |
| 4 | P2-PHYS-LOCK-72-HEALTHCHECK | PA spec → E1 + E4 | 4-6h | 可派（需 PA spec 1-2h）|
| 5 | P1-SWEEP-A-AXIS-PRUNE | — | — | DEFER（下輪 sweep）|
| 6 | P1-WATCHDOG-NETOUTAGE-SPARSE-LOG-OQ | — | — | DEFER |
| 7 | P2-FALLBACK-DEAD-ENUM-90D-AUDIT | — | — | PASSIVE WAIT 2026-08-21 |

**立刻派數量：4 條**（#1-#4），總工時 ~6-8h；1d 內並行收口。

**Dispatch 建議順序**：
1. 批 A 並行：#1 (E1, 30min) + #2 (E4, 30min) — 1h closure
2. 批 B 並行：#3 PA spec (1h) + #4 PA spec (1.5h)
3. 批 C 並行：#3 IMPL (E1) + #4 IMPL (E1a) + E4 對抗 — 1-2d

## §E 應移到 archive 的歷史 section（content path）

新 archive `docs/archive/2026-05-21--todo_v58_layout_refactor_archive.md`：

```markdown
## §A v58 closure metadata（從 TODO header 移出）
## §B v55 一段話留底
## §C 翻譯歸檔索引
## §D §6 W-AUDIT 優先順序歷史 verdict
## §E §6.1 A4-C tombstone 歷史 verdict
## §F §7 W-AUDIT-6d 砍 6 ledger
## §G §8 D-02 Layer 2 SOP（再移 `docs/references/`）
## §H §11.4 P0-MICRO-PROFIT QC verdict 全文
## §I §11.5 EDGE-P2-3 Phase 1b 摘要
## §J §11.6 12-Agent Audit follow-up
## §K §13 Push Back 治理記錄
## §L §12.4 27 條 P2 closure detail
```

**§16 References 拆分**：
- Active spec / AMD（≤ 8 條）留主 TODO §11
- Historical reports / closed audits（≥ 38 條）移 `docs/archive/references/2026-05-21--todo_v58_references_archive.md`

## §F OQ 給 PM 決議（10 條）

| # | OQ | 影響 |
|---|----|-----|
| OQ-1 | 路線變更區 §-0 / §1 / §14 三個空白 placeholder 是否合併到單一一行？ | 削 6 行 |
| OQ-2 | §0.0 PM Freeze A4-C tombstone 是否提到 §2 架構邊界主節？ | 削 13 行 |
| OQ-3 | §4.2 跨 Wave 衝突仲裁是否合入 §10 P0 active queue？ | 削 12 行 |
| OQ-4 | §9 Dormant D-XX 是否合併入 §7 Dormant + Passive Wait？ | 結構統一 |
| OQ-5 | §11.2 W-AUDIT-4b retained 5 列是否折成 §6 P2/P3 backlog？ | 削 13 行 |
| OQ-6 | §-1 v56 P0 closure marker 是否合入 §0 摘要？ | 削 5 行 |
| OQ-7 | 「翻譯與歸檔說明」是否整段刪除？ | 削 15 行 |
| OQ-8 | §15 派工規則是否從 TODO 提到 `docs/agents/todo-maintenance.md`？ | 削 22 行 |
| OQ-9 | 「待 operator 拍板（不主動推）」5 條是否每條對應到 §4-§6 表格的 status column？ | 結構統一 |
| OQ-10 | §-0 / §-1 / §0 / §0.0 / §1 五個負/零開頭節是否簡化為 §0 摘要 + §1 架構邊界？ | 編號統一；削 ~25 行 |

## PA 結論（給 PM 拍板用）

1. **Layout 主要改動**：549 行 → ~310 行（縮 42%）；移除 §-1 / §0 / §0.0 / §1 / §6 / §6.1 / §7 / §8 / §11.1 / §11.4 / §11.5 / §11.6 / §12.2 / §12.4 / §13 全部或大部分歷史 verdict + closure ledger（移歸檔），保留 §0-§10 + §11 References + §-1 closure index — 共 11 節。

2. **可歸檔行數估算**：~245 行移歸檔；本檔淨削 ~190 行。

3. **可立刻派 actionable**：4 條（總工時 ~6-8h）— P3-AUDIT-SCRIPT-STALE-CONST + P2-DYN-STOP-FLOOR-SENTINEL + P2-LG1-DEMO-SLO-CARVEOUT + P2-PHYS-LOCK-72-HEALTHCHECK；其餘 3 條 DEFER / PASSIVE WAIT。

PM 決議 OQ-1 ~ OQ-10 後可開始 rewrite。
