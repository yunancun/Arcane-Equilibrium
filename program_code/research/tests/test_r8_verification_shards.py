"""Real DV3 -> DV1 -> DV3 symbol-shard equivalence, with local originals only."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import gzip
import io
import json
import shutil
import socket

import pytest

from program_code.research.tests.test_r8_data_verification import (
    DAY, HOUR, T, FIELDS, VERIFICATION_KEYS, enc, sha, read,
)
from program_code.research.r8_data import verification as dv1
from program_code.research.r8_data import verification_fetch as dv3


SYMBOLS = ['AUSDT', 'BUSDT', 'CUSDT']


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)


def frozen_case(root, days=1, invalid_contract=False):
    """Three symbols with independent e/s/s expected daily outcomes."""
    p3b = root / 'p3b'; downloads = root / 'downloads'
    (p3b / 'raw').mkdir(parents=True); downloads.mkdir()
    files = {}; requests = []; inventory = []
    for symbol in SYMBOLS:
        for interval, count, step, volume in [('D', days, DAY, '24'), ('60', days * 24, HOUR, '1')]:
            rows = [[str(T + i * step), '10', '10', '10', '10', volume, str(int(volume) * 10)] for i in range(count)]
            if symbol == 'AUSDT' and interval == 'D':
                rows[0][2] = rows[0][4] = '11'  # Real L2/C5 correction, frozen before sampling.
            rid = len(requests) + 1
            raw = enc(dict(retCode=0, result=dict(category='linear', symbol=symbol, list=rows)))
            (p3b / f'raw/{rid}.json').write_bytes(raw)
            requests.append(dict(request_id=rid, base_url='https://api.bybit.com', endpoint='/v5/market/kline',
                params=dict(category='linear', symbol=symbol, interval=interval), http_status=200,
                retCode=0, raw_sha256=sha(raw)))
            stream = io.StringIO(); writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(['timestamp', *FIELDS]); writer.writerows(rows)
            data = gzip.compress(stream.getvalue().encode(), mtime=0)
            name = f'kline_{symbol}_{interval}.csv.gz'; (p3b / name).write_bytes(data)
            files[name] = dict(sha256=sha(data), dataset='kline', symbol=symbol, interval=interval,
                source_request_ids=[rid], first_timestamp=T-HOUR, last_timestamp=T+days*DAY-HOUR)
        for d in range(days):
            day = T + d * DAY
            rows = ['timestamp,symbol,side,size,price,trdMatchID']
            rows += [f'{(day+h*HOUR)//1000}.0000001,{symbol},Buy,1,10,{h}' for h in range(24)]
            data = gzip.compress(('\n'.join(rows)+'\n').encode(), mtime=0)
            date = datetime.fromtimestamp(day // 1000, timezone.utc).strftime('%Y-%m-%d')
            name = f'{symbol}{date}.csv.gz'; (downloads / name).write_bytes(data)
            inventory.append(dict(schema_version='r8_verification_download_v1', request_id=name,
                symbol=symbol, day_start=day, interval='trade', source_kind='bybit_trade',
                url=f'https://public.bybit.com/trading/{symbol}/{name}', started_at=T,
                finished_at=T+1, http_status=200, api_status=None, byte_count=len(data),
                relative_path=name, sha256=sha(data), status='AVAILABLE', reason_code=None))
    rid = len(requests) + 1
    instruments = [dict(symbol=s, baseCoin=s[:-4], quoteCoin='USDT', settleCoin='USDT',
        contractType='LinearPerpetual', deliveryTime='0', launchTime=str(T-HOUR)) for s in SYMBOLS]
    if invalid_contract:
        instruments[-1]['contractType'] = 'InversePerpetual'
    raw = enc(dict(retCode=0, result=dict(category='linear', list=instruments)))
    (p3b / f'raw/{rid}.json').write_bytes(raw)
    requests.append(dict(request_id=rid, base_url='https://api.bybit.com', endpoint='/v5/market/instruments-info',
        params=dict(category='linear'), http_status=200, retCode=0, raw_sha256=sha(raw)))
    log = b''.join(enc(r) for r in requests); (p3b / 'requests.jsonl').write_bytes(log)
    manifest = enc(dict(tool_version='r8-public-data-2', files=files, request_log_sha256=sha(log),
        universe_request_ids=[rid], universe={s: dict(launch_time=T-HOUR, deliveryTime=0) for s in SYMBOLS}))
    (p3b / 'manifest.json').write_bytes(manifest)
    (downloads / 'download_inventory.jsonl').write_bytes(b''.join(enc(r) for r in inventory))
    scope = dict(start=T, end=T+days*DAY)
    sources = [dv3.CSVSource(m['symbol'], m['dataset'], m['interval'], n, m['sha256']) for n, m in files.items()]
    result = dv3.build_sample_plan(p3b, root/'plan', sources, readable=scope, p3b_manifest_sha256=sha(manifest))
    assert result['status'] == 'READY', json.dumps(result)
    return root


def verify_bundle(root, name, symbols, report=None, version='v1-strict'):
    bundle = root / name; plan = read(root/'plan', 'sample_plan.json')
    policy_path = root/'plan/policy.json'
    if version == dv1.V2:
        policy = read(root/'plan', 'policy.json')
        policy.update(schema_version='r8_data_verification_policy_v2', approval_event='RH-20261022-05',
            volume_semantics_policy=dv1.V2, standard_sha256=dv1.STANDARD_SHA256)
        policy_path = root/'v2-policy.json'; policy_path.write_bytes(enc(policy))
    result = dv1.verify(p3b_root=root/'p3b', download_root=root/'downloads',
        inventory_path=root/'downloads/download_inventory.jsonl', output_root=bundle,
        policy_path=policy_path, readable=plan['readable'], symbols=symbols,
        sample_plan_path=root/'plan/sample_plan.json', sample_report_path=report)
    assert result['status'] == 'READY', json.dumps(result)
    assert (bundle/'sample_plan.json').read_bytes() == (root/'plan/sample_plan.json').read_bytes()
    v = read(bundle, 'verification.json')
    assert set(v) == VERIFICATION_KEYS | ({'standard_sha256', 'volume_semantics_policy'} if version == dv1.V2 else set())
    if set(symbols) != set(SYMBOLS):
        assert 'SAMPLE_SHARD_SYMBOLS=' + ','.join(sorted(symbols)) in v['reason_codes']
    # Preserve the original namespaces and every SourceRef byte binding.
    for source in (root/'p3b', root/'downloads'):
        shutil.copytree(source, bundle, dirs_exist_ok=True)
    return bundle


def adjudications(bundle):
    rows = read(bundle, 'corrections.jsonl'); findings_sha = sha((bundle/'findings.jsonl').read_bytes())
    for row in rows:
        identity = row.pop('correction_id')
        assert identity == sha(enc(row))
        for ref in row['source_refs']:
            if ref['kind'] == 'report' and ref['relative_path'] == 'findings.jsonl':
                assert ref['sha256'] == findings_sha
                # Container linkage changes with packaging; every adjudication field stays exact.
                ref['sha256'] = '<validated findings container>'
    return sorted(rows, key=lambda r: (r['symbol'], r['timestamp'], r['interval'], r['field']))


def equivalent(root, whole, pieces, label):
    expected = adjudications(whole)
    actual = [r for b in pieces for r in adjudications(b)]
    assert sorted(actual, key=lambda r: (r['symbol'], r['timestamp'], r['interval'], r['field'])) == expected
    assert sorted([r for b in pieces for r in read(b, 'findings.jsonl')], key=lambda r: r['finding_id']) == sorted(read(whole, 'findings.jsonl'), key=lambda r: r['finding_id'])
    a = dv3.summarize_sample(root/'plan', [whole], root/(label+'-whole-report'))
    b = dv3.summarize_sample(root/'plan', pieces, root/(label+'-shard-report'))
    assert a['primary_file'] == b['primary_file'] == 'sample_report.txt', (a, b)
    assert a['reason_codes'] == b['reason_codes']
    report = root/(label+'-shard-report')/'sample_report.txt'
    assert (root/(label+'-whole-report')/'sample_report.txt').read_bytes() == report.read_bytes()
    return report


@pytest.mark.parametrize('shards', [[['AUSDT'], ['BUSDT', 'CUSDT']], [[s] for s in SYMBOLS]])
@pytest.mark.parametrize('version', ['v1-strict', dv1.V2])
def test_shards_equal_unsharded_draws_and_report_bytes(tmp_path, shards, version):
    root = frozen_case(tmp_path)
    whole = verify_bundle(root, 'whole', SYMBOLS, version=version)
    pieces = [verify_bundle(root, f'shard-{i}', symbols, version=version) for i, symbols in enumerate(shards)]
    report = equivalent(root, whole, pieces, 'base')
    assert 'N=3 n=3 e=1 u=0 s=2' in report.read_text()


@pytest.mark.parametrize('version', ['v1-strict', dv1.V2])
def test_missing_shard_counts_u_and_overlapping_shards_are_rejected(tmp_path, version):
    root = frozen_case(tmp_path)
    a = verify_bundle(root, 'a', ['AUSDT', 'BUSDT'], version=version)
    b = verify_bundle(root, 'b', ['BUSDT', 'CUSDT'], version=version)
    missing = dv3.summarize_sample(root/'plan', [a], root/'missing')
    assert missing['primary_file'] == 'sample_report.txt'
    assert 'N=3 n=3 e=1 u=1 s=1' in (root/'missing/sample_report.txt').read_text()
    overlap = dv3.summarize_sample(root/'plan', [a, b], root/'overlap')
    assert overlap['status'] == 'BLOCKED' and overlap['primary_file'] is None
    assert overlap['reason_codes'] == ['OVERLAPPING_VERIFICATION']


@pytest.mark.parametrize('mutation,reason', [
    ('foreign', 'SAMPLE_SCOPE'), ('rank', 'SAMPLE_SCOPE'), ('day', 'SAMPLE_SCOPE'),
    ('duplicate', 'SAMPLE_DUPLICATE'), ('schema', 'SAMPLE_IDENTITY'),
    ('readable', 'SAMPLE_IDENTITY'), ('seed', 'SAMPLE_IDENTITY'),
    ('manifest', 'SAMPLE_IDENTITY'), ('policy', 'SAMPLE_IDENTITY'),
])
def test_shard_still_validates_whole_plan(tmp_path, mutation, reason):
    root = frozen_case(tmp_path); p = read(root/'plan', 'sample_plan.json')
    draws = p['strata'][0]['draws']; other = next(d for d in draws if d['symbol'] == 'CUSDT')
    if mutation == 'foreign': other['symbol'] = 'OUTSIDEUSDT'
    elif mutation == 'rank': other['rank'] = 99
    elif mutation == 'day': other['day_start'] += HOUR
    elif mutation == 'duplicate': other['symbol'] = 'BUSDT'
    elif mutation == 'schema': p['schema_version'] = 'unknown'
    elif mutation == 'readable': p['readable']['end'] += DAY
    elif mutation == 'seed': p['seed'] += 1
    elif mutation == 'manifest': p['p3b_manifest_sha256'] = 'f'*64
    elif mutation == 'policy': p['policy_sha256'] = 'f'*64
    (root/'plan/sample_plan.json').write_bytes(enc(p))
    result = dv1.verify(p3b_root=root/'p3b', download_root=root/'downloads',
        inventory_path=root/'downloads/download_inventory.jsonl', output_root=root/'rejected',
        policy_path=root/'plan/policy.json', readable=dict(start=T, end=T+DAY), symbols=['AUSDT'],
        sample_plan_path=root/'plan/sample_plan.json')
    assert result['primary_file'] is None and reason in result['reason_codes'], result


def test_shard_preserves_full_universe_contract_identity_checks(tmp_path):
    root = frozen_case(tmp_path, invalid_contract=True)
    result = dv1.verify(p3b_root=root/'p3b', download_root=root/'downloads',
        inventory_path=root/'downloads/download_inventory.jsonl', output_root=root/'rejected',
        policy_path=root/'plan/policy.json', readable=dict(start=T, end=T+DAY), symbols=['AUSDT'],
        sample_plan_path=root/'plan/sample_plan.json')
    assert result['primary_file'] is None and 'CONTRACT_IDENTITY' in result['reason_codes'], result


@pytest.mark.parametrize('version', ['v1-strict', dv1.V2])
def test_shards_preserve_pre_erratum_frozen_policy(tmp_path, version):
    root = frozen_case(tmp_path)
    policy = read(root/'plan', 'policy.json')
    policy['standard_sha256'] = 'afcb87578676c998b4ce7529c6e1c09d5214cfe7e8af53ad03d120781c696931'
    (root/'plan/policy.json').write_bytes(enc(policy))
    plan = read(root/'plan', 'sample_plan.json'); plan['policy_sha256'] = sha(enc(policy))
    frozen = enc(plan); (root/'plan/sample_plan.json').write_bytes(frozen)
    (root/'plan/sample_plan.sha256').write_text(sha(frozen)+'\n')
    whole = verify_bundle(root, 'whole', SYMBOLS, version=version)
    shards = [verify_bundle(root, f'shard-{i}', symbols, version=version)
              for i, symbols in enumerate([['AUSDT'], ['BUSDT', 'CUSDT']])]
    report = equivalent(root, whole, shards, 'historical')
    assert 'N=3 n=3 e=1 u=0 s=2' in report.read_text()


@pytest.mark.parametrize('version', ['v1-strict', dv1.V2])
def test_expansion_handoff_filters_after_full_plan_validation(tmp_path, version):
    root = frozen_case(tmp_path, days=101)
    frozen = (root/'plan/sample_plan.json').read_bytes(); p = json.loads(frozen)
    assert len(p['strata']) == 1
    s = p['strata'][0]; assert (s['population_size'], s['base_size'], s['max_size']) == (303, 300, 303)
    whole = verify_bundle(root, 'whole', SYMBOLS, version=version)
    pieces = [verify_bundle(root, f'base-{sym}', [sym], version=version) for sym in SYMBOLS]
    report = equivalent(root, whole, pieces, 'base')
    assert 'required_prefix=303 max_expansions=1' in report.read_text()
    expanded = verify_bundle(root, 'expanded', SYMBOLS, report, version)
    shards = [verify_bundle(root, f'expanded-{sym}', [sym], report, version) for sym in SYMBOLS]
    final_report = equivalent(root, expanded, shards, 'expanded')
    assert 'N=303 n=300 e=1 u=0 s=299' in final_report.read_text()
    extra = {(d['symbol'], d['day_start']) for d in s['draws'][300:]}
    base_rows = read(whole, 'corrections.jsonl')
    assert not any((r['symbol'], r['timestamp']//DAY*DAY) in extra for r in base_rows)
    rows = [r for b in shards for r in read(b, 'corrections.jsonl') if (r['symbol'], r['timestamp']//DAY*DAY) in extra]
    assert len(rows) == 3*25*6
    assert all(r['decision'] == 'KEEP' and r['row_action'] == 'include' for r in rows)
    assert (root/'plan/sample_plan.json').read_bytes() == frozen
    # An unselected tail draw is still checked before any prefix or shard filtering.
    s['draws'][-1]['symbol'] = 'OUTSIDEUSDT'
    (root/'plan/sample_plan.json').write_bytes(enc(p))
    rejected = dv1.verify(p3b_root=root/'p3b', download_root=root/'downloads',
        inventory_path=root/'downloads/download_inventory.jsonl', output_root=root/'bad-tail',
        policy_path=root/'plan/policy.json', readable=p['readable'], symbols=['AUSDT'],
        sample_plan_path=root/'plan/sample_plan.json')
    assert rejected['primary_file'] is None and 'SAMPLE_SCOPE' in rejected['reason_codes']
