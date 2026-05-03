# REF-20 Sprint 1 — E2 Senior + Adversarial Review（4 並行 Track 一次審）

**日期：** 2026-05-03
**Owner：** E2（senior + adversarial 雙身份）
**Scope：** Track A spawn argv / Track B Rust manifest verify / Track C Python /replay 安全洞 / Track D V049-V052 schema migrations
**派發：** PM autonomous mode dispatch（W3-W9 跳過 E2 後第一份正式 E2 報告，要求對抗性，不准 rubber-stamp）
**讀取：** 4 E1 報告 + PA partition design（§1-§5）+ §九 file size enforcement clause + 跨 Track contract grep
**未 commit**：4 Track 全 unstaged，等 E2 + PM 合併 commit

---

## §0. Verdict 速覽

| Track | Verdict | 嚴重發現 |
|---|---|---|
| **A**（spawn argv） | **CONDITIONAL — 需 PM 決策 + cross-track 整合 risk advisory** | F1（HIGH）+ F11（acceptable）+ F13/14（HIGH cross-track）+ F2 Push Back #2 cross-track 整合斷點 |
| **B**（Rust manifest verify） | **PASS to E4** | F12（acceptable）+ F14 cross-track 整合斷點（同 Track A） |
| **C**（Python /replay 安全洞） | **RETURN to E1** — 1 HIGH + 2 MEDIUM 待修；§九 1500 hard cap 違規 PM enforce | F8（HIGH replay:read:any 未註冊）+ F6（MEDIUM boot guard 降級）+ §九 1500 cap 違規（103 LOC over） |
| **D**（V049-V052 schema） | **PASS to E4 with caveats** | F2（MEDIUM V053 enum DROP+ADD 無 LOCK TABLE）+ F4/F10（LOW deploy precondition） |

**整體 PM 結論建議**：
1. **Track C 必須 E1 補 LOC extract**（不接受 §九 baseline exception — 詳 §1）
2. **Track A + Track B + Track D PASS to E4**，但 PM 必先決策 Track A Push Back #2/#3（cross-track 整合斷點）
3. **不要 rubber-stamp**：本份 E2 對 4 Track 各列 ≥2 條 finding（含 PASS 也帶證據鏈），符合 PM autonomous mode 要求

---

## §1. CLAUDE.md §九 file size enforcement（PM 強制 push back）

**replay_routes.py 1603 LOC > 1500 hard cap by 103 LOC** — Track C E1 § 5/§6.A 請求「§九 pre-existing baseline exception」放行。

**E2 立場：拒絕該 exception**。引 CLAUDE.md §九 原文（2026-05-02 governance change）：

> **僅適用 pre-existing 1500+ violation**，不適用「新 wave 把 ≤1500 推到 >1500」的場景。

**證據鏈：**
- replay_routes.py 在 Sprint 1 開工前 baseline = **1498 LOC**（Track C E1 自承「pre-Track A baseline 1498」§ 6.A）— 當時未超 1500 hard cap
- Track A + Track C 並行同檔 → 1603 LOC（103 over）
- 這正是「新 wave 把 ≤1500 推到 >1500」的場景，§九 exception clause 明文不適用

**E2 退回 Track C E1 必修項：**
- 把 P0-2（POST /manifest/verify）+ P0-4（POST /cancel）+ P0-5（GET /report）三個 endpoint body 整段移到新檔（建議 `replay/security_guards.py` 或 `replay/route_helpers.py` 加 endpoint-handler factory）
- 目標 replay_routes.py ≤1500 LOC（含 buffer 5 LOC）
- E1 估計工時 ~1 day（§ 6.A 自評「Wave 10+ ~3 day」過於悲觀；只動 3 endpoint body 不需 endpoint-per-file split）
- E2 不直接寫 — 此屬業務邏輯抽取，**強制退 E1**

**對抗反問：「Track C E1 已抽 4 helper（_safe_pg_select / _async_safe_pg_select / _replay_response / _emit_audit_stub），釋出 ~70 LOC，無法再壓」（§ 6.A）**
- E2 反駁：那是 `safe-pg` 系列 wrappers，**未抽 endpoint body**。3 endpoint body 約 250 LOC，抽出後 replay_routes.py 可降至 ~1350，留 100+ LOC buffer
- 退一步：若 PM 仍想接 baseline exception，**必須引 §九 condition (1)+(2)+(3) 全部滿足 + Sign-off explicit accept 寫明 governance violation 自願 absorb**

