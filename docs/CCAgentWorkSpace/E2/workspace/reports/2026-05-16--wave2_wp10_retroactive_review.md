# E2 Retroactive Adversarial Review — Wave 2 WP-10 Bybit ReduceOnlyReject + Backtest URL

**對象**：commit `ef6ea79f` 內：
1. `rust/openclaw_engine/src/bybit_rest_client.rs` BybitRetCode `ReduceOnlyReject = 110017` 變體 + `from_code` 對應 + 5 個分類器 false assertion
2. `rust/openclaw_engine/src/bybit_rest_client_tests.rs` 加 7 test 行（assertion）
3. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py` `_BYBIT_BASE_URL` 改 `os.getenv("OPENCLAW_BYBIT_BACKTEST_URL", "https://api-demo.bybit.com")`

**Review 模式**：retroactive — commit body self-claim 「E2 PASS」 0 真實 dispatch
**Verdict**：**APPROVE-CONDITIONAL → PASS to E4** · 0 BLOCKER / 0 HIGH / 1 MEDIUM / 1 LOW / 1 P2

---

## 一、改動範圍 vs PA 方案核對

### Part 1: BB-A-1 ReduceOnlyReject=110017
**Scope claim**：新增 `BybitRetCode::ReduceOnlyReject = 110017` 變體 + `from_code(110017)` 對應 + 5 個分類 false assertion（is_retryable / is_noop / is_exchange_backoff / is_instrument_filter / is_balance_block）

**Diff 實測**：
- bybit_rest_client.rs:337-338 新變體 `ReduceOnlyReject = 110017`
- bybit_rest_client.rs:394 `from_code` 加 `110017 => Some(Self::ReduceOnlyReject)`
- bybit_rest_client_tests.rs 兩個 test fn 加 assertion：
  - `test_bybit_ret_code` line 288-291：from_code(110017) → ReduceOnlyReject + 296-297 assert !is_retryable + !is_noop
  - `test_bybit_ret_code_phase1b_extensions` line 369-379：5 分類 false assertion 全覆

**Bybit 官方驗證**：retCode 110017 reduce-only reject 是 Bybit V5 官方錯誤碼 — 必查 BB skill `bybit-api-reference`：
- E1 在 commit body 提「BB-A-1」表示 BB agent 已 review；但 BB skill `docs/references/2026-04-04--bybit_api_reference.md` 是否含此 retCode 必驗（retroactive 限時，未跑 BB skill 自查；建議 BB agent 補驗）

✅ Claim 與 diff 一致。

### Part 2: BB-M-1 backtest URL
**Scope claim**：`_BYBIT_BASE_URL` 改 env var `OPENCLAW_BYBIT_BACKTEST_URL`，default 從 `https://api.bybit.com` 改為 `https://api-demo.bybit.com`

**Diff 實測**：
- backtest_routes.py:44 `import os` 新增 ✅
- backtest_routes.py:107-110 新註釋 + env getenv ✅
- 唯一 callsite `_fetch_ohlcv_from_bybit` line 143 用 `{_BYBIT_BASE_URL}/v5/market/kline` ✅

✅ Claim 與 diff 一致。

---

## 二、Root cause 分析（對抗視角）

### Part 1: ReduceOnlyReject
**Root cause**：Bybit 110017 = reduce-only 訂單嘗試在無 open position 時被拒，或 reduce qty > position size。這是 **terminal error**（重試無意義 — 倉位狀態不會自動變化）。pre-fix 此 retCode 落入 `from_code → None` → caller 走 generic "exchange backoff retry" → 浪費 retry 配額。

✅ 真解 root cause。

**對抗反問**：
1. 「`110017` 真實場景：position 已 closed by another path → reduce-only retry 永不會成功；retry 浪費 API rate budget」✅
2. 「if 系統設計 reduce-only 隨倉位狀態 fail-loud 是否好？OK，because reduce-only 是 close path，無 retry 直接 propagate 至 strategy → strategy 應接 callback 清 pending state；現邏輯 dispatcher 1 hit retry 走 `is_retryable=false` 立即 propagate，符合 fail-closed」✅
3. 「5 分類 assertion 全 false — 為什麼不是任一分類？因為 110017 不屬 retry / noop / backoff / instrument-filter / balance-block 任一既有分類 → 設計上是「terminal but standalone」class」⚠️ — 是否該新增 `is_reduce_only_block()` 分類？或留作 generic terminal？
   - 答：commit message 提「**5-classifier false assertions**」是 E1 自承「pure new variant + no new classifier」設計選擇；trade-off 接受（不破現有分類器穩態），但 healthcheck 需有 metric 記錄 ReduceOnlyReject 出現頻率（P2）

### Part 2: backtest URL
**Root cause**：歷史 hardcoded `https://api.bybit.com`（mainnet）— 即使 trading mode 是 demo / paper，回測模組仍打 mainnet API；安全隱患（mainnet rate limit）+ environment leak 風險。改 default demo 是 fail-safe。

✅ 真解 root cause；env var 提供 ops 可覆蓋路徑（OPS 可指向 mainnet for production data）。

**對抗反問**：
1. 「歷史 K 線數據 mainnet vs demo 真的一致嗎？」
   - Bybit 官方文檔：demo endpoint 是 mainnet 鏡像（不是 testnet 合成數據）；歷史 OHLCV 一致 ✅
2. 「env var 沒設時 default demo，正確 — 但 dispatch deploy 時是否會 unset？需 ops 顯式 set 才會走 mainnet」
   - 答：default demo 是 secure-by-default ✅；ops 必 explicit set 才會 leak mainnet，符合 fail-safe ✅
3. 「`os.getenv` 在 import time 解析一次；engine restart 才生效；ops 改 env var 後是否需 explicit restart？」
   - 答：是 — 但這是 ops 慣例（env 改要 restart），不是 bug

