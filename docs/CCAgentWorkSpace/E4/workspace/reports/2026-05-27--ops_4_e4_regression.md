# E4 Regression — OPS-4 systemd (GAP-A + GAP-F + minor fix)

- **Date**: 2026-05-27 19:36 UTC
- **Commits**: `65e78437` (OPS-4 IMPL) + `07027493` (OPS-4 minor fix)
- **Scope**: 2 install scripts (bash -n) + 6 systemd units (systemd-analyze verify on trade-core) + README/SCRIPT_INDEX render + cross-platform path grep + idempotency smoke
- **Mode**: 靜態 / 語法 / runtime verify；無安裝、無啟動、無 commit

## §1 bash -n + systemd-analyze verify 結果

### bash -n（Mac local）
| 檔 | 結果 |
|---|---|
| `helper_scripts/systemd/install_engine_service.sh` | PASS |
| `helper_scripts/systemd/install_watchdog_service.sh` | PASS |

### systemd-analyze verify（ssh trade-core，sed 替換 9 占位符後）
| Unit | verdict | 備註 |
|---|---|---|
| `openclaw-engine.service` | WARN | `StartLimitIntervalSec` 寫在 `[Service]` 被 ignore（systemd 245+ 期望 `[Unit]`）— 預存非本次 minor fix scope |
| `openclaw-watchdog.service` | WARN | 同上 `StartLimitIntervalSec` ignore — 預存 |
| `openclaw-caddy.service` | WARN | `/usr/bin/caddy not executable` — OPS-1 Track A，Caddy 尚未安裝；operator hand-action |
| `openclaw-tls-renew.service` | PASS | clean |
| `openclaw-tls-renew.timer` | PASS | clean |
| `openclaw-tls-renew-notify.service` | FAIL | `Failed to resolve unit specifiers` on `$(date -u +%FT%TZ)` — `%F/%T/%Z` 撞 systemd specifiers，須 `%%FT%%TZ`；預存 OPS-1 Track A |

**重要**：3 個 finding 全屬 `65e78437`（OPS-4 初版）或更早 OPS-1 Track A，**不是 07027493 minor fix 引入的 regression**。E2 APPROVE-WITH-MINOR 已過閘；E4 在本 round 顯式記錄為 carry-over，不阻擋本次 commit。

### Carry-over（建議 OPS-4 round 3 / OPS-1 round 3 處理）
1. **C-1 HIGH（runtime correctness）**：engine + watchdog 的 `StartLimitIntervalSec` 寫在 `[Service]` 被 systemd ignore → rate-limiting **實際不生效**；應改為 `StartLimitInterval` 或移到 `[Unit]`（systemd 230+）。RTO 雙重防線（spec §5.1）依賴 watchdog circuit-break + systemd 5 連 fail，systemd 端目前失效。
2. **C-2 MED**：`openclaw-tls-renew-notify.service` `ExecStart` 內 `%FT%TZ` 須 escape 為 `%%FT%%TZ`；目前 fatal error，OnFailure hook 完全無法被拉起。
3. **C-3 LOW**：caddy binary `/usr/bin/caddy` 缺檔 — operator hand-action 提示，非 IMPL 缺陷。

## §2 README + SCRIPT_INDEX render check

| 檢查 | 結果 |
|---|---|
| `helper_scripts/systemd/README.md` markdown 結構 | 1 H1 / 7 H2 / 9 H3 / 12 code fence（even balanced）/ 154 行 — PASS |
| README §B「systemctl reset-failed」recovery 提示 | 3 mention（LOW-4 fix land 已驗）— PASS |
| `helper_scripts/SCRIPT_INDEX.md` 系列 entry | 9 systemd entries（5 OPS-1 Track A + 4 OPS-4 GAP-A/F）對齊實際檔案 — PASS |
| SCRIPT_INDEX 表格欄位（163 `|` 行）| 結構未破 — PASS |

## §3 跨平台 grep 反驗證

