# 決策：路線歷史與工程交付的 Git 記錄方式

決策 ID：`RH-20261003-01`。記錄／分類採用日期：2026-10-03（Asia/Shanghai）。
狀態：**Accepted — 歷史分類與記錄方式**。
Operator 明確要求：「按照你描述的R1-R8（我會採用）和版本變化歷史寫進git」。
接受範圍是 R1–R8 的追溯分類及本記錄機制；R8 的供應商、實作與遷移仍為候選。

## 背景與選擇

現有 `CHANGELOG.md` 記 v5.x 計畫，`docs/CLAUDE_CHANGELOG.md` 記日常工程與 TODO 修訂。
Rust 遷移、融合方案、AIML 計畫、DB migration 各有自己的版號。它們不構成統一產品 release。
五月多輪草案甚至同日出現，僅按數字遞增會把審議、修正、採用及部署混為一談。

採用 Git 內的可攜文件與結構化索引，加上提交 trailers 和 annotated tag。
不採用僅存聊天／工作區外報告的紀錄；不以 Git notes 作唯一正本（一般 clone 不會自動帶回）；
不回寫舊 commit message、不替舊提交補造當年採用日期，也不建立八個暗示歷史 release 的標籤。

## 正本與分工

| 層 | 正本 | 更新時機 |
|---|---|---|
| 路線 ID、版本映射、事件、固定來源 | [route-history-register.json](../references/2026-10-03--route-history-register.json) | 有 route event 或歷史更正時 |
| 人類可讀歷程與理由 | [路線總覽](../references/2026-10-03--route-history.md) | 同一提交同步受影響行 |
| 具體路線決策 | `docs/decisions/YYYY-MM-DD--<topic>.md`；權限／架構規範仍走既有 ADR/AMD | 提出、採納、取代、撤回或更正時 |
| 日常工程交付 | `docs/CLAUDE_CHANGELOG.md`／既有交付報告＋Git commit | 可用能力或驗證／採用狀態有實質變化 |
| 現行工作佇列 | `TODO.md` | 依既有派工規則；歷史表不派工 |

R1–R8 是**回溯分期**，可能重疊；`follows_in_retrospective` 僅表敘事順序，
不是「前一代全數退役」。R7 表示交付重心，R6 未完成需求仍保留；R8 候選不自動取代 R7。
以 `Route-Id`（而非裸 R 編號）限定此命名空間，避免與 reviewer R4、其他任務 R1 等混淆。
五月版號屬 `May-2026-strategy-roadmap` family；所有跨 family 的同名 v1/v2 都分開處理。

## Git 提交與查詢

路線事件獨立成可審查提交；一般工程提交在真正相關時加 route trailer。
提交使用 subject＋body，末尾保留以下欄位（多路線可重複 `Route-Id`）：

```text
docs(history): record R8 architecture decision

說明觸發原因、選擇、保留能力、被取代範圍與具名未驗項目。

Route-Id: R8
History-Event: proposed
Decision-Ref: docs/decisions/YYYY-MM-DD--topic.md
Evidence-Level: planning-only
```

`History-Event` 可用 `retrospective-baseline`、`proposed`、`accepted`、`superseded`、
`withdrawn`、`corrected`、`delivery`；它描述本次事件，不代表交易權限。
`Evidence-Level` 必須符合實際範圍，如 `planning-only`、`source-only`、
`runtime-verified`；mixed delivery 應在正文逐項界定，避免一個詞替全系統背書。
`Delivery-Id` 可引用既有 H2／D1.1 等工作 ID，`Plan-Revision` 可引用既有帶 family 的計畫版號。
這些是人工可查詢的記錄慣例，不是新增的強制 CI／派工權限介面。

在 repo 根執行：

```sh
# 精確找到 R7 相關的新式提交，包含尚未整合的本機分支
git log --all --extended-regexp --grep='^Route-Id: R7$' --format='%h %ad %s' --date=short
# 找路線基準與其他歷史標籤
git tag --list 'history/routes/*'
# 讀取第一次記錄時的版本映射，不受後續檔案變動影響
git show history/routes/2026-10-03:docs/references/2026-10-03--route-history-register.json
# 查總覽怎樣演變
git log --follow -p -- docs/references/2026-10-03--route-history.md
# 查某一來源的當時內容：用登記簿內 commit 與 path
git show <commit>:<path>
```

旧提交不補 trailer；用登記簿的 `sources`／`engineering_anchors` 找回原來源。
annotated tag `history/routes/2026-10-03` 指向**本次最終記錄提交**，tag 訊息說明
它是 retrospective recording baseline，不是 R8 release／部署／採用認證。
未來只在重要歷史基準更新时加新日期標籤，保留舊 tag 不移動；一般修補用 commit 即可。
Git tags 不會因只 push branch 而全部送出；獲准發布時明確選擇 branch 與 tag。
本次授權是本機 Git 記錄，不自動包含遠端發布。

## 後續更新步驟

1. 區分路線方向／範圍／順序變動，與一般工程交付。工程修補沿用既有 Route-Id；
   只有新的主要方向才由 Operator 決定是否新增 R9 等 ID。R8 從候選變採納沿用 R8。
2. 在有日期的決策中記「為何改、舊／新做法、保留能力、取代範圍、批准者及狀態」。
   `effective_on` 只有來源能證明才填；`recorded_on` 永遠是真正記錄日期。
3. 在 JSON 追加唯一事件，連結決策、路線和來源。來源已 commit 時固定 `commit/path/blob/sha256`；
   同提交新增文件用 `recorded_file/path/sha256`，之後由該提交歷史固定身份。
   新路線或狀態變化同步總覽，工程結果接回原工程日誌。更正用 `corrected` 事件引用原事件，
   保留被更正內容及原來源；不把過去的失敗、候選或未驗改寫成成功。
4. 檢查唯一 ID、引用完整性、來源在指定 Git object 中存在、blob/hash 一致、
   文件連結與統計數相符；路線內容走原 docs review。小型純文件改動不跑無關產品測試。
5. 一次提交同步資料、可讀視圖與必要入口，寫入 trailers。既有審查、commit／merge／push
   授權規則照常；各種採用／效果狀態分開記，不能以記錄提交關閉 runtime gate。

`recorded_file` digest 以新增當時的 bytes 為準，日後改文檔需追加新來源記錄，保留舊記錄的 Git 版本。
歷史來源日期比記錄日期早是正常情況，不能把目前 source snapshot 說成當時的主機證據。
分支 checkpoint 可能不隨 main clone 取得；僅作額外定位，關鍵歷史必須有 repo 內可攜摘要。

## 驗收範圍

八個路線 ID；五月十八個審議節點（十六份獨立正文、一份 changelog、一個間接引用）；
來源固定並能離線還原；R8 仍候選；現有入口與兩層 changelog 可抵達歷史正本；
Git log／show／tag 能找到本次基準。以上不宣告整個產品已發佈、學習落地或盈利。
