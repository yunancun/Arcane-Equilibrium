# TODO v180 cold-audit completed-row archive

已把兩個 cold-audit 已完成項從 TODO §5 active queue 移出：

- `AUDIT-2026-06-14-AUTH-1`
- `AUDIT-2026-06-14-PROFIT-1`

保留的尾巴沒有消失，只改放 §7：

- `P2-LIVE-AUTHZ-RUST-DIRECT-SOCKET-FUTURE`：只有在 operator 決定要完全關 direct-socket bypass 時才重開。
- `P1-COST-GATE-DOUBLE-DEDUCT-TRIGGER`：只有在 explore-gate/Stage0R 寫出 validated-positive cell，或 forward PnL 證明 released cell 為正時才重開。

邊界：文檔隊列整理；沒有 CI、沒有代碼改動、沒有 deploy/rebuild/restart、沒有 runtime/DB/auth/risk/order/trading mutation。