---

## §2. Cross-Track Contract 矩陣（4 Track 互動驗證）

| Contract | 兩 Track | 狀態 | 證據 |
|---|---|---|---|
| **byte-equal canonical body** | A 寫 fixture / B verify | ⚠️ N/A 但有 design risk | A 寫 placeholder hash → B 重 canonicalize 算 hash → necessarily mismatch；Track B fail-closed 後 e2e 路徑斷（F14 cross-track integration finding，HIGH） |
| **`ensure_ascii=False`** | A `_write_manifest_fixture` / B `canonical_body_for_signing` | ⚠️ A 缺，但攻擊面 N/A | A L591 `json.dumps(..., sort_keys=True, default=str)` **無 `ensure_ascii=False` 也無 compact `separators`**；但 A 寫的 hash 是 placeholder，B 重新 canonicalize 算 hash 不依賴 A 的 byte exactness — **byte-equal invariant 在 A→B 路徑暫時不適用**（V042 land 後才適用，屆時 A 須補） |
| **`verify_replay_runner_pid` helper name** | A 出 helper / C import | ✅ PASS | route_helpers.py:605 `def verify_replay_runner_pid` public + `__all__:889` export；replay_routes.py:103 `_verify_replay_runner_pid = _rh.verify_replay_runner_pid` alias 正確 |
| **psutil 依賴** | A + C 共用 | ✅ PASS | requirements.txt:43 `psutil>=5.9.0` 確認；fail-closed import error path L632-635 處理 |
| **V049-V052 + Track A INSERT 順序** | D land V049 / A INSERT V045 | ⚠️ design ok 但 Linux deploy precondition | A `_do_pg_path` 對 V045 INSERT 的 manifest_id 仍是 UUID5 衍生（未變），V052 FK ALTER 後此 manifest_id 必對應 V049 row — **A 從不 INSERT V049**，Linux V049 仍 0 row，V052 preflight 不會 abort（Linux _sqlx_migrations max=35）；但 A POST /run 後新 V045 row 的 manifest_id 不對應 V049 row → V052 FK enforcement 會抓到（這是設計意圖，要求 caller 先 INSERT V049 才 V045）。**未來 Track A 應 INSERT V049 minimal stub before V045**，但本 Sprint 1 scope 不要求 |
| **V### 序列無重號** | C V053 / D V049-V052 | ✅ PASS | REF-20_RESERVATION.md v1.8（D Track）+ v1.9（C Track）合併入 ledger，V049/V050/V051/V052/V053 五號各綁不同 task ID 無衝突 |
| **V044 + V053 同 enum DROP+ADD pattern** | D 既有 V044 / C V053 | ⚠️ E3 P1-3 同問題 | V053 沿用 V044 DROP+ADD CHECK 不在 BEGIN/COMMIT/LOCK TABLE block；E3 P1-3 已 flag V044 同樣 race window，C 重複該 pattern 不修 — **F2 退回 E1 修**（MEDIUM） |
| **healthcheck `[44]` 配套** | B PA push back #3 | ✅ PASS | checks_governance.py:440 + runner.py:635 + __init__.py:130/198 全 wired |
| **Singleton 登記 §九 表** | 4 Track 全部 | ✅ PASS | A 重用 `_SHARED_IPC_SLOTS`（不變）；B `Lg5ReviewConsumer` style 不適用；C `is_live_release_profile` 是純 function；D `table_present` factory 是純 function — **0 新 module-level mutable singleton 需登記** |
| **0 hardcoded path** | 4 Track 全部 | ✅ PASS | `grep -E '/home/ncyu\|/Users/[a-zA-Z0-9_]+'` 9 file 0 hit |
| **0 trading.* mutate / 0 live_* mutate / 0 authorization.json touch** | 4 Track 全部 | ✅ PASS | grep 0 hit（Track C `_is_live_release_profile` 是 import alias 不是 mutation） |

---

## §3. 8 條 §九 既有 checklist（4 Track 合審）

