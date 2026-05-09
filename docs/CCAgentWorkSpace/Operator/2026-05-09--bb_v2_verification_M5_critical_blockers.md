# BB — 2026-05-09 v2 對抗性核實報告（v1 → v2 跨 34 commits）

**Auditor**：BB（Bybit Broker Compatibility Auditor — Bybit-side advisor）
**Stance**：Bybit 派來的合規顧問。對抗性嚴苛核實 v1 verdict 在 v2 是否真修。
**v1 → v2 baseline**：HEAD `455d796e` → `1bd55689`（34 commits）
**v1 verdict**：✅5 / ⚠3 / ❌7 / 🆕2；技術 97% / 政策 70%
**Methodology**：靜態審計 + Linux PG empirical query + Bybit V5 changelog WebFetch + Linux runtime healthcheck.

---

## §1. Executive Summary

### 三句話結論

1. **L5-1..L5-4 字典 drift**：v1 已 ✅ closed；v2 **無 regression**（字典 v1.2 line 137 / 171 / 686-697 / 1023-1033 仍正確）。**字典 SSOT 100% align**。

2. **funding_arb retire**：v2 **真實前進一步** — `af4942b6` 把 funding_arb 從 4 個 risk_config TOML 全部清乾淨（W-AUDIT-6 IMPL），ADR-0018 + AMD-2026-05-09-02 + SM-05 收口；strategy_params 三端 `active=false` 維持為 retirement authority；Rust grid PostOnly reject callback 同 commit 接 cooldown helper。**但 BUSDT PG 殘倉 12186 條未變**（demo 9327 / live_demo 2859），最後 snapshot 仍 5-6 天前；NEW-1 dust clear runbook **0 進展**。

3. **M5-1 ToS / KYC / 地理禁區 + M5-2 IP whitelist**：❌ **0 修復**。`docs/governance_dev/` 24h 新增 4 條（W-C lease router、SM-05 polling、operator decision audit closure、SPECIFICATION_REGISTER），**0 條觸 KYC / ToS / 地理禁區 / IP whitelist**；`helper_scripts/preflight/` 目錄**仍不存在**。Bybit-side 政策合規度 **70% → 70%**（無進展）。

### Severity verdict

| 維度 | v1 (`72f05aa0`→`7fccad06`) | v2 (`455d796e`→`1bd55689`) | Δ |
|---|---|---|---|
| 技術合規度 | 97% | **97%**（funding_arb risk config 清整 +1pp，但 [56] 健康倒退 -1pp 平手） | 0pp |
| 政策合規度 | 70% | **70%** | 0pp |
| 字典 drift open | 0 | **0** ✅ | 維持 |
| funding_arb risk config drift | open（per_strategy.funding_arb 仍掛在 4 個 TOML） | **closed**（W-AUDIT-6） | -4 ✅ |
| BUSDT PG 殘倉 | open 12186 條 | **open 12186 條** | unchanged |
| Bybit 30d changelog impact | 0 breaking | **0 breaking** ✅ | safe |
| 🆕 [56] LiveDemo healthcheck FAIL | n/a | **FAIL @ 14:33 UTC** | 🆕 regression |

### Verification tally（v2 final）

| Status | Count | Findings |
|---|---:|---|
| ✅ closed (verified 維持) | 6 | L5-1, L5-2, L5-3, L5-4, A5-4 + 🆕 W-AUDIT-6 funding_arb risk config retirement |
| ⚠ partially-closed | 3 | A5-2 retCode 110017 enum 未補；A5-6 fee_drop 仍受 funding_arb 樣本污染；🆕 [56] LiveDemo healthcheck CLAUDE.md §三 寫 PASS 但實測 FAIL |
| ❌ unchanged / open | 7 | M5-1 ToS / M5-2 IP whitelist / A5-1 04-30 新欄位 / A5-3 settleCoin / A5-5 broker_id / A5-7 rate_limit memory drift / A5-9 V3 預檢 |
| 🆕 NEW-ISSUE v2 | 2 | NEW-3 LiveDemo authorization.json missing → snapshot 44min stale → [56] FAIL；NEW-4 §三 [56] 寫 PASS 但實測 FAIL → §三 drift |

---

## §2. v1 ❌ 7 + ⚠ 3 + 🆕 2 對抗性核實逐條

### v1 ❌ 7 → v2

#### M5-1 ToS / KYC / 地理禁區 governance entry — ❌ **unchanged**

