# E1 報告 — P2p sentinel E4 RED HIGH 修復：cron wrapper A3 API base Tailscale IPv4 解析

- 日期：2026-06-10
- 分支：`feat/l2-p2p-impl`
- base：`8b7994fb`（E4 測試 commit，已確認為 HEAD 後動工）
- commit：`bd324886`（已 push origin）
- 範圍：**僅 1 檔** `helper_scripts/cron/incident_sentinel_cron.sh`（+16 行，0 刪）

## 任務摘要

E4 RED 唯一 HIGH blocker：`incident_sentinel.py:635` A3 軸默認
`OPENCLAW_SENTINEL_API_BASE=http://127.0.0.1:8000`，但 trade-core uvicorn 實際
bind 在 Tailscale IPv4（`100.91.109.86:8000`，restart_all auto 解析政策、禁
0.0.0.0），loopback:8000 不聽 → installer apply 後 A3 常駐假 CRITICAL（每 4h
重發），§8.3-3「兩輪 all-pass」結構性不可達。cron wrapper 與 installer 均未設
此 env。

## 修改清單

| 檔 | 改動 |
|---|---|
| `helper_scripts/cron/incident_sentinel_cron.sh` | secrets/env 段後新增 A3 API base 解析塊（+16：8 行中文註釋 + 8 行邏輯） |

## 關鍵 diff（新增塊全文）

```bash
# A3 API base：對齊 uvicorn 實際 bind host（restart_all.sh auto 解析 Tailscale
# IPv4，禁 0.0.0.0）——實機 loopback:8000 不聽，sentinel.py 的 127.0.0.1 默認
# 會讓 A3 常駐假 CRITICAL（§8.3-3 兩輪 all-pass 結構性不可達）。
# 已設 OPENCLAW_SENTINEL_API_BASE 則尊重不覆蓋；未設則 auto-detect tailscale
# ip -4（mirror m11_replay_runner_daily_cron.sh 同坑解法；lib/api_bind_host.sh
# 是 server bind 視角且 0.0.0.0/:: 走 ERROR exit 2，不合本 client 端 fail-soft
# 場景，故 inline 不 source）。解析失敗不設變數，留 sentinel.py 默認 loopback
# （未來 bind=loopback 場景仍可達）；`|| true` 保證無 tailscale CLI 時
# set -euo pipefail 不殺 wrapper。
if [[ -z "${OPENCLAW_SENTINEL_API_BASE:-}" ]]; then
    TS_IP=$(tailscale ip -4 2>/dev/null | head -1 || true)
    if [[ -n "$TS_IP" ]]; then
        export OPENCLAW_SENTINEL_API_BASE="http://${TS_IP}:8000"
    fi
fi
```

## 修法決策：mirror m11 inline，不 source 共用 lib

E4 指定的 source-lib 優先條件（「m11 或其他 wrapper 已 source 它」）**為偽**：
grep 證 `lib/api_bind_host.sh` 只被 `restart_all.sh` / `clean_restart.sh` /
`fresh_start.sh` 三個 lifecycle script source，**0 個 cron wrapper** 用它；
m11（`m11_replay_runner_daily_cron.sh:144-153`）本身就是 inline。落到第二分支
「lib 接口不合 cron wrapper 場景 → mirror m11 inline + 註明理由」：

1. **語義不合**：`resolve_openclaw_api_bind_host` 是 server bind 視角——消費
   `OPENCLAW_BIND_HOST`，對 `0.0.0.0`/`::` 走 stderr ERROR + `return 2`。
   client 端組「可達 URL」的正確語義是該情形 fallback loopback，而非報錯；
   在 `set -e` fail-soft wrapper 內還得額外吞 exit 2。
2. **fail-soft 成本**：source 缺檔（舊部署/部分 checkout）在 `set -e` 下殺
   wrapper，需 file-existence guard，guard 失敗後仍要 fallback 邏輯 →
   複雜度不降反升。
3. **前例對稱**：兩個 cron wrapper（m11 + sentinel）同 inline 模式，維護一致。

## set -euo pipefail 安全性說明

- `[[ -z "${OPENCLAW_SENTINEL_API_BASE:-}" ]]`：`:-` 防 `set -u`；`[[ ]]` 在
  if 條件位不觸 errexit。
- `TS_IP=$(tailscale ip -4 2>/dev/null | head -1 || true)`：tailscale 缺失
  （exit 127）或失敗（daemon down/logged-out）時 pipefail 使管線非零，
  `|| true` 吞掉 → 賦值 exit 0 不觸 errexit。redirection 先於 command
  lookup 執行，故 command-not-found 的 stderr 訊息也進 /dev/null（cron mail
  零噪音）。
- `[[ -n "$TS_IP" ]]`：TS_IP 必已賦值（可為空），無 `set -u` 風險。
- 三案例實測 rc 全 0（見下）。

## 驗證輸出摘要（全綠）

1. `bash -n` → SYNTAX OK。
2. contained 模擬（真 wrapper 全程跑，`OPENCLAW_PYTHON_BIN` 指向 echo-stub
   截住 python 執行，不觸真 sentinel 防誤發告警；DATA 用 /tmp 隔離目錄）：
   - Case A 已設 `http://10.9.9.9:1` → log 透傳原值不覆蓋，rc=0。
   - Case B 未設 + `env -i PATH=/usr/bin:/bin`（無 tailscale）→
     `STUB_API_BASE=UNSET`（不設變數，留 py 默認），rc=0 不炸。
   - Case C 未設 + Mac 真 tailscale CLI（/usr/local/bin/tailscale）→
     `http://100.77.153.53:8000`，URL 形狀 `^http://100\.x:8000$` 驗過。
3. `python -m pytest helper_scripts/canary/test_incident_sentinel.py -q` →
   **58 passed**（未動；該 suite 0 引用 cron wrapper，grep 證）。
4. `git status --porcelain` → 僅 ` M helper_scripts/cron/incident_sentinel_cron.sh`；
   `diff --stat` = 1 file, +16。

## 治理對照

- 禁區守恆：**未碰** sentinel.py（never-remediate 結構測試
  `findall==["run"]` 不變量無第二 subprocess）、installer、其他任何檔。
- 0 硬編路徑 / 0 硬邊界 token；新註釋全中文（技術名詞保留英文）。
- 0 migration / 0 singleton；SCRIPT_INDEX 無需更新（既有腳本行為內變更，
  非新腳本）。
- 鏈位：E1 → 待 E2 複審 → E4 re-RED→GREEN 驗證（Linux 真 cron 環境）。

## 不確定之處

- Mac 解析到的是本機 Tailscale IP（100.77.153.53）；Linux cron 環境下解析到
  trade-core 自身 100.91.109.86 屬同邏輯，但**真 cron PATH 是否含 tailscale**
  （通常 /usr/bin/tailscale，Linux 標準安裝在 PATH）由 E4 Linux 實證收尾；
  即便不含，fallback 行為=現狀（py 默認 loopback），不會更糟。

## Operator 下一步

無需 operator 動作。E2 複審 → E4 Linux 真環境驗 A3 轉綠（兩輪 all-pass）→
QA → PM 統一 merge。
