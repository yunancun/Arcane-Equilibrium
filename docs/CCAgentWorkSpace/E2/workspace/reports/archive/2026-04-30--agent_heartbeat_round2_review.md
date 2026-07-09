# E2 Round 2 Adversarial Review — 5-Agent `last_heartbeat_ms` 契約

**日期**: 2026-04-30
**Repo state**: working tree (E1 round 2 unstaged), base = E1 round 1 + round 2 deltas
**範圍**: 5 round-1 findings (M-1 / M-2 / MED-1 / MED-2 / MED-3)
**判決**: **APPROVE_WITH_NITS → PASS to E4**

完整內容鏡像見 `srv/.claude_reports/20260430_220000_e2_agent_heartbeat_round2_review.md`（同檔複本，符合 Mac CC 本地 LLM 審核流程）。

---

## TL;DR

5 round-1 findings 全修：
- **M-1 strict** ✅ 4 agent on_message stamp 在 RUNNING gate 之後 (grep 驗 + 4 negative test)
- **M-2** ✅ TestStoppedAgentDoesNotStampOnMessage 4 case 真覆蓋 stopped path
- **MED-1** ✅ scout_agent.py:301-303 record_scan stamp 移入 with self._lock atomic
- **MED-2** ✅ produce_intel + produce_event_alert 蓋章刪除 + 2 改寫 negative test 鎖契約
- **MED-3** ✅ `_surface_heartbeat_ts(stats, card)` helper 抽出，4 build fn 改 1 行 call；Strategist 不套（保 eval-log 主路徑 + stats fallback）

CLAUDE.md §九 8/8 + OpenClaw 9/9 全綠。

3 informational findings 留尾不退回：
1. **NEW-RISK-1 MEDIUM**: `record_scan()` production 0 caller — Scout `last_heartbeat_ts` runtime 永不刷新（state chip 不受影響，建議下 wave 補 1 行 wiring）
2. **NEW-RISK-2 LOW**: M-2 contract 僅鎖 on_message stopped path；review_intent/_handle_intel/analyze_trade direct path 為設計 carve-out
3. **LOW-1**: helpers 827>800 警告線，但 round 1 governance accept 850 threshold；net +8 LOC vs round 1 為 MED-3 必要產物

E2 直接修動作: 0（注釋完整、無 typo / lint / dead import）。
