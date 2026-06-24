# API Service Enablement Review

結論：API service 已經由 systemd user service 接管並保持 `active/running`，但 boot autostart 仍未啟用。這是有意保守狀態，不是故障。

本輪只做 source-only / read-only review：

- fresh parity packet: `API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY`
- unit state: `disabled`
- health surface: HTTP `401`
- listener: only `100.91.109.86:8000`
- `loginctl`: `Linger=yes`
- `[Install] WantedBy=default.target`: present
- no `default.target.wants` symlink yet

E3 verdict: future `systemctl --user enable openclaw-trading-api.service` is acceptable only as a separate PM/E3 checkpoint, using enable without `--now`, after fresh parity and security gates pass.

Nothing was enabled, restarted, written to PG, sent to Bybit, or granted as probe/order/live authority.
