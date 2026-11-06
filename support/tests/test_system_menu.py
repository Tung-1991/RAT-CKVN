"""Menu dispatch and source updates run offline in disposable projects."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import zipfile

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


def test_menu_has_exactly_the_requested_five_actions():
    text=(ROOT/'START_SYSTEM.bat').read_text()
    assert 'choice /c 12345 ' in text and 'if errorlevel 5 exit /b 0' in text
    assert all(label in text for label in ('1. Mo app','2. Blackbox','3. Ra soat / cai moi truong','4. Update','5. Thoat'))
    assert ':prepare' not in text and ':check' not in text
    assert '-Action Blackbox' in text and '-Action Update' in text
    # The old BAT exits before its source can be replaced by the updater.
    assert ':update\nstart ' in text and text.rstrip().endswith('exit /b 0')


@pytest.mark.parametrize('action,module',[('Start','ckps'),('Blackbox','ckps.signal_app')])
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


def update_zip(tmp_path,files,extra=''):
    project=tmp_path/'installed';project.mkdir()
    for name,value in {'START_SYSTEM.bat':'old-menu','ckps/__main__.py':'old-app','requirements.txt':'old-deps',
                       'runtime/ckps/settings.json':'private-settings','.venv/keep':'private-env','.env':'private-secret'}.items():
        path=project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
    archive=tmp_path/'download.zip'
    with zipfile.ZipFile(archive,'w') as stream:
        for name,value in files.items():stream.writestr('RAT-CKVN-main/'+name,value)
    result=powershell(tmp_path,f"""
. {ps_quote(ROOT/'support/update.ps1')}
function Invoke-WebRequest {{ param($OutFile); Copy-Item -LiteralPath {ps_quote(archive)} -Destination $OutFile }}
{extra}
Update-CkpsSource -ProjectRoot {ps_quote(project)}
""")
    for name,value in {'runtime/ckps/settings.json':'private-settings','.venv/keep':'private-env','.env':'private-secret'}.items():
        assert (project/name).read_text()==value
    return project,result


SOURCE={'START_SYSTEM.bat':'new-menu','ckps/__main__.py':'new-app','requirements.txt':'new-deps'}


def test_zip_install_updates_source_and_backs_up_without_git_or_environment_changes(tmp_path):
    project,result=update_zip(tmp_path,SOURCE)
    assert result.returncode==0,result.stdout+result.stderr
    assert (project/'ckps/__main__.py').read_text()=='new-app'
    backups=list(project.glob('.artifacts/update-*/backup/START_SYSTEM.bat'))
    assert len(backups)==1 and backups[0].read_text()=='old-menu'


@pytest.mark.parametrize('path',['ckps/../../outside.py','runtime/ckps/settings.json','.env'])
def test_zip_rejects_paths_outside_source_before_replacing_anything(tmp_path,path):
    project,result=update_zip(tmp_path,{**SOURCE,path:'forbidden'})
    assert result.returncode!=0 and (project/'START_SYSTEM.bat').read_text()=='old-menu'
    assert not (tmp_path/'outside.py').exists()


def test_zip_copy_failure_restores_overwritten_source_and_removes_only_new_files(tmp_path):
    extra=r"""
$script:failed=$false
function Copy-Item {
    param($LiteralPath,$Destination,[switch]$Force)
    if (-not $script:failed -and $LiteralPath -like '*\source\START_SYSTEM.bat') {
        $script:failed=$true
        throw 'Simulated copy failure'
    }
    Microsoft.PowerShell.Management\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -Force:$Force
}
"""
    project,result=update_zip(tmp_path,{'ckps/new.py':'new',**SOURCE},extra)
    assert result.returncode!=0 and 'Simulated copy failure' in result.stderr
    assert (project/'START_SYSTEM.bat').read_text()=='old-menu'
    assert not (project/'ckps/new.py').exists()


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


@pytest.mark.parametrize('folder',['accounts/LOCAL/paper','blackbox'])
def test_update_refuses_an_open_book_or_blackbox_before_downloading_or_mutating(tmp_path,folder):
    path=tmp_path/'runtime/ckps'/folder/'session.lock';path.parent.mkdir(parents=True)
    with path.open('w+b') as stream:
        stream.write(b'0');stream.flush()
        result=powershell(tmp_path,f". {ps_quote(ROOT/'support/update.ps1')}\nUpdate-CkpsSource -ProjectRoot {ps_quote(tmp_path)}")
    assert result.returncode!=0 and 'Dong app va Blackbox' in result.stderr
    assert not (tmp_path/'.artifacts').exists()
