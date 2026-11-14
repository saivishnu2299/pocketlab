"""ADB transport for stock TrimUI PocketLAB. No network/debug services are enabled."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid

REMOTE = '/mnt/SDCARD/Apps/PocketLab'
CONTROL = REMOTE + '/data/control'
INSTALL_LOCK = '/tmp/pocketlab-shell-install.lock'
quote = shlex.quote

class USBError(RuntimeError):
    pass

class AppLaunchError(USBError):
    """A complete upload was rejected or failed startup; retry after a source fix."""

class Brick:
    def __init__(self, serial=None, require_install=True, confirm_model=None):
        self.adb = shutil.which('adb')
        if not self.adb: raise USBError('adb is required on this computer.')
        listing=subprocess.run([self.adb,'devices'],capture_output=True,text=True,timeout=8,check=True)
        devices=[line.split()[0] for line in listing.stdout.splitlines()[1:] if len(line.split())>=2 and line.split()[1]=='device']
        if serial and serial not in devices: raise USBError('Selected USB device is not connected or authorized.')
        if not serial and len(devices)!=1: raise USBError(f'Expected one ADB device; found {len(devices)}. Connect the bottom USB-C port or select --serial.')
        self.serial=serial or devices[0]
        # Stock-device discovery must also work before PocketLAB is installed.
        arch=self.remote('uname -m').strip()
        if arch!='aarch64': raise USBError(f'Expected an ARM64 Brick; received {arch!r}.')
        self.remote("test -d /usr/trimui; grep -qs ' /mnt/SDCARD ' /proc/mounts; test -d /mnt/SDCARD/Apps; test -d /mnt/SDCARD/Roms; test -f /usr/trimui/lib/libSDL2-2.0.so.0")
        self.remote('\n'.join('test ! -L '+quote(REMOTE+suffix) for suffix in ('','/data','/apps','/assets','/data/updates')))
        try:
            config=json.loads(self.remote('cat '+quote(REMOTE+'/config.json')))
        except (USBError,ValueError): config=None
        self.installed = config is not None
        if config is not None and (not isinstance(config,dict) or config.get('package')!='org.pocketlab.shell'):
            raise USBError('PocketLAB package identity does not match.')
        if require_install and not self.installed:
            raise USBError('Install PocketLAB first: ./pocketlab install --usb --confirm-model TG4040')
        if not require_install and not self.installed and confirm_model != 'TG4040':
            raise USBError('First USB installation requires --confirm-model TG4040 after checking your device model, or use its SD card.')

    def adb_run(self,*args,timeout=40):
        try:
            p=subprocess.run([self.adb,'-s',self.serial,*map(str,args)],capture_output=True,timeout=timeout)
        except subprocess.TimeoutExpired as e: raise USBError('USB operation timed out; reconnect and retry.') from e
        output=p.stdout.decode('utf-8','replace').replace('\r','')
        if p.returncode: raise USBError((p.stderr.decode('utf-8','replace')+output).strip()[-1800:])
        return output

    def remote(self,script,timeout=30):
        # This stock adbd does not propagate remote shell exit codes. An explicit
        # sentinel is required; adb's exit 0 is NOT proof that a shell command worked.
        marker='__PL_RESULT_'+uuid.uuid4().hex+'__'
        wrapped='(\nset -e\n'+script+'\n)\npl_result=$?\nprintf "\\n'+marker+'%s\\n" "$pl_result"\n'
        command='sh -c '+quote(wrapped)
        if len(command.encode()) > 3000:
            # Stock adbd has a small command-length limit. Transfer longer scripts
            # as files; stdin would launch an interactive shell on this firmware.
            remote_script='/tmp/pocketlab-command-'+uuid.uuid4().hex+'.sh'
            with tempfile.TemporaryDirectory(prefix='pocketlab-command-') as tmp:
                local=Path(tmp)/'command.sh'
                local.write_text('trap '+quote('rm -f '+quote(remote_script))+' EXIT\n'+wrapped)
                self.adb_run('push',str(local),remote_script)
            output=self.adb_run('shell','sh '+quote(remote_script),timeout=timeout)
        else:
            output=self.adb_run('shell',command,timeout=timeout)
        match=re.search(r'\n'+re.escape(marker)+r'(\d+)\n?$',output)
        if not match: raise USBError('USB shell returned no completion marker; operation status is unknown.')
        body=output[:match.start()]
        if int(match.group(1)): raise USBError(body.strip()[-1800:] or 'Remote command failed.')
        return body

    def status(self,required=True):
        try:
            state=json.loads(self.remote('cat '+quote(CONTROL+'/status.json')))
            pid=int(state['shell_pid'])
            exe=self.remote(f'readlink /proc/{pid}/exe').strip()
            # FAT can report the replacement file's former staging path for the
            # still-running, unlinked executable during a shell update.
            expected=re.fullmatch(re.escape(REMOTE)+r'/(?:\.update-[0-9a-f]{32}/)?pocketlab(?: \(deleted\))?',exe)
            command=self.remote(f'cat /proc/{pid}/cmdline').split('\0')[0]
            if state.get('protocol')!=1 or state.get('state')=='stopped' or not expected or command!=REMOTE+'/pocketlab':
                raise USBError('PocketLAB is not running.')
            return state
        except (USBError,ValueError,KeyError):
            if required: raise USBError('Open PocketLAB 1.1 or newer on the Brick. The first upgrade needs one close-and-reopen.')
            return None

    def request(self,operation,app=None,token=None,timeout=25):
        if operation not in ('launch','install','library','refresh','restart'): raise ValueError('Invalid command')
        if app is not None and not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',app): raise ValueError('Invalid app ID')
        before=self.status();token=token or uuid.uuid4().hex
        if not re.fullmatch(r'[0-9a-f]{32}',token): raise ValueError('Invalid request token')
        message=operation+(' '+app if app else '')+'\n'
        incoming=CONTROL+'/.request-'+token
        request=CONTROL+'/requests/'+token
        reply=CONTROL+'/replies/'+token+'.json'
        self.remote('printf %s '+quote(message)+' > '+quote(incoming)+'\nmv '+quote(incoming)+' '+quote(request))
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            value=self.remote('if [ -f '+quote(reply)+' ]; then cat '+quote(reply)+'; fi')
            if value.strip():
                result=json.loads(value)
                self.remote('rm -f '+quote(reply))
                if not result.get('ok'): raise AppLaunchError(result.get('message','Device rejected command'))
                return result
            current=self.status(required=False)
            if not current or current['instance']!=before['instance']:
                raise USBError('PocketLAB stopped/restarted before acknowledgement. Check status before retrying.')
            time.sleep(.15)
        self.remote('rm -f '+quote(request))
        raise USBError('No app acknowledgement before timeout. Inspect status and logs; the app may still be running.')

    def upload(self,source,stage,token):
        source=Path(source)
        if source.is_symlink() or any(p.is_symlink() for p in source.rglob('*')):
            raise ValueError('Package symlinks are not supported.')
        with tempfile.TemporaryDirectory(prefix='pocketlab-upload-') as tmp:
            payload=Path(tmp)/'payload'
            shutil.copytree(source,payload,ignore=shutil.ignore_patterns('.DS_Store','._*','__pycache__','*.pyc'))
            files=[]
            for p in sorted(payload.rglob('*')):
                relative=p.relative_to(payload).as_posix()
                if p.is_symlink() or any(ord(c)<32 for c in relative) or '\\' in relative:
                    raise ValueError('Package paths cannot contain symlinks, backslashes or control characters.')
                if p.is_file() and p.name not in ('.pocketlab-sha256','.verified'):
                    files.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+relative+'\n')
            (payload/'.verified').unlink(missing_ok=True)
            (payload/'.pocketlab-sha256').write_text(''.join(files))
            self.remote('test ! -e '+quote(stage))
            self.adb_run('push',str(payload),stage)
            # Verification happens on the Brick, before a running app is stopped.
            self.remote('cd '+quote(stage)+'\nsha256sum -c .pocketlab-sha256\nprintf %s '+quote(token)+' > .verified',timeout=40)
            return len(files)

    def deploy(self,source):
        self.status()
        token=uuid.uuid4().hex;app=Path(source).name
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',app) or app in ('esp32','starfall'):
            raise ValueError('Invalid or reserved app ID.')
        stage=REMOTE+'/apps/.incoming-'+app+'-'+token
        count=self.upload(source,stage,token)
        print(f'USB: {count} files verified on the Brick. Applying {app}...')
        result=self.request('install',app,token=token)
        status=self.status()
        if status.get('app')!=app or status.get('state')!='app': raise USBError('App acknowledged launch but is no longer running; inspect logs.')
        print(f'{result["message"]} Session {status["session"]}; PID {status["child_pid"]}.')
        return status

    def install_shell(self, package):
        from release import verify_runtime
        verify_runtime(package)
        if not self.installed:
            return self.install_first(package)
        self.remote('test ! -f '+quote(REMOTE+'/data/pending-shell-update'))
        previous = self.status(required=False)
        if previous:
            self.request('library')
        token = uuid.uuid4().hex
        stage = REMOTE+'/.update-'+token
        count = self.upload(package, stage, token)
        backup = REMOTE+'/data/updates/'+token
        files = [p.relative_to(package).as_posix() for p in Path(package).rglob('*') if p.is_file()]
        files.sort(key=lambda name: (name=='pocketlab', name!='launch.sh', name))
        script = ['mkdir '+quote(INSTALL_LOCK), 'trap '+quote('rmdir '+quote(INSTALL_LOCK))+' EXIT',
                  'test ! -f '+quote(REMOTE+'/data/pending-shell-update'), 'mkdir -p '+quote(backup)]
        restore = ['#!/bin/sh', 'set -e', 'cd '+quote(REMOTE),
                   '(cd '+quote(backup)+' && sha256sum -c backup.sha256)']
        for name in files:
            dst, old = REMOTE+'/'+name, backup+'/'+name
            script += ['mkdir -p '+quote(str(Path(old).parent)),
                       'if [ -f '+quote(dst)+' ]; then cp '+quote(dst)+' '+quote(old)+'; fi']
            replacement=dst+'.restore-'+token
            restore += ['if [ -f '+quote(old)+' ]; then cp '+quote(old)+' '+quote(replacement)+
                        ' && mv '+quote(replacement)+' '+quote(dst)+'; else rm -f '+quote(dst)+'; fi']
        restore += ['chmod 755 '+quote(REMOTE+'/pocketlab')+' '+quote(REMOTE+'/launch.sh'), 'sync',
                    'rm -f '+quote(REMOTE+'/data/pending-shell-update'), 'sync']
        def phase_record(phase):
            temporary=REMOTE+'/data/.pending-shell-update-'+token
            return ['printf %s '+quote(token+' '+phase+'\n')+' > '+quote(temporary), 'sync',
                    'mv '+quote(temporary)+' '+quote(REMOTE+'/data/pending-shell-update'), 'sync']
        script += ['cd '+quote(backup), 'find . -type f -exec sha256sum {} \\; > ../backup-'+token+'.sha256',
                   'mv ../backup-'+token+'.sha256 backup.sha256',
                   'printf %s '+quote('\n'.join(restore)+'\n')+' > restore.sh']
        script += phase_record('copying')
        for name in files:
            dst=REMOTE+'/'+name
            script += ['mkdir -p '+quote(str(Path(dst).parent)), 'mv '+quote(stage+'/'+name)+' '+quote(dst)]
        script += ['chmod 755 '+quote(REMOTE+'/pocketlab')+' '+quote(REMOTE+'/launch.sh'), 'sync']
        script += phase_record('ready')
        self.remote('\n'.join(script), timeout=60)
        print(f'PocketLAB updated; {count} uploaded files verified. Previous files: {backup}')
        if not previous:
            print('Open PocketLAB from Apps. The launcher will verify startup.')
            return False
        self.request('restart')
        end=time.monotonic()+20
        while time.monotonic()<end:
            state=self.status(required=False)
            if state and state['instance']!=previous['instance']:
                expected=hashlib.sha256((Path(package)/'pocketlab').read_bytes()).hexdigest()
                actual=self.remote('sha256sum '+quote(REMOTE+'/pocketlab')).split()[0]
                if actual!=expected:
                    raise AppLaunchError('The updated shell failed startup; the previous runtime was restored.')
                self.remote('rm -f '+quote(REMOTE+'/data/pending-shell-update'))
                print(f'PocketLAB {state["version"]} restarted automatically.')
                return True
            time.sleep(.3)
        self.remote('sh '+quote(backup+'/restore.sh'), timeout=40)
        raise USBError('New shell did not acknowledge startup. Previous files restored; reopen PocketLAB from Apps.')

    def install_first(self, package):
        token=uuid.uuid4().hex
        stage=str(Path(REMOTE).parent/('.PocketLab.incoming-'+token))
        self.remote('test ! -e '+quote(REMOTE))
        self.upload(package, stage, token)
        self.remote('mkdir '+quote(INSTALL_LOCK)+'\ntrap '+quote('rmdir '+quote(INSTALL_LOCK))+' EXIT\n'+
                    'test ! -e '+quote(REMOTE)+'\nmkdir -p '+quote(stage+'/apps')+' '+quote(stage+'/data')+
                    '\nchmod 755 '+quote(stage+'/pocketlab')+' '+quote(stage+'/launch.sh')+
                    '\nmv '+quote(stage)+' '+quote(REMOTE)+'\nsync')
        print('PocketLAB installed and verified. Open Apps → PocketLAB on the Brick.')
        return True

    def recover_shell(self):
        pending=self.remote('cat '+quote(REMOTE+'/data/pending-shell-update')).split()
        if len(pending)!=2 or not re.fullmatch('[0-9a-f]{32}',pending[0]):
            raise USBError('Invalid pending-update record')
        self.remote('mkdir '+quote(INSTALL_LOCK)+'\ntrap '+quote('rmdir '+quote(INSTALL_LOCK))+' EXIT\n'+
                    'sh '+quote(REMOTE+'/data/updates/'+pending[0]+'/restore.sh'), timeout=40)
        print('Previous shell files restored. Close and reopen PocketLAB from Apps.')
