from __future__ import annotations

"""
Engine Capabilities Router / 引擎能力路由

MODULE_NOTE (EN): Exposes a single backward-compat probe endpoint
  `GET /api/v1/engine/capabilities` (EDGE-P3-1 spec §12.3 item 7 / Step 7f).

  The endpoint's purpose is NOT to mirror the full RiskConfig — that lives on
  `/api/v1/paper/risk/config/engine/{engine}`. This endpoint only reports a
  compact "what features does THIS engine build support?" payload so clients
  (GUI, CI, tooling) can degrade gracefully across engine versions:
    * schema-level feature inventory (FeatureVectorV1 name list + dim)
    * which EDGE-P3-1 IPC variants are wired in this build
    * per-engine predictor runtime flags (use / shadow / quantile_k / ε)
    * degraded flag when any engine's RiskConfig IPC fetch failed

  Fail-closed contract: the endpoint MUST return HTTP 200 with degraded=true
  + partial data when IPC is unavailable (tests, cold boot, engine crash),
  never 5xx. Clients are expected to treat degraded=true as "probe unreliable".

MODULE_NOTE (中): 單一 backward-compat 探針端點 `GET /api/v1/engine/capabilities`
  （EDGE-P3-1 §12.3 #7 / Step 7f）。用途是回報「這個引擎 build 支援哪些特徵」
  供 GUI / CI / 工具跨版本優雅降級；不回傳完整 RiskConfig（那在另一條路由）。
  Fail-closed：IPC 不可用時回 200 + degraded=true + 部分資料，絕不 5xx。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from . import main_legacy as base
from .ipc_client import EngineIPCClient

logger = logging.getLogger(__name__)

engine_capabilities_router = APIRouter(
    prefix="/api/v1/engine",
    tags=["Engine Capabilities / 引擎能力"],
)


# Allowed engine names (whitelist prevents IPC injection via engine param).
# 允許的引擎名稱白名單。
_ENGINES: tuple[str, ...] = ("paper", "demo", "live")


# Per-build declaration of which EDGE-P3-1 Step 7 IPC variants are wired.
# When Step 7b/7c land, flip the corresponding flag to True in the same PR
# that wires the Rust handler + Python consumer — this is the only client-
# facing declaration that prevents silent drift between build and probe.
# 本 build 宣告哪些 EDGE-P3-1 Step 7 IPC 變體已接線。Step 7b/7c 落地時
# 必須在同一 PR 翻為 True（唯一防漂移宣告）。
_EDGE_P3_IPC_SUPPORT: dict[str, bool] = {
    # Step 7a — DecisionFeatureSnapshot IPC + Python consumer (commit d73addb)
    "decision_feature_snapshot": True,
    # Step 7d — write_toml_atomic_fsynced helper (U2, commit a110892)
    "fsynced_toml_write": True,
    # Step 7e — DisableEdgePredictorAll two-phase commit + V014 audit
    "disable_edge_predictor_all": True,
    # Step 7b — ReloadEdgePredictor{engine, strategy, path} IPC (pending)
    "reload_edge_predictor": False,
    # Step 7c — EmitShadowFill Python consumer → learning.decision_shadow_fills
    "emit_shadow_fill": False,
    # v1.3 §12.3 item 7 U1 — SetEdgePredictorShadow{engine, operator_token}
    "set_edge_predictor_shadow": False,
}


# Canonical feature-vector metadata (mirrors Rust FeatureVectorV1 §3.2).
# The single source of truth for the name list lives in
# `program_code/ml_training/parquet_etl.py::EDGE_P3_FEATURE_NAMES`, which
# already carries a DO-NOT-REORDER contract with Rust. Import from there so
# drift is impossible as long as that contract holds.
# 特徵向量規範元資料（鏡像 Rust FeatureVectorV1 §3.2）。從 parquet_etl
# 匯入已有的 DO-NOT-REORDER 鏡像，避免新增另一份獨立副本。
def _feature_schema() -> dict[str, Any]:
    try:
        from program_code.ml_training.parquet_etl import EDGE_P3_FEATURE_NAMES
        names = list(EDGE_P3_FEATURE_NAMES)
        return {
            "schema_version": "v1",
            "dim": len(names),
            "names": names,
        }
    except Exception as exc:  # pragma: no cover — import-time guard
        logger.warning("capabilities: feature-name import failed: %s", exc)
        return {"schema_version": "v1", "dim": 17, "names": []}


# Subset of RiskConfig.edge_predictor fields surfaced by capabilities.
# Kept deliberately narrow — clients looking for the full snapshot should use
# `/api/v1/paper/risk/config/engine/{engine}`. Adding fields here is a public
# contract change and requires a test update.
# 表面化 RiskConfig.edge_predictor 的子集。刻意保持窄 — 完整快照請用另一路由。
_EDGE_PREDICTOR_FIELDS: tuple[str, ...] = (
    "use_edge_predictor",
    "shadow_mode",
    "quantile_safety_k",
    "require_q10_positive_for_adds",
    "exploration_rate",
    "fallback_on_error",
)


def _extract_edge_predictor(config: dict[str, Any]) -> dict[str, Any]:
    """
    Pull the narrow capabilities view out of a RiskConfig snapshot.
    Missing fields become None — the client must treat None as "unknown"
    rather than "disabled" (fail-closed semantic).
    從 RiskConfig 快照抽取能力視圖的窄子集，缺失欄位以 None 表示「未知」。
    """
    ep = config.get("edge_predictor", {}) if isinstance(config, dict) else {}
    if not isinstance(ep, dict):
        return {field: None for field in _EDGE_PREDICTOR_FIELDS}
    return {field: ep.get(field) for field in _EDGE_PREDICTOR_FIELDS}


async def _query_engine_snapshot(
    ipc: EngineIPCClient | None,
    engine: str,
) -> tuple[dict[str, Any], str | None]:
    """
    Query one engine's RiskConfig via `get_risk_config` IPC and return the
    narrow edge_predictor view. Returns (snapshot, error_reason_or_None).
    向單一引擎查 RiskConfig 並抽 edge_predictor 視圖；第二個返回值為錯誤原因
    字串（None = 成功）。
    """
    if ipc is None:
        return ({field: None for field in _EDGE_PREDICTOR_FIELDS}, "ipc_unavailable")
    try:
        resp = await ipc.call("get_risk_config", params={"engine": engine})
    except Exception as exc:
        logger.warning("capabilities: get_risk_config engine=%s failed: %s", engine, exc)
        return ({field: None for field in _EDGE_PREDICTOR_FIELDS}, f"ipc_error:{type(exc).__name__}")

    raw = resp if isinstance(resp, dict) else {}
    config = raw.get("config", raw)
    if not isinstance(config, dict):
        return ({field: None for field in _EDGE_PREDICTOR_FIELDS}, "bad_payload_shape")
    return (_extract_edge_predictor(config), None)


# Module-level IPC singleton (mirrors risk_routes._get_direct_ipc pattern).
# 模組級 IPC 單例（複用 risk_routes 的懶初始化樣式）。
_IPC_CLIENT: EngineIPCClient | None = None


async def _get_ipc() -> EngineIPCClient | None:
    """
    Lazy-init the IPC client. Returns None on connect failure so the endpoint
    can still serve the static parts of its payload (fail-closed).
    延遲初始化 IPC 客戶端；連線失敗回 None（仍可輸出靜態部分）。
    """
    global _IPC_CLIENT
    if _IPC_CLIENT is None:
        client = EngineIPCClient()
        try:
            await client.connect()
        except Exception as exc:
            logger.warning("capabilities: IPC connect failed: %s", exc)
            return None
        _IPC_CLIENT = client
    return _IPC_CLIENT


@engine_capabilities_router.get("/capabilities")
async def get_engine_capabilities(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    GET /api/v1/engine/capabilities

    Backward-compat probe for EDGE-P3-1-aware clients (spec §12.3 #7, Step 7f).

    Returns:
        ok (bool): always True at HTTP layer; see `degraded` for IPC health.
        data.api_version (str): API layer tag ("v1").
        data.feature_schema (dict): FeatureVectorV1 metadata (dim / names /
            schema_version). Mirrors Rust `features.rs::FEATURE_NAMES_V1`.
        data.ipc_methods (dict[str, bool]): Which EDGE-P3-1 Step 7 IPC
            variants this build supports. See `_EDGE_P3_IPC_SUPPORT`.
        data.engines (dict[str, dict]): per-engine edge_predictor view
            (paper / demo / live) — narrow subset of RiskConfig.
        data.degraded (bool): True if any engine's IPC fetch failed.
        data.reason (str | None): First failure reason when degraded.
    """
    ipc = await _get_ipc()

    engines: dict[str, dict[str, Any]] = {}
    first_reason: str | None = None
    for engine in _ENGINES:
        snapshot, reason = await _query_engine_snapshot(ipc, engine)
        engines[engine] = snapshot
        if reason is not None and first_reason is None:
            first_reason = reason

    degraded = first_reason is not None

    data: dict[str, Any] = {
        "api_version": "v1",
        "feature_schema": _feature_schema(),
        "ipc_methods": dict(_EDGE_P3_IPC_SUPPORT),
        "engines": engines,
        "degraded": degraded,
        "reason": first_reason,
    }
    return {
        "ok": True,
        "data": data,
        "is_simulated": False,
        "data_category": "engine_capabilities",
    }
