---
spec: Sprint 5+ Wave 1 §4.3.2 — AC-7 m3 emitter cold start bench IMPL
date: 2026-05-23
author: E1
parent_spec: docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_2_ac7_m3_cold_start_bench.md
parent_pa_design: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_m3_follow_up_design.md §2
ssot_source: docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md §AC-7 line 841
risk_grade: 低
status: IMPL-DONE-AWAIT-E2
---

# §1 任務摘要

per PA spec §2 + §6.1 IMPL `MetricEmitterScheduler::new + run` first tick cold
start bench；目標 wall-clock < 50ms / 100 iter p99 為 hard assert。

SSOT 校正（per PA push back）：本 item ≠ Sprint 1B cross-language fixture
（commit `9cf0fe82` 5/5 已 FULL PASS）；真正 AC-7 = Sprint 2 m3 emitter scheduler
cold start budget。

範式選擇：對齊既有 `benches/hot_path_baseline.rs` +
`benches/intent_processor_exposure.rs` plain `fn main()` + 手動 `Instant` 計時，
**0 criterion dev-dep**（per PA spec §3 AC-3）。注意 operator prompt 提到
`criterion framework` 與 PA spec §2 line 26-29 衝突；以 PA spec 為準（spec line
26：「0 criterion dev-dep」明示）。

# §2 修改清單

| 檔案 | 動作 | LOC（新增）| 範疇 |
|---|---|---|---|
| `rust/openclaw_engine/benches/m3_emitter_cold_start.rs` | 新檔 | 252 | bench fixture |
| `rust/openclaw_engine/Cargo.toml` | edit | +8 | `[[bench]]` entry |

LOC 252（含 MODULE_NOTE + 7 段中文 rationale 注釋 + assertion comment block）；
比 PA spec §5 估算 ~155 LOC 多 ~97 LOC，差異全來自中文 rationale 注釋（per
`feedback_chinese_only_comments`：注釋默認中文，解釋 why）。淨 code LOC（剝除
注釋）約 140 行，落在 spec ±10 LOC 範圍。

無既有檔 production code 改動。

# §3 關鍵設計決策

## §3.1 EngineModeProvider 簽名修正

PA spec §6.2 範本 line 198 `Arc::new(|| "paper")` 會 compile fail（返
`&'static str` 不對齊 `EngineModeProvider = Arc<dyn Fn() -> String + Send + Sync>`）。
IMPL 端改為 `Arc::new(|| "paper".to_string())`。已在 bench 注釋
（line 247-253）標註該 type 約束。

## §3.2 MockEmitter 對齊 6 domain

per PA spec §2.3：6 個 emitter 對應 production 6 domain
（EngineRuntime / PipelineThroughput / DatabasePool / ApiLatency /
StrategyQuality / RiskEnvelope）；每個 emitter `sample_interval_sec()=1`
+ `sample()` 返 1 個 MockSample（unit struct）。

為什麼 `interval_sec=1` 而非 production 30s：`tokio::time::interval` 預設
MissedTickBehavior::Delay 下首次 tick 立即 fire；interval=1s 在 cold start
scenario 與 30/60/300s 等價（都只測首次 tick），且避「interval=0」debug_assert
失敗（tokio 0.1+ 規約）。

## §3.3 NotifyOnceWriter 走 notify_one()

per PA spec §7 重點 2：任一 emitter 首 row 寫入即 wake main loop；
`notify_one()` 給單一 waiter，多次呼叫只記 ≤1 wake permit，正好對齊
「任一 emitter 首 row 即達標」語意。

## §3.4 固定 tokio worker_threads=2

per PA spec §7 重點 3 + §2.2 量測語意：跨平台一致避免 default 全核差異
（Mac aarch64 / Linux x86_64 thread pool 大小依機器 CPU）污染量測；2
thread 足以承載 main loop + 6 emitter spawn task。

## §3.5 percentile p99 assert 而非 max

per PA spec §6.2 line 219 對齊；max 易受系統 GC / kernel jitter 單次 spike
干擾，p99 對 100 iter 是更穩 SLO 邊界。

