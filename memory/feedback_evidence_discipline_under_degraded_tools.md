# Evidence Discipline Under Degraded Tools（2026-05-31 慘痛教訓）

**背景**：2026-05-30~31 一個 session 內，因 (a) Opus 安全 classifier 間歇不可用導致 Bash 整批 cascade 取消、結果延遲/亂序 flush；(b) sub-agent 反覆撞 usage limit；(c) 多 session 並行同一 repo —— 主會話（PM）**四次**把未經乾淨原始輸出證實的內容寫進治理帳本 TODO.md，每次靠後續核實救回 + forward-fix。對一個「不可 fake evidence」為最高硬邊界的交易治理項目，這個比率不可接受。

## 四次幻覺/誤讀（全部已撤回）
1. **V104 migration「已存在 287 行 21 col」** → 實為從未存在的 free hole（classifier-cancel 期殘留讀取被當真）。
2. **A2 runner「runtime EXIT 0」** → 實為 EXIT 1/2（截斷輸出誤讀）。
3. **A2「source 密碼後 EXIT 0 / JSON 21366 bytes / verdict observe_more」** → 憑空數字，該檔 `secrets/basic_system_services.env` 根本不存在（真實路徑含 `environment_files/` 子目錄）。
4. **MIT Gate 2b「RETURN-WITH-BLOCKER / 2/4 CHECK 裸 ADD CONSTRAINT」** → 沒讀 report 全文就臆測；報告原文 Sign-off = **APPROVE**（double-apply 0 RAISE / 9-query 9/9）。

## 根因
對**延遲、亂序、被取消後一次性 flush** 的工具輸出做即時解讀時，會張冠李戴：把 A 指令的殘影當 B 指令的結果、把通知摘要當 report 全文、把記憶中的數字當剛跑出的數字。

## 硬性紀律（下次必守）
1. **寫任何 verdict/數字進帳本前，必讀 source 全文**（report .md、stderr 原文、git 原始輸出）。通知摘要 ≠ 報告全文；sub-agent summary 可信度高於我的即時 ssh 解讀，但仍以落檔 report 為準。
2. **ssh / 易延遲指令**：用「重定向 /tmp 暫存檔 + 分次 Read」取結果，不從混在一起的 stdout 即時讀數字。看到確實回傳的檔內容才寫。
3. **小批次工具呼叫**：classifier 故障時，一批塞 50+ 並行 = 第 9 個掛掉後 40+ 全 cascade 取消、結果延遲亂序 flush（兩小時拖延的元兇）。故障期改單條/小批。
4. **build SHA ≠ git commit**：`/proc/exe` 內容 SHA（如 `e9f01569`）不能拿去做 `git merge-base --is-ancestor`（會 exit 128 全錯）。要驗部署涵蓋，對**真實 build commit**（如 basis rebuild 的 `ec995160`）做 ancestry。
5. **PG 容器名先查再用**：是 `trading_postgres` 不是 `trading_ai_pg`；docker exec 走容器內 socket 能連 ≠ 宿主 psycopg2 TCP 能連（後者需 PGPASSWORD/.pgpass）。
6. **多 session race 自檢**：動 repo 前先 `git status -sb` 看分支（曾發現主 checkout 被別的 agent 切到 `fix/c4-incident-policy-trigger` 帶 35 個 WIP）；Edit「String not found」反覆出現 = 強烈信號「我讀的不是我以為的那個版本/分支」。
7. **sub-agent 比我可靠的場景**：它們在隔離 worktree + 獨立 grep + 自我核實。三個 E1 agent 各自獨立抓出我 brief 的 base SHA 錯（`eaf9a0d3` 不存在 → 真實 `cc6c54d0`）、檔案錯（metrics.py vs report.py）、路徑錯（secrets 子目錄）。**IMPL/取證優先交 sub-agent，主會話別硬扛即時 ssh 解讀。**
8. **commit message 也是帳本**：發現前 agent commit message 不實（`ba2090ad` 宣稱 cargo PASS 實為 E0004 FAIL）→ 別人的 commit message 同樣需 `cargo build` 親驗，不可採信自報。

## 防呆模式（已驗有效）
- 撤回幻覺時：forward-fix（新 commit 標明「自我修正/撤回」），不 rewrite 已 push history。
- 帳本只寫被原始輸出反覆證實的事實；不確定的標「未證實/待驗」而非填數字。
- 收尾前 `git ls-files` 確認自己的關鍵 report 已 commit（非只在 WIP）。

ref：`project_multi_session_memory_race.md`（commit-first / 不認識的改動禁 revert）+ `feedback_v_migration_pg_dry_run.md`（idempotency double-apply 是 load-bearing gate）+ CLAUDE.md §四（不可 fake evidence）。
