"""Pinned native cross compiler. Downloads once; later builds work offline."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'build/toolchain'
ZIG_VERSION = '0.14.1'
ZIG_HASHES = {
    'aarch64-macos': '39f3dc5e79c22088ce878edc821dedb4ca5a1cd9f5ef915e9b3cc3053e8faefa',
    'x86_64-macos': 'b0f8bdfb9035783db58dd6c19d7dea89892acc3814421853e5752fe4573e5f43',
    'x86_64-linux': '24aeeec8af16c381934a6cd7d95c807a8cb2cf7df9fa40d359aa884195c4716c',
    'aarch64-linux': 'f7a654acc967864f7a050ddacfaa778c7504a0eca8d2b678839c21eea47c992b',
}
SDL_VERSION = '2.26.1'
SDL_HASH = '02537cc7ebd74071631038b237ec4bfbb3f4830ba019e569434da33f42373e04'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unpack(url, expected, folder):
    archive = CACHE / url.rsplit('/', 1)[1]
    marker = folder / '.pocketlab-verified'
    if marker.is_file() and marker.read_text().strip() == expected:
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        print(f'One-time SDK download: {archive.name}', flush=True)
        part = archive.with_suffix(archive.suffix + '.part')
        try:
            with urllib.request.urlopen(url, timeout=60) as src, part.open('wb') as dst:
                shutil.copyfileobj(src, dst)
            if sha256(part) != expected:
                raise ValueError(f'Download checksum mismatch: {archive.name}')
            part.replace(archive)
        finally:
            part.unlink(missing_ok=True)
    if sha256(archive) != expected:
        raise ValueError(f'SDK checksum mismatch; remove {archive} and retry.')
    # Extract only a verified official archive, confined to its expected root.
    with tempfile.TemporaryDirectory(prefix='unpack-', dir=CACHE) as tmp:
        with tarfile.open(archive) as tf:
            if not hasattr(tarfile, 'data_filter'):
                raise RuntimeError('Python 3.12+ (or updated 3.11 with tarfile.data_filter) is required.')
            tf.extractall(tmp, filter='data')
        extracted = Path(tmp) / folder.name
        if not extracted.is_dir():
            raise ValueError('SDK archive has an unexpected layout.')
        if folder.exists():
            shutil.rmtree(folder)
        extracted.rename(folder)
    marker.write_text(expected + '\n')


def elf_info(path):
    data = Path(path).read_bytes()
    if data[:6] != b'\x7fELF\x02\x01' or data[18:20] != b'\xb7\0':
        raise ValueError(f'Expected a little-endian ARM64 Linux ELF: {path}')
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count = struct.unpack_from('<HH', data, 58)
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + size*i) for i in range(count)]
    needed = []
    for section in sections:
        if section[1] != 6:  # SHT_DYNAMIC
            continue
        strings = sections[section[6]]
        for pos in range(section[4], section[4]+section[5], section[9]):
            tag, value = struct.unpack_from('<qQ', data, pos)
            if tag == 1:  # DT_NEEDED
                start = strings[4] + value
                needed.append(data[start:data.index(b'\0', start)].decode())
    versions = sorted(set(v.decode() for v in re.findall(rb'GLIBC_[0-9.]+', data)))
    return {'needed': needed, 'glibc': versions, 'sha256': sha256(path)}


def setup(serial=None):
    machine = {'arm64': 'aarch64', 'AMD64': 'x86_64'}.get(platform.machine(), platform.machine())
    system = {'Darwin': 'macos', 'Linux': 'linux'}.get(platform.system())
    host = f'{machine}-{system}'
    if host not in ZIG_HASHES:
        raise RuntimeError('The SDK supports ARM64/Intel macOS and Linux hosts.')
    zig = CACHE / f'zig-{host}-{ZIG_VERSION}'
    unpack(f'https://ziglang.org/download/{ZIG_VERSION}/{zig.name}.tar.xz', ZIG_HASHES[host], zig)
    sdl = CACHE / f'SDL2-{SDL_VERSION}'
    unpack(f'https://www.libsdl.org/release/{sdl.name}.tar.gz', SDL_HASH, sdl)
    # Import-only library: exported names come from pinned upstream SDL, while
    # call signatures come from its headers. The real stock SDL resolves these
    # symbols on the Brick. This file MUST NEVER be installed on a device.
    imports = CACHE / 'sdl-imports'
    imports.mkdir(exist_ok=True)
    library = imports / 'libSDL2.so'
    record = imports / 'source.json'
    api = sdl / 'src/dynapi/SDL_dynapi_procs.h'
    identity = {'sdl_sha256': SDL_HASH, 'api_sha256': sha256(api), 'generator': 1,
                'kind': 'link-only; never deploy', 'soname': 'libSDL2-2.0.so.0'}
    cached = json.loads(record.read_text()) if record.is_file() else {}
    if not library.is_file() or any(cached.get(k) != v for k, v in identity.items()):
        names = sorted(set(re.findall(r'^SDL_DYNAPI_PROC\([^,]+,\s*(SDL_\w+)\s*,',
                                      api.read_text(), re.M)))
        if len(names) < 500:
            raise ValueError('Unexpected upstream SDL export table')
        source = imports / 'imports.c'
        notice = api.read_text().split('*/', 1)[0] + '*/\n'
        source.write_text(notice + '/* Generated import stubs, not an SDL runtime. */\n' +
                          '\n'.join(f'void {name}(void) {{ __builtin_trap(); }}' for name in names))
        temporary = imports / 'libSDL2.so.incoming'
        subprocess.run([str(zig/'zig'), 'cc', '-target', 'aarch64-linux.4.9-gnu.2.17',
                        '-shared', '-nostdlib', '-fno-stack-protector', '-O2', '-s',
                        '-Wl,-soname,libSDL2-2.0.so.0', str(source), '-o', str(temporary)],
                       check=True, env=dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(CACHE/'zig-cache')))
        elf_info(temporary)
        temporary.replace(library)
        record.write_text(json.dumps(dict(identity, sha256=sha256(library)), indent=2)+'\n')
    if sha256(library) != json.loads(record.read_text())['sha256']:
        raise ValueError(f'Cached SDL imports differ; remove {imports} and retry.')
    return zig / 'zig', sdl / 'include', imports


def compile_arm(sources, output, includes=(), serial=None):
    zig, headers, libraries = setup(serial)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(CACHE/'zig-cache'))
    # Build away from app sources so watch mode never observes its own build files.
    with tempfile.TemporaryDirectory(prefix='compile-', dir=CACHE) as tmp:
        binary = Path(tmp) / 'app'
        command = [str(zig), 'cc', '-target', 'aarch64-linux.4.9-gnu.2.17',
                   '-std=gnu11', '-O2', '-Wall', '-Wextra', '-DHAVE_LIBC=1',
                   '-ffile-prefix-map='+str(ROOT)+'=.',
                   *['-ffile-prefix-map='+str(Path(p).resolve())+'=app' for p in includes
                     if not Path(p).resolve().is_relative_to(ROOT)],
                   '-I'+str(headers), *['-I'+str(p) for p in includes],
                   *map(str, sources), '-L'+str(libraries), '-lSDL2',
                   '-Wl,--allow-shlib-undefined', '-lm', '-lpthread', '-s', '-o', str(binary)]
        subprocess.run(command, env=env, check=True)
        info = elf_info(binary)
        allowed = {'libSDL2-2.0.so.0', 'libm.so.6', 'libpthread.so.0', 'libc.so.6', 'libdl.so.2', 'librt.so.1'}
        if set(info['needed']) - allowed:
            raise ValueError(f'Unexpected runtime dependencies: {info["needed"]}')
        if any(tuple(map(int, v[6:].split('.'))) > (2, 17) for v in info['glibc']):
            raise ValueError(f'Build requires newer glibc: {info["glibc"]}')
        shutil.copy2(binary, output.with_name(output.name+'.incoming'))
        output.with_name(output.name+'.incoming').replace(output)
    print('ARM64 verified: '+', '.join(info['needed'])+'; '+', '.join(info['glibc']), flush=True)
    return info


def build_shell(serial=None):
    sources = [ROOT/'src'/name for name in ('main.c','ui.c','usb.c','game.c','audio.c','control.c','cover.c')]
    info = compile_arm(sources, ROOT/'build/pocketlab', serial=serial)
    from release import core_hashes
    receipt = {'binary':info, 'core_sources':core_hashes(), 'builder_sha256':sha256(Path(__file__))}
    (ROOT/'build/pocketlab.build.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    return info
