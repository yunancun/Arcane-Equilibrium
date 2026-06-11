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

# ═══════════════════════════════════════════════════════════════════════════════
# P3a — ml_advisory 兩模式 PromptContract + OutputSchema（PA P3 設計 §C/§D；確定性 versioned）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 鐵律（同 manual）：template 是 checked-in 字面常數，Ollama/任何 model 禁生成。三模式共用「一個」
# output-schema ml_advisory.v1（PA 設計 §E.2(0)），但各有「獨立」versioned PromptContract（role
# 不同）。P3a 只註冊 diagnose_leak + interpret_result（斷言無 alpha）；hypothesize（P3b，alpha-
# bearing）blocked on QC B1，不在本 phase。
#
# 為什麼 contract_ver/schema_ver 是顯式字面常數（非沿用引擎常數）：ml_advisory 是 P3 新 capability，
# 與既有 l2.manual_reasoning 是不同契約。每個 ref 永得同模板（versioned）；契約變更必 bump 新 ver。
# 這兩個 ver 由 resolve_contract_versions 寫進每 D3 row（fault-localization replay 用）。

# 共用輸出 schema（三模式共用「一個」schema ml_advisory.v1；PA 設計 §C line 140）。mode 欄驅動哪個
# 子物件被填（design §E.2(0) line 858 mode:"hypothesize|diagnose_leak|interpret_result"）。schema
# 版本獨立於 contract 版本（schema 可不變而 prompt 演進）。
#
# 為什麼三模式共用一個 schema（非各自一個）：PA §C「one output-schema ml_advisory.v1」。required_fields
# 只列「mode」（所有模式共有的識別欄）；per-mode 必填子物件（diagnose→leak_drift_diagnosis、
# interpret→result_interpretation）的強制在「executor + guard」層（按 mode 分流），非 schema 層
# ——避免 resolve_contract_versions 在共用 schema_ref 下解析到錯誤 required_fields 物件。
_ML_ADVISORY_SCHEMA_VER = "ml_advisory_schema.v1"

_ML_ADVISORY_SCHEMA = OutputSchema(
    schema_ref="ml_advisory.v1",
    schema_ver=_ML_ADVISORY_SCHEMA_VER,
    # 只列共有的 mode 欄；per-mode 子物件必填由 executor/guard 按 mode 強制（見 MODULE_NOTE）。
    required_fields=("mode",),
)

# per-mode 必填子物件（executor/guard 按 output["mode"] 分流強制；schema 層只驗共有的 mode 欄）。
ML_ADVISORY_MODE_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "diagnose_leak": ("mode", "leak_drift_diagnosis"),
    "interpret_result": ("mode", "result_interpretation"),
    # hypothesize 是 P3b（alpha-bearing）：LLM 只「生成」假說（mechanism + falsification +
    # signal_axes_used + beta_neutralization_plan），不作 alpha 斷言——math gate 是唯一 validator。
    "hypothesize": ("mode", "feature_hypotheses"),
}

# M3 leak-typing 合法 source_class（design §E.2(0) line 864）。P3a 只有 name_pattern_check 這個
# producer 存在（leakage_check.py）；shift1_compliance / is_oos_gap 是 MIT-owned producer（P3b leak
# precondition）尚未存在，但合法值集合須含三者，使 guard 能 typing-強制：name_pattern_check 不得
# 宣稱 leak-free PIT（只有 shift1_compliance/is_oos_gap 可），P3a 的 diagnose 證據一律 typed 為
# name_pattern_check 且不宣稱 leak-free。
ML_ADVISORY_LEAK_SOURCE_CLASSES: frozenset[str] = frozenset(
    {"name_pattern_check", "shift1_compliance", "is_oos_gap"}
)

# 能支撐「leak-free PIT」斷言的 source_class（design §E.2(0) lines 894-900）。name_pattern_check
# 不在其中（weak necessary-not-sufficient screen）；P3a 無這兩個 producer，故任何 leak-free PIT
# 斷言在 P3a 必被 guard reject（typing 強制 M3）。
ML_ADVISORY_LEAKFREE_SOURCE_CLASSES: frozenset[str] = frozenset(
    {"shift1_compliance", "is_oos_gap"}
)

