"""U4 物化：合成 U1 來源、公開帳本介面與實際檔案產物。"""
import ast
import copy
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import socket
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import pytest
from program_code.research.r8_ledger.ledger import canonical, LedgerError
from program_code.research.tests.test_r8_ledger_access import make_book, registration, begin, append_fixture_event
from program_code.research.r8_engine import materialize as mod


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('禁止網路')
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)
    monkeypatch.setattr(socket, 'create_connection', denied)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def ms(text):
    return int(datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()*1000)


WINDOW = {'start': '2022-01-01T00:00:00Z', 'end': '2022-02-01T00:00:00Z'}
START = ms(WINDOW['start'])
END = ms(WINDOW['end'])


def source(root):
    root.mkdir()
    (root/'raw').mkdir()
    files, instruments = {}, []
    for symbol in ('XUSDT', 'BTCUSDT'):
        instruments.append({'symbol': symbol, 'contractType': 'LinearPerpetual', 'settleCoin': 'USDT',
                            'status': 'Trading', 'deliveryTime': '0', 'fundingInterval': '480',
                            'priceFilter': {'tickSize': '1e-5'},
                            'lotSizeFilter': {'qtyStep': '0.01', 'minOrderQty': '0.1', 'minNotionalValue': '5'}})
        for dataset, interval, header, values in [
            ('kline', '60', 'timestamp,open,high,low,close,volume,turnover\n', '9.464e-05,0.0001,0.00009,9.5e-5,1e3,0.095'),
            ('kline', 'D', 'timestamp,open,high,low,close,volume,turnover\n', '9.464e-05,0.0001,0.00009,9.5e-5,1e3,0.095'),
            ('open_interest', '4h', 'timestamp,open_interest\n', '1e2'),
            ('funding', 'funding', 'timestamp,funding_rate\n', '-1e-4')]:
            name = f'{dataset}_{symbol}_{interval}.csv.gz'
            stamps = [START-14*86400000, START-13*86400000, START, END, END+3600000]
            raw = gzip.compress((header+''.join(f'{t},{values}\n' for t in stamps)).encode(), mtime=0)
            (root/name).write_bytes(raw)
            files[name] = {'dataset': dataset, 'symbol': symbol, 'interval': interval, 'sha256': digest(raw),
                           'first_timestamp': stamps[0], 'gaps': {'missing_intervals': []}}
    page = canonical({'retCode': 0, 'result': {'list': instruments}})
    (root/'raw/1.json').write_bytes(page)
    requests = canonical({'request_id': 1, 'endpoint': '/v5/market/instruments-info', 'http_status': 200,
                          'retCode': 0, 'raw_sha256': digest(page)})+b'\n'
    (root/'requests.jsonl').write_bytes(requests)
    manifest = {'tool_version': 'r8-public-data-2', 'files': files, 'universe_request_ids': [1],
                'request_log_sha256': digest(requests)}
    (root/'manifest.json').write_bytes(canonical(manifest))
    return digest(canonical(manifest))


@pytest.fixture
def setup(tmp_path):
    book = make_book(tmp_path/'ledger')
    root = tmp_path/'u1'
    sha = source(root)
    args = {'u1': root, 'u1_manifest_sha256': sha, 'ledger': book.out, 'hypothesis': 'h1',
            'window': WINDOW, 'out': tmp_path/'result', 'validation': True}
    return book, args


