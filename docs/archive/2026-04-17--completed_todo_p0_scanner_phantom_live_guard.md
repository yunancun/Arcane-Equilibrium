# 已完成 TODO 歸檔 — 2026-04-17（SCANNER-GATE + PHANTOM-2-FUP + LIVE-GUARD-1 + STABILITY-1 RCA）

> 自 `TODO.md` 於 2026-04-17 夜整理時切出。條目依主題分組，commit 為權威出處。
> 驗證依據：引擎 PID 1771173 於 2026-04-17 20:55 local 啟動（binary mtime 同刻），所有 4 commit 皆在此前 landed，代碼路徑 + 測試檔案均已 grep 確認。

---

## 🛡️ P0-10 · SCANNER-GATE — orphan_handler death loop fix ✅

**commit** `7131250` fix(engine): SCANNER-GATE — kill orphan_handler death loop + P0-6 triage

**原問題**：策略開倉 → scanner 輪替移除 symbol → orphan_handler A4 強平 → 策略再開 → 死循環。BASEDUSDT 等 20+ 個 symbol 受影響（228 筆 `ipc_close_symbol` fills）。

**根因**：A4 `HardSafetyNotInUniverse` 把「掃描器輪替掉的持倉」當作 orphan 強平，但引擎會在下一 tick 重新開倉 → 無限循環。同時 REST→WS 時間差（FUP race condition）使引擎自家剛下的單也被誤判為 orphan。

**修復（三部分）**：
1. **SCANNER-GATE**：`tick_pipeline/mod.rs:791` 新增 `symbol_registry: Option<Arc<SymbolRegistry>>` 字段 + `set_symbol_registry()` setter（mod.rs:929），在 `on_tick.rs:763` strategy Open dispatch 前檢查 `reg.is_active(symbol)`，非活躍 symbol 阻止開新倉
2. **FUP-RACE**：`paper_state.rs:254` 新增 `proactive_mirror_insert()`，exchange OrderDispatchRequest 發送後（`on_tick.rs:875`）立即寫 mirror，彌合 REST→WS 空窗
3. **A4 移除**：`orphan_handler.rs:244-252` Stage A4 代碼移除並加註解 "Stage A4: REMOVED (SCANNER-GATE fix)"，enum 變體 `HardSafetyNotInUniverse` 保留（DB backward compat，as_str() 仍可序列化），決策路徑不再發射

**改動檔案**：`tick_pipeline/mod.rs`（+field +setter +init）· `on_tick.rs`（+scanner gate + proactive mirror）· `paper_state.rs`（+proactive_mirror_insert）· `orphan_handler.rs`（-A4 +updated tests +doc）· `event_consumer/mod.rs:216`（+registry wiring）

**測試**：engine lib 1351 passed / 0 failed（含 17 orphan_handler 測試全綠）· core 380 passed

**部署驗證**：binary mtime 2026-04-17 20:55:48 local，engine 啟動後 engine.log 無新 `HardSafetyNotInUniverse` 事件、無 `Temporary failure in name resolution` 以外 panic/assertion。

---

## 🔒 P0-5 · PHANTOM-2-FUP — ReduceToHalf one-shot guard 跨 tick 失效 ✅

**commit** `fe3f4ab` fix(engine): P0-5 PHANTOM-2-FUP — ReduceToHalf cooldown + Normal-only clear

**原問題**：Phantom-2 one-shot guard 在跨 tick 場景失效，1.3s 內同 symbol 連發 9 次 `fast_track_reduce_half`（24h 335 次，主要集中在 drawdown-driven Cautious 模式）。

**方案（A+C 組合）**：先 propose C-alone，QC 對抗性審查翻轉為 A+C — 因 `risk_gov.rs:617` 無自動降級路徑 + `position_risk_evaluator` 不認 sigma 離群，純 C 會讓 Cautious 下已半倉 symbol 永久鎖定直到 operator 手動 de-escalate。

- **A**：`ft_reduced_symbols: HashSet<String>` → `HashMap<String, i64>`（symbol → last reduce ts_ms）+ 60s cooldown 封毫秒連發
- **C**：clear 條件 `< Defensive` → `== Normal`，僅完全回到 Normal 清空（快速 re-arm 新 episode）
- 新常數 `FT_REDUCE_COOLDOWN_MS = 60_000` 於 `on_tick_helpers.rs:23`（const 不熱載 — 60s 配合 governance Defensive 窗，足夠保守）
- 新 pure helper `ft_reduce_cooldown_expired()` 於 `on_tick_helpers.rs:45`，filter 可單測