| 模式 | 結果 |
|---|---|
| `grep -rn "/home/ncyu\|/Users/ncyu" helper_scripts/systemd/` | 11 hit：全屬注釋 / Usage example / 錯誤訊息字串 / `__OPENCLAW_BASE_DIR__` 模板 placeholder 周邊註釋 |
| **logic line 違反**（排除註釋）| **0 hit** — PASS |
| `/home/ncyu/BybitOpenClaw/srv` 在 `install_*.sh:38/40` | 位於 `${VAR:?例: /home/ncyu/...}` 錯誤訊息字串內，路徑仍走 `$OPENCLAW_BASE_DIR` 參數化 — PASS |
| `__OPENCLAW_BASE_DIR__` / `__ENGINE_USER__` 等占位符 | 由 install script `sed` 替換為 env var；模板無硬編碼 — PASS |

跨平台 portability（OpenClaw §六 hard requirement）達標。

## §4 install script idempotency smoke

**Static review**（未實際 sudo 跑安裝）：
| 操作 | 行為 |
|---|---|
| `install -m 644 "$TMP_UNIT" "$TARGET"` | atomic OVERWRITE pattern — 第二次跑直接覆寫，不抓「已存在」抛錯 |
| `trap 'rm -f "$TMP_UNIT"' EXIT` | tmp 清理；不污染 |
| `systemctl daemon-reload` | 冪等（無條件 reload） |
| user/group preflight `id -u` | 第二次跑同條件，pass |
| systemd-analyze verify | 第二次跑同 unit 同結果（warn-only 繼續，error exit 11） |
| root user guard exit 12 | 第二次跑同 guard |

**結論**：兩次跑 = OVERWRITE+reload pattern（非 skip-warn），對 systemd unit 安裝是**正確的冪等語意**（unit 是 leaf state，不像 user/db 須去重）。不會 fail，不會殘留半成型 unit（atomic mv + trap 清 tmp）。

## §5 final verdict

**PASS**

- bash -n 2/2 PASS
- systemd-analyze 4/6 clean / 2 WARN（StartLimitIntervalSec、caddy 缺檔）/ 1 FAIL（tls-renew-notify %FT%TZ escape）— **全為 65e78437 或更早 OPS-1 Track A 預存問題**，E2 APPROVE-WITH-MINOR 已通過，不阻 07027493 minor fix
- 0 hardcoded path 違反
- README + SCRIPT_INDEX 渲染 PASS
- Install script 第二次跑 idempotent (overwrite + daemon-reload)
- 4 minor fix 全 land（MED-1 空 Requires= 刪 / LOW-2 verify warn vs error / LOW-3 root user guard exit 12 / LOW-4 README reset-failed）

**carry-over 至下一 round**（不阻本次 commit）：
- C-1 `StartLimitIntervalSec` 寫在 `[Service]` 被 ignore → rate-limit 不生效（HIGH 但 OPS-4 round 3 處理）
- C-2 `openclaw-tls-renew-notify.service` `%FT%TZ` escape 缺失 → OnFailure hook 無法觸發（MED，OPS-1 round 3）
- C-3 caddy binary 缺檔 — operator hand-action

**operator deploy ready**：Y（OPS-4 主路徑 engine/watchdog 接線 deploy-ready；OPS-1 TLS renewal notify hook 本身 deploy 後不會被觸發，但故障時 notify 鏈斷需 follow-up）

## 6 大測試類型對應

| 類型 | 應用 | 結果 |
|---|---|---|
| Unit test | bash -n（語法層） | PASS 2/2 |
| Integration test | systemd-analyze verify（systemd parser 層） | 4 clean / 2 warn / 1 fail（預存）|
| Property-based | N/A（純 config 檔，無狀態機） | — |
| Concurrency | N/A（install script 序列化） | — |
| SLA | RTO < 5min 數學論證（E2 已驗）| 引用 |
| Cross-language | N/A（純 systemd unit） | — |

## Mock 安全規則

- 無 mock — 全靜態 / runtime verify
- bash -n + systemd-analyze 是 native parser，不掩蓋業務邏輯
