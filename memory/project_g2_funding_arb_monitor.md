---
name: G-2 FundingArb 監控 daemon 狀態
description: v2 已結案 NEGATIVE EDGE 2026-04-18；daemon killed；demo funding_arb.active=false；待 R-02 Strategist 重評
type: project
originSessionId: 258747c1-ad4c-4e68-89b4-57dab2c6a8e0
---
**狀態（2026-04-18T17:00Z）：** **v2 結案 NEGATIVE EDGE。Daemon killed。Demo funding_arb stratey 停用（Rust 側 IPC hot-reload + TOML active=false）。**

## v2 結案（2026-04-18，n=13/20 partial，提前結案）

- **Audit 文件：** `docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md`（含 operator 結案註記）
- **Net edge：-$2.90 USDT / -36.76 bps**（per-fill 惡化 v1 -15.55 → v2 -36.76 bps）
- **勝率：0/13 = 0%**（v1 n=10 為 40%）
- **Exit 分布：13/13 全部在 `max_basis_pct = 0.5%` 邊界觸發**（basis 範圍 0.501–0.522%）— 說明入場時 basis 已接近止損邊界，hysteresis buffer (`entry_basis_ratio=0.8` → 0.4%) 被 market micro-structure 輕易吃掉
- **提前結案理由：** 趨勢單調惡化 + 0/13 勝率 + 13/13 exit 命中 basis 上限 = 無「後期反轉」合理路徑
- **結論：** MICRO-PROFIT-FIX-1（fast_track + COST EDGE 窄帶）對 funding_arb 無效甚至略負；funding_arb 利潤來自 funding payment 非 basis mean-reversion，當前成本預算 (`total_cost_bps=34` ≈ 0.34%) 吃掉 `max_basis_pct=0.5%` 的 68%，預算本就太薄

## Daemon + 策略狀態（2026-04-18 結案後）

- Daemon PID 1834915 `kill` 完成（`/tmp/openclaw/g2_monitor.pid` 已 cleanup）
- `/tmp/openclaw/g2_monitor.progress.json` 最後狀態保留
- v1/v2 歷史 monitor/log/progress 按 `.v1_n10_1776457972` / `.pre_r1.1776356004` 後綴歸檔在 `/tmp/openclaw/`
- `settings/strategy_params_demo.toml` `funding_arb.active = false`（含結案註記）
- Rust funding_arb 已補 `update_params_json` + `FundingArbUpdateParams` + `impl StrategyParams`（參考 bb_reversion 模式，但 intentional 含 `active` 字段 — 記錄於 funding_arb.rs inline comment），+5 新單測全綠
- 下次 engine rebuild 重啟時 TOML active=false 生效；IPC `update_strategy_params` 亦可 hot-toggle 不需重啟（ORPHAN/DUST fixes 之後 funding_arb 也加入 tunable surface）

## v1 結案（2026-04-17T20:05Z，n=10/10）

- **Net edge：-$1.04 USDT / -15.55 bps**
- **勝率：40% (4/10)**
- **Verdict：❌ NEGATIVE EDGE**
- **Audit 文件：** `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md`
- **Per-symbol：** ORDIUSDT 2/2 全虧、MOVRUSDT 3 筆淨負、SOONUSDT 1/1 正

## 前置歷史（P0-4 R1 根因）

- 不是策略層系統性不退場，是**記錄遮蔽 bug**：舊版 `execute_position_close` 硬編碼 `strategy: "risk_check"` 吞掉真 tag
- Commit **a5401ce** 修復 tag 傳播（2026-04-16）— R1 前的 29h 0/20 是遮蔽 bug 產物
- 完整審計：`docs/audits/2026-04-16--demo_zero_strategy_exit_audit.md` V2 版

## 下次接手應關注

### R-02 / Strategist 任務排入後做什麼

重評 funding_arb 三參數配對，特別注意：
1. `total_cost_bps` 34（perp 11 + spot 20 + slippage 3）是否反映實際 Bybit taker + funding 來回成本？考慮降 slippage 若用 limit 入場（但需先修 GAP-9 paper 無限價撮合）
2. `max_basis_pct` 0.5% 太寬，13/13 exit 全命中此邊界。可能該收到 0.3% 並搭配 `entry_basis_ratio = 0.5`（entry 0.15% / exit 0.3%）
3. `funding_threshold` 0.0005 = 5 bps — 實際 Bybit funding rate 歷史分布多集中在 ±5–10 bps，閾值可能太低讓 edge 為負時也通過
4. 或考慮 entry-signal redesign：等 funding 8h 定存後 5–10min 入場，捕獲 funding payment 時間窗，不追基差
5. ONDI/SOON/SIREN/HIGHUSDT/CL 等 symbol 分布顯示 universe 無偏好 — edge 問題是策略本體，非幣種選擇

### 若要重新啟用 funding_arb（不用重啟 engine）

現在可通過 IPC hot-reload：
```python
from app.ipc_client import EngineIPCClient
import os, json
os.environ["OPENCLAW_IPC_SECRET"] = open(os.path.expanduser(
    "~/BybitOpenClaw/secrets/environment_files/ipc_secret.txt")).read().strip()
client = EngineIPCClient()
await client.connect()
await client.call("update_strategy_params", {
    "engine": "demo",
    "strategy_name": "funding_arb",
    "params_json": json.dumps({
        "active": True,  # or False
        "cooldown_ms": 3600000,
        "total_cost_bps": 34.0,
        "expected_periods": 3.0,
        "funding_threshold": 0.0005,
        "max_basis_pct": 0.5,
        "max_hold_ms": 259200000,
        "entry_basis_ratio": 0.8,
    })
})
```
記得同步更新 `settings/strategy_params_demo.toml` 保證下次重啟一致（hot-reload 不會自動寫 TOML for funding_arb）。

## 關鍵副產品（仍有效）

- operator 手動 `ipc_close_all` 是全引擎最賺錢的平倉路徑（+$45.84 / 29 筆，avg +$1.58）— tag 正確寫入，R1 前後不受遮蔽 bug 影響
- R1 修復後歸因可信度大幅提升，可用真 tag 做 per-trigger edge 分析
