# 2026-05-09 — ml_training cron IPC __auth fix Round 2 E2 對抗 review

**Agent**：E2 (Senior Code Reviewer / Adversarial Auditor)
**Round 2 commit**：`1448e0a1 test(ml-training): IPC __auth handshake regression + LOW-1 cleanup`
**Round 1 (business logic)**：`3d8d543e` — E2 round 1 verdict 已 PASS（11/11 byte-equal）；本 round 2 範圍 = test 補洞 + LOW-1 清理
**E2 round 1 review**：`b3607c10`（1 HIGH + 2 LOW）
**Verdict**：**APPROVED**

---

## 改動範圍

| 檔 | 變動 | LOC |
|---|---|---|
| program_code/ml_training/tests/test_optuna_ipc_handshake.py | 新檔（12 test method / 4 case group） | +557 |
| program_code/ml_training/optuna_optimizer.py | LOW-1 line 324 + 416 中英並列 → 純中文 | -1（1011 → 1010） |
| docs/CCAgentWorkSpace/E1/memory.md | 追加 round 2 lesson | +35 |
| docs/CCAgentWorkSpace/E1/workspace/reports/...round2... | 新檔 self-report | +190 |

無業務代碼變更（除 LOW-1 純中文化兩行 error message）。

---

## HIGH-1 closure 證據（test 真覆蓋 4 case group，獨立驗證）

E2 不採信 E1 自報，獨立 read test source + 真跑 + 真做對抗 mutation。

### (a) `_resolve_ipc_secret` 5 case 真覆蓋

| Case | 函數 line | 行為 | 對應 ipc_client.secret_runtime.get_secret_value |
|---|---|---|---|
| `test_resolve_ipc_secret_env_var_direct` | optuna_optimizer.py:303-304 `if direct: return direct` | env truthy 直返 | ✓ env-first |
| `test_resolve_ipc_secret_file_fallback` | :306-310 file path 讀檔 | file fallback | ✓ file-fallback |
| `test_resolve_ipc_secret_missing_file_returns_none` | :311-312 `except OSError: return None` | OSError fail-soft | ✓ fail-soft |
| `test_resolve_ipc_secret_strips_trailing_whitespace` | :310 `.strip()` | trailing `\n\t \n` 必 strip | ✓ HMAC sensitivity 守 |
| `test_resolve_ipc_secret_env_takes_precedence_over_file` | :303-308 fall-through 順序 | env > file | ✓ multi-source 順序 |

**結論**：5/5 真覆蓋設計表中 5 條 ipc_client 對齊行為（env-first / file-fallback / OSError None / strip / 雙設置優先序）。

### (b) `_send_ipc_command` mock socket 4 case 真覆蓋

| Case | 函數 line | 不變式 | 真覆蓋 |
|---|---|---|---|
| `test_send_ipc_command_no_secret_skips_auth` | :369-399 `if secret:` 不進 → 直送 business | 無 secret = 1 wire（business only） | ✓ wire 計數 1 + 內容驗證 |
| `test_send_ipc_command_with_secret_auth_then_business` | :369-410 完整 happy path | 2 wire（__auth id=0 + business id=1）+ recv 2 reply 解析 result | ✓ wire 計數 2 + id/method 對齊 |
| `test_send_ipc_command_auth_error_response_raises` | :391-395 `if "error" in auth_resp` | server 回 JSON-RPC error → RuntimeError + match `IPC __auth rejected.*-32600` | ✓ pytest.raises + regex match |
| `test_send_ipc_command_socket_timeout_raises` | _read_response_line 內部 sock.recv 噴 socket.timeout | timeout 必 propagate（不可吞回 None / {}） | ✓ pytest.raises((socket.timeout, TimeoutError, OSError)) |

**結論**：4/4 真覆蓋。case 1 隱含驗 fail-closed 不變式 — 「無 secret = skip auth = 直送 business」當前語義被凍結，未來「順手加 fake __auth」會破 wire 計數 assertion。

### (c) Wire format byte-equal 1 case 真比對 byte sequence

讀 test source line 410-478，確認 **不是 stub**：

```python
expected_token = _hmac_lib.new(
    secret.encode("utf-8"),
    str(frozen_now).encode("utf-8"),
    hashlib.sha256,
).hexdigest()
reference_request = {
    "jsonrpc": "2.0",
    "method": "__auth",
    "params": {"token": expected_token, "ts": frozen_now},
    "id": 0,
}
reference_payload = (
    json.dumps(reference_request, separators=(",", ":"), ensure_ascii=False)
    + "\n"
).encode("utf-8")

actual_wire1 = fake.sent_payloads[0]
assert actual_wire1 == reference_payload, ...
```

**真 byte sequence 比對** — `actual_wire1 == reference_payload`（line 469）逐字節比；frozen_now=1_700_000_000 凍結 time.time；HMAC 真跑 hashlib.sha256；reference 與 ipc_client._authenticate（line 595-614）byte-equal 構造同源。

對抗 mutation 真驗（E2 自跑）：把 `optuna_optimizer.py:386-388` 的 `json.dumps(auth_req, separators=(",", ":"), ensure_ascii=False)` 改成 `json.dumps(auth_req)`（默認帶空格分隔）→ (c) 立即 RED：

