"""
MODULE_NOTE
模塊用途：
  L2 Advisory Mesh 的 conductor（PA P2 設計 §A/§F/§H）。一個 async scheduler/dispatcher
  singleton，擁有迴圈：trigger → admission → capability dispatch → PromptContract →
  out-of-bound guard → D3 write → result routing（proposal 進既有被閘管線，非執行）。

  它是 conductor（root principle 15），**不是第六個 trading agent**。擁有 Layer2Engine
  作為「眾多 executor 之一」（cloud-L2 capabilities）；local-sentinel/Ollama-only capability
  永不碰 Layer2Engine。

主要類/函數：
  - L2AdvisoryOrchestrator：conductor singleton（module-level binding + getter）。
      * dispatch(trigger):公共入口（trigger → admission → ... → routing）。
      * status():唯讀狀態投影。
  - _AdmissionState：per-capability in-process 窗口（dedup/debounce）；orchestrator 內部
    state（非獨立 singleton，per PA §K 註記）。
  - FailSafeState / 狀態機：HEALTHY→RETRY→DEGRADE_OLLAMA→NO_ADVICE→TRIPPED→GLOBAL_CONSERVATIVE。
  - get_l2_advisory_orchestrator():取 singleton。

依賴（reuse ~70%，PA §J）：
  - l2_capability_registry（registry + LANE_DIRECTION + effective_autonomy）。
  - l2_prompt_contract_registry（contract_ver/schema_ver，寫每 D3 row）。
  - l2_out_of_bound_guard（確定性 guard，proposal 前跑）。
  - l2_conflict_adjudicator（fixed precedence，無 model 裁決）。
  - l2_call_ledger_writer（P1 D3 writer：record_l2_call / record_gate_seam）。
  - layer2_cost_tracker.check_daily_budget（admission stage 4，DOC-08 $2/day）。
  - layer2_engine.Layer2Engine（cloud-L2 executor，一個 executor）。

硬邊界（CC 逐條 grep）：
  - 無 order authority：本模塊 import 無 IntentProcessor / submit_intent / place_order / order IPC。
  - 無 lease authority（trading scope）：無 acquire_lease for trading。
  - 無 promote_tier / autonomy-raiser（C1）：本模塊不呼 promote_tier，不 import 任何 tier-raiser。
  - 無 live-config write：不碰 live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET /
    authorization.json / execution_authority / system_mode。
  - 無 model-adjudication（F.2）：裁決走 l2_conflict_adjudicator 的 fixed table，非 model。
  - fail-safe 鐵律：任何態都「減去」L2 能力，worst=NO_ADVICE=今日 baseline；零態通「阻塞
    baseline」或「auto-apply live」（§H）。
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from . import l2_capability_registry as _registry
from . import l2_conflict_adjudicator as _adjudicator
from . import l2_out_of_bound_guard as _guard
from . import l2_prompt_contract_registry as _contracts
from .l2_call_ledger_writer import get_l2_call_ledger_writer as _get_l2_ledger_writer
from .learning_tier_gate import LearningTier

logger = logging.getLogger("l2_advisory_orchestrator")


def _utc_day(ts: float) -> str:
    """epoch 秒 → UTC date 字串（YYYY-MM-DD）。per-cap 日花費的歸桶鍵，與 cost_tracker 對齊。"""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


# ── coarse_subject DoS 防護常數（E3 P3-flag：dedup_key 含 coarse_subject 無 evict → memory DoS）──
#
# 為什麼需要：dedup_key = capability_id|spec|coarse_subject。若 coarse_subject 高基數（攻擊者
# 餵不同 subject 繞 dedup），last_served_ts / debounce_pending 會無界增長（每個 distinct subject
# 一永久 key；P3 接 executor 即活、無 healthcheck 可察 → memory DoS）。兩道防護：
#   (1) server-derive 低基數 coarse_subject（_derive_coarse_subject）——把任意 input 正規化進
#       有界集合（已知 symbol/strategy token，否則落 "other" 桶），上游無法吹爆基數。
#   (2) TTL + maxsize eviction（_evict_admission_windows）——admission 窗口本就是「近窗口去重」，
#       過 TTL 的 key 永不再被讀（dedup 窗 = max(debounce,1)，遠短於 TTL），可安全清；maxsize
#       是硬上限兜底（即便低基數 derive 失效仍有界）。
_ADMISSION_KEY_TTL_SECS = 86_400.0  # dedup/debounce key 存活上限（24h；遠超任何 debounce 窗）
_ADMISSION_KEY_MAXSIZE = 4_096  # last_served_ts / debounce_pending 各自硬上限（兜底）
# 低基數 coarse_subject 字符上限（再長一律截斷 + 標記，防單一超長 subject 當 unique key）。
_COARSE_SUBJECT_MAXLEN = 48


# ═══════════════════════════════════════════════════════════════════════════════
# Fail-safe 狀態機（§H）—— 鐵律：每態「減去」L2 能力，worst=NO_ADVICE=今日 baseline
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼每態都是「subtraction」：L2 failure 永遠降級到確定性 baseline——never blocks，
# never unsafe。zero 態寫 live_execution_allowed / 呼 promote_tier / acquire trading lease。
# GLOBAL_CONSERVATIVE 只是 force「已存在的」Conservative posture（更保守，永不 live-enabling）。
class FailSafeState(str, Enum):
    HEALTHY = "HEALTHY"
    RETRY = "RETRY"
    DEGRADE_OLLAMA = "DEGRADE_OLLAMA"
    NO_ADVICE = "NO_ADVICE"  # worst common case = 等同今天無 L2 的行為
    TRIPPED = "TRIPPED"  # per-capability，cooling timer
    GLOBAL_CONSERVATIVE = "GLOBAL_CONSERVATIVE"  # force 既有 Conservative posture（更保守）


# admission 裁決結果（供 D3 gate-seam 記錄）。
@dataclass
class AdmissionDecision:
    admitted: bool
    reason: str  # admitted / trigger_deduped / debounced / coalesced / budget_exceeded / tier_locked / manual
    autonomy: str = ""  # effective_autonomy 結果（MANUAL/TIER_LOCKED/AUTO_VIA_GATE）
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class _AdmissionState:
    """per-capability in-process admission 窗口（dedup/debounce + per-cap 日花費）。

    為什麼 in-process（無持久化）：重啟乾淨 re-arm（design §L）。dedup_key → last_served_ts；
    debounce → pending burst latest ts。

    cap_daily_spend：per-capability per-UTC-day 累計花費（design §F.1 stage 4「per-capability
    hard daily ceiling」）。鍵為 (capability_id, utc_day)；值為當日該 cap 累計 USD。**獨立於**
    全域 DOC-08 $2/day（check_daily_budget 是全域 total，無 per-cap 拆分），故 per-cap 上限
    必須在 orchestrator 內自管：cap_daily 小、全域 remaining 大時，該 cap 仍能被擋。

    有界不變式（re-E2 MED-1）：此 dict 只保留「今日」key。寫入（record_capability_spend）
    時清除非今日 key——因為閘只讀「今日」累計（_cap_spend_today 用 ts 所屬 day_key），昨日
    及更早的桶永不再被讀，留著只會線性無界增長（每日每 cap 一永久 key；P3 接 executor 後
    即活、無 healthcheck 可察）。歸零靠「跨日後新 day_key 無紀錄」自然達成，舊桶不需保留。
    """

    last_served_ts: dict[str, float] = field(default_factory=dict)  # dedup_key → ts
    debounce_pending: dict[str, float] = field(default_factory=dict)  # dedup_key → first-seen ts
    # (capability_id, utc_day_iso) → 當日該 cap 累計花費 USD。
    cap_daily_spend: dict[tuple[str, str], float] = field(default_factory=dict)

    def _prune_stale_spend(self, today: str) -> None:
        """清除 cap_daily_spend 中非 today 的桶（re-E2 MED-1：防無界增長）。

        為什麼安全：閘 (_cap_spend_today) 只讀「ts 所屬 day_key」累計，跨日歸零靠新 day_key
        無紀錄達成——舊 day 的桶從不再被讀。每日每 cap 留一永久 key 是純線性洩漏。寫入時
        in-process O(n) sweep 即可（n=cap數×天數，低頻 mutator）。呼叫端須持鎖（mutator 內）。
        """
        stale = [k for k in self.cap_daily_spend if k[1] != today]
        for k in stale:
            del self.cap_daily_spend[k]

    def _evict_admission_windows(self, now: float) -> None:
        """TTL + maxsize 驅逐 last_served_ts / debounce_pending（E3 coarse_subject DoS 防護）。

        為什麼安全：admission 窗口是「近窗口去重」——dedup 只比 (now-last)<max(debounce,1)，
        debounce pending 只比 (now-first)<debounce_secs；兩者窗口都 ≪ TTL（24h）。過 TTL 的 key
        早已超出任何去重窗口、永不再被讀，清除不改任何去重判定（被清的 key 下次來等同新 key，
        本就該重新計窗）。maxsize 是硬上限兜底（即便低基數 derive 失效仍有界）：超限時驅逐最舊。
        呼叫端須持鎖（在 _admit 臨界區內呼叫）。
        """
        # (1) TTL：清掉 now-ts 超過 TTL 的 key（兩 dict 各自）。
        ttl_cut = now - _ADMISSION_KEY_TTL_SECS
        for d in (self.last_served_ts, self.debounce_pending):
            stale = [k for k, ts in d.items() if ts < ttl_cut]
            for k in stale:
                del d[k]
        # (2) maxsize 兜底：超硬上限 → 驅逐最舊（ts 小者）直到 ≤ maxsize。
        for d in (self.last_served_ts, self.debounce_pending):
            if len(d) > _ADMISSION_KEY_MAXSIZE:
                # 按 ts 升序，刪到剩 maxsize（驅逐最舊；最舊最不可能仍在去重窗口內）。
                for k, _ts in sorted(d.items(), key=lambda kv: kv[1])[: len(d) - _ADMISSION_KEY_MAXSIZE]:
                    del d[k]


def _derive_coarse_subject(raw: str) -> str:
    """把任意上游 coarse_subject 正規化成低基數桶（E3 DoS 防護第一道）。

    為什麼：dedup_key 含 coarse_subject；高基數會吹爆 admission 窗口。server-derive 把 input
    收進有界集合——上游無法用「每次不同 subject」當 unique key 繞 dedup + 撐爆記憶體。

    規則（保守、確定性、無 model）：
      - 空 → "default"（穩定桶）。
      - 截斷到 _COARSE_SUBJECT_MAXLEN（防單一超長字串當 unique key）；超長標 ":trunc"。
      - 只保留 [A-Za-z0-9_:.-]（去除可被用來造無限變體的字元如空白/控制字元），其餘折成 "_"。
      - upper-case 正規化（BTCusdt / btcusdt → 同桶；降低大小寫造的基數）。
    這不是「驗 subject 合法性」，而是「把基數壓進有界範圍」——真正的有界保證仍由 TTL+maxsize
    eviction 兜底（derive 是第一道、便宜、降基數；eviction 是硬上限）。
    """
    s = (raw or "").strip()
    if not s:
        return "default"
    truncated = len(s) > _COARSE_SUBJECT_MAXLEN
    s = s[:_COARSE_SUBJECT_MAXLEN]
    # 折疊非白名單字元（防空白/控制字元/emoji 等造無限變體）。
    cleaned = "".join(ch if (ch.isalnum() or ch in "_:.-") else "_" for ch in s).upper()
    return f"{cleaned}:trunc" if truncated else cleaned


@dataclass
class DispatchResult:
    """dispatch 的最終結果（供 route 投影；含 admission/guard/routing 概要）。"""

    capability_id: str
    admitted: bool
    admission_reason: str
    autonomy: str = ""
    fail_safe_state: str = FailSafeState.HEALTHY.value
    guard_verdict: str | None = None
    routed_to: str | None = None  # neutral_sink / risk_governor_advisory / manual_inbox / dropped
    l2_reply_id: str | None = None
    advisory_review_packet: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)


class L2AdvisoryOrchestrator:
    """L2 advisory 迴圈的 conductor singleton（無 order/lease/promote_tier 權）。

    為什麼是新 singleton（非擴 Layer2Engine）：Layer2Engine 是「單次深推理 session 的
    worker」；Orchestrator 是「跨 capability/trigger/budget/lane 的 conductor」。混在一起
    會把 scheduling/gating/fail-safe 推進 session worker，破壞 route-thin 紀律。Orchestrator
    「擁有」Layer2Engine 作為一個 executor。
    """

    def __init__(
        self,
        *,
        cost_tracker: Any = None,
        engine_provider: Any = None,
        registry_loader: Any = None,
        current_tier: LearningTier = LearningTier.L1,
        posture: str = "Conservative",
        max_retries: int = 1,
        tier_provider: Any = None,
    ) -> None:
        # cost_tracker / engine 注入供測試；預設 lazy 取既有 singleton（避免 import cycle）。
        self._cost_tracker = cost_tracker
        self._engine_provider = engine_provider
        self._registry_loader = registry_loader or _registry.load_capability_registry
        self._current_tier = current_tier
        self._posture = posture
        # P4 §6：injectable 唯讀 tier 投影 `() -> (LearningTier, {flag_name: bool})`。
        # fail-closed：None / raise / 非法回值 → (self._current_tier=L1, {})——行為與
        # 未接線 byte-identical（tier_flag_value 落 None，STEP-2 照鎖）。tier 只讀不寫
        # （C1 鐵則：本模塊 0 promote_tier）。
        self._tier_provider = tier_provider
        # 為何 retry 上限可注入但預設 1：fail-safe RETRY 態的有界重試；與交易 max_retries=0
        # 硬邊界「無關」（此為 advisory 模型呼叫重試，非交易重試）。
        self._max_retries = max_retries

        # 為什麼 RLock（非 Lock）：admission 的原子臨界區（dedup read-modify-write）會呼叫
        # 同樣取本鎖的 _cap_spend_today / record_capability_spend；non-reentrant Lock 會自鎖。
        # RLock 讓同執行緒重入安全，不影響跨執行緒互斥（MED-2 admission-window race 修）。
        self._lock = threading.RLock()
        self._admission = _AdmissionState()
        self._fail_safe = FailSafeState.HEALTHY
        self._consecutive_failures = 0
        self._registry_cache: _registry.L2CapabilityRegistry | None = None
        # last-good registry：reload 後若新 TOML 壞掉，read-path fail-soft 退回此份（非空），
        # 比退到空 registry 保留更多運維資訊（cold-cache 無 last-good 時才退空）。
        self._registry_last_good: _registry.L2CapabilityRegistry | None = None
        # registry 載入是否降級（malformed TOML 等）：read-path fail-soft 用，供 status() 投影。
        self._registry_degraded = False
        self._registry_degraded_reason = ""

    # ── registry 取用（lazy + cache）────────────────────────────────

    def _registry_obj(self) -> _registry.L2CapabilityRegistry:
        """取 registry（lazy + cache）。read-path fail-soft：載入失敗回 last-good 或空 registry。

        為什麼 fail-soft（E2-LOW-1 修）：本函數被唯讀 GET route（status/orchestrator）呼叫；
        cold-cache 遇 malformed TOML 時，原本 loader raise L2RegistryLoadError 會冒泡成
        GET /orchestrator/status 的 500。read-path 不該因壞 config 而 500——改 fail-soft 到
        last-good cache（若有）或空 registry，並標記 _registry_degraded 供 status() 暴露。

        降級語義（re-E2 LOW-1：兩種退路不同，勿混為「降級必空」）：
          - cold-cache 無 last-good → 退**空 registry**：真 fail-closed，enabled_capabilities
            為空，不放行任何 advisory（無 capability=無 advisory=今日 baseline）。
          - warm（曾成功載入過）→ 退**last-good 已驗證 config**：保留先前那份「通過全 loader
            reject」的已驗證 enabled capabilities，dispatch 仍可 admit 它們。這是合理的——
            last-good 是 advisory subtraction-only 的保守降級（壞的新 TOML 不切換、不引入新
            cap），**不是**放行未驗證的壞 config 新 cap。
        write-path（reload route）另行明確 reject，不走此 fail-soft。
        """
        if self._registry_cache is None:
            try:
                self._registry_cache = self._registry_loader()
                self._registry_last_good = self._registry_cache  # 成功載入 → 更新 last-good
                self._registry_degraded = False
                self._registry_degraded_reason = ""
            except _registry.L2RegistryLoadError as exc:
                # 壞 config：退 last-good（若有）否則空 registry（fail-closed）+ 標記降級。
                # 不冒泡（避免 GET /orchestrator/status 500）。
                fallback = self._registry_last_good or _registry.L2CapabilityRegistry()
                logger.warning(
                    "registry 載入失敗，read-path fail-soft 退 %s（degraded）：%s",
                    "last-good" if self._registry_last_good else "空 registry",
                    exc,
                )
                self._registry_cache = fallback
                self._registry_degraded = True
                self._registry_degraded_reason = "registry_load_rejected"
        return self._registry_cache

    def reload_registry(self) -> None:
        """強制重載 registry（operator 改 TOML 後）。"""
        with self._lock:
            self._registry_cache = None

    # ── 公共入口 ────────────────────────────────────────────────

    def dispatch(
        self,
        *,
        capability_id: str,
        trigger: str = "manual",
        coarse_subject: str = "",
        now: float | None = None,
    ) -> DispatchResult:
        """conductor 入口：trigger → admission → (executor) → guard → D3 → routing。

        P2 範圍：完整接通 admission + 取 contract version + fail-safe 狀態投影 + D3 gate-seam
        記錄 + routing 決策（依 lane direction）。實際 cloud-L2 executor 呼叫沿用既有
        layer2_engine 路徑（manual capability 零回歸）；P3 capability 才接各自 executor。

        回 DispatchResult（供 route 薄投影）。永不執行任何交易效果。
        """
        ts = now if now is not None else time.time()
        reg = self._registry_obj()
        cap = reg.get(capability_id)

        result = DispatchResult(
            capability_id=capability_id,
            admitted=False,
            admission_reason="unknown_capability",
            fail_safe_state=self._fail_safe.value,
        )

        # capability 不在 registry（P2 skeleton 預期：只有 P3 才填）→ 不可達，fail-closed。
        if cap is None:
            result.notes.append("capability 不在 registry（P2 skeleton 無 capability stanza）")
            self._record_admission_seam(capability_id, AdmissionDecision(False, "unknown_capability"))
            return result

        if not cap.enabled:
            result.admission_reason = "capability_disabled"
            result.notes.append("capability enabled=false（fail-closed 預設）")
            self._record_admission_seam(capability_id, AdmissionDecision(False, "capability_disabled"))
            return result

        # ── §F.1 ADMISSION（確定性，model 呼叫之前）──
        decision = self._admit(cap, coarse_subject=coarse_subject, ts=ts)
        result.admitted = decision.admitted
        result.admission_reason = decision.reason
        result.autonomy = decision.autonomy
        self._record_admission_seam(capability_id, decision)
        if not decision.admitted:
            # MANUAL → routed_to manual_inbox（非執行）；其餘 suppressed。
            result.routed_to = "manual_inbox" if decision.autonomy == "MANUAL" else "dropped"
            return result

        # ── fail-safe 閘：NO_ADVICE / TRIPPED / GLOBAL_CONSERVATIVE → 不發 advice（baseline）──
        if self._fail_safe in (
            FailSafeState.NO_ADVICE,
            FailSafeState.TRIPPED,
            FailSafeState.GLOBAL_CONSERVATIVE,
        ):
            result.routed_to = "dropped"
            result.notes.append(f"fail-safe={self._fail_safe.value}：減去 L2 能力，走確定性 baseline")
            return result

        # ── contract version（寫每 D3 row；來自 registry 非硬編、非 model）──
        contract_ver, schema_ver = _contracts.resolve_contract_versions(
            capability_id=capability_id,
            contract_ref=cap.prompt_contract_ref or None,
            schema_ref=cap.output_schema_ref or None,
        )
        result.notes.append(f"contract_ver={contract_ver} schema_ver={schema_ver}")

        # sync dispatch() 只做 admission + routing 「決策」（P2 + P3a 共用，無 await）；真正的
        # async executor 呼叫在 dispatch_and_execute()（P3a 活化此路徑——對 ml_advisory capability
        # 接 run_ml_advisory_cascade）。sync 路徑保持不變故 P2 測試零回歸。
        # routing 依 lane direction（§C/§A.2）：
        direction = _registry.LANE_DIRECTION.get(cap.lane, "neutral")
        if direction == "neutral":
            result.routed_to = "neutral_sink"  # research/hypothesis/replay/告警 sink
        elif direction == "contract":
            result.routed_to = "risk_governor_advisory"  # advisory INPUT only；governor 擁有終值
        else:  # expand — 已被 admission 的 MANUAL 攔下，理論不可達；防禦性 fail-closed
            result.routed_to = "manual_inbox"
            result.notes.append("expand lane 不應到此（admission MANUAL 應已攔）——fail-closed")

        return result

    # ── P3a：async executor 接線（活化 dormant dispatch 路徑）──

    async def dispatch_and_execute(
        self,
        *,
        capability_id: str,
        mode: str,
        context: dict[str, Any],
        trigger: str = "ml:training_complete",
        coarse_subject: str = "",
        engine: Any = None,
        engine_mode: str = "demo",
        symbol: str | None = None,
        strategy_name: str | None = None,
        available_signal_axes: list[str] | None = None,
        bull_only: bool = False,
        now: float | None = None,
    ) -> DispatchResult:
        """conductor 完整入口（admission + executor）：先跑 sync dispatch() 取 admission/routing
        決策，再對 ml_advisory neutral capability 接 run_ml_advisory_cascade（P3a 活化）。

        為什麼分兩段（sync dispatch + async executor）：admission（dedup/debounce/budget/tier）
        是同步、無 await、持 RLock 的確定性決策（P2 已驗）；真正花 cloud 的 executor 是 async。
        分離讓 sync 路徑（P2 測試）零回歸，async executor 疊加在「已 admit + neutral」之上。

        鐵律：executor 只在 admitted + routed_to=neutral_sink + capability=ml_advisory 時跑；
        其餘（disabled / deduped / budget / tier / MANUAL / fail-safe drop）皆短路不呼 model。
        executor direction=neutral、0 新執行權；report_call_outcome 推進 fail-safe SM。
        """
        result = self.dispatch(
            capability_id=capability_id, trigger=trigger,
            coarse_subject=coarse_subject, now=now,
        )
        # 只有「admitted + neutral_sink + ml_advisory capability」才接 executor。
        if not (
            result.admitted
            and result.routed_to == "neutral_sink"
            and capability_id.startswith("ml_advisory")
        ):
            return result

        # lazy import 避免 boot-time / import cycle（executor import 本模塊的 writer）。
        from . import l2_ml_advisory_executor as _exec  # noqa: PLC0415

        eng = engine if engine is not None else self._resolve_engine()
        if eng is None:
            # engine 不可用 → fail-soft（advisory 失敗只「減去」L2 能力，不阻塞 baseline）。
            result.notes.append("executor: engine 不可用，cascade skipped（fail-soft）")
            self.report_call_outcome(ok=False, ollama_available=False)
            return result

        # contract version（寫每 D3 row）：必須用「此 capability 真實送 cloud 的 per-mode 契約 ref」
        # 解析，否則 D3 ledger 記的 contract_ver/schema_ver 與實際用的契約分歧（記錯 provenance，
        # 違 root principle 8 可重建）。dispatch() 已用 cap.prompt_contract_ref/output_schema_ref 正確
        # 解析（:354-359）但結果只進 notes 後丟棄；此處對「同一 cap」重取 ref 再解析，與 dispatch()
        # 的解析路徑等價（同 registry、同 ref → 同版本），不可傳 None（會落 generic fallback
        # l2_contract.v1/l2_schema.v1=錯值）。cap 必非 None：能到此處代表 dispatch() 已 admit 它
        # （capability 存在且 enabled），re-fetch fail-soft 退 None 時才回 generic fallback。
        cap = self._registry_obj().get(capability_id)
        contract_ver, schema_ver = _contracts.resolve_contract_versions(
            capability_id=capability_id,
            contract_ref=(cap.prompt_contract_ref or None) if cap is not None else None,
            schema_ref=(cap.output_schema_ref or None) if cap is not None else None,
        )
        try:
            casc = await _exec.run_ml_advisory_cascade(
                capability_id=capability_id, mode=mode, context=context, engine=eng,
                contract_ver=contract_ver, schema_ver=schema_ver, trigger=trigger,
                engine_mode=engine_mode, symbol=symbol, strategy_name=strategy_name,
                available_signal_axes=available_signal_axes, bull_only=bull_only,
                spend_recorder=self.record_capability_spend,
            )
        except Exception as exc:  # noqa: BLE001 — executor 必 fail-soft，不拋進 dispatch
            logger.warning("ml_advisory cascade fail-soft（dispatch 不中斷）: %s", exc)
            result.notes.append("executor: cascade 例外，fail-soft")
            self.report_call_outcome(ok=False, ollama_available=True)
            return result

        # cascade 結果投影進 DispatchResult（供 route 薄投影）。
        result.guard_verdict = casc.guard_verdict
        result.l2_reply_id = casc.l2_reply_id
        result.advisory_review_packet = casc.advisory_review_packet
        result.notes.append(f"executor: stage={casc.stage} sink_written={casc.sink_written}")
        if casc.screen_disabled:
            result.notes.append("executor: M4 ollama_screen DISABLED（flag MIT）")
        # fail-safe SM：cascade ok（sink written or honest短路）= healthy；cloud 不可用 = 失敗。
        # 為什麼 screen_rejected / guard_rejected 算 ok：它們是「確定性閘正確擋下」，非執行器故障；
        # 只有 cloud_unavailable / sink_write_failed 才是真故障（推進 fail-safe 降級）。
        executor_ok = casc.stage in (
            "sink_written", "screen_rejected", "guard_rejected", "unknown_mode_rejected",
        )
        self.report_call_outcome(ok=executor_ok, ollama_available=True)
        return result

    def set_tier_provider_if_absent(self, provider: Any) -> None:
        """注入唯讀 tier 投影（僅當尚未注入；冪等，不覆蓋測試注入的 provider）。

        為什麼 set-if-absent：singleton 經 layer2_routes._get_orchestrator 每請求取用，
        無條件覆蓋會把測試/未來顯式注入的 provider 踩掉；首見注入一次即定。
        """
        with self._lock:
            if self._tier_provider is None and provider is not None:
                self._tier_provider = provider

    def _resolve_tier(self) -> tuple[LearningTier, dict[str, bool]]:
        """解析 (current_tier, capability flags)（唯讀投影；fail-closed 默認 L1）。

        provider None / raise / 回值非法 → (self._current_tier, {})：與未接線行為
        byte-identical（P4 §6 誠實語義——in-memory tier 重啟歸 L1 是系統真值，本函數
        不為任何 capability 造假 tier）。
        """
        provider = self._tier_provider
        if provider is None:
            return self._current_tier, {}
        try:
            tier, flags = provider()
            if not isinstance(tier, LearningTier):
                return self._current_tier, {}
            safe_flags = {
                str(k): bool(v) for k, v in dict(flags or {}).items()
            }
            return tier, safe_flags
        except Exception as exc:  # noqa: BLE001 — 投影故障 → fail-closed L1（不放行）
            logger.warning("tier_provider 解析失敗（fail-closed → L1）：%s", exc)
            return self._current_tier, {}

    def _resolve_engine(self) -> Any:
        """lazy 取 Layer2Engine（cloud-L2 + Ollama executor）。fail-soft：取不到回 None。"""
        if self._engine_provider is not None:
            try:
                return self._engine_provider()
            except Exception as exc:  # noqa: BLE001 — 注入式 provider 失敗 → None
                logger.warning("executor engine_provider 失敗（fail-soft）: %s", exc)
                return None
        try:
            from .layer2_routes import _get_engine  # noqa: PLC0415 — 避免 import cycle

            return _get_engine()
        except Exception as exc:  # noqa: BLE001 — 取不到 engine → None（cascade skipped）
            logger.warning("executor 取 Layer2Engine 失敗（fail-soft）: %s", exc)
            return None

    # ── §F.1 ADMISSION stage（dedup→debounce→coalesce→budget→tier/posture）──

    def _admit(
        self, cap: _registry.L2Capability, *, coarse_subject: str, ts: float
    ) -> AdmissionDecision:
        """確定性 admission：順序 dedup→debounce→coalesce→budget→tier/posture（design §F.1）。

        鐵律：trigger storm 即便 debounce OFF 也不能吹破 DOC-08 $2/day——因 budget（stage 4）
        是 dedup/debounce/coalesce 下游的「硬」閘，且 per-capability 日上限降級 NO_ADVICE。
        """
        trig = cap.trigger
        debounce_secs = trig.debounce_secs if trig else 0
        dedup_template = trig.dedup_key if trig else "capability_id+spec+coarse_subject"
        spec = trig.spec if trig else ""
        # E3 DoS 防護第一道：server-derive 低基數 coarse_subject（上游無法吹爆基數）。
        coarse = _derive_coarse_subject(coarse_subject)
        # dedup identity：capability_id + spec + derived coarse_subject（design §F.1）。
        dedup_key = f"{cap.capability_id}|{spec}|{coarse}"

        # 為什麼整段 admission 納 self._lock（MED-2 修）：dedup/debounce 的 read-modify-write
        # 若無鎖，P3 多執行緒同 dedup_key 兩 trigger 都讀 None → 都 admit → dedup 失效、storm
        # 漏出。把 Stage 1 讀、Stage 2 debounce 讀寫、Stage 4 per-cap 讀、admitted 後的 mark
        # 收進「同一」臨界區，使「檢查→放行→標記」原子化。_admit 為同步函數、無 await（asyncio
        # 邊界不在此），故 threading lock 跨 sync 呼叫（_check_budget / effective_autonomy）安全；
        # 鎖為 RLock，_cap_spend_today 重入取鎖不自鎖。
        with self._lock:
            # E3 DoS 防護第二道：TTL+maxsize 驅逐過期 admission 窗口 key（在臨界區內，持鎖）。
            # 過 TTL 的 key 早已超出去重窗口、永不再被讀，清除不改任何去重判定。
            self._admission._evict_admission_windows(ts)

            # ── Stage 1 — DEDUP：in-flight/近期已服務的 key 在窗口內 → drop（無 model 呼叫）──
            last = self._admission.last_served_ts.get(dedup_key)
            if last is not None and (ts - last) < max(debounce_secs, 1):
                return AdmissionDecision(
                    False, "trigger_deduped",
                    details={"dedup_key": dedup_key, "since_last_s": round(ts - last, 3)},
                )

            # ── Stage 2 — DEBOUNCE：trailing-edge，等 burst 沉澱後 fire 一次 ──
            if debounce_secs > 0:
                first_seen = self._admission.debounce_pending.get(dedup_key)
                if first_seen is None:
                    # burst 起點：登記 pending，本次先不 fire（等沉澱）。
                    self._admission.debounce_pending[dedup_key] = ts
                    return AdmissionDecision(
                        False, "debounced",
                        details={"dedup_key": dedup_key, "settle_secs": debounce_secs},
                    )
                if (ts - first_seen) < debounce_secs:
                    # 仍在沉澱窗口內 → drop（flapping 3×/min → 一次 advisory）。
                    return AdmissionDecision(
                        False, "debounced",
                        details={"dedup_key": dedup_key, "elapsed_s": round(ts - first_seen, 3)},
                    )
                # 沉澱完成 → 清 pending，續走（fire once on latest）。
                self._admission.debounce_pending.pop(dedup_key, None)

            # ── Stage 3 — COALESCE：P2 dedup_key 已天然合併同 subject；批次列表是 P3 list-input ──
            # （P2 skeleton：coalesce 退化為 dedup 的延伸；多 trigger 同 key 已被 stage1/2 合一。）

            # ── Stage 4 — BUDGET：check_daily_budget（DOC-08 硬閘）+ per-capability 日上限 ──
            # 為什麼是硬閘：storm-control 鐵律——即便上游 debounce 失效，預算閘擋住超支。
            allowed, remaining = self._check_budget()
            if not allowed:
                return AdmissionDecision(
                    False, "budget_exceeded",
                    details={"remaining_usd": remaining},
                )
            cap_daily = cap.budget.daily_usd_cap if cap.budget else 0.0
            if cap_daily > 0:
                # per-capability 硬日上限：對「該 cap 當日累計花費」比 cap_daily（design §F.1 stage 4）。
                # 為什麼用 per-cap accumulator 而非全域 remaining：全域 check_daily_budget 是所有
                # capability 的 total（layer2_cost_tracker.py:286），不帶 per-cap 拆分；若沿用全域
                # remaining 比 cap_daily，等於宣稱了不存在的 per-cap 保證（cap_daily 小、全域寬時不擋）。
                # 真 per-cap 計帳獨立於全域：cap_daily=$0.50 而全域 remaining=$2.00 時，該 cap 花滿
                # $0.50 仍被擋。spend 由 P3 executor 經 record_capability_spend 累計（P2 dispatch
                # dormant 故累計值為 0，閘現不觸發，P3 接線即活）。
                spent = self._cap_spend_today(cap.capability_id, ts)
                if spent >= cap_daily:
                    # per-capability 硬日上限命中 → drop（design §F.1 stage 4 per-cap ceiling）。
                    return AdmissionDecision(
                        False, "budget_exceeded",
                        details={
                            "reason": "per_capability_daily_ceiling",
                            "cap_daily_usd": cap_daily,
                            "cap_spent_usd": round(spent, 4),
                        },
                    )

            # ── Stage 5 — TIER/POSTURE：effective_autonomy（§C.2）──
            # P4 §6：tier/flag 由 injectable 唯讀投影解析（默認 None → L1+{} → 與舊行為
            # byte-identical）。唯讀；promote/晉升不在此（C1）。
            eff_tier, tier_flags = self._resolve_tier()
            flag_name = cap.tier_capability_flag or ""
            tier_flag_value = tier_flags.get(flag_name) if flag_name else None
            autonomy = _registry.effective_autonomy(
                cap,
                current_tier=eff_tier,
                posture=self._posture,
                tier_flag_value=tier_flag_value,
            )
            if autonomy == "TIER_LOCKED":
                return AdmissionDecision(False, "tier_locked", autonomy=autonomy)
            if autonomy == "MANUAL":
                # MANUAL → route 人工 inbox，無 auto-call（promotion-class / expand lane）。
                return AdmissionDecision(False, "manual", autonomy=autonomy)

            # admitted：標記 dedup 已服務（後續同 key 在窗口內被 dedup）。
            self._admission.last_served_ts[dedup_key] = ts
        return AdmissionDecision(True, "admitted", autonomy=autonomy)

    # ── per-capability 日花費計帳（design §F.1 stage 4；獨立於全域 DOC-08）──

    def _cap_spend_today(self, capability_id: str, ts: float) -> float:
        """回該 capability 在 ts 所屬 UTC-day 的累計花費 USD（無紀錄 → 0.0）。

        為什麼按 UTC-day：與 layer2_cost_tracker 的 daily_spend date_key（UTC date）對齊；
        跨日自然歸零（新 day_key 無紀錄）。lock 內讀寫保 P3 多執行緒一致。
        """
        day = _utc_day(ts)
        with self._lock:
            return self._admission.cap_daily_spend.get((capability_id, day), 0.0)

    def record_capability_spend(
        self, capability_id: str, usd: float, *, now: float | None = None
    ) -> None:
        """累加一筆 per-capability 花費（P3 executor 在 model 呼叫後呼此計帳）。

        為什麼是分離的 mutator（非在 admission 內加）：admission 在 model 呼叫「之前」跑，
        實際花費要等呼叫完成才知。P2 dispatch dormant（無 executor 呼叫）故無 caller，
        accumulator 恆為空、per-cap 閘不觸發；P3 接 executor 即活。usd<=0 視為 no-op。
        """
        if usd <= 0:
            return
        day = _utc_day(now if now is not None else time.time())
        with self._lock:
            # 先 prune 非今日桶（re-E2 MED-1：有界不變式），再累加今日——保 dict 只含今日 key。
            self._admission._prune_stale_spend(day)
            key = (capability_id, day)
            self._admission.cap_daily_spend[key] = (
                self._admission.cap_daily_spend.get(key, 0.0) + usd
            )

    def _check_budget(self) -> tuple[bool, float]:
        """admission stage 4 預算閘（reuse check_daily_budget；lazy 取 cost_tracker）。"""
        tracker = self._cost_tracker
        if tracker is None:
            try:
                from .layer2_routes import _get_cost_tracker  # noqa: PLC0415 — 避免 import cycle

                tracker = _get_cost_tracker()
                self._cost_tracker = tracker
            except Exception as exc:  # noqa: BLE001 — 取不到 tracker → fail-closed（不放行）
                logger.warning("admission budget gate 取 cost_tracker 失敗（fail-closed）：%s", exc)
                return False, 0.0
        try:
            return tracker.check_daily_budget()
        except Exception as exc:  # noqa: BLE001 — 預算查詢失敗 → fail-closed
            logger.warning("check_daily_budget 失敗（fail-closed）：%s", exc)
            return False, 0.0

    # ── D3 gate-seam 記錄（admission 決策落 learning.l2_gate_seam_log）──

    def _record_admission_seam(self, capability_id: str, decision: AdmissionDecision) -> None:
        """admission 決策（含 suppressed）落 gate-seam log，附 trigger_decision reason。

        為什麼記 suppressed：§O metric 讀它——triggers 很多但多被 dedup 的 capability 是
        demote candidate。fail-soft：D3 寫失敗不阻斷 dispatch。
        """
        try:
            verdict = "pass" if decision.admitted else "reject"
            writer = _get_l2_ledger_writer()
            # admission 階段尚未鑄 l2_reply_id（無模型呼叫）；用 admission-scoped synthetic id。
            seam_reply_id = f"l2adm:{uuid.uuid4().hex[:12]}"
            writer.record_gate_seam(
                l2_reply_id=seam_reply_id,
                gate_id="admission",
                verdict=verdict,
                applier="L2AdvisoryOrchestrator",
                applied_as=decision.reason,
                details={
                    "capability_id": capability_id,
                    "trigger_decision": decision.reason,
                    "autonomy": decision.autonomy,
                    **decision.details,
                },
            )
        except Exception as exc:  # noqa: BLE001 — gate-seam 記錄 fail-soft
            logger.warning("admission gate-seam 記錄 skipped (fail-soft): %s", exc)

    # ── fail-safe 狀態轉移（§H）──

    def report_call_outcome(self, *, ok: bool, ollama_available: bool = True) -> FailSafeState:
        """回報一次 executor 呼叫結果，推進 fail-safe SM。回新狀態。

        鐵律：任何態都「減去」L2 能力（never blocks baseline / never auto-live）。本函數
        **不**寫任何 live-enabling state；GLOBAL_CONSERVATIVE 僅標記（實際 posture 切換由
        既有 governance_autonomy_service 的 operator/TOTP 路徑或既有 fail-safe，非此處 auto-live）。
        """
        with self._lock:
            if ok:
                self._consecutive_failures = 0
                self._fail_safe = FailSafeState.HEALTHY
                return self._fail_safe

            self._consecutive_failures += 1
            # 為什麼 escalation 與 ollama_available 解耦（MED-1 修）：升級必須由「連續失敗計數」
            # 跨閾值驅動，不能卡在 DEGRADE_OLLAMA。舊碼 `elif ollama_available: DEGRADE_OLLAMA`
            # 在計數閾值「之前」，ollama-up 持續失敗永停 DEGRADE_OLLAMA、到不了 TRIPPED/
            # GLOBAL_CONSERVATIVE（違 design §H 的 systemic escalation）。改為：先以計數定升級階，
            # ollama_available 只在「未到 TRIPPED」的中間階選 floor（DEGRADE_OLLAMA vs NO_ADVICE）。
            # 仍是 subtraction-only：每階都只「減去」L2 能力，無 live-enabling write（CC iron rule）。
            if self._consecutive_failures <= self._max_retries:
                self._fail_safe = FailSafeState.RETRY
            elif self._consecutive_failures < 5:
                # 中間階：ollama 可用 → DEGRADE_OLLAMA（退到本地 ollama）；否則 NO_ADVICE（今日 baseline）。
                self._fail_safe = (
                    FailSafeState.DEGRADE_OLLAMA if ollama_available else FailSafeState.NO_ADVICE
                )
            elif self._consecutive_failures < 10:
                # systemic：跨 5 連敗 → TRIPPED（per-capability cooling），即便 ollama 仍 up。
                self._fail_safe = FailSafeState.TRIPPED
            else:
                # 跨 10 連敗 → GLOBAL_CONSERVATIVE（force 既有 Conservative posture，永不 live-enabling）。
                self._fail_safe = FailSafeState.GLOBAL_CONSERVATIVE
            return self._fail_safe

    def reset_fail_safe(self) -> None:
        """N consecutive ok 後回 HEALTHY（亦供 operator 手動清）。"""
        with self._lock:
            self._consecutive_failures = 0
            self._fail_safe = FailSafeState.HEALTHY

    # ── 唯讀狀態投影（route 用；不可 mutate）──

    def status(self) -> dict[str, Any]:
        # _registry_obj() fail-soft：壞 config 不 raise（避免 GET 500），改設 _registry_degraded。
        reg = self._registry_obj()
        return {
            "fail_safe_state": self._fail_safe.value,
            "consecutive_failures": self._consecutive_failures,
            "current_tier": self._current_tier.name,
            # P4 §6 觀測欄：投影是否接線 + 解析後的有效 tier（fail-closed 退 L1 可見）。
            "tier_provider_wired": self._tier_provider is not None,
            "effective_tier": self._resolve_tier()[0].name,
            "posture": self._posture,
            "registered_capabilities": sorted(reg.capabilities.keys()),
            "enabled_capabilities": [c.capability_id for c in reg.enabled_capabilities()],
            "lane_directions": dict(_registry.LANE_DIRECTION),
            # registry 降級旗標（E2-LOW-1）：malformed TOML 時 read-path 退 last-good/空，true 提示
            # operator config 壞了（但 status 仍 200，fail-closed：enabled_capabilities 不誤放行）。
            "registry_degraded": self._registry_degraded,
            "registry_degraded_reason": self._registry_degraded_reason,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }


# ── process-global singleton（module-level binding；singleton-registry §2.6.2 已登記）──
_ORCHESTRATOR: L2AdvisoryOrchestrator | None = None


def get_l2_advisory_orchestrator() -> L2AdvisoryOrchestrator:
    """取 L2AdvisoryOrchestrator singleton（首次 lazy 構造）。"""
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = L2AdvisoryOrchestrator()
    return _ORCHESTRATOR


def _reset_l2_advisory_orchestrator_for_tests() -> None:
    """僅供測試：清空 singleton。"""
    global _ORCHESTRATOR
    _ORCHESTRATOR = None


__all__ = [
    "FailSafeState",
    "AdmissionDecision",
    "DispatchResult",
    "L2AdvisoryOrchestrator",
    "get_l2_advisory_orchestrator",
    "_reset_l2_advisory_orchestrator_for_tests",
]
