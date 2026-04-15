# OpenClaw TODO — 工作計劃清單

**最後更新：2026-04-15**（🚨 **引擎 04:03 自殺事故** — WS tick stale Fix 4 按設計 cancel，但 **watchdog daemon 從未部署** → 7h10m 空窗無人拉起，11:13 operator 手動重啟。新增 **ENGINE-HEAL-FUP-1/2/3**。**FIX-PHASE1 FUP-A/B 完成** — canary_writer warn 節流 1Hz + drop counter + 覆蓋 `TrySendError::Full` 分支單元測試。**E4-HYG-1 ✅** — `golden_extreme.rs` 漏 `trailing_activation_pct` 欄位補齊，`cargo test -p openclaw_core` 恢復 372 pass。**ENGINE-HEAL-FUP-1 ✅ 正式結清** — watchdog 從 nohup PID 592881 升級為 systemd user unit `openclaw-watchdog.service`（Restart=always + log append + linger=yes 跨重啟存活），新 PID 678153 Main（PPID=1983 systemd --user）。**EDGE-P3-1 Phase B #1 ✅** — main.rs bootstrap 構造 `PerEnginePredictors` → 三引擎 Deps；E2 nits（debug_assert 雙注入 + Arc::clone 精簡）收尾；tract/ort backend 選型 audit 文檔化；commits `c9416d0` + `0fcf449` + `3dd845c`。）
**測試基準線**：Rust **engine lib 1264 + core 372 + e2e 35 = 1671** · Python **2852 passed (5 skipped · 0 fail)** · ml_training **135 passed (6 skipped)**
**EDGE-P3-1 Phase A/A6 COMPLETE** — gate 在 hot path 被諮詢 + MA/BBR/BBB 策略 confluence/persistence 經 OrderIntent 穿透至 feature_builder；產線預設 `use_edge_predictor=false` 零行為改變；commits `8c1f234` A1-A4 + `3753ede` A5 + `a23b268` A6
**EDGE-P3-1 Phase B IN PROGRESS** — #1 bootstrap + #2 backend 選型 + #5 pipeline_cmd_tx wire ✅；PA #63 `load_training_data` + ETL Parquet export ✅（ML-MIT 可啟動）；**Step 7a `DecisionFeatureSnapshot` Rust-direct writer ✅ (commit `d73addb`)** · **Step 7d `write_toml_atomic_fsynced` + T23 SIGKILL 回歸 ✅**；#3 model loader 等 Stage 2 artifact；Step 7 餘項 4 條（7b/7c/7e/7f：`ReloadEdgePredictor` IPC · shadow-fill Python consumer · 兩階段 commit · capabilities endpoint）可獨立前推

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 歷史歸檔索引在文件末尾。詳細完成度視角見 README.md。

---

## 🎯 Immediate Next Actions（依賴 + 阻塞力排序）

| # | 項目 | 預估 | 阻塞者 | 解鎖 |
|---|------|------|-------|------|
| ~~**1**~~ | ✅ **ENGINE-HEAL-FUP-1 watchdog daemon 化** — 2026-04-15 11:31 先以 nohup PID 592881 啟動；**14:25 升級為 systemd user unit**（`~/.config/systemd/user/openclaw-watchdog.service`，Restart=always + `StandardOutput=append:/tmp/openclaw/watchdog.log` + linger=yes 跨重啟存活）。新 PID 678153 Main（PPID=1983 `systemd --user`），flock 正確轉交 | done | — | ✅ |
| ~~**2**~~ | ✅ **ENGINE-HEAL-FUP-2 根因調查完成** — 2026-04-15：實為 **2h 內 15+ 波段累積壓力**（非一秒 8,445 噴發），主因 = canary JSONL 同步寫盤在 live event loop 熱路徑上 + live channel 512 偏小。詳 `docs/worklogs/2026-04-15--engine_2000_stall_postmortem.md` | done | — | ✅ |
| ~~**3**~~ | ✅ **ENGINE-HEAL-FIX-PHASE1** — 合併 R1（canary 寫盤改 bounded mpsc → 專用 tokio 任務 / BufWriter / size rotation）+ R2（live channel 512→1024 對稱化）+ FUP-3（`OPENCLAW_DISABLE_CANARY_DUMP=1` 旗標 + 4 個 env 控制旋轉）單 commit。1262 + 372 + 35 = 1669 cargo tests 0 fail。E2 GREEN（2 nits 列為 FUP）。**留尾**：operator 需 `restart_all.sh --rebuild` 部署；24h 觀察 `live pipeline lagging` WARN 是否歸零 | done | — | ✅ |
| ~~**3a**~~ | ✅ **FIX-PHASE1 FUP-A** — `canary_writer` handle 加 `total_dropped` + `last_warn_ms` Arc<AtomicU64>；Full 分支遞增計數器 + 1Hz CAS 節流 warn（避免 warn 自身在持續壓力下成為 log flood）。engine lib 1262→1264（+2） | done | — | ✅ |
| ~~**3b**~~ | ✅ **FIX-PHASE1 FUP-B** — `try_send_full_branch_drops_and_counts` + `warn_throttle_caps_at_one_hz` 單元測試；1-slot 通道驗證 Full 分支非阻塞 + 計數器單調 + clone 共享 Arc；節流窗口測試 | done | — | ✅ |
| **4** | 🧪 **G-2 FundingArb 驗證** — Step 4.1 ✅ 路徑全鏈路驗證（strategy_exit + ipc_close 都帶 realized_pnl 入 DB）。Step 4.3 ⏳ **後台 daemon PID 598572 監控中**（`/tmp/openclaw/g2_monitor.{py,log,pid,progress.json}`），達 demo ≥20 strategy_exit fills 自動寫 `docs/audits/2026-04-15--g2_funding_arb_clean_edge.md`。**operator/Claude 接手先 `cat /tmp/openclaw/g2_monitor.progress.json`** | ~17h ETA | — | Phase 5 歸因量化確認 · LG-1 觀察期起點 |
| **5** | 🕰️ **LG-1 Paper Trading 21d** — EDGE-P0/P1 + FA-PHANTOM-1 + FUP-8 部署後啟動正式觀察期；不再綁定 05-01 | 3 w | #2, #4 | Live Gate · LG-2/3 |
| **6** | 📊 **Phase 5 策略 Edge 2w 重評** — 乾淨 paper 2w 後重算 per-strategy gross edge。若翻正 → Phase 5 cost_gate 工作重啟；若仍負 → 策略本身需重做（EDGE-P2/P3） | 2 w | #4 | Phase 5 restart / rebuild 決策 |