def test_materialize_formats_known_times_and_manifest(setup):
    book, args = setup
    result = mod.materialize(**args)
    assert result['schema_version'] == 'r8_materialization_v1'
    assert result['purpose'] == 'validation'
    assert result['ledger_id'] == book.ledger_id
    assert result['strategy_symbols'] == ['XUSDT']
    assert result['symbols'] == ['BTCUSDT', 'XUSDT']
    assert result['warmup'] == {'start': 1639872000000, 'end': START}
    with zipfile.ZipFile(args['out']/'lean/cryptofuture/bybit/hour/xusdt_trade.zip') as archive:
        assert archive.namelist() == ['xusdt_trade_perp.csv']
        assert archive.read(archive.namelist()[0]).decode().splitlines()[-1] == '20220101 00:00,0.00009464,0.0001,0.00009,0.000095,1000,0.095'.rsplit(',', 1)[0]
    assert (args['out']/'custom/open_interest/xusdt.csv').read_text().splitlines()[-1] == f'{START+14400000},{START},100'
    assert (args['out']/'custom/kline_day/xusdt.csv').read_text().splitlines()[-1] == f'{START+86400000},{START},0.00009464,0.0001,0.00009,0.000095,1000'
    assert (args['out']/'custom/turnover_hour/xusdt.csv').read_text().splitlines()[-1] == f'{START+3600000},{START},0.095'
    assert (args['out']/'custom/funding/xusdt.csv').read_text().splitlines()[-1] == f'{END},{END},-0.0001'
    assert (args['out']/'source/kline_XUSDT_60.csv').read_text().splitlines()[-1] == f'{START},9.464e-05,0.0001,0.00009,9.5e-5,1e3,0.095'
    assert result['first_bar'] == {'BTCUSDT': None, 'XUSDT': None}
    assert result['min_notional']['XUSDT'] == '5'
    assert result['funding_interval_ms']['XUSDT'] == 28800000
    assert 'bybit,XUSDT,cryptofuture,XUSDT,USDT,1,0.00001,0.01,XUSDT,0.1,' in (args['out']/'symbol_properties_overlay.csv').read_text()
    for name, meta in result['files'].items():
        assert digest((args['out']/name).read_bytes()) == meta['sha256']
    assert not list(args['out'].rglob('*margin_interest*'))


def test_manifest_windows_use_utc_milliseconds(setup):
    _, args = setup
    result = mod.materialize(**args)
    assert result['window'] == {'start': START, 'end': END}
    assert result['warmup'] == {'start': START-13*86400000, 'end': START}


def update_manifest(args, change):
    path = args['u1']/'manifest.json'
    value = json.loads(path.read_bytes())
    change(value)
    path.write_bytes(canonical(value))
    args['u1_manifest_sha256'] = digest(path.read_bytes())


def update_page(args, change):
    path = args['u1']/'raw/1.json'
    page = json.loads(path.read_bytes())
    change(page['result']['list'][0])
    path.write_bytes(canonical(page))
    log = args['u1']/'requests.jsonl'
    record = json.loads(log.read_bytes())
    record['raw_sha256'] = digest(path.read_bytes())
    log.write_bytes(canonical(record)+b'\n')
    update_manifest(args, lambda m: m.update(request_log_sha256=digest(log.read_bytes())))


@pytest.mark.parametrize('target', ['manifest.json', 'requests.jsonl', 'raw/1.json', 'kline_XUSDT_60.csv.gz'])
def test_tampered_hashes_rejected_without_output(setup, target):
    _, args = setup
    path = args['u1']/target
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(mod.MaterializationError):
        mod.materialize(**args)
    assert not args['out'].exists()
    assert not list(args['out'].parent.glob('.result-*'))


def test_version_and_pinned_manifest_rejected_even_self_consistent(setup, monkeypatch):
    _, args = setup
    with pytest.raises(mod.MaterializationError, match='P3b'):
        mod.materialize(**{**args, 'validation': False})
    monkeypatch.setattr(mod, 'P3B_MANIFEST_SHA256', args['u1_manifest_sha256'])
    result = mod.materialize(**{**args, 'validation': False})
    assert result['purpose'] == 'research'
    args['out'] = args['out'].parent/'other'
    update_manifest(args, lambda m: m.update(tool_version='r8-public-data-1'))
    with pytest.raises(mod.MaterializationError, match='版本'):
        mod.materialize(**args)
    with pytest.raises(mod.MaterializationError, match='P3b'):
        mod.materialize(**{**args, 'validation': False})


@pytest.mark.parametrize('state', ['unopened', 'denied', 'other_candidate', 'candidate'])
def test_all_holdout_materialization_denied(setup, state):
    book, args = setup
    interval = {'start': '2026-01-08T00:00:00Z', 'end': '2026-05-15T00:00:00Z'}
    if state != 'unopened':
        append_fixture_event(book, 'holdouts', {'action': 'denied' if state == 'denied' else 'opened',
                            'generation': 1, 'intervals': {'h2' if state == 'other_candidate' else 'h1': interval}})
    with pytest.raises(mod.MaterializationError, match='holdout'):
        mod.materialize(**{**args, 'window': interval})
    assert not args['out'].exists()


