from copy import deepcopy
from dataclasses import asdict

from ckps.dashboard.mayin.preview_state import preview_state
from ckps.models import ExitSettings, Position, Quote


def test_status_requires_managed_position_bot_fresh_matching_quote_and_synced_book():
    position=Position.create('VN30F1M','LONG',1,2000,managed=True)
    rules=ExitSettings(sl_enabled=True,sl_distance=10)
    view={'armed':True,'healthy':True,'consistent':True,'contract':'VN30F1M',
          'quotes':{'VN30F1M':asdict(Quote('VN30F1M',2007))},'orders':[]}
    before=deepcopy(view)
    assert preview_state(view,10,position,rules)==(('BOT ON','green'),('QUẢN LÝ ON','green'),('GIÁ · MỚI','green'))
    assert view==before  # Presentation cannot change quotes, permissions or orders.
    view['quotes']['VN30F1M']['at']=0
    assert preview_state(view,10,position,rules)[1:]==(('QL · CHỜ DỮ LIỆU','red'),('GIÁ · CŨ','amber'))
    view=deepcopy(before);view['consistent']=False
    assert preview_state(view,10,position,rules)[1:]==(('QL · CHỜ DỮ LIỆU','red'),('SỔ · ĐỐI SOÁT','red'))
    view=deepcopy(before);view['quotes']['VN30F1M']['symbol']='VN30F2611'
    assert preview_state(view,10,position,rules)[1][1]=='red'
    view=deepcopy(before);view['armed']=False
    assert preview_state(view,10,position,rules)[1]==('QL · TẠM DỪNG','amber')
    position.managed=False
    assert preview_state(before,10,position,rules)[1]==('QL · CHƯA NHẬN','amber')


def test_status_distinguishes_pending_close_alert_only_disabled_rules_and_demo():
    position=Position.create('VN30F1M','SHORT',2,2000,managed=True)
    view={'armed':True,'healthy':True,'consistent':True,'contract':'VN30F1M',
          'quotes':{'VN30F1M':asdict(Quote('VN30F1M',1990))},'orders':[]}
    alert=ExitSettings(dynamic_enabled=True,dynamic_policy='ALERT')
    assert preview_state(view,10,position,alert)[1]==('QL · CHỈ BÁO','blue')
    assert preview_state(view,10,position,ExitSettings())[1]==('QL · RULE OFF','amber')
    view['orders']=[{'position_id':position.id,'action':'CLOSE','status':'UNKNOWN'}]
    assert preview_state(view,10,position,alert)[1]==('QL · CHỜ KHỚP','amber')
    assert preview_state(view,10,position,alert,changing_book=True)[1:]==(('QL · CHỜ DỮ LIỆU','red'),('SỔ · ĐANG ĐỔI','amber'))
    assert preview_state(view,10,demo=True)[1:]==(('VÉ · CHỈ XEM','blue'),('GIÁ MẪU','blue'))