| Item | Track A | Track B | Track C | Track D |
|---|---|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ | ✅ | ✅ + V053（自加但 PA §6 提過） | ✅ |
| 沒有 except:pass 或靜默吞異常 | ✅ noqa BLE001 標 | ✅ | ✅（pre-existing L618/L956 不是 Track 改） | N/A SQL |
| 日誌使用 %s 格式 | ✅ | N/A Rust | ✅ | N/A SQL |
| 新 API 端點有 _require_operator_role | N/A 不新增 endpoint | N/A Rust | ✅ pre-existing 不變 | N/A SQL |
| except HTTPException raise 在 except Exception 之前 | N/A | N/A Rust | ✅ pre-existing | N/A SQL |
| detail=str(e) 已改為 Internal server error | N/A | N/A Rust | ✅ pre-existing | N/A SQL |
| asyncio 路由中沒有 blocking threading.Lock | ✅ time.sleep 在 to_thread worker（F11） | N/A Rust | ✅ | N/A SQL |
| 沒有私有屬性穿透（._xxx） | ✅ | ✅ | ✅ | N/A SQL |

**全 PASS**（Track A F11 是 time.sleep 在 to_thread 內，不阻塞 event loop — 設計合理）。

---

## §4. OpenClaw 9 條特殊 review

| Item | Status |
|---|---|
| 跨平台 grep | ✅ 0 hit |
| 雙語注釋 | ✅ 9 file 全 MODULE_NOTE/Purpose/目的雙語 |
| Rust unsafe 零容忍 / unwrap 限不可恢復 / panic 不在交易路徑 | ✅ Track B Rust 0 unsafe；replay_runner 是 binary 非交易路徑 |
| 跨語言 IPC schema + serde 型別 | ✅ Track A `run_id: Option<String>` + `#[serde(default)]` 向後相容 |
| Migration Guard A/B/C | ✅ V049 A+B+C / V050 A+C / V051 A+B / V052 A+B + preflight / V053 A only（B/C N/A 因 enum-only） |
| healthcheck 配對 | ✅ Track B `[44]` 完整 wired |
| Singleton 登記 §九 表 | ✅ 0 新 singleton |
| 文件大小 800/1500 行 | ⚠️ replay_routes.py 1603 > 1500 cap（**§1 退回 Track C**）；route_helpers 891 / replay_runner 1013 / manifest_signer 958 / checks_governance 906 / runner 757 全 ≤1500 OK 但 ≥800 warn |
| Bybit API 改動先查字典 | N/A 4 Track 不觸 Bybit API |

**警告線觸發列表（800 < LOC ≤ 1500）：**
- replay_routes.py 1603（**HARD VIOLATION** — 退 Track C E1）
- replay_runner.rs 1013（warn — 含 380 LOC `#[cfg(test)] mod tests`，E1 § 6.1 提供 3 option，建議 PM/E5 看是否抽到 integration test；不阻塞）
- manifest_signer.rs 958（warn）
- route_helpers.py 891（warn）
- checks_governance.py 906（warn）

**P2 建議 ticket**：route_helpers.py / manifest_signer.rs / replay_runner.rs / checks_governance.py 後續觀察 LOC 增長，下個 Wave 若再 +50 LOC 觸 1000 警戒須 split。

---

## §5. 各 Track 詳細 finding

### Track A — spawn argv schema fix

#### F1 — Track A `_write_manifest_fixture` 缺 `ensure_ascii=False` + 缺 compact separators（HIGH future-proofing）

**位置**：route_helpers.py L591 / L595

```python
# 現況：
payload = json.loads(json.dumps(manifest_data, sort_keys=True, default=str))  # L591
fixture_path.write_text(
    json.dumps(payload, sort_keys=True, indent=2),  # L595 — indent=2 而非 compact
    encoding="utf-8",
)
```

**問題**：Track B `canonical_body_for_signing` 設計依賴 Python sibling 用 `json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False)`（manifest_signer.rs L524-531 注釋明文）。但本檔 Track A 寫 fixture 用 `indent=2` + 缺 `ensure_ascii=False` — disk bytes 與簽名時的 canonical bytes 不對齊。

**目前 attack surface 為 0**：因 Track A 寫 placeholder hash，B 端會 mismatch fail-closed（F14 cross-track 整合斷點）。但 V042 Wave 6 land 後 Track A 必須升級為**真 sign**，屆時不修就會破。

**修法（E1 補）：**
```python
# L591 deep-copy:
payload = json.loads(json.dumps(manifest_data, sort_keys=True, default=str))
payload["run_id"] = run_id

# L594-597 寫 disk — 改用 compact + ensure_ascii=False：
fixture_path.write_text(
    json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False),
    encoding="utf-8",
)
```

