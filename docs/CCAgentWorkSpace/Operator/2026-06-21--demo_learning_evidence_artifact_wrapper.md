# Demo Learning Evidence Artifact Wrapper

新增一個只讀 wrapper：`helper_scripts/cron/demo_learning_evidence_audit_cron.sh`。

它把 demo learning composite audit 變成可排程 heartbeat，輸出 latest Markdown/JSON 和 status log。用途是持續回答：demo 是在累積可學習證據，還是只是 observation telemetry；Cost Gate rejects 是否已記錄；learning ledger / blocked outcomes / review candidates 是否真的在累積。

本次沒有安裝 cron、沒有啟用 writer、沒有重啟 runtime、沒有下單權、沒有降低 Cost Gate。

建議下一個 operator decision 不是全局 lower Cost Gate，而是：在 source/env/runtime 對齊後，是否批准 bounded cost-gate learning lane 的 runtime writer + cron activation，讓被 Cost Gate 擋掉的 demo 信號能形成 ledger/outcome/review 閉環。

驗證：wrapper `bash -n` PASS；新 cron static 6 passed；合併 smoke（`--import-mode=importlib`）75 passed；audit focused 16 passed；cost-gate learning policy 53 passed。
