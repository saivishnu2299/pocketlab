#!/usr/bin/env python3
"""Build and deploy PocketLAB and its independent native mini apps.

Uses direct USB ADB with automatic relaunch, or a mounted stock-OS SD card.
No device firmware, system partitions, drivers, or unrelated apps are modified.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
import time
from usb_deploy import Brick, USBError, AppLaunchError
from native_build import compile_arm, build_shell, setup
from cover_art import write_cover
from release import digest
from card_io import remove_tree, strip_appledouble

ROOT = Path(__file__).resolve().parents[1]


def verify_tree(source, destination):
    for p in Path(source).rglob('*'):
        if p.name == '.DS_Store' or p.name.startswith('._'):
            continue
        if p.is_file():
            other = Path(destination) / p.relative_to(source)
            if not other.is_file() or digest(p) != digest(other):
                raise RuntimeError(f'Copy verification failed: {other}')


def safe_tree(path):
    if Path(path).is_symlink():
        raise ValueError('Package root cannot be a symlink')
    for p in Path(path).rglob('*'):
        if p.is_symlink():
            raise ValueError(f'Package symlinks are not supported: {p}')
        if p.name.startswith('._') or p.name == '.DS_Store':
            continue
        if not p.is_dir() and not p.is_file():
            raise ValueError(f'Package contains a special file: {p}')


def install_tree(source, destination, preserve=(), allow_pending=False):
    """Stage, hash-check, rename, retain the prior package for rollback."""
    source, destination = Path(source).resolve(), Path(destination).absolute()
    safe_tree(source)
    if destination.is_symlink():
        raise ValueError('Refusing a symlink install destination')
    destination = destination.resolve()
    if destination.name=='PocketLab' and (destination/'data/pending-shell-update').exists() and not allow_pending:
        raise ValueError('A shell update is pending. Run recover --sd CARD before a card-reader update.')
    if destination.name=='PocketLab' and not destination.exists() and any(destination.parent.glob('.PocketLab.backup-*')):
        raise ValueError('PocketLAB is missing but a retained backup exists. Use recover --sd CARD --backup BACKUP_NAME before installing again.')
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination must not overlap')
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = sum(p.stat().st_size for p in source.rglob('*') if p.is_file())
    size += sum(p.stat().st_size for name in preserve for p in (destination/name).rglob('*') if p.is_file())
    if shutil.disk_usage(destination.parent).free < size + 8*1024*1024:
        raise ValueError('Not enough space for a verified staged update; current installation retained.')
    suffix = uuid.uuid4().hex[:10]
    stage = destination.parent / f'.{destination.name}.incoming-{suffix}'
    backup = destination.parent / f'.{destination.name}.backup-{suffix}'
    try:
        shutil.copytree(source, stage, ignore=shutil.ignore_patterns('.DS_Store', '._*'))
        # New releases never replace app-owned data or the user's mini apps.
        for relative in preserve:
            old = destination / relative
            if old.exists():
                safe_tree(old)
                target = stage / relative
                if target.exists():
                    remove_tree(target)
                shutil.copytree(old, target)
                verify_tree(old, target)
        verify_tree(source, stage)
        # Flush copied file bytes before replacing the visible directory.
        for p in stage.rglob('*'):
            if p.is_file():
                with p.open('rb') as f:
                    os.fsync(f.fileno())
        if destination.exists():
            destination.rename(backup)
        try:
            stage.rename(destination)
        except BaseException:
            if backup.exists():
                backup.rename(destination)
            raise
    finally:
        if stage.exists():
            remove_tree(stage)
    verify_tree(source, destination)
    strip_appledouble(destination, [p.relative_to(source) for p in source.rglob('*')])
    strip_appledouble(destination.parent, [destination.name])
    if backup.exists():
        print(f'Previous version retained: {backup}')
    print(f'Installed and SHA-256 verified: {destination}')
    return destination


def card_root(value):
    card = Path(value).resolve()
    if not card.is_dir() or not (card / 'Apps').is_dir() or not (card / 'Roms').is_dir():
        raise ValueError('Expected the root of a mounted TrimUI SD card (Apps and Roms folders).')
    if (card / 'Apps').is_symlink():
        raise ValueError('Apps must be a normal directory')
    return card


def validate_app(app):
    app = Path(app).resolve()
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', app.name) or app.name in ('esp32','starfall'):
        raise ValueError('Use a folder ID of 1-48 lowercase letters/digits/hyphens; start with a letter.')
    manifest = json.loads((app / 'app.json').read_text())
    if not isinstance(manifest, dict) or manifest.get('ready') not in (None, 'file'):
        raise ValueError('app.json must be an object; readiness must be "file" or omitted.')
    for name, limit in (('name', 90), ('description', 240)):
        value = manifest.get(name)
        if not isinstance(value, str) or not value or len(value) > limit:
            raise ValueError(f'app.json {name} must contain 1-{limit} characters')
        if any(ord(c) < 32 or ord(c) > 126 or c in '\\"' for c in value):
            raise ValueError(f'app.json {name}: use printable ASCII without quotes or backslashes')
    if not (app / 'launch.sh').is_file():
        raise ValueError('Missing launch.sh')
    safe_tree(app)
    return app


def new_app(path, name=None):
    app = Path(path).absolute()
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', app.name) or app.name in ('esp32', 'starfall'):
        raise ValueError('Use a new folder ID starting with a letter, followed by lowercase letters/digits/hyphens.')
    title = name or app.name.replace('-', ' ').title()
    if not 1 <= len(title) <= 90 or any(ord(c) < 32 or ord(c) > 126 or c in '\\"' for c in title):
        raise ValueError('Use a 1-90 character printable ASCII name without quotes or backslashes.')
    if app.exists():
        raise ValueError(f'App folder already exists; nothing overwritten: {app}')
    shutil.copytree(ROOT/'templates/native-app', app,
                    ignore=shutil.ignore_patterns('app','app.incoming','cover.bmp','data','.DS_Store','._*','__pycache__'))
    manifest = {'name': title, 'description': 'An independent PocketLAB mini app.', 'ready': 'file'}
    (app/'app.json').write_text(json.dumps(manifest, indent=2)+'\n')
    code = (app/'app.c').read_text().replace('My app', title).replace('YOUR MINI APP', title.upper())
    (app/'app.c').write_text(code)
    write_cover(app/'cover.bmp', app.name, title)
    print(f'Created {app}\nEdit app.c and app.json; then run:')
    import shlex
    print('python3 '+shlex.quote(str(ROOT/'tools/pocketlab.py'))+' run '+shlex.quote(str(app))+' --usb')
    return app


def build_app(app, host=False, serial=None):
    app = validate_app(app)
    ensure_cover(app)
    if not (app / 'app.c').is_file():
        raise ValueError('The starter build expects app.c; use your own build for other languages/layouts.')
    sources = [p for p in sorted(app.rglob('*.c'))
               if not any(part.startswith('.') or part in ('build','data') for part in p.relative_to(app).parts)]
    sources += [ROOT/'src/ui.c', ROOT/'src/usb.c']
    if host:
        flags = subprocess.check_output(['sdl2-config','--cflags','--libs'],text=True).split()
        subprocess.run(['clang','-std=gnu11','-O2','-Wall','-Wextra','-I'+str(ROOT/'src'),
                        '-I'+str(app),*map(str,sources),
                        *flags,*(['-framework','IOKit','-framework','CoreFoundation'] if sys.platform == 'darwin' else []),'-lm','-lpthread',
                        '-o',str(app/'app')],check=True)
    else:
        compile_arm(sources, app/'app', includes=(ROOT/'src',app), serial=serial)
    print(f'Built {"native preview" if host else "Brick ARM64"}: {app / "app"}')


def ensure_cover(app):
    """Backfill legacy packages while preserving any author-provided artwork."""
    manifest = json.loads((app/'app.json').read_text())
    if write_cover(app/'cover.bmp', app.name, manifest['name']):
        print(f'Created library artwork: {app / "cover.bmp"}')


def package():
    """Stage the bundled, verified release; installation never needs a compiler."""
    from release import RUNTIME, verify_runtime
    verify_runtime()
    folder = ROOT/'build/release/Apps/PocketLab'
    if folder.exists(): shutil.rmtree(folder)
    shutil.copytree(RUNTIME, folder)
    (folder/'apps').mkdir()
    (folder/'data').mkdir()
    return folder


def transport(parser):
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--sd');choice.add_argument('--usb',action='store_true')
    parser.add_argument('--serial')


def app_fingerprint(app):
    paths=[p for p in app.rglob('*') if p.is_file() and p.name not in ('app','app.incoming','.DS_Store') and not any(part.startswith('.') or part in ('__pycache__','build','data') for part in p.relative_to(app).parts)]
    paths += [ROOT/'src'/n for n in ('ui.c','ui.h','usb.c','usb.h','app.h')]
    return tuple((str(p),digest(p)) for p in sorted(paths))


def watch_app(app,serial):
    last=None;retry=False
    print('Watching source edits. Ctrl-C stops watching; the app keeps running on the Brick.',flush=True)
    while True:
        current=app_fingerprint(app)
        if current!=last or retry:
            time.sleep(.5)
            stable=app_fingerprint(app)
            if stable!=current:continue
            try:
                build_app(app,serial=serial)
            except (subprocess.CalledProcessError, ValueError):
                print('Build failed; installed app is unchanged. Waiting for your next edit.',flush=True)
                last=current;retry=False;continue
            try:
                Brick(serial).deploy(app)
                last=current;retry=False
                print('Live update complete. Waiting for edits.',flush=True)
            except AppLaunchError as e:
                print(f'App update failed: {e} Waiting for your next edit.',flush=True)
                last=current;retry=False
            except USBError as e:
                print(f'USB update pending: {e} Retrying in 5 seconds.',flush=True)
                retry=True;time.sleep(5)
        time.sleep(.5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('new',help='Create a ready-to-edit independent mini app');p.add_argument('app');p.add_argument('--name')
    p=commands.add_parser('setup',help='Guided first installation or SDK setup')
    route=p.add_mutually_exclusive_group();route.add_argument('--sdk',action='store_true');route.add_argument('--sd');route.add_argument('--usb',action='store_true')
    p.add_argument('--serial');p.add_argument('--confirm-model',choices=['TG4040'])
    p.add_argument('--eject', action='store_true', help='Eject the selected --sd card after successful setup')
    p=commands.add_parser('build-shell');p.add_argument('--serial')
    commands.add_parser('package')
    p=commands.add_parser('install'); transport(p);p.add_argument('--confirm-model',choices=['TG4040'])
    p=commands.add_parser('cards',help='List mounted SD cards and the command that sets each one up');p.add_argument('--json',action='store_true')
    p=commands.add_parser('doctor');route=p.add_mutually_exclusive_group();route.add_argument('--sd');route.add_argument('--usb',action='store_true');p.add_argument('--serial');p.add_argument('--json',action='store_true')
    p = commands.add_parser('prepare-card', help='Prepare a blank FAT32 card or resume an interrupted copy')
    p.add_argument('--sd', required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--new-card', action='store_true', help='Start on a blank card or continue its saved setup')
    mode.add_argument('--resume', action='store_true', help='Resume a saved setup or complete an older interrupted stock copy')
    p.add_argument('--eject', action='store_true', help='Eject the card after successful preparation')
    p=commands.add_parser('format-card');p.add_argument('--disk',required=True);p.add_argument('--confirm-erasure')
    p=commands.add_parser('recover');transport(p);p.add_argument('--backup')
    p=commands.add_parser('backups');p.add_argument('--sd',required=True);p.add_argument('--prune',action='store_true');p.add_argument('--keep',type=int,default=2)
    p=commands.add_parser('build-app');p.add_argument('app');p.add_argument('--host',action='store_true');p.add_argument('--serial')
    p=commands.add_parser('deploy-app');p.add_argument('app');transport(p)
    for name in ('run','watch'):
        p=commands.add_parser(name);p.add_argument('app');p.add_argument('--usb',action='store_true',required=True);p.add_argument('--serial')
    p=commands.add_parser('open');p.add_argument('app');p.add_argument('--usb',action='store_true',required=True);p.add_argument('--serial')
    for name in ('status','library','logs'):
        p=commands.add_parser(name);p.add_argument('--usb',action='store_true',required=True);p.add_argument('--serial')
    args=parser.parse_args()
    if args.command=='new':new_app(args.app,args.name)
    elif args.command=='setup':
        from onboarding import bundled_runtime, guided_setup, setup_card
        if args.eject and not args.sd:
            parser.error('setup --eject requires --sd PATH')
        if args.sdk:setup(args.serial);print('SDK ready. Subsequent builds work offline without a connected device.')
        elif args.sd:setup_card(args.sd, eject=args.eject)
        elif args.usb:Brick(args.serial,require_install=False,confirm_model=args.confirm_model).install_shell(bundled_runtime())
        else:guided_setup()
    elif args.command=='prepare-card':
        from onboarding import prepare_card
        prepare_card(args.sd, args.new_card, resume=args.resume, eject=args.eject)
    elif args.command=='format-card':
        from onboarding import format_card
        print(json.dumps(format_card(args.disk,args.confirm_erasure),indent=2))
    elif args.command=='recover':
        if args.usb:Brick(args.serial).recover_shell()
        else:
            from maintenance import restore_card
            from onboarding import mounted_card, recheck_card
            card = mounted_card(args.sd)
            with card.lock():
                recheck_card(card)
                restore_card(card.root, args.backup, check_mount=card.check_mount)
    elif args.command=='backups':
        from maintenance import backups
        if args.prune:
            from onboarding import mounted_card, recheck_card
            card = mounted_card(args.sd)
            with card.lock():
                recheck_card(card)
                result = backups(card.root, True, args.keep)
        else:
            result = backups(args.sd, False, args.keep)
        print(json.dumps(result, indent=2))
    elif args.command=='build-shell':build_shell(args.serial)
    elif args.command=='package':print(f'Package: {package()}')
    elif args.command=='build-app':build_app(args.app,args.host,args.serial)
    elif args.command=='install' and args.usb:
        from onboarding import bundled_runtime
        Brick(args.serial, require_install=False, confirm_model=args.confirm_model).install_shell(bundled_runtime())
    elif args.command in ('run','watch'):
        app=validate_app(args.app)
        if args.command=='run':build_app(app,serial=args.serial);Brick(args.serial).deploy(app)
        else:
            try:
                watch_app(app, args.serial)
            except KeyboardInterrupt:
                print('\nStopped watching. The installed app remains available.')
    elif args.command in ('status','library','logs','open'):
        brick=Brick(args.serial)
        if args.command=='status':print(json.dumps(brick.status(),indent=2))
        elif args.command=='logs':print(brick.remote('tail -n 80 /mnt/SDCARD/Apps/PocketLab/data/pocketlab.log'))
        else:print(brick.request('launch',args.app) if args.command=='open' else brick.request('library'))
    elif args.command=='install':
        from onboarding import setup_card
        setup_card(args.sd, allow_resume=False)
    elif args.command=='deploy-app':
        app=validate_app(args.app)
        ensure_cover(app)
        # Reject the common mistake of copying the Mac preview to the Brick.
        executable=app/'app'
        if executable.exists():
            with executable.open('rb') as f: header=f.read(20)
            if header[:5]!=b'\x7fELF\x02' or header[18:20]!=b'\xb7\0':
                raise ValueError('app is not an ARM64 Linux ELF binary. Run build-app without --host first.')
        if args.usb:Brick(args.serial).deploy(app);return
        from card_io import check_directory
        from onboarding import mounted_card, recheck_card
        card = mounted_card(args.sd)
        with card.lock():
            recheck_card(card)
            dest = card_root(card.root)/'Apps/PocketLab'
            if not check_directory(dest) or not (dest/'pocketlab').is_file():
                raise ValueError('Install PocketLAB first')
            check_directory(dest/'apps')
            install_tree(app, dest/'apps'/app.name)
        print('Safely eject the card, then open PocketLAB. The library discovers the app automatically.')
    elif args.command=='cards':
        from onboarding import list_cards
        sys.exit(list_cards(args.json))
    elif args.command=='doctor':
        from onboarding import diagnostics, show_diagnostics
        sys.exit(show_diagnostics(diagnostics(args.sd,args.usb,args.serial),args.json))


if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:
        print('\nPocketLAB operation interrupted.', file=sys.stderr)
        sys.exit(130)
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as e:
        print(f'PocketLAB: {e}',file=sys.stderr)
        from onboarding import access_hint
        if access_hint(e):print(access_hint(e),file=sys.stderr)
        sys.exit(1)