# §4 cargo bench 結果（Mac aarch64）

## §4.1 Compile check

```
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
cargo bench --bench m3_emitter_cold_start --no-run
```

結果：`Finished bench profile [optimized] target(s) in 28.64s`
+ `Executable benches/m3_emitter_cold_start.rs (...)` — 編譯成功，0 error。

3 warnings 全是 pre-existing crate-wide warnings
（`risk_envelope_probe_impl.rs::MIN_PAIRWISE_SAMPLES` 等），與本 bench 無關。

## §4.2 實測（Mac aarch64 / Darwin 25.5.0）

```
m3_emitter_cold_start iters=100 \
  mean_ms=0 p50_ms=1 p99_ms=1 max_ms=1 budget_ms=50
```

**AC-7 Mac aarch64：PASS** — p99 1ms << 50ms budget（safety margin 49ms）。

## §4.3 Linux x86_64

per PA spec §3.1：E4 端走 `ssh trade-core "cd ~/TradeBot/srv && source
~/.cargo/env && cargo bench --bench m3_emitter_cold_start 2>&1 | tail -20"`
復跑。E1 不接 Linux runtime 驗證（per `feedback_dev_runtime_split` —
Mac=dev / Linux=runtime）；E4 regression 階段做。

# §5 cargo bench 跑法（FYI）

直接 `cargo bench --bench m3_emitter_cold_start` 會撞 pre-existing
`openclaw-engine` bin compile error（`main_health_emitters.rs:580`
`update_from_pipeline_snapshot` 簽名漂移；by 隔壁 session 改 risk_envelope
probe；參見 `git status` 顯示 `risk_envelope_probe_impl.rs` 在 modified
清單內）。此 error 與本 bench **完全無關**。

跑此 bench 兩條路徑：

1. **僅 compile bench**（最乾淨）：
   ```
   cargo bench --bench m3_emitter_cold_start --no-run
   ```
   接著直接執行：
   ```
   target/release/deps/m3_emitter_cold_start-<hash> --bench
   ```

2. **等隔壁 main_health_emitters.rs 與 risk_envelope_probe_impl.rs 簽名重對齊
   後**：`cargo bench --bench m3_emitter_cold_start` 即一條龍跑完並印報告。

E4 regression 階段建議走路徑 2（Linux runtime 端 main 分支應該已 commit 修
正後乾淨）；若 Linux 也夾在簽名漂移期，走路徑 1。

# §6 PA spec AC 對照

| AC# | 描述 | Mac 結果 | Linux 結果 |
|---|---|---|---|
| AC-1 | bench file 新建 + cargo bench 可跑 | ✅ `--no-run` clean compile | E4 待跑 |
| AC-2 | first tick < 50ms（Mac+Linux 均驗）| ✅ Mac p99=1ms（<<50ms）| E4 待跑 |
| AC-3 | 0 criterion dep 引入 | ✅ bench 0 criterion import | E2 grep 驗 |
| AC-4 | Cargo.toml `[[bench]]` entry 新增 | ✅ line 130-137 | E2 grep 驗 |

# §7 治理對照

## §7.1 16 根原則

| # | 原則 | 觸碰 | 證據 |
|---|---|---|---|
| 1-9 | trading hard rails | ✗ 不觸碰 | bench 0 production code path；走 MockEmitter + NotifyOnceWriter |
| 10 | 認知誠實 | ✓ 對齊 | mock writer/sample 全標 mock；bench output 明標 cold_start 語意；assertion 是 hard fail not 靜默 swallow |
| 14 | 零外部成本可運行 | ✓ 對齊 | 0 dep 新增；既有 async-trait + tokio-util workspace 已有 |

## §7.2 跨平台合規（feedback_cross_platform）

- 不寫 `cfg(target_os = "linux")` 分支
- 不硬編碼 `/home/ncyu` / `/Users/ncyu` 路徑
- 0 platform-specific API（tokio + std::time::Instant + std::sync::Arc 純跨平台）
- 固定 `worker_threads=2` 避免 default 全核差異污染量測

## §7.3 注釋規範（bilingual-comment-style）

