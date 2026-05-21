# P2-PHYS-LOCK-72-HEALTHCHECK — phys_lock gate4 distribution observability spec

**日期**：2026-05-21
**作者**：PA
**狀態**：spec land + IMPL drafted；PM dispatch E2 review 後 commit。
**Slot 編號**：`[68]` (canary/healthchecks/ namespace；passive_wait namespace 已用 [68] portfolio_resting，**物理分離 + spec/import label 明標 namespace** 治理)
**Trigger**：FA C6 audit 2026-05-20 verdict — Phase 1b spec §4.3 缺 `phys_lock_gate4_stale_roc_neg` trigger observability SLA / per-reason alert threshold；FA OQ-C6-2 推薦 daily cron standalone healthcheck。

---

## §1 動機

FA 2026-05-20 C6 audit §2 確認 production wiring 完整健全：

```
exit_features/v2.rs:359
  → PhysicalDecision::Lock("phys_lock_gate4_stale_roc_neg")
  → risk_checks.rs:410-413
  → step_6_risk_checks.rs:218-275
  → maker_price.rs:104-108 (close_maker_price_policy)
  → close path 走 maker-first
```

但 spec §4.3 沒有對應的 **per-reason fire 分布觀察 SLA**。production runtime 上，operator 監控只能看 `[66] close_maker_pre_stopout_rate` 整體 stopout 率 / `[63] fallback NULL ladder` 等聚合層，**無法區分**：

- **0-fire-natural**（policy 設定門檻保守，14d 自然 0 fire）
- **0-fire-router-bug**（emit point → maker_price.rs 之間 routing 損壞，policy 邏輯活但 close path 不接通）

兩者治理應對完全不同：
- 0-fire-natural → **不調整**（policy 設計如此，繼續累 sample）
- 0-fire-router-bug → **P1 ticket**（emit alive 但 maker_price.rs 沒 receive，close path 路斷）

本 healthcheck `[68] phys_lock_gate4_distribution` 提供 daily cron 量度，**verdict ladder 直接區分以上兩者**。

---

## §2 SQL + verdict ladder

### 2.1 SQL

```sql
SELECT
    engine_mode,
    CASE
      WHEN exit_reason LIKE '%phys_lock_gate4_giveback%' THEN 'gate4_giveback'
      WHEN exit_reason LIKE '%phys_lock_gate4_stale_roc_neg%' THEN 'gate4_stale_roc_neg'
      ELSE 'other_phys_lock'
    END AS phys_lock_kind,
    COUNT(*)::int AS n,
    COUNT(*) FILTER (WHERE close_maker_attempt = TRUE)::int AS close_maker_attempts,
    COUNT(*) FILTER (
      WHERE close_maker_attempt = TRUE
        AND close_maker_fallback_reason IS NULL
    )::int AS close_maker_fills
FROM trading.fills
WHERE ts > NOW() - (%s::int * INTERVAL '1 second')
  AND (
      exit_reason LIKE 'phys_lock_%%'
      OR details->>'close_maker_eligible_reason' LIKE 'phys_lock_%%'
  )
  AND engine_mode = ANY(%s::text[])
GROUP BY engine_mode, phys_lock_kind
ORDER BY engine_mode, phys_lock_kind;
```

**Schema 真相**（PA 2026-05-21 grep 驗證）：

| 欄位 | 路徑 | 驗證 |
|------|------|------|
| `exit_reason` | `trading.fills` 直 column (V033) | ✅ (PA grep `INSERT INTO trading.fills` 確認) |
| `close_maker_attempt` | `trading.fills` 直 column (V094) | ✅ (passive_wait [70-74] 同 schema 使用) |
| `close_maker_fallback_reason` | `trading.fills` 直 column (V094) | ✅ |
| `details->>'close_maker_eligible_reason'` | `details` JSONB key | ✅ (trading_writer.rs:1399 反射 + passive_wait [72] 使用) |

**PA 對 FA C6 SQL 草案的修正**：FA prompt 給出 `AVG(COALESCE((details->>'fee_bps')::numeric, 0))` ——`details` JSONB **不寫入** `fee_bps` field（PA grep trading_writer.rs INSERT statement 確認）；`trading.fills` 有 `fee` / `fee_rate` 直 column 但**沒有** `fee_bps`。本 spec **移除 avg_fee_bps 觀察** —— OQ-C6-2 核心是 「prevent natural vs router-bug 混淆」，fee 是 secondary nice-to-have，後續若需要走獨立 healthcheck。

