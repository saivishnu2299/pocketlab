"""Exercise the actual native shell's control protocol with isolated app processes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1]

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        shutil.copytree(ROOT/'assets',self.root/'assets');(self.root/'apps').mkdir()
        self.log=(self.root/'test.log').open('w')
        self.process=None;self.start()
    def tearDown(self):
        if self.process and self.process.poll() is None:
            self.process.terminate();self.process.wait(timeout=8)
        self.log.close();self.tmp.cleanup()
    def start(self):
        env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
        self.process=subprocess.Popen([os.environ.get('POCKETLAB_TEST_BINARY',str(ROOT/'build/pocketlab-host')),'--root',str(self.root),'--quiet'],env=env,stdout=self.log,stderr=self.log)
        self.wait(lambda:self.status().get('state')=='library')
    def status(self):
        try:return json.loads((self.root/'data/control/status.json').read_text())
        except (FileNotFoundError,ValueError):return {}
    def wait(self,condition,seconds=12):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            result=condition()
            if result:return result
            time.sleep(.05)
        self.fail('Timed out. '+(self.root/'test.log').read_text()[-2400:])
    def send(self,command,token=None):
        token=token or uuid.uuid4().hex
        incoming=self.root/'data/control'/('tmp-'+token)
        incoming.write_text(command+'\n');incoming.rename(self.root/'data/control/requests'/token)
        reply=self.root/'data/control/replies'/(token+'.json')
        self.wait(reply.exists)
        result=json.loads(reply.read_text());reply.unlink();return result
    def stage(self,token,revision='one',fail=False,verified=True,ready=True):
        folder=self.root/'apps'/('simulated-'+token)  # hidden only after writing, like an upload
        folder.mkdir()
        (folder/'app.json').write_text(json.dumps({'name':'Control test','description':'Fixture','ready':'file'}))
        script='#!/bin/sh\n'
        if fail:script+='exit 42\n'
        else:
            script+='trap \'printf saved-'+revision+' > "$POCKETLAB_APP_DATA/saved"; exit 0\' TERM\n'
            if ready:script+='printf "%s\\n" "$POCKETLAB_SESSION" > "$POCKETLAB_READY_FILE"\n'
            script+='while :; do sleep 1; done\n'
        (folder/'launch.sh').write_text(script)
        if verified:(folder/'.verified').write_text(token)
        folder.rename(self.root/'apps'/('.incoming-demo-'+token))
    def test_install_reload_invalid_upload_rollback_and_return(self):
        token=uuid.uuid4().hex;self.stage(token)
        self.assertTrue(self.send('install demo',token)['ok'])
        first=self.status();self.assertTrue(first['ready']);self.assertEqual(first['app'],'demo')
        # Incomplete uploads and unknown targets must not interrupt a working app.
        token=uuid.uuid4().hex;self.stage(token,verified=False)
        self.assertFalse(self.send('install demo',token)['ok'])
        self.assertEqual(self.status()['child_pid'],first['child_pid'])
        self.assertFalse(self.send('launch missing')['ok'])
        self.assertFalse(self.send('launch ../escape')['ok'])
        self.assertEqual(self.status()['child_pid'],first['child_pid'])
        # A second successful build gets a new process; TERM saves the first app's state.
        token=uuid.uuid4().hex;self.stage(token,revision='two')
        self.assertTrue(self.send('install demo',token)['ok'])
        self.assertNotEqual(self.status()['child_pid'],first['child_pid'])
        self.assertEqual((self.root/'data/demo/saved').read_text(),'saved-one')
        # A broken release is rolled back and the working app starts again.
        token=uuid.uuid4().hex;self.stage(token,fail=True)
        result=self.send('install demo',token);self.assertFalse(result['ok']);self.assertIn('restored',result['message'])
        self.wait(lambda:self.status().get('state')=='app' and self.status().get('ready'))
        self.assertIn('saved-two',(self.root/'apps/demo/launch.sh').read_text())
        self.assertTrue(self.send('library')['ok'])
        self.assertEqual(self.status()['state'],'library')
        self.assertEqual((self.root/'data/demo/saved').read_text(),'saved-two')
    def test_readiness_timeout_and_restart(self):
        token=uuid.uuid4().hex;self.stage(token,ready=False)
        result=self.send('install demo',token);self.assertFalse(result['ok'])
        self.assertFalse((self.root/'apps/demo').exists())
        self.assertTrue(self.send('restart')['ok'])
        self.assertEqual(self.process.wait(timeout=5),75)
    def test_stale_request_expired_on_start(self):
        self.process.terminate();self.process.wait(timeout=5)
        token=uuid.uuid4().hex
        (self.root/'data/control/requests'/token).write_text('launch starfall\n')
        self.start()
        reply=self.root/'data/control/replies'/(token+'.json')
        self.wait(reply.exists)
        self.assertFalse(json.loads(reply.read_text())['ok'])
        self.assertEqual(self.status()['state'],'library')
    def test_library_with_many_independent_apps(self):
        for i in range(40):
            folder=self.root/'apps'/f'app-{i:02d}';folder.mkdir()
            (folder/'app.json').write_text(json.dumps({'name':f'Instrument {i}','description':'Library fixture','ready':'file'}))
            (folder/'launch.sh').write_text('''#!/bin/sh
trap 'exit 0' TERM
printf '%s\\n' "$POCKETLAB_SESSION" > "$POCKETLAB_READY_FILE"
while :; do sleep 1; done
''')
        self.assertTrue(self.send('refresh')['ok'])
        for app in ('app-00','app-39'):
            self.assertTrue(self.send('launch '+app)['ok'])
            self.assertEqual(self.status()['app'],app)
        self.assertTrue(self.send('library')['ok'])

if __name__=='__main__':unittest.main(verbosity=2)
