# E1-B IMPL DONE — P0 Replay Tier A T3 + T4 manifest config echo（2026-05-11）

**Owner**：E1-B
**Branch / Worktree**：`worktree-agent-a558256f65b2d2af2`（dispatch worktree）
**Base HEAD**：`17d95d67` (PA: P0 replay engine counterfactual fix design Tier A v1)
**Status**：IMPL DONE — 待 E2 審查 + E4 regression + E1-D T6 acceptance integration

---

## 1. 任務摘要

依 PA 設計 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_replay_engine_counterfactual_fix_design.md` §2.4 + §2.5 + §3.3.3 + §3.3.4：

- **T3**：`_build_manifest_jsonb` echo production `scanner_config.toml`（25 pinned sym + anti-churn + market_judgment + opportunity）→ 讓 Rust replay_runner `config.rs:7-31` deserialise 為真 `ScannerConfig`，不再退化用 `replay_default_scanner_config` 的 2-sym default
- **T4**：直接 echo prepared 階段 IPC fetched 的 `strategy_params` + `risk_overrides` blob 進 `manifest_jsonb` top-level — 對齊 P0 Option A-Lite 後 demo TOML 改動（`bb_reversion.min_persistence_ms=120000` / `ma_crossover.min_trend_snr=0.60`）

---

## 2. 修改清單

| File | LOC delta | 改動內容 |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py` | +193 / -2 | 加 `tomllib` import (含 py3.10 `tomli` fallback) / 加 `_resolve_settings_root()` + `_load_production_scanner_config()` + `_load_production_strategy_params_toml()` + `_load_production_risk_overrides_toml()` 4 helpers / `_build_manifest_jsonb` 新增 `strategy_params` + `risk_overrides` kwargs + manifest 加 `scanner_config` / `strategy_params` / `risk_overrides` 3 個 top-level key / `manifest_version` 1→2 / `post_replay_full_chain_run` caller 把 prepared dict 的 2 個 blob 傳給 `_build_manifest_jsonb` |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_run_routes.py` | +375 / -0 | 加 3 個 TOML fixture writer helper + 5 個新 test（scanner_config echo 25 pinned / strategy_params echo / hash invariance / fail-soft fallback / engine 正規化） |

---

## 3. 關鍵 diff

### 3.1 tomllib 雙路徑 import (line 17–32)

```python
# Python 3.11+ stdlib tomllib；Mac dev 在 py3.10 可裝 tomli 1.x backport
# (runtime 跑於 Linux py 3.12.3 已驗，tomllib 直接可用)
try:
    import tomllib  # type: ignore[unresolved-import]
    _TOMLLIB_DECODE_ERROR: type = tomllib.TOMLDecodeError
except ImportError:  # pragma: no cover — Mac py3.10 dev only path
    try:
        import tomli as tomllib  # type: ignore[no-redef]
        _TOMLLIB_DECODE_ERROR = tomllib.TOMLDecodeError
    except ImportError:
        tomllib = None  # type: ignore[assignment]
        _TOMLLIB_DECODE_ERROR = Exception
```

### 3.2 TOML loader helpers

3 個 helper 全走相同 fail-soft pattern：
- `tomllib is None` → return None（logger warning）
- 檔案不存在 → return None（logger warning）
- parse 失敗 → return None（logger warning + exception msg）
- 成功 → return loaded dict

路徑解析統一用 `_resolve_settings_root()`：
```python
def _resolve_settings_root() -> Path:
    base = os.environ.get("OPENCLAW_BASE_DIR")
    if base:
        return Path(base) / "settings"
    return Path(__file__).resolve().parents[5] / "settings"
```

對齊 `paper_trading_routes.py:1128` 既有 `parents[5]` fallback pattern；無硬編碼路徑。

### 3.3 `_build_manifest_jsonb` 簽名 + 新 manifest fields

```python
def _build_manifest_jsonb(
    *,
    body: ReplayFullChainRunRequest,
    strategy: str,
    # ...既有 args 不變
    strategy_params: Optional[dict[str, Any]] = None,  # 新
    risk_overrides: Optional[dict[str, Any]] = None,   # 新
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "manifest_version": 2,   # 1 → 2 (新增 3 key)
        # ...既有 field 不變
    }

    # T3: scanner_config production TOML echo
    scanner_config = _load_production_scanner_config()
    if scanner_config is not None:
        manifest["scanner_config"] = scanner_config

    # T4: strategy_params + risk_overrides echo
    if strategy_params is not None:
        manifest["strategy_params"] = strategy_params
    if risk_overrides is not None:
        manifest["risk_overrides"] = risk_overrides

    return manifest
