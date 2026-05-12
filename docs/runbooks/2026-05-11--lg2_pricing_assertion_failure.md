# LG-2 T2 Pricing Binding Assertion Failure — Spawn Reject SOP

**Date**: 2026-05-11
**Author**: PM (consolidated from A3 R7 + E1 LG-2 T2 push back)
**Related**: `docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md` (對稱結構)
**Related**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §2

---

## 1. 用途 / Why this runbook exists

LG-2 T2 `assert_pricing_binding_for_live_spawn` 在 engine `build_exchange_pipeline` 啟動瞬間做 3 項 pre-check + 30s wait 守門。任一 fail → **拒 spawn live pipeline** + tracing audit log `target=openclaw_engine::live_spawn_audit`。

operator 觀察症狀：**restart 後 LiveDemo / Mainnet 不啟動，watchdog `live` engine alive=false 但 demo/paper 正常**。本 runbook 提供 4 種 `LivePricingBindingError` reason_code 對應的診斷 + 修復路徑。

**重要**：本 runbook 對應的是 LiveDemo + Mainnet spawn path（per PA §2.5 risk #1，demo + paper 路徑不 enforce）。

---

## 2. Spawn reject 4 種 reason_code

| reason_code | 觸發條件 | 預期環境 |
|---|---|---|
| `NoRefresh` | `last_fee_refresh_ms == 0`（fee_rate task 從未首次 refresh）| Mainnet 必拒 / LiveDemo 視 `cold_default_acceptable_modes` |
| `InsufficientSymbolCoverage` | `fee_rate_count() < 25` active symbols | 任 live 模式都拒 |
| `MainnetNonApiSource` | 任一 symbol `FeeSource != BybitApi`（含 DemoConservativeDefault / ColdDefault）| **僅 Mainnet** 拒 |
| `LiveDemoNonApiSourceWhenStrict` | LiveDemo `FeeSource = ColdDefault` 且 `cold_default_acceptable_modes` 不含 `"live_demo"` | 視 risk_config_live.toml `[pricing]` 設定 |

---

## 3. 第一步診斷：找出 reason_code

```bash
# 從 systemd journal 找 live_spawn_audit event
ssh trade-core "journalctl -u openclaw-engine --since '5 minutes ago' --grep 'live_spawn_audit' | tail -30"

# 或直接 grep engine.log（tracing 同時寫 file appender）
ssh trade-core "tail -200 /tmp/openclaw/logs/engine.log | grep 'live_spawn_audit'"

# 預期看到類似:
# level=ERROR target=openclaw_engine::live_spawn_audit
# reason_code=MainnetNonApiSource symbol=BTCUSDT fee_source=DemoConservativeDefault
```

**Note**: tracing audit 是 ephemeral（systemd journal 24h-7d retention 視 config）。建議 operator 觀察到症狀第一時間立即 grep + 截圖；不可事後追補。後續 P2 retrofit 改寫 PG row（E2 MEDIUM-4 P2 ticket，db_pool 連線前限制使當前只能走 tracing）。

---

## 4. NoRefresh 處置

### 4.1 觸發條件
`last_fee_refresh_ms == 0` — fee_rate 任務 spawn 後 30s 內未首次 refresh 成功。

### 4.2 常見原因
- Bybit V5 `GET /v5/account/fee-rate?category=linear` endpoint return non-2xx
- 網路問題 + Bybit API rate limit
- API key 失效 / 無 fee endpoint permission
- DNS 失敗 / Bybit endpoint stale

### 4.3 診斷步驟
```bash
# 1. 直接呼叫 Bybit fee endpoint 看
ssh trade-core "cat /home/ncyu/BybitOpenClaw/srv/settings/secret_files/bybit/live/api_credentials.json | jq -r '.api_key'"
# 拿 api_key 後手動 curl Bybit V5 fee-rate endpoint (帶 signed header) → 看 retCode
# 或直接看 engine.log 找 fee_rate API call response

# 2. 看 fee refresh task 是否 spawn
ssh trade-core "grep 'spawn_fee_rate_tasks\|fee_rate refresh' /tmp/openclaw/logs/engine.log | tail -20"

# 3. 確認 secret slot 存在
ssh trade-core "ls /home/ncyu/BybitOpenClaw/srv/settings/secret_files/bybit/live/"
```

### 4.4 修復
- **API key 失效** → 走 `live_trust_routes::renew()` 或 operator 手動 rotate（per `docs/runbooks/` 既有 credential rotation runbook）
- **Bybit endpoint 5xx** → 等待 + 重試（Bybit 端問題）
- **網路** → 確認 Tailscale + Bybit endpoint 連通
- 修好後 `bash helper_scripts/restart_all.sh --rebuild --keep-auth` 重啟

---

## 5. InsufficientSymbolCoverage 處置

### 5.1 觸發條件
`fee_rate_count() < 25` — fee cache 中 active symbol 數不足 25。

### 5.2 常見原因
- Active universe TOML 配置少於 25 symbol
- fee endpoint 只 return 部分 symbol（Bybit V5 paginate）
- 初次 refresh 部分成功（race + retry 不充分）

