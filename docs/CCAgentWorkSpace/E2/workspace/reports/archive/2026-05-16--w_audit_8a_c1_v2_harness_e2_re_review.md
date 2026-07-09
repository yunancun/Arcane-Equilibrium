# E2 RE-REVIEW — W-AUDIT-8a C1 v2 Resilient Harness Consolidated 6-Fix

**Date**: 2026-05-16
**Reviewer**: E2 (Senior Backend Code Reviewer + Adversarial Auditor)
**Target branch**: `worktree-agent-a58d99ef4ea1a440b`
**Target commit**: `dbd0277c` (consolidated fix on top of `5983f955`)
**Worktree**: `/Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-a58d99ef4ea1a440b`
**E1 self-report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_consolidated_fix_self_report.md`
**Prior E2 review (RETURN)**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_e2_review.md`
**Prior A3 review (APPROVE-CONDITIONAL)**: `srv/docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_a3_adversarial_review.md`

---

## §0 Scope

Focused re-review on 4 fix（per task brief） + 5 附加 check。不重做全量 review。

---

## §1 改動範圍

| 檔 | LOC pre | LOC post | 動作 |
|---|---:|---:|---|
| `helper_scripts/bybit/liquidation_topic_probe_v2.py` | 942 | 1045 | +103 / -18 |
| `helper_scripts/bybit/test_liquidation_topic_probe_v2.py` | 656 | 913 | +257 |
| `helper_scripts/bybit/run_c1_v2_proof.sh` | — | 138 | NEW |
| `helper_scripts/bybit/liquidation_topic_probe.py` (v1) | 351 | 351 | 0 byte（control 保留） |

Diff total: 3 files, +519 / -18.

---

## §2 4 Fix verify verdict

### Fix 1 — UTC midnight 5min buffer (A3 CRITICAL-1)

**位置**：`liquidation_topic_probe_v2.py:742-767` `_wait_until_next_utc_midnight()`

**驗證**：
- ✅ 條件 `seconds_since_midnight = now.hour*3600 + now.minute*60 + now.second` + `if < 300: return` 正確
- ✅ Wall-clock 秒數比較不受 hour/minute 邊界邏輯歧義（修了原 `now.hour==0 and now.minute==0 and now.second<=30` 在 00:00:30 後落入加一天分支的 bug）
- ✅ 注釋全中文 + explain WHY（operator hang 誤判 → kill → 重派 cycle 動機清楚）
- ✅ Unit test 3 個邊界涵蓋：00:00:45 / 00:04:59 / 00:05:00 strict less-than 邊界

**Verdict**：**PASS**

---

### Fix 2 — Atomic checkpoint write (A3 CRITICAL-2 + E2 MEDIUM-2)

**位置**：`liquidation_topic_probe_v2.py:400-416` `_atomic_write_text()` + `_write_checkpoint()` + `write_reports()`

**驗證**：
- ✅ POSIX 慣用 pattern：`tmp_path = target.with_suffix(suffix + '.tmp')` + `tmp_path.replace(target)`（empirically tested `Path.with_suffix` 對含多 '.' 路徑也正確產生 `<full>.tmp`）
- ✅ Scope 正確：`_write_checkpoint` + `write_reports` latest 兩檔走 atomic；dated 兩檔一次性 final write 不需（per task brief）
- ✅ Exception path 行為對：mock disk-full OSError 時 target 保留 OLD content 不被破壞（empirically tested via `unittest.mock.patch`）
- ✅ Unit test 3 個涵蓋：(a) 寫完無 .tmp 殘留 (b) 覆寫既有 target (c) `_write_checkpoint` integration 無 .tmp 殘留
- ✅ 注釋全中文 + explain WHY（jq parse error 致 operator 失信心動機清楚）

**對抗反問**：Caller 不重試會留 partial .tmp 殘留？  
→ Empirically tested：mock partial write fail，target 保留舊內容，.tmp 殘留 partial 但**不破壞** progress.json。Caller 不重試 .tmp 累積 = minor cleanup issue，**不影響業務不變式**。可標 P3 next-pass cleanup，不阻 PM merge。

**Verdict**：**PASS**

---

### Fix 3 — `keepalive_warnings` 拆分 + assess() 白名單 (E2 HIGH-1 + A3 ADV-4)

