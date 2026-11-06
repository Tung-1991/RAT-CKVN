"""Menu dispatch and source updates run offline in disposable projects."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('headless',[False,True])
def test_backend_entrypoint_opens_blackbox_or_private_pipe_without_autostart(monkeypatch,headless):
    from ckps import signal_app
    import ckps.dashboard.signal_app as panel
    import ckps.services.signal_process as pipe
    import customtkinter as ctk
    calls=[]
    class Window:
        def __init__(self):calls.append('panel')
        def mainloop(self):calls.append('loop')
    monkeypatch.setattr(panel,'SignalApp',Window)
    monkeypatch.setattr(ctk,'set_appearance_mode',lambda *args:None)
    monkeypatch.setattr(ctk,'set_default_color_theme',lambda *args:None)
    monkeypatch.setattr(pipe,'serve',lambda *args:calls.append('pipe') or 0)
    monkeypatch.setattr(sys,'argv',['backend.py']+(['--headless'] if headless else []))
    assert signal_app.main()==0
    assert calls==(['pipe'] if headless else ['panel','loop'])


def ps_quote(value):
    return "'"+str(value).replace("'","''")+"'"


def powershell(tmp_path,body):
    script=tmp_path/'probe.ps1'
    guards="function Invoke-WebRequest { throw 'Network forbidden in offline tests' }\nfunction Start-Process { throw 'Process launch forbidden in offline tests' }\n"
    script.write_text("$ErrorActionPreference='Stop'\n"+guards+body,encoding='utf-8-sig')
    return subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],
        capture_output=True,text=True,timeout=30)


def test_menu_has_git_update_and_saved_preset_as_separate_actions():
    text=(ROOT/'START_SYSTEM.bat').read_text()
    assert 'choice /c 123456 ' in text and 'if errorlevel 6 exit /b 0' in text
    assert all(label in text for label in ('1. Mo app','2. Blackbox','3. Ra soat / cai moi truong','4. Update','5. Nap preset','6. Thoat'))
    assert ':prepare' not in text and ':check' not in text
    assert '-Action Blackbox' in text and '-Action Update' in text and '-Action Preset' in text
    # CMD caches this block before Git replaces the BAT, then reloads the new
    # menu in the same console instead of resuming at obsolete byte offsets.
    update=text.split(':update\n',1)[1]
    assert update.startswith('(\n') and 'start ' not in update.lower()
    assert 'pause' in update and '"%~f0"' in update
    assert 'Read-Host' not in (ROOT/'support/launcher.ps1').read_text()


@pytest.mark.parametrize('padding',[0,500])
def test_same_console_update_reloads_the_bat_even_when_git_replaces_it(tmp_path,padding):
    batch=tmp_path/'START_SYSTEM.bat'
    replacement='@echo off\necho RELOADED_MENU\nexit /b 0\n'+'rem padding\n'*padding
    rewriter=tmp_path/'rewrite.py'
    rewriter.write_text(f'from pathlib import Path\nPath({str(batch)!r}).write_text({replacement!r})\n')
    fake=tmp_path/'update.cmd'
    fake.write_text(f'@"{sys.executable}" "{rewriter}"\n@exit /b 0\n')
    text=(ROOT/'START_SYSTEM.bat').read_text()
    text=text.replace('choice /c 123456 /n /m "Chon [1/2/3/4/5/6]: "','cmd.exe /d /c exit 4')
    command='powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\\launcher.ps1" -Action Update'
    assert command in text
    text=text.replace(command,f'call "{fake}"').replace('    pause\n','    rem automated test\n')
    batch.write_text(text)
    result=subprocess.run(['cmd.exe','/d','/c',str(batch)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0 and 'RELOADED_MENU' in result.stdout,result.stdout+result.stderr
    assert batch.read_text()==replacement


@pytest.mark.parametrize('action,module',[('Start','ckps'),('Blackbox','ckps.signal_app'),('Preset','ckps.preset_app')])
def test_open_actions_launch_only_and_never_install(tmp_path,action,module):
    support=tmp_path/'support';support.mkdir()
    shutil.copyfile(ROOT/'support/system.ps1',support/'system.ps1')
    (support/'bootstrap.ps1').write_text("function Test-CkpsPython { return $true }\nfunction Initialize-CkpsEnvironment { throw 'Unexpected install' }\n")
    result=powershell(tmp_path,f"""
