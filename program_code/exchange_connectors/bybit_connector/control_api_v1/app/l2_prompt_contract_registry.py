"""
MODULE_NOTE
模塊用途：
  L2 Advisory Mesh PromptContract + output-schema registry（PA P2 設計 §D）。把 prompt
  契約與輸出 schema 一般化成 versioned registry（keyed by prompt_contract_ref /
  output_schema_ref，§B），供 Orchestrator 寫 D3 ledger 的 contract_ver/schema_ver。

  鐵律：prompt 是「確定性、versioned 模板」——Ollama（或任何 model）**禁止生成 prompt**。
  讓 model 寫 prompt 會疊加幻覺、毀掉 D3 attribution、破壞 fault-localization replay。
  Ollama 僅允許兩個 seam（非本模塊職責）：(1) input 抽取（ContextDistiller）；(2) output
  NL 渲染（on human trigger）。它「永不」是 prompt author，「永不」是 validator。

  本 phase（P2）= registry 機制 + 確定性模板紀律 + 接線。具體 capability 契約（ml_advisory.v1
  等）是 P3。P2 種子註冊既有的 l2.manual_reasoning（沿用 layer2_engine 的 l2_contract.v1 /
  l2_schema.v1 常數），證明 registry reachable 非死碼，且既有 manual-trigger 零回歸。

主要類/函數：
  - PromptContract：versioned 確定性模板（contract_ver + schema_ver + template + 不變式）。
  - get_prompt_contract(ref) / get_output_schema(ref)：registry 查詢。
  - resolve_contract_versions(capability_id, contract_ref, schema_ref)：給 Orchestrator
    取 (contract_ver, schema_ver) 寫每 D3 row；ref 缺失 → fallback 既有 l2_contract.v1。

依賴：
  - layer2_engine 的 L2_PROMPT_CONTRACT_VER / L2_OUTPUT_SCHEMA_VER（種子版本，single source，不複製字面值）。

硬邊界：
  - registry 是「唯一」prompt 模板來源；無 code path 讓 model 生成模板（CC/E2 grep target）。
  - 確定性：模板是 checked-in 常數，非 runtime 生成；同 ref 永得同模板（versioned）。
  - 純 registry：無 model 呼叫、無 order surface。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# 種子版本沿用既有引擎常數（single source；不在此複製字面 "l2_contract.v1"）。
from .layer2_engine import (
    L2_DEFAULT_CAPABILITY_ID,
    L2_OUTPUT_SCHEMA_VER,
    L2_PROMPT_CONTRACT_VER,
)

logger = logging.getLogger("l2_prompt_contract_registry")


class PromptContract(BaseModel):
    """versioned 確定性 PromptContract（§D）。

    為什麼 frozen + extra="forbid"：契約一旦註冊即不可變（同 ref→同模板），任何契約變更
    必 bump 新版本 ref；未知欄 = drift error。template 是 checked-in 字面常數，**非** model
    生成（鐵律）。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_ref: str = Field(..., min_length=1, max_length=128)
    contract_ver: str = Field(..., min_length=1, max_length=64)
    output_schema_ref: str = Field(..., min_length=1, max_length=128)
    schema_ver: str = Field(..., min_length=1, max_length=64)
    role: str = Field(default="", max_length=256)
    # template = 確定性 system-prompt 模板（checked-in；Ollama 禁生成）。
    template: str = Field(default="", max_length=200_000)
    # 不變式宣告：advisory-not-decision + governance + fact/inference/assumption 紀律。
    constraints: tuple[str, ...] = Field(default_factory=tuple)
    uncertainty_rule: str = Field(default="", max_length=512)