```

### 3.4 Caller

```python
manifest_jsonb = _build_manifest_jsonb(
    body=body,
    strategy=strategy,
    # ...既有 args
    strategy_params=prepared["strategy_params"],
    risk_overrides=prepared["risk_overrides"],
)
```

`prepared["strategy_params"]` 與 `prepared["risk_overrides"]` 來自 `_prepare_full_chain_run_fixture` 內既有 IPC fetch（`_fetch_full_chain_strategy_params` + `_fetch_current_risk_config`），無新加 fetch path。

---

## 4. 治理對照

### 4.1 V3 §5 不變式：`sha256(manifest_jsonb) == manifest_hash`

T3 + T4 加的 `scanner_config / strategy_params / risk_overrides` 三 key 都是 client-supplied top-level field，不以 `_` 開頭 → **不破 M-4 `_no_reserved_prefix_keys` validator**。

V049 register handler `run_register_in_pg_xact`（`experiment_registry.py:1083`）對 augmented `manifest_to_persist` 重算 `compute_manifest_canonical_bytes` + sha256 → manifest_hash 自動含新 3 key bytes。**對齊 V3 §5**。

### 4.2 M-4 reserved prefix rejector

新加 3 個 top-level key 命名（`scanner_config / strategy_params / risk_overrides`）全無 `_` 前綴。V049 reserved blob (`_replay_strategy_params / _replay_risk_overrides`) 仍由 register handler 在 server-side 注入（既有 path），與 T4 top-level echo 並存（雙保險，內容相同 → 仍滿足 hash invariant，因 server-side 注入後 hash 也重算）。

### 4.3 §四 5 硬邊界

| 邊界 | T3/T4 觸碰? |
|---|---|
| `live_execution_allowed` | 不觸（replay isolated subprocess） |
| `decision_lease_emitted` | 不觸 |
| `max_retries = 0` | 不觸 |
| `OPENCLAW_ALLOW_MAINNET=1` | 不觸 |
| `live_reserved` system_mode | 不觸 |

### 4.4 forbidden_guard / V3 §6.2

純 Python `_build_manifest_jsonb` + TOML read-only loader；無：
- Decision Lease acquire/release
- IPC server start
- WS client start
- Exchange dispatch
- DB writer channel use（manifest write 走既有 register handler V049 path）
- Live/demo config mutate
- Advisory write outside PL/pgSQL

### 4.5 跨平台兼容 (§七)

| Item | T3/T4 |
|---|---|
| 路徑硬編碼 | 0 — 全用 `OPENCLAW_BASE_DIR` + `parents[5]` fallback |
| `/home/ncyu` / `/Users/ncyu` 字面 | 0 (`grep` 已驗) |
| Linux-only 依賴 | 0 — `tomllib` 是 py3.11+ stdlib；Mac py3.10 dev 走 `tomli` 1.x backport（既有 `requirements.txt` 已含 tomli 1.2.3） |
| LocalLLM 抽象洩漏 | N/A |
| systemd → launchd 遷移 | N/A |

### 4.6 注釋規範 (§七 2026-05-05 governance change)

新代碼注釋默認中文；只在 import block 加一行英文用於 IDE hint。MODULE_NOTE block 中文 + 必要英文技術詞混排。

### 4.7 文件大小限制 (§九)

| File | Before | After | Cap |
|---|---|---|---|
| `replay_full_chain_routes.py` | 1740 | 1931 | 2000 hard / 800 warn — 已過 800 警告線（既有就過），未破 2000 |
| `test_replay_full_chain_run_routes.py` | 829 | 1203 | 2000 hard — test file 內聚性高，未破 |

---

## 5. 不確定之處

1. **V049 reserved blob path 與 T4 top-level echo 雙寫的 hash 表現**：register handler 看到 client manifest_jsonb 已含 top-level `strategy_params` + `risk_overrides`，再把 `body.strategy_params` 注入 `_replay_strategy_params`（line 1072）→ augmented manifest 含 4 個對應 key（top-level + `_replay_*`）。內容相同但 key 名不同，canonical bytes 不同，hash 不同（但仍滿足「DB SELECT 出來 manifest_jsonb 再 sha256 = manifest_hash」不變式）。**E2 驗證點**：跑既有 `test_full_chain_run_registers_and_starts_one_subprocess_per_strategy` 確認 register success（已 PASS 170/170）。
2. **Rust 端 deserialise**：`bin/replay_runner/config.rs:7-31` 已支援從 `manifest.scanner_config` blob deserialise 為 `ScannerConfig` — 但實際 deser 路徑由 E1-A T1 完成（不在本 sub-agent 範圍）。E1-D T6 acceptance 會 end-to-end 驗 `replay_runner` 跑通 TOML→JSON→Rust `ScannerConfig` 完整路徑。本任務只負責 Python 端 echo，Rust 端 reader 邏輯不在 scope。
3. **`manifest_version` 1→2 bump**：T3+T4 加新 fields 視為 manifest schema 演進。E2 驗證 V049 register handler 是否對 `manifest_version=2` 有任何 hard reject — 既有 register 對 manifest_version 無 schema validation（只查 size cap + canonical bytes hash），所以**理論上 backward compat**。E2 / E4 confirm。
4. **既有 `_register_full_chain_experiment` 仍 pass strategy_params + risk_overrides 給 register body** — V049 reserved blob 路徑保留作 backward compat（PA §6.3 建議 future 同改 `route_helpers.py:922-928`「if manifest_jsonb has key skip V049 lookup」，本任務 not in scope）。
5. **Quick prepare path（`replay_quick_routes.py`）不寫 manifest**：只在 prepare endpoint response 中回 strategy_params + risk_overrides；不需改。**確認**：T3/T4 改 scope 是 `/full-chain/run` only，不含 `/full-chain/prepare` 與 `/quick/prepare`。

---

## 6. 驗證結果

### 6.1 pytest

```bash
cd /Users/ncyu/Projects/TradeBot/srv
python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_*.py -v
# 170 passed, 13 warnings in 0.87s
```

包括：
- 11 既有 `test_replay_full_chain_run_routes.py` test 全 PASS（無 regression）
- 5 新加 T3+T4 acceptance test 全 PASS：
  - `test_scanner_config_echo_includes_pinned_25` ✓
  - `test_strategy_params_echo_matches_production_toml` ✓
  - `test_manifest_jsonb_hash_changes_when_scanner_config_changes` ✓
  - `test_scanner_config_load_failure_returns_none_does_not_break_replay` ✓
  - `test_strategy_params_toml_loader_engine_normalization` ✓
- 154 其他 replay test 全 PASS

### 6.2 forbidden_guard 對齊

- 無硬編碼路徑（`grep -E '(/home/ncyu|/Users/[^/]+)'` = 0 match）
- 無 IPC / Lease / Bybit / DB writer 直接操作
- 無 mutate global state

### 6.3 manifest_version bump 影響

既有 `test_full_chain_run_*` 11 個 test 全 PASS（包括 `test_full_chain_run_registers_and_starts_one_subprocess_per_strategy` 對 register body 內 `manifest_jsonb` 各 field 的精準 assert）→ V049 register handler 對 `manifest_version=2` 無 reject。

---

## 7. Operator 下一步

1. **E2 audit**：
   - 確認 V049 register handler 對 augmented manifest（top-level `scanner_config/strategy_params/risk_overrides` + reserved `_replay_*` blob）的 hash 正確性
   - 確認 `_size_cap` 256KB 不會被 25-sym scanner_config + 5-strategy strategy_params + full risk_config 撐爆（粗估：scanner_config ~2KB + strategy_params ~5KB + risk_overrides ~10KB ≈ 17KB << 256KB）
   - 確認 TOML→JSON→Rust serde rename rules 一致（per PA §3.5.2 E2 重點審查）— 雖然 byte-equal 是 E1-A T1 scope（Rust 端 deserialise），E2 仍可 spot-check key naming convention（pinned_symbols vs pinnedSymbols 等 case sensitivity）
3. **E1-D T6 acceptance**：T3+T4 完成後 E1-D 跑 end-to-end `replay_counterfactual_tier_a.rs` 整合測，驗 `manifest.scanner_config` 真實傳到 Rust `replay_runner` 並讓 `is_pinned` 計算用 25-sym pinned set（而非 default 2-sym）
4. **E4 regression**：跑 `cargo test --release -p openclaw_engine --lib`（既有 2792 test 應仍 PASS） + 全 Python pytest 確認本改動無對 ML / scheduler / cron 等 sibling module regression

---

## 8. Commit 狀態

**未 commit**（per 啟動序列 + workflow chain：E1 IMPL → E2 review → E4 regression → PM bundle commit）。

待 E2 sign-off 後加入 PM bundle commit。

報告 path：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_b_manifest_config_echo.md`