# diagnose_leak 的 PromptContract（role=診斷 leak/drift；確定性模板）。
# 為什麼 template 明確要求 tag source_class + 禁 leak-free 斷言：M3（design §E.2(0) lines 884-903）
# ——name_pattern_check 是 weak necessary-not-sufficient screen，ml_advisory 不得宣稱 leakage_check
# 輸出 = leak-free PIT。typing 強制此。constraints 宣告「LLM 不驗 alpha」鐵律。
_ML_ADVISORY_DIAGNOSE_CONTRACT = PromptContract(
    contract_ref="ml_advisory.diagnose_leak.v1",
    contract_ver="ml_advisory_diagnose.v1",
    output_schema_ref="ml_advisory.v1",
    schema_ver=_ML_ADVISORY_SCHEMA_VER,
    role="ML pipeline leakage/drift diagnostician（advisory-only；asserts NO alpha）",
    template=(
        "You are a deterministic ML-pipeline leakage/drift diagnostician for a crypto "
        "trading research system. You are given a completed training run's metrics, the "
        "leakage_check findings (name-pattern only), and drift signals. Your job is to "
        "diagnose suspected leak/drift causes and recommend a concrete follow-up CHECK.\n"
        "HARD CONSTRAINTS:\n"
        "- You make NO alpha claim and NO promotion-readiness claim. You only diagnose "
        "pipeline integrity. You do not validate whether any signal has edge.\n"
        "- Every leak/PIT claim in your evidence[] MUST carry a source_class. The only "
        "evidence you have here is name_pattern_check (leakage_check.py). You MUST NOT "
        "claim leak-free point-in-time integrity backed only by name_pattern_check — it "
        "is a necessary-not-sufficient screen. A leak-free PIT assertion requires "
        "shift1_compliance and/or is_oos_gap evidence, which is NOT provided here.\n"
        "- Cite the exact metric/finding you reason from (source_ref).\n"
        "Respond with ONLY a compact JSON object: "
        '{"mode":"diagnose_leak","leak_drift_diagnosis":{"suspected_cause":"...",'
        '"evidence":[{"claim":"...","kind":"leak|drift","source_ref":"...",'
        '"source_class":"name_pattern_check"}],"recommended_check":"..."}}'
    ),
    constraints=(
        "ALL output is advisory only（AI 輸出非命令，須經 Decision Lease + 風控；direction=neutral）",
        "asserts NO alpha（diagnose 不作 promotion-relevant 斷言，無 alpha 需驗）",
        "name_pattern_check is NOT leak-free PIT（M3：source_class typing 強制）",
        "the LLM NEVER validates alpha（math gate 是唯一 validator；P3a 無 alpha gate）",
        "distinguish facts / inferences / assumptions（事實/推論/假設分離）",
    ),
    uncertainty_rule="證據不足以定因 → suspected_cause='inconclusive' 並建議更強的 check（保守）",
)

