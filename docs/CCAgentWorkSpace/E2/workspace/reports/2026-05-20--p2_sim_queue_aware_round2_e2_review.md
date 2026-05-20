# E2 Round 2 Quick Scan — P2-SIM-QUEUE-AWARE-ADJUSTMENT v55

- HEAD (worktree base): `f2c1123c` (origin/main 已 fetch，sibling commit
  `f2c1123c docs(e1-memory): salvage Worktree A round 1 lessons`，docs-only，
  不衝突 scope)
- Date: 2026-05-20
- Reviewer: E2 (Round 2 quick scan after E1 Round 2 fix)
- Round 1 verdict: APPROVE-CONDITIONAL (2 MEDIUM SHOULD-FIX / 4 LOW NTH)
- Round 2 fix scope: 2 MEDIUM only（family-specific anchor disclosure + sample window pinning）

---

## §0 Verdict

**APPROVE → pass to E4**

- 0 CRITICAL / 0 HIGH / 0 MEDIUM 新發現
- 2 Round 1 MEDIUM 真實修復 ✓
- 4 LOW NTH 全保持未動 ✓
- SIM model 核心邏輯 0 改 ✓
- 89/89 pytest PASS（E2 重跑驗證，0.04s）
- backward compat 對舊 invocation 0 破壞
- JSON artifact 新欄位 add-only 不破現有 consumer

---

## §1 5 個 review 維度逐項

### §1.1 MEDIUM-1 真修驗證

**PASS**

| Sub-fix | 預期位置 | 實際位置 | 證據 |
|---|---|---|---|
| 1a 11 行 family-specific 警告 comment 在 `DEFAULT_BASE_REJECTION_RATE` 前 | `phase_1b_queue_adjustment.py` | line 61-70（共 10 行 + comment block 連線 1 行） | 行首 ⚠️ marker，內含 `family-specific empirical anchor` / 適用範圍 / G-AB-01-C90 / PG-AB-01-C15 / PS-AB-01-C10 example 完整 |
| 1b `[DISCLAIMER]` 段在 `print_results` 結尾 | `phase_1b_queue_bias_regression.py:print_results` | line 363-375 | `print("[DISCLAIMER — per E2 review MEDIUM-1, 2026-05-20]")` 明確；內含 anchor cell ID / family / n / lookback / 「不應外推到其他 family」 |
| 1c JSON artifact `anchor_family` + `anchor_disclaimer` | `payload` dict | line 539-547 | `anchor_family: ANCHOR_CELL.family` + `anchor_disclaimer` 完整 6 行英文 disclaimer |
| 1d argparse `--base-rejection` help text 加 family 警告 | `--base-rejection` argparse | line 466-472 | help 內含 `⚠️ family-specific anchor — 結論限 anchor cell 對應 family` |

**所有 4 sub-fix 真實落地**。disclaimer 文本長度足夠（regression CLI 結尾 ~12 行 + JSON 6 行英文）、不可能被忽略 — text length 充足。

**Adversarial probe — disclaimer 是否真足以警告**：
- print_results 結尾 disclaimer 用 `[DISCLAIMER]` 顯著標記，配 `===` 分隔線（line 361, 374），不會被誤讀為一般 verdict 輸出
- 用 `print()` 強制 stdout 而非 stderr → 直接進入 caller redirect 的 log
- 包含具體 alternative anchor cell ID（PG-AB-01-C15 / PS-AB-01-C10）讓未來 sweep 階段有 actionable next step
- ✓ 充足

### §1.2 MEDIUM-2 真修驗證

**PASS**

| Sub-fix | 預期位置 | 實際位置 | 證據 |
|---|---|---|---|
| 2a argparse `--sample-end-utc` flag | argparse parser | line 456-461 | help 含 ISO-8601 example + `default = now() (sliding)` + 中文「audit 對齊」說明 |
| 2b `_parse_sample_end_utc` helper 4 種格式 + reject invalid | top-level function | line 428-445 | 處 `None` / `""` / `"now"` / `"NOW"` / `Z`-suffix / tz / naive；invalid 走 `datetime.fromisoformat` raise `ValueError` |
| 2c SQL `WHERE ts > NOW() - interval` 改 Python-side range | `load_v094_attempts` | line 119-167 | Python resolve `window_end / window_start`（line 122-130）+ SQL `WHERE ts >= %s AND ts <= %s`（line 152-153）+ params 顯式注 `window_start, window_end`（line 165-166） |
| 2d JSON artifact 4 欄 `sample_end_utc` / `sample_window_start_utc` / `sample_window_end_utc` / `sample_window_pinned` | `payload` dict | line 549-555 | 4 欄真寫；`sample_window_pinned: sample_end_utc is not None` 正確語意 |
| 2e default `None` = `now()` 向後相容 | `load_v094_attempts` signature | line 97 + line 122-123 | default `None` → `datetime.now(timezone.utc)`；舊 caller 不傳該參數 0 破 |

