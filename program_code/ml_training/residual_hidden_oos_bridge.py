"""
MODULE_NOTE
模塊用途：Residual alpha PART 2 接線 primitive。把一個 residual-candidate cell
（strategy::symbol）的 demo round-trip → **leak-free 三窗 carve-out** → 非 OOS
residual report → sealed hidden_oos_state → replay-experiment 註冊（V049
``replay.experiments`` + ``learning.hidden_oos_state_registry`` 兩張 durable 表）。
補上 cycle/sealer 已建好 schema/validator 但缺「把 sealed-state 真正註冊進 replay
registry」的接線缺口（FACT 3 sealer flat-key + FACT 5 OOS 第三窗 carve-out）。
主要函數：
  - ``partition_round_trips_by_oos``（純函數，leak carve-out 的唯一切點）。
  - ``register_residual_candidate_experiment``（producer primitive，唯一寫入經
    注入的 register_fn）。
依賴：residual_alpha_cycle（env-flag + evaluate_cell）、residual_alpha_producer_db
  （bucket/factor/DB 載入，重用不重造）、candidate_hidden_oos_sealer（封存）、
  experiment_registry（ReplayExperimentRegisterRequest / run_register_in_pg_xact /
  REGISTRY_RESIDUAL_ALPHA_HASH_FIELD）；標準庫。
硬邊界：
  - **只讀** round_trips/klines；唯一寫入 = 注入的 register_fn（受控 register
    路徑 Operator+replay:write）；不碰 runtime / order / risk / auth / lease。
  - **env-flag 預設 OFF**（``residual_producer_enabled()``）：OFF 立即
    ``(None, "disabled")`` 零寫入（fail-closed，部署預設不改現役行為）。
  - **leak-free**（三道，MED-2 後精確化）：①exit_ts 落在 OOS 窗（>= oos_start，
    嚴格 ``exit_ts < oos_start`` 才算非 OOS）的 round-trip 整筆排除，永不進
    residual 計算；②BTC klines 載入終點夾到 ``min(max_exit+pad, oos_start)``，
    **strictly < oos_start**（非僅 max_exit；否則 4h pad 會在 oos_start 非桶對齊時
    把 ts>=oos_start 的 bar 載進邊界桶的 factor）；③只保留**完全在 OOS 之前結束**
    的桶 ``b + bucket_sec <= oos_start``（半開區間 [b,b+bucket_sec) 不得跨進 OOS）
    → train/eval 切分與三窗只由完全非 OOS 的桶衍生。
  - **三窗由 bucket 邊界 epoch→ISO datetime 衍生**，**不**用 report 的 fit_window
    字串（那是 float-string，experiment_registry `_parse_manifest_datetime` 回
    None）；三窗嚴格遞增以滿足 V132 windows_chk。
  - ``embargo_seconds`` 公式與 evaluate_cell 的 embargo_gap **完全一致**
    （``(eb+0.5)*bs if eb>0 else 0``）；封存的 embargo 即 residual 計算實際 purge
    的秒數，不誤述。eb=0 ⇒ 0 ⇒ ``>= 1`` fail-closed（V132 ``embargo_seconds>0``
    STRICT；永不送 0 去撞 CHECK rollback）。
  - **不引入生產 caller**（無 route、無 cycle auto-fire）：PART 2 只交付 primitive
    + 測；caller 由後續 PART（deploy）接。
  - residual hash 用 ``canonical_sha256``（sort_keys/separators/ensure_ascii=True），
    與 source_contract / drar writer byte-identical（gate 比對需一致）。
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

try:  # 套件式 import（app runtime）
    from program_code.ml_training.residual_alpha_cycle import (
        evaluate_cell,
        residual_producer_enabled,
    )
    from program_code.ml_training.residual_alpha_producer_db import (
        DEFAULT_BUCKET_SEC,
        bucket_round_trips_by_exit,
        bucketed_btc_factor,
        load_btc_klines,
        load_round_trips,
        to_epoch_seconds,
    )
    from program_code.ml_training.candidate_hidden_oos_sealer import build_hidden_oos_state
    from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.experiment_registry import (  # noqa: E501
        REGISTRY_RESIDUAL_ALPHA_HASH_FIELD,
        ReplayExperimentRegisterRequest,
        run_register_in_pg_xact,
    )
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from ml_training.residual_alpha_cycle import (  # type: ignore
        evaluate_cell,
        residual_producer_enabled,
    )
    from ml_training.residual_alpha_producer_db import (  # type: ignore
        DEFAULT_BUCKET_SEC,
        bucket_round_trips_by_exit,
        bucketed_btc_factor,
        load_btc_klines,
        load_round_trips,
        to_epoch_seconds,
    )
    from ml_training.candidate_hidden_oos_sealer import build_hidden_oos_state  # type: ignore
    from exchange_connectors.bybit_connector.control_api_v1.replay.experiment_registry import (  # type: ignore  # noqa: E501
        REGISTRY_RESIDUAL_ALPHA_HASH_FIELD,
        ReplayExperimentRegisterRequest,
        run_register_in_pg_xact,
    )


# residual report body 帶上 manifest 的 key（payload-lane；與 cycle 同名）。
RESIDUAL_ALPHA_REPORT_FIELD = "demo_residual_alpha_report"


def _canonical_sha256(value: Any) -> str:
    """canonical sha256（hex64）。

    為什麼算法必須完全對齊：source_contract `_canonical_sha256` 與 durable
    residual writer 都用 ``sort_keys=True / separators=(",",":") / ensure_ascii
    =True``；residual-hash gate 比對 ``registry_hash == canonical_sha256(report)``，
    任何序列化差異都會讓 gate 誤判 mismatch。
    """
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _epoch_to_iso(epoch_sec: float) -> str:
    """epoch 秒 → ISO-8601 UTC datetime 字串（experiment_registry 可 parse）。

    experiment_registry `_parse_manifest_datetime` 用 ``datetime.fromisoformat``，
    故必須給標準 ISO（帶 +00:00）。round-trip 透過 `datetime.fromtimestamp(..., UTC)`
    保整秒邊界穩定。
    """
    return datetime.fromtimestamp(float(epoch_sec), tz=timezone.utc).isoformat()


def partition_round_trips_by_oos(
    round_trips: Sequence[Mapping[str, Any]],
    oos_start_epoch: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把 round-trip 按 OOS 窗起點切成 ``(non_oos, oos)``。

    這是 leak carve-out 的**唯一**切點（PART 2 §4 最高風險）。嚴格判據
    ``exit_ts < oos_start_epoch`` 才歸 non_oos；exit==oos_start 歸 oos（與
    ``bucket_floor`` 半開區間語意一致：報酬已實現於 exit，exit<oos_start 保證
    該報酬在 OOS 窗開始前已完全實現 → 無前視）。只有 ``non_oos`` 會進 residual
    計算。exit_ts 缺失/非法者歸 oos（保守排除，不讓污染進 non_oos）。
    """
    non_oos: list[dict[str, Any]] = []
    oos: list[dict[str, Any]] = []
    for rt in round_trips:
        exit_ = to_epoch_seconds(rt.get("exit_ts"))
        if exit_ is not None and exit_ < oos_start_epoch:
            non_oos.append(dict(rt))
        else:
            oos.append(dict(rt))
    return non_oos, oos


