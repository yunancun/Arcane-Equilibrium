# 2026-05-09 — ml_training cron IPC __auth fix E2 對抗 review

**Agent**：E2 (Senior Code Reviewer / Adversarial Auditor)
**E1 commit**：`3d8d543e fix(ml-training): IPC __auth handshake to unblock optuna param_ranges`
**E1 docs commit**：`fac9e386 docs(e1): ml_training cron IPC __auth fix RCA report + memory`
**Mac HEAD now**：`fac9e386`（Linux 稍領先 `fa9788b7` ci change，與本 fix 解耦）
**Verdict**：**RETURN-TO-E1**（1 HIGH + 2 LOW）

---

## 改動範圍

| 檔 | 行 | 內容 |
|---|---|---|
| helper_scripts/cron/ml_training_maintenance_cron.sh | +9 | 注入 `OPENCLAW_IPC_SECRET_FILE` (line 52-59) |
| program_code/ml_training/optuna_optimizer.py | +98/-33 | `_resolve_ipc_secret` (line 296-312) + `_read_response_line` (line 315-326) + `_send_ipc_command` 改寫 (line 329-421) |

LOC：946 → 1011（+65；§九 800-2000 軟區間）。

---

## 對抗反問結果（6 條全跑）

### Q1 `_resolve_ipc_secret` 與 `secret_runtime.get_secret_value` 行為等價性

PASS。逐條對比：

| 條件 | get_secret_value (基準) | _resolve_ipc_secret (E1 fix) | 一致 |
|---|---|---|---|
| 直接 env truthy | `if value: return value` | `if direct: return direct` | ✓ |
| 直接 env empty `""` | falsy → fallback | falsy → fallback | ✓ |
| FILE env truthy | `os.environ.get(f"{name}_FILE", "").strip()` | `os.environ.get("OPENCLAW_IPC_SECRET_FILE", "").strip()` | ✓ |
| FILE 空字串 | `if not file_path: return None` | 同 | ✓ |
| 讀 file | `Path(file_path).read_text(encoding="utf-8").strip()` | 同 | ✓ |
| OSError | `except OSError: return None` | 同 | ✓ |
| 空 file content | `secret or None` | `... .strip() or None` | ✓ |

multi-source 優先序：env-first / file-fallback。與 ipc_client 完全同步。

### Q2 `_send_ipc_command` 與 `ipc_client._authenticate` wire format byte-equal

PASS（11/11 細項 byte-equal）。詳 memory.md lesson 32 的對照表。

唯一差別：E1 fix 多 1 條 `result.authenticated == true` strict check（line 396-399）。基準 ipc_client._authenticate (line 625) 只檢查 `resp.get("error")`，沒驗 `authenticated=true`。E1 是 over-strict 方向（fail-closed），accept。Rust engine connection.rs:183 確認成功路徑永遠回 `{"authenticated":true}`，over-strict 不會誤殺。

### Q3 5/10 03:17 cron 真實 secret 解析

PASS。模擬 cron 隔絕 env：

```bash
ssh trade-core "env -i HOME=/home/ncyu PATH=/usr/bin:/bin OPENCLAW_BASE_DIR=\$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw bash -c '<inline cron.sh secret resolve logic>'"
```

返回 `RESOLVED=/home/ncyu/BybitOpenClaw/secrets/environment_files/ipc_secret.txt`。

證明 cron 環境（不繼承 daemon shell env）下：
- `$HOME` cron 內建 = `/home/ncyu`（per `/etc/passwd`）
- `OPENCLAW_SECRETS_ROOT` unset → cron.sh:28 fallback `$HOME/BybitOpenClaw/secrets`
- `IPC_SECRET_FILE_DEFAULT` = `/home/ncyu/BybitOpenClaw/secrets/environment_files/ipc_secret.txt`
- `[[ -z ${OPENCLAW_IPC_SECRET_FILE:-} && -f $IPC_SECRET_FILE_DEFAULT ]]` → true → export

restart_all.sh:62 同 path source-of-truth byte-equal aligned。

### Q4 ml_parameter_suggestions=0 真因 = fills<80 嗎？

PASS — IPC 200 OK 真通過，業務樣本不足是真因。