### 2.2 Verdict ladder

**PA 2026-05-21 IMPL refine 修正**（原 FA C6 prompt §2.2 ladder 在 IMPL test
覆蓋階段暴露邏輯 bug — `stale_roc=0 AND giveback>=10 → WARN` 條件會把所有
demo natural sparse 環境誤升 WARN，與 spec §1 「natural sparse 不阻 deploy」
原則矛盾）：

對應每 cell（per engine_mode × phys_lock_kind 組合）：

| Verdict | 條件 | 語義 |
|---------|------|------|
| `INSUFFICIENT_SAMPLE` | `n < insufficient_sample_threshold` (default 5) | natural sparse；不阻 deploy；繼續累 sample |
| `PASS` | `gate4_giveback n >= 5 AND close_maker_attempts > 0` | policy alive + close path 通；**stale_roc 0 fire 視為 natural sparse**（14d window 無能力區分 vs router-bug；不沖淡 PASS） |
| `WARN` (弱訊號) | `gate4_giveback n >= 10 AND close_maker_attempts == 0` | giveback 多但 close path 完全 0 attempts；與 FAIL 對稱訊號（stale_roc 看不到 → giveback path 觀察為 close path 健康代理） |
| `FAIL` (最優先) | `gate4_stale_roc_neg n > 0 AND close_maker_attempts = 0` | policy alive 但 close path 不接通；**P1 ticket** |

**為什麼移除原 FA C6 §2.2 WARN 條件 `stale_roc=0 AND giveback>=10`**：

- `phys_lock_gate4_stale_roc_neg` 的 trigger 條件本身嚴苛（per FA C6 audit
  §2 production wiring — exit_features/v2.rs:359 需 stale ROC neg 雙重條件），
  14d window 自然 0 fire 是預期狀態
- 若按原 WARN 條件，所有 demo / live_demo 環境（giveback 30 + stale_roc
  自然 0 fire）都會升 WARN → 與 spec §1 OQ-C6-2 「prevent natural vs
  router-bug 混淆」訴求**完全矛盾**（natural 被誤判為 router-bug）
- **router 缺口疑似** 的真正訊號 = 「giveback close path 也不通」（即
  stale_roc + giveback 同步看不到 close attempts），這才是 spec §1 真實
  訴求，新 WARN 條件 `giveback n>=10 AND close_attempts=0` 對齊

**為什麼 FAIL 仍保留 stale_roc 條件**：

- FAIL = 「我們 *確實* 看到 stale_roc fire 了（即 emit_features 在 emit），
  但 close path 0 attempts」→ 確定 routing bug
- 這條件可在 14d window 內成立（即使 stale_roc 只 1 fire 也算），與 PASS
  條件對稱獨立

**aggregate verdict**（per engine_mode 或全體）：按 `severity_max` 規則
合併（PASS < INSUFFICIENT < WARN < FAIL），對齊 `_common.severity_max` 慣例。

**整體判定邏輯（cross-cell aggregation；PA refine）**：

```
for each engine_mode in (demo, live_demo):
    rows = fetch cells matching engine_mode
    has_giveback = any row.phys_lock_kind == 'gate4_giveback' AND row.n > 0
    has_stale_roc = any row.phys_lock_kind == 'gate4_stale_roc_neg' AND row.n > 0
    giveback_n = max(row.n for phys_lock_kind == 'gate4_giveback') (default 0)
    giveback_close_attempts_sum = sum(close_attempts WHERE giveback)
    stale_roc_close_attempts_sum = sum(close_attempts WHERE stale_roc_neg)

    # 1. FAIL 最優先：policy alive 但 close path 不通
    if has_stale_roc AND stale_roc_close_attempts_sum == 0:
        verdict = FAIL
    # 2. PASS：giveback alive + close path 通 + n 達 threshold
    #    (stale_roc 0 fire 視 natural sparse 不沖淡)
    elif has_giveback AND giveback_close_attempts_sum > 0
         AND giveback_n >= insufficient_sample_threshold:
        verdict = PASS
    # 3. WARN（弱訊號）：giveback 多但 close path 0 attempts
    elif has_giveback AND giveback_n >= warn_giveback_threshold
         AND giveback_close_attempts_sum == 0:
        verdict = WARN
    # 4. INSUFFICIENT_SAMPLE：natural sparse
    else:
        verdict = INSUFFICIENT_SAMPLE
```