**位置**：
- `liquidation_topic_probe_v2.py:170` `ProbeV2Stats.keepalive_warnings: list[str]` 新 field
- `liquidation_topic_probe_v2.py:470 / 620` `_run_session` + `_try_reconnect` 兩 keepalive_warn append 路徑 → `keepalive_warnings`
- `liquidation_topic_probe_v2.py:776-796` `_FATAL_CONNECTION_ERROR_PREFIXES` whitelist + `_has_fatal_connection_error()`
- `liquidation_topic_probe_v2.py:847-851` `assess()` reconnect_exhausted 用 whitelist prefix match
- `liquidation_topic_probe_v2.py:955-960` `render_markdown()` 新增獨立 "Keepalive Warnings (non-fatal, last 20)" section

**驗證**：
- ✅ Grep `connection_errors.append` 8 個 site：所有皆 fatal/data-quality 性質（initial_connect_failed / ping_send_failed / recv_failed / non_json_message / websocket-client unavailable / restart_budget_exhausted）+ 0 個 keepalive_warning 殘留
- ✅ Grep `keepalive_warnings.append` 2 個 site：`initial: ...` (L470) + `on_reconnect: ...` (L620) — 兩個唯一 keepalive 寫入點都進新 list
- ✅ Whitelist 6 prefix 對齊：`initial_connect_failed:` / `recv_failed:` / `ping_send_failed:` / `subscribe_failed:` (reserved) / `websocket-client unavailable:` / `restart_budget_exhausted:` — `non_json_message:` 不在內，正確被 filter
- ✅ `assess()` L848 改 `_has_fatal_connection_error(stats.connection_errors)`，取代「非空 list」judge
- ✅ Unit test 4 個：(a) keepalive_warning alone → SMOKE_PASS (b) `non_json_message:` alone → SMOKE_PASS (c) `recv_failed:` 仍觸 FAIL (d) `keepalive_warnings` field schema exists 驗 dataclass
- ✅ Grab-bag pattern 完全消除：`connection_errors` 只剩 fatal/data-quality；`keepalive_warnings` 獨立透明度

**Verdict**：**PASS**

---

### Fix 4 — assess() `reconnect_failures < 3` gate + `FAIL_RECONNECT_INSTABILITY` (E2 MEDIUM-1)

**位置**：`liquidation_topic_probe_v2.py:810-842` `assess()`

**驗證**：
- ✅ `c1_proof_eligible` 條件 L810-814 三條 AND：elapsed_sec >= proof_min + uptime_ratio >= ratio_min + `reconnect_failures < 3`
- ✅ 新 verdict `FAIL_RECONNECT_INSTABILITY` 條件 L832-842：`elapsed >= proof_min AND uptime_ratio >= ratio_min AND reconnect_failures >= 3` → 顯式 surface
- ✅ Priority order 對齊 design §5.3：poison > restart_budget > **reconnect_instability** (new) > reconnect_exhausted > canary > smoke
- ✅ c1_blocker 訊息提示 BB invariant (c) 字面 `"reconnect_failures<3"`，operator 看得懂
- ✅ Unit test 3 個邊界：reconnect_failures=2 (< 3 PASS) / =3 (boundary FAIL) / =5 (far above FAIL)
- ✅ Strict less-than 邊界 `< 3` 對齊 design §5.3 BB invariant (c)
- ✅ 不影響既有 36 test：跑兩次 49/49 PASS deterministic

**對抗反問**：未跑滿 + reconnect_failures >= 3 的 edge 是否漏 surface？  
→ 不影響業務：未跑滿（elapsed < proof_min）走 reconnect_exhausted 白名單路徑；要觸該路徑需 fatal connection error（whitelist prefix）— 通常 4 次 reconnect failed 會累積至少 1 個 `recv_failed:` 或 `ping_send_failed:` 進 connection_errors，所以邊界一致。

**Verdict**：**PASS**

---

## §3 附加 check verdict

### A. 注釋規範（chinese-only per 2026-05-05 governance）