**所有 5 sub-fix 真實落地**。

**Adversarial probe — `--sample-end-utc default=None` 是否與舊 invocation 100% identical**：
- 舊 SQL: `WHERE ts > NOW() - %s::interval` — PG-side `NOW()` 在 SQL 執行**時**取
- 新 SQL: `WHERE ts >= %s AND ts <= %s` with `window_end = datetime.now(timezone.utc)` — Python-side **call 前** 取
- 差異 1: **ms 級時差**（Python now() 在 SQL roundtrip 前先取，理論差 < 5ms）
  - 對 14d / n=18 sample 影響 0（無 fill 落在這 ms 窗口）
  - 對 future runtime / heavy sample 場景，可能有 1-2 fill drift — 但這正是 fix 改善「audit 重現性」的代價
- 差異 2: **新版多了 `ts <= window_end` 上邊界**
  - 舊版 `ts > NOW() - interval` 只下邊界（隱含上邊界 = 查詢時刻 PG NOW()）
  - 新版顯式 `<= window_end` — 對舊 caller 行為相當於「現在時刻」rounded to Python now() ms
  - 嚴格說新版包含 `ts == window_end` 而舊版不包含 — 但 fill timestamp 精度遠細於 ms，重疊概率 ~0
- 差異 3: **舊版 `>` 嚴格 vs 新版 `>=` 寬鬆**（下邊界）
  - 嚴格說 `ts == window_start` 邊界在新版包含，舊版不包含
  - 對任意 historical fill timestamp 一致性影響 ~0（fill ts 不會剛好等於 Python now() - 14d ms 精度）
- **結論**：行為 **functionally identical**；唯一觀察差異 = JSON artifact 紀錄 window_end_utc vs 實際 SQL `NOW()` 一致（正是 fix 目的），不是「hidden time drift」而是「audit 可重現」

**Adversarial probe — `_parse_sample_end_utc` 邊界**：
- `'now'` / `'NOW'` / `'Now'` 都 lowercase compare `raw.lower() == "now"` → 都 fallback None ✓
- `'Z'` suffix `raw.replace("Z", "+00:00")` → 正確 ISO-8601 ✓
- naive datetime `dt.replace(tzinfo=timezone.utc)` → 假設 UTC（不 system tz）✓
- `'2026-05-20T11:00:00+08:00'` → `.astimezone(timezone.utc)` → UTC 03:00 ✓
- `'not-a-date'` → `datetime.fromisoformat` raise ValueError → argparse 報錯 ✓
- 邊界 `'2026-13-50T99:00:00'` → ValueError ✓（fromisoformat 拒絕無效月日）

### §1.3 Scope 鎖定驗證

**PASS**

#### SIM model 核心邏輯 0 改

驗 `compute_queue_factor` (line 87-133) + `apply_queue_adjustment` (line 136-) 邏輯：
- 公式 `fill_p × (1 - base_rej) × (1 - queue_w × queue_factor)` 100% 保留
- clamp paths `[0, 1]` for `fill_probability_proxy` / `queue_factor` / `base_rejection_rate` 全保留
- fail-closed path（`my_qty <= 0`、`depth_5 <= 0`、`finite check`）100% 保留
- 0 新邏輯加入 / 0 既有邏輯改動

#### 4 LOW NTH 全保持未動

| LOW NTH | 預期位置 | 實際狀態 |
|---|---|---|
| queue depth timing alignment | `phase_1b_tick_loader.py:depth_at_or_before` | 未動 ✓ |
| f-string DSN | `_get_conn()` | line 83-91 未動 ✓ |
| `--sweep-params` hardcode tuple | `find_best_params` defaults | line 383-384 `queue_weights=(0.10, 0.20, 0.40, 0.60, 0.80) base_rejections=(0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80)` 未動 ✓ |
| `_qty_for_diagnostic` O(n) scan | function | line 278-283 未動 ✓ |

#### git diff scope

`git diff --stat HEAD` 顯示 Round 1 既有 modified 文件（3 個：sweep_replay / tick_loader / test_sweep_replay）+ Round 2 修的是 untracked Round 1 新建檔（phase_1b_queue_adjustment.py / phase_1b_queue_bias_regression.py / test_phase_1b_queue_adjustment.py）→ Round 2 修在 untracked file 上，diff stat 不變即 Round 1 既有 modified file 0 觸 ✓。

### §1.4 89/89 PASS 不破

**PASS**

E2 重跑 `python3 -m pytest helper_scripts/calibration/tests/ -q`：
```
89 passed in 0.04s
```

Test count `grep "def test_" tests/` = **89**（與 Round 1 一致）。0 test name 改名 / 0 test 減少。新加 fix 屬非 test code（disclaimer + SQL window resolve + helper function），test 不需改動。