**CLI 覆寫**：`--warn-giveback-threshold N` (default 10) / `--insufficient-sample-threshold N` (default 5)

---

## §3 File 位置 + slot

| 角色 | 路徑 | 行數預估 |
|------|------|---------|
| spec（本檔） | `docs/execution_plan/2026-05-21--p2_phys_lock_72_healthcheck_spec.md` | ~150 |
| IMPL | `helper_scripts/canary/healthchecks/68_phys_lock_gate4_distribution.py` | ~280 |
| test | `helper_scripts/canary/healthchecks/tests/test_68_phys_lock_gate4_distribution.py` | ~170 |
| `__init__.py` entry | `helper_scripts/canary/healthchecks/__init__.py` 補 [68] 入口 + slot edge 註 | +10 |

**Slot decision rationale**（PA 拍板 [68]）：

- canary `[62-67]` 連續占用
- canary `[68][69]` 物理 file system free
- passive_wait `[68]=portfolio_resting` / `[69]=wp03_ou_sigma` namespace 已占；canary `[68]` cross-namespace 號碼會碰
- **PA 評估 5 維度**：
  1. **物理連續性** ✅ best — canary 自然接續
  2. **語義對齊** ✅ — 本 healthcheck = close_maker-first observability family，與 canary `[62-67]` 同主題；放 `[80+]` 反而語義斷裂
  3. **passive_wait [68] = portfolio_resting** vs **canary [68] = phys_lock_gate4** 是**完全不同 domain**（前者 leverage chain semantic / 後者 micro-profit lock trigger distribution），不會誤判（與 `[66]` `[67]` 同模式已 land）
  4. **R2 [66] 範本治理**：`__init__.py` MODULE_NOTE 明標 namespace 邊界 + 每 healthcheck 在 spec/註中標 namespace 已有最佳實踐
  5. **跳到 [80+]** 不會根除問題 — 任何號碼都可能在未來被另一 namespace 占
- **Mitigation**：(a) spec / `__init__.py` 明標 namespace；(b) `check_id="[68]"` payload 帶 `namespace="canary"` field；(c) report file naming `2026-05-21--p2_phys_lock_72_healthcheck_*`（72 取 P2 task number，避混淆 slot）

---

## §4 Acceptance criteria

### 4.1 IMPL acceptance（PA + E1）

| AC | 條件 | 驗證方法 |
|----|------|---------|
| AC-1 | SQL bind `stopout_patterns` style `LIKE ANY()` 或 `LIKE`-or-chain 正確 | unit test SQL string |
| AC-2 | `details->>'close_maker_eligible_reason' LIKE 'phys_lock_%'` 子句正確含 | unit test SQL string |
| AC-3 | `n < 5` cell → `INSUFFICIENT_SAMPLE` | unit test |
| AC-4 | `gate4_giveback n>=5 + close_maker_attempts>0` → cell `PASS` + aggregate `PASS` (stale_roc 0 fire 不沖淡) | unit test |
| AC-5 | `gate4_giveback n>=10 + close_maker_attempts=0` → aggregate `WARN` (router 缺口弱訊號) | unit test |
| AC-6 | `gate4_stale_roc_neg n>0 + close_maker_attempts=0` → aggregate `FAIL` | unit test |
| AC-7 | multi engine_mode (demo + live_demo) 取 `severity_max` | unit test |
| AC-8 | production exit_reason 字串 fixture 真實 match `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`（fnmatch 模擬 LIKE） | unit test |

### 4.2 deploy acceptance（QA T+24h）

- daily cron 04:00 UTC fire 1 次
- 14d window 內 demo + live_demo runtime data 確認 `PASS` 或 `INSUFFICIENT_SAMPLE`（**禁** WARN/FAIL silent acceptance — 任一觸發 → P1 ticket）

### 4.3 反模式（test 必 catch）

- `phys_lock_gate1_*` / `phys_lock_gate2_*` 字串 **不應** match `phys_lock_gate4_giveback` filter（test 用 fnmatch 驗）
- `phys_lock_gate4_*` 第三、第四 variant 若未來新增（如 `phys_lock_gate4_pending_unlock`），CASE WHEN 會 fall through 到 `other_phys_lock` bucket（cells payload 仍 emit `other_phys_lock` cell；test 驗）