**Severity**：HIGH for V042 deploy；MEDIUM 現階段（attack surface 0 dev）。Track A E1 § 6.3 提到 byte-equal invariant，但只在 unit test 驗，**沒在 production code 實作**。

**E2 動作**：退回 Track A E1 補（修 ~3 行 + 加一個 unit test 驗 byte-equal）。

#### F11 — `time.sleep(1.5)` 在 sync function（acceptable）

**位置**：route_helpers.py L458

**對抗反問**：「`time.sleep` 在 async route 阻塞 event loop」— 經 grep 驗證 caller 是 `await asyncio.to_thread(_do_pg_path)` (replay_routes.py:625)，sync `_do_pg_path` 整個 wrapped 在 to_thread worker 中執行 — **time.sleep 不阻塞 event loop**。

**Severity**：N/A — 設計正確。**PASS**。

#### F13 — PA push back #2 `output_dir.basename() == manifest.run_id` 不變量（PASS）

**對抗反問**：「attacker 改 manifest data 寫 run_id 是否破解？」— Caller (`replay_routes.py:529-538`) 對 manifest_data 控制權 100%（內部 generated）；attacker 必須先入侵 Python 進程才能改 — 那時整個系統已 compromised。Rust assertion 是 sanity check 不是安全邊界。

**Severity**：N/A — 設計合理。**PASS**。

#### F14 — Track A + Track B 同 commit 後 e2e 路徑全 fail-closed（HIGH cross-track integration）

**狀況**：Track A 寫 `signature="placeholder_..."` + `manifest_hash="placeholder_..."`（L514-518 自承）；Track B fail-closed 路徑（key.hex missing → Err；canonical body hash mismatch → Err）。Linux deploy 後：
1. POST /api/v1/replay/run
2. Python 寫 placeholder hash → spawn replay_runner
3. Rust verify path：sibling key.hex 不存 → `manifest_signer_key_missing` Err → exit non-zero
4. Python poll 1.5s 偵測 returncode != 0 → UPDATE 'failed' → 503

**整個 e2e 路徑零 success rate**直到 V042 Wave 6 land（ETA 2026-05-15+）。

**Track A E1 § 5 Push Back #2 已標**，列 3 option（3a 建議 / 3b / 3c）。E2 補充：

- **PM 強制決策**：選 3a/3b/3c — 不選 PM 部署 Sprint 1 後 e2e 直接斷
- **建議 3a**：Track A 寫 placeholder（dev fail-closed 為已知 acceptable），同 commit 加文件 advisory note 提醒 operator「Sprint 1 land 後 V042 Wave 6 前 e2e 路徑全 fail-closed」
- **配套 healthcheck**：建議 healthcheck `[45]` 監測 V045 status='failed' rate；> 50% 提示 V042 未 land

**Severity**：HIGH cross-track integration（不阻塞 commit，但**不通報就部署 = 黑屏**）。

#### Track A 結論

**Verdict**：CONDITIONAL — 需 PM 決策 3a/3b/3c + E1 補 F1（ensure_ascii=False + compact） + cross-track integration risk advisory in commit message。

---

### Track B — Rust manifest signature verify path

#### F12 — Track B `manifest.signature` hex decode 失敗 mode（acceptable）

**對抗反問**：「`manifest.signature` 是 hex string，verify 內部 hex::decode 失敗會怎樣？」— Track B E1 § 6.4 已自驗：失敗在 `compute_key_fingerprint` 路徑回 `manifest_signer_key_invalid_hex`（test fail_mode_b 旁系覆蓋）。

**Severity**：N/A — 已測。**PASS**。

#### F14（同 Track A）— cross-track integration 斷點

詳見 Track A § F14。Track B fail-closed 設計**正確**（非 bug），但與 Track A placeholder hash 同 commit deploy 後 e2e 全斷。**PM 必通報**。

#### Track B 結論

**Verdict**：**PASS to E4**。Track B 自身 IMPL 邏輯正確 + 6 unit test 全綠 + 既有 8 xlang fixture 不破 + 0 forbidden symbol。F14 cross-track integration 斷點不是 Track B IMPL 問題，是 4 並行 Track 同 commit 部署 risk。

---

