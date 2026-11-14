"""Exercise generated assets, native decoding, fallbacks, and complete library renders."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from cover_art import write_cover
from pocketlab import new_app, ensure_cover
from render import png_from_bmp

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    with contextlib.redirect_stdout(io.StringIO()):
        first = new_app(root/'first-beats', 'First Beats')
        second = new_app(root/'second-beats', 'Second Beats')
    original = (first/'cover.bmp').read_bytes()
    assert original[:2] == b'BM' and len(original) == 480*192*3+54
    assert original != (second/'cover.bmp').read_bytes()
    # A user's cover always survives new builds and preparation for deployment.
    (first/'cover.bmp').write_bytes(b'authored image')
    ensure_cover(first)
    assert (first/'cover.bmp').read_bytes() == b'authored image'
    (second/'cover.bmp').unlink()
    with contextlib.redirect_stdout(io.StringIO()): ensure_cover(second)
    assert (second/'cover.bmp').read_bytes()[:2] == b'BM'
    assert not write_cover(second/'cover.bmp', 'different-id', 'Different name')
    cases = {'good': original, 'huge': bytearray(original), 'truncated': original[:60],
             'negative': bytearray(original), 'bad-bits': bytearray(original),
             'offset': bytearray(original), 'top-down': bytearray(original)}
    struct.pack_into('<I', cases['huge'], 18, 0x7fffffff)
    struct.pack_into('<i', cases['negative'], 22, -2147483648)
    struct.pack_into('<H', cases['bad-bits'], 28, 64)
    struct.pack_into('<I', cases['offset'], 10, 0xfffffff0)
    struct.pack_into('<i', cases['top-down'], 22, -192)
    for name, data in cases.items():
        (root/name).mkdir(); (root/name/'cover.bmp').write_bytes(data)
    binary = ROOT/'build/cover-test'
    flags = subprocess.check_output(['sdl2-config', '--cflags', '--libs'], text=True).split()
    subprocess.run(['clang', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-g',
                    '-fsanitize=address,undefined', str(ROOT/'tests/cover_test.c'),
                    str(ROOT/'src/cover.c'), *flags, '-lm', '-o', str(binary)], check=True)
    subprocess.run([str(binary), str(root)], check=True, env=dict(os.environ, SDL_VIDEODRIVER='dummy'))
    fixture = root/'library'; (fixture/'apps').mkdir(parents=True)
    shutil.copytree(ROOT/'assets', fixture/'assets')
    # Keep this render independent of app binaries and user data.
    for app_id in ('fixture-music', 'fixture-visual'):
        app = fixture/'apps'/app_id; app.mkdir()
        (app/'app.json').write_text(json.dumps({'name':app_id.replace('-', ' ').title(),'description':'Isolated artwork fixture'}))
        (app/'launch.sh').write_text('#!/bin/sh\nexit 0\n')
        name = json.loads((app/'app.json').read_text())['name']
        write_cover(app/'cover.bmp', app_id, name)
    output = ROOT/'build/cover-validation'; output.mkdir(parents=True, exist_ok=True)
    for variant in ('artwork', 'fallback'):
        if variant == 'fallback':
            (fixture/'apps/fixture-music/cover.bmp').unlink()
            (fixture/'apps/fixture-visual/cover.bmp').write_bytes(b'broken artwork')
        bmp = output/f'library-{variant}.bmp'
        subprocess.run([str(ROOT/'build/pocketlab-host'), '--root', str(fixture), '--render',
                        str(bmp), '--render-app', 'fixture-visual'], check=True)
        png_from_bmp(bmp, bmp.with_suffix('.png'))
    shutil.rmtree(fixture/'apps')
    (fixture/'apps').mkdir()
    for app_id in ('fixture-panel', 'fixture-blocks'):
        app = fixture/'apps'/app_id; app.mkdir()
        (app/'app.json').write_text(json.dumps({'name':app_id.replace('-', ' ').title(),'description':'Isolated artwork fixture'}))
        (app/'launch.sh').write_text('#!/bin/sh\nexit 0\n')
        write_cover(app/'cover.bmp', app_id, json.loads((app/'app.json').read_text())['name'])
    bmp = output/'library-fixture-blocks.bmp'
    subprocess.run([str(ROOT/'build/pocketlab-host'), '--root', str(fixture), '--render',
                    str(bmp), '--render-app', 'fixture-blocks'], check=True)
    png_from_bmp(bmp, bmp.with_suffix('.png'))
print('Automatic covers, authored-cover preservation and library render checks passed.')
