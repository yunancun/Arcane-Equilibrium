# Demo Learning Evidence Killboard Ingestion

`alpha_discovery_throughput` 已接入 `demo_learning_evidence_audit_latest.json`。

效果：killboard 現在能看到 demo composite evidence，不只看 cost-gate plan/ledger/historical review。若 PG 已記錄大量 Cost Gate rejects 但 learning ledger 沒累積，blocker 會直接指向 bounded learning-lane enablement；若只是 observation-only telemetry，blocker 會指向 candidate/reject data coverage，不會誤標 probe readiness。

本次仍是 source/test/docs + artifact-only ingestion：不連 PG、不連 Bybit、不下單、不啟 writer、不安裝 cron、不重啟、不降低 Cost Gate。

驗證：`test_alpha_discovery_throughput.py` 36 passed；py_compile passed。
