"""
MODULE_NOTE
模塊用途：
  L2 Advisory Mesh capability registry（TOML-only SSOT，PA P2 設計 §B/§C/§L）。把
  settings/l2_capability_registry.toml 載入成 typed model，並擁有「no-auto-path-to-live」
  linchpin 不變式：LANE_DIRECTION 型別表 + effective_autonomy 函數的 STEP-1。

  registry = TOML SSOT（operator 拍板：無 DB 表、無 V137）。capability 是 operator
  enable/tune 的原子單位。全 capabilities 預設 enabled=false（fail-closed）。

主要類/函數：
  - LANE_DIRECTION：loader-owned module-level 常數——lane→direction 的「唯一」定義處。
      無 "live" key（live 不可從任何 auto 路徑到達）。CC grep 此表 + STEP-1 即驗 linchpin。
  - effective_autonomy(cap, *, current_tier, posture, tier_flag_value)：派生 autonomy。
      STEP-1（函數頂、非-overridable）：if LANE_DIRECTION[lane]=="expand": return MANUAL。
      tier/posture 任何邏輯都在 STEP-1 之後，永不能解鎖 expand→MANUAL。
  - L2Capability：typed model（Pydantic extra="forbid"；enabled 預設 false）。
  - load_capability_registry(path=None)：loader，含三 reject 分支
      （autonomy_level 宣告 / can_auto_deploy_to_paper-as-posture / lane∉LANE_DIRECTION）。

依賴：
  - tomllib（stdlib）；pydantic（ConfigDict extra="forbid"，mirror agent_contracts.py）。
  - learning_tier_gate.LearningTier（min_tier 解析，reuse 不 fork）。
  - 路徑解析 reuse paper_trading_routes 範式（OPENCLAW_BASE_DIR env + parents[5] fallback；
    禁硬編 /home/ncyu /Users/ncyu，跨平台）。

硬邊界：
  - LANE_DIRECTION 無 "live" key；STEP-1 expand→MANUAL 不可被 tier/posture 覆寫（CC 5/10 linchpin）。
  - loader 拒宣告 autonomy_level（autonomy 是 DERIVED 非宣告）的 config（C2-adjacent）。
  - loader 拒把 can_auto_deploy_to_paper 當 posture gate 的 config（它 True@all-tiers 無 signal，C2）。
  - effective_autonomy STEP-3 永不 read can_auto_deploy_to_paper（True@all-tiers → 無 signal）。
  - 純 registry/policy：本模塊無 order surface / 無 lease-acquire / 無 promote_tier。
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .learning_tier_gate import LearningTier

logger = logging.getLogger("l2_capability_registry")


# ═══════════════════════════════════════════════════════════════════════════════
# ★ LANE_DIRECTION — no-auto-path-to-live linchpin（CC stress-test 5/10）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼是「單一 loader-owned 常數」而非 strictness lattice 的 emergent property：
# CC 只要讀「此表 + effective_autonomy 的 STEP-1」兩個 construct 就能驗「mostly-automatic
# 在 root principle 5 下安全」，不必推理整個格。最危險的 v1 旋鈕（autonomy_level 欄）
# 被刪除——autonomy 永遠 DERIVE 自 (lane + min_tier + posture)，永不宣告。
#
# direction 語義（grounded against governance_autonomy_service._AUTONOMY_PATH_MATRIX
# 的 tighten/loosen 不對稱）：
#   - neutral  ：研究/假說/replay/告警 sink；非 remediation，無交易效果。
#   - contract ：survival-first 收緊（auto，但被 deterministic governor 夾住，只能更緊）。
#   - expand   ：promotion-class 放鬆/晉升 → STEP-1 強制 MANUAL（永不 auto）。
#
# 任何未來的 "risk_loosen" / "*_promote" / live → 必 map 成 "expand" → forced human。
# **此表無 "live" key。live 不可從任何 auto 路徑到達。**
LANE_DIRECTION: dict[str, str] = {
    "research": "neutral",
    "hypothesis": "neutral",
    "ml_backlog": "neutral",
    "replay_0r": "neutral",
    "ops_alert": "neutral",  # alert != remediation（告警非補救動作）
    "risk_tighten": "contract",  # survival-first；auto（被 deterministic governor 夾住）
    "demo_stage1": "expand",  # promotion-class → Conservative 下 MANUAL（§C.3 forward-OOS bar）
    "none": "neutral",
}

# autonomy 派生結果型別（供 effective_autonomy 回傳；CC grep 此 Literal 確認無第四態）。
EffectiveAutonomy = Literal["MANUAL", "TIER_LOCKED", "AUTO_VIA_GATE"]

# 合法 model_tier 值（loader 不額外驗 enum，由 typed model Literal 強制）。
ModelTier = Literal["local_sentinel", "ollama", "cloud_l2"]


def is_promotion_class(lane: str) -> bool:
    """lane 是否屬 promotion-class（Conservative posture 下加摩擦 → MANUAL）。

    為什麼用 direction=="expand"：promotion-class 的「唯一」判準是 LANE_DIRECTION 表
    （single source），不另立第二份 lane 清單（避免兩處 drift）。
    """
    return LANE_DIRECTION.get(lane) == "expand"


# ═══════════════════════════════════════════════════════════════════════════════
# effective_autonomy — STEP-1 是 linchpin
# ═══════════════════════════════════════════════════════════════════════════════


def effective_autonomy(
    cap: "L2Capability",
    *,
    current_tier: LearningTier,
    posture: str,
    tier_flag_value: bool | None = None,
) -> EffectiveAutonomy:
    """派生 capability 的 effective autonomy。STEP-1 是 no-auto-path-to-live linchpin。

    為什麼 STEP-1 在函數頂且 non-overridable：expand lane = promotion/loosen class，
    在 root principle 5（survival>profit）下「永不 auto」。把這條設計成「函數頂第一個
    if，引用 LANE_DIRECTION 單一常數」，CC 讀兩個 construct 即可驗；不是 strictness
    lattice 的 emergent property。STEP-2/3 的 tier/posture 邏輯都在其後，結構上不可能
    解鎖 expand→MANUAL。

    回傳 ∈ {MANUAL, TIER_LOCKED, AUTO_VIA_GATE}。AUTO_VIA_GATE = 「有資格經 deterministic
    gate 嘗試」，**非**「現在就 apply」（proposal 仍進既有被閘管線，非執行）。
    """
    # ── STEP 1 — DIRECTION GATE（typed, loader-owned, NON-OVERRIDABLE — CC linchpin）──
    # expand → MANUAL：永不 auto。full stop。無 tier/posture 能解鎖此分支。
    if LANE_DIRECTION[cap.lane] == "expand":
        return "MANUAL"

    # ── STEP 2 — TIER GATE：tier 不足或綁定 flag 為 False → refuse（不降級跑）──
    if current_tier < cap.min_tier_enum or (
        cap.tier_capability_flag and not tier_flag_value
    ):
        return "TIER_LOCKED"

    # ── STEP 3 — POSTURE MODULATION（只能「加摩擦」，永不「移除 gate」）──
    # 為什麼 STEP-3 永不 read can_auto_deploy_to_paper：它 True@all-tiers（learning_tier_gate
    # :185/196/205/218/231），不帶 auto-vs-manual signal。demo 的 auto-vs-manual 完全由
    # LANE_DIRECTION + 此 posture 邏輯決定（C2）。
    if posture == "Conservative" and is_promotion_class(cap.lane):
        return "MANUAL"  # §C.3 trust-building（promotion-class 在保守姿態下走人工）

    return "AUTO_VIA_GATE"


# ═══════════════════════════════════════════════════════════════════════════════
# L2Capability — typed model（extra="forbid"；enabled 預設 false）
# ═══════════════════════════════════════════════════════════════════════════════


class L2CapabilityTrigger(BaseModel):
    """capability 的觸發規格（§B trigger 區塊）。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["event", "schedule", "manual", "threshold"]
    spec: str = Field(default="", max_length=256)
    debounce_secs: int = Field(default=0, ge=0, le=86_400)  # §F.1 trailing-edge settle
    dedup_key: str = Field(default="capability_id+spec+coarse_subject", max_length=128)


