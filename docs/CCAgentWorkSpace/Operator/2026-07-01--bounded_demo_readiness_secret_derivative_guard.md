# Bounded Demo Readiness Secret-Derivative Guard

已完成一個 source/test checkpoint，目標是解除 E3 對 standing-envelope runtime-refresh packet 的 secret-derivative blocker。

- `bounded_demo_runtime_readiness.py` 現在支援 `--redact-secret-derivatives`。
- redacted mode 只用 stat 檢查 `api_key` / `api_secret` 是否存在、是否 regular file、是否 nonempty、mode 是什麼；不讀 key/secret bytes。
- redacted mode 不輸出 API key 的 masked value、length、hash、expected-prefix length/hash、match derivative。
- 若 redacted mode 收到 expected-key hint 但沒有要求 strict match，它會保持 no-secret readiness，並記錄 advisory `demo_api_key_expected_value_redacted`。
- 若 redacted mode 同時要求 strict expected-key match，會 fail closed，因為不讀 secret bytes 就不能證明 match。
- directory / non-regular secret path regression 已補，避免把非檔案 secret slot 當成 READY。
- non-redacted strict expected-key mismatch 行為保留。

驗證通過：PM `py_compile`、相鄰 pytest `26 passed`、`git diff --check`；E2 final review `DONE`；E4 final verification `DONE`，包含 redacted no-byte-read smoke。

這輪沒有做 runtime/exchange action，沒有 Control API GET、public quote、Decision Lease、order、PG write、service/env/risk mutation、Cost Gate change、live/mainnet、fill/PnL/proof。runtime standing Demo envelope 仍是 expired；下一步仍是 `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`，重新產生 fresh exact E3/BB runtime-refresh request，並在 readiness path 使用 `--redact-secret-derivatives`、fast-balance capture 使用 `--forbid-env-token`。
