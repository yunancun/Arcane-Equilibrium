# P5-SM [81]/[82] Selector Fix

日期：2026-06-12
Commit：`bf673cdc`

## 結論

`--check 81 --check 82` 現在可以直接跑，不再報 unsupported selector。

Linux 真 DB smoke：

```bash
PYTHONPATH=/home/ncyu/BybitOpenClaw/srv \
program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python3 \
  -m helper_scripts.db.passive_wait_healthcheck.runner --check 81 --check 82
```

目前輸出：

- `[81] PASS`
- `[82] FAIL`，原因是 `38.7h < 48h`，probes=1160

這代表入口已修好，但 soak gate 還不能提前收掉。等 48h 到期後再跑同一命令；若 `[82]` PASS，再進 P2 activation / V138→V139 / L2 activation 窗口。

邊界：本次只修 CLI routing；沒有 CI、沒有 deploy/rebuild/restart、沒有 DB/auth/risk/trading mutation。

