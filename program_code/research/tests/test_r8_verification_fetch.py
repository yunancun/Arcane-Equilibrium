"""DV3 offline acceptance: independently fixed expectations, no market requests."""
import gzip
import hashlib
import json
from pathlib import Path
import socket
import sys
from fractions import Fraction

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
from program_code.research.r8_data import verification_fetch as v

D = 86400000
H = 3600000
T = 1577836800000  # 2020-01-01 UTC
M = 'a' * 64


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*a, **kw):
        raise AssertionError('network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)


def source(tmp, symbol='AUSDT', days=14, *, extra=(), turnover='1e8'):
    inputs = []
    for interval in ('60', 'D'):
        rows = ['timestamp,open,high,low,close,volume,turnover']
        for day in range(days):
            for hour in (range(24) if interval == '60' else (0,)):
                rows.append(f'{T+day*D+hour*H},BAD,0,-1,NaN,-2,{turnover}')
        if interval == '60':
            rows.extend(extra)
        p = tmp / f'{symbol}_{interval}.csv.gz'
        p.write_bytes(gzip.compress(('\n'.join(rows)+'\n').encode(),mtime=0))
        inputs.append(v.CSVSource(symbol, 'kline', interval, p.name, hashlib.sha256(p.read_bytes()).hexdigest()))
    manifest_path=tmp/'manifest.json'
    manifest=json.loads(manifest_path.read_bytes()) if manifest_path.exists() else {'files':{},'universe':{}}
    for src in inputs:
        manifest['files'][src.relative_path]={'dataset':src.dataset,'symbol':src.symbol,'interval':src.interval,'sha256':src.sha256}
    manifest['universe'][symbol]={'launchTime':T,'deliveryTime':0}
    manifest_path.write_bytes(v.encoded(manifest))
    return inputs


def plan(tmp, inputs, end=T+14*D, **kw):
    return v.build_sample_plan(tmp, tmp/'out', inputs, readable={'start':T,'end':end},
                               p3b_manifest_sha256=hashlib.sha256((tmp/'manifest.json').read_bytes()).hexdigest(), **kw)


def artifact(result):
    assert set(result) == {'schema_version','status','artifact_root','primary_file','primary_sha256','files','reason_codes'}
    assert result['schema_version'] == 'r8_verification_handoff_v1'
    p = Path(result['artifact_root']) / result['primary_file']
    assert hashlib.sha256(p.read_bytes()).hexdigest() == result['primary_sha256']
    return json.loads(p.read_bytes())


def test_population_uses_grid_not_l1_and_tier_uses_original_prior_twelve_days(tmp_path):
    inputs=source(tmp_path,extra=[f'{T},garbage,garbage,garbage,garbage,garbage,garbage'])
    r=plan(tmp_path,inputs)
    p=artifact(r)
    assert r['status']=='READY'
    assert [(s['tier'],s['population_size']) for s in p['strata']]==[('GE_100M',2),('NO_OPEN',12)]
    assert p['seed']==20261022
    assert p['readable']=={'start':T,'end':T+14*D}
    assert (tmp_path/'out'/'sample_plan.sha256').read_text()==r['primary_sha256']+'\n'


def test_outside_scope_numeric_bombs_are_not_decoded_and_bytes_repeat(tmp_path):
    inputs=source(tmp_path,extra=[f'{T-1},BOOM,BOOM,BOOM,BOOM,BOOM,BOOM',f'{T+14*D},BOOM,BOOM,BOOM,BOOM,BOOM,BOOM'])
    a=plan(tmp_path,inputs)
    b=v.build_sample_plan(tmp_path,tmp_path/'again',list(reversed(inputs)),readable={'start':T,'end':T+14*D},p3b_manifest_sha256=hashlib.sha256((tmp_path/'manifest.json').read_bytes()).hexdigest())
    assert a['primary_sha256']==b['primary_sha256']
    assert Path(a['artifact_root'],'sample_plan.json').read_bytes()==Path(b['artifact_root'],'sample_plan.json').read_bytes()


def test_invalid_timestamp_stops_without_excluding_population(tmp_path):
    r=plan(tmp_path,source(tmp_path,extra=['bad,1,2,1,2,1,2']))
    assert r['status']=='BLOCKED' and r['primary_file'] is None
    assert 'INVALID_TIMESTAMP' in r['reason_codes']


def test_python312_draw_order_is_fixed_across_strata(tmp_path):
    p=artifact(plan(tmp_path,source(tmp_path)))
    assert [[(d['day_start']-T)//D for d in s['draws']] for s in p['strata']]==[
        [13,12], [2,0,3,9,8,10,5,4,1,6,11,7]]
    assert [[d['rank'] for d in s['draws']] for s in p['strata']]==[list(range(1,3)),list(range(1,13))]


@pytest.mark.parametrize('amount,tier',[('1e8','GE_100M'),('99999999.999999999999999999999999999','GE_10M'),
    ('1e7','GE_10M'),('9999999.99999999999999999999','GE_1M'),('1e6','GE_1M'),('999999.999999999999999999','NO_OPEN')])
def test_tier_thresholds_exact_decimal_no_binary64(tmp_path,amount,tier):
    p=artifact(plan(tmp_path,source(tmp_path,turnover=amount)))
    assert next(s['tier'] for s in p['strata'] if any(d['day_start']==T+13*D for d in s['draws']))==tier


def test_partial_days_known_truncation_and_bad_timestamps_do_not_sneak_in(tmp_path):
    inputs=source(tmp_path)
    p=artifact(plan(tmp_path,inputs,end=T+13*D+H,truncated_days=[('AUSDT',T+12*D)]))
    assert sum(s['population_size'] for s in p['strata'])==12


def test_sequence_seal_conflict_prevents_sample_disclosure(tmp_path):
    inputs=source(tmp_path)
    (tmp_path/'out').mkdir(); (tmp_path/'out'/'sample_plan.sha256').write_text('preexisting\n')
    r=plan(tmp_path,inputs)
    assert r['status']=='BLOCKED'
    assert not (tmp_path/'out'/'sample_plan.json').exists()


def test_holdout_rejected_before_source_reads(tmp_path):
    r=v.build_sample_plan(tmp_path,tmp_path/'out',[],readable={'start':T,'end':v.TRAIN_END+1},p3b_manifest_sha256=M)
    assert r['reason_codes']==['SCOPE_NOT_AUTHORIZED']


@pytest.mark.parametrize('N,n,x,alpha,expected',[(10,5,0,Fraction(1,20),3),
    (10,5,1,Fraction(1,20),5),(10,5,0,Fraction(1,60),4),(10,10,2,Fraction(1,20),2),
    (10,5,5,Fraction(1,20),10)])
def test_hypergeometric_exact_integer_inversion(N,n,x,alpha,expected):
    # Hand check: C(7,5)/C(10,5)=21/252 >= .05; C(6,5)/252=6/252 < .05.
    assert v.hypergeometric_upper(N,n,x,alpha)==Fraction(expected,N)


def test_missing_samples_remain_unresolved_and_full_census_bound_is_exact(tmp_path):
    p=plan(tmp_path,source(tmp_path,days=2),end=T+2*D)
    r=v.summarize_sample(tmp_path/'out',[],tmp_path/'summary')
    assert r['status']=='BLOCKED' and 'UPPER_LIMIT_EXCEEDED' in r['reason_codes']
    text=Path(r['artifact_root'],r['primary_file']).read_text()
    assert 'N=2 n=2 e=0 u=2 s=0' in text
    assert 'conservative_upper=1/1' in text


@pytest.mark.skip(reason='DV1 actual implementation absent on accepted main d6b162092; requires real bundle and bidirectional handoff in DV4 integration')
def test_pending_real_dv1_bundle_counts_expansion_and_dv3_artifacts_consumed():
    pass


class Clock:
    def __init__(self): self.t=0
    def __call__(self): return self.t
    def sleep(self,n): self.t+=n


def request(i=1,symbol='AUSDT',day=T):
    from datetime import datetime,timezone
    date=datetime.fromtimestamp(day//1000,timezone.utc).strftime('%Y-%m-%d')
    return v.DownloadRequest(str(i),symbol,day,'trade','bybit_trade',f'https://public.bybit.com/trading/{symbol}/{symbol}{date}.csv.gz')


class FakeTransport:
    def __init__(self,clock,heads=None,gets=None):
        self.clock=clock; self.calls=[]; self.heads=heads or {}; self.gets=gets or {}
    def __call__(self,method,url):
        self.calls.append((method,url,self.clock()))
        status,headers,body=(self.heads if method=='HEAD' else self.gets).get(url,(200,{'Content-Length':'3'},b'abc'))
        return v.Response(status,headers,__import__('io').BytesIO(body))


def download(tmp,requests,*,heads=None,gets=None,readable=None,approved=None,**kw):
    clock=Clock(); send=FakeTransport(clock,heads,gets)
    r=v.fetch_downloads(tmp/'download',requests,approved_urls=[x.url for x in requests] if approved is None else approved,
        readable=readable or {'start':T,'end':T+30*D},max_total_bytes=kw.pop('max_total_bytes',100),
        max_file_bytes=kw.pop('max_file_bytes',100),transport=send,clock=clock,sleep=clock.sleep,now=lambda:T,**kw)
    rows=[]
    if r['primary_file']:
        rows=[json.loads(x) for x in (tmp/'download'/r['primary_file']).read_bytes().splitlines()]
    return r,rows,send.calls


def test_download_preflight_all_before_get_and_sha_inventory_contract(tmp_path):
    a,b=request(2),request(1,'BUSDT')
    r,rows,calls=download(tmp_path,[b,a])
    assert r['status']=='READY'
    assert [c[0] for c in calls]==['HEAD','HEAD','GET','GET']
    assert [x['symbol'] for x in rows]==['AUSDT','BUSDT']
    assert all(x['sha256']=='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad' for x in rows)
    assert all(x['byte_count']==3 and x['status']=='AVAILABLE' for x in rows)
    assert set(rows[0])==set('schema_version request_id symbol day_start interval source_kind url started_at finished_at http_status api_status byte_count relative_path sha256 status reason_code'.split())


@pytest.mark.parametrize('headers,limit,reason',[({},100,'UNKNOWN_LENGTH'),({'Content-Length':'101'},100,'SIZE_LIMIT'),({'Content-Length':'NaN'},100,'UNKNOWN_LENGTH')])
def test_unknown_length_or_oversize_stops_entire_preflight(tmp_path,headers,limit,reason):
    a,b=request(),request(2,'BUSDT')
    r,rows,calls=download(tmp_path,[a,b],heads={a.url:(200,headers,b'')},max_total_bytes=limit)
    assert r['status']=='BLOCKED'
    assert not any(c[0]=='GET' for c in calls)
    assert all(x['status']=='SIZE_BLOCKED' for x in rows)
    assert reason in r['reason_codes']


@pytest.mark.parametrize('status',[403,429])
def test_host_stops_after_forbidden_or_rate_limit(tmp_path,status):
    a,b=request(),request(2,'BUSDT')
    r,rows,calls=download(tmp_path,[a,b],heads={a.url:(status,{},b'')})
    assert len(calls)==1 and len(rows)==2
    assert rows[0]['http_status']==status
    assert rows[1]['reason_code']=='HOST_STOPPED'
    assert all(x['status']=='UNAVAILABLE' for x in rows)


def test_rate_limit_counts_head_and_get(tmp_path):
    requests=[request(i+1,f'{c}USDT') for i,c in enumerate('ABCDE')]
    _,_,calls=download(tmp_path,requests)
    times=[c[2] for c in calls]
    assert len(times)==10
    assert all(sum(t<=other<t+1 for other in times)<=4 for t in times)


def test_partial_day_has_scope_incomplete_and_zero_requests(tmp_path):
    r,rows,calls=download(tmp_path,[request()],readable={'start':T+H,'end':T+D})
    assert calls==[] and rows[0]['status']=='SCOPE_INCOMPLETE'


@pytest.mark.parametrize('url',[
 'http://public.bybit.com/trading/AUSDT/AUSDT2020-01-01.csv.gz',
 'https://user:pass@public.bybit.com/trading/AUSDT/AUSDT2020-01-01.csv.gz',
 'https://public.bybit.com.evil/trading/AUSDT/AUSDT2020-01-01.csv.gz',
 'https://public.bybit.com/trading/AUSDT/../AUSDT2020-01-01.csv.gz',
 'https://public.bybit.com/trading/BUSDT/BUSDT2020-01-01.csv.gz',
 'https://public.bybit.com/trading/AUSDT/AUSDT2020-01-02.csv.gz',
 'https://api.bybit.com/v5/order/create'])
def test_url_pattern_and_identity_allowlist_fail_closed(tmp_path,url):
    a=v.DownloadRequest('1','AUSDT',T,'trade','bybit_trade',url)
    r,rows,calls=download(tmp_path,[a])
    assert calls==[] and rows[0]['status']=='UNAVAILABLE' and r['status']=='BLOCKED'


def test_exact_approved_list_required_even_for_allowlisted_host(tmp_path):
    r,rows,calls=download(tmp_path,[request()],approved=[])
    assert calls==[] and rows[0]['reason_code']=='URL_NOT_APPROVED'


def test_get_size_change_is_blocked_and_no_unbounded_body_read(tmp_path):
    a=request()
    r,rows,calls=download(tmp_path,[a],gets={a.url:(200,{'Content-Length':'4'},b'abcd')})
    assert r['status']=='BLOCKED' and rows[0]['status']=='SIZE_BLOCKED'
    assert rows[0]['sha256'] is None


def test_duplicate_url_download_once_but_requests_retained(tmp_path):
    r,rows,calls=download(tmp_path,[request(1),request(2)])
    assert len(calls)==2 and len(rows)==2
    assert rows[0]['sha256']==rows[1]['sha256']


def test_unknown_length_immediately_stops_further_heads(tmp_path):
    a,b=request(),request(2,'BUSDT')
    _,_,calls=download(tmp_path,[a,b],heads={a.url:(200,{},b'')})
    assert len(calls)==1


def test_get_size_change_stops_rest_of_batch(tmp_path):
    a,b=request(),request(2,'BUSDT')
    _,rows,calls=download(tmp_path,[a,b],gets={a.url:(200,{'Content-Length':'4'},b'abcd')})
    assert [c[0] for c in calls]==['HEAD','HEAD','GET']
    assert rows[1]['status']=='SIZE_BLOCKED'


def test_manifest_membership_and_hash_are_required(tmp_path):
    inputs=source(tmp_path)
    manifest=json.loads((tmp_path/'manifest.json').read_bytes())
    manifest['files'][inputs[0].relative_path]['sha256']='b'*64
    (tmp_path/'manifest.json').write_bytes(v.encoded(manifest))
    assert plan(tmp_path,inputs)['reason_codes']==['SOURCE_NOT_IN_FROZEN_MANIFEST']


def test_known_launch_window_from_manifest_excludes_partial_day(tmp_path):
    inputs=source(tmp_path)
    manifest=json.loads((tmp_path/'manifest.json').read_bytes())
    manifest['universe']['AUSDT']['launchTime']=T+H
    (tmp_path/'manifest.json').write_bytes(v.encoded(manifest))
    p=artifact(plan(tmp_path,inputs))
    assert sum(s['population_size'] for s in p['strata'])==13


def test_api_only_status_decoded_never_market_numbers(tmp_path,monkeypatch):
    a=v.DownloadRequest('1','AUSDT',T,'1','bybit_minute',f'https://api.bybit.com/v5/market/kline?category=linear&symbol=AUSDT&interval=1&start={T}&end={T+59999}&limit=1')
    body=b'{"retCode":0,"result":{"list":[[999999999999999999,1e999,"SCOPE_BOMB"]]}}'
    real=json.loads
    def guard(value,*args,**kwargs):
        if b'SCOPE_BOMB' in (value.encode() if isinstance(value,str) else value):
            raise AssertionError('market JSON decoded')
        return real(value,*args,**kwargs)
    monkeypatch.setattr(v.json,'loads',guard)
    _,rows,calls=download(tmp_path,[a],heads={a.url:(200,{'Content-Length':str(len(body))},b'')},gets={a.url:(200,{'Content-Length':str(len(body))},body)},flagged_days=[('AUSDT',T)])
    assert rows[0]['status']=='AVAILABLE' and rows[0]['api_status']==0


def dv1_fixture(tmp,p,days,*,error=False,unresolved=False,semantic=False):
    """Isolated fixed-format fixture, expressly NOT the required real DV1 test."""
    root=tmp/'dv1'; root.mkdir()
    original=b'timestamp,open,high,low,close,volume,turnover\n1577836800000,1,1,1,1,1,1\n'
    (root/'source.csv').write_bytes(original)
    ref={k:None for k in 'kind relative_path url sha256 row request_id list_index byte_start byte_end trade_id line_sha256'.split()}
    ref.update(kind='csv',relative_path='source.csv',sha256=hashlib.sha256(original).hexdigest(),row=2)
    rows=[]
    for day in days:
        for interval,times in [('D',[day]),('60',range(day,day+D,H))]:
            for t in times:
                for field in ('open','high','low','close','volume','turnover'):
                    changed=error and interval=='D' and field=='close'
                    pending=unresolved and field=='volume'
                    rows.append(dict(schema_version='r8_data_correction_v1',correction_id=f'{interval}-{t}-{field}',symbol='AUSDT',dataset='kline',interval=interval,timestamp=t,field=field,original_value='1',candidate_value='2' if changed else '1',corrected_value='2' if changed else None,unit='USDT',formula='fixed fixture',evidence_kind='reported_turnover_selection' if semantic and field=='turnover' else 'trade_adjudication',source_refs=[ref],coverage_status='PASS',order_status='UNIQUE',rule_ids=['C5_REBUILD'],decision='CORRECT' if changed else 'UNRESOLVED' if pending else 'KEEP',reason_code='FIXTURE_UNRESOLVED' if pending else 'FIXTURE',row_action='missing' if pending else 'include',policy_sha256=p['policy_sha256'],approval_event='RH-20261022-04',supersedes=None))
    rows.sort(key=lambda r:(r['timestamp'],r['symbol'],r['dataset'],r['interval'],r['field'],r['correction_id']))
    data=b''.join(v.encoded(x) for x in rows)
    (root/'corrections.jsonl').write_bytes(data); (root/'findings.jsonl').write_bytes(b'')
    verification=dict(schema_version='r8_data_verification_v1',status='READY',policy_sha256=p['policy_sha256'],p3b_manifest_sha256=p['p3b_manifest_sha256'],sample_plan_sha256=hashlib.sha256(v.encoded(p)).hexdigest(),previous_corrections_sha256=None,review_refs=[],tool_commit='c'*40,readable=p['readable'],counts=dict(input_rows=len(rows),checked_days=len(days),flagged_days=int(error or unresolved),corrected_fields=int(error),unresolved_rows=int(unresolved)),files={'findings.jsonl':{'sha256':hashlib.sha256(b'').hexdigest(),'rows':0},'corrections.jsonl':{'sha256':hashlib.sha256(data).hexdigest(),'rows':len(rows)}},reason_codes=['REVIEW_PENDING'])
    (root/'verification.json').write_bytes(v.encoded(verification))
    return root


def test_error_deduplicates_unresolved_same_day_and_semantics_kept(tmp_path):
    p=artifact(plan(tmp_path,source(tmp_path,days=1),end=T+D))
    root=dv1_fixture(tmp_path,p,[T],error=True,unresolved=True)
    r=v.summarize_sample(tmp_path/'out',[root],tmp_path/'summary')
    assert 'N=1 n=1 e=1 u=0 s=0' in Path(r['artifact_root'],r['primary_file']).read_text()


def test_complete_census_keep_semantic_has_zero_bound(tmp_path):
    p=artifact(plan(tmp_path,source(tmp_path,days=1),end=T+D))
    root=dv1_fixture(tmp_path,p,[T],semantic=True)
    r=v.summarize_sample(tmp_path/'out',[root],tmp_path/'summary')
    assert r['status']=='READY'
    text=Path(r['artifact_root'],r['primary_file']).read_text()
    assert 'N=1 n=1 e=0 u=0 s=1' in text
    assert 'conservative_upper=0/1' in text


def test_expansion_only_frozen_prefix_and_base_denominator_unchanged(tmp_path):
    inputs=source(tmp_path,days=365)
    p=artifact(plan(tmp_path,inputs,end=T+365*D))
    s=p['strata'][0]
    assert (s['population_size'],s['base_size'],s['max_size'])==(353,300,353)
    # Expanded day reports an error. Base remains all 300 uncompleted, not 353.
    root=dv1_fixture(tmp_path,p,[s['draws'][300]['day_start']],error=True)
    r=v.summarize_sample(tmp_path/'out',[root],tmp_path/'summary')
    text=Path(r['artifact_root'],r['primary_file']).read_text()
    assert 'N=353 n=300 e=0 u=300 s=0' in text
    assert 'required_prefix=353 max_expansions=1' in text
    assert 'EXPANSION_FAILED_REFER_CONDUCTOR' in r['reason_codes']


@pytest.mark.parametrize('mutation',['unknown','duplicate','hash','wrong_policy','invalid_type'])
def test_strict_fixed_bundle_rejects_invalid_schema_or_hash(tmp_path,mutation):
    p=artifact(plan(tmp_path,source(tmp_path,days=1),end=T+D))
    root=dv1_fixture(tmp_path,p,[T]); path=root/'verification.json'; value=json.loads(path.read_bytes())
    if mutation=='unknown': value['result']={}
    if mutation=='hash': value['files']['corrections.jsonl']['sha256']='0'*64
    if mutation=='wrong_policy': value['policy_sha256']='0'*64
    if mutation=='invalid_type': value['counts']['checked_days']=True
    path.write_bytes(v.encoded(value))
    if mutation=='duplicate': path.write_bytes(path.read_bytes().replace(b'{',b'{"status":"READY",',1))
    r=v.summarize_sample(tmp_path/'out',[root],tmp_path/'summary')
    assert r['status']=='BLOCKED' and r['primary_file'] is None


def test_plan_unknown_field_rejected_even_with_matching_seal(tmp_path):
    p=artifact(plan(tmp_path,source(tmp_path)))
    p['strata'][0]['draws'][0]['price']='DO_NOT_READ'
    data=v.encoded(p); (tmp_path/'out'/'sample_plan.json').write_bytes(data)
    (tmp_path/'out'/'sample_plan.sha256').write_text(hashlib.sha256(data).hexdigest()+'\n')
    r=v.summarize_sample(tmp_path/'out',[],tmp_path/'summary')
    assert r['reason_codes']==['INVALID_FIELDS']


def test_missing_evidence_cannot_become_successful_complete_day(tmp_path):
    p=artifact(plan(tmp_path,source(tmp_path,days=1),end=T+D))
    root=dv1_fixture(tmp_path,p,[T]); path=root/'corrections.jsonl'
    rows=[json.loads(x) for x in path.read_bytes().splitlines()]
    for row in rows: row['source_refs']=[]
    data=b''.join(v.encoded(x) for x in rows); path.write_bytes(data)
    info=json.loads((root/'verification.json').read_bytes()); info['files']['corrections.jsonl']['sha256']=hashlib.sha256(data).hexdigest()
    (root/'verification.json').write_bytes(v.encoded(info))
    assert v.summarize_sample(tmp_path/'out',[root],tmp_path/'summary')['status']=='BLOCKED'


@pytest.mark.parametrize('kind,url,interval',[
 ('binance_hour','https://data.binance.vision/data/futures/um/daily/klines/AUSDT/1h/AUSDT-1h-2020-01-01.zip','60'),
 ('okx_hour',f'https://www.okx.com/api/v5/market/history-candles?instId=A-USDT-SWAP&bar=1H&before={T-1}&after={T+D}&limit=24','60')])
def test_other_approved_sources_and_api_status(tmp_path,kind,url,interval):
    a=v.DownloadRequest('1','AUSDT',T,interval,kind,url)
    body=b'{"code":"0","data":[]}' if kind=='okx_hour' else b'zip'
    r,rows,_=download(tmp_path,[a],heads={url:(200,{'Content-Length':str(len(body))},b'')},gets={url:(200,{'Content-Length':str(len(body))},body)})
    assert r['status']=='READY' and rows[0]['status']=='AVAILABLE'


def test_reuse_is_hash_verified_no_request_no_duplicate_payload_budget(tmp_path):
    a=request(); p=tmp_path/'existing.gz'; p.write_bytes(b'abc')
    r,rows,calls=download(tmp_path,[a],reuse={a.url:(p,hashlib.sha256(b'abc').hexdigest())},max_total_bytes=0)
    assert r['status']=='READY' and calls==[] and rows[0]['reason_code']=='REUSED'


def test_symlink_output_is_rejected(tmp_path):
    inputs=source(tmp_path); (tmp_path/'other').mkdir(); (tmp_path/'out').symlink_to(tmp_path/'other')
    assert plan(tmp_path,inputs)['reason_codes']==['UNSAFE_PATH']


def test_http_get_forbidden_stops_host_and_preserves_failed_inventory(tmp_path):
    a,b=request(),request(2,'BUSDT')
    _,rows,calls=download(tmp_path,[a,b],gets={a.url:(429,{},b'')})
    assert [c[0] for c in calls]==['HEAD','HEAD','GET']
    assert rows[1]['reason_code']=='HOST_STOPPED'


def test_empty_scope_batch_cannot_claim_success(tmp_path):
    r,rows,calls=download(tmp_path,[])
    assert r['status']=='BLOCKED' and calls==[]


def test_twenty_four_strata_and_300_900_sizes(tmp_path):
    inputs=[]
    for symbol,amount in [('AUSDT','1e8'),('BUSDT','1e7'),('CUSDT','1e6'),('DUSDT','1')]:
        inputs+=source(tmp_path,symbol,days=2008,turnover=amount)
    p=artifact(plan(tmp_path,inputs,end=v.TRAIN_END))
    assert [(s['year'],s['tier']) for s in p['strata']]==[(y,tier) for y in range(2020,2026) for tier in ('GE_100M','GE_10M','GE_1M','NO_OPEN')]
    assert p['strata'][0]['base_size']==300
    assert p['strata'][0]['max_size']==354
    assert p['strata'][-1]['base_size']==181


def test_large_stratum_draws_match_independent_python312_golden(tmp_path):
    inputs=[]
    for symbol in 'ABCDEFGHIJKLM':
        inputs+=source(tmp_path,symbol+'USDT',days=365)
    p=artifact(plan(tmp_path,inputs,end=T+365*D)); s=p['strata'][0]
    assert (s['population_size'],s['base_size'],s['max_size'])==(4589,300,900)
    # Captured from the installed, unmodified CPython 3.12 random.Random.sample,
    # independently of this module; covers its large-population set branch.
    assert hashlib.sha256(v.encoded(s['draws'])).hexdigest()=='76363617a540379531cf80e67ac8b8c7531bf8fe5d53fab8bc175c20b27b8bb2'


def test_production_transport_verifies_tls_no_auth_proxy_or_redirect(monkeypatch):
    import ssl
    captured={}
    class Result:
        code=200; headers={'Content-Length':'0'}
    class Opener:
        def open(self,request,timeout):
            captured['request']=request; captured['timeout']=timeout
            return Result()
    def build(*handlers):
        captured['handlers']=handlers
        return Opener()
    monkeypatch.setattr(v,'build_opener',build)
    v._transport('HEAD','https://public.bybit.com/trading/AUSDT/AUSDT2020-01-01.csv.gz')
    proxy,https,redirect=captured['handlers']
    assert proxy.proxies=={}
    assert https._context.verify_mode==ssl.CERT_REQUIRED and https._context.check_hostname
    assert redirect.redirect_request(None,None,302,'',{},'https://evil/') is None
    assert set(captured['request'].headers)=={'User-agent','Accept-encoding'}


def test_e2_manifest_population_cannot_be_narrowed_by_omitting_symbol(tmp_path):
    only_a=source(tmp_path,'AUSDT')
    source(tmp_path,'BUSDT')
    r=plan(tmp_path,only_a)
    assert r['status']=='BLOCKED' and r['primary_file'] is None
    assert r['reason_codes']==['INCOMPLETE_MANIFEST_SOURCES']
    assert not (tmp_path/'out'/'sample_plan.sha256').exists()


def test_e2_nonexistent_referenced_evidence_blocks_summary(tmp_path):
    p=artifact(plan(tmp_path,source(tmp_path,days=1),end=T+D))
    root=dv1_fixture(tmp_path,p,[T])
    referenced=root/'source.csv'
    if referenced.exists(): referenced.unlink()
    r=v.summarize_sample(tmp_path/'out',[root],tmp_path/'summary')
    assert r['status']=='BLOCKED' and r['primary_file'] is None
    assert r['reason_codes']==['SOURCE_EVIDENCE_UNAVAILABLE']


def test_e2_referenced_evidence_hash_mismatch_blocks_summary(tmp_path):
    p=artifact(plan(tmp_path,source(tmp_path,days=1),end=T+D))
    root=dv1_fixture(tmp_path,p,[T]); (root/'source.csv').write_bytes(b'tampered')
    r=v.summarize_sample(tmp_path/'out',[root],tmp_path/'summary')
    assert r['status']=='BLOCKED' and r['reason_codes']==['SOURCE_EVIDENCE_HASH_MISMATCH']


@pytest.mark.parametrize('status',[404,500])
def test_e2_failed_head_prevents_get_of_other_host(tmp_path,status):
    a=request(); b=v.DownloadRequest('2','BUSDT',T,'60','binance_hour','https://data.binance.vision/data/futures/um/daily/klines/BUSDT/1h/BUSDT-1h-2020-01-01.zip')
    r,rows,calls=download(tmp_path,[a,b],heads={a.url:(status,{},b'')})
    assert r['status']=='BLOCKED' and len(rows)==2
    assert len(calls)==1
    assert not any(c[0]=='GET' for c in calls)
    assert rows[0]['http_status']==status and rows[0]['reason_code']=='HTTP_UNAVAILABLE'


def test_e2_head_transport_error_prevents_any_get(tmp_path):
    a,b=request(),request(2,'BUSDT'); calls=[]
    def send(method,url):
        calls.append((method,url))
        if url==a.url: raise OSError('simulated')
        return v.Response(200,{'Content-Length':'3'},__import__('io').BytesIO(b'abc'))
    c=Clock()
    r=v.fetch_downloads(tmp_path/'out',[a,b],approved_urls=[a.url,b.url],readable={'start':T,'end':T+D},max_total_bytes=10,max_file_bytes=10,transport=send,clock=c,sleep=c.sleep,now=lambda:T)
    assert r['status']=='BLOCKED' and not any(method=='GET' for method,url in calls)
    assert len(calls)==1
