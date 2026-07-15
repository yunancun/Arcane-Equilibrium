# IBKR Live-Capability Loop — 進度帳本

> 協議正本:`docs/agents/ibkr-live-capability-loop.md`;工程正本:repo 根 `IBKR_TODO.md`;dispatch 正本:`TODO.md` W 行。
> 一輪一行,append-only;殘項欄禁空泛(「無」或具體 ticket/包名)。

| R | 日期 | 切片 | PR / merge SHA | 測試證據 | verdict | 殘項/教訓 |
|---|---|---|---|---|---|---|
| R0 | 2026-07-15 | loop 基建:協議正本 + 本帳本 + TODO v808 對位(W2 收口證據行 + W-CI 新行 + Links)+ IBKR_TODO §10 接線 + CHANGELOG v808 敘事 | PR #18(merge SHA 見 git) | docs-only;無代碼/runtime 變更 | LANDED | R1=W2 收口波(PA 設計文檔補簽→E2/E3 審→E4 Mac+Linux cargo→行遷移)+ W-CI 實作同輪派;R2 起 W3(session manager + fake-TWS harness) |
| R1 | 2026-07-15 | W2 收口四腿(PA 補簽/E2/E3/E4)+ W-CI 實作落地 | W-CI=PR#21 `48872c4f`(job 首綠 7m35s);記帳=本 PR;設計檔 `2026-07-15--w2_seal_caller_authority_design.md` 隨本 PR 入 repo | E4 雙腿同 SHA 全綠(engine 47/0、types 5/0、守衛 14);W-CI 五 scope 74+287+94+33+2+audit PASS;E2 兩輪(REJECT→APPROVE) | W2=四腿完成、修復待辦(行維持 ACTIVE);W-CI=DONE_LANDED_FIRST_GREEN | **E2-F1 HIGH(staggered-expiry brick,修法=expiry 只約束 active leaf)為 R2 主目標**;R2 切片=F1+E3 三缺口(/run/絕對路徑/errno)+anti-placeholder+F8/F10 負測試,E2-F2(AMD 綁定漂移)另走 CC 出典;殘:audit script 不在 classifier;教訓:字面 cargo filter 會空轉(名稱 filter 不含檔名),CI 接線必附執行計數證明 |