# interpret_result 的 PromptContract（role=解讀訓練結果；regime_caveat when bull-only）。
# 為什麼 template 明確要求 regime_caveat：out-of-bound guard 對「宣稱 promotion-ready 卻缺
# regime_caveat 且 metrics 標 bull-only」的 interpretation reject（design §E.2(0) line 872 +
# Alpha Evidence Governance：bull-only 結果是 regime-bet/learning-only，非 promotion proof）。
_ML_ADVISORY_INTERPRET_CONTRACT = PromptContract(
    contract_ref="ml_advisory.interpret_result.v1",
    contract_ver="ml_advisory_interpret.v1",
    output_schema_ref="ml_advisory.v1",
    schema_ver=_ML_ADVISORY_SCHEMA_VER,
    role="ML training-result interpreter（advisory-only；asserts NO alpha；separates signal from regime）",
    template=(
        "You are a deterministic interpreter of a completed ML training run for a crypto "
        "trading research system. You are given the run's metrics, feature importances, "
        "and the regime label under which it was trained. Your job is to give a sober "
        "reading of what the result means, separating a genuine signal from a regime "
        "artifact.\n"
        "HARD CONSTRAINTS:\n"
        "- You make NO alpha claim and NO promotion-readiness claim. You only interpret. "
        "A bull-only / rally-dominated / single-regime result is a regime-bet / "
        "learning-only observation, NOT promotion proof.\n"
        "- If the result is bull-only or rally-dominated, you MUST populate regime_caveat "
        "explaining the regime dependence. Do not present a regime-conditional result as "
        "regime-robust.\n"
        "- Do not invent signal axes that are not present in the feature set.\n"
        "Respond with ONLY a compact JSON object: "
        '{"mode":"interpret_result","result_interpretation":{"reading":"...",'
        '"regime_caveat":"...","confidence":"low|medium|high"}}'
    ),
    constraints=(
        "ALL output is advisory only（direction=neutral；AI≠命令）",
        "asserts NO alpha（interpret 不作 promotion-relevant 斷言）",
        "bull-only/rally-dominated = regime-bet/learning-only（Alpha Evidence Governance）",
        "regime_caveat mandatory when bull-only（out-of-bound guard 強制）",
        "the LLM NEVER validates alpha（P3a 無 alpha gate）",
    ),
    uncertainty_rule="無法分離 signal vs regime → confidence='low' + regime_caveat 說明依賴（保守）",
)

# hypothesize 的 PromptContract（P3b；role=生成可預註冊的 feature 假說；LLM 不作 alpha 斷言）。
# 為什麼 template 硬約束 mechanism + falsification_test + signal_axes_used + beta_neutralization_plan：
#   - 經濟 mechanism 非空：無 mechanism 的假說 = curve-fit（guard 的 empty-mechanism clause 會 reject）。
#   - falsification_test：每個假說須可證偽（科學紀律；avoids 不可否證的 just-so story）。
#   - signal_axes_used ⊆ available_signal_axes：捏造資料軸 → guard clause D reject。
#   - beta_neutralization_plan：假說須說明如何對 BTC+altcap 中性化（B1 是唯一 alpha validator，
#     LLM 不驗 alpha，但須產出可被 B1 驗的中性化計畫）。
# 鐵律（constraints 宣告）：LLM「永不」驗 alpha；math gate（B1+DSR+PBO+leak+Q1）是唯一 validator。
# 結果是 promotion-relevant verdict，但「晉升」是人工（demo_stage1=expand=MANUAL），0 新 live authority。
_ML_ADVISORY_HYPOTHESIZE_CONTRACT = PromptContract(
    contract_ref="ml_advisory.hypothesize.v1",
    contract_ver="ml_advisory_hypothesize.v1",
    output_schema_ref="ml_advisory.v1",
    schema_ver=_ML_ADVISORY_SCHEMA_VER,
    role="ML feature-hypothesis proposer（advisory-only；proposes pre-registerable hypotheses；asserts NO alpha）",
    template=(
        "You are a deterministic feature-hypothesis proposer for a crypto trading research "
        "system. You are given a completed training run's metrics, the available signal axes, "
        "and the regime label. Your job is to PROPOSE pre-registerable feature hypotheses for "
        "a downstream DETERMINISTIC math gate to validate. You do NOT validate them.\n"
        "HARD CONSTRAINTS:\n"
        "- You make NO alpha claim, NO edge claim, and NO promotion-readiness claim. A "
        "downstream deterministic math gate (beta-neutrality B1, DSR, PBO, leak-typing, "
        "trade-count) is the ONLY validator. You only propose what to test.\n"
        "- Each hypothesis MUST carry: a concrete economic mechanism (a non-empty causal "
        "story for why an edge could exist), a falsification_test (how it would be proven "
        "wrong), signal_axes_used (a subset of the provided available signal axes — do NOT "
        "invent axes), an expected_direction, and a beta_neutralization_plan (how the "
        "candidate would be made orthogonal to BTC and the altcap basket).\n"
        "- An empty or hand-wavy mechanism is curve-fitting and will be rejected.\n"
        "- A bull-only / rally-dominated / single-regime observation is a regime-bet / "
        "learning-only basis, NOT a promotion basis; mark such hypotheses with a regime_caveat.\n"
        "Respond with ONLY a compact JSON object: "
        '{"mode":"hypothesize","signal_axes_used":["..."],"feature_hypotheses":['
        '{"hid":"...","statement":"...","mechanism":"...","falsification_test":"...",'
        '"signal_axes_used":["..."],"expected_direction":"long|short|neutral",'
        '"beta_neutralization_plan":"..."}],"backlog_items":["..."]}'
    ),
    constraints=(
        "ALL output is advisory only（direction=neutral；AI≠命令，須經 Decision Lease + 風控）",
        "asserts NO alpha（hypothesize 只「提案」，不作 promotion-relevant alpha 斷言）",
        "the math gate is the ONLY alpha validator（B1+DSR+PBO+leak+Q1；LLM 永不驗 alpha）",
        "each hypothesis needs economic mechanism + falsification_test（無 mechanism = curve-fit，guard reject）",
        "signal_axes_used ⊆ available_signal_axes（捏造軸 → guard reject）",
        "bull-only = regime-bet/learning-only（Alpha Evidence Governance；須 regime_caveat）",
        "0 new live authority（pass-verdict → backlog；晉升人工 demo_stage1=expand=MANUAL）",
    ),
    uncertainty_rule="無可信機制可提 → 回空 feature_hypotheses（不捏造假說充數）",
)

