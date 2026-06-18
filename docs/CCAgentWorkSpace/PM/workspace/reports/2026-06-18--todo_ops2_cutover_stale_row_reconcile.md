# TODO v172 OPS-2 Cutover Stale Row Reconcile

日期：2026-06-18
角色：PM
範圍：TODO §5 active queue hygiene

## 結論

`P1-OPS-2-PHASE-2-CUTOVER` 從 `TODO.md` §5 移出。該 row 的「deploy operator-gated」狀態已 stale：cutover 已 merge 並經後續 runtime rebuild 生效。

## 證據

- `3018c7a3` 是 OPS-2 Phase-2 cutover merge commit，且是 runtime source HEAD `83b7632d` 與當前 docs HEAD 的 ancestor。
- Linux `trade-core` checkout 目前在 main HEAD，且 `3018c7a3` 是其 ancestor。
- `memory/project_2026_06_10_a_group_triage.md` 記錄 2026-06-11 04:00 operator 指令下 PM 代跑 `restart_all --rebuild`，OPS-2 cutover 新 binary 生效，`ops2_secret_split_phase1_fallback` 0，V137 applied，48h soak 啟動。
- `TODO.md` §6 已保留 OPS-2 leftover operator row。

## 保留 Gate

本輪沒有關閉 C-B 手動 `/auth/renew` 留證，也沒有關閉 2026-09-08 首次 rotation timing。這兩項仍由 `TODO.md` §6 OPS-2 leftover row 承接。

## 邊界

Docs hygiene only。未執行 CI、deploy、rebuild、restart，未改 production source、runtime、DB、auth、risk、order 或 trading state。
