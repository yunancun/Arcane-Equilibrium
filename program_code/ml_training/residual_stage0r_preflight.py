"""
MODULE_NOTE
模塊用途：Stage-0R replay preflight **orchestrator**（PART 4 Gap A + Gap D）。把
β-residualization 晉升閘從「因缺 producer 輸入而 INERT」變成「真正審判真實候選」——
但**三重 flag-gated OFF**（部署即行為中性，operator 評估後才啟用）。對每個「數值預閘
達標但缺 lineage」的 demo shadow 候選，跑一條內聚流程：
  ① 多因子 residual（btc+market+funding）+ permutation（model-free null）；PBO 對單一
     配置**誠實 defer**（candidate_oos_returns=None → 既有 defer_data 路徑），**絕不**
     合成/捏造 PBO peer（#1 方法論硬規則）。
  ② 從真實 fills 推導候選**淨方向** net_side（**絕不**用 +1 預設；funding sign 反號會
     放大 carry = 本功能要消滅的 false-promote 向量 = MIT 硬條件）。
  ③（Gap D）預先註冊 selection-bias 斷言（K>=10 / oos_pct>=0.20 / cv_protocol /
     embargo），跑 orphan validator；失敗 fail-closed（不註冊/不寫 drar/不蓋章）。
  ④ 註冊 replay experiment（**重用** bridge：寫 replay.experiments + sealed
     hidden_oos_state_registry，含 4 道 leak guard）。
  ⑤ 寫 drar（**重用**抽出的薄 writer；非 pass 報告誠實 skip）。
  ⑥ 蓋 lineage 到 shadow rec（UPDATE，WHERE replay_experiment_id IS NULL 防重蓋）。
主要類/函數：ResidualPreflightConfig、ResidualPreflightSummary、CandidatePreflightOutcome、
  run_residual_stage0r_preflight、_select_candidates、_build_selection_bias_block。
依賴：residual_hidden_oos_bridge（register primitive，重用）、residual_alpha_cycle
  （derive_n_trials）、residual_alpha_producer_db（多因子 DB 載入 + net_side 推導，重用）、
  promotion_evidence.write_demo_residual_alpha_report（drar writer，重用）、
  selection_bias_validator（Gap D orphan validator，接線）、psycopg2。
  數值預閘門檻預設對齊 mlde_demo_applier.DemoApplierConfig 的 live-candidate 門檻
  （net_bps=5.0 / confidence=0.65 / samples=30），但**不 import** 該模組（避免拉進
  整個 applier 重鏈 + 直跑 import 脆弱性）；門檻寫進 ResidualPreflightConfig 可覆蓋。
硬邊界：
  - **行為中性**：``OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT`` 預設 OFF + 既有
    ``OPENCLAW_RESIDUAL_ALPHA_PRODUCER`` 預設 OFF + cron job 不在 DEFAULT_JOBS。
    任一未開 → orchestrator 早退、零寫入、生產 cron 零新路徑。
  - **DEMO evidence lane ONLY**：只寫 replay.experiments / hidden_oos_state_registry /
    demo_residual_alpha_reports + rec-stamp UPDATE；只讀 demo 資料。**零 live / auth /
    order / risk / lease 變動**。live-candidate INSERT 留在下游 mlde_demo_applier
    （需 GovernanceHub + Decision Lease，**不碰**）。
  - **NO peer synthesis**：單一配置 → candidate_oos_returns=None → 既有 defer；**永不**
    捏造/重組 peer；**永不**新增 verdict literal（單配置區分寫進 reasons 不進 verdict enum）。
  - **hash byte-identity**：bridge ``_canonical_sha256(report)`` == drar report_hash ==
    registry demo_residual_alpha_report_hash，三者同 canonical bytes（§5.6）。
  - **PIT/leak**：hidden-OOS hold-out 由 bridge 強制；net_side 真實；permutation in-window；
    idempotent re-run（WHERE replay_experiment_id IS NULL / WHERE state='sealed'）。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

try:  # 套件式 import（app runtime）
    from program_code.ml_training.residual_alpha_cycle import (
        RESIDUAL_PRODUCER_ENV,
        derive_n_trials,
        residual_producer_enabled,
    )
    from program_code.ml_training.residual_alpha_producer_db import (
        DEFAULT_BUCKET_SEC,
        load_candidate_net_side,
        load_klines_by_symbols,
        load_liquid_basket_symbols,
        load_symbol_lifecycles,
        load_funding_rates,
        pit_active_symbols,
        to_epoch_seconds,
    )
    from program_code.ml_training.residual_hidden_oos_bridge import (
        RESIDUAL_ALPHA_REPORT_FIELD as _RESIDUAL_ALPHA_REPORT_FIELD,
        register_residual_candidate_experiment,
    )
    from program_code.ml_training.promotion_evidence import (
        write_demo_residual_alpha_report,
    )
    from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.experiment_registry import (  # noqa: E501
        run_register_in_pg_xact,
    )
    from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.selection_bias_validator import (  # noqa: E501
        validate_selection_bias_correction,
    )
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from ml_training.residual_alpha_cycle import (  # type: ignore
        RESIDUAL_PRODUCER_ENV,
        derive_n_trials,
        residual_producer_enabled,
    )
    from ml_training.residual_alpha_producer_db import (  # type: ignore
        DEFAULT_BUCKET_SEC,
        load_candidate_net_side,
        load_klines_by_symbols,
        load_liquid_basket_symbols,
        load_symbol_lifecycles,
        load_funding_rates,
        pit_active_symbols,
        to_epoch_seconds,
    )
    from ml_training.residual_hidden_oos_bridge import (  # type: ignore
        RESIDUAL_ALPHA_REPORT_FIELD as _RESIDUAL_ALPHA_REPORT_FIELD,
        register_residual_candidate_experiment,
    )
    from ml_training.promotion_evidence import (  # type: ignore
        write_demo_residual_alpha_report,
    )
    from exchange_connectors.bybit_connector.control_api_v1.replay.experiment_registry import (  # type: ignore  # noqa: E501
        run_register_in_pg_xact,
    )
    from exchange_connectors.bybit_connector.control_api_v1.replay.selection_bias_validator import (  # type: ignore  # noqa: E501
        validate_selection_bias_correction,
    )

logger = logging.getLogger("residual_stage0r_preflight")

# NEW flag（預設 OFF）：orchestrator 唯一寫入入口。與既有 RESIDUAL_PRODUCER_ENV
# **同時 ON** 才會真寫（bridge 內部還會再 check RESIDUAL_PRODUCER_ENV）。
STAGE0R_PREFLIGHT_ENV = "OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT"

# drar / experiment source 標籤（calibrated_replay tier 對應的 producer source）。
PREFLIGHT_SOURCE = "residual_stage0r_preflight"

# 蓋章寫的 lineage tier（source_contract PROMOTION_EVIDENCE_SOURCE_TIERS 之一）。
CALIBRATED_REPLAY_TIER = "calibrated_replay"

# market basket 載入上限（避免一次拉太多 symbol klines；PIT-active 過濾仍在算 factor 時做）。
_DEFAULT_MAX_BASKET_SYMBOLS = 60


def stage0r_preflight_enabled() -> bool:
    """NEW flag（預設 OFF）：未明確設 ``OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1`` 一律
    不跑 orchestrator。部署即關（fail-closed），不寫任何 row，待 operator 評估後啟用。
    """
    return os.environ.get(STAGE0R_PREFLIGHT_ENV, "0").strip() == "1"


@dataclass(frozen=True)
class ResidualPreflightConfig:
    """Stage-0R preflight 顯式配置（flag + cohort + bounds）。

    所有窗（since/oos_start/data_end）與 selection-bias provenance 皆顯式傳入，
    orchestrator 不自行猜時間軸（PIT 紀律：時間邊界是 caller/operator 的承諾）。
    """

    # 啟用旗標（與 env flag 同時 ON 才跑；cfg 層先 gate 便於測試與 dry-run）。
    enabled: bool = False
    engine_mode: str = "demo"
    # residual 計算的 since（FIFO round-trip / klines 載入起點）。
    since: datetime = field(default_factory=lambda: datetime(1970, 1, 1, tzinfo=timezone.utc))
    # hidden-OOS 窗起點（strict carve-out：exit_ts < oos_start 才進 residual）。
    oos_start: datetime | None = None
    # OOS 窗終點（data_window_end；> oos_start）。
    data_end: datetime | None = None
    # 多因子（btc + market + funding）；orchestrator 預設啟用三因子（Gap B 全開）。
    required_factors: tuple[str, ...] = ("btc", "market", "funding")
    permutation_enabled: bool = True
    permutation_n: int = 2000
    bucket_sec: float = DEFAULT_BUCKET_SEC
    klines_timeframe: str = "4h"
    embargo_buckets: int = 1
    # n_trials 推導輸入（搜尋家族多重性）。
    n_param_variants: int = 1
    n_symbols_screened: int = 1
    n_strategies_screened: int = 1
    # Gap D selection-bias block provenance（V3 §8.3）。
    # embargo_days 是 **V3 §8.3 selection-bias provenance floor**（>=7），與 sealed
    # hidden_oos_state.embargo_seconds（內部 train→eval purge ~0.25d）是兩個獨立概念。
    selection_bias_cv_protocol: str = "walk_forward"
    selection_bias_embargo_days: int = 7
    # 配置指紋（unsigned register；orchestrator 不簽，由受控 register 路徑記錄）。
    strategy_config_sha256: str = "0" * 64
    risk_config_sha256: str = "0" * 64
    half_life_days: float = 7.0
    data_tier: str = "S3"
    # 候選選取上限（一輪最多處理幾個候選；避免一次跑爆）。
    max_candidates: int = 16
    # 數值預閘門檻（預設對齊 DemoApplierConfig 的 live-candidate 門檻）。
    min_net_bps: float = 5.0
    min_confidence: float = 0.65
    min_samples: int = 30
    # market basket 載入 symbol 上限。
    max_basket_symbols: int = _DEFAULT_MAX_BASKET_SYMBOLS


@dataclass(frozen=True)
class CandidatePreflightOutcome:
    """單一候選的 preflight 結果（透明診斷，供 summary / audit）。"""

    rec_id: Any
    strategy: str
    symbol: str
    status: str  # registered | skipped | failed
    reason: str
    net_side: int = 0
    experiment_id: str | None = None
    manifest_hash: str | None = None
    report_hash: str | None = None
    drar_written: bool = False
    rec_stamped: bool = False
    verdict: str | None = None


@dataclass(frozen=True)
class ResidualPreflightSummary:
    """一輪 preflight 的彙總。"""

    enabled: bool
    reason: str
    candidates_selected: int = 0
    registered: int = 0
    skipped: int = 0
    failed: int = 0
    outcomes: tuple[CandidatePreflightOutcome, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "reason": self.reason,
            "candidates_selected": self.candidates_selected,
            "registered": self.registered,
            "skipped": self.skipped,
            "failed": self.failed,
            "outcomes": [
                {
                    "rec_id": str(o.rec_id),
                    "strategy": o.strategy,
                    "symbol": o.symbol,
                    "status": o.status,
                    "reason": o.reason,
                    "net_side": o.net_side,
                    "experiment_id": o.experiment_id,
                    "report_hash": o.report_hash,
                    "drar_written": o.drar_written,
                    "rec_stamped": o.rec_stamped,
                    "verdict": o.verdict,
                }
                for o in self.outcomes
            ],
        }


# 選取「數值預閘達標但缺 lineage」的 demo shadow 候選。
# 為什麼用 NUMERIC pre-gate 而非 should_create_live_candidate：後者第二步會呼
# build_live_candidate_evidence_from_source（=本 orchestrator 要修的 lineage 缺口），
# 必然 False；orchestrator 只要數值達標 + replay_experiment_id IS NULL（缺 lineage）。
_SELECT_CANDIDATES_SQL = """
SELECT id, strategy_name, symbol, expected_net_bps, confidence, sample_count
FROM learning.mlde_shadow_recommendations
WHERE engine_mode = %(engine_mode)s
  AND replay_experiment_id IS NULL
  AND COALESCE(expected_net_bps, 0.0) >= %(min_net_bps)s
  AND COALESCE(confidence, 0.0) >= %(min_confidence)s
  AND COALESCE(sample_count, 0) >= %(min_samples)s
  AND strategy_name IS NOT NULL
  AND symbol IS NOT NULL