---

## §5 cron schedule

**建議**：每日 `04:00 UTC` 跑 1 次（不 install crontab；本 PA spec 只**建議**）。

### 5.1 rationale

- 避 close_maker_first 高峰期 `13:00-22:00 UTC`（per AMD-2026-05-15-02 §5.2 observation）
- 避 passive_wait 4h cycle（`00:00 / 04:00 / 08:00 / 12:00 / 16:00 / 20:00` UTC fire 各 4h aggregate） — `04:00 UTC` 與 passive_wait 同步是**有意設計**（allow operator 在 04:00 + ε secs 跑 ad-hoc 對比 daily snapshot vs 4h aggregate）
- daily 而非 hourly：phys_lock 事件 sparse（per FA C6 14d 內 production 觀察），hourly 等於每小時 0 fire；daily 是 sample accumulation 的合理頻率

### 5.2 cron entry 範本（**不接 cron**；spec 註記留 ops 參考）

```bash
# /etc/cron.d/openclaw-canary-phys-lock-daily（範本 — 不 install）
0 4 * * * ncyu cd /home/ncyu/Projects/TradeBot/srv && \
  python3 helper_scripts/canary/healthchecks/68_phys_lock_gate4_distribution.py \
    --window-secs 1209600 \
    --engine-mode demo,live_demo \
    --write-file /home/ncyu/Projects/TradeBot/srv/_var/run/healthcheck/phys_lock_gate4_distribution.json \
    >> /home/ncyu/Projects/TradeBot/srv/_var/log/healthcheck/phys_lock_gate4_distribution.log 2>&1
```

預設 `--window-secs 1209600` = 14d；可 CLI 覆寫做 7d / 30d sliding window 分析。

### 5.3 alert escalation

| Verdict | Action |
|---------|--------|
| `PASS` | 無 action；continue daily |
| `INSUFFICIENT_SAMPLE` | 無 action；continue daily |
| `WARN` | log INFO + dashboard 黃色 indicator；連續 7d WARN 升 P2 ticket (PM check) |
| `FAIL` | log CRITICAL + dashboard 紅 indicator；**立即** P1 ticket (router 路斷可能影響 close maker-first 整體) |

---

## §6 Risk + 副作用

### 6.1 改動風險評級

**低**：
- 新增 standalone healthcheck（純讀 SQL + Python verdict）
- 不入 production runtime（純 audit-layer）
- 不動 `_common.py`（per task 規範）
- 不動 production code（不動 Rust / risk_checks / maker_price / exit_features）

### 6.2 副作用清單

1. 其他模組是否 import 此 file？❌ 否（新檔，僅 `__init__.py` re-export）
2. 是否動其他測試 mock？❌ 否（新 test 用 existing fake cursor 模式）
3. asyncio/threading 邊界？❌ 否（純 sync psycopg2）
4. API response schema 改動？❌ 否
5. Rust ↔ Python IPC schema？❌ 否

### 6.3 16 根原則合規

| # | 原則 | 影響 | 狀態 |
|---|------|------|------|
| 1 | 單一寫入口 | 純讀 | ✅ 無影響 |
| 2 | 讀寫分離 | 純讀 `trading.fills` + `learning.fills`-adjacent JSONB | ✅ |
| 4 | 策略不繞風控 | 不動 strategy | ✅ |
| 5 | 生存 > 利潤 | 此 healthcheck 是 alpha-orthogonal observability，不阻 trading | ✅ |
| 7 | 學習 ≠ 改寫 Live | 不寫 learning state | ✅ |
| 8 | 交易可解釋 | 強化 explainability（明區分 natural vs router-bug） | ✅ ↑ |
| 14 | 零外部成本可運行 | 純 PG query；無外部 API | ✅ |

