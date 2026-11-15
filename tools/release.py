#!/usr/bin/env python3
"""Build local, allowlisted release archives. This tool never publishes anything."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime/Apps/PocketLab'


def digest(path):
    # Chunked hashing keeps card setup compatible with the Python 3.9 bundled by macOS.
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def version():
    value = (ROOT/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9.]+)?', value):
        raise ValueError('Invalid VERSION')
    return value


def source_files():
    names = (ROOT/'release-files.txt').read_text().splitlines()
    result = []
    for name in names:
        if not name or name.startswith('#'):
            continue
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\' in name or name in result:
            raise ValueError('Invalid or duplicate release path: '+name)
        path = ROOT/name
        if not path.is_file() or any(parent.is_symlink() for parent in [path, *path.parents]):
            raise ValueError('Missing or linked release file: '+name)
        result.append(name)
    return sorted(result)


def core_hashes():
    return {str(p.relative_to(ROOT)): digest(p) for d in ('src','assets','vendor')
            for p in sorted((ROOT/d).rglob('*')) if p.is_file()}


def verify_runtime(folder=RUNTIME, match_source=True):
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError('No bundled runtime. Maintainers: build-shell, then release.py runtime.')
    from native_build import elf_info
    manifest = json.loads((folder/'manifest.sha256.json').read_text())
    if not isinstance(manifest, dict) or not {'pocketlab','launch.sh','config.json'} <= set(manifest):
        raise ValueError('Incomplete runtime manifest')
    for name, expected in manifest.items():
        path = PurePosixPath(name)
        if not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name or path.parts[0] in ('data','apps','lib'):
            raise ValueError('Invalid runtime manifest path')
        target = folder/name
        if not target.is_file() or target.is_symlink() or digest(target) != expected:
            raise ValueError('Runtime checksum mismatch: '+name)
    actual = {str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file()}
    if actual != set(manifest) | {'manifest.sha256.json'} or any(p.is_symlink() for p in folder.rglob('*')):
        raise ValueError('Unexpected runtime files; apps/data must be empty')
    config = json.loads((folder/'config.json').read_text())
    if config.get('package') != 'org.pocketlab.shell':
        raise ValueError('Wrong runtime identity')
    # The stock launcher draws "icon" as a second, larger layer behind "icontop".
    if config.get('icontop') != 'icon.png' or config.get('icon') != '':
        raise ValueError('Launcher icon must be set only as icontop, with an empty icon field')
    info = json.loads((folder/'build-info.json').read_text())
    binary = elf_info(folder/'pocketlab')
    if binary['sha256'] != info['binary']['sha256']:
        raise ValueError('Runtime provenance mismatch')
    if match_source and (info['core_sources'] != core_hashes() or info['version'] != version()
                         or info.get('builder_sha256') != digest(ROOT/'tools/native_build.py')):
        raise ValueError('Bundled runtime does not match core source/VERSION; rebuild the runtime')
    return info


def build_runtime():
    from native_build import elf_info
    from icon_art import write_icon
    binary = ROOT/'build/pocketlab'
    info = elf_info(binary)
    receipt=json.loads((ROOT/'build/pocketlab.build.json').read_text())
    if receipt.get('binary')!=info or receipt.get('core_sources')!=core_hashes() or receipt.get('builder_sha256')!=digest(ROOT/'tools/native_build.py'):
        raise ValueError('ARM build receipt is stale. Re-run make brick before packaging.')
    for source in ('src/main.c','src/control.c'):
        if version() not in (ROOT/source).read_text():
            raise ValueError('VERSION differs from shell/controller version')
    RUNTIME.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='runtime-', dir=ROOT/'build') as tmp:
        stage = Path(tmp)/'PocketLab'; stage.mkdir()
        shutil.copy2(binary, stage/'pocketlab')
        shutil.copytree(ROOT/'assets', stage/'assets')
        for name in ('config.json','launch.sh'):
            shutil.copy2(ROOT/'packaging'/name, stage/name)
        for name in ('LICENSE','THIRD_PARTY.md'):
            shutil.copy2(ROOT/name, stage/name)
        shutil.copy2(ROOT/'docs/DEVICE.md', stage/'README.md')
        write_icon(stage/'icon.png')
        for name in ('pocketlab','launch.sh'):
            (stage/name).chmod(0o755)
        data = {'version': version(), 'default_apps':['esp32','starfall'], 'target':'TG4040-stock-arm64',
                'binary':info, 'core_sources':core_hashes(), 'builder_sha256':receipt['builder_sha256'],
                'build':{'zig':'0.14.1','sdl_headers':'2.26.1','target':'aarch64-linux.4.9-gnu.2.17',
                         'sdl_link_input':'generated from pinned upstream exports; not a runtime'}}
        (stage/'build-info.json').write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
        manifest={str(p.relative_to(stage)):digest(p) for p in sorted(stage.rglob('*')) if p.is_file()}
        (stage/'manifest.sha256.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
        verify_runtime(stage)
        if RUNTIME.exists(): shutil.rmtree(RUNTIME)
        shutil.copytree(stage,RUNTIME)
    print('Prepared verified runtime with ESP32 detector and Starfall only.')


def check():
    baseline = json.loads((ROOT/'tests/baseline/ui-source.json').read_text())
    if baseline != core_hashes():
        raise ValueError('Shell/source/artwork differs from the frozen UI baseline')
    files = source_files()
    if (ROOT/'.git').exists():
        tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'))-{''}
        allowed=set(files)|{'runtime/'+p.relative_to(ROOT/'runtime').as_posix() for p in RUNTIME.rglob('*') if p.is_file()}
        if tracked-allowed:
            raise ValueError('Tracked files outside the public release allowlist: '+', '.join(sorted(tracked-allowed)))
    if not all(name in files for name in core_hashes()):
        raise ValueError('Release allowlist omits core sources')
    # Reject common accidentally embedded workstation paths and credentials.
    patterns = [rb'/Users/[^/\s]+/', rb'/home/[^/\s]+/', rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                rb'github_pat_[A-Za-z0-9_]{30,}', rb'ghp_[A-Za-z0-9]{30,}', rb'sk-proj-[A-Za-z0-9_-]{30,}']
    candidates=[(name,ROOT/name) for name in files]
    candidates += [('runtime/'+p.relative_to(RUNTIME).as_posix(),p) for p in RUNTIME.rglob('*') if p.is_file()]
    for name,path in candidates:
        if name == 'tools/release.py': continue
        raw = path.read_bytes()
        if any(re.search(pattern,raw) for pattern in patterns):
            raise ValueError('Private material candidate in '+name+'; inspect locally')
    verify_runtime()
    print(f'Release checks passed: {len(files)} allowlisted source files; frozen UI; two default apps; verified runtime.')
    return files


def archive(path, items):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as out:
        for name, source in sorted(items):
            info=zipfile.ZipInfo(name, date_time=(2026,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.create_system=3
            mode=0o755 if source.stat().st_mode & 0o111 else 0o644
            info.external_attr=(stat.S_IFREG | mode) << 16
            out.writestr(info,source.read_bytes())


def bundle():
    files=check(); output=ROOT/'dist';output.mkdir(exist_ok=True)
    name='PocketLAB-'+version()
    runtime=[(p.relative_to(ROOT/'runtime').as_posix(),p) for p in RUNTIME.rglob('*') if p.is_file()]
    archive(output/(name+'-device.zip'),runtime)
    source=[(name+'/'+p,ROOT/p) for p in files]
    source += [(name+'/runtime/'+p,path) for p,path in runtime]
    archive(output/(name+'-source.zip'),source)
    paths=[output/(name+'-device.zip'),output/(name+'-source.zip')]
    (output/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in paths))
    print('Local archives prepared in dist/. Nothing published.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['runtime','check','bundle'])
    try:
        {'runtime':build_runtime,'check':check,'bundle':bundle}[parser.parse_args().command]()
    except (ValueError,OSError,KeyError) as e:
        print('Release: '+str(e),file=sys.stderr);sys.exit(1)
