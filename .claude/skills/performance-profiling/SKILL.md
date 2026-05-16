---
name: performance-profiling
description: Rust + Python + PostgreSQL 三層效能分析；針對 128GB 統一記憶體 / 4-8GB PG 限制 / Apple Silicon 部署目標調校。E5 agent 主用。
allowed-tools: Read, Grep, Glob, Bash
---

# Performance Profiling（效能分析）

> **優先序**：runtime RiskConfig TOML > Rust schema > `TODO.md` active state / runtime evidence > `README.md` stable surfaces > `CLAUDE.md` operating rules > governance docs > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> ⚠️ **SLA 數字 disclaimer**：「H0 Gate < 1ms / Tick path < 0.3ms / IPC < 5ms / 128GB / 4-8GB PG」等硬體 + 性能數字治理依據需 verify（SM-* 治理是否定義 SLA 不確定）；本 skill 引用值為 **CLAUDE.md memory + 工程實測 baseline**，若與真實 runtime 衝突以實測為準。

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

## 三層工具鏈

### Rust（hot path）
```bash
# Flamegraph（CPU sample）
cargo install flamegraph
RUSTFLAGS='-C debuginfo=2' cargo build --release -p openclaw_engine
sudo flamegraph -o engine.svg -- target/release/openclaw_engine

# Binary size
cargo install cargo-bloat
cargo bloat --release -p openclaw_engine --crates -n 30

# Compile-time bloat
cargo bloat --release --time -j 1

# Macro expansion（找 PyO3/sqlx 過度展開）
cargo install cargo-expand
cargo expand -p openclaw_engine <module>

# Audit
cargo audit && cargo deny check

# Bench
cargo bench -p openclaw_engine -- --save-baseline before
# ... change ...
cargo bench -p openclaw_engine -- --baseline before
```

### Python
```bash
# Sampling profiler（不阻塞 prod）
pip install py-spy
sudo py-spy record -o flame.svg --pid <uvicorn-pid> --duration 60

# Top 即時
sudo py-spy top --pid <uvicorn-pid>

# cProfile（測試/離線）
python -m cProfile -o out.prof script.py
python -m pstats out.prof  # interactive

# Memory
pip install memray
memray run -o trace.bin script.py
memray flamegraph trace.bin

# Async-specific
pip install aiomonitor       # live tasks list
```

### PostgreSQL
```sql
-- 啟用 pg_stat_statements 後
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC LIMIT 20;

-- 慢 query
ALTER SYSTEM SET log_min_duration_statement = 100;  -- ms
SELECT pg_reload_conf();

-- 鎖等
SELECT * FROM pg_stat_activity WHERE wait_event_type IS NOT NULL;

-- Index 使用率
SELECT schemaname, relname, idx_scan, seq_scan
FROM pg_stat_user_tables ORDER BY seq_scan DESC LIMIT 20;

-- TimescaleDB hypertable chunks
SELECT * FROM timescaledb_information.chunks
WHERE hypertable_name = 'fills' ORDER BY range_end DESC LIMIT 10;
```

## 工作流（5 步）

1. **建 baseline** — 改前 `cargo bench --save-baseline before` + py-spy 60s + pg_stat_reset()
2. **改動** — 套用優化
3. **驗證** — `cargo bench --baseline before`（比對）+ 同 workload 再 60s py-spy + pg_stat_statements diff
4. **回歸測試** — cargo test + pytest 全綠
5. **報告** — 改前/改後 P50 / P95 / P99 + RAM peak + binary size + 結論 PASS/FAIL

## OpenClaw context — 不在本 skill 列具體熱點路徑

具體熱點檔案 / 行數 / 模組分布隨 commit 演進變動（refactor / split / rename 都會讓 cite 過期）。**本 skill 不寫死**避免 sub-agent 引過期路徑。

實際熱點必跑 profiler 取真值：Rust `flamegraph` + `cargo bloat`；Python `py-spy top` + `memray`；PostgreSQL `pg_stat_statements` + `pg_stat_user_tables`（見 §三層工具鏈段）。從 profile 結果再決定優化目標 — **不從本 skill 預設熱點清單**。

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
