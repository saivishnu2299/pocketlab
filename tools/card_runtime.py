"""Install or restore the PocketLAB shell without copying mini apps or saves."""
import json
from pathlib import Path, PurePosixPath
import re
from shlex import quote
import shutil
from tempfile import TemporaryDirectory
import uuid

from card_io import check_directory, file_stat, flush_writes, remove_tree, strip_appledouble, write_record
from release import digest

MANIFEST = 'manifest.sha256.json'
PENDING = 'data/pending-shell-update'
BACKUP_RECORD = 'card-update.json'
PACKAGE_ID = 'org.pocketlab.shell'


def runtime_files(root):
    path = root/MANIFEST
    if not file_stat(path):
        raise ValueError('Missing PocketLAB runtime manifest.')
    files = json.loads(path.read_text())
    if not isinstance(files, dict) or not {'pocketlab', 'launch.sh', 'config.json'} <= files.keys():
        raise ValueError('Incomplete PocketLAB runtime manifest.')
    validate_names(files)
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value) for value in files.values()):
        raise ValueError('Invalid runtime checksum.')
    return {**files, MANIFEST: digest(path)}


def validate_names(names):
    for name in names:
        path = PurePosixPath(name)
        if (not path.parts or path.is_absolute() or name != path.as_posix()
                or any(part in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]+', part) for part in path.parts)
                or path.parts[0].casefold() in (
                    'apps', 'data', 'lib', 'restore.sh', 'backup.sha256', BACKUP_RECORD, '.incoming')):
            raise ValueError(f'Invalid runtime file path: {name}')
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError('Conflicting runtime paths on a case insensitive card.')


def file_hash(root, name):
    path = root/name
    directory = root
    for part in path.parent.relative_to(root).parts:
        directory /= part
        if not check_directory(directory):
            return None
    return digest(path) if file_stat(path) else None


def package_id(root):
    path = root/'config.json'
    if not file_stat(path):
        return None
    config = json.loads(path.read_text())
    return config.get('package') if isinstance(config, dict) else None


def pending_update(root):
    if not check_directory(root/'data') or not file_stat(root/PENDING):
        return None
    fields = (root/PENDING).read_text().split()
    if (len(fields) != 2 or not re.fullmatch('[0-9a-f]{32}', fields[0])
            or fields[1] not in ('copying', 'ready', 'attempted')):
        raise ValueError('Invalid pending shell update. Inspect the update before installing again.')
    return tuple(fields)


def install_runtime(source, destination, check_mount):
    """Keep runtime verification and updates independent of the user's data size."""
    from pocketlab import install_tree

    check_mount()
    print('Checking PocketLAB on the card…', flush=True)
    if not check_directory(destination):
        install_tree(source, destination)
        for directory in ('apps', 'data'):
            (destination/directory).mkdir(exist_ok=True)
        strip_appledouble(destination, ['apps', 'data'])
        return 'installed'

    if package_id(destination) != PACKAGE_ID:
        raise ValueError('Apps/PocketLab is occupied by an unrecognized installation. Existing files were preserved.')

    expected = runtime_files(source)
    current = {name: file_hash(destination, name) for name in expected}
    pending = pending_update(destination)
    if pending and (pending[1] != 'ready' or current != expected):
        raise ValueError('A shell update needs recovery. Run recover --sd CARD before installing again.')
    if current == expected:
        if pending:
            print('PocketLAB files verified. Open PocketLAB on the Brick to finish the update.', flush=True)
        else:
            print('PocketLAB is already installed and verified.', flush=True)
        return 'verified'

    changed = [name for name, checksum in expected.items() if current[name] != checksum]
    # Keep a complete snapshot of the known old runtime for later manual restore.
    # Older PocketLAB builds may be missing the manifest or have a damaged one.
    try:
        old_names = runtime_files(destination)
    except ValueError:
        old_names = {}
    snapshot = dict(current)
    for name in old_names.keys() - snapshot.keys():
        snapshot[name] = file_hash(destination, name)
    validate_names(snapshot)
    apply_update(source, destination, expected, changed, snapshot, check_mount)
    return 'updated'


def tidy(root, names):
    """Drop macOS metadata files next to installer-written paths and their folders."""
    parents = {str(PurePosixPath(name).parent) for name in names} - {'.'}
    strip_appledouble(root, [*names, *parents])


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, destination)


def write_restore_script(backup, snapshot):
    # Use the same pending record and recovery entry point as the USB updater.
    # Backup paths are relative to the token directory on either host or device.
    checks = [f'{checksum}  ./{name}\n' for name, checksum in snapshot.items() if checksum is not None]
    (backup/'backup.sha256').write_text(''.join(checks))
    lines = [
        '#!/bin/sh', 'set -e',
        'BACKUP=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)',
        'cd "$BACKUP"',
        'sha256sum -c backup.sha256',
        'cd ../../..',
    ]
    for name, checksum in sorted(snapshot.items(), key=lambda entry: entry[0] == 'launch.sh'):
        target = quote('./'+name)
        if checksum is None:
            lines.append('rm -f '+target)
        else:
            temporary = quote('./'+name+'.restore-'+backup.name)
            lines += [
                'mkdir -p '+quote('./'+str(PurePosixPath(name).parent)),
                'cp "$BACKUP"/'+quote(name)+' '+temporary,
                'mv '+temporary+' '+target,
            ]
    for name in ('pocketlab', 'launch.sh'):
        if snapshot.get(name) is not None:
            lines.append('chmod 755 ./'+name)
    lines += ['sha256sum -c "$BACKUP"/backup.sha256', 'sync', 'rm -f '+PENDING, 'sync']
    (backup/'restore.sh').write_text('\n'.join(lines)+'\n')


