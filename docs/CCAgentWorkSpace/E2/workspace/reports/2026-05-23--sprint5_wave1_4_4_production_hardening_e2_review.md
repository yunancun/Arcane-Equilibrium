---
report: E2 round 1 review — Sprint 5+ Wave 1 §4.4 production hardening (4 items + AC-1b monthly cron)
date: 2026-05-23
author: E2 (Senior Backend Reviewer + Adversarial Auditor)
phase: Sprint 5+ Wave 1 Phase B-5 (between IMPL DONE and E4 regression)
parent_impl: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_4_4_production_hardening_impl.md
parent_design: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_production_hardening_design.md
head_at_review: 612d1383 (per prompt) / d514bd80 (current; sibling 3 commit GUI bump 0 overlap)
verdict: RETURN to E1 — 4 finding (1 HIGH / 3 MEDIUM / 2 LOW) 待修
---

# §1 Executive Summary

## §1.1 Verdict
**RETURN to E1** — IMPL 主要邏輯（Rust ladder amend / 4 unit test / fixture amend / 3 bash script / SCRIPT_INDEX update）整體 sound，PA spec §7.5 E2 必審 3 點全 PASS。但發現 **4 finding（1 HIGH / 3 MEDIUM / 2 LOW）需修**，主要圍繞「跨 wave fixture spec drift」+「sentinel/env var convention drift」+「靜默吞 bash error」。

修復估時：**30-45 min E1**（純 fixture注釋同步 + env var rename + bash error 抑制顯式化；無業務邏輯改動）。

## §1.2 E2 必審 3 點結果（per PA spec §7.5）

| Item | 結果 | 證據 |
|---|---|---|
| **§2.3.1 open_fd_count baseline 3072 校準** | PASS | doc-comment line 346-364 含完整 25 symbol baseline rationale + RLIMIT_NOFILE 8192 headroom 說明；6h Linux PG empirical（PA report §2.1）vmin=1783 vmax=1809 vavg=1788 fall 入新 OK band <3072；unit test test_open_fd_count_baseline_1800_is_ok + test_open_fd_count_3500_warn 2/2 PASS。建議 E4 regression ssh trade-core 跑 `docker exec engine ls /proc/{pid}/fd/ | wc -l` 一次確認 production runtime empirical 對齊（per PA spec §7.5 要求） |
| **§2.3.2 ws_rtt 170ms mainnet warning** | PASS | doc-comment line 340-341 明確含 mainnet warning：「Live mainnet endpoint 物理距離可能不同（hk/sg DC 更近）；mainnet 切換時須重 calibrate ladder；本次 amend 只覆蓋 demo + live_demo 範圍」 |
| **§5.2.2 PGPASSWORD vs PG_PASSWORD 一致性** | PASS | 3 db scripts 全用 `PGPASSWORD` 統一（grep 確認 `helper_scripts/db/health_60s_boundary_verify.sh:65/67/82` + `ac1b_monthly_healthcheck.sh:68/70/104`）；PA spec §5.2.2 原 bug `-e PGPASSWORD="$PG_PASSWORD"` 已修為 `"$PGPASSWORD"` 一致名 |

## §1.3 ladder amend + fixture amend scope 完整度

| 改動 | 結果 |
|---|---|
| open_fd_count classify ladder OK<3072 / WARN 3072-6144 / DEGRADED>6144 | ✓ verified line 365-373 |
| ws_rtt_p50_ms classify ladder OK<170 / WARN 170-300 / DEGRADED>300 | ✓ verified line 349-357 |
| rest_p50/p95/p99 classify 不改（per PA verdict）+ production hardening note 補注釋 | ✓ verified line 234-322 |
| 4 new unit test（1800 OK / 3500 WARN / 163 OK / 250 WARN） | ✓ 4/4 PASS（cargo test --lib --release） |
| 既有 test_classify_ws_rtt_p50_ms_thresholds 對齊新 ladder boundary | ✓ verified line 740-762（169/170/300/301 4 boundary case） |
| 既有 test_api_latency_emitter_critical_sample_propagates fixture ws_rtt 200→350 | ✓ verified line 985 + 977-980 inline rationale |
| PM 提到的「tests/sprint2_track_d_api_latency.rs:629 ws_rtt 200→350」 amend | ✓ verified line 628-633（assert helper 對齊新 ladder） |

