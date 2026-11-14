"""Prepare and resume the pinned TrimUI stock-card copy."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.request

from card_io import check_directory, exclusive_lock, file_stat, flush_writes, write_record
from release import digest

ROOT = Path(__file__).resolve().parents[1]
BASE = {
    'version': 'v1.0.0-20260626',
    'name': 'trimui_brick_pro_tg4040_sd_base_20260626.7z',
    'sha256': 'bf029612fab90bb427c54c11a816f862c2bbf33e3d64e5830c38e8fc1b9fc8eb',
    'url': 'https://github.com/trimui/assets_brickpro/releases/download/v1.0.0-20260626/trimui_brick_pro_tg4040_sd_base_20260626.7z',
}
IGNORED_CARD_ENTRIES = {'.DS_Store', '.Spotlight-V100', '.Trashes', '.fseventsd', 'System Volume Information'}
WORK = '.pocketlab-preparing'
MIB = 1024 * 1024
CHUNK = MIB


@dataclass(frozen=True)
class Stock:
    root: Path
    directories: tuple[str, ...]
    files: dict[str, tuple[int, str]]

    @property
    def fingerprint(self):
        record = (BASE['sha256'], self.directories, self.files)
        return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


class Progress:
    def __init__(self, label, size, files=None):
        self.label = label
        self.size = size
        self.files = files
        self.bytes_done = self.files_done = 0
        self.start = self.last = time.monotonic()
        self.report(force=True)

    def advance(self, size=0, files=0):
        self.bytes_done += size
        self.files_done += files
        self.report()

    def report(self, force=False):
        now = time.monotonic()
        if not force and now - self.last < 2:
            return
        self.last = now
        message = f'{self.label}: {self.bytes_done / MIB:.1f}'
        if self.size is not None:
            message += f' / {self.size / MIB:.1f}'
        message += ' MiB'
        if self.files is not None:
            message += f', {self.files_done:,} / {self.files:,} files'
        elapsed = now - self.start
        if elapsed >= 2 and self.bytes_done:
            rate = self.bytes_done / elapsed
            message += f', {rate / MIB:.2f} MiB/s'
            eta = max(0, ((self.size or 0) - self.bytes_done) / rate)
            if self.files and self.files_done:
                eta = max(eta, (self.files - self.files_done) * elapsed / self.files_done)
            if eta > 0 and (self.files is None or self.files_done > 0):
                message += f', about {max(1, round(eta))}s left'
        print(message, flush=True)


def transfer(reader, progress, writer=None):
    """Hash the bytes while reading or copying, in bounded chunks."""
    checksum = hashlib.sha256()
    while chunk := reader.read(CHUNK):
        if writer is not None:
            writer.write(chunk)
        checksum.update(chunk)
        progress.advance(size=len(chunk))
    return checksum.hexdigest()


def mac_metadata(name):
    return name == '.DS_Store' or name.startswith('._')


def inventory(root, *, ignore_metadata=False):
    directories = []
    files = {}

    def walk(directory, parent=''):
        with os.scandir(directory) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                name = f'{parent}{entry.name}'
                if stat.S_ISDIR(info.st_mode):
                    directories.append(name)
                    walk(entry.path, name+'/')
                elif not stat.S_ISREG(info.st_mode):
                    raise ValueError(f'Expected ordinary stock files: {entry.path}')
                elif not ignore_metadata or not mac_metadata(entry.name):
                    files[name] = info

    walk(root)
    return tuple(sorted(directories)), dict(sorted(files.items()))


def stock_from_directory(root, hashes=None):
    check_directory(root)
    directories, files = inventory(root)
    if hashes is None:
        hashes = {name: digest(root/name) for name in files}
    if not isinstance(hashes, dict) or hashes.keys() != files.keys() or any(
        not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for value in hashes.values()
    ):
        raise ValueError('The extracted stock cache differs from its manifest. Recreate build/stock-base and retry.')
    for name in (*directories, *files):
        lowered = name.casefold()
        if lowered == WORK or lowered.startswith((WORK+'/', 'apps/pocketlab/')) or lowered == 'apps/pocketlab':
            raise ValueError('The stock files overlap the PocketLAB installation or preparation directory.')
    return Stock(root, directories, {name: (info.st_size, hashes[name]) for name, info in files.items()})


def download_stock(archive):
    print(f'Downloading the official TrimUI SD base ({BASE["version"]}).', flush=True)
    with tempfile.TemporaryDirectory(prefix='.download-', dir=archive.parent) as temporary:
        part = Path(temporary)/'stock.part'
        with urllib.request.urlopen(BASE['url'], timeout=60) as response, part.open('xb') as out:
            length = response.headers.get('Content-Length', '')
            progress = Progress('Downloading stock files', int(length) if length.isdecimal() else None)
            actual = transfer(response, progress, out)
        progress.report(force=True)
        if actual != BASE['sha256']:
            raise ValueError('Stock base download checksum mismatch.')
        part.replace(archive)


def stock_base():
    """Verify the vendor archive once and reuse the stock file hash manifest."""
    cache = ROOT/'build/downloads'
    cache.mkdir(parents=True, exist_ok=True)
    with exclusive_lock('stock-' + hashlib.sha256(os.fsencode(cache.resolve())).hexdigest()):
        archive = cache/BASE['name']
        if not file_stat(archive):
            download_stock(archive)
        else:
            print('Checking the cached TrimUI download…', flush=True)
            if digest(archive) != BASE['sha256']:
                raise ValueError('Stock base checksum mismatch. Remove the cached archive and retry.')
        base = ROOT/'build/stock-base'
        marker = ROOT/'build/stock-base.sha256'
        file_record = ROOT/'build/stock-base.files.json'
        if (check_directory(base) and file_stat(marker) and file_stat(file_record)
                and marker.read_text().strip() == BASE['sha256']):
            print('Reading the stock file manifest…', flush=True)
            return stock_from_directory(base, json.loads(file_record.read_text()))

        extractor = shutil.which('bsdtar')
        if not extractor:
            raise ValueError('Stock base extraction needs bsdtar (included in macOS; Linux package: libarchive-tools).')
        listing = subprocess.check_output([extractor, '-tf', str(archive)], text=True, timeout=60)
        for name in listing.splitlines():
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError('Stock archive contains an unsafe path.')
        print('Extracting stock files on the computer…', flush=True)
        with tempfile.TemporaryDirectory(prefix='stock-', dir=ROOT/'build') as temporary:
            extracted = Path(temporary)/'contents'
            extracted.mkdir()
            subprocess.run([extractor, '-xf', str(archive), '-C', str(extracted)], check=True)
            stock = stock_from_directory(extracted)
            if not {'Apps', 'Roms'} <= set(stock.directories):
                raise ValueError('Unexpected official stock archive layout.')
            if base.exists():
                shutil.rmtree(base)
            extracted.rename(base)
            write_record(file_record, json.dumps({name: entry[1] for name, entry in stock.files.items()}))
            write_record(marker, BASE['sha256'] + '\n')
            return Stock(base, stock.directories, stock.files)


def card_entries(card):
    return {path.name for path in card.iterdir()
            if path.name not in IGNORED_CARD_ENTRIES and not mac_metadata(path.name)}


def verify_file(path, expected, progress):
    with path.open('rb') as stream:
        actual = transfer(stream, progress)
    progress.advance(files=1)
    return actual == expected


def publish_tree(staged, destination, stock, check_mount):
    """Move whole new directories where possible, merge older copies by addition."""
    def publish(source, target):
        check_mount()
        name = target.relative_to(destination).as_posix()
        if mac_metadata(source.name) and name not in stock.files:
            if file_stat(source):
                source.unlink(missing_ok=True)
            return
        if source.is_dir():
            if check_directory(target):
                for child in list(source.iterdir()):
                    publish(child, target/child.name)
                source.rmdir()
                return
        elif file_stat(target):
            if name not in stock.files or digest(target) != stock.files[name][1]:
                raise ValueError(f'Stock file conflicts with the card: {name}. Existing file preserved.')
            source.unlink()
            return
        # The mount is locked against other PocketLAB installers. FAT on macOS
        # does not support rename with an exclusive flag. Check the name again
        # immediately before moving files, including when resuming publication.
        if os.path.lexists(target):
            raise ValueError(f'Card contents changed during preparation: {target.name}. Rerun to resume.')
        source.rename(target)

    for item in list(staged.iterdir()):
        publish(item, destination/item.name)


def prepare_tree(stock, card, *, identity, resume=False, check_mount):
    """Stage and verify stock files. Keep the checkpoint until the app is installed."""
    work = card/WORK
    work_exists = check_directory(work)
    record = work/'state.json'
    staged = work/'stock'
    saved = bool(file_stat(record)) if work_exists else False
    if work_exists:
        unexpected = [path for path in work.iterdir() if path not in (record, staged)
                      and not (file_stat(path) and (
                          mac_metadata(path.name) or re.fullmatch(r'\.record-[a-z0-9_]{8}', path.name)))]
        if unexpected or (not saved and check_directory(staged)):
            raise ValueError(f'Unrecognized setup files in {WORK}. Existing files were preserved.')
    entries = card_entries(card) - {WORK}
    roots = {name.split('/', 1)[0] for name in (*stock.directories, *stock.files)}
    if not saved and entries and (not resume or not entries <= roots):
        raise ValueError('New-card preparation needs an empty card or an interrupted stock copy. Existing files were preserved.')

    # Only the selected volume and this exact stock manifest can use the saved
    # verification results. A remount at another path is fine.
    state = {'version': 1, 'card': identity, 'stock': stock.fingerprint, 'verified': {}}
    if saved:
        prior = json.loads(record.read_text())
        if not isinstance(prior, dict) or any(prior.get(key) != state[key] for key in ('version', 'card', 'stock')):
            raise ValueError('This setup record belongs to a different card or stock package.')
        if not isinstance(prior.get('verified'), dict):
            raise ValueError('Invalid setup verification record.')
        state['verified'] = prior['verified']
        print('Resuming stock-card preparation…', flush=True)
    if check_directory(staged):
        print('Inspecting saved files on the card…', flush=True)
        stage_dirs, stage_files = inventory(staged, ignore_metadata=True)
        if stage_files.keys() - stock.files.keys() or set(stage_dirs) - set(stock.directories):
            raise ValueError(f'Unexpected files in {WORK}/stock. Existing files were preserved.')
    else:
        stage_files = {}

    existing_dirs = {name for name in stock.directories
                     if name.split('/', 1)[0] in entries and check_directory(card/name)}

    # Check published files first. An older interrupted copy can be adopted only
    # if its existing stock files match, leaving all unrelated files in place.
    existing = {}
    for name in stock.files:
        if name.split('/', 1)[0] in entries and (info := file_stat(card/name)):
            if info.st_size != stock.files[name][0]:
                raise ValueError(f'Stock file conflicts with the card: {name}. Existing file preserved.')
            existing[name] = info.st_mtime_ns
    uncertain = [name for name, mtime in existing.items()
                 if state['verified'].get(name) != ['card', mtime]]
    if uncertain:
        progress = Progress('Checking existing stock files', sum(stock.files[name][0] for name in uncertain), len(uncertain))
        for name in uncertain:
            check_mount()
            if not verify_file(card/name, stock.files[name][1], progress):
                raise ValueError(f'Stock file conflicts with the card: {name}. Existing file preserved.')
        progress.report(force=True)
    state['verified'].update({name: ['card', mtime] for name, mtime in existing.items()})

    # Checkpointed staged files can be reused directly. Read any incomplete or
    # unverified files once, and write only missing or damaged staged files.
    missing = [name for name in stock.files if name not in existing]
    copy = []
    uncertain = []
    for name in missing:
        size, _ = stock.files[name]
        info = stage_files.get(name)
        if info is None or info.st_size != size:
            copy.append(name)
        elif state['verified'].get(name) != ['staged', info.st_mtime_ns]:
            uncertain.append(name)
    if uncertain:
        # A previous process may have stopped before flushing its staged writes.
        flush_writes()
        progress = Progress('Checking files from the interrupted copy', sum(stock.files[name][0] for name in uncertain), len(uncertain))
        for name in uncertain:
            check_mount()
            if verify_file(staged/name, stock.files[name][1], progress):
                state['verified'][name] = ['staged', file_stat(staged/name).st_mtime_ns]
            else:
                copy.append(name)
        progress.report(force=True)

    # Account for allocation rounding as well as directories and the setup record.
    block = os.statvfs(card).f_frsize
    required = sum(max(1, (stock.files[name][0] + block - 1) // block) * block for name in copy)
    if shutil.disk_usage(card).free < required + len(stock.directories) * block + 8 * MIB:
        raise ValueError('Not enough free space for the remaining stock files and PocketLAB.')
    check_mount()
    if not work_exists:
        work.mkdir()
    for name in copy:
        state['verified'].pop(name, None)
    write_record(record, json.dumps(state))
    if not saved:
        flush_writes()
    for name in stage_files.keys() & existing.keys():
        check_mount()
        (staged/name).unlink()
    staged.mkdir(exist_ok=True)
    # Keep empty stock directories as well as those containing files. Create
    # parents once, outside the transfer loop.
    directories = set(stock.directories) - existing_dirs
    directories.update(str(PurePosixPath(name).parent) for name in copy)
    for name in sorted(directories):
        (staged/name).mkdir(parents=True, exist_ok=True)

    if copy:
        total = sum(stock.files[name][0] for name in copy)
        progress = Progress('Copying stock files', total, len(copy))
        for name in copy:
            check_mount()
            target = staged/name
            if name in stage_files:
                target.unlink()
            with (stock.root/name).open('rb') as source, target.open('xb') as out:
                checksum = transfer(source, progress, out)
            if checksum != stock.files[name][1]:
                raise ValueError(f'Cached stock file failed verification: {name}. Recreate build/stock-base and retry.')
            progress.advance(files=1)
        progress.report(force=True)
        print('Flushing copied files…', flush=True)
        flush_writes()
        progress = Progress('Verifying copied stock files', total, len(copy))
        for index, name in enumerate(copy, 1):
            check_mount()
            if not verify_file(staged/name, stock.files[name][1], progress):
                raise ValueError(f'Card checksum mismatch: {name}. Rerun setup to retry this file.')
            state['verified'][name] = ['staged', file_stat(staged/name).st_mtime_ns]
            if index % 2048 == 0:
                write_record(record, json.dumps(state))
        progress.report(force=True)

    # At this point the selected stock files have all been read back. Record
    # that before publication so a disconnect during the moves is resumable.
    check_mount()
    write_record(record, json.dumps(state))
    print('Putting the verified stock files in place…', flush=True)
    publish_tree(staged, card, stock, check_mount)
    flush_writes()
    check_mount()
    state['verified'] = {name: ['card', state['verified'][name][1]] for name in stock.files}
    write_record(record, json.dumps(state))
    return work
