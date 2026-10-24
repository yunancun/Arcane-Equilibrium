"""U6 的獨立 Decimal 重算；不匯入 U4 物化或 U5 成交規則。"""

import argparse
import bisect
import copy
import csv
import hashlib
import io
import json
import math
import re
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, localcontext
from functools import wraps
from pathlib import Path, PurePosixPath

from program_code.research.r8_ledger.ledger import canonical, ResearchLedger


class SeriesError(ValueError):
    """輸入或重算證據不符合研究契約。"""


def decimal_value(value):
    """只接收原始十進位字串或已解析的 Decimal，避免浮點數污染。"""
    if not isinstance(value, (str, Decimal)):
        raise SeriesError("數值必須是十進位字串")
    if isinstance(value,str) and not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?',value):
        raise SeriesError("數值須為一般小數，不接受科學記號")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise SeriesError("無效十進位數值") from exc
    if not result.is_finite():
        raise SeriesError("數值必須有限")
    return result


def _exchange_decimal(value):
    """僅供 U4 的交易所來源數值；十進位科學記號直接轉 Decimal，不經浮點。"""
    if not isinstance(value,str) or not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?',value):
        raise SeriesError('交易所來源數值須為十進位字串，可含科學記號')
    try:
        return decimal_value(Decimal(value))
    except InvalidOperation as exc:
        raise SeriesError('無效交易所來源十進位數值') from exc


def decimal_text(value):
    """依 §3.9 輸出一般小數，零統一為 0。"""
    value = decimal_value(value)
    with localcontext() as ctx:
        ctx.prec = max(28, len(value.as_tuple().digits))
        return "0" if not value else format(value.normalize(), "f")


def target_quantity(equity, weight, decision_price, qty_step):
    """目標權重按決策收盤價換算，數量向零取整。"""
    equity, weight, price, step = map(
        decimal_value, (equity, weight, decision_price, qty_step)
    )
    if equity <= 0 or price <= 0 or step <= 0:
        raise SeriesError("權益、價格及數量步長必須為正")
    with localcontext() as ctx:
        ctx.prec = 50
        return (equity * weight / price / step).to_integral_value(
            rounding=ROUND_DOWN
        ) * step


def fill_cost(quantity, reference_price, slippage_bps, fee_rate):
    """滑價作用於價格，手續費作用於含滑價的成交名目。"""
    quantity, price, bps, rate = map(
        decimal_value, (quantity, reference_price, slippage_bps, fee_rate)
    )
    if not quantity or price <= 0 or not 0 <= bps < 10000 or rate < 0:
        raise SeriesError("成交數量、價格、滑價或費率不合法")
    with localcontext() as ctx:
        ctx.prec = 50
        fill_price = price * (1 + (bps if quantity > 0 else -bps) / 10000)
        return fill_price, abs(quantity) * fill_price * rate


def funding_amount(q_before, q_after, price, rate, delta, *, estimated=False):
    """結算點前後取較不利現金流；估計的資金費一律為支付。"""
    before, after, price, rate, delta = map(
        decimal_value, (q_before, q_after, price, rate, delta)
    )
    if price <= 0 or not 0 <= delta <= 1 or (estimated and rate < 0):
        raise SeriesError("資金費價格、調整或估計費率不合法")
    with localcontext() as ctx:
        ctx.prec = 50
        if estimated:
            return -max(abs(before), abs(after)) * price * rate * (1 + delta)
        amount = min(-before * price * rate, -after * price * rate)
        return amount * (1 + delta if amount < 0 else 1 - delta)


def delisting_cost(position, last_bar, previous_complete_bar, penalty_bps, fee_rate):
    """下架時以最後兩根的不利極值平倉，部分 K 線仍可用於結算。"""
    quantity = decimal_value(position)
    if quantity > 0:
        price = min(decimal_value(last_bar["low"]),
                    decimal_value(previous_complete_bar["low"]))
    else:
        price = max(decimal_value(last_bar["high"]),
                    decimal_value(previous_complete_bar["high"]))
    return fill_cost(-quantity, price, penalty_bps, fee_rate)


def order_segments(position, target, decision_price, min_qty, min_notional,
                   daily_turnover, hourly_turnover, history_sufficient, cost):
    """按單一標的拆反手；減曝險段與增曝險段分別檢查。"""
    position, target, price, minimum, notional, daily, hourly = map(
        decimal_value, (position, target, decision_price, min_qty,
                        min_notional, daily_turnover, hourly_turnover)
    )
    if price <= 0 or min(minimum, notional, daily, hourly) < 0:
        raise SeriesError("訂單價格、最小門檻或成交額不合法")
    with localcontext() as ctx:
        ctx.prec = 50
        multiplier = decimal_value(cost["slippage_multiplier"])
        penalty = decimal_value(cost["forced_reduce_penalty_bps"]) * multiplier
        threshold = decimal_value(cost["untradeable_below_turnover"])
        cap = hourly * decimal_value(cost["order_cap_fraction"])
        tiers = [
            (decimal_value(t["min_turnover"]), decimal_value(t["bps"]))
            for t in cost["slippage_tiers_bps"]
        ]
        if (multiplier < 0 or threshold < 0 or cap < 0 or
                not tiers or tiers != sorted(tiers, reverse=True) or
                any(level < 0 or bps < 0 for level, bps in tiers)):
            raise SeriesError("流動性與滑價設定不合法")
        bps = next((bps * multiplier for level, bps in tiers if daily >= level), None)
        pieces = [-position, target] if position * target < 0 else [target - position]
        result = []
        current = position
        for change in pieces:
            if not change:
                continue
            closing = bool(current) and change == -current
            reducing = bool(current) and current * change < 0 and abs(change) <= abs(current)
            reason = None
            if not closing and abs(change) < minimum:
                reason = "min_qty"
            elif not closing and abs(change) * price < notional:
                reason = "min_notional"
            liquidity_reason = (
                "insufficient_history" if not history_sufficient else
                "untradeable" if daily < threshold or bps is None else
                "order_cap" if abs(change) * price > cap else None
            )
            if reason is None and not reducing:
                reason = liquidity_reason
            if reason:
                result.append({"quantity": decimal_text(change), "reason": reason})
            else:
                result.append({
                    "quantity": decimal_text(change),
                    "slippage_bps": decimal_text(penalty if liquidity_reason else bps),
                    "kind": "forced_reduce_penalty" if liquidity_reason else "normal",
                })
                current += change
        return result


HOUR = 3600000
DAY = 24 * HOUR
# Operator 2026-10-20 明示豁免 §2.9 的固定驗收／估計規則。
PRICE_REL_TOL = Decimal('1e-9')
CASH_ABS_TOL = Decimal('1e-6')
EQUITY_FRACTION_TOL = Decimal('1e-8')
BETA_DAYS = 365
BETA_MIN_OBSERVATIONS = 90
BETA_MIN, BETA_MAX = Decimal('0'), Decimal('3')
IMAGE_DIGEST = 'sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6'
RUNTIME_METADATA = {
    'cost_model': {'id': 'r8_cost_rules', 'version': 'r8-p4-v1'},
    'fill_model': {'id': 'r8_next_open_fill', 'version': 'r8-p4-v1'},
    'engine': {'id': 'lean', 'version': IMAGE_DIGEST},
    'dependencies': {'lean_image_digest': IMAGE_DIGEST},
    'time_semantics': {'known_at': 'bar_end', 'fill_at': 'next_bar_open', 'simulated_latency_ms': 0},
}
FAILURES = {'fill_forward_bar', 'gross_exposure_cap', 'invalid_decision',
            'algorithm_exception', 'lean_error'}
# 固定於 55586c1e 的 U6 歷史來源；只供原 P4 run 回歸，不讓新引擎缺證據降級。
HISTORICAL_SERIES_SHAS = frozenset({
    'a91e604d52b13bdd6a2acb4f4b706ae78147856d6af2c20ca7528c129639dbe4',
    'dd2ec8bef1168263610151916d240d23dd1ba69122ae31c5e3453a3c6ed27e53',
    '6b8ab3c124773383e60591b251b6c4a939b0e8c2f38597e2160dd6abb58ceb57',
    '1b83f74575fb270fc5ae81abb003e1662ba61c1585ac5790218ae67f149fa5fc',
    '45f8a70f93d6e6343c12d507e64bab171481881a9df5522b6c872aa58c9c0f75',
    '6ecb67fb44fc30b9fa5ee7dea86562b54e5a81f48d605038faad0cf46a36e9b4',
    'fadd1526bb21a282259039b997af4e3ce35b0c4b5371dbc989cd4c4a877af41c',
    '258ab408fa0a61eb94459a996e304b2c9c9a526681d709800de4e2cbeb4b7455',
    '154eebed4c71683ff1fce7dc7769fba82935f1ca3ea8375b343314de84accc3a',
})


def _historical_run(run):
    files = run.get('algorithm_files')
    return isinstance(files, dict) and files.get('program_code/research/r8_engine/series.py') in HISTORICAL_SERIES_SHAS


def precise(function):
    @wraps(function)
    def call(*args, **kwargs):
        with localcontext() as ctx:
            ctx.prec = 50
            return function(*args, **kwargs)
    return call


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def timestamp(value):
    if type(value) is int:
        return value
    if not isinstance(value, str):
        raise SeriesError('時刻須為 UTC 毫秒或帳本 ISO 時刻')
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
            raise ValueError('UTC required')
        return int(dt.timestamp()*1000)
    except ValueError as exc:
        raise SeriesError('無效 UTC 時刻') from exc


def interval(value):
    a, b = timestamp(value['start']), timestamp(value['end'])
    if a >= b:
        raise SeriesError('區間必須遞增')
    return a, b


def load_json(path):
    raw = Path(path).read_bytes()
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SeriesError('JSON 重複鍵')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs)
        if canonical(value) != raw:
            raise SeriesError('必須是帳本 canonical JSON')
    except (ValueError, UnicodeError) as exc:
        raise SeriesError('無效標準化 JSON') from exc
    return value, raw


def exact_keys(value, required, optional=()):
    if not isinstance(value,dict) or not set(required)<=set(value) or set(value)-set(required)-set(optional):
        raise SeriesError('§7 欄位缺漏或含額外欄位')


def contained(root, name):
    root = root.resolve()
    if not isinstance(name, str):
        raise SeriesError('相對路徑必須是字串')
    relative = PurePosixPath(name)
    if (not isinstance(name, str) or relative.is_absolute() or
            any(part in ('..', '.') for part in name.split('/')) or
            '\\' in name or not name):
        raise SeriesError('不安全的相對路徑')
    path = root.joinpath(*relative.parts)
    if any(parent.is_symlink() for parent in (path, *path.parents)
           if parent != root and parent.is_relative_to(root)):
        raise SeriesError('不接受 symlink')
    if not path.resolve().is_relative_to(root.resolve()):
        raise SeriesError('路徑超出物化目錄')
    return path