---

## 🗓️ 排期總覽（2026-04-14 更新）

| 週次 | 日期 | 主要焦點 | 狀態 |
|------|------|---------|------|
| W19-W21 | 04-14~05-02 | 基礎設施 / 安全 / Phase 6 / 3E-ARCH / Audit | ✅ 歸檔 |
| W22 | 05-05~09 | **G-SR-1 + R-02/R-06-v2**（提前完成）· **FA-PHANTOM-1 + FUP-1~8 全數結清** · **ENGINE-HEAL deploy** · **G-2 驗證重啟** | 🟡 進行中 |
| W23 | 05-12~16 | **LG-1 觀察期**（if clean）· G-7 Teacher · G-10 Calibration · LG-2/3 | ⬜ |
| W24 | 05-19~23 | **LG-4/5 Live Gate**（M/N 章）· SEC-21 · QoL-2 | ⬜ |
| W25+ | 05-26+ | **EDGE-P3-1 Realized Edge Predictor** · Phase 5 補強或重做 · R-06 全 5 agent | ⬜ |

**關鍵路徑**：`~~FUP-1 watchdog daemon 化~~ ✅ → ~~FUP-2 根因調查~~ ✅ → FIX-PHASE1 合併 (R1+R2+FUP-3) → G-2 驗證 (daemon 監控中) → LG-1 21d → LG-4/5 → Live`
**最早 Live 日期**：視 FIX-PHASE1 + LG-1 乾淨觀察期起點。樂觀估 **W24 末**（～2026-05-23）。

---

## 🟡 W22 活躍工作（當前週）

### 🚨 ENGINE-HEAL 事故 follow-up（2026-04-15 發現）

**時間線**：
- 2026-04-14 23:56:35 UTC 引擎啟動（PID 未存檔；rotated log `engine-1776244436.log`）
- 2026-04-15 00:04:55 UTC — 首波 `fan-out: live pipeline lagging, tick dropped`（3,474 條在該分鐘內）— 後續 ~2h 內 15+ 波段共 8,446 條（TODO 原敘述「02:00:33 一秒 8,445 條」為誤讀，實際 02:00 波段只 464 條）
- 2026-04-15 02:03:05.327 UTC（04:03 CEST）`ERROR WS tick stale — triggering engine cancel (Fix 4) stale_ms=135201 threshold_ms=120000` → 優雅關閉（10 倉位市價平、event consumer 存盤 ticks=1,753,274 fills=382 balance=530.01）
- 04:03 → 11:13 **空窗 7h10m**（watchdog daemon 不存在 → 無重啟）
- 2026-04-15 09:13:56 UTC（11:13 CEST）operator 手動拉起 PID 577219（parent=init，非從 shell 啟動）

