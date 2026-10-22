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

# DV2 uses real producer and ledger APIs.  Only the deployment pin is injected:
# neither the producer's return value nor a ledger query is mocked.
from program_code.research.r8_data import verification as verifier
from program_code.research.r8_ledger.ledger import ResearchLedger, sha256 as ledger_sha
import csv
import io
import shutil

DV_T = 1609459200000
DV_DAY = 86400000
DV_HOUR = 3600000
DV_FIELDS = ['open', 'high', 'low', 'close', 'volume', 'turnover']


def dv_encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                       allow_nan=False)+'\n').encode()


def dv_read(root, name):
    raw = (root/name).read_bytes()
    return [json.loads(line) for line in raw.splitlines()] if name.endswith('.jsonl') else json.loads(raw)


class VerifiedCase:
    def __init__(self, root, monkeypatch, *, days=40, version=1, first_hour=0,
                 quantities=None, amounts=None, daily_amounts=None, suffix=False,
                 missing=(), registration_change=None, instrument_change=None, poison_outside=False, end_offset=0, daily_open='10', sampling=False):
        self.root, self.monkeypatch = root, monkeypatch
        root.mkdir(parents=True, exist_ok=True)
        self.u1 = root/'u1'; self.u1.mkdir()
        self.downloads = root/'downloads'; self.downloads.mkdir()
        self.start = DV_T; self.end = DV_T+days*DV_DAY+end_offset
        self.first = DV_T+first_hour*DV_HOUR
        self.version = version; self.files = {}; self.requests = []; self.inventory = []
        self.poison_outside = poison_outside
        quantities = quantities or ['1']*days
        amounts = amounts or ['10']*days  # each hourly reported turnover
        instruments = []
        for symbol in ('BTCUSDT', 'XUSDT'):
            hours, daily = [], []
            for d in range(days):
                day = DV_T+d*DV_DAY; bins = range(first_hour if d == 0 else 0, 24)
                q, amount = Decimal(quantities[d]), Decimal(amounts[d])
                count = len(bins); trades = []
                for h in bins:
                    t = day+h*DV_HOUR
                    values = ['10', '10', '10', '10', str(q), str(amount)]
                    if (d, h) not in missing: hours.append([str(t), *values])
                    trades.append([str(t//1000)+'.0000001', symbol, 'Buy', str(q), '10', str(t)])
                    if suffix and d == 20 and h == 0:
                        trades.append([str(t//1000+1800)+'.0000002', symbol, 'Sell', '0.5', '10', str(t)+'tail'])
                volume = q*count + (Decimal('0.5') if suffix and d == 20 else 0)
                a = str(amount*count) if daily_amounts is None else daily_amounts[d]
                daily.append([str(day), daily_open, '10', '10', '10', str(volume), a])
                name = f'{symbol}-{day}.csv.gz'
                self._csv(self.downloads/name, ['timestamp', 'symbol', 'side', 'size', 'price', 'trdMatchID'], trades)
                data = (self.downloads/name).read_bytes()
                self.inventory.append(dict(schema_version='r8_verification_download_v1', request_id=name,
                    symbol=symbol, day_start=day, interval='trade', source_kind='bybit_trade',
                    url=f'https://public.bybit.com/trading/{symbol}/{symbol}{datetime.fromtimestamp(day//1000,timezone.utc):%Y-%m-%d}.csv.gz',
                    started_at=day, finished_at=day+1, http_status=200, api_status=None,
                    byte_count=len(data), relative_path=name, sha256=digest(data), status='AVAILABLE', reason_code=None))
            for interval, rows in [('60', hours), ('D', daily)]:
                self._market(symbol, 'kline', interval, ['timestamp', *DV_FIELDS], rows)
            funding=[[str(DV_T), '0']]
            if end_offset:funding += [[str(self.end),'0.001'],[str(self.end+1),'0.002']]
            self._market(symbol, 'funding', 'funding', ['timestamp', 'funding_rate'], funding)
            self._market(symbol, 'open_interest', '4h', ['timestamp', 'open_interest'], [[str(DV_T), '1']])
            instruments.append(dict(symbol=symbol, baseCoin=symbol[:-4], quoteCoin='USDT', settleCoin='USDT',
                contractType='LinearPerpetual', status='Trading', launchTime=str(self.first), deliveryTime='0',
                fundingInterval='480', priceFilter={'tickSize':'0.01'},
                lotSizeFilter={'qtyStep':'0.01','minOrderQty':'0.01','minNotionalValue':'5'}))
            if instrument_change and symbol=='XUSDT':instrument_change(instruments[-1])
        rid = self._raw('/v5/market/instruments-info', {'category':'linear'},
                        {'category':'linear','list':instruments})
        request_bytes = b''.join(dv_encode(r) for r in self.requests)
        (self.u1/'requests.jsonl').write_bytes(request_bytes)
        manifest = dict(tool_version='r8-public-data-2', files=self.files, request_log_sha256=digest(request_bytes),
                        universe_request_ids=[rid], universe={s:{'deliveryTime':0,'launch_time':self.first} for s in ('BTCUSDT','XUSDT')})
        (self.u1/'manifest.json').write_bytes(dv_encode(manifest))
        self.manifest_sha = digest(dv_encode(manifest))
        spec = Path(__file__).resolve().parents[3]/'docs/execution_plan/2026-10-22--r8-stage2-data-verification-standard.md'
        self.policy = dict(schema_version=f'r8_data_verification_policy_v{version}', standard_sha256=digest(spec.read_bytes()),
            approval_event='RH-20261022-04' if version == 1 else 'RH-20261022-05', p3b_manifest_sha256=self.manifest_sha,
            listing=dict(x_pct='50',y_pct='20',z_pct='20',cooling_days=7,quantity='hourly_base_volume_daily_mean',variation='mean_relative_difference',stage_end_ranges=[[1,3],[7,15],[15,30]]),
            sampling=dict(seed=20261022,base_per_stratum=300,max_per_stratum=900,max_expansions=1,confidence='0.95',upper_limit='0.025'),
            turnover=dict(window_days=12,thresholds=['1000000','10000000','100000000'],trigger_pct='5',general='exchange_reported',suspect='sum_hourly_reported'),l4_price_threshold_pct='1')
        if version == 2:self.policy['volume_semantics_policy'] = 'v2-terminal-suffix-20261022'
        (root/'policy.json').write_bytes(dv_encode(self.policy))
        self.inventory.sort(key=lambda r:(r['symbol'],r['day_start'],r['source_kind'],r['interval'],r['request_id']))
        (root/'inventory.jsonl').write_bytes(b''.join(dv_encode(r) for r in self.inventory))
        plan=None
        if sampling:
            from program_code.research.r8_data import verification_fetch as fetch
            sources=[fetch.CSVSource(m['symbol'],m['dataset'],m['interval'],n,m['sha256']) for n,m in self.files.items() if m['dataset']=='kline']
            handoff=fetch.build_sample_plan(self.u1,root/'plan',sources,readable={'start':self.start,'end':self.end},p3b_manifest_sha256=self.manifest_sha)
            assert handoff['status']=='READY',handoff
            plan=root/'plan/sample_plan.json'
        result = verifier.verify(p3b_root=self.u1, download_root=self.downloads, inventory_path=root/'inventory.jsonl',
            output_root=root/'bundle', policy_path=root/'policy.json', readable={'start':self.start,'end':self.end}, symbols=['BTCUSDT','XUSDT'],sample_plan_path=plan)
        assert result['status'] == 'READY', result
        self.bundle_sha = result['primary_sha256']
        self.bundle = root/'verification-bundles'/self.bundle_sha
        self.bundle.parent.mkdir(); shutil.move(root/'bundle', self.bundle)
        # Archive referenced originals in the immutable bundle namespace.
        for p in self.downloads.iterdir():shutil.copyfile(p, self.bundle/p.name)
        self.pin()
        self.policy_sha = digest((root/'policy.json').read_bytes())
        r = registration(); r.update(data_family='ordinary', data_policy_sha256=self.policy_sha)
        if registration_change:registration_change(r)
        self.book = ResearchLedger(root/'ledger')
        self.registration_sha = self.book.preregister(r)
        self.args = dict(u1=self.u1, u1_manifest_sha256=self.manifest_sha, ledger=self.book.out,
                         hypothesis='h1', window={'start':DV_T+13*DV_DAY,'end':self.end}, out=root/'result', validation=True)

    def pin(self):
        self.monkeypatch.setattr(mod, 'VERIFICATION_BUNDLES',
            ((self.manifest_sha,self.start,self.end,('BTCUSDT','XUSDT'),self.bundle_sha),), raising=False)

    def _csv(self, path, header, rows):
        text = io.StringIO(); writer = csv.writer(text, lineterminator='\n'); writer.writerow(header);writer.writerows(rows)
        path.write_bytes(gzip.compress(text.getvalue().encode(),mtime=0))

    def _raw(self, endpoint, params, result):
        rid = len(self.requests)+1; data = dv_encode({'retCode':0,'result':result})
        (self.u1/'raw').mkdir(exist_ok=True);(self.u1/f'raw/{rid}.json').write_bytes(data)
        self.requests.append(dict(request_id=rid,base_url='https://api.bybit.com',endpoint=endpoint,
                                 params=params,http_status=200,retCode=0,raw_sha256=digest(data)))
        return rid

    def _market(self, symbol, dataset, interval, header, rows):
        if self.poison_outside:rows = rows+[[str(self.end+DV_DAY), *(['UNREADABLE']*(len(header)-1))]]
        name=f'{dataset}_{symbol}_{interval}.csv.gz';self._csv(self.u1/name,header,rows)
        rid=self._raw('/v5/market/kline',dict(category='linear',symbol=symbol,interval=interval),
                      dict(category='linear',symbol=symbol,list=rows)) if dataset=='kline' else None
        self.files[name]=dict(dataset=dataset,symbol=symbol,interval=interval,sha256=digest((self.u1/name).read_bytes()),
            first_timestamp=int(rows[0][0]),last_timestamp=int(rows[-1][0]),source_request_ids=[rid] if rid else [],gaps={'missing_intervals':[]})


@pytest.mark.parametrize('version',[1,2])
def test_dv2_real_verify_ledger_materialize_fixed_handoff(tmp_path,monkeypatch,version):
    case=VerifiedCase(tmp_path,monkeypatch,version=version)
    result=mod.materialize(**case.args)
    binding=dv_read(case.args['out'],'verification/hypothesis_binding.json')
    assert binding==dict(schema_version='r8_verification_hypothesis_binding_v1',hypothesis_id='h1',
        policy_sha256=case.policy_sha,family='ordinary',registration_sha256=case.registration_sha)
    assert case.book.data_access('h1')['selection']['symbols']==['XUSDT']
    stages=dv_read(case.args['out'],'verification/listing_regimes.jsonl')
    assert [(r['day_start'],r['stage']) for r in stages if r['symbol']=='XUSDT' and r['day_start'] in (DV_T,DV_T+3*DV_DAY,DV_T+7*DV_DAY,DV_T+15*DV_DAY)]==[
        (DV_T,'initial'),(DV_T+3*DV_DAY,'middle'),(DV_T+7*DV_DAY,'stabilizing'),(DV_T+15*DV_DAY,'ordinary')]
    rows=dv_read(case.args['out'],'verification/turnover_decisions.jsonl')
    row=next(r for r in rows if r['symbol']=='XUSDT' and r['decision_utc_day']==DV_T+13*DV_DAY)
    assert (row['m_d'],row['m_e'],row['m_h'],row['selected_tier'],row['history_sufficient'])==('240','240',None,'NO_OPEN',True)
    assert len(row['inputs'])==12 and row['status']=='READY'
    assert result==dv_read(case.args['out'],'materialization.json')
    for name,meta in result['files'].items():
        assert set(meta)=={'sha256','rows','first','last','source_file','source_sha256'}
        assert digest((case.args['out']/name).read_bytes())==meta['sha256']
    assert (case.args['out']/'custom/listing_regime/xusdt.csv').read_text().splitlines()[0]=='known_at,day_start,stage,reason_code,cooling,policy_sha256'
    if version==2:assert 'verification/volume_semantics.jsonl' in result['files']


@pytest.mark.parametrize('field,value', [
    ('data_family',None),('data_policy_sha256',None),('data_family','carry'),
    ('data_family',1),('data_policy_sha256','A'*64),('data_policy_sha256',1),
    ('data_policy_sha256','a'*64)])
def test_dv2_binding_fail_closed_without_parameter_fallback(tmp_path,monkeypatch,field,value):
    def change(r):
        r['strategy_parameters']=dict(data_family=r['data_family'],data_policy_sha256=r['data_policy_sha256'])
        if value is None:r.pop(field)
        else:r[field]=value
    case=VerifiedCase(tmp_path,monkeypatch,registration_change=change)
    with pytest.raises(mod.MaterializationError,match='BINDING'):
        mod.materialize(**case.args)
    assert not (case.args['out']/'materialization.json').exists()
    blocked=dv_read(tmp_path/'result.blocked','verification.json')
    assert blocked['status']=='BLOCKED' and blocked['reason_codes']
    assert case.book._read('trials')==[]


@pytest.mark.parametrize('statistical_family',['carry','fixture','synthetic','ordinary','listing'])
def test_dv2_statistical_family_does_not_select_data_family(tmp_path,monkeypatch,statistical_family):
    case=VerifiedCase(tmp_path,monkeypatch,registration_change=lambda r:r.update(family=statistical_family,data_family='listing'))
    mod.materialize(**case.args)
    assert dv_read(case.args['out'],'verification/hypothesis_binding.json')['family']=='listing'


@pytest.mark.parametrize('version',[1,2])
def test_dv2_real_correction_overlay_missing_and_v2_tail(tmp_path,monkeypatch,version):
    case=VerifiedCase(tmp_path,monkeypatch,version=version,suffix=True)
    result=mod.materialize(**case.args)
    out=case.args['out'];t=DV_T+20*DV_DAY
    def rows(name):return {int(r['timestamp']):r for r in csv.DictReader((out/name).read_text().splitlines())}
    original=rows('verification/original/kline_XUSDT_60.csv')
    hour=rows('source/kline_XUSDT_60.csv');day=rows('source/kline_XUSDT_D.csv')
    assert original[t]['volume']=='1'
    if version==2:
        assert [hour[t][f] for f in ('volume','high','low','close')]==['1.5','10','10','10']
        assert day[t]['volume']=='24.5' and day[t]['turnover']=='240'
        assert any(r['hour_classification']=='TERMINAL_SUFFIX_EXACT' for r in dv_read(out,'verification/volume_semantics.jsonl'))
    else:
        assert t not in day and t not in hour
        assert any(g['start']<=t<g['end_exclusive'] for g in result['gaps']['XUSDT']['kline_hour'])
    for root in ('source','custom','lean'):
        for path in (out/root).rglob('*'):
            if path.is_file():
                raw=path.read_bytes()
                assert all(x not in raw for x in (b'tail_count',b'confidence_evidence',b'trade_reconstructed',b'original_value'))
    assert 'source/funding_XUSDT_funding.csv' in result['files']


def test_dv2_future_unreadable_numeric_values_never_decoded(tmp_path,monkeypatch):
    case=VerifiedCase(tmp_path,monkeypatch,poison_outside=True)
    result=mod.materialize(**case.args)
    for name in result['files']:
        assert b'UNREADABLE' not in (case.args['out']/name).read_bytes()


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


@pytest.fixture
def setup(tmp_path,monkeypatch):
    case=VerifiedCase(tmp_path,monkeypatch)
    return case.book,case.args


def directory_bytes(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_materialize_formats_known_times_and_manifest(setup):
    book,args=setup;result=mod.materialize(**args);out=args['out']
    assert result['schema_version']=='r8_materialization_v1' and result['purpose']=='validation'
    assert result['ledger_id']==book.ledger_id and result['symbols']==['BTCUSDT','XUSDT']
    assert result['strategy_symbols']==['XUSDT']
    assert result['warmup']=={'start':DV_T,'end':DV_T+13*DV_DAY}
    with zipfile.ZipFile(out/'lean/cryptofuture/bybit/hour/xusdt_trade.zip') as z:
        assert z.namelist()==['xusdt_trade_perp.csv']
        assert z.read(z.namelist()[0]).decode().splitlines()[0]=='20210101 00:00,10,10,10,10,1'
    assert (out/'custom/open_interest/xusdt.csv').read_text()==f'{DV_T+4*DV_HOUR},{DV_T},1\n'
    assert (out/'custom/funding/xusdt.csv').read_text()==f'{DV_T},{DV_T},0\n'
    assert (out/'custom/turnover_hour/xusdt.csv').read_text().splitlines()[0]==f'{DV_T+DV_HOUR},{DV_T},10'
    assert (out/'custom/kline_day/xusdt.csv').read_text().splitlines()[0]==f'{DV_T+DV_DAY},{DV_T},10,10,10,10,24'
    assert result['first_bar']=={'BTCUSDT':DV_T,'XUSDT':DV_T}
    assert result['min_notional']['XUSDT']=='5' and result['funding_interval_ms']['XUSDT']==28800000
    assert not list(out.rglob('*margin_interest*'))


@pytest.mark.parametrize('target',['manifest.json','requests.jsonl','raw/5.json','kline_XUSDT_60.csv.gz'])
def test_tampered_hashes_rejected_without_output(setup,target):
    _,args=setup;p=args['u1']/target;p.write_bytes(p.read_bytes()+b' ')
    with pytest.raises(mod.MaterializationError):mod.materialize(**args)
    assert not args['out'].exists() and not list(args['out'].parent.glob('.result-*'))


def test_version_and_pinned_manifest_rejected_even_self_consistent(setup,monkeypatch):
    _,args=setup
    with pytest.raises(mod.MaterializationError,match='P3b'):mod.materialize(**dict(args,validation=False))
    monkeypatch.setattr(mod,'P3B_MANIFEST_SHA256',args['u1_manifest_sha256'])
    assert mod.materialize(**dict(args,validation=False))['purpose']=='research'
    p=args['u1']/'manifest.json';m=json.loads(p.read_bytes());m['tool_version']='r8-public-data-1';p.write_bytes(dv_encode(m))
    with pytest.raises(mod.MaterializationError,match='版本'):
        mod.materialize(**dict(args,out=args['out'].parent/'other',u1_manifest_sha256=digest(p.read_bytes())))


@pytest.mark.parametrize('state',['unopened','denied','other_candidate','candidate'])
def test_all_holdout_materialization_denied(setup,state):
    book,args=setup;interval={'start':'2026-01-08T00:00:00Z','end':'2026-05-15T00:00:00Z'}
    if state!='unopened':append_fixture_event(book,'holdouts',{'action':'denied' if state=='denied' else 'opened',
        'generation':1,'intervals':{'h2' if state=='other_candidate' else 'h1':interval}})
    with pytest.raises(mod.MaterializationError,match='holdout'):mod.materialize(**dict(args,window=interval))
    assert not args['out'].exists()


@pytest.mark.parametrize('window',[
    {'start':'2025-07-03T00:00:00Z','end':'2025-10-02T00:00:00Z'},
    {'start':'2025-12-20T00:00:00Z','end':'2026-01-09T00:00:00Z'},
    {'start':'2026-05-28T00:00:00Z','end':'2026-06-01T00:00:00Z'},
    {'start':'2019-12-31T00:00:00Z','end':'2020-02-01T00:00:00Z'}])
def test_forbidden_window_and_cross_generation_warmup_rejected(setup,window):
    _,args=setup
    with pytest.raises(mod.MaterializationError):mod.materialize(**dict(args,window=window))
    assert not args['out'].exists()


@pytest.mark.parametrize('change',['short_lookback','no_symbols','duplicate_symbols','path_symbol'])
def test_registration_constraints_rejected(setup,change):
    _,args=setup;r=registration()
    if change=='short_lookback':r['max_lookback_seconds']=12*86400
    elif change=='no_symbols':del r['selection']['symbols']
    else:r['selection']['symbols']=['BTCUSDT','BTCUSDT'] if change=='duplicate_symbols' else ['../bad']
    other=args['ledger'].parent/'other';make_book(other,r)
    with pytest.raises(mod.MaterializationError):mod.materialize(**dict(args,ledger=other))
    assert not args['out'].exists()


@pytest.mark.parametrize('missing_identity',[False,True])
def test_missing_ledger_refused_without_creation(setup,missing_identity):
    _,args=setup;other=args['ledger'].parent/'absent'
    if missing_identity:other.mkdir()
    with pytest.raises(mod.MaterializationError):mod.materialize(**dict(args,ledger=other))
    assert not (other/'ledger_id.json').exists() and not (other/'.ledger.lock').exists()


@pytest.mark.parametrize('field,value',[('tickSize',None),('qtyStep','0'),('minOrderQty','-1'),('minNotionalValue','NaN'),('fundingInterval','0')])
def test_bad_instrument_fields_rejected(tmp_path,monkeypatch,field,value):
    def change(item):
        target=item if field=='fundingInterval' else item['priceFilter'] if field=='tickSize' else item['lotSizeFilter']
        if value is None:del target[field]
        else:target[field]=value
    case=VerifiedCase(tmp_path,monkeypatch,instrument_change=change)
    with pytest.raises((mod.MaterializationError,KeyError)):mod.materialize(**case.args)
    assert not case.args['out'].exists()


@pytest.mark.parametrize('case,value,reason',[
    ('missing',None,'鍵不存在'),('null',None,'值為 None'),('empty','','值為空字串'),('whitespace','  ','值僅含空白')])
def test_missing_min_notional_is_zero_and_disclosed(tmp_path,monkeypatch,case,value,reason):
    def change(item):
        if case=='missing':item['lotSizeFilter'].pop('minNotionalValue')
        else:item['lotSizeFilter']['minNotionalValue']=value
    data=VerifiedCase(tmp_path,monkeypatch,instrument_change=change)
    result=mod.materialize(**data.args)
    assert result['min_notional']=={'BTCUSDT':'5','XUSDT':'0'}
    assert [x for x in result['limitations'] if 'minNotionalValue' in x]==[f'XUSDT: 缺 minNotionalValue（{reason}），記為 0。']


@pytest.mark.parametrize('value',['abc','-1','nan','NaN','inf','-inf','Infinity',0,False])
def test_invalid_min_notional_rejected_without_output(tmp_path,monkeypatch,value):
    case=VerifiedCase(tmp_path,monkeypatch,instrument_change=lambda i:i['lotSizeFilter'].update(minNotionalValue=value))
    with pytest.raises(mod.MaterializationError):mod.materialize(**case.args)
    assert not case.args['out'].exists()


@pytest.mark.parametrize('field',['tickSize','qtyStep','minOrderQty'])
@pytest.mark.parametrize('value',[None,'','  '])
def test_other_missing_numeric_attributes_still_rejected(tmp_path,monkeypatch,field,value):
    def change(i):(i['priceFilter'] if field=='tickSize' else i['lotSizeFilter'])[field]=value
    case=VerifiedCase(tmp_path,monkeypatch,instrument_change=change)
    with pytest.raises(mod.MaterializationError):mod.materialize(**case.args)
    assert not case.args['out'].exists()


def test_output_byte_determinism_and_schema(setup):
    _,args=setup;result=mod.materialize(**args);other=args['out'].parent/'second'
    mod.materialize(**dict(args,out=other))
    assert directory_bytes(args['out'])==directory_bytes(other)
    assert set(result)==set('schema_version u1_manifest_sha256 u1_tool_version ledger_id hypothesis_id generation purpose window warmup readable symbols strategy_symbols files gaps first_bar min_notional funding_interval_ms delistings symbol_properties_overlay_sha256 limitations'.split())
    assert (args['out']/'materialization.json').read_bytes()==canonical(result)
    names={str(p.relative_to(args['out'])) for folder in ('lean','custom','source','verification') for p in (args['out']/folder).rglob('*') if p.is_file()}
    assert names==set(result['files'])


def test_existing_output_repository_and_interrupted_publication(setup,monkeypatch):
    _,args=setup;args['out'].mkdir();(args['out']/'keep').write_bytes(b'keep')
    with pytest.raises(mod.MaterializationError):mod.materialize(**args)
    assert (args['out']/'keep').read_bytes()==b'keep'
    repo_out=Path(__file__).resolve().parents[3]/'u4-forbidden-output'
    with pytest.raises(mod.MaterializationError,match='倉庫'):mod.materialize(**dict(args,out=repo_out))
    assert not repo_out.exists()
    def fail(*args):raise OSError('合成 rename 失敗')
    monkeypatch.setattr(mod.os,'rename',fail)
    with pytest.raises(OSError):mod.materialize(**dict(args,out=args['out'].parent/'interrupted'))
    assert not (args['out'].parent/'interrupted').exists() and not list(args['out'].parent.glob('.interrupted-*'))


def test_ast_host_imports_and_no_float_decimal_conversion():
    root=Path(__file__).resolve().parents[3]
    for name in ('r8_engine/materialize.py','r8_ledger/ledger.py'):
        tree=ast.parse((root/'program_code/research'/name).read_text())
        for node in ast.walk(tree):
            imports=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else []
            for imported in imports:assert imported.split('.')[0] in sys.stdlib_module_names or imported.startswith(('program_code.research.r8_engine','program_code.research.r8_ledger'))
            if name.startswith('r8_engine') and isinstance(node,ast.Call) and isinstance(node.func,ast.Name):assert node.func.id!='float'


def test_strategy_symbols_preserve_order_and_btc_membership(tmp_path,monkeypatch):
    case=VerifiedCase(tmp_path,monkeypatch,registration_change=lambda r:r['selection'].update(symbols=['XUSDT','BTCUSDT']))
    result=mod.materialize(**case.args)
    assert result['strategy_symbols']==['XUSDT','BTCUSDT'] and result['symbols']==['BTCUSDT','XUSDT']


def test_cli_accepts_iso_window_and_reports_failure_without_output(setup,capsys):
    _,args=setup;argv=[]
    for key in ('u1','u1_manifest_sha256','ledger','hypothesis','out'):argv.extend(['--'+key.replace('_','-'),str(args[key])])
    dates=[datetime.fromtimestamp(args['window'][k]//1000,timezone.utc).isoformat() for k in ('start','end')]
    argv.extend(['--window',','.join(dates),'--validation']);mod.main(argv)
    assert json.loads(capsys.readouterr().out)['window']==args['window']
    with pytest.raises(SystemExit) as failure:mod.main(argv)
    assert failure.value.code==2


def listing_fixture(q, *, first_hour=0, amounts=None):
    first=DV_T+first_hour*DV_HOUR;hours={};daily={};refs={}
    for d,value in enumerate(q):
        day=DV_T+d*DV_DAY
        for h in range(first_hour if d==0 else 0,24):
            if value is None and h==1:continue
            hours[day+h*DV_HOUR]=['10','10','10','10',value or '1','10']
        if amounts is None or amounts[d] is not None:daily[day]=['10','10','10','10','24',amounts[d] if amounts else '240']
    return mod._listing('XUSDT',first,first,[],hours,daily,refs,DV_T+len(q)*DV_DAY,'a'*64)


@pytest.mark.parametrize('second,expected',[('5','middle'),('4.999999999999999999999999999999','middle'),('5.000000000000000000000000000001','initial')])
def test_listing_peak_threshold_exact_and_first_partial_mean(second,expected):
    rows=listing_fixture(['10',second]+['10']*5,first_hour=12)
    row=next(r for r in rows if r['known_at']==DV_T+2*DV_DAY)
    assert row['stage']==expected
    first=row['quantity_inputs'][0]
    assert (first['volume_sum'],first['hour_count'],first['status'])==('120',12,'PARTIAL')
    assert rows[0]['known_at']==DV_T+13*DV_HOUR and rows[0]['quantity_inputs']==[]


@pytest.mark.parametrize('recent,expected',[('24','stabilizing'),('24.00000000000000000000001','middle')])
def test_listing_middle_relative_mean_not_cv(recent,expected):
    rows=listing_fixture(['17']*4+[recent]*3)
    assert rows[-1]['stage']==expected


@pytest.mark.parametrize('recent,expected',[('15','ordinary'),('15.00000000000000000000001','stabilizing')])
def test_listing_stabilizing_median_threshold_exact(recent,expected):
    rows=listing_fixture(['10']*8+[recent]*7)
    assert rows[-1]['stage']==expected


def test_listing_missing_prefix_forces_clock_only_one_transition():
    rows=listing_fixture([None]*31)
    assert [(r['day_start'],r['stage']) for r in rows if r['day_start'] in [DV_T+3*DV_DAY,DV_T+15*DV_DAY,DV_T+30*DV_DAY]]==[
        (DV_T+3*DV_DAY,'middle'),(DV_T+15*DV_DAY,'stabilizing'),(DV_T+30*DV_DAY,'ordinary')]
    assert all(r['cooling'] is True for r in rows if r['day_start']>=DV_T+7*DV_DAY)
    assert all(x['status']=='MISSING' and x['hour_count']==24 and x['volume_sum'] is None for x in rows[-1]['quantity_inputs'])


def test_listing_zero_volume_boxes_count_and_zero_peak_no_early_end():
    hours={DV_T+h*DV_HOUR:['1','1','1','1','24' if h==0 else '0','1'] for h in range(24)}
    item,q=mod._quantity(DV_T,DV_T,hours,{})
    assert item['volume_sum']=='24' and item['hour_count']==24 and q==1
    assert [r['stage'] for r in listing_fixture(['0']*3)]==['initial','initial','initial','middle']


def test_listing_cooling_w7_threshold_missing_and_partial():
    rows=listing_fixture(['1']*10,amounts=['999999.99']*7+['1000000',None,'1'])
    by={r['day_start']:r['cooling'] for r in rows}
    assert [by[DV_T+d*DV_DAY] for d in (6,7,8,9)]==[None,True,False,None]
    partial=listing_fixture(['1']*8,first_hour=12)
    assert partial[7]['cooling'] is None and partial[8]['cooling'] is True


def test_listing_and_turnover_causal_prefix_invariance(tmp_path,monkeypatch):
    a=VerifiedCase(tmp_path/'a',monkeypatch,quantities=['10']*40);mod.materialize(**a.args)
    b=VerifiedCase(tmp_path/'b',monkeypatch,quantities=['10']*20+['999999']*20,amounts=['10']*20+['9000000']*20);mod.materialize(**b.args)
    def prefix(case):
        return [{k:r[k] for k in ('symbol','day_start','known_at','stage','reason_code','cooling')} for r in dv_read(case.args['out'],'verification/listing_regimes.jsonl') if r['known_at']<=DV_T+20*DV_DAY]
    assert prefix(a)==prefix(b)
    def decisions(case):
        return [{k:r[k] for k in ('symbol','decision_utc_day','history_sufficient','m_d','m_e','m_h','triggered','selected_source','selected_median','selected_tier','reason_codes')} for r in dv_read(case.args['out'],'verification/turnover_decisions.jsonl') if r['known_at']<=DV_T+20*DV_DAY]
    assert decisions(a)==decisions(b)


def turnover_fixture(amounts, hourly, *, first=DV_T, missing_hour=None, day=None):
    originals={DV_T+i*DV_DAY:['1']*5+[v] for i,v in enumerate(amounts) if v is not None}
    hours={DV_T+i*DV_DAY+h*DV_HOUR:['1']*5+[hourly] for i in range(len(amounts)) for h in range(24) if (i,h)!=missing_hour}
    t=DV_T+12*DV_DAY if day is None else day
    return mod._turnover('XUSDT',first,t,t+DV_DAY,originals,originals,hours,{}, {},'a'*64)[0]


@pytest.mark.parametrize('threshold',[1000000,10000000,100000000])
@pytest.mark.parametrize('factor,triggered',[('0.95',True),('1.05',True),('0.94999999999999999999999999',False),('1.05000000000000000000000001',False)])
def test_turnover_trigger_inclusive_five_percent_band(threshold,factor,triggered):
    # Integer scaling preserves the independently chosen decimal endpoints.
    from fractions import Fraction
    value=mod._text(Fraction(factor)*threshold)
    row=turnover_fixture([value]*12,'1')
    assert row['triggered'] is triggered
    assert row['m_d']==row['m_e']==value
    assert row['known_at']==row['decision_utc_day'] and len(row['inputs'])==12
    assert (row['m_h'] is not None) is triggered


@pytest.mark.parametrize('amount,tier',[('999999','NO_OPEN'),('1000000','GE_1M'),('10000000','GE_10M'),('100000000','GE_100M')])
def test_turnover_four_tiers_and_even_median(amount,tier):
    row=turnover_fixture([amount]*12,amount)
    assert row['tier_e']==tier
    row=turnover_fixture([str(n) for n in range(1,13)],'1')
    assert row['m_e']=='6.5' and row['m_d']=='6.5' and row['selected_source']=='effective_daily'


def test_turnover_hourly_flip_missing_zero_and_history_insufficient():
    row=turnover_fixture(['1050000']*12,'40000')
    assert (row['m_h'],row['tier_h'],row['selected_source'],row['selected_tier'])==('960000','NO_OPEN','hourly_sum','NO_OPEN')
    assert 'ORIGINAL_HOURLY_TIER_DIFFERENCE' in row['reason_codes']
    row=turnover_fixture(['1000000']*12,'50000',missing_hour=(2,3))
    assert row['inputs'][2]['sum_hourly_reported'] is None and row['inputs'][2]['hourly_status']=='MISSING'
    assert row['m_h']=='1200000' and row['selected_source']=='effective_daily'
    assert 'TURNOVER_INPUT_INCOMPLETE' in row['reason_codes']
    row=turnover_fixture(['1000000']*12,'50000',first=DV_T+DV_HOUR)
    assert row['history_sufficient'] is False and row['selected_tier']=='NO_OPEN'
    assert row['inputs'][0]['effective_reported'] is None


def mutate_bundle(case,name,change):
    data=dv_read(case.bundle,name);change(data)
    raw=b''.join(dv_encode(r) for r in data) if name.endswith('.jsonl') else dv_encode(data)
    (case.bundle/name).write_bytes(raw)
    report=dv_read(case.bundle,'verification.json')
    if name!='verification.json':report['files'][name]={'sha256':digest(raw),'rows':len(raw.splitlines())}
    else:report=data
    (case.bundle/'verification.json').write_bytes(dv_encode(report))
    sha=digest(dv_encode(report));target=case.bundle.parent/sha
    case.bundle.rename(target);case.bundle=target;case.bundle_sha=sha;case.pin()


@pytest.mark.parametrize('part', ['counts','finding','reference_type','semantic_number','semantic_timestamp','semantic_source','semantic_day','rules'])
def test_dv2_rejects_unknown_fields_and_wrong_types_with_blocked_evidence(tmp_path,monkeypatch,part):
    case=VerifiedCase(tmp_path,monkeypatch,version=2,suffix=True)
    if part=='counts':name='verification.json';change=lambda r:r['counts'].update(extra=1)
    elif part=='finding':name='findings.jsonl';change=lambda r:r[0].update(extra='bad')
    elif part=='reference_type':name='corrections.jsonl';change=lambda r:r[0]['source_refs'][0].update(trade_id=12)
    elif part=='semantic_number':name='volume_semantics.jsonl';change=lambda r:r[0].update(original_volume=1)
    elif part=='semantic_timestamp':name='volume_semantics.jsonl';change=lambda r:r[0].update(day_start=r[0]['day_start']+1)
    elif part=='semantic_source':name='volume_semantics.jsonl';change=lambda r:r[0].update(volume_source='v1_strict')
    elif part=='semantic_day':name='volume_semantics.jsonl';change=lambda r:r[0].update(day_applicable=False)
    else:name='corrections.jsonl';change=lambda r:r[0].update(rule_ids=['DV-L1','DV-L1'])
    if name=='corrections.jsonl':
        original_change=change
        def change(r):
            original_change(r)
            r[0]['correction_id']=digest(dv_encode({k:v for k,v in r[0].items() if k!='correction_id'}))
    mutate_bundle(case,name,change)
    with pytest.raises(mod.MaterializationError):mod.materialize(**case.args)
    assert not case.args['out'].exists()
    assert dv_read(tmp_path/'result.blocked','verification.json')['status']=='BLOCKED'


LOCAL_P3B=Path('/Users/ncyu/Projects/TradeBot/r8-research/data/p3b-20261020')
LOCAL_CROSSCHECK=Path('/Users/ncyu/Projects/TradeBot/r8-research/crosscheck-20261022')


def actual_bch_bundle(root,version):
    """Copy opaque originals; real verify alone decodes the approved training prefix."""
    from types import SimpleNamespace
    root.mkdir(parents=True,exist_ok=True);u1=root/'u1';u1.mkdir();(u1/'raw').mkdir()
    manifest_raw=(LOCAL_P3B/'manifest.json').read_bytes();manifest=json.loads(manifest_raw)
    assert digest(manifest_raw)==mod.P3B_MANIFEST_SHA256
    (u1/'manifest.json').write_bytes(manifest_raw)
    (u1/'requests.jsonl').write_bytes((LOCAL_P3B/'requests.jsonl').read_bytes())
    ids=set(manifest['universe_request_ids'])
    for name,meta in manifest['files'].items():
        if meta.get('symbol') in ('BTCUSDT','BCHUSDT') and (meta['dataset'],meta['interval']) in mod.DATASETS:
            shutil.copyfile(LOCAL_P3B/name,u1/name);ids.update(meta['source_request_ids'])
    for rid in ids:shutil.copyfile(LOCAL_P3B/f'raw/{rid}.json',u1/f'raw/{rid}.json')
    start=1585094400000;end=1607990400000;downloads=root/'downloads';downloads.mkdir();inventory=[]
    for line in (LOCAL_CROSSCHECK/'requests.jsonl').read_bytes().splitlines():
        record=json.loads(line);metadata=record['metadata'];symbol=metadata.get('symbol')
        if (symbol,metadata.get('date_utc')) not in [('BCHUSDT','2020-12-14'),('BTCUSDT','2020-03-25')]:continue
        kind={'bybit_trade_file':'bybit_trade','bybit_1m':'bybit_minute'}.get(record['kind'])
        if kind is None:continue
        data=(LOCAL_CROSSCHECK/record['path']).read_bytes();assert digest(data)==record['sha256']
        target=downloads/record['path'];target.parent.mkdir(exist_ok=True,parents=True);target.write_bytes(data)
        day=ms(metadata['date_utc']+'T00:00:00Z')
        inventory.append(dict(schema_version='r8_verification_download_v1',request_id=str(record['request_id']),symbol=symbol,
            day_start=day,interval='trade' if kind=='bybit_trade' else '1',source_kind=kind,url=record['url'],
            started_at=start,finished_at=start+1,http_status=200,api_status=None if kind=='bybit_trade' else 0,
            byte_count=len(data),relative_path=record['path'],sha256=record['sha256'],status='AVAILABLE',reason_code=None))
    inventory.sort(key=lambda r:(r['symbol'],r['day_start'],r['source_kind'],r['interval'],r['request_id']))
    inv=root/'download_inventory.jsonl';inv.write_bytes(b''.join(dv_encode(r) for r in inventory))
    p=json.loads(Path(mod.__file__).with_name('data_verification_policy.json').read_bytes())
    if version==1:p.pop('volume_semantics_policy');p.update(schema_version='r8_data_verification_policy_v1',approval_event='RH-20261022-04')
    policy=root/'policy.json';policy.write_bytes(dv_encode(p))
    result=verifier.verify(p3b_root=u1,download_root=downloads,inventory_path=inv,output_root=root/'verified',
        policy_path=policy,readable={'start':start,'end':end},symbols=['BCHUSDT','BTCUSDT'])
    assert result['status']=='READY',result
    sha=result['primary_sha256'];bundle=root/'verification-bundles'/sha;bundle.parent.mkdir();shutil.move(root/'verified',bundle)
    refs=[ref for name in ('findings.jsonl','corrections.jsonl')+ (('volume_semantics.jsonl',) if version==2 else ())
          for row in dv_read(bundle,name) for ref in row['source_refs']]
    if version==2:refs += [ref for row in dv_read(bundle,'volume_semantics.jsonl') for e in row['confidence_evidence'].values() for ref in e['source_refs']]
    for ref in refs:
        relative=ref['relative_path']
        if relative is None or (u1/relative).is_file() or (bundle/relative).exists():continue
        data=(downloads/relative).read_bytes();assert digest(data)==ref['sha256']
        target=bundle/relative;target.parent.mkdir(exist_ok=True,parents=True);target.write_bytes(data)
    return SimpleNamespace(u1=u1,start=start,end=end,bundle=bundle,bundle_sha=sha,manifest_sha=digest(manifest_raw),policy_sha=digest(policy.read_bytes()),result=result)


def actual_trial(book,result,root):
    # Obtain the existing trial record shape through the real ledger helper, then
    # register this materialization with the real destination ledger.
    template=make_book(root/'template-ledger');record=begin(template)
    iso=lambda n:datetime.fromtimestamp(n//1000,timezone.utc).isoformat().replace('+00:00','Z')
    window={k:iso(v) for k,v in result['window'].items()}
    record.update(data_window=window,fit_window=window,score_window=window,
        manifest_sha256=digest(canonical(result)),data_files={k:v['sha256'] for k,v in result['files'].items()})
    book.begin_trial(record)
    actual=book.trial_record('t1')
    assert set(actual)=={'record','finished','status'} and actual['finished'] is False and actual['status']=='aborted'
    return actual


@pytest.mark.parametrize('version',[1,2])
@pytest.mark.skipif(not LOCAL_P3B.exists(),reason='frozen local P3b originals unavailable')
def test_dv2_real_bch_original_verify_ledger_trial_and_materialize(tmp_path,monkeypatch,version,record_property):
    case=actual_bch_bundle(tmp_path,version)
    monkeypatch.setattr(mod,'VERIFICATION_BUNDLES',((case.manifest_sha,case.start,case.end,('BCHUSDT','BTCUSDT'),case.bundle_sha),))
    r=registration(lookback=(1607904000000-case.start)//1000)
    # This synthetic registration needs room for its long warmup after the first
    # holdout; extending a future boundary reads no future market value.
    r['data_range']['end']='2028-01-01T00:00:00Z'
    r['time_splits'][-1]['end']='2028-01-01T00:00:00Z'
    r['selection']['symbols']=['BCHUSDT'];r.update(data_family='listing',data_policy_sha256=case.policy_sha)
    book=ResearchLedger(tmp_path/'ledger');registration_sha=book.preregister(r)
    args=dict(u1=case.u1,u1_manifest_sha256=case.manifest_sha,ledger=book.out,hypothesis='h1',
        window={'start':1607904000000,'end':case.end},out=tmp_path/'materialized')
    result=mod.materialize(**args);out=args['out']
    effective=list(csv.DictReader((out/'source/kline_BCHUSDT_D.csv').read_text().splitlines()))
    original=list(csv.DictReader((out/'verification/original/kline_BCHUSDT_D.csv').read_text().splitlines()))
    assert len(effective)==1 and len(original)==1
    assert [effective[0][k] for k in DV_FIELDS]==['272.95','280.35','265.15','276.95','10905.15','2954180.78']
    assert original[0]['open']=='0.0' and original[0]['low']=='0.0' and effective[0]['close']==original[0]['close']
    assert dv_read(out,'verification/hypothesis_binding.json')['registration_sha256']==registration_sha
    listing=dv_read(out,'verification/listing_regimes.jsonl');assert any(x['symbol']=='BCHUSDT' and x['stage']=='initial' for x in listing)
    turnover=dv_read(out,'verification/turnover_decisions.jsonl');bch=next(x for x in turnover if x['symbol']=='BCHUSDT')
    assert bch['history_sufficient'] is False and bch['selected_tier']=='NO_OPEN'
    actual=actual_trial(book,result,tmp_path)
    again=mod.materialize(**dict(args,trial='t1',out=tmp_path/'replay'))
    assert result==again and actual['record']['preregistration_sha256']==registration_sha
    assert book.trial_record('t1')['finished'] is False
    record_property('peer_evidence',json.dumps(dict(version=version,producer_file_sha256=digest(Path(verifier.__file__).read_bytes()),
        bundle_sha256=case.bundle_sha,policy_sha256=case.policy_sha,manifest_sha256=digest(canonical(result)),
        bch_effective=effective[0],bch_original=original[0],trial_record_keys=sorted(actual),network_requests=0)))


# These 13 dates are the distinct §13.7 terminal-suffix witnesses, not a list
# selected using this consumer's result.
V2_APPLICABLE=[1,2,4,6,7,8,9,12,13,15,19,21,25]


@pytest.mark.parametrize('index',V2_APPLICABLE)
@pytest.mark.skipif(not LOCAL_CROSSCHECK.exists(),reason='frozen crosscheck originals unavailable')
def test_dv2_v2_thirteen_applicable_original_days_effective_values(tmp_path,monkeypatch,index,record_property):
    from fractions import Fraction
    from program_code.research.tests.test_r8_data_verification import real_dv13_flow,dv7_reverify,V2_DAILY,CROSSCHECK
    flow=real_dv13_flow(tmp_path,index);handoff=dv7_reverify(tmp_path,flow)
    t=flow['day_start'];symbol=flow['symbol'];sha=handoff['primary_sha256']
    parent=tmp_path/'verification-bundles';parent.mkdir();bundle=parent/sha;shutil.move(tmp_path/'bundle-v2',bundle)
    manifest=dv_read(tmp_path/'p3b','manifest.json');manifest_sha=digest((tmp_path/'p3b/manifest.json').read_bytes())
    monkeypatch.setattr(mod,'VERIFICATION_BUNDLES',((manifest_sha,t,t+DV_DAY,(symbol,),sha),))
    consumer=mod._Bundle(tmp_path/'p3b',manifest_sha,t,t+DV_DAY,[symbol])
    assert all(r['day_applicable'] for r in consumer.semantics)
    # Independent exact oracle from archived trades, using only this UTC day.
    trades=[]
    for item in dv_read(tmp_path/'downloads','download_inventory.jsonl'):
        if item['source_kind']!='bybit_trade':continue
        with gzip.open(tmp_path/'downloads'/item['relative_path'],'rt') as source:
            for r in csv.DictReader(source):
                stamp=Fraction(r['timestamp'])
                if t//1000<=stamp<(t+DV_DAY)//1000:trades.append((stamp,Fraction(r['price']),Fraction(r['size'])))
    assert trades
    def truth(group):
        latest=max(x[0] for x in group);closes={x[1] for x in group if x[0]==latest}
        return (sum((x[2] for x in group),Fraction()),max(x[1] for x in group),min(x[1] for x in group),next(iter(closes)) if len(closes)==1 else None)
    daily_expected=truth(trades);counts={}
    for interval in ('D','60'):
        name=f'kline_{symbol}_{interval}.csv.gz';meta=manifest['files'][name]
        rows,effective,original,_,_,missing=mod._market_rows((tmp_path/'p3b'/name).read_bytes(),meta,name,t,t+DV_DAY,consumer)
        actual={stamp:values for stamp,values in rows};counts[interval]=len(rows)
        missing_keys={a for a,b in missing}
        assert not set(actual)&missing_keys
        if interval=='D':
            assert (t in actual)==('U' not in V2_DAILY[index].split('/'))
            if t in actual:assert tuple(Fraction(actual[t][i]) for i in (4,1,2,3))==daily_expected
        else:
            for stamp,values in rows:
                group=[r for r in trades if stamp//1000<=r[0]<(stamp+DV_HOUR)//1000]
                assert tuple(Fraction(values[i]) for i in (4,1,2,3))==truth(group)
        (tmp_path/f'effective-{interval}.csv').write_bytes(effective)
    record_property('v2_effective',json.dumps(dict(symbol=symbol,date=CROSSCHECK[index][1],bundle_sha256=sha,
        original_manifest_sha256=flow['original_p3b_manifest_sha256'],effective_rows=counts,network_requests=0)))


def test_unclosed_market_values_not_decoded_and_funding_endpoint_preserved(tmp_path,monkeypatch):
    end=DV_T+40*DV_DAY-DV_HOUR//2
    case=VerifiedCase(tmp_path,monkeypatch,end_offset=-DV_HOUR//2,
        instrument_change=lambda i:i.update(deliveryTime=str(end),status='Closed'))
    result=mod.materialize(**case.args)
    with (case.args['out']/'source/kline_XUSDT_60.csv').open() as stream:
        hour=list(csv.DictReader(stream))
    assert max(int(r['timestamp']) for r in hour)+DV_HOUR<=end
    original=(case.args['out']/'verification/original/kline_XUSDT_60.csv').read_text()
    assert str(end-DV_HOUR//2)+',' not in original
    funding=(case.args['out']/'custom/funding/xusdt.csv').read_text()
    assert f'{end},{end},0.001\n' in funding and '0.002' not in funding
    assert result['delistings']['XUSDT']['deliveryTime']==end


@pytest.mark.parametrize('mode',['conflict','cycle','source_mismatch','missing_evidence','unknown_v2_enum','unknown_schema'])
def test_bundle_adjudication_failures_preserve_blocked_evidence(tmp_path,monkeypatch,mode):
    case=VerifiedCase(tmp_path,monkeypatch,version=2,suffix=True)
    if mode=='missing_evidence':
        ref=next(r for c in dv_read(case.bundle,'corrections.jsonl') for r in c['source_refs'] if r['kind']=='trade')
        (case.bundle/ref['relative_path']).unlink()
    elif mode=='unknown_v2_enum':mutate_bundle(case,'volume_semantics.jsonl',lambda r:r[0].update(hour_classification='PARTIAL_SUBSET_UNDETERMINED'))
    elif mode=='unknown_schema':mutate_bundle(case,'verification.json',lambda r:r.update(schema_version='r8_data_verification_v3'))
    else:
        def change(rows):
            if mode=='conflict':
                row=copy.deepcopy(rows[0]);row['reason_code']='CONFLICTING_CONTENT';row['correction_id']=digest(dv_encode({k:v for k,v in row.items() if k!='correction_id'}));rows.append(row)
                rows.sort(key=lambda r:(r['timestamp'],r['symbol'],r['dataset'],r['interval'],r['field'],r['correction_id']))
            elif mode=='cycle':rows[0]['supersedes']=rows[0]['correction_id']
            else:
                rows[0]['original_value']='12345';rows[0]['correction_id']=digest(dv_encode({k:v for k,v in rows[0].items() if k!='correction_id'}))
        mutate_bundle(case,'corrections.jsonl',change)
    with pytest.raises(mod.MaterializationError):mod.materialize(**case.args)
    blocked=dv_read(tmp_path/'result.blocked','verification.json')
    assert blocked['status']=='BLOCKED' and blocked['reason_codes']
    assert not case.args['out'].exists()
    assert case.book._read('trials')==[]


def test_unresolved_first_bar_original_identity_and_merged_gap_union(tmp_path,monkeypatch):
    case=VerifiedCase(tmp_path,monkeypatch,version=1,suffix=True)
    # Exercise the union independently of producer values: adjacent/overlapping
    # pre-existing and quarantined ranges must count each hourly slot once.
    assert mod._merged_gaps([(DV_T,DV_T+2*DV_HOUR),(DV_T+DV_HOUR,DV_T+3*DV_HOUR),(DV_T+3*DV_HOUR,DV_T+4*DV_HOUR)],DV_HOUR)==[
        {'start':DV_T,'end_exclusive':DV_T+4*DV_HOUR,'count':4}]
    result=mod.materialize(**case.args)
    assert result['first_bar']['XUSDT']==DV_T
    assert result['gaps']['XUSDT']['kline_hour'] and result['gaps']['XUSDT']['kline_day']
    assert result['files']['source/funding_XUSDT_funding.csv']['rows']==1


def test_real_trial_record_replay_withdrawal_and_post_begin_failure(tmp_path,monkeypatch):
    case=VerifiedCase(tmp_path,monkeypatch);result=mod.materialize(**case.args)
    trial=actual_trial(case.book,result,tmp_path)
    assert trial['record']['manifest_sha256']==digest(canonical(result))
    case.book.withdraw_hypothesis('h1','fixed test withdrawal')
    with pytest.raises(LedgerError):mod.materialize(**dict(case.args,out=tmp_path/'withdrawn'))
    with pytest.raises(mod.MaterializationError,match='data_window'):
        mod.materialize(**dict(case.args,trial='t1',window={'start':DV_T+14*DV_DAY,'end':case.end},out=tmp_path/'bad-window'))
    assert mod.materialize(**dict(case.args,trial='t1',out=tmp_path/'replay'))==result
    (case.bundle/'policy.json').write_bytes(b'corrupted')
    with pytest.raises(mod.MaterializationError):mod.materialize(**dict(case.args,trial='t1',out=tmp_path/'failed-replay'))
    assert case.book.trial_record('t1')==trial
    assert dv_read(tmp_path/'failed-replay.blocked','verification.json')['status']=='BLOCKED'


def test_suspect_daily_turnover_replaced_but_hourly_cap_unchanged(tmp_path,monkeypatch):
    case=VerifiedCase(tmp_path,monkeypatch,daily_amounts=['500']*40,daily_open='0')
    mod.materialize(**case.args);out=case.args['out']
    decision=next(r for r in dv_read(out,'verification/turnover_decisions.jsonl') if r['symbol']=='XUSDT')
    assert (decision['m_d'],decision['m_e'],decision['m_h'])==('500','240',None)
    assert all(i['exchange_reported']=='500' and i['effective_reported']=='240' for i in decision['inputs'])
    assert all(r['turnover']=='10' for r in csv.DictReader((out/'source/kline_XUSDT_60.csv').read_text().splitlines()))
    assert all(r['turnover']=='240' for r in csv.DictReader((out/'source/kline_XUSDT_D.csv').read_text().splitlines()))


def test_turnover_blocked_reason_and_same_key_contract():
    row=turnover_fixture(['1000000']*12,'1')
    for key in ('selected_source','selected_median','selected_tier'):row[key]=None
    row.update(status='BLOCKED',reason_codes=[])
    with pytest.raises(mod.MaterializationError):mod._check_decisions([row])
    row['reason_codes']=['TURNOVER_INPUT_INVALID'];mod._check_decisions([row])
    other=copy.deepcopy(row);other['reason_codes']=['DIFFERENT_CONTENT']
    with pytest.raises(mod.MaterializationError,match='CONFLICT'):mod._check_decisions([row,other])
    row['selected_source']='effective_daily'
    with pytest.raises(mod.MaterializationError):mod._check_decisions([row])


@pytest.mark.parametrize('mutation',['missing_pin','ambiguous_pin','bundle_hash','policy_digest'])
def test_fixed_bundle_selection_no_fallback(tmp_path,monkeypatch,mutation):
    case=VerifiedCase(tmp_path,monkeypatch)
    if mutation=='missing_pin':monkeypatch.setattr(mod,'VERIFICATION_BUNDLES',())
    elif mutation=='ambiguous_pin':monkeypatch.setattr(mod,'VERIFICATION_BUNDLES',mod.VERIFICATION_BUNDLES*2)
    elif mutation=='bundle_hash':(case.bundle/'verification.json').write_bytes((case.bundle/'verification.json').read_bytes()+b' ')
    else:mutate_bundle(case,'verification.json',lambda r:r.update(policy_sha256='a'*64))
    with pytest.raises(mod.MaterializationError):mod.materialize(**case.args)
    assert not case.args['out'].exists()
    assert dv_read(tmp_path/'result.blocked','verification.json')['status']=='BLOCKED'


def test_actual_submit_rejects_real_u4_failure_without_finishing(tmp_path,monkeypatch):
    import subprocess
    from program_code.research.r8_engine import series
    case=VerifiedCase(tmp_path/'inputs',monkeypatch)
    result=mod.materialize(**case.args);trial=actual_trial(case.book,result,tmp_path)
    repo=tmp_path/'isolated-source';repo.mkdir()
    project=Path(mod.__file__).resolve().parents[3]
    for directory in series.ENGINE_DIRS:
        shutil.copytree(project/directory,repo/directory,ignore=shutil.ignore_patterns('__pycache__'))
    (repo/'hypothesis.py').write_text('class Hypothesis: pass\n')
    (repo/'.gitignore').write_text('__pycache__/\n*.pyc\n')
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL).decode().strip()
    git('init','-q');git('config','user.name','DV2 offline fixture');git('config','user.email','fixture@example.invalid')
    git('add','.');git('-c','core.hooksPath=/dev/null','commit','-qm','fixed actual engine bytes')
    head=git('rev-parse','HEAD');git('update-ref','refs/remotes/origin/main',head)
    names=git('ls-files','--',*series.ENGINE_DIRS,'hypothesis.py').splitlines()
    now=ms(trial['record']['started_at'])
    # No fabricated completed run: this minimal trial envelope reaches the real
    # rematerialization boundary and is rejected there before any result exists.
    run=dict(mode='trial',started_at=now,ended_at=now,algorithm_files={n:digest((repo/n).read_bytes()) for n in names},
        run_config=dict(mode='trial',trial_id='t1',code_commit=head,engine_commit=head,algorithm={'path':'hypothesis.py','class':'Hypothesis'}))
    run_path=tmp_path/'attempt.json';run_path.write_bytes(canonical(run))
    with pytest.raises(series.SeriesError,match='U4 重新物化失敗'):
        series.submit(case.book.out,'t1',case.u1,run_path,repo=repo)
    assert case.book.trial_record('t1')==trial
    assert not (case.book.out/'u6_artifacts').exists()


def test_history_clock_uses_original_first_bar_before_positive_listing_box(tmp_path,monkeypatch):
    case=VerifiedCase(tmp_path,monkeypatch,quantities=['0','0']+['1']*38)
    result=mod.materialize(**case.args)
    assert result['first_bar']['XUSDT']==DV_T
    regimes=dv_read(case.args['out'],'verification/listing_regimes.jsonl')
    first=next(r for r in regimes if r['symbol']=='XUSDT')
    assert first['observed_listing_at']==DV_T+2*DV_DAY
    decision=next(r for r in dv_read(case.args['out'],'verification/turnover_decisions.jsonl') if r['symbol']=='XUSDT')
    assert decision['decision_utc_day']==DV_T+13*DV_DAY and decision['history_sufficient'] is True


def test_bundle_scope_escape_rejected_without_decoding_or_copying_future_values(tmp_path,monkeypatch):
    case=VerifiedCase(tmp_path,monkeypatch,version=2,suffix=True)
    def append_outside(rows):
        other=copy.deepcopy(rows[-1]);other['timestamp']=case.end+DV_DAY
        other['original_value']='FUTURE_MUST_NOT_BE_DECODED';other['candidate_value']='NaN'
        rows.append(other)
    mutate_bundle(case,'corrections.jsonl',append_outside)
    with pytest.raises(mod.MaterializationError,match='SCOPE'):mod.materialize(**case.args)
    for p in (tmp_path/'result.blocked').rglob('*'):
        if p.is_file():assert b'FUTURE_MUST_NOT_BE_DECODED' not in p.read_bytes()


@pytest.mark.parametrize('version',[1,2])
def test_real_frozen_v1_sample_plan_preserved_in_both_policy_versions(tmp_path,monkeypatch,version):
    case=VerifiedCase(tmp_path,monkeypatch,version=version,sampling=True)
    result=mod.materialize(**case.args)
    assert (case.args['out']/'verification/sample_plan.json').read_bytes()==(tmp_path/'plan/sample_plan.json').read_bytes()
    report=dv_read(case.args['out'],'verification/verification.json');plan=dv_read(tmp_path/'plan','sample_plan.json')
    assert report['sample_plan_sha256']==result['files']['verification/sample_plan.json']['sha256']
    assert (plan['policy_sha256']==case.policy_sha) is (version==1)


@pytest.mark.parametrize('mutation',['report_sha','unknown_key','foreign_policy','scope','rank'])
def test_sample_plan_identity_and_schema_rejected(tmp_path,monkeypatch,mutation):
    case=VerifiedCase(tmp_path,monkeypatch,version=2,sampling=True)
    if mutation=='report_sha':mutate_bundle(case,'verification.json',lambda r:r.update(sample_plan_sha256='a'*64))
    else:
        def change(p):
            if mutation=='unknown_key':p['extra']='not permitted'
            elif mutation=='foreign_policy':p['policy_sha256']='b'*64
            elif mutation=='scope':p['readable']['end']+=DV_DAY
            else:p['strata'][0]['draws'][0]['rank']=2
        mutate_bundle(case,'sample_plan.json',change)
        # Bind the new bytes as a negative consumer test, not an altered producer.
        mutate_bundle(case,'verification.json',lambda r:r.update(sample_plan_sha256=digest((case.bundle/'sample_plan.json').read_bytes())))
    with pytest.raises(mod.MaterializationError,match='SAMPLE'):mod.materialize(**case.args)
    assert dv_read(tmp_path/'result.blocked','verification.json')['status']=='BLOCKED'
