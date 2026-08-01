---
name: performance-profiling
description: E5 agent 主用：效能優化、latency 超 SLA、記憶體/CPU spike、DB 慢查詢排查，及每 Phase/Wave 完成後強制體檢時讀；SLA 閾值唯一正本在此。
allowed-tools: Read, Grep, Glob, Bash
---

# Performance Profiling（效能分析）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：flamegraph / cargo-bloat / py-spy / memray / cProfile / pg_stat_statements 等工具用法通識不在本檔重述；本檔只列本專案的 SLA 正本、硬體預算與判準。

**本檔為 SLA 閾值唯一正本（H0 Gate <1ms / Tick path <0.3ms / IPC round-trip <5ms），他檔引用不重述。**
SLA 來源：CLAUDE.md 硬件 memory + 工程實測 baseline；與真實 runtime 衝突以實測為準。

## 何時觸發

- E5 收到「效能優化」「P95 latency 偏高」「記憶體 / CPU spike」「DB 慢查詢」
- 每個 Phase / Wave 完成或 ≥3 E1 任務後強制
- Tick pipeline / IPC / Bybit REST 延遲 > SLA
- Rust 遷移期 binary size 監控

## 硬體預算（CLAUDE.md project_hardware_constraints）

| 資源 | 上限 | 實際分配 | 留給 engine |
|---|---|---|---|
| RAM | 128GB unified | LLM ~54GB + PG 4-8GB + uvicorn ~2GB | ≤60GB headroom |
| PG buffer | 4-8GB max | shared_buffers + work_mem | 大 query 必分批 |
| NAS via 10GbE | 40TB | 歷史 kline / log archive | I/O 走網路非本地 |
| CPU | M-series | Rust + Python tokio runtime | 不能 over-thread |

## 工具鏈選型（用法靠內建知識）

- **Rust hot path**：flamegraph（`RUSTFLAGS='-C debuginfo=2'` release build）、cargo-bloat（crates + compile-time）、cargo-expand（找 sqlx 過度展開）、cargo audit / deny、criterion bench（`--save-baseline before` / `--baseline before` 對比）
- **Python**：py-spy（sampling，不阻塞 prod uvicorn）、cProfile（離線）、memray（memory）、aiomonitor（live async tasks）
- **PostgreSQL**：pg_stat_statements（mean_exec_time top）、`log_min_duration_statement=100`、pg_stat_activity 鎖等、pg_stat_user_tables seq_scan、`timescaledb_information.chunks`

## 工作流（5 步）

1. **建 baseline** — 改前 `cargo bench --save-baseline before` + py-spy 60s + pg_stat_reset()
2. **改動** — 套用優化
3. **驗證** — `cargo bench --baseline before` + 同 workload 再 60s py-spy + pg_stat_statements diff
4. **回歸測試** — cargo test + pytest 全綠
5. **報告** — 改前/改後 P50 / P95 / P99 + RAM peak + binary size + 結論 PASS/FAIL

## OpenClaw context — 不在本 skill 列具體熱點路徑

具體熱點檔案 / 行數 / 模組分布隨 commit 演進變動。**本 skill 不寫死**避免 sub-agent 引過期路徑。實際熱點必跑 profiler 取真值，從 profile 結果再決定優化目標 — **不從預設熱點清單**。

## 紅旗（直接標 FAIL）

- 任何 P99 > 2× P50（雙峰分佈 = 鎖 / GC / cold cache）
- Rust `unsafe` 區段無 SAFETY 注釋
- Python `await` 內含同步 blocking I/O（`requests.get` / `time.sleep`）
- N+1 query（loop 內 `await conn.fetch`）
- `SELECT *` 在 hot path
- Lock 持有 > 10ms

## Apple Silicon 部署準備

- `cargo build --target aarch64-apple-darwin --release` 必過（CI tuple 必含）
- 不依賴 Linux-only kernel 特性（`epoll` 直呼）
- `psutil` Linux-specific API 加平台守衛
- launchd plist 樣板就緒 vs systemd unit 對等

## 輸出格式

```markdown
# E5 效能分析 — <scope> · <date>

baseline：commit `<sha-before>`
after：commit `<sha-after>`

## 摘要
- P50：X → Y ms（−Z%）
- P99：A → B ms
- RAM peak：M → N MB
- Binary size：S → T MB
- DB query mean：U → V ms

## 改動清單
| 檔 | 動作 | 預期效益 | 實測 |
|---|---|---|---|

## 紅旗發現
（list）

## 建議下一輪
- ...
```