# hypothesize v2（P4 §4.2(4)：falsification_test 結構化三欄 + primary_axis）。
# 為什麼 bump v2 而非改 v1：契約 frozen——D3 歷史 row 引用 v1 不可變（versioned 鐵律）；
# v1 保留供血緣回放，TOML stanza 的 prompt_contract_ref 同 commit 指 v2。
# v2 delta（QC FIX-1.2/1.3 + MIT ratify #4 的契約面）：
#   - falsification_test 從自由字串改為 {null_hypothesis, test_statistic, reject_condition}
#     三欄結構（pre-registration V138 prh_falsification_chk 兜底；guard clause F 驗非空；
#     math gate fail 時三欄入 dead-mode lesson = novelty 自饋失敗庫的可檢索證偽紀錄）。
#   - 每假說必宣告 primary_axis ∈ signal_axes_used（wealth family = capability:primary_axis，
#     MIT #4——拒 axes 組合鑄幣面；guard clause F 強制）。
_ML_ADVISORY_HYPOTHESIZE_CONTRACT_V2 = PromptContract(
    contract_ref="ml_advisory.hypothesize.v2",
    contract_ver="ml_advisory_hypothesize.v2",
    output_schema_ref="ml_advisory.v1",
    schema_ver=_ML_ADVISORY_SCHEMA_VER,
    role="ML feature-hypothesis proposer（advisory-only；pre-registerable + falsifiable；asserts NO alpha）",
    template=(
        "You are a deterministic feature-hypothesis proposer for a crypto trading research "
        "system. You are given a completed training run's metrics, the available signal axes, "
        "and the regime label. Your job is to PROPOSE pre-registerable feature hypotheses for "
        "a downstream DETERMINISTIC math gate to validate. You do NOT validate them.\n"
        "HARD CONSTRAINTS:\n"
        "- You make NO alpha claim, NO edge claim, and NO promotion-readiness claim. A "
        "downstream deterministic math gate (beta-neutrality B1, DSR, PBO, leak-typing, "
        "trade-count) is the ONLY validator. You only propose what to test.\n"
        "- Each hypothesis MUST carry: a concrete economic mechanism (a non-empty causal "
        "story for why an edge could exist), a STRUCTURED falsification_test object with "
        "three non-empty fields (null_hypothesis: the precise claim that the edge does NOT "
        "exist; test_statistic: the deterministic statistic that adjudicates it; "
        "reject_condition: the exact condition under which the hypothesis is proven wrong), "
        "signal_axes_used (a subset of the provided available signal axes — do NOT invent "
        "axes), a primary_axis (exactly one member of signal_axes_used naming the dominant "
        "signal source — it determines the FDR wealth family being charged), an "
        "expected_direction, and a beta_neutralization_plan (how the candidate would be "
        "made orthogonal to BTC and the altcap basket).\n"
        "- An empty or hand-wavy mechanism is curve-fitting and will be rejected. A "
        "free-text falsification_test (not the three-field object) will be rejected.\n"
        "- A bull-only / rally-dominated / single-regime observation is a regime-bet / "
        "learning-only basis, NOT a promotion basis; mark such hypotheses with a regime_caveat.\n"
        "Respond with ONLY a compact JSON object: "
        '{"mode":"hypothesize","signal_axes_used":["..."],"feature_hypotheses":['
        '{"hid":"...","statement":"...","mechanism":"...",'
        '"falsification_test":{"null_hypothesis":"...","test_statistic":"...",'
        '"reject_condition":"..."},"primary_axis":"...","signal_axes_used":["..."],'
        '"expected_direction":"long|short|neutral","beta_neutralization_plan":"..."}],'
        '"backlog_items":["..."]}'
    ),
    constraints=(
        "ALL output is advisory only（direction=neutral；AI≠命令，須經 Decision Lease + 風控）",
        "asserts NO alpha（hypothesize 只「提案」，不作 promotion-relevant alpha 斷言）",
        "the math gate is the ONLY alpha validator（B1+DSR+PBO+leak+Q1；LLM 永不驗 alpha）",
        "each hypothesis needs economic mechanism + structured falsification_test 三欄（缺 = guard reject）",
        "primary_axis ∈ signal_axes_used（FDR wealth family 錨點；捏造軸 → guard reject）",
        "signal_axes_used ⊆ available_signal_axes（捏造軸 → guard reject）",
        "bull-only = regime-bet/learning-only（Alpha Evidence Governance；須 regime_caveat）",
        "0 new live authority（pass-verdict → backlog；晉升人工 demo_stage1=expand=MANUAL）",
    ),
    uncertainty_rule="無可信機制可提 → 回空 feature_hypotheses（不捏造假說充數）",
)

