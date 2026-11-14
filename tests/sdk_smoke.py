"""Generate/build an external app, verify host readiness/save/exit, inspect ARM output. No device access."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from pocketlab import new_app,build_app
from native_build import elf_info

with tempfile.TemporaryDirectory(prefix='pocketlab-sdk-') as tmp:
    base=Path(tmp);app=new_app(base/'outside-project','100% instrument')
    build_app(app,host=True)
    data=base/'state';data.mkdir();ready=base/'ready'
    log=base/'app.log'
    for session in ('first','second'):
        if session=='second':(data/'count.txt').write_text('37\n')
        ready.unlink(missing_ok=True)
        env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy',
                 POCKETLAB_ROOT=str(ROOT),POCKETLAB_APP_DATA=str(data),
                 POCKETLAB_READY_FILE=str(ready),POCKETLAB_SESSION=session)
        with log.open('w') as out:
            process=subprocess.Popen([str(app/'app')],env=env,stdout=out,stderr=out)
            try:
                deadline=time.monotonic()+8
                while not ready.exists() and process.poll() is None and time.monotonic()<deadline:
                    time.sleep(.05)
                assert ready.exists() and ready.read_text().strip()==session,log.read_text()
            finally:
                if process.poll() is None:process.terminate()
                process.wait(timeout=5)
        assert process.returncode==0
        assert (data/'count.txt').read_text().strip()==('0' if session=='first' else '37')
    (app/'extra.c').write_text('int sdk_extra_source(void) { return 7; }\n')
    build_app(app)
    info=elf_info(app/'app');assert info['glibc']==['GLIBC_2.17']
    assert b'/Users/' not in (app/'app').read_bytes()
    previous=(app/'app').read_bytes()
    (app/'extra.c').write_text('#error deliberate SDK build failure\n')
    try:build_app(app)
    except subprocess.CalledProcessError:pass
    else:raise AssertionError('Broken source compiled')
    assert (app/'app').read_bytes()==previous
    assert (app/'cover.bmp').exists()
print('SDK smoke passed: external project, title escaping, readiness, SIGTERM, saved-state reopen, multi-file ARM64 build, failed-build preservation, artwork.')