**事實**：
- ✅ Fix 4 WS tick stale self-cancel **按設計觸發**（stale_ms > threshold_ms）
- ❌ Fix 2 Python watchdog **從未以 daemon 模式部署**：`restart_all.sh:187` 只跑 `engine_watchdog.py --status` 一次性檢查；`/tmp/openclaw/watchdog.log` 和 `canary_events.jsonl` 根本不存在；systemd 僅 `openclaw-gateway.service`；crontab 空
- ✅ **Fix 4 上游根因已查明**（2026-04-15 post-mortem）：live event loop 的 `event_rx.recv()` select arm 在每 tick 同步 `writeln!` 到 canary JSONL（raw `std::fs::File`，無 buffer），~280 ticks/sec × 2.5KB × canary 檔案已 100GB+ 的 FS 壓力週期性卡住 consumer；加上 live fan-out channel 512 偏小（paper/demo 1024）。115s consumer 拉不到新 tick → Fix 4 越過 120s 閾值
- 🗑️ `/tmp/openclaw/engine_results.jsonl` 111 GB 並仍在增長（canary schema 每 tick 2-3KB）— FUP-3 同時解

- [x] **ENGINE-HEAL-FUP-1** ✅ 2026-04-15 14:25 — watchdog daemon 正式化為 systemd user unit（Action #1）
  - **方案 A 採用**：`~/.config/systemd/user/openclaw-watchdog.service`
    - `Type=simple` + `Restart=always` + `RestartSec=5` + `StartLimitBurst=5/60s`
    - `StandardOutput=append:/tmp/openclaw/watchdog.log` + `StandardError=` 同檔
    - `WorkingDirectory=/home/ncyu/BybitOpenClaw/srv`（auto-restart 用 `restart_all.sh --engine-only`，需 repo root）
    - `KillSignal=SIGTERM` + `TimeoutStopSec=30` → watchdog 內建 SIGTERM handler 清 flock
  - **跨重啟存活**：`loginctl show-user ncyu` 確認 `Linger=yes`，user systemd 在 boot 時自動啟動 watchdog
  - **遷移**：SIGTERM PID 592881 釋放 flock → `daemon-reload + enable --now` → 新 PID 678153（PPID=1983 `systemd --user`，非 PPID=1 nohup 孤兒）
  - **單例 + 退避機制確認**：`engine_watchdog.py:508` `fcntl.flock LOCK_EX|LOCK_NB`（重複啟動 exit 3）；`RESTART_BACKOFF_SECONDS = [60,120,300,600,3600]`；`MAX_CONSECUTIVE_FAILURES = 5` 後 circuit-break
  - **未壓測 kill -9 engine**（會打斷 G-2 daemon + 當前活倉）；依 snapshot-based 健康判斷 + Fix 4 self-cancel 時 watchdog 能重啟的邏輯已在 `engine_watchdog.py` main loop 驗證過（commit `4e09c09` Fix 2 單元測試）

- [x] **ENGINE-HEAL-FUP-2** 🔍 live pipeline lagging 根因 — **調查完成 2026-04-15**
  - **TODO 敘述更正**：**不是** 8,445 條一秒噴發，而是 **~2h 內 15+ 波段** 共 8,446 條（首波 00:04:55 UTC，共 3,474 條；末波 02:00 共 464 條）；Fix 4 是累積壓力最終讓 consumer 120s 拉不到 tick 觸發
  - **根因**（詳 `docs/worklogs/2026-04-15--engine_2000_stall_postmortem.md`）：
    1. **主因**：canary JSONL 在 `event_consumer/mod.rs:890-896` 以**無 buffer 的 `std::fs::File` + `writeln!`** 在 `event_rx.recv()` select arm 裡**同步寫盤**；live ~280 ticks/sec × 2.5KB JSON = ~700KB/sec 同步 syscall，配上 canary 檔案已長到 100GB+ 的 FS cache 壓力，consumer loop 週期性被 I/O 卡住
    2. **加劇**：live fan-out channel **512** vs paper/demo **1024**（無設計理由）→ 飽和時間減半
    3. **非因**：337 條 `fills flush failed`（V017 schema 未 apply）與 lagging 併發但不相關，`flush_fills` 於錯誤後 `buf.clear()` 不 back-pressure
  - **修復計劃**（Phase 1 單 PR，R1+R2+FUP-3 一起）：
    - **R1** canary 寫盤移出 event loop（bounded mpsc → 獨立 blocking 任務 / `BufWriter`；最大影響項）
    - **R2** live channel 512 → 1024 對稱化（`main.rs:736`，1 行）
    - **FUP-3** env flag `OPENCLAW_DISABLE_CANARY_DUMP=1` + size-based rotation
    - 驗收：24h 零 `live pipeline lagging` WARN；canary dump ≤5GB/24h（或 0 if flag 開）
    - R3/R4 延後到 R1+R2 入產後再看 telemetry 決定
  - ✅ 產出 worklog