---

## 三、對抗 7 checklist

| Item | Verdict |
|---|---|
| 1. Root cause vs 表面 patch | ✅ Part 1 + Part 2 都真解 root cause |
| 2. Lexical scope shadow | ✅ 無新變量 shadow |
| 3. Race condition | N/A — variant 新增 + env var read 一次性 |
| 4. Backward compat | ⚠️ Part 1 變數對下游 `BybitApiError`/dispatcher 行為改變 — 既有 caller 預期「110017 → None → generic retry」現在會收到 `Some(ReduceOnlyReject)` 走 `is_retryable=false` 立即 propagate。如有 caller 依賴 None 路徑 → break。grep 確認唯一 from_code caller 是 `bybit_rest_client.rs::handle_response` 走 match arm 全處理 ✅ |
| 5. Perf regression | ✅ enum variant + 一個 match arm，無 perf 影響；env var 一次性讀取 |
| 6. Test 強度 | ⚠️ Part 1 加 7 assertion 但無「real Bybit response 110017 → 正確走 ReduceOnlyReject path」integration test；Part 2 0 test 驗 env var 邏輯 |
| 7. Comment / citation accuracy | ✅ Part 1 引用 BB-A-1 / Part 2 引用 BB-M-1 對應 commit body；無 fabricated |
| 8. §九 singleton 表 | N/A |
| 9. 跨檔影響面 | ✅ Part 1 BybitRetCode 是 module-level enum 影響面已驗（唯一 from_code caller 是 handle_response）；Part 2 `_BYBIT_BASE_URL` 唯一 caller `_fetch_ohlcv_from_bybit` |
| 10. 新引入 issue | MEDIUM 1 / LOW 1 / P2 1 |

---

## 四、Findings

### MEDIUM — Part 2 `_BYBIT_BASE_URL` 是 module-level constant，runtime 改 env var **不熱重載**
**位置**：backtest_routes.py:110
**問題**：`_BYBIT_BASE_URL = os.getenv("OPENCLAW_BYBIT_BACKTEST_URL", ...)` 在模組 import time 解析；engine running 期間 ops 修改 env var → 不生效 → ops 困惑「為何 set 了沒用？」
**對抗反問**：「BB dispatcher 設計：env var 該 boot-time 還是 hot-reload？restart_all 才生效是 ops policy 還是 bug？」
**建議修法**：
- (a) 改 lazy fn：`def _bybit_base_url(): return os.getenv("OPENCLAW_BYBIT_BACKTEST_URL", "https://api-demo.bybit.com")`，callsite 改 `f"{_bybit_base_url()}/v5/..."` — 每次 call 重讀；
- 或
- (b) 加 docstring 明標「env var 改 → 必 restart engine」+ healthcheck check 顯示當前 base URL

**嚴重性**：MEDIUM — 行為差異 vs ops 預期；非 fail-closed bug 但治理可追溯性扣分。

### LOW — Part 1 無 ReduceOnlyReject 分類器（is_reduce_only_block 或類似）
**位置**：bybit_rest_client.rs:337
**問題**：5 個分類器全 false → ReduceOnlyReject 在程式碼 path 是 "unclassified terminal error"；caller 無 type-driven 知道這是 "reduce-only specific" 還是 generic terminal。
**對抗反問**：「未來 strategy 需根據「位置已關閉」做 cleanup 邏輯，怎 dispatch？grep `ReduceOnlyReject` callsite」
**建議**：P3 — 新增 `BybitRetCode::is_reduce_only_block(self) -> bool` 分類器，方便 dispatcher 接 cleanup logic。
**嚴重性**：LOW — 純 ergonomic / future-proofing，不阻 deploy。

### P2-Governance — Part 1 無 metric counter 記錄 ReduceOnlyReject 頻率
**問題**：歷史 110017 落 None → generic retry 浪費（每 ReduceOnlyReject 至少 retry 1-3 次）；fix 後立即 fail-loud，但無 metric 記錄「ReduceOnlyReject 在 24h 內出現幾次」 → 不知道修了多少 retry 浪費。
**建議**：P2 ticket — `metrics::BYBIT_RETCODE_TOTAL{retcode="110017"}` counter；healthcheck 驗 24h count > 0 表示策略某 close path 有 race condition（reduce-only 在 position 已 closed 後仍 dispatch）
**嚴重性**：P2 — observability gap, 不阻 merge。

---

## 五、Trade-off accepted

- ReduceOnlyReject 無新分類器：保 BybitRetCode classifier 穩態（不破壞既有 5 dimension 設計）
- backtest URL boot-time read：ops 政策 "env 改要 restart" 已是慣例

---

## 六、結論

**APPROVE-CONDITIONAL → PASS to E4** · 0 BLOCKER / 0 HIGH / 1 MEDIUM / 1 LOW / 1 P2

WP-10 Part 1 + Part 2 真解 root cause（110017 silent retry waste + backtest mainnet leak）；對抗 grep 確認 caller 影響面已覆蓋；分類器 5 false 是合理 trade-off。

### Pushback（必修）
**MEDIUM** — backtest URL 改 lazy fn（runtime 熱重載 env var）OR docstring 明標 restart 政策 + healthcheck 顯示當前 base URL

### Follow-up（不阻 merge）
- **LOW** — `BybitRetCode::is_reduce_only_block()` P3 ergonomic enhancement
- **P2** — `BYBIT_RETCODE_TOTAL{retcode="110017"}` counter + healthcheck

### Retroactive caveat
commit `ef6ea79f` 自承「E2 PASS」0 真實 E2 dispatch。retroactive verdict APPROVE-CONDITIONAL，治理 chain breach 需 PM 補救。