- 新檔 MODULE_NOTE block 完整中文（line 4-46）
- 7 段「為什麼 X 而非 Y」rationale 注釋（per skill required: 解釋 why 而非
  what）
- 0 中英對照重複；技術詞（tokio / Notify / Instant / interval）保英文
- assertion 注釋說明 why p99 not max（line 235-241）

## §7.4 硬約束（profile.md）

- 不擴大 PA 給定範圍：僅新建 1 bench file + Cargo.toml 1 entry，0 既有檔
  production code 動
- 不改 hot path 既有 max_retries / live_execution_allowed / execution_authority
  / system_mode
- 不順手「優化」未被要求的代碼
- 不 commit（per profile 完成序列：等 E2 → E4 → PM）

# §8 不確定之處 / 風險評估

## §8.1 跨 iter notify wake permit 殘留風險（已規避）

**risk**：`Arc<tokio::sync::Notify>` 多次 `notify_one()` 累積 wake permit；若
iter 間共享同一 Notify instance，前 iter 殘留 permit 會讓下 iter `notified()`
立即返回 → 量測偏向暖啟動。

**規避**：每 iter `let notify = Arc::new(tokio::sync::Notify::new())` 新建
instance（line 184-186）；不跨 iter share。已在注釋（line 174-178）標註此
設計意圖。

## §8.2 Linux x86_64 跑可能差異

**predict**：per PA spec §3.1 + `feedback_restart_bind_host_default`，Linux
x86_64 tokio scheduler 通常更快（默認 8+ thread pool vs Mac aarch64 ~10
P+E core）。但本 bench 固定 `worker_threads=2`，預期 Mac/Linux 差異 < 2x
（即 Linux p99 ≤ 2ms），仍遠 < 50ms budget。

**fallback**：若 Linux p99 ≥ 50ms（極端 regression），E4 應立即 PUSH BACK
不簽 + 觸發 PA 重審量測對象（懷疑 sqlx 或 sysinfo 真實構造被 leak 入 bench）。

## §8.3 main_health_emitters.rs 簽名漂移

**known**：當前 worktree `risk_envelope_probe_impl.rs` 有 uncommitted 改動，
`main_health_emitters.rs:580` 仍呼舊 4-arg 簽名。`cargo bench --bench
m3_emitter_cold_start --no-run` 不觸碰 bin compile，所以 bench 可獨立跑；
但 `cargo bench` 不加 `--bench` 限定會 compile bin 撞此 error。

**not my scope**：此 error 與本任務無關；隔壁 session 應自完成
risk_envelope probe 簽名一致化或回滾 update_from_pipeline_snapshot 第 5
arg。我未動 main_health_emitters.rs / risk_envelope_probe_impl.rs。

## §8.4 1ms 量測解析度極限

**caveat**：`as_millis()` 整數精度；Mac aarch64 cold start 真實值可能介於
500us~1500us，全 cast 到 1ms。對 `< 50ms` 硬閾值無影響，但若未來需要 sub-ms
SLO（如 PA 重定 < 5ms budget），應改 `as_micros()` 量。Sprint 5 cascade 加
PG writer 後若閾值放寬到 100ms（per spec line 887）此精度更不是問題。

# §9 E2 重點審查 3 條（per PA spec §7）

## §9.1 重點 1 — bench 計時邊界

**check**：
- `t0` 必在 `MetricEmitterScheduler::new` 前（bench line 175）
- `t1` 必在 `notify.notified().await` 後第一行（bench line 226）
- `tokio::spawn(scheduler.run(...))` 返回後立即 `notified().await`
  避 race

**E2 grep verify**：
```
grep -n "let t0 = Instant::now" benches/m3_emitter_cold_start.rs
grep -n "let t1 = Instant::now" benches/m3_emitter_cold_start.rs
grep -n "notify.notified" benches/m3_emitter_cold_start.rs
```
應分別 1 hit + 1 hit + 1 hit 排序為 t0 < notified < t1（line 175 < 226 <
228）。

## §9.2 重點 2 — mock writer 不漏 notify