## §1.4 3 helper script syntax + idempotency

| Script | bash -n | chmod +x | 對齊 passive_wait 範式 |
|---|---|---|---|
| health_60s_boundary_verify.sh | PASS | ✓ 0755 | ✓ secrets load + container psql + venv-aware |
| health_60s_boundary_verify.sql | n/a | n/a | 3 section LIMIT 20+30+per-metric structure 對齊 spec |
| health_f2_sanitize_monitor.sh | PASS | ✓ 0755 | ✓ DISABLED-BY-DEFAULT + grep-based + cross-platform date (GNU/BSD) |
| ac1b_monthly_healthcheck.sh | PASS | ✓ 0755 | ✓ secrets load + container psql + sentinel mtime touch |

# §2 Findings

## §2.1 HIGH-1: Cross-wave integration test fixture spec drift（注釋/docstring 邏輯描述跟 IMPL ladder 不同步）

**位置**: `rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs:711-712, 742`

**現狀**:
```rust
// Line 711-712（test 上方 docstring）:
///   - 注入 sample = (p50=300 DEGRADED / p95=800 DEGRADED / p99=3000 CRITICAL /
///     ws_p50=200 DEGRADED / ws_p99=2000 CRITICAL / 4xx=80 DEGRADED / 5xx=30
//                ^^^^^^^^^^^^ ↑ 跟新 ladder 不一致 (200 在新 ladder = WARN 非 DEGRADED)
//                            
// Line 742（MockDegradedApiLatencyEmitter fixture）:
ws_rtt_p50_ms: 200,           // DEGRADED (>150)
                              // ^^^^^^^^^^^^^ ↑ 注釋 ladder boundary 仍舊 150
```

**問題**:
- E1 IMPL report §7 提到 「PM 直接 Edit fix: tests/sprint2_track_d_api_latency.rs:629 ws_rtt 200→350 (E1-5 漏改; PM 順手修)」— 但只改 line 629 helper assertion，沒同步 line 711-712 docstring + line 742 fixture 注釋。
- 跑 `cargo test --release --test sprint2_track_d_api_latency` PASS（不會 fail）— 因該 test 對 `ws_rtt_p50_ms` row 個別 `row.state` 不做 DEGRADED check，只 contain check。
- 但 docstring 邏輯描述 + fixture 注釋 ladder 變舊 → 維護成本 + 後續人重看誤導 + E2 retro 範式違反（per E1 memory line 12091 教訓：「跨 wave 並行 sub-agent 改 threshold 必同步改既有 integration test fixture；E2 review 跨 wave conflict 必 grep `assert.*HealthDegraded` vs ladder boundary 對齊」）。

**對抗反問**: 為何 IMPL 報告 PM「順手修」line 629 沒順手改 line 742? E1 應主動 grep `ws_rtt_p50_ms.*200\|ws_rtt_p50_ms.*150` 全 codebase 確認 ladder amend 影響面，不僅憑「PM 提到的那行」順手修。

**修法（30 min）**:
1. Edit `rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs:711-712` docstring：`ws_p50=200 DEGRADED` → `ws_p50=350 DEGRADED`
2. Edit line 742 fixture: `ws_rtt_p50_ms: 200, // DEGRADED (>150)` → `ws_rtt_p50_ms: 350, // DEGRADED (>300 per Sprint 5+ Wave 1 §4.4 amend ladder)`
3. 重跑 `cargo test --release --test sprint2_track_d_api_latency test_sprint2_track_d_api_latency_degraded_band_classify` 確認仍 PASS（fixture 改 350 仍 DEGRADED；對 assertion 0 影響）

## §2.2 MEDIUM-1: Sentinel mtime env var convention drift（`OPENCLAW_HEARTBEAT_DIR` vs codebase 主流 `OPENCLAW_DATA_DIR/cron_heartbeat` 或 `OPENCLAW_CRON_HEARTBEAT_DIR`）

**位置**: `helper_scripts/db/ac1b_monthly_healthcheck.sh:34, 44, 136`

**現狀**:
```bash
# line 34
#   OPENCLAW_HEARTBEAT_DIR   sentinel mtime dir (default: /tmp/openclaw/cron_heartbeat)
# line 44
SENTINEL_DIR="${OPENCLAW_HEARTBEAT_DIR:-/tmp/openclaw/cron_heartbeat}"
# line 136
touch "$SENTINEL_DIR/ac1b_monthly_healthcheck.last_run"
```