### 5.3 診斷步驟
```bash
# 1. 看 fee cache 多少 symbol
ssh trade-core "grep 'fee_rate cache updated\|fee_rate_count' /tmp/openclaw/logs/engine.log | tail -5"

# 2. 看 active universe 設定
ssh trade-core "grep 'scanner_active_universe\|active_symbols' /home/ncyu/BybitOpenClaw/srv/settings/risk_control_rules/scanner_config.toml | head -5"

# 3. 直接呼叫 IPC query_fee_source 看 cache
# (deploy 後若 IPC slot 已 wire) ssh trade-core "echo '...' | nc -U /tmp/openclaw/ipc.sock"
```

### 5.4 修復
- **TOML 配置不足 25** → 增 active symbol 配置（per PA §2.2 hardcoded threshold 25 是設計 cap，符 OpenClaw 25-symbol concurrency cap）
- **paginate 部分成功** → 等 1 次完整 refresh cycle (3600s) OR 手動 trigger fee refresh
- **Bybit response 少** → check Bybit V5 endpoint 是否最新

---

## 6. MainnetNonApiSource 處置（最嚴格）

### 6.1 觸發條件
**Mainnet 環境**：任一 active symbol `FeeSource != BybitApi`（含 `DemoConservativeDefault` / `ColdDefault`）。

### 6.2 原因
- Bybit Mainnet fee endpoint return 4xx/5xx 個別 symbol → fallback to default
- 部分 symbol 在 Bybit 端標 `inactive` → 不可交易

### 6.3 診斷步驟
```bash
# 1. journalctl 找具體哪幾個 symbol
ssh trade-core "journalctl -u openclaw-engine --grep 'MainnetNonApiSource\|fee_source=' | tail -20"

# 2. 對每個 fail symbol 看 Bybit response
# (參考 §4.3 step 1 手動 curl)
```

### 6.4 修復
- **個別 symbol Bybit 端 inactive** → 從 active universe 移除該 symbol 直到 Bybit 重新 enable
- **大批 fail** → 等 Bybit 端恢復 + 重 restart
- **絕不可** 為了 spawn live 放寬 cold_default_acceptable_modes 加入 `"live"` — 這是 hard 邊界

---

## 7. LiveDemoNonApiSourceWhenStrict 處置

### 7.1 觸發條件
**LiveDemo 環境**：`FeeSource = ColdDefault` 且 `cold_default_acceptable_modes` 不含 `"live_demo"`。

### 7.2 原因
- `risk_config_live.toml [pricing].cold_default_acceptable_modes` 限制白名單
- LiveDemo 應接受 `DemoConservativeDefault` 但實際 `ColdDefault`（連 demo fallback 都未走）

### 7.3 診斷步驟
```bash
# 1. 看 LiveDemo TOML pricing 設定
ssh trade-core "cat /home/ncyu/BybitOpenClaw/srv/settings/risk_control_rules/risk_config_live.toml | grep -A 5 '\[pricing\]'"

# expect:
# cold_default_acceptable_modes = ["demo", "live_demo"]
```

### 7.4 修復
- **TOML 不含 live_demo** → 加入 acceptable_modes（per PA §2.5 risk #1，LiveDemo 可接 demo fallback）
- **fee_rate task 全失敗** → 走 §4 NoRefresh path 修

---

## 8. 失敗模式 / Failure modes 表

| Fail-mode | 觸發條件 | 操作員處置 |
|---|---|---|
| 全部 LiveDemo spawn 失敗 | NoRefresh + Mainnet 也炸 | Bybit API key / endpoint 問題（§4） |
| 只 Mainnet 拒 | MainnetNonApiSource | 部分 symbol Bybit 端 inactive（§6） |
| LiveDemo 拒但 Demo OK | LiveDemoNonApiSourceWhenStrict + cold_default_acceptable_modes 設嚴 | TOML 設定問題（§7） |
| 30s wait timeout | NoRefresh 且 30s 內 fee task 真的沒 schedule | engine 啟動順序問題 / spawn_fee_rate_tasks 未呼 |

---

## 9. 監測 / Verification 渠道

- **systemd journal**: `journalctl -u openclaw-engine --grep live_spawn_audit`
- **engine.log**: `/tmp/openclaw/logs/engine.log` grep
- **watchdog**: `live` engine alive=false 但 demo/paper alive=true 是 LG-2 T2 signature
- **healthcheck [45] pricing_binding**: dual-source compare（LG-2 T3 IPC + PG proxy）
- **runbook 對稱**: 參考 LG-1 T3 `2026-05-11--lg1_h0_flip_rollback.md` 監測章節

---

## 10. Cross-References

- LG-2 T2 PA spec: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §2
- LG-2 T2 IMPL: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t2_startup_assertion.md`
- LG-2 T3 FeeSource enum: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t3_fee_source_enum.md`
- LG-2 T4 PricingConfig: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg2_t4_riskconfig_pricing.md`
- E2 review: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--wave2_2_lg1_lg2_e2_review.md`
- A3 R7 audit: `docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-11--wave2_2_a3_ux.md` §4

---

## 11. 修訂 / Revision

- 2026-05-11 v1: A3 R7 audit → PM apply（initial draft，對齊 LG-1 T3 結構 + 4 reason_code 各一段 + LiveDemo 寬鬆/Mainnet 嚴格邏輯）