### Track C — Python /replay 3 critical security fixes

#### F6 — P0-2 boot guard 降級為 logging-only（MEDIUM）

**位置**：replay_routes.py L113-117

```python
if _is_live_release_profile() and os.environ.get("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "").strip():
    logging.getLogger(__name__).error(
        "REF-20 Track C P0-2 boot guard: OPENCLAW_REPLAY_VERIFY_TEST_KEY set "
        "with OPENCLAW_RELEASE_PROFILE=live; live ignores test key (forced empty)."
    )
```

**問題**：PA spec L133 明文要求「**raise** 若 `OPENCLAW_REPLAY_VERIFY_TEST_KEY` 在 environ（fail-closed boot guard）」。E1 改成 log ERROR 沒 raise — **PA spec drift**。

**對抗反問**：「per-route 確實 force-clear，所以 boot guard 沒 raise 也 OK？」— 弱點：若有 caller 繞過 per-route gate（直接 import `_ms.create_archive_with_test_key()` 之類），boot guard 是 last line of defense。

**修法（E1 補）：**
```python
if _is_live_release_profile() and os.environ.get("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "").strip():
    raise RuntimeError(
        "REF-20 Track C P0-2 boot guard: OPENCLAW_REPLAY_VERIFY_TEST_KEY set "
        "with OPENCLAW_RELEASE_PROFILE=live; live MUST NOT honor test key. "
        "Unset OPENCLAW_REPLAY_VERIFY_TEST_KEY before starting uvicorn."
    )
```

**Severity**：MEDIUM（per-route 已是首道防線，但 PA spec 明文要 raise）。

#### F8 — `replay:read:any` scope 未在 default `auth_scopes` 註冊（HIGH）

**位置**：auth.py L184-233（default scopes definition）+ replay_routes.py L296（`_actor_can_read_any_replay_report` check）

**狀況**：Track C 引入 `replay:read:any` scope 作 IDOR admin bypass — 但 auth.py 預設 scope set 沒列。沒有任何 actor 能取得這個 scope（除非 operator 顯式設 `OPENCLAW_AUTH_SCOPES` env 加上）— 預設情境下 admin bypass **永遠關閉**。

**對抗反問**：「fail-closed default 不是好事？」— 是，但 **operator 不知道怎麼啟用**。Track C E1 報告 § 8 deployment notes 沒提加 scope 步驟。

**修法選項（E1 補 + PM 決策）：**

選項 A（建議）：把 `replay:read:any` 加到 auth.py default scopes（operator role 預設可用）：
```python
# auth.py L221 後加：
"replay:read:any",  # Track C P0-5a IDOR admin bypass for cross-actor incident investigation
```

選項 B：Track C 報告 § 8 補 deploy 文件（operator 須 export `OPENCLAW_AUTH_SCOPES=...,replay:read:any`）+ 加註 deploy runbook。

**E2 建議選 B**（fail-closed 預設更安全，但需明確 deploy 文件）。

**Severity**：HIGH（PA spec L141 設計意圖是 admin bypass 可工作，E1 IMPL 後無人能取得 scope = 功能失效）。

#### F2 — V053 enum DROP+ADD 無 LOCK TABLE / BEGIN/COMMIT（MEDIUM）

**位置**：sql/migrations/V053__governance_audit_log_replay_event_types.sql L123-194

**狀況**：V044 已 land 的 DROP+ADD CHECK pattern 被 E3 P1-3 flag 為「DROP+ADD enum 非原子問題 + race window」。V053 沿用該 pattern，**沒加 LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE 在 DROP 前**。

**對抗反問**：「DROP CONSTRAINT 自動拿 ACCESS EXCLUSIVE lock，race window 不存在？」— Postgres ALTER TABLE DROP CONSTRAINT 拿 ACCESS EXCLUSIVE 直到 statement 完成，**release lock**，下一個 ALTER ADD CONSTRAINT 再取一次 lock。**兩個獨立 ALTER 之間 lock 確實 release，concurrent INSERT 可在 window 內寫入 invalid event_type**（CHECK 暫時不存在）。

**修法（E1 補）：**
```sql
-- 把 DROP + ADD 包在 single DO block 加 LOCK：
DO $$
BEGIN
    LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;
    -- 然後 DROP IF EXISTS + ADD CONSTRAINT ...
END $$;
```