**證據**：
```bash
$ grep -rln "kyc|geographic|tos|jurisdiction" docs/governance_dev/ docs/adr/
# 0 matches
$ find docs/governance_dev -name "*bybit_compliance*" -o -name "*kyc*"
# 0 matches
$ find docs -name "2026-05-09*" -type f | wc -l
> 14（全是 W-AUDIT / V077 / launchd / ContextDistiller / strategist_cap，0 條 Bybit ToS）
```

**Bybit-side push back**：v1 已 hard 列 P0 0-day action「`docs/governance_dev/2026-05-09--bybit_compliance_signoff.md` 框架建檔」，34 commits 跨 24h 0 進展。從 Bybit 立場：Live 真綁 mainnet 前 0 governance entry = 0 audit trail = 0 due diligence 證明。**仍是 ship-stop blocker**。

#### M5-2 API key IP whitelist — ❌ **unchanged**

**證據**：
```bash
$ ls helper_scripts/preflight/
# bfs: error: helper_scripts/preflight: No such file or directory
$ grep -rn "ip_whitelist|IP_WHITELIST|IP whitelist" helper_scripts/ program_code/exchange_connectors/
# 0 matches
```

**Bybit-side push back**：v1 已列 P0 1-day 「`helper_scripts/preflight/check_bybit_ip_whitelist.py` IMPL」，34 commits 跨 24h 0 進展。**仍是 ship-stop blocker**。

#### A5-1 04-30 Bybit 新欄位字典未記（symbolId / withdrawMax / openTime）— ❌ **unchanged**
grep `symbolId|withdrawMax|openTime` 字典 → 0 命中。advisory，不阻 Live。

#### A5-3 settleCoin fallback advisory — ❌ **unchanged**
無 commit 觸動。caller 仍透過 symbol 傳入。0 hot-path impact。

#### A5-5 broker_id / x-bapi-broker header 未送 — ❌ **unchanged**
30d volume ~$45K << $10M 門檻，無需送。advisory 維持。

#### A5-7 rate_limit default 10 vs memory「Order=20」— ❌ **unchanged**
不影響 runtime。

#### A5-9 funding_arb V3 重啟預檢 advisory — ❌ **unchanged**
當前已 active=false，0 流量；ADR-0018 / AMD-2026-05-09-02 / SM-05 補件已將「重啟需 spot lending support」明文化（v2 governance 加分），但 Rust 端 `BybitEnvironment::is_demo()` 預檢未實裝。

### v1 ⚠ 3 → v2

#### funding_arb V2 已止血未根治 — ⚠ **部分前進**

**v2 真實進展**：
- `af4942b6 risk: retire funding arb from risk config` 把 `[per_strategy.funding_arb]` 從 4 個 TOML（base / demo / live / paper）全部刪除
- ADR-0018 + AMD-2026-05-09-02 + SM-05 文件層收口
- `strategy_params_{paper,demo,live}.toml [funding_arb] active=false` 仍是 retirement authority（保留 trigger evidence trail）
- Rust `funding_arb.rs` + grid PostOnly reject callback wire（cooldown helper）

**Bybit-side 對抗性質疑**：W-AUDIT-6 Risk config layer cleanup 是 **policy authority cleanup**，不是 **operational dust clear**。具體仍 open：

PG 直查（`docker exec trading_postgres`）：
```sql
SELECT engine_mode, COUNT(*), MAX(ts)::text FROM trading.position_snapshots WHERE symbol='BUSDT';
demo|9327|2026-05-04 14:34:31.244+02
live_demo|2859|2026-05-03 21:01:35.117+02
```
殘倉 5-6 天前最後寫入 snapshot，**嚴重 stale**：
- demo: qty=19, long, entry=0.28464（5 days stale）
- live_demo: qty=69, long, entry=0.4273（6 days stale）

**結論**：W-AUDIT-6 IMPL **真實前進**（risk authority 收乾），但 NEW-1 真實 dust clear runbook **未跑**：
1. 操作層：未確認 Bybit 端 BUSDT 真實 qty（`/v5/position/list?symbol=BUSDT` operator action）
2. PG 層：12186 條歷史 snapshot 仍掛
3. fee_filter 仍受污染（[33] healthcheck 仍 WARN）

#### A5-2 retCode 110007 vs 110017 不一致 — ⚠ **unchanged**