---

## 9. E1 memory 追加 hint

```markdown
## 2026-05-11 — P0 Replay Tier A E1-B：scanner_config + strategy_params + risk_overrides manifest echo

**Branch**: `worktree-agent-a558256f65b2d2af2`；待 E2 + E4 + PM bundle commit
**Report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_b_manifest_config_echo.md`

### 修復概要
- `replay_full_chain_routes.py` 加 tomllib 雙路徑 import + 3 helper loader + `_build_manifest_jsonb` 加 3 個 manifest top-level key（scanner_config / strategy_params / risk_overrides） + `manifest_version` 1→2
- `test_replay_full_chain_run_routes.py` 加 5 acceptance test：scanner 25-pinned echo / strategy_params verbatim echo / hash invariant / fail-soft fallback / engine 正規化

### 驗證
- Mac py3.10 (tomli backport) pytest 170/170 PASS
- forbidden_guard 0 violation；§四 5 硬邊界 0 觸碰
- 文件 LOC：1740→1931（< 2000 hard cap）

### 關鍵教訓
1. **Python 跨版本 tomllib**：runtime Linux py3.12 有 stdlib tomllib，Mac py3.10 dev 走 tomli backport（已在 requirements.txt）。雙路徑 import + None guard fail-soft 是正解。**新 governance hint**：類似涉 py3.11+ stdlib feature 的 IMPL 必須加 Mac py3.10 fallback path（否則 pytest collection 直接 ImportError）。
2. **M-4 `_no_reserved_prefix_keys` rejector**：client manifest_jsonb top-level 不能用 `_*` 開頭 key。但我加的 `scanner_config / strategy_params / risk_overrides` 都不以 `_` 開頭 → 合法。V049 既有 `_replay_strategy_params / _replay_risk_overrides` 是 server-side 注入，與 client 路徑不衝突。
3. **manifest_version bump 風險**：1→2 看似 minor change，但若 register handler / Rust deserialise 任一端有 hard match `manifest_version == 1`，就 break。本 case 確認 register handler 無 schema reject，但 E2 必查 Rust 端 deserialise 是否容忍 `version=2`。
4. **PA spec §3.3.4 直接 echo 而非 V049 blob lookup detour**：T4 把 strategy_params + risk_overrides 直接寫進 manifest_jsonb top-level，比依賴 `lookup_replay_config_blob` 從 V049 reserved blob 反查更顯式可靠。E1 報告 §5.5 PG 直查發現 manifest_jsonb 的 strategy_params=NULL 的根因不是 fetch 失敗而是「從不 echo」，T4 直接修這個 root cause。
5. **fail-soft over fail-fast**：tomllib 不可用 / 檔案不存在 / parse 失敗 → 全回 None + logger.warning，manifest 不含對應 key，replay 退化為 Rust default。比 raise 更穩，因 prepare path 已有 fixture/事件 mock，TOML load 失敗不該整個 run 退 503。

### 治理對照
- V3 §5 sha256(manifest_jsonb)==manifest_hash 不變式：register handler 對 augmented manifest 重算 hash，自動 cover 新 fields
- 跨平台 §七：0 硬編碼路徑（OPENCLAW_BASE_DIR + parents[5] fallback）
- 注釋 §七 2026-05-05：中文默認，import block 加最少英文
- 文件 §九：1740→1931（< 2000 hard cap）
```

---

E1 IMPLEMENTATION DONE: 待 E2 審查 + E4 regression + E1-D T6 acceptance integration（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_b_manifest_config_echo.md`）
