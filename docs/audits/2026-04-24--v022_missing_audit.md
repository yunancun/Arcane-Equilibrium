# V022 Missing Migration — Forensic Audit / V022 缺失遷移取證審計

- **Date / 日期**: 2026-04-24
- **Auditor / 審計**: E1 sub-agent (read-only forensic)
- **Severity / 嚴重度**: LOW (informational; no DB / runtime impact)
- **Verdict / 結論**: Case A+ — V022 曾以 file-only 形式短暫存在於 git，從未套用至任何 DB；已於 operator 指示下完整刪除。編號跳號 `V021 → V023` 為設計上正確的 sqlx 行為，不需補號。

---

## 1. Problem Statement / 問題陳述

DB `_sqlx_migrations` 套用版本序列：

```
[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 23, 24]
```

V022 缺失。同時 repo `srv/sql/migrations/` 列出：

```
... V020, V021, V023, V024, V999
```

V022 file 同樣不存在。問題：V022 是 **abandoned reservation** / **never existed** / **unapplied file** / **deleted file**？

---

## 2. Evidence / 證據

### 2.1 File-system check / 檔案系統檢查

```
srv/sql/migrations/V020__strategist_applied_params_tie_break.sql
srv/sql/migrations/V021__fills_exit_source.sql
srv/sql/migrations/V023__model_registry.sql                       # gap here
srv/sql/migrations/V024__guard_v019_v020_strategist_applied_params.sql
```

→ V022 file 不在工作樹。

### 2.2 Git history / Git 歷史

```
$ git log --all --oneline -- 'sql/migrations/V022*'
e6a7051 chore(sql): remove V022__grafana_views_engine_mode.sql migration
80b2e4b feat(grafana-views): expose engine_mode on trade_executions / order_events / position_snapshots
```

兩條 commit 共同證明 V022 file 曾在 `main` 分支存在過。

### 2.3 Lifecycle / 生命週期

| Phase | Commit | Author / Date | Action |
|---|---|---|---|
| Birth / 誕生 | `80b2e4b` | NCYu @ Mac · 2026-04-23 20:01 +0200 | 新增 `V022__grafana_views_engine_mode.sql` (118 行) — Grafana 橋接 VIEW 暴露 `engine_mode` |
| Death / 移除 | `e6a7051` | Nancun @ Linux · 2026-04-23 22:19 +0200 | `chore(sql): remove V022__grafana_views_engine_mode.sql migration` — operator-directed removal，文中明確說「Deletion staged in the Linux working tree; this commit lands it.」 |

存活時長：**約 2 小時 18 分鐘**，且全程未進入任何 `_sqlx_migrations` apply 視窗。

### 2.4 DB cross-check / DB 交叉確認

依任務上文，前手 adversarial agent 已驗證 `_sqlx_migrations` 無 version=22 row（任務文已陳述：「**前面 adversarial agent 證實沒**」）。本審計不重新觸 DB（read-only Mac SSOT 範圍）。

→ V022 從未被任何 engine 啟動週期套用。

### 2.5 Functionality re-absorption check / 功能是否被吸收檢查

V023 (`model_registry.sql`) 表頭明示：「INFRA-PREBUILD-1 Part B — learning.model_registry … ML model artifacts produced by `run_training_pipeline.py`」。與 V022 的 Grafana views 完全無關。

→ V022 撤銷並無「功能搬到 V023」的事實。Grafana engine_mode 暴露任務在當前 main 分支處於 **未實作** 狀態（dashboard 仍依賴 legacy `is_paper`，這是當初 V022 試圖修的問題）。是否重新規劃為新編號 migration，屬於後續產品決策，不屬本審計範圍。

---

## 3. Root Cause / 根因

V022 是一條 **生於 Mac dev、死於 Linux operator-directed removal** 的短命 migration。歷時 2h18m，完全在 file-only 階段被撤銷，從未進入任何 DB 的 `_sqlx_migrations`。

刪除 commit (`e6a7051`) 描述明確：「Operator-directed removal … Deletion staged in the Linux working tree; this commit lands it.」表明：

1. 這是 operator 的明確決定（非誤刪）；
2. Linux working tree 已先 stage 刪除動作，commit 只是「落地」；
3. 沒有走 revert 流程（避免 sqlx checksum mismatch 風險），而是純 `git rm`。

刪除原因未在 commit message 內展開，但從時序與 codebase 狀態可推：可能是 (a) Grafana view DROP+CREATE 對 production-like 的 demo DB 風險過高、(b) 想配合 dashboard JSON 一併重做、(c) 想換策略不動 view 改在 Rust writer 修 `is_paper`。本審計不臆測——這是 **設計決策**，非 **取證問題**。

