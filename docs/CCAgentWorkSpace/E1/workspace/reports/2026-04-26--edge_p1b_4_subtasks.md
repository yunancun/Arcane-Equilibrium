# EDGE-P1b 7-Dim Threshold Bind · 4 子任務串行 · 2026-04-26 CEST

**Agent**：E1 (Backend Developer)
**派發**：PM Wave 3 EDGE-P1b（per `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--edge_p1b_7dim_bind_rfc.md`）
**狀態**：4 子任務全 done · Linux release 驗證通過 · 待 E2 + E4 review

---

## 1. 任務摘要

EDGE-P1b RFC 的 4 子任務全部串行落地：
- **T1** calibrator 工具（新檔，per-strategy 7 維百分位 + ExitConfig patch JSON envelope）
- **T2** summary 工具（新檔，分布 + cohort fraction + 樣本充足度 tier）
- **T3** IPC method `restore_exit_config_defaults`（risk.rs append + dispatch wiring + 3 unit tests）
- **T4** healthcheck [14] per-strategy 切片升級（passive_wait_healthcheck.py）

驗證：
- Mac local：smoke-test PASS（calibrator + summary）+ AST OK + Python 3.12 import + 合成資料 render markdown 正確
- Linux release：`cargo test --release -p openclaw_engine --lib` baseline 2138 → **2141 passed / 0 failed**（+3 T3 tests）
- Linux 真實 DB：[14] 上線跑出 `PASS this_week=446, last_week=1 (ratio=446.00) — accumulation healthy; per_strategy: grid_trading=282[READY], ma_crossover=146[GROWING], bb_reversion=7[SPARSE], risk_close:fast_track_reduce_half=7[SPARSE], orphan_frozen=4[SPARSE] (READY_frac=63% of this_week)`

---

## 2. 修改清單

| 檔案 | 操作 | 行數 | 說明 |
|---|---|---|---|
| `srv/helper_scripts/research/exit_threshold_calibrator.py` | 新增 | 1067 | T1 calibrator（CLI + SQL + percentile + RFC §2.1 mapping + JSON/markdown/yaml + smoke-test） |
| `srv/helper_scripts/research/exit_features_summary.py` | 新增 | 825 | T2 summary（CLI + dist 分析 + 24h/7d/14d cohort + 3 tier 標籤 + markdown/json + smoke-test） |
| `srv/rust/openclaw_engine/src/ipc_server/handlers/risk.rs` | append | +332 行 → 598 行 | T3 `handle_restore_exit_config_defaults` fn + 3 unit tests |
| `srv/rust/openclaw_engine/src/ipc_server/handlers/mod.rs` | edit | +1 行 | re-export `handle_restore_exit_config_defaults` |
| `srv/rust/openclaw_engine/src/ipc_server/mod.rs` | edit | +11 行 | dispatch_request `"restore_exit_config_defaults" =>` 路由 |
| `srv/helper_scripts/db/passive_wait_healthcheck.py` | edit | +99 行 → 2185 行 | T4 [14] per-strategy GROUP BY + tier 標籤 + READY_frac + fail-soft on query err |

**已超 1200 硬上限警告**：`mod.rs` 1251 行（PRE-EXISTING；本變動只加 11 行的 dispatch 路由，按 §九 + 「不擴張」原則嚴守不順手 split，留 E2 / E5 決定 follow-up split）。

---

## 3. 關鍵 diff

### T1 calibrator — RFC §2.1 mapping 核心

```python
def derive_exit_config_patch(pct_results) -> dict:
    # min_net_floor_bps ← est_net_bps p10 (clamped >= 0)
    p10_net = _get("est_net_bps", "p10")
    if p10_net is not None:
        ipc_wired["min_net_floor_bps"] = max(p10_net, 0.0)

    # min_peak_atr_norm ← peak_pnl_pct p25 / atr_pct p25 (ratio, dim 2/3 合算)
    p25_peak = _get("peak_pnl_pct", "p25"); p25_atr = _get("atr_pct", "p25")
    if p25_peak is not None and p25_atr is not None and p25_atr > 0:
        ipc_wired["min_peak_atr_norm"] = max(p25_peak / p25_atr, 0.0)

    # giveback_base ← giveback_atr_norm p75 (clamped > 0 per validate())
    # giveback_floor ← giveback_atr_norm p25 (clamped > 0 per validate())
    # giveback_slope ← (base − floor) / max(min_peak_atr_norm, 1.0)  (linear)
    # stale_peak_ms ← time_since_peak_ms p75  (TOML-only — no IPC path)
    # min_hold_secs ← entry_age_secs p25
```