@pytest.mark.parametrize('window', [
    {'start': '2025-07-03T00:00:00Z', 'end': '2025-10-02T00:00:00Z'},
    {'start': '2020-01-01T00:00:00Z', 'end': '2026-01-01T00:00:00Z'}])
def test_gap_crossing_fold15_and_full_oos_allowed(setup, window):
    _, args = setup
    result = mod.materialize(**{**args, 'window': window})
    assert result['window'] == {k: ms(v) for k, v in window.items()}
    if window['start'].startswith('2020'):
        assert '暖機早於 2020-01-01 的部分為空。' in result['limitations']
        assert result['warmup']['start'] == ms('2019-12-19T00:00:00Z')


@pytest.mark.parametrize('window', [
    {'start': '2025-12-20T00:00:00Z', 'end': '2026-01-09T00:00:00Z'},
    {'start': '2026-05-28T00:00:00Z', 'end': '2026-06-01T00:00:00Z'},
    {'start': '2019-12-31T00:00:00Z', 'end': '2020-02-01T00:00:00Z'}])
def test_forbidden_window_and_cross_generation_warmup_rejected(setup, window):
    _, args = setup
    with pytest.raises(mod.MaterializationError):
        mod.materialize(**{**args, 'window': window})
    assert not args['out'].exists()


@pytest.mark.parametrize('change', ['short_lookback', 'no_symbols', 'duplicate_symbols', 'path_symbol'])
def test_registration_constraints_rejected(setup, change):
    _, args = setup
    r = registration()
    if change == 'short_lookback':
        r['max_lookback_seconds'] = 12*86400
    elif change == 'no_symbols':
        del r['selection']['symbols']
    elif change == 'duplicate_symbols':
        r['selection']['symbols'] = ['BTCUSDT', 'BTCUSDT']
    else:
        r['selection']['symbols'] = ['../bad']
    args['ledger'] = args['ledger'].parent/'other_ledger'
    make_book(args['ledger'], r)
    with pytest.raises(mod.MaterializationError):
        mod.materialize(**args)
    assert not args['out'].exists()


@pytest.mark.parametrize('missing_identity', [False, True])
def test_missing_ledger_refused_without_creation(setup, missing_identity):
    _, args = setup
    args['ledger'] = args['ledger'].parent/'absent_ledger'
    if missing_identity:
        args['ledger'].mkdir()
    with pytest.raises(mod.MaterializationError):
        mod.materialize(**args)
    assert not (args['ledger']/'ledger_id.json').exists()
    assert not (args['ledger']/'.ledger.lock').exists()
    if not missing_identity:
        assert not args['ledger'].exists()


def test_withdrawn_replay_requires_exact_trial_window(setup):
    book, args = setup
    begin(book)
    book.withdraw_hypothesis('h1', '合成撤回')
    with pytest.raises(LedgerError):
        mod.materialize(**args)
    with pytest.raises(mod.MaterializationError, match='data_window'):
        mod.materialize(**{**args, 'trial': 't1', 'window': {'start': WINDOW['start'], 'end': '2022-01-15T00:00:00Z'}})
    assert mod.materialize(**{**args, 'trial': 't1'})['hypothesis_id'] == 'h1'


@pytest.mark.parametrize('field,value', [('tickSize', None), ('qtyStep', '0'), ('minOrderQty', '-1'), ('minNotionalValue', 'NaN'), ('fundingInterval', '0')])
def test_bad_instrument_fields_rejected(setup, field, value):
    _, args = setup
    def change(item):
        target = item if field == 'fundingInterval' else item['priceFilter'] if field == 'tickSize' else item['lotSizeFilter']
        if value is None:
            del target[field]
        else:
            target[field] = value
    update_page(args, change)
    with pytest.raises((mod.MaterializationError, KeyError)):
        mod.materialize(**args)
    assert not args['out'].exists()
    assert not list(args['out'].parent.glob('.result-*'))


def test_missing_min_notional_is_zero_and_disclosed(setup):
    _, args = setup
    update_page(args, lambda item: item['lotSizeFilter'].pop('minNotionalValue'))
    result = mod.materialize(**args)
    assert result['min_notional']['XUSDT'] == '0'
    assert 'XUSDT: 缺 minNotionalValue，記為 0。' in result['limitations']


