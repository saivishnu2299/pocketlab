"""Update a PocketLAB clone with git, without touching user mini apps.

User app sources under miniapps/ (and data/, projects/, build/) are ignored by
git, so a fast-forward pull cannot change them. Local edits to tracked files
are reported instead of being merged, stashed or discarded.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(*args, check=True):
    return subprocess.run(['git', *args], cwd=ROOT, check=check, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def is_clone():
    return (ROOT/'.git').exists() and shutil.which('git') is not None


def changed_tracked_files():
    """Tracked files with local edits; untracked and ignored files are excluded."""
    out = git('status', '--porcelain', '--untracked-files=no').stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def pull():
    """Fast-forward the clone. Returns (old, new) commit ids."""
    if not (ROOT/'.git').exists():
        raise ValueError('This folder is not a git clone. Download the new release, '
                         'or clone https://github.com/saivishnu2299/pocketlab and copy miniapps/ into it.')
    if shutil.which('git') is None:
        raise ValueError('git is not installed. On macOS run xcode-select --install; on Linux use your distribution package.')
    changed = changed_tracked_files()
    if changed:
        shown = ', '.join(changed[:8]) + (' …' if len(changed) > 8 else '')
        raise ValueError(f'Local edits to PocketLAB files would block the update: {shown}. '
                         'Your mini apps in miniapps/ are not affected. Keep the edits with '
                         '"git stash", or discard them with "git checkout -- FILE", then run update again.')
    if git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}', check=False).returncode:
        raise ValueError('This branch has no upstream to update from. Run "git checkout main" and try again.')
    old = git('rev-parse', 'HEAD').stdout.strip()
    result = git('pull', '--ff-only', check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ValueError('git pull --ff-only failed' + (f': {detail[-1]}' if detail else '') +
                         '. Your mini apps are unchanged. If you made local commits, '
                         'rebase them with "git pull --rebase" yourself.')
    return old, git('rev-parse', 'HEAD').stdout.strip()


def update(sd=None, usb=False, serial=None, confirm_model=None, eject=False, pull_first=True):
    if pull_first:
        old, new = pull()
        if old == new:
            print('PocketLAB source is already up to date.')
        else:
            print(f'Updated PocketLAB source {old[:7]} → {new[:7]}. Mini apps in miniapps/ were not changed.')
    # Run the install step with the freshly pulled code, not the code loaded in this process.
    command = [sys.executable, str(ROOT/'tools/pocketlab.py')]
    if sd:
        command += ['setup', '--sd', sd] + (['--eject'] if eject else [])
    elif usb:
        command += ['install', '--usb'] + (['--serial', serial] if serial else [])
        command += ['--confirm-model', confirm_model] if confirm_model else []
    else:
        print('To update the Brick, run one of:\n'
              '  ./pocketlab setup --sd CARD --eject                     (card in this computer)\n'
              '  ./pocketlab install --usb --confirm-model TG4040        (Brick connected over USB)\n'
              'Then open PocketLAB on the Brick once to finish the startup check.')
        return 0
    code = subprocess.call(command, cwd=ROOT)
    if code == 0:
        print('Open PocketLAB on the Brick once to finish the startup check. Installed mini apps and saves were kept.')
    return code