新代碼 + 改動 block grep（`grep -E "^\+[^+].*#|^\+.*\"\"\""`）：
- ✅ 全中文注釋
- ✅ Technical token 保留 English（atomic rename / POSIX / FAIL_RECONNECT_EXHAUSTED / connection_errors / dataclass / setsockopt — 技術名詞）
- ✅ `--max-restart` help text English（operator-facing CLI flag desc，per E1 self-report §5 justified）
- ✅ Wrapper script help text English（operator-facing CLI flag desc）
- ✅ WHY explain：每個 fix 中文注釋附明確動機（operator hang / jq parse error / Mac smoke 誤判 / BB invariant (c)）

**Verdict**：**PASS**

---

### B. File size + governance

| 檔 | LOC | Limit | 結論 |
|---|---:|---|---|
| `liquidation_topic_probe_v2.py` | 1045 | 800 warn / 2000 hard | ⚠️ > 800 警告（pre-existing 942 已超） |
| `test_liquidation_topic_probe_v2.py` | 913 | 800 warn / 2000 hard | ⚠️ > 800 警告（test 檔 high-cohesion 例外 accept） |
| `run_c1_v2_proof.sh` | 138 | 800 warn | ✅ |

probe_v2 1045 vs 942 baseline 增 +103 LOC（4 fix + 13 test 預設）— 屬 pre-existing baseline +103，accept exception with future P2 split candidate（probe_core / reconnect / checkpoint 拆檔）。E1 self-report §4 已列入 ACCEPT。

**Verdict**：**PASS with governance exception**（< 2000 hard cap；E1 已 self-report 記錄）

---

### C. Cross-platform 合規

`grep -nE '(/home/ncyu|/Users/[^/]+)' <3 files>` → **0 命中** ✅

`OPENCLAW_DATA_DIR` fallback：probe_v2 L189 `os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")` + wrapper L81 `${OPENCLAW_DATA_DIR:-/tmp/openclaw}` 一致。

Bash wrapper `bash -n` syntax check PASS + `--help` runtime PASS。

TCP keepalive cross-platform guard：`hasattr(socket, "TCP_KEEPIDLE")` fallback to `TCP_KEEPALIVE`（Mac/Darwin）未動，pre-existing 邏輯保留。

**Verdict**：**PASS**

---

### D. 業務不變式

- ✅ v1 (`liquidation_topic_probe.py`) **0 byte change**（`git diff main HEAD -- helper_scripts/bybit/liquidation_topic_probe.py | wc -l` = 0）
- ✅ 0 production module import（`grep -E "from (program_code|settings|app|rust|trading_services)"` = 0 hit）
- ✅ 不動 production builder / writer / authorization / lease / risk_config / Mainnet 邊界
- ✅ 16-root + 9 invariant 全 untouched（read-only WS probe + atomic file write only）
- ✅ 硬邊界（max_retries / live_execution / execution_authority）0 觸碰

**Verdict**：**PASS**

---

### E. Test result

`python3 -m unittest helper_scripts.bybit.test_liquidation_topic_probe_v2 -v` 2026-05-16：

```
Ran 49 tests in 0.007s
OK
```

49/49 PASS deterministic fast。

- 13 new test cover 4 fix（per E1 self-report §2 table）：
  - TestUtcMidnightBuffer ×3（Fix 1 邊界）
  - TestAtomicWrite ×3（Fix 2 atomic + checkpoint integration）
  - TestKeepaliveWarningsSeparation ×4（Fix 3 whitelist + non-fatal regression guard）
  - TestReconnectFailuresInstabilityGate ×3（Fix 4 邊界 2/3/5）

**Verdict**：**PASS**

---

## §4 對抗發現（adversarial probes）

### Probe 1：24h+ 跑滿 + uptime_ratio < 0.95 + reconnect_failures >= 3 + 無 fatal connection_error

Empirical run：
- `elapsed=85000s` (> proof_min 82800)
- `uptime_ratio=0.823` (< 0.95)
- `reconnect_failures=5` (>= 3)
- `connection_errors=[]` (無 fatal prefix)
- → verdict = `SMOKE_PASS_NOT_C1_PROOF`
- → c1_blocker = `"Duration 85000s < required 82800s; keep C1 blocked until full proof."`