### T3 IPC restore — sends 7 baseline values + flags TOML-only fields

```rust
pub(in crate::ipc_server) async fn handle_restore_exit_config_defaults(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<...>,
) -> JsonRpcResponse {
    let baseline = ExitConfig::default();
    // 7 IPC-wired Some(baseline.<field>); non-exit fields all None
    if let Err(e) = tx.send(PipelineCommand::UpdateRiskConfig {
        hard_stop_pct: None, /* ...20 None... */
        exit_missing_edge_fallback_bps: Some(baseline.missing_edge_fallback_bps),
        exit_min_net_floor_bps: Some(baseline.min_net_floor_bps),
        /* ...etc 7 exit fields... */
    }) { ... }
    JsonRpcResponse::success(id, json!({
        "restored": true,
        "fields_restored": ["missing_edge_fallback_bps", ...7],
        "baseline_values": { ... },
        "toml_only_fields_skipped": [
            { "field": "stale_peak_ms", "baseline_value": ..., "reason": "..." },
            { "field": "shadow_enabled", "baseline_value": ..., "reason": "..." },
        ],
    }))
}
```

### T4 healthcheck [14] tail format

```python
slice_parts.append(f"{name}={n}{tier}")  # tier ∈ [READY] [GROWING] [SPARSE]
cohort_frac = ready_count / this_week
per_strategy_tail = (
    "; per_strategy: " + ", ".join(slice_parts)
    + f" (READY_frac={cohort_frac:.0%} of this_week)"
)
```

實測 Linux 1 行 message：
```
PASS [14] exit_features_accumulation_rate this_week=446, last_week=1 (ratio=446.00) — accumulation healthy; per_strategy: grid_trading=282[READY], ma_crossover=146[GROWING], bb_reversion=7[SPARSE], risk_close:fast_track_reduce_half=7[SPARSE], orphan_frozen=4[SPARSE] (READY_frac=63% of this_week)
```

---

## 4. 治理對照

| 文件 / 編號 | 對照狀態 |
|---|---|
| **CLAUDE.md §四 硬邊界** | ExitConfig 不在 5 項 live 門控 list；T1/T3 不觸碰；符合 |
| **CLAUDE.md §七 跨平台** | 路徑全用 `os.environ.get(...)` / `Path(__file__)`；無 `/home/ncyu` / `/Users/ncyu` 硬編碼（grep 已驗）；T1/T2 lazy-import psycopg2 in main fn；符合 |
| **CLAUDE.md §七 雙語注釋** | T1/T2 module docstring 中英對照；T1/T2 fn docstring 中英；T3 fn doc-comment 中英；[14] docstring 中英；新 fn / class / inline 全雙語；符合 |
| **CLAUDE.md §七 被動等待 healthcheck 強制** | T4 [14] 升級為 EDGE-P1b 的 per-strategy 監控（≥200 calibrator threshold）；對應 EDGE-P1b 被動等待 row accumulation 條目；符合 |
| **CLAUDE.md §九 singleton 表** | 0 新 singleton；無需更新表 |
| **CLAUDE.md §九 文件大小** | mod.rs 1251 行 PRE-EXISTING 超過 1200 硬上限；本變動 +11 行（dispatch route），不擴張原則嚴守不 split，**E2 / E5 follow-up 處理**；calibrator 1067 行（800-1200 警告區，整合 SQL+math+render+CLI 為單檔合理）；summary 825 行（剛過 800 警告線） |
| **DOC-01 §5.7 學習 ≠ 改寫 Live** | calibrator 屬 learning plane（read learning.exit_features），bind 寫 RiskConfig 屬 live plane edge；當前 dry-run 預設不寫 IPC，per RFC §2.2 manual-approve 模式 A；符合 |
| **DOC-08 §12 安全不變量 #4 風控降級** | T3 restore 只把 ExitConfig 7 字段恢復為硬編碼 default，不降低風控；符合 |
| **memory `feedback_risk_changes_scoped`** | calibrator 只動 ExitConfig 7 字段，T3 restore 只動同 7 字段；不連帶改其他 RiskConfig 段；符合 |
| **memory `feedback_demo_over_paper_for_edge`** | calibrator 預設 `--engine-mode demo`（CLI 可切 live_demo / paper / live）；符合 |
| **memory `engineering:bilingual-comment-style`** | MODULE_NOTE / docstring / inline 全中英對照；TODO / SAFETY 等 tag 用 English；符合 |