```
E   actual:    b'{"jsonrpc": "2.0", "method": "__auth", ...}'
E   reference: b'{"jsonrpc":"2.0","method":"__auth",...}'
E   At index 11 diff: b' ' != b'"'
FAILED test_send_ipc_command_auth_wire_byte_equal_to_ipc_client
```

**結論**：byte-equal 不變式對 separators drift 真實守門（不是 stub）。

### (d) Critical fail-closed 不變式 1 主 + 1 補強

對抗 mutation 真驗（E2 不採信 E1 自報，自跑）：

把 `optuna_optimizer.py:396-399` 改成 `if not auth_resp.get("result", {}).get("authenticated"): return {}` →

```
FAILED test_send_ipc_command_authenticated_false_raises_no_silent_skip
  Failed: DID NOT RAISE <class 'RuntimeError'>
FAILED test_send_ipc_command_missing_authenticated_key_raises
  Failed: DID NOT RAISE <class 'RuntimeError'>
```

**(d) 兩個 case 立即 RED 標明「DID NOT RAISE RuntimeError」** — 證實這兩條對 future commit 把 `raise RuntimeError` 改成 silent return 的反模式有實際守門能力。

E1 自報的 「pass / return {} 兩輪 mutation 」屬實，E2 獨立重現一致。

---

## Mock 不掩蓋邏輯結論

逐項驗證 brief 點到的 4 條：

| 項 | 結論 |
|---|---|
| socket mock 真模擬 wire frame 還是 stub return True | **真 wire** — `_FakeSocket.sendall` 捕真 bytes（line 203-204）；`recv(n)` 按 line 切片返回 newline-delimited JSON-RPC reply（line 206-214）；`fake.sent_payloads` 是 list of bytes 真供 (c) byte-equal assert |
| HMAC 真跑 hashlib.hmac.new 還是 stub assert hash == "xxx" | **真跑** — test line 451-455 真調用 `_hmac_lib.new(secret.encode("utf-8"), str(frozen_now).encode("utf-8"), hashlib.sha256).hexdigest()`，再 line 469 byte-equal compare |
| timeout case 真 raise socket.timeout 還是 fake time.sleep + early return | **真 raise** — `_TimeoutSocket.recv` (line 380-382) `raise socket.timeout("recv timeout")`；無 sleep / early return |
| (a)/(b)/(c)/(d) 是否有任何隱形 stub 走 happy assert | **零隱形 stub** — 所有 case 都 monkey-patch `socket.socket` 為 `_FakeSocket` 構造，sendall 捕 bytes、recv 噴 reply queue 或 raise；assert 對齊 byte/wire-count/exception type，非 truthy / mocked-method-called 之類 surface assert |

---

## LOW-1 closure 證據

E1 round 1 對應 line 324（_read_response_line 內 ConnectionError）+ line 416（_send_ipc_command 業務 error 分支 RuntimeError）。

```diff
-            raise ConnectionError("Socket closed before response / 響應前套接字已關閉")
+            raise ConnectionError("響應前套接字已關閉")

-            raise RuntimeError(
-                f"IPC error [{err.get('code')}]: {err.get('message')} / "
-                f"IPC 錯誤 [{err.get('code')}]: {err.get('message')}"
-            )
+            raise RuntimeError(
+                f"IPC 錯誤 [{err.get('code')}]: {err.get('message')}"
+            )
```

E2 grep `grep -nE 'Socket closed|IPC error \[' program_code/ml_training/optuna_optimizer.py` exit 0 / 0 hit — 無英文殘留。

E1 留了 line 394 `f"IPC __auth rejected [{err.get('code')}]: {err.get('message')}"` 為純中文化中性的純技術消息（method name `__auth` 是 wire-level 識別符，不是英文敘述）— acceptable。

中文 punctuation 通順：`響應前套接字已關閉` / `IPC 錯誤 [code]: message`，無語法瑕疵。

---

## Regression risk 評估

| 維度 | 結果 |
|---|---|
| **12 test method run time** | Linux 0.14s 全跑（每 test ~12ms 含 setup/teardown）— 無 CI cost 影響 |
| **外部依賴** | 純 monkeypatch + tmp_path + _FakeSocket — 無真 socket / 真 PG / 真 Bybit；不 flake |
| **既有 ml_training 測試衝突** | Linux baseline 398 passed / 29 skipped / 0 fail（含本 12 新 test）— 0 regression |
| **與 ipc_client/test_ipc_client_hmac_ts_unit.py 重複 mock pattern** | 對齊但不重複 — `_FakeSocket` 的 recv 行為（按 line 切片釋出）刻意對齊 `_send_ipc_command` 的 `IPC_RECV_BUFFER` 模式（一次 recv 取整 line）；ipc_client 端用 `recv(1)` 逐字節讀 → 兩個 fake 互不衝突 |
| **不依賴 optuna**（test 注釋 line 38-40 + Mac 跑時不 skip） | ✓ test_optuna.py 整檔 importorskip("optuna") skip；本 test 直接 from optuna_optimizer import 三 helper（IPC helper 不依賴 optuna）— Mac 無 optuna 也跑全 12 case |