ORDER BY confidence DESC, expected_net_bps DESC
LIMIT %(limit)s
"""


def _select_candidates(cur: Any, cfg: ResidualPreflightConfig) -> list[dict[str, Any]]:
    """選取候選 rec（數值預閘 + 缺 lineage）。回 list[dict]。"""
    cur.execute(
        _SELECT_CANDIDATES_SQL,
        {
            "engine_mode": cfg.engine_mode,
            "min_net_bps": cfg.min_net_bps,
            "min_confidence": cfg.min_confidence,
            "min_samples": cfg.min_samples,
            "limit": int(cfg.max_candidates),
        },
    )
    rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
        else:  # tuple cursor fallback（與 SELECT 欄序一致）
            out.append(
                {
                    "id": row[0],
                    "strategy_name": row[1],
                    "symbol": row[2],
                    "expected_net_bps": row[3],
                    "confidence": row[4],
                    "sample_count": row[5],
                }
            )
    return out


def _oos_fraction_from_windows(
    *, since: datetime, oos_start: datetime, data_end: datetime
) -> float | None:
    """OOS 窗佔總跨期的比例（供 Gap D out_of_sample_pct）。

    total_span = [since, data_end]、oos_span = [oos_start, data_end]。回
    oos_span / total_span。非法（total<=0 / oos<=0 / 任一 epoch 缺失）回 None
    （caller fail-closed，不送非法比例去撞 selection_bias_validator）。
    """
    s = to_epoch_seconds(since)
    o = to_epoch_seconds(oos_start)
    e = to_epoch_seconds(data_end)
    if s is None or o is None or e is None:
        return None
    total = e - s
    oos = e - o
    if total <= 0.0 or oos <= 0.0 or oos > total:
        return None
    return oos / total


def _build_selection_bias_block(
    *,
    n_trials: int,
    oos_pct: float,
    cv_protocol: str,
    embargo_days: int,
    backtest_period_days: int,
) -> dict[str, Any]:
    """組 V3 §8.3 selection_bias_correction block（Gap D validator 的輸入）。

    為什麼 embargo_days 與 sealed embargo_seconds 不同：本 block 的 embargo_days 是
    **selection-bias provenance floor**（V3 §8.3 / V041 CHECK >=7 天），描述「家族選擇
    偏差修正用的 embargo」；sealed hidden_oos_state.embargo_seconds 是 residual 計算的
    **內部 train→eval purge**（~0.25d）。兩者是獨立機制，故 block embargo_days 由 cfg
    顯式提供（預設 7），**不**沿用 sealed embargo_seconds（會 <7 撞 EMBARGO_TOO_LOW）。
    """
    return {
        "n_trials_K": int(n_trials),
        "backtest_period_days": int(backtest_period_days),
        "out_of_sample_pct": float(oos_pct),
        "cv_protocol": str(cv_protocol),
        "embargo_days": int(embargo_days),
    }


def _load_multi_factor_inputs(
    conn: Any,
    *,
    symbol: str,
    cfg: ResidualPreflightConfig,
) -> dict[str, Any]:
    """載多因子 DB 來源（market klines_by_symbol + lifecycles + funding）。只讀。

    為什麼 orchestrator 負責載入（非 bridge）：bridge 只載 BTC klines（btc 因子）；
    market basket（klines_by_symbol + lifecycles）與 funding（funding_by_symbol）是
    Gap A orchestrator 的責任（PA §2 Gap B point 1 / cycle docstring）。窗用 cfg.since
    ~ cfg.oos_start（OOS 區資料不載，PIT-clean，與 bridge 的 < oos_start clamp 一致）。
    """
    required = tuple(cfg.required_factors)
    start_dt = cfg.since
    # 載入終點夾到 oos_start（OOS 區 factor bar 不載；bridge 還會再做桶級過濾）。
    end_dt = cfg.oos_start if cfg.oos_start is not None else cfg.data_end

    inputs: dict[str, Any] = {
        "klines_by_symbol": None,
        "lifecycles": None,
        "funding_by_symbol": None,
        "position_symbols": [symbol],
    }
    if "market" in required:
        lifecycles = load_symbol_lifecycles(conn)
        # basket 選取（Gap A bug 修）：先取整窗 [since, oos_start] 的 PIT-active universe
        # （含已下市但當時在交易者，排 survivorship），再交給 load_liquid_basket_symbols
        # 按窗內 4h-bar 計數（流動性代理）排序取前 max_basket_symbols。
        #
        # 為什麼不再用 sorted(set(active))[:N]（舊 bug）：字母序前 N 在真實資料上命中
        # 0GUSDT / 1000000BABYDOGEUSDT 等冷門 symbol，窗內 market.klines 4h bar 數=0 →
        # bucketed_multi_factor 的 market basket 每桶成員 < min_basket_symbols → factor
        # panel 空 → evaluate_cell 回 no_aligned_buckets → btc/market(/funding) 多因子閘
        # 在真實資料上永不計算。改按資料可得性選取即可保證 basket 都有 bar。
        #
        # PIT 性質保留：load_liquid_basket_symbols 用 symbol = ANY(active) 把選取域夾在
        # PIT-active 集內（lifecycle 權威），故「當時在交易、今已下市」者仍可入選；
        # 「今日才上市」者因不在 active 集而被排除。s/e epoch 缺失（理論上不該，窗已驗）
        # → 退回全 lifecycle keys 當候選域，仍交給 liquidity 查詢過濾掉無資料者。
        s_epoch = to_epoch_seconds(start_dt)
        e_epoch = to_epoch_seconds(end_dt)
        if s_epoch is not None and e_epoch is not None:
            active = pit_active_symbols(lifecycles, s_epoch, e_epoch)
        else:
            active = sorted(lifecycles.keys())
        basket = load_liquid_basket_symbols(
            conn,
            active,
            start_ts=start_dt,
            end_ts=end_dt if end_dt is not None else start_dt,
            timeframe=cfg.klines_timeframe,
            limit=int(cfg.max_basket_symbols),
        )
        klines = load_klines_by_symbols(
            conn,
            basket,
            start_ts=start_dt,
            end_ts=end_dt if end_dt is not None else start_dt,
            timeframe=cfg.klines_timeframe,
        )
        inputs["klines_by_symbol"] = klines
        inputs["lifecycles"] = lifecycles
    if "funding" in required:
        funding = load_funding_rates(
            conn,
            [symbol],
            start_ts=start_dt,
            end_ts=end_dt if end_dt is not None else start_dt,
        )
        inputs["funding_by_symbol"] = funding
    return inputs


def _process_candidate(
    conn: Any,
    write_cur: Any,
    rec: dict[str, Any],
    *,
    cfg: ResidualPreflightConfig,
    get_pg_conn_fn: Callable,
    actor: Any,
    register_fn: Callable,
) -> CandidatePreflightOutcome:
    """對單一候選跑六步流程。任一前置失敗 fail-closed（不註冊/不寫 drar/不蓋章）。"""
    rec_id = rec.get("id")
    strategy = str(rec.get("strategy_name") or "").strip()
    symbol = str(rec.get("symbol") or "").strip()

    def _skip(reason: str, **kw: Any) -> CandidatePreflightOutcome:
        return CandidatePreflightOutcome(
            rec_id=rec_id, strategy=strategy, symbol=symbol,
            status="skipped", reason=reason, **kw,
        )

    if not strategy or not symbol:
        return _skip("missing_strategy_or_symbol")
    if cfg.oos_start is None or cfg.data_end is None:
        return _skip("oos_window_not_configured")

    # ② 從真實 fills 推導 net_side（MIT 硬條件：絕不把 +1 預設送進真實 run）。
    #    HIGH-2：必須逐 (strategy, symbol)——候選身分是 strategy::symbol、funding factor
    #    也是該 symbol 的 funding_rate；跨 symbol 聚合可能與真實 per-symbol 曝險反號。
    net_side, net_diag = load_candidate_net_side(
        conn, strategy, symbol=symbol, engine_mode=cfg.engine_mode, since=cfg.since
    )
    if net_diag.get("ambiguous", 0.0) >= 1.0:
        # 淨方向不可判（無入場成交 / 淨 0）→ funding sign 無法確定 → fail-closed。
        return _skip("net_side_ambiguous", net_side=net_side)

    # ③（Gap D）預先註冊 selection-bias 斷言（K>=10 / oos_pct>=0.20 / cv_protocol /
    #    embargo）。失敗 fail-closed（在任何寫入之前）。
    n_trials, _deriv = derive_n_trials(
        cfg.n_param_variants, cfg.n_symbols_screened, cfg.n_strategies_screened
    )
    oos_pct = _oos_fraction_from_windows(
        since=cfg.since, oos_start=cfg.oos_start, data_end=cfg.data_end
    )
    if oos_pct is None:
        return _skip("oos_fraction_invalid", net_side=net_side)
    # backtest_period_days：總跨期天數（用於 V3 §8.3 backtest_period_days>0）。
    s_epoch = to_epoch_seconds(cfg.since)
    e_epoch = to_epoch_seconds(cfg.data_end)
    backtest_days = int(max(1, round(((e_epoch or 0.0) - (s_epoch or 0.0)) / 86400.0)))
    sb_block = _build_selection_bias_block(
        n_trials=n_trials,
        oos_pct=oos_pct,
        cv_protocol=cfg.selection_bias_cv_protocol,
        embargo_days=cfg.selection_bias_embargo_days,
        backtest_period_days=backtest_days,
    )
    sb_result = validate_selection_bias_correction(
        {"selection_bias_correction": sb_block}
    )
    if not sb_result.ok:
        mode = sb_result.fail_mode.value if sb_result.fail_mode else "unknown"
        return _skip(f"selection_bias_invalid:{mode}", net_side=net_side)

    # ① + ④ 多因子 residual（PBO 誠實 defer：candidate_oos_returns=None，**不**合成 peer）
    #    + permutation 啟用 + 註冊 replay experiment（重用 bridge，唯一寫入經 register_fn）。
    mf = _load_multi_factor_inputs(conn, symbol=symbol, cfg=cfg)
    family_id = f"{strategy}::{symbol}"

    # ★ §5.6 hash byte-identity 關鍵：drar 必須 hash **bridge 算出並送進 registry 的
    #   同一份 report dict**，否則三寫者 hash 不一致 → source_contract 跨檢失敗。bridge
    #   把 report 放進 ``body.manifest_jsonb[demo_residual_alpha_report]`` 後交給
    #   register_fn；故用一個 capturing wrapper 從 **body** 抓那份 report（=registry
    #   hash 的 exact 物件），不由 orchestrator 重算（重算會引入第二份序列化路徑→漂移）。
    captured: dict[str, Any] = {}

    def _capturing_register_fn(get_conn_fn: Any, act: Any, body: Any, **kw: Any) -> Any:
        manifest = getattr(body, "manifest_jsonb", None) or {}
        rpt = manifest.get(_RESIDUAL_ALPHA_REPORT_FIELD)
        if isinstance(rpt, dict):
            captured["report"] = rpt
        # LOW-3：設 deterministic idempotency_key 縮小 crash-retry 重複窗。
        # 為什麼從 family_id + split_hash 衍生：同一候選（replay_experiment_id IS NULL）
        # 重跑 → 同窗 → 同 split_hash → 同 key。register_experiment 用 (actor, key) 的
        # in-memory cache + PG advisory lock + H-2 hash guard：同 process 內重送直接回
        # 既有 experiment（不重 INSERT），跨 process race 由 advisory lock 序列化。
        # **誠實殘留風險**：in-memory cache 重啟即失（registry module note），且 cache-miss
        # 競態下 registry 明確接受跨-process 重複 INSERT（H-1 取捨）；故「register 已 commit
        # 但 process 在 stamp 前崩潰、重啟後重跑」仍可能產生第二個 replay.experiments row。
        # 此 key 把重複窗從「任意 retry」縮到「僅 crash-then-restart」，是 cheap strict-
        # better；完全消除需 durable idempotency 欄（V049 無，OUT OF Gap A scope）。
        if getattr(body, "idempotency_key", None) is None:
            split_ref = ""
            state = manifest.get("hidden_oos_state")
            if isinstance(state, dict):
                split_ref = str(state.get("split_hash") or "")
            if split_ref:
                key = f"residual_stage0r:{family_id}:{split_ref}"
                try:
                    body.idempotency_key = key[:128]
                except (AttributeError, ValueError):  # 非預期不可變 body → 不阻斷 register
                    logger.warning(
                        "residual_stage0r_preflight: could not set idempotency_key on body"
                    )
        return register_fn(get_conn_fn, act, body, **kw)

    result, err = register_residual_candidate_experiment(
        conn,
        strategy=strategy,
        symbol=symbol,
        timeframe=cfg.klines_timeframe,
        family_id=family_id,
        since=cfg.since,
        oos_start=cfg.oos_start,
        data_end=cfg.data_end,
        n_param_variants=cfg.n_param_variants,
        n_symbols_screened=cfg.n_symbols_screened,
        n_strategies_screened=cfg.n_strategies_screened,
        actor=actor,
        strategy_config_sha256=cfg.strategy_config_sha256,
        risk_config_sha256=cfg.risk_config_sha256,
        get_pg_conn_fn=get_pg_conn_fn,
        data_tier=cfg.data_tier,
        embargo_buckets=cfg.embargo_buckets,
        bucket_sec=cfg.bucket_sec,
        klines_timeframe=cfg.klines_timeframe,
        half_life_days=cfg.half_life_days,
        engine_mode=cfg.engine_mode,
        register_fn=_capturing_register_fn,
        # ★ NO peer synthesis：單一配置 → peer_variant_round_trips=None → evaluate_cell
        #   單配置 defer（gate 因無 PBO peer 已 fail-closed defer_data）。永不捏造 peer。
        peer_variant_round_trips=None,
        # 多因子 + permutation（透過 bridge **gate_kwargs → evaluate_cell）。
        required_factors=tuple(cfg.required_factors),
        permutation_enabled=cfg.permutation_enabled,
        permutation_n=cfg.permutation_n,
        net_side=net_side,
        position_symbols=mf["position_symbols"],
        funding_by_symbol=mf["funding_by_symbol"],
        klines_by_symbol=mf["klines_by_symbol"],
        lifecycles=mf["lifecycles"],
    )
    if err is not None or not isinstance(result, dict):
        # disabled / no_round_trips / leak-guard fail / register err → 誠實 skip 或 fail。
        # disabled 與資料不足是 skip（非錯誤）；register/PG 錯誤是 failed。
        reason = str(err or "register_returned_no_result")
        is_failure = reason.startswith("pg_") or reason.startswith("register_") or (
            ":" in reason and reason.split(":", 1)[0] in {"manifest", "idempotency"}
        )
        outcome_status = "failed" if is_failure else "skipped"
        return CandidatePreflightOutcome(
            rec_id=rec_id, strategy=strategy, symbol=symbol,
            status=outcome_status, reason=reason, net_side=net_side,
        )

    experiment_id = str(result.get("experiment_id") or "")
    manifest_hash = str(result.get("manifest_hash") or "")
    if not experiment_id or not manifest_hash:
        return CandidatePreflightOutcome(
            rec_id=rec_id, strategy=strategy, symbol=symbol,
            status="failed", reason="register_missing_ids", net_side=net_side,
        )

    # 取 bridge 送進 registry 的同一份 report（capturing wrapper 從 body 抓到）→
    # hash byte-identical（§5.6）。bridge 必定有產 report 才會走到 register；理論上
    # captured 必有，但保守 fallback：缺則不蓋章（無 report 的 lineage 對下游 source
    # contract 無意義——它第一道就讀 payload report，缺則死在 not_dict）。
    report = captured.get("report") if isinstance(captured.get("report"), dict) else None
    if report is None:
        # register 已寫但 capturing 缺 report（不該發生）→ 不蓋 lineage、不寫 payload。
        # 不重算 report（重算=第二序列化路徑→hash 漂移）。reason=register_ok_but_report_
        # uncaptured 供 audit；experiment 仍存在（bridge 已 commit），下次重跑 WHERE NULL
        # 仍會選到（此時 idempotency_key 縮小重複窗，見 LOW-3）。
        return CandidatePreflightOutcome(
            rec_id=rec_id, strategy=strategy, symbol=symbol,
            status="skipped", reason="register_ok_but_report_uncaptured",
            net_side=net_side, experiment_id=experiment_id,
            manifest_hash=manifest_hash,
        )

    verdict = str(report.get("verdict") or "")
    # ⑤ 寫 drar（重用薄 writer；非 pass 報告誠實 skip → 回 None）。
    report_hash = write_demo_residual_alpha_report(
        write_cur,
        report,
        strategy_name=strategy,
        engine_mode=cfg.engine_mode,
        source=PREFLIGHT_SOURCE,
    )
    drar_written = report_hash is not None

    # ⑥ 蓋 lineage **並**把同一份 report 寫進 payload（HIGH-1）。pass 與 defer report
    #    皆寫 payload：defer report 經下游 source contract 第一道 validator 自然 surface
    #    真實 math reason（如 passes_not_true / verdict_not_pass），**非** not_dict
    #    （=defer-by-absence）。WHERE replay_experiment_id IS NULL 防重蓋/重開。
    rec_stamped = _stamp_rec_lineage(
        write_cur,
        rec_id=rec_id,
        experiment_id=experiment_id,
        manifest_hash=manifest_hash,
        report=report,
    )

    return CandidatePreflightOutcome(
        rec_id=rec_id, strategy=strategy, symbol=symbol,
        status="registered",
        reason="ok",
        net_side=net_side,
        experiment_id=experiment_id,
        manifest_hash=manifest_hash,
        report_hash=report_hash,
        drar_written=drar_written,
        rec_stamped=rec_stamped,
        verdict=verdict,
    )


# 蓋 lineage **並**把 bridge 產的 report 寫進 payload（HIGH-1 修復）。
# 為什麼 payload 必須帶 report：下游 source contract（candidate_evidence_source_contract.
# build_live_candidate_evidence_from_source）**第一道**就讀 ``payload.
# demo_residual_alpha_report`` 並過 validate_demo_residual_alpha_report；production
# fetch（mlde_demo_applier_evidence_filter.fetch_pending_sql_and_params）的 SELECT
# **沒有** top-level demo_residual_alpha_report 欄，report 只能從 payload 取。若只蓋
# lineage 不寫 payload，source contract 必死在 ``residual_alpha:not_dict``（=defer-by-
# absence 換個名字）——即使 pass 候選也卡在第一道，durable gate 永不可達。
# 同一 UPDATE 用 jsonb_set 寫入：原子（lineage + report 同進同出），且**覆寫**任何先前
# attach_residual_reports hook 留下的 btc-only report → payload report == manifest
# 內 multi-factor report → registry-hash 跨檢一致（§5.6 byte-identity）。
# WHERE replay_experiment_id IS NULL：idempotent，已蓋過則整筆 no-op（不重寫 payload）。
_STAMP_REC_SQL = """
UPDATE learning.mlde_shadow_recommendations
SET replay_experiment_id = %(experiment_id)s::uuid,
    manifest_hash = %(manifest_hash)s,
    evidence_source_tier = %(tier)s,
    payload = jsonb_set(
        COALESCE(payload, '{}'::jsonb),
        '{demo_residual_alpha_report}',
        %(report_jsonb)s::jsonb
    )
