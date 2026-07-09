# R4 文檔索引核實 — 2026-05-09

基準：HEAD `7fccad06` · 採集時間 2026-05-09 · 工作目錄 `/Users/ncyu/Projects/TradeBot/srv`

**Tally：✅ 8 / ⚠️ 8 / ❌ 9 / 🆕 5 · 索引完整度 ~75% · CRITICAL × 5 closed: 2/5**

## §1 Executive Summary

| 維度 | 2026-05-08 R4 audit | 2026-05-09 核實 | Δ |
|---|---|---|---|
| 整體索引完整度 | ~62% CRITICAL | **~75% HIGH** | +13% |
| CRITICAL × 5 修復 | — | **2 真補 / 1 部分補 / 2 結構補表面缺實質** | 2/5 真 closed |
| HIGH × 6 修復 | — | **4 真補 / 2 部分補** | 4/6 真 closed |
| MEDIUM × 5 修復 | — | **3 真補 / 2 缺** | 3/5 真 closed |
| LOW × 4 修復 | — | **0 真補 / 4 缺** | 0/4 真 closed |
| 新發現 issue (NEW) | — | **5 新 finding** | — |

**整體判斷**：本次 24h docs 修復 **比第一眼看上去差**。docs/README.md 雖加了 ~50 條，但 archive/ 區塊 51 文件**仍只列 7 條缺 44 條**；CCAgentWorkSpace 表 line 729-747 寫「17 個 Agent」**未補 MIT/BB**；SPECIFICATION_REGISTER LG-X 區塊新增但**順序錯位**（LG-X-04 給了 Ops 而非 Supervised-Live）且**完全缺 LG-X-05**；ADR 0015-0019 真寫但內容均約 30 行極簡（符合既有 ADR 0001-0014 體例）。

## §2 30 finding 逐條核實

### 2.1 CRITICAL × 5

| # | 原 finding | 核實命令 / 結果 | 結論 |
|---|---|---|---|
| C1 | docs/README.md 補 multi_agent_rework_2026-05-05/ 14 文件 | grep `multi_agent_rework\|MAG-\|AgentTodo\|ENGINEERING_PLAN` = 22 命中；line 179-193 列 14 條完整 | ✅ **真 closed** |
| C2 | docs/README.md 補 docs/agents/ 整章 | grep `issue-tracker\|triage-labels\|domain` 在 README = 0 命中；CLAUDE.md §十一 引用但 README 0 索引 | ❌ **未 closed** |
| C3 | docs/README.md 補 helper_scripts/SCRIPT_INDEX.md | grep `SCRIPT_INDEX` 在 README = 0 命中（SCRIPT_INDEX.md 自身有補 section 但 README 沒入口）| ❌ **未 closed** |
| C4 | SPECIFICATION_REGISTER 新增 Live Gate (LG-X) 區塊 | line 57「Live Gate Foundation Specifications (LG-X)」存在，列 LG-X-01/02/03/04 共 **4 條**；**完全缺 LG-X-05**（4 個 LG-5 RFC 文件全未登記）；且 LG-X-04 補的是 Live Ops Foundation 而非 LG-4 Supervised-Live → **編號錯位** | ⚠️ **表面 closed 實質缺漏** |
| C5 | SM-03 Reserved → Active；EX-03 / ARCH-02/03 / AUDIT-13 補 | 全 ✅ Active | ✅ **真 closed** |

### 2.2 HIGH × 6

| # | 原 finding | 結論 |
|---|---|---|
| H1 | ADR 0015-0019 補錄 5 條 | ⚠️ 真寫但內容稀薄 — 符合既有 ADR 體例 |
| H2 | docs/README.md 補 §一/§十 引用的 8/14 條指針 | ⚠️ 僅補 1/8 |
| H3 | docs/README.md 補 archive/ 缺漏 39 條 | ❌ 未補（仍 7/51 = 14%）|
| H4 | CONTEXT.md 補 LG-X / REF-19/21 / Agent Decision Spine / 3-Config / feature flag 8 條 | ✅ 真補（缺 MAG 直接定義 minor gap）|
| H5 | docs/README.md CCAgentWorkSpace 表補 MIT / BB | ❌ **舊表未補**；新區段補但舊表 stale，line 727 仍寫「17 個 Agent」 |
| H6 | EX-03 / ARCH-02/03 補登 register | ✅ 真 closed（重疊 C5）|

### 2.3 MEDIUM × 5

| # | 原 finding | 結論 |
|---|---|---|
| M1 | docs/README.md 補 audits/ 缺漏 10 條 | ⚠️ 未直接驗證 |
| M2 | docs/README.md 補 execution_plan/ 缺漏 5 條 | ❌ 未 closed |
| M3 | SPECIFICATION_REGISTER AUDIT-13 補 P0-DATA-INDICATOR-SWEEP | ⚠️ 取代而非補登（line 128 補的是 12-Agent Full Audit Fix Plan）|
| M4 | docs/README.md 補 `Last Updated: YYYY-MM-DD` header | ❌ 未 closed |
| M5 | MIT + BB workspace/README.md 補 | ❌ **位置錯**：補的是 `MIT/README.md` 與 `BB/README.md`（dir 根，非 workspace 子目錄）|

### 2.4 LOW × 4

