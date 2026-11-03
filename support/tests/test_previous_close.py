"""Same-contract previous-session comparison, including rollover and slow I/O."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timedelta
from types import SimpleNamespace
import threading
import time

import pytest

from ckps.models import Quote
from ckps.rules.p2.market import VN_TZ
from ckps.services.previous_close import quote_key,read_previous_close,PreviousCloseWorker
from ckps.dashboard.mayin.quote_header import quote_header


NOW=datetime(2026,11,3,10,0,tzinfo=VN_TZ)
SYMBOL='41I1GB000'


@pytest.fixture(autouse=True)
def clock(monkeypatch):monkeypatch.setattr('time.time',lambda:NOW.timestamp())


def trade(day='2026-11-02',**values):
    return {'symbol':SYMBOL,'boardId':'G1','matchPrice':1800,'time':day+' 14:45:00.100',**values}


def test_contract_specific_get_is_daily_descending_and_skips_weekends_and_empty_holidays():
    calls=[]
    def request(method,path,*,params):
        calls.append((method,path,params))
        day=datetime.fromtimestamp(int(params['from']),VN_TZ).date().isoformat()
        assert int(params['to'])-int(params['from'])==86400
        assert params['order']=='desc' and params['limit']==1 and params['boardId']=='G1'
        return {'trades':[] if day=='2026-11-02' else [trade(day)]}
    ref=read_previous_close(SimpleNamespace(request=request),(SYMBOL,'2026-11-03'))
    assert len(calls)==2 and all(method=='GET' and path==f'/price/{SYMBOL}/trades' for method,path,_ in calls)
    assert ref['session']=='2026-10-30' and ref['quote_session']=='2026-11-03' and ref['price']==1800


@pytest.mark.parametrize('values',[{'symbol':'41I1GC000'},{'boardId':'T1'},{'matchPrice':0},
    {'matchPrice':None},{'matchPrice':True},{'matchPrice':float('nan')},
    {'time':'2026-11-03 00:00:00'},{'time':'2026-11-03 09:00:00'},{'time':None}])
def test_wrong_contract_board_day_or_missing_price_never_becomes_a_previous_close(values):
    client=SimpleNamespace(request=lambda *a,**kw:{'trades':[trade(**values)]})
    assert read_previous_close(client,(SYMBOL,'2026-11-03'))=={}


@pytest.mark.parametrize('price,tone,text',[(1818,'green','+18,0 (+1,00%)'),(1782,'red','-18,0 (-1,00%)'),(1800,'amber','+0,0 (+0,00%)')])
def test_header_color_points_percent_and_full_margin_hint_are_read_only(price,tone,text):
    ref=read_previous_close(SimpleNamespace(request=lambda *a,**kw:{'trades':[trade()]}),(SYMBOL,'2026-11-03'))
    view={'contract':SYMBOL,'quotes':{SYMBOL:asdict(Quote(SYMBOL,price,at=NOW.timestamp(),source='DNSE'))},
        'account':{'margin_per_contract':33_596_640},'previous_close':ref}
    before=deepcopy(view)
    value,color,margin,hint=quote_header(view,'REAL')
    assert (value,color,margin)==(text,tone,'KQ/HĐ 33,60tr')
    assert SYMBOL in hint and '33,596,640 đ' in hint and '02/11/2026' in hint and '1,800.0' in hint
    assert view==before
    assert quote_header(view,'PAPER')[2]=='~ KQ/HĐ 33,60tr'
    view['previous_close']['contract']='41I1GC000'
    assert quote_header(view,'REAL')[:2]==('—','neutral')


def test_cached_quote_compares_its_own_session_and_does_not_reuse_reference_across_a_new_tick_day():
    quote=asdict(Quote(SYMBOL,1818,at=(NOW-timedelta(days=1)).timestamp(),source='DNSE'))
    view={'contract':SYMBOL,'quotes':{},'market_cache':{'quote':quote},'previous_close':{
        'contract':SYMBOL,'quote_session':'2026-11-02','session':'2026-10-30','price':1800,'source':'DNSE'}}
    assert quote_header(view,'REAL')[0]=='+18,0 (+1,00%)'
    view['quotes'][SYMBOL]={**quote,'at':NOW.timestamp()}
    assert quote_header(view,'REAL')[:2]==('—','neutral')
    assert not view.get('market_ready')
    view['quotes']={};view['contract']='41I1GC000'
    value,_,_,hint=quote_header(view,'REAL')
    assert value=='—' and 'Mã giao dịch: 41I1GC000' in hint and 'Giá lưu thuộc mã: 41I1GB000' in hint


def test_worker_does_not_block_observe_and_discards_obsolete_contract_reply():
    entered,release,closed=threading.Event(),threading.Event(),threading.Event()
    calls=[]
    class Client:
        def request(self,method,path,**kwargs):
            calls.append(path)
            if SYMBOL in path:entered.set();assert release.wait(3)
            return {'trades':[trade(symbol='41I1GC000' if '41I1GC000' in path else SYMBOL)]}
        def close(self):closed.set()
    worker=PreviousCloseWorker(Client())
    quote=asdict(Quote(SYMBOL,1818,at=NOW.timestamp(),source='DNSE'))
    try:
        assert worker.observe(quote)=={} and entered.wait(2)
        newer={**quote,'symbol':'41I1GC000'}
        start=time.monotonic();assert worker.observe(newer)=={}
        assert time.monotonic()-start<.1
        release.set()
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            value=worker.observe(newer)
            if value:break
            time.sleep(.01)
        assert value['contract']=='41I1GC000'
        for _ in range(3):assert worker.observe(newer)==value
        assert len(calls)==2
        assert worker.observe({})=={}
    finally:release.set();worker.close()
    assert closed.is_set() and not worker.thread.is_alive()