def test_delisting_endpoint_partial_bar_and_funding_cutoff(setup):
    _, args = setup
    delivery = START+1800000
    update_page(args, lambda item: item.update(deliveryTime=str(delivery), status='Closed'))
    name = 'funding_XUSDT_funding.csv.gz'
    raw = gzip.compress(f'timestamp,funding_rate\n{START},0.001\n{delivery},0.002\n{delivery+1},0.003\n'.encode(), mtime=0)
    (args['u1']/name).write_bytes(raw)
    update_manifest(args, lambda m: m['files'][name].update(sha256=digest(raw)))
    result = mod.materialize(**{**args, 'window': {'start': WINDOW['start'], 'end': '2022-01-01T00:30:00Z'}})
    assert result['delistings']['XUSDT'] == {'deliveryTime': delivery, 'partial_last_bar': True}
    assert (args['out']/'custom/funding/xusdt.csv').read_text() == f'{START},{START},0.001\n{delivery},{delivery},0.002\n'
    assert '0.003' not in (args['out']/('source/'+name[:-3])).read_text()
    assert all('deliveryTime' not in (p.read_bytes().decode() if p.suffix == '.csv' else '')
               for folder in ('lean', 'custom') for p in (args['out']/folder).rglob('*') if p.is_file())


def directory_bytes(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_output_byte_determinism_and_schema(setup):
    _, args = setup
    result = mod.materialize(**args)
    other = args['out'].parent/'second'
    mod.materialize(**{**args, 'out': other})
    assert directory_bytes(args['out']) == directory_bytes(other)
    assert set(result) == set('schema_version u1_manifest_sha256 u1_tool_version ledger_id hypothesis_id generation purpose window warmup readable symbols strategy_symbols files gaps first_bar min_notional funding_interval_ms delistings symbol_properties_overlay_sha256 limitations'.split())
    assert (args['out']/'materialization.json').read_bytes() == canonical(result)
    names = {str(p.relative_to(args['out'])) for folder in ('lean', 'custom', 'source') for p in (args['out']/folder).rglob('*') if p.is_file()}
    assert names == set(result['files'])
    for meta in result['files'].values():
        assert set(meta) == {'sha256', 'rows', 'first', 'last', 'source_file', 'source_sha256'}


def test_existing_output_repository_and_interrupted_publication(setup, monkeypatch):
    _, args = setup
    args['out'].mkdir()
    (args['out']/'keep').write_bytes(b'keep')
    with pytest.raises(mod.MaterializationError):
        mod.materialize(**args)
    assert (args['out']/'keep').read_bytes() == b'keep'
    repo_out = Path(__file__).resolve().parents[3]/'u4-forbidden-output'
    with pytest.raises(mod.MaterializationError, match='倉庫'):
        mod.materialize(**{**args, 'out': repo_out})
    assert not repo_out.exists()
    def fail(*args):
        raise OSError('合成 rename 失敗')
    monkeypatch.setattr(mod.os, 'rename', fail)
    with pytest.raises(OSError):
        mod.materialize(**{**args, 'out': args['out'].parent/'interrupted'})
    assert not (args['out'].parent/'interrupted').exists()
    assert not list(args['out'].parent.glob('.interrupted-*'))


def test_ast_host_imports_and_no_float_decimal_conversion():
    root = Path(__file__).resolve().parents[3]
    for name in ('r8_engine/materialize.py', 'r8_ledger/ledger.py'):
        tree = ast.parse((root/'program_code/research'/name).read_text())
        for node in ast.walk(tree):
            imports = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) else []
            for imported in imports:
                assert imported.split('.')[0] in sys.stdlib_module_names or imported.startswith(('program_code.research.r8_engine', 'program_code.research.r8_ledger'))
            if name.startswith('r8_engine') and isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != 'float'