**對比 codebase 主流範式（per `checks_cron_heartbeat.py:48`）**:
```python
# OPENCLAW_CRON_HEARTBEAT_DIR override
# fallback: OPENCLAW_DATA_DIR/cron_heartbeat
# fallback: /tmp/openclaw/cron_heartbeat
```

**問題**:
- 默認 path `/tmp/openclaw/cron_heartbeat` 兩邊一致 → 沒 override 場景下 ac1b cron 寫的 sentinel + cron_heartbeat 哨兵讀的 dir **一致**（碰巧）
- 但 operator override（per profile §跨平台「Mac dev 用 OPENCLAW_DATA_DIR=$HOME/.openclaw_runtime」）一邊不另設 override → ac1b 仍 touch `/tmp/openclaw/...`；cron_heartbeat 哨兵讀 `$OPENCLAW_DATA_DIR/cron_heartbeat/...` → **路徑差** → silent dead alert 風險。
- 同時 sentinel 命名 `.last_run` 不對齊 cron_heartbeat module 規範的 `.last_fire`（per `checks_cron_heartbeat.py:6` MODULE_NOTE）— 但 cron_heartbeat module 接受任意 `sentinel_name`，所以不 hard fail，是 convention drift。

**對抗反問**: 「§4.4 hardening 是否承諾將來會加 `[8X]` healthcheck cron 守 monthly ac1b cron fire?」— PA spec §5.2.2 沒承諾，sentinel mtime 是「自願記錄」非「強制哨兵接口」。**但這正是 anti-pattern 起點** — 未來人想加 healthcheck 守 ac1b cron silent-dead 時，convention drift 會卡住。

**修法（10 min）**:
1. 改 env var name `OPENCLAW_HEARTBEAT_DIR` → 對齊 cron_heartbeat module 範式：
   ```bash
   # 優先 OPENCLAW_CRON_HEARTBEAT_DIR (overrideoverride)
   # 否則 OPENCLAW_DATA_DIR/cron_heartbeat
   # 最後 /tmp/openclaw/cron_heartbeat
   SENTINEL_DIR="${OPENCLAW_CRON_HEARTBEAT_DIR:-${OPENCLAW_DATA_DIR:-/tmp/openclaw}/cron_heartbeat}"
   ```
2. 改 sentinel 命名 `.last_run` → `.last_fire`（per checks_cron_heartbeat.py MODULE_NOTE 範式；如未來加 `[8X]` 哨兵直接讀）
3. 同步 docstring `# line 34` 描述

## §2.3 MEDIUM-2: 靜默吞 bash error（`2>/dev/null` 在 health_60s_boundary_verify.sh col 字串轉 int 失敗時）

**位置**: `helper_scripts/db/health_60s_boundary_verify.sh:130, 139`

**現狀**:
```bash
# line 130
elif [[ -n "$samples" && "$samples" -gt 2 ]] 2>/dev/null; then
# line 139
if [[ -z "$row_count" || "$row_count" -lt 25 ]] 2>/dev/null; then
```

**問題**:
- `[[ "$x" -gt N ]]` 對非數字 x（如 `abc` / 空 / NULL）bash 內部 short-circuit 視為 0 仍跑 → silent 報 FAIL 但訊息誤導（驗證：`[[ "abc" -lt 25 ]]` → MATCH，因 bash 把 "abc" 當作 0）
- `2>/dev/null` 吞掉 stderr「: integer expression expected」誤報 — 對齊 E2 8 條 checklist「沒有 except:pass 或靜默吞異常」**bash version 反模式**
- 真實場景：psql 返回 garbage 字串（連接 timeout / SQL syntax error）→ FAIL alert 訊息變誤導「row_count=abc < 25」而非「PG query 結果格式不對」

**對抗反問**: 為何不顯式檢查 `[[ "$x" =~ ^[0-9]+$ ]]` 確認 numeric 才比？

