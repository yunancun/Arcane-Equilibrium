# AE 運行面全面改名 — 遷移指引（Apple Silicon 遷移時強制執行）

**狀態**：GATED（未啟動）。本文檔是未來執行時的完整指引；TODO §7 僅保留一行指針。
**建立**：2026-06-10（operator 決策：現階段維持軟更名口徑，改名綁定 Apple Silicon 遷移窗口強制執行）
**背景**：2026-05-06 軟更名後，「玄衡 · Arcane Equilibrium」為正式產品名，OpenClaw 降為控制平面服務族名；運行面名稱（crate / env var / systemd / 路徑 / repo 名）當時決策「短期不改」。本文檔記錄全面改名的波及面盤點（2026-06-10 實測）、觸發條件、分階段流程、風險與驗收標準。

---

## 一、觸發條件（gate）

| 條件 | 性質 |
|---|---|
| **Apple Silicon 遷移啟動**（Linux trade-core → Mac M 系列 runtime） | **強制**——屆時本來就要重做 systemd→launchd、物理路徑、部署面，改名搭車邊際成本最低 |
| Mainnet hardening 期（真實資金上線前的系統加固窗口） | 可選提前——若 operator 判斷認知收益值得 |
| 前置 gate（任一觸發路徑都必須滿足） | 無 in-flight migration / 無未收口 deploy bundle / 全測試綠 baseline 凍結 / 無 RUNNING soak |

**改名完成前的禁令（自本文檔建立日起生效）**：禁止新代碼使用 `AE_*` env 前綴或 `ae_*` crate/模組前綴——雙前綴並存是 agent 誤解的最大來源，必須保持「單一舊名 + 文檔錨定」直到一次性原子切換。

## 二、波及面盤點（2026-06-10 實測快照；執行時必須重新掃描）

| 層 | 規模 | 關鍵項 |
|---|---|---|
| `OPENCLAW_*` env vars | **353 個**（去重） | 含 5-gate 硬邊界 `OPENCLAW_ALLOW_MAINNET`、`OPENCLAW_IPC_SECRET`、`OPENCLAW_LIVE_AUTH_SIGNING_KEY`（OPS-2）、`OPENCLAW_BASE_DIR`/`OPENCLAW_SRV_ROOT`（legacy alias 對）；分佈：repo 代碼 + Linux systemd env + crontab + operator shell 配置 |
| 代碼字樣 | **~6,400 處** | Rust .rs 2,029（不含 target）/ Python .py 2,313 / helper_scripts 1,973 / tests 58 / settings 15 |
| Rust crates | 3 個 + binary | `openclaw_types` / `openclaw_core` / `openclaw_engine`（crate 名+全部 `use` import+PyO3 綁定）；binary `openclaw-engine` |
| Python 模組 | `openclaw_routes`（API 路由）+ import 面 | `/api/v1/openclaw/*` 路由前綴是對外 API 契約（OpenClaw Gateway 調用）|
| systemd units | 8+ | openclaw-engine / -watchdog / -trading-api / -gateway / -caddy / -tls-renew(-notify) / -listing-collector；重裝=sudo/operator 閘控；Apple Silicon 上對應 launchd `com.ae.*` |
| IPC / 路徑 | `/tmp/openclaw/`（含 ai_service.sock、aeg_gate_b_runs 等） | 運行時契約；切換需雙監聽過渡或停機窗口 |
| 物理路徑 | Linux `~/BybitOpenClaw/srv`、`~/BybitOpenClaw/secrets` | 多個腳本寫死 fallback 默認值（`${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}` 模式） |
| GitHub repo | `yunancun/BybitOpenClaw` | rename 後 GitHub 自動 redirect，但三端 remote、CI、文檔引用需更新 |
| 產品組件名 | OpenClaw Control Console / OpenClaw Gateway | 是否一併改（→ AE Console / AE Gateway）= 屆時 operator 決策；GUI 標題、登錄頁、Tailscale serve 配置 |

## 三、目標命名約定（基調；細節屆時 PA 確認）

- env：`OPENCLAW_*` → `AE_*`（`OPENCLAW_ALLOW_MAINNET` → `AE_ALLOW_MAINNET` 等；`OPENCLAW_SRV_ROOT` legacy alias 趁機淘汰，只留 `AE_BASE_DIR`）
- crates：`openclaw_types`/`openclaw_core`/`openclaw_engine` → `ae_types`/`ae_core`/`ae_engine`；binary → `ae-engine`
- systemd/launchd：`openclaw-*` → `ae-*` / `com.ae.*`
- 路徑：`/tmp/openclaw` → `/tmp/ae`；`~/BybitOpenClaw` → 屆時隨新機 layout 定（建議 `~/ArcaneEquilibrium` 或 `~/ae`）
- repo 名：operator 屆時定（候選 `ArcaneEquilibrium`）
- DB：表名/schema 無 openclaw 字樣，**零改動**（已驗證）；audit JSONL 歷史值不回溯改寫