---

## 5. 不確定之處

### 5.1 PA RFC §2.1 vs IPC handler 真實 schema 差異（隱性 push back，但不阻塞）

PA RFC §2.1 把 `stale_peak_ms` 列為 calibrator percentile-derived bind 字段（dim 5 `time_since_peak_ms` p75），但 `ipc_server/handlers/risk.rs:84-99` 只 wire **7 個** `exit_*`：
- `missing_edge_fallback_bps` / `min_net_floor_bps` / `min_hold_secs` / `min_peak_atr_norm` / `giveback_base` / `giveback_slope` / `giveback_floor`

`stale_peak_ms` + `shadow_enabled` **不在 IPC**，需 TOML edit + `reload_risk_config` IPC（per `RiskConfig.exit` schema 9 字段，IPC 子集 7 字段）。

**處理策略（不暫停執行）**：
- PM 派發已說「dry-run 預設 + 不直接 IPC 寫」，所以 calibrator 端只算 patch 不寫，**不阻塞**
- T1 calibrator 在 docstring + JSON envelope 標 `toml_only_fields`（`stale_peak_ms` 在內）讓 operator 看到「此值需 TOML edit」
- T3 restore response 標 `toml_only_fields_skipped: [{stale_peak_ms,...}, {shadow_enabled,...}]` 暴露不對稱
- **後續 follow-up（建議 E2 / PM 評估）**：是否擴 `update_risk_config` IPC 加入 `exit_stale_peak_ms` 欄位以閉合 calibrator → IPC 整鏈；目前阻塞門檻是「stale_peak_ms 之外 6 字段已可 IPC 寫」，partial bind 仍可運作

### 5.2 mod.rs 1251 行已超 1200 硬上限（pre-existing）

本變動只加 11 行 dispatch 路由（`"restore_exit_config_defaults" =>`），mod.rs 已 PRE-EXISTING 超過 §九 1200 硬上限。我嚴守 PA 派發「不擴張」原則 + memory `feedback_risk_changes_scoped`，**沒順手 split** —留 E2 review 或 E5 refactor wave 處理。

### 5.3 Per-strategy bind vs global ExitConfig schema

當前 `RiskConfig.exit` 是**全局**單一 struct（無 per-strategy 段）。T1 calibrator 算出 per-strategy patch，但 IPC 寫只能 global。這個 gap 在 RFC §10 #3 已記錄為 v3 schema follow-up；本輪 calibrator 把 per-strategy patch 都列在 markdown report，operator 可挑「worst-case across strategies」當全局 patch 用。**不在本輪 scope**。

### 5.4 跨平台風險

- **Mac local Python 3.10 缺 `tomllib`**：[14] healthcheck 不依賴 tomllib（用 SQL GROUP BY 不讀 TOML），不受影響；T1/T2 calibrator/summary 不依賴 tomllib
- **PyYAML 為 optional dep**：T1 `--output-format yaml` 缺 PyYAML 時 fall back 至 JSON-style YAML（valid YAML 1.1）+ stderr WARN；不阻塞執行
- **psycopg2 lazy import**：T1/T2 `--smoke-test` 在無 PG 環境可跑（驗 SQL placeholder + 合成資料），與 G2-02 ma_crossover_replay 一致

### 5.5 測試覆蓋判斷