**修法（15 min）**:
```bash
# line 130 重寫
elif [[ "$samples" =~ ^[0-9]+$ ]] && (( samples > 2 )); then
  echo "[FAIL] §2 $domain $metric_name bucket=$col4 samples_per_min=$samples (duplicate emit bug?)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
elif ! [[ "$samples" =~ ^[0-9]+$ ]]; then
  echo "[FAIL] §2 $domain $metric_name samples_per_min='$samples' (non-numeric — PG query garbage?)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi
# line 139 重寫
if [[ -z "$row_count" ]] || ! [[ "$row_count" =~ ^[0-9]+$ ]]; then
  echo "[FAIL] §3 $domain $metric_name row_count='$row_count' (empty or non-numeric)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
elif (( row_count < 25 )); then
  echo "[FAIL] §3 $domain $metric_name 30min row_count=$row_count (expected ~30)"
  FAIL_COUNT=$((FAIL_COUNT + 1))
else
  (( QUIET == 0 )) && echo "[OK] §3 $domain $metric_name row=$row_count avg_delta=${avg_delta}s"
fi
```

## §2.4 MEDIUM-3: Active execution_plan spec ladder 描述舊（doc drift）

**位置**: `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md:144`

**現狀**:
```markdown
| `ws_rtt_p50_ms` | WS 常態 RTT | < 50ms | 50-150ms | > 150ms | —（不含）|
```

**問題**:
- 該 doc 是 active execution_plan（非 archive）
- §4.4 hardening amend ladder 為 OK<170 / WARN 170-300 / DEGRADED>300，**spec 還寫舊 ladder**
- 新 IMPL doc-comment 已 land 完整新 ladder + rationale；新 amendment 沒同步回流 active spec

**對抗反問**: 「為何 IMPL doc-comment 是新的 + execution_plan spec 是舊的？」— spec drift 是 governance 反模式（per 治理 16 原則「Migration Guard A/B/C」精神）

**修法（10 min）**:
1. Edit `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md:144` 加 amendment 行 OR 直接更新 ladder row 並加 `（per Sprint 5+ Wave 1 §4.4 amend 2026-05-23）` 註腳
2. 同時加 open_fd_count amendment note（如 spec 中有 metric_emitter 段）

## §2.5 LOW-1: ac1b crontab usage hint 含絕對路徑 `/home/ncyu/...`

**位置**: `helper_scripts/db/ac1b_monthly_healthcheck.sh:18`

**現狀**:
```bash
#   30 3 1 * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/ac1b_monthly_healthcheck.sh
```

**問題**:
- profile §3.1 跨平台合規：新代碼禁硬編碼 `/home/ncyu` / `/Users/ncyu`
- 但這是 **doc-comment usage hint**（不是 production code path），屬「歷史 worklog / dated snapshot / 政策反例引用不在此限」灰區
- 對齊 PA spec §5.2.3 line 543 已含同形式，operator-specific path

**修法（5 min，可選 / 不阻 merge）**:
```bash
#   30 3 1 * * ${OPENCLAW_BASE_DIR:-/home/ncyu/BybitOpenClaw/srv}/helper_scripts/db/ac1b_monthly_healthcheck.sh
```
或加 inline 注釋說明這是 trade-core operator default path，Mac dev 走 `$OPENCLAW_BASE_DIR` override。

## §2.6 LOW-2: docs/CCAgentWorkSpace/Operator/ 含 mirror PA design report（drift 風險）

**位置**: `docs/CCAgentWorkSpace/Operator/2026-05-23--sprint5_wave1_production_hardening_design.md:68, 79`

**現狀**: Operator 目錄含 PA design report mirror，內容仍寫舊 ladder（demo 數據引用 vs 新 ladder 校準）

**問題**: 此 file 不是 SSOT，PA design 才是；但 mirror 形態如未來人不同步更新會 drift

**修法（可選）**: Operator/ 目錄 mirror 標 deprecated 或加 「per PA report 2026-05-23 §4.4 amended ladder」note

# §3 8 條 reviewer checklist（per E2 profile）

| Item | 狀態 | 備註 |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✓ | PA spec §2-§5 4 items + AC-1b 全 land；不多改不少改 |
| 沒有 except:pass 或靜默吞異常 | ✗ MEDIUM-2 | bash `2>/dev/null` 吞 integer expression error |
| 日誌使用 %s 格式 | n/a | 本 IMPL 無 Python 日誌（Rust tracing::warn 已 land 自 risk_envelope_probe_impl.rs，未改動）|
| 新 API 端點有 _require_operator_role() | n/a | 本 IMPL 無 API 端點改動 |
| except HTTPException: raise 在 except Exception 之前 | n/a | 本 IMPL 無 Python except |
| detail=str(e) 已改為 "Internal server error" | n/a | 本 IMPL 無 detail=str(e) |
| asyncio 路由中沒有 blocking threading.Lock | n/a | 本 IMPL 無 asyncio 路由 |
| 沒有私有屬性穿透（._xxx） | n/a | 本 IMPL 無 Python 私有屬性穿透 |

