from __future__ import annotations

"""
Layer 2 AI Reasoning Engine — Cost Tracker / 成本追踪器
成本追踪（Claude + Perplexity）+ 自适应预算 + 定价核实

MODULE_NOTE (中文):
  本模組為 Layer 2 推理引擎的成本追蹤聚合 facade，G3-08 Phase 4 Method A
  拆分後（930→~480 LOC），實作分散到 3 個 sibling：
    - layer2_cost_recording.py  ：成本寫入路徑（9 method）
    - layer2_adaptive.py        ：自適應預算 + cost_edge_ratio（3 method）
    - layer2_h_state_snapshots.py：H2/H5 wire-shape 投影（2 method）
  本主檔保留：
    - ctor + 持久化（_load / _apply_state / _save / _read_raw / _write_raw）
    - daily budget / session 預算讀取邏輯
    - session history / PnL 歸因
    - pricing / config 讀寫
    - cost summary / ollama_stats / check_*
    - 14 個 1-line delegator 委派至 sibling
  Layer2CostTracker 仍為 STRATEGIST_AGENT.cost_tracker SSOT，外部 import
  路徑 ``from .layer2_cost_tracker import Layer2CostTracker`` 不變。

  狀態持久化到 runtime/layer2_cost_state.json（atomic tmp→replace）。
  $2/天硬上限不可突破（DOC-08 §4）。

MODULE_NOTE (English):
  Cost tracking aggregator facade for Layer 2. After G3-08 Phase 4
  Method A split (930→~480 LOC), implementation lives in 3 siblings:
    - layer2_cost_recording.py     : cost-write path (9 methods)
    - layer2_adaptive.py           : adaptive budget + cost_edge_ratio (3)
    - layer2_h_state_snapshots.py  : H2/H5 wire-shape projection (2)
  This main file keeps:
    - ctor + persistence (_load / _apply_state / _save / _read_raw /
      _write_raw)
    - daily budget / session budget read logic
    - session history / PnL attribution
    - pricing / config read/write
    - cost summary / ollama_stats / check_*
    - 14 1-line delegators that forward into the sibling functions
  Layer2CostTracker remains the STRATEGIST_AGENT.cost_tracker SSOT; the
  external import path
  ``from .layer2_cost_tracker import Layer2CostTracker`` is unchanged.

  State persisted to runtime/layer2_cost_state.json (atomic tmp→replace).
  $2/day hard cap is absolute (DOC-08 §4).
"""

import contextlib
import datetime
import fcntl
import json
import logging
import os
import stat
import threading
from pathlib import Path
from typing import Any

from .layer2_types import (
    AdaptiveBudgetState,
    Layer2Config,
    Layer2Session,
    PricingTable,
)

# G3-08 Phase 4 Method A sibling re-exports / Method A 姊妹模組重導入
# Each sibling exposes module-level functions whose first arg is the
# tracker instance; the Layer2CostTracker class delegates 14 methods to
# these functions via 1-line wrappers (per RFC §6.4 / §7.2).
# 各 sibling 暴露 module-level functions（第一參數為 tracker 實例）；
# Layer2CostTracker 14 個 method 以 1-line delegator 委派至此（per RFC
# §6.4 / §7.2）。
from . import layer2_adaptive as _adaptive_sibling
from . import layer2_cost_recording as _recording_sibling
from . import layer2_h_state_snapshots as _h_state_sibling
from . import l2_secret_redactor as _redactor
# 隊列 H：grandfather 正規化用的靜態白名單來源（無循環——provider_client
# 頂層不 import 任何 app 模組，layer2_types 只在函數內延遲 import）。
from . import provider_client

logger = logging.getLogger(__name__)


