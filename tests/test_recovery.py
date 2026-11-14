import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import usb_deploy


class LocalTransport(usb_deploy.Brick):
    """Execute generated update scripts ONLY in an isolated temporary tree."""
    def __init__(self):self.installed=True
    def status(self,required=True):return None
    def remote(self,script,timeout=40):
        return subprocess.check_output(['sh','-ec',script],text=True,timeout=timeout)
    def upload(self,source,stage,token):
        shutil.copytree(source,stage)
        return sum(p.is_file() for p in Path(stage).rglob('*'))


class RecoveryTests(unittest.TestCase):
    def test_concurrent_installer_cannot_promote_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,payload=self.prepare(Path(tmp))
            original=(app/'pocketlab').read_bytes()
            lock=app.parent/'install-lock';lock.mkdir()
            with self.assertRaises(subprocess.CalledProcessError):self.install(app,payload)
            self.assertEqual((app/'pocketlab').read_bytes(),original)
            self.assertTrue(lock.exists())

    def test_first_install_needs_no_running_controller(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);payload=root/'payload';payload.mkdir()
            (payload/'pocketlab').write_text('binary');(payload/'launch.sh').write_text('#!/bin/sh\n')
            app=root/'Apps/PocketLab';app.parent.mkdir();(root/'untouched').write_text('keep')
            transport=LocalTransport();transport.installed=False
            with patch('usb_deploy.REMOTE',str(app)),patch('usb_deploy.INSTALL_LOCK',str(root/'install-lock')),patch('release.verify_runtime'),contextlib.redirect_stdout(io.StringIO()):
                transport.install_shell(payload)
            self.assertTrue((app/'apps').is_dir());self.assertTrue((app/'data').is_dir())
            self.assertEqual((root/'untouched').read_text(),'keep')

    def prepare(self, root, fails=False):
        app=root/'installed';payload=root/'payload';app.mkdir();payload.mkdir()
        (app/'data/keep').mkdir(parents=True);(app/'data/keep/score').write_text('123')
        (app/'apps/user-app').mkdir(parents=True);(app/'apps/user-app/keep').write_text('user')
        (app/'pocketlab').write_text('#!/bin/sh\nprintf restored > data/restored\nexit 0\n')
        (app/'pocketlab').chmod(0o755)
        shutil.copy2(ROOT/'packaging/launch.sh',app/'launch.sh')
        shutil.copy2(ROOT/'packaging/launch.sh',payload/'launch.sh')
        code='#!/bin/sh\n'
        if fails:code+='exit 42\n'
        else:
            code+='mkdir -p data/control\nprintf \'{"shell_pid":%s,"state":"library"}\\n\' "$$" > data/control/status.json\nsleep 1\nexit 0\n'
        (payload/'pocketlab').write_text(code);(payload/'pocketlab').chmod(0o755)
        (payload/'new-runtime-file').write_text('new')
        return app,payload

    def install(self,app,payload):
        with patch('usb_deploy.REMOTE',str(app)),patch('usb_deploy.INSTALL_LOCK',str(app.parent/'install-lock')),patch('release.verify_runtime'),contextlib.redirect_stdout(io.StringIO()):
            LocalTransport().install_shell(payload)

    def test_good_update_acknowledges_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,payload=self.prepare(Path(tmp));self.install(app,payload)
            subprocess.run(['sh',str(app/'launch.sh')],check=True,timeout=15)
            self.assertFalse((app/'data/pending-shell-update').exists())
            self.assertFalse((app/'data/restored').exists())
            self.assertEqual((app/'data/keep/score').read_text(),'123')
            self.assertEqual((app/'apps/user-app/keep').read_text(),'user')

    def test_failed_startup_restores_old_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,payload=self.prepare(Path(tmp),True);self.install(app,payload)
            subprocess.run(['sh',str(app/'launch.sh')],check=True,timeout=15)
            self.assertTrue((app/'data/restored').exists())
            self.assertFalse((app/'new-runtime-file').exists())
            self.assertFalse((app/'data/pending-shell-update').exists())
            self.assertEqual((app/'data/keep/score').read_text(),'123')

    def test_interrupted_copy_recovers_before_attempting_new_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,payload=self.prepare(Path(tmp));self.install(app,payload)
            pending=app/'data/pending-shell-update';token=pending.read_text().split()[0]
            pending.write_text(token+' copying\n')
            (app/'pocketlab').write_text('incomplete binary')
            subprocess.run(['sh',str(app/'launch.sh')],check=True,timeout=15)
            self.assertTrue((app/'data/restored').exists())

    def test_corrupt_backup_is_not_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,payload=self.prepare(Path(tmp),True);self.install(app,payload)
            token=(app/'data/pending-shell-update').read_text().split()[0]
            (app/'data/updates'/token/'pocketlab').write_text('corrupt backup')
            result=subprocess.run(['sh',str(app/'launch.sh')],timeout=15)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((app/'data/restored').exists())


if __name__=='__main__':unittest.main()