**證據**：`bybit_rest_client.rs:297-387` BybitRetCode enum 仍只有 `AvailableInsufficient = 110007`，**未加 `SpotLendingUnavailable = 110017`**。`fee_execution_calibrator.py:91` 字串匹配 110017 維持工作。

**Bybit-side push back**：W-AUDIT-6 把 funding_arb risk authority 撤但 **沒補語意分類**。Rust enum 110017 仍缺 → 未來重新評估 V3 / 任何 spot 端 strategy 都可能誤把 110017 當 backoff 而非 dead-end。建議仍是 v1 P1：enum 加變體 + `is_balance_block()` 分類器接線。

#### A5-6 maker fill rate fee_drop 59.5% < 60% target — ⚠ **unchanged**

**證據**：
- `helper_scripts/db/passive_wait_healthcheck/checks_execution.py:1026 check_maker_fill_rate` 仍用 `_MAKER_FILL_CTE` 無 funding_arb 過濾
- `STRATEGY_ENTRY_FILL_PREDICATE` 只過濾 entry_context_id / exit_reason / oc_risk_*，**未過濾 strategy_name = 'funding_arb'**
- CLAUDE.md §三 [33]: `entry_fills=298, maker_like=89.6%, fee_drop=59.5% target>=60%` WARN 未動

**Bybit-side push back**：v1 已列 P1 1hr fix「healthcheck `[33]` 加 funding_arb filter」，34 commits 0 進展。fee_filter 不對稱仍 active：ML training filter funding_arb（`fee_execution_calibrator.py:91`）但 healthcheck 沒同步 → operator 看 [33] WARN 會誤啟 PostOnly review 浪費資源。**1 hr fix 拖了 8 天**。

### v1 🆕 2 → v2

#### NEW-1 BUSDT PG 殘倉 12186 — ⚠ **無變化**
v1 列 P0 3-day operator action（empirical query → 決定 PG 純清 vs dust clear），34 commits 0 進展。仍 12186 條 stale snapshot。

#### NEW-2 healthcheck [33] fee_filter 不對稱 — ❌ **unchanged**
與 A5-6 同源，1 hr fix 未做。

---

## §3. v2 NEW-ISSUE（24h 新發現）

### NEW-3 LiveDemo authorization.json missing → [56] healthcheck FAIL — Severity HIGH

**直接 PG / 檔案系統實測（2026-05-09 14:33 UTC）**：
```bash
$ ssh trade-core "ls /home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/"
api_key  api_secret  bybit_endpoint
# authorization.json 缺失！

$ ssh trade-core "stat -c '%Y' /tmp/openclaw/pipeline_snapshot_live.json"
1778334537   # mtime = 13:48:57 UTC
# 距 now()=14:33:25 UTC = 2668s ≈ 44.4 min stale，threshold 180s = 14× 超

$ python3 -c "from helper_scripts.db.passive_wait_healthcheck.checks_live_pipeline import check_56_live_pipeline_active; print(check_56_live_pipeline_active())"
('FAIL', 'live pipeline expected endpoint=live_demo but auth=authorization_json_missing path=/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json; operator must renew via signed live-auth route, not manual file write')
```

**Bybit-side push back**：v2 commit `c15985a5 healthcheck: add live pipeline activity sentinel` 加了 [56] check 是好事 — 但 check **正在 FAIL**。CLAUDE.md §三 寫「2026-05-09 09:41 UTC direct check PASS」是 5h 前的 snapshot；當下 LiveDemo pipeline 已死。

**RCA hypothesis**：
1. `authorization.json` 在 09:12 UTC operator renew，TTL 有限（CLAUDE.md §三 寫 expires_at_ms=1778405563954 = 2026-05-10 04:12 UTC），所以**未過期**但檔案被刪
2. 或 1778405563954 ms 換算 = 2026-05-10 04:12:43 UTC（明天凌晨），仍在有效期
3. 既然檔案缺但沒過期 → 表示有人/腳本/操作把檔案刪了 → **`restart_all.sh --keep-auth` 邏輯實測失敗** OR `clean_restart.sh` 走過

**對 BB 的影響**：
- LiveDemo 是 Live 管線走 demo endpoint（feedback `live_no_degradation_by_endpoint`）
- 8 days 之前已有「LIVE-AUTH-WATCHER fix」歷史 RCA（memory `project_live_auth_watcher_event_consumer_spawn.md`）
- v2 出現第 2 次類似事件 → live 真綁 mainnet 前 watchdog + auth lifecycle 仍未穩

