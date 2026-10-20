"""依帳本唯讀授權切片 U1 資料；本版一律拒絕 holdout 物化。"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from program_code.research.r8_ledger.ledger import ResearchLedger, LedgerError, canonical

P3B_MANIFEST_SHA256 = 'b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006'
TOOL_VERSION = 'r8-public-data-2'
DATA_START = '2020-01-01T00:00:00Z'
MIN_LOOKBACK_SECONDS = 13 * 86400
HOUR = 3600000
DAY = 24 * HOUR
HEADERS = {
    'kline': ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'],
    'funding': ['timestamp', 'funding_rate'],
    'open_interest': ['timestamp', 'open_interest'],
}
DATASETS = (('kline', '60'), ('kline', 'D'), ('open_interest', '4h'), ('funding', 'funding'))


class MaterializationError(ValueError):
    """來源、可讀範圍或輸出不符合物化契約。"""


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'[0-9]+', str(value)):
        raise MaterializationError('時間戳或間隔須為非負整數')
    return int(value)


def _timestamp(value):
    if type(value) is int:
        return value
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None or dt.utcoffset() != timedelta(0) or dt.microsecond % 1000:
            raise ValueError()
        delta = dt - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000
    except (ValueError, TypeError, AttributeError) as exc:
        raise MaterializationError('時間須為 UTC ISO8601，最多毫秒精度') from exc


def _date(stamp):
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=stamp)


def _window(value):
    if isinstance(value, str):
        parts = value.split(',')
        if len(parts) != 2:
            raise MaterializationError('window 須為起點,終點')
        value = dict(zip(('start', 'end'), parts))
    if not isinstance(value, dict) or set(value) != {'start', 'end'}:
        raise MaterializationError('window 須有 start 與 end')
    start, end = _timestamp(value['start']), _timestamp(value['end'])
    if start >= end:
        raise MaterializationError('視窗須為非空遞增區間')
    return start, end


def _decimal(value, *, positive=False, nonnegative=False):
    try:
        if not isinstance(value, str) or not value.strip():
            raise InvalidOperation()
        number = Decimal(value)
        if not number.is_finite() or positive and number <= 0 or nonnegative and number < 0:
            raise InvalidOperation()
        return format(number, 'f')
    except (InvalidOperation, ValueError) as exc:
        raise MaterializationError('數值缺失、非有限或不符合正負限制') from exc


def _source_bytes(root, relative, expected):
    path = root / relative
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise MaterializationError('來源檔案不存在或越出 U1 目錄')
    raw = path.read_bytes()
    if _digest(raw) != expected:
        raise MaterializationError('來源雜湊不符: ' + relative)
    return raw


def _instruments(root, manifest, symbols):
    raw = _source_bytes(root, 'requests.jsonl', manifest['request_log_sha256'])
    records = {}
    for line in raw.splitlines():
        record = json.loads(line)
        request_id = record['request_id']
        if type(request_id) is not int or request_id <= 0 or request_id in records:
            raise MaterializationError('請求代號不合法或重複')
        records[request_id] = record
    ids = manifest['universe_request_ids']
    if not isinstance(ids, list) or not ids or any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise MaterializationError('universe_request_ids 不合法')
    instruments = {}
    for request_id in ids:
        record = records[request_id]
        page = json.loads(_source_bytes(root, f'raw/{request_id}.json', record['raw_sha256']))
        if record['endpoint'] != '/v5/market/instruments-info':
            raise MaterializationError('原始頁不是 instruments-info')
        # 探測失敗的頁仍核對雜湊，但不能作屬性來源。
        if record['http_status'] != 200 or record['retCode'] != 0 or page.get('retCode') != 0:
            continue
        for item in page['result']['list']:
            symbol = item.get('symbol')
            if symbol not in symbols:
                continue
            if item.get('contractType') != 'LinearPerpetual' or item.get('settleCoin') != 'USDT' or item.get('status') not in ('Trading', 'Closed'):
                raise MaterializationError('標的不是已開盤 USDT 永續合約')
            if symbol in instruments and instruments[symbol] != item:
                raise MaterializationError('原始頁的合約屬性衝突')
            instruments[symbol] = item
    if set(instruments) != set(symbols):
        raise MaterializationError('原始頁缺少所需標的')
    return instruments


def _selected_rows(raw, dataset, start, end, delivery):
    lines = gzip.decompress(raw).splitlines(keepends=True)
    if not lines or next(csv.reader([lines[0].decode('utf-8')])) != HEADERS[dataset]:
        raise MaterializationError('U1 CSV 標頭不符')
    selected, original, previous = [], [lines[0]], None
    for line in lines[1:]:
        # 整檔位元組只用於來源雜湊；範圍外只掃時間戳，不解讀數值或推導市場資訊。
        stamp = _integer(line.split(b',', 1)[0].decode('ascii'))
        if not start <= stamp < end and not (dataset == 'funding' and stamp == end):
            continue
        if dataset == 'funding' and delivery and stamp > delivery:
            continue
        row = next(csv.reader([line.decode('utf-8')]))
        if len(row) != len(HEADERS[dataset]) or previous is not None and stamp <= previous:
            raise MaterializationError('可讀資料列結構不符或時間不嚴格遞增')
        previous = stamp
        numbers = [_decimal(value, positive=(dataset == 'kline' and i < 4),
                            nonnegative=(dataset == 'open_interest' or dataset == 'kline' and i >= 4))
                   for i, value in enumerate(row[1:])]
        selected.append((stamp, numbers))
        original.append(line)
    return selected, b''.join(original)


def _csv(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def _zip(symbol, raw):
    stream = io.BytesIO()
    info = zipfile.ZipInfo(symbol.lower()+'_trade_perp.csv', (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    # 不壓縮以避免 zlib 版本影響確定性的位元組。
    info.compress_type = zipfile.ZIP_STORED
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr(info, raw)
    return stream.getvalue()


def _output_path(out):
    out = Path(out).absolute()
    if out.exists() or out.is_symlink():
        raise MaterializationError('輸出目錄必須不存在')
    resolved = out.resolve()
    if any((parent/'.git').exists() for parent in (resolved, *resolved.parents)):
        raise MaterializationError('輸出不可位於倉庫內')
    if not resolved.parent.is_dir():
        raise MaterializationError('輸出的父目錄必須存在')
    return resolved


def materialize(*, u1, u1_manifest_sha256, ledger, hypothesis, window, out,
                trial=None, validation=False):
    """物化一個已授權樣本外視窗；成功後回傳 §7.1 manifest。"""
    out = _output_path(out)
    ledger = Path(ledger)
    if not ledger.is_dir() or not (ledger/'ledger_id.json').is_file():
        raise MaterializationError('帳本目錄與 ledger_id.json 必須已存在')
    book = ResearchLedger(ledger)
    access = book.data_access(hypothesis, trial)
    start, end = _window(window)
    if trial is not None and (start, end) != _window(book.trial_record(trial)['record']['data_window']):
        raise MaterializationError('視窗必須等於已開始試驗的 data_window')
    allowed_start, allowed_end = _window(access['out_of_sample'])
    if not allowed_start <= start < end <= allowed_end:
        raise MaterializationError('本版只物化樣本外，拒絕所有 holdout 區間')
    lookback = access['max_lookback_seconds']
    if isinstance(lookback, bool) or not isinstance(lookback, (int, float)) or lookback < MIN_LOOKBACK_SECONDS:
        raise MaterializationError('最長回看不得小於 13 日')
    duration = Decimal(str(lookback)) * 1000
    if not duration.is_finite() or duration != duration.to_integral_value():
        raise MaterializationError('回看須為有限的毫秒長度')
    warm_start = start - int(duration)
    data_start = _timestamp(DATA_START)
    if warm_start < allowed_start and not (allowed_start == data_start and warm_start < data_start):
        raise MaterializationError('暖機越出可讀範圍')
    for segment in access['time_splits']:
        if segment['kind'] == 'holdout':
            a, b = _window({k: segment[k] for k in ('start', 'end')})
            if warm_start < b and a < start:
                raise MaterializationError('暖機跨入不可讀 holdout')
    strategy_symbols = access['selection'].get('symbols')
    if (not isinstance(strategy_symbols, list) or not strategy_symbols
            or any(not isinstance(s, str) or not re.fullmatch(r'[A-Z0-9]{1,32}', s) for s in strategy_symbols)
            or len(set(strategy_symbols)) != len(strategy_symbols)):
        raise MaterializationError('預登記須列出不重複的 selection.symbols')
    symbols = sorted(set(strategy_symbols) | {'BTCUSDT'})
    root = Path(u1).resolve()
    if not validation and u1_manifest_sha256 != P3B_MANIFEST_SHA256:
        raise MaterializationError('研究來源必須是釘住的 P3b manifest')
    source_manifest = json.loads(_source_bytes(root, 'manifest.json', u1_manifest_sha256))
    if source_manifest['tool_version'] != TOOL_VERSION:
        raise MaterializationError('U1 工具版本不符')
    instruments = _instruments(root, source_manifest, symbols)
    limitations = ['合約屬性為取數當時值，歷史變更未驗證。']
    if warm_start < data_start:
        limitations.append('暖機早於 2020-01-01 的部分為空。')
    result = {'schema_version': 'r8_materialization_v1', 'u1_manifest_sha256': u1_manifest_sha256,
              'u1_tool_version': TOOL_VERSION, 'ledger_id': book.ledger_id, 'hypothesis_id': hypothesis,
              'generation': access['generation'], 'purpose': 'validation' if validation else 'research',
              'window': {'start': start, 'end': end},
              'warmup': {'start': warm_start, 'end': start}, 'readable': access,
              'symbols': symbols, 'strategy_symbols': strategy_symbols, 'files': {}, 'gaps': {},
              'first_bar': {}, 'min_notional': {}, 'funding_interval_ms': {}, 'delistings': {},
              'symbol_properties_overlay_sha256': None, 'limitations': limitations}
    temporary = Path(tempfile.mkdtemp(prefix='.'+out.name+'-', dir=out.parent))
    try:
        def emit(name, raw, rows, source_file, source_sha256):
            path = temporary/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            stamps = [t for t, _ in rows]
            result['files'][name] = {'sha256': _digest(raw), 'rows': len(rows),
                                     'first': stamps[0] if stamps else None, 'last': stamps[-1] if stamps else None,
                                     'source_file': source_file, 'source_sha256': source_sha256}

        overlay = []
        for symbol in symbols:
            item = instruments[symbol]
            tick = _decimal(item['priceFilter']['tickSize'], positive=True)
            lot = item['lotSizeFilter']
            step = _decimal(lot['qtyStep'], positive=True)
            minimum = _decimal(lot['minOrderQty'], positive=True)
            if 'minNotionalValue' not in lot:
                limitations.append(symbol+': 缺 minNotionalValue，記為 0。')
            result['min_notional'][symbol] = _decimal(lot.get('minNotionalValue', '0'), nonnegative=True)
            interval = _integer(item['fundingInterval']) * 60000
            if interval <= 0:
                raise MaterializationError('資金費間隔須為正')
            result['funding_interval_ms'][symbol] = interval
            delivery = _integer(item.get('deliveryTime', '0'))
            overlay.append(['bybit', symbol, 'cryptofuture', symbol, 'USDT', '1', tick, step, symbol, minimum, ''])
            result['gaps'][symbol] = {}
            for dataset, interval_name in DATASETS:
                filename = f'{dataset}_{symbol}_{interval_name}.csv.gz'
                meta = source_manifest['files'][filename]
                if (meta['dataset'], meta['symbol'], meta['interval']) != (dataset, symbol, interval_name):
                    raise MaterializationError('來源檔案身份不符')
                raw = _source_bytes(root, filename, meta['sha256'])
                rows, original = _selected_rows(raw, dataset, max(warm_start, data_start), end, delivery)
                emit('source/'+filename[:-3], original, rows, filename, meta['sha256'])
                key = 'kline_hour' if interval_name == '60' else 'kline_day' if interval_name == 'D' else dataset
                clipped = []
                period = HOUR if interval_name == '60' else DAY if interval_name == 'D' else 4*HOUR
                for gap in meta['gaps']['missing_intervals']:
                    a, b = max(_integer(gap['start']), warm_start, data_start), min(_integer(gap['end_exclusive']), end)
                    if a < b:
                        clipped.append({'start': a, 'end_exclusive': b, 'count': (b-a+period-1)//period})
                result['gaps'][symbol][key] = clipped
                if dataset == 'kline':
                    if interval_name == '60':
                        emit(f'lean/cryptofuture/bybit/hour/{symbol.lower()}_trade.zip',
                             _zip(symbol, _csv([[_date(t).strftime('%Y%m%d %H:%M'), *n[:5]] for t, n in rows])), rows, filename, meta['sha256'])
                        first = meta['first_timestamp']
                        result['first_bar'][symbol] = first if rows and first == rows[0][0] else None
                        if delivery and warm_start <= delivery <= end:
                            last = next((t for t, _ in reversed(rows) if t < delivery), None)
                            result['delistings'][symbol] = {'deliveryTime': delivery,
                                                           'partial_last_bar': last is not None and last < delivery < last+HOUR}
                    else:
                        emit(f'custom/kline_day/{symbol.lower()}.csv', _csv([[t+DAY, t, *n[:5]] for t, n in rows]), rows, filename, meta['sha256'])
                    resolution = 'hour' if interval_name == '60' else 'day'
                    offset = HOUR if interval_name == '60' else DAY
                    emit(f'custom/turnover_{resolution}/{symbol.lower()}.csv', _csv([[t+offset, t, n[5]] for t, n in rows]), rows, filename, meta['sha256'])
                else:
                    offset = 4*HOUR if dataset == 'open_interest' else 0
                    emit(f'custom/{dataset}/{symbol.lower()}.csv', _csv([[t+offset, t, n[0]] for t, n in rows]), rows, filename, meta['sha256'])
        overlay_raw = _csv(overlay)
        (temporary/'symbol_properties_overlay.csv').write_bytes(overlay_raw)
        result['symbol_properties_overlay_sha256'] = _digest(overlay_raw)
        (temporary/'materialization.json').write_bytes(canonical(result))
        if out.exists() or out.is_symlink():
            raise MaterializationError('輸出目錄已被建立')
        os.rename(temporary, out)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('u1', 'u1-manifest-sha256', 'ledger', 'hypothesis', 'window', 'out'):
        parser.add_argument('--'+flag, required=True)
    parser.add_argument('--trial')
    parser.add_argument('--validation', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = materialize(**vars(args))
        print(canonical(result).decode('utf-8'))
    except (MaterializationError, LedgerError, OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc)+'\n')


if __name__ == '__main__':
    main()