**改動檔案**：
- `rust/openclaw_engine/src/tick_pipeline/mod.rs`（struct 欄位型別 + init）
- `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:151-246`（clear 條件 + filter + insert）
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`（+const + fn）
- `rust/openclaw_engine/src/tick_pipeline/tests.rs:1456-1653`（+5 新單測）

**新單測**（5 個）：
- `test_ft_reduce_cooldown_expired_no_prior_entry`：首次永遠放行
- `test_ft_reduce_cooldown_blocks_within_window`：+0ms / +59999ms 一律擋（複現 1.3s/9 次 cascade）
- `test_ft_reduce_cooldown_re_arms_after_window`：+60000ms 解鎖 + 跨 symbol 獨立
- `test_ft_reduce_clear_only_on_normal`：Cautious/Reduced/Defensive 絕不清空
- `test_ft_reduce_cooldown_map_stamps_once_per_window`：真實 TickPipeline + paper_state 整合

**驗收（部署後觀察）**：
- `grep "FAST_TRACK ReduceToHalf" /tmp/openclaw/engine.log` 同 symbol 連續事件時間戳間隔 ≥60s（不再毫秒連發）
- `risk_close:fast_track_reduce_half` 24h 計數 < 50（vs 修復前 335/2.6h，預期降 >80%）

**RCA**：`docs/references/2026-04-16--phantom2_fup_reduce_to_half_cascade_rca.md`

**部署驗證**：與 P0-10 同一 binary（2026-04-17 20:55:48）landed。

---

## 🔐 P0-8 · LIVE-GUARD-1 — Rust 端 Mainnet 三重硬鎖回補 ✅

**commit** `5de9b23` fix(security): LIVE-GUARD-1 — restore Rust-side Mainnet triple fail-safe

**根因**：SEC-17（2026-04-10 commit 25b5d73）移除 `OPENCLAW_ALLOW_MAINNET=1` Rust guard 後未補替代 fail-safe；憑證來源同時從「slot 文件唯一」擴展為「env var > slot」雙路徑，導致任何能設環境變數的進程都能繞過 secret slot。門控完全外移 Python → Rust 長跑 × Python 重啟脆弱的對稱性崩潰。

**方案（三重加固 Gate #1/#2/#3）**（env 路徑，非 operator-signed file — CLAUDE.md §三建議選項；後者 HMAC+mtime freshness 屬 over-engineer）：
- **Gate #1**（`bybit_rest_client.rs:414-425`）：`env=Mainnet` 需 `OPENCLAW_ALLOW_MAINNET=1`（exact `"1"`，拒絕 `"0"`/`"true"`/`"yes"`/`"1 "`），缺即 `BybitApiError::Business`
- **Gate #2**（`bybit_rest_client.rs:432-461`）：`env=Mainnet` 時禁用 `BYBIT_API_KEY`/`BYBIT_API_SECRET` env var fallback，只允許 param → slot file（封閉 env 繞 slot 的攻擊面）
- **Gate #3**（`bybit_rest_client.rs:463-476`）：`env=Mainnet` 時憑證空 → 構造時 `Err` fail-closed（之前只 `warn!` + client 建立 + 簽名階段 401，污染重試循環）
- Demo/Testnet/LiveDemo 不受影響（向後兼容，當前 live pipeline 走 LiveDemo endpoint 零回歸）

**改動檔案**：
- `rust/openclaw_engine/src/bybit_rest_client.rs:386-497`（new() 重寫 + 三重 gate + bilingual docstring）
- 同檔 tests mod 1305-1528 +7 新單測（`LIVE_GUARD_ENV_LOCK` Mutex + EnvSnapshot RAII）

**新單測**（7 個）：
- `test_mainnet_blocked_without_allow_env` — 未設 env → Err
- `test_mainnet_blocked_with_wrong_allow_value` — `"0"/"true"/"yes"/"1 "/" 1"` 全拒絕
- `test_mainnet_blocked_without_credentials` — allow=1 無 creds → Err
- `test_mainnet_ignores_env_var_credentials` — BYBIT_API_KEY env 有值、slot 無 → 仍 Err（驗 Gate #2）
- `test_mainnet_accepts_explicit_param_creds` — allow=1 + param 傳入 → OK
- `test_demo_env_var_creds_still_work` — 回歸守衛：Demo + env var 不壞
- `test_testnet_no_guard_check` — 回歸守衛：Testnet 不需 allow env

**E2 審查結論**（5/5 APPROVED）：無 struct literal 繞過、`startup.rs:432` + `pyo3/client.rs:93` Err 硬傳播、無獨立 HTTP client 可打 mainnet、WS 靠 REST 憑證無獨立 guard 需求、repo grep 無既存 OPENCLAW_ALLOW_MAINNET 誤用值。

**測試基準**：engine lib 1342 passed / 0 failed。

**部署狀態**：已隨 `restart_all.sh --rebuild` 附帶生效（binary mtime 2026-04-17 20:55:48）。當前 LiveDemo→Demo endpoint 零影響；真實 Mainnet 僅在 operator 顯式配置 `trading_mode=Live` + secret slot + env var 三項俱全時可用（門控從 1 項 Rust-verifiable 升為 3 項，見 CLAUDE.md §四）。

---

## 📡 P0-9 · STABILITY-1 — 2026-04-16 停電事件 RCA ✅（非代碼 bug）

**commit** `aff12c0` docs(p0-9): STABILITY-1 RCA — 2026-04-16 停電基礎設施事件，非 code bug

**原敘述**：當日 9h 引擎 5 次崩潰被誤判為「代碼穩定性 P0-CRITICAL 阻塞 + 21d 時鐘必須重置」。

**RCA 結論**（2026-04-16 深夜，operator 確認）：**全部 30 次 crash（深入撈後實為 30 非 5）均為單次斷電造成的網路基礎設施事件，非引擎代碼 bug。** 21d demo 時鐘**不重置**。

**證據鏈**：
- 時區：operator 筆電 CEST (UTC+2) — UTC→local 加 2h
- operator 報告：**2026-04-16 10:00-16:00 local 停電 ~6h**，造成斷網
- **第一次 crash 10:45 local**（08:45 UTC）= 停電後 45min（電池 + 路由器失電）
- **watchdog 完全靜默 13:16-18:03 local**（4h 47min blackout）= 筆電電池耗盡或硬關機期間
- **post-gap 首條** `snapshot age=17313.5s`（4.81h 陳舊）= 硬斷電復電鐵證
- **engine log（engine-1776330656.log 09:10 UTC 啟動）**所有錯誤簽名一致：
  - `HTTP transport error: error sending request for url (https://api-demo.bybit.com/...)`
  - `IO error: failed to lookup address information: Temporary failure in name resolution`（DNS 失敗）
  - REST / WS private / WS public 全部連不上 Bybit
- 非代碼 bug 的證據：**零 panic、零 assertion、零 rust backtrace**；全部為 DNS/transport error 合理 fail-closed 行為
- 斷網恢復後（18:03 local 之後）網路還不穩又滾了幾輪，再之後當前 PID 1364222 於 22:16 local 穩定啟動（其後於 2026-04-17 20:55 因 `--rebuild` 自然 recycle 為 PID 1771173）

**對觀察期時鐘的判定**：
- **P0-2 LG-1 21d demo 時鐘不重置**：基礎設施事件 ≠ 引擎不穩定。若每次停電都重置時鐘，21d 永遠達不到
- **P0-3 Phase 5 edge 2w 重評**：crash 時段（10:45-18:03 local）fills 樣本應排除（自然也沒有 fills，因為引擎連不上 Bybit）

**Nice-to-have（不阻塞，已列 P4 WATCHDOG-DNS-CLASSIFY-1）**：
- `engine_watchdog` 可加 network-loss detection（DNS failure 連續 N 次分類為 `network_outage`，不計入 stability strike）
- 不急，等有空再做

**阻塞**：無（已解除，非 Live 前置）
**歸檔**：本 RCA 結論取代 CLAUDE.md §三「9h 5 crash / 21d 時鐘未啟動」敘述，§三 + §十 + §十一 已同步更新

---

## 📦 部署時序（權威時間線）

| 時間（local） | 事件 | 證據 |
|---|---|---|
| 2026-04-16 22:16 | 停電 RCA 後 PID 1364222 啟動（LIVE-GUARD-1 已 landed in commit 5de9b23） | engine_results.jsonl |
| 2026-04-17 18:55 | P1-8 DUST-EVICTION-GAP-1 E1/E4 完成（triage 預檢 + orphan_frozen 分支） | engine.log 18:55:57Z `DUST-EVICTION-GAP-1:` warn |
| 2026-04-17 20:55:48 | `restart_all.sh --rebuild` 產新 binary；PID 1771173 起跑（P0-5 + P0-10 完整到位） | binary mtime + ps etime |
| 2026-04-17 22:00+ | 本歸檔落筆 | 本文件 |

## 🔬 驗證方法（future session 可重跑）

```bash
# 1. 代碼結構存在性
grep -rn --include="*.rs" "FT_REDUCE_COOLDOWN_MS\|ft_reduce_cooldown_expired" rust/openclaw_engine/src
grep -rn --include="*.rs" "OPENCLAW_ALLOW_MAINNET\|LIVE_GUARD" rust/openclaw_engine/src
grep -rn --include="*.rs" "symbol_registry\|proactive_mirror_insert" rust/openclaw_engine/src
grep -n "Stage A4: REMOVED" rust/openclaw_engine/src/position_reconciler/orphan_handler.rs

# 2. 部署時序對齊
stat -c '%y' rust/target/release/openclaw-engine
ps -o pid,etime,cmd -p $(pgrep -f openclaw-engine) | head -5

# 3. 穩定性
grep -c "ENGINE_CRASH" /tmp/openclaw/watchdog.log
grep -iE "panic|assertion failed|rust backtrace" /tmp/openclaw/engine.log | tail -5
```
