"""Independent §3–§8.4 examples. No expected values are computed by DV1.

DV3 integration uses real implementations with an offline transport. The oracle was frozen
from report C and a separate timestamp-set audit before verification.py existed.
"""
from pathlib import Path
import csv
import gzip
import hashlib
import io
import json
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from program_code.research.r8_data.verification import verify

DAY = 86400000
HOUR = 3600000
T = 1609459200000  # 2021-01-01, within the frozen training range
FIELDS = ('open', 'high', 'low', 'close', 'volume', 'turnover')
SPEC = Path(__file__).resolve().parents[3] / 'docs/execution_plan/2026-10-22--r8-stage2-data-verification-standard.md'
HANDOFF_KEYS = {'schema_version','status','artifact_root','primary_file','primary_sha256','files','reason_codes'}
FINDING_KEYS = {'schema_version','finding_id','symbol','dataset','interval','timestamp','field','rule_id','reason_code','source_refs','details'}
CORRECTION_KEYS = {'schema_version','correction_id','symbol','dataset','interval','timestamp','field','original_value','candidate_value','corrected_value','unit','formula','evidence_kind','source_refs','coverage_status','order_status','rule_ids','decision','reason_code','row_action','policy_sha256','approval_event','supersedes'}
VERIFICATION_KEYS = {'schema_version','status','policy_sha256','p3b_manifest_sha256','sample_plan_sha256','previous_corrections_sha256','review_refs','tool_commit','readable','counts','files','reason_codes'}
SOURCE_KEYS = {'kind','relative_path','url','sha256','row','request_id','list_index','byte_start','byte_end','trade_id','line_sha256'}


def enc(x):
    return (json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)+'\n').encode()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def policy(manifest):
    return dict(schema_version='r8_data_verification_policy_v1', standard_sha256=sha(SPEC.read_bytes()), approval_event='RH-20261022-04', p3b_manifest_sha256=manifest,
                listing=dict(x_pct='50',y_pct='20',z_pct='20',cooling_days=7,quantity='hourly_base_volume_daily_mean',variation='mean_relative_difference',stage_end_ranges=[[1,3],[7,15],[15,30]]),
                sampling=dict(seed=20261022,base_per_stratum=300,max_per_stratum=900,max_expansions=1,confidence='0.95',upper_limit='0.025'),
                turnover=dict(window_days=12,thresholds=['1000000','10000000','100000000'],trigger_pct='5',general='exchange_reported',suspect='sum_hourly_reported'),l4_price_threshold_pct='1')


def bar(t, **kw):
    r=dict(timestamp=t,open='10',high='10',low='10',close='10',volume='1',turnover='10')
    r.update(kw)
    return r


