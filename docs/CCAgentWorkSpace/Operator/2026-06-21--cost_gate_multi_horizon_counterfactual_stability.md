# Cost Gate Multi-Horizon Counterfactual Stability

日期：2026-06-21
狀態：source/test/docs checkpoint 完成

## 結論

我把 Cost Gate 被拒信號的反事實評估從單一 horizon 擴展為多 horizon 穩定性 scorecard。這避免我們只因 60m 之類單一持倉窗口不合適，就判斷某個被擋信號沒有盈利可能。

現在系統會標出：

- 跨多個 horizon 都像候選的 side-cell
- 只在某個 horizon 像候選的 side-cell
- 一個 horizon 可行、另一個 horizon 應阻擋的混合情況
- 多個 horizon 都確認應該阻擋的 side-cell

這是支持 demo 自主學習的源側能力，不是下單授權。

## 驗證

- Python compile passed
- Bash syntax passed
- DB audit + policy tests：`70 passed`
- Cron static tests：`12 passed`
- Alpha discovery tests：`44 passed`

## 邊界

沒有 runtime sync、沒有安裝 cron、沒有開 writer、沒有 PG 寫入、沒有 Bybit private/signed/trading call、沒有重啟、沒有 order authority、沒有 lower main/global Cost Gate。

下一個真正會產生數據的步驟仍是：operator 授權後做 runtime source reconcile/sync + preflight + cron/writer activation。
