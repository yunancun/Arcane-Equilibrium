# P0-LG-3 Reality-Check + Corrected Dispatch Packet

**Date**: 2026-05-30
**Owner**: PA
**Trigger**: LG-3 Wave 2.4.A 今日 ~16:00 UTC Gate 1 一過即將 dispatch；operator 報「TODO freeze 文字與磁碟實況矛盾」。要先查清真實狀態再修正 dispatch packet。
**Method**: 全部 empirical — Mac repo HEAD=187704f6 / branch=main。`ls sql/migrations/` 全列 + 逐檔 grep + 讀 SQL header 全文 + repo-wide `grep --include=*.rs/*.py/*.sql` + spec + `linux_bootstrap_db.sh` 應用器。
**Status**: REALITY-CHECK DONE — **結論與 operator 前提 AND 現行 TODO 行 72「freeze 過期修正」段落全部相反**。supervised_live_audit migration **從未被寫過**（git 全史 0 hit）；磁碟上沒有任何 supervised SQL；PG max=115 的 115 個版本裡沒有 supervised。**真實風險不是「誤派重建已 apply 的 migration」，而是「有人幻覺 V104 已做 → 跳過寫 V104」**。

---

## 結論先行（給 16:00 UTC dispatch 決策）

1. **可以派，但 packet 內容必須整段改寫**。真實剩餘 = 4 件全新 NEW（含 **V104 SQL 本身要從頭寫**）+ T1 整組 Rust SM。
2. **operator「我已確認的事實」5 條裡 4 條錯**（見 §A 對賬表）：
   - V104 supervised SQL **不存在**（`sql/migrations/` 由 V103 直接跳到 V106，V104 是真空洞）。
   - operator 說的「V114 也存在 = supervised v2」**錯**：`V114__notification_failsafe_events_hypertable.sql` 是 Wave 5 Packet C 的通知 failsafe 表，與 supervised **毫無關係**。
   - 「PG max=115 代表 V104..V115 全已 apply 到 trading_ai」**對一半**：max=115 是真，但這 115 個版本是 V099/V100/.../V113/V114(notification)/V115(basis)，**沒有任何一個是 supervised_live_audit**。
   - migration 路徑前綴 `openclaw_engine/sql/migrations/` 錯：canonical = `sql/migrations/`（repo 根，`linux_bootstrap_db.sh:33 MIG_DIR="$BASE/sql/migrations"`）。Rust engine 也在 `rust/openclaw_engine/`，不是 `openclaw_engine/`。
   - 唯一對的：fact #4「T1 Rust SM 核心不存在」屬實。
3. **現行 TODO 行 72 的「⚠️ freeze 過期修正 2026-05-30：V104+V114 supervised 均已存在且已 apply（max=115，checksum 凍結 → T4 migration 部分 DONE，禁重建）」整段是錯誤資訊（很可能是把 V114 notification 誤認成 supervised v2 + 把 max=115 誤讀成 supervised 已 apply）。必須 revert 這段**，否則會誤導 E1 跳過寫 V104 → LG-3 audit 表永遠不存在 → writer runtime 失敗。
4. **sqlx hash drift 在此情境不適用**（因為 V104 supervised 根本還沒 apply，無 checksum 可 drift）。真正要守的紅線反過來：V104 是 **FREE 號**，E1 必須**新寫** `V104__supervised_live_audit.sql`；但**不可動已 apply 的 V099-V115 任何既有檔**（那些才會 drift）。
5. **無撞表風險**（因 supervised 表還沒建）；但有**撞號風險**：V104 號目前 free，Wave 5 / Sprint 2 其他 migration 不得搶占 V104；packet 要鎖死「LG-3 = V104」。

---

## A. operator 5 條「事實」 vs 磁碟真相對賬