class L2CapabilityBudget(BaseModel):
    """capability 的預算規格（§B budget 區塊）。daily_usd_cap ≤ DOC-08 $2/day。"""

    model_config = ConfigDict(extra="forbid")

    per_call_usd_cap: float = Field(default=0.0, ge=0.0, le=2.0)
    daily_usd_cap: float = Field(default=0.0, ge=0.0, le=2.0)  # ≤ DOC-08 cap
    tier_gated_spend: bool = True


class L2Capability(BaseModel):
    """單一 capability（operator enable/tune 的原子單位）。

    為什麼 extra="forbid"（reuse agent_contracts.py:109 範式）：catches 過期 v1 config /
    drift——一個帶未知欄的 stanza 是錯誤組態，不該靜默吞掉。
    為什麼**無 autonomy_level 欄**：autonomy 是 DERIVED（lane+min_tier+posture，見
    effective_autonomy），永不宣告。loader 額外 reject 宣告它的 config（§C2-adjacent）。
    """

    model_config = ConfigDict(extra="forbid")

    capability_id: str = Field(..., min_length=1, max_length=64)
    enabled: bool = False  # master off-switch — FAIL-CLOSED DEFAULT（省略 ⇒ false）
    min_tier: str = Field(default="L1", max_length=4)
    tier_capability_flag: str = Field(default="", max_length=64)
    model_tier: ModelTier = "local_sentinel"
    cloud_model_pref: str = Field(default="", max_length=64)
    lane: str = Field(default="none", max_length=32)
    output_schema_ref: str = Field(default="", max_length=128)
    prompt_contract_ref: str = Field(default="", max_length=128)
    out_of_bound_guard_ref: str = Field(default="", max_length=128)
    novelty_gate: bool = False
    consequential_default: bool = False  # → D3 ledger consequential_at_creation
    quality_metric_ref: str = Field(default="", max_length=128)
    trigger: L2CapabilityTrigger | None = None
    budget: L2CapabilityBudget | None = None

    @field_validator("min_tier")
    @classmethod
    def _validate_min_tier(cls, v: str) -> str:
        """min_tier 必為合法 LearningTier 名（L1-L5）；否則 reject（fail-closed）。"""
        if v not in LearningTier.__members__:
            raise ValueError(
                f"min_tier '{v}' 非合法 LearningTier（須 ∈ {sorted(LearningTier.__members__)}）"
            )
        return v

    @field_validator("lane")
    @classmethod
    def _validate_lane(cls, v: str) -> str:
        """lane 必在 LANE_DIRECTION keys（無 'live' lane → live 不可從 auto 到達）。

        為什麼在此 fail-closed：每個 lane 都必須能 resolve 一個 direction（§C）；一個
        無法 resolve 的 lane（含 'live'）是組態錯誤，必須 reject，不得靜默當 neutral。
        """
        if v not in LANE_DIRECTION:
            raise ValueError(
                f"lane '{v}' 不在 LANE_DIRECTION（合法：{sorted(LANE_DIRECTION)}；無 'live' lane）"
            )
        return v

    @property
    def min_tier_enum(self) -> LearningTier:
        """min_tier 字串 → LearningTier enum（已由 validator 保證合法）。"""
        return LearningTier[self.min_tier]


