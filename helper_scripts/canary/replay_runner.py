#!/usr/bin/env python3
"""
MODULE_NOTE (English):
  Canary Replay Runner (R07-1) — fetches historical klines from Bybit REST API,
  synthesizes PriceEvent ticks, runs them through both Python PipelineBridge
  and a simulated Rust engine path, and outputs JSONL files for the comparator.

  This replaces the live 7-day shadow process with a compressed historical replay
  that can verify Rust-vs-Python equivalence in hours instead of days.

MODULE_NOTE (中文):
  灰度回放運行器（R07-1）— 從 Bybit REST API 獲取歷史 K 線，合成 PriceEvent tick，
  通過 Python PipelineBridge 和模擬 Rust 引擎路徑運行，輸出 JSONL 文件供比較器使用。

  用壓縮歷史回放取代 7 天即時灰度，幾小時內完成 Rust 與 Python 的等價性驗證。

Usage:
  python replay_runner.py                          # Default: 5 symbols, 7 days of 1m bars
  python replay_runner.py --days 3 --symbols BTCUSDT ETHUSDT
  python replay_runner.py --output-dir /tmp/canary  # Custom output directory
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [REPLAY] %(levelname)s %(message)s",
)
logger = logging.getLogger("replay_runner")

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

BYBIT_BASE_URL = "https://api.bybit.com"
BYBIT_TF_MAP = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "D"}
MAX_BARS_PER_REQUEST = 200
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
DEFAULT_DAYS = 7
TICKS_PER_BAR = 4  # Synthesize 4 ticks per 1m bar (open, high, low, close)

# Schema version must match canary_schema.py / 模式版本必須匹配
SCHEMA_VERSION = "1.0.0"


# ═══════════════════════════════════════════════════════════════════════════════
# Bybit Historical Data Fetcher / Bybit 歷史數據獲取器
# ═══════════════════════════════════════════════════════════════════════════════


def fetch_klines(
    symbol: str,
    interval: str = "1m",
    limit: int = 200,
    end_ms: Optional[int] = None,
) -> list[dict]:
    """
    Fetch historical klines from Bybit V5 public API.
    從 Bybit V5 公開 API 獲取歷史 K 線。

    Returns list of dicts: [{open_time_ms, open, high, low, close, volume, turnover}, ...]
    """
    bybit_interval = BYBIT_TF_MAP.get(interval)
    if bybit_interval is None:
        raise ValueError(f"Unsupported interval: {interval}")

    limit = min(limit, MAX_BARS_PER_REQUEST)
    url = (
        f"{BYBIT_BASE_URL}/v5/market/kline"
        f"?category=linear&symbol={urllib.parse.quote(symbol, safe='')}"
        f"&interval={urllib.parse.quote(bybit_interval, safe='')}&limit={limit}"
    )
    if end_ms is not None:
        url += f"&end={end_ms}"

    req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())

    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {data.get('retMsg', 'unknown')}")

    raw = data.get("result", {}).get("list", [])
    if not raw:
        return []

    # Bybit returns newest first → reverse for chronological order
    # Bybit 返回最新在前 → 反轉為時間順序
    raw.reverse()

    bars = []
    for k in raw:
        # Format: [startTime, open, high, low, close, volume, turnover]
        bars.append({
            "open_time_ms": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "turnover": float(k[6]) if len(k) > 6 else 0.0,
        })

    return bars


def fetch_klines_multi_page(
    symbol: str,
    days: int = 7,
    interval: str = "1m",
) -> list[dict]:
    """
    Fetch multiple pages of klines to cover the requested number of days.
    獲取多頁 K 線以覆蓋請求的天數。
    """
    bars_needed = days * 24 * 60  # 1 bar per minute for 1m interval
    all_bars: list[dict] = []
    end_ms: Optional[int] = None

    logger.info(
        "Fetching %d bars (%d days) of %s %s klines... / 獲取 %d 根 K 線...",
        bars_needed, days, symbol, interval, bars_needed,
    )

    while len(all_bars) < bars_needed:
        remaining = bars_needed - len(all_bars)
        batch_size = min(remaining, MAX_BARS_PER_REQUEST)

        try:
            batch = fetch_klines(symbol, interval, batch_size, end_ms)
        except Exception as e:
            logger.warning("Fetch error for %s (have %d bars): %s", symbol, len(all_bars), e)
            break

        if not batch:
            break

        # Prepend (older bars come first in the batch, but we're paginating backward)
        all_bars = batch + all_bars
        # Next page ends before the oldest bar we have
        end_ms = batch[0]["open_time_ms"] - 1

        logger.debug("  fetched %d bars, total %d / %d", len(batch), len(all_bars), bars_needed)

        # Rate limit: 100ms between requests / 請求間隔 100ms
        time.sleep(0.1)

    logger.info("  %s: fetched %d / %d bars / 已獲取 %d / %d 根", symbol, len(all_bars), bars_needed, len(all_bars), bars_needed)
    return all_bars


# ═══════════════════════════════════════════════════════════════════════════════
# Tick Synthesizer / Tick 合成器
# ═══════════════════════════════════════════════════════════════════════════════


def synthesize_ticks(bars: list[dict], symbol: str) -> list[dict]:
    """
    Synthesize realistic tick events from OHLCV bars.
    從 OHLCV K 線合成真實的 tick 事件。

    Each bar produces 4 ticks (OHLC) at evenly spaced timestamps within the bar.
    每根 K 線產生 4 個 tick（開高低收）。
    """
    ticks = []
    for bar in bars:
        open_ts = bar["open_time_ms"]
        period_ms = 60_000  # 1 minute for 1m bars
        step = period_ms // TICKS_PER_BAR

        prices = [bar["open"], bar["high"], bar["low"], bar["close"]]
        vol_per_tick = bar["volume"] / TICKS_PER_BAR

        for i, price in enumerate(prices):
            ticks.append({
                "symbol": symbol,
                "last_price": price,
                "ts_ms": open_ts + i * step,
                "volume_24h": vol_per_tick,
            })

    return ticks


# ═══════════════════════════════════════════════════════════════════════════════
# Python Shadow Pipeline / Python 影子管線
# ═══════════════════════════════════════════════════════════════════════════════


def run_python_shadow(
    all_ticks: list[dict],
    output_path: str,
) -> int:
    """
    Run ticks through Python pipeline and output shadow_results.jsonl.
    通過 Python 管線運行 tick 並輸出 shadow_results.jsonl。

    Returns number of records written.
    """
    # Import Python pipeline components / 導入 Python 管線組件
    program_code = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "program_code",
    )
    if program_code not in sys.path:
        sys.path.insert(0, program_code)

    from local_model_tools.kline_manager import KlineManager as PyKlineManager
    from local_model_tools.indicator_engine import IndicatorEngine as PyIndicatorEngine
    from local_model_tools.signal_generator import SignalEngine as PySignalEngine

    symbols = list({t["symbol"] for t in all_ticks})
    km = PyKlineManager(symbols=symbols)
    ie = PyIndicatorEngine(kline_manager=km)
    se = PySignalEngine()

    # Wire indicator → signal callback / 連接指標 → 信號回調
    collected_signals: list[dict] = []

    def _on_indicators(symbol: str, timeframe: str, indicators: dict) -> None:
        for rule in se._rules:
            try:
                sig = rule.evaluate(symbol, timeframe, indicators)
                if sig is not None:
                    collected_signals.append(_serialize_signal_obj(sig))
            except Exception:
                pass

    ie.register_on_update(_on_indicators)

    record_count = 0
    tick_number = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for tick in all_ticks:
            tick_number += 1
            symbol = tick["symbol"]
            price = tick["last_price"]
            ts_ms = tick["ts_ms"]

            # Clear signal collector / 清空信號收集器
            collected_signals.clear()

            # Feed kline manager (triggers indicator computation on bar close)
            # 餵入 K 線管理器（K 線收盤時觸發指標計算）
            km.on_price_event(tick)

            # Get current indicators (may be from last closed bar)
            # 獲取當前指標（可能來自上一根收盤 K 線）
            indicators = ie.get_indicators(symbol, "1m")

            # Build canary record / 構建灰度記錄
            record = {
                "schema_version": SCHEMA_VERSION,
                "source": "python_shadow",
                "tick_number": tick_number,
                "timestamp_ms": ts_ms,
                "symbol": symbol,
                "price": price,
                "indicators": _serialize_indicators(indicators),
                "signals": list(collected_signals),
                "order_intents": [],  # Shadow doesn't execute orders
                "paper_state": {},    # Shadow doesn't track paper state
                "stats": {"total_ticks": tick_number},
            }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            record_count += 1

            if tick_number % 10000 == 0:
                logger.info("  Python shadow: %d / %d ticks processed", tick_number, len(all_ticks))

    logger.info("Python shadow complete: %d records → %s", record_count, output_path)
    return record_count


def _serialize_indicators(ind: Any) -> dict:
    """Convert indicator result to flat dict for JSONL / 將指標結果轉換為扁平字典"""
    if ind is None:
        return {}
    if isinstance(ind, dict):
        return ind
    # If it's an object with attributes / 如果是帶屬性的對象
    result = {}
    for attr in ("sma_20", "ema_12", "rsi_14", "volume_ratio"):
        val = getattr(ind, attr, None)
        if val is not None:
            result[attr] = val
    for compound in ("macd", "bollinger", "atr", "stochastic", "adx", "kama", "hurst", "ewma_vol", "donchian"):
        sub = getattr(ind, compound, None)
        if sub is not None:
            if isinstance(sub, dict):
                result[compound] = sub
            elif hasattr(sub, "__dict__"):
                result[compound] = {k: v for k, v in sub.__dict__.items() if not k.startswith("_")}
    return result


def _serialize_signal_obj(s: Any) -> dict:
    """Convert a single signal object to dict / 將單個信號對象轉換為字典"""
    if isinstance(s, dict):
        return s
    if hasattr(s, "__dict__"):
        return {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
    return {"value": str(s)}


def _serialize_signals(signals: list) -> list[dict]:
    """Convert signal objects to dicts for JSONL / 將信號對象轉換為字典"""
    return [_serialize_signal_obj(s) for s in signals]


# ═══════════════════════════════════════════════════════════════════════════════
# Rust Engine Replay / Rust 引擎回放
# ═══════════════════════════════════════════════════════════════════════════════


def run_rust_replay(
    all_ticks: list[dict],
    output_path: str,
    engine_binary: Optional[str] = None,
) -> int:
    """
    Run ticks through Rust engine in replay mode and output engine_results.jsonl.
    通過 Rust 引擎回放模式運行 tick 並輸出 engine_results.jsonl。

    Strategy: write ticks to a temp JSONL file, then invoke the Rust binary
    with --replay-mode --replay-input --replay-output flags.
    策略：將 tick 寫入臨時 JSONL，然後用 --replay-mode 調用 Rust 二進制。
    """
    # Write tick data for Rust binary consumption / 寫入 tick 數據供 Rust 二進制消費
    tick_file = output_path.replace("engine_results", "replay_ticks")
    with open(tick_file, "w", encoding="utf-8") as f:
        for tick in all_ticks:
            f.write(json.dumps(tick, ensure_ascii=False) + "\n")

    logger.info("Tick data written to %s (%d ticks) for Rust replay", tick_file, len(all_ticks))

    # Locate Rust binary / 定位 Rust 二進制
    if engine_binary is None:
        # Try common paths / 嘗試常見路徑
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "..", "rust", "target", "release", "openclaw-engine"),
            os.path.join(os.path.dirname(__file__), "..", "..", "rust", "target", "debug", "openclaw-engine"),
        ]
        for c in candidates:
            resolved = os.path.realpath(c)
            if os.path.isfile(resolved):
                engine_binary = resolved
                break

    if not engine_binary or not os.path.isfile(engine_binary):
        logger.warning(
            "Rust engine binary not found. Build with: cargo build --release "
            "/ 未找到 Rust 引擎二進制。請先執行 cargo build --release"
        )
        return 0

    # Invoke Rust engine in replay mode / 調用 Rust 引擎回放模式
    cmd = [
        engine_binary,
        "--replay-mode",
        "--replay-input", tick_file,
        "--replay-output", output_path,
    ]
    logger.info("Running Rust replay: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout / 10 分鐘超時
        )
        if result.returncode != 0:
            logger.error(
                "Rust replay failed (exit %d). stderr:\n%s",
                result.returncode,
                result.stderr[:2000] if result.stderr else "(empty)",
            )
            return 0

        # Log Rust engine stdout (contains tracing output) / 記錄引擎輸出
        if result.stderr:
            for line in result.stderr.strip().split("\n")[-5:]:
                logger.info("  [rust] %s", line)

    except subprocess.TimeoutExpired:
        logger.error("Rust replay timed out after 600s / Rust 回放超時（600 秒）")
        return 0
    except FileNotFoundError:
        logger.error("Rust binary not executable: %s / 二進制不可執行", engine_binary)
        return 0
    except Exception as e:
        logger.error("Rust replay error: %s / Rust 回放錯誤", e)
        return 0

    # Count output records / 計算輸出記錄數
    record_count = 0
    if os.path.isfile(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record_count += 1

    logger.info(
        "Rust replay complete: %d records → %s / Rust 回放完成：%d 條記錄",
        record_count, output_path, record_count,
    )
    return record_count


# ═══════════════════════════════════════════════════════════════════════════════
# Main Orchestrator / 主編排器
# ═══════════════════════════════════════════════════════════════════════════════


def run_replay(
    symbols: list[str],
    days: int,
    output_dir: str,
) -> dict:
    """
    Full replay pipeline: fetch → synthesize → run Python shadow → compare.
    完整回放管線：獲取 → 合成 → 運行 Python 影子 → 比較。
    """
    os.makedirs(output_dir, exist_ok=True)
    start_time = time.time()

    # Step 1: Fetch historical klines / 步驟 1：獲取歷史 K 線
    logger.info("=" * 60)
    logger.info("Step 1: Fetching %d days of klines for %d symbols", days, len(symbols))
    logger.info("=" * 60)

    all_ticks: list[dict] = []
    for symbol in symbols:
        bars = fetch_klines_multi_page(symbol, days=days)
        ticks = synthesize_ticks(bars, symbol)
        all_ticks.extend(ticks)

    # Sort by timestamp for realistic interleaving / 按時間戳排序以模擬真實交錯
    all_ticks.sort(key=lambda t: (t["ts_ms"], t["symbol"]))
    logger.info("Total ticks synthesized: %d", len(all_ticks))

    # Step 2: Run Python shadow / 步驟 2：運行 Python 影子
    logger.info("=" * 60)
    logger.info("Step 2: Running Python shadow pipeline")
    logger.info("=" * 60)

    shadow_path = os.path.join(output_dir, "shadow_results.jsonl")
    shadow_count = run_python_shadow(all_ticks, shadow_path)

    # Step 3: Run Rust replay (or note for live engine) / 步驟 3：運行 Rust 回放
    logger.info("=" * 60)
    logger.info("Step 3: Rust engine replay")
    logger.info("=" * 60)

    engine_path = os.path.join(output_dir, "engine_results.jsonl")
    rust_count = run_rust_replay(all_ticks, engine_path)

    # Step 4: Run comparator if both files exist / 步驟 4：如果兩個文件都存在則運行比較器
    elapsed = time.time() - start_time
    result = {
        "symbols": symbols,
        "days": days,
        "total_ticks": len(all_ticks),
        "shadow_records": shadow_count,
        "engine_records": rust_count,
        "shadow_path": shadow_path,
        "engine_path": engine_path,
        "elapsed_seconds": round(elapsed, 1),
    }

    if shadow_count > 0 and rust_count > 0:
        logger.info("=" * 60)
        logger.info("Step 4: Running comparator")
        logger.info("=" * 60)
        try:
            from canary_comparator import run_comparison
            report = run_comparison(engine_path, shadow_path)
            result["comparison_verdict"] = report.verdict
            result["critical_count"] = report.critical_count
            result["warning_count"] = report.warning_count
            logger.info("Comparison verdict: %s (CRITICAL=%d, WARNING=%d)",
                        report.verdict, report.critical_count, report.warning_count)
        except Exception as e:
            logger.warning("Comparator failed: %s", e)
            result["comparison_verdict"] = "SKIPPED"
    else:
        logger.info("=" * 60)
        logger.info("Step 4: Comparison skipped — Rust engine records pending")
        logger.info("  To generate Rust records, run the engine with OPENCLAW_CANARY_MODE=1")
        logger.info("  Then run: python canary_comparator.py --engine %s --shadow %s",
                     engine_path, shadow_path)
        logger.info("=" * 60)
        result["comparison_verdict"] = "PENDING_RUST"

    # Summary / 摘要
    logger.info("")
    logger.info("═" * 60)
    logger.info("REPLAY COMPLETE")
    logger.info("  Symbols: %s", ", ".join(symbols))
    logger.info("  Days: %d → %d ticks", days, len(all_ticks))
    logger.info("  Shadow records: %d → %s", shadow_count, shadow_path)
    logger.info("  Engine records: %d", rust_count)
    logger.info("  Elapsed: %.1f seconds", elapsed)
    logger.info("  Verdict: %s", result["comparison_verdict"])
    logger.info("═" * 60)

    # Write summary / 寫入摘要
    summary_path = os.path.join(output_dir, "replay_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    logger.info("Summary: %s", summary_path)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CLI / 命令行接口
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Canary Replay Runner — historical kline replay for Rust vs Python comparison"
    )
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS,
                        help="Symbols to replay (default: 5 majors)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help="Days of historical data to replay (default: 7)")
    parser.add_argument("--output-dir", default=os.path.join(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"), "canary"),
                        help="Output directory for JSONL files")
    args = parser.parse_args()

    result = run_replay(args.symbols, args.days, args.output_dir)

    sys.exit(0 if result.get("comparison_verdict") in ("PASS", "PENDING_RUST") else 1)


if __name__ == "__main__":
    main()
