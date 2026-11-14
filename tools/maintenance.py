"""Inspect or explicitly prune retained backups on a card-reader installation."""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from card_io import remove_tree


def backups(card, prune=False, keep=2):
    from card_runtime import BACKUP_RECORD
    from pocketlab import card_root, safe_tree
    if keep<1:raise ValueError('Keep at least one backup per app/shell.')
    card=card_root(card);root=card/'Apps/PocketLab'
    safe_tree(root)
    pending=None
    marker=root/'data/pending-shell-update'
    if marker.exists():
        fields=marker.read_text().split()
        if len(fields)!=2 or not re.fullmatch('[0-9a-f]{32}',fields[0]):
            raise ValueError('Invalid pending update; resolve recovery before pruning backups.')
        pending=fields[0]
    candidates=[]
    specifications=[(card/'Apps',r'\.PocketLab\.backup-[0-9a-f]{10}','shell-card','manifest.sha256.json'),
                    (root/'apps',r'\.backup-([a-z][a-z0-9-]{0,47})-[0-9a-f]{32}',None,'app.json'),
                    (root/'data/updates',r'[0-9a-f]{32}','shell-usb','backup.sha256')]
    for parent,pattern,group,marker_name in specifications:
        if not parent.exists():continue
        if parent.is_symlink():raise ValueError('Backup parent cannot be a symlink')
        for path in parent.iterdir():
            match=re.fullmatch(pattern,path.name)
            if not match or not path.is_dir() or not (path/marker_name).is_file():continue
            safe_tree(path)
            backup_group = 'shell-card-runtime' if (path/BACKUP_RECORD).is_file() else group
            candidates.append({'path':path,'group':backup_group or 'app:'+match.group(1),
                               'bytes':sum(p.stat().st_size for p in path.rglob('*') if p.is_file()),
                               'mtime':path.stat().st_mtime,'protected':path.name==pending})
    kept={};result=[]
    for item in sorted(candidates,key=lambda x:x['mtime'],reverse=True):
        group=item['group'];position=kept.get(group,0);kept[group]=position+1
        remove=position>=keep and not item['protected']
        path=item['path'];record=dict(item,path=path.relative_to(card).as_posix(),eligible=remove,removed=False)
        if prune and remove:
            safe_tree(path)
            remove_tree(path)
            record['removed']=True
        result.append(record)
    return {'keep_per_group':keep,'pruned':prune,'backups':result}


def restore_card(card, backup_name, check_mount=lambda: None):
    from card_io import check_directory
    from card_runtime import BACKUP_RECORD, restore_snapshot
    from pocketlab import card_root, safe_tree, digest, install_tree
    card=card_root(card);destination=card/'Apps/PocketLab'
    check_directory(destination)
    check_directory(destination/'data')
    check_directory(destination/'data/updates')
    if not backup_name and (destination/'data/pending-shell-update').is_file():
        fields=(destination/'data/pending-shell-update').read_text().split()
        if len(fields)==2:backup_name=fields[0]
    if backup_name and re.fullmatch(r'\.PocketLab\.backup-[0-9a-f]{10}',backup_name):
        backup=card/'Apps'/backup_name
    elif backup_name and re.fullmatch('[0-9a-f]{32}',backup_name):
        backup=destination/'data/updates'/backup_name
    else:
        raise ValueError('Choose an exact shell backup from backups --sd CARD and pass --backup NAME.')
    if check_directory(backup) and (backup/BACKUP_RECORD).is_file():
        restore_snapshot(destination, backup, check_mount)
        print('Previous shell restored; current apps and data preserved. Safely eject and reopen PocketLAB.')
        return
    safe_tree(backup)
    manifest=json.loads((backup/'manifest.sha256.json').read_text())
    if not isinstance(manifest,dict) or not {'pocketlab','launch.sh','config.json'} <= set(manifest):
        raise ValueError('Incomplete backup manifest')
    for name,expected in manifest.items():
        path=Path(name)
        if not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name or path.parts[0] in ('apps','data'):
            raise ValueError('Invalid backup manifest path')
        if digest(backup/name)!=expected:raise ValueError('Backup checksum mismatch: '+name)
    if destination.is_symlink():raise ValueError('Installed folder cannot be a symlink')
    if not destination.exists():
        # Recover the complete original tree after a power interruption between
        # directory renames, including its original apps and persistent data.
        backup.rename(destination)
    else:
        with tempfile.TemporaryDirectory(prefix='pocketlab-restore-') as tmp:
            payload=Path(tmp)
            for name in [*manifest,'manifest.sha256.json']:
                target=payload/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(backup/name,target)
            install_tree(payload,destination,('data','apps'),allow_pending=True)
    if hasattr(os,'sync'):os.sync()
    (destination/'data/pending-shell-update').unlink(missing_ok=True)
    print('Previous shell restored; current apps and data preserved. Safely eject and reopen PocketLAB.')
