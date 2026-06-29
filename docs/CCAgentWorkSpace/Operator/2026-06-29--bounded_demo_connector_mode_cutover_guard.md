# bounded Demo connector-mode cutover guard

已完成一個安全收緊：connector mode 切換 API 現在會拒絕「Demo key 還不對」的 preflight。

結果：
- source commit `d9336342d3ee45467f456224eca278da14673956`
- runtime 已同步並重啟 Control API 載入修改
- runtime dry-run 當時已驗證：因 `demo_api_slot:demo_api_key_expected_value_mismatch`，cutover 會 HTTP `400` fail closed；2026-06-30 更正後，此 mismatch 來源是 stale `BHw4...` expected hint
- env 未變：`BYBIT_MODE=read_only`、`BYBIT_CONNECTOR_WRITE_ENABLED=false`

2026-06-30 更正：`FWkGZX...g53T` 是正確 Demo Read-Write key；`BHw4...` 是 stale expected hint，不是 live/mainnet key 問題。

下一步：用新 source 重跑 readiness，不帶 stale `BHw4...` expected pin；如果 Demo credential/endpoint 綠，再切 Demo connector mode，然後才進 final-window BBO / Decision Lease / Guardian / Rust authority gates。
