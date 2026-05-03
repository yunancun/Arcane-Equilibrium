# `replay_runner` e2e Test Fixtures

REF-20 Wave 4 R20-P2b-T1 — replay_runner end-to-end acceptance test fixtures.
REF-20 Wave 4 R20-P2b-T1 — replay_runner 端到端 acceptance 測試 fixture。

## 內容 / Contents

| 檔 / File | 用途 / Purpose |
|---|---|
| `synthetic_btcusdt.json` | 10-tick S3 synthetic OHLC fixture (BTCUSDT) used by the happy-path e2e test。10-tick S3 合成 OHLC fixture（BTCUSDT），happy-path e2e test 使用。|
| `key.hex` | 32-byte fixture HMAC signing key (hex-encoded). NOT a production secret — checked in by design for deterministic e2e replay。32-byte fixture HMAC 簽名 key（hex 編）。**非** production secret — 為確定性 e2e replay 刻意提交。|

The actual signed manifest JSON for each test case is constructed at test
runtime inside `tests/replay_runner_e2e.rs::write_test_manifest` so each test
can edit the body (happy path / signature mismatch / missing fixture /
forbidden trip / baseline-vs-candidate) without checking in a combinatorial
explosion of pre-signed manifests.

每個 test case 的已簽 manifest JSON 於 test 執行時於
`tests/replay_runner_e2e.rs::write_test_manifest` 內構造，使每 test 可編輯
body（happy path / signature mismatch / missing fixture / forbidden trip /
baseline-vs-candidate）而毋須 check-in 組合爆炸的預簽 manifest。

## V3 §6.2 + §6.3 Compliance

- **0 network call** — fixture 為 in-tree file，e2e test 不發 outbound HTTP。
- **0 IPC / dispatch / lease** — 對應 PA boundary §5 forbidden 清單。
- **macOS smoke 安全** — fixture 為 S3 synthetic（V3 §6.3 #1 允許）。
- **HMAC key 非 production secret** — 確定性 fixture key，與 production
  `replay_signing_key` 完全分離。