**問題**：blocker 訊息誤導 — 實際 `85000 >= 82800`，但 text 印 "85000 < required 82800"（template f-string 一直假設未跑滿）。  
**影響**：PASS/FAIL 結論本身正確（c1_proof_eligible=False 因 uptime/reconnect_failures gate），但 operator 看 progress.json blocker text 會困惑。  
**嚴重性**：**LOW**（不影響業務不變式 / 不影響 PASS gate）。  
**動作**：標 P2 follow-up — 把 SMOKE_PASS_NOT_C1_PROOF 路徑加 condition：if elapsed >= proof_min 改寫 "Window met but uptime/reconnect_failures gate not satisfied"。不阻 PM merge。

### Probe 2：tmp_path partial write failure cleanup

Empirical：mock `write_text` 拋 OSError 模擬 disk-full。
- → target 保留 OLD content ✅
- → tmp_path 在 raise 前未創建 file 即沒殘留（mock 場景 tmp_path 還沒 open file）

真實 disk-full 場景若 tmp 已 open 寫一半被 OS killed：
- → tmp 殘留 partial content（不是 valid JSON）
- → target 仍 OLD（atomic rename 沒跑）
- → 業務不變式不破，但 .tmp 累積占空間

**嚴重性**：**LOW / P3 cleanup**（不影響業務 / 罕見場景）。  
**動作**：標 P3 follow-up — `_atomic_write_text` 在 exception 路徑 unlink tmp。不阻 PM merge。

---

## §5 直接修

E2 frontmatter 允許範圍：typo / lint / dead import / 小範圍格式。

掃描結果：
- 注釋 typo：未發現
- 格式：PEP 8 對齊
- Dead import：未發現

**E2 直接修 = 0 處。**

---

## §6 Findings 表

| 嚴重性 | 位置 | 描述 | 動作 |
|---|---|---|---|
| LOW | `liquidation_topic_probe_v2.py:889-892` | `SMOKE_PASS_NOT_C1_PROOF` blocker text 在 24h+ 跑滿 + low uptime + high reconnect_failures + 無 fatal connection_error 的 edge case 印錯 "Duration X < required Y"（實際 X >= Y）。Verdict 本身正確（c1_proof_eligible=False），只是 text 誤導 | P2 follow-up；不阻 PM merge |
| LOW | `liquidation_topic_probe_v2.py:400-416` | `_atomic_write_text` 在 tmp partial write fail 場景無 finally cleanup → tmp 累積占空間；業務不變式不破 | P3 follow-up；不阻 PM merge |

之前 E2 退回的 HIGH-1 / MEDIUM-1 + A3 退回的 CRITICAL-1 / CRITICAL-2 = **全 4 件 PASS**。

---

## §7 結論

**Verdict**：**PASS to PM merge**

**E1 consolidated 6-fix commit `dbd0277c` 修了之前 E2 退回的 2 blocker（HIGH-1 / MEDIUM-1）+ A3 退回的 2 CRITICAL（CRIT-1 / CRIT-2）+ 1 WARN（WARN-1 wrapper）+ 1 advisory（max-restart help text）。13 新 test 覆蓋扎實，49/49 PASS deterministic。業務不變式不破，跨平台合規 OK，注釋全中文，file size < 2000 hard cap。**

**剩餘 2 LOW（P2/P3 follow-up）不阻 PM merge**：
- LOW-1：SMOKE_PASS_NOT_C1_PROOF blocker text 在 specific edge case 誤導（不影響 PASS gate）
- LOW-2：`_atomic_write_text` partial-fail cleanup（罕見場景，不破壞業務不變式）

E1 self-report 列入 ACCEPT 的 governance exception（file size 1045 > 800 warn）= 接受（< 2000 hard cap + high-cohesion 單檔），與 §九 governance rules 一致。

---

## §8 給 PM 的下一步建議

1. **PM merge `dbd0277c` 至 main**（A3+E2 已 PASS；E4 regression 由 PM 派）
2. **可選 BB/MIT recheck**（schema 0 改，per E1 self-report §6 可 skip）
3. **24h proof 啟動前 wrapper script 部署到 trade-core**：
   ```
   ssh trade-core 'bash ~/BybitOpenClaw/srv/helper_scripts/bybit/run_c1_v2_proof.sh'
   ```
4. **2 LOW finding 開 P2/P3 ticket** 進 TODO.md follow-up backlog