**Severity**：MEDIUM（attack window 短，attacker 必須已能寫 governance_audit_log，但同 pattern 已被 E3 P1-3 flag — 一致性要求修）。

#### Track C 結論

**Verdict**：**RETURN to E1**

**E1 必修清單（按優先序）：**
1. **§九 1500 hard cap 違規（HIGH）**：抽 P0-2/P0-4/P0-5 三 endpoint body 到 `replay/security_guards.py`，目標 replay_routes.py ≤1500 LOC
2. **F8 replay:read:any scope（HIGH）**：選 A 加 default scope 或 B 補 deploy doc
3. **F6 boot guard 升 raise（MEDIUM）**：5 行修改
4. **F2 V053 加 LOCK TABLE（MEDIUM）**：V053 改 single DO block + LOCK TABLE，重跑 idempotent test 驗證

預估 E1 工時：~6 hours。

---

### Track D — V049-V052 schema migrations

#### F4 — V052 preflight LEFT JOIN 在 0 row 場景（acceptable）

**對抗反問**：「Linux runtime 0 row 場景 preflight 是否還能跑？」— V052 preflight L193-231 用 `SELECT COUNT(*) ... WHERE e.experiment_id IS NULL` — 0 row 場景 COUNT=0 → PASS（不 abort）。**設計合理**。

**Severity**：N/A — 已測。

#### F9 — V049 CHECK NULL 寬容（LOW）

**狀況**：V049 chk_window_no_overlap L505-528 三 pair NULL 寬容 — 任一邊 NULL 即跳過。實際 use case：研究階段三 window 可能 NULL → CHECK 不擋。

**E1 § 5 #1 已自承**：「實際 use case 中 V045 row 可能寫 candidate_window NULL（research 階段）；此時 EXCLUDE 不生效，CHECK chk_window_no_overlap 仍守 intra-row」。

**對抗反問**：「V3 §4.1 有沒有強制三 window NOT NULL？」— V3 §4.1 列了 22 col 但未明文 window 必 NOT NULL（候選 window 可空於 baseline experiment）— **設計與 spec 一致**。

**Severity**：LOW（不阻塞）。

#### F10 — V049 ALTER COLUMN TYPE 對既有 row 風險（acceptable）

**對抗反問**：「ALTER COLUMN TYPE 對 production 來說是 rewriting full table，會拿 ACCESS EXCLUSIVE lock 直到完成 — 大表會卡？」— V049 Guard B 確認 V041 stub Linux 0 row（PA Sprint 1 panorama 已驗）+ `regex` 驗 UUID-castable + RAISE EXCEPTION on mismatch。0 row → ALTER TYPE 是 instant no-op。

**Severity**：N/A — 已守。

#### V051 paired CHECK 對既有 row 兼容性（PASS）

**對抗反問**：「既有 mlde_shadow_recommendations row 是否違反 paired CHECK 致 ADD CONSTRAINT fail？」— V038/V039/V040 三步把所有既有 row 設為 `evidence_source_tier='real_outcome'` — V051 ADD COLUMN 後兩新欄為 NULL，paired CHECK 第一分支「real_outcome AND replay_experiment_id NULL AND manifest_hash NULL」自動滿足。**設計合理**。

但 **deploy precondition**：若 V040 land 後 + V051 land 前的窗口有 producer 寫 `evidence_source_tier='calibrated_replay'` + 兩欄 NULL（既有 producer 未升級寫 V049 lineage），V051 CHECK ADD 會 fail。需 PA panorama 確認 0 calibrated_replay row 才安全。Linux 0 row（V051 前無 producer）→ 安全。

**Severity**：N/A — Linux 0 row 場景安全。

#### Track D 結論

**Verdict**：**PASS to E4 with caveats**

**deploy caveats（PM 通知 operator）：**
1. V052 部署前 必先跑 V052_preflight.sql 真實驗 0 dangling
2. V051 部署前 確認 0 `evidence_source_tier='calibrated_replay'` row（既 V040 後無 producer，安全）
3. V049 ALTER COLUMN TYPE 只對 0 row 表 instant no-op；確認 _sqlx_migrations 寫入後 engine restart 前避觸 P0 sqlx hash drift

---

## §6. 對抗反問結果總表