def test_scoped_gaps_first_bar_and_outside_rows_do_not_leak(setup):
    _, args = setup
    name = 'kline_XUSDT_60.csv.gz'
    warm = START-13*86400000
    def meta_change(m):
        m['files'][name]['gaps'] = {'missing_intervals': [
            {'start': warm-HOUR, 'end_exclusive': warm+HOUR, 'count': 2},
            {'start': END-HOUR, 'end_exclusive': END+HOUR, 'count': 2},
            {'start': END+2*HOUR, 'end_exclusive': END+3*HOUR, 'count': 1}]}
    HOUR = 3600000
    update_manifest(args, meta_change)
    before = mod.materialize(**args)
    assert before['gaps']['XUSDT']['kline_hour'] == [
        {'start': warm, 'end_exclusive': warm+HOUR, 'count': 1},
        {'start': END-HOUR, 'end_exclusive': END, 'count': 1}]
    source_path = args['u1']/name
    raw = gzip.decompress(source_path.read_bytes()).splitlines(keepends=True)
    raw[1] = f'{START-14*86400000},not-readable,invalid,outside,row,numbers,ignored\n'.encode()
    raw[-1] = f'{END+HOUR},NaN,NaN,NaN,NaN,NaN,NaN\n'.encode()
    source_path.write_bytes(gzip.compress(b''.join(raw), mtime=0))
    update_manifest(args, lambda m: m['files'][name].update(sha256=digest(source_path.read_bytes())))
    second = args['out'].parent/'changed_outside'
    after = mod.materialize(**{**args, 'out': second})
    for key in ('gaps', 'first_bar', 'delistings'):
        assert before[key] == after[key]
    for path in before['files']:
        assert (args['out']/path).read_bytes() == (second/path).read_bytes()
    # 改動來源必然改變來源雜湊；只允許 provenance 改變，禁止範圍外市場內容洩漏。
    assert before['u1_manifest_sha256'] != after['u1_manifest_sha256']
    assert before['files']['source/'+name[:-3]]['source_sha256'] != after['files']['source/'+name[:-3]]['source_sha256']


def test_first_bar_inside_readable_range(setup):
    _, args = setup
    name = 'kline_XUSDT_60.csv.gz'
    path = args['u1']/name
    lines = gzip.decompress(path.read_bytes()).splitlines(keepends=True)
    raw = gzip.compress(b''.join([lines[0], *lines[2:]]), mtime=0)
    path.write_bytes(raw)
    update_manifest(args, lambda m: m['files'][name].update(sha256=digest(raw), first_timestamp=START-13*86400000))
    assert mod.materialize(**args)['first_bar']['XUSDT'] == START-13*86400000


def test_strategy_symbols_preserve_order_and_btc_membership(setup):
    _, args = setup
    r = registration()
    r['selection']['symbols'] = ['XUSDT', 'BTCUSDT']
    args['ledger'] = args['ledger'].parent/'both'
    make_book(args['ledger'], r)
    result = mod.materialize(**args)
    assert result['strategy_symbols'] == ['XUSDT', 'BTCUSDT']
    assert result['symbols'] == ['BTCUSDT', 'XUSDT']


def test_cli_accepts_iso_window_and_reports_failure_without_output(setup, capsys):
    _, args = setup
    argv = []
    for key in ('u1', 'u1_manifest_sha256', 'ledger', 'hypothesis', 'out'):
        argv.extend(['--'+key.replace('_', '-'), str(args[key])])
    argv.extend(['--window', WINDOW['start']+','+WINDOW['end'], '--validation'])
    mod.main(argv)
    result = json.loads(capsys.readouterr().out)
    assert result['window'] == {'start': START, 'end': END}
    with pytest.raises(SystemExit) as failure:
        mod.main(argv)
    assert failure.value.code == 2


@pytest.mark.parametrize('number', ['NaN', 'Infinity', '-Infinity', '0', '-1'])
def test_invalid_selected_prices_fail_atomically(setup, number):
    _, args = setup
    name = 'kline_XUSDT_60.csv.gz'
    path = args['u1']/name
    raw = gzip.compress(f'timestamp,open,high,low,close,volume,turnover\n{START},{number},1,1,1,1,1\n'.encode(), mtime=0)
    path.write_bytes(raw)
    update_manifest(args, lambda m: m['files'][name].update(sha256=digest(raw), first_timestamp=START))
    with pytest.raises(mod.MaterializationError):
        mod.materialize(**args)
    assert not args['out'].exists()
    assert not list(args['out'].parent.glob('.result-*'))
