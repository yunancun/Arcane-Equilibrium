# FA Short Re-Review — AMD v0.3 + spec v1.2

**Reviewer**: FA
**Date**: 2026-05-15
**Subject**: AMD-2026-05-15-02 v0.3 + spec v1.2 short re-review
**Mode**: Short focused — verify v0.2→v0.3 + v1.1→v1.2 patch 收口完整 + 治理 trace 完整度

> 註：FA agent read-only；本檔由主會話按 FA agent 返回原文存檔（governance trail completeness 補錄，內容已被 PA Wave 1.5b consolidated 報告 inline integrated 進 spec v1.3 + AMD v0.4）。

## §1 Review Scope（FA round 2 must-fix 對照 v0.3/v1.2 land 狀態）

Round 2 FA verdict（`2026-05-15--amd_2026_05_15_02_4agent_review_fa.md`）曾提 must-fix：spec §4.3 negative whitelist 真風控行明文 + AMD §10.1 V094 IMPL 順序 explicit。v0.3 / v1.2 land 後逐條驗：

| Round-2 must-fix | v0.3/v1.2 land 狀態 | 證據 |
|---|---|---|
| spec §4.3 negative whitelist 含 `risk_close:*` + `halt_session*` | ✅ land | spec v1.2 §4.3 |
| AMD §10.1 V094 IMPL kickoff 明列 schema invariant | ⚠️ 部分 | AMD §10.1 含 V094 表但 writer:430 / Fill enum 21→24 未顯列 |
| AC SoT 同步 spec 新增 AC-17/18/19 | ❌ 未跟上 | AMD §3 rollout 表仍寫「AC-1..AC-16」 |
| 16 原則表完整度 | ⚠️ 部分 | #3/#11/#13/#15 未明列 PASS（7/12） |

兩 must-fix 完整 / 部分；無新增 BLOCKER；剩 4 條為 cosmetic governance trace 補錄。

## §2 v0.3/v1.2 增量 governance trace 完整度 audit

### FA-#1 (cosmetic): AC SoT 引用 stale
**位置**：AMD v0.3.1 §3 rollout table「AC SoT」欄
**現況**：寫「AC-1..AC-16」；spec v1.2 §6 已加 AC-17（writer details payload 完整性）/ AC-18（schema invariant 兩段式驗證）/ AC-19（rollback 不變量保留 details）
**Patch**：改「AC-1..AC-19」一處 string replace；DOC-06 audit trail 範圍不再 stale。

### FA-#2 (cosmetic): V094 writer 升級依賴 explicit
**位置**：AMD §10.1 V094 backward-compat 表
**現況**：列 `payload_v` 引入 + `payload_v2` 影子寫但未明列上游 writer 依賴
**Patch**：IMPL kickoff bullet 加三條：
- `crates/openclaw_engine/src/storage/trading_writer.rs:430` details payload writer 升級為 schema v2 reflection
- `TradingMsg::Fill` enum 21 fields → 24（add `payload_v` / `details_v2` / `schema_invariant_check`）
- 兩段式 schema invariant（pre-fill / post-fill）對應 spec §6 AC-18

依據 Wave 1 Track A4 §4.4 writer gap finding；IMPL 不會落入「migration land 但 writer 沒升級」沉默 fail。

### FA-#3 (cosmetic): negative whitelist 變體補錄
**位置**：AMD §2.3 negative whitelist
**現況**：spec v1.2 §4.3 已列 `risk_close:fast_track*` / `halt_session*` 變體；AMD 主文未同步
**Patch**：AMD §2.3 末端加「真風控變體（per spec §4.3）：`risk_close:fast_track_*` / `halt_session_*` / `halt_session:*`」一行；AMD vs spec SSOT 完全同步，FA round 3 不需再 cross-check。

### FA-#4 (cosmetic): 16 原則表完整度
**位置**：AMD §7 16 根原則對照表
**現況**：7/12 PASS 明列（#1/#2/#4/#5/#6/#7/#8）；#3（AI→Lease→複核→執行）/ #11（P0/P1 內最大自主）/ #13（governance trace）/ #15（cross-platform）未列 PASS
**Patch**：補 4 行 PASS + 證據錨點：
- #3 → AMD §2.2 decision_lease_emitted 不變
- #11 → spec §5 Phase 1b 自主邊界（PA 範圍內）
- #13 → DOC-06 V094 audit trail full
- #15 → 無 `/home/ncyu` / `/Users/*` 路徑硬編碼新增

7/12 → 11/12（#9/#10/#12/#14/#16 N/A 標明即可）。

## §3 FA verdict

**判定**：APPROVED（4 cosmetic only）

**BLOCKER**：無

**Patch direction**：FA-#1 string replace；FA-#2 三條 bullet add（writer:430 / Fill enum 21→24 / 兩段式 invariant）；FA-#3 一行 negative whitelist 變體補錄；FA-#4 四行 16 原則 PASS + 錨點。全為純治理 trace 補錄，不影響 IMPL 排程；可於 IMPL kickoff 前 inline patch 完成。

**Risk**：4 cosmetic 不 fix 不影響 v0.3 / v1.2 runtime semantic，僅未來 audit 翻查時 DOC-06 trace 不完整 / round-3 FA 重 cross-check 浪費。建議 PA Wave 1.5b consolidated inline 一併 ship。

---

**Patch land 狀態（post-Wave 1.5b consolidation by PA）**：FA-#1 / FA-#2 / FA-#3 / FA-#4 4 cosmetic 全 ✅ 整合進 AMD v0.4 + spec v1.3（per AMD v0.4 changelog entry）。本短 re-review 為 audit trail completeness 追補。