# D3 sanitize（設計 §D.1.1「applies everywhere full text is persisted」）：session
# 摘要落 durable layer2_cost_state.json 前過 secret redactor 的自由文本欄。這些欄是
# LLM 生成（final_summary / recommendation.reasoning / insight.detail·title），可能
# drift 進 secret（DSN / api_key / bearer），與 D3 ledger 寫入路徑同一消毒語意。
# 為何在「寫入前」：layer2_cost_state.json 是長存盤面，未消毒 secret 落盤後難清除
# （root principle 8 reconstructable + CLAUDE §四 signed-auth material never leak）。
def _sanitize_session_dict_for_persist(session_dict: dict[str, Any]) -> dict[str, Any]:
    """回新 dict（不就地改 caller）：對 session.to_dict() 的 LLM 自由文本欄套 D3
    redactor。只動會夾 secret 的自由文本欄（final_summary / recommendation.reasoning
    / insights[].title·detail），結構/數值欄（cost/tokens/symbol/action/...）原樣
    保留——避免誤遮破壞 forensic 可讀的盤面欄位。"""
    out = dict(session_dict)

    fs = out.get("final_summary")
    if isinstance(fs, str) and fs:
        out["final_summary"] = _redactor.redact(fs).text

    rec = out.get("recommendation")
    if isinstance(rec, dict):
        rec_out = dict(rec)
        reasoning = rec_out.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            rec_out["reasoning"] = _redactor.redact(reasoning).text
        out["recommendation"] = rec_out

    insights = out.get("insights")
    if isinstance(insights, list):
        sanitized_insights = []
        for ins in insights:
            if isinstance(ins, dict):
                ins_out = dict(ins)
                for k in ("title", "detail"):
                    v = ins_out.get(k)
                    if isinstance(v, str) and v:
                        ins_out[k] = _redactor.redact(v).text
                sanitized_insights.append(ins_out)
            else:
                sanitized_insights.append(ins)
        out["insights"] = sanitized_insights

    return out


# ═══════════════════════════════════════════════════════════════════════════════
# Cost State Store / 成本状态存储
# ═══════════════════════════════════════════════════════════════════════════════

# 隊列 H：provider/model 配對欄位（default + tier2/3 降級），與 layer2_routes
# 的 _PROVIDER_MODEL_CONFIG_KEYS 覆蓋的 6 鍵一一對應。
_PROVIDER_MODEL_PAIR_FIELDS: tuple[tuple[str, str], ...] = (
    ("default_provider", "default_model"),
    ("fallback_tier2_provider", "fallback_tier2_model"),
    ("fallback_tier3_provider", "fallback_tier3_model"),
)


def _pair_statically_legal(provider: str, model: str) -> bool:
    """靜態判定 provider/model 配對是否合法（純記憶體查表，不打網路）。

    cloud provider（anthropic/deepseek/openai）：model 必須在
    provider_client.PROVIDER_TIERS 靜態白名單內——與 layer2_routes 線上校驗
    用的 provider_model_catalog.allowed_model_values 對 cloud provider 逐字
    等價（兩者同源自 TIER_* 常量），故本檢查放行的配對線上校驗必也放行。
    local_llm：allowed_model_values 依賴 Ollama 即時列表（掉線=空表），
    啟動載入時不可依賴；只做弱前綴檢查（``local:`` 前綴），細粒度合法性
    仍由線上校驗把關——避免 Ollama 掉線時把合法 local 配對誤重置。
    """
    if provider not in provider_client.L2_PROVIDERS:
        return False
    if provider == provider_client.PROVIDER_LOCAL_LLM:
        return provider_client.is_local_tier(model)
    return model in provider_client.PROVIDER_TIERS.get(provider, [])


def _default_cost_state() -> dict[str, Any]:
    """Default cost state structure / 默认成本状态结构"""
    return {
        "daily_spend": {},             # {"2026-03-27": {"claude_usd": 0.0, "search_usd": 0.0, "total_usd": 0.0, "session_count": 0}}
        "sessions": [],                # List of session summaries (most recent first, max 500)
        "adaptive": {
            "multiplier": 1.0,
            "roi_7d": None,
            "ai_spend_7d_usd": 0.0,
            "paper_pnl_7d_usd": 0.0,
            "data_days": 0,
            "last_recalculated_ms": 0,
        },
        "pricing": PricingTable().to_dict(),
        "config": Layer2Config().to_dict(),
    }


