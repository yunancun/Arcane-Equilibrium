# 2026-06-22 — Bounded Probe Matched-Control Evidence Quality

本輪不是放寬 Cost Gate，而是提高「未來放寬是否合理」的證據質量。

核心變更：未來 bounded demo probe 即使實際 demo 成交為正，也必須有同 side-cell / 同 horizon 的 `blocked_signal_outcome` 對照樣本，才會被主閉環視為可進入 Cost Gate/operator review 的證據。沒有 matched control 的正收益 probe 會被標成 `anecdote_risk`，並退回 data coverage。

已驗證：Mac py_compile passed；Mac focused pytest `74 passed`；`git diff --check` passed；Linux 已同步 source 到 `1553d63c`，Linux py_compile passed，Linux focused pytest `74 passed`。

邊界未變：沒有 Cost Gate lowering，沒有 probe/order authority，沒有 runtime mutation，沒有 PG/Bybit write，沒有 deploy/restart，沒有 promotion proof。