# §4 OpenClaw 9 條 §3 checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 跨平台 grep | ✗ LOW-1 | ac1b script line 18 doc-comment usage hint 含絕對路徑 `/home/ncyu/...` |
| 注釋規範 | ✓ | bilingual-comment-style: 新代碼注釋中文為主 land；既有 bilingual block 未動 |
| Rust unsafe 零容忍 | ✓ | 本 IMPL 無 unsafe |
| 跨語言 IPC boundary | n/a | 本 IMPL 無 IPC 改動 |
| Migration Guard A/B/C | n/a | 本 IMPL 無 V### migration |
| healthcheck 配對 | ⚠️ MEDIUM-1 | sentinel mtime touch 對齊「自願記錄」；env var convention drift 風險（將來加 `[8X]` 哨兵守 ac1b 時碰壁）|
| Singleton/monkey-patch | ✓ | 本 IMPL 無 mutable singleton |
| 文件大小 | ✓ | metric_emitter/mod.rs 1364 行；api_latency.rs 1059 行（含 fixture amend）；均 <2000 行硬上限 |
| Bybit API 改動 | ✓ | 本 IMPL 無 Bybit API 改動 |
| P0/P1 caller proof | n/a | 本 IMPL 無 P0/P1 finding |
| ML training invariant（close_maker_*）| n/a | 本 IMPL 無 ML training pipeline 改動 |

# §5 §5 multi-session race check（per CLAUDE 操作人格 + multi-session-race-SOP-1 Phase 2）

| Item | 結果 | 證據 |
|---|---|---|
| 5a fetch + sibling window | ✓ | origin/main HEAD d514bd80 → 2h 內 sibling 3 commit 都 GUI/WS test，0 health/ helper_scripts/db/ overlap |
| 5b status clean | ✓ | 4 IMPL files 已 commit 在 HEAD 612d1383；剩 unstaged 屬其他 session WIP（PA/E1/CC autonomy work + cost_gate review）不在本 review scope |
| 5c unknown WIP 禁 revert | ✓ | 0 revert / 0 checkout |
| 5d sign-off path clean | n/a | E2 不 commit |
| 5e sibling overlap | ✓ | sibling 3 commit 0 overlap with review scope |

# §6 對抗反問結果

1. **Q: 「unit test PASS 就證明邏輯對」?**
   - E2: open_fd / ws_rtt 2 新 unit test PASS 證明 ladder 對齊 6h Linux empirical；但 integration test fixture `sprint2_track_d_api_latency.rs:711-712 + :742` 沒同步 amend，docstring 注釋仍寫「ws_p50=200 DEGRADED」誤導 → **HIGH-1**
   - **教訓**：unit test 範圍 ≠ codebase 範圍；ladder amend 必 `grep -r ws_rtt_p50_ms` 確認全 IMPL + tests + spec 同步

2. **Q: 「PA spec §7.5 3 點 E2 必審 → 結論是否完整？」**
   - E2: 3 點全 PASS，但 PA spec 沒涵蓋 fixture spec drift / sentinel env var convention / bash error 抑制 3 條反模式；E2 主動補上

3. **Q: 「sentinel mtime touch 不阻 merge，為何 MEDIUM 而非 LOW?」**
   - E2: 因 convention drift 是 silent-dead alert 起點；未來人要加 healthcheck cron 守 monthly ac1b fire 時，env var 名不一致會 silent-fail。MEDIUM 反映 follow-up debt 風險。

4. **Q: 「mainnet warning 為何 PASS 即可，不要求 ladder 暫 freeze 等 mainnet?」**
   - E2: ladder 已標明 「本次 amend 只覆蓋 demo + live_demo 範圍」；mainnet 切換的 calibrate 是 future sprint 工作；本 hardening 不在範圍。PASS。

