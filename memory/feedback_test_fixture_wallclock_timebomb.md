---
name: feedback_test_fixture_wallclock_timebomb
description: "測試 fixture 禁硬編日期——日期腐化型 time-bomb 已兩度發生(decision_packet/agent_governance),commit 當日綠、隔日轉紅"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 44dcb981-21bd-4402-aed2-973fd12f7f5f
---

測試 fixture 硬編「未來/當前」日期=日期腐化型 time-bomb:commit 當日綠、時間越過硬編值後轉紅,且紅測試會污染下游(如 command-capture replay 的確定性輸出契約)。2026-07 兩例:①`test_cost_gate_learning_lane_decision_packet`(07-10 修=凍結 `_utc_now`);②`test_agent_governance_capture` expired/future fixture(07-11 提交 07-12 轉紅,修 `b23e1f85d`=相對 `datetime.now(timezone.utc)` ±N 天)。

**Why**:時間窗校驗類測試的語義是「相對窗口」,硬編絕對日期把語義綁死在提交時點。

**How to apply**:寫或審含時間窗斷言的測試時,fixture 一律相對當前時鐘(±timedelta)或注入凍結時鐘;E2 審 diff 見到 fixture 硬編未來日期即退回;E4 見「昨日綠今日紅、diff 無關」先查日期腐化再查代碼。相關:[[feedback_indicator_lookahead_bias]](同為時間語義陷阱)。