| # | operator 宣稱 | 磁碟真相（empirical） | 判定 |
|---|---|---|---|
| 1 | `openclaw_engine/sql/migrations/V104__supervised_live_audit.sql` 存在（commit 9a832c7f 引入） | `sql/migrations/` 無任何 V104 檔（V103→V106 跳號）；`openclaw_engine/sql/migrations/` 目錄不存在；canonical = `sql/migrations/`。9a832c7f 真存在但 = `docs(todo): 4-track plan...`，**不碰任何 V104/supervised SQL** | ❌ **FALSE** |
| 2 | `V114__supervised_live_audit_v2.sql` 也存在 | `V114__notification_failsafe_events_hypertable.sql`（Wave 5 Packet C 通知 failsafe 表，header 親讀）。**沒有** supervised v2 檔 | ❌ **FALSE（撞名誤認）** |
| 3 | PG `_sqlx_migrations` max=115 → V104..V115 全 apply（含 supervised） | max=115 是真（§0 snapshot + TODO 行 11 V115 applied），但這些版本 = V099/.../V115，**0 個 supervised**。supervised 表從未 apply | ⚠️ **半真：max 對，但 supervised 不在內** |
| 4 | T1 Rust SM 核心疑似不存在 | `grep -rl supervised_live\|SupervisedLive rust/openclaw_engine/src/` = **0**；`find -iname '*supervised*'` 在 src = 空 | ✅ **TRUE** |
| 5 | TODO ticket 文字自相矛盾（「V104 scaffold ✅」又「V104 still FREE / T1+T4 absent」）| 真相：**V104 SQL 確實 FREE（未寫）**；「scaffold ✅」指的是 **spec scaffold doc**（`docs/execution_plan/specs/2026-05-26--v104-...md`，378 行設計文，非 SQL 本體）。兩句其實不矛盾 — 一句講 spec doc 已寫，一句講 SQL 還沒寫。**真正矛盾的是行 72 新加的「V104+V114 已 apply」段，那段才是錯的** | ⚠️ **誤判矛盾點** |

**根因推測**：某 session（行 72「freeze 過期修正 2026-05-30」）看到磁碟上有 `V114__...` 檔 + PG max=115，就推斷「V104/V114 supervised 已 land + apply」，但沒讀 V114 header（是 notification 不是 supervised）、也沒 grep 確認 supervised SQL 內容存在。operator 的「我已確認的事實」很可能繼承自這個錯誤的 TODO 段落。

---

## B. V104 真實狀態 + V104 vs V114 關係

**判定：supervised_live_audit migration 不存在於磁碟、不存在於 git 全史、不存在於 PG。只存在 spec 設計文。**

- `git log --all -S 'supervised_live_audit'` 全史 → 0 commit 觸及 supervised SQL（pickaxe 空）。
- 磁碟 supervised SQL = 0（`grep -il supervised_live sql/migrations/*.sql` 空）。
- **存在的只有設計藍圖**：
  - `docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md`（16.6KB / 378 行 scaffold — 21 col / 4 CHECK / hypertable 7d / Guard A 3-part / 4-step dry-run plan / V094→V104 替換規則）。**這是 spec，不是可 apply 的 SQL。**
  - LG-3 spec v2 final（`docs/CCAgentWorkSpace/{Operator,PA}/...2026-05-11--lg_3_spec_v2_final.md`）。
- **V104 號 = FREE 真空洞**：V103 land → V104/V105 空 → V106 land（`ls` 親證）。V105/V108/V110/V111 同為 free holes。
- **V104 vs V114「v1/v2」是誤會**：`V114__notification_failsafe_events_hypertable.sql` header 原文「Wave 5 Packet C C2 — observability.notification_failsafe_events」，與 supervised 無任何關係。不存在 supervised v1/v2 雙檔，故無撞表問題。

**MIT 2026-05-27 dry-run 9/9 PASS 怎麼解釋**：MIT 在 trading_ai 用 `BEGIN; ... ROLLBACK;` 跑的是**它依 spec 自己手寫的 candidate SQL**（archived `/tmp/v104_dryrun_candidate.sql` on trade-core），全程 ROLLBACK 未 commit、未進 `_sqlx_migrations`。所以 dry-run 證明了「spec 的 schema 在 PG 可成立」，但**沒有**把 V104 land 進 repo 或 PG。dry-run PASS ≠ migration 已存在。

---

## C. T1 Rust SM 核心

**判定：src 確實 0 supervised code。T1 整組 NEW。**