| # | 原 finding | 結論 |
|---|---|---|
| L1 | AgentTodo.md / ENGINEERING_PLAN.md 命名違規 | ❌ 未處理 |
| L2 | PA reports `4.24TodoAudit*.md` rename | — 屬歷史，不要求修 |
| L3 | docs/CCAgentWorkSpace/Operator/ 加 README.md | ✅ 真補 |
| L4 | docs/governance_dev/DEPRECATED.md 補 | ⚠️ 檔存在；新增廢棄條目未驗 |

### 2.5 OK × 5（baseline 健康）

memory MEMORY 1:1 對應 / CCAgentWorkSpace 結構 / 18 sub-agent / 跨引用 / 命名規範 全 ✅。

## §3 NEW-ISSUE（5 條對抗性新發現）

| NEW # | 嚴重度 | 位置 | 描述 |
|---|---|---|---|
| N1 | **CRITICAL** | SPECIFICATION_REGISTER.md line 57-65 | LG-X 區塊**編號 vs RFC 名稱錯位**：原期望 LG-X-02=H0 / LG-X-03=Pricing / LG-X-04=Supervised-Live / LG-X-05=Constrained Autonomous Live。實補：LG-X-01=H0 / LG-X-02=Pricing / LG-X-03=Supervised-Live / LG-X-04=Live Ops Foundation。**LG-X-05 (LG-5 Constrained Autonomous Live) 完全缺**（4 條 LG-5 RFC 全未登記）|
| N2 | **HIGH** | docs/README.md line 729-747 | 表頭寫「17 個 Agent」但實際 18-agent；**完全缺 MIT 與 BB**（雖 W-AUDIT-1 addendum 補了 MIT/BB README pointer，舊表 stale）|
| N3 | **HIGH** | docs/README.md line 751-761 archive/ 區塊 | archive/ 實 51 個 .md 但只列 7 條；缺 4-01..4-22 早期 + 5-01/02/06/07 系列 共 **44 條缺漏** |
| N4 | **MEDIUM** | docs/README.md head | 缺 `Last Updated: YYYY-MM-DD` header → 接手 CC 無法判斷此索引同步度 |
| N5 | **MEDIUM** | docs/CCAgentWorkSpace/MIT/workspace/README.md & BB/workspace/README.md | 原期望 workspace/README.md 子目錄級；實補 MIT/README.md 與 BB/README.md dir 根級 → 位置不一致 |

## §4 對抗性 Push Back

### 4.1 對 W-AUDIT-1 closure 的核心反駁

PM commit `d90f3d10` 聲稱 W-AUDIT-1 source-closed，但 R4 實證：
1. **CRITICAL × 5 真 closed 僅 2/5**（C1 + C5），C2/C3/C4 仍開 → W-AUDIT-1 不該 closure
2. **C4 LG-X 編號錯位是 governance regression**：LG-5 是 18 blocker 中 #5「constrained autonomous live」核心 milestone，SPECIFICATION_REGISTER **完全缺 LG-5 條目** = 接手 sub-agent 看 register 會以為 LG-5 規格不存在
3. **CONTEXT.md 補了詞條但 SPECIFICATION_REGISTER 沒補對應 spec** → 詞彙與規格 SoT 漂移
4. **docs/README.md addendum 區塊** 加在「文檔索引」前但**沒整理進原有「目錄結構」分類** → 形成「addendum 區段管 W-AUDIT-1」+「舊區段管之前」**雙索引漂移**

### 4.2 對 ADR 0015-0019 內容的批評

- ADR 0015 ~30 行 → 沒揭示「為何 OpenClaw 不能持 Bybit 憑證但 Gateway Agent 能 read state」的 surprising boundary 或 trade-off
- ADR 0016 (Decision Lease Router) **未說明 W-C 24h window 為何優先於 MAG-082 真 PASS** = 缺 trade-off 分析
- ADR 0019 (GitHub Issues) **未說明為何不繼續 Linear**

但 **符合既有 ADR 0001-0014 體例**（同樣短小 30 行格式）→ push back 為「**MEDIUM** 改進建議」非「**HIGH** 必修」。

### 4.3 W-AUDIT-1 應重新開啟至以下三條完成

1. SPECIFICATION_REGISTER LG-X 重編號 + 補 LG-X-05
2. docs/README.md CCAgentWorkSpace 表補 MIT/BB（line 727 改 18 + 1 Operator）
3. docs/README.md archive/ 區塊補 44 條 OR 加「完整 ls」入口註記

### 4.4 對抗性 checklist 對照

| Checklist 項 | 結論 |
|---|---|
| docs/README 加了 5 條但 50+ 缺漏的多數仍缺 | ⚠️ 部分屬實 |
| LG-X 區塊新增但只列 LG-2 一條 / 缺 LG-5 amendments | ✅ 嚴格屬實 |
| ADR 0015 寫了但內容空泛無 surprising / trade-off | ✅ 屬實但合既有體例 |
| CONTEXT.md 詞條加但無定義 | ❌ 不屬實（詞條完整）|
| SM-03 還是 Reserved 不改 Active | ❌ 不屬實（已改 ✅ Active）|
| MIT/BB workspace/README 是 1 行 placeholder | ❌ 位置錯位 |

---

**R4 VERIFICATION DONE** · ✅ 8 / ⚠️ 8 / ❌ 9 / 🆕 5 · 索引完整度 ~75% · CRITICAL × 5 closed: 2/5