**建議 Operator action**：
1. 立即 `POST /api/v1/live/auth/renew` 重簽 authorization.json
2. 跑 `restart_all.sh --keep-auth` 驗 keep-auth warn 邏輯（commit `11d7e098`）
3. RCA 為何 09:33 UTC `--keep-auth` 部署 5h 後 auth 又消失

### NEW-4 CLAUDE.md §三 [56] 寫 PASS 但實測 FAIL → §三 drift — Severity MEDIUM

**事實**：CLAUDE.md §三 line 顯示：
> `[56]` live pipeline active | 2026-05-09 09:41 UTC direct check PASS：`live pipeline active endpoint=live_demo auth=present snapshot_age=2.6s threshold=180s`

實際 14:33 UTC 直查 = FAIL。CLAUDE.md §五 中 §三 衛生規則：
> §三 數據 vs runtime drift 防線：§三 任何「runtime 數值 + 狀態」必註明採集時間 + 對應 healthcheck id；滿 7 日未經自動化重驗即必須更新或從 §三 刪除；CC 收到 §三 數字當決策輸入時必先實測 source-of-truth 才採納，發現 drift 同 commit 修。

**Bybit-side push back**：§三 [56] entry 採集才 5h 但 CC 主會話讀 §三 直接信「PASS」會誤判 LiveDemo 狀態。**§三 drift 防線實際失效**因為衛生規則只強制 7 日，但 live healthcheck 5h drift 已嚴重。建議 §三 「runtime 數值 + 狀態」加副規則：critical health entry（[55] / [56]）保留期 ≤6h，否則必標 [STALE-需重驗]。

---

## §4. funding_arb v2 retire 真實狀態（W-AUDIT-6 進展深評）

### Risk config layer ✅ 真清乾淨
```
risk_config.toml:        0 funding_arb 行 ✅
risk_config_demo.toml:   0 funding_arb 行 ✅
risk_config_live.toml:   0 funding_arb 行 ✅
risk_config_paper.toml:  0 funding_arb 行 ✅
```

### Strategy params layer 仍持「retirement authority」
```
strategy_params_demo.toml:   [funding_arb] active = false  ✅（trigger evidence trail）
strategy_params_live.toml:   [funding_arb] active = false  ✅
strategy_params_paper.toml:  [funding_arb] active = false  ✅
```

### ADR / AMD / SM-05 governance layer
- ADR-0018 funding_arb v2 deprecation watch（修訂 2026-05-09）
- ADR-0020 Layer2 manual supervisor only
- AMD-2026-05-09-02 operator decision audit closure
- SM-05 amendments 升 accepted

### 殘倉 operational layer ❌ 未動
- demo 9327 條 + live_demo 2859 條 PG snapshot
- 5-6 天前最後寫入
- 0 dust clear runbook 跑過
- 0 Bybit 端 `/v5/position/list?symbol=BUSDT` 實測

**Bybit-side verdict**：W-AUDIT-6 是 **policy / risk authority cleanup 真前進**（值得肯定），但 **operational dust clear 仍 NEW-1 stuck**。從 Bybit 立場 funding_arb 已是退休策略 — 但帳戶上掛 BUSDT 持倉若真實還在 → reconciler 不再觀察 + risk_config 沒對應 cap → **倉位失監管狀態**。Operator 必須跑實測。

---

## §5. Bybit V5 30d changelog（2026-04-30 → 2026-05-09）

WebFetch 結果（重複 v1 確認 + 新增 8-9 日）：

| Date | Endpoint | Type | OpenClaw 影響 |
|---|---|---|---|
| 2026-05-07 | Get Staked Position | UPDATE non-breaking +`availableAmount` +`freezeDetails` | 0 |
| 2026-05-06 | Create/Cancel Supply Order | UPDATE non-breaking optional `availableSource`/`refundedAccount` | 0 |
| 2026-04-30 | Instruments-Info etc | Mixed | 0 |
| 2026-05-08+ | n/a | (changelog 無新項) | 0 |

**Bybit-side 結論**：30d **0 breaking change in OpenClaw scope**。所有變動 OpenClaw `serde(default)` 兜底。**vs v1 結論一致**。

---

## §6. 對抗性 push back（Bybit-side 立場）