WHERE id = %(rec_id)s
  AND replay_experiment_id IS NULL
"""


def _stamp_rec_lineage(
    cur: Any,
    *,
    rec_id: Any,
    experiment_id: str,
    manifest_hash: str,
    report: dict[str, Any],
) -> bool:
    """蓋 lineage + 寫 payload report 到 shadow rec；WHERE replay_experiment_id IS NULL
    防 re-stamp/re-open。

    manifest_hash 來自 registry 已 commit 的值（單一真相來源）。report 是 bridge 送進
    registry 的**同一份** dict（capturing wrapper 抓到），故 payload 內的 report ==
    manifest 內的 report → 下游 source contract 的 registry-hash 跨檢必一致（§5.6）。
    序列化用 ``json.dumps(report, sort_keys=True)``：與 drar writer 的 report_jsonb 同
    convention，且 jsonb 是結構（非位元組）儲存，round-trip 回 dict 後 ``_canonical_sha256``
    與 manifest 的 hash 結構一致（pass/defer 皆寫，defer 報告經第一道 validator 自然
    surface 真實 math reason，非 not_dict）。idempotent：已蓋過（replay_experiment_id
    NOT NULL）→ rowcount=0，回 False（no-op，不覆蓋既有 lineage/payload）。
    """
    cur.execute(
        _STAMP_REC_SQL,
        {
            "experiment_id": experiment_id,
            "manifest_hash": manifest_hash,
            "tier": CALIBRATED_REPLAY_TIER,
            "report_jsonb": json.dumps(report, sort_keys=True),
            "rec_id": rec_id,
        },
    )
    rowcount = getattr(cur, "rowcount", 0)
    return bool(rowcount and rowcount > 0)


def run_residual_stage0r_preflight(
    dsn: str | None,
    *,
    cfg: ResidualPreflightConfig,
    get_pg_conn_fn: Callable,
    actor: Any,
    conn_factory: Callable[[str | None], Any] | None = None,
    register_fn: Callable = run_register_in_pg_xact,
) -> ResidualPreflightSummary:
    """Stage-0R replay preflight orchestrator 入口（只由 gated cron / CLI 呼叫）。

    三重 flag gate（fail-closed）：cfg.enabled AND ``stage0r_preflight_enabled()``
    AND ``residual_producer_enabled()``（bridge 內部也會再 check 後者）。任一未開 →
    立即回 enabled=False summary，**零寫入**、零候選查詢。

    流程：開讀連線（conn_factory）→ 選候選（數值預閘 + 缺 lineage）→ 對每個候選跑
    六步（net_side / Gap D / register / drar / stamp）→ 每候選成功後 commit 寫入 →
    回彙總。register 用其自有 get_pg_conn_fn xact（bridge 持有）；orchestrator 的
    drar + stamp 在 conn 的 cursor 上、每候選後 commit（與 register xact 分離）。
    """
    # 1) 三重 flag gate（任一 OFF → 零寫入早退）。
    if not cfg.enabled:
        return ResidualPreflightSummary(enabled=False, reason="cfg_disabled")
    if not stage0r_preflight_enabled():
        return ResidualPreflightSummary(
            enabled=False, reason=f"flag_off:{STAGE0R_PREFLIGHT_ENV}"
        )
    if not residual_producer_enabled():
        return ResidualPreflightSummary(
            enabled=False, reason=f"flag_off:{RESIDUAL_PRODUCER_ENV}"
        )
    if cfg.oos_start is None or cfg.data_end is None:
        return ResidualPreflightSummary(
            enabled=True, reason="oos_window_not_configured"
        )

    factory = conn_factory or _default_conn_factory
    conn = factory(dsn)
    if conn is None:
        return ResidualPreflightSummary(enabled=True, reason="pg_unavailable")

    outcomes: list[CandidatePreflightOutcome] = []
    try:
        with conn.cursor() as sel_cur:
            candidates = _select_candidates(sel_cur, cfg)
        if not candidates:
            return ResidualPreflightSummary(
                enabled=True, reason="no_candidates", candidates_selected=0
            )
        for rec in candidates:
            with conn.cursor() as write_cur:
                outcome = _process_candidate(
                    conn,
                    write_cur,
                    rec,
                    cfg=cfg,
                    get_pg_conn_fn=get_pg_conn_fn,
                    actor=actor,
                    register_fn=register_fn,
                )
                # 只有真寫了 drar 或蓋了章才 commit；純 skip（無寫入）也 commit 無害
                # （write_cur 無 pending 寫入）。register 的兩個 INSERT 由 bridge 的
                # get_pg_conn_fn xact 自己 commit，與此 cursor 無關。
                if outcome.status == "failed":
                    _safe_rollback(conn)
                else:
                    _safe_commit(conn)
            outcomes.append(outcome)
    finally:
        _safe_close(conn)

    registered = sum(1 for o in outcomes if o.status == "registered")
    skipped = sum(1 for o in outcomes if o.status == "skipped")
    failed = sum(1 for o in outcomes if o.status == "failed")
    return ResidualPreflightSummary(
        enabled=True,
        reason="ran",
        candidates_selected=len(outcomes),
        registered=registered,
        skipped=skipped,
        failed=failed,
        outcomes=tuple(outcomes),
    )


def _default_conn_factory(dsn: str | None) -> Any:
    """預設讀連線工廠（psycopg2）。lazy import 讓 Mac pure-core 測試免依賴。"""
    if not dsn:
        return None
    try:
        import psycopg2  # type: ignore
    except ImportError:  # pragma: no cover
        return None
    return psycopg2.connect(dsn)


def _safe_commit(conn: Any) -> None:
    try:
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — commit 失敗記錄不中斷整輪
        logger.warning("residual_stage0r_preflight commit failed: %s", exc)


def _safe_rollback(conn: Any) -> None:
    try:
        conn.rollback()
    except Exception as exc:  # noqa: BLE001
        logger.warning("residual_stage0r_preflight rollback failed: %s", exc)


def _safe_close(conn: Any) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001 — close 失敗忽略（連線本就要丟棄）
        pass


__all__ = [
    "STAGE0R_PREFLIGHT_ENV",
    "PREFLIGHT_SOURCE",
    "CALIBRATED_REPLAY_TIER",
    "stage0r_preflight_enabled",
    "ResidualPreflightConfig",
    "CandidatePreflightOutcome",
    "ResidualPreflightSummary",
    "run_residual_stage0r_preflight",
]