class OutputSchema(BaseModel):
    """versioned 輸出 schema（§D）。parsed_output 須過此 schema，否則 guard reject。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_ref: str = Field(..., min_length=1, max_length=128)
    schema_ver: str = Field(..., min_length=1, max_length=64)
    # 必填欄位名（最小化；具體 capability schema 在 P3 細化）。
    required_fields: tuple[str, ...] = Field(default_factory=tuple)


# ═══════════════════════════════════════════════════════════════════════════════
# 種子 registry（P2 skeleton）—— 既有 l2.manual_reasoning 契約
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼種子既有契約：P2 不改 manual-trigger 行為（零回歸）。Orchestrator 驅動既有
# manual capability 時，contract_ver/schema_ver 由「此 registry」解析而非 layer2_engine
# 硬編——但解析結果就是既有的 l2_contract.v1 / l2_schema.v1（值不變，來源變 registry）。

_MANUAL_CONTRACT = PromptContract(
    contract_ref="l2.manual_reasoning.v1",
    contract_ver=L2_PROMPT_CONTRACT_VER,  # "l2_contract.v1"（沿用，single source）
    output_schema_ref="l2.manual_reasoning.v1",
    schema_ver=L2_OUTPUT_SCHEMA_VER,  # "l2_schema.v1"（沿用）
    role="Layer 2 AI Reasoning Engine（manual-trigger，既有 SYSTEM_PROMPT）",
    # template 留空：manual capability 仍用 layer2_engine.SYSTEM_PROMPT（既有路徑，零改動）；
    # 此 registry 條目記錄其版本血緣，不在此複製整份 prompt（避免兩份 drift）。
    template="",
    constraints=(
        "ALL recommendations are advisory only（AI 輸出非即時命令，須經 Decision Lease + 風控）",
        "distinguish facts / inferences / hypotheses（事實/推論/假設分離）",
        "is_simulated=True（paper；不觸 live）",
    ),
    uncertainty_rule="情況不明 → 建議 hold 並說明（保守預設）",
)

_MANUAL_SCHEMA = OutputSchema(
    schema_ref="l2.manual_reasoning.v1",
    schema_ver=L2_OUTPUT_SCHEMA_VER,
    required_fields=(),  # manual capability 用既有 submit_recommendation tool schema，不在此重述
)

_PROMPT_CONTRACTS: dict[str, PromptContract] = {
    _MANUAL_CONTRACT.contract_ref: _MANUAL_CONTRACT,
}

_OUTPUT_SCHEMAS: dict[str, OutputSchema] = {
    _MANUAL_SCHEMA.schema_ref: _MANUAL_SCHEMA,
}

# capability_id → 種子 contract_ref（P2 僅 manual；P3 capabilities 自帶 prompt_contract_ref）。
_CAPABILITY_SEED_CONTRACT: dict[str, str] = {
    L2_DEFAULT_CAPABILITY_ID: _MANUAL_CONTRACT.contract_ref,
}


def get_prompt_contract(contract_ref: str) -> PromptContract | None:
    """取 versioned PromptContract（registry 是唯一模板來源；無 model 生成）。"""
    return _PROMPT_CONTRACTS.get(contract_ref)


def get_output_schema(schema_ref: str) -> OutputSchema | None:
    """取 versioned 輸出 schema。"""
    return _OUTPUT_SCHEMAS.get(schema_ref)


def resolve_contract_versions(
    *,
    capability_id: str,
    contract_ref: str | None = None,
    schema_ref: str | None = None,
) -> tuple[str, str]:
    """解析 (contract_ver, schema_ver) 給 Orchestrator 寫每 D3 row。

    為什麼 fallback 既有版本：P2 種子只有 manual capability；當 ref 缺失（manual-trigger
    路徑）回既有 l2_contract.v1 / l2_schema.v1（零回歸）。P3 capability 自帶 ref → 取
    registry 對應版本。**版本永遠來自 registry/種子常數，非 model**。
    """
    # 1) 顯式 contract_ref 命中 registry → 用其版本。
    if contract_ref and contract_ref in _PROMPT_CONTRACTS:
        pc = _PROMPT_CONTRACTS[contract_ref]
        sch = _OUTPUT_SCHEMAS.get(schema_ref or pc.output_schema_ref)
        schema_ver = sch.schema_ver if sch else pc.schema_ver
        return pc.contract_ver, schema_ver
    # 2) capability_id 命中種子映射 → 用種子契約版本。
    seed_ref = _CAPABILITY_SEED_CONTRACT.get(capability_id)
    if seed_ref and seed_ref in _PROMPT_CONTRACTS:
        pc = _PROMPT_CONTRACTS[seed_ref]
        return pc.contract_ver, pc.schema_ver
    # 3) fallback：既有引擎常數（manual-trigger 零回歸）。
    return L2_PROMPT_CONTRACT_VER, L2_OUTPUT_SCHEMA_VER


__all__ = [
    "PromptContract",
    "OutputSchema",
    "get_prompt_contract",
    "get_output_schema",
    "resolve_contract_versions",
]