### Push back #1：v2 34 commits 0 觸 M5-1 / M5-2 = ship-stop blocker 重複出現

W-AUDIT-1..7 v2 修了大量 docs / runtime / security / GUI confirmation / R:R exits / portfolio tail risk / strategist cap / context distiller — **0 條觸 Bybit ToS / KYC / 地理禁區 / IP whitelist**。從 Bybit 立場看，operator 把全部精力放在 internal hardening + code quality，**忽略了 Live 真綁 mainnet 的法律 / 合規前提**。

**v1 已硬列 P0 0-day + P0 1-day 兩個 action，v2 0 進展**。**Bybit-side 拒絕背書 Live 啟動**重申。

### Push back #2：W-AUDIT-6 funding_arb risk config 收乾但 BUSDT 殘倉仍在懸

W-AUDIT-6 commit `af4942b6` 把 funding_arb 從所有 risk_config TOML 移除是 **policy 層真前進**（值得肯定）；但**操作層 operator 沒跑 BUSDT 實測 + dust clear**。從 Bybit 立場：「funding_arb 在 risk_config 不存在」≠「BUSDT 倉位被清乾淨」。如果 Bybit 真實端仍有 long 19/69，**現在沒任何 risk cap 監管它了**。**這在 policy retirement 後變得更危險而非更安全**。

**建議 immediate operator action**：跑 ssh + `/v5/position/list` 實測（3 day P0 v1 列出，已第 7 天）。

### Push back #3：[56] LiveDemo 健康倒退是新 trade-off

v2 commit `c15985a5` 加了 [56] live_pipeline_active sentinel 是好事（fail-closed exposure）。但 commit 5h 後 `authorization.json` 又消失 → check 進入 FAIL → CLAUDE.md §三 寫 PASS 是過期 snapshot。

從 Bybit 立場：**有 sentinel 但 sentinel 真實 trip 了**，operator 沒收到 alert（cron 沒跑或 alert 沒接到）→ §三 / TODO / dispatch 看到「PASS」假象。這是 **observability theatre** — 寫了 check 但 no-one acts。**比沒 check 更糟**因為造成虛假信心。

### Push back #4：funding_arb 退休 governance 收口 vs spot lending enum 缺位

ADR-0018 + AMD-2026-05-09-02 + SM-05 把 funding_arb 退休理由文件化是好事。但 **Rust BybitRetCode enum 110017 仍缺**。從 Bybit 立場：未來如果 OpenClaw 重新評估 spot 端策略（spot trading / margin / lending），110017 reject 仍會被誤判為 backoff（is_exchange_backoff）而非 dead-end → 無限重試 reject。**enum 補完是 1 day 工作量**，v1 已列 P1，v2 0 進展。

### Push back #5：v2 §三 [56] drift 違反 §五 衛生規則

CLAUDE.md §五 明寫「runtime 數值 + 狀態」7 日 drift 防線，但 [56] 5h 就 drift 了。**critical health gate 用 7d 寬容期不夠**。建議 §五 加副規則：[55] / [56] 等 critical health entry 只能保留 ≤6h 直查 snapshot，否則必標 [STALE-需重驗]。

---

## §7. 結論

### 技術合規度核實

| 項 | v1 (97%) | v2 (97%) |
|---|---|---|
| Bybit V5 REST endpoint 用法 | 100% | **100%** ✅ |
| HMAC 簽名 | 100% | **100%** ✅ |
| Rate limit 6 分組 | 100% | **100%** ✅ |
| WS auth + reconnect + G9-02 | 100% | **100%** ✅ |
| LIVE-GUARD-1 三閘 + Gate #4/#5 | 100% | **100%** ✅ |
| 字典 SSOT 對齊 | 100% | **100%** ✅ |
| funding_arb risk_config layer | 90%（殘留 4 TOML） | **100%** ✅（W-AUDIT-6 清乾） |
| LiveDemo pipeline 健康 | 100%（v1 [56] PASS） | **70%**（[56] 實測 FAIL；§三 drift） |
| 政策層 | 70% | **70%** ❌ |

**整體技術合規度：97%**（funding_arb +1pp 但 LiveDemo -1pp 平手）。

### 政策合規度核實

**0 進展**。M5-1 / M5-2 仍空白。Bybit-side 嚴苛立場：**Live mainnet 啟動前必完成**：
1. `docs/governance_dev/2026-05-09--bybit_compliance_signoff.md` 框架建檔（[PENDING] markers OK）
2. operator 在 Bybit UI 完成 6 項自證
3. `helper_scripts/preflight/check_bybit_ip_whitelist.py` IMPL（startup self-check）

