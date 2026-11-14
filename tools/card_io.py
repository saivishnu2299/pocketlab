"""Small filesystem operations shared by the card installers."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import shutil
import stat
import sys

APPLEDOUBLE = b'\x00\x05\x16\x07'


@contextmanager
def exclusive_lock(key):
    """Coordinate PocketLAB processes on this host without writing to the card."""
    directory = Path('/tmp') / f'pocketlab-locks-{os.getuid()}'
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Cannot use the PocketLAB lock directory in /tmp.')
    with os.fdopen(os.open(directory/key, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), 'rb+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another PocketLAB process is using this card or cache.') from exc
        yield


def flush_writes():
    if hasattr(os, 'sync'):
        os.sync()


def file_stat(path):
    """Return metadata for an ordinary file, or None for an absent path."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f'Expected an ordinary file at {path}.')
    return info


def check_directory(path):
    """Allow an ordinary directory or an absent path."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f'Expected an ordinary directory at {path}.')
    return True


def write_record(path, text):
    """Replace a small, installer-owned record only after writing its bytes."""
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(mode='w', encoding='utf-8', prefix='.record-', dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        try:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
            out.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def remove_tree(path):
    """Delete an installer-owned tree on a card.

    On FAT, macOS keeps extended attributes in AppleDouble companions (._NAME)
    and deletes each companion with its file, so a listed entry can vanish
    before rmtree reaches it.
    """
    def vanished(function, name, error):
        error = error[1] if isinstance(error, tuple) else error
        if not isinstance(error, FileNotFoundError):
            raise error
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=vanished)
    else:
        shutil.rmtree(path, onerror=vanished)


def strip_appledouble(root, names):
    """Remove the macOS AppleDouble companions of paths PocketLAB wrote.

    macOS creates ._NAME files on FAT for anything carrying extended
    attributes; the Brick never uses them. Only genuine AppleDouble files next
    to the given paths are removed, never a companion that is itself listed.
    """
    if sys.platform != 'darwin':
        return 0
    names = {str(name) for name in names}
    removed = 0
    for name in sorted(names):
        path = Path(root)/name
        companion = path.with_name('._'+path.name)
        if str(companion.relative_to(root)) in names:
            continue
        try:
            info = companion.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
                continue
            with companion.open('rb') as stream:
                if stream.read(4) != APPLEDOUBLE:
                    continue
            companion.unlink()
            removed += 1
        except FileNotFoundError:
            continue
    return removed