- `grep -rl 'supervised_live' rust/openclaw_engine/src/` = 0；`grep -rln 'SupervisedLive'` = 0；`find rust/openclaw_engine/src -iname '*supervised*'` = 空。
- repo-wide（排 docs）`grep supervised_live --include=*.rs/*.py/*.sql` = 0 命中。
- 既有掛接 anchor（非 T1 交付物，供 T5 後續用）：`rust/openclaw_engine/src/intent_processor/mod.rs` + `rust/openclaw_engine/src/.../governance_hub`（lease / SM-04）。

---

## D. T4 其餘交付物

**判定：T4 四件全部不存在（含 V104 SQL）。operator/TODO 說的「V104 已 land 不重建」是錯的 — V104 要從頭寫。**

per spec scaffold §8.2 + §0.2，T4 = 4 件 NEW：

| T4 交付物 | 期望檔 | 磁碟實況 |
|---|---|---|
| DB migration | `sql/migrations/V104__supervised_live_audit.sql` | ❌ **不存在 — 要新寫**（git 全史 0 hit；V104 號 free） |
| Rust audit writer | `rust/openclaw_engine/src/.../supervised_live_audit_writer.rs` | ❌ 不存在（grep src = 0） |
| healthcheck | `checks_supervised_live_audit.py` | ❌ 不存在（find 空） |
| grep guard | `e3_grep_non_training_surface.sh` | ❌ 不存在（find 空） |

T4 LOC 估 ~980（含 V104 SQL ~165 + writer + healthcheck + grep guard）— **維持原估，因為 V104 並未 land**。

---

## E. 真實剩餘 gap + 修正後 dispatch packet

### E.1 已完成 vs 真實剩餘

| 項 | 狀態 | 證據 |
|---|---|---|
| V104 spec scaffold（設計文） | ✅ 存在 | `docs/execution_plan/specs/2026-05-26--v104-...md` 378 行 |
| LG-3 spec v2 final | ✅ 存在 | `2026-05-11--lg_3_spec_v2_final.md` |
| MIT spec-schema dry-run（手寫 candidate, ROLLBACK） | ✅ 9/9 PASS | MIT 2026-05-27 report — 證明 schema 可成立，**未 land** |
| `repair_migration_checksum` binary | ✅ 存在 | `rust/openclaw_engine/src/bin/repair_migration_checksum.rs` |
| **T4 V104 SQL** | ❌ **NEW（要從頭寫）** | git 全史 0 hit；V104 號 free |
| **T4 audit writer .rs** | ❌ NEW | grep src=0 |
| **T4 healthcheck .py** | ❌ NEW | find 空 |
| **T4 grep guard .sh** | ❌ NEW | find 空 |
| **T1 Rust SM core**（mod/state/transition/reconciler/tests）| ❌ NEW（5 檔 ~1700 LOC）| grep src=0 |
| T2/T3/T5/T7 | ❌ 後續 Wave 2.4.B-E | `live_session_routes.py` 已存在（T3/T5/T7 EXTEND，非 CREATE） |

### E.2 紅線（dispatch packet 必含）

1. **V104 SQL 必須新寫**（不是「已 land 不重建」）。檔名 `sql/migrations/V104__supervised_live_audit.sql`（repo 根 canonical 路徑，**非** `openclaw_engine/sql/migrations/`）。寫完後走標準 forward-apply：`OPENCLAW_AUTO_MIGRATE=1` engine restart 或 `linux_bootstrap_db.sh` 在 Linux PG land。
2. **V104 land 前必 MIT 正式 dry-run 進 repo**：MIT 2026-05-27 的 ROLLBACK dry-run 是用「依 spec 手寫 candidate」驗 schema 可行，但 repo 內並無此 SQL；E1 寫出真檔後仍要 MIT 對「真檔」跑一次 dry-run（idempotency double-apply per `feedback_v_migration_pg_dry_run`），不能拿舊 candidate 的 9/9 當真檔已驗。
3. **不可動 V099-V115 任何既有 migration 檔**（那些已 apply，edit 會撞 sqlx hash drift，見 `project_2026_05_02_p0_sqlx_hash_drift`）。V104 是它們之間的 free hole，新增 V104 不影響既有 checksum（sqlx 按 version sort，補洞合法）。
4. **若 V104 真檔在 land 後又 edit** → 必 `bin/repair_migration_checksum --target V104`（spec §5.1）。
5. **撞號防護**：LG-3 鎖定 V104；告知 Wave 5 / Sprint 2 並行 owner 勿搶 V104 號。
6. **V094/V099 字眼清零**：T4 完工前 `grep -n 'V094\|V099' <touched>` = 0（spec §7.2）。