# ═══════════════════════════════════════════════════════════════════════════════
# Loader — 三 reject 分支（autonomy_level / can_auto_deploy_to_paper-as-posture / lane∉表）
# ═══════════════════════════════════════════════════════════════════════════════

# 為什麼 reject「把 can_auto_deploy_to_paper 當 posture gate」：它 True@all-tiers（無 signal）；
# 任何把它寫進 stanza 當 auto-vs-manual decider 的 config 是危險誤解（C2）。loader 掃 stanza
# 的任何 key/value 是否引用此字串。read-for-display 不經 loader（不會誤觸）。
_FORBIDDEN_POSTURE_GATE_TOKEN = "can_auto_deploy_to_paper"

# 為什麼 reject 宣告 autonomy_level：autonomy 是 DERIVED（effective_autonomy），宣告它 =
# drift error（C2-adjacent）。extra="forbid" 已會擋未知欄，但顯式檢查給出明確 reason。
_FORBIDDEN_DECLARED_FIELD = "autonomy_level"


class L2CapabilityRegistry(BaseModel):
    """已載入的 registry（capabilities + meta）。"""

    model_config = ConfigDict(extra="forbid")

    meta: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, L2Capability] = Field(default_factory=dict)

    def get(self, capability_id: str) -> L2Capability | None:
        return self.capabilities.get(capability_id)

    def enabled_capabilities(self) -> list[L2Capability]:
        """回傳 enabled=true 的 capabilities（P2 skeleton 預期空）。"""
        return [c for c in self.capabilities.values() if c.enabled]


