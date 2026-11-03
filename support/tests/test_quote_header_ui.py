"""Native layout and delayed margin hint, isolated from the running app."""
import inspect
from pathlib import Path
import subprocess
import sys

import pytest


def _quote_header_scenario(scale):
    from dataclasses import asdict
    from datetime import datetime,timedelta
    from time import monotonic,time
    from types import SimpleNamespace
    import socket
    import requests
    import customtkinter as ctk
    from tkinter import Misc
    from ckps.dashboard.window import App
    from ckps.dashboard.mayin.ui_compat import NativeFontMetrics
    from ckps.models import Settings,Quote
    from ckps.rules.p2.market import VN_TZ
    def forbidden(*a,**kw):raise AssertionError('No DNSE or Telegram in UI checks')
    requests.Session.request=socket.socket.connect=forbidden
    ctk.deactivate_automatic_dpi_awareness()
    ctk.set_widget_scaling(scale);ctk.set_window_scaling(scale)
    app=App(settings=Settings(),start_runtime=False)
    app.geometry('1080x700')
    errors=[];app.report_callback_exception=lambda *a:errors.append(a)
    def settle(ms=100):
        end=monotonic()+ms/1000
        while monotonic()<end:
            timer=app.after(max(1,round((end-monotonic())*1000)),app.quit)
            Misc.mainloop(app);app.after_cancel(timer)
        app.update()
    try:
        now=time();today=datetime.fromtimestamp(now,VN_TZ).date();previous=today-timedelta(days=1)
        app.view={'contract':'41I1GB000','mode':'PAPER','healthy':True,'consistent':True,
            'quotes':{'41I1GB000':asdict(Quote('41I1GB000',1818,at=now,source='DNSE'))},
            'account':{'margin_per_contract':33596640,'qmax_long':2,'qmax_short':2},
            'previous_close':{'contract':'41I1GB000','quote_session':today.isoformat(),
                'session':previous.isoformat(),'price':1800,'source':'DNSE'}}
        app.render();settle(400)
        assert not hasattr(app,'lbl_quote_symbol')
        assert app.lbl_change.cget('text')=='+18,0 (+1,00%)'
        assert app.lbl_margin.cget('text')=='~ KQ/HĐ 33,60tr'
        for label in (app.lbl_change,app.lbl_margin):
            measured=NativeFontMetrics(label,label._label.cget('font')).measure(label.cget('text'))
            assert measured<=label.winfo_width(),(label.cget('text'),measured,label.winfo_width())
            assert label.winfo_rootx()+label.winfo_width()<=app.left.winfo_rootx()+app.left.winfo_width()
        hint=app.lbl_margin._hover_hint
        assert '41I1GB000' in hint.text() and '33,596,640 đ' in hint.text()
        assert previous.strftime('%d/%m/%Y') in hint.text()
        hint._enter(SimpleNamespace(x_root=app.lbl_margin.winfo_rootx(),y_root=app.lbl_margin.winfo_rooty()))
        settle(180);assert hint.popup is None
        settle(400);assert hint.popup is not None and hint.popup.winfo_manager()=='place'
        # Leave without depending on where the user's real pointer happens to be.
        import ckps.dashboard.mayin.hint_box as hints
        hints.contains_pointer=lambda _:False
        hint._leave();settle(160);assert hint.popup is None
        app.view['quotes']['41I1GB000']['last']=1782;app.render()
        assert app.lbl_change.cget('text')=='-18,0 (-1,00%)'
        app.view['quotes']['41I1GB000']['last']=1800;app.render()
        assert app.lbl_change.cget('text')=='+0,0 (+0,00%)'
        assert not errors,errors
    finally:app.close()


@pytest.mark.parametrize('scale',[1.,1.25,1.5,2.])
def test_quote_header_fits_and_margin_hint_requires_half_a_second(scale):
    result=subprocess.run([sys.executable,'-X','utf8','-c',
        inspect.getsource(_quote_header_scenario)+f'\n_quote_header_scenario({scale!r})'],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
