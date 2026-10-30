"""Read-only balance display and complete broker order pagination, without OTP."""
import queue
from types import SimpleNamespace

import pytest

from ckps.connections.dnse.client import DNSEBroker
from ckps.connections.dnse.order_book import intraday_orders
from ckps.connections.dnse.protocol import BrokerError
from ckps.models import Quote, Settings, Snapshot
from ckps.services.runtime import Runtime
from ckps.trading.execution import Engine


def test_read_orders_uses_explicit_category_and_zero_based_pages_without_trading_token():
    calls=[]
    def request(method,path,**kwargs):
        assert method=='GET' and path=='/accounts/123/orders' and not kwargs.get('trading')
        params=kwargs['params'];calls.append(params)
        assert params==dict(marketType='DERIVATIVE',orderCategory='NORMAL',pageIndex=len(calls)-1,pageSize=100)
        page=params['pageIndex']
        return {'orders':[{'id':str(i)} for i in range(page*100,min(205,(page+1)*100))],
                'pageIndex':page,'totalRecords':205,'totalPages':3}
    result=intraday_orders(SimpleNamespace(account_no='123',request=request))
    assert len(result)==205 and len(calls)==3 and result[-1]['id']=='204'


@pytest.mark.parametrize('failure',['missing_page','duplicate','changed_total','wrong_page'])
def test_incomplete_or_unstable_order_pages_never_become_a_reconciled_book(failure):
    def request(method,path,**kwargs):
        page=kwargs['params']['pageIndex']
        rows=[{'id':str(i)} for i in range(page*100,(page+1)*100)]
        total=200
        if page:
            if failure=='missing_page':rows=[]
            if failure=='duplicate':rows[0]['id']='1'
            if failure=='changed_total':total=201
            if failure=='wrong_page':page=0
        return {'orders':rows,'totalRecords':total,'pageIndex':page}
    with pytest.raises(BrokerError):intraday_orders(SimpleNamespace(account_no='123',request=request))


@pytest.mark.parametrize('prior_snapshot',[False,True])
def test_balance_survives_an_order_read_failure_without_authorizing_capacity_or_otp(system,monkeypatch,prior_snapshot):
    _,_,store=system
    broker=DNSEBroker('key','secret','123','7')
    monkeypatch.setattr(broker,'resolve',lambda:'41I1GB000')
    def request(method,path,**kwargs):
        assert method=='GET' and not kwargs.get('trading')
        if path.endswith('/balances'):
            return {'derivative':{'remainSecure':70_000_000,'usedSecure':30_000_000},'stock':{'totalCash':5_000_000}}
        if path.endswith('/positions'):return {'positions':[]}
        raise BrokerError('DNSE HTTP 400 · GET /accounts/123/orders')
    monkeypatch.setattr(broker,'request',request)
    settings=Settings(mode='REAL',account_no='123',loan_package_id='7')
    engine=Engine(store,broker,settings)
    if prior_snapshot:
        engine.latest=Snapshot('41I1GB000',[],[],{'41I1GB000':Quote('41I1GB000',2000)},
            80_000_000,0,40_000_000,2,2)
    try:
        with pytest.raises(BrokerError):engine.poll()
        assert bool(engine.latest)==prior_snapshot and not engine.healthy and not broker.token
        runtime=Runtime.__new__(Runtime)
        runtime.settings=settings;runtime.engine=engine;runtime.store=store;runtime.events=queue.Queue()
        runtime.quote_cache=SimpleNamespace(value={},observe=lambda _:None)
        runtime._publish()
        kind,view=runtime.events.get_nowait()
        assert kind=='snapshot' and view['account']['collateral_total']==100_000_000
        assert view['account']['total_money']==5_000_000
        assert view['market_connection']['configured'] and not view['healthy']
        assert 'qmax_long' not in view['account'] and not view['trading_auth']['valid']
        assert not view['armed'] and not store.orders()
        # A later failed balance read clears the previous display rather than relabeling it fresh.
        monkeypatch.setattr(broker,'request',lambda *a,**k:(_ for _ in ()).throw(BrokerError('offline')))
        with pytest.raises(BrokerError):engine.poll()
        assert broker.account_view=={}
    finally:broker.close()
