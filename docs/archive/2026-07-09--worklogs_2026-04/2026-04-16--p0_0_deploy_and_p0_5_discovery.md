# 2026-04-16 工程日誌 — P0-0 部署 + P0-5 發現 + 部署後健檢

**Operator**：Nancun
**CCAgent**：Claude Code (Opus 4.6)
**Session 範圍**：G-2 daemon 健檢 → 平倉行為核查 → PHANTOM-2-FUP 發現 → P0-0 binary 部署 → 部署後觀察

---

## 1. 今日摘要

| 項目 | 狀態 |
|---|---|
| P0-0 RECONCILER-BURST-FIX | ✅ 實作 + 單測 + e2e 全綠 + binary 部署 |
| P0-5 PHANTOM-2-FUP RCA | ✅ Spec 完成（1 section x 9 subsection 共 178 行）未排期實作 |
| G-2 FundingArb daemon | 🟢 PID 1274192 持續運行，進度 2/20 fills（funding window 決定） |
| 引擎健康（部署後） | 🟢 三引擎 alive、ENGINE_CRASH=0、FAST_TRACK cascade 噪音消失 |

今日新增 commits：
- `a2e4719` — fix(reconciler): P0-0 startup grace window
- `b0c119a` — docs(p0-5): PHANTOM-2-FUP RCA
- `a068d4a` — test(reconciler): P0-0 e2e startup_grace_window_ignores_orphan_storm
- `b7633ae` — chore: refresh test-generated snapshot files
- `cd78ee9` — docs(todo): P0-3 阻塞者改為 P0-0；關鍵路徑剝離 P0-1

均未 push（遵循 Git Safety Protocol，push 需 operator 顯式授權）。

---

## 2. 發現時序

### 2.1 G-2 daemon 健檢（起點）
- `cat /tmp/openclaw/g2_monitor.progress.json` → 2/20 fills，累計 sum_pnl=-$0.38，sum_fee=$0.08，net edge=-$0.46
- daemon 存活 ~2h37m，funding window 時間驅動，無需介入

### 2.2 平倉行為核查
Operator 要求「確認是否現在策略有正常關閉單」。查詢 `trading.fills` (ts > 2026-04-16 15:40:48 UTC, engine_mode='demo')：
- `strategy_close:grid_close_short` 27 筆
- `strategy_close:ma_reverse_cross` 7 筆
- `strategy_close:grid_close_long` 6 筆
- `strategy_close:funding_arb_exit` 2 筆
- → **P0-4 R1 tag 透傳修復 (commit a5401ce) 生效**，策略關閉路徑乾淨

### 2.3 PHANTOM-2-FUP 揭露
同時觀察到 `risk_close:fast_track_reduce_half` **335 筆**，對 strategy_close 共 42 筆成 **8:1 ratio**。進一步檢查：
- DB 1-min bucket：18:03 UTC 單分鐘 **147 fills 跨 7 symbols**
- engine.log 18:03:41.602042 → 18:03:41.603320（**1.3 秒內**）出現 **9 次 FAST_TRACK ReduceToHalf WARN**
- 全是 ORDIUSDT 同條件：held_drop=6.07%、sigma=3.02、positions=2、risk_level=Cautious
- 每次都印 "halving positions (one-shot)" 但每秒重複數次 → one-shot guard **名存實亡**

### 2.4 根因定位
`rust/openclaw_engine/src/tick_pipeline/on_tick.rs:151-163`：

```rust
if self.governance.risk.level < openclaw_core::sm::risk_gov::RiskLevel::Defensive
    && !self.ft_reduced_symbols.is_empty()
{
    self.ft_reduced_symbols.clear();
}
```

配合 `fast_track.rs` 的 `evaluate_fast_track(Cautious, 6%, 3σ, ...) → ReduceToHalf` 形成閉環：
1. tick N：evaluate → ReduceToHalf
2. 行 155-163：risk < Defensive 為真 → 清空 `ft_reduced_symbols`
3. 行 175-228：for-loop 對「不在集合」symbols 執行 emit_close_fill → 插入集合
4. tick N+1：條件不變 → 同流程再跑 → 清空 → 再 emit

→ Cautious + 5%+ drop + 3σ 持續期間每 tick 重複觸發。

RCA 文件：`docs/references/2026-04-16--phantom2_fup_reduce_to_half_cascade_rca.md`

---

## 3. P0-0 部署操作記錄

### 3.1 Rebuild 觸發
- Operator 指令：`跑` → `bash helper_scripts/restart_all.sh --rebuild` (background task `bmaoyxs79`)
- 結束狀態：exit 0
- 效果：engine binary + PyO3 bindings 重新編譯，`a2e4719` P0-0 grace 邏輯生效

### 3.2 部署後健康指標（2026-04-16 ~20:51 UTC）