證據：
- log line 2026-05-09 20:22:34: `Insufficient fills for optimization: 25 < 80 required. Skipping. / 成交數不足: 25 < 80，跳過優化。`
- status_json: `param_ranges_source: 'ipc'`（fix 前是 `unavailable:RuntimeError`）+ `result.status: 'insufficient_data'`

「IPC silent fall through」假說 = REFUTED。fix 後 source 從 `unavailable:RuntimeError` → `ipc`，明確證實業務分支正確路由到 fills<80 insufficient_data。

### Q5 三端同步 + bilingual + commit-即-push

| 項 | 狀態 |
|---|---|
| Mac HEAD | fac9e386 |
| origin/main | fa9788b7（領先 Mac，本 fix 不在領先 commit chain 內） |
| Linux trade-core | fa9788b7（與 origin 同步） |
| 本 fix `3d8d543e` 三端皆有 | ✓ |
| commit message 含 RCA 一句話 | ✓ (16 line body) |
| 注釋默認中文（2026-05-05 governance） | ✓ docstring + inline 純中文 |
| 錯誤訊息中英並列（line 324 + 416） | LOW-1（cosmetic，不違規） |

### Q6 regression-testing-protocol

FAIL → HIGH-1。E1 自報「9/9 unit test pass」但 commit `3d8d543e --stat` 0 test file added/modified。

```
helper_scripts/cron/ml_training_maintenance_cron.sh   |   9 ++
program_code/ml_training/optuna_optimizer.py          | 131 ++++++--
2 files changed, 107 insertions(+), 33 deletions(-)
```

既有 test_optuna.py mtime = Apr 20（pre-fix），grep 0 line 涉 ipc/secret/auth/hmac。E1 ad-hoc inline 跑沒 commit。

「fail-closed 不 silent skip」測試覆蓋亦缺。

---

## 8 條 §九 checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 RCA 一致 | ✓ |
| 沒有 except:pass 或靜默吞異常 | ✓（`except OSError: return None` 是顯式 fail-soft，不是吞異常） |
| 日誌使用 %s 格式 | n/a 無新 logger.info |
| 新 API 端點有 _require_operator_role() | n/a 非 API endpoint |
| except HTTPException 在 except Exception 之前 | n/a 無新 except 鏈 |
| detail=str(e) 已改為 "Internal server error" | n/a 非 user-facing HTTP detail |
| asyncio 路由中沒有 blocking threading.Lock | ✓ `_send_ipc_command` 是 sync，cron 後台 thread 跑（line 336 docstring 明示） |
| 沒有私有屬性穿透 | ✓ |

---

## 9 條 OpenClaw 特殊 checklist

| Item | 狀態 |
|---|---|
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✓ 0 hard-coded user home |
| 雙語注釋（2026-05-05 後改默認中文） | ✓ 新加 docstring 純中文；△ 錯誤訊息 line 324/416 仍中英並列（LOW-1） |
| Rust unsafe 零容忍 | n/a Python only |
| 跨語言 IPC schema | ✓ wire format byte-equal aligned with ipc_client._authenticate（11/11 細項 PASS） |
| Migration Guard A/B/C | n/a 無 SQL migration |
| healthcheck 配對 | n/a 非被動等待 TODO |
| Singleton 登記 §九 表 | ✓ 無新 singleton |
| 文件大小 800/2000 | △ 1011 行 > 800 警告（LOW-2） |
| Bybit API 改動 | n/a 不涉 |

---

## Findings

