---
name: project-2026-06-10-triend-sync-ops2-merge
description: "三端同步+ops2 merge+Mac 多 session 髒樹清理收口;rescue branch 持 stale L2_TODO 與 aeg WIP;fork memory 檔方向判定法"
metadata:
  type: project
---

# 三端同步 + ops2 merge + 多 session 髒樹清理 (2026-06-10)

**ops2 落地**:`fix/ops2-phase2-cutover`(原僅 Mac 本地 branch,從未推 origin——「merge-ready」工作差點只活在一台機器上)→ push origin → merge main **`fa88a487`** 零衝突。4 commits:a3d27729 cutover(remove Phase-1 IPC fallback,fail loud on missing signing key)+cf1b9320 E2 fixes+e34a8772 E4 負向測試+823e53ad CC doc-reconcile。觸碰面=rust live_authorization/main.rs+control_api live_trust_routes+fresh_start.sh,**零 cron 路徑→pull 安全,代碼靜止至重啟才生效**;rotation 仍 operator 9 月節點(due 09-08)。

**Mac 髒樹 60 檔分桶清理**(切 main 前):
- 31 檔與 main byte-identical(殘留副本)→ 直接吸收
- 17 檔孤檔(UT-NOT-ON-MAIN:13 報告/設計+4 memory)→ docs commit 入庫 main
- 9 M-divergent:E1/E2/E4 memory+feedback 純追加→入庫;**L2_TODO.md 本地=stale 舊版**(main 已是 deploy-DONE 新版,直 commit 會倒灌)+aeg builder/tests WIP(+202/−12 未走鏈)→只進 rescue
- 2 fork memory topic 檔(l2_d3_phase1_green/agents_skills_revamp):**本地較新**(引用收口 SHA `9e920c21`/「三端同步完」)→本地入庫,main 舊版留 history
- 全量快照 branch **`rescue/mac-dirty-2026-06-10`**(`1689b153`,已 push;勿 merge,純保存)

**教訓**:
1. fork 檔判方向不能只看 diff 行數,看**誰引用更晚的 commit SHA / 完成態敘述**(L2_TODO 本地舊但 memory topic 本地新——同一工作樹兩個方向並存)。
2. 「merge-ready」branch 必須 push origin 才算防丟;本地-only branch 是單點故障。
3. 三端同步期間 main 高頻移動(2h 內 02c80f3b→35d923aa→97a5c310 l2-owed 落地),每步 push 前 re-fetch,merge 用 worktree 不碰主 checkout。
4. Mac 主 checkout 三個 stash 未動(stash@{0} 他人 recovered WIP)。

關聯:[[project_2026_06_10_a_group_triage]](ops2 鏈出處)、[[project_2026_06_10_half_life_scipy_lane_fix]](同日 scipy 實裝)、[[feedback_fetch_before_dispatch]]