| # | 反問 | 對 Track | 結果 |
|---|---|---|---|
| 1 | A `time.sleep(1.5)` 真擋 Linux release binary cold cache？ | A | ⚠️ 1.5s 估計足夠（cold start 200-800ms）但無實測 — F11 acceptable，F12 cross-track 重要更急 |
| 2 | A `output_dir.basename()` invariant 是否擋 attacker 改 run_id？ | A | ✅ Caller 控 manifest_data 100%；attacker 必先入侵 Python 進程，那時系統已 compromised — Rust assert 是 sanity 不是安全邊界 |
| 3 | B verify 兩邊都 verify（不能只 verify 其一）？ | B | ✅ replay_runner.rs `signer.verify(&canonical_body, &manifest.manifest_hash, &manifest.signature, ...)` 兩 disk-supplied 都當 expected；canonical body hash sanity gate 在 verify 前抓 mismatch |
| 4 | B key.hex 缺 hard error 後 dev workflow cold start 怎工作？ | B | ⚠️ V042 land 前 dev/Linux 需手動部署 sibling key.hex；Track B § 6.2 已標 + healthcheck `[44]` 監測 |
| 5 | C `is_live_release_profile()` env var attacker 控？ | C | ⚠️ attacker 控 env 即可改 profile；但 attacker 控 env 已是 high-priv 入侵 — 等於要 attacker 已 compromised systemd / launchd 配置；防線退到 OS 層 |
| 6 | C `_verify_replay_runner_pid` cmdline 邊界（PID-1 init）？ | C | ✅ psutil cmdline 對 init/postmaster 不會包含 'replay_runner' substring → 擋住 |
| 7 | C `Path.resolve().is_relative_to` 對 symlink 攻擊？ | C | ✅ resolve 解 symlink 後對比 root；attacker 寫 symlink 到 /etc 仍會被 resolve 解開外部 path → is_relative_to FALSE |
| 8 | D V049 EXCLUDE GIST 真擋三 pair overlap？ | D | ⚠️ E1 自承 EXCLUDE 是 inter-row（experiment_id WITH = 對 PK 是 demo），intra-row 三 pair 由 chk_window_no_overlap CHECK 守 — **設計合理 + spec 一致** |
| 9 | D V051 paired CHECK 對既有 row 兼容？ | D | ✅ V040 後既有 row 全 'real_outcome' → 第一分支自動滿足 |
| 10 | D V052 preflight 0 row 場景跑得起來？ | D | ✅ COUNT=0 → PASS not abort；Linux _sqlx_migrations max=35 確認 0 row |

---

## §7. PM 決策清單（按優先序）

1. **§九 1500 hard cap enforce**（P0）：拒絕 Track C E1 baseline exception 申請 — 退回 E1 補 LOC extract（F: §1）
2. **F8 replay:read:any scope 未註冊**（P0）：選 auth.py 加 default scope 或 deploy doc 補 — 退回 E1
3. **F6 P0-2 boot guard 降級為 log**（P1）：退回 E1 補 raise
4. **F2 V053 enum DROP+ADD 無 LOCK TABLE**（P1）：退回 E1 補 single DO block + LOCK TABLE
5. **F1 Track A `ensure_ascii=False` 缺**（P1）：退回 E1 補 + 加 byte-equal unit test
6. **F14 Track A + B cross-track integration 斷點**（P0 advisory）：PM 必通報 operator「Sprint 1 land 後 V042 Wave 6 前 e2e 路徑全 fail-closed」+ commit message 加 known-issue note
7. **Track D PASS** + caveats（V051 / V052 deploy precondition）

---

## §8. PM 操作建議

### 退回 Track C E1（必須）

派 sub-agent 修 4 條 finding（按優先序）：
1. §九 LOC extract（~1 day）
2. F8 replay:read:any 選項 A 或 B（~1 hour）
3. F6 boot guard raise（~10 min）
4. F2 V053 LOCK TABLE（~30 min）

### Track A E1 補（建議併入下一輪）

1. F1 ensure_ascii=False + compact separators（~30 min）
2. byte-equal unit test（~30 min）

### Track B / Track D 接 E4（並行）

兩 Track 自身 IMPL 邏輯正確，可派 E4 跑 regression。E4 注意：
- Track B：跑 cargo test + 8 xlang fixture + nm forbidden symbol scan
- Track D：跑 V049-V052 dual-apply idempotent + V052_preflight 真 PG smoke

### Final commit 順序