def register_residual_candidate_experiment(
    conn: Any,
    *,
    strategy: str,
    symbol: str,
    timeframe: str,
    family_id: str,
    since: datetime,
    oos_start: datetime,
    data_end: datetime,
    n_param_variants: int,
    n_symbols_screened: int,
    n_strategies_screened: int,
    actor: Any,
    strategy_config_sha256: str,
    risk_config_sha256: str,
    get_pg_conn_fn: Any,
    data_tier: str = "S3",
    embargo_buckets: int = 1,
    bucket_sec: float = DEFAULT_BUCKET_SEC,
    klines_timeframe: str = "4h",
    klines_pad_sec: float = DEFAULT_BUCKET_SEC,
    half_life_days: float = 7.0,
    engine_mode: str = "demo",
    register_fn: Any = run_register_in_pg_xact,
    manifest_signer_module: Any = None,
    peer_variant_round_trips: Sequence[Sequence[Mapping[str, Any]]] | None = None,
    **gate_kwargs: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """把一個 residual-candidate cell 算 + 封存 + 註冊成 replay experiment。

    流程（PART 2 §3.3）：env-flag gate → 載 round_trips（只讀）→ OOS carve-out
    （唯一切點）→ 載 BTC klines（範圍夾止 < oos_start）→ ``evaluate_cell`` 算
    residual（只在 non-OOS）→ bucket 邊界衍生三窗 ISO datetime → embargo 對賬
    → ``build_hidden_oos_state`` 封存 → 組 ``manifest_jsonb`` → 組
    ``ReplayExperimentRegisterRequest``（unsigned）→ 呼注入的 ``register_fn``
    （唯一寫入）。回 ``register_fn`` 的 ``(result, err)``。

    任一前置失敗（flag OFF / 無非 OOS trip / 對齊不足 / embargo<=0 / 三窗非遞增）
    一律 fail-closed 回 ``(None, err)``，**不**送非法資料去撞 V132 CHECK。
    """
    # 1) env-flag：預設 OFF → 零寫入。
    if not residual_producer_enabled():
        return None, "disabled"

    # 2) 載 round_trips（只讀）。
    rts_all = load_round_trips(conn, strategy, engine_mode=engine_mode, since=since)
    if not rts_all:
        return None, "no_round_trips"

    # 3) ★ LEAK carve-out（唯一切點）：只有非 OOS round-trip 進 residual。
    oos_start_epoch = to_epoch_seconds(oos_start)
    if oos_start_epoch is None:
        return None, "oos_start_invalid"
    rts_non_oos, _rts_oos = partition_round_trips_by_oos(rts_all, oos_start_epoch)
    if not rts_non_oos:
        return None, "no_non_oos_round_trips"

    # 3b) embargo（純 input 檢查，提前到 klines/windowing 之前 fail-fast）。
    #     MED-3：公式必須與 evaluate_cell 的 embargo_gap **完全一致**——
    #     ``(eb+0.5)*bs if eb>0 else 0.0``。eb=0 時 evaluate_cell purge 0 秒，
    #     若 bridge 卻封存 (0+0.5)*4h=7200s 會讓 sealed embargo 與 residual 計算
    #     實際用的 purge 不符（誤述）。對齊後 eb=0 → embargo_seconds=0 →
    #     下面 ``>= 1`` fail-closed 自然拒絕（一致：eb=0 ⇒ 0 ⇒ fail-closed，
    #     永不撞 V132 embargo_seconds>0 CHECK）。embargo 只依賴 embargo_buckets/
    #     bucket_sec，與 round-trip/factor 無關，故當前置 input 驗證最穩健（PA §3.5/
    #     trap #3：此處比 §3.3 step-7 提前是等價且不被資料不足遮蔽的 fail-fast）。
    embargo_seconds = (
        int(round((embargo_buckets + 0.5) * bucket_sec)) if embargo_buckets > 0 else 0
    )
    if embargo_seconds < 1:
        return None, "embargo_seconds_non_positive"
    embargo_days = embargo_seconds / 86400.0
    # round-trip 對賬：experiment_registry `_extract` 要
    # ``embargo_seconds == int(round(embargo_days*86400))``；夾死 float 抖動。
    if int(round(embargo_days * 86400)) != embargo_seconds:
        return None, "embargo_days_round_trip_mismatch"

    # 4) 載 BTC klines：範圍夾止在非 OOS round-trip 的 [min_entry, max_exit]。
    #    為什麼 end 必須 strictly < oos_start（MED-2 修復）：max_exit<oos_start，但
    #    +klines_pad_sec（4h）會把載入終點推過 oos_start，當 oos_start 非 4h 桶
    #    對齊時，bucketed_btc_factor 對邊界桶 bucket_floor(oos_start) 會用到
    #    ts>=oos_start 的 bar → 二階前視洩漏。故 end 夾到 oos_start_epoch 之下，
    #    連 OOS 區的 factor bar 都不載入（PIT-clean）。
    min_entry = min(rt["entry_ts"] for rt in rts_non_oos)
    max_exit = max(rt["exit_ts"] for rt in rts_non_oos)
    end_epoch = min(max_exit + klines_pad_sec, oos_start_epoch)
    start_dt = datetime.fromtimestamp(min_entry - klines_pad_sec, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_epoch, tz=timezone.utc)
    btc_klines = load_btc_klines(
        conn, start_ts=start_dt, end_ts=end_dt, timeframe=klines_timeframe
    )

    # 5) 算 residual（只在 non-OOS）。
    cell_key = f"{strategy}::{symbol}"
    result = evaluate_cell(
        cell_key,
        rts_non_oos,
        btc_klines,
        n_param_variants=n_param_variants,
        n_symbols_screened=n_symbols_screened,
        n_strategies_screened=n_strategies_screened,
        peer_variant_round_trips=peer_variant_round_trips,
        bucket_sec=bucket_sec,
        embargo_buckets=embargo_buckets,
        **gate_kwargs,
    )
    report = result.report
    if not isinstance(report, dict):
        return None, f"no_residual_report:{result.reason}"

    # 6) 衍生三窗 ISO datetime（由 bucket 邊界 epoch→ISO；不用 report.fit_window
    #    字串——那是 float-string，experiment_registry parse 回 None）。
    #    train/eval 切分規則與 producer _build_fit_window 完全一致
    #    （train_fraction 0.7：n_train = max(1, min(floor(0.7*n), n-1))）。
    buckets, _counts = bucket_round_trips_by_exit(rts_non_oos, bucket_sec)
    factor = bucketed_btc_factor(btc_klines, bucket_sec)
    aligned = sorted(set(buckets) & set(factor))
    # MED-2：只接受**完全在 OOS 之前**結束的桶。桶 b 覆蓋半開區間
    # [b, b+bucket_sec)；b+bucket_sec>oos_start_epoch 代表該桶尾端跨進 OOS 區，
    # 其 factor/報酬可能含 ts>=oos_start 的 bar → 排除（PIT-clean）。如此 train/
    # eval 切分與三窗只由完全非 OOS 的桶衍生；過濾後若清空則 fail-closed。
    aligned = [b for b in aligned if b + bucket_sec <= oos_start_epoch]
    if len(aligned) < 2:
        return None, "insufficient_aligned_buckets"
    n_aligned = len(aligned)
    n_train = max(1, min(int(math.floor(0.7 * n_aligned)), n_aligned - 1))
    train_buckets = aligned[:n_train]
    eval_buckets = aligned[n_train:]
    if not train_buckets or not eval_buckets:
        return None, "empty_train_or_eval_bucket"

    # +bucket_sec：bucket_ts 是桶起點，end 取最後一桶的「結束」邊界，保 start<end。
    calibration_window = (
        _epoch_to_iso(train_buckets[0]),
        _epoch_to_iso(train_buckets[-1] + bucket_sec),
    )
    candidate_window = (
        _epoch_to_iso(eval_buckets[0]),
        _epoch_to_iso(eval_buckets[-1] + bucket_sec),
    )
    oos_window = (_epoch_to_iso(oos_start_epoch), _to_iso_dt(data_end))
    if oos_window[1] is None:
        return None, "data_end_invalid"

    # 三窗嚴格遞增（V132 windows_chk）：calib_end<=eval_start by split；
    # eval_end<=oos_start（MED-2 桶過濾保證 eval_buckets[-1]+bucket_sec<=oos_start）。
    # 逐窗 + 跨窗驗。
    if not _windows_strictly_increasing(
        calibration_window, candidate_window, oos_window
    ):
        return None, "windows_not_strictly_increasing"

    # 7) residual hash（與 source_contract / drar writer byte-identical）。
    #    embargo_seconds / embargo_days 已於 step-3b 算妥並驗過對賬。
    residual_hash = _canonical_sha256(report)

    # 8) 封存 sealed hidden_oos_state（同一 object 同時進 manifest 與 durable，
    #    source_contract durable gate 比對兩者 canonical sha256 須相等）。
    state = build_hidden_oos_state(
        family_id=family_id,
        calibration_window=calibration_window,
        candidate_window=candidate_window,
        oos_window=oos_window,
        embargo_seconds=embargo_seconds,
        total_candidates_k=int(result.n_trials),
        residual_report_hash=residual_hash,
    )

    # 9) 組 manifest_jsonb：runtime 欄位值須與 body 同名欄位字串相等（避免
    #    register :1340 `manifest_runtime_field_mismatch`）；禁 "_"-prefix key。
    manifest_jsonb: dict[str, Any] = {
        "symbol": symbol,
        "strategy": strategy,
        "timeframe": timeframe,
        "data_tier": data_tier,
        "hidden_oos_state": state,
        REGISTRY_RESIDUAL_ALPHA_HASH_FIELD: residual_hash,
        RESIDUAL_ALPHA_REPORT_FIELD: report,
    }

    # 10) 組 request：data_window = OOS 窗（experiment_registry `_extract` 強制
    #     state.window_start == body.data_window_start）；unsigned。
    body = ReplayExperimentRegisterRequest(
        symbol=symbol,
        strategy=strategy,
        timeframe=timeframe,
        data_tier=data_tier,
        data_window_start=oos_start,
        data_window_end=data_end,
        strategy_config_sha256=strategy_config_sha256,
        risk_config_sha256=risk_config_sha256,
        half_life_days=half_life_days,
        embargo_days=embargo_days,
        manifest_jsonb=manifest_jsonb,
        signature_hex=None,
    )

    # 11) 唯一寫入：注入的 register_fn（預設 run_register_in_pg_xact，xact 內
    #     兩個 INSERT：replay.experiments + learning.hidden_oos_state_registry）。
    return register_fn(
        get_pg_conn_fn, actor, body, manifest_signer_module=manifest_signer_module
    )


def _to_iso_dt(value: datetime) -> str | None:
    """datetime → ISO-8601 UTC 字串；非法回 None。naive 當 UTC（MIT UTC 紀律）。"""
    if not isinstance(value, datetime):
        return None
    dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _windows_strictly_increasing(
    calibration_window: tuple[str, str],
    candidate_window: tuple[str, str],
    oos_window: tuple[str, str],
) -> bool:
    """三窗皆嚴格遞增且首尾相接不交叉（V132 windows_chk 的 Python 前置守衛）。

    驗：每窗 start<end，且 calib_end<=cand_start、cand_end<=oos_start。任一不滿
    足回 False（caller fail-closed），避免送非法窗去撞 durable INSERT CHECK。
    """
    cw = [_parse_iso(x) for x in calibration_window]
    nw = [_parse_iso(x) for x in candidate_window]
    ow = [_parse_iso(x) for x in oos_window]
    if any(x is None for x in cw + nw + ow):
        return False
    return (
        cw[0] < cw[1]
        and nw[0] < nw[1]
        and ow[0] < ow[1]
        and cw[1] <= nw[0]
        and nw[1] <= ow[0]
    )


def _parse_iso(value: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


__all__ = [
    "RESIDUAL_ALPHA_REPORT_FIELD",
    "partition_round_trips_by_oos",
    "register_residual_candidate_experiment",
]
