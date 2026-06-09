"""
MODULE_NOTE
模塊用途：
  L2 Advisory Mesh — ml_advisory capability 的 cascade executor（PA P3 設計 §C/§D/§G.2）。
  P3a 只跑兩個「斷言無 alpha」模式：diagnose_leak + interpret_result。它是 orchestrator
  dispatch（l2_advisory_orchestrator.py:300-301 seam）接的「各 capability executor」之一。

  P3a cascade（design §D line 169，diagnose/interpret 無 alpha math gate）：
    (1) Ollama screen（M4 校準，recall≥0.85；loose coarse screen，judge 本次 run 是否
        值得花一次 cloud call）。校準不過（recall<0.85）→ screen DISABLED：全數放行到
        gate（不丟 alpha，多花 cloud），且 flag MIT（gate-seam verdict="disabled"）。
    (2) cloud-L2 diagnose/interpret（單發 structured JSON，sonnet）——**只在 screen 放行的
        survivor 跑**（cost only on survivors，root principle 13）。LLM「永不」驗 alpha。
    (3) 確定性 guard（M3 source_class typing / regime_caveat；run_guard ml_advisory.guard.v1）
        ——guard 抓「形」，P3a 無 alpha math gate 故 M3 typing 是 P3a 主 gate（design §D line 169）。
    (4) advisory sink（agent.lessons，genuinely inert）+ D3 ledger（record_l2_call）+ 每階
        gate-seam（record_gate_seam）。

  為什麼 sink 是 agent.lessons（非 mlde_shadow_recommendations）：後者的 source='ml_shadow' +
  recommendation_type='regret_summary' 正是 active 的 mlde_demo_applier.py 掃描去 mutate demo
  RiskConfig 的 namespace（若其 MIN_CONFIDENCE=0，P3a 的中性診斷會被 applier 抓去改配置，違
  「0 新執行權」鐵律）。agent.lessons 是 L2 Reflexion 教訓索引庫——**無任何 applier/mutator 掃描
  它去執行**（只 layer2_critic.persist 寫、retrieve_lessons 唯讀檢索、layer2_engine 呼叫 persist），
  故「0 新執行權」在此 sink 上是**結構性成立**（genuinely inert），非靠 applied=false 旗標約束。

  鐵律（CC/E2/MIT grep target）：
    - LLM 永不驗 alpha：本模塊「無 alpha gate」（P3a 斷言無 alpha）；guard 只 typing/形檢。
    - direction=neutral、0 新執行權：sink 寫進 genuinely-inert 的 agent.lessons（無 applier
      掃描）；本模塊 import 無 order surface / IntentProcessor / place_order / acquire_lease /
      promote_tier / live-config write。
    - cost only on survivors：Ollama screen reject ⇒ 零 cloud call（短路）；guard reject ⇒
      不寫 sink（logged-and-dropped）。
    - prompt 確定性：cloud call 用 contract registry 的 checked-in 模板（Ollama/任何 model
      禁生成 prompt）；本模塊不自寫 prompt 字面，只取 PromptContract.template。
    - M3：diagnose 不得宣稱 leakage_check=leak-free PIT；交由 guard typing 強制（不在此放鬆）。

主要類/函數：
  - MlAdvisoryCascadeResult：cascade 結果（供 orchestrator 投影 + 測試斷言）。
  - run_ml_advisory_cascade(...)：async cascade 入口（orchestrator dispatch 接此）。
  - OllamaScreenCalibration：M4 校準機制（held-out benchmark → recall → <0.85 disable）。
      benchmark data 是 MIT-owned（本模塊建「機制」+ 初始 placeholder，不捏造 benchmark）。
  - write_ml_advisory_advisory_sink(...)：薄 sink writer（寫 genuinely-inert 的 agent.lessons，
      content 過 secret redactor）。

依賴（reuse；PA §K）：
  - l2_prompt_contract_registry（PromptContract.template + per-mode 必填 + M3 source_class 常數）。
  - l2_out_of_bound_guard.run_guard（確定性 M3 typing / regime_caveat guard）。
  - l2_call_ledger_writer（D3：record_l2_call / record_gate_seam）。
  - l2_secret_redactor.redact（sink content 落 durable store 前消毒；與 critic 寫 agent.lessons
      同一消毒語意——沒有任何 L2 衍生文本以未消毒形進入難清除的 append-only store）。
  - layer2_engine.Layer2Engine（cloud-L2 + Ollama 呼叫經 engine._provider_complete，不自建 provider）。
  - layer2_cost_tracker（cost 記帳經 engine._cost_tracker；per-cap spend 經 orchestrator）。
  - db_pool.get_pg_conn（advisory sink INSERT；fail-soft）。

硬邊界：
  - async executor；無新 mutable singleton（純函數 + 注入式依賴；OllamaScreenCalibration 是
    讀 settings/artifact 的 stateless helper，無 process-global binding）。
  - 任何失敗 fail-soft：cloud 不可用 / DB 不可用 / parse 失敗 → 回 ok=False，NEVER raise 進
    orchestrator dispatch（advisory 失敗只「減去」L2 能力，不阻塞 baseline）。
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import db_pool
from . import l2_out_of_bound_guard as _guard
from . import l2_prompt_contract_registry as _contracts
from . import l2_secret_redactor as _redactor
from .l2_call_ledger_writer import get_l2_call_ledger_writer as _get_l2_ledger_writer

logger = logging.getLogger("l2_ml_advisory_executor")

# P3a 合法模式（斷言無 alpha）。hypothesize 是 P3b（alpha-bearing），本模塊不含——未知 mode
# 在 cascade 入口 fail-closed reject（不誤跑 P3b 模式）。
_P3A_MODES: frozenset[str] = frozenset({"diagnose_leak", "interpret_result"})

# 模式 → PromptContract ref（contract registry 是唯一模板來源；本模塊不複製字面模板）。
_MODE_CONTRACT_REF: dict[str, str] = {
    "diagnose_leak": "ml_advisory.diagnose_leak.v1",
    "interpret_result": "ml_advisory.interpret_result.v1",
}

# cloud-L2 interpret 的 max_tokens（單發 structured JSON 診斷/解讀，非 agentic session）。
_CLOUD_MAX_TOKENS = 1024
_CLOUD_TIMEOUT_S = 60.0

# Ollama screen 的 max_tokens（loose coarse screen，只回一個短 JSON verdict）。
_SCREEN_MAX_TOKENS = 64
_SCREEN_TIMEOUT_S = 30.0

# M4：screen recall floor（design §G.2.1 line 1267；PA default 0.85，MIT 可調高）。
_SCREEN_RECALL_FLOOR = 0.85


# ═══════════════════════════════════════════════════════════════════════════════
# M4 — Ollama screen 校準機制（held-out benchmark → recall → <0.85 disable screen）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼是「機制 + placeholder」而非寫死 enable：benchmark data（good=歷史 demo-confirmed
# discoveries / 正確 post-hoc diagnoses；bad=agent.lessons V133 dead-modes）是 MIT-owned
# （design §G.2.1 line 1276-1277）。E1 建「量 recall → 低於 floor 就 disable screen 全進 gate
# + flag MIT」的機制；初始無 benchmark artifact 時 fail-closed 到「screen DISABLED」（safer：
# 全進 gate，多花 cloud 但不丟 alpha；design line 1271-1272 的退化方向）。MIT 落 benchmark
# artifact 後本機制即量真 recall。
#
# 為什麼「無 benchmark → DISABLED（全進 gate）」是正確的 fail-safe：screen 的風險是「漏殺
# good hypothesis」（false-kill 真 alpha）。未校準的 screen 無 recall 保證，啟用它可能 false-
# kill；停用它只是多花 cloud（math/guard gate 仍兜底 precision）。故 fail-closed = 停用 screen，
# 對齊 design line 1271「below recall 0.85 → screen DISABLED」。


@dataclass
class OllamaScreenCalibration:
    """M4 screen 校準結果。enabled=False ⇒ screen 停用（全進 gate + flag MIT）。

    為什麼 dataclass（非 singleton）：每次 cascade 讀一次 calibration artifact（stateless）；
    無 process-global mutable state（避免 singleton 註冊負擔；artifact 是 SSOT）。
    """

    enabled: bool  # screen 是否啟用（recall≥floor 且有 benchmark）
    recall: float | None  # 量到的 recall（無 benchmark → None）
    threshold: float  # recall floor（design line 1267）
    benchmark_version: str  # benchmark artifact 版本（無 → "absent"）
    reason: str  # disabled 原因（供 gate-seam + MIT flag）

    def to_seam_details(self) -> dict[str, Any]:
        """gate-seam details（design §G line 240：record recall/threshold/version）。"""
        return {
            "recall": self.recall,
            "threshold": self.threshold,
            "benchmark_version": self.benchmark_version,
            "reason": self.reason,
        }


def _calibration_artifact_path() -> Path:
    """M4 benchmark/校準 artifact 路徑（跨平台；reuse capability_registry 範式）。

    為什麼 OPENCLAW_BASE_DIR env + parents[5] fallback：禁硬編 /home/ncyu /Users/ncyu
    （CLAUDE §六 portable）；與 l2_capability_registry._default_registry_path 同範式。
    artifact 由 MIT 產（held-out benchmark + 量到的 recall）；E1 只讀。
    """
    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path(__file__).resolve().parents[5])))
    return base / "settings" / "l2_ml_advisory_screen_calibration.json"


def load_ollama_screen_calibration(
    *, artifact_path: Path | str | None = None, recall_floor: float = _SCREEN_RECALL_FLOOR
) -> OllamaScreenCalibration:
    """讀 M4 校準 artifact，回 OllamaScreenCalibration。fail-closed：無 artifact / 壞 / recall<floor
    → enabled=False（screen 停用，全進 gate + flag MIT）。

    artifact schema（MIT-owned；E1 只定 schema + 讀）：
      {"benchmark_version": "<ver>", "recall": <float 0..1>, "measured_at": "<iso>", ...}

    為什麼 fail-closed 到 DISABLED（非 ENABLED）：未校準/低 recall 的 screen 可能 false-kill 真
    alpha；停用只是多花 cloud（gate 兜底 precision）。對齊 design line 1271-1272。
    """
    p = Path(artifact_path) if artifact_path is not None else _calibration_artifact_path()
    if not p.exists():
        # 初始無 benchmark（MIT 尚未產）→ screen DISABLED（全進 gate；safer，不丟 alpha）。
        return OllamaScreenCalibration(
            enabled=False, recall=None, threshold=recall_floor,
            benchmark_version="absent",
            reason="no_benchmark_artifact_screen_disabled_flag_mit",
        )
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — 壞 artifact → fail-closed DISABLED（不啟用未驗 screen）
        logger.warning("M4 screen calibration artifact 壞，screen DISABLED（flag MIT）：%s", exc)
        return OllamaScreenCalibration(
            enabled=False, recall=None, threshold=recall_floor,
            benchmark_version="malformed",
            reason="malformed_benchmark_artifact_screen_disabled_flag_mit",
        )
    recall = raw.get("recall")
    bver = str(raw.get("benchmark_version", "unknown"))
    try:
        recall_f = float(recall) if recall is not None else None
    except (TypeError, ValueError):
        recall_f = None
    if recall_f is None:
        return OllamaScreenCalibration(
            enabled=False, recall=None, threshold=recall_floor, benchmark_version=bver,
            reason="recall_missing_screen_disabled_flag_mit",
        )
    if recall_f < recall_floor:
        # recall < floor → screen DISABLED（design line 1271：全進 gate + flag MIT）。
        return OllamaScreenCalibration(
            enabled=False, recall=recall_f, threshold=recall_floor, benchmark_version=bver,
            reason=f"recall_{recall_f:.3f}_below_floor_{recall_floor:.2f}_screen_disabled_flag_mit",
        )
    # recall≥floor 且有 benchmark → screen ENABLED（loose；removing obvious dead-modes）。
    return OllamaScreenCalibration(
        enabled=True, recall=recall_f, threshold=recall_floor, benchmark_version=bver,
        reason="calibrated",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# cascade 結果型別
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class MlAdvisoryCascadeResult:
    """cascade 最終結果（供 orchestrator 投影 + 測試斷言）。

    stage：cascade 停在哪階（screen_rejected / cloud_unavailable / parse_failed /
      guard_rejected / sink_written / disabled_input）。
    """

    ok: bool
    mode: str
    stage: str
    screen_passed: bool = False
    screen_disabled: bool = False  # M4：screen 停用（全進 gate），供 MIT 審計
    cloud_called: bool = False
    guard_verdict: str | None = None
    sink_written: bool = False
    l2_reply_id: str | None = None
    cost_usd: float = 0.0
    notes: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Ollama screen（M4-gated；loose coarse screen）
# ═══════════════════════════════════════════════════════════════════════════════


# 為什麼 screen prompt 是 checked-in 常數：Ollama 禁生成 prompt（鐵律）。screen 只做 loose
# coarse 判斷「本 run 是否值得花一次 cloud diagnose/interpret」——強烈偏向放行（recall-tuned，
# precision 由 guard 兜底；design line 1267）。它「不」驗 alpha、「不」下任何 promotion 判斷。
_SCREEN_SYSTEM_PROMPT = (
    "You are a loose, recall-tuned coarse screen for an ML-pipeline diagnostic advisor. "
    "Given a completed training run's summary, decide ONLY whether it is worth spending a "
    "deeper analysis call on. Strongly bias toward 'pass'. Choose 'skip' ONLY if the run "
    "summary is empty/degenerate (no metrics at all). You make NO alpha claim and NO "
    "promotion judgment.\n"
    'Respond with ONLY a compact JSON object: {"verdict":"pass|skip","reason":"<=12 words"}'
)


async def _run_ollama_screen(
    engine: Any, *, mode: str, context: dict[str, Any]
) -> tuple[bool, str, float]:
    """跑 Ollama loose coarse screen（reuse engine._provider_complete role=triage）。

    回 (passed, reason, cost_usd)。fail-soft：provider 不可用 / 非 JSON / 例外 → passed=True
    （recall-first：screen 失敗時「放行到 gate」而非誤殺，對齊 design line 1271 退化方向）。
    """
    try:
        from . import provider_client as _pc  # noqa: PLC0415 — 避免 import cycle

        cfg = engine._cost_tracker.get_config()
        base_provider = cfg.default_provider or _pc.PROVIDER_ANTHROPIC
        # role="triage"：強制 effective provider 的 cheapest tier（screen 是便宜粗篩）。
        eff_provider, eff_tier = engine._resolve_effective_provider(
            base_provider=base_provider, base_tier=_pc.TIER_HAIKU, role="triage",
        )
        screen_input = (
            f"mode={mode}\n"
            f"run summary (truncated):\n{json.dumps(context, ensure_ascii=False, default=str)[:1500]}"
        )
        resp = await engine._provider_complete(
            provider_name=eff_provider, tier=eff_tier,
            system_prompt=_SCREEN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": screen_input}],
            tools=None, max_tokens=_SCREEN_MAX_TOKENS, timeout=_SCREEN_TIMEOUT_S,
        )
        if resp is None:
            # provider 不可用 → 放行到 gate（recall-first；不丟可能的 good run）。
            return True, "screen_provider_unavailable_pass_through", 0.0
        # 記帳（triage tier；pricing 缺條目不致命）。
        cost = _record_call_cost(engine, resp, eff_tier)
        try:
            parsed = json.loads(resp.text or "{}")
        except (json.JSONDecodeError, TypeError):
            return True, "screen_non_json_pass_through", cost
        verdict = str(parsed.get("verdict", "")).lower()
        if verdict == "skip":
            return False, str(parsed.get("reason", "screen_skip"))[:120], cost
        # 任何非 "skip"（含 "pass" / 未知）→ 放行（loose；偏向 pass）。
        return True, str(parsed.get("reason", "screen_pass"))[:120], cost
    except Exception as exc:  # noqa: BLE001 — screen 必 fail-soft（放行到 gate，不誤殺）
        logger.warning("ml_advisory Ollama screen fail-soft → pass-through: %s", exc)
        return True, "screen_exception_pass_through", 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# cloud-L2 diagnose/interpret（單發 structured JSON；contract registry 模板）
# ═══════════════════════════════════════════════════════════════════════════════


async def _run_cloud_interpret(
    engine: Any, *, mode: str, context: dict[str, Any]
) -> tuple[dict[str, Any] | None, str, float, str, dict[str, Any]]:
    """跑 cloud-L2 diagnose/interpret（單發；用 contract registry 的 checked-in 模板）。

    回 (parsed_output, raw_response, cost_usd, system_prompt, meta)。LLM「永不」驗 alpha——
    此步只 diagnose/interpret（contract template 內已硬約束「asserts NO alpha」）。

    為什麼用 _provider_complete 單發（非 run_session agentic loop）：diagnose/interpret 是
    「對結構化 context 出一個 structured JSON」的確定性單發，非多輪工具 agentic session。
    prompt 是 PromptContract.template（checked-in；Ollama/model 禁生成）。
    """
    from . import provider_client as _pc  # noqa: PLC0415

    contract_ref = _MODE_CONTRACT_REF[mode]
    pc = _contracts.get_prompt_contract(contract_ref)
    system_prompt = pc.template if pc is not None else ""
    meta: dict[str, Any] = {"contract_ref": contract_ref}

    cfg = engine._cost_tracker.get_config()
    base_provider = cfg.default_provider or _pc.PROVIDER_ANTHROPIC
    # role="agent"：用 base_tier（sonnet）；fallback 觸發時走 fallback tier（cost-aware）。
    eff_provider, eff_tier = engine._resolve_effective_provider(
        base_provider=base_provider, base_tier=_pc.TIER_SONNET, role="agent",
    )
    meta["model"] = f"{eff_provider}:{eff_tier}"

    user_input = (
        f"Training run context (structured, extracted from the pipeline):\n"
        f"{json.dumps(context, ensure_ascii=False, default=str)[:6000]}"
    )
    resp = await engine._provider_complete(
        provider_name=eff_provider, tier=eff_tier,
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": user_input}],
        tools=None, max_tokens=_CLOUD_MAX_TOKENS, timeout=_CLOUD_TIMEOUT_S,
    )
    if resp is None:
        return None, "", 0.0, system_prompt, meta
    cost = _record_call_cost(engine, resp, eff_tier)
    raw = resp.text or ""
    try:
        parsed = json.loads(raw or "{}")
        if not isinstance(parsed, dict):
            parsed = None
    except (json.JSONDecodeError, TypeError):
        parsed = None
    return parsed, raw, cost, system_prompt, meta


def _record_call_cost(engine: Any, resp: Any, eff_tier: str) -> float:
    """經 engine._cost_tracker.record_claude_cost 記一次呼叫成本（reuse 既有記帳 + 更新 DOC-08
    daily counter）。回 cost_usd（供 per-cap spend 累計 + D3 row）。

    為什麼用 record_claude_cost（非自估）：它是「真記帳 + 更新 daily_spend.<day>.total_usd」的
    single source——check_daily_budget 讀的就是這個 counter。ml_advisory 的 cloud/screen 花費
    必須計入全域 DOC-08 $2/day（否則 admission budget 閘看不到 ml_advisory 花費 = 漏 storm 防護）。
    用一個臨時 Layer2Session 承接記帳（ml_advisory cascade 非 agentic session，無常駐 session 物件）。
    """
    cost = 0.0
    try:
        from .layer2_types import Layer2Session  # noqa: PLC0415 — 避免 import cycle

        tracker = engine._cost_tracker
        in_tok = int(getattr(resp, "input_tokens", 0) or 0)
        out_tok = int(getattr(resp, "output_tokens", 0) or 0)
        # 臨時 session 承接記帳；record_claude_cost 用 tracker._pricing 算 cost 並更新 daily counter。
        tmp_session = Layer2Session(trigger="ml:training_complete")
        cost = float(tracker.record_claude_cost(tmp_session, in_tok, out_tok, eff_tier))
    except Exception as exc:  # noqa: BLE001 — 記帳失敗不阻斷 cascade（cost 仍由 admission 閘兜底）
        logger.warning("ml_advisory cost 記帳 skipped (fail-soft): %s", exc)
    return cost


# ═══════════════════════════════════════════════════════════════════════════════
# advisory sink（agent.lessons；genuinely inert——無 applier 掃描）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼 sink 是 agent.lessons（operator 拍板，取代 mlde_shadow_recommendations）：
#   1. 安全（0 新執行權結構性成立）：mlde_shadow_recommendations 的 source='ml_shadow' +
#      recommendation_type='regret_summary' 正是 active 的 mlde_demo_applier.py:451 掃描去 mutate
#      demo RiskConfig 的 namespace；若 applier MIN_CONFIDENCE=0，P3a 的中性診斷會被抓去改配置。
#      agent.lessons **無任何 applier/mutator 掃描它去執行**（只 layer2_critic.persist 寫、
#      retrieve_lessons 唯讀 pg_trgm 檢索、layer2_engine 呼叫 persist），故此 sink genuinely inert。
#   2. schema-clean：mlde_shadow_recommendations 在 prod 會寫失敗（evidence_source_tier V040
#      NOT NULL 無 default + V051 paired-CHECK + V037 REVOKE PUBLIC INSERT 繞 sanctioned 路徑）。
#
# 寫法（reuse critic 既有 redactor-protected 寫路徑語意；V133 schema）：
#   - content：診斷/解讀蒸餾成 "title: detail" 形（reuse critic 的 content 構造慣例）。
#   - content **必過 l2_secret_redactor.redact()** 再落庫（與 layer2_critic._persist_lessons_sync
#     同一消毒語意：LLM 蒸餾自由文本可能 drift 進 secret，落 append-only durable store 前消毒）。
#   - context_id = l2_reply_id（D3 provenance 鏈；P1 已映此——lesson 可逆溯回產生它的 L2 呼叫）。
#   - source='ml_advisory'：與 critic lessons（source='l2_session'）**分離 namespace**，避免污染
#     critic 的 pg_trgm 檢索池語義，且使 sink 可被 filter/audit 為 ml_advisory-origin。
#   - symbol：候選標的（NOT NULL；無則用佔位 'ml_advisory'，不阻斷診斷落庫）。
#   - lesson_type=mode（diagnose_leak / interpret_result）；outcome_net_bps 恆 NULL（無 edge 斷言）。
_SINK_SOURCE = "ml_advisory"  # 與 critic lessons（'l2_session'）分離；ml_advisory-origin discriminator
_SINK_SYMBOL_PLACEHOLDER = "ml_advisory"  # symbol 為 V133 NOT NULL；候選無 symbol 時的佔位（不阻斷落庫）


def write_ml_advisory_advisory_sink(
    *,
    engine_mode: str,
    mode: str,
    parsed_output: dict[str, Any],
    l2_reply_id: str,
    symbol: str | None = None,
    strategy_name: str | None = None,
    trigger: str = "ml:training_complete",
    conn_provider: Any = None,
) -> dict[str, Any]:
    """把 ml_advisory 診斷/解讀寫進 genuinely-inert 的 agent.lessons（V133）。回 {ok, sink_state,
    errors}。fail-soft：DB 不可用 → ok=False 不 raise。

    為什麼 0 新執行權在此 sink 結構性成立：agent.lessons 無任何 applier/mutator 掃描它去執行
    （不像 mlde_shadow_recommendations 被 mlde_demo_applier 掃描去 mutate demo RiskConfig）；它純粹
    是 L2 Reflexion 教訓索引庫（persist 寫 / retrieve 唯讀）。

    硬不變式：
      - content **必過 l2_secret_redactor.redact()** 再落庫（無未消毒文本進 append-only durable
        store；與 layer2_critic._persist_lessons_sync 同一消毒語意）。redact-then-truncate[:4000]。
      - context_id = l2_reply_id（D3 provenance 鏈：lesson 可逆溯回 agent.l2_calls）。
      - source='ml_advisory'（與 critic lessons 分離 namespace）。
      - session_trigger = trigger（cascade 真實觸發源；非硬編，與 D3 ledger 的 trigger 一致）。
    """
    provider = conn_provider or db_pool.get_pg_conn
    result: dict[str, Any] = {"ok": True, "sink_state": "ml_advisory_advisory_recorded", "errors": []}

    # content：診斷/解讀蒸餾成 "title: detail" 形（reuse critic 的 content 構造慣例），payload
    # 帶 mode + l2_reply_id（D3 回溯）+ engine_mode/strategy_name（reconstructable）+ 完整 parsed
    # 診斷/解讀 + asserts_no_alpha。
    content = _build_lesson_content(
        mode=mode, parsed_output=parsed_output, l2_reply_id=l2_reply_id,
        engine_mode=engine_mode, strategy_name=strategy_name,
    )
    # D3 sanitize（D.1.1「applies everywhere」）：落 append-only agent.lessons 前過 secret redactor
    # （與 critic 寫路徑同一消毒語意），確保沒有未消毒的 L2 衍生文本進入難清除的 durable store。
    content = _redactor.redact(content).text[:4000]
    # symbol 為 V133 NOT NULL：候選無 symbol 時用佔位（診斷本就可能無單一標的，不阻斷落庫）。
    sym = (symbol or "").strip() or _SINK_SYMBOL_PLACEHOLDER

    try:
        with provider() as conn:
            if conn is None:
                result["ok"] = False
                result["sink_state"] = "ml_advisory_sink_skipped_db_unavailable"
                result["errors"].append("db_unavailable")
                return result
            try:
                cur = conn.cursor()
                # 參數化 INSERT（symbol/content 等皆綁定參數）。lesson_type=mode；context_id=
                # l2_reply_id（D3 鏈）；outcome_net_bps 恆 NULL（無 edge 斷言）；source='ml_advisory'。
                cur.execute(
                    """
                    INSERT INTO agent.lessons (
                        symbol, lesson_type, content, session_trigger,
                        context_id, outcome_net_bps, session_cost_usd, source
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, NULL, NULL, %s
                    )
                    """,
                    (
                        sym, mode, content, trigger,
                        l2_reply_id, _SINK_SOURCE,
                    ),
                )
                conn.commit()
            except Exception as exc:  # noqa: BLE001 — 寫失敗 rollback + fail-soft
                result["ok"] = False
                result["sink_state"] = "ml_advisory_sink_write_failed"
                result["errors"].append("insert_failed")
                logger.warning("ml_advisory advisory sink insert failed (fail-soft): %s", exc)
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    pass
    except Exception as exc:  # noqa: BLE001 — 連線層失敗亦 fail-soft
        result["ok"] = False
        result["sink_state"] = "ml_advisory_sink_write_failed"
        result["errors"].append("conn_failed")
        logger.warning("ml_advisory advisory sink conn failed (fail-soft): %s", exc)
    return result


def _build_lesson_content(
    *,
    mode: str,
    parsed_output: dict[str, Any],
    l2_reply_id: str,
    engine_mode: str | None = None,
    strategy_name: str | None = None,
) -> str:
    """把 ml_advisory 診斷/解讀蒸餾成 agent.lessons.content 字串（"title: detail" 形）。

    為什麼帶完整 parsed JSON + engine_mode/strategy_name：lesson 須 reconstructable（root
    principle 8）——content 嵌 l2_reply_id（D3 回溯）+ asserts_no_alpha 標記（P3a 斷言無 alpha，非
    edge/promotion 推薦）+ engine_mode/strategy_name（agent.lessons 無對應欄，嵌 content 保留可溯）+
    完整 parsed 物件。**此字串隨後整體過 redactor**，故此處不做任何消毒（消毒在唯一 write path）。
    """
    title = f"ml_advisory:{mode}"
    body = {
        "ml_advisory_mode": mode,
        "l2_reply_id": l2_reply_id,
        "engine_mode": engine_mode,
        "strategy_name": strategy_name,
        "advisory": parsed_output,
        "asserts_no_alpha": True,  # P3a 斷言無 alpha（非 edge/promotion 推薦）
    }
    detail = json.dumps(body, ensure_ascii=False, default=str)
    return f"{title}: {detail}"


# ═══════════════════════════════════════════════════════════════════════════════
# cascade 入口（orchestrator dispatch 接此）
# ═══════════════════════════════════════════════════════════════════════════════


async def run_ml_advisory_cascade(
    *,
    capability_id: str,
    mode: str,
    context: dict[str, Any],
    engine: Any,
    contract_ver: str,
    schema_ver: str,
    trigger: str = "ml:training_complete",
    engine_mode: str = "demo",
    symbol: str | None = None,
    strategy_name: str | None = None,
    available_signal_axes: list[str] | None = None,
    bull_only: bool = False,
    calibration: OllamaScreenCalibration | None = None,
    sink_conn_provider: Any = None,
    spend_recorder: Any = None,
) -> MlAdvisoryCascadeResult:
    """P3a ml_advisory cascade：Ollama screen（M4）→ cloud-L2 diagnose/interpret（survivors only）
    → 確定性 guard（M3 typing）→ advisory sink + D3。

    參數：
      - mode ∈ {diagnose_leak, interpret_result}（P3a；未知/hypothesize → fail-closed reject）。
      - context：結構化 input（pipeline 抽取，非 model-authored）。
      - engine：Layer2Engine（cloud-L2 + Ollama 呼叫 + cost 記帳的 single source）。
      - contract_ver/schema_ver：orchestrator 由 contract registry 解析（寫每 D3 row）。
      - available_signal_axes：guard 的 no-inventing-data 軸清單（parquet_etl.EDGE_P3_FEATURE_NAMES）。
      - bull_only：metrics 是否標 bull-only（guard regime_caveat clause 用）。
      - calibration：M4 screen 校準（None → 即時 load_ollama_screen_calibration）。
      - spend_recorder：per-cap 花費累計 callback（orchestrator.record_capability_spend），可選。

    回 MlAdvisoryCascadeResult。LLM 永不驗 alpha；cost only on survivors；guard reject ⇒ 不寫 sink。
    """
    result = MlAdvisoryCascadeResult(ok=False, mode=mode, stage="init")
    writer = _get_l2_ledger_writer()
    l2_reply_id = f"l2r:{uuid.uuid4().hex[:12]}"
    result.l2_reply_id = l2_reply_id
    started = time.time()

    # ── fail-closed：未知/非 P3a mode（含 hypothesize=P3b）→ reject，零 model 呼叫 ──
    if mode not in _P3A_MODES:
        result.stage = "unknown_mode_rejected"
        result.notes.append(f"mode={mode} 非 P3a 合法模式（diagnose_leak/interpret_result）")
        _seam(writer, l2_reply_id, "ml_advisory_mode", "reject",
              {"mode": mode, "reason": "unknown_or_p3b_mode"})
        return result

    # ── STAGE 1 — Ollama screen（M4-gated；loose coarse）──
    calib = calibration if calibration is not None else load_ollama_screen_calibration()
    if not calib.enabled:
        # M4：screen 停用（無 benchmark / recall<floor / 壞 artifact）→ 全進 gate + flag MIT。
        result.screen_disabled = True
        result.screen_passed = True  # 全進 gate（不丟 alpha）
        result.notes.append(f"ollama_screen_disabled:{calib.reason}")
        _seam(writer, l2_reply_id, "ollama_screen", "disabled", calib.to_seam_details())
    else:
        passed, reason, screen_cost = await _run_ollama_screen(engine, mode=mode, context=context)
        result.cost_usd += screen_cost
        result.screen_passed = passed
        _seam(writer, l2_reply_id, "ollama_screen", "pass" if passed else "reject",
              {"reason": reason, **calib.to_seam_details()})
        if not passed:
            # screen reject → 零 cloud call（cost only on survivors；短路）。
            result.stage = "screen_rejected"
            result.notes.append(f"ollama_screen_skip:{reason}")
            _record_spend(spend_recorder, capability_id, result.cost_usd)
            return result

    # ── STAGE 2 — cloud-L2 diagnose/interpret（survivors only；LLM 永不驗 alpha）──
    parsed, raw, cloud_cost, system_prompt, cloud_meta = await _run_cloud_interpret(
        engine, mode=mode, context=context
    )
    result.cost_usd += cloud_cost
    result.cloud_called = True
    model_str = str(cloud_meta.get("model", "cloud_l2"))

    if parsed is None:
        # cloud 不可用 / 非 JSON → fail-soft（D3 記 error，不寫 sink）。
        result.stage = "cloud_unavailable_or_unparsable"
        result.notes.append("cloud diagnose/interpret 回 None 或非 JSON dict")
        _ledger(writer, l2_reply_id=l2_reply_id, capability_id=capability_id, trigger=trigger,
                model=model_str, contract_ver=contract_ver, schema_ver=schema_ver,
                system_prompt=system_prompt, context=context, raw_response=raw,
                parsed_output=None, guard_verdict=None, cost_usd=result.cost_usd,
                latency_ms=int((time.time() - started) * 1000))
        _record_spend(spend_recorder, capability_id, result.cost_usd)
        return result

    # ── STAGE 3 — 確定性 guard（M3 source_class typing / regime_caveat）──
    # guard 抓「形」；P3a 無 alpha math gate，故 M3 typing 是 P3a 主 gate（design §D line 169）。
    guard_ctx: dict[str, Any] = {"bull_only": bull_only}
    if available_signal_axes is not None:
        guard_ctx["available_signal_axes"] = available_signal_axes
    gres = _guard.run_guard(parsed, guard_ref="ml_advisory.guard.v1", context=guard_ctx)
    result.guard_verdict = gres.verdict
    _seam(writer, l2_reply_id, "ml_advisory_guard", gres.verdict,
          {"mode": mode, "kinds_hit": gres.kinds_hit})

    # fact/inference/assumption 標籤（design §E.2(0) line 848）：診斷/解讀的證據 kind。
    fact_inf_assm = _extract_fact_inf_assm(mode, parsed)

    # 不論 guard verdict 皆寫 D3 ledger（reconstructable；root principle 8）——guard reject 也要
    # 入庫（記錄被擋的 model 輸出 + guard_verdict），但「不」route 給 sink。
    guard_out = gres.clamped_output if gres.clamped_output is not None else parsed
    _ledger(writer, l2_reply_id=l2_reply_id, capability_id=capability_id, trigger=trigger,
            model=model_str, contract_ver=contract_ver, schema_ver=schema_ver,
            system_prompt=system_prompt, context=context, raw_response=raw,
            parsed_output=guard_out, guard_verdict=gres.verdict, fact_inf_assm=fact_inf_assm,
            cost_usd=result.cost_usd, latency_ms=int((time.time() - started) * 1000))

    if gres.verdict == "reject":
        # guard reject ⇒ logged-and-dropped（不寫 sink；M3 typing 失敗 / regime_caveat 缺漏）。
        result.stage = "guard_rejected"
        result.notes.append(f"guard reject: {','.join(gres.kinds_hit)}")
        _record_spend(spend_recorder, capability_id, result.cost_usd)
        return result

    # ── STAGE 4 — advisory sink（agent.lessons，genuinely inert；0 新執行權結構性成立）──
    sink_res = write_ml_advisory_advisory_sink(
        engine_mode=engine_mode, mode=mode, parsed_output=guard_out, l2_reply_id=l2_reply_id,
        symbol=symbol, strategy_name=strategy_name, trigger=trigger, conn_provider=sink_conn_provider,
    )
    result.sink_written = bool(sink_res.get("ok"))
    # gate-seam details：標 sink 為 genuinely-inert（agent.lessons 無 applier 掃描）——0 新執行權
    # 在此 sink 結構性成立，非靠旗標約束（故不再記已不存在的 applied/requires_governance 欄語意）。
    _seam(writer, l2_reply_id, "ml_advisory_sink",
          "pass" if result.sink_written else "reject",
          {"sink_state": sink_res.get("sink_state"), "sink_table": "agent.lessons",
           "inert": True, "no_applier_scan": True})

    result.ok = result.sink_written
    result.stage = "sink_written" if result.sink_written else "sink_write_failed"
    if not result.sink_written:
        result.notes.append(f"sink write failed: {sink_res.get('errors')}")
    _record_spend(spend_recorder, capability_id, result.cost_usd)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 內部 helper（D3 ledger / gate-seam / spend / fact-inf-assm）
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_fact_inf_assm(mode: str, parsed: dict[str, Any]) -> dict[str, Any]:
    """從 parsed 輸出抽 fact/inference/assumption 標籤（design §E.2(0) line 848）。

    為什麼：D3 row 的 fact_inf_assm 欄分離「事實/推論/假設」（root principle 10）。diagnose 的
    evidence[].kind / interpret 的 confidence 是這條分離的載體；缺則記空（不捏造標籤）。
    """
    fia: dict[str, Any] = {"mode": mode}
    if mode == "diagnose_leak":
        diag = parsed.get("leak_drift_diagnosis")
        if isinstance(diag, dict):
            ev = diag.get("evidence")
            if isinstance(ev, (list, tuple)):
                fia["evidence_kinds"] = [
                    e.get("kind") for e in ev if isinstance(e, dict)
                ]
            fia["suspected_cause"] = diag.get("suspected_cause")
    elif mode == "interpret_result":
        interp = parsed.get("result_interpretation")
        if isinstance(interp, dict):
            fia["confidence"] = interp.get("confidence")
            fia["has_regime_caveat"] = bool(
                isinstance(interp.get("regime_caveat"), str)
                and interp.get("regime_caveat", "").strip()
            )
    return fia


def _seam(writer: Any, l2_reply_id: str, gate_id: str, verdict: str, details: dict[str, Any]) -> None:
    """落一筆 gate-seam（fail-soft：寫失敗不阻斷 cascade）。

    verdict 必 ∈ pass|clamp|reject（DB CHECK 強制）；M4 screen 停用用 "disabled" 不入 seam
    verdict CHECK 集合——故 disabled 映射為 reject-語義不對，改記為「seam details 帶 reason，
    verdict 用 pass」會誤導。實際處理：screen 停用記 verdict="reject" 會誤判 screen 殺了它；
    正確語義是「screen 被旁路（全進 gate）」。故 disabled 用 applied_as 攜帶，verdict 取 "pass"
    （screen 未阻擋，artifact 仍前進）。見呼叫端對 disabled 的處理。
    """
    try:
        # disabled（M4 screen 旁路）：artifact 未被 screen 阻擋（全進 gate）→ verdict="pass"，
        # 以 applied_as="screen_disabled" 攜帶語義（不誤記為 reject 殺它）。
        seam_verdict = verdict
        applied_as = None
        if verdict == "disabled":
            seam_verdict = "pass"
            applied_as = "screen_disabled_flag_mit"
        writer.record_gate_seam(
            l2_reply_id=l2_reply_id, gate_id=gate_id, verdict=seam_verdict,
            applier="ml_advisory_cascade", applied_as=applied_as, details=details,
        )
    except Exception as exc:  # noqa: BLE001 — gate-seam fail-soft
        logger.warning("ml_advisory gate-seam 記錄 skipped (fail-soft): %s", exc)


def _ledger(
    writer: Any, *, l2_reply_id: str, capability_id: str, trigger: str, model: str,
    contract_ver: str, schema_ver: str, system_prompt: str, context: dict[str, Any],
    raw_response: str, parsed_output: dict[str, Any] | None, guard_verdict: str | None,
    cost_usd: float, latency_ms: int | None, fact_inf_assm: dict[str, Any] | None = None,
) -> None:
    """落一筆 D3 ledger row（record_l2_call；消毒在 writer INSERT 前）。fail-soft。"""
    try:
        writer.record_l2_call(
            l2_reply_id=l2_reply_id, capability_id=capability_id, trigger=trigger,
            created_at=datetime.now(timezone.utc), model=model,
            contract_ver=contract_ver, schema_ver=schema_ver,
            system_prompt=system_prompt, input_context=context, raw_response=raw_response,
            parsed_output=parsed_output, guard_verdict=guard_verdict,
            fact_inf_assm=fact_inf_assm, cost_usd=cost_usd, latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 — D3 寫失敗不阻斷 cascade
        logger.warning("ml_advisory D3 ledger 記錄 skipped (fail-soft): %s", exc)


def _record_spend(spend_recorder: Any, capability_id: str, cost_usd: float) -> None:
    """累計 per-cap 花費（orchestrator.record_capability_spend；可選 + fail-soft）。"""
    if spend_recorder is None or cost_usd <= 0:
        return
    try:
        spend_recorder(capability_id, cost_usd)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ml_advisory per-cap spend 記帳 skipped (fail-soft): %s", exc)


__all__ = [
    "OllamaScreenCalibration",
    "load_ollama_screen_calibration",
    "MlAdvisoryCascadeResult",
    "run_ml_advisory_cascade",
    "write_ml_advisory_advisory_sink",
]