### Bybit-side overall verdict

**verification v2: PARTIAL PASS WITH NEW REGRESSION**
- ✅ 字典 drift 全清維持（5/5 source-closed）
- ✅ funding_arb risk config layer 真清（W-AUDIT-6 進展可見）
- ✅ 30d changelog 安全（0 breaking）
- ✅ 技術層 G9-02 + LIVE-GUARD + WS health 全綠
- ⚠ funding_arb 殘倉 + 110017 enum + fee_filter asymmetry 仍 v1 stuck
- 🆕 LiveDemo healthcheck [56] FAIL（authorization.json missing + snapshot 44min stale）→ Live infra 倒退
- 🆕 §三 [56] drift（5h drift）→ governance hygiene 失效
- ❌ 政策層 M5-1 / M5-2 = ship-stop blocker 仍空白

### Bybit-side 下一步建議（優先序）

| 優先 | Action | Owner | ETA |
|---|---|---|---|
| **P0 🆕** | 立即重簽 authorization.json + RCA 為何 09:33 UTC --keep-auth 部署 5h 後 auth 消失 | operator + E1 | 0 day |
| **P0 🆕** | §五 衛生規則加副規則：critical health entry ([55]/[56]) ≤6h drift | PM | 0.5 day |
| P0 | `helper_scripts/preflight/check_bybit_ip_whitelist.py` IMPL + commit | E1 | 1 day（v1 已列） |
| P0 | `docs/governance_dev/2026-05-09--bybit_compliance_signoff.md` 框架建檔 | PM | 0 day（v1 已列） |
| P0 | operator BUSDT empirical query → 決定 PG 清 vs dust clear | operator | 3 day（v1 已列，第 8 天） |
| P1 | Rust BybitRetCode enum 加 `SpotLendingUnavailable = 110017` + 分類器接線 | E1 | 1 day（v1 已列） |
| P1 | healthcheck [33] 加 funding_arb filter（NEW-2） | E1 | 1 hr（v1 已列，第 8 天拖延） |
| P2 | 字典 v1.3 補 04-30 新欄位 catalog | TW | 0.5 day |
| P3 | funding_arb V3（如重啟）必加 `BybitEnvironment::is_demo()` 預檢 | E1 | future |

---

## §8. 檔案清單

**字典（已修，v1 → v2 維持）**：
- /Users/ncyu/Projects/TradeBot/srv/docs/references/2026-04-04--bybit_api_reference.md（v1.2）

**v2 新進展（risk config 收乾）**：
- /Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config.toml
- /Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_demo.toml
- /Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_live.toml
- /Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_paper.toml
- /Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-09--w_audit_6_funding_arb_risk_cleanup.md
- /Users/ncyu/Projects/TradeBot/srv/docs/adr/0018-funding-arb-v2-deprecation-watch.md（v2 修訂）
- /Users/ncyu/Projects/TradeBot/srv/docs/adr/0020-layer2-manual-supervisor-only.md（new）

**v2 新進展（[56] healthcheck IMPL）**：
- /Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/passive_wait_healthcheck/checks_live_pipeline.py（new 158 LOC）
- /Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/passive_wait_healthcheck/runner.py（+17 LOC）
- /Users/ncyu/Projects/TradeBot/srv/tests/db/test_live_pipeline_healthcheck.py（new 125 LOC）

**v2 governance closure**：
- /Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md
- /Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-09--SM-05_executor_shadow_mode_polling_design.md

**Governance gap（仍空白，v1 → v2 0 進展）**：
- /Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/2026-05-09--bybit_compliance_signoff.md（**未建** — M5-1 ship-stop）
- /Users/ncyu/Projects/TradeBot/srv/helper_scripts/preflight/check_bybit_ip_whitelist.py（**目錄不存在** — M5-2 ship-stop）

**PG 殘倉（仍 open，v1 → v2 0 進展）**：
- trading.position_snapshots WHERE symbol='BUSDT' demo n=9327 + live_demo n=2859

**v2 NEW regression**：
- /home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json（**missing** @ 14:33 UTC）
- /tmp/openclaw/pipeline_snapshot_live.json（mtime 13:48 UTC，44min stale）

---

BB AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-09--bybit_compatibility_verification_v2.md