**硬邊界**：未觸碰 `execution_state` / `execution_authority` / `live_execution_allowed` / `decision_lease_emitted` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json`。

### 6.4 跨平台兼容

- Python 3.10+ stdlib + psycopg2（已對齊現有 `[62-67]` 慣例）
- Apple Silicon Mac 部署 ready：no hardcoded `/home/ncyu` / `/Users/ncyu`（spec §5.2 cron entry **不接 cron**，僅範本）

---

## §7 Test plan

**範圍**：~8 test cases，覆蓋 §4.1 AC-1..AC-8 + adversarial probe（per task 規範）。

| Test | 對應 AC | 驗證 |
|------|---------|------|
| `test_empty_window_returns_insufficient_sample` | AC-3 | 0 rows fixture → aggregate INSUFFICIENT_SAMPLE |
| `test_pass_with_giveback_and_close_attempts` | AC-4 | `(demo, gate4_giveback, 30, 25, 20)` → PASS |
| `test_insufficient_sample_when_n_below_threshold` | AC-3 | `(demo, gate4_giveback, 3, 0, 0)` → INSUFFICIENT_SAMPLE |
| `test_warn_when_stale_roc_zero_but_giveback_high` | AC-5 | giveback n=20，stale_roc 0 row → WARN |
| `test_fail_when_stale_roc_alive_but_close_path_broken` | AC-6 | gate4_stale_roc_neg n=8 close_attempts=0 → FAIL |
| `test_multi_engine_severity_max` | AC-7 | demo=PASS / live_demo=FAIL → aggregate FAIL |
| `test_production_exit_reason_string_match` | AC-8 | fnmatch fixture 驗 `phys_lock_gate4_giveback` / `_stale_roc_neg` match；非 phys_lock_gate4_* 0 match |
| `test_sql_binds_engine_modes_and_window` | AC-1 + AC-2 | SQL string contains `LIKE 'phys_lock_%'` + `close_maker_eligible_reason` + bind tuple shape |

---

## §8 PA → E2 review 重點 3 點

E2 對本 IMPL 重點審查：

1. **AC-2 + AC-8 SQL semantic — production exit_reason 是 free-text + emit 經 helpers_close_tags strip `risk_close:` prefix**：spec §2.1 SQL 內 `exit_reason LIKE 'phys_lock_%'` 必驗對 production `"phys_lock_gate4_giveback"` 字串真實 match（test_production_exit_reason_string_match）。**反模式風險**：若 emit 後 exit_reason 經未來 helpers_close_tags 改動帶 prefix（如 `"physical:phys_lock_gate4_giveback"`），LIKE 不會 match → silent miss；E2 必 push back 補 regression test 鎖死 prefix 保證 strip。

2. **Verdict ladder 4-cell aggregation 邏輯邊界 case**：spec §2.2 aggregate verdict 邏輯需驗 (a) FAIL 先判優於 WARN（OQ-C6-2 核心）(b) `gate4_stale_roc_neg` 與 `gate4_giveback` 兩 row 同存時的 severity_max 正確（多 cells 不能讓單 cell PASS 沖淡 aggregate FAIL）。E2 必驗 IMPL aggregate function 而非單 cell function。

3. **`details->>'close_maker_eligible_reason' LIKE 'phys_lock_%'` 的 OR-condition**：spec §2.1 SQL 用 `(exit_reason LIKE ... OR details->>'...' LIKE ...)` —— 為什麼**雙條件 OR** 而非單條件：(a) exit_reason 是 close path 完成後寫入的 final reason；(b) details.close_maker_eligible_reason 是 maker_price.rs 寫入的 entry-side eligible reason；兩處都應該有 `phys_lock_*` 痕跡但不一定**同時** present（per close path 邏輯）。 E2 必驗 fixture 涵蓋兩種 row：only exit_reason match / only details match / both match。

---

## §9 PA → PM dispatch hint

- **不 commit**；spec + IMPL + test 同 PR
- **PM dispatch E2 review**：對齊 §8 三點重點
- E2 review PASS 後 PM 派 E4 regression（跑 baseline 88 + 新 ~8 = ~96 tests 確認全 PASS）
- E4 PASS 後 commit；commit hint `feat(healthcheck): [68] phys_lock_gate4_distribution standalone observability (P2-PHYS-LOCK-72-HEALTHCHECK; FA C6 OQ-C6-2 follow-up)`
- **不接 cron** — spec §5.2 只範本；後續 ops install 走 helper_scripts/SCRIPT_INDEX.md 註冊路徑

---

## §10 Sign-off

| 角色 | 狀態 | 日期 |
|------|------|------|
| PA spec + IMPL | LAND | 2026-05-21 |
| E2 review | pending | — |
| E4 regression | pending | — |
| PM commit gate | pending | — |
