# AEG-S3 Gate-B Preflight Command Guard

日期：2026-06-12
角色：PM
Code checkpoint：`289fcbe8 [skip ci] Guard Gate-B preflight command guidance`

## 結論

AEG-S3 Gate-B preflight 已升到 v0.3，`recommended_command` 旁新增 operator guard。

這次不改 watcher、不自動啟動 probe、不連 Bybit、不寫 DB、不碰 runtime/auth/risk/order/trading。目的只是避免在 `WATCH_ONLY` 或樣本不足時，舊 Gate-B artifact 產出的 full-chain shell 被誤讀成「現在該執行」。

## 行為

新增欄位：

- `recommended_command.operator_recommended`
- `recommended_command.operator_status`
- `recommended_command.operator_message`

主要狀態：

- `HOLD_WAIT_FOR_ACTIONABLE_WATCH`：watcher 仍 wait-only 且 listing sample `<30`，full-chain shell 只作診斷提示，不建議執行。
- `RUN_ISOLATED_PROBE_BEFORE_FULL_CHAIN`：watcher 已是 `ACTIONABLE_START_NOW` / `ACTIONABLE_SCHEDULE`，下一步是 isolated 24h probe，不是直接跑 full chain。
- `RUNNABLE_FOR_RESEARCH_REVIEW`：artifact/sample gate 已滿足，full-chain 可作 research review，但仍不是 promotion proof，需 E2/MIT/QC。
- `BLOCKED_PRECHECK_FAILED` / `UNAVAILABLE`：先修 precheck 或補 artifact。

## 當前主線狀態

Linux `trade-core` true DB narrow check：

```text
PASS [81] lease_ipc_soak
FAIL [82] lease_ipc_soak_window  S3 not yet met: window=43.0h < 48h; probes=1290
```

`[82]` 48h gate 錨點仍是 `2026-06-11 03:59:37+02`，到期點約 `2026-06-13 03:59:37+02`。在本次 `2026-06-12 23:00+02` 查驗時，剩餘約 5 小時，不可提前收掉。

Linux live Gate-B preflight smoke：

```text
run_id=aeg_s3_gate_b_preflight_command_guard_20260612T2105Z
gate_watch.artifact_status=WATCH_ONLY
gate_watch.operator_action=WAIT_FOR_ACTIONABLE_WATCH
candidate_counts total=23 alertable=0 start_now=0 schedule=0 watch_only=1
listing sample_count=2
readiness_status=READY_BUT_SAMPLE_BELOW_GATE
recommended_command_operator_recommended=false
recommended_command_operator_status=HOLD_WAIT_FOR_ACTIONABLE_WATCH
```

結論：Gate-B 主線仍等 fresh Pre-Market / PreLaunch / standard-conversion window；本次補強讓 preflight 自己給出「不要從舊 artifact 跑 full-chain」的機器可讀 guard。

## 驗證

Mac：

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest helper_scripts/research/tests/test_aeg_s3_gate_b_preflight.py -q
# 8 passed
python3 -m compileall -q helper_scripts/research/aeg_s3_gate_b_preflight helper_scripts/research/tests/test_aeg_s3_gate_b_preflight.py
rg -n "control_api_v1|psycopg2|asyncpg|INSERT INTO|UPDATE |DELETE FROM|OPENCLAW_ALLOW_MAINNET|execution_authority|wss://stream.bybit.com|urlopen" helper_scripts/research/aeg_s3_gate_b_preflight
# no hits
git diff --check
```

Linux：

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest helper_scripts/research/tests/test_aeg_s3_gate_b_preflight.py -q
# 8 passed
python3 -m compileall -q helper_scripts/research/aeg_s3_gate_b_preflight helper_scripts/research/tests/test_aeg_s3_gate_b_preflight.py
grep -R -n -E "control_api_v1|psycopg2|asyncpg|INSERT INTO|UPDATE |DELETE FROM|OPENCLAW_ALLOW_MAINNET|execution_authority|wss://stream.bybit.com|urlopen" helper_scripts/research/aeg_s3_gate_b_preflight
# no hits
```

無 CI、無 deploy、無 rebuild/restart、無 DB/auth/risk/order/trading mutation。