- [x] **ENGINE-HEAL-FUP-3** ✅ engine_results.jsonl rotation / 關閉 — 折入 FIX-PHASE1 同 commit
  - `OPENCLAW_DISABLE_CANARY_DUMP=1` 覆寫 `OPENCLAW_CANARY_MODE` 完全關閉（灰度驗證過後常態）
  - `OPENCLAW_CANARY_ROTATE_MB`（預設 1024 = 1GB）+ `OPENCLAW_CANARY_MAX_ROTATED`（預設 3）→ 自動輪轉到 `engine_logs/engine_results-<UTC ts>.jsonl`，mtime 排序保留最新 N 個

### 📎 E4 hygiene（2026-04-15 巡查發現）

- [x] **E4-HYG-1** ✅ 2026-04-15 — `openclaw_core/tests/golden_extreme.rs:161` 加 `trailing_activation_pct: None,`（保留原測試語義：`activation_pct` 默認 = `trail_pct` 2%，`test_trailing_and_time_stop_interaction` 時間停損斷言不變）。`cargo test -p openclaw_core` 恢復 372 pass 0 fail；engine lib 1264 無迴歸

### 部署窗口（已完成，歸檔用）

- [x] **ENGINE-HEAL-DEPLOY** ✅ 2026-04-15 — PID 403560 跑 binary mtime 01:55，含 ENGINE-HEAL Fix 1/3/4 + FA-PHANTOM-1 leverage-aware margin + FUP-8 Phase 1（sentinel flag `f6b07cd`）+ FUP-8 Phase 2（paper 走 sizing `2061310`）全數到位
  - DB 驗證：paper intents 10 筆最近 3 分鐘樣本，`submitted_qty` 真實 sized（0.47~31742），`is_sentinel=false`
  - 註：此 binary 已於 2026-04-15 02:03 Fix 4 self-cancel 下線，11:13 operator 手動重啟後 PID 577219 仍是同一 binary mtime 01:55（含 ENGINE-HEAL 全部修復）

### G-2 FundingArb 驗證（Action #4 — FUP-1 ✅ 已解除）

- [ ] **G-2** FundingArb 策略驗證 + 參數調優
  - OC-5 ✅：FundingArb on_tick() 完整實現（entry/exit/cooldown/basis/edge），index_price TickContext 全鏈路
  - 2026-04-14 驗證失敗 — 窗口 17:33-21:55 內 22 paper funding_arb fills 全為 PHANTOM（FA-PHANTOM-1 致瞬平）
  - **恢復流程（#1 deploy 後）**：
    1. 驗證修復：手動跑 funding_arb paper 1 個 entry → 查 paper_state positions 有出現 → IPC close → DB 出現 close fill with realized_pnl
    2. 重新啟動驗證窗口（paper `funding_threshold=0.0001 / total_cost_bps=1.0` 臨時降，4h 累積後還原）
    3. 累積 ≥20 乾淨 fills 後分析 edge + 撰寫 audit note

### FA-PHANTOM-1 留尾 — 已清

- [x] **FA-PHANTOM-1-FUP-7** operator 選 C（保留 90% 為 cash-mode fail-safe + 加註釋）— 2026-04-15 完成
  - `fast_track.rs:39-57` 加了 ~19 行註釋說明：(a) 90% 是 Bybit MMR 物理常數不可 auto-scale；(b) margin_utilization_pct 本身 post FA-PHANTOM-1 fix 已是 leverage-aware；(c) 當前高槓桿配置下不觸發是刻意的 cash-mode 兜底；(d) 反 pattern 警告不要為「看起來死碼」去降閾值（會重開 FA-PHANTOM-1 類 false-positive）
  - 純註釋改動，`cargo check` 通過，無新測試需求

### Phase 5 策略 Edge 觀察（Action #6）

- [ ] **PH5-VERIFY-1** 乾淨 paper 2w 重評 — EDGE-P0/P1 + FA-PHANTOM-1 fix 部署後 2 週數據，重新評估 gross edge
  - 若 gross edge 翻正 → Phase 5 cost_gate 工作重啟
  - 若 gross edge 仍負 → 策略本身需重做（EDGE-P2/P3 排期）

---

## 🟢 W23-W24 下週工作

### AI 治理層補強（G-1 後續）

- [ ] **G-7** ClaudeTeacher 正式啟用（W23）
  - 現況：consumer_loop.rs `enabled = false`（啟動時 fail-closed）+ learning_store "currently has no consumer"
  - 前置：E3 審查 PASS ✅ + G-3 IPC 認證 ✅ + 21d paper 穩定（LG-1）

- [ ] **G-10** Calibration.py 整合（W23）
  - 現況：ml_training/calibration.py 骨架，apply_calibration 缺整合入口
  - 目標：calibrate_isotonic → run_training_pipeline.py，加入 ECE < 0.05 門檻
  - 前置：fills 累積 + 2-11 actual training

