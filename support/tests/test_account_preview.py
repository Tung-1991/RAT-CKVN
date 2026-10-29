"""The account preview reads only; package fees must not become all-in fees."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
import queue
import threading
import time

import pytest

from ckps.connections.dnse.discovery import AccountReader
from ckps.connections.dnse.fees import package_fees
from ckps.connections.dnse.protocol import BrokerError
from ckps.models import ExitSettings, Quote, Settings


PACKAGE={'id':2279,'name':'Gói thử','initialRate':.2,'tradingFee':{
    'schemaType':'FIXED','fixedTradingFee':2000,'fixedDailyCloseTradingFee':1500}}


def account_data(accounts=None, packages=None):
    return {'/accounts':{'accounts':accounts if accounts is not None else [
        {'id':'123','derivativeAccount':True,'derivative':{'status':'ACTIVE'}},
        {'id':'456','derivativeAccount':True,'derivative':{'status':'INACTIVE'}},
        {'id':'789','derivativeAccount':False,'derivative':{'status':'ACTIVE'}}]},
        '/accounts/123/loan-packages':{'loanPackages':packages if packages is not None else [deepcopy(PACKAGE)]},
        '/accounts/123/balances':{'stock':{'totalCash':999_000_000},'derivative':{'remainSecure':70_000_000,'usedSecure':30_000_000}}}


def reader_with_data(monkeypatch, data):
    reader=AccountReader('offline-key','offline-secret')
    calls=[]
    class Response:
        ok=True;status_code=200;headers={}
        def __init__(self,value):self.value=value
        def json(self):return deepcopy(self.value)
    def request(method,url,**kwargs):
        path=url.removeprefix('https://openapi.dnse.com.vn')
        assert method=='GET' and 'trading-token' not in kwargs['headers']
        calls.append((path,kwargs))
        return Response(data[path])
    monkeypatch.setattr(reader.session,'request',request)
    return reader,calls


def test_profile_auto_selects_unique_active_derivative_account_and_exact_package(monkeypatch):
    reader,calls=reader_with_data(monkeypatch,account_data())
    try:
        profile=reader.profile()
        assert profile['accounts']==[{'id':'123'}]
        assert profile['account_no']=='123' and profile['loan_package_id']=='2279'
        assert profile['balance']['collateral_total']==100_000_000
        assert profile['balance']['remaining_margin']==70_000_000
        assert profile['fees']['open']==2000 and profile['fees']['close']==2000
        assert all('marketType' not in kwargs['params'] or kwargs['params']['marketType']=='DERIVATIVE'
            for _,kwargs in calls if kwargs['params'])
        assert 'offline-secret' not in json.dumps(profile)
        assert len(calls)==3
    finally:reader.close()


def test_multiple_accounts_packages_require_choice_and_never_fall_back_to_first(monkeypatch):
    data=account_data(accounts=[{'id':account,'derivativeAccount':True,'derivative':{'status':'ACTIVE'}} for account in ('123','124')],
        packages=[PACKAGE,{**PACKAGE,'id':2280}])
    reader,calls=reader_with_data(monkeypatch,data)
    try:
        assert reader.profile()['account_no']=='' and len(calls)==1
        assert reader.profile('123')['loan_package_id']==''
        assert reader.profile('123','2280')['loan_package_id']=='2280'
        for account,package in (('999',''),('123','999')):
            with pytest.raises(BrokerError):reader.profile(account,package)
    finally:reader.close()


def test_account_reader_cannot_get_orders_positions_or_request_otp():
    reader=AccountReader('offline-key','offline-secret')
    try:
        for method,path in (('POST','/accounts'),('POST','/registration/send-email-otp'),
                ('GET','/accounts/123/orders'),('GET','/accounts/123/positions'),('GET','/positions/123')):
            with pytest.raises(BrokerError,match='chỉ đọc'):reader.request(method,path)
    finally:reader.close()


@pytest.mark.parametrize('response',[{'marketType':'STOCK','loanPackages':[PACKAGE]},
    {'marketType':'DERIVATIVE','loanPackages':[PACKAGE,PACKAGE]}])
def test_preview_rejects_stock_packages_or_ambiguous_package_ids(monkeypatch,response):
    data=account_data()
    data['/accounts/123/loan-packages']=response
    reader,_=reader_with_data(monkeypatch,data)
    try:
        with pytest.raises(BrokerError):reader.profile()
    finally:reader.close()


@pytest.mark.parametrize('value',[0,1500])
def test_zero_fixed_fee_is_known_but_missing_or_tiered_fee_is_not_zero(value):
    fees=package_fees({'tradingFee':{'schemaType':'FIXED','fixedTradingFee':value,'fixedDailyCloseTradingFee':2000}})
    assert fees['open']==value and fees['close']==2000
    for package in ({},{'brokerFirmBuyingFeeRate':.0003},
            {'tradingFee':{'schemaType':'FIXED','fixedTradingFee':None}},
            {'tradingFee':{'schemaType':'PROGRESSIVE','progressTradingFee':[{'fromQuantity':1,'toQuantity':2000,'fee':1500}]}}):
        assert package_fees(package)['open'] is None


def test_read_worker_replaces_obsolete_response_and_never_publishes_credentials():
    from ckps.services.connection_probe import ConnectionProbe
    entered,released=threading.Event(),threading.Event()
    calls=[]
    class Reader:
        def __init__(self,key,secret):calls.append((key,secret))
        def profile(self,account,package):
            if account=='old':entered.set();released.wait(3)
            return {'account_no':account,'loan_package_id':package}
        def close(self):pass
    probe=ConnectionProbe(Reader)
    try:
        probe.request({'key':'old-key','secret':'old-secret'},'old','1')
        assert entered.wait(2)
        revision=probe.request({'key':'new-key','secret':'new-secret'},'new','2')
        released.set()
        seen,profile=probe.events.get(timeout=3)
        assert seen==revision and profile=={'account_no':'new','loan_package_id':'2'}
        assert 'secret' not in json.dumps(profile)
        with pytest.raises(queue.Empty):probe.events.get_nowait()
    finally:released.set();probe.close();probe.thread.join(3)
    assert not probe.thread.is_alive()


def test_real_capacity_uses_api_fee_for_sl_estimate_without_limiting_broker_power(system):
    from ckps.trading.portfolio import capacity
    engine,broker,store=system
    settings=replace(engine.settings,mode='REAL',estimated_fee_per_contract=900_000)
    rules=ExitSettings(distance_unit='POINTS', sl_enabled=True,sl_distance=10)
    snapshot=replace(engine.latest,package_fees=package_fees(PACKAGE))
    result=capacity(settings,snapshot,[],[],'LONG',2000,rules)
    assert result.risk_per_contract==1_004_000 and result.maximum==2
    snapshot.package_fees=package_fees({})
    result=capacity(settings,snapshot,[],[],'SHORT',2000,rules)
    assert result.maximum==2 and result.risk_per_contract is None


def test_paper_uses_api_fees_without_mutating_settings_or_real_wallet(system):
    from ckps.connections.dnse.paper import PaperBroker
    from ckps.trading.execution import Engine
    engine,_,store=system
    class Market:
        feed=None
        def snapshot(self,symbols):return {'contract':'41I1GB000','quotes':{'41I1GB000':Quote('41I1GB000',2000,source='DNSE')},
            'bars':[],'account_profile':{'fees':package_fees(PACKAGE),'balance':{'collateral_total':999_000_000}}}
    broker=PaperBroker(store,engine.settings,market=Market())
    live=Engine(store,broker,engine.settings)
    live.open_manual('LONG',1,'MOK');live.poll()
    live.close_position(store.positions()[0].id,1)
    assert store.get('paper','account')['cash']==100_000_000-4000
    assert engine.settings.estimated_fee_per_contract==0
    assert live.latest.collateral_total != 999_000_000
    assert sum(row.fees for row in store.positions(closed=True))==4000


def test_paper_reconnect_reads_another_account_fee_without_switching_simulated_ledger(monkeypatch):
    from ckps.services.runtime import Runtime
    settings=Settings()
    first=Runtime(settings,offline=True)
    try:
        first.command('paper_capital',200_000_000)
        first.command('open_manual','LONG',1,'MOK')
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and not first.store.positions():time.sleep(.01)
        assert len(first.store.positions())==1
        original_path=first.store.path
    finally:first.close();first.thread.join(3)
    seen=[]
    class Reader:
        def __init__(self,*args):pass
    class Market:
        feed=None
        def __init__(self,*args,**kwargs):seen.append(kwargs)
        def snapshot(self,symbols):return {'contract':'VN30F1M','quotes':{'VN30F1M':Quote('VN30F1M',2000,source='DNSE')},
            'bars':[],'account_profile':{'fees':package_fees(PACKAGE),'balance':{'collateral_total':999_000_000}}}
        def close(self):pass
    monkeypatch.setattr('ckps.connections.dnse.discovery.AccountReader',Reader)
    monkeypatch.setattr('ckps.services.runtime.ReadOnlyHistory',Reader)
    monkeypatch.setattr('ckps.services.runtime.PaperMarket',Market)
    second=Runtime(settings,{'key':'offline-key','secret':'offline-secret'},market_profile={'account_no':'456','loan_package_id':'2279'})
    try:
        deadline=time.monotonic()+3
        while second.engine.latest is None and time.monotonic()<deadline:time.sleep(.01)
        assert second.engine.latest.paper_capital==200_000_000
        assert second.engine.latest.collateral_total==200_000_000
        assert len(second.store.positions())==1 and second.store.path==original_path
        assert seen[0]['account']=='456' and seen[0]['package']=='2279'
        assert not second.engine.enabled.is_set()
    finally:second.close();second.thread.join(3)
    assert not second.thread.is_alive()