def _default_registry_path() -> Path:
    """settings/l2_capability_registry.toml 的跨平台解析（reuse paper_trading 範式）。

    為什麼用 OPENCLAW_BASE_DIR env + parents[5] fallback：禁硬編 /home/ncyu /Users/ncyu
    （CLAUDE §六 跨平台 portable）；與 paper_trading_routes._PAPER_CONFIG_PATH 同範式。
    """
    base = Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path(__file__).resolve().parents[5])))
    return base / "settings" / "l2_capability_registry.toml"


class L2RegistryLoadError(ValueError):
    """registry 載入失敗（reject load）。fail-closed：壞 config 不靜默吞。"""


def _reject_forbidden_keys(raw_stanza: dict[str, Any], capability_id: str) -> None:
    """掃 stanza 的兩個顯式 reject token（autonomy_level 宣告 / posture-gate 誤用）。

    為什麼在 typed-model 驗證「之前」掃 raw dict：extra="forbid" 會擋 autonomy_level
    這種「未知頂層欄」，但 can_auto_deploy_to_paper 可能藏在 value（如 tier_capability_flag）
    或巢狀；顯式掃 raw 的 key+value 字串給出 deterministic reject + 明確 reason。
    """
    # (i) 宣告 autonomy_level → reject（autonomy 是 DERIVED）。
    if _FORBIDDEN_DECLARED_FIELD in raw_stanza:
        raise L2RegistryLoadError(
            f"capability '{capability_id}' 宣告了 '{_FORBIDDEN_DECLARED_FIELD}'："
            f"autonomy 是 DERIVED（lane+min_tier+posture），永不宣告（§C2-adjacent）"
        )
    # (ii) 把 can_auto_deploy_to_paper 當 posture gate 用 → reject（True@all-tiers 無 signal）。
    for k, v in raw_stanza.items():
        if _FORBIDDEN_POSTURE_GATE_TOKEN in str(k) or _FORBIDDEN_POSTURE_GATE_TOKEN in str(v):
            raise L2RegistryLoadError(
                f"capability '{capability_id}' 引用了 '{_FORBIDDEN_POSTURE_GATE_TOKEN}'"
                f"（key={k!r} value={v!r}）：它 True@all-tiers 無 auto-vs-manual signal，"
                f"不得當 posture gate（C2）"
            )