### Live Gate（W23-W24）

- [ ] **LG-2** H0 Gate blocking 驗證（shadow → blocking，W23）
- [ ] **LG-3** provider pricing table 正式綁定（W23）
- [ ] **LG-4** M 章 Supervised Live Gate（W24）
- [ ] **LG-5** N 章 Constrained Autonomous Live（W24）
- [ ] **G-4 / SEC-21** Cookie `secure=True`（HTTPS 部署後，W24）

**完成後**：換入 mainnet API key，系統即進入真實 Live（零代碼改動）。

### QoL

- [ ] **QoL-2** Demo AI cost 無追蹤 — `tab-demo.html` 硬編碼 `'N/A'`，後端無 per-engine AI 調用成本歸因機制（依賴 G-1 H1-H5 AI 治理層接通後才有意義）

---

## 🔮 W25+ 長期工作

### 🧠 EDGE-P3-1 Realized Edge Predictor（取代 JS shrinkage，解鎖 Phase 5 cost_gate）

- [ ] **EDGE-P3-1** 🧠 **Realized Edge Predictor** — shrunk_bps 退役 · 單筆單子 ex-ante edge 預測
  - **一句話**：`shrunk_bps` 是「策略**歷史平均**賺多少」（靜態）；此項改為「**這一筆**在現在市場條件下預期賺多少」（quantile LightGBM 動態預測）
  - **Why**：當前所有策略 gross edge ≈ 0，shrunk_bps 塌到 -35.72 bps → cost_gate 形同虛設。LightGBM 管線是空殼。LinUCB 只做 arm 選擇。三件事同一個洞：**沒有模型把「決策瞬間 features」映射到「實現 edge」**
  - **模型**：`P(realized_edge_bps | context)` per-strategy quantile LGBM (q10/q50/q90) + CQR + monotone rearrangement
  - **Features**（17 維，決策瞬間快照，禁 look-ahead）：Regime 5 · Microstructure 3 · Strategy 3 · Position 3 · Time 3
  - **Label**：`realized_net_edge_bps = (exit-entry)/entry × side − closed_fees_bps`，close fill 時回填；grid VWAP merge / 其他 qty-weighted blend
  - **接線**：替換 cost_gate 比較邏輯 → `predicted_median_edge − k×(median−q10) > cost` 才放行；`q10 > 0` 才加倉
  - **規格演化**（2026-04-15 完成 4 輪審查）：v1.0 → v1.1（round-1 QC/QA）→ v1.2（round-2 F1-F10，816→1019 行）→ v1.3（round-3 U1-U4 + M1，1019→1101 行）→ round-4 **GREEN**
  - **規格路徑**：`docs/references/2026-04-15--edge_predictor_spec.md`（1101 行 · CC 13 項 · T1-T23 命名測試）
  - **Worklog**：`docs/worklogs/2026-04-15--edge_predictor_spec_v1_to_v1_3.md`（規格四輪演化完整記錄）
  - **分工（Stage 0 Phase A COMPLETE，Phase B + #25 可並行）**：
    - **FA** ✅ spec v1.3 GREEN（commit `9141e08`）→ v1.4 reality-alignment（commit `1366054`）
    - **PA** (#25 / #63) → SQL migration V017 ✅（commit `1366054`）· Parquet ETL 擴展 ✅：`load_training_data()` 讀 `learning.decision_features` + JSONB→17 列矩陣 + `EDGE_P3_FEATURE_NAMES` 順序凍結 + `export_decision_features_parquet()` reproducibility 逃生艙 + 4 新測試（monkeypatch PG，無外部依賴）· Label backfill + stale alerter 住在 `edge_label_backfill.py`（single source of truth，不重複實現）
    - **ML-MIT** (#26) → quantile LGBM + CQR + CPCV + isotonic calibration + 離線 pinball loss / decile lift（blocked by #25 ETL）
    - **AI-E** (#27) → **Phase A COMPLETE** ✅（commits `8c1f234` A1-A4 + `3753ede` A5 + `a23b268` A6）：Rust `edge_predictor/` 模組骨架 + `gate.rs` pure function + `IntentProcessor` 整合 + `feature_builder.rs` 13/17 features + `to_jsonb` + `PipelineCommand::{SetEdgePredictorShadow, DisableEdgePredictorAll, EmitShadowFill}` IPC
    - **AI-E Phase B** (#27 後半)：
      - ✅ **#1 Bootstrap wire** — main.rs 構造 `PerEnginePredictors` → 三引擎 Deps + `set_edge_predictor_store` 同步 IntentProcessor + debug_assert 防雙注入（commits `c9416d0` + `0fcf449`）
      - ✅ **#2 Backend 選型 audit** — spec §7.1 決策確認 tract-first / ort-fallback + Stage 2 precision-fail 切換 runbook（`docs/audits/2026-04-15--edge_predictor_backend_selection.md`，commit `3dd845c`）
      - ⬜ **#3 Bootstrap-time model loader** — 掃 `settings/models/<engine>/<strategy>.onnx` 載入至 `EdgePredictorStore` 槽（blocked by ML-MIT Stage 2 首 ONNX export）
      - ⬜ **#4 RNG seeding** — `seed_for_engine(PipelineKind) → StdRng`（僅 ε-greedy 運行時相關）
      - ✅ **#5 main.rs wire pipeline_cmd_tx → IntentProcessor** — `EventConsumerDeps.pipeline_cmd_tx` 新欄位 + `TickPipeline::set_shadow_fill_tx` wrapper + 三引擎 (paper/demo/live) 注入 tx clone；IPC `EmitShadowFill` 脫離 fail-soft 丟棄分支，可真實下發 Python consumer（Step 7c 前置）
    - **AI-E Step 7 餘項**（IPC 全套，非 blocking，可獨立前推）：
      - ✅ **Step 7a** `DecisionFeatureSnapshot` — Option B (Rust-direct writer + passthrough IPC)（commit `d73addb`）：`FEATURE_NAMES_V1`+schema/definition hash OnceLock · `DecisionFeatureMsg` struct · `decision_feature_writer.rs` async drain+dedup+DB-RUN-6 reject+`ON CONFLICT DO NOTHING` · `PipelineCommand::DecisionFeatureSnapshot` · `TickPipeline::set_decision_feature_tx` 傳 IntentProcessor+handler · `emit_decision_feature_snapshot()` 於 `evaluate_predictor_gate` 頂端發射（先於 `use_edge_predictor` 短路，Stage 0 即採集） · `spawn_db_writers` 4→5 tuple · 3 `EventConsumerDeps` sites 注入 · lib 1264→1285（+21：6 hash 決定性/6 writer/3 handler 穿透/4 emission）
      - ⬜ **Step 7b** `ReloadEdgePredictor{engine, strategy, path}` IPC + Python route（資料面，沿用 `ReloadRiskConfig` 授權）
      - ⬜ **Step 7c** `EmitShadowFill` Python consumer → `learning.decision_shadow_fills`（DB CHECK `engine_mode='paper'`）
      - ✅ **Step 7d** `write_toml_atomic_fsynced()` helper + `test_write_toml_atomic_fsynced_survives_sigkill`（T23 CC #13）：helper 本體 pre-existing（`config/store.rs:261-291`，tmp fsync → rename → 父目錄 fsync），本 step 補齊耐久性證明 — `current_exe()` 自我 spawn + env-var 閘控 child 分支（寫 TOML + 觸發 marker → idle loop），parent 等 marker → `Child::kill()` (SIGKILL unix) → `wait()` → 讀檔驗 `use_edge_predictor=false`/`shadow_mode=false` 皆落盤 + 驗 `.toml.tmp` 伴隨檔 rename 後消失。`#[cfg(unix)]` 閘控（Windows 無 SIGKILL 語義，部署目標 linux+macOS 皆 unix）。lib 1285→1286（+1 T23）
      - ⬜ **Step 7e** `DisableEdgePredictorAll` 兩階段 commit（U4）+ V014 `observability.engine_events` audit row
      - ⬜ **Step 7f** `GET /api/v1/engine/capabilities` endpoint
    - **CC** (#28) → 13 項必查（v1.3 CC clist）+ T1-T22 regression（`edge_predictor_tests.rs` 0/22 已寫；blocked by Stage 2 artifact for T2/T7/T18）
  - **安全門檻**（不可違背）：Shadow ≥14d（#29）· pinball loss 對比常數模型 >10% 才 promote · Feature freeze time = entry 瞬間 · Per-strategy 獨立模型 · 推理失敗 fail-closed → 回退現有 shrinkage · 不觸 LinUCB · 兩階段提交防 half-enabled · macOS CI `aarch64-apple-darwin`（M1/M2/M3/M4 → M5 Ultra/Max 部署目標，見 memory `project_mac_deployment_target.md`）
  - **Stage 0 收尾前 housekeeping**（Round-4 YELLOW-nit，非阻塞）：§7.1 加 ort macOS dylib bundling 提醒 ✅（已入 audit）· CC #13 加 strace Linux-only 註記
  - **狀態**：🟢 Stage 0 + Phase A COMPLETE · Phase B 3/5 完成（#1 bootstrap ✅ + #2 backend 選型 ✅ + #5 pipeline_cmd_tx wire ✅）· PA `parquet_etl.py` 擴展 ✅（#63 `load_training_data` + `EDGE_P3_FEATURE_NAMES` 凍結 + DuckDB export 逃生艙）· **Step 7a `DecisionFeatureSnapshot` ✅ (commit `d73addb`)** · **Step 7d `write_toml_atomic_fsynced` T23 SIGKILL 回歸 ✅** · Step 7 IPC 餘 4 條（7b/7c/7e/7f）可獨立前推 · Stage 2+ 現唯一 blocker = ML-MIT 首 ONNX artifact 訓練
  - **頭號瓶頸**：ML-MIT #26 — 跑 quantile LGBM + CQR + CPCV + isotonic 產出首個 per-strategy ONNX（unblock AI-E #3 model loader + CC T2/T7/T18 + Stage 3 Shadow mode）
  - **次要瓶頸**：AI-E Step 7b/7c/7e/7f 進度為 0，但不 blocked — 可獨立拆分為 4 個獨立 session 工作項

### Phase 6 擴展

- [ ] **ORPHAN-ADOPT-1 Phase 2** — 真正 Adopt 路徑
  - 前置：Strategist/Guardian AI agent 在線 ✅ + StopManager adopt 接口 + 合成 StrategyId 規約
  - 實作：Stage B2/B3 策略信號匹配 → 合成 `StrategyId` → 原子三件事（注入 `position_map` + 綁 hard/trailing stop + 寫 `ORPHAN_ADOPTED` audit）→ 任一失敗降級 Close
  - Phase 1 已預留 `OrphanDecision::Adopt` enum variant + `OrphanStage::SoftAdoptEligible` 分支，Phase 2 改 dispatch 即可

### AI Agent 全 5 鏈路

- [ ] **G-1 / R-06 全 5 agent**（W25+）— 當前 Conductor 仍 stub，其他 4 agent 已 real（R-06-v2 ✅）
- [ ] **FIX-01** H1-H5 AI Agent 接入（= R-06 完整）
- [ ] **FIX-02** Decision Lease Rust 接入（與 FIX-01 一起）
- [ ] **FIX-12** CSP nonce 遷移（長期）
- [ ] **FUP-8 Phase 2** OrderIntent 加 edge/funding_rate/basis/regime 欄位（與 G-1 Strategist 串線同步）
  - **Paper sentinel 根治 ✅**（2026-04-15）：`IntentResult` 加 `approved_qty: f64` 字段，`process()` 在成功路徑暴露 Kelly+P1 sizing 後的 `final_qty`；`on_tick.rs:721` 改傳 `result.approved_qty` 給 `persist_intent`，paper 的 `submitted_qty` 現在記錄真實 sized qty（非 1e9 sentinel）。既有 sentinel guard 降為安全網（IPC 路徑 + 未來新 caller 防呆）。+2 測試 `test_fup8_phase2_approved_qty_{exposed_on_success,zero_on_rejection}`。
  - **Sentinel 的使用場景**：5 策略 `default_qty/DEFAULT_QTY_PER_GRID = 1e9`（`grid_trading.rs:172`, `funding_arb.rs:62`, `bb_*`.rs, `ma_crossover.rs`）作為「請幫我 size」信號 — 此設計本身不需改動
  - **剩餘工作**：OrderIntent 加 `edge/funding_rate/basis/regime` 欄位（等 G-1 Strategist）

### Phase 5 補強（非阻塞）

- [ ] **5-04~07** DL-1 Symbol Embedding + DL-2 Regime LSTM Shadow
- [ ] **5-08~09** JS+Scorer 整合 + correlation_pairs
- [ ] **5-10~13** E2 + E4 + QC + E5

### EDGE P2（架構層，大工程）

- [ ] **EDGE-P2-2** OI + Liquidation 信號源 — 給 bb_breakout 加領先信號（Bybit WS `tickers` OI + `liquidation` stream）
- [ ] **EDGE-P2-3** Maker order 支持 — fee 從 5.5 bps/side → ~1 bps/side（post-only limit order，改 IntentProcessor + order_manager + exchange execution layer，根本性改變盈利方程式）

---

## 🧰 WP Backlog（低優先 · 維護性）

詳見 `docs/audits/2026-04-06--consolidated_remediation_report.md` §10。

### WP-F GUI 殘留

- [ ] WP-F/O-xx / AH-08~11（詳見 §10.1）

### WP-E4 測試覆蓋

- [ ] T-P2-9 PyO3 bridge tests / T-P2-10 panic-path / T-P2-11 並發
- [ ] T-Q3/Q4/Q7/Q8 覆蓋品質
- [ ] T-I1~I4 tarpaulin / CI 門禁 / 文檔
- [ ] WP-E4/T-P1-1 殘餘 event_consumer 完整事件循環整合測試

### WP-E5 大文件

- [ ] tick_pipeline.rs 2117 行 — 留專屬 session

### WP-I 文檔衛生

- [ ] R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

---

## 📦 殘留延後（前 phase，非阻塞）

- [ ] **2-11** actual training（需足夠 trading.fills 累積）
- [ ] **ort crate** activation（首個 ONNX 模型訓練後）
- [ ] **4-06** LinUCB live warm-start deployment（script 已交付，等首次 v1→v2 遷移）
- [ ] **OC-4** MCP PostgreSQL 自然語言查詢
- [ ] **G-6** Edge estimates 重訓（JS 滾動，LG-1 觀察期後重訓）
- [ ] **G-8** cost_gate 可信度評估（依賴 EDGE-P3-1 或 G-6）

### Phase 4-Conditional（觸發後）

- [ ] 4-1 PairsTrading（需 3 月協整）/ 4-2 Beta Hedging / 4-3 Kalman / 4-5 Mac Studio 遷移 / 4-10 Jump detection

---

## 🔍 Gap 排期索引（2026-04-10 審計，10 項全錄）

| Gap | 描述 | 排期週 | 狀態 |
|-----|------|--------|------|
| G-1 | AI Agent 5 stub | W22(R-02) ✅ + W25+(R-06 full) | 🟡 |
| G-2 | FundingArb.on_tick() | W22 | 🟡 進行中（BLOCKED by deploy）|
| G-3 | IPC socket 無認證 | W19 | ✅ |
| G-4 | Cookie secure=False | W24 | ⬜ |
| G-5 | API Rate Limiting | W19 | ✅ |
| G-6 | ML edge 噪音數據 | LG-1 觀察期後 | ⬜ |
| G-7 | ClaudeTeacher disabled | W23 | ⬜ |
| G-8 | cost_gate 可信度低 | EDGE-P3-1 後 | ⬜ |
| G-9 | HMAC dead import | W20 | ✅ |
| G-10 | Calibration.py 骨架 | W23 | ⬜ |

---

## 📚 已完成歸檔索引

- **2026-04-14 Phantom-Heal + Engine Self-Healing + EDGE**：`docs/archive/2026-04-14--completed_todo_w22_phantom_heal.md`（ENGINE-HEAL 4 Fix + FA-PHANTOM-1 修復 + FUP-1/2/3/4/5/6/8 + EDGE-P0/P1/P2-1 + QoL-1/3 + ORPHAN-ADOPT-1 Phase 1 + WP-F UX-07~10 + ZOMBIE-API-SVC + PNL-5/6 + OC-5）
- **2026-04-12 全程序鏈審計**：`docs/archive/2026-04-12--completed_todo_full_program_audit.md`（P0 8/8 + P1 19/19 + P2 Rust 7/7 + PNL-1~4 + QoL-4）
- **W19 + W20 + Phase 6 + 3E-E2 Fix Rounds A-G + 晚間 Audit BLOCKERs**：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`
- **3E-ARCH 三引擎並行**：`docs/archive/2026-04-11--completed_todo_3e_arch.md`（S0-S13 + 10 BLOCKER + 7 MAJOR）
- **Live GUI P0~P6 + DEAD-PY-1/2 + 1C-4 收尾**：`docs/archive/2026-04-10--completed_todo_live_gui_dead_py.md`
- **Phase 5 P0 promotion + WIRE chain**：commits `5d7d673` → `0e848fa` → `638afa3` → `563d54a` → `5e760be`
- **ARCH-RC1 Session 1A → 1C-4 WRAP**：`docs/archive/2026-04-08--arch_rc1_1c_history_archive.md` + `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`
- **Phase 4 (4-00 ~ 4-21 + 4.1)**：`docs/audits/2026-04-07--phase4_final_signoff_audit.md`
- **Session 11 之前**：`docs/archive/2026-04-06--completed_todo_archive_l3_phases.md`
- **Phase 0/1/2/3 + Rust migration**：`docs/archive/2026-04-04--completed_todo_archive_phase0123_rust.md`
- **已知問題清單**：`docs/KNOWN_ISSUES.md`
- **Bybit API 字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`
- **工程日誌（2026-04-14 ENGINE-HEAL）**：`docs/worklogs/2026-04-14--engine_self_healing.md`
- **工程日誌（2026-04-15 EDGE-P3-1 規格四輪演化）**：`docs/worklogs/2026-04-15--edge_predictor_spec_v1_to_v1_3.md`

---

## ⚙️ 工作流程速查

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
角色定義詳見 CLAUDE.md §八
```

**Bybit API 開發必查**：先讀 `docs/references/2026-04-04--bybit_api_reference.md`。

**風控參數修改強制原則**：所有風控/止損/cost-gate/regime 參數必須透過 IPC `patch_risk_config` 單一通道更新。