E2 退 E1 → E1 修 → E2 重審 → 4 Track E4 → PM commit

---

## §9. 不要 commit / push 注意事項

E2 review 結果為 RETURN to Track C E1 + advisory advisory to Track A — **不要進 commit**。等 E1 修完 + E2 重審後，PM 再決定一次 commit 還是分批。

E2 自己 0 直接補 — 0 typo / dead import / unused variable found。Pre-existing `except Exception: pass` (L618 / L956) 不是 4 Track 改動，不在 E2 範圍。

---

## §10. 證據鏈（grep + pytest 結果）

```bash
# LOC count
$ wc -l <changed files>
1603 replay_routes.py    ← OVER §九 1500 hard cap by 103
1013 replay_runner.rs    ← warn 800
 958 manifest_signer.rs  ← warn 800
 906 checks_governance.py ← warn 800
 891 route_helpers.py    ← warn 800
 757 runner.py           ← OK
4 V### + 1 preflight     ← all <800

# Cross-platform path grep
$ grep -nE '/home/ncyu|/Users/[a-zA-Z0-9_]+' <changed files>
0 hit

# Hard boundary grep
$ grep -nE 'live_execution_allowed|max_retries|execution_authority|system_mode|OPENCLAW_ALLOW_MAINNET|authorization\.json' <changed files>
0 hit

# Trading.* mutate / live_* mutate
$ grep -nE 'INSERT INTO trading\.|UPDATE trading\.|DELETE FROM trading\.' <changed files>
0 hit

# Cross-track contracts
$ grep -nE 'verify_replay_runner_pid' <Python>
route_helpers.py:605 def verify_replay_runner_pid(pid)
route_helpers.py:889 "verify_replay_runner_pid" (in __all__)
replay_routes.py:103 _verify_replay_runner_pid = _rh.verify_replay_runner_pid
replay_routes.py:911 pid_ok, pid_err = _verify_replay_runner_pid(int(pid))

$ grep -nE 'ENVELOPE_KEYS_FOR_SIGNING|canonical_body_for_signing' manifest_signer.rs
574 pub const ENVELOPE_KEYS_FOR_SIGNING: [&str; 3] = ["signature", "manifest_hash", "signature_key_ref"]
594 pub fn canonical_body_for_signing(disk_bytes: &[u8]) -> Result<Vec<u8>, serde_json::Error>

$ grep -nE 'replay:read:any' auth.py
0 hit  ← F8 finding：scope 未在 default 註冊

# Track A + C pytest live run
$ pytest tests/test_replay_routes_track_c_security.py replay/tests/test_track_a_spawn_argv.py
24 passed in 0.22s

# Sibling regression
$ pytest tests/test_replay_routes_t2_subprocess.py tests/test_replay_routes_t2_pg_advisory_lock.py tests/test_replay_routes_safe_query_audit.py tests/test_replay_routes_auth.py
23 passed in 0.29s

# main import
$ python3 -c "from app.main import app; print('routes:', len(app.routes))"
routes: 250

# Rust check
$ cargo check --bin replay_runner --features replay_isolated
Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.26s
21 pre-existing warnings (NOT Track B introduced)

# requirements.txt
$ grep psutil program_code/.../requirements.txt
43:psutil>=5.9.0
```

---

## §11. 總結

**RETURN to E1**（Track C 必須修）+ Track A 配套修 + Track B/D PASS to E4。

PM autonomous mode dispatch 的核心要求「W3-W9 跳過 E2 chain 後第一份正式 E2，不得 rubber-stamp」— 本份 E2 對 4 Track 各列 ≥2 條 finding（含 PASS 帶證據鏈）：
- Track A：F1（HIGH 退）+ F11/F13 PASS + F14（cross-track HIGH 通報）
- Track B：F12 PASS + F14（cross-track HIGH 通報）
- Track C：F6（MEDIUM 退）+ F8（HIGH 退）+ F2（MEDIUM 退）+ §九 LOC（HIGH 退）
- Track D：F4/F10 PASS + F9 LOW + V051/V052 PASS with deploy caveats

預估 E1 補修工時：~8 hours total（Track C 6h + Track A 1h + Track D 1h verification）。

---

E2 REVIEW DONE: RETURN to E1（Track C 必修，Track A 建議補，Track B/D PASS to E4） · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_sprint1_4track_review.md`