class Layer2CostTracker:
    """
    Tracks all Layer 2 AI costs, enforces budgets, manages adaptive multiplier.
    追踪所有 Layer 2 AI 成本，执行预算限制，管理自适应倍率。

    G3-08 Phase 4 Method A: 14 methods delegate to module-level functions
    in 3 sibling files (layer2_cost_recording / layer2_adaptive /
    layer2_h_state_snapshots). The class itself stays the SSOT and
    persists state; sibling functions take ``self`` as the first arg.
    G3-08 Phase 4 Method A：14 個方法委派到 3 個 sibling 模組的 module-
    level functions（layer2_cost_recording / layer2_adaptive /
    layer2_h_state_snapshots）。Class 本身仍為 SSOT 並持久化狀態；
    sibling functions 以 ``self`` 為第一參數。
    """

    MAX_SESSION_HISTORY = 500

    def __init__(self, state_file: str | None = None):
        if state_file is None:
            state_file = os.getenv(
                "OPENCLAW_LAYER2_COST_FILE",
                os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "..", "runtime", "layer2_cost_state.json")
                ),
            )
        self._file_path = Path(state_file)
        self._lock = threading.RLock()
        # P2-13（冷審計 R2）：跨進程互斥基礎設施。self._lock（RLock）只擋同進程
        # 線程；4 uvicorn worker 各持一份 tracker 實例共寫同一 state 檔，須加
        # flock。鎖標的是 sidecar 檔而非 state 檔本身——_write_raw 用 tmp→replace
        # 換 inode，鎖被替換掉的檔案會靜默失去互斥。fd/depth 由 self._lock 保護。
        self._flock_path = Path(str(self._file_path) + ".lock")
        self._flock_fd: int | None = None
        self._flock_depth = 0
        self._config = Layer2Config()
        self._pricing = PricingTable()
        self._adaptive = AdaptiveBudgetState()
        # B14: Initialize _ollama_stats in __init__ instead of lazy hasattr check.
        # B14: 在 __init__ 中初始化 _ollama_stats，而非延迟的 hasattr 检查。
        self._ollama_stats: dict = {}
        self._ollama_stats_initialized: bool = False
        self._load()

    # ── Persistence / 持久化 ──

    @contextlib.contextmanager
    def _state_lock(self):
        """跨進程 + 跨線程互斥的狀態寫入鎖（P2-13，冷審計 R2 AI-E confirmed）。

        為什麼需要：4 個 uvicorn worker 對 layer2_cost_state.json 做
        read-modify-write 時互吞對方剛寫入的成本（lost update）→ daily_spend
        低估 → DOC-08 $2/day 預算閘可被繞過；且共用固定名 .tmp 檔會在
        tmp→replace 競態下直接 FileNotFoundError（回歸測試已實證兩者）。

        選型（flock 而非 O_APPEND JSONL 改造）：state 檔是 document 型 SSOT
        （config/pricing/adaptive/daily rollup/session history 多面讀者），
        JSONL event-log 需重寫全部讀取路徑 + fold 邏輯 + 既有檔遷移，對
        dormant lane 過度工程。flock 是本 codebase 既有模式（paper_trading_wiring
        / evolution_auto_scheduler / grafana_data_writer 等），Mac/Linux 雙
        平台可用，進程崩潰時 kernel 隨 fd 關閉自動釋放，無 stale lock。

        重入：先取 self._lock（RLock，同線程可重入），flock 只在 depth 0→1
        時取得——同進程對同一檔開第二個 fd 再 flock 會自我死鎖，必須用
        depth 計數消化嵌套（如 record_session 內嵌 _increment_daily_session_count）。
        使用契約：任何「讀 raw → 改 → 寫 raw」序列必須整段包在本鎖內，
        只鎖 _write_raw 擋不住 lost update。
        """
        with self._lock:
            if self._flock_depth == 0:
                fd = os.open(str(self._flock_path), os.O_CREAT | os.O_RDWR, 0o600)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                except OSError:
                    os.close(fd)
                    raise
                self._flock_fd = fd
            self._flock_depth += 1
            try:
                yield
            finally:
                self._flock_depth -= 1
                if self._flock_depth == 0 and self._flock_fd is not None:
                    try:
                        fcntl.flock(self._flock_fd, fcntl.LOCK_UN)
                    finally:
                        os.close(self._flock_fd)
                        self._flock_fd = None

    def _load(self) -> None:
        """Load state from file or initialize defaults / 从文件加载状态或初始化默认值"""
        with self._lock:
            if self._file_path.exists():
                try:
                    with self._file_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    if self._apply_state(data):
                        # 隊列 H：grandfather 修復後立即持久化，避免非法舊值
                        # 殘留檔案。_save 走 _state_lock（RLock 可重入 + flock）；
                        # 冪等——修復後配對合法，下次載入不再觸發回寫。
                        self._save()
                    return
                except (json.JSONDecodeError, KeyError, TypeError):
                    logger.warning("layer2_cost_state.json corrupted, reinitializing")
            self._save()

    def _apply_state(self, data: dict[str, Any]) -> bool:
        """Apply loaded state to in-memory objects / 将加载的状态应用到内存对象

        回傳值：是否觸發了 grandfather 配對修復（True 時呼叫端須回寫持久化）。
        """
        # Config
        cfg = data.get("config", {})
        for k, v in cfg.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)

        # 隊列 H grandfather 正規化：歷史 state 檔可能殘留靜態非法的
        # provider/model 配對（例 default=(anthropic, "qwen3.5:9b")）。
        # layer2_routes._validate_layer2_model_config 對 6 鍵做整體校驗，
        # 非法舊值會把全部 6 鍵鎖成事實唯讀。此處在狀態擁有者的 load 路徑
        # 逐對重置為出廠對（Layer2Config dataclass 預設）。行為保持：引擎
        # map_tier_to_provider 對未知 tier 取 rank 3 本就映到出廠 tier
        # （anthropic→sonnet），重置只是把實際行為誠實化。
        factory = Layer2Config()
        repaired = False
        for provider_key, model_key in _PROVIDER_MODEL_PAIR_FIELDS:
            provider = str(getattr(self._config, provider_key) or "")
            model = str(getattr(self._config, model_key) or "")
            if _pair_statically_legal(provider, model):
                continue
            setattr(self._config, provider_key, getattr(factory, provider_key))
            setattr(self._config, model_key, getattr(factory, model_key))
            repaired = True
            logger.warning(
                "layer2 config grandfather 修復：(%s, %s)=(%r, %r) 非法，重置為出廠對 (%r, %r)",
                provider_key, model_key, provider, model,
                getattr(factory, provider_key), getattr(factory, model_key),
            )

        # Pricing
        pricing_data = data.get("pricing", {})
        models_data = pricing_data.get("models", {})
        for tier, mp in models_data.items():
            if tier in self._pricing.models:
                self._pricing.models[tier].input_per_mtok = mp.get("input_per_mtok", self._pricing.models[tier].input_per_mtok)
                self._pricing.models[tier].output_per_mtok = mp.get("output_per_mtok", self._pricing.models[tier].output_per_mtok)
                self._pricing.models[tier].last_verified_date = mp.get("last_verified_date", "")
        self._pricing.perplexity_per_search = pricing_data.get("perplexity_per_search", self._pricing.perplexity_per_search)
        self._pricing.perplexity_last_verified_date = pricing_data.get("perplexity_last_verified_date", "")
        self._pricing.source_meta = pricing_data.get("source_meta", {}) if isinstance(pricing_data.get("source_meta", {}), dict) else {}

        # Adaptive
        adp = data.get("adaptive", {})
        self._adaptive.multiplier = adp.get("multiplier", 1.0)
        self._adaptive.roi_7d = adp.get("roi_7d")
        self._adaptive.ai_spend_7d_usd = adp.get("ai_spend_7d_usd", 0.0)
        self._adaptive.paper_pnl_7d_usd = adp.get("paper_pnl_7d_usd", 0.0)
        self._adaptive.data_days = adp.get("data_days", 0)
        self._adaptive.last_recalculated_ms = adp.get("last_recalculated_ms", 0)

        return repaired

    def _save(self) -> None:
        """Atomic persist: tmp-file-then-replace / 原子持久化：tmp→replace 防止損壞

        P2-13：_read_raw→merge→寫檔是 read-modify-write，取 _state_lock 而非
        僅 RLock（跨進程互斥見 _state_lock docstring）。
        """
        with self._state_lock():
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            state = self._read_raw()
            state["config"] = self._config.to_dict()
            state["pricing"] = self._pricing.to_dict()
            state["adaptive"] = self._adaptive.to_dict()
            tmp_path = self._file_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            except OSError:
                pass
            tmp_path.replace(self._file_path)

    def _read_raw(self) -> dict[str, Any]:
        """Read raw state from file / 从文件读取原始状态"""
        if self._file_path.exists():
            try:
                with self._file_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, TypeError):
                pass
        return _default_cost_state()

    def _write_raw(self, raw: dict[str, Any]) -> None:
        """Atomic write: tmp-file-then-replace to prevent corruption / 原子寫入：tmp→replace 防止損壞

        P2-13：本函數自身也取 _state_lock（可重入），兜底任何未包整段
        read-modify-write 的呼叫端；但正確用法仍是呼叫端整段包鎖。
        固定名 .tmp 檔在 flock 之下不會跨進程相撞。
        """
        with self._state_lock():
            raw["config"] = self._config.to_dict()
            raw["pricing"] = self._pricing.to_dict()
            raw["adaptive"] = self._adaptive.to_dict()
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._file_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            try:
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
            tmp_path.replace(self._file_path)

    # ── Daily Spend / 每日花费 ──

    def _today_key(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    def get_daily_spend(self, date_key: str | None = None) -> dict[str, Any]:
        """Get spend for a specific day / 获取某天的花费"""
        if date_key is None:
            date_key = self._today_key()
        raw = self._read_raw()
        return raw.get("daily_spend", {}).get(date_key, {
            "claude_usd": 0.0,
            "search_usd": 0.0,
            "total_usd": 0.0,
            "session_count": 0,
        })

    def get_today_total_usd(self) -> float:
        """Get today's total spend / 获取今天的总花费"""
        return self.get_daily_spend().get("total_usd", 0.0)

    def check_daily_budget(self) -> tuple[bool, float]:
        """
        Check if daily budget allows a new session.
        Returns (allowed, remaining_usd).
        Uses min(hard_cap, adaptive_effective_budget) when adaptive is enabled.
        检查每日预算是否允许新 session。自适应启用时使用有效预算和硬上限中的较小值。
        """
        today_total = self.get_today_total_usd()
        cap = self._config.daily_hard_cap_usd
        if self._config.adaptive_enabled and self._adaptive.effective_daily_budget_usd > 0:
            cap = min(cap, self._adaptive.effective_daily_budget_usd)
        remaining = round(cap - today_total, 4)
        return remaining > 0, max(0.0, remaining)

    def get_effective_session_budget(self, model_tier: str) -> float:
        """
        Get effective session budget considering adaptive multiplier.
        获取考虑自适应倍率后的有效 session 预算。
        """
        if model_tier == "opus":
            base = self._config.session_budget_opus_usd
        else:
            base = self._config.session_budget_sonnet_usd

        if self._config.adaptive_enabled:
            adjusted = round(base * self._adaptive.multiplier, 4)
        else:
            adjusted = base

        # Cannot exceed daily remaining
        _, remaining = self.check_daily_budget()
        return min(adjusted, remaining)

    # ── G3-08 Phase 3 / Phase 4: H state snapshot delegators ──
    # Delegated to layer2_h_state_snapshots sibling (Phase 4 Method A).
    # 委派至 layer2_h_state_snapshots sibling（Phase 4 Method A）。

    def get_h2_snapshot(self) -> dict[str, Any]:
        """Delegator → layer2_h_state_snapshots.get_h2_snapshot. / 委派至 sibling。"""
        return _h_state_sibling.get_h2_snapshot(self)

    def get_h5_snapshot(self) -> dict[str, Any]:
        """Delegator → layer2_h_state_snapshots.get_h5_snapshot. / 委派至 sibling。"""
        return _h_state_sibling.get_h5_snapshot(self)

    # ── Record Costs / 记录成本（delegators to layer2_cost_recording） ──

    def record_claude_cost(
        self, session: Layer2Session, input_tokens: int, output_tokens: int, model_tier: str,
    ) -> float:
        """Delegator → layer2_cost_recording.record_claude_cost. / 委派至 sibling。"""
        return _recording_sibling.record_claude_cost(
            self, session, input_tokens, output_tokens, model_tier,
        )

    def record_search_cost(self, session: Layer2Session, provider: str, cost_usd: float) -> None:
        """Delegator → layer2_cost_recording.record_search_cost. / 委派至 sibling。"""
        _recording_sibling.record_search_cost(self, session, provider, cost_usd)

    def _add_daily_claude_cost(self, cost: float) -> None:
        """Delegator → layer2_cost_recording._add_daily_claude_cost. / 委派至 sibling。"""
        _recording_sibling._add_daily_claude_cost(self, cost)

    def _sync_to_rust_budget(
        self, provider: str, model: str, tokens_in: int = 0, tokens_out: int = 0,
    ) -> None:
        """Delegator → layer2_cost_recording._sync_to_rust_budget. / 委派至 sibling。"""
        _recording_sibling._sync_to_rust_budget(
            self, provider=provider, model=model, tokens_in=tokens_in, tokens_out=tokens_out,
        )

    def _add_daily_search_cost(self, cost: float) -> None:
        """Delegator → layer2_cost_recording._add_daily_search_cost. / 委派至 sibling。"""
        _recording_sibling._add_daily_search_cost(self, cost)

    def _increment_daily_session_count(self) -> None:
        """Delegator → layer2_cost_recording._increment_daily_session_count. / 委派至 sibling。"""
        _recording_sibling._increment_daily_session_count(self)

    # ── Session Management / Session 管理 ──

    def record_session(self, session: Layer2Session) -> None:
        """Record a completed session summary / 记录已完成 session 的摘要

        D3 §D.1.1：session.to_dict() 的 LLM 自由文本欄（final_summary /
        recommendation.reasoning / insights）在落 durable layer2_cost_state.json
        之前過 secret redactor（消毒在寫入路徑、無窗口）。

        P2-13：整段（計數 + 讀 raw + 插入 + 寫回）包 _state_lock，跨進程原子。
        """
        with self._state_lock():
            self._increment_daily_session_count()
            raw = self._read_raw()
            sessions = raw.setdefault("sessions", [])
            sessions.insert(0, _sanitize_session_dict_for_persist(session.to_dict()))
            # Trim to max history
            if len(sessions) > self.MAX_SESSION_HISTORY:
                raw["sessions"] = sessions[:self.MAX_SESSION_HISTORY]
            self._write_raw(raw)

    def get_sessions(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """Get session history / 获取 session 历史"""
        raw = self._read_raw()
        sessions = raw.get("sessions", [])
        return sessions[offset:offset + limit]

    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None:
        """Find a session by ID / 按 ID 查找 session"""
        raw = self._read_raw()
        for s in raw.get("sessions", []):
            if s.get("session_id") == session_id:
                return s
        return None

    # ── PnL Attribution / PnL 归因 ──

    def backfill_pnl_attribution(self, session_id: str, attribution: dict[str, Any]) -> bool:
        """
        Backfill PnL attribution for a completed session.
        为已完成 session 回填 PnL 归因。

        P2-13：read-modify-write 序列，包 _state_lock（跨進程原子）。
        """
        with self._state_lock():
            raw = self._read_raw()
            for s in raw.get("sessions", []):
                if s.get("session_id") == session_id:
                    s["pnl_attribution"] = attribution
                    self._write_raw(raw)
                    return True
            return False

    # ── Adaptive Budget / 自适应预算（delegators to layer2_adaptive） ──

    def recalculate_adaptive(self) -> AdaptiveBudgetState:
        """Delegator → layer2_adaptive.recalculate_adaptive. / 委派至 sibling。"""
        return _adaptive_sibling.recalculate_adaptive(self)

    def get_adaptive_state(self) -> AdaptiveBudgetState:
        """Delegator → layer2_adaptive.get_adaptive_state. / 委派至 sibling。"""
        return _adaptive_sibling.get_adaptive_state(self)

    # ── Pricing / 定价 ──

    def get_pricing(self) -> PricingTable:
        return self._pricing

    def update_pricing(self, updates: dict[str, Any]) -> PricingTable:
        """Update pricing table entries / 更新定价表条目"""
        with self._lock:
            models_update = updates.get("models", {})
            for tier, mp_update in models_update.items():
                if tier in self._pricing.models:
                    mp = self._pricing.models[tier]
                    if "input_per_mtok" in mp_update:
                        mp.input_per_mtok = mp_update["input_per_mtok"]
                    if "output_per_mtok" in mp_update:
                        mp.output_per_mtok = mp_update["output_per_mtok"]
                    if "last_verified_date" in mp_update:
                        mp.last_verified_date = mp_update["last_verified_date"]
            if "perplexity_per_search" in updates:
                self._pricing.perplexity_per_search = updates["perplexity_per_search"]
            if "perplexity_last_verified_date" in updates:
                self._pricing.perplexity_last_verified_date = updates["perplexity_last_verified_date"]
            if isinstance(updates.get("source_meta"), dict):
                self._pricing.source_meta = updates["source_meta"]
            self._save()
            return self._pricing

    # ── Config / 配置 ──

    def get_config(self) -> Layer2Config:
        return self._config

    def update_config(self, updates: dict[str, Any]) -> Layer2Config:
        """Update engine configuration / 更新引擎配置"""
        with self._lock:
            for k, v in updates.items():
                if hasattr(self._config, k):
                    setattr(self._config, k, v)
            self._save()
            return self._config

    # ── Cost Summary / 成本汇总 ──

    def get_cost_summary(self) -> dict[str, Any]:
        """
        Full cost summary for API response.
        完整成本汇总（用于 API 响应）。
        """
        raw = self._read_raw()
        today_key = self._today_key()
        today_data = raw.get("daily_spend", {}).get(today_key, {})
        allowed, remaining = self.check_daily_budget()

        # Total cumulative
        total_cumulative = 0.0
        total_sessions = 0
        for day_data in raw.get("daily_spend", {}).values():
            total_cumulative += day_data.get("total_usd", 0.0)
            total_sessions += day_data.get("session_count", 0)

        return {
            "today": {
                "date": today_key,
                "claude_usd": round(today_data.get("claude_usd", 0.0), 4),
                "search_usd": round(today_data.get("search_usd", 0.0), 4),
                "total_usd": round(today_data.get("total_usd", 0.0), 4),
                "session_count": today_data.get("session_count", 0),
            },
            "budget": {
                "daily_hard_cap_usd": self._config.daily_hard_cap_usd,
                "remaining_usd": remaining,
                "budget_ok": allowed,
            },
            "adaptive": self._adaptive.to_dict(),
            "cumulative": {
                "total_usd": round(total_cumulative, 4),
                "total_sessions": total_sessions,
            },
            "pricing_stale": self._pricing.is_stale(),
            # Principle 10 (cognitive honesty): all PnL-based metrics are paper simulation only
            # 根原則 10（認知誠實）：所有 PnL 相關指標均基於模擬，非真實盈虧
            "roi_basis": "paper_simulation_only",
            "roi_disclaimer": "基於模擬 PnL，非真實盈虧",
        }

    # ── Unified Call Recording / 統一調用記錄（delegators to layer2_cost_recording） ──

    def record_call(
        self,
        provider: str,
        model: str,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Delegator → layer2_cost_recording.record_call. / 委派至 sibling。"""
        _recording_sibling.record_call(
            self,
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            cost_usd=cost_usd,
        )

    def record_ollama_call(
        self,
        model: str,
        duration_ms: float = 0.0,
        prompt_tokens: int = 0,
    ) -> None:
        """Delegator → layer2_cost_recording.record_ollama_call. / 委派至 sibling。"""
        _recording_sibling.record_ollama_call(
            self, model=model, duration_ms=duration_ms, prompt_tokens=prompt_tokens,
        )

    def get_ollama_stats(self) -> dict:
        """
        Return in-memory Ollama call statistics per model.
        返回記憶體中每個模型的 Ollama 調用統計。

        B14: Returns a meaningful response even when empty (status + total_calls).
        B14: 即使无数据也返回有意义的响应（status + total_calls）。
        """
        with self._lock:
            if not self._ollama_stats:
                # B14: Return meaningful empty response instead of bare {}
                # B14: 返回有意义的空响应而非裸 {}
                return {"status": "no_data", "total_calls": 0}
            # Strip "ollama/" prefix for backward compatibility with callers
            # expecting bare model names (e.g., "l1_9b" not "ollama/l1_9b").
            # 去除 "ollama/" 前綴，向後兼容調用者期望的裸模型名稱。
            result: dict = {}
            total_calls = 0
            for key, val in self._ollama_stats.items():
                short_key = key.split("/", 1)[1] if "/" in key else key
                if key.startswith("ollama/") or "/" not in key:
                    result[short_key] = val
                    total_calls += val.get("call_count", 0)
            result["status"] = "active"
            result["total_calls"] = total_calls
            return result

    def get_cost_edge_ratio(self) -> dict:
        """Delegator → layer2_adaptive.get_cost_edge_ratio. / 委派至 sibling。"""
        return _adaptive_sibling.get_cost_edge_ratio(self)

    # ── Budget Check for Session / Session 预算检查 ──

    def check_session_budget(self, session: Layer2Session) -> bool:
        """Check if session is still within budget / 检查 session 是否仍在预算内"""
        return session.total_cost() < session.session_budget_usd

    def check_daily_hard_cap(self) -> bool:
        """Check if daily hard cap is exceeded / 检查每日硬上限是否已超过"""
        allowed, _ = self.check_daily_budget()
        return allowed

    def reset_today_costs(self) -> dict[str, Any]:
        """Delegator → layer2_cost_recording.reset_today_costs. / 委派至 sibling。"""
        return _recording_sibling.reset_today_costs(self)


# ═══════════════════════════════════════════════════════════════════════════════
# API Budget Manager — re-export for backward compatibility
# API 預算管理器 — 重導出以保持向後兼容
# Extracted to api_budget_manager.py / 已提取至 api_budget_manager.py
# ═══════════════════════════════════════════════════════════════════════════════
from .api_budget_manager import APIBudgetManager  # noqa: F401