_PROMPT_CONTRACTS: dict[str, PromptContract] = {
    _MANUAL_CONTRACT.contract_ref: _MANUAL_CONTRACT,
    _ML_ADVISORY_DIAGNOSE_CONTRACT.contract_ref: _ML_ADVISORY_DIAGNOSE_CONTRACT,
    _ML_ADVISORY_INTERPRET_CONTRACT.contract_ref: _ML_ADVISORY_INTERPRET_CONTRACT,
    _ML_ADVISORY_HYPOTHESIZE_CONTRACT.contract_ref: _ML_ADVISORY_HYPOTHESIZE_CONTRACT,
    _ML_ADVISORY_HYPOTHESIZE_CONTRACT_V2.contract_ref: _ML_ADVISORY_HYPOTHESIZE_CONTRACT_V2,
}

_OUTPUT_SCHEMAS: dict[str, OutputSchema] = {
    _MANUAL_SCHEMA.schema_ref: _MANUAL_SCHEMA,
    _ML_ADVISORY_SCHEMA.schema_ref: _ML_ADVISORY_SCHEMA,
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
    "ML_ADVISORY_MODE_REQUIRED_FIELDS",
    "ML_ADVISORY_LEAK_SOURCE_CLASSES",
    "ML_ADVISORY_LEAKFREE_SOURCE_CLASSES",
    "get_prompt_contract",
    "get_output_schema",
    "resolve_contract_versions",
]
