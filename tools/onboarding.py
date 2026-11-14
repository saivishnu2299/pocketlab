"""Computer-side installation, diagnostics and explicitly requested card setup."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time

from card_io import check_directory, exclusive_lock, file_stat, flush_writes, remove_tree, strip_appledouble
from stock_card import WORK, card_entries, prepare_tree, stock_base

ROOT = Path(__file__).resolve().parents[1]


def run_json(command):
    return json.loads(subprocess.check_output(command,text=True,timeout=15))


def disk_info(device):
    if platform.system() != 'Darwin':
        raise ValueError('Automatic formatting is available on macOS. On Linux, format the chosen card using your disk utility, then use prepare-card.')
    if not re.fullmatch(r'/dev/disk[0-9]+', device):
        raise ValueError('Choose a whole external disk, for example /dev/disk4; partition paths are refused.')
    info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',device],timeout=15))
    physical=plistlib.loads(subprocess.check_output(['diskutil','list','-plist','external','physical'],timeout=15))
    identifiers={x['DeviceIdentifier'] for x in physical.get('AllDisksAndPartitions',[])}
    if info.get('DeviceIdentifier') not in identifiers or info.get('Internal') is not False or info.get('WholeDisk') is not True:
        raise ValueError('Refusing a system, internal, virtual, or non-physical disk.')
    if info.get('Writable') is not True or info.get('TotalSize',0) <= 0:
        raise ValueError('The selected disk is not writable.')
    identity={key:info.get(key) for key in ('DeviceIdentifier','MediaName','TotalSize','DeviceTreePath','DiskUUID','BusProtocol')}
    identity['device']=device
    identity['confirmation']='ERASE-'+hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    return identity


def format_card(device, confirmation=None, *, stock=None):
    identity=disk_info(device)
    if confirmation is None:
        return {'action':'format-plan','disk':identity,'filesystem':'FAT32','partition_scheme':'MBR',
                'next':'Re-run format-card with --confirm-erasure and the displayed confirmation after checking the card.'}
    if confirmation != identity['confirmation']:
        raise ValueError('Erasure confirmation does not match this disk. Nothing changed.')
    # Resolve downloads/runtime before erasing, and recheck identity afterwards.
    from release import verify_runtime

    with exclusive_lock(Path(device).name):
        verify_runtime()
        if stock is None:
            stock_base()
        if disk_info(device) != identity:
            raise ValueError('Disk identity changed during preparation. Nothing erased.')
        subprocess.run(['diskutil', 'eraseDisk', 'FAT32', 'POCKETLAB', 'MBRFormat', device], check=True)
    return {'action':'formatted','disk':identity,'next':'Run prepare-card on the newly mounted POCKETLAB volume.'}


@dataclass(frozen=True)
class MountedCard:
    root: Path
    device: str
    whole_disk: str
    identity: str
    label: str
    capacity: int
    fat32: bool
    device_number: int

    def lock(self):
        key = Path(self.whole_disk).name if self.whole_disk else f'volume-{self.device_number}'
        return exclusive_lock(key)

    def check_mount(self):
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_dev != self.device_number:
            raise ValueError('The selected card mount changed. Reconnect the card and retry.')


def mac_disk_info(path):
    return plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', str(path)], timeout=15))


def mounted_card(value, require_fat=False):
    supplied = Path(value).absolute()
    if supplied.is_symlink():
        raise ValueError('Choose the actual card mount, not a symlink.')
    path = supplied.resolve()
    if path == Path('/') or not path.is_dir() or not path.is_mount():
        raise ValueError('Choose the root of a mounted SD card.')
    if Path.home().resolve().is_relative_to(path) or ROOT.is_relative_to(path):
        raise ValueError('The project or home disk cannot be prepared as a card.')
    number = path.stat().st_dev
    system = platform.system()
    if system == 'Darwin':
        info = mac_disk_info(path)
        if info.get('Internal') is not False or info.get('MountPoint') != str(path):
            raise ValueError('Choose a mounted external SD card.')
        if info.get('WritableVolume') is False:
            raise ValueError('The card is read-only. Check the reader or write-protect switch.')
        device = '/dev/'+info['DeviceIdentifier']
        whole = '/dev/'+(info.get('ParentWholeDisk') or info['DeviceIdentifier'])
        uuid = info.get('VolumeUUID')
        label = info.get('VolumeName') or path.name
        size = info.get('TotalSize', 0)
        fat32 = info.get('FilesystemType') == 'msdos' and 'FAT32' in info.get('FilesystemName', '')
    elif system == 'Linux':
        result = run_json(['findmnt', '--json', '--bytes', '--target', str(path),
                           '--output', 'TARGET,SOURCE,FSTYPE,UUID,SIZE,OPTIONS'])
        filesystems = result.get('filesystems', [])
        if not filesystems or filesystems[0]['target'] != str(path):
            raise ValueError('Choose the root of a mounted SD card.')
        info = filesystems[0]
        if 'ro' in info.get('options', '').split(','):
            raise ValueError('The card is read-only. Check the reader or write-protect switch.')
        device, whole, uuid = info['source'], '', info.get('uuid')
        label, size, fat32 = path.name, int(info.get('size') or 0), info['fstype'] == 'vfat'
    else:
        raise ValueError('Card setup supports macOS and Linux.')
    if require_fat and not fat32:
        raise ValueError('New-card preparation requires a mounted FAT32 card.')
    card = MountedCard(path, device, whole, f'{system}:{uuid or device}', label, size, fat32, number)
    card.check_mount()
    return card


def card_mode(card):
    root = card.root
    if check_directory(root/WORK):
        return 'resume'
    if (root/'Apps').is_dir() and not (root/'Apps').is_symlink() and (root/'Roms').is_dir():
        return 'install'
    if card.fat32 and not card_entries(root):
        return 'prepare'
    return 'unknown'


def discover_cards():
    """List mounted external candidates. An explicit mount also works."""
    system = platform.system()
    if system == 'Darwin':
        inventory = plistlib.loads(subprocess.check_output(
            ['diskutil', 'list', '-plist', 'external', 'physical'], timeout=15))
        mounts = [entry['MountPoint']
                  for disk in inventory['AllDisksAndPartitions']
                  for entry in (disk, *disk.get('Partitions', []))
                  if entry.get('MountPoint')]
    elif system == 'Linux':
        inventory = run_json(['lsblk', '-J', '-p', '-o', 'TYPE,TRAN,RM,HOTPLUG,MOUNTPOINTS'])

        def removable_mounts(devices, removable=False):
            for device in devices:
                external = removable or (device['type'] == 'disk' and (
                    device.get('tran') in ('usb', 'mmc') or device.get('rm') or device.get('hotplug')))
                if external:
                    yield from (path for path in device.get('mountpoints') or [] if path)
                yield from removable_mounts(device.get('children', []), external)

        mounts = list(removable_mounts(inventory['blockdevices']))
    else:
        return []

    cards = []
    for path in dict.fromkeys(mounts):
        try:
            cards.append(mounted_card(path))
        except (OSError, ValueError, subprocess.CalledProcessError):
            continue
    return cards


MAC_ACCESS_HINT = ('macOS is blocking access to removable volumes for this terminal or agent app. '
                   'Open System Settings > Privacy & Security > Files & Folders (or Full Disk Access), '
                   'allow the app running this command to use Removable Volumes, then retry.')


def access_hint(exc):
    """Explain the macOS privacy refusal that otherwise looks like a broken card."""
    if platform.system() == 'Darwin' and isinstance(exc, PermissionError):
        return MAC_ACCESS_HINT
    return None


def card_report(card):
    """Describe one mounted card and the single command that sets it up."""
    path = shlex.quote(str(card.root))
    report = {'path': str(card.root), 'label': card.label, 'capacity_bytes': card.capacity,
              'fat32': card.fat32, 'state': None, 'installed_version': None, 'next': None, 'note': ''}
    try:
        mode = card_mode(card)
        if mode == 'install':
            info = card.root/'Apps/PocketLab/build-info.json'
            if check_directory(card.root/'Apps/PocketLab') and file_stat(info):
                report['installed_version'] = json.loads(info.read_text()).get('version')
            elif check_directory(card.root/'Apps/PocketLab'):
                report['installed_version'] = 'unknown'
    except (OSError, ValueError) as exc:
        report.update(state='unreadable', note=access_hint(exc) or f'Cannot read the card: {exc}')
        return report
    if mode == 'install':
        report.update(state='stock-with-pocketlab' if report['installed_version'] else 'stock',
                      next=f'./pocketlab setup --sd {path} --eject',
                      note='Installs or updates only Apps/PocketLab; games, saves and other apps stay untouched.')
    elif mode == 'resume':
        report.update(state='unfinished-preparation', next=f'./pocketlab setup --sd {path} --eject',
                      note='Resumes an interrupted new-card preparation.')
    elif mode == 'prepare':
        report.update(state='blank', next=f'./pocketlab prepare-card --sd {path} --new-card --eject',
                      note='Downloads the official TrimUI SD base (about 400 MiB) and copies 1.6 GiB; slow cards can take up to an hour.')
    else:
        report.update(state='not-a-trimui-card',
                      note='No stock Apps and Roms folders. Choose another card; setup never erases one automatically.')
    return report


def list_cards(as_json=False):
    reports = [card_report(card) for card in discover_cards()]
    if as_json:
        print(json.dumps({'cards': reports}, indent=2))
        return 0 if reports else 1
    if not reports:
        print('No mounted external SD card found. Put the Brick\'s SD card in this computer\'s card reader.')
        if platform.system() == 'Darwin':
            print('If the card is visible in Finder, the cause may be macOS privacy settings: ' + MAC_ACCESS_HINT)
        return 1
    for report in reports:
        print(f"{report['label']} ({report['capacity_bytes'] / 10**9:.1f} GB) at {report['path']}")
        version = f" {report['installed_version']}" if report['installed_version'] else ''
        print(f"  state: {report['state']}{version}")
        if report['next']:
            print(f"  next:  {report['next']}")
        if report['note']:
            print(f"  note:  {report['note']}")
    return 0


def recheck_card(card):
    if mounted_card(card.root) != card:
        raise ValueError('The selected card mount changed. Reconnect the card and retry.')


def finish_card(card, eject=False):
    if eject:
        with card.lock():
            recheck_card(card)
            command = (['diskutil', 'eject', card.whole_disk] if platform.system() == 'Darwin'
                       else ['umount', '--', str(card.root)])
            # Spotlight often indexes a freshly written card and briefly blocks the unmount.
            for delay in (0, 3, 5, 8):
                time.sleep(delay)
                try:
                    result = subprocess.run(command, capture_output=True, text=True)
                except OSError as exc:
                    result = subprocess.CompletedProcess(command, 1, '', str(exc))
                if result.returncode == 0:
                    break
            else:
                print('Setup finished and verified, but the computer is still using the card: '
                      + (result.stderr or result.stdout).strip().splitlines()[0]
                      + '\nEject the card in your file manager before removing it.', file=sys.stderr, flush=True)
                return
        print('Card ejected and ready to remove. Insert it into the powered-off Brick, then open Apps → PocketLAB.', flush=True)
    else:
        print('Safely eject the card, then open Apps → PocketLAB on the Brick.', flush=True)


def setup_card(value, *, eject=False, selected=None, allow_resume=True):
    from card_runtime import install_runtime
    from pocketlab import card_root

    card = selected or mounted_card(value)
    mode = card_mode(card)
    if mode == 'resume':
        if not allow_resume:
            raise ValueError('This card has unfinished setup. Run setup --sd CARD to resume.')
        return prepare_card(card.root, resume=True, eject=eject, selected=card)
    if mode == 'prepare':
        raise ValueError(f'This card is blank. Run prepare-card --sd {shlex.quote(str(card.root))} --new-card.')
    if mode != 'install':
        raise ValueError('This card is missing the stock Apps or Roms folder. Use setup for card preparation options.')
    runtime = bundled_runtime()
    with card.lock():
        recheck_card(card)
        if card_mode(card) != 'install':
            raise ValueError('Card contents changed while selecting setup. Rerun setup.')
        install_runtime(runtime, card_root(card.root)/'Apps/PocketLab', card.check_mount)
    finish_card(card, eject)


def prepare_card(value, new_card=False, *, resume=False, eject=False, selected=None, stock=None):
    from card_runtime import install_runtime

    if not new_card and not resume:
        raise ValueError('Use --new-card for a blank card or --resume for an interrupted stock copy.')
    card = selected or mounted_card(value, require_fat=True)
    if not card.fat32:
        raise ValueError('New-card preparation requires a mounted FAT32 card.')
    with card.lock():
        recheck_card(card)
        saved = check_directory(card.root/WORK)
        if not saved and card_entries(card.root) and not resume:
            raise ValueError('This card is not empty. Use setup --sd for a working card or --resume for an interrupted stock copy.')
        if resume and not saved and not card_entries(card.root):
            raise ValueError('This card is blank. Use --new-card to start preparation.')
        runtime = bundled_runtime()
        try:
            stock = stock if stock is not None else stock_base()
            recheck_card(card)
            work = prepare_tree(stock, card.root, identity=card.identity, resume=resume, check_mount=card.check_mount)
            install_runtime(runtime, card.root/'Apps/PocketLab', card.check_mount)
            card.check_mount()
            remove_tree(work)
            strip_appledouble(card.root, [WORK])
            flush_writes()
        except (KeyboardInterrupt, OSError, ValueError, subprocess.CalledProcessError):
            flag = '--resume' if resume else '--new-card'
            print(f'To retry card preparation, run: ./pocketlab prepare-card --sd {shlex.quote(str(card.root))} {flag}',
                  file=sys.stderr, flush=True)
            raise
    finish_card(card, eject)


def diagnostics(sd=None, usb=False, serial=None):
    from release import verify_runtime
    checks=[]
    def add(name,ok,detail,action=''):
        checks.append({'name':name,'ok':bool(ok),'detail':detail,'action':action})
    python = platform.python_version()
    if sys.version_info < (3, 12):
        python += ' (card setup OK; building mini apps needs Python 3.12+)'
    add('python', sys.version_info >= (3, 9), python, 'Install Python 3.9 or newer; mini-app builds need 3.12+.')
    add('host',platform.system() in ('Darwin','Linux') and platform.machine() in ('arm64','aarch64','AMD64','x86_64'),platform.system()+' '+platform.machine(),'Use a supported macOS/Linux host; see docs/COMPATIBILITY.md.')
    try:verify_runtime();add('runtime',True,'Bundled ARM64 runtime and source hashes match.')
    except (ValueError,OSError,KeyError) as e:add('runtime',False,str(e),'Use the complete source release or rebuild its runtime.')
    if sd:
        try:
            from card_runtime import PACKAGE_ID, file_hash, package_id, pending_update, runtime_files
            from pocketlab import card_root

            root = Path(sd).resolve()
            if check_directory(root/WORK):
                add('card', False, 'Stock-card preparation is unfinished.', 'Run setup --sd CARD to resume.')
            else:
                card = card_root(root)
                dest = card/'Apps/PocketLab'
                if not check_directory(dest) or package_id(dest) != PACKAGE_ID:
                    raise ValueError('PocketLAB is missing or its package identity does not match.')
                pending = pending_update(dest)
                if pending and pending[1] != 'ready':
                    add('card', False, 'A PocketLAB runtime update needs recovery.', 'Run recover --sd CARD.')
                else:
                    for name, checksum in runtime_files(dest).items():
                        if file_hash(dest, name) != checksum:
                            raise ValueError('Installed file differs: '+name)
                    detail = f'Installed files verified; {shutil.disk_usage(card).free//(1024**2)} MiB free.'
                    if pending:
                        detail += ' Open PocketLAB on the Brick to finish the update.'
                    elif runtime_files(dest) != runtime_files(bundled_runtime()):
                        detail += ' A newer bundled runtime is available: run setup --sd CARD to update.'
                    add('card', True, detail)
        except (ValueError, OSError, KeyError) as exc:
            add('card', False, str(exc), 'Run setup --sd with the mounted card root.')
    if usb:
        try:
            from usb_deploy import Brick
            brick=Brick(serial)
            state=brick.status(required=False)
            add('usb',True,'Stock ARM64 TrimUI with PocketLAB connected.')
            add('controller',state is not None,'Running' if state else 'Not running','Open Apps → PocketLAB; keep USB Storage closed.')
        except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as e:
            add('usb',False,str(e),'Use a data cable in the bottom USB-C port, wake the Brick, and check adb devices.')
    return {'ok':all(c['ok'] for c in checks),'checks':checks,'sdk_cached':(ROOT/'build/toolchain/sdl-imports/source.json').is_file()}


def show_diagnostics(result, as_json=False):
    if as_json:print(json.dumps(result,indent=2))
    else:
        for c in result['checks']:
            print(('OK   ' if c['ok'] else 'FIX  ')+c['name']+': '+c['detail'])
            if not c['ok'] and c['action']:print('     '+c['action'])
    return 0 if result['ok'] else 1


def guided_setup():
    if not sys.stdin.isatty():
        raise ValueError('Choose setup --sd PATH, setup --usb, or setup --sdk. Run ./pocketlab setup in a terminal for guided setup.')
    labels = {'install': 'Install or verify PocketLAB', 'prepare': 'Prepare new FAT32 card',
              'resume': 'Resume card preparation', 'unknown': 'Check card options'}
    print('PocketLAB setup')
    try:
        cards = discover_cards()
    except (OSError, ValueError, subprocess.CalledProcessError):
        cards = []
    if not cards:
        print('No mounted external cards detected.')
    for index, card in enumerate(cards, 1):
        label = labels[card_mode(card)]
        print(f'{index}. {card.label} ({card.capacity / 10**9:.1f} GB, {card.root}) — {label}')
    print('m. Enter the path to a mounted card')
    print('u. Install over USB')
    print('s. Set up the development SDK')
    if platform.system() == 'Darwin':
        print('f. Format a new card (erases the selected disk)')
    choice = input('Choose a card or option [1]: ' if len(cards) == 1 else 'Choose a card or option: ').strip().lower()
    if not choice and len(cards) == 1:
        choice = '1'

    if choice == 'u':
        from usb_deploy import Brick
        model = input('Enter TG4040 after checking the device is a Brick Pro: ').strip()
        Brick(require_install=False, confirm_model=model).install_shell(bundled_runtime())
        return
    if choice == 's':
        from native_build import setup
        setup()
        print('SDK ready. Create your app with ./pocketlab new miniapps/my-app --name "My app"')
        return
    if choice == 'f' and platform.system() == 'Darwin':
        subprocess.run(['diskutil', 'list', 'external', 'physical'], check=True)
        device = input('Whole SD disk path: ').strip()
        plan = format_card(device)
        print(json.dumps(plan, indent=2))
        answer = input('Enter the displayed ERASE token to erase that disk, or Enter to cancel: ').strip()
        if not answer:
            print('Formatting cancelled.')
            return
        if answer != plan['disk']['confirmation']:
            raise ValueError('Erasure confirmation does not match this disk. Nothing changed.')
        stock = stock_base()
        format_card(device, answer, stock=stock)
        matches = [card for card in discover_cards() if card.whole_disk == device and card.fat32]
        if len(matches) != 1:
            print('After the formatted card mounts, run ./pocketlab prepare-card --sd CARD --new-card.')
            return
        card = matches[0]
        prepare_card(card.root, new_card=True, selected=card, stock=stock)
    else:
        if choice == 'm':
            card = mounted_card(input('Mounted card path: ').strip())
        elif choice.isascii() and choice.isdecimal() and 1 <= int(choice) <= len(cards):
            card = cards[int(choice)-1]
        else:
            raise ValueError('Choose a listed card or option.')
        mode = card_mode(card)
        if mode == 'install':
            setup_card(card.root, selected=card)
        elif mode == 'prepare':
            print('This blank card needs the stock TrimUI files (about 1.6 GiB once extracted).')
            if input('Prepare this card now? [y/N]: ').strip().lower() not in ('y', 'yes'):
                return
            prepare_card(card.root, new_card=True, selected=card)
        elif mode == 'resume':
            prepare_card(card.root, resume=True, selected=card)
        else:
            path = shlex.quote(str(card.root))
            raise ValueError(f'Card layout is incomplete or unsupported. For an interrupted stock copy, run prepare-card --sd {path} --resume.')
    if input(f'Eject {card.label} now? [y/N]: ').strip().lower() in ('y', 'yes'):
        finish_card(card, eject=True)


def bundled_runtime():
    from release import RUNTIME, verify_runtime
    verify_runtime()
    return RUNTIME