### §1.5 Adversarial — R2 missed issues 找

**0 BLOCKER / 0 HIGH / 0 NEW MEDIUM**

#### Probe A: JSON artifact 新欄位與既有 consumer compatibility

`grep -rn "p2_sim_queue_aware_regression_v55\|queue_bias_regression\|sample_window_pinned\|anchor_disclaimer\|anchor_family"` 結果 **0 外部 consumer**（除本檔自身）。0 外部模塊 import `phase_1b_queue_bias_regression`。

→ 新欄位 add-only，舊 reader（如有 future tool）走 `dict.get(key, default)` pattern 不破。 ✓

#### Probe B: `--sample-end-utc default=None` 時 hidden time drift

詳見 §1.2 第二個 adversarial probe — **functionally identical**，差異全在 ms 級、邊界精度層次，對 historical fill 樣本 0 觀察差異。✓

#### Probe C: backward compat — 既有 invocation 不破

舊 invocation: `python3 phase_1b_queue_bias_regression.py --queue-weight 0.10 --base-rejection 0.70 --json-out X.json`
- 不傳 `--sample-end-utc` → argparse default `None` → `_parse_sample_end_utc(None)` → None → `load_v094_attempts(... sample_end_utc=None)` → fallback `datetime.now(timezone.utc)`
- JSON 多 6 個新欄位（add-only），舊 consumer dict reader 不破
- print_results 多 1 個 `Sample window UTC` + 1 個 `Lookback days` line（line 322-325）+ disclaimer block — stdout 變長但不破任何結構化解析

→ ✓ 真向後相容

#### Probe D: disclaimer 文字是否真足以警告 / 不被忽略

stdout disclaimer block:
```
[DISCLAIMER — per E2 review MEDIUM-1, 2026-05-20]
  本 regression base_rejection=X 是針對 anchor cell `G-AB-01-C90` (family=`grid`)
  以 14d V094 sample n=18 校的 family-specific anchor。
  不應外推到其他 family（phys_lock_giveback / phys_lock_stale_roc_neg ...）；
  非 grid family 需各自用對應 anchor cell（如 PG-AB-01-C15 / PS-AB-01-C10）
  重跑此 regression CLI 校自家 base_rejection 值。
  Sample window 已 pin 至 [start, end]，可 bit-exact 重現。
```

評估：
- `[DISCLAIMER]` 標記在前，配 `===` 分隔線顯著
- 內容含 actionable next step（alternative anchor cell）
- 包含具體 cell ID + family + n + lookback 數字，非泛泛警告
- 出現位置在 verdict 之後 — 讀者剛看完 PASS/FAIL 立即看到適用範圍
- ✓ 足以警告，不會被忽略

#### Probe E: source comment 11 行 family 警告位置

位於 `DEFAULT_BASE_REJECTION_RATE = 0.0` declaration **之前**（line 61-70），讀者修改 default 前必看到 — 防止未來開發者 hardcode 0.70 進 source 的關鍵防線。✓

#### Probe F: race / IPC / 跨語言 / Rust runtime / V### migration

純 Python read-only research tool，不涉 race / IPC / Rust runtime / 新 V### migration / authorization / risk gate。Round 1 已驗的 9 條 OpenClaw 特殊條目仍全 N/A 或 PASS。

#### Probe G: ML training pipeline non-input invariant (§3.11)

```bash
grep -rn "queue_adjusted\|queue_factor\|base_rejection_rate\|sample_end_utc\|anchor_disclaimer" \
  rust/openclaw_engine/src/strategist \
  rust/openclaw_engine/src/learning \
  rust/openclaw_engine/src/ml_training
```
→ 0 命中（同 Round 1）。**§3.11 ML invariant FULL PASS**。

#### Probe H: 跨平台合規

```bash
grep -E '/home/ncyu|/Users/[^/]+/' \
  helper_scripts/calibration/phase_1b_queue_adjustment.py \
  helper_scripts/calibration/phase_1b_queue_bias_regression.py
```
→ 0 命中。✓

#### Probe I: except:pass / 注釋規範

- `grep -E "except\\s*:\\s*pass"` 兩檔 0 命中 ✓
- 所有新加 comment 中文為主（per feedback_chinese_only_comments 2026-05-05）；anchor_disclaimer JSON value 用英文是 E1 §6 honest 註記「便於 downstream tool parse / log search」reasonable 設計決定 ✓

---

## §2 8 條 reviewer checklist