- **T1/T2** smoke-test 在 import-time / SQL 模板 / 合成資料 render 三方面覆蓋；真實 DB 階段 PG-dep 故未在本 sprint 加 pytest（與 ma_crossover_counterfactual_replay.py + bb_breakout_threshold_sweep.py 風格一致）
- **T3** 3 unit tests 覆蓋 (a) happy 路徑 + 通道內容比對 (b) error 路徑（缺 channel）(c) baseline 值與 `ExitConfig::default()` `f64::EPSILON` 比對。整合 ConfigStore.apply_patch 真實 atomic rollback 已由 `event_consumer/tests/exit_config_ipc_tests.rs` 覆蓋（既有測試，T3 不重複 wire）
- **T4** 在 Mac Python 3.12 import + 合成 cursor 驗 + Linux 真實 DB cron run 三層

---

## 6. Operator 下一步

### 立即可做（PM 統一 commit 前）

1. **E2 review**：`E2 → E1 →...→PM` 強制鏈
   - 重點 1：T1 calibrator percentile 計算公式無 lookahead bias —`ts > now() - lookback days AND ts <= now() - embargo days` 確保排除最近 7d（per RFC §8 #1）
   - 重點 2：T1 stratification `strategy_name = ANY(%s)` 精確比對非 prefix（per RFC §8 #2）
   - 重點 3：T1 fail-closed default — 任何 NaN / inf / 0-row strategy 跳過 + INSUFFICIENT 標籤，不 fallback pooled percentile（per RFC §8 #3）
   - 重點 4：T3 happy-path test 通道內容是否 bit-exact 匹配 `ExitConfig::default()` 7 個 fns（已用 `f64::EPSILON` 比對）
   - 重點 5：T4 [14] tier 閾值 200/50 是否與 calibrator min 對齊（已對齊）+ READY_frac 是否符合 operator 直覺
   - 重點 6：mod.rs 1251 行（pre-existing 超 1200 硬上限），本輪不 split 是否 OK 還是 E2 要求順便處理

2. **E4 regression**：跑全 lib `cargo test --release -p openclaw_engine --lib`（已驗 2141 / 0 failed）+ 跑 healthcheck cron（已驗 PASS [14] 真實 DB 輸出）

3. **Mac CC 透過 SSH 已做的驗證**：
   - `cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib` → 2141/0 failed
   - `cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck_cron.sh` → SUMMARY: WARN [11] only（[14] 升級正常輸出）
   - Linux git tree 已 revert clean（scp 暫存後 `git checkout` 三檔）

### 需 operator 親自動手

- **無**：本批次無 high-risk 操作；`--apply` calibrator 仍是 dry-run JSON envelope，無 IPC 寫；E2 / E4 review 通過後 PM 統一 commit + push 可走自動化

### Phase B 後續設計（不在本輪 scope）

1. Per-strategy ExitConfig schema（v3 RiskConfig.exit 擴展）— RFC §10 #3
2. Calibrator → IPC 自動化 wrapper（含 `change_audit_log` + operator approve UI）— RFC §2.2 Phase B
3. `update_risk_config` IPC 加 `exit_stale_peak_ms` + `exit_shadow_enabled`（閉合 calibrator → IPC 整鏈）— 5.1 follow-up

---

## 7. 預期 E2 review 重點（self-audit pre-flagging）

- ✅ percentile 計算 lookahead bias guard（embargo > 0 + lookback > embargo）
- ✅ stratification 精確比對（`strategy_name = ANY(%s)` 不 prefix）
- ✅ fail-closed default（INSUFFICIENT 跳過、不 fallback pooled）
- ✅ ExitConfig validate() invariant clamp（floor > 0 / floor <= base / slope >= 0 / 等）
- ✅ T3 unit test bit-exact 匹配 default fns
- ✅ T4 [14] tier 閾值對齊 calibrator min=200
- ⚠️ mod.rs pre-existing 超 1200 行（本輪不處理，留 E2 / E5 決定）
- ⚠️ stale_peak_ms / shadow_enabled 不在 IPC（已標 toml_only，計 follow-up）
- ⚠️ Per-strategy patches 顯示在 markdown 但 ExitConfig 是全局（per RFC §10 #3 v3 schema follow-up）

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-26--edge_p1b_4_subtasks.md`）**
