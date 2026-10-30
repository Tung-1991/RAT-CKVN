"""Account mode changes stay inline, GET-only and bound to the latest intent."""
from dataclasses import replace
import queue
from types import SimpleNamespace

import pytest

from ckps.dashboard.mode_switch import ModeSwitchMixin
from ckps.models import Settings


class Probe:
    def __init__(self):
        self.events=queue.Queue();self.closed=False;self.requested=None
    def request(self,credentials,account,package):
        self.requested=(credentials,account,package)
        return 1
    def close(self):self.closed=True


class Harness(ModeSwitchMixin):
    def __init__(self):
        self.settings=Settings(account_no='123',loan_package_id='2278')
        self.credentials={'key':'offline-key','secret':'offline-secret'}
        self.closing=False;self.order_busy=False;self.switch_pending=None;self.mode_requested=None
        self.bot_requested=True;self.preview_only=False;self.view={'armed':True}
        self.chosen=[];self.messages=[];self.started=[]
        self.mode_choice=SimpleNamespace(set=self.chosen.append)
        self.old=SimpleNamespace(closed=False,armed=True)
        def close():self.old.closed=True;self.old.armed=False
        self.runtime=SimpleNamespace(close=close)
    def clear_confirmation(self):pass
    def render(self):pass
    def report(self,text,**kwargs):self.messages.append(text)
    def connection(self,*a,**kw):pytest.fail('A mode click must never open settings.')
    def _start_runtime(self,*args):self.started.append(args)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr('ckps.dashboard.mode_switch.ConnectionProbe',Probe)
    return Harness()


def test_missing_credentials_show_inline_message_and_keep_current_book(app):
    app.credentials={}
    app._mode_selected('REAL')
    assert app.settings.mode=='PAPER' and app.mode_requested is None
    assert app.chosen[-1]=='PAPER' and 'KẾT NỐI' in app.messages[-1]
    assert not app.old.closed and not app.started


def test_real_is_verified_before_old_book_closes_and_bot_is_off(app):
    app._mode_selected('REAL')
    probe=app._mode_probe
    assert probe.requested[1:]==('123','2278')
    assert not app.old.closed and not app.started
    probe.events.put((1,dict(account_no='123',loan_package_id='2278')))
    app._drain_mode_probe()
    settings,credentials=app.switch_pending
    assert settings.mode=='REAL' and settings.account_no=='123' and settings.loan_package_id=='2278'
    assert credentials==app.credentials and not app.bot_requested
    assert app.old.closed and not app.old.armed and not app.started
    assert probe.closed


@pytest.mark.parametrize('profile',[{'error':'API offline'},{'account_no':'','loan_package_id':''},
    {'account_no':'123','loan_package_id':''}])
def test_failed_or_ambiguous_discovery_keeps_current_book_and_permissions(app,profile):
    app._mode_selected('REAL')
    app._mode_probe.events.put((1,profile))
    app._drain_mode_probe()
    assert app.settings.mode=='PAPER' and app.mode_requested is None
    assert not app.old.closed and app.old.armed and not app.started
    assert app.switch_pending is None and app.messages


def test_selecting_paper_cancels_pending_real_and_ignores_its_reply(app):
    app._mode_selected('REAL')
    probe=app._mode_probe
    app._mode_selected('PAPER')
    probe.events.put((1,dict(account_no='123',loan_package_id='2278')))
    app._drain_mode_probe()
    assert probe.closed and app.mode_requested is None and app.switch_pending is None
    assert not app.old.closed


def test_changed_credentials_cannot_apply_an_old_account_result(app):
    app._mode_selected('REAL')
    probe=app._mode_probe
    app.credentials={'key':'another-key','secret':'another-secret'}
    probe.events.put((1,dict(account_no='123',loan_package_id='2278')))
    app._drain_mode_probe()
    assert not app.old.closed and app.switch_pending is None and probe.closed


def test_paper_switch_does_not_read_real_account_or_open_settings(app):
    app.settings=replace(app.settings,mode='REAL')
    app._mode_selected('PAPER')
    assert app.switch_pending[0].mode=='PAPER' and app.old.closed
    assert getattr(app,'_mode_probe',None) is None and not app.bot_requested


def test_busy_order_blocks_book_switch(app):
    app.order_busy=True
    app._mode_selected('REAL')
    assert not app.old.closed and app.switch_pending is None and app.mode_requested is None


def test_paper_button_can_restart_a_book_after_a_failed_switch(app):
    app.runtime=None
    app._mode_selected('PAPER')
    assert len(app.started)==1 and app.started[0][0].mode=='PAPER'
    assert app.switch_pending is None and not app.bot_requested


def test_queued_order_operation_is_not_discarded_by_a_book_switch(app):
    app.settings=replace(app.settings,mode='REAL')
    app.runtime.commands=queue.Queue()
    app.runtime.commands.put(('cancel','order-one'))
    app._mode_selected('PAPER')
    assert not app.old.closed and app.old.armed
    assert app.switch_pending is None and app.chosen[-1]=='REAL'