def apply_update(source, destination, expected, changed, snapshot, check_mount):
    check_mount()
    required = sum((source/name).stat().st_size for name in changed)
    required += sum((destination/name).stat().st_size for name, value in snapshot.items() if value is not None)
    if shutil.disk_usage(destination).free < required + 8 * 1024**2:
        raise ValueError('Not enough free space for the PocketLAB runtime and its rollback copy.')
    for part in ('data', 'data/updates'):
        path = destination/part
        check_directory(path)
        path.mkdir(exist_ok=True)
    token = uuid.uuid4().hex
    backup = destination/'data/updates'/token
    backup.mkdir()
    print(f'Staging {len(changed)} changed PocketLAB runtime files…', flush=True)
    marker = destination/PENDING
    try:
        for name, checksum in snapshot.items():
            if checksum is not None:
                copy_file(destination/name, backup/name)
                if digest(backup/name) != checksum:
                    raise ValueError(f'PocketLAB changed while preparing the backup: {name}')
        write_record(backup/BACKUP_RECORD, json.dumps(snapshot))
        write_restore_script(backup, snapshot)
        staged = backup/'.incoming'
        for name in changed:
            copy_file(source/name, staged/name)
            if digest(staged/name) != expected[name]:
                raise ValueError(f'Staged runtime checksum mismatch: {name}')
        check_mount()
        flush_writes()
        write_record(marker, token+' copying\n')
        flush_writes()
        # A legacy launcher cannot recover an interrupted update. Put the
        # recovery-capable launcher in place before the other changed files.
        for name in sorted(changed, key=lambda name: (name != 'launch.sh', name == MANIFEST, name)):
            check_mount()
            target = destination/name
            target.parent.mkdir(parents=True, exist_ok=True)
            (staged/name).replace(target)
        if any(file_hash(destination, name) != checksum for name, checksum in expected.items()):
            raise ValueError('Installed PocketLAB runtime failed verification.')
        flush_writes()
        remove_tree(staged)
        write_record(marker, token+' ready\n')
        flush_writes()
    except BaseException:
        # If the card disconnected, leave the durable recovery record alone.
        check_mount()
        pending = pending_update(destination)
        if pending and pending[0] == token:
            restore_snapshot(destination, backup, check_mount)
            print('Previous PocketLAB runtime restored.', flush=True)
        else:
            remove_tree(backup)
        raise
    tidy(destination, [*changed, PENDING, 'data/updates/'+token])
    tidy(backup, [*(name for name, checksum in snapshot.items() if checksum), BACKUP_RECORD, 'backup.sha256', 'restore.sh'])
    print(f'PocketLAB updated and verified. Open it on the Brick to finish. Runtime backup: {token}', flush=True)


def restore_snapshot(destination, backup, check_mount=lambda: None):
    """Restore an exact verified runtime snapshot, keeping user files in place."""
    check_mount()
    check_directory(backup)
    record = backup/BACKUP_RECORD
    if not file_stat(record):
        raise ValueError('Missing PocketLAB card update backup record.')
    snapshot = json.loads(record.read_text())
    if not isinstance(snapshot, dict) or not snapshot.get('config.json'):
        raise ValueError('Invalid PocketLAB backup record.')
    validate_names(snapshot)
    for name, checksum in snapshot.items():
        if checksum is not None and (
            not isinstance(checksum, str) or not re.fullmatch('[0-9a-f]{64}', checksum)
            or file_hash(backup, name) != checksum
        ):
            raise ValueError(f'Backup checksum mismatch: {name}')
        file_hash(destination, name)  # Refuse linked or non-file targets before changing anything.
    with TemporaryDirectory(prefix='.restore-', dir=backup) as directory:
        for name, checksum in sorted(snapshot.items(), key=lambda entry: entry[0] == 'launch.sh'):
            check_mount()
            target = destination/name
            if checksum is None:
                target.unlink(missing_ok=True)
            else:
                temporary = Path(directory)/name
                copy_file(backup/name, temporary)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary.replace(target)
    if any(file_hash(destination, name) != checksum for name, checksum in snapshot.items()):
        raise ValueError('Restored PocketLAB runtime failed verification. The backup was retained.')
    tidy(destination, [name for name, checksum in snapshot.items() if checksum])
    flush_writes()
    (destination/PENDING).unlink(missing_ok=True)
    flush_writes()