def load_capability_registry(path: Path | str | None = None) -> L2CapabilityRegistry:
    """載入 TOML registry → typed model。fail-closed：任何違規 reject（不靜默）。

    reject 分支（CC stress-test 16 + LANE_DIRECTION loader-reject）：
      (i)   unknown field（任何 model）→ extra="forbid" raise → reject。
      (ii)  宣告 autonomy_level → 顯式 reject（_reject_forbidden_keys）。
      (iii) 把 can_auto_deploy_to_paper 當 posture gate → 顯式 reject（_reject_forbidden_keys）。
      (iv)  lane ∉ LANE_DIRECTION（含 'live'）→ L2Capability.lane validator raise → reject。
      (v)   min_tier ∉ L1-L5 → validator raise → reject。

    path=None → 預設 settings/l2_capability_registry.toml；不存在 → 回空 registry
    （fail-closed：無 capability 即無 advisory，等同今天行為，非崩潰）。
    """
    p = Path(path) if path is not None else _default_registry_path()
    if not p.exists():
        logger.warning("l2_capability_registry TOML 不存在（%s）；回空 registry（fail-closed）", p)
        return L2CapabilityRegistry()

    try:
        raw = tomllib.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — 解析失敗 = reject load（fail-closed）
        # 為什麼只用 basename（p.name）而非完整 p：error 字串會回給已認證 caller（route
        # 的 status/capabilities/reload），完整 resolved path 含 runtime 主機絕對路徑
        # （如 /home/ncyu/.../settings/l2_capability_registry.toml），繞過 main_legacy 的
        # _LEAK_PATTERN sanitizer（只處理 HTTPException-str-detail，不處理 200-body / dict-detail）
        # 並違 CLAUDE §六「production code 不洩 /home/ncyu」。basename 已足夠 operator 定位是哪個
        # 檔（檔名固定），不洩主機路徑（E3-LOW-1 修）。完整 path 仍進伺服器端 log（loader caller 可記）。
        raise L2RegistryLoadError(
            f"l2_capability_registry TOML 解析失敗（{p.name}）：{exc}"
        ) from exc

    # TOML 用 [[capability]] array-of-tables；reject 未知頂層 key（meta/capability 以外）。
    known_top = {"meta", "capability"}
    unknown_top = set(raw) - known_top
    if unknown_top:
        raise L2RegistryLoadError(
            f"l2_capability_registry 含未知頂層 key {sorted(unknown_top)}"
            f"（合法：{sorted(known_top)}）"
        )

    meta = raw.get("meta", {})
    if not isinstance(meta, dict):
        raise L2RegistryLoadError("l2_capability_registry [meta] 必為 table")

    capabilities: dict[str, L2Capability] = {}
    for stanza in raw.get("capability", []):
        if not isinstance(stanza, dict):
            raise L2RegistryLoadError("每個 [[capability]] 必為 table")
        cap_id = str(stanza.get("capability_id", ""))
        # 顯式 reject 掃描在 typed 驗證前（給 deterministic reason）。
        _reject_forbidden_keys(stanza, cap_id or "<missing capability_id>")
        try:
            cap = L2Capability(**stanza)
        except Exception as exc:  # noqa: BLE001 — pydantic ValidationError → reject load
            raise L2RegistryLoadError(
                f"capability '{cap_id or '<unknown>'}' 驗證失敗（reject load）：{exc}"
            ) from exc
        if cap.capability_id in capabilities:
            raise L2RegistryLoadError(f"capability_id '{cap.capability_id}' 重複宣告")
        capabilities[cap.capability_id] = cap

    return L2CapabilityRegistry(meta=meta, capabilities=capabilities)


__all__ = [
    "LANE_DIRECTION",
    "EffectiveAutonomy",
    "is_promotion_class",
    "effective_autonomy",
    "L2Capability",
    "L2CapabilityTrigger",
    "L2CapabilityBudget",
    "L2CapabilityRegistry",
    "L2RegistryLoadError",
    "load_capability_registry",
]