class Materialization:
    """唯讀 U4 市場切片、屬性與 manifest 綁定的 DV6 驗證證據。"""

    def __init__(self, path, *, historical=False):
        if Path(path).is_symlink():
            raise SeriesError('manifest 不接受 symlink')
        self.path = Path(path).resolve()
        self.manifest, raw = load_json(self.path)
        self.sha256 = digest(raw)
        m = self.manifest
        exact_keys(m,('schema_version','u1_manifest_sha256','u1_tool_version','ledger_id',
            'hypothesis_id','generation','purpose','window','warmup','readable','symbols',
            'strategy_symbols','files','gaps','first_bar','min_notional','funding_interval_ms',
            'delistings','symbol_properties_overlay_sha256','limitations'))
        if m.get('schema_version') != 'r8_materialization_v1':
            raise SeriesError('物化 schema 不符')
        self.start, self.end = interval(m['window'])
        self.warm_start, warm_end = interval(m['warmup'])
        if warm_end != self.start:
            raise SeriesError('暖機終點不符')
        verified = any(name.startswith('verification/') for name in m['files'])
        if not verified and not historical:
            raise SeriesError('VERIFICATION_EVIDENCE_REQUIRED')
        read_start = self.warm_start
        if verified:
            read_start = TurnoverVerification.access(m, self.warm_start, self.start, self.end)
        self.symbols = m['symbols']
        if (len(set(self.symbols)) != len(self.symbols) or
                any(not re.fullmatch(r'[A-Z0-9]+', s) for s in self.symbols)):
            raise SeriesError('標的清單不合法')
        if (not isinstance(m['gaps'],dict) or set(m['gaps'])-set(self.symbols) or
                any(not isinstance(gaps,dict) or
                    set(gaps)-{'kline_hour','kline_day','open_interest','funding'}
                    for gaps in m['gaps'].values())):
            raise SeriesError('gaps 資料集名稱必須沿用 U4 manifest')
        self.hourly = {s: {} for s in self.symbols}
        self.daily = {s: {} for s in self.symbols}
        self.funding = {s: {} for s in self.symbols}
        self.properties = {}
        seen = set()
        for name, meta in m['files'].items():
            file = contained(self.path.parent, name)
            if not name.startswith('source/'):
                # 市場資料只解析 source；verification 證據由下方 DV6 邊界核對。
                # lean/custom payload 仍由 U5 檢查；submit 核對完整 files 身份。
                continue
            raw = file.read_bytes()
            if digest(raw) != meta['sha256']:
                raise SeriesError('source SHA-256 不符：'+name)
            match = re.fullmatch(r'source/(kline|funding|open_interest)_([A-Z0-9]+)_([^/]+)\.csv', name)
            if not match or match[2] not in self.symbols:
                raise SeriesError('無法識別原始切片：'+name)
            kind, symbol, resolution = match.groups()
            key = (kind, symbol, resolution)
            if key in seen:
                raise SeriesError('重複資料集')
            seen.add(key)
            reader = csv.DictReader(io.StringIO(raw.decode('utf-8')))
            fields = {'kline': ['timestamp','open','high','low','close','volume','turnover'],
                      'funding': ['timestamp','funding_rate'],
                      'open_interest': ['timestamp','open_interest']}[kind]
            if reader.fieldnames != fields:
                raise SeriesError('原始切片標頭不符')
            rows = list(reader)
            if len(rows) != meta['rows']:
                raise SeriesError('原始切片列數不符')
            previous = None
            for row in rows:
                try:
                    t = int(row.pop('timestamp'))
                except (ValueError, TypeError) as exc:
                    raise SeriesError('無效切片時刻') from exc
                if (previous is not None and t <= previous or t < read_start or
                        t > self.end or (kind != 'funding' and t == self.end)):
                    raise SeriesError('原始切片時間超界或不遞增')
                previous = t
                # §4 的 source 保留原字串：小時／日 K 線 OHLC、volume、turnover，
                # funding_rate 與 open_interest 都可能含科學記號；時刻仍走整數檢查。
                # run、設定、目標及帳本不是來源資料，仍只使用嚴格的 decimal_value。
                parsed = {k: _exchange_decimal(v) for k, v in row.items()}
                if kind == 'kline':
                    if resolution not in ('60', 'D'):
                        raise SeriesError('U6 只讀一小時與日線')
                    if (min(parsed[k] for k in ('open','high','low','close')) <= 0 or
                            parsed['low'] > min(parsed['open'], parsed['close']) or
                            parsed['high'] < max(parsed['open'], parsed['close']) or
                            min(parsed['volume'], parsed['turnover']) < 0):
                        raise SeriesError('不合法的 K 線')
                    (self.hourly if resolution == '60' else self.daily)[symbol][t] = parsed
                elif kind == 'funding':
                    delivery = m['delistings'].get(symbol, {}).get('deliveryTime')
                    if delivery is not None and t > delivery:
                        raise SeriesError('下架之後的資金費不得物化')
                    self.funding[symbol][t] = parsed['funding_rate']
        for s in self.symbols:
            if not any(k[:2] == ('kline',s) and k[2]=='60' for k in seen):
                raise SeriesError('缺少小時原始切片')
        overlay = contained(self.path.parent, 'symbol_properties_overlay.csv').read_bytes()
        if digest(overlay) != m['symbol_properties_overlay_sha256']:
            raise SeriesError('overlay SHA-256 不符')
        for row in csv.reader(io.StringIO(overlay.decode('utf-8'))):
            if len(row) != 11 or row[0] != 'bybit' or row[2] != 'cryptofuture':
                raise SeriesError('合約屬性列不符')
            s = row[1]
            if s not in self.symbols or s in self.properties:
                raise SeriesError('屬性標的缺漏或重複')
            # 這四欄來自 instruments-info。U4 目前已輸出一般小數，仍按交易所
            # 來源邊界解析；不把此入口用於 run.json 或任何研究／成本設定。
            prop = {'qty_step': _exchange_decimal(row[7]), 'min_qty': _exchange_decimal(row[9]),
                    'tick_size': _exchange_decimal(row[6]), 'min_notional': _exchange_decimal(m['min_notional'][s])}
            if min(prop.values()) < 0 or prop['qty_step'] <= 0 or prop['tick_size'] <= 0:
                raise SeriesError('合約屬性不合法')
            self.properties[s] = prop
        if set(self.properties) != set(self.symbols):
            raise SeriesError('缺少合約屬性')
        self.times = {s: sorted(self.hourly[s]) for s in self.symbols}
        try:
            self.turnover = TurnoverVerification(self) if verified else None
        except SeriesError:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise SeriesError('VERIFICATION_MALFORMED') from exc

    def last_bar(self, symbol, t):
        index = bisect.bisect_right(self.times[symbol], t-HOUR)-1
        if index < 0:
            raise SeriesError('計價時沒有已知收盤價：'+symbol)
        start = self.times[symbol][index]
        return start, self.hourly[symbol][start]

    def close(self, symbol, t):
        return self.last_bar(symbol, t)[1]['close']

    def funding_mark(self, symbol, t):
        """資金費以 T 結束的末根計價，包含非整點下架的部分 K 線。"""
        delivery=self.manifest['delistings'].get(symbol,{})
        if delivery.get('deliveryTime')==t and delivery.get('partial_last_bar'):
            index=bisect.bisect_left(self.times[symbol],t)-1
            if index>=0:
                start=self.times[symbol][index]
                if start<t<start+HOUR:
                    return self.hourly[symbol][start]['close'],False
        return self.close(symbol,t),t-HOUR not in self.hourly[symbol]

    def opening(self, symbol, t):
        return self.hourly[symbol][t]['open'] if t in self.hourly[symbol] else self.close(symbol,t)

    def liquidity(self, symbol, t, cost):
        days = cost['liquidity_window_days']
        if type(days) is not int or days <= 0:
            raise SeriesError('流動性回看天數須為正整數')
        if self.turnover is not None:
            if (days != 12 or decimal_value(cost['untradeable_below_turnover']) != 1000000 or
                    decimal_value(cost['order_cap_fraction']) != Decimal('0.01') or
                    [(decimal_value(v['min_turnover']),decimal_value(v['bps'])) for v in cost['slippage_tiers_bps']]
                    != [(100000000,5),(10000000,10),(1000000,20)]):
                raise SeriesError('TURNOVER_POLICY_MISMATCH')
            median, enough = self.turnover.at(symbol, t)
            return median, self.hourly[symbol].get(t-HOUR, {}).get('turnover', Decimal(0)), enough
        midnight = t//DAY*DAY
        first = self.manifest['first_bar'][symbol]
        complete_start = ((first+DAY-1)//DAY)*DAY if first is not None else midnight
        enough = first is not None and midnight-complete_start >= days*DAY
        values = [self.daily[symbol].get(midnight-i*DAY, {}).get('turnover', Decimal(0))
                  for i in range(1, days+1)]
        hourly = self.hourly[symbol].get(t-HOUR, {}).get('turnover', Decimal(0))
        return statistics.median(values), hourly, enough


class TurnoverVerification:
    """DV6：只驗 manifest 綁定切片；與 U4／U5 的生產及選級程式相互獨立。"""

    STANDARD = '794f4f652ab23ad78eb84d57c5f76fb8deb55b432f051ae4d963a69336c8b051'
    ROW_KEYS = ('schema_version symbol decision_utc_day known_at policy_sha256 history_sufficient '
                'inputs m_d m_e m_h tier_d tier_e tier_h triggered selected_source selected_median '
                'selected_tier status reason_codes').split()

    @staticmethod
    def access(m, warm_start, start, end):
        try:
            access = m['readable']
            exact_keys(access, ('generation time_splits selection out_of_sample max_lookback_seconds holdout').split())
            lo, hi = interval(access['out_of_sample'])
            if (access['generation'] != m['generation'] or not lo <= start < end <= hi or
                    any(s['kind']=='holdout' and warm_start < interval(s)[1] and interval(s)[0] < end
                        for s in access['time_splits'])):
                raise SeriesError('VERIFICATION_ACCESS_SCOPE')
            return max(warm_start, lo)
        except (ValueError, TypeError, KeyError) as exc:
            raise SeriesError('VERIFICATION_ACCESS_SCOPE') from exc

    def __init__(self, data):
        self.data, self.rows, self.original, self.origins = data, {}, {}, {}
        self.files = data.manifest['files']; self.raw = {}; self.source_shas = {}
        for name, meta in self.files.items():
            self.source_shas.setdefault(meta['source_file'], set()).add(meta['source_sha256'])
            self.source_shas.setdefault(name, set()).add(meta['sha256'])
        for name, meta in self.files.items():
            if not name.startswith('verification/'):
                continue
            exact_keys(meta, ('sha256 rows first last source_file source_sha256').split())
            self.sha(meta['sha256']); self.sha(meta['source_sha256'])
            contained(data.path.parent, meta['source_file'])  # 只檢查路徑，不開 P3b。
            if type(meta['rows']) is not int or meta['rows'] < 0:
                raise SeriesError('VERIFICATION_METADATA')
            if any(meta[k] is not None and type(meta[k]) is not int for k in ('first','last')):
                raise SeriesError('VERIFICATION_METADATA')
            raw = contained(data.path.parent, name).read_bytes()
            if digest(raw) != meta['sha256']:
                raise SeriesError('VERIFICATION_SHA_MISMATCH')
            self.raw[name] = raw
        policy = self.json('policy.json'); version = policy.get('schema_version')
        v2 = version == 'r8_data_verification_policy_v2'
        expected = dict(schema_version='r8_data_verification_policy_v2' if v2 else 'r8_data_verification_policy_v1',
            standard_sha256=self.STANDARD, approval_event='RH-20261022-05' if v2 else 'RH-20261022-04',
            p3b_manifest_sha256=data.manifest['u1_manifest_sha256'],
            listing=dict(x_pct='50', y_pct='20', z_pct='20', cooling_days=7,
                quantity='hourly_base_volume_daily_mean', variation='mean_relative_difference',
                stage_end_ranges=[[1,3],[7,15],[15,30]]),
            sampling=dict(seed=20261022, base_per_stratum=300, max_per_stratum=900,
                max_expansions=1, confidence='0.95', upper_limit='0.025'),
            turnover=dict(window_days=12, thresholds=['1000000','10000000','100000000'],
                trigger_pct='5', general='exchange_reported', suspect='sum_hourly_reported'),
            l4_price_threshold_pct='1')
        if v2:
            expected['volume_semantics_policy'] = 'v2-terminal-suffix-20261022'
        if canonical(policy) != canonical(expected):
            raise SeriesError('VERIFICATION_POLICY_MISMATCH')
        self.policy_sha = digest(self.raw['verification/policy.json'])
        binding = self.json('hypothesis_binding.json')
        self.binding = binding
        exact_keys(binding, ('schema_version hypothesis_id policy_sha256 family registration_sha256').split())
        self.sha(binding['registration_sha256'])
        if (binding['schema_version'] != 'r8_verification_hypothesis_binding_v1' or
                binding['hypothesis_id'] != data.manifest['hypothesis_id'] or
                binding['policy_sha256'] != self.policy_sha or binding['family'] not in ('ordinary','listing')):
            raise SeriesError('VERIFICATION_HYPOTHESIS_MISMATCH')
        report = self.json('verification.json')
        exact_keys(report, ('schema_version status policy_sha256 p3b_manifest_sha256 sample_plan_sha256 '
            'previous_corrections_sha256 review_refs tool_commit readable counts files reason_codes').split() +
            (['standard_sha256','volume_semantics_policy'] if v2 else []))
        if (report['schema_version'] != ('r8_data_verification_v2' if v2 else 'r8_data_verification_v1') or
                report['policy_sha256'] != self.policy_sha or
                report['p3b_manifest_sha256'] != data.manifest['u1_manifest_sha256'] or
                v2 and (report['standard_sha256'] != self.STANDARD or
                        report['volume_semantics_policy'] != expected['volume_semantics_policy'])):
            raise SeriesError('VERIFICATION_IDENTITY_MISMATCH')
        if report['status'] != 'READY':
            raise SeriesError('VERIFICATION_BLOCKED')
        exact_keys(report['readable'], ('start','end'))
        if any(type(v) is not int for v in report['readable'].values()):
            raise SeriesError('VERIFICATION_SCOPE_MISMATCH')
        self.scope = interval(report['readable'])
        if not self.scope[0] <= data.start < data.end <= self.scope[1]:
            raise SeriesError('VERIFICATION_SCOPE_MISMATCH')
        self.scope = (max(self.scope[0],data.warm_start), min(self.scope[1],data.end))
        self.reasons(report['reason_codes']); self.refs(report['review_refs'], report['reason_codes'])
        for key in ('sample_plan_sha256','previous_corrections_sha256'):
            if report[key] is not None:
                self.sha(report[key])
        if not isinstance(report['tool_commit'], str) or re.fullmatch('[0-9a-f]{40}', report['tool_commit']) is None:
            raise SeriesError('VERIFICATION_TOOL_IDENTITY')
        exact_keys(report['counts'], ('input_rows checked_days flagged_days corrected_fields unresolved_rows').split())
        if any(type(v) is not int or v < 0 for v in report['counts'].values()):
            raise SeriesError('VERIFICATION_COUNTS')
        for name, meta in report['files'].items():
            contained(data.path.parent, name); exact_keys(meta, ('sha256','rows')); self.sha(meta['sha256'])
            if type(meta['rows']) is not int or meta['rows'] < 0:
                raise SeriesError('VERIFICATION_FILES_MISMATCH')
        for name in ['policy.json','corrections.jsonl','findings.jsonl'] + (['volume_semantics.jsonl'] if v2 else []):
            meta = self.files.get('verification/'+name)
            if meta is None or report['files'].get(name) != {k:meta[k] for k in ('sha256','rows')}:
                raise SeriesError('VERIFICATION_FILES_MISMATCH')
        # 信心證據／上市階段不成為 U6 交易閘門；僅以上述 files 身份綁定。
        for symbol in data.symbols:
            if any(t % HOUR for t in data.hourly[symbol]) or any(t % DAY for t in data.daily[symbol]):
                raise SeriesError('TURNOVER_SOURCE_GRID')
            for t, volume in self.original_days(symbol, '60', 'volume').items():
                if volume is None:
                    raise SeriesError('TURNOVER_ORIGIN_UNKNOWN')
                if volume > 0:
                    self.origins[symbol] = t
                    break
            if symbol not in self.origins:
                raise SeriesError('TURNOVER_ORIGIN_UNKNOWN')
            self.original[symbol] = self.original_days(symbol)
        name = 'verification/turnover_decisions.jsonl'
        if name not in self.raw:
            raise SeriesError('TURNOVER_TABLE_MISSING')
        lines = self.raw[name].splitlines(keepends=True); previous = None; times = []
        for line in lines:
            row = self.decode(line); exact_keys(row, self.ROW_KEYS)
            day, symbol = row['decision_utc_day'], row['symbol']
            if (type(day) is not int or day % DAY or symbol not in data.symbols or
                    day < data.warm_start//DAY*DAY or day > data.end or
                    type(row['known_at']) is not int or row['known_at'] != day):
                raise SeriesError('TURNOVER_TIME_OR_SYMBOL')
            key = (day, symbol)
            if previous is not None and key <= previous:
                raise SeriesError('TURNOVER_DUPLICATE_OR_ORDER')
            previous = key; times.append(day)
            self.rows[key] = self.check(row)
        meta = self.files[name]
        if (meta['rows'] != len(lines) or meta['first'] != (min(times) if times else None) or
                meta['last'] != (max(times) if times else None)):
            raise SeriesError('TURNOVER_METADATA')

    @staticmethod
    def sha(value):
        if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
            raise SeriesError('VERIFICATION_SHA_FORMAT')

    @staticmethod
    def reasons(value):
        if (not isinstance(value, list) or any(not isinstance(v,str) or not v for v in value) or
                value != sorted(set(value))):
            raise SeriesError('VERIFICATION_REASON_CODES')

    def refs(self, refs, reasons, *, bound=False):
        if not isinstance(refs, list):
            raise SeriesError('VERIFICATION_SOURCE_REFS')
        keys = []
        for ref in refs:
            exact_keys(ref, ('kind relative_path url sha256 row request_id list_index byte_start byte_end trade_id line_sha256').split())
            if ref['kind'] not in ('raw','csv','trade','instruments','policy','plan','report'):
                raise SeriesError('VERIFICATION_SOURCE_REFS')
            if ref['relative_path'] is None:
                if ref['sha256'] is not None or not reasons:
                    raise SeriesError('VERIFICATION_SOURCE_REFS')
            else:
                contained(self.data.path.parent, ref['relative_path']); self.sha(ref['sha256'])
                # 若引用具名切片／原檔，SHA 必須與 manifest 已綁定的身份相同。
                matches = self.source_shas.get(ref['relative_path'], set())
                if (bound or matches) and ref['sha256'] not in matches:
                    raise SeriesError('VERIFICATION_SOURCE_IDENTITY')
            for key in ('row','list_index','byte_start','byte_end'):
                if ref[key] is not None and (type(ref[key]) is not int or ref[key] < (1 if key=='row' else 0)):
                    raise SeriesError('VERIFICATION_SOURCE_REFS')
            for key in ('url','request_id','trade_id'):
                if ref[key] is not None and not isinstance(ref[key], str):
                    raise SeriesError('VERIFICATION_SOURCE_REFS')
            if ref['line_sha256'] is not None:
                self.sha(ref['line_sha256'])
            if ref['byte_start'] is not None and ref['byte_end'] is not None and ref['byte_start']>ref['byte_end']:
                raise SeriesError('VERIFICATION_SOURCE_REFS')
            keys.append((ref['kind'],ref['relative_path'] or '', *[ref[k] if ref[k] is not None else -1
                         for k in ('row','list_index','byte_start')]))
        if keys != sorted(keys):
            raise SeriesError('VERIFICATION_SOURCE_REFS_ORDER')

    @staticmethod
    def decode(raw):
        try:
            value = json.loads(raw, parse_constant=lambda _: None)
            if canonical(value)+b'\n' != raw:
                raise ValueError()
            return value
        except (ValueError, UnicodeError) as exc:
            raise SeriesError('VERIFICATION_JSON_ENCODING') from exc

    def json(self, name):
        name = 'verification/'+name
        if name not in self.raw:
            raise SeriesError('VERIFICATION_FILE_MISSING')
        meta = self.files[name]
        if meta['rows'] != 1 or meta['first'] is not None or meta['last'] is not None:
            raise SeriesError('VERIFICATION_JSON_METADATA')
        result = self.decode(self.raw[name])
        if not isinstance(result, dict):
            raise SeriesError('VERIFICATION_JSON_OBJECT')
        return result

    def isolated_original(self, symbol, resolution, timestamp, source, line):
        if not hasattr(self,'quarantines'):
            indexes = []
            for name, identity in [('findings.jsonl','finding_id'),('corrections.jsonl','correction_id')]:
                keys = set()
                for raw in self.raw['verification/'+name].splitlines(keepends=True):
                    row = self.decode(raw)
                    relevant = (row.get('rule_id')=='DV-L1' and row.get('reason_code')=='OFF_GRID_TIMESTAMP' and row.get('field')=='timestamp'
                        if identity=='finding_id' else row.get('decision')=='UNRESOLVED' and row.get('row_action')=='missing'
                        and row.get('policy_sha256')==self.policy_sha and row.get('field') in ('open','high','low','close','volume','turnover'))
                    if not relevant: continue
                    if digest(canonical({k:v for k,v in row.items() if k!=identity})+b'\n') != row.get(identity): raise SeriesError('TURNOVER_QUARANTINE_IDENTITY')
                    self.refs(row['source_refs'],[row['reason_code']])
                    keys.update((row['symbol'],row['interval'],row['timestamp'],row['dataset'],r['relative_path'],r['sha256'],r['line_sha256'])
                                for r in row['source_refs'] if r['kind']=='csv')
                indexes.append(keys)
            self.quarantines = indexes[0].intersection(indexes[1])
        return (symbol,resolution,timestamp,'kline_day' if resolution=='D' else 'kline_hour',
                source['source_file'],source['source_sha256'],digest(line)) in self.quarantines

    def original_days(self, symbol, interval='D', field='turnover'):
        name = 'verification/original/kline_'+symbol+'_'+interval+'.csv'
        if name not in self.raw: raise SeriesError('TURNOVER_ORIGINAL_MISSING')
        effective = self.files.get('source/kline_'+symbol+'_'+interval+'.csv', {})
        if any(self.files[name][k] != effective.get(k) for k in ('source_file','source_sha256')): raise SeriesError('TURNOVER_ORIGINAL_IDENTITY')
        reader = csv.DictReader(io.StringIO(self.raw[name].decode('utf-8')))
        if reader.fieldnames != ['timestamp','open','high','low','close','volume','turnover']: raise SeriesError('TURNOVER_ORIGINAL_HEADER')
        result, times, origin, lines = {}, [], None, self.raw[name].splitlines(keepends=True)
        for index, row in enumerate(reader,1):
            try:
                t = int(row['timestamp'])
            except (ValueError, TypeError) as exc:
                raise SeriesError('TURNOVER_ORIGINAL_TIME') from exc
            offgrid = t % (DAY if interval=='D' else HOUR)
            known_origin = origin if interval=='60' else self.origins.get(symbol)
            if (not self.scope[0] <= t < self.scope[1] or times and t < times[-1]
                    or offgrid and (known_origin is None or t <= known_origin
                        or not self.isolated_original(symbol,interval,t,self.files[name],lines[index]))):
                raise SeriesError('TURNOVER_ORIGINAL_SCOPE')
            # 時刻／標的／範圍先於市場值；無法用的原額保留 null 比較及零中位數輸入。
            try:
                if offgrid: raise SeriesError('TURNOVER_ORIGINAL_AMOUNT')
                value = _exchange_decimal(row[field])
                if value < 0: value = None
            except SeriesError: value = None
            result[t] = value if t not in result else None
            if interval=='60' and field=='volume' and origin is None and result[t] is not None and result[t]>0: origin = t
            times.append(t)
        meta = self.files[name]
        if (meta['rows'] != len(times) or meta['first'] != (min(times) if times else None) or
                meta['last'] != (max(times) if times else None)):
            raise SeriesError('TURNOVER_ORIGINAL_METADATA')
        return result

    @staticmethod
    def total(values, divisor=1):
        # 保留任意來源小數尾數，不能用重算現金容差或固定精度比較市場額。
        with localcontext() as ctx:
            ctx.prec = max(50, max(v.adjusted() for v in values)-min(v.as_tuple().exponent for v in values)+10)
            return sum(values, Decimal(0))/divisor

    @classmethod
    def median(cls, values):
        ordered = sorted(v if v is not None and v >= 0 else Decimal(0) for v in values)
        return cls.total(ordered[5:7], 2)

    @staticmethod
    def tier(value):
        return next((name for threshold, name in [(100000000,'GE_100M'),(10000000,'GE_10M'),
                    (1000000,'GE_1M')] if value >= threshold), 'NO_OPEN')

    @staticmethod
    def same_amount(actual, expected):
        if (actual is None) != (expected is None) or actual is not None and _exchange_decimal(actual) != expected:
            raise SeriesError('TURNOVER_AMOUNT_MISMATCH')

    def check(self, row):
        day, symbol = row['decision_utc_day'], row['symbol']; data = self.data
        if row['schema_version'] != 'r8_turnover_decision_v1' or row['policy_sha256'] != self.policy_sha:
            raise SeriesError('TURNOVER_POLICY_MISMATCH')
        if row['status'] != 'READY':
            raise SeriesError('TURNOVER_BLOCKED')
        self.reasons(row['reason_codes'])
        if type(row['triggered']) is not bool or type(row['history_sufficient']) is not bool:
            raise SeriesError('TURNOVER_BOOLEAN')
        if not isinstance(row['inputs'], list) or len(row['inputs']) != 12:
            raise SeriesError('TURNOVER_WINDOW')
        original, effective, hourly = [], [], []
        for index, item in enumerate(row['inputs']):
            exact_keys(item, ('day_start exchange_reported effective_reported sum_hourly_reported '
                             'daily_status hourly_status source_refs').split())
            t = day-(12-index)*DAY
            if type(item['day_start']) is not int or item['day_start'] != t:
                raise SeriesError('TURNOVER_WINDOW')
            d = self.original[symbol].get(t); e = data.daily[symbol].get(t, {}).get('turnover')
            if t < self.origins[symbol]:
                d = e = None  # A partial listing day is not a complete daily input.
            self.refs(item['source_refs'], row['reason_codes'], bound=True)
            if (d is not None or e is not None or item['sum_hourly_reported'] is not None) and not item['source_refs']:
                raise SeriesError('TURNOVER_SOURCE_REFS_MISSING')
            self.same_amount(item['exchange_reported'], d); self.same_amount(item['effective_reported'], e)
            if item['daily_status'] not in (('VALID',) if e is not None else ('MISSING','INVALID')):
                raise SeriesError('TURNOVER_DAILY_STATUS')
            original.append(d); effective.append(e)
            h = None; status = item['hourly_status']
            if status != 'NOT_EVALUATED':
                hours = [data.hourly[symbol].get(t+i*HOUR, {}).get('turnover') for i in range(24)]
                first = max(self.origins[symbol], data.manifest['first_bar'][symbol])
                delivery = data.manifest['delistings'].get(symbol, {}).get('deliveryTime')
                if (first is not None and first <= t and (delivery is None or delivery >= t+DAY) and
                        self.scope[0] <= t and t+DAY <= self.scope[1] and all(v is not None for v in hours)):
                    h = self.total(hours)
                if status not in (('VALID',) if h is not None else ('MISSING','INVALID')):
                    raise SeriesError('TURNOVER_HOURLY_STATUS')
            self.same_amount(item['sum_hourly_reported'], h); hourly.append(h)
        md, me = self.median(original), self.median(effective)
        triggered = any(Decimal(t)*Decimal('0.95') <= me <= Decimal(t)*Decimal('1.05')
                        for t in (1000000,10000000,100000000))
        if (any(v is None for v in effective) or triggered and any(v is None for v in hourly)) and not row['reason_codes']:
            raise SeriesError('TURNOVER_INCOMPLETE_REASON_MISSING')
        if row['triggered'] != triggered or triggered and any(i['hourly_status']=='NOT_EVALUATED' for i in row['inputs']):
            raise SeriesError('TURNOVER_TRIGGER_MISMATCH')
        evaluated = all(i['hourly_status'] != 'NOT_EVALUATED' for i in row['inputs'])
        mh = self.median(hourly) if evaluated else None
        for suffix, amount in [('d',md),('e',me),('h',mh)]:
            self.same_amount(row['m_'+suffix], amount)
            if row['tier_'+suffix] != (self.tier(amount) if amount is not None else None):
                raise SeriesError('TURNOVER_TIER_MISMATCH')
        first = data.manifest['first_bar'][symbol]
        enough = first is not None and day-((first+DAY-1)//DAY)*DAY >= 12*DAY
        chosen = mh if triggered and self.tier(mh) != self.tier(me) else me
        source = 'hourly_sum' if triggered and self.tier(mh) != self.tier(me) else 'effective_daily'
        self.same_amount(row['selected_median'], chosen)
        if (row['selected_source'] != source or row['selected_tier'] != (self.tier(chosen) if enough else 'NO_OPEN') or
                row['history_sufficient'] != enough):
            raise SeriesError('TURNOVER_SELECTION_MISMATCH')
        return chosen, enough

    def at(self, symbol, t):
        key = (t//DAY*DAY, symbol)
        if key not in self.rows:
            raise SeriesError('TURNOVER_DECISION_MISSING')
        return self.rows[key]


@precise
def funding_schedule(rows, start, end, current_interval, minimum_rate):
    """由可讀紀錄獨立找出內部與邊緣空白；不借用 U4 的空白判定。"""
    if type(current_interval) is not int or current_interval <= 0 or start > end:
        raise SeriesError('資金費區間不合法')
    floor = decimal_value(minimum_rate)
    if floor < 0:
        raise SeriesError('估計費率下限不得為負')
    times = sorted(t for t in rows if start <= t <= end)
    result = {t: {'t': t, 'rate': decimal_text(rows[t]), 'estimated': False} for t in times}
    def estimate(t, rate):
        if start <= t <= end and t not in result:
            result[t] = {'t': t, 'rate': decimal_text(max(floor, rate)), 'estimated': True}
    if not times:
        for t in range(((start+current_interval-1)//current_interval)*current_interval,
                       end+1, current_interval):
            estimate(t, floor)
    else:
        distances = [b-a for a,b in zip(times,times[1:])]
        left = distances[0] if distances else current_interval
        right = distances[-1] if distances else current_interval
        for t in range(times[0]-left, start-1, -left):
            estimate(t, abs(rows[times[0]]))
        for t in range(times[-1]+right, end+1, right):
            estimate(t, abs(rows[times[-1]]))
        for i, distance in enumerate(distances):
            neighbors = ([distances[i-1]] if i else []) + ([distances[i+1]] if i+1<len(distances) else [])
            if not neighbors or distance <= min(neighbors):
                continue
            step = min(neighbors)
            count = max(1, int((Decimal(distance)/step).to_integral_value(rounding=ROUND_HALF_UP))-1)
            for k in range(1,count+1):
                estimate(times[i]+k*step, max(abs(rows[times[i]]),abs(rows[times[i+1]])))
    return [result[t] for t in sorted(result)]


class Account:
    """線性期貨平均成本記帳；名目不從現金扣除，也不加回權益。"""

    def __init__(self, initial_cash):
        self.cash = decimal_value(initial_cash)
        self.positions = {}
        self.basis = {}

    @precise
    def fill(self, symbol, quantity, price, fee):
        old = self.positions.get(symbol, Decimal(0))
        basis = self.basis.get(symbol, price)
        if old * quantity < 0:
            self.cash += min(abs(old), abs(quantity)) * (price-basis) * (1 if old>0 else -1)
        new = old+quantity
        if not old or old*quantity>0:
            self.basis[symbol] = (abs(old)*basis+abs(quantity)*price)/abs(new)
        elif old*new < 0:
            self.basis[symbol] = price
        self.cash -= fee
        if new:
            self.positions[symbol] = new
        else:
            self.positions.pop(symbol, None)
            self.basis.pop(symbol, None)

    @precise
    def equity(self, prices):
        return self.cash + sum((q*(prices[s]-self.basis[s]) for s,q in self.positions.items()),Decimal(0))


@precise
def select_grid_point(grid, neighborhood, scores):
    """僅由已記錄成績重推合格與選擇；不重新執行假說的 score。"""
    if not grid or len(grid)!=len(scores):
        raise SeriesError('網格與成績長度不符')
    values = [decimal_value(s) for s in scores]
    # 只接受預登記的軸定義，鄰點由規則推導，不能由索引清單任意刪除。
    if isinstance(neighborhood, dict) and set(neighborhood)=={'numeric','categorical'}:
        axes = neighborhood['numeric']; categories = neighborhood['categorical']
        if not isinstance(axes,dict) or not isinstance(categories,list) or len(set(categories))!=len(categories):
            raise SeriesError('鄰域軸定義不合法')
        if set(axes)&set(categories) or any(set(point)!=set(axes)|set(categories) for point in grid):
            raise SeriesError('鄰域軸與網格不符')
        for vals in axes.values():
            if not isinstance(vals,list) or not vals:
                raise SeriesError('數值軸必須有依序列出的取值')
            parsed=[decimal_value(str(value)) for value in vals]
            if any(a>=b for a,b in zip(parsed,parsed[1:])):
                raise SeriesError('數值軸必須嚴格遞增且不重複')
        try:
            neighbors = [[j for j,other in enumerate(grid)
                          if all(abs(vals.index(point[k])-vals.index(other[k]))<=1 for k,vals in axes.items())
                          and all(point[k]==other[k] for k in categories)] for point in grid]
        except ValueError as exc:
            raise SeriesError('網格值不在鄰域軸') from exc
    else:
        raise SeriesError('鄰域須為預登記的數值／類別軸，不接受索引清單')
    for i, group in enumerate(neighbors):
        if (not isinstance(group,list) or i not in group or len(set(group))!=len(group) or
                any(type(j) is not int or not 0<=j<len(grid) for j in group)):
            raise SeriesError('鄰域索引不合法')
    means = [sum((values[j] for j in group),Decimal(0))/len(group) for group in neighbors]
    qualified = [values[i]>0 and sum(values[j]>0 for j in group)*2>len(group)
                 for i,group in enumerate(neighbors)]
    candidates = [i for i,yes in enumerate(qualified) if yes]
    selected = max(candidates,key=lambda i:(means[i],-i)) if candidates else None
    if selected is not None and means[selected]<=0:
        selected = None
    return {'grid_scores':list(scores),'neighborhood_means':[decimal_text(x) for x in means],
            'qualified':qualified,'selected':selected,
            'selected_minus_neighborhood':None if selected is None else decimal_text(values[selected]-means[selected]),
            'no_trade':selected is None}


def score_intervals(config):
    windows = [interval(w) for w in config['score_windows']]
    if not windows or windows != sorted(windows) or any(a[1]>b[0] for a,b in zip(windows,windows[1:])):
        raise SeriesError('計分窗重疊或順序不符')
    merged = []
    for a,b in windows:
        if merged and merged[-1][1]==a:
            merged[-1]=(merged[-1][0],b)
        else:
            merged.append((a,b))
    return merged


def _check_config(data, run, *, _hold_folds=False):
    c=run['run_config'];m=data.manifest
    if data.turnover is None and not _historical_run(run):
        raise SeriesError('VERIFICATION_EVIDENCE_REQUIRED')
    exact_keys(run,('schema_version','materialization_sha256','run_config_sha256','run_config',
        'image_digest','docker_argv','algorithm_config_sha256','algorithm_files','base_symbol_properties_sha256',
        'started_at','ended_at','exit_code','lean_log_sha256','mode','status','failure_reason','failure_t',
        'steps','decisions','orders','fills','voided','funding','endpoint_funding','fits',
        'unexplained_cash_residual','fill_forward_bars'))
    exact_keys(c,('trial_id','materialization_sha256','code_commit','engine_commit','symbols',
        'initial_cash','leverage','gross_exposure_cap','decision_resolution','sharpe_frequency_seconds',
        'warmup','score_windows','folds','cost','model_artifact','random_seed','strategy','algorithm','mode'),
        ('fit_window',))
    exact_keys(c['cost'],('taker_fee_rate','stress_fee_rate','slippage_tiers_bps','untradeable_below_turnover',
        'order_cap_fraction','forced_reduce_penalty_bps','slippage_multiplier','funding_delta',
        'funding_blank_min_rate','liquidity_window_days'))
    if run['schema_version']!='r8_lean_run_v1' or run['status'] not in ('completed','failed'):
        raise SeriesError('執行 schema 或狀態不符')
    if run['mode']!=c['mode'] or c['mode'] not in ('validation','trial','verification'):
        raise SeriesError('執行模式不符')
    if (type(run['started_at']) is not int or type(run['ended_at']) is not int or
            run['started_at']>run['ended_at']):
        raise SeriesError('執行起訖須為遞增的 UTC 毫秒')
    if run['status']=='completed' and (run['failure_reason'] is not None or run['failure_t'] is not None):
        raise SeriesError('完成狀態與失敗欄位矛盾')
    if run['status']=='failed' and (run['failure_reason'] not in FAILURES or
            run['failure_t'] is not None and type(run['failure_t']) is not int):
        raise SeriesError('失敗原因或時刻不合法')
    if run['failure_reason']=='gross_exposure_cap' and run['failure_t'] is None:
        raise SeriesError('曝險失敗必須提供可重現的 failure_t')
    if (run['materialization_sha256']!=data.sha256 or c['materialization_sha256']!=data.sha256 or
            run['run_config_sha256']!=digest(canonical(c))):
        raise SeriesError('執行／物化設定雜湊不符')
    if run['algorithm_config_sha256']!=digest(canonical({k:v for k,v in c.items() if k!='mode'})):
        raise SeriesError('容器設定雜湊不符')
    if c['symbols']!=m['strategy_symbols'] or c['warmup']!=m['warmup']:
        raise SeriesError('標的或暖機不符')
    if type(c['random_seed']) is not int or c['decision_resolution'] not in ('hour','day'):
        raise SeriesError('種子或決策頻率不合法')
    if type(c['sharpe_frequency_seconds']) is not int or c['sharpe_frequency_seconds']<=0:
        raise SeriesError('Sharpe 頻率不合法')
    if c['sharpe_frequency_seconds'] % (HOUR//1000):
        raise SeriesError('小時資料的 Sharpe 頻率須為整小時')
    if not 0<decimal_value(c['gross_exposure_cap'])<=1 or decimal_value(c['initial_cash'])<=0:
        raise SeriesError('權益或曝險上限不合法')
    windows=score_intervals(c)
    if (not _hold_folds and c['mode']=='validation' and not c['folds'] and
            [interval(w) for w in c['score_windows']] != [(data.start,data.end)]):
        raise SeriesError('validation 無摺表時計分窗必須恰為物化 window')
    if any(a<data.start or b>data.end for a,b in windows):
        raise SeriesError('計分窗超出物化範圍')
    if c['folds'] and [interval(f['score_window']) for f in c['folds']]!=[interval(w) for w in c['score_windows']]:
        raise SeriesError('摺表與計分窗不符')
    if run['mode']!='validation' and m['purpose']!='research':
        raise SeriesError('研究不可使用驗證物化')
    return c


@precise
def replay(data, run, *, cost=None, stop_on_recorded_failure=True, _hold_folds=False):
    """從來源列與決策重建，觀測到的成交／現金值不作計算輸入。"""
    c=_check_config(data,run,_hold_folds=_hold_folds);cost=copy.deepcopy(cost or c['cost'])
    windows=score_intervals(c);ends={b for a,b in windows};symbols=c['symbols']
    if _hold_folds:
        ends.update(interval(w)[1] for w in c['score_windows'])
    starts={interval(w)[0] for w in c['score_windows']}
    out={k:[] for k in ('orders','fills','voided','funding','endpoint_funding','steps')}
    out.update({'failure_reason':None,'failure_t':None,'fit_errors':[],
                'max_actual_gross_exposure':'0','delayed_fills':[]})
    if stop_on_recorded_failure and run['status']=='failed' and run['failure_t'] is None:
        return out
    account=Account(c['initial_cash']);pending={};number=0;latest=None
    decision_rows=run['decisions']
    external_failure=(stop_on_recorded_failure and run['status']=='failed' and
                      run['failure_reason']!='gross_exposure_cap')
    if external_failure:
        decision_rows=[d for d in decision_rows if d['t']<run['failure_t']]
    if any(type(d['t']) is not int for d in decision_rows) or len({d['t'] for d in decision_rows})!=len(decision_rows):
        raise SeriesError('決策時間重複或不合法')
    if [d['t'] for d in decision_rows]!=sorted(d['t'] for d in decision_rows):
        raise SeriesError('決策時間不遞增')
    decisions={d['t']:d['targets'] for d in decision_rows}
    for targets in decisions.values():
        for target in targets.values():
            if set(target) not in ({'weight'},{'quantity'}):
                raise SeriesError('目標欄位不符')
            if 'quantity' in target and c['mode']!='validation':
                raise SeriesError('只有 validation 允許 quantity 目標')
            decimal_value(next(iter(target.values())))
    no_trade=set();flatten_waiting={}
    if (len(run['fits'])>len(c['folds']) or
            run['status']=='completed' and len(run['fits'])!=len(c['folds'])):
        out['fit_errors'].append('fits.count')
    if run['status']=='failed' and run['failure_t'] is not None:
        required=sum(interval(f['score_window'])[0]<run['failure_t'] for f in c['folds'])
        if len(run['fits'])<required:
            out['fit_errors'].append('fits.count')
    for i,fold in enumerate(c['folds']):
        if external_failure and interval(fold['score_window'])[0]>=run['failure_t']:
            continue
        if i>=len(run['fits']):
            continue
        fit=run['fits'][i]
        exact_keys(fit,('fold','fit_window','selection','params','model_sha256'))
        selected=select_grid_point(c['strategy']['grid'],c['strategy']['neighborhood'],fit['selection']['grid_scores'])
        expected=None if selected['no_trade'] else c['strategy']['grid'][selected['selected']]
        if (fit['fold']!=i or fit['fit_window']!=fold['fit_window'] or
                fit['selection']!=selected or fit['params']!=expected or
                (selected['no_trade'] and fit['model_sha256'] is not None) or
                (not selected['no_trade'] and
                 (not isinstance(fit['model_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',fit['model_sha256'])))):
            out['fit_errors'].append('fits.'+str(i))
        if selected['no_trade']:
            no_trade.add(i)
    times=sorted({t+HOUR for s in data.symbols for t in data.hourly[s]}|
                 (starts|ends if _hold_folds else set()))
    time_set=set(times)
    if any(t not in time_set for t in decisions):
        raise SeriesError('決策不在可送達時間步')
    execution_end=data.end
    schedules=[]
    for symbol in symbols:
        delivery=data.manifest['delistings'].get(symbol,{}).get('deliveryTime',data.end)
        for event in funding_schedule(data.funding[symbol],data.warm_start,min(data.end,delivery),
                                      data.manifest['funding_interval_ms'][symbol],cost['funding_blank_min_rate']):
            schedules.append({**event,'symbol':symbol})
    schedules.sort(key=lambda x:(x['t'],x['symbol']));funding_cursor=0;delisted=set()
    position_times={s:[] for s in symbols};position_values={s:[] for s in symbols}
    def prices(t):
        return {s:data.close(s,t) for s in account.positions}
    def fail(reason,t):
        out['failure_reason']=reason;out['failure_t']=t
    def cancel(symbol,t,reason,replaced_by=None):
        if symbol not in pending:
            return
        for order,leg,opening in pending.pop(symbol):
            order['status']='cancelled';order['cancel_t']=t;order['cancel_reason']=reason
            if reason=='replaced':
                order['replaced_by']=replaced_by
    def fill(order,quantity,price,bps,fee,change_t,kind):
        account.fill(order['symbol'],quantity,price,fee);order['status']='filled'
        s=order['symbol']
        position_times[s].append(change_t)
        position_values[s].append(account.positions.get(s,Decimal(0)))
        out['fills'].append({'order_id':order['order_id'],'decision_t':order['decision_t'],
                             'change_t':change_t,'symbol':order['symbol'],'quantity':decimal_text(quantity),
                             'price':decimal_text(price),'slippage_bps':decimal_text(bps),
                             'fee':decimal_text(fee),'kind':kind})
    def liquidate(symbol,t,kind):
        nonlocal number
        quantity=account.positions.get(symbol,Decimal(0))
        if not quantity:
            return
        bps=decimal_value(cost['forced_reduce_penalty_bps'])*decimal_value(cost['slippage_multiplier'])
        if _hold_folds and kind=='score_end_liquidation':
            median,_,_=data.liquidity(symbol,t,cost)
            tier=next((item for item in cost['slippage_tiers_bps']
                       if median>=decimal_value(item['min_turnover'])),None)
            if tier is None:
                raise SeriesError('BTC 持有基準缺少可用流動性分級')
            bps=decimal_value(tier['bps'])*decimal_value(cost['slippage_multiplier'])
        if kind=='delisting_settlement':
            rows=[(x,data.hourly[symbol][x]) for x in data.times[symbol] if x<t]
            if len(rows)<2:
                raise SeriesError('下架結算缺少兩根 K 線')
            price,fee=delisting_cost(quantity,rows[-1][1],rows[-2][1],bps,cost['taker_fee_rate'])
        else:
            price,fee=fill_cost(-quantity,data.close(symbol,t),bps,cost['taker_fee_rate'])
        number+=1
        order={'order_id':number,'kind':kind,'decision_t':t,'symbol':symbol,
               'quantity':decimal_text(-quantity),'status':'filled'}
        out['orders'].append(order);fill(order,-quantity,price,bps,fee,t,kind)
    def funding(event,endpoint=False):
        t=event['t'];s=event['symbol']
        left=bisect.bisect_left(position_times[s],t)-1
        right=bisect.bisect_right(position_times[s],t)-1
        before=position_values[s][left] if left>=0 else Decimal(0)
        after=position_values[s][right] if right>=0 else Decimal(0)
        if not before and not after:
            return
        price=data.funding_mark(s,t)[0]
        amount=funding_amount(before,after,price,event['rate'],cost['funding_delta'],estimated=event['estimated'])
        row={'t':t,'symbol':s,'q_before':decimal_text(before),'q_after':decimal_text(after),
             'price':decimal_text(price),'rate':event['rate'],'amount':decimal_text(amount),'estimated':event['estimated']}
        out['endpoint_funding' if endpoint else 'funding'].append(row)
        if not endpoint:
            account.cash+=amount
    settled_ends=set()
    def settle(t, include_current_end):
        # 沒有送達步的終點，於下一步或結束時處理，但仍以原終點的資料與時間入帳。
        events=[(e,1,'') for e in ends-settled_ends if e<t or include_current_end and e==t]
        for s in symbols:
            delivery=data.manifest['delistings'].get(s,{}).get('deliveryTime')
            if delivery is not None and delivery<=t and s not in delisted:
                events.append((delivery,0,s))
        for event_t,kind,s in sorted(events):
            if kind==0:
                cancel(s,t,'delivery');liquidate(s,event_t,'delisting_settlement');delisted.add(s)
            else:
                for symbol in sorted(list(pending)):
                    cancel(symbol,t,'score_end')
                for symbol in sorted(list(account.positions)):
                    liquidate(symbol,event_t,'score_end_liquidation')
                settled_ends.add(event_t)
    for t in times:
        if external_failure and t>=run['failure_t']:
            break
        if stop_on_recorded_failure and run['status']=='failed' and run['failure_t'] is not None and t>run['failure_t']:
            break
        # 下一根開盤的成交在下一個送達步驟才入帳。
        for s in sorted(list(pending)):
            legs=pending[s]
            if legs and legs[0][2] is not None and legs[0][2]+HOUR<=t:
                for order,leg,opening in legs:
                    q=decimal_value(leg['quantity']);bps=decimal_value(leg['slippage_bps'])
                    price,fee=fill_cost(q,data.hourly[s][opening]['open'],bps,cost['taker_fee_rate'])
                    fill(order,q,price,bps,fee,opening,leg['kind'])
                    if opening>order['decision_t']:
                        out['delayed_fills'].append({'symbol':s,'t':opening})
                pending.pop(s)
        settle(t,True)
        if latest:
            lp,le=latest
            exposure=sum((abs(q*lp[s]) for s,q in account.positions.items()),Decimal(0))/le
            if exposure>decimal_value(c['gross_exposure_cap']):
                fail('gross_exposure_cap',t);break
        active_fold=next((i for i,f in enumerate(c['folds']) if interval(f['score_window'])[0]<=t<interval(f['score_window'])[1]),None)
        valid={s for s in symbols if s not in delisted and data.manifest['first_bar'][s] is not None
               and data.manifest['first_bar'][s]+HOUR<=t and
               (_hold_folds or t-HOUR in data.hourly[s])}
        flatten=active_fold in no_trade
        targets=decisions.get(t)
        if flatten:
            if targets is not None:
                fail('invalid_decision',t);break
            if active_fold not in flatten_waiting:
                # 折啟用時先取消所有待成交訂單，連不可見標的也不能保留。
                for s in sorted(list(pending)):
                    cancel(s,t,'no_trade')
                flatten_waiting[active_fold]=set(symbols)-valid
            else:
                # 缺漏部位只在恢復可見的第一步平倉；不替換已送出的平倉單。
                recovered=flatten_waiting[active_fold]&valid
                flatten_waiting[active_fold]-=recovered
                valid={s for s in recovered if account.positions.get(s,Decimal(0))}
            targets={s:{'weight':'0'} for s in valid} if valid else None
        if targets is not None:
            if (set(targets)!=valid or not flatten and c['decision_resolution']=='day' and t%DAY or
                    t in ends and not (_hold_folds and t in starts) or
                    not any(a<=t<b for a,b in windows)):
                fail('invalid_decision',t);break
            equity=account.equity(prices(t))
            # 缺漏中的待成交標的雖不交給策略，仍須保留成交後曝險檢查的計價基礎。
            decision_prices={s:data.close(s,t) for s in valid|set(account.positions)|set(pending)}
            if equity<=0:
                fail('gross_exposure_cap',t);break
            desired=dict(account.positions);plans=[]
            for s in sorted(targets):
                target=targets[s];price=decision_prices[s];prop=data.properties[s]
                wanted=(target_quantity(equity,target['weight'],price,prop['qty_step']) if 'weight' in target
                        else decimal_value(target['quantity']))
                if 'quantity' in target:
                    # 驗證模式的固定數量與 U5 相同，分段前依步長向零取整。
                    step=decimal_value(prop['qty_step'])
                    wanted=(wanted/step).to_integral_value(rounding=ROUND_DOWN)*step
                median,hourly,enough=data.liquidity(s,t,cost)
                legs=order_segments(account.positions.get(s,Decimal(0)),wanted,price,prop['min_qty'],
                                    prop['min_notional'],median,hourly,enough,cost)
                plans.append((s,legs))
                for leg in legs:
                    if 'reason' not in leg:
                        desired[s]=desired.get(s,Decimal(0))+decimal_value(leg['quantity'])
            # 先檢查整批目標；拒絕的決策不得取消既有訂單或產生任何訂單事件。
            gross=sum((abs(q*decision_prices[s]) for s,q in desired.items() if q),Decimal(0))/equity
            if gross>decimal_value(c['gross_exposure_cap']):
                fail('gross_exposure_cap',t);break
            latest=(decision_prices,equity)
            for s,legs in plans:
                if not legs:
                    cancel(s,t,'replaced')
                    continue
                number+=1;cancel(s,t,'replaced',number)
                pending[s]=[]
                for leg in legs:
                    order={'order_id':number,'kind':'no_trade_flatten' if flatten else 'strategy',
                           'decision_t':t,'symbol':s,'quantity':leg['quantity'],
                           'status':'voided' if 'reason' in leg else 'pending'}
                    out['orders'].append(order)
                    if 'reason' in leg:
                        out['voided'].append({k:order[k] for k in ('order_id','decision_t','symbol','quantity')}|{'reason':leg['reason']})
                    else:
                        index=bisect.bisect_left(data.times[s],t)
                        opening=data.times[s][index] if index<len(data.times[s]) else None
                        if opening is not None and (opening>=next(b for a,b in windows if a<=t<b) or
                                opening>=data.manifest['delistings'].get(s,{}).get('deliveryTime',data.end+1)):
                            opening=None
                        pending[s].append((order,leg,opening))
                if not pending[s]:
                    pending.pop(s)
        while funding_cursor<len(schedules) and schedules[funding_cursor]['t']<t:
            funding(schedules[funding_cursor]);funding_cursor+=1
        eq=account.equity(prices(t))
        actual=sum((abs(q*data.close(s,t)) for s,q in account.positions.items()),Decimal(0))/eq if eq>0 else Decimal(0)
        out['max_actual_gross_exposure']=decimal_text(max(decimal_value(out['max_actual_gross_exposure']),actual))
        out['steps'].append({'t':t,'cash':decimal_text(account.cash),'equity':decimal_text(eq),
                             'positions':{s:decimal_text(q) for s,q in sorted(account.positions.items())}})
        if stop_on_recorded_failure and run['status']=='failed' and run['failure_t']==t:
            break
    if run['status']=='completed' or not stop_on_recorded_failure:
        if out['failure_reason'] is None:
            settle(data.end,True)
            # 結束回呼先補記最後時間步之後的資金費；只有 window.end 屬 endpoint。
            while funding_cursor<len(schedules) and schedules[funding_cursor]['t']<=execution_end:
                event=schedules[funding_cursor]
                funding(event,event['t']==execution_end);funding_cursor+=1
    # U5 只輸出已終結的訂單腿；失敗時仍待成交的腿沒有觀測事件。
    out['orders']=[o for o in out['orders'] if o['status']!='pending']
    # 穩定排序保留同一複合訂單先減曝險、再增曝險的兩段順序。
    for key in ('orders','voided'):
        out[key].sort(key=lambda row:row['order_id'])
    out['fills'].sort(key=lambda row:(row['change_t'],row['order_id']))
    for key in ('funding','endpoint_funding'):
        out[key].sort(key=lambda row:(row['t'],row['symbol']))
    return out


def _inputs(materialization, run):
    record=run if isinstance(run,dict) else load_json(run)[0]
    data=materialization if isinstance(materialization,Materialization) else Materialization(
        materialization, historical=_historical_run(record))
    return data,record


def _observed_prefix(data, run):
    """外部失敗只比較失敗步之前已送達的事件與訂單狀態。"""
    cutoff=run['failure_t'];prefix=copy.deepcopy(run)
    times=sorted({t+HOUR for rows in data.hourly.values() for t in rows})
    def received(t, strict=False):
        i=(bisect.bisect_right if strict else bisect.bisect_left)(times,t)
        return times[i] if i<len(times) else float('inf')
    def fill_time(row):
        t=row['change_t']
        return received(t if row['kind'] in ('delisting_settlement','score_end_liquidation') else t+HOUR)
    prefix['fills']=[r for r in run['fills'] if fill_time(r)<cutoff]
    prefix['funding']=[r for r in run['funding'] if received(r['t'],True)<cutoff]
    prefix['endpoint_funding']=[]
    prefix['steps']=[r for r in run['steps'] if r['t']<cutoff]
    prefix['voided']=[r for r in run['voided'] if r['decision_t']<cutoff]
    prefix['orders']=[]
    filled={(r['order_id'],r['quantity']) for r in prefix['fills']}
    for raw in run['orders']:
        created=(received(raw['decision_t']) if raw['kind'] in
                 ('delisting_settlement','score_end_liquidation') else raw['decision_t'])
        if created>=cutoff:
            continue
        order=copy.deepcopy(raw)
        if order.get('cancel_t',-1)>=cutoff:
            continue
        if order['status']=='filled' and (order['order_id'],order['quantity']) not in filled:
            continue
        prefix['orders'].append(order)
    prefix['fill_forward_bars']=[r for r in run['fill_forward_bars'] if r['t']<cutoff]
    prefix['unexplained_cash_residual']={
        'per_step':[r for r in run['unexplained_cash_residual']['per_step'] if r['t']<cutoff],
        'total':'0'}
    return prefix


def _compare(expected, actual, location, cash_tolerance, errors, stats):
    if isinstance(expected,dict):
        if not isinstance(actual,dict) or set(expected)!=set(actual):
            errors.append(location+':keys');return
        for k,v in expected.items():
            _compare(v,actual[k],location+'.'+k,cash_tolerance,errors,stats)
    elif isinstance(expected,list):
        if not isinstance(actual,list) or len(expected)!=len(actual):
            errors.append(location+':count');return
        for i,(a,b) in enumerate(zip(expected,actual)):
            _compare(a,b,location+'.'+str(i),cash_tolerance,errors,stats)
    elif isinstance(expected,str) and location.rsplit('.',1)[-1] in ('price','fee','amount','cash','equity','quantity','slippage_bps','q_before','q_after','rate'):
        try:
            left,right=decimal_value(expected),decimal_value(actual)
        except SeriesError:
            errors.append(location+':decimal');return
        difference=abs(left-right);field=location.rsplit('.',1)[-1]
        if difference>stats['max_difference']:
            stats.update(max_difference=difference,max_location=location)
        tolerance=(cash_tolerance if field in ('cash','equity') else
                   max(abs(left)*PRICE_REL_TOL,CASH_ABS_TOL) if field in ('fee','amount') else
                   abs(left)*PRICE_REL_TOL if field=='price' else Decimal(0))
        if difference>tolerance:
            errors.append(location)
    elif type(expected) is not type(actual) or expected!=actual:
        errors.append(location)


def _cash_residual_summary(run, end):
    """§16：獨立使用紀錄中的框架現金；total 僅作記錄，不參與判定。"""
    cash_by_time={row['t']:row['cash'] for row in run['steps']}
    maximum=Decimal(0);first=None
    for row in run['unexplained_cash_residual']['per_step']:
        residual=decimal_value(row['residual']).copy_abs()
        if not residual:
            continue
        cash_text=cash_by_time.get(row['t'])
        if row['t']==end and cash_by_time:
            # on_end_of_algorithm 可在沒有新 step 時另記一筆殘差。
            cash_text=cash_by_time[max(cash_by_time)]
        if cash_text is None:
            raise SeriesError('現金殘差缺少對應時間步')
        cash=decimal_value(cash_text)
        exponent=max(cash.adjusted()-27,-28) if cash else -28
        ulp=Decimal(1).scaleb(exponent)
        maximum=max(maximum,residual/ulp)
        if residual>100*ulp and (first is None or row['t']<first):
            first=row['t']
    return maximum,first


@precise
def recompute(materialization, run):
    data,run=_inputs(materialization,run);expected=replay(data,run)
    observed=run
    if run['status']=='failed':
        if run['failure_t'] is None:
            observed={**run,**{key:[] for key in ('orders','fills','voided','funding','endpoint_funding','steps')},
                      'fill_forward_bars':[], 'unexplained_cash_residual':{'per_step':[],'total':'0'}}
        elif run['failure_reason']!='gross_exposure_cap':
            observed=_observed_prefix(data,run)
    errors=list(expected['fit_errors']);stats={'max_difference':Decimal(0),'max_location':None}
    counts={};cash_tol=decimal_value(run['run_config']['initial_cash'])*EQUITY_FRACTION_TOL
    for key in ('orders','fills','voided','funding','endpoint_funding','steps'):
        counts[key]=len(expected[key]);_compare(expected[key],observed[key],key,cash_tol,errors,stats)
    if observed['fill_forward_bars']:
        errors.append('fill_forward_bars')
    # 外部失敗的事件重播只比對前綴，殘差判定仍涵蓋整份 run（含失敗步）。
    max_residual_ulps,first_residual_t=_cash_residual_summary(run,data.end)
    if first_residual_t is not None:
        errors.append('unexplained_cash_residual')
    if expected['failure_reason'] is not None:
        if run['status']!='failed' or (run['failure_reason'],run['failure_t'])!=(expected['failure_reason'],expected['failure_t']):
            errors.append('failure_reason/failure_t')
    elif run['failure_reason']=='gross_exposure_cap' and run['failure_t'] is not None:
        errors.append('gross_exposure_cap:not_reproduced')
    totals={}
    for name,key,field in [('fees','fills','fee'),('funding','funding','amount'),('endpoint_funding','endpoint_funding','amount')]:
        exp=sum((decimal_value(row[field]) for row in expected[key]),Decimal(0))
        amount=sum((decimal_value(row[field]) for row in observed[key]),Decimal(0))
        totals[name]={'expected':decimal_text(exp),'observed':decimal_text(amount)}
        _compare(decimal_text(exp),decimal_text(amount),'totals.'+field,cash_tol,errors,stats)
    return {'schema_version':'r8_recompute_report_v1','materialization_sha256':data.sha256,
            'run_sha256':digest(canonical(run)),'recompute_passed':not errors and run['status']=='completed',
            'counts':counts,'max_difference':decimal_text(stats['max_difference']),
            'max_location':stats['max_location'],'differences':errors,'totals':totals,
            'max_cash_residual_ulps':decimal_text(max_residual_ulps),
            'first_unexplained_cash_residual_t':first_residual_t,
            'max_actual_gross_exposure':expected['max_actual_gross_exposure']}


def periods(config):
    f=config['sharpe_frequency_seconds']
    if type(f) is not int or f<=0:
        raise SeriesError('期數頻率不合法')
    result=set()
    for window in config['score_windows']:
        a,b=interval(window);unit=f*1000
        result.update(range(((a+unit-1)//unit)*f,(b//unit)*f,f))
    return sorted(result)


class History:
    """以單調查詢游標重建實際部位變動時刻的期貨帳戶。"""
    def __init__(self, config, reconstructed):
        self.account=Account(config['initial_cash'])
        self.fills=sorted(reconstructed['fills'],key=lambda f:(f['change_t'],f['order_id']))
        self.funding=sorted(reconstructed['funding']+reconstructed['endpoint_funding'],key=lambda f:(f['t'],f['symbol']))
        self.fi=self.fu=0;self.last=-float('inf')

    def advance(self,t,*,after=False,endpoint=False):
        if t<self.last:
            raise SeriesError('History 必須單調查詢')
        self.last=t
        while self.fi<len(self.fills):
            f=self.fills[self.fi]
            include=f['change_t']<t or f['change_t']==t and (after or endpoint and f['kind'] in ('score_end_liquidation','delisting_settlement'))
            if not include:
                break
            self.account.fill(f['symbol'],decimal_value(f['quantity']),decimal_value(f['price']),decimal_value(f['fee']));self.fi+=1
        while self.fu<len(self.funding):
            f=self.funding[self.fu]
            if f['t']>t or f['t']==t and not endpoint:
                break
            self.account.cash+=decimal_value(f['amount']);self.fu+=1
        return self.account


class PositionIndex:
    """已完成重算的累計部位索引；查詢成本不隨整份成交紀錄線性增長。"""
    def __init__(self,fills):
        self.times={};self.values={}
        for fill in sorted(fills,key=lambda row:row['change_t']):
            symbol=fill['symbol'];times=self.times.setdefault(symbol,[]);values=self.values.setdefault(symbol,[])
            times.append(fill['change_t'])
            values.append((values[-1] if values else Decimal(0))+decimal_value(fill['quantity']))

    def at(self,symbol,t,inclusive=False):
        times=self.times.get(symbol,[])
        i=(bisect.bisect_right if inclusive else bisect.bisect_left)(times,t)-1
        return self.values[symbol][i] if i>=0 else Decimal(0)

    def held(self,symbol,start,end):
        if self.at(symbol,start,True):
            return True
        times=self.times.get(symbol,[])
        a=bisect.bisect_right(times,start);b=bisect.bisect_left(times,end)
        return any(self.values.get(symbol,[])[a:b])


def filled_periods(data,config,reconstructed,grid):
    f=config['sharpe_frequency_seconds']*1000;flag=set();positions=PositionIndex(reconstructed['fills'])
    ends={b for a,b in score_intervals(config)};starts=[p*1000 for p in grid]
    def mark(t):
        i=bisect.bisect_right(starts,t)-1
        if i>=0 and starts[i]<=t<starts[i]+f:
            flag.add(grid[i])
        if t in ends:
            i=bisect.bisect_left(starts,t)-1
            if i>=0 and starts[i]+f==t:
                flag.add(grid[i])
    def overlapping(a,b):
        lo=bisect.bisect_right(starts,a-f);hi=bisect.bisect_left(starts,b)
        return grid[lo:hi]
    for s in config['symbols']:
        bars=data.times[s]
        delivery=data.manifest['delistings'].get(s,{}).get('deliveryTime',data.end)
        gaps=[]
        for left,right in zip(bars,bars[1:]):
            if right>left+HOUR:
                gaps.append((left+HOUR,min(right,delivery),right))
        if bars and bars[-1]+HOUR<min(data.end,delivery):
            gaps.append((bars[-1]+HOUR,min(data.end,delivery),None))
        for ga,gb,recovery in gaps:
            if ga>=gb or not positions.at(s,ga):
                continue
            flag.update(overlapping(ga,gb))
            if recovery is not None and recovery<delivery:
                mark(recovery)
        raw=data.funding[s];times=sorted(raw);funding_gaps=set()
        schedule=funding_schedule(raw,data.warm_start,min(data.end,delivery),data.manifest['funding_interval_ms'][s],config['cost']['funding_blank_min_rate'])
        for row in schedule:
            t=row['t'];before=positions.at(s,t);after=positions.at(s,t,True)
            if row['estimated']:
                i=bisect.bisect_left(times,t)
                ga=times[i-1] if i else data.warm_start
                gb=times[i] if i<len(times) else min(data.end,delivery)
                funding_gaps.add((ga,gb))
                if before or after:
                    mark(t)
            if (before or after) and data.funding_mark(s,t)[1]:
                mark(t)
        for ga,gb in funding_gaps:
            for p in overlapping(ga,gb):
                a=max(p*1000,ga);b=min(p*1000+f,gb)
                if positions.held(s,a,b):
                    flag.add(p)
    for item in reconstructed['delayed_fills']:
        mark(item['t'])
    return flag


@precise
def _series_values(data,run,reconstructed):
    config=run['run_config'];grid=periods(config);f=config['sharpe_frequency_seconds']*1000
    if run['status']=='failed' and run['failure_t'] is None:
        return {'period_seconds':config['sharpe_frequency_seconds'],'filled_periods':len(grid),
                'returns':[[p,0.0] for p in grid]},0
    flagged=filled_periods(data,config,reconstructed,grid)
    failure=run['failure_t'] if run['status']=='failed' else None
    if run['status']=='failed' and failure is None:
        failure=min(a for a,b in score_intervals(config))
    ends={b for a,b in score_intervals(config)}
    history=History(config,reconstructed);equities={};produced=0
    for t in sorted({p*1000+offset for p in grid for offset in (0,f)}):
        if failure is not None and t>=failure:
            continue
        account=history.advance(t,endpoint=t in ends)
        equities[t]=account.equity({s:data.close(s,t) for s in account.positions})
    rows=[]
    for p in grid:
        a=p*1000;b=a+f
        if failure is not None and b>=failure:
            value=Decimal(0);flagged.add(p)
        else:
            if equities[a]<=0:
                raise SeriesError('期初權益不為正')
            value=equities[b]/equities[a]-1;produced+=1
        number=float(value)
        if not math.isfinite(number):
            raise SeriesError('報酬超出帳本有限數值範圍')
        rows.append([p,number])
    return {'period_seconds':config['sharpe_frequency_seconds'],'filled_periods':len(flagged),'returns':rows},produced


@precise
def make_series(materialization, run, report):
    data,run=_inputs(materialization,run)
    if not isinstance(report,dict):
        report=load_json(report)[0]
    # 檢查用入口也不信任可由呼叫者自行改成 PASS 的報告。
    actual=recompute(data,run)
    if report!=actual:
        raise SeriesError('重算報告與當次輸入不符')
    if run['status']=='completed' and not actual['recompute_passed']:
        raise SeriesError('完成執行重算不通過')
    reconstructed=replay(data,run)
    if reconstructed['fit_errors']:
        raise SeriesError('fits 選擇或參數與獨立重推不符')
    if run['failure_reason']=='gross_exposure_cap' and run['failure_t'] is not None and (
            reconstructed['failure_reason']!='gross_exposure_cap' or reconstructed['failure_t']!=run['failure_t']):
        raise SeriesError('曝險失敗未重現')
    if actual['differences']:
        raise SeriesError('失敗前綴重算有差異或更早失敗')
    values,produced=_series_values(data,run,reconstructed)
    return values,{'schema_version':'r8_series_sidecar_v1','run_sha256':digest(canonical(run)),
                   'materialization_sha256':data.sha256,'recompute_report_sha256':digest(canonical(report)),
                   'produced_periods':produced,'submitted_periods':len(values['returns']),
                   'failure_reason':run['failure_reason'],'failure_t':run['failure_t'],
                   'recompute_passed':actual['recompute_passed'],
                   'limitations':['貝塔跳空曝險以開盤價計價，接受二階近似；缺漏後大跳空時誤差較明顯。',
                                  '網格成績與模型內容不由 U6 重算；重現選擇不證明假說模型正確。']}


@precise
def ols_beta(x,y):
    """含截距 OLS；常數自變量明確回傳不足，不能當成零貝塔。"""
    if len(x)!=len(y) or len(x)<2:
        return None
    mx=sum(x,Decimal(0))/len(x);my=sum(y,Decimal(0))/len(y)
    denominator=sum(((v-mx)**2 for v in x),Decimal(0))
    if not denominator:
        return None
    beta=sum(((a-mx)*(b-my) for a,b in zip(x,y)),Decimal(0))/denominator
    return min(BETA_MAX,max(BETA_MIN,beta))


@precise
def estimate_betas(data, fit_window):
    start,end=interval(fit_window);start=max(start,end-BETA_DAYS*DAY)
    returns={}
    for s,rows in data.daily.items():
        returns[s]={t:row['close']/rows[t-DAY]['close']-1 for t,row in rows.items()
                    if t-DAY in rows and t-DAY>=start and t+DAY<=end}
    btc=returns.get('BTCUSDT',{});result={'BTCUSDT':Decimal(1)};qualified=[]
    if len(btc)>=BETA_MIN_OBSERVATIONS:
        qualified.append(Decimal(1))
    insufficient=[]
    for s in data.symbols:
        if s=='BTCUSDT':
            continue
        common=sorted(set(btc)&set(returns[s]))
        beta=ols_beta([btc[t] for t in common],[returns[s][t] for t in common]) if len(common)>=BETA_MIN_OBSERVATIONS else None
        if beta is None:
            insufficient.append(s)
        else:
            result[s]=beta;qualified.append(beta)
    if insufficient and not qualified:
        raise SeriesError('貝塔觀測不足且沒有可用的其他標的中位數')
    for s in insufficient:
        result[s]=statistics.median(qualified)
    return {s:decimal_text(v) for s,v in sorted(result.items())}


def _folds(config):
    return config['folds'] or [{'fit_window':config['warmup'],'score_window':w} for w in config['score_windows']]


@precise
def _matched_baseline(data,run,reconstructed):
    cfg=run['run_config'];grid=periods(cfg);width=cfg['sharpe_frequency_seconds']*1000
    if 'BTCUSDT' not in data.symbols:
        raise SeriesError('基準缺少 BTCUSDT')
    if run['status']=='failed' and run['failure_t'] is None:
        return {'period_seconds':cfg['sharpe_frequency_seconds'],'filled_periods':len(grid),
                'returns':[[p,0.0] for p in grid]}
    folds=_folds(cfg)
    betas=[{s:decimal_value(v) for s,v in estimate_betas(data,f['fit_window']).items()} for f in folds]
    history=History(cfg,reconstructed);rows=[];flagged=set()
    failure=run['failure_t'] if run['status']=='failed' else None
    if run['status']=='failed' and failure is None:
        failure=score_intervals(cfg)[0][0]
    btc=data.hourly['BTCUSDT'];times=data.times['BTCUSDT']
    schedule=funding_schedule(data.funding['BTCUSDT'],data.warm_start,data.end,
                              data.manifest['funding_interval_ms']['BTCUSDT'],cfg['cost']['funding_blank_min_rate'])
    fund_by_hour={}
    for f in schedule:
        hour=f['t']//HOUR*HOUR
        fund_by_hour[hour]=fund_by_hour.get(hour,Decimal(0))+decimal_value(f['rate'])
    for p in grid:
        if failure is not None and p*1000+width>=failure:
            rows.append([p,0.0]);flagged.add(p);continue
        product=Decimal(1)
        for h in range(p*1000,p*1000+width,HOUR):
            i=next((i for i,f in enumerate(folds) if interval(f['score_window'])[0]<=h<interval(f['score_window'])[1]),None)
            if i is None:
                raise SeriesError('基準時刻不在摺表中')
            before=history.advance(h)
            opening={s:data.opening(s,h) for s in before.positions}
            equity=before.equity(opening)
            if equity<=0:
                raise SeriesError('基準曝險的權益不為正')
            bminus=sum((q*opening[s]*betas[i][s] for s,q in before.positions.items()),Decimal(0))/equity
            after=history.advance(h,after=True)
            opening.update({s:data.opening(s,h) for s in after.positions if s not in opening})
            equity=after.equity(opening)
            if equity<=0:
                raise SeriesError('成交後基準權益不為正')
            b=sum((q*opening[s]*betas[i][s] for s,q in after.positions.items()),Decimal(0))/equity
            gap=inside=Decimal(0)
            if h not in btc and (bminus or b):
                flagged.add(p)
            if h in btc:
                index=bisect.bisect_left(times,h)-1
                if index>=0:
                    gap=btc[h]['open']/btc[times[index]]['close']-1
                    if times[index]<h-HOUR and bminus:
                        flagged.add(p)
                inside=btc[h]['close']/btc[h]['open']-1
            product *= (1+bminus*gap)*(1+b*inside-b*fund_by_hour.get(h,Decimal(0)))
        rows.append([p,float(product-1)])
    return {'period_seconds':cfg['sharpe_frequency_seconds'],'filled_periods':len(flagged),'returns':rows}


@precise
def _hold_baseline(data,run):
    # 同一 Decimal 記帳器，僅替換為固定逐折持有決策；邊界資金費只結算一次。
    cfg=copy.deepcopy(run['run_config']);cfg.update(symbols=['BTCUSDT'],mode='validation',
        trial_id=None,folds=[],strategy={},model_artifact=None,gross_exposure_cap='1')
    # §9.7 的全部權益持有定義為一倍；這是基準自身的部位，不受假說較低上限限制。
    fixture=copy.copy(data);fixture.manifest=copy.deepcopy(data.manifest)
    fixture.manifest['strategy_symbols']=['BTCUSDT']
    observed=copy.deepcopy(run);observed.update(run_config=cfg,mode='validation',status='completed',
        failure_reason=None,failure_t=None,fits=[],decisions=[])
    for fold in _folds(run['run_config']):
        a,b=interval(fold['score_window'])
        observed['decisions'].append({'t':a,'targets':{'BTCUSDT':{'weight':'1'}}})
    observed['run_config_sha256']=digest(canonical(cfg))
    observed['algorithm_config_sha256']=digest(canonical({k:v for k,v in cfg.items() if k!='mode'}))
    rebuilt=replay(fixture,observed,_hold_folds=True)
    if rebuilt['failure_reason']:
        raise SeriesError('固定持有基準失敗：'+rebuilt['failure_reason'])
    # 相鄰折邊界以一般 E(s) 歸期；該處關閉與重新開倉的成本一起進入新一期。
    return _series_values(fixture,observed,rebuilt)[0]


def baselines(materialization,run):
    data,run=_inputs(materialization,run);rebuilt=replay(data,run)
    return {'beta_matched_btc_v1':_matched_baseline(data,run,rebuilt),
            'btc_perp_hold_v1':_hold_baseline(data,run)}


@precise
def _net_return(data,config,rebuilt):
    history=History(config,rebuilt);product=Decimal(1)
    for a,b in score_intervals(config):
        start=history.advance(a)
        first=start.equity({s:data.close(s,a) for s in start.positions})
        end=history.advance(b,endpoint=True)
        last=end.equity({s:data.close(s,b) for s in end.positions})
        if first<=0:
            raise SeriesError('壓力期初權益不為正')
        product*=last/first
    return product-1


@precise
def stress(materialization,run):
    data,run=_inputs(materialization,run);cfg=run['run_config'];base=cfg['cost']
    def scenario(multiplier,fee):
        cost={**base,'slippage_multiplier':decimal_text(multiplier),'taker_fee_rate':fee}
        rebuilt=replay(data,run,cost=cost,stop_on_recorded_failure=run['status']=='failed')
        failed=rebuilt['failure_reason'] is not None or run['status']=='failed'
        current=copy.deepcopy(run)
        if rebuilt['failure_reason']:
            current.update(status='failed',failure_reason=rebuilt['failure_reason'],failure_t=rebuilt['failure_t'])
        values,_=_series_values(data,current,rebuilt)
        fees=sum((decimal_value(f['fee']) for f in rebuilt['fills']),Decimal(0))
        funding=sum((decimal_value(f['amount']) for f in rebuilt['funding']+rebuilt['endpoint_funding']),Decimal(0))
        slippage=Decimal(0)
        for f in rebuilt['fills']:
            q=decimal_value(f['quantity']);price=decimal_value(f['price']);bps=decimal_value(f['slippage_bps'])
            reference=price/(1+(bps if q>0 else -bps)/10000)
            slippage+=abs(q)*abs(price-reference)
        net=None if failed else _net_return(data,cfg,rebuilt)
        gross=None if net is None else net*decimal_value(cfg['initial_cash'])+fees+slippage-funding
        total_cost=fees+slippage-funding
        return {'slippage_multiplier':decimal_text(multiplier),'fee_rate':fee,
                'status':'failed' if failed else 'completed','failure_reason':current['failure_reason'],
                'failure_t':current['failure_t'],'net_return':None if net is None else decimal_text(net),
                'fees':decimal_text(fees),'funding':decimal_text(funding),'slippage':decimal_text(slippage),
                'cost_ratio':None if gross is None or gross==0 else decimal_text(total_cost/abs(gross)),
                'series':values}
    scenarios=[scenario(Decimal(m),base['taker_fee_rate']) for m in (1,2,3)]
    scenarios.append(scenario(Decimal(2),base['stress_fee_rate']))
    zero=scenario(Decimal(0),base['taker_fee_rate'])
    breakeven={'multiplier':None,'status':'unresolved','lower':None,'upper':None,
               'lower_net_return':None,'upper_net_return':None,
               'method':'bracketed_repricing; discrete quantities can create multiple crossings'}
    if zero['net_return'] is not None:
        lower=Decimal(0);lo_net=decimal_value(zero['net_return'])
        if lo_net<=0:
            breakeven.update(multiplier='0',status='nonpositive_without_slippage')
        else:
            largest=max([decimal_value(x['bps']) for x in base['slippage_tiers_bps']]+[decimal_value(base['forced_reduce_penalty_bps'])])
            bound=Decimal(10000)/largest if largest else None
            # 最後探測點取目前 Decimal 精度下 bound 的前一個可表示值。
            # 除法／乘法可能捨入；乘回最大 bps 若仍達 10000，再退一格，
            # 保證最後一點及其內的二分探測均維持有效滑價 < 10000 bps。
            last=bound.next_minus() if bound is not None else None
            while last is not None and largest*last>=10000:
                last=last.next_minus()
            upper=min(Decimal(1),last) if last is not None else Decimal(1)
            while bound is not None and upper<bound:
                probe=scenario(upper,base['taker_fee_rate'])
                if probe['net_return'] is None:
                    breakeven['status']='scenario_failed';break
                hi_net=decimal_value(probe['net_return'])
                if hi_net<=0:
                    # 迭代次數是求根演算法的精度控制，不是研究門檻。
                    for _ in range(40):
                        middle=(lower+upper)/2
                        probe=scenario(middle,base['taker_fee_rate'])
                        if probe['net_return'] is None:
                            breakeven['status']='scenario_failed';break
                        value=decimal_value(probe['net_return'])
                        if value>0:
                            lower,lo_net=middle,value
                        else:
                            upper,hi_net=middle,value
                    else:
                        breakeven.update(multiplier=decimal_text((lower+upper)/2),status='bracketed',
                                         lower=decimal_text(lower),upper=decimal_text(upper),
                                         lower_net_return=decimal_text(lo_net),upper_net_return=decimal_text(hi_net))
                    break
                lower,lo_net=upper,hi_net
                if upper==last:
                    breakeven['status']='no_crossing_in_valid_slippage_range';break
                upper=min(upper*2,last)
            else:
                breakeven['status']='no_crossing_in_valid_slippage_range'
    return {'schema_version':'r8_stress_v1','run_sha256':digest(canonical(run)),
            'materialization_sha256':data.sha256,'scenarios':scenarios,'breakeven':breakeven,
            'stress_passed':scenarios[-1]['status']=='completed' and decimal_value(scenarios[-1]['net_return'])>0,
            'decision_approximation':'決策固定；若假說依賴自身部位或權益，壓力下的真實決策可能不同。'}


P3B_U1_SHA256 = 'b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006'
ENGINE_DIRS = ('program_code/research/r8_engine', 'program_code/research/r8_ledger')
IDENTITY_RUN_KEYS = ('initial_cash','leverage','gross_exposure_cap','decision_resolution',
                     'sharpe_frequency_seconds','algorithm','engine_commit')


def _git(repo, *args):
    result = subprocess.run(['git','--no-replace-objects','-C',str(repo),*args],
                            check=False,capture_output=True)
    if result.returncode:
        raise SeriesError('Git 完整性核對失敗：'+args[0])
    return result.stdout


def verify_code(repo, run):
    """只讀本機物件、參照與來源；不 fetch、不執行候選演算法。"""
    repo=Path(repo).resolve();cfg=run['run_config']
    for key in ('code_commit','engine_commit'):
        sha=cfg[key]
        if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{40}',sha):
            raise SeriesError('必須提供完整 commit')
        if _git(repo,'rev-parse',sha+'^{commit}').strip().decode()!=sha:
            raise SeriesError('commit 不符')
    _git(repo,'merge-base','--is-ancestor',cfg['engine_commit'],'refs/remotes/origin/main')
    def tree(commit):
        result={}
        for entry in _git(repo,'ls-tree','-rz',commit,'--',*ENGINE_DIRS).split(b'\0'):
            if not entry:
                continue
            metadata,name=entry.split(b'\t',1);mode,kind,oid=metadata.split()
            if kind!=b'blob' or mode not in (b'100644',b'100755'):
                raise SeriesError('引擎來源不接受 symlink 或子模組')
            result[name.decode()]=oid
        return result
    code=tree(cfg['code_commit']);engine=tree(cfg['engine_commit'])
    if not code or code!=engine or any(not any(n.startswith(d+'/') for n in code) for d in ENGINE_DIRS):
        raise SeriesError('引擎目錄清單或內容與 main 引擎不符')
    files=run['algorithm_files'];algorithm=cfg['algorithm']['path']
    contained(repo,algorithm)
    if any(algorithm.startswith(d+'/') for d in ENGINE_DIRS):
        raise SeriesError('試驗假說不得位於引擎目錄')
    if not isinstance(files,dict) or not set(code)|{algorithm}<=set(files):
        raise SeriesError('algorithm_files 缺少演算法或主機程式')
    names=list(files)
    if _git(repo,'status','--porcelain','--untracked-files=all','--',*ENGINE_DIRS,*names).strip():
        raise SeriesError('演算法或主機程式有未提交改動')
    # git status 不含被 ignore 的額外來源；執行時的 Python bytecode cache 非來源。
    for directory in ENGINE_DIRS:
        for path in (repo/directory).rglob('*'):
            if '__pycache__' in path.parts and path.suffix=='.pyc':
                continue
            if path.is_symlink() or path.is_file() and path.relative_to(repo).as_posix() not in code:
                raise SeriesError('主機目錄含額外來源')
    for name,sha in files.items():
        path=contained(repo,name)
        raw=_git(repo,'show',cfg['code_commit']+':'+name)
        if digest(raw)!=sha or path.read_bytes()!=raw:
            raise SeriesError('演算法檔案或雜湊不符：'+name)


def _trial_query(ledger, trial):
    book=ResearchLedger(ledger)
    if not hasattr(book,'trial_record'):
        raise SeriesError('U4 trial_record 尚未整合；不得改用私有帳本查詢')
    return book.trial_record(trial)


def rematerialize(*, u1, ledger, hypothesis, window, trial, out, repo):
    """U4 只由子程序呼叫；U6 不開啟 U1 檔案，也不匯入物化實作。"""
    argv=[sys.executable,'-m','program_code.research.r8_engine.materialize',
          '--u1',str(u1),'--u1-manifest-sha256',P3B_U1_SHA256,
          '--ledger',str(ledger),'--hypothesis',hypothesis,
          '--window',window['start']+','+window['end'],'--trial',trial,'--out',str(out)]
    result=subprocess.run(argv,cwd=repo,check=False,capture_output=True)
    if result.returncode:
        raise SeriesError('U4 重新物化失敗')
    return Path(out)/'materialization.json'


def _verify_identity(data, run, record, ledger_id):
    cfg=_check_config(data,run);m=data.manifest
    if data.turnover is not None and data.turnover.binding['registration_sha256'] != record.get('preregistration_sha256'):
        raise SeriesError('驗證綁定與帳本預登記身份不符')
    configuration={'strategy_parameters':{'run':{k:cfg[k] for k in IDENTITY_RUN_KEYS},
                                          'strategy':cfg['strategy']},
                   'cost_model_parameters':cfg['cost']}
    if (record['configuration']!=configuration or
            record['configuration_sha256']!=digest(canonical(configuration)) or
            record['code_commit']!=cfg['code_commit'] or record['random_seed']!=cfg['random_seed'] or
            record['sharpe_frequency']['seconds']!=cfg['sharpe_frequency_seconds'] or
            record['sharpe_frequency']['annualized'] is not False):
        raise SeriesError('執行設定與試驗身份不符')
    for name,value in RUNTIME_METADATA.items():
        if record[name]!=value:
            raise SeriesError('執行環境身份不符：'+name)
    if run['image_digest']!=IMAGE_DIGEST:
        raise SeriesError('映像摘要不符')
    if (m['purpose']!='research' or m['ledger_id']!=ledger_id or
            m['hypothesis_id']!=record['hypothesis_id'] or m['generation']!=record['generation'] or
            interval(m['window'])!=interval(record['data_window']) or
            data.sha256!=record['manifest_sha256'] or
            {k:v['sha256'] for k,v in m['files'].items()}!=record['data_files']):
        raise SeriesError('重新物化與帳本身份不符')
    folds=record.get('folds',[])
    expected=[interval(f['score_window']) for f in folds] if record['evaluation_kind']=='out_of_sample' else [interval(record['score_window'])]
    if cfg['folds']!=folds or [interval(w) for w in cfg['score_windows']]!=expected:
        raise SeriesError('視窗或摺表與身份不符')
    if cfg.get('fit_window') is not None and interval(cfg['fit_window'])!=interval(record['fit_window']):
        raise SeriesError('擬合窗與身份不符')
    if cfg['model_artifact'] is not None:
        raise SeriesError('本版不接受 holdout 模型提交')


def submit(ledger, trial, u1, run, *, trial_query=None, materializer=None, repo=None):
    """唯一帳本寫入口；注入邊界只供離線查詢與 U4 CLI 替身測試。"""
    ledger=Path(ledger).resolve()
    if not ledger.is_dir() or not (ledger/'ledger_id.json').is_file():
        raise SeriesError('帳本必須已存在；submit 不建立帳本')
    record=load_json(run)[0]
    if record['mode']!='trial' or record['run_config']['mode']!='trial' or record['run_config']['trial_id']!=trial:
        raise SeriesError('submit 只接受同一試驗的 trial 執行')
    queried=(trial_query or _trial_query)(ledger,trial)
    exact_keys(queried, ('record','finished','status'))
    identity=queried['record']
    if not identity or identity['trial_id']!=trial or queried['finished'] is not False:
        raise SeriesError('試驗不存在或已結束')
    if identity['evaluation_kind']=='holdout_falsification':
        raise SeriesError('本版拒收 holdout_falsification')
    if (timestamp(identity['started_at'])>record['started_at'] or
            record['ended_at']>int(datetime.now(timezone.utc).timestamp()*1000)):
        raise SeriesError('執行發生於 begin_trial 之前或結束時刻在未來')
    repo=Path(repo).resolve() if repo is not None else Path(__file__).resolve().parents[3]
    verify_code(repo,record)
    with tempfile.TemporaryDirectory(prefix='r8-u6-submit-') as temporary:
        path=(materializer or rematerialize)(u1=Path(u1),ledger=ledger,
              hypothesis=identity['hypothesis_id'],window=identity['data_window'],trial=trial,
              out=Path(temporary)/'materialized',repo=repo)
        data=Materialization(path, historical=_historical_run(record))
        ledger_id=load_json(ledger/'ledger_id.json')[0]['ledger_id']
        _verify_identity(data,record,identity,ledger_id)
        report=recompute(data,record)
        values,sidecar=make_series(data,record,report)
        baseline=baselines(data,record);pressure=stress(data,record)
        artifacts={'recompute_report':report,'series':values,'baseline':baseline['beta_matched_btc_v1'],
                   'btc_perp_hold':baseline['btc_perp_hold_v1'],'stress':pressure,'sidecar':sidecar}
        provenance={k+'_sha256':digest(canonical(v)) for k,v in artifacts.items() if k!='btc_perp_hold'}
        provenance.update(materialization_sha256=data.sha256,run_sha256=digest(canonical(record)),
                          stress_scenarios=[{'slippage_multiplier':s['slippage_multiplier'],'fee_rate':s['fee_rate']}
                                            for s in pressure['scenarios']],
                          model_artifact_sha256=None,recompute_passed=report['recompute_passed'])
        stop=(identity['evaluation_kind']=='out_of_sample' and record['status']=='failed' and
              (record['failure_t'] is None or record['failure_t']>=score_intervals(record['run_config'])[0][0]))
        summary={'fits':record['fits'],'stress':pressure,'provenance':provenance,
                 'produced_periods':sidecar['produced_periods'],'failure_reason':record['failure_reason'],
                 'failure_t':record['failure_t'],'recompute_passed':report['recompute_passed'],
                 'operator_stop_required':stop,'btc_perp_hold_sha256':digest(canonical(artifacts['btc_perp_hold']))}
        # 所有拒絕檢查與計算完成後才持久化；第二次檢查避免長時間計算中來源被改動。
        verify_code(repo,record)
        if (trial_query or _trial_query)(ledger,trial)!=queried:
            raise SeriesError('產物計算期間試驗身份或狀態已改變')
        output=contained(ledger,'u6_artifacts');output.mkdir(exist_ok=True)
        for value in artifacts.values():
            raw=canonical(value);destination=output/digest(raw)
            if destination.exists():
                if destination.is_symlink() or destination.read_bytes()!=raw:
                    raise SeriesError('既有產物雜湊內容不符')
            else:
                with destination.open('xb') as stream:
                    stream.write(raw)
        def descriptor(name):
            sha=provenance[name+'_sha256']
            return {'path':str(output/sha),'sha256':sha}
        request={'status':record['status'],'returns':descriptor('series'),
                 'produced_periods':len(values['returns']),'result_summary':summary,
                 'ended_at':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}
        if identity['evaluation_kind']=='out_of_sample':
            request['baselines']={'beta_matched_btc_v1':descriptor('baseline')}
        return ResearchLedger(ledger).finish_trial(trial,request)


def argument_parser():
    parser=argparse.ArgumentParser(description='U6 獨立重算、序列與帳本提交',allow_abbrev=False)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('recompute','series','baseline','stress'):
        sub=commands.add_parser(name,allow_abbrev=False)
        for option in ('materialization','run','out'):
            sub.add_argument('--'+option,required=True,type=Path)
        if name=='series':
            sub.add_argument('--recompute',required=True,type=Path)
    sub=commands.add_parser('submit',allow_abbrev=False)
    for option in ('ledger','trial','u1','run'):
        sub.add_argument('--'+option,required=True)
    return parser


def main(argv=None):
    args=argument_parser().parse_args(argv)
    try:
        if args.command=='submit':
            print(canonical(submit(args.ledger,args.trial,args.u1,args.run)).decode())
            return 0
        if args.command=='baseline':
            values=baselines(args.materialization,args.run);args.out.mkdir(parents=True,exist_ok=True)
            for name,value in values.items():
                (args.out/(name+'.json')).write_bytes(canonical(value))
        elif args.command=='series':
            value,sidecar=make_series(args.materialization,args.run,load_json(args.recompute)[0])
            args.out.write_bytes(canonical(value))
            args.out.with_name(args.out.name+'.sidecar.json').write_bytes(canonical(sidecar))
        else:
            function=recompute if args.command=='recompute' else stress
            args.out.write_bytes(canonical(function(args.materialization,args.run)))
        return 0
    except (SeriesError,OSError,KeyError,TypeError,ValueError) as exc:
        print('U6 拒絕：'+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