class Case:
    def __init__(self, root):
        self.root=root; self.p3b=root/'p3b'; self.dl=root/'downloads'
        self.p3b.mkdir(); self.dl.mkdir()
        self.daily=[bar(T,volume='24',turnover='240')]
        self.hours=[bar(T+i*HOUR) for i in range(24)]
        self.trades=[dict(timestamp=str((T+i*HOUR)//1000)+'.0000001',symbol='TESTUSDT',side='Buy',size='1',price='10',trdMatchID=str(i)) for i in range(24)]
        self.extra_inventory=[]; self.policy_change=None; self.first=T-HOUR; self.delivery=0
        self.readable={'start':T,'end':T+DAY}; self.outputs=0

    def write(self):
        files={}; requests=[]
        for interval, rows in [('D',self.daily),('60',self.hours)]:
            rawrows=[[str(r['timestamp'])]+[r[f] for f in FIELDS] for r in rows]
            rid=len(requests)+1; raw=enc({'retCode':0,'result':{'category':'linear','symbol':'TESTUSDT','list':rawrows}})
            (self.p3b/'raw').mkdir(exist_ok=True); (self.p3b/f'raw/{rid}.json').write_bytes(raw)
            requests.append(dict(request_id=rid,base_url='https://api.bybit.com',endpoint='/v5/market/kline',params=dict(category='linear',symbol='TESTUSDT',interval=interval),http_status=200,retCode=0,raw_sha256=sha(raw)))
            s=io.StringIO(); w=csv.writer(s,lineterminator='\n'); w.writerow(['timestamp',*FIELDS]); w.writerows(rawrows)
            data=gzip.compress(s.getvalue().encode(),mtime=0); name=f'kline_TESTUSDT_{interval}.csv.gz'; (self.p3b/name).write_bytes(data)
            files[name]=dict(sha256=sha(data),dataset='kline',symbol='TESTUSDT',interval=interval,source_request_ids=[rid],first_timestamp=self.first,last_timestamp=T+DAY-HOUR)
        req=b''.join(enc(r) for r in requests); (self.p3b/'requests.jsonl').write_bytes(req)
        inst=enc({'retCode':0,'result':{'category':'linear','list':[dict(symbol='TESTUSDT',baseCoin='TEST',quoteCoin='USDT',settleCoin='USDT',contractType='LinearPerpetual',deliveryTime=str(self.delivery),launchTime=str(self.first))]}})
        (self.p3b/'raw/3.json').write_bytes(inst)
        requests.append(dict(request_id=3,base_url='https://api.bybit.com',endpoint='/v5/market/instruments-info',params={'category':'linear'},http_status=200,retCode=0,raw_sha256=sha(inst)))
        req=b''.join(enc(r) for r in requests);(self.p3b/'requests.jsonl').write_bytes(req)
        manifest=enc(dict(files=files,request_log_sha256=sha(req),universe_request_ids=[3],universe={'TESTUSDT':{'deliveryTime':self.delivery}},tool_version='r8-public-data-2'))
        (self.p3b/'manifest.json').write_bytes(manifest)
        p=policy(sha(manifest))
        if self.policy_change:self.policy_change(p)
        (self.root/'policy.json').write_bytes(enc(p))
        inv=[]
        if self.trades is not None:
            s=io.StringIO();w=csv.DictWriter(s,fieldnames=['timestamp','symbol','side','size','price','trdMatchID'],lineterminator='\n');w.writeheader();w.writerows(self.trades)
            b=gzip.compress(s.getvalue().encode(),mtime=0); (self.dl/'trades.csv.gz').write_bytes(b)
            inv.append(dict(schema_version='r8_verification_download_v1',request_id='trades',symbol='TESTUSDT',day_start=T,interval='trade',source_kind='bybit_trade',url='https://public.bybit.com/trading/TESTUSDT/TESTUSDT2021-01-01.csv.gz',started_at=T,finished_at=T+1,http_status=200,api_status=None,byte_count=len(b),relative_path='trades.csv.gz',sha256=sha(b),status='AVAILABLE',reason_code=None))
        inv+=self.extra_inventory
        inv.sort(key=lambda x:(x['symbol'],x['day_start'],x['source_kind'],x['interval'],x['request_id']))
        (self.dl/'download_inventory.jsonl').write_bytes(b''.join(enc(r) for r in inv))

    def run(self, **kw):
        self.write();self.outputs+=1
        out=self.root/f'out{self.outputs}'
        result=verify(p3b_root=self.p3b,download_root=self.dl,inventory_path=self.dl/'download_inventory.jsonl',output_root=out,policy_path=self.root/'policy.json',readable=self.readable,symbols=['TESTUSDT'],**kw)
        return result, read(out,'findings.jsonl'), read(out,'corrections.jsonl'), read(out,'verification.json')


def read(out,name):
    p=out/name
    if not p.exists(): return [] if name.endswith('jsonl') else {}
    return [json.loads(l) for l in p.read_bytes().splitlines()] if name.endswith('jsonl') else json.loads(p.read_bytes())


def correction(cs,field,interval='D',timestamp=T):
    return next(c for c in cs if c['interval']==interval and c['timestamp']==timestamp and c['field']==field)


V2 = 'v2-terminal-suffix-20261022'


def v2_policy(p):
    p.update(schema_version='r8_data_verification_policy_v2',
             approval_event='RH-20261022-05',volume_semantics_policy=V2,
             standard_sha256=sha(SPEC.read_bytes()))


def suffix_case(case):
    # Fixed independent example: 24 original units plus a half-unit tail.
    # The daily original already includes the tail. No width cutoff is allowed.
    case.policy_change=v2_policy
    case.daily[0]['volume']='24.5'
    case.trades.insert(1,dict(timestamp=str(T//1000+1800)+'.0000002',
        symbol='TESTUSDT',side='Sell',size='0.5',price='10',trdMatchID='tail'))


def test_v2_complete_suffix_daily_already_contains_tail_keeps_volume(case):
    suffix_case(case)
    result,findings,cs,v=case.run()
    assert result['status']=='READY',result
    assert v['schema_version']=='r8_data_verification_v2'
    assert v['volume_semantics_policy']==V2
    rows=read(Path(result['artifact_root']),'volume_semantics.jsonl')
    assert len(rows)==24
    h=rows[0]
    assert (h['hour_classification'],h['day_applicable'])==('TERMINAL_SUFFIX_EXACT',True)
    assert (h['tail_count'],h['tail_group_count'],h['tail_volume'])==(1,1,'0.5')
    assert h['tail_first_timestamp']==h['tail_last_timestamp']=='1609461000.0000002'
    assert h['prefix_first_timestamp']=='1609459200.0000001' and h['prefix_count']==1
    assert (h['original_volume'],h['trade_volume'],h['volume_delta'])==('1','1.5','-0.5')
    assert correction(cs,'volume')['decision']=='KEEP'
    assert correction(cs,'volume','60')['corrected_value']=='1.5'
    assert correction(cs,'volume')['volume_source']=='trade_reconstructed_terminal_suffix'
    assert correction(cs,'volume','60',T+HOUR)['volume_source']=='v1_strict'
    assert {'C3_ORIGINAL_FAIL','TERMINAL_SUFFIX_SOURCE_SELECTED','SOURCE_TRUTH_UNVERIFIED'}<=set(h['reason_codes'])
    assert any(f['rule_id']=='C3_QUANTITY' and f['reason_code']=='COVERAGE_CONFLICT' for f in findings)
    assert all(c['row_action']=='include' for c in cs)


@pytest.fixture
def case(tmp_path):return Case(tmp_path)


def test_exact_bundle_handoff_and_deterministic_bytes(case):
    a,fs,cs,v=case.run()
    assert a['status']=='READY' and set(a)==HANDOFF_KEYS
    assert set(v)==VERIFICATION_KEYS
    assert v['counts']==dict(input_rows=25,checked_days=1,flagged_days=0,corrected_fields=0,unresolved_rows=0)
    assert v['review_refs']==[] and 'REVIEW_PENDING' in v['reason_codes']
    assert cs==[]
    for f in fs:
        assert set(f)==FINDING_KEYS
        assert all(set(r)==SOURCE_KEYS for r in f['source_refs'])
    b,*_=case.run()
    assert a['files']==b['files']
    for name,meta in a['files'].items():
        data=(Path(a['artifact_root'])/name).read_bytes()
        assert sha(data)==meta['sha256']
        assert all(enc(json.loads(l))==l+b'\n' for l in data.splitlines())
    assert a['primary_file']=='verification.json'
    assert a['primary_sha256']==a['files']['verification.json']['sha256']
    assert 'verification.json' not in v['files']


@pytest.mark.parametrize('field,value,reason',[
    ('open','0','NONPOSITIVE_PRICE'),('high','-1','NONPOSITIVE_PRICE'),('low','0','NONPOSITIVE_PRICE'),('close','NaN','INVALID_NUMBER'),
    ('volume','-1','NEGATIVE_QUANTITY'),('turnover','-1','NEGATIVE_QUANTITY'),('open','Infinity','INVALID_NUMBER'),('close','garbage','INVALID_NUMBER'),
    ('low','11','INVALID_OHLC'),('high','9','INVALID_OHLC')])
def test_l1_rejects_every_market_invalidity(case,field,value,reason):
    case.daily[0][field]=value
    _,fs,cs,_=case.run()
    assert any(f['rule_id']=='DV-L1' and f['reason_code']==reason for f in fs)
    assert cs


@pytest.mark.parametrize('stamp,reason',[('bad','INVALID_TIMESTAMP'),('1609459200000.5','INVALID_TIMESTAMP'),(T+1,'OFF_GRID_TIMESTAMP')])
def test_l1_timestamp_not_guessed(case,stamp,reason):
    case.daily[0]['timestamp']=stamp
    a,fs,cs,_=case.run()
    assert any(f['reason_code']==reason for f in fs)
    if reason=='INVALID_TIMESTAMP':assert a['status']=='BLOCKED' and fs[0]['timestamp'] is None


def test_duplicate_key_all_rows_missing_even_identical(case):
    case.daily*=2
    _,fs,cs,v=case.run()
    assert any(f['reason_code']=='DUPLICATE_KEY' for f in fs)
    assert all(c['row_action']=='missing' and c['decision']=='UNRESOLVED' for c in cs if c['interval']=='D')
    assert v['counts']['unresolved_rows']>=2


def test_unsorted_is_not_silently_reordered(case):
    case.hours[0],case.hours[1]=case.hours[1],case.hours[0]
    _,fs,_,_=case.run()
    assert any(f['reason_code']=='UNSORTED_KEYS' for f in fs)


@pytest.mark.parametrize('change,reason',[
    ('gap','GAPPED'),('no_daily','MISSING_COUNTERPART'),('no_hours','NO_VALID_HOURLY'),('invalid','INVALID_INPUT'),('scope','SCOPE_INCOMPLETE')])
def test_l2_union_and_incomplete_flags(case,change,reason):
    if change=='gap':del case.hours[10]
    elif change=='no_daily':case.daily=[]
    elif change=='no_hours':case.hours=[]
    elif change=='invalid':case.hours[2]['close']='0'
    else:case.readable['start']=T+HOUR
    _,fs,_,_=case.run()
    assert any(f['reason_code']==reason for f in fs)


def test_dva_turnover_only_does_not_require_trades(case):
    case.daily[0]['turnover']='-1';case.trades=None
    _,fs,cs,v=case.run()
    c=correction(cs,'turnover')
    assert (c['decision'],c['corrected_value'],c['evidence_kind'])==('CORRECT','240','reported_turnover_selection')
    assert c['coverage_status']==c['order_status']=='NOT_APPLICABLE'
    assert not any(f['rule_id']=='DV-L3' for f in fs)
    assert v['counts']['unresolved_rows']==0


def test_amount_difference_alone_is_diagnostic(case):
    case.daily[0]['turnover']='239';case.trades=None
    _,fs,cs,v=case.run()
    assert any(f['reason_code']=='TURNOVER_DIFFERENCE' for f in fs)
    assert cs==[] and v['counts']['flagged_days']==0


@pytest.mark.parametrize('mode,reason',[('missing','TURNOVER_INPUT_INCOMPLETE'),('duplicate','TURNOVER_INPUT_INCOMPLETE'),('nan','TURNOVER_INPUT_INCOMPLETE')])
def test_dva_rejects_incomplete_grid(case,mode,reason):
    case.daily[0]['turnover']='-1'
    if mode=='missing':del case.hours[5]
    elif mode=='duplicate':case.hours.append(dict(case.hours[0]))
    else:case.hours[0]['turnover']='NaN'
    _,_,cs,_=case.run()
    assert correction(cs,'turnover')['decision']=='UNRESOLVED'
    assert correction(cs,'turnover')['reason_code']==reason


def test_dva_works_despite_quantity_conflict_but_row_stays_missing(case):
    case.hours[0]['volume']='2'
    case.daily[0]['turnover']='239'
    _,_,cs,_=case.run()
    assert correction(cs,'turnover')['corrected_value']=='240'
    assert correction(cs,'turnover')['row_action']=='missing'
    assert correction(cs,'volume')['decision']=='UNRESOLVED'


def test_valid_open_keeps_exchange_semantics(case):
    case.daily[0].update(open='9',low='9',volume='23')
    case.hours[0].update(open='9',low='9')
    # L2 low mismatch flags the day; reconstruction high/low would exclude kept O.
    _,_,cs,_=case.run()
    assert correction(cs,'open')['original_value']=='9'
    assert correction(cs,'open')['decision']=='UNRESOLVED'
    assert correction(cs,'low')['reason_code']=='POST_L1_FAILED'


def test_open_semantics_keep_when_rebuilt_range_contains_it(case):
    case.daily[0].update(open='9',low='9',volume='23')
    case.hours[0].update(open='9',low='9')
    case.trades[1]['price']='9';case.hours[1].update(open='10',low='9',close='9')
    _,_,cs,_=case.run()
    c=correction(cs,'open')
    assert c['decision']=='KEEP' and c['corrected_value'] is None
    assert c['reason_code']=='EXCHANGE_OPEN_SEMANTICS' and c['original_value']=='9'


def test_invalid_open_requires_native_support_and_post_l1(case):
    case.daily[0].update(open='0',low='0')
    _,_,cs,_=case.run()
    assert correction(cs,'open')['corrected_value']=='10'
    assert correction(cs,'low')['corrected_value']=='10'
    assert all(c['row_action']=='include' for c in cs if c['interval']=='D')


@pytest.mark.parametrize('mode,reason',[
    ('duplicate_id','C1_ID_TIME'),('bad_price','C1_ID_TIME'),('bad_size','C1_ID_TIME'),('wrong_symbol','C1_ID_TIME'),('outside_day','C1_ID_TIME'),('clock','C1_ID_TIME'),
    ('empty_hour','C2_WINDOWS'),('quantity','C3_QUANTITY'),('multi','C4_ORDER'),('zero_box','C5_REBUILD')])
def test_each_coverage_gate_rejects(case,mode,reason):
    case.daily[0]['close']='9'
    if mode=='duplicate_id':case.trades[1]['trdMatchID']='0'
    elif mode=='bad_price':case.trades[0]['price']='0'
    elif mode=='bad_size':case.trades[0]['size']='0'
    elif mode=='wrong_symbol':case.trades[0]['symbol']='OTHERUSDT'
    elif mode=='outside_day':case.trades[0]['timestamp']=str((T-DAY)//1000)
    elif mode=='clock':case.trades[1],case.trades[2]=case.trades[2],case.trades[1]
    elif mode=='empty_hour':del case.trades[3]
    elif mode=='quantity':case.hours[3]['volume']='2'
    elif mode=='multi':
        case.trades.insert(1,dict(case.trades[0],price='11',trdMatchID='multi',size='0.5'));case.trades[0]['size']='0.5';case.hours[0]['high']='11'
    else:
        del case.trades[3];case.hours[3]['volume']='0';case.daily[0]['volume']='23'
    _,fs,cs,_=case.run()
    assert any(f['rule_id']==reason for f in fs)
    assert correction(cs,'open' if mode=='multi' else 'close')['decision']=='UNRESOLVED'


def test_first_stamp_multi_only_blocks_open_and_other_hour_independent(case):
    case.daily[0]['close']='9'
    case.trades.insert(1,dict(case.trades[0],price='11',trdMatchID='multi',size='0.5'));case.trades[0]['size']='0.5';case.hours[0]['high']='11'
    _,_,cs,_=case.run()
    assert correction(cs,'open')['order_status']=='TIMESTAMP_MULTI_PRICE'
    assert correction(cs,'close')['decision']=='CORRECT'
    assert correction(cs,'close')['corrected_value']=='10'
    assert correction(cs,'high')['decision']=='CORRECT'
    assert correction(cs,'close','60',T+HOUR)['decision']=='KEEP'


def test_exact_scientific_strings_and_submillisecond_boundary(case):
    case.trades[0].update(timestamp=str(T//1000)+'.000000000001',price='1e1',size='1e0')
    case.daily[0]['close']='9'
    _,_,cs,_=case.run()
    assert correction(cs,'close')['corrected_value']=='10'


def test_decimal_no_default_context_rounding(case):
    value='10.000000000000000000000000000001'
    case.daily[0].update(high=value,close='9')
    case.hours[-1].update(high=value,close=value)
    case.trades[-1]['price']=value
    _,_,cs,_=case.run()
    assert correction(cs,'close')['corrected_value']==value


def test_holdout_and_oos_refused_before_any_market_read(case):
    case.readable={'start':1751328000000,'end':1751414400000}
    a,_,_,_=case.run()
    assert a['status']=='BLOCKED' and 'READABLE_SCOPE_DENIED' in a['reason_codes']


def test_policy_parameters_cannot_be_overridden(case):
    case.policy_change=lambda p:p['turnover'].update(trigger_pct='6')
    a,_,_,_=case.run()
    assert a['status']=='BLOCKED' and 'POLICY_MISMATCH' in a['reason_codes']


# Report C §5, §6, interpreted per conductor clarification (2026-10-22):
# C4 is field-specific. Interior multi-price stamps do not invalidate a bar.
CROSSCHECK = [
 ('BCHUSDT','2020-12-14',3),('BCHUSDT','2021-02-18',1169),('BCHUSDT','2021-02-28',293),('BCHUSDT','2021-03-03',437),('BCHUSDT','2021-04-02',848),
 ('BTCUSDT','2020-03-25',18),('BTCUSDT','2021-02-12',7576),('BTCUSDT','2021-02-13',5476),('BTCUSDT','2021-02-14',5947),('BTCUSDT','2021-02-27',9364),
 ('BUZZUSDT','2025-04-19',2065),('DOTUSDT','2021-11-29',794),('ETHUSDT','2021-04-01',2318),('ETHUSDT','2021-04-07',3192),
 ('LINKUSDT','2020-10-21',61),('LINKUSDT','2021-03-03',1314),('LINKUSDT','2021-03-25',1507),('LTCUSDT','2020-10-21',10),('LTCUSDT','2021-02-18',2665),
 ('LTCUSDT','2021-03-17',939),('LTCUSDT','2021-04-08',901),('LTCUSDT','2021-04-10',1541),('PUMPBTCUSDT','2025-06-03',6229),('XEMUSDT','2021-11-30',218),('XTZUSDT','2020-10-21',3),('XTZUSDT','2021-03-24',1276)]


def test_dv3_real_plan_inventory_originals_into_dv1(tmp_path,monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket,'connect',lambda *a,**k: pytest.fail('network forbidden'))
    local=Path('/Users/ncyu/Projects/TradeBot/r8-research/crosscheck-20261022').exists()
    result=real_dv13_flow(tmp_path,3 if local else None)
    assert result['verification']['status']=='READY',result['verification']
    assert result['fetch']['status']=='READY',result['fetch']
    daily=[c for c in read(tmp_path/'bundle','corrections.jsonl') if c['interval']=='D']
    if local:
        assert {c['field']:c['decision'] for c in daily}==dict(zip(FIELDS,['KEEP','KEEP','KEEP','CORRECT','CORRECT','CORRECT']))
        assert next(c for c in daily if c['field']=='close')['corrected_value']=='521.2'
    else:
        assert len(daily)==6 and all(c['decision']=='KEEP' for c in daily)
    for r in read(tmp_path/'downloads','download_inventory.jsonl'):
        assert sha((tmp_path/'downloads'/r['relative_path']).read_bytes())==r['sha256']


def external(case, *, price='10.1', wrong_contract=False, partial=False):
    """Native Binance files and native exchangeInfo, not a fake verifier."""
    import zipfile
    data=','.join([str(T),'10','11','9',price,'2',str(T+HOUR-1),'20','2','1','10','0'])+'\n'
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as archive:archive.writestr('TESTUSDT-1h-2021-01-01.csv',data)
    raw=buf.getvalue();(case.dl/'external.zip').write_bytes(raw)
    inv=dict(schema_version='r8_verification_download_v1',request_id='external',symbol='TESTUSDT',day_start=T,interval='60',source_kind='binance_hour',url='https://data.binance.vision/data/futures/um/daily/klines/TESTUSDT/1h/TESTUSDT-1h-2021-01-01.zip',started_at=T,finished_at=T+1,http_status=200,api_status=None,byte_count=len(raw),relative_path='external.zip',sha256=sha(raw),status='AVAILABLE',reason_code=None)
    case.extra_inventory.append(inv)
    info=enc({'symbols':[dict(symbol='TESTUSDT',contractType='CURRENT_QUARTER' if wrong_contract else 'PERPETUAL',baseAsset='TEST',quoteAsset='USDT',marginAsset='USDT')]})
    (case.dl/'instrument.json').write_bytes(info)
    ref=dict.fromkeys(SOURCE_KEYS);ref.update(kind='instruments',relative_path='instrument.json',sha256=sha(info),url='https://fapi.binance.com/fapi/v1/exchangeInfo')
    if partial:case.first=T
    return [ref]


@pytest.mark.parametrize('price,hit',[('10.1',False),('10.100000000000000000000000000001',True),('9.9',False),('9.899999999999999999999999999999',True)])
def test_l4_strict_one_percent_no_tolerance(case,price,hit):
    refs=external(case,price=price)
    _,fs,_,_=case.run(external_contract_refs=refs)
    assert any(f['reason_code']=='PRICE_THRESHOLD_EXCEEDED' for f in fs)==hit
    assert any(f['reason_code']==('PRICE_THRESHOLD_EXCEEDED' if hit else 'WITHIN_THRESHOLD') for f in fs)


@pytest.mark.parametrize('mode,reason',[('wrong','INCOMPARABLE'),('missing','INCOMPARABLE'),('partial','INCOMPARABLE_PARTIAL'),('zero','UNDEFINED')])
def test_l4_rejects_incomparable_contract_partial_and_nonpositive(case,mode,reason):
    refs=external(case,wrong_contract=mode=='wrong',partial=mode=='partial')
    if mode=='zero':case.hours[0]['close']='0'
    _,fs,_,_=case.run(external_contract_refs=[] if mode=='missing' else refs)
    assert any(f['rule_id']=='DV-L4' and f['reason_code']==reason for f in fs)
    assert not any(f['reason_code']=='PRICE_THRESHOLD_EXCEEDED' for f in fs)


def test_l4_missing_source_remains_unavailable(case):
    _,fs,_,_=case.run()
    assert len([f for f in fs if f['rule_id']=='DV-L4' and f['reason_code']=='UNAVAILABLE'])==2


def test_l1_l2_gap_is_terminal_missing_not_manufactured_zero_trade(case):
    del case.hours[10];del case.trades[10]
    # Day quantity differs from available hours: L3 must also fail the missing box.
    _,fs,cs,_=case.run()
    assert correction(cs,'volume')['decision']=='UNRESOLVED'
    assert any(f['rule_id']=='C2_WINDOWS' for f in fs)


def test_coverage_known_delisting_window_cannot_accept_later_trades(case):
    case.delivery=T+12*HOUR
    case.daily[0]['volume']='23'
    _,fs,cs,_=case.run()
    assert any(f['rule_id']=='C2_WINDOWS' for f in fs)
    assert correction(cs,'volume')['decision']=='UNRESOLVED'


def test_dva_observed_partial_listing_sums_only_complete_existing_boxes(case):
    case.hours=case.hours[6:];case.trades=case.trades[6:];case.first=T+6*HOUR
    case.daily[0].update(volume='18',turnover='179')
    # A bad turnover is sufficient to select reported amount, without G.
    case.daily[0]['turnover']='-1';case.trades=None
    _,fs,cs,_=case.run()
    assert correction(cs,'turnover')['corrected_value']=='180'
    assert any({'name':'grid','value':'PARTIAL'} in f['details'] for f in fs if f['rule_id']=='DV-A')


def test_scoped_csv_and_raw_poison_are_never_market_decoded(case):
    case.hours.insert(0,bar(T-HOUR,close='SECRET_BEFORE'))
    case.hours.append(bar(T+DAY,close='SECRET_AFTER'))
    a,fs,cs,_=case.run()
    assert a['status']=='READY'
    assert b'SECRET' not in b''.join((Path(a['artifact_root'])/n).read_bytes() for n in a['files'])
    assert not any(f['reason_code']=='INVALID_NUMBER' for f in fs)


def test_unavailable_trade_and_scope_crossing_have_terminal_findings(case):
    case.daily[0]['volume']='23';case.trades=None
    _,fs,cs,_=case.run()
    assert correction(cs,'volume')['decision']=='UNRESOLVED'
    assert any(f['reason_code']=='TRADE_UNAVAILABLE' for f in fs)
    case.readable['end']=T+12*HOUR
    _,fs,cs,_=case.run()
    assert any(f['reason_code']=='SCOPE_INCOMPLETE' for f in fs)


def test_minute_bad_support_cannot_vote_open_into_validity(case):
    case.daily[0].update(open='0',low='0');case.hours[0]['open']='9'
    # Earliest hourly open is not T.O and later equal opens cannot vote it in.
    case.hours[0]['low']='9'
    _,_,cs,_=case.run()
    assert correction(cs,'open')['decision']=='UNRESOLVED'
    assert correction(cs,'open')['reason_code']=='NATIVE_OPEN_SUPPORT_MISSING'


def test_corrections_have_exact_keys_provenance_and_no_keep_rewrite(case):
    case.daily[0].update(open='0',low='0',turnover='240.00')
    a,fs,cs,v=case.run()
    assert cs and all(set(c)==CORRECTION_KEYS for c in cs)
    assert all(set(f)==FINDING_KEYS for f in fs)
    for c in cs:
        assert all(set(r)==SOURCE_KEYS for r in c['source_refs'])
        assert c['rule_ids']==sorted(set(c['rule_ids']))
        if c['decision']!='CORRECT':assert c['corrected_value'] is None
    assert correction(cs,'turnover')['original_value']=='240.00'
    assert correction(cs,'turnover')['decision']=='KEEP'
    assert correction(cs,'open')['corrected_value']=='10'


@pytest.mark.parametrize('mode,reason',[('unknown','SCHEMA_FIELDS'),('version','SCHEMA_VERSION'),('duplicate','DUPLICATE_JSON_KEY'),('sha','SOURCE_HASH_MISMATCH'),('path','UNSAFE_PATH'),('symlink','SYMLINK_DENIED')])
def test_inventory_schema_hash_and_path_refusals(case,mode,reason):
    case.daily[0]['volume']='23';case.write()
    p=case.dl/'download_inventory.jsonl';r=json.loads(p.read_bytes())
    if mode=='unknown':r['extra']=True
    elif mode=='version':r['schema_version']='v999'
    elif mode=='sha':r['sha256']='0'*64
    elif mode=='path':r['relative_path']='../escape'
    elif mode=='symlink':
        (case.dl/'link.gz').symlink_to(case.dl/'trades.csv.gz');r['relative_path']='link.gz'
    raw=enc(r)
    if mode=='duplicate':raw=raw.replace(b'"interval":"trade"',b'"interval":"trade","interval":"trade"')
    p.write_bytes(raw)
    a=verify(p3b_root=case.p3b,download_root=case.dl,inventory_path=p,output_root=case.root/'result',policy_path=case.root/'policy.json',readable=case.readable,symbols=['TESTUSDT'])
    assert a['status']=='BLOCKED' and reason in a['reason_codes']


# 31 original disputed fields from C §5. Ambiguous boundaries have no candidate.
DISPUTED = [
 {'open':'272.95','low':'265.15'},{'close':'704.45'},{'close':'460.85'},{'close':'521.2'},{'close':'581.8'},
 {'low':'6457.5'},{'close':None},{'close':'47191.5'},{'close':'48689.5'},{'close':'46137'},
 {'close':'0.006479'},{'high':'37.535'},{'close':'1968.2'},{'close':'1965'},
 {'open':'10.425','low':'10.342'},{'close':None},{'close':'25.558'},
 {'open':'48.83','low':'48.76'},{'close':None},{'close':'206.02'},{'close':'226.44'},{'close':'256.71'},
 {'open':None},{'open':'0.172','high':'0.177'},{'open':'2.131','low':'2.1'},{'close':'3.99'}]


@pytest.mark.parametrize('index',range(26),ids=[s+'-'+d for s,d,_ in CROSSCHECK])
def test_frozen_26_day_originals_and_31_disputes(tmp_path,index,record_property):
    from datetime import datetime, timezone
    base=Path('/Users/ncyu/Projects/TradeBot')
    p3b=base/'r8-research/data/p3b-20261020';dl=base/'r8-research/crosscheck-20261022';audit=base/'audits/2026-10-22-r8-crosscheck'
    if not p3b.exists() or not dl.exists() or not audit.exists():pytest.skip('26-day original files unavailable on this host')
    symbol,date,multi=CROSSCHECK[index];t=int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())*1000
    manifest_sha=sha((p3b/'manifest.json').read_bytes())
    assert manifest_sha=='b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006'
    p=policy(manifest_sha);(tmp_path/'policy.json').write_bytes(enc(p));records=[]
    for line in (dl/'requests.jsonl').read_bytes().splitlines():
        r=json.loads(line);m=r['metadata']
        if m.get('symbol')!=symbol or m.get('date_utc')!=date:continue
        kind={'bybit_trade_file':'bybit_trade','bybit_1m':'bybit_minute'}.get(r['kind'])
        if kind is None:continue
        records.append(dict(schema_version='r8_verification_download_v1',request_id=str(r['request_id']),symbol=symbol,day_start=t,interval='trade' if kind=='bybit_trade' else '1',source_kind=kind,url=r['url'],started_at=t,finished_at=t+1,http_status=r['http_status'],api_status=None if kind=='bybit_trade' else 0,byte_count=r['saved_bytes'],relative_path=r['path'],sha256=r['sha256'],status='AVAILABLE',reason_code=None))
    records.sort(key=lambda r:(r['symbol'],r['day_start'],r['source_kind'],r['interval'],r['request_id']))
    (tmp_path/'inventory.jsonl').write_bytes(b''.join(enc(r) for r in records))
    out=tmp_path/'bundle'
    a=verify(p3b_root=p3b,download_root=dl,inventory_path=tmp_path/'inventory.jsonl',output_root=out,policy_path=tmp_path/'policy.json',readable={'start':t,'end':t+DAY},symbols=[symbol])
    assert a['status']=='READY',a
    fs,cs=read(out,'findings.jsonl'),read(out,'corrections.jsonl')
    daily=[c for c in cs if c['interval']=='D']
    expected=DAILY_DECISIONS[index]
    assert {c['field']:c['decision'] for c in daily if c['field']!='turnover'}==dict(zip(FIELDS[:5],expected))
    assert {c['row_action'] for c in daily}==({'missing'} if 'UNRESOLVED' in expected else {'include'})
    for f,ambiguous in zip(('open','close'),BOUNDARY_MULTI[index]):
        assert (correction(cs,f,timestamp=t)['order_status']=='TIMESTAMP_MULTI_PRICE')==ambiguous
    if index==0:
        assert correction(cs,'open',timestamp=t)['corrected_value']=='272.95'
        assert correction(cs,'low',timestamp=t)['corrected_value']=='265.15'
        assert correction(cs,'close',timestamp=t)['decision']=='KEEP'
        assert correction(cs,'turnover',timestamp=t)['corrected_value']=='2954180.78'
    assert any(f['interval']=='D' and f['rule_id']=='C4_ORDER' and {'name':'multi_timestamp_count','value':str(multi)} in f['details'] for f in fs)
    for f,expected in DISPUTED[index].items():
        c=correction(cs,f,timestamp=t)
        assert c['candidate_value']==expected
    if symbol in ('XEMUSDT','PUMPBTCUSDT'):
        assert any(f['rule_id']=='C2_WINDOWS' and f['reason_code']=='COVERAGE_CONFLICT' for f in fs)
    # Original D values remain faithful to the independent archived scoped input.
    original=json.loads((audit/'p3b-scoped-inputs.json').read_bytes())['scoped_csv_rows'][symbol+'|D']
    row=next(r for r in original if r['timestamp']==t)
    for c in daily:assert c['original_value']==row[c['field']]
    assert all(any(r['kind']=='raw' and r['byte_start'] is not None for r in c['source_refs']) for c in daily)
    assert any(f['rule_id']=='C5_REBUILD' and f['reason_code']=='SOURCE_COMPARISON' for f in fs)
    record_property('crosscheck',json.dumps(dict(symbol=symbol,date=date,earliest_multi=BOUNDARY_MULTI[index][0],latest_multi=BOUNDARY_MULTI[index][1],decisions={c['field']:{k:c[k] for k in ('decision','corrected_value','candidate_value','reason_code','row_action','coverage_status','order_status')} for c in daily},verification_sha256=a['primary_sha256'],bundle=str(out)),sort_keys=True))


def test_frozen_sample_without_trade_still_has_terminal_result(case):
    case.trades=None;case.write()
    p=json.loads((case.root/'policy.json').read_bytes())
    plan=dict(schema_version='r8_verification_sample_plan_v1',policy_sha256=sha(enc(p)),p3b_manifest_sha256=p['p3b_manifest_sha256'],readable=case.readable,seed=20261022,strata=[dict(year=2021,tier='NO_OPEN',population_size=1,base_size=1,max_size=1,draws=[dict(rank=1,symbol='TESTUSDT',day_start=T)])])
    path=case.root/'sample_plan.json';path.write_bytes(enc(plan))
    a,fs,cs,v=case.run(sample_plan_path=path)
    assert a['status']=='READY' and v['counts']['flagged_days']==1
    assert correction(cs,'open')['decision']=='UNRESOLVED'
    refs=[r for c in cs for r in c['source_refs'] if r['kind']=='trade']
    assert refs and refs[0]['url']=='https://public.bybit.com/trading/TESTUSDT/TESTUSDT2021-01-01.csv.gz'
    assert refs[0]['relative_path'] is None and refs[0]['sha256'] is None


def test_trade_corrections_pin_coverage_report_digest(case):
    case.daily[0]['volume']='23'
    a,_,cs,_=case.run()
    c=correction(cs,'volume')
    assert any(r['kind']=='report' and r['relative_path']=='findings.jsonl' and r['sha256']==a['files']['findings.jsonl']['sha256'] for r in c['source_refs'])


def test_prior_correction_outside_scope_not_market_decoded(case):
    # Invalid UTF8 value must never be decoded: scope is checked first.
    p=case.root/'prior.jsonl'
    p.write_bytes(b'{"timestamp":1751328000000,"symbol":"TESTUSDT","original_value":"\xff"}\n')
    a,_,_,_=case.run(previous_corrections_path=p)
    assert a['status']=='BLOCKED' and 'PREVIOUS_SCOPE' in a['reason_codes']


def test_previous_bundle_chain_and_immutable_original_identity(case):
    case.daily[0]['volume']='23'
    a,_,old,_=case.run();prev=Path(a['artifact_root'])/'corrections.jsonl'
    b,_,new,v=case.run(previous_corrections_path=prev)
    assert b['status']=='READY'
    assert v['previous_corrections_sha256']==sha(prev.read_bytes())
    assert {c['supersedes'] for c in new}=={c['correction_id'] for c in old}
    case.daily[0]['volume']='22'
    c,*_=case.run(previous_corrections_path=prev)
    assert c['status']=='BLOCKED' and 'PREVIOUS_POLICY_MISMATCH' in c['reason_codes']


@pytest.mark.parametrize('mode,reason',[('cycle','SUPERSEDES_CYCLE'),('duplicate','CORRECTION_CONFLICT'),('evidence','MISSING_EVIDENCE'),('unknown','SCHEMA_FIELDS')])
def test_previous_correction_rejects_invalid_lineage(case,mode,reason):
    case.daily[0]['volume']='23';a,_,cs,_=case.run()
    if mode=='cycle':cs[0]['supersedes']=cs[0]['correction_id']
    elif mode=='duplicate':cs.append(dict(cs[0]))
    elif mode=='evidence':cs[0]['source_refs']=[]
    else:cs[0]['surprise']=True
    p=case.root/'bad-prior.jsonl';p.write_bytes(b''.join(enc(c) for c in cs))
    r,*_=case.run(previous_corrections_path=p)
    assert r['status']=='BLOCKED' and reason in r['reason_codes']


# Frozen BEFORE the clarified implementation, from C boundary evidence and C3
# hourly quantity conflicts. O,H,L,C,V order; A remains an independent decision.
BOUNDARY_MULTI = [(False,False),(True,False),(False,False),(False,False),(False,False),
 (False,False),(False,True),(False,False),(False,False),(True,False),
 (True,False),(False,False),(False,False),(False,False),(False,False),
 (False,True),(True,False),(False,False),(True,True),(True,False),
 (False,False),(False,False),(True,False),(False,False),(False,False),(False,False)]
U='UNRESOLVED';K='KEEP';C='CORRECT'
DAILY_DECISIONS = [
 (C,K,C,K,K),(U,U,U,U,U),(U,U,U,U,U),(K,K,K,C,C),(U,U,U,U,U),
 (K,K,C,K,K),(U,U,U,U,U),(U,U,U,U,U),(U,U,U,U,U),(U,U,U,U,U),
 (U,K,K,C,C),(U,U,U,U,U),(U,U,U,U,U),(U,U,U,U,U),(K,K,C,K,K),
 (U,U,U,U,U),(U,K,K,C,C),(K,K,C,K,K),(U,K,K,U,C),(U,U,U,U,U),
 (K,K,K,C,C),(U,U,U,U,U),(U,U,U,U,U),(U,U,U,U,U),(K,K,C,K,K),(U,U,U,U,U)]


@pytest.mark.parametrize('position,unresolved',[('first',{'open'}),('middle',set()),('last',{'close'})])
def test_conductor_c4_only_boundary_dependent_fields(case,position,unresolved):
    idx={'first':0,'middle':12,'last':23}[position]
    case.daily[0].update(volume='23',low='9')
    case.trades[idx]['size']='0.5'
    case.trades.insert(idx+1,dict(case.trades[idx],price='11',size='0.5',trdMatchID='additional'))
    case.hours[idx]['high']='11'
    _,fs,cs,_=case.run()
    daily=[c for c in cs if c['interval']=='D']
    assert {c['field'] for c in daily if c['decision']=='UNRESOLVED'}==unresolved
    assert correction(cs,'high')['corrected_value']=='11'
    assert correction(cs,'low')['corrected_value']=='10'
    assert correction(cs,'volume')['corrected_value']=='24'
    assert any(f['rule_id']=='C4_ORDER' and {'name':'prices','value':'10,11'} in f['details'] for f in fs)


def test_hourly_turnover_only_invalid_never_triggers_trade_gate(case):
    case.hours[0]['turnover']='NaN';case.trades=None
    _,fs,cs,_=case.run()
    assert not any(f['rule_id']=='DV-L3' for f in fs)
    assert all(c['decision']=='KEEP' for c in cs if c['field']!='turnover')
    assert correction(cs,'turnover')['decision']=='UNRESOLVED'


def test_partial_post_l2_keeps_original_open_semantic_difference(case):
    case.hours=case.hours[6:];case.trades=case.trades[6:];case.first=T+6*HOUR
    case.daily[0].update(open='11',high='11',volume='17',turnover='180')
    case.hours[10].update(open='11',high='11',low='11',close='11');case.trades[10]['price']='11'
    _,fs,cs,_=case.run()
    assert correction(cs,'open')['decision']=='KEEP'
    assert any(f['reason_code']=='POST_L2_SEMANTICS' and f['field']=='open' for f in fs)


@pytest.mark.parametrize('mode,reason',[('rank','SAMPLE_SCOPE'),('unknown','SCHEMA_FIELDS'),('policy','SAMPLE_IDENTITY'),('outside','SAMPLE_SCOPE')])
def test_sample_plan_cannot_change_scope_identity_or_draw_rank(case,mode,reason):
    case.trades=None;case.write();p=json.loads((case.root/'policy.json').read_bytes())
    plan=dict(schema_version='r8_verification_sample_plan_v1',policy_sha256=sha(enc(p)),p3b_manifest_sha256=p['p3b_manifest_sha256'],readable=case.readable,seed=20261022,strata=[dict(year=2021,tier='NO_OPEN',population_size=1,base_size=1,max_size=1,draws=[dict(rank=1,symbol='TESTUSDT',day_start=T)])])
    if mode=='rank':plan['strata'][0]['draws'][0]['rank']=2
    elif mode=='unknown':plan['extra']=1
    elif mode=='policy':plan['policy_sha256']='0'*64
    else:plan['strata'][0]['draws'][0]['day_start']=T+DAY
    path=case.root/'plan.json';path.write_bytes(enc(plan))
    a,*_=case.run(sample_plan_path=path)
    assert a['status']=='BLOCKED' and reason in a['reason_codes']


def test_duplicate_source_rows_produce_one_unresolved_correction_per_key(case):
    case.daily.append(dict(case.daily[0],open='9',low='9'))
    _,_,cs,v=case.run()
    keys=[(c['symbol'],c['dataset'],c['interval'],c['timestamp'],c['field']) for c in cs]
    assert len(keys)==len(set(keys))
    c=correction(cs,'open')
    assert c['decision']=='UNRESOLVED' and c['original_value'] is None
    assert len([r for r in c['source_refs'] if r['kind']=='csv'])>=2
    assert v['counts']['unresolved_rows']>=2


@pytest.mark.parametrize('field,value',[('coverage_status','PASSISH'),('order_status',True),('candidate_value',10),('policy_sha256','0'*64),('correction_id','0'*64),('supersedes',42)])
def test_previous_correction_rejects_wrong_types_enums_or_identity(case,field,value):
    case.daily[0]['volume']='23';_,_,cs,_=case.run()
    cs[0][field]=value
    p=case.root/'prior-invalid.jsonl';p.write_bytes(b''.join(enc(c) for c in cs))
    a,*_=case.run(previous_corrections_path=p)
    assert a['status']=='BLOCKED'


def test_tool_commit_identity_cannot_be_spoofed(case):
    a,*_=case.run(tool_commit='0'*40)
    assert a['status']=='BLOCKED' and 'TOOL_COMMIT_MISMATCH' in a['reason_codes']


class OfflineArchiveTransport:
    """Only the HTTP boundary is replaced; response bytes are never normalized."""
    def __init__(self,payloads,unavailable=False):
        self.payloads=payloads;self.calls=[];self.t=0;self.unavailable=unavailable
    def clock(self):return self.t
    def sleep(self,delay):self.t+=delay
    def __call__(self,method,url):
        from program_code.research.r8_data import verification_fetch as fetch
        assert method in ('HEAD','GET') and url in self.payloads
        self.calls.append((method,url));data=self.payloads[url]
        return fetch.Response(404 if self.unavailable else 200,{'Content-Length':str(len(data))},io.BytesIO(data if method=='GET' else b''))


def real_dv13_flow(root,index=None,fetch_failure=None,configure=None,frozen_standard=None):
    """Real plan -> local byte transport -> real verifier -> real statistics.

    Local archives use a one-symbol fixture manifest to bound the population;
    its original CSV/raw bytes and metadata are copied without alteration. The
    original full P3b manifest is immutable and its SHA is retained in provenance.
    CI runs the same APIs on the portable fixed-value fixture when archives are
    unavailable; the two named integration tests never skip or mock a peer API.
    """
    from datetime import datetime,timezone
    import shutil
    from program_code.research.r8_data import verification_fetch as fetch
    root=Path(root);root.mkdir(exist_ok=True,parents=True);p3b=root/'p3b';payloads={};requests=[]
    if index is None:
        case=Case(root)
        if configure is not None:configure(case)
        case.write();symbol='TESTUSDT';t=T
        # Case's source directory is immutable after this fixture preparation.
        m=json.loads((p3b/'manifest.json').read_bytes())
        m['universe'][symbol]['launch_time']=case.first
        (p3b/'manifest.json').write_bytes(enc(m))
        for r in read(case.dl,'download_inventory.jsonl'):
            payloads[r['url']]=(case.dl/r['relative_path']).read_bytes()
            requests.append(fetch.DownloadRequest(r['request_id'],symbol,r['day_start'],r['interval'],r['source_kind'],r['url']))
        # Fetch outputs have their own immutable root.
        shutil.move(str(case.dl),str(root/'fixture-download-source'))
        full_sha=None;mode='portable_fixed_values'
    else:
        base=Path('/Users/ncyu/Projects/TradeBot');original=base/'r8-research/data/p3b-20261020'
        archive=base/'r8-research/crosscheck-20261022'
        symbol,date,_=CROSSCHECK[index];t=int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())*1000
        full=(original/'manifest.json').read_bytes();full_sha=sha(full)
        assert full_sha=='b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006'
        m=json.loads(full);m['files']={n:x for n,x in m['files'].items() if x.get('symbol')==symbol and x.get('dataset')=='kline' and x.get('interval') in ('D','60')}
        m['universe']={symbol:m['universe'][symbol]};p3b.mkdir()
        ids=set(m['universe_request_ids'])
        for name,meta in m['files'].items():
            shutil.copyfile(original/name,p3b/name);assert sha((p3b/name).read_bytes())==meta['sha256']
            ids.update(meta['source_request_ids'])
        log=[]
        for line in (original/'requests.jsonl').read_bytes().splitlines(keepends=True):
            r=json.loads(line)
            if r['request_id'] in ids:
                log.append(line);name=f"raw/{r['request_id']}.json"
                (p3b/'raw').mkdir(exist_ok=True);shutil.copyfile(original/name,p3b/name)
        data=b''.join(log);(p3b/'requests.jsonl').write_bytes(data);m['request_log_sha256']=sha(data)
        (p3b/'manifest.json').write_bytes(enc(m))
        for line in (archive/'requests.jsonl').read_bytes().splitlines():
            r=json.loads(line)
            if r['metadata'].get('symbol')!=symbol or r['metadata'].get('date_utc')!=date:continue
            kind={'bybit_trade_file':'bybit_trade','bybit_1m':'bybit_minute'}.get(r['kind'])
            if kind is None:continue
            data=(archive/r['path']).read_bytes();assert sha(data)==r['sha256']
            payloads[r['url']]=data
            requests.append(fetch.DownloadRequest(str(r['request_id']),symbol,t,'trade' if kind=='bybit_trade' else '1',kind,r['url']))
        mode='local_original_bytes'
    scope=case.readable if index is None else {'start':t,'end':t+DAY}
    manifest_sha=sha((p3b/'manifest.json').read_bytes())
    sources=[fetch.CSVSource(x['symbol'],x['dataset'],x['interval'],n,x['sha256']) for n,x in m['files'].items()]
    plan=fetch.build_sample_plan(p3b,root/'plan',sources,readable=scope,p3b_manifest_sha256=manifest_sha)
    assert plan['primary_file']=='sample_plan.json',plan
    if frozen_standard is not None:
        # Prepare a historical-policy fixture before any verifier consumes it.
        # This never mutates an archived plan or any original market bytes.
        p=read(root/'plan','policy.json');p['standard_sha256']=frozen_standard
        sample=read(root/'plan','sample_plan.json');sample['policy_sha256']=sha(enc(p))
        (root/'plan/policy.json').write_bytes(enc(p))
        (root/'plan/sample_plan.json').write_bytes(enc(sample))
        (root/'plan/sample_plan.sha256').write_text(sha(enc(sample))+'\n')
        plan['primary_sha256']=sha(enc(sample))
        for name,meta in plan['files'].items():meta['sha256']=sha((root/'plan'/name).read_bytes())
    transport=OfflineArchiveTransport(payloads,fetch_failure=='UNAVAILABLE')
    downloaded=fetch.fetch_downloads(root/'downloads',requests,approved_urls=list(payloads),readable={'start':t+HOUR,'end':t+DAY} if fetch_failure=='SCOPE_INCOMPLETE' else scope,
        max_total_bytes=0 if fetch_failure=='SIZE_BLOCKED' else sum(map(len,payloads.values())),max_file_bytes=max(map(len,payloads.values())),
        flagged_days=[(symbol,t)],transport=transport,clock=transport.clock,sleep=transport.sleep,now=lambda:t)
    assert downloaded['status']==('BLOCKED' if fetch_failure else 'READY'),downloaded
    output=verify(p3b_root=p3b,download_root=root/'downloads',inventory_path=root/'downloads'/'download_inventory.jsonl',
        output_root=root/'bundle',policy_path=root/'plan'/'policy.json',readable=scope,symbols=[symbol],sample_plan_path=root/'plan'/'sample_plan.json')
    assert output['status']=='READY',output
    bundle=root/'bundle'
    # Package original namespaces without rewriting a reference or market byte.
    for name in ('manifest.json','requests.jsonl'):shutil.copyfile(p3b/name,bundle/name)
    shutil.copyfile(root/'downloads/download_inventory.jsonl',bundle/'download_inventory.jsonl')
    refs=[r for name in ('corrections.jsonl','findings.jsonl') for row in read(bundle,name) for r in row['source_refs']]
    for ref in refs:
        name=ref['relative_path']
        if name is None:continue
        target=bundle/name
        if target.exists():assert sha(target.read_bytes())==ref['sha256'];continue
        candidates=[x/name for x in (p3b,root/'downloads') if (x/name).is_file() and sha((x/name).read_bytes())==ref['sha256']]
        assert candidates,ref
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(candidates[0],target)
    summary=fetch.summarize_sample(root/'plan',[bundle],root/'summary')
    provenance={'mode':mode,'symbol':symbol,'day_start':t,'original_p3b_manifest_sha256':full_sha,
        'fixture_manifest_sha256':manifest_sha,'transport_calls':transport.calls,'network_requests':0,
        'plan':plan,'fetch':downloaded,'verification':output,'summary':summary}
    (root/'integration.json').write_bytes(enc(provenance))
    return provenance


def real_partial_and_sampled_flow(root,readable_offset=0):
    """A partial first day without trades and a fully evidenced sampled next day."""
    def configure(case):
        first_hour=1 if readable_offset else 6
        case.first=T-HOUR if readable_offset else T+first_hour*HOUR
        case.readable={'start':T+readable_offset,'end':T+2*DAY}
        case.daily=[bar(T,volume=str(24-first_hour),turnover=str(10*(24-first_hour))),
                    bar(T+DAY,volume='24',turnover='240')]
        case.hours=[bar(T+i*HOUR) for i in range(first_hour,48)]
        case.trades=None
        lines=['timestamp,symbol,side,size,price,trdMatchID']
        lines += [f'{(T+DAY+h*HOUR)//1000}.0000001,TESTUSDT,Buy,1,10,{h}' for h in range(24)]
        data=gzip.compress(('\n'.join(lines)+'\n').encode(),mtime=0)
        (case.dl/'sampled.csv.gz').write_bytes(data)
        case.extra_inventory=[dict(schema_version='r8_verification_download_v1',request_id='sampled',symbol='TESTUSDT',
            day_start=T+DAY,interval='trade',source_kind='bybit_trade',url='https://public.bybit.com/trading/TESTUSDT/TESTUSDT2021-01-02.csv.gz',
            started_at=T+DAY,finished_at=T+DAY+1,http_status=200,api_status=None,byte_count=len(data),
            relative_path='sampled.csv.gz',sha256=sha(data),status='AVAILABLE',reason_code=None)]
    return real_dv13_flow(root,configure=configure)


def test_partial_readable_day_keeps_diagnostics_and_complete_sample_statistics(tmp_path,monkeypatch):
    import socket
    from program_code.research.r8_data import verification_fetch as fetch
    def deny(*args,**kwargs):raise AssertionError('network forbidden')
    monkeypatch.setattr(socket.socket,'connect',deny)
    monkeypatch.setattr(socket,'create_connection',deny)
    root=tmp_path/'partial';flow=real_partial_and_sampled_flow(root,HOUR)
    assert flow['verification']['status']=='READY'
    assert flow['summary']['status']=='READY',flow['summary']
    findings=read(root/'bundle','findings.jsonl')
    diagnostics=[f for f in findings if f['rule_id']=='DV-L2' and T<=f['timestamp']<T+DAY]
    assert {'SCOPE_INCOMPLETE','GAPPED','MISSING_COUNTERPART','POST_L2_MISSING_INPUTS'}<={f['reason_code'] for f in diagnostics}
    assert all(f['timestamp']==T+HOUR for f in diagnostics)
    assert all({d['name']:d['value'] for d in f['details']}.items()>={
        'day_start':str(T),'scope_start':str(T+HOUR),'scope_end':str(T+DAY)}.items() for f in diagnostics)
    assert all(f['timestamp'] is None or T+HOUR<=f['timestamp']<T+2*DAY for f in findings)
    p=read(root/'plan','sample_plan.json')
    assert [d['day_start'] for s in p['strata'] for d in s['draws']]==[T+DAY]
    outcomes,_=fetch._bundle_outcomes(root/'bundle',p,sha((root/'plan/sample_plan.json').read_bytes()))
    assert outcomes=={('TESTUSDT',T):'u',('TESTUSDT',T+DAY):'s'}
    assert 'N=1 n=1 e=0 u=0 s=1' in (root/'summary/sample_report.txt').read_text()


def test_l2_missing_hour_routes_turnover_without_price_adjudication(case):
    case.hours.pop(12)
    case.daily[0].update(volume='23',turnover='230')
    case.trades=None
    result,findings,cs,_=case.run()
    assert result['status']=='READY'
    assert any(f['reason_code']=='GAPPED' for f in findings)
    amount=next((c for c in cs if c['interval']=='D' and c['field']=='turnover'),None)
    assert amount is not None, 'L2 coverage finding left original daily turnover available'
    assert (amount['decision'],amount['reason_code'],amount['row_action'])==('UNRESOLVED','TURNOVER_INPUT_INCOMPLETE','missing')
    assert not any(f['rule_id'] in ('DV-L3','C3_QUANTITY','C5_REBUILD') for f in findings)
    assert not any(r['kind']=='trade' for c in cs for r in c['source_refs'])


def test_daily_selection_inspects_each_bar_and_inventory_only_linearly(case,monkeypatch,record_property):
    from program_code.research.r8_data import verification as dv1
    days=120
    case.readable={'start':T,'end':T+days*DAY}
    case.daily=[bar(T+d*DAY,volume='24',turnover='240') for d in range(days)]
    case.hours=[bar(T+i*HOUR) for i in range(days*24)]
    case.trades=None
    case.extra_inventory=[dict(schema_version='r8_verification_download_v1',request_id=str(d),symbol='TESTUSDT',
        day_start=T+d*DAY,interval='60',source_kind='binance_hour',url='https://data.binance.vision/unavailable',
        started_at=T,finished_at=T,http_status=404,api_status=None,byte_count=0,relative_path=None,sha256=None,
        status='UNAVAILABLE',reason_code='HTTP_UNAVAILABLE') for d in range(days)]
    class Counted(list):
        visits=0
        def __iter__(self):
            for item in super().__iter__():
                self.visits+=1
                yield item
    observed={};load_bars=dv1._load_p3b;load_inventory=dv1._load_inventory
    def counted_bars(*args):
        bars,meta,instruments=load_bars(*args)
        observed['bars']=Counted(bars)
        return observed['bars'],meta,instruments
    def counted_inventory(*args):
        observed['inventory']=Counted(load_inventory(*args))
        return observed['inventory']
    monkeypatch.setattr(dv1,'_load_p3b',counted_bars)
    monkeypatch.setattr(dv1,'_load_inventory',counted_inventory)
    result,_,cs,info=case.run()
    assert result['status']=='READY' and info['counts']['checked_days']==days and not cs
    assert observed['bars'].visits<=len(observed['bars'])*8
    assert observed['inventory'].visits<=len(observed['inventory'])*4
    record_property('bar_count',len(observed['bars']))
    record_property('bar_visits',observed['bars'].visits)
    record_property('inventory_count',len(observed['inventory']))
    record_property('inventory_visits',observed['inventory'].visits)


def real_expansion_flow(root):
    """302 fixed days, one precommitted base error; both passes use real peers."""
    from datetime import datetime,timezone
    import shutil
    from program_code.research.r8_data import verification_fetch as fetch
    root.mkdir();case=Case(root);days=302
    case.readable={'start':T,'end':T+days*DAY}
    case.daily=[bar(T+d*DAY,volume='24',turnover='240') for d in range(days)]
    case.hours=[bar(T+i*HOUR) for i in range(days*24)]
    # Frozen independently of the sampled order; the raw and CSV both retain it.
    case.daily[0].update(high='11',close='11')
    case.trades=None;case.write()
    manifest=json.loads((case.p3b/'manifest.json').read_bytes())
    manifest['universe']['TESTUSDT']['launch_time']=case.first
    (case.p3b/'manifest.json').write_bytes(enc(manifest))
    inputs=[fetch.CSVSource(x['symbol'],x['dataset'],x['interval'],name,x['sha256']) for name,x in manifest['files'].items()]
    planned=fetch.build_sample_plan(case.p3b,root/'plan',inputs,readable=case.readable,p3b_manifest_sha256=sha(enc(manifest)))
    assert planned['status']=='READY'
    frozen=(root/'plan/sample_plan.json').read_bytes();p=json.loads(frozen);s=p['strata'][0]
    assert len(p['strata'])==1 and (s['population_size'],s['base_size'],s['max_size'])==(302,300,302)
    assert T in {d['day_start'] for d in s['draws'][:300]}
    payloads={};requests=[]
    for d in s['draws']:
        day=d['day_start'];date=datetime.fromtimestamp(day//1000,timezone.utc).strftime('%Y-%m-%d')
        url=f'https://public.bybit.com/trading/TESTUSDT/TESTUSDT{date}.csv.gz'
        lines=['timestamp,symbol,side,size,price,trdMatchID']
        lines += [f'{(day+h*HOUR)//1000}.0000001,TESTUSDT,Buy,1,10,{h}' for h in range(24)]
        payloads[url]=gzip.compress(('\n'.join(lines)+'\n').encode(),mtime=0)
        requests.append(fetch.DownloadRequest(str(day),'TESTUSDT',day,'trade','bybit_trade',url))
    bundles=[];summaries=[]
    for stage,count in [('base',300),('expanded',302)]:
        transport=OfflineArchiveTransport(payloads);download=root/(stage+'-downloads')
        got=fetch.fetch_downloads(download,requests[:count],approved_urls=list(payloads),readable=case.readable,
            max_total_bytes=sum(map(len,payloads.values())),max_file_bytes=max(map(len,payloads.values())),
            transport=transport,clock=transport.clock,sleep=transport.sleep,now=lambda:T)
        assert got['status']=='READY',got
        bundle=root/(stage+'-bundle');kw={}
        if stage=='expanded':kw['sample_report_path']=root/'base-summary/sample_report.txt'
        result=verify(p3b_root=case.p3b,download_root=download,inventory_path=download/'download_inventory.jsonl',
            output_root=bundle,policy_path=root/'plan/policy.json',readable=case.readable,symbols=['TESTUSDT'],
            sample_plan_path=root/'plan/sample_plan.json',**kw)
        assert result['status']=='READY',result
        for name in ('manifest.json','requests.jsonl'):shutil.copyfile(case.p3b/name,bundle/name)
        shutil.copyfile(download/'download_inventory.jsonl',bundle/'download_inventory.jsonl')
        for name in ('findings.jsonl','corrections.jsonl'):
            for row in read(bundle,name):
                for ref in row['source_refs']:
                    path=ref['relative_path']
                    if path is None or (bundle/path).exists():continue
                    source=next(base/path for base in (case.p3b,download) if (base/path).is_file())
                    (bundle/path).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,bundle/path)
        summary=fetch.summarize_sample(root/'plan',[bundle],root/(stage+'-summary'))
        if stage=='base':
            assert 'EXPANSION_REQUIRED' in summary['reason_codes'],summary
            assert 'N=302 n=300 e=1 u=0 s=299' in (root/'base-summary/sample_report.txt').read_text()
        bundles.append(bundle);summaries.append(summary)
    assert frozen==(root/'plan/sample_plan.json').read_bytes()
    return root,p,bundles,summaries


def test_real_dv3_error_expands_frozen_prefix_into_dv1_l3(tmp_path,monkeypatch):
    import socket
    def deny(*args,**kwargs):raise AssertionError('network forbidden')
    monkeypatch.setattr(socket.socket,'connect',deny)
    monkeypatch.setattr(socket,'create_connection',deny)
    root,p,bundles,summaries=real_expansion_flow(tmp_path/'expansion')
    assert summaries[1]['status']=='READY',summaries[1]
    extra={d['day_start'] for d in p['strata'][0]['draws'][300:]}
    base=read(bundles[0],'corrections.jsonl');expanded=read(bundles[1],'corrections.jsonl')
    assert not any(c['timestamp']//DAY*DAY in extra for c in base)
    selected=[c for c in expanded if c['timestamp']//DAY*DAY in extra]
    assert len(selected)==2*25*6
    assert all(c['decision']=='KEEP' and c['row_action']=='include' for c in selected)
    assert all(c['coverage_status']=='PASS' for c in selected if c['evidence_kind']=='trade_adjudication')
    for b in bundles:assert read(b,'verification.json')['sample_plan_sha256']==sha((root/'plan/sample_plan.json').read_bytes())
    report=(root/'base-summary/sample_report.txt').read_bytes()
    assert (bundles[1]/'sample_report.txt').read_bytes()==report
    assert read(bundles[1],'verification.json')['files']['sample_report.txt']['sha256']==sha(report)
    assert 'N=302 n=300 e=1 u=0 s=299' in (root/'expanded-summary/sample_report.txt').read_text()


@pytest.mark.parametrize('mutation,reason',[
    ('sha','EXPANSION_PLAN_MISMATCH'),('tier','EXPANSION_STRATUM_MISMATCH'),
    ('population','EXPANSION_STRATUM_MISMATCH'),('base','EXPANSION_STRATUM_MISMATCH'),
    ('short_prefix','EXPANSION_PREFIX_MISMATCH'),('long_prefix','EXPANSION_PREFIX_MISMATCH'),
    ('duplicate_prefix','EXPANSION_REPORT_SCHEMA'),('no_trigger','EXPANSION_REPORT_SCHEMA'),
    ('rank','SAMPLE_SCOPE'),('replace_draw','EXPANSION_PLAN_MISMATCH')])
def test_expansion_handoff_rejects_changed_identity_or_nonprefix(tmp_path,mutation,reason):
    from program_code.research.r8_data import verification as dv1
    from program_code.research.r8_data import verification_fetch as dv3
    from program_code.research.tests.test_r8_verification_fetch import source,plan,artifact,T as start
    p=artifact(plan(tmp_path,source(tmp_path,days=365,valid=True),end=start+365*DAY))
    summary=dv3.summarize_sample(tmp_path/'out',[],tmp_path/'summary')
    report=Path(summary['artifact_root'],summary['primary_file']).read_bytes()
    assert 'EXPANSION_REQUIRED' in summary['reason_codes']
    path=tmp_path/'out/sample_plan.json'
    if mutation=='sha':report=report.replace(sha(path.read_bytes()).encode(),b'0'*64)
    if mutation=='tier':report=report.replace(b'2020 GE_100M',b'2020 NO_OPEN')
    if mutation=='population':report=report.replace(b'N=353',b'N=354')
    if mutation=='base':report=report.replace(b'n=300',b'n=299')
    if mutation=='short_prefix':report=report.replace(b'required_prefix=353',b'required_prefix=301')
    if mutation=='long_prefix':report=report.replace(b'required_prefix=353',b'required_prefix=354')
    if mutation=='duplicate_prefix':report=report.replace(b'required_prefix=353 max_expansions=1\n',b'required_prefix=353 max_expansions=1\n'*2)
    if mutation=='no_trigger':report=report.replace(b'e=0 u=300',b'e=0 u=0')
    if mutation=='rank':
        p['strata'][0]['draws'][300]['rank']=302;path.write_bytes(enc(p))
    if mutation=='replace_draw':
        draws=p['strata'][0]['draws'];draws[0]['day_start'],draws[-1]['day_start']=draws[-1]['day_start'],draws[0]['day_start']
        path.write_bytes(enc(p))
    run=dv1._Run(p['readable'],p['policy_sha256'])
    with pytest.raises(ValueError,match='^'+reason+'$'):
        dv1._sample(path,run,p['p3b_manifest_sha256'],['AUSDT'],report)


@pytest.mark.parametrize('mode',['missing_counterpart','partial_listing'])
def test_l2_coverage_only_turnover_worklist(case,mode):
    case.trades=None
    if mode=='missing_counterpart':
        case.hours=[];case.daily[0].update(volume='0',turnover='0')
    else:
        case.first=T+6*HOUR;case.hours=case.hours[6:]
        case.daily[0].update(volume='18',turnover='180')
    result,findings,cs,_=case.run()
    assert result['status']=='READY'
    amount=correction(cs,'turnover')
    if mode=='missing_counterpart':
        assert (amount['decision'],amount['reason_code'],amount['row_action'])==('UNRESOLVED','TURNOVER_INPUT_INCOMPLETE','missing')
    else:
        assert (amount['decision'],amount['candidate_value'],amount['formula'])==('KEEP','180','sum_hourly_reported')
    assert not any(f['rule_id'] in ('DV-L3','C3_QUANTITY','C5_REBUILD') for f in findings)


# §13.7 transcribed literals: independent of both verification implementations.
V2_DAILY = [
 'R/K/R/K/K/R','U/K/K/K/K/R','Ks/K/K/K/K/R','K/K/K/R/R/R',
 'Ks/K/K/K/K/R','K/K/R/K/K/R','K/K/K/U/R/R','Ks/K/K/R/R/R',
 'K/K/K/R/R/R','U/K/K/K/K/R','U/K/K/R/R/U','U/U/U/U/U/R',
 'Ks/K/K/K/K/R','Ks/K/K/K/K/R','K/K/R/K/K/R','Ks/K/K/U/K/R',
 'U/K/K/R/R/R','K/K/R/K/K/R','U/K/K/U/R/R','U/K/K/R/R/R',
 'K/K/K/R/R/R','K/K/K/R/R/R','U/U/U/U/U/U','U/U/U/U/U/R',
 'K/K/R/K/K/R','Ks/K/K/K/K/R']


def dv7_reverify(root,flow,*,previous=True):
    """DV1 consumes real DV3 plan/originals, keeping its v1 sample bytes frozen."""
    import shutil
    root=Path(root);plan=read(root/'plan','sample_plan.json')
    p=read(root/'plan','policy.json');v2_policy(p)
    (root/'policy-v2.json').write_bytes(enc(p))
    out=root/'bundle-v2'
    kwargs=dict(p3b_root=root/'p3b',download_root=root/'downloads',
        inventory_path=root/'downloads/download_inventory.jsonl',output_root=out,
        policy_path=root/'policy-v2.json',readable=plan['readable'],symbols=[flow['symbol']],
        sample_plan_path=root/'plan/sample_plan.json')
    if previous:kwargs['previous_corrections_path']=root/'bundle/corrections.jsonl'
    result=verify(**kwargs)
    assert result['status']=='READY',result
    assert (out/'sample_plan.json').read_bytes()==(root/'plan/sample_plan.json').read_bytes()
    for name in ('manifest.json','requests.jsonl','download_inventory.jsonl'):
        shutil.copyfile(root/'bundle'/name,out/name)
    refs=[r for name in ('findings.jsonl','corrections.jsonl','volume_semantics.jsonl')
          for item in read(out,name) for r in item['source_refs']]
    refs += [r for item in read(out,'volume_semantics.jsonl')
             for e in item['confidence_evidence'].values() for r in e['source_refs']]
    for ref in refs:
        name=ref['relative_path']
        if name is None:continue
        target=out/name
        if target.exists():assert sha(target.read_bytes())==ref['sha256'];continue
        source=next(p/name for p in (root/'p3b',root/'downloads',root/'bundle')
                    if (p/name).is_file() and sha((p/name).read_bytes())==ref['sha256'])
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    return result


@pytest.fixture(scope='session')
def dv7_main_verifier():
    # Differential byte oracle is immutable reviewed main source, run with the
    # same actual tool identity. No tool_commit byte is masked or rewritten.
    if not Path('/Users/ncyu/Projects/TradeBot/r8-research/crosscheck-20261022').exists():
        pytest.skip('frozen local originals unavailable')
    import subprocess,types
    from program_code.research.r8_data import verification as current
    source=subprocess.check_output(['git','show',
        'a892fea5a171dd1b7fda421e7b2d4c3bf9c1de13:program_code/research/r8_data/verification.py'],cwd=SPEC.parents[2])
    module=types.ModuleType('_dv7_reviewed_main');module.__file__=current.__file__
    sys.modules[module.__name__]=module
    exec(compile(source,current.__file__,'exec'),module.__dict__)
    return module.verify


@pytest.mark.parametrize('index',range(26),ids=[s+'-'+d for s,d,_ in CROSSCHECK])
def test_dv7_26_days_spec_cells_tail_witnesses_and_v1_bytes(tmp_path,index,dv7_main_verifier,record_property):
    base=Path('/Users/ncyu/Projects/TradeBot')
    if not (base/'r8-research/crosscheck-20261022').exists():pytest.skip('frozen local originals unavailable')
    root=tmp_path/'integration';flow=real_dv13_flow(root,index,
        frozen_standard='ba65fbca3b9230ad1807b82c923e9e60ab870edbe5c1e0d5090ebce99b06f6d0')
    plan=read(root/'plan','sample_plan.json')
    oracle=dv7_main_verifier(p3b_root=root/'p3b',download_root=root/'downloads',
        inventory_path=root/'downloads/download_inventory.jsonl',output_root=root/'main-bundle',
        policy_path=root/'plan/policy.json',readable=plan['readable'],symbols=[flow['symbol']],
        sample_plan_path=root/'plan/sample_plan.json')
    assert oracle['status']=='READY',oracle
    hashes={}
    for name in ('findings.jsonl','corrections.jsonl','verification.json'):
        actual=(root/'bundle'/name).read_bytes();expected=(root/'main-bundle'/name).read_bytes()
        assert actual==expected,name
        hashes[name]=sha(actual)
    legacy=read(root/'bundle','corrections.jsonl');t=flow['day_start']
    prior=read(base/'audits/2026-10-22-r8-data-verify-dv1','26-day-results.json')[index]
    for f in FIELDS:
        c=correction(legacy,f,timestamp=t)
        for key,value in prior['decisions'][f].items():assert c[key]==value,(f,key)
    for f,ambiguous in zip(('open','close'),BOUNDARY_MULTI[index]):
        assert (correction(legacy,f,timestamp=t)['order_status']=='TIMESTAMP_MULTI_PRICE')==ambiguous
    result=dv7_reverify(root,flow)
    cs=read(root/'bundle-v2','corrections.jsonl');rows=read(root/'bundle-v2','volume_semantics.jsonl')
    expected=V2_DAILY[index].split('/')
    for f,s in zip(FIELDS,expected):
        c=correction(cs,f,timestamp=t)
        assert c['decision']=={'K':'KEEP','Ks':'KEEP','R':'CORRECT','U':'UNRESOLVED'}[s],(f,c)
        assert c['row_action']==('missing' if 'U' in expected else 'include')
        if s=='Ks':assert c['reason_code']=='EXCHANGE_OPEN_SEMANTICS'
        assert c['supersedes']==correction(legacy,f,timestamp=t)['correction_id']
    tails=[r for r in rows if r['hour_classification']=='TERMINAL_SUFFIX_EXACT' and r['day_applicable']]
    witnesses=[x for x in V2_TAIL_WITNESSES if x[0]==CROSSCHECK[index][0] and x[1]==CROSSCHECK[index][1]]
    assert len(tails)==len(witnesses)
    for symbol,date,hour,count,volume,first,tail_first,tail_last,groups,prefix_count in witnesses:
        row=next(r for r in tails if r['timestamp']==t+hour*HOUR)
        assert (row['tail_count'],row['tail_volume'],row['prefix_first_timestamp'])==(count,volume,first)
        assert (row['tail_first_timestamp'],row['tail_last_timestamp'],row['tail_group_count'],row['prefix_count'])==(tail_first,tail_last,groups,prefix_count)
        assert {'C3_ORIGINAL_FAIL','SOURCE_TRUTH_UNVERIFIED'}<=set(row['reason_codes'])
    # §8.4.1 emits evidence only; the six effective scalar values carry none of it.
    assert set(result['files'])=={'policy.json','findings.jsonl','corrections.jsonl','verification.json','sample_plan.json','volume_semantics.jsonl'}
    effective=[{f:next(c['corrected_value'] if c['decision']=='CORRECT' else c['original_value']
        for c in cs if (c['interval'],c['timestamp'],c['field'])==(interval,stamp,f)) for f in FIELDS}
        for interval,stamp in sorted({(c['interval'],c['timestamp']) for c in cs if c['row_action']=='include'})]
    assert all(set(row)==set(FIELDS) and all(isinstance(v,str) for v in row.values()) for row in effective)
    record_property('dv7',json.dumps(dict(symbol=flow['symbol'],date=CROSSCHECK[index][1],v1_sha256=hashes,
        field_cells=42,boundary_flags=2,v2_daily=expected,selected_hours=len(tails),tail_count=sum(r['tail_count'] for r in tails),bundle=str(root/'bundle-v2')),sort_keys=True))


@pytest.mark.parametrize('mutation,classification',[
 ('subset','PARTIAL_TIMESTAMP_SUBSET'),('no_suffix','NO_COMPLETE_SUFFIX'),
 ('positive','POSITIVE_VOLUME_DELTA'),('empty','EMPTY_PREFIX'),
 ('c2','C2_CONFLICT'),('missing','MISSING_ORIGINAL_HOUR'),('c1','C1_INVALID')])
def test_v2_rejects_incomplete_or_invalid_day_without_fallback(case,mutation,classification):
    suffix_case(case)
    if mutation in ('subset','no_suffix'):
        case.trades.insert(2,dict(case.trades[1],size='0.7',trdMatchID='same-time'))
        case.hours[0]['volume']='1.8' if mutation=='no_suffix' else '1.7'
    elif mutation=='positive':case.hours[0]['volume']='2'
    elif mutation=='empty':case.hours[0]['volume']='0'
    elif mutation=='c2':case.trades=[x for x in case.trades if x['trdMatchID']!='1']
    elif mutation=='missing':case.hours.pop(0)
    elif mutation=='c1':case.trades[1]['trdMatchID']='0'
    a,fs,cs,_=case.run();assert a['status']=='READY',a
    rows=read(Path(a['artifact_root']),'volume_semantics.jsonl')
    target=T+HOUR if mutation=='c2' else T
    assert next(r for r in rows if r['timestamp']==target)['hour_classification']==classification
    assert not any(r['day_applicable'] for r in rows)
    assert correction(cs,'volume')['decision']=='UNRESOLVED'
    assert not any('TERMINAL_SUFFIX_SOURCE_SELECTED' in c['reason_codes'] for c in cs)


def test_v2_multiple_hours_multiple_numeric_timestamp_groups(case):
    suffix_case(case)
    case.trades.insert(2,dict(case.trades[1],timestamp='1609461001.0000002',size='0.25',trdMatchID='tail2'))
    case.trades.insert(4,dict(case.trades[1],timestamp='1609466400',size='0.5',trdMatchID='later'))
    # 1609466400 is the next box: use an interior time for the second tail.
    case.trades[4]['timestamp']='1609466399.9999999'
    case.daily[0]['volume']='25.25'
    a,_,cs,_=case.run();assert a['status']=='READY'
    rows=read(Path(a['artifact_root']),'volume_semantics.jsonl')
    assert [(r['tail_count'],r['tail_group_count'],r['tail_volume']) for r in rows[:2]]==[(2,2,'0.75'),(1,1,'0.5')]
    assert all(r['day_applicable'] for r in rows)
    assert correction(cs,'volume')['decision']=='KEEP'


@pytest.mark.parametrize('boundary',['open','close'])
def test_v2_boundary_mult_price_blocks_only_affected_field(case,boundary):
    suffix_case(case)
    i=0 if boundary=='open' else 1
    case.trades.insert(i+1,dict(case.trades[i],price='11',size='0.1',trdMatchID='ambiguous'))
    case.daily[0]['volume']='24.6'
    if boundary=='open':case.hours[0]['volume']='1.1'
    a,_,cs,_=case.run();assert a['status']=='READY'
    c=correction(cs,boundary,'60')
    assert c['decision']=='UNRESOLVED' and c['reason_code']=='TIMESTAMP_MULTI_PRICE'
    assert c['row_action']=='missing'
    assert correction(cs,'volume','60')['decision']=='CORRECT'


def test_v2_post_l1_failure_preserves_selected_volume_and_original_c3(case):
    suffix_case(case);case.hours[0].update(open='11',high='11')
    a,fs,cs,_=case.run();assert a['status']=='READY'
    assert all(c['row_action']=='missing' for c in cs if c['interval']=='60' and c['timestamp']==T)
    assert correction(cs,'volume','60')['corrected_value']=='1.5'
    assert 'POST_CORRECTION_L1_FAIL' in correction(cs,'high','60')['reason_codes']
    assert any(f['reason_code']=='POST_CORRECTION_L1_FAIL' for f in fs)
    assert any(f['rule_id']=='C3_QUANTITY' and f['reason_code']=='COVERAGE_CONFLICT' for f in fs)
    assert not any(f['reason_code']=='C3_STRICT_PASS' for f in fs)


def test_v2_invalid_open_does_not_gain_new_correction_authority(case):
    suffix_case(case);case.daily[0]['open']='0'
    a,_,cs,_=case.run();assert a['status']=='READY'
    assert correction(cs,'open')['decision']=='UNRESOLVED'
    assert correction(cs,'volume')['decision']=='KEEP'


@pytest.mark.parametrize('change',[
 lambda p:p.pop('schema_version'),lambda p:p.pop('volume_semantics_policy'),
 lambda p:p.update(volume_semantics_policy='unknown'),lambda p:p.update(volume_semantics_policy='v1-strict'),
 lambda p:p.update(schema_version='r8_data_verification_policy_v1'),lambda p:p.update(approval_event='RH-20261022-04'),
 lambda p:p.update(extra=True)])
def test_v2_policy_missing_unknown_or_inconsistent_rejected(case,change):
    def invalid(p):v2_policy(p);change(p)
    case.policy_change=invalid
    a,*_=case.run();assert a['status']=='BLOCKED' and 'POLICY_MISMATCH' in a['reason_codes']


# Independent investigation E_23_HOUR_TABLE.md / e-hour-rebuilds.json witnesses.
V2_TAIL_WITNESSES = [
    ('BCHUSDT', '2021-02-18', 12, 2, '0.58', '1613649600.1464', '1613653193.6058', '1613653193.7813', 2, 1907),
    ('BCHUSDT', '2021-02-18', 23, 1, '0.1', '1613689236.8757', '1613692796.5758', '1613692796.5758', 1, 776),
    ('BCHUSDT', '2021-02-28', 23, 1, '1.99', '1614553221.5927', '1614556798.7559', '1614556798.7559', 1, 878),
    ('BCHUSDT', '2021-04-02', 8, 2, '0.81', '1617350411.4117', '1617353998.4274', '1617353998.7136', 2, 703),
    ('BCHUSDT', '2021-04-02', 23, 1, '0.04', '1617404424.2353', '1617407997.2861', '1617407997.2861', 1, 435),
    ('BTCUSDT', '2021-02-12', 12, 4, '0.423', '1613131204.5969', '1613134793.9543', '1613134799.6303', 3, 4178),
    ('BTCUSDT', '2021-02-12', 17, 1, '0.001', '1613149201.529', '1613152796.5575', '1613152796.5575', 1, 3823),
    ('BTCUSDT', '2021-02-12', 21, 2, '3', '1613163602.888', '1613167199.359', '1613167199.359', 1, 3450),
    ('BTCUSDT', '2021-02-13', 8, 2, '0.033', '1613203200.231', '1613206799.1439', '1613206799.1772', 2, 6524),
    ('BTCUSDT', '2021-02-13', 17, 2, '0.013', '1613235603.7484', '1613239199.5159', '1613239199.5599', 2, 2806),
    ('BTCUSDT', '2021-02-14', 15, 3, '0.02', '1613314801.6059', '1613318398.4869', '1613318398.7442', 3, 6390),
    ('BTCUSDT', '2021-02-14', 16, 2, '0.079', '1613318400.4643', '1613321997.5258', '1613321999.9987', 2, 3945),
    ('BTCUSDT', '2021-02-27', 23, 4, '0.333', '1614466800.1404', '1614470397.8247', '1614470398.4796', 4, 12139),
    ('ETHUSDT', '2021-04-01', 23, 2, '1.93', '1617318003.3117', '1617321596.0894', '1617321596.0903', 2, 734),
    ('ETHUSDT', '2021-04-07', 10, 3, '0.17', '1617789601.0343', '1617793199.4473', '1617793199.6229', 3, 2542),
    ('ETHUSDT', '2021-04-07', 16, 2, '3.61', '1617811202.8834', '1617814799.3476', '1617814799.9548', 2, 2439),
    ('ETHUSDT', '2021-04-07', 23, 1, '0.69', '1617836403.9464', '1617839996.5873', '1617839996.5873', 1, 1496),
    ('LINKUSDT', '2021-03-03', 10, 2, '92.4', '1614765600.285', '1614769187.7426', '1614769188.1207', 2, 683),
    ('LINKUSDT', '2021-03-03', 14, 1, '37.7', '1614780012.5234', '1614783589.7446', '1614783589.7446', 1, 1122),
    ('LINKUSDT', '2021-03-03', 23, 7, '199', '1614812405.4653', '1614815997.383', '1614815997.3833', 2, 676),
    ('LTCUSDT', '2021-03-17', 9, 2, '2.2', '1615971610.8684', '1615975173.7629', '1615975173.9742', 2, 966),
    ('LTCUSDT', '2021-04-10', 12, 7, '81.3', '1618056000.4971', '1618059589.5184', '1618059589.5839', 7, 1153),
    ('XTZUSDT', '2021-03-24', 23, 1, '0.1', '1616626807.2922', '1616630395.8748', '1616630395.8748', 1, 672),
]


def test_v2_confidence_unknown_and_contradiction_never_change_selected_verdict(case):
    suffix_case(case)
    a,_,first,_=case.run()
    semantics=read(Path(a['artifact_root']),'volume_semantics.jsonl')
    assert semantics[0]['confidence_evidence']['tail_minute']['status']=='UNAVAILABLE'
    assert semantics[0]['confidence_evidence']['next_hour_open']['status']=='SUPPORTS'
    case.hours[1].update(open='11',high='11')
    b,_,second,_=case.run()
    semantics=read(Path(b['artifact_root']),'volume_semantics.jsonl')
    assert semantics[0]['confidence_evidence']['next_hour_open']['status']=='CONTRADICTS'
    for interval in ('D','60'):
        for f in FIELDS:
            x=correction(first,f,interval);y=correction(second,f,interval)
            assert tuple(x[k] for k in ('decision','corrected_value','row_action'))==tuple(y[k] for k in ('decision','corrected_value','row_action'))


def test_v2_numeric_timestamp_grouping_no_partial_equal_stamp_selection(case):
    suffix_case(case)
    case.trades[1]['timestamp']='1609461000.00000020'
    case.trades.insert(2,dict(case.trades[1],timestamp='1.6094610000000002e9',size='0.5',trdMatchID='equal_numeric'))
    case.hours[0]['volume']='1.5' # only half of the indivisible last stamp group
    case.daily[0]['volume']='25'
    a,_,cs,_=case.run();assert a['status']=='READY'
    rows=read(Path(a['artifact_root']),'volume_semantics.jsonl')
    assert rows[0]['hour_classification']=='PARTIAL_TIMESTAMP_SUBSET'
    assert correction(cs,'volume')['decision']=='UNRESOLVED'


def test_v2_large_partial_subset_diagnosis_is_resource_bounded(tmp_path,record_property):
    # Isolate the historical exponential search so RED cannot exhaust the runner.
    import subprocess,time
    script = '''
import json,resource,sys,time,tracemalloc
from pathlib import Path
from fractions import Fraction
from program_code.research.tests.test_r8_data_verification import Case,T,v2_policy,read,correction
from program_code.research.r8_data import verification as v
case=Case(Path(sys.argv[1]));case.policy_change=v2_policy
sizes=[2**i for i in range(1,31)];need=2**30-1
case.trades=case.trades[1:]+[dict(timestamp=str(T//1000+1800),symbol='TESTUSDT',side='Buy',size=str(s),price='10',trdMatchID='power'+str(i)) for i,s in enumerate(sizes)]
case.trades.sort(key=lambda r:Fraction(r['timestamp']))
case.hours[0]['volume']=str(sum(sizes)-need)
case.daily[0]['volume']=str(sum(sizes)+23)
tracemalloc.start();start=time.monotonic();result,_,cs,_=case.run()
assert result['status']=='READY',result
row=next(r for r in read(Path(result['artifact_root']),'volume_semantics.jsonl') if r['timestamp']==T)
print(json.dumps(dict(classification=row['hour_classification'],applicable=row['day_applicable'],decision=correction(cs,'volume')['decision'],seconds=time.monotonic()-start,peak_traced_bytes=tracemalloc.get_traced_memory()[1],peak_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)))
'''
    started=time.monotonic()
    try:
        completed=subprocess.run([sys.executable,'-c',script,str(tmp_path)],
            cwd=SPEC.parents[2],capture_output=True,text=True,timeout=5)
    except subprocess.TimeoutExpired:
        pytest.fail('partial subset diagnosis exceeded the fixed five-second process budget')
    assert completed.returncode==0,completed.stderr
    result=json.loads(completed.stdout)
    assert (result['classification'],result['applicable'],result['decision'])==('PARTIAL_SUBSET_UNDETERMINED',False,'UNRESOLVED')
    from program_code.research.r8_data import verification as v
    assert (v.MAX_PARTIAL_SUBSET_BITS,v.MAX_PARTIAL_SUBSET_ITEMS,v.MAX_PARTIAL_SCALE_BITS)==(1048576,4096,4096)
    peak_bytes=result['peak_rss']*(1 if sys.platform=='darwin' else 1024)
    # Linux lifetime RSS can retain the pre-exec parent's high-water mark.
    # Bound allocations made by this verification call; retain RSS diagnostically.
    assert result['peak_traced_bytes']<256*1024*1024
    record_property('partial_subset_wall_seconds',time.monotonic()-started)
    record_property('partial_subset_peak_traced_bytes',result['peak_traced_bytes'])
    record_property('partial_subset_peak_rss_bytes',peak_bytes)


def test_v2_no_next_day_or_outside_readable_market_decode(case):
    suffix_case(case)
    # Move the tail to 23:00; no following-day price may be read for confidence.
    tail=case.trades.pop(1);tail['timestamp']='1609545599.123456789';case.trades.append(tail)
    case.hours.append(bar(T+DAY,open='POISON',high='POISON',low='POISON',close='POISON',volume='POISON',turnover='POISON'))
    a,_,cs,_=case.run();assert a['status']=='READY'
    rows=read(Path(a['artifact_root']),'volume_semantics.jsonl')
    assert rows[-1]['hour_classification']=='TERMINAL_SUFFIX_EXACT'
    assert rows[-1]['confidence_evidence']['next_hour_open']['status']=='UNAVAILABLE'
    assert b'POISON' not in b''.join((Path(a['artifact_root'])/n).read_bytes() for n in a['files'])
    case.readable['end']=T+12*HOUR
    b,_,cs,_=case.run();assert b['status']=='READY'
    rows=read(Path(b['artifact_root']),'volume_semantics.jsonl')
    assert rows and all(r['hour_classification']=='OUT_OF_SCOPE' and not r['day_applicable'] for r in rows)
    assert not any('TRADE_SOURCE_SELECTED_BY_E' in c['reason_codes'] for c in cs)


def test_v2_real_dv3_plan_and_originals_and_evidence_only_handoff(tmp_path):
    root=tmp_path/'actual';flow=real_dv13_flow(root,configure=suffix_case)
    result=dv7_reverify(root,flow)
    assert flow['network_requests']==0
    p=read(root/'bundle-v2','policy.json');v=read(root/'bundle-v2','verification.json')
    assert v['standard_sha256']==sha(SPEC.read_bytes())
    assert v['policy_sha256']==sha(enc(p))
    assert v['sample_plan_sha256']==flow['plan']['primary_sha256']
    assert all(name in {'policy.json','verification.json','findings.jsonl','corrections.jsonl','volume_semantics.jsonl','sample_plan.json'} for name in result['files'])
    cs=read(root/'bundle-v2','corrections.jsonl')
    for c in cs:
        assert not {'tail_count','confidence_evidence','hour_classification'}&set(c)
        if c['decision']=='KEEP':assert c['corrected_value'] is None
    # No effective-value file is emitted by DV1: DV2 owns the U4 writer.
    assert not (root/'bundle-v2/source').exists()


def test_v2_frozen_sample_policy_mismatch_is_not_blanket_exempt(case):
    suffix_case(case);case.write()
    p=policy(sha((case.p3b/'manifest.json').read_bytes()))
    plan=dict(schema_version='r8_verification_sample_plan_v1',policy_sha256='a'*64,
        p3b_manifest_sha256=p['p3b_manifest_sha256'],readable=case.readable,seed=20261022,
        strata=[dict(year=2021,tier='NO_OPEN',population_size=1,base_size=1,max_size=1,
            draws=[dict(rank=1,symbol='TESTUSDT',day_start=T)])])
    path=case.root/'sample_plan.json';path.write_bytes(enc(plan))
    a,*_=case.run(sample_plan_path=path)
    assert a['status']=='BLOCKED' and 'SAMPLE_IDENTITY' in a['reason_codes']


@pytest.mark.parametrize('standard',[
 'afcb87578676c998b4ce7529c6e1c09d5214cfe7e8af53ad03d120781c696931',
 'd0fbf9ff02d080027d575eb6488f2c552c3a583485b8c685166fe0ef94b2af98',
 'ba65fbca3b9230ad1807b82c923e9e60ab870edbe5c1e0d5090ebce99b06f6d0',
 'ad80220cd6dc3f8dc5c451c6281aa9f1b2acf7fbb47bc80ed21eb3905710110c',
 '125901d0341487bd058be70e7cc2ed27be7c3be270a45d05587e471104b7cacf'])
def test_v2_historical_v1_frozen_policy_identity_is_retained(case,standard):
    suffix_case(case);case.write()
    manifest=sha((case.p3b/'manifest.json').read_bytes())
    p=policy(manifest);p['standard_sha256']=standard
    plan=dict(schema_version='r8_verification_sample_plan_v1',policy_sha256=sha(enc(p)),
        p3b_manifest_sha256=manifest,readable=case.readable,seed=20261022,
        strata=[dict(year=2021,tier='NO_OPEN',population_size=1,base_size=1,max_size=1,
            draws=[dict(rank=1,symbol='TESTUSDT',day_start=T)])])
    path=case.root/'sample_plan.json';path.write_bytes(enc(plan));before=path.read_bytes()
    a,_,cs,v=case.run(sample_plan_path=path)
    assert a['status']=='READY',a
    assert v['sample_plan_sha256']==sha(before)
    assert (Path(a['artifact_root'])/'sample_plan.json').read_bytes()==before
    assert correction(cs,'volume','60')['corrected_value']=='1.5'


def test_v2_identity_precedes_c1_and_retains_all_input_failures(case):
    suffix_case(case)
    case.trades[1].update(symbol='WRONGUSDT',price='UNREADABLE_OTHER_SYMBOL',size='UNREADABLE_OTHER_SYMBOL')
    a,_,cs,_=case.run();assert a['status']=='READY'
    rows=read(Path(a['artifact_root']),'volume_semantics.jsonl')
    assert rows[0]['hour_classification']=='IDENTITY_UNCERTAIN'
    assert {'IDENTITY_UNCERTAIN','C1_INVALID'}<=set(rows[0]['reason_codes'])
    assert not any(r['day_applicable'] for r in rows)
    assert b'UNREADABLE_OTHER_SYMBOL' not in b''.join((Path(a['artifact_root'])/n).read_bytes() for n in a['files'])


def test_v2_no_suffix_day_retains_v1_post_l1_unresolved_decisions(case):
    case.hours[0].update(open='11',high='11')
    _,_,v1,_=case.run();case.policy_change=v2_policy
    a,_,v2,_=case.run();assert a['status']=='READY'
    assert all(r['hour_classification']=='STRICT_C3' and not r['day_applicable'] for r in read(Path(a['artifact_root']),'volume_semantics.jsonl'))
    for f in FIELDS:
        old=correction(v1,f,'60');new=correction(v2,f,'60')
        assert tuple(old[k] for k in ('decision','corrected_value','row_action'))==tuple(new[k] for k in ('decision','corrected_value','row_action'))


@pytest.mark.parametrize('bad',[[],None,'v2-terminal-suffix-20261022'])
def test_v2_non_object_policy_is_rejected_with_fixed_reason(case,bad):
    case.write();path=case.root/'bad-policy.json';path.write_bytes(enc(bad))
    result=verify(p3b_root=case.p3b,download_root=case.dl,inventory_path=case.dl/'download_inventory.jsonl',
        output_root=case.root/'invalid-policy-output',policy_path=path,readable=case.readable,symbols=['TESTUSDT'])
    assert result['status']=='BLOCKED' and result['reason_codes']==['POLICY_MISMATCH']


def test_e2_001_v2_turnover_only_day_has_every_required_hour(case):
    case.policy_change=v2_policy;case.hours.pop(12)
    case.daily[0].update(volume='23',turnover='230');case.trades=None
    result,_,cs,_=case.run()
    assert result['status']=='READY'
    rows=read(Path(result['artifact_root']),'volume_semantics.jsonl')
    assert {r['timestamp'] for r in rows}==set(range(T,T+DAY,HOUR))
    missing=next(r for r in rows if r['timestamp']==T+12*HOUR)
    assert missing['hour_classification']=='MISSING_ORIGINAL_HOUR'
    assert all(not r['day_applicable'] for r in rows)
    assert correction(cs,'turnover')['decision']=='UNRESOLVED'


def test_e2_002_zero_trade_hour_is_strict_without_bypassing_rebuild_gate(case):
    suffix_case(case)
    case.trades=[r for r in case.trades if r['trdMatchID']!='1']
    case.hours[1].update(volume='0',turnover='0')
    case.daily[0].update(volume='23.5',turnover='230')
    result,_,cs,_=case.run();rows=read(Path(result['artifact_root']),'volume_semantics.jsonl')
    zero=next(r for r in rows if r['timestamp']==T+HOUR)
    assert (zero['hour_classification'],zero['trade_volume'],zero['volume_delta'])==('STRICT_C3','0','0')
    assert zero['day_applicable'] is True
    assert (zero['prefix_count'],zero['prefix_first_timestamp'],zero['tail_count'])==(0,None,0)
    assert correction(cs,'volume','60',T+HOUR)['row_action']=='missing'
    assert 'C5_REBUILD' in correction(cs,'volume','60',T+HOUR)['reason_codes']
