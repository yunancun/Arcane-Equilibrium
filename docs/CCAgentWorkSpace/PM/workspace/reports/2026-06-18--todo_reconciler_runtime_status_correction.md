# TODO v178 Reconciler Runtime-Status Correction

日期：2026-06-18
角色：PM
範圍：`P2-RECONCILER-GET-POSITIONS-PAGINATION`、`P3-110017-D2-AUDIT-REMOVED-SEMANTICS`

## 結論

修正 TODO 狀態漂移，但不歸檔這兩個 row。

`bb7e9efc` 與 `baf46a69` 已在 Mac/Linux HEAD 祖先鏈內，running engine binary 也已載入 D2 audit semantics 字串。因此 `P2-RECONCILER-GET-POSITIONS-PAGINATION` 不應再標「未部署」。

但 PM 1-4 integration report 仍明示下一步是 E2/E4/QA review，且 production DB 尚無 `reconcile_ghost_converge` event row。故兩個 TODO 仍 active。

## 證據

- Mac `HEAD`: `cfe5a9805f61d29663a66550570024c0e3920b76`
- Linux `/home/ncyu/BybitOpenClaw/srv HEAD`: `cfe5a9805f61d29663a66550570024c0e3920b76`
- `git merge-base --is-ancestor bb7e9efc HEAD`: pass（Mac + Linux）
- `git merge-base --is-ancestor baf46a69 HEAD`: pass（Mac + Linux）
- Linux watchdog read-only status: `engine_alive=true`，demo snapshot age about 6s at check time
- Running engine PID 3134818, started `Thu Jun 18 14:11:50 2026`
- `/proc/3134818/exe` points to release engine image held by the process
- `/proc/3134818/exe` strings include:
  - `removed_position_semantics`
  - `dispatched-not-confirmed`
  - `handler-confirmed`
  - `reconcile_ghost_converge`

Read-only DB checks:

- `SELECT count(*) FROM observability.engine_events WHERE event_type='reconcile_ghost_converge'` = 0
- `SELECT count(*) FROM observability.engine_events WHERE event_type='reconcile_ghost_converge' AND payload::text LIKE '%removed_position_semantics%'` = 0

## Decision

- `P2-RECONCILER-GET-POSITIONS-PAGINATION`: status becomes source+runtime present, but BB/E2/E4 review remains required.
- `P3-110017-D2-AUDIT-REMOVED-SEMANTICS`: status becomes runtime binary has the semantic payload support, but E2/E4 review and event proof remain open.

No CI, deploy, rebuild, restart, DB write, auth, risk, order, or trading mutation was performed.