. {ps_quote(support/'system.ps1')}
function Start-Process {{
    param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle)
    if (($ArgumentList -join ' ') -ne '-X utf8 -m {module}') {{ throw 'Wrong module' }}
    if ($WindowStyle -ne 'Hidden' -or $WorkingDirectory -ne {ps_quote(tmp_path)}) {{ throw 'Wrong launch settings' }}
    Write-Host 'LAUNCH_ONLY'
}}
Invoke-CkpsAction -ProjectRoot {ps_quote(tmp_path)} -Action {action}
""")
    assert result.returncode==0,result.stdout+result.stderr
    assert 'LAUNCH_ONLY' in result.stdout


def test_missing_environment_points_to_menu_three_without_installing(tmp_path):
    support=tmp_path/'support';support.mkdir()
    shutil.copyfile(ROOT/'support/system.ps1',support/'system.ps1')
    (support/'bootstrap.ps1').write_text("function Test-CkpsPython { return $false }\nfunction Initialize-CkpsEnvironment { throw 'Unexpected install' }\n")
    result=powershell(tmp_path,f". {ps_quote(support/'system.ps1')}\nInvoke-CkpsAction -ProjectRoot {ps_quote(tmp_path)} -Action Start")
    assert result.returncode!=0 and 'muc 3' in result.stderr and 'Unexpected install' not in result.stderr


def git(path,*args):
    return subprocess.run(['git','-C',str(path),'-c','commit.gpgsign=false',*args],
        check=True,capture_output=True,text=True).stdout.strip()


@pytest.mark.parametrize('state',['clean','dirty','diverged'])
def test_git_updates_only_by_fast_forward_without_overwriting_local_work(tmp_path,monkeypatch,state):
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM','1');monkeypatch.setenv('GIT_CONFIG_GLOBAL',os.devnull)
    monkeypatch.setenv('GIT_AUTHOR_NAME','Offline');monkeypatch.setenv('GIT_AUTHOR_EMAIL','offline@example.invalid')
    monkeypatch.setenv('GIT_COMMITTER_NAME','Offline');monkeypatch.setenv('GIT_COMMITTER_EMAIL','offline@example.invalid')
    origin=tmp_path/'origin';origin.mkdir();git(origin,'init','-b','main')
    (origin/'app.txt').write_text('one');git(origin,'add','.');git(origin,'commit','-m','one')
    installed=tmp_path/'installed';git(tmp_path,'clone',str(origin),str(installed))
    (installed/'private.txt').write_text('keep')
    if state=='dirty':(installed/'app.txt').write_text('local-edit')
    if state=='diverged':
        (installed/'app.txt').write_text('local-commit');git(installed,'add','app.txt');git(installed,'commit','-m','local')
    before=git(installed,'rev-parse','HEAD')
    (origin/'app.txt').write_text('two');git(origin,'add','.');git(origin,'commit','-m','two')
    result=powershell(tmp_path,f". {ps_quote(ROOT/'support/update.ps1')}\nUpdate-CkpsSource -ProjectRoot {ps_quote(installed)}")
    assert (installed/'private.txt').read_text()=='keep'
    if state=='clean':
        assert result.returncode==0,result.stdout+result.stderr
        assert (installed/'app.txt').read_text()=='two' and git(installed,'rev-parse','HEAD')==git(origin,'rev-parse','HEAD')
    else:
        assert result.returncode!=0 and git(installed,'rev-parse','HEAD')==before
        assert (installed/'app.txt').read_text()==('local-edit' if state=='dirty' else 'local-commit')


def test_update_is_only_git_pull_without_install_download_or_preset(tmp_path):
    source=(ROOT/'support/update.ps1').read_text()
    assert 'pull --ff-only origin main' in source
    for forbidden in ('Invoke-WebRequest','Initialize-CkpsEnvironment','pip','pytest','session.lock','preset'):
        assert forbidden not in source.split('function Update-CkpsSource',1)[1]