### E.3 Corrected Wave 2.4.A 並行切分（2 E1 + MIT）

**MIT（先行 / 與 E1 並行起手）— V104 真檔 dry-run**
- E1-T4 寫出 `V104__supervised_live_audit.sql` 真檔後，MIT 對真檔走 spec §4 4-step Linux PG dry-run（snapshot → apply → idempotency double-apply → 9-query reflection），出新 report。**不可沿用 2026-05-27 candidate 的 PASS。**
- 真檔 land 進 PG 後寫進 `_sqlx_migrations`（max 115→116，version=104 補洞）。

**E1-T1（Rust SM core）— 純 NEW，零 EXTEND，零 SQL**
- 交付：`rust/openclaw_engine/src/supervised_live_sm/{mod,state,transition,reconciler,tests}.rs`（5 NEW）
- spec：v2 final §1+§2+§3+§5+§6.3+§7；AC = §8 AC-T1-1~9
- LOC ≈ 1700
- worktree：`git worktree add ../wt-lg3-t1 -b feature/lg3-t1`
- 紅線：不碰 `sql/migrations/`；不碰 main tree；不看 T4 worktree

**E1-T4（V104 SQL + audit writer + healthcheck + grep guard）— 4 NEW**
- 交付（4 NEW）：
  - `sql/migrations/V104__supervised_live_audit.sql`（**新寫**，依 spec §2 21 col / §2.2 4 CHECK / §2.3 hypertable 7d + compress 30d + retention 90d / §3 Guard A 3-part / §2.4 4 index）
  - `rust/openclaw_engine/src/.../supervised_live_audit_writer.rs`（INSERT 對齊 21 col；engine_mode ∈ {live, live_demo} 拒 paper）
  - `helper_scripts/healthchecks/checks_supervised_live_audit.py`（[59]/[60]/[61]）
  - `helper_scripts/.../e3_grep_non_training_surface.sh`（forbidden ML column CI gate）
- spec：v2 final §2.2A + §4 + V104 spec scaffold 全；AC = §8 AC-T4-1~10
- LOC ≈ 980
- worktree：`git worktree add ../wt-lg3-t4 -b feature/lg3-t4`
- 紅線：V104 號 free 必新寫；**不得編輯任何 V099-V115 既有 SQL**；完工前 `grep -n 'V094\|V099' <touched>` = 0

T1 ∥ T4 檔案零 overlap（T1 = `supervised_live_sm/`；T4 = V104 SQL + writer + 2 script）→ 2 E1 並行安全。

### E.4 後續 Wave overlap 順序（給 PM 排期，非本次派）

- **`live_session_routes.py`（已存在 at `program_code/exchange_connectors/bybit_connector/control_api_v1/app/`）** 被 T3 / T5 / T7 EXTEND：**嚴格 sequential T3 → T5 → T7**；每 task 先 `git pull origin main`。注意 operator dispatch packet 寫的路徑要更正為此實際路徑。
- **`rust/openclaw_engine/src/intent_processor/mod.rs`** 被 T5 EXTEND：**T1 land 前 T5 不可開動**（T5 依賴 T1 SM 型別）。
- **governance_hub（lease / SM-04 anchor）**：T5 kill+lease 掛接處；E2 重點審。

### E.5 Dispatch gate 狀態