---

## bilingual 注釋政策驗證（2026-05-05 governance）

| 範圍 | 結果 |
|---|---|
| test 檔 docstring | 純中文 + 結構性英文（`MODULE_NOTE` / `WHY` / `case` 等 framework keyword）— 合規 |
| test 檔 inline 注釋 | 純中文（line 187-189 / 202 等）— 合規 |
| optuna_optimizer.py LOW-1 後 line 324 + 416 | 純中文 — 合規 |
| optuna_optimizer.py 整檔 grep `# .*[A-Za-z]{8,}.*[一-鿿]` | pre-existing 中英並列段（如 line 283「Cost per side (simplified) / 每邊成本（簡化）」）為 round 2 範圍外舊 code — 不在 LOW-1 修正範圍 |
| pytest.raises / monkeypatch / FakeSocket / _FakeSocket 等 framework name | 保留英文 — 合規（CLAUDE.md §七：技術術語不譯） |

---

## 三端 git log 同步證據

| 端 | HEAD |
|---|---|
| Mac local | `1448e0a1` |
| origin/main | `1448e0a1` |
| Linux trade-core | `1448e0a1` |

**完全同步** — `git fetch && git log` 三端一致。

---

## 8 條 §九 checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 round 1 retrofit 計劃一致 | ✓ test 補洞 + LOW-1 清理，無 scope creep |
| 沒有 except:pass 或靜默吞異常 | ✓（test 用 pytest.raises + monkeypatch；optuna_optimizer.py:311 OSError → return None 是顯式 fail-soft，已被 (a) case 3 凍結） |
| 日誌使用 %s 格式 | n/a 無 logger |
| 新 API 端點有 _require_operator_role() | n/a 非 API |
| except HTTPException 在 except Exception 之前 | n/a |
| detail=str(e) 已改為 "Internal server error" | n/a |
| asyncio 路由中沒有 blocking threading.Lock | ✓ test 純 sync；_send_ipc_command 是 sync helper（cron 後台 thread 跑） |
| 沒有私有屬性穿透 | ✓ from optuna_optimizer import _resolve_ipc_secret 等 module-level helper（非 class 私有屬性） |

---

## 9 條 OpenClaw 特殊 checklist

| Item | 狀態 |
|---|---|
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✓ 0 hit |
| 雙語注釋（2026-05-05 後改默認中文） | ✓ test 純中文 + framework keyword；LOW-1 已清 |
| Rust unsafe / unwrap / panic | n/a Python only |
| 跨語言 IPC schema | ✓ (c) byte-equal 對齊 ipc_client._authenticate；對抗 separators mutation 真守 |
| Migration Guard A/B/C | n/a 無 SQL |
| healthcheck 配對 | n/a 非被動等待 |
| Singleton 登記 §九 表 | ✓ 無新 singleton |
| 文件大小 800/2000 | △ optuna_optimizer.py 1010 > 800 警告（pre-existing baseline 946，round 1 +65 → 1011，round 2 -1 → 1010）；LOW-2 deferred 至 P2「拆 _ipc_helpers.py」 |
| Bybit API | n/a |

---

## Findings

| # | 嚴重性 | 位置 | 描述 | 動作 |
|---|---|---|---|---|
| LOW-2 | LOW (deferred P2) | optuna_optimizer.py 整檔 | 1010 行 > 800 警告線；pre-existing baseline 946，round 1 +65（IPC fix 主邏輯），round 2 -1。新增 LOC 與既有 800 violation 同檔內聚（IPC helper），不破額外不變式 | E1 自評 deferred 至 P2 ticket（拆 `_ipc_helpers.py`），E2 接受 — round 2 範圍純粹是 test 補洞 + LOW-1 清理，硬要在本 round 2 內拆檔反而破「最小影響」原則 |

無 NEW HIGH / MEDIUM / CRITICAL。

---

## 結論

**APPROVED** — to E4 regression。

| 收口項 | 證據 |
|---|---|
| HIGH-1 closure | 12/12 PASS Linux pytest（0.14s）；4 case group 各自真覆蓋（E2 獨立 read source 確認）；對抗 mutation × 2 真驗（E2 自跑：silent return {} → (d) RED；separators drop → (c) RED） |
| LOW-1 closure | grep 0 hit；line 324 + 416 純中文且通順 |
| LOW-2 closure | deferred P2，無 scope creep |
| Mock 不掩蓋邏輯 | wire byte 真存 / HMAC 真跑 / timeout 真 raise / 4 條反模式各有對應 assert |
| 三端同步 | Mac/origin/Linux 全 1448e0a1 |
| Run time | 0.14s（CI 友好） |
| Regression | Linux ml_training pytest baseline 398 passed / 29 skipped / 0 fail（含 12 新 test），無 regression |

下一步：E4 全 ml_training pytest baseline + cron next-fire（5/10 03:17）監控。

**E2 REVIEW DONE: APPROVED · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-09--ml_training_cron_round2_e2_review.md**