| Item | 狀態 | 證據（Round 2） |
|---|---|---|
| 1. 改動範圍與 PA 方案一致 | ✓ | Round 2 修限 2 MEDIUM；SIM core 0 改；4 LOW NTH 全 unchanged |
| 2. 沒有 except:pass | ✓ | grep 0 命中 |
| 3. 日誌使用 %s 格式 | ✓ | 0 logger.* 調用；f-string 全在 print/stdout（非 log） |
| 4. 新 API 端點有 _require_operator_role() | N/A | 0 API endpoint |
| 5. except HTTPException 在 except Exception 之前 | N/A | 0 HTTPException 用 |
| 6. detail=str(e) → "Internal server error" | N/A | 0 FastAPI 用 |
| 7. asyncio 路由無 blocking threading.Lock | N/A | 0 asyncio/threading 用 |
| 8. 沒有私有屬性穿透（._xxx） | ✓ | grep 0 命中 |

---

## §3 OpenClaw 9 條特殊 checklist（Round 2 增量）

| Item | 狀態 | 證據 |
|---|---|---|
| 3.1 跨平台合規 | ✓ | grep 0 命中 |
| 3.2 注釋規範 中文為主 | ✓ | 11 行 source comment + disclaimer block 中文；JSON value 英文有 reasonable rationale |
| 3.3 Rust unsafe / unwrap | N/A | 0 Rust 改 |
| 3.4 跨語言 IPC | N/A | 0 IPC schema 改 |
| 3.5 Migration Guard A/B/C | N/A | 0 V### migration |
| 3.6 healthcheck 配對 | N/A | 0 新被動等待 TODO |
| 3.7 Singleton / monkey-patch | N/A | 0 新 singleton |
| 3.8 文件大小 800/2000 | ✓ | `phase_1b_queue_adjustment 221 LOC` + `phase_1b_queue_bias_regression 572 LOC`；最大 572 < 800 警告 |
| 3.9 Bybit API | ✓ | 0 REST/WS endpoint call |
| 3.10 P0/P1 leak caller-path grep | N/A | 0 P0/P1 finding |
| 3.11 ML training non-input invariant | ✓ | grep 0 命中 linucb/scorer/quantile/mlde/dl3 |

---

## §4 Multi-session race check 5/5

| Check | Result | 評估 |
|---|---|---|
| 5a 提交前 fetch + sibling commit | `git fetch` HEAD `f2c1123c` docs-only sibling，不衝突 file scope | ✓ |
| 5b sub-agent IMPL DONE 前 status clean | `git status --porcelain helper_scripts/calibration/` 3 M file（unchanged）+ 3 untracked（Round 1+2 同檔）；無外洩 | ✓ |
| 5c sibling WIP 不 revert | 0 動既有 dirty file | ✓ |
| 5d sign-off report path | `2026-05-20--p2_sim_queue_aware_round2_e2_review.md` 唯一 | ✓ |
| 5e review 期間 sibling 推 origin | `f2c1123c` docs-only 不衝突 scope；不需重 review | ✓ |

---

## §5 Findings

### CRITICAL: 0
### HIGH: 0
### MEDIUM (new): 0
### LOW (new): 0

**Round 1 兩 MEDIUM 全部真實修復**。LOW NTH 4 條全保留為 P2/P3 follow-up。

---

## §6 對 E1 Round 2 honest disclosure 評估

| E1 disclose | E2 verdict |
|---|---|
| §3.2.b Python-side resolve window 取代 PG NOW() | ✓ accept — 是 fix 目的本身，不是 hidden risk |
| §6.3 load_v094_attempts signature 5-tuple breaking change | ✓ accept — grep 確認唯一 caller 同檔內 main()；0 外部 import |
| §6.4 anchor_disclaimer JSON value 用英文 | ✓ accept — downstream tool parse / log search 友好的 reasonable trade-off |
| §6.1 未動 SIM model 核心邏輯 | ✓ accept — E2 line-by-line 驗 `compute_queue_factor` / `apply_queue_adjustment` 100% unchanged |
| §6.2 4 LOW NTH 全保留 | ✓ accept — 4 條全 grep 確認未動 |

E1 Round 2 honest disclosure quality **A-grade**。

---

## §7 結論

**APPROVE — pass to E4**

E2 Round 2 quick scan 已驗：
1. MEDIUM-1 全 4 sub-fix 真實落地（source comment + disclaimer block + JSON 2 欄 + argparse help）
2. MEDIUM-2 全 5 sub-fix 真實落地（argparse flag + parse helper 4 格式 + SQL BETWEEN + JSON 4 欄 + default backward compat）
3. SIM model 核心邏輯 0 改
4. 4 LOW NTH 全保留未動
5. 89/89 pytest PASS (E2 重跑驗證 0.04s)
6. 0 新 finding / 0 backward compat 破壞 / 0 JSON consumer 衝突
7. 8 條 + 9 條 + ML invariant + race check 全 PASS

PM 可直接派 E4 regression（per Round 1 §1.8 task #8 list；不需 E1 Round 3）。

---

P2-SIM-QUEUE-AWARE R2 E2 quick scan DONE — verdict: APPROVE