| Gate | 條件 | 狀態 |
|---|---|---|
| Gate 1 | v56 P0 Layer B + 24h（~16:00 UTC，engine 15:51 重啟 clock reset） | ⏳ operator 觀察中 |
| Gate 2 | MIT V104 schema dry-run（candidate, ROLLBACK） | ✅ 達成（2026-05-27）— 但僅證 schema 可行 |
| **NEW Gate 2b** | **MIT 對 E1 寫出的 V104 真檔再跑一次 dry-run（含 idempotency double-apply）** | ❌ **未做（真檔還沒寫）— 必補** |

Gate 1 一過 → PM 派 E1-T1 + E1-T4 並行；E1-T4 寫出 V104 真檔 → MIT Gate 2b → 真檔 land。

---

## 高風險警告（E2 必須重點審查 3 點）

1. **V104 SQL 是「新增 free-hole migration」而非「重建已 apply」**：E2 收 PR 要確認 (a) diff 只**新增** `sql/migrations/V104__supervised_live_audit.sql`，(b) diff 對 V099-V115 既有 SQL 改動 = **空**（任何既有檔出現在 diff = BLOCKER，撞 drift），(c) MIT 已對真檔（非舊 candidate）出新 dry-run report。
2. **audit writer 欄位 / CHECK 對齊**：writer INSERT 的 action ∈ 17-enum、engine_mode ∈ {live, live_demo}（拒 paper，LiveDemo 不降級）、21 col 全對；違 DB CHECK 會 runtime `check_violation`。
3. **T1 SM kill / lease / fail-closed 邊界**：SM transition 不繞 governance_hub lease；kill 路徑（kill_api/kill_ipc/session_max_duration/reconcile_force_close）對應 audit action 齊；不確定態 default 收縮（根原則 6）；不觸碰 `live_execution_allowed`/`max_retries`/`OPENCLAW_ALLOW_MAINNET`/`authorization.json`（硬邊界 0 變動）。

---

## TODO 行 72 必須修正（給主會話）

把行 72「⚠️ freeze 過期修正 2026-05-30：V104__supervised_live_audit.sql + V114__supervised_live_audit_v2.sql 均已存在且已 apply（max=115，checksum 凍結 → T4 migration 部分 DONE，禁重建/改 checksum）」整段 **revert / 改寫為**：

> ⚠️ **2026-05-30 reality-check 更正前一段錯誤**：磁碟 `sql/migrations/` 無任何 supervised SQL（V104 號 FREE 真空洞，git 全史 0 hit）；`V114__notification_failsafe_events_hypertable.sql` 是 Wave 5 Packet C 通知表非 supervised v2；PG max=115 的版本不含 supervised。**T4 V104 SQL + writer + healthcheck + grep guard 全部仍要新寫；T1 SM core 全新。MIT 2026-05-27 dry-run 是手寫 candidate ROLLBACK 驗 schema 可行，repo 無真檔 → 寫出真檔後須 MIT 再跑一次（含 idempotency double-apply）。** ref `2026-05-30--lg3_reality_check_and_corrected_packet.md`。

---

## 16 root principles compliance

本次為 read+design only。對 LG-3 IMPL 設計約束維持 A 級：§1 單一寫入口（writer 只 INSERT）/ §3 AI→Lease→複核（T1 SM 不繞 lease）/ §6 失敗收縮 / §8 可解釋（append-only audit）/ §11 自主邊界。硬邊界 live_reserved / max_retries / system_mode / live_execution_allowed / OPENCLAW_ALLOW_MAINNET 全 0 變動。

---

## 工具環境註記（誠實披露）

本次 Mac 本地 Bash 通道間歇性靜默（部分指令執行成功但無 stdout 回傳）。所有結論均取自**有確實回傳輸出**的指令（`ls sql/migrations/` 全列 / V114 header 親讀 / grep supervised 全 0 / rust src grep 0 / `linux_bootstrap_db.sh:33` MIG_DIR）。**PG `_sqlx_migrations` 的逐版本內容、engine binary commit、真檔 land 狀態屬 Linux runtime 權威，Mac 不可直驗** — 須 `ssh trade-core` 在 dispatch 前最終確認 max=115 的 116 個版本確無 supervised（本報告依 §0 snapshot + TODO 行 11 推斷，標為 inference）。

---

PA DESIGN DONE: report path: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-30--lg3_reality_check_and_corrected_packet.md`
