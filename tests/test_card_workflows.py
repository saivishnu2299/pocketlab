"""Regression tests for interrupted copies and updates on a populated card."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))

import card_runtime
import card_io
from card_io import exclusive_lock
from maintenance import restore_card
import onboarding
from release import RUNTIME, digest
import stock_card


def keep_mount():
    """The test fixture is an ordinary directory with a fixed identity."""


class CardFixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.card = self.root/'card'
        self.card.mkdir()
        self.output = self.enterContext(redirect_stdout(io.StringIO()))
        self.enterContext(patch('stock_card.flush_writes'))
        self.enterContext(patch('card_runtime.flush_writes'))


class StockPreparationTests(CardFixture):
    def setUp(self):
        super().setUp()
        self.base = self.root/'stock'
        (self.base/'Apps/StockApp').mkdir(parents=True)
        (self.base/'Roms').mkdir()
        (self.base/'RetroArch').mkdir()
        (self.base/'Apps/StockApp/launch.sh').write_bytes(b'launcher')
        (self.base/'RetroArch/one.dat').write_bytes(b'one content')
        (self.base/'RetroArch/two.dat').write_bytes(b'two content')
        self.stock = stock_card.stock_from_directory(self.base)
        self.work = self.card/stock_card.WORK
        self.staged = self.work/'stock'

    def prepare(self, *, resume=False, identity='test-volume'):
        return stock_card.prepare_tree(self.stock, self.card, identity=identity, resume=resume, check_mount=keep_mount)

    def test_retry_after_partial_write_copies_only_missing_or_incomplete_files(self):
        transfer = stock_card.transfer

        def partial_copy(reader, progress, writer=None):
            if writer and Path(writer.name).name == 'one.dat':
                writer.write(b'partial')
                raise OSError('Reader disconnected')
            return transfer(reader, progress, writer)

        with patch('stock_card.transfer', side_effect=partial_copy):
            with self.assertRaisesRegex(OSError, 'disconnected'):
                self.prepare()
        self.assertFalse((self.card/'Apps').exists())
        self.assertEqual((self.staged/'RetroArch/one.dat').read_bytes(), b'partial')
        self.assertTrue((self.work/'state.json').is_file())
        (self.work/'._state.json').write_bytes(b'macOS metadata')

        copied = []

        def record_copy(reader, progress, writer=None):
            if writer:
                copied.append(Path(writer.name).name)
            return transfer(reader, progress, writer)

        with patch('stock_card.transfer', side_effect=record_copy):
            self.prepare()
        self.assertEqual(copied, ['one.dat', 'two.dat'])
        self.assertEqual((self.card/'Apps/StockApp/launch.sh').read_bytes(), b'launcher')
        self.assertEqual((self.card/'RetroArch/one.dat').read_bytes(), b'one content')
        self.assertEqual((self.card/'RetroArch/two.dat').read_bytes(), b'two content')
        self.assertTrue((self.card/'Roms').is_dir())
        for phase in ('Resuming', 'Copying stock files', 'Verifying copied stock files'):
            self.assertIn(phase, self.output.getvalue())

    def test_verified_files_are_reused_after_interrupted_publication(self):
        original = Path.rename

        def interrupt(path, target):
            if path == self.staged/'RetroArch':
                raise KeyboardInterrupt
            return original(path, target)

        with patch.object(Path, 'rename', interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.prepare()

        self.assertTrue((self.staged/'RetroArch/one.dat').exists())
        verify = stock_card.verify_file

        def verify_published(path, expected, progress):
            self.assertFalse(path.is_relative_to(self.staged), 'Verified staged files were read again')
            return verify(path, expected, progress)

        with patch('stock_card.verify_file', side_effect=verify_published):
            self.prepare()
        self.assertEqual((self.card/'RetroArch/two.dat').read_bytes(), b'two content')

    def test_stock_is_reused_if_pocketlab_install_needs_retry(self):
        self.prepare()
        with patch('stock_card.verify_file', side_effect=AssertionError('Completed stock was read again')):
            self.prepare()
        self.assertEqual((self.card/'RetroArch/two.dat').read_bytes(), b'two content')

    def test_older_macos_card_metadata_is_left_in_place(self):
        (self.card/'._RetroArch').write_bytes(b'filesystem metadata')
        (self.card/'RetroArch').mkdir()
        (self.card/'RetroArch/one.dat').write_bytes(b'one content')
        self.prepare(resume=True)
        self.assertTrue((self.card/'RetroArch/two.dat').is_file())
        self.assertEqual((self.card/'._RetroArch').read_bytes(), b'filesystem metadata')

    def test_mac_metadata_generated_during_publication_is_not_treated_as_stock(self):
        original = stock_card.publish_tree

        def add_sidecars(staged, destination, stock, check_mount):
            (staged/'._Apps').write_bytes(b'staged metadata')
            (destination/'._Apps').write_bytes(b'card metadata')
            return original(staged, destination, stock, check_mount)

        with patch('stock_card.publish_tree', side_effect=add_sidecars):
            self.prepare()
        self.assertTrue((self.card/'Apps/StockApp/launch.sh').exists())
        self.assertEqual((self.card/'._Apps').read_bytes(), b'card metadata')

    def test_resume_detects_changes_to_previously_verified_stock(self):
        original = Path.rename

        def interrupt(path, target):
            if path == self.staged/'RetroArch':
                raise OSError('Interrupted before promotion')
            return original(path, target)

        with patch.object(Path, 'rename', interrupt):
            with self.assertRaises(OSError):
                self.prepare()
        path = self.staged/'RetroArch/one.dat'
        path.write_bytes(b'bad content')
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 3_000_000_000))
        self.prepare()
        self.assertEqual((self.card/'RetroArch/one.dat').read_bytes(), b'one content')

    def test_adopts_matching_legacy_stock_without_touching_user_files(self):
        (self.card/'Apps/PocketLab/data').mkdir(parents=True)
        user_file = self.card/'Apps/PocketLab/data/song.wav'
        user_file.write_bytes(b'original song')
        (self.card/'RetroArch').mkdir()
        first = self.card/'RetroArch/one.dat'
        first.write_bytes(b'one content')
        before = first.stat()
        self.prepare(resume=True)
        self.assertEqual(first.stat().st_ino, before.st_ino)
        self.assertEqual(first.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual((self.card/'RetroArch/two.dat').read_bytes(), b'two content')
        self.assertEqual(user_file.read_bytes(), b'original song')

    def test_same_size_stock_conflict_is_preserved_before_any_writes(self):
        (self.card/'RetroArch').mkdir()
        conflict = self.card/'RetroArch/one.dat'
        conflict.write_bytes(b'own content')
        with self.assertRaisesRegex(ValueError, 'conflicts.*one.dat'):
            self.prepare(resume=True)
        self.assertEqual(conflict.read_bytes(), b'own content')
        self.assertFalse(self.work.exists())
        self.assertFalse((self.card/'Apps').exists())

    def test_disconnected_or_wrong_card_cannot_use_another_cards_checkpoint(self):
        with patch('stock_card.publish_tree', side_effect=OSError('disconnected')):
            with self.assertRaises(OSError):
                self.prepare()
        with self.assertRaisesRegex(ValueError, 'different card'):
            self.prepare(identity='other-volume')
        self.assertFalse((self.card/'Apps').exists())

    def test_corrupt_extracted_source_is_not_published(self):
        (self.base/'RetroArch/one.dat').write_bytes(b'bad content')
        with self.assertRaisesRegex(ValueError, 'Cached stock file failed verification'):
            self.prepare()
        self.assertFalse((self.card/'RetroArch').exists())

    def test_low_space_preserves_existing_files(self):
        (self.card/'RetroArch').mkdir()
        existing = self.card/'RetroArch/one.dat'
        existing.write_bytes(b'one content')
        with patch('stock_card.shutil.disk_usage', return_value=shutil._ntuple_diskusage(10, 9, 1)):
            with self.assertRaisesRegex(ValueError, 'Not enough free space'):
                self.prepare(resume=True)
        self.assertEqual(existing.read_bytes(), b'one content')
        self.assertFalse(self.work.exists())

    def test_conflict_during_publication_is_preserved(self):
        # Simulate a conflict introduced after the preflight by another program.
        original = stock_card.publish_tree

        def add_conflict(staged, destination, stock, check_mount):
            (destination/'RetroArch').mkdir()
            (destination/'RetroArch/one.dat').write_bytes(b'own content')
            return original(staged, destination, stock, check_mount)

        with patch('stock_card.publish_tree', side_effect=add_conflict):
            with self.assertRaisesRegex(ValueError, 'conflicts'):
                self.prepare()
        self.assertEqual((self.card/'RetroArch/one.dat').read_bytes(), b'own content')
        self.assertTrue(self.work.exists())


class StockCacheTests(CardFixture):
    @unittest.skipUnless(shutil.which('bsdtar'), 'bsdtar is needed to extract the stock archive')
    def test_cold_extract_is_promoted_and_cache_reuses_file_hashes(self):
        build = self.root/'build'
        (build/'downloads').mkdir(parents=True)
        vendor = self.root/'vendor'
        (vendor/'Apps').mkdir(parents=True)
        (vendor/'Roms').mkdir()
        (vendor/'Apps/stock').write_bytes(b'stock app')
        archive = build/'downloads/fixture.tar'
        with tarfile.open(archive, 'w') as pack:
            pack.add(vendor, arcname='.')
        base = dict(stock_card.BASE, name=archive.name, sha256=digest(archive))
        with patch.object(stock_card, 'ROOT', self.root), patch.object(stock_card, 'BASE', base):
            with patch('stock_card.shutil.copytree', side_effect=AssertionError('Extracted stock tree was copied again')):
                extracted = stock_card.stock_base()
            self.assertEqual((extracted.root/'Apps/stock').read_bytes(), b'stock app')
            with patch('stock_card.digest', wraps=digest) as hash_file:
                cached = stock_card.stock_base()
            hash_file.assert_called_once_with(archive)
            self.assertEqual(cached, extracted)

    def test_download_promotes_only_matching_archive_bytes(self):
        archive = self.root/'stock.7z'
        content = b'vendor download'
        base = dict(stock_card.BASE, sha256=hashlib.sha256(content).hexdigest())
        response = io.BytesIO(content)
        response.headers = {'Content-Length': str(len(content))}
        with patch.object(stock_card, 'BASE', base), patch('stock_card.urllib.request.urlopen', return_value=response):
            stock_card.download_stock(archive)
        self.assertEqual(archive.read_bytes(), content)
        with patch.object(stock_card, 'BASE', base):
            response = io.BytesIO(b'incorrect download')
            response.headers = {}
            with patch('stock_card.urllib.request.urlopen', return_value=response):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    stock_card.download_stock(archive)
        self.assertEqual(archive.read_bytes(), content)
        self.assertEqual(list(self.root.glob('.download-*')), [])


class RuntimeUpdateTests(CardFixture):
    def setUp(self):
        super().setUp()
        self.app = self.card/'Apps/PocketLab'
        (self.card/'Roms').mkdir()
        card_runtime.install_runtime(RUNTIME, self.app, keep_mount)
        (self.app/'apps/custom').mkdir()
        self.user_app = self.app/'apps/custom/app'
        self.user_app.write_bytes(b'personal app')
        self.user_data = self.app/'data/recording.wav'
        with self.user_data.open('wb') as stream:
            stream.write(b'personal recording')
            stream.truncate(32*1024**2)
        self.rom = self.card/'Roms/game'
        self.rom.write_bytes(b'existing ROM')

    def mark_old(self, legacy_launcher=False):
        (self.app/'pocketlab').write_bytes(b'old executable')
        if legacy_launcher:
            (self.app/'launch.sh').write_text('#!/bin/sh\nexit 0\n')
        (self.app/card_runtime.MANIFEST).unlink()

    def test_already_installed_route_does_not_write(self):
        with patch('card_runtime.shutil.copy', side_effect=AssertionError('Unexpected write')):
            with patch('pocketlab.install_tree', side_effect=AssertionError('Unexpected install')):
                result = card_runtime.install_runtime(RUNTIME, self.app, keep_mount)
        self.assertEqual(result, 'verified')
        self.assertFalse((self.app/'data/updates').exists())

    def test_updates_and_restores_runtime_without_copying_user_apps_or_data(self):
        self.mark_old()
        user_files = (self.user_data, self.user_app, self.rom)
        before = {path: (path.stat().st_ino, digest(path)) for path in user_files}
        original = card_runtime.copy_file

        def forbid_user_copy(source, destination):
            self.assertNotIn(source, user_files)
            return original(source, destination)

        with patch('card_runtime.copy_file', side_effect=forbid_user_copy):
            self.assertEqual(card_runtime.install_runtime(RUNTIME, self.app, keep_mount), 'updated')
        token, phase = card_runtime.pending_update(self.app)
        self.assertEqual(phase, 'ready')
        self.assertEqual(card_runtime.install_runtime(RUNTIME, self.app, keep_mount), 'verified')
        self.assertEqual(digest(self.app/'pocketlab'), digest(RUNTIME/'pocketlab'))
        with patch('card_runtime.copy_file', side_effect=forbid_user_copy):
            restore_card(self.card, token)
        self.assertEqual((self.app/'pocketlab').read_bytes(), b'old executable')
        self.assertFalse((self.app/card_runtime.MANIFEST).exists())
        self.assertIsNone(card_runtime.pending_update(self.app))
        self.assertEqual(before, {path: (path.stat().st_ino, digest(path)) for path in user_files})

    def test_failed_update_restores_previous_runtime_and_preserves_user_files(self):
        self.mark_old(legacy_launcher=True)
        old_launcher = (self.app/'launch.sh').read_bytes()
        original = Path.replace

        def interrupt(path, target):
            if '.incoming' in path.parts and path.name == 'pocketlab':
                self.assertNotEqual((self.app/'launch.sh').read_bytes(), old_launcher)
                raise OSError('Interruption while replacing the binary')
            return original(path, target)

        with patch.object(Path, 'replace', interrupt):
            with self.assertRaisesRegex(OSError, 'Interruption'):
                card_runtime.install_runtime(RUNTIME, self.app, keep_mount)
        self.assertEqual((self.app/'launch.sh').read_bytes(), old_launcher)
        self.assertEqual((self.app/'pocketlab').read_bytes(), b'old executable')
        self.assertEqual(self.user_app.read_bytes(), b'personal app')
        self.assertIsNone(card_runtime.pending_update(self.app))

    def test_pending_copy_requires_recovery_before_updating(self):
        (self.app/card_runtime.PENDING).write_text('0'*32+' copying\n')
        with self.assertRaisesRegex(ValueError, 'needs recovery'):
            card_runtime.install_runtime(RUNTIME, self.app, keep_mount)
        self.assertEqual(self.user_app.read_bytes(), b'personal app')
        self.assertFalse((self.app/'data/updates').exists())
        check = onboarding.diagnostics(sd=self.card)['checks'][-1]
        self.assertFalse(check['ok'])
        self.assertIn('recover --sd', check['action'])

    def test_corrupt_backup_is_rejected_before_runtime_is_touched(self):
        self.mark_old()
        card_runtime.install_runtime(RUNTIME, self.app, keep_mount)
        token, _ = card_runtime.pending_update(self.app)
        (self.app/'data/updates'/token/'pocketlab').write_bytes(b'corrupted snapshot')
        with self.assertRaisesRegex(ValueError, 'Backup checksum mismatch'):
            restore_card(self.card, token)
        self.assertEqual(digest(self.app/'pocketlab'), digest(RUNTIME/'pocketlab'))
        self.assertIsNotNone(card_runtime.pending_update(self.app))


class MacMetadataTests(CardFixture):
    DOUBLE = card_io.APPLEDOUBLE + bytes(4092)

    def test_tree_removal_tolerates_companions_that_vanish_with_their_file(self):
        # Python 3.9-3.12 rmtree raises here (found on a real card); 3.13+ ignores it internally.
        tree = self.card/'.pocketlab-preparing'
        (tree/'stock').mkdir(parents=True)
        (tree/'._stock').write_bytes(self.DOUBLE)
        (tree/'state.json').write_text('{}')
        real_unlink = os.unlink

        def macos_unlink(name, *args, **kwargs):
            # macOS removes ._NAME together with NAME; a later unlink finds nothing.
            real_unlink(name, *args, **kwargs)
            if os.path.basename(name).startswith('._'):
                raise FileNotFoundError(2, 'No such file or directory', name)

        with patch('os.unlink', macos_unlink):
            card_io.remove_tree(tree)
        self.assertFalse(tree.exists())

    def test_only_appledouble_companions_of_written_paths_are_removed(self):
        (self.card/'Apps/PocketLab').mkdir(parents=True)
        (self.card/'Apps/PocketLab/icon.png').write_bytes(b'png')
        (self.card/'Apps/PocketLab/._icon.png').write_bytes(self.DOUBLE)
        (self.card/'Apps/._PocketLab').write_bytes(self.DOUBLE)
        (self.card/'Apps/PocketLab/._notes.txt').write_bytes(self.DOUBLE)  # not written by PocketLAB
        (self.card/'Apps/PocketLab/._readme').write_bytes(b'user file, not AppleDouble')
        with patch('card_io.sys.platform', 'darwin'):
            removed = card_io.strip_appledouble(self.card, ['Apps/PocketLab', 'Apps/PocketLab/icon.png', 'Apps/PocketLab/readme'])
        self.assertEqual(removed, 2)
        self.assertEqual(sorted(p.name for p in (self.card/'Apps/PocketLab').iterdir()), ['._notes.txt', '._readme', 'icon.png'])
        self.assertFalse((self.card/'Apps/._PocketLab').exists())
        with patch('card_io.sys.platform', 'linux'):
            self.assertEqual(card_io.strip_appledouble(self.card, ['Apps/PocketLab/notes.txt']), 0)


class SetupEntryTests(CardFixture):
    def test_setup_offers_the_connected_working_card_first(self):
        (self.card/'Apps').mkdir()
        (self.card/'Roms').mkdir()
        card = onboarding.MountedCard(self.card, '/dev/fixture', '', 'test', 'CARD', 8000000000, True, self.card.stat().st_dev)
        with patch('onboarding.discover_cards', return_value=[card]), patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', side_effect=['', '']), patch('onboarding.setup_card') as install, \
                patch('onboarding.stock_base', side_effect=AssertionError('Working card accessed stock files')):
            onboarding.guided_setup()
        install.assert_called_once_with(self.card, selected=card)
        self.assertIn('CARD (8.0 GB', self.output.getvalue())

    def test_guided_blank_card_requires_a_positive_selection_before_copying(self):
        card = onboarding.MountedCard(self.card, '/dev/fixture', '', 'test', 'BLANK', 8000000000, True, self.card.stat().st_dev)
        with patch('onboarding.discover_cards', return_value=[card]), patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', side_effect=['', 'n']), patch('onboarding.prepare_card') as prepare:
            onboarding.guided_setup()
        prepare.assert_not_called()
        self.assertIn('Prepare new FAT32 card', self.output.getvalue())
        self.assertEqual(list(self.card.iterdir()), [])

    def test_guided_setup_routes_an_interrupted_card_to_resume(self):
        (self.card/stock_card.WORK).mkdir()
        card = onboarding.MountedCard(self.card, '/dev/fixture', '', 'test', 'CARD', 8000000000, True, self.card.stat().st_dev)
        with patch('onboarding.discover_cards', return_value=[card]), patch('sys.stdin.isatty', return_value=True), \
                patch('builtins.input', side_effect=['', 'n']), patch('onboarding.prepare_card') as prepare:
            onboarding.guided_setup()
        prepare.assert_called_once_with(self.card, resume=True, selected=card)
        self.assertIn('Resume card preparation', self.output.getvalue())

    def fixture_card(self, label='CARD'):
        return onboarding.MountedCard(self.card, '/dev/fixture', '', 'test', label, 8000000000, True, self.card.stat().st_dev)

    def test_card_listing_names_one_command_for_each_card_state(self):
        card = self.fixture_card()
        self.assertEqual(onboarding.card_report(card)['state'], 'blank')
        self.assertIn('prepare-card --sd', onboarding.card_report(card)['next'])
        (self.card/'Apps').mkdir()
        (self.card/'Roms').mkdir()
        report = onboarding.card_report(card)
        self.assertEqual((report['state'], report['installed_version']), ('stock', None))
        self.assertTrue(report['next'].startswith('./pocketlab setup --sd ') and report['next'].endswith(' --eject'))
        shutil.copytree(RUNTIME, self.card/'Apps/PocketLab')
        report = onboarding.card_report(card)
        self.assertEqual(report['state'], 'stock-with-pocketlab')
        self.assertEqual(report['installed_version'], json.loads((RUNTIME/'build-info.json').read_text())['version'])
        (self.card/stock_card.WORK).mkdir()
        self.assertEqual(onboarding.card_report(card)['state'], 'unfinished-preparation')

    def test_card_listing_never_offers_to_prepare_an_unknown_card(self):
        (self.card/'Photos').mkdir()
        report = onboarding.card_report(self.fixture_card())
        self.assertEqual(report['state'], 'not-a-trimui-card')
        self.assertIsNone(report['next'])

    def test_macos_privacy_refusal_is_explained(self):
        card = self.fixture_card()
        with patch('onboarding.card_mode', side_effect=PermissionError(1, 'Operation not permitted')), \
                patch('onboarding.platform.system', return_value='Darwin'):
            report = onboarding.card_report(card)
        self.assertEqual(report['state'], 'unreadable')
        self.assertIn('Removable Volumes', report['note'])
        self.assertIsNone(report['next'])

    def test_card_listing_json_and_empty_status(self):
        card = self.fixture_card('POCKETLAB')
        with patch('onboarding.discover_cards', return_value=[card]):
            self.assertEqual(onboarding.list_cards(as_json=True), 0)
        listing = json.loads(self.output.getvalue())
        self.assertEqual(listing['cards'][0]['label'], 'POCKETLAB')
        with patch('onboarding.discover_cards', return_value=[]):
            self.assertEqual(onboarding.list_cards(), 1)
        self.assertIn('No mounted external SD card', self.output.getvalue())

    def test_eject_waits_for_spotlight_and_never_fails_a_finished_setup(self):
        card = self.fixture_card()
        self.enterContext(patch('onboarding.recheck_card'))
        busy = subprocess.CompletedProcess([], 1, '', 'Unmount was dissented by PID 404 (mds)\n')
        done = subprocess.CompletedProcess([], 0, '', '')
        with patch('onboarding.subprocess.run', side_effect=[busy, busy, done]) as run, patch('onboarding.time.sleep'):
            onboarding.finish_card(card, eject=True)
        self.assertEqual(run.call_count, 3)
        self.assertIn('Card ejected', self.output.getvalue())
        with patch('onboarding.subprocess.run', return_value=busy), patch('onboarding.time.sleep'), \
                redirect_stderr(io.StringIO()) as stderr:
            onboarding.finish_card(card, eject=True)
        self.assertIn('dissented', stderr.getvalue())
        self.assertIn('Eject the card in your file manager', stderr.getvalue())

    def test_card_lock_is_released_after_interruption(self):
        key = f'test-{os.getpid()}'
        with self.assertRaises(KeyboardInterrupt):
            with exclusive_lock(key):
                with self.assertRaisesRegex(ValueError, 'Another PocketLAB process'):
                    with exclusive_lock(key):
                        self.fail('Two owners held the card lock')
                raise KeyboardInterrupt
        with exclusive_lock(key):
            pass

    def test_prepare_card_interrupt_reports_failure_not_watch_status(self):
        args = ['pocketlab.py', 'prepare-card', '--sd', str(self.card), '--new-card']
        with patch.object(sys, 'argv', args), patch('onboarding.prepare_card', side_effect=KeyboardInterrupt):
            with redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit) as status:
                runpy.run_path(str(ROOT/'tools/pocketlab.py'), run_name='__main__')
        self.assertEqual(status.exception.code, 130)
        self.assertIn('interrupted', stderr.getvalue())
        self.assertNotIn('Stopped watching', self.output.getvalue())


if __name__ == '__main__':
    unittest.main()