5. **Q: 「3 helper script syntax PASS 是否等於 production 跑得通?」**
   - E2: bash -n 只驗 syntax；runtime 邏輯走通要 Linux deploy 跑（per profile 「Mac sandbox 不能代替 Linux empirical」）。 E4 regression 階段 + operator Phase F deploy 後須跑一次驗 `helper_scripts/db/health_60s_boundary_verify.sh` + `ac1b_monthly_healthcheck.sh` 在 Linux 環境 actual PG query 走通。

# §7 退回 E1 修復清單

| # | 嚴重性 | 位置 | 修法 | 估時 |
|---|---|---|---|---|
| 1 | HIGH-1 | `rust/openclaw_engine/tests/sprint2_track_d_api_latency.rs:711-712, 742` | docstring 注釋 `ws_p50=200 DEGRADED` → `ws_p50=350 DEGRADED`；fixture L742 `ws_rtt_p50_ms: 200, // DEGRADED (>150)` → `ws_rtt_p50_ms: 350, // DEGRADED (>300 per Sprint 5+ Wave 1 §4.4 amend)`；重跑 test PASS | 10 min |
| 2 | MEDIUM-1 | `helper_scripts/db/ac1b_monthly_healthcheck.sh:34, 44, 136` | env var `OPENCLAW_HEARTBEAT_DIR` → `OPENCLAW_CRON_HEARTBEAT_DIR` 對齊 checks_cron_heartbeat.py 範式；fallback chain `OPENCLAW_DATA_DIR/cron_heartbeat` → `/tmp/openclaw/cron_heartbeat`；sentinel 命名 `.last_run` → `.last_fire` | 10 min |
| 3 | MEDIUM-2 | `helper_scripts/db/health_60s_boundary_verify.sh:130, 139` | 顯式 `[[ "$x" =~ ^[0-9]+$ ]]` 檢查 numeric；非數字另行 FAIL alert「non-numeric — PG query garbage?」；移除 `2>/dev/null` 抑制 | 15 min |
| 4 | MEDIUM-3 | `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md:144` | 更新 ladder row 為新 amend OR 加 amendment note 「per Sprint 5+ Wave 1 §4.4 amend 2026-05-23 ladder OK<170 / WARN 170-300 / DEGRADED>300」；同時加 open_fd_count amendment note | 10 min |
| 5 | LOW-1（可選） | `helper_scripts/db/ac1b_monthly_healthcheck.sh:18` | doc-comment usage hint 改為 `${OPENCLAW_BASE_DIR:-/home/ncyu/...}` 抽象 OR 加 inline 注釋說明 operator-specific path | 5 min |
| 6 | LOW-2（可選） | `docs/CCAgentWorkSpace/Operator/2026-05-23--sprint5_wave1_production_hardening_design.md` | mirror file 標 deprecated 或加 amendment note | 5 min |

**修復後 E2 round 2 review**: 5-10 min（重 grep + 重跑 4 test）

# §8 結論

**E2 round 1 verdict: RETURN to E1**

- 修復 **HIGH-1 + MEDIUM-1/2/3 共 4 finding**（LOW-1/2 可選，不阻 merge）
- 預計 E1 修復時間：**30-45 min**（無業務邏輯改動，純 fixture/注釋/env var rename/bash error 顯式化）
- 修復完重派 E2 round 2 review → PASS → E4 regression（per PA spec §6.1 Phase B）

**主要正面評**:
- Rust IMPL doc-comment 完整 + rationale 細節豐富（25 symbol baseline / RLIMIT_NOFILE 8192 headroom / mainnet warning）
- 4 new unit test 對齊新 ladder boundary（baseline 1800/3500 + 163/250）
- 3 helper script 對齊 passive_wait_healthcheck.sh 範式 + cross-platform date support
- SCRIPT_INDEX 4 new entries land 完整 + 格式對齊
- PGPASSWORD 一致性（catch PA spec §5.2.2 原 bug `PG_PASSWORD` 已修）

**主要 finding 共性**:
- 「跨 wave / 跨範式」對齊 — 改 ladder 必同步影響所有 fixture+spec；改 sentinel mtime 必對齊 codebase 主流 env var convention
- bash error 抑制反模式 — `2>/dev/null` 是 bash version 的 except:pass，對齊 E2 8 條 checklist 精神升嚴

---

E2 REVIEW DONE: RETURN to E1 (4 finding HIGH+MEDIUM 待修，估 30-45 min) · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-23--sprint5_wave1_4_4_production_hardening_e2_review.md
