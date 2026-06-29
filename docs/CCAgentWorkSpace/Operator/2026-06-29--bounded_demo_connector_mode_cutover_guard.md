# bounded Demo connector-mode cutover guard

已完成一個安全收緊：connector mode 切換 API 現在會拒絕「Demo key 還不對」的 preflight。

結果：
- source commit `d9336342d3ee45467f456224eca278da14673956`
- runtime 已同步並重啟 Control API 載入修改
- runtime dry-run 已驗證：因 `demo_api_slot:demo_api_key_expected_value_mismatch`，目前 cutover 會 HTTP `400` fail closed
- env 未變：`BYBIT_MODE=read_only`、`BYBIT_CONNECTOR_WRITE_ENABLED=false`

目前仍未能下單，原因不是 engine 掛掉，而是 Demo key slot 還是 `FWkGZX...g53T`，不是你要的 `BHw4...` 前綴。

下一步：先在 GUI/approved settings API 寫入新的 Demo key+secret；readiness 變綠後，再切 Demo connector mode，然後才進 final-window BBO / Decision Lease / Guardian / Rust authority gates。
