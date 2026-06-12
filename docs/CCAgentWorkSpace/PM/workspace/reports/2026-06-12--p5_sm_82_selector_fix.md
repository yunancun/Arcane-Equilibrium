# P5-SM [81]/[82] Healthcheck Selector Fix

日期：2026-06-12
角色：PM
Commit：`bf673cdc [skip ci] Fix P5-SM healthcheck selectors`

## 結論

`passive_wait_healthcheck.runner --check 81 --check 82` 已修好。此前 runner 的 narrow selector 只支援 `[1] [4] [Xb]`，導致 TODO/SOP 寫的 `[81]/[82]` 手跑命令不可用。此批只修 CLI routing，不改 `[81]/[82]` healthcheck 判定邏輯。

## 改動

- `helper_scripts/db/passive_wait_healthcheck/runner.py`
  - `_run_selected_cursor_checks` supported set 增加 `81` / `82`
  - selected path 直接 dispatch：
    - `[81] lease_ipc_soak`
    - `[82] lease_ipc_soak_window`
- `helper_scripts/db/test_lease_ipc_soak_healthcheck.py`
  - 新增 selected runner routing test
  - 新增 unsupported selector rejection test

## 驗證

Mac：

```bash
PYTHONPATH=. python3 -m pytest helper_scripts/db/test_lease_ipc_soak_healthcheck.py -q
# 47 passed, 1 skipped
python3 -m compileall -q helper_scripts/db/passive_wait_healthcheck helper_scripts/db/test_lease_ipc_soak_healthcheck.py
git diff --check
```

Linux：

```bash
PYTHONPATH=. python3 -m pytest helper_scripts/db/test_lease_ipc_soak_healthcheck.py -q
# 47 passed, 1 skipped
python3 -m compileall -q helper_scripts/db/passive_wait_healthcheck helper_scripts/db/test_lease_ipc_soak_healthcheck.py
```

Linux true DB smoke：

```bash
PYTHONPATH=/home/ncyu/BybitOpenClaw/srv \
program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python3 \
  -m helper_scripts.db.passive_wait_healthcheck.runner --check 81 --check 82
```

結果：

- `[81] PASS`：lease_transitions fresh，newest_age=5s
- `[82] FAIL`：`S3 not yet met: window=38.7h < 48h ... probes=1160`
- exit code 1 是合理結果，來自 `[82]` accumulating；已不是 unsupported selector。

## 邊界

無 CI、無 deploy、無 rebuild/restart、無 migration、無 DB write、無 auth/risk/trading mutation。