---

## 4. Impact Assessment / 影響評估

| Dimension / 面向 | Impact / 影響 |
|---|---|
| sqlx runtime | **無**。sqlx 只檢查「DB 已套用版本是否與 file 對應」，不要求版本連續。`[..21, 23, 24]` 完全合法。 |
| DB schema | **無**。V022 從未 apply。Grafana bridge VIEW 維持 V005 原狀（即 legacy `is_paper`-only）。 |
| Grafana 面板 | **未修復**。原 V022 commit (80b2e4b) 描述的 bug — 「engine_mode 不暴露導致 demo/live/live_demo 全錯標」— 在當前 main 仍存在。需另案處理（建議命名為 `V025__grafana_views_engine_mode.sql` 或更高版本，**避免重用 V022**）。 |
| 既有 docs / TODO | **可能含過期引用**。若有任何 docs/TODO 提及 V022，應更新或刪除。本審計建議後續以 grep 掃過 `docs/`、`TODO.md`、`CLAUDE.md`。 |

---

## 5. Recommendation / 建議

### 5.1 不要補號 V022 / DO NOT reissue V022

理由：
- sqlx 以 `(version, checksum)` 配對驗證。若未來新增 file `V022__xxx.sql`，**sqlx 會視為「DB 應套用 V022 但 _sqlx_migrations 沒有對應 row」**，導致 startup migration runner 嘗試套用它。
- 此時若 V022 與 V023 / V024 邏輯衝突，或 V022 套用順序違反「先 V023 再 V022」的時間語意，會炸 schema。
- 即使技術上 sqlx 容許「out-of-order migration」（取決於 mode），補號仍會讓 schema 演化歷史混亂、難以 reasoning。

### 5.2 下一條 migration 一律用 V025+

- 當前最高 file/applied 編號為 V024。
- 下一條新增 migration 應為 `V025__<topic>.sql`。
- 跳號 V022 永久公開記錄於 git history（`e6a7051` deletion + 本審計 doc），不會誤導後續開發者。

### 5.3 規範補強 / Convention reinforcement

建議在 `srv/sql/migrations/README.md` 補一段 (本審計 **不** 自行修改，僅建議；操作後續處理)：

> **遷移編號為單調遞增、不可重用、不可補號。**
> 若某條 migration 在 file-only 階段（未 apply 至任何 DB）被撤銷，**不要**用相同編號重新發布，否則會讓 sqlx schema 同步邏輯混亂。改用下一個未使用編號。
> 若某條 migration 已 apply 至任何 DB 後需撤銷，必須改用「forward-fix migration」（新編號 + 反向 SQL），絕不 git revert 已 apply 的 migration file。

### 5.4 後續任務（非本審計範圍）/ Follow-ups (out of scope)

- **Grafana engine_mode 暴露任務**：V022 撤銷後此問題仍存在。是否重啟此 work item 屬產品決策。
- **Docs sweep**：grep `srv/docs/`、`TODO.md`、`CLAUDE.md` 是否含 V022 引用，避免 stale。

---

## 6. Conclusion / 結論

| Question | Answer |
|---|---|
| V022 是否曾存在於 repo？ | **是**。`80b2e4b` (2026-04-23 20:01 +0200) 創建。 |
| V022 是否曾 apply 至任何 DB？ | **否**。`_sqlx_migrations` 無 v22 row（前手已驗證）。 |
| V022 為何不在當前 working tree？ | **operator-directed removal**，commit `e6a7051` (2026-04-23 22:19 +0200)。 |
| V022 編號是否需要補回？ | **不需要且不應該**。下一條 migration 用 V025+。 |
| 是否需要 follow-up 修復？ | **本審計範圍內：無**。Grafana view engine_mode 任務獨立另議。 |

Case 結論：**A+** (file existed transiently, never applied, deliberately removed) — 低風險 informational finding。

---

## 7. Cross-references / 交叉引用

- Birth commit / 創建：`80b2e4b feat(grafana-views): expose engine_mode on trade_executions / order_events / position_snapshots`
- Death commit / 刪除：`e6a7051 chore(sql): remove V022__grafana_views_engine_mode.sql migration`
- Adjacent migrations / 相鄰：
  - `srv/sql/migrations/V021__fills_exit_source.sql`
  - `srv/sql/migrations/V023__model_registry.sql`
  - `srv/sql/migrations/V024__guard_v019_v020_strategist_applied_params.sql`
- Related memory log / 相關記憶：`engine_mode 標籤 live_demo 升級 (2026-04-16)` — `engine_mode` 來源語意背景。
