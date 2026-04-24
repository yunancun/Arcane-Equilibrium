---
name: 派 sub-agent 前 fetch + 查遠端 branch
description: Multi-agent 派發前必 `git fetch` + `git branch -r | grep <topic>` 查隔壁 session 是否已開 feature branch 做同題目，避免重複工作 + branch topology 混亂
type: feedback
originSessionId: 1d6c6364-1fdb-4b51-a62a-b4624f0fa446
---
規則：任何 multi-agent 並行派發（尤其 Wave-level TODO 批次）之前，必先跑：

```bash
git fetch --prune origin && git branch -r | grep -iE '<topic-keyword>'
git log --oneline origin/main -10  # 看隔壁剛推什麼
```

若匹配到 `origin/fix/<topic>` / `origin/<topic>-*` / 近期 commits 已帶 `<topic>` tag，**先判斷隔壁進度再決定派不派**：
- 已完成 → 跳過，TODO 標 [x] + 指向 commit
- 進行中 → 等或派補充工作（test / doc / review）
- 未動 → 正常派

**Why**：2026-04-24 G6 Wave 1 派發時沒先 fetch，結果：
- G6-01 被**重派** — 隔壁 session 早已開 `origin/fix/g6-01-healthcheck-5-defects` branch 做完 5 缺陷 + FUP [Xb]，我的 sub-agent 讀到 QA audit 後發現 4/5 已修（實際 5/5 都已修），重複工時
- Branch topology 一度混亂 — 我 commit 落到 feature branch `g1-06-drawdown-auto-revoke` 而非 main，需暫停等 operator 判讀 PR-style workflow 意圖
- G6-02 也被隔壁順手做了（commit `a0a4981`），我原計畫「G6-01 完成後接力派」多餘

**How to apply**：
- Multi-session 協作中，派發 sub-agent 或 background agent 前**必** fetch + 掃 branches
- 單 session 線性工作可略（無隔壁併發）
- 派發前一次 fetch 成本遠低於派發後發現重複的處理成本（branch 歸屬討論 / commit 拓撲修復）
- 亦適用：operator 說「隔壁 session 已派 X」時，不要盲信完成狀態，fetch + log 確認實際進度
