# 2026-06-22 -- Alpha learning worklist completion gates

本輪把 `alpha_learning_worklist` 升到 v2。

新增重點：每個 learning task 現在不只說下一步做什麼，也說什麼證據算完成。

新增欄位：

- `completion_gate`
- `completion_status`
- `completion_evidence_required`

例如 runtime source reconcile 的完成證據會要求 source `SYNCED_CLEAN`、expected head match、dirty/behind = 0，並重新跑 activation preflight。MM signal search 的完成證據會要求 train/holdout sample-gated gross edge 清過 current fee round trip。Polymarket replay history 會要求 dated history ready、天數達標、PBO/breadth 欄位存在。

邊界：這仍是 artifact-only learning contract，不是下單、不是 probe 授權、不是 promotion proof、不降低 Cost Gate，也沒有 runtime 寫入。

驗證：learning worklist focused tests 2 passed，既有 alpha discovery focused suite 44 passed。