## 四、分階段流程（每階段 = 獨立 green checkpoint）

**P0 前置**：重掃波及面（本文檔 §二過期則更新）；凍結測試 baseline；PA 出正式遷移設計包；**CC 必審**（觸碰 `OPENCLAW_ALLOW_MAINNET` 等硬邊界字段，走 compliance / architecture 鏈 PM→CC→FA→PA）。

**P1 env var 兼容層**（風險最高，最先做、最後收）：讀取邏輯改為「`AE_*` 優先 → `OPENCLAW_*` fallback + deprecation 日誌」；353 個變量分批，**5-gate 安全字段最後切**；fallback 保留一個完整版本期。Linux/launchd env 文件、crontab、shell 配置同步雙寫。

**P2 代碼 rename**：crates（Cargo.toml + 全 import + PyO3 模組名）→ Python 模組 → 路徑常量；每層一次性原子 commit + 全測試綠；`/api/v1/openclaw/*` 路由保留 alias 一個版本期（Gateway 外部調用方）。

**P3 runtime 面**：systemd→launchd unit 改名重裝（operator 窗口）；IPC socket 雙監聽過渡或停機窗口一次切；secrets 路徑遷移 + `authorization.json` 重簽（HMAC 綁 IPC_SECRET **值**不變，但讀取 env 名變，須驗證簽章鏈完整）；watchdog / cron / Telegram 告警鏈全鏈驗證。

**P4 repo rename + 三端 remote 更新**：GitHub rename（redirect 自動）→ Mac/Linux remote URL 更新 → CI 配置。

**P5 文檔與治理**：CLAUDE.md / README / CONTEXT.md Product naming 詞條更新（OpenClaw 詞條轉歷史注記）；AE_INVENTORY、SCRIPT_INDEX、全 docs 引用 sweep（R4 audit）。

**P6 兼容層移除**（下一版本期）：刪除 `OPENCLAW_*` fallback；grep 全 repo 零殘留舊名（docs/archive 與歷史報告除外）；E3 secret-leak 掃描確認無舊名洩漏路徑殘留。

## 五、風險清單與緩解

| 風險 | 緩解 |
|---|---|
| fail-closed 系統 env 漏改 = 拒啟動/降級（先例：2026-06-05 bind-host 20h 宕機） | P1 兼容層 fallback + deprecation 日誌先行一個版本期；切換後 grep 驗證 + watchdog 告警驗證 |
| 5-gate live boundary 字段改名引入授權旁路或鎖死 | CC 專項審計；5-gate 字段最後切換；切換前後 E2E 授權鏈測試（renew/approve/TTL/拒絕路徑） |
| IPC socket 路徑切換期間引擎↔API 斷聯 | 雙監聽過渡或維護窗口一次切（stop_all → 改 → restart_all） |
| `authorization.json` 簽章鏈因 env 名變化失效 | 簽章綁定值非名稱；重簽走 GUI renew 正路（禁手寫）；LiveDemo lane 重授權納入 checklist |
| 跨三端（Mac/origin/Linux）遷移窗口 binary/source/env 不匹配 | 每階段三端同步後才進下一階段；engine rebuild 與 env 切換同窗口 |
| 測試內 openclaw 字樣（58 處 tests + fixtures）漏改造成假綠/假紅 | E4 全量回歸 + baseline 對照；禁刪測試遮蓋 |
| 半改名狀態長期滯留（最大認知風險） | 每階段有完成期限；P6 收尾 grep 零殘留為 DONE 定義；改名期間凍結其他大型 refactor |

## 六、驗收標準（DONE 定義）

1. 全 repo grep `OPENCLAW\|openclaw` 活代碼/配置/腳本零命中（`docs/archive/`、歷史報告、git history 除外）。
2. Python pytest + Rust cargo workspace 全綠，數量不低於凍結 baseline。
3. 雙進程 E2E + 授權鏈（5-gate）+ watchdog 自愈 + cron 三類 runtime 驗證全過。
4. 灰度觀察 ≥7d 0 CRITICAL（QA e2e-integration-acceptance 標準）。
5. R4 文檔交叉引用 audit PASS；AE_INVENTORY 與 SCRIPT_INDEX 同步。
6. memory / TODO / CLAUDE_CHANGELOG 收口，本文檔標記 EXECUTED 後歸檔。

## 七、工程量粗估（2026-06-10 視角）

PA 設計 2-3d；P1 兼容層 3-5d（含 Linux env 面）；P2 代碼 rename 3-4d（机械量大但工具可半自動）；P3 runtime 面 2-3d + operator 窗口×2；P4-P6 共 2-3d + 一個版本期等待。合計 **~2-3 週 wall-clock**（不含灰度 7d），多個 operator 閘控點。屆時若搭 Apple Silicon 遷移車，P3 與新機部署合併，淨增量約 -40%。