**check**：
- `notify_one()` 語意對齊「任一 emitter 首 row 即達標」（vs notify_waiters
  錯）
- 6 emitter spawn 後 `interval.tick()` 預設首次立即 fire（tokio default
  MissedTickBehavior::Delay）→ 6 個 emitter 同時呼 sample → 任一 emitter
  寫 row 即觸發 notify

**E2 risk**：若 PA review 認為 `notify_one()` 多次堆 wake permit 有 fairness
風險（即多 iter 之間殘留），請看本 report §8.1 的 per-iter rebuild 規避；
bench line 184 `Arc::new(tokio::sync::Notify::new())` 每 iter 新建證明已
規避。

## §9.3 重點 3 — Mac vs Linux 一致性

**check**：
- `tokio::runtime::Builder` 固定 `worker_threads=2`（bench line 168）
- 不依賴 mpsc channel 排程（NotifyOnceWriter 走 `Arc<Notify>` + `notify_one()`，
  非 mpsc）
- 不寫 `cfg(target_os = "linux")` 分支

**E4 follow up**：bench Linux runtime 端跑後若 p99 ≥ 50ms，立即 PUSH BACK
觸發 PA 重審；正常預期 Linux p99 ≤ Mac p99（Linux x86_64 thread spawn 通常
更快）。

# §10 Operator 下一步

1. **E2 reviewer**：跑 §9 3 條重點 grep + 確認 bench 計時邊界 / notify
   semantics / 跨平台一致性
2. **E4 regression**（per PA spec §3.1）：
   - Mac aarch64：`cargo bench --bench m3_emitter_cold_start --no-run` +
     直接執行 binary
   - Linux x86_64：`ssh trade-core "cd ~/TradeBot/srv && source ~/.cargo/env
     && cargo bench --bench m3_emitter_cold_start 2>&1 | tail -20"`
   - 兩平台 bench output 寫入 E4 report；確認 AC-2 Mac+Linux 雙平台 PASS
3. **PM 統一 commit + push**（per E1 完成序列：等 E2 + E4 + QA → PM）：
   - 建議 commit message subject：
     `feat(sprint5-wave1-ac7): m3 emitter scheduler cold start bench fixture`
   - body 帶 SSOT 校正說明 + Mac p99 結果 + PA spec link
   - 注意：不要 batch 把 `risk_envelope_probe_impl.rs` 等隔壁 session 改動
     一併 commit（per `feedback_git_commit_only_for_metadoc`：`git commit
     --only <paths>` 隔絕 multi-session race）

# §11 完成回報（4 條）

1. **bench file LOC + criterion fixture 設計**：252 LOC（含 MODULE_NOTE +
   7 段中文 rationale + assertion comment）；無 criterion，走 plain
   `fn main()` + 手動 `Instant` + harness=false，對齊既有 hot_path_baseline.rs
   + intent_processor_exposure.rs 範式；MockEmitter（6 個對應 6 domain）+
   NotifyOnceWriter（任一 row 寫入 notify_one wake）+ tokio
   worker_threads=2 固定避平台差異
2. **cargo bench 結果（Mac aarch64）**：iters=100 / mean=0ms / p50=1ms /
   p99=1ms / max=1ms / budget=50ms → AC-7 Mac PASS（49ms safety margin）。
   Linux x86_64 待 E4 復跑
3. **Cargo.toml [[bench]] entry 新增**：line 130-137 加 `[[bench]] name =
   "m3_emitter_cold_start" harness = false` + 中文 rationale 注釋對齊既有 2
   個 bench entry 範式
4. **E2 重點 3 條**：
   - (a) 計時邊界 t0/t1 排序 + notified().await race-free check（§9.1）
   - (b) notify_one() vs notify_waiters() 語意 + per-iter Notify rebuild
     規避 wake permit 跨 iter 殘留（§9.2）
   - (c) 跨平台一致性 worker_threads=2 固定 + 0 cfg(target_os) 分支
     + Linux x86_64 E4 復跑（§9.3）

E1 IMPLEMENTATION DONE: 待 E2 審查（report path:
`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_4_3_2_ac7_cold_start_bench_impl.md`）。