| # | 嚴重性 | 位置 | 描述 | 修復建議 |
|---|---|---|---|---|
| HIGH-1 | HIGH | program_code/ml_training/tests/ | E1 自報「9/9 unit test 通過」但 commit `3d8d543e --stat` 0 test file added/modified；既有 test_optuna.py 0 line 涉 ipc/secret/auth/hmac | 補 program_code/ml_training/tests/test_optuna_ipc_handshake.py：(1) `_resolve_ipc_secret` 5 case (env-only / file-only / both / empty / OSError) (2) `_send_ipc_command` mock socket 4 case (auth-then-business / no-secret-skip-auth / auth-rejected-RuntimeError / authenticated=false-RuntimeError) (3) byte-equal vs ipc_client._authenticate 1 case (token + ts + json shape 對齊) |
| LOW-1 | LOW | optuna_optimizer.py:324, 416 | 錯誤訊息中英並列；2026-05-05 governance 廢除 bilingual mandate，新加默認中文 | E1 commit-after-fix 順帶清；E2 不單獨 RETURN |
| LOW-2 | LOW | optuna_optimizer.py 整檔 | 1011 行 > 800 警告線；pre-existing baseline 946（已超過警告）+ 65 增量；§九 pre-existing exception 僅針對 2000+ violation | P2 ticket：拆 `_resolve_ipc_secret` + `_read_response_line` + `_send_ipc_command` 至 `program_code/ml_training/_ipc_helpers.py`（IPC helper 與 TPE optimizer / PG writer 邊界天然存在） |

---

## 退回 E1 修復清單（HIGH-1）

E1 必跑：

```bash
cd ~/BybitOpenClaw/srv

# 補 regression test
cat > program_code/ml_training/tests/test_optuna_ipc_handshake.py <<'EOF'
"""IPC __auth handshake regression test for optuna_optimizer.

對應 commit 3d8d543e 的 fix；確保 wire format 與 ipc_client._authenticate
byte-equal 對齊不變式 + fail-closed 不 silent skip 不變式。
"""
# ... 參見 ipc_client/tests/test_ipc_client_hmac_ts_unit.py 的 FakeSocket pattern
EOF

# 跑 + commit
python3 -m pytest program_code/ml_training/tests/test_optuna_ipc_handshake.py -v
git add program_code/ml_training/tests/test_optuna_ipc_handshake.py
git commit -m "test(ml-training): regression for IPC __auth handshake (commit 3d8d543e)"
git push origin main
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"
```

最少 9 case（對齊 E1 自報的 9 unit test）+ 1 case 「secret 設置但 server reject auth → RuntimeError 不 silent skip」(fail-closed 不變式驗證)。

---

## 5/10 03:17 cron real-fire 監控

```bash
# 1. cron fire 確認
ssh trade-core "tail -50 /tmp/openclaw/logs/ml_training_maintenance_cron.log | grep '2026-05-10 03:1'"

# 2. IPC handshake 通過
ssh trade-core "cat /tmp/openclaw/status/ml_training_maintenance_status.json | jq '.jobs[] | select(.job==\"optuna_optimizer\") | {status, param_ranges_source: .detail.param_ranges_source, error}'"
# Expected: status=ok / param_ranges_source=ipc / error=""
# FAIL: status=skipped / param_ranges_source=unavailable:RuntimeError → cron 環境注入失敗

# 3. Sunday weekday=6 五個 audit job 自然 fire
ssh trade-core "cat /tmp/openclaw/status/ml_training_maintenance_status.json | jq '.jobs[] | select(.job | IN(\"thompson_sampling\",\"optuna_optimizer\",\"cpcv_validator\",\"dl3_foundation\",\"weekly_report_generator\")) | {job, status}'"

# 4. PG 4 表 row count delta（明天 cron 後）
ssh trade-core "psql trading_ai -c \"SELECT 'bayesian_posteriors' AS tbl, COUNT(*) FROM learning.bayesian_posteriors UNION ALL SELECT 'ml_parameter_suggestions', COUNT(*) FROM learning.ml_parameter_suggestions UNION ALL SELECT 'foundation_model_features', COUNT(*) FROM learning.foundation_model_features UNION ALL SELECT 'weekly_review_log', COUNT(*) FROM learning.weekly_review_log;\""
```

---

## 結論

RETURN to E1（1 HIGH + 2 LOW）。

業務邏輯（IPC __auth handshake / wire format / cron secret 注入）**全部 PASS**。退回原因 = process gap：sign-off 自報 9/9 unit test 但 0 test file commit 進 repo，下次 CI 不 catch + 將來 wire-equal 不變式破壞無 regression 守。

E1 補 regression test commit 後重 E2 → 通過 → E4 回歸。

**E2 REVIEW DONE: RETURN-TO-E1 · report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-09--ml_training_cron_ipc_fix_e2_review.md**
