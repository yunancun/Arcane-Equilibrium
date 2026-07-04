# AMD-2026-07-04-01：DOC-06 Runtime Mutation 紀錄規則（before/after + manifest 泛化）

日期：2026-07-04
狀態：**Active — DOC-06 變更治理條款泛化**
作者：TW（per R4 cold-audit R2 + FA F2/F4 findings + CC「DOC-06 缺口」finding）
關聯規範：DOC-06（變更治理 / Change Governance V2）、DOC-07（審計持久化 / Audit Persistence）、CLAUDE.md §「Git And Sync」、根原則 8（每筆交易可重建可解釋）、根原則 12（系統行為由證據演進）
關聯 ADR：ADR-0001（項目憲法）
範圍：**所有 runtime mutation**（不限交易面）——crontab 增刪改、`git reset` / checkout / rebuild、engine / uvicorn restart、`OPENCLAW_DATA_DIR` / SSOT 路徑遷移、env-file 變更、PG 手動調參、cron pin 更新。**不含**：純程式碼 commit（已由 git 歷史記錄）、read-only 查詢。

## 背景（為什麼要做這個）

冷審計 R2 揭露一組同類缺陷：

- **FA F2**：2026-06-27 crontab 從 ~70 行重寫為 5 行，靜默移除 ~12 個既有 producer cron（edge label 回填 / edge estimates 刷新 / canary+halt PG audit mirror / alpha discovery / listing 哨兵），**無退役記錄、無 owner、無復查日、無 before/after 快照**（`crontab_pre_sha256=8403678a…` 雖有 sha 但快照檔落在 boot-volatile `/tmp`）。學習/進化 chain 上游 producer 因此無主 dormant——FA 規則下與「功能缺失」同級 gap。
- **FA F4**：cron expected-head pins 再度 stale（06-24 已修同類，一週內復發），因 pin-by-value 手改 crontab literal 缺結構化紀錄。
- **CC（DOC-06 缺口）**：2026-07-03 runtime `git reset` + engine restart（03:02–04:21 CEST）缺鏈接的 mutation 紀錄。

共同根因：**runtime mutation 是「git 看不見的操作」**（crontab / env / SSOT 路徑 / 進程重啟不進 commit 歷史），現行 DOC-06 對「代碼變更」有 change_audit_log 覆蓋，但對「運維面 runtime mutation」無等價強制紀錄腿。缺此腿，審計面（DOC-07 persistence）在運維操作處出現靜默斷點，違反根原則 8（可重建）。

## 關鍵決策（DOC-06 條款泛化，而非新建獨立 spec）

把 FA F2 對 crontab 提出的「須有 before/after + sha 記錄」要求，**泛化為 DOC-06 的一條通用 runtime mutation 紀錄規則**，適用於上列所有 runtime mutation 類別。選擇泛化進 DOC-06 而非另立新 spec 的理由：

- DOC-06（變更治理）本就是「變更需可審計」的正本 spec；runtime mutation 是「變更」的一個子類，語義同源，不應碎片化為第二套治理文件（避免治理文檔本身的 lineage gap）。
- 被否決方案：另立 `OPS-runtime-mutation` 獨立 spec。否決理由——與 DOC-06 職責重疊，會製造「代碼變更走 DOC-06、運維變更走 OPS-X」的雙頭治理，增加 agent 查表成本且易漂移。

## 條款正文（DOC-06 §runtime-mutation，新增）

> **DOC-06-RM-1（Runtime Mutation 紀錄強制）**：任何 runtime mutation 執行前後，須留下三件可持久檢核的證據：
> 1. **before 快照**：mutation 前的狀態（如 `crontab -l` 全文、`git rev-parse HEAD`、env-file 內容、`OPENCLAW_DATA_DIR` 指向、PG 相關參數值），連同其內容 sha256。
> 2. **after 快照**：mutation 後的同類狀態 + sha256。
> 3. **manifest**：一則結構化紀錄，至少含 `{時間戳(UTC), 操作者/觸發源, mutation 類型, 對象, 動機/關聯 ticket, before_sha, after_sha, revert 路徑}`。
>
> **DOC-06-RM-2（持久位置）**：before/after 快照與 manifest **不得只落在 boot-volatile 路徑**（如 `/tmp`，`tmpfiles.d` 標 `D` 每次開機清空 + 30d age 清理）。須落於持久路徑（`OPENCLAW_DATA_DIR` 指向的持久卷 / `var/openclaw` / NAS）或進 git-tracked 治理文檔 / PG audit 表。理由：F1 已證 `/tmp` SSOT 會在 reboot / 30d age 清理時靜默滅失，使 sha 引用逐步斷鏈。
>
> **DOC-06-RM-3（移除類 mutation 的裁決義務）**：凡 mutation 為「移除既有 runtime 能力」（如刪 cron、停 producer、關 flag），除 before/after 外還須顯式裁決被移除項的處置：**恢復 / 正式退役**，退役者須記 owner + 退役依據 + （若適用）復查日。無裁決地移除 = 與「功能缺失」同級缺陷（FA 規則）。
>
> **DOC-06-RM-4（pin-by-reference 優先）**：需隨 runtime head 前進而更新的 pin（如 cron expected-head），優先採 pin-by-reference（腳本內 `git rev-parse HEAD` 或 deploy 路徑維護的 pin file）而非 pin-by-value 手改 literal，以消除重複手動介入與 stale 復發（FA F4）。若必須 pin-by-value，該更新本身視為 runtime mutation，走 RM-1。

## 驗收標準

- 未來任一 crontab / git reset / restart / SSOT 遷移 / env 變更操作，可在持久路徑或 git / PG 找到對應 before/after + manifest。
- reboot 演練後，任一治理文檔 / TODO / 報告中以 sha 引用的 runtime artifact 仍可解析（承 F1 驗收）。
- 移除類 mutation 每條有顯式「恢復 / 退役 + owner」裁決記錄（承 F2 驗收）。

## 已知限制

- 本 AMD 是**治理條款泛化**，不含執行器實作。把 RM-1..RM-4 落為自動化（如 restart_all.sh 自動寫 manifest、crontab wrapper 自動 diff）屬後續 E1/E3 實作範圍，owner 待 PA 派工。
- 06-27 crontab 重寫與 07-03 git reset 兩起既發事件的**回溯補紀錄**（before 快照已在 /tmp 可能已隨 reboot 滅失）屬一次性 remediation，不在本條款泛化範圍，由 FA F2 fix 追蹤。
- 本 AMD 不改動 DOC-06 源 `.docx/.md` 正本條文；以 amendment 形式登記於 active governance 層（`amendments/` + SPECIFICATION_REGISTER），與既有 AMD 慣例一致。