| 指標 | 修復前 | 修復後 |
|---|---|---|
| `/tmp/openclaw/engine.log` 體積 | 280MB | 381KB（新會話） |
| ENGINE_CRASH 計數（本會話） | N/A | 0 |
| 三引擎 alive（paper/demo/live） | — | ✅ 全活 snapshot=19.4s |
| `FAST_TRACK\|ReduceToHalf\|risk_close` 累計（2.6h / 本會話） | 335 行 | **1 行** |
| reconciler 啟動時間 | — | 18:44:58 三實例正常 |
| warmup baseline seeded | — | demo=6, live=0 |
| 後續 baseline reseed | — | 全 `seeded=0 stale=false`（無 drift） |
| P0-0 grace suppression 日誌 | — | 未觸發（無 drift → 無需抑制，符合預期） |
| REST failure | — | 1 筆 demo Bybit connect 失敗（fail-open 未升級） |

→ **P0-0 grace 在「零真實 drift」場景下透明無副作用**；真實驗收需等外部手動操作 / 冷啟動時 Bybit 殘留 drift 場景觀察。

### 3.3 G-2 daemon 狀態
- PID 1274192 持續運行（未被 rebuild 影響，python 子程序獨立於引擎 binary）
- 進度 2/20，達標後自動寫 `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md`

---

## 4. 關鍵決策

### 4.1 P0-5 不立即實作
理由（RCA §6）：
1. **未壞** — `reduce_position()` 會計正確，不強平整倉，不破壞 governance 不變式
2. Phase 5 PAUSED 狀態下噪音不造成新傷害（P0-3 不依賴 funding_arb 子集）
3. **P0-0 可能壓低發生率** — reconciler burst 消除 → Defensive auto-escalation 減少 → ReduceToHalf 觸發頻率下降
4. 建議流程：**觀察 24-48h** → 若 ReduceToHalf cascade 仍每秒多次 fire 才動 P0-5

### 4.2 P0-5 方案選擇（預留）
RCA 提三候選：
- **A**：HashMap + 60s cooldown（推薦主機制）
- **B**：tick-level early-return（輔助，需搭配 A/C）
- **C**：清空條件收緊至 Normal-only（副機制）
- **推薦組合 A + C**：cooldown 保證 burst 行為，Normal 清空允許新 episode 再半倉

### 4.3 Push 抑制
兩個 commit 已 merge 到本地 main 未 push。遵守 Git Safety Protocol，等 operator 顯式授權。

---

## 5. 待辦 / 觀察項

**短期**：
- [ ] 觀察 24-48h engine.log，確認 `FAST_TRACK ReduceToHalf` 不再每秒多次 fire
  - 命令：`grep "FAST_TRACK ReduceToHalf" /tmp/openclaw/engine.log | awk -F'T' '{print substr($2,1,8)}' | uniq -c | sort -rn | head`
- [ ] G-2 daemon 達 20/20 → 自動生成 audit → operator review
- [ ] P0-0 真實 drift 場景驗收（下次 `restart_all.sh --rebuild` 時若 Bybit 有殘留，觀察前 5min grace 日誌）

**若 P0-5 仍需實作**（P0-0 部署 48h 後判斷）：
- 修改點 `rust/openclaw_engine/src/tick_pipeline/mod.rs:738`（HashSet → HashMap）+ `on_tick.rs:151-228`
- 單測位置 `tick_pipeline/tests.rs:171` 已有 ReduceToHalf fixture 可擴展
- 預估 1.5d（spec 已完成，剩實作 + 2-3 單測 + 回歸）

**Push 審批**（operator 決定）：
- `a2e4719` P0-0 fix
- `a068d4a` P0-0 e2e test
- `b0c119a` P0-5 RCA
- `b7633ae` test snapshot refresh
- `cd78ee9` TODO P0-0 block graph update

---

## 6. 關鍵文件索引

- **P0-0 RCA**：`docs/references/2026-04-16--reconciler_burst_escalation_rca.md`
- **P0-5 RCA**：`docs/references/2026-04-16--phantom2_fup_reduce_to_half_cascade_rca.md`
- **G-2 監控腳本**：`/tmp/openclaw/g2_monitor.py`
- **G-2 進度**：`/tmp/openclaw/g2_monitor.progress.json`
- **G-2 預期 audit 輸出**：`docs/audits/2026-04-16--g2_funding_arb_clean_edge.md`（達 20/20 後自動生成）
- **引擎日誌**（重啟後新檔）：`/tmp/openclaw/engine.log`
- **Watchdog 日誌**：`/tmp/openclaw/watchdog.log`

---

**作者**：Claude Code (CCAgent) 認真核查 P0-4 R1 部署後行為 + P0-0 部署 + 健康驗證
**Reviewer**：PM（Nancun）
